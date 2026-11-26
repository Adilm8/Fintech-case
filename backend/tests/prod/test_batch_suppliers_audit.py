"""Tests for B7: batch sign-green/send-to-director, suppliers directory, audit API, and error i18n."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.i18n import MESSAGES, SUPPORTED_LANGS, t
from app.prod.app import create_prod_app
from app.prod.db import connect
from app.prod.deps import CSRF_HEADER_NAME, CSRF_HEADER_VALUE
from app.prod.errors import PROD_ERROR_CODES, localize_prod_error
from app.settings import BACKEND_DIR, Settings
from app.store import DEFAULT_DATA_DIR
from tests.prod.conftest import TEST_SEED_PW, TEST_TODAY

CSRF: dict[str, str] = {CSRF_HEADER_NAME: CSRF_HEADER_VALUE}
OCTET_HEADERS: dict[str, str] = {**CSRF, "Content-Type": "application/octet-stream"}
SAMPLES_DIR: Path = DEFAULT_DATA_DIR / "samples"


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
def b7_env(seeded_db: Path) -> Iterator[tuple[FastAPI, Path, TestClient, TestClient, TestClient]]:
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


class TestBatchOperations:
    def test_batch_sign_green_signs_only_green_and_skips_others_with_codes(
        self, b7_env: tuple[FastAPI, Path, TestClient, TestClient, TestClient]
    ) -> None:
        _, _, acc, director, analyst = b7_env

        # Import sample_1c.txt: 5 checked payments (green, yellow, red, grey, invalid)
        imp = acc.post(
            "/api/v1/payments/import?filename=sample_1c.txt",
            content=(SAMPLES_DIR / "sample_1c.txt").read_bytes(),
            headers=OCTET_HEADERS,
        )
        assert imp.status_code == 201
        batch_id = imp.json()["batch"]["id"]
        by_verdict = {item["check"]["verdict"]: item["id"] for item in imp.json()["items"]}

        # Analyst cannot call batch sign-green -> 403
        assert (
            analyst.post(
                "/api/v1/payments/batch/sign-green",
                json={"batch_id": batch_id},
                headers=CSRF,
            ).status_code
            == 403
        )

        # Accountant batch signs green (localized in English)
        res = acc.post(
            "/api/v1/payments/batch/sign-green?lang=en",
            json={"batch_id": batch_id},
            headers=CSRF,
        )
        assert res.status_code == 200
        body = res.json()
        assert [item["id"] for item in body["done"]] == [by_verdict["green"]]
        assert body["done"][0]["status"] == "signed"

        skipped_by_id = {item["id"]: item for item in body["skipped"]}
        assert set(skipped_by_id.keys()) == {
            by_verdict["yellow"],
            by_verdict["red"],
            by_verdict["grey"],
            by_verdict["invalid"],
        }
        assert skipped_by_id[by_verdict["yellow"]]["code"] == "ack_or_approval_required"
        assert skipped_by_id[by_verdict["grey"]]["code"] == "ack_or_approval_required"
        assert skipped_by_id[by_verdict["red"]]["code"] == "red_requires_approval"
        assert skipped_by_id[by_verdict["invalid"]]["code"] == "invalid_requisites"
        assert skipped_by_id[by_verdict["red"]]["detail"] == t("error.prod.red_requires_approval", "en")

        # Director can also call batch sign-green; missing/approved payments are skipped
        queue = _load_queue_by_id()
        p_green2 = acc.post(
            "/api/v1/payments",
            json=_to_payment_input(queue["Q-008"]),
            headers=CSRF,
        ).json()
        # Approve the red payment first -> batch/sign-green must NOT sign status='approved'
        apr_red = acc.post(
            f"/api/v1/payments/{by_verdict['red']}/send-to-director",
            json={"accountant_note": "Проверка"},
            headers=CSRF,
        ).json()["approval"]["id"]
        assert (
            director.post(
                f"/api/v1/approvals/{apr_red}/decision",
                json={
                    "decision": "approved",
                    "director_comment": "Подтверждено лично по договору",
                },
                headers=CSRF,
            ).status_code
            == 200
        )

        dir_batch = director.post(
            "/api/v1/payments/batch/sign-green",
            json={
                "payment_ids": [p_green2["id"], by_verdict["red"], "pay-nonexistent"],
            },
            headers=CSRF,
        )
        assert dir_batch.status_code == 200
        d_body = dir_batch.json()
        assert [item["id"] for item in d_body["done"]] == [p_green2["id"]]
        d_skipped = {item["id"]: item["code"] for item in d_body["skipped"]}
        assert d_skipped == {
            by_verdict["red"]: "invalid_transition",
            "pay-nonexistent": "not_found",
        }

    def test_batch_send_to_director_skips_invalid_and_green(
        self, b7_env: tuple[FastAPI, Path, TestClient, TestClient, TestClient]
    ) -> None:
        _, _, acc, director, analyst = b7_env

        imp = acc.post(
            "/api/v1/payments/import?filename=sample_1c.txt",
            content=(SAMPLES_DIR / "sample_1c.txt").read_bytes(),
            headers=OCTET_HEADERS,
        )
        assert imp.status_code == 201
        batch_id = imp.json()["batch"]["id"]
        by_verdict = {item["check"]["verdict"]: item["id"] for item in imp.json()["items"]}

        # Director and analyst cannot batch-send -> 403
        for client in (director, analyst):
            assert (
                client.post(
                    "/api/v1/payments/batch/send-to-director",
                    json={"batch_id": batch_id},
                    headers=CSRF,
                ).status_code
                == 403
            )

        res = acc.post(
            "/api/v1/payments/batch/send-to-director?lang=kk",
            json={"batch_id": batch_id, "accountant_note": "Пакет на согласование"},
            headers=CSRF,
        )
        assert res.status_code == 200
        body = res.json()

        done_ids = {item["id"] for item in body["done"]}
        assert done_ids == {by_verdict["yellow"], by_verdict["red"], by_verdict["grey"]}
        assert all(item["status"] == "pending_approval" for item in body["done"])

        skipped = {item["id"]: item for item in body["skipped"]}
        assert set(skipped.keys()) == {by_verdict["green"], by_verdict["invalid"]}
        assert skipped[by_verdict["green"]]["code"] == "invalid_transition"
        assert skipped[by_verdict["invalid"]]["code"] == "invalid_requisites"
        assert skipped[by_verdict["invalid"]]["detail"] == t("error.prod.invalid_requisites", "kk")

        # Verify green and invalid remain untouched in 'checked' status
        assert acc.get(f"/api/v1/payments/{by_verdict['green']}").json()["status"] == "checked"
        assert acc.get(f"/api/v1/payments/{by_verdict['invalid']}").json()["status"] == "checked"


class TestSuppliersAPI:
    def test_suppliers_list_search_filter_pending_change_and_account_added(
        self, b7_env: tuple[FastAPI, Path, TestClient, TestClient, TestClient]
    ) -> None:
        prod_app, _, acc, director, analyst = b7_env
        queue = _load_queue_by_id()

        # 1. Seeded directory has 12 suppliers; changed supplier (150846341552) comes first
        all_sups = acc.get("/api/v1/suppliers").json()
        assert len(all_sups) == 12
        assert all_sups[0]["bin"] == "150846341552"
        assert all_sups[0]["requisites_changed_at"] is not None
        assert all_sups[0]["accounts_count"] == 2

        # Cyrillic case-insensitive search and BIN search
        by_name = acc.get("/api/v1/suppliers?q=казлогистик").json()
        assert len(by_name) == 1
        klg_id = by_name[0]["id"]
        assert by_name[0]["bin"] == queue["Q-002"]["recipient_bin"]
        assert by_name[0]["has_pending_change"] is False
        assert by_name[0]["requisites_changed_days_ago"] is None

        assert len(acc.get(f"/api/v1/suppliers?q={queue['Q-002']['recipient_bin']}").json()) == 1

        # 2. Create yellow payment Q-002 (new IIK + new BIK) -> has_pending_change becomes True
        p_yellow = acc.post(
            "/api/v1/payments",
            json=_to_payment_input(queue["Q-002"]),
            headers=CSRF,
        ).json()
        before_sign = acc.get(f"/api/v1/suppliers/{klg_id}").json()
        assert before_sign["has_pending_change"] is True
        assert before_sign["accounts_count"] == 1
        assert before_sign["changes"] == []
        assert before_sign["payments"][0]["id"] == p_yellow["id"]
        assert "analyst_details" not in before_sign["payments"][0]["check"]

        # 3. Approve with trust + sign -> account_added + bank_changed + requisites_changed_days_ago == 0
        apr_id = acc.post(
            f"/api/v1/payments/{p_yellow['id']}/send-to-director",
            json={"accountant_note": "Новый счёт"},
            headers=CSRF,
        ).json()["approval"]["id"]
        assert (
            director.post(
                f"/api/v1/approvals/{apr_id}/decision",
                json={
                    "decision": "approved",
                    "director_comment": "Подтвердили по договору с директором поставщика",
                    "trust_account": True,
                },
                headers=CSRF,
            ).status_code
            == 200
        )
        assert acc.post(f"/api/v1/payments/{p_yellow['id']}/sign", json={}, headers=CSRF).status_code == 200

        after_sign = acc.get(f"/api/v1/suppliers/{klg_id}").json()
        assert after_sign["has_pending_change"] is False
        assert after_sign["accounts_count"] == 2
        assert after_sign["trusted_accounts_count"] == 1
        assert after_sign["requisites_changed_days_ago"] == 0
        change_kinds = {ch["kind"] for ch in after_sign["changes"]}
        assert {"account_added", "bank_changed"} <= change_kinds
        assert all(ch["payment_id"] == p_yellow["id"] for ch in after_sign["changes"])

        new_acc = next(a for a in after_sign["accounts"] if a["iik"] == queue["Q-002"]["recipient_iik"])
        assert new_acc["trusted"] is True
        assert new_acc["trusted_comment"] is not None
        assert new_acc["bank_name"] is not None

        # Filter changed_within_days=90 includes the updated supplier
        changed_recent = acc.get("/api/v1/suppliers?changed_within_days=90").json()
        assert any(s["id"] == klg_id and s["requisites_changed_days_ago"] == 0 for s in changed_recent)

        # Analyst sees supplier card + analyst_details on embedded payments
        ana_card = analyst.get(f"/api/v1/suppliers/{klg_id}").json()
        assert ana_card["id"] == klg_id

        # Cross-company accountant sees empty list and 404 on supplier card
        with TestClient(prod_app) as other_acc:
            _login(other_acc, "other_accountant")
            assert other_acc.get("/api/v1/suppliers").json() == []
            r_404 = other_acc.get(f"/api/v1/suppliers/{klg_id}")
            assert r_404.status_code == 404
            assert r_404.json()["code"] == "not_found"


class TestAuditEndpoints:
    def test_audit_role_guards_scoping_filters_and_verify(
        self, b7_env: tuple[FastAPI, Path, TestClient, TestClient, TestClient]
    ) -> None:
        prod_app, db_path, acc, director, analyst = b7_env
        queue = _load_queue_by_id()

        # Generate some audit entries for client-technostroy and for comp-other
        p_red = acc.post("/api/v1/payments", json=_to_payment_input(queue["Q-003"]), headers=CSRF).json()
        assert acc.post(f"/api/v1/payments/{p_red['id']}/sign", json={}, headers=CSRF).status_code == 409

        with TestClient(prod_app) as other_acc:
            _login(other_acc, "other_accountant")
            p_other = other_acc.post(
                "/api/v1/payments",
                json=_to_payment_input(queue["Q-004"]),
                headers=CSRF,
            ).json()

        # Accountant -> 403 forbidden_role on both /audit and /audit/verify
        r_acc = acc.get("/api/v1/audit?lang=ru")
        assert r_acc.status_code == 403
        assert r_acc.json()["code"] == "forbidden_role"
        assert acc.get("/api/v1/audit/verify").status_code == 403

        # Director -> 200 on /audit (own company only), 403 on /audit/verify
        dir_entries = director.get("/api/v1/audit").json()
        assert len(dir_entries) >= 2
        assert all(e["payment_id"] != p_other["id"] for e in dir_entries)
        assert director.get("/api/v1/audit/verify").status_code == 403

        # Filter by payment_id & action
        denied = director.get(f"/api/v1/audit?payment_id={p_red['id']}&action=sign_denied").json()
        assert len(denied) == 1
        assert denied[0]["action"] == "sign_denied"
        assert denied[0]["details"]["code"] == "red_requires_approval"

        # Analyst -> sees entries from both companies and can run /audit/verify
        ana_entries = analyst.get("/api/v1/audit?limit=500").json()
        payment_ids = {e["payment_id"] for e in ana_entries}
        assert p_red["id"] in payment_ids
        assert p_other["id"] in payment_ids

        verify_ok = analyst.get("/api/v1/audit/verify")
        assert verify_ok.status_code == 200
        v_body = verify_ok.json()
        assert v_body["ok"] is True
        assert v_body["checked"] >= len(ana_entries)
        assert v_body["broken_at"] is None

        # Tamper with DB row -> /audit/verify reports ok=False and broken_at
        conn = connect(db_path)
        try:
            conn.execute("DROP TRIGGER audit_no_update")
            conn.execute("UPDATE audit_log SET action = 'tampered' WHERE id = 1")
        finally:
            conn.close()

        verify_bad = analyst.get("/api/v1/audit/verify").json()
        assert verify_bad["ok"] is False
        assert verify_bad["broken_at"] == 1


class TestProdErrorLocalization:
    def test_every_prod_error_code_has_ru_kk_en_in_i18n_catalog(self) -> None:
        # 1. Scan all app/prod/**/*.py files for ProdError(..., "code") and localize_prod_error("code")
        prod_dir = BACKEND_DIR / "app" / "prod"
        discovered_codes: set[str] = set()
        patterns = (
            re.compile(r'ProdError\(\s*\d+\s*,\s*"([a-z0-9_]+)"'),
            re.compile(r'localize_prod_error\(\s*"([a-z0-9_]+)"'),
            re.compile(r'block_code\s*=\s*"([a-z0-9_]+)"'),
            re.compile(r'code\s*=\s*"(not_found|invalid_transition|invalid_requisites|validation_error|internal_error)"'),
        )
        for py_file in prod_dir.rglob("*.py"):
            src = py_file.read_text(encoding="utf-8")
            for pat in patterns:
                discovered_codes.update(pat.findall(src))

        # Every discovered code must be declared in PROD_ERROR_CODES
        missing_from_set = discovered_codes - PROD_ERROR_CODES
        assert not missing_from_set, f"Codes used in app/prod but missing from PROD_ERROR_CODES: {missing_from_set}"

        # Every code in PROD_ERROR_CODES must exist under error.prod.<code> in app.i18n.MESSAGES
        for code in sorted(PROD_ERROR_CODES):
            key = f"error.prod.{code}"
            assert key in MESSAGES, f"Missing i18n key {key} in app.i18n.MESSAGES"
            rendered: dict[str, str] = {}
            for lang in SUPPORTED_LANGS:
                msg = localize_prod_error(code, lang)
                assert isinstance(msg, str) and msg.strip(), f"Empty message for {key} ({lang})"
                assert msg != code, f"Unlocalized fallback returned for {key} ({lang})"
                assert msg == t(key, lang)
                rendered[lang] = msg
            assert rendered["ru"] != rendered["en"], f"ru == en for {key}"
            assert rendered["kk"] != rendered["en"], f"kk == en for {key}"
            assert rendered["kk"] != rendered["ru"], f"kk == ru for {key}"

    @pytest.mark.parametrize("lang", ["ru", "kk", "en"])
    def test_http_error_responses_use_requested_language(
        self,
        b7_env: tuple[FastAPI, Path, TestClient, TestClient, TestClient],
        lang: str,
    ) -> None:
        prod_app, _, acc, _, _ = b7_env

        # 403 forbidden_role (accountant -> /audit)
        r_403 = acc.get(f"/api/v1/audit?lang={lang}")
        assert r_403.status_code == 403
        assert r_403.json() == {
            "detail": t("error.prod.forbidden_role", lang),
            "code": "forbidden_role",
        }

        # 404 not_found
        r_404 = acc.get(f"/api/v1/suppliers/999999?lang={lang}")
        assert r_404.status_code == 404
        assert r_404.json() == {
            "detail": t("error.prod.not_found", lang),
            "code": "not_found",
        }

        # 401 not_authenticated
        with TestClient(prod_app) as anon:
            r_401 = anon.get(f"/api/v1/auth/me?lang={lang}")
            assert r_401.status_code == 401
            assert r_401.json() == {
                "detail": t("error.prod.not_authenticated", lang),
                "code": "not_authenticated",
            }
            # /meta accepts ?lang=
            r_meta = anon.get(f"/api/v1/meta?lang={lang}")
            assert r_meta.status_code == 200
            assert r_meta.json()["mode"] == "prod"


class TestB8UntrustAndAnalystMetrics:
    def test_untrust_sets_revoked_at_and_next_check_returns_yellow(
        self, b7_env: tuple[FastAPI, Path, TestClient, TestClient, TestClient]
    ) -> None:
        _, db_path, acc, director, analyst = b7_env
        queue = _load_queue_by_id()
        q2 = queue["Q-002"]

        # 1. Create yellow payment Q-002 (new IIK + new bank), send to director, approve WITH trust
        p1 = acc.post("/api/v1/payments", json=_to_payment_input(q2), headers=CSRF).json()
        assert p1["check"]["verdict"] == "yellow"
        apr_id = acc.post(
            f"/api/v1/payments/{p1['id']}/send-to-director",
            json={"accountant_note": "Новый счёт поставщика"},
            headers=CSRF,
        ).json()["approval"]["id"]
        assert (
            director.post(
                f"/api/v1/approvals/{apr_id}/decision",
                json={
                    "decision": "approved",
                    "director_comment": "Подтвердили по договору с бухгалтерией поставщика",
                    "trust_account": True,
                },
                headers=CSRF,
            ).status_code
            == 200
        )

        # Next check while trusted is green (trusted=True)
        p2 = acc.post(
            "/api/v1/payments",
            json=_to_payment_input(q2, purpose="Оплата по новому счёту № 811"),
            headers=CSRF,
        ).json()
        assert p2["check"]["verdict"] == "green"
        assert p2["check"]["trusted"] is True

        # Find supplier and its trusted account entry on GET /suppliers/{id}
        sups = director.get(f"/api/v1/suppliers?q={q2['recipient_bin']}").json()
        assert len(sups) == 1
        sup_id = sups[0]["id"]
        card = director.get(f"/api/v1/suppliers/{sup_id}").json()
        trusted_acc = next(a for a in card["accounts"] if a["iik"] == q2["recipient_iik"])
        assert trusted_acc["trusted"] is True
        acc_id = trusted_acc["id"]

        # Accountant and analyst cannot untrust -> 403
        for client in (acc, analyst):
            assert (
                client.post(
                    f"/api/v1/suppliers/{sup_id}/accounts/{acc_id}/untrust",
                    json={"comment": "Отзыв доверия с достаточным комментарием"},
                    headers=CSRF,
                ).status_code
                == 403
            )

        # Short comment -> 422 trust_comment_required
        r_short = director.post(
            f"/api/v1/suppliers/{sup_id}/accounts/{acc_id}/untrust",
            json={"comment": "коротко"},
            headers=CSRF,
        )
        assert r_short.status_code == 422
        assert r_short.json()["code"] == "trust_comment_required"

        # Director revokes trust with valid comment -> 200 SupplierDetail, revoked_at set, audit logged
        r_untrust = director.post(
            f"/api/v1/suppliers/{sup_id}/accounts/{acc_id}/untrust",
            json={"comment": "Поставщик сообщил о компрометации почты — отзыв доверия"},
            headers=CSRF,
        )
        assert r_untrust.status_code == 200
        updated_card = r_untrust.json()
        assert updated_card["trusted_accounts_count"] == 0
        assert all(
            not a["trusted"] for a in updated_card["accounts"] if a["iik"] == q2["recipient_iik"]
        )

        # Verify revoked_at & revoked_by in DB + trust_revoked in audit_log
        conn = connect(db_path)
        try:
            row = conn.execute(
                "SELECT revoked_at, revoked_by FROM trusted_accounts WHERE recipient_iik = ?",
                (q2["recipient_iik"],),
            ).fetchone()
            assert row is not None and row["revoked_at"] is not None and row["revoked_by"] is not None
        finally:
            conn.close()

        revoked_logs = analyst.get("/api/v1/audit?action=trust_revoked").json()
        assert len(revoked_logs) == 1
        assert revoked_logs[0]["details"]["recipient_iik"] == q2["recipient_iik"]

        # Next check of that same account (after cancelling unsigned drafts) is YELLOW again!
        assert acc.post(f"/api/v1/payments/{p1['id']}/cancel", headers=CSRF).status_code == 200
        assert acc.post(f"/api/v1/payments/{p2['id']}/cancel", headers=CSRF).status_code == 200
        p3 = acc.post(
            "/api/v1/payments",
            json=_to_payment_input(q2, purpose="Оплата по новому счёту № 812"),
            headers=CSRF,
        ).json()
        assert p3["check"]["verdict"] == "yellow"
        assert p3["check"]["trusted"] is False
        assert "iik_changed" in {s["rule_id"] for s in p3["check"]["signals"]}

    def test_analyst_metrics_matches_demo_and_blocks_client_roles(
        self, b7_env: tuple[FastAPI, Path, TestClient, TestClient, TestClient]
    ) -> None:
        from app.main import app as demo_app

        _, _, acc, director, analyst = b7_env

        assert acc.get("/api/v1/metrics").status_code == 403
        assert director.get("/api/v1/metrics").status_code == 403

        with TestClient(demo_app) as demo_client:
            for lang in ("ru", "en"):
                prod_m = analyst.get(f"/api/v1/metrics?lang={lang}")
                demo_m = demo_client.get(f"/api/metrics?lang={lang}")
                assert prod_m.status_code == 200
                assert demo_m.status_code == 200
                assert prod_m.json() == demo_m.json()
