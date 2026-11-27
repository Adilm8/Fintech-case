"""Tests for prod extensions: profile, password, company/users, settings/threshold, notifications, CSV/PDF export."""

from __future__ import annotations

import csv
import io
import json
import re
import zlib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.prod import export_service, policy
from app.prod.app import create_prod_app
from app.prod.audit_db import list_audit, verify_chain
from app.prod.db import MIGRATIONS_DIR, connect, get_schema_version, migrate, tx
from app.prod.deps import CSRF_HEADER_NAME, CSRF_HEADER_VALUE
from app.settings import Settings
from app.store import DEFAULT_DATA_DIR
from tests.prod.conftest import TEST_SEED_PW, TEST_TODAY, build_sign_payload

CSRF: dict[str, str] = {CSRF_HEADER_NAME: CSRF_HEADER_VALUE}


def _load_queue_by_id() -> dict[str, dict[str, Any]]:
    raw = json.loads((DEFAULT_DATA_DIR / "queue.json").read_text(encoding="utf-8"))
    return {item["id"]: item for item in raw}


def _to_payment_input(item: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "recipient_name": item["recipient_name"],
        "recipient_bin": item["recipient_bin"],
        "recipient_iik": item["recipient_iik"],
        "recipient_bik": item["recipient_bik"],
        "amount_kzt": item["amount_kzt"],
        "purpose": item.get("purpose", ""),
        "kbe": item.get("kbe", ""),
        "knp": item.get("knp", ""),
        "doc_number": item.get("id", ""),
        "doc_date": TEST_TODAY.isoformat(),
    }
    payload.update(overrides)
    return payload


def _login(client: TestClient, login: str, password: str = TEST_SEED_PW) -> None:
    resp = client.post(
        "/api/v1/auth/login",
        json={"login": login, "password": password},
        headers=CSRF,
    )
    assert resp.status_code == 200, resp.text


@pytest.fixture
def ext_env(seeded_db: Path) -> Iterator[tuple[FastAPI, Path, TestClient, TestClient, TestClient]]:
    cfg = Settings(
        app_mode="prod",
        db_path=seeded_db,
        today_override=TEST_TODAY,
        cookie_secure=False,
    )
    prod_app = create_prod_app(db_path=seeded_db, settings_override=cfg)
    with (
        TestClient(prod_app) as acc,
        TestClient(prod_app) as director,
        TestClient(prod_app) as analyst,
    ):
        _login(acc, "accountant")
        _login(director, "director")
        _login(analyst, "analyst")
        yield prod_app, seeded_db, acc, director, analyst


class TestMigration002Upgrade:
    def test_upgrade_from_001_to_002_preserves_existing_rows(self, tmp_path: Path) -> None:
        db_file = tmp_path / "upgrade.db"
        conn = connect(db_file)
        try:
            # Apply only 001_init.sql directly
            sql_001 = (MIGRATIONS_DIR / "001_init.sql").read_text(encoding="utf-8")
            conn.executescript(f"BEGIN IMMEDIATE;\n{sql_001}\nCOMMIT;")
            assert get_schema_version(conn) == 1

            ts = "2026-11-26T10:00:00+00:00"
            with tx(conn):
                conn.execute(
                    "INSERT INTO companies (id, name, bin, iik, bik, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    ("c1", "ТОО Альфа", "111111111111", "KZ86125KZT5004100100", "KCJBKZKX", ts),
                )
                conn.execute(
                    "INSERT INTO users (id, company_id, login, full_name, role, password_hash, created_at) "
                    "VALUES (1, 'c1', 'dir1', 'Директор', 'director', 'scrypt$15$8$1$AA==$AA==', ?)",
                    (ts,),
                )

            # Now run migrate() -> applies pending migrations cleanly
            assert migrate(conn) == 3
            assert get_schema_version(conn) == 3

            user_row = conn.execute("SELECT login, default_lang FROM users WHERE id = 1").fetchone()
            assert user_row is not None
            assert user_row["login"] == "dir1"
            assert user_row["default_lang"] == "ru"
        finally:
            conn.close()


class TestProfileAndPassword:
    def test_get_and_put_profile_updates_user_and_writes_audit(
        self, ext_env: tuple[FastAPI, Path, TestClient, TestClient, TestClient]
    ) -> None:
        prod_app, db_path, acc, _, analyst = ext_env

        # Unauthenticated -> 401
        with TestClient(prod_app) as anon:
            assert anon.get("/api/v1/me").status_code == 401

        # Initial profile
        me = acc.get("/api/v1/me")
        assert me.status_code == 200
        data = me.json()
        assert data["login"] == "accountant"
        assert data["default_lang"] == "ru"
        assert data["company"]["id"] == "client-technostroy"

        # Update full_name + default_lang
        upd = acc.put(
            "/api/v1/me",
            json={"full_name": "Айгуль Нурланова-Серик", "default_lang": "kk"},
            headers=CSRF,
        )
        assert upd.status_code == 200
        upd_data = upd.json()
        assert upd_data["full_name"] == "Айгуль Нурланова-Серик"
        assert upd_data["default_lang"] == "kk"

        # Existing /auth/me remains backwards-compatible and reflects updated full_name
        auth_me = acc.get("/api/v1/auth/me").json()
        assert auth_me["user"]["full_name"] == "Айгуль Нурланова-Серик"
        assert set(auth_me["user"].keys()) == {"id", "login", "full_name", "role", "company_id"}

        # Analyst can also view/update own profile (company is None)
        ana_me = analyst.get("/api/v1/me").json()
        assert ana_me["company"] is None
        ana_upd = analyst.put("/api/v1/me", json={"default_lang": "en"}, headers=CSRF)
        assert ana_upd.status_code == 200
        assert ana_upd.json()["default_lang"] == "en"

        conn = connect(db_path)
        try:
            entries = list_audit(conn, action="profile_updated", limit=10)
            assert len(entries) == 2
            assert verify_chain(conn).ok is True
        finally:
            conn.close()

    def test_change_password_scrypt_revokes_other_sessions_and_audits(
        self, ext_env: tuple[FastAPI, Path, TestClient, TestClient, TestClient]
    ) -> None:
        prod_app, db_path, acc_primary, _, _ = ext_env

        # Open a second session for the same user
        with TestClient(prod_app) as acc_other:
            _login(acc_other, "accountant")
            assert acc_other.get("/api/v1/me").status_code == 200

            # Wrong current password -> 400 invalid_current_password + audit
            bad_cur = acc_primary.post(
                "/api/v1/me/password",
                json={"current_password": "WrongPassword99!", "new_password": "New-Pass-2027!"},
                headers=CSRF,
            )
            assert bad_cur.status_code == 400
            assert bad_cur.json()["code"] == "invalid_current_password"

            # Same password -> 422 password_same_as_current
            same_pw = acc_primary.post(
                "/api/v1/me/password",
                json={"current_password": TEST_SEED_PW, "new_password": TEST_SEED_PW},
                headers=CSRF,
            )
            assert same_pw.status_code == 422
            assert same_pw.json()["code"] == "password_same_as_current"

            # Too short new password -> 422 validation_error
            short_pw = acc_primary.post(
                "/api/v1/me/password",
                json={"current_password": TEST_SEED_PW, "new_password": "short"},
                headers=CSRF,
            )
            assert short_pw.status_code == 422
            assert short_pw.json()["code"] == "validation_error"

            # Valid password change -> revokes other session, preserves current session
            new_password = "New-Strong-Pass-2027!"
            ok = acc_primary.post(
                "/api/v1/me/password",
                json={"current_password": TEST_SEED_PW, "new_password": new_password},
                headers=CSRF,
            )
            assert ok.status_code == 200
            assert ok.json() == {"ok": True, "revoked_sessions": 1}

            # Current session still valid
            assert acc_primary.get("/api/v1/me").status_code == 200
            # Other session revoked -> 401
            assert acc_other.get("/api/v1/me").status_code == 401

        # Old password rejected, new password works
        with TestClient(prod_app) as fresh:
            r_old = fresh.post(
                "/api/v1/auth/login",
                json={"login": "accountant", "password": TEST_SEED_PW},
                headers=CSRF,
            )
            assert r_old.status_code == 401
            r_new = fresh.post(
                "/api/v1/auth/login",
                json={"login": "accountant", "password": new_password},
                headers=CSRF,
            )
            assert r_new.status_code == 200

        # Verify scrypt format, no plaintext secrets in audit log, and hash chain ok
        conn = connect(db_path)
        try:
            row = conn.execute(
                "SELECT password_hash FROM users WHERE login = 'accountant'"
            ).fetchone()
            assert row is not None
            assert str(row["password_hash"]).startswith("scrypt$15$8$1$")
            assert new_password not in str(row["password_hash"])

            changed_logs = list_audit(conn, action="password_changed", limit=5)
            assert len(changed_logs) == 1
            assert changed_logs[0].details["revoked_sessions"] == 1
            failed_logs = list_audit(conn, action="password_change_failed", limit=5)
            assert len(failed_logs) == 1

            all_details = " ".join(
                str(r["details_json"])
                for r in conn.execute("SELECT details_json FROM audit_log").fetchall()
            )
            assert new_password not in all_details
            assert TEST_SEED_PW not in all_details
            assert verify_chain(conn).ok is True
        finally:
            conn.close()


class TestCompanyAndUserManagement:
    def test_company_read_invite_update_and_last_director_protection(
        self, ext_env: tuple[FastAPI, Path, TestClient, TestClient, TestClient]
    ) -> None:
        prod_app, db_path, acc, director, analyst = ext_env

        # Accountant and director can view company; analyst gets 403
        acc_comp = acc.get("/api/v1/company")
        assert acc_comp.status_code == 200
        comp_data = acc_comp.json()
        assert comp_data["name"]
        assert comp_data["bin"]
        assert len(comp_data["users"]) == 2
        assert all("password" not in u and "password_hash" not in u for u in comp_data["users"])

        assert director.get("/api/v1/company").status_code == 200
        assert analyst.get("/api/v1/company").status_code == 403

        # Only director can invite or update users
        assert (
            acc.post(
                "/api/v1/company/users",
                json={"login": "acc2", "full_name": "Новый Бухгалтер", "role": "accountant"},
                headers=CSRF,
            ).status_code
            == 403
        )
        assert (
            analyst.post(
                "/api/v1/company/users",
                json={"login": "acc2", "full_name": "Новый Бухгалтер", "role": "accountant"},
                headers=CSRF,
            ).status_code
            == 403
        )

        # Find current director ID
        dir_user = next(u for u in comp_data["users"] if u["role"] == "director")
        dir_id = dir_user["id"]

        # Last director CANNOT be demoted or deactivated
        demote_last = director.put(
            f"/api/v1/company/users/{dir_id}",
            json={"role": "accountant"},
            headers=CSRF,
        )
        assert demote_last.status_code == 409
        assert demote_last.json()["code"] == "last_director_protected"

        deact_last = director.put(
            f"/api/v1/company/users/{dir_id}",
            json={"active": False},
            headers=CSRF,
        )
        assert deact_last.status_code == 409
        assert deact_last.json()["code"] == "last_director_protected"

        # Director invites a second director -> returns temporary_password once
        inv = director.post(
            "/api/v1/company/users",
            json={"login": "director2", "full_name": "Аскар Беков", "role": "director"},
            headers=CSRF,
        )
        assert inv.status_code == 201
        inv_data = inv.json()
        temp_pw = inv_data["temporary_password"]
        assert isinstance(temp_pw, str) and len(temp_pw) >= 12
        dir2_id = inv_data["user"]["id"]
        assert inv_data["user"]["role"] == "director"
        assert inv_data["user"]["is_active"] is True

        # Duplicate login (case-insensitive) -> 409 invalid_login
        dup_inv = director.post(
            "/api/v1/company/users",
            json={"login": "DIRECTOR2", "full_name": "Дубль", "role": "accountant"},
            headers=CSRF,
        )
        assert dup_inv.status_code == 409
        assert dup_inv.json()["code"] == "invalid_login"

        # Invited user logs in with temp password and changes it before accessing /me
        with TestClient(prod_app) as dir2_client:
            _login(dir2_client, "director2", temp_pw)
            ch_pw = dir2_client.post(
                "/api/v1/me/password",
                json={"current_password": temp_pw, "new_password": "Dir2-Permanent-Pass-1!"},
                headers=CSRF,
            )
            assert ch_pw.status_code == 200
            assert dir2_client.get("/api/v1/me").status_code == 200

            # Now demote director2 to accountant -> allowed since director1 is still active director
            demoted = director.put(
                f"/api/v1/company/users/{dir2_id}",
                json={"role": "accountant"},
                headers=CSRF,
            )
            assert demoted.status_code == 200
            assert demoted.json()["role"] == "accountant"

            # Promote back to director, then deactivate director2 -> revokes their session immediately
            assert (
                director.put(
                    f"/api/v1/company/users/{dir2_id}",
                    json={"role": "director"},
                    headers=CSRF,
                ).status_code
                == 200
            )
            deact2 = director.put(
                f"/api/v1/company/users/{dir2_id}",
                json={"is_active": False},
                headers=CSRF,
            )
            assert deact2.status_code == 200
            assert deact2.json()["is_active"] is False
            assert dir2_client.get("/api/v1/me").status_code == 401

        # Cross-company user cannot be edited (404 not_found)
        conn = connect(db_path)
        try:
            other_row = conn.execute(
                "SELECT id FROM users WHERE login = 'other_accountant'"
            ).fetchone()
            assert other_row is not None
            other_id = int(other_row["id"])
        finally:
            conn.close()

        cross = director.put(
            f"/api/v1/company/users/{other_id}",
            json={"role": "director"},
            headers=CSRF,
        )
        assert cross.status_code == 404
        assert cross.json()["code"] == "not_found"

        # Verify audit entries and that temporary_password is NEVER stored in audit_log
        conn = connect(db_path)
        try:
            assert len(list_audit(conn, action="user_invited", limit=10)) == 1
            assert len(list_audit(conn, action="company_user_updated", limit=10)) == 3
            raw_audit = " ".join(
                str(r["details_json"])
                for r in conn.execute("SELECT details_json FROM audit_log").fetchall()
            )
            assert temp_pw not in raw_audit
            assert verify_chain(conn).ok is True
        finally:
            conn.close()


class TestCompanySettingsAndThresholdPolicy:
    def test_sign_policy_threshold_unit(self) -> None:
        sha = "sha-1"
        # Green below threshold -> allowed
        below = policy.sign_decision(
            role="accountant",
            status="checked",
            previous_verdict="green",
            fresh_verdict="green",
            payment_request_sha256=sha,
            approval_status=None,
            approval_request_sha256=None,
            accountant_ack=False,
            amount_tiyn=99_999_900,
            approval_threshold_tiyn=100_000_000,
        )
        assert below.allowed is True

        # Green equal to threshold -> blocked with threshold_requires_approval
        at_thresh = policy.sign_decision(
            role="accountant",
            status="checked",
            previous_verdict="green",
            fresh_verdict="green",
            payment_request_sha256=sha,
            approval_status=None,
            approval_request_sha256=None,
            accountant_ack=False,
            amount_tiyn=100_000_000,
            approval_threshold_tiyn=100_000_000,
        )
        assert not at_thresh.allowed and at_thresh.block_code == "threshold_requires_approval"

        # Yellow >= threshold even with accountant_ack=True -> threshold_requires_approval
        yellow_thresh = policy.sign_decision(
            role="accountant",
            status="checked",
            previous_verdict="yellow",
            fresh_verdict="yellow",
            payment_request_sha256=sha,
            approval_status=None,
            approval_request_sha256=None,
            accountant_ack=True,
            amount_tiyn=150_000_000,
            approval_threshold_tiyn=100_000_000,
        )
        assert not yellow_thresh.allowed and yellow_thresh.block_code == "threshold_requires_approval"

        # Red >= threshold still returns red_requires_approval
        red_thresh = policy.sign_decision(
            role="accountant",
            status="checked",
            previous_verdict="red",
            fresh_verdict="red",
            payment_request_sha256=sha,
            approval_status=None,
            approval_request_sha256=None,
            accountant_ack=False,
            amount_tiyn=150_000_000,
            approval_threshold_tiyn=100_000_000,
        )
        assert not red_thresh.allowed and red_thresh.block_code == "red_requires_approval"

        # Approved green >= threshold -> allowed
        approved_thresh = policy.sign_decision(
            role="accountant",
            status="approved",
            previous_verdict="green",
            fresh_verdict="green",
            payment_request_sha256=sha,
            approval_status="approved",
            approval_request_sha256=sha,
            accountant_ack=False,
            amount_tiyn=150_000_000,
            approval_threshold_tiyn=100_000_000,
        )
        assert approved_thresh.allowed is True

    def test_settings_and_threshold_enforcement_in_sign_and_sign_green(
        self, ext_env: tuple[FastAPI, Path, TestClient, TestClient, TestClient]
    ) -> None:
        _, db_path, acc, director, analyst = ext_env
        queue = _load_queue_by_id()

        # Role guards: accountant and analyst get 403
        assert acc.get("/api/v1/company/settings").status_code == 403
        assert acc.put("/api/v1/company/settings", json={"notify_on": "red"}, headers=CSRF).status_code == 403
        assert analyst.get("/api/v1/company/settings").status_code == 403

        # Defaults
        default_cfg = director.get("/api/v1/company/settings").json()
        assert default_cfg["notify_on"] == "red_yellow"
        assert default_cfg["approval_threshold_kzt"] is None

        # Pick two green queue items with different natural amounts and place threshold between them
        q_small, q_large = sorted(
            (queue["Q-008"], queue["Q-001"]),
            key=lambda item: float(item["amount_kzt"]),
        )
        small_amt = float(q_small["amount_kzt"])
        large_amt = float(q_large["amount_kzt"])
        assert small_amt < large_amt
        threshold_kzt = large_amt  # exact boundary: payment == threshold must require approval

        put_cfg = director.put(
            "/api/v1/company/settings",
            json={"notify_on": "red_yellow", "approval_threshold_kzt": threshold_kzt},
            headers=CSRF,
        )
        assert put_cfg.status_code == 200
        assert put_cfg.json()["approval_threshold_kzt"] == threshold_kzt

        p_small = acc.post(
            "/api/v1/payments",
            json=_to_payment_input(q_small),
            headers=CSRF,
        ).json()
        p_large = acc.post(
            "/api/v1/payments",
            json=_to_payment_input(q_large),
            headers=CSRF,
        ).json()
        assert p_small["check"]["verdict"] == "green"
        assert p_large["check"]["verdict"] == "green"
        assert p_small["permissions"]["can_sign"] is True
        assert p_small["permissions"]["sign_block_code"] is None
        assert p_large["permissions"]["can_sign"] is False
        assert p_large["permissions"]["sign_block_code"] == "threshold_requires_approval"
        assert p_large["permissions"]["can_send_to_director"] is True

        # Direct sign of large green -> 409 threshold_requires_approval (accountant AND director)
        r_acc_sign = acc.post(
            f"/api/v1/payments/{p_large['id']}/sign",
            json=build_sign_payload(acc, p_large["id"]),
            headers=CSRF,
        )
        assert r_acc_sign.status_code == 409
        assert r_acc_sign.json()["code"] == "threshold_requires_approval"

        r_dir_sign = director.post(
            f"/api/v1/payments/{p_large['id']}/sign",
            json=build_sign_payload(director, p_large["id"]),
            headers=CSRF,
        )
        assert r_dir_sign.status_code == 409
        assert r_dir_sign.json()["code"] == "threshold_requires_approval"

        # Batch sign-green signs small green and skips large green with threshold_requires_approval
        sg = acc.post(
            "/api/v1/payments/batch/sign-green",
            json={"payment_ids": [p_small["id"], p_large["id"]]},
            headers=CSRF,
        )
        assert sg.status_code == 200
        sg_body = sg.json()
        assert [p["id"] for p in sg_body["done"]] == [p_small["id"]]
        assert len(sg_body["skipped"]) == 1
        assert sg_body["skipped"][0]["id"] == p_large["id"]
        assert sg_body["skipped"][0]["code"] == "threshold_requires_approval"

        # Batch send-to-director sends the threshold-blocked green payment
        sd = acc.post(
            "/api/v1/payments/batch/send-to-director",
            json={"payment_ids": [p_large["id"]], "accountant_note": "Сумма выше порога"},
            headers=CSRF,
        )
        assert sd.status_code == 200
        assert [p["id"] for p in sd.json()["done"]] == [p_large["id"]]
        apr_id = sd.json()["done"][0]["approval"]["id"]

        # Director approves -> now signing succeeds
        dec = director.post(
            f"/api/v1/approvals/{apr_id}/decision",
            json={"decision": "approved", "director_comment": "Согласовано по лимиту"},
            headers=CSRF,
        )
        assert dec.status_code == 200
        signed_after = acc.post(
            f"/api/v1/payments/{p_large['id']}/sign",
            json=build_sign_payload(acc, p_large["id"]),
            headers=CSRF,
        )
        assert signed_after.status_code == 200
        assert signed_after.json()["status"] == "signed"

        # Clearing threshold with null restores normal green signing
        clear_cfg = director.put(
            "/api/v1/company/settings",
            json={"approval_threshold_kzt": None},
            headers=CSRF,
        )
        assert clear_cfg.status_code == 200
        assert clear_cfg.json()["approval_threshold_kzt"] is None

        conn = connect(db_path)
        try:
            assert len(list_audit(conn, action="company_settings_updated", limit=10)) == 2
            denied = list_audit(conn, payment_id=p_large["id"], action="sign_denied", limit=10)
            assert any(e.details.get("code") == "threshold_requires_approval" for e in denied)
            assert verify_chain(conn).ok is True
        finally:
            conn.close()


class TestNotifications:
    def test_notifications_derived_respects_notify_on_and_mark_read(
        self, ext_env: tuple[FastAPI, Path, TestClient, TestClient, TestClient]
    ) -> None:
        _, db_path, acc, director, analyst = ext_env
        queue = _load_queue_by_id()

        # Create yellow (Q-002) and red (Q-003) payments
        p_yellow = acc.post("/api/v1/payments", json=_to_payment_input(queue["Q-002"]), headers=CSRF).json()
        p_red = acc.post("/api/v1/payments", json=_to_payment_input(queue["Q-003"]), headers=CSRF).json()
        assert p_yellow["check"]["verdict"] == "yellow"
        assert p_red["check"]["verdict"] == "red"

        # Trigger sign_denied on both yellow (no ack) and red
        assert (
            acc.post(
                f"/api/v1/payments/{p_yellow['id']}/sign",
                json=build_sign_payload(acc, p_yellow["id"]),
                headers=CSRF,
            ).status_code
            == 409
        )
        assert (
            acc.post(
                f"/api/v1/payments/{p_red['id']}/sign",
                json=build_sign_payload(acc, p_red["id"]),
                headers=CSRF,
            ).status_code
            == 409
        )

        # Send both to director
        apr_y = acc.post(
            f"/api/v1/payments/{p_yellow['id']}/send-to-director",
            json={"accountant_note": "Жёлтый"},
            headers=CSRF,
        ).json()["approval"]["id"]
        apr_r = acc.post(
            f"/api/v1/payments/{p_red['id']}/send-to-director",
            json={"accountant_note": "Красный"},
            headers=CSRF,
        ).json()["approval"]["id"]

        # With default notify_on='red_yellow', director sees both pending approvals + both sign_denied
        dir_notifs = director.get("/api/v1/notifications?lang=kk").json()
        assert dir_notifs["unread_count"] == 4
        assert len(dir_notifs["items"]) == 4
        verdicts_seen = {item["verdict"] for item in dir_notifs["items"]}
        assert verdicts_seen == {"yellow", "red"}
        kinds_seen = {item["kind"] for item in dir_notifs["items"]}
        assert kinds_seen == {"approval_pending", "sign_denied"}

        # Switch notify_on to 'red' -> yellow items disappear!
        assert (
            director.put(
                "/api/v1/company/settings",
                json={"notify_on": "red"},
                headers=CSRF,
            ).status_code
            == 200
        )
        dir_red_only = director.get("/api/v1/notifications").json()
        assert dir_red_only["unread_count"] == 2
        assert all(item["verdict"] == "red" for item in dir_red_only["items"])

        # Mark a single notification as read
        first_id = dir_red_only["items"][0]["id"]
        mark_one = director.post(
            "/api/v1/notifications/read",
            json={"ids": [first_id]},
            headers=CSRF,
        )
        assert mark_one.status_code == 200
        assert mark_one.json() == {"marked": 1, "unread_count": 1}

        # Mark all remaining as read
        mark_all = director.post("/api/v1/notifications/read", json={}, headers=CSRF)
        assert mark_all.status_code == 200
        assert mark_all.json() == {"marked": 1, "unread_count": 0}

        # Restore 'red_yellow' and decide on both approvals -> accountant receives decision notifications
        assert (
            director.put(
                "/api/v1/company/settings",
                json={"notify_on": "red_yellow"},
                headers=CSRF,
            ).status_code
            == 200
        )
        assert (
            director.post(
                f"/api/v1/approvals/{apr_y}/decision",
                json={"decision": "approved", "director_comment": "Одобрено"},
                headers=CSRF,
            ).status_code
            == 200
        )
        assert (
            director.post(
                f"/api/v1/approvals/{apr_r}/decision",
                json={"decision": "rejected", "director_comment": "Подмена"},
                headers=CSRF,
            ).status_code
            == 200
        )

        acc_notifs = acc.get("/api/v1/notifications?lang=en").json()
        acc_kinds = {item["kind"] for item in acc_notifs["items"]}
        assert {"approval_approved", "approval_rejected", "sign_denied"} <= acc_kinds
        assert acc_notifs["unread_count"] == len(acc_notifs["items"])

        # Analyst sees sign_denied notifications globally
        ana_notifs = analyst.get("/api/v1/notifications").json()
        assert any(item["kind"] == "sign_denied" for item in ana_notifs["items"])

        conn = connect(db_path)
        try:
            assert len(list_audit(conn, action="notifications_read", limit=10)) == 2
            assert verify_chain(conn).ok is True
        finally:
            conn.close()


class TestPaymentsExport:
    def test_csv_export_utf8_bom_filters_and_localization(
        self, ext_env: tuple[FastAPI, Path, TestClient, TestClient, TestClient]
    ) -> None:
        prod_app, db_path, acc, _, _ = ext_env
        queue = _load_queue_by_id()

        p1 = acc.post(
            "/api/v1/payments",
            json=_to_payment_input(queue["Q-001"], doc_date="2026-11-20"),
            headers=CSRF,
        ).json()
        p2 = acc.post(
            "/api/v1/payments",
            json=_to_payment_input(queue["Q-003"], doc_date="2026-11-26"),
            headers=CSRF,
        ).json()

        # Queue CSV in Russian -> UTF-8 BOM + 2 payments + reasons & advice
        resp = acc.get("/api/v1/payments/export?format=csv&scope=queue&lang=ru")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        assert resp.content.startswith(b"\xef\xbb\xbf")

        decoded = resp.content.decode("utf-8-sig")
        rows = list(csv.reader(io.StringIO(decoded)))
        assert len(rows) == 3  # header + 2 payments
        assert rows[0][0] == "ID платежа"
        ids = {r[0] for r in rows[1:]}
        assert ids == {p1["id"], p2["id"]}
        red_row = next(r for r in rows[1:] if r[0] == p2["id"])
        assert red_row[4] == "Красный"
        assert red_row[13]  # reasons non-empty
        assert red_row[14]  # advice non-empty

        # Date range filter (from=2026-11-25&to=2026-11-26) returns only p2
        resp_range = acc.get(
            "/api/v1/payments/export?format=csv&scope=queue&from=2026-11-25&to=2026-11-26&lang=kk"
        )
        assert resp_range.status_code == 200
        rows_range = list(csv.reader(io.StringIO(resp_range.content.decode("utf-8-sig"))))
        assert len(rows_range) == 2
        assert rows_range[0][7] == "БСН/ЖСН"
        assert rows_range[0][8] == "ЖСК"
        assert rows_range[1][0] == p2["id"]

        # Invalid date range -> 422 invalid_date_range
        bad_range = acc.get(
            "/api/v1/payments/export?format=csv&from=2026-11-28&to=2026-11-20"
        )
        assert bad_range.status_code == 422
        assert bad_range.json()["code"] == "invalid_date_range"

        # Cross-company isolation: other_accountant gets header only (0 data rows)
        with TestClient(prod_app) as other_acc:
            _login(other_acc, "other_accountant")
            other_csv = other_acc.get("/api/v1/payments/export?format=csv&scope=all")
            assert other_csv.status_code == 200
            other_rows = list(csv.reader(io.StringIO(other_csv.content.decode("utf-8-sig"))))
            assert len(other_rows) == 1

        conn = connect(db_path)
        try:
            assert len(list_audit(conn, action="payments_exported", limit=10)) == 3
            assert verify_chain(conn).ok is True
        finally:
            conn.close()

    def test_pdf_export_embeds_cyrillic_ttf_and_supports_fallback(
        self, ext_env: tuple[FastAPI, Path, TestClient, TestClient, TestClient]
    ) -> None:
        _, db_path, acc, director, _ = ext_env
        queue = _load_queue_by_id()

        for qid in ("Q-001", "Q-002", "Q-003", "Q-004", "Q-007"):
            assert (
                acc.post(
                    "/api/v1/payments",
                    json=_to_payment_input(queue[qid]),
                    headers=CSRF,
                ).status_code
                == 201
            )

        # Generate PDF report in Russian and Kazakh via API
        for lang in ("ru", "kk", "en"):
            resp = director.get(f"/api/v1/payments/export?format=pdf&scope=queue&lang={lang}")
            assert resp.status_code == 200
            assert resp.headers["content-type"] == "application/pdf"
            pdf = resp.content
            assert pdf.startswith(b"%PDF-1.4\n")
            assert pdf.rstrip().endswith(b"%%EOF")
            assert b"xref\n" in pdf

            # If a system TTF font is installed (true on Windows/Linux desktops), verify Unicode Type0 + Cyrillic ToUnicode
            if export_service.find_system_ttf() is not None:
                assert b"/Subtype /Type0" in pdf
                assert b"/Subtype /CIDFontType2" in pdf
                assert b"/ToUnicode" in pdf
                if lang in ("ru", "kk"):
                    # Decompress streams and verify Cyrillic Unicode mappings exist in ToUnicode CMap
                    streams = re.findall(rb"stream\n(.*?)\nendstream", pdf, re.DOTALL)
                    cmap_text = ""
                    for s in streams:
                        try:
                            dec = zlib.decompress(s).decode("ascii", errors="ignore")
                            if "begincmap" in dec:
                                cmap_text = dec
                                break
                        except zlib.error:
                            continue
                    assert cmap_text, "Expected ToUnicode CMap stream in PDF"
                    # U+041F ('П') or U+043E ('о') must appear in bfchar mappings
                    assert "<04" in cmap_text

        # Test explicit no-TTF fallback produces valid PDF with ASCII transliteration + clear note
        conn = connect(db_path)
        try:
            # Build hydrated payments via endpoint data -> render_payments_pdf with font_paths=[]
            from app.prod import payments_service
            from app.prod.schemas import User

            u_row = conn.execute("SELECT * FROM users WHERE login = 'director'").fetchone()
            assert u_row is not None
            dir_u = User(
                id=int(u_row["id"]),
                login=str(u_row["login"]),
                full_name=str(u_row["full_name"]),
                role=u_row["role"],
                company_id=str(u_row["company_id"]),
            )
            hydrated = payments_service.list_payments_for_export(
                conn, user=dir_u, today=TEST_TODAY, scope="queue", lang="ru"
            )
            fallback_pdf = export_service.render_payments_pdf(
                hydrated,
                company_label="ТОО «ТехноСтрой Астана»",
                scope="queue",
                today=TEST_TODAY,
                lang="ru",
                font_paths=[],
            )
            assert fallback_pdf.startswith(b"%PDF-1.4\n")
            assert fallback_pdf.rstrip().endswith(b"%%EOF")
            assert b"/BaseFont /Helvetica" in fallback_pdf
            streams = re.findall(rb"stream\n(.*?)\nendstream", fallback_pdf, re.DOTALL)
            page_text = b"".join(zlib.decompress(s) for s in streams)
            assert b"No Cyrillic TTF font found" in page_text
            assert verify_chain(conn).ok is True
        finally:
            conn.close()

    @pytest.mark.parametrize("prefix", ["=", "+", "-", "@", "\t", "\r"])
    def test_csv_export_neutralizes_formula_injection_prefixes_and_keeps_numbers(
        self, prefix: str
    ) -> None:
        from app.prod.schemas import (
            ApprovalBrief,
            Payment,
            PaymentPermissions,
            SupplierRef,
            UserBrief,
        )
        from app.schemas import (
            CheckRequest,
            CheckResult,
            Evidence,
            HistorySummary,
            NextAction,
            Signal,
        )

        user = UserBrief(id=1, login="accountant", full_name="Айгуль Нурланова", role="accountant")
        # Use model_construct for request so we also verify a negative numeric amount stays numeric.
        req = CheckRequest.model_construct(
            payer_id="client-technostroy",
            recipient_name=f"{prefix}CMD|' /C calc'!A0",
            recipient_bin="160542439625",
            recipient_iik="KZ246010005016525808",
            recipient_bik="HSBKKZKX",
            amount_kzt=-1500.5,
            purpose=f"{prefix}HYPERLINK(\"http://example.test\")",
            kbe="17",
            knp="710",
        )
        chk = CheckResult(
            check_id="chk-csv-1",
            verdict="yellow",
            score=45,
            headline_ru=f"{prefix}Заголовок",
            headline=f"{prefix}Заголовок",
            signals=[
                Signal(
                    rule_id="iik_changed",
                    points=35,
                    severity="primary",
                    reason_ru=f"{prefix}Причина",
                    reason=f"{prefix}Причина",
                    evidence=Evidence(field="iik"),
                )
            ],
            comparison=[],
            next_action=NextAction(
                text_ru=f"{prefix}Совет",
                text=f"{prefix}Совет",
                primary="send_to_director",
            ),
            history=HistorySummary(payments_count=1),
        )
        payment = Payment.model_construct(
            id="pay-csv-inj",
            company_id="client-technostroy",
            status="checked",
            source="manual",
            batch_id=None,
            line_no=None,
            doc_number=f"{prefix}DOC-1",
            doc_date="2026-11-26",
            request=req,
            check=chk,
            approval=ApprovalBrief.model_construct(
                id="apr-1",
                status=f"{prefix}approved",
                accountant_note="",
                director_comment=f"{prefix}comment",
                trust_account=False,
                created_by=user,
                created_at="2026-11-26T10:00:00+00:00",
                decided_by=None,
                decided_at=None,
            ),
            accountant_ack=False,
            supplier=SupplierRef(
                id=1,
                known=True,
                account_known=False,
                requisites_changed_days_ago=None,
            ),
            duplicate_of=None,
            permissions=PaymentPermissions(
                can_edit=True,
                can_sign=False,
                sign_requires_ack=False,
                sign_block_code=None,
                can_send_to_director=True,
                can_postpone=True,
                can_resume=False,
                can_cancel=True,
                can_decide=False,
            ),
            created_by=user,
            created_at="2026-11-26T10:00:00+00:00",
            updated_at="2026-11-26T10:00:00+00:00",
            signed_by=None,
            signed_at=None,
        )

        raw = export_service.render_payments_csv([payment], lang="ru")
        rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
        assert len(rows) == 2
        row = rows[1]

        # Every free-text cell starting with a formula prefix is neutralized with a leading single quote
        for idx in (2, 6, 11, 12, 13, 14, 15):
            assert row[idx].startswith("'"), f"Col {idx} was not neutralized for {prefix!r}: {row[idx]!r}"

        # Numeric columns stay numeric (including negative amount)
        assert row[5] == "45"
        assert row[10] == "-1500.50"

    def test_csv_export_leaves_normal_values_untouched_and_neutralizes_via_api(
        self, ext_env: tuple[FastAPI, Path, TestClient, TestClient, TestClient]
    ) -> None:
        _, _, acc, _, _ = ext_env
        queue = _load_queue_by_id()

        normal = acc.post(
            "/api/v1/payments",
            json=_to_payment_input(
                queue["Q-001"],
                recipient_name='ТОО "Алатау-Снаб"',
                doc_number="INV-101",
                purpose="Оплата по счёту № 214",
            ),
            headers=CSRF,
        ).json()
        injected = acc.post(
            "/api/v1/payments",
            json=_to_payment_input(
                queue["Q-001"],
                recipient_name="=SUM(1+1)",
                doc_number="@A1",
                purpose="+1+1",
            ),
            headers=CSRF,
        ).json()

        resp = acc.get("/api/v1/payments/export?format=csv&scope=queue&lang=ru")
        assert resp.status_code == 200
        rows = list(csv.reader(io.StringIO(resp.content.decode("utf-8-sig"))))
        by_id = {r[0]: r for r in rows[1:]}

        normal_row = by_id[normal["id"]]
        assert normal_row[2] == "INV-101"
        assert normal_row[6] == 'ТОО "Алатау-Снаб"'
        assert normal_row[10] == f"{queue['Q-001']['amount_kzt']:.2f}"
        assert normal_row[11] == "Оплата по счёту № 214"
        assert not normal_row[6].startswith("'")
        assert not normal_row[11].startswith("'")

        inj_row = by_id[injected["id"]]
        assert inj_row[2] == "'@A1"
        assert inj_row[6] == "'=SUM(1+1)"
        assert inj_row[10] == f"{queue['Q-001']['amount_kzt']:.2f}"
        assert inj_row[11] == "'+1+1"

        # Space-padded formula is also neutralized while normal text is unchanged
        assert export_service.sanitize_csv_cell("   =1+1", clean=True) == "'=1+1"
        assert export_service.sanitize_csv_cell("Normal-Supplier", clean=True) == "Normal-Supplier"
