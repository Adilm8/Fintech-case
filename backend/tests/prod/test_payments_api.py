"""Tests for B4: payments CRUD, list counts/filters, permissions, isolation, edit/ack, transitions."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.prod.app import create_prod_app
from app.prod.audit_db import list_audit, verify_chain
from app.prod.db import connect, tx
from app.prod.deps import CSRF_HEADER_NAME, CSRF_HEADER_VALUE
from app.settings import Settings
from app.store import DEFAULT_DATA_DIR
from tests.prod.conftest import TEST_SEED_PW, TEST_TODAY

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
def payments_env(seeded_db: Path) -> Iterator[tuple[FastAPI, Path, TestClient]]:
    cfg = Settings(
        app_mode="prod",
        db_path=seeded_db,
        today_override=TEST_TODAY,
        cookie_secure=False,
    )
    prod_app = create_prod_app(db_path=seeded_db, settings_override=cfg)
    with TestClient(prod_app) as client:
        yield prod_app, seeded_db, client


class TestCreateAndReadPayments:
    def test_create_payment_runs_check_writes_audit_and_supports_invalid(
        self, payments_env: tuple[FastAPI, Path, TestClient]
    ) -> None:
        _, db_path, client = payments_env
        queue = _load_queue_by_id()
        _login(client, "accountant")

        # 1. Green payment (also verify spoofed payer_id is ignored)
        green_body = _to_payment_input(queue["Q-001"], payer_id="comp-other")
        r_green = client.post("/api/v1/payments", json=green_body, headers=CSRF)
        assert r_green.status_code == 201
        p_green = r_green.json()
        assert p_green["id"].startswith("pay-")
        assert p_green["company_id"] == "client-technostroy"
        assert p_green["request"]["payer_id"] == "client-technostroy"
        assert p_green["status"] == "checked"
        assert p_green["source"] == "manual"
        assert p_green["check"]["verdict"] == "green"
        assert "analyst_details" not in p_green["check"]
        assert p_green["supplier"]["known"] is True
        assert p_green["supplier"]["account_known"] is True
        assert p_green["duplicate_of"] is None
        assert p_green["accountant_ack"] is False

        # 2. Invalid payment is STILL saved (201) and editable
        r_inv = client.post(
            "/api/v1/payments",
            json=_to_payment_input(queue["Q-007"]),
            headers=CSRF,
        )
        assert r_inv.status_code == 201
        p_inv = r_inv.json()
        assert p_inv["status"] == "checked"
        assert p_inv["check"]["verdict"] == "invalid"
        assert p_inv["permissions"]["can_edit"] is True
        assert p_inv["permissions"]["can_sign"] is False
        assert p_inv["permissions"]["sign_block_code"] == "invalid_requisites"
        assert p_inv["permissions"]["can_send_to_director"] is False

        # 3. Duplicate active payment sets duplicate_of pointing to the original
        r_dup = client.post("/api/v1/payments", json=green_body, headers=CSRF)
        assert r_dup.status_code == 201
        p_dup = r_dup.json()
        assert p_dup["duplicate_of"] == p_green["id"]

        # 4. Verify checks table and audit_log ('check' + 'payment_created') + chain integrity
        conn = connect(db_path)
        try:
            checks = conn.execute(
                "SELECT payment_id, trigger, verdict FROM checks WHERE payment_id = ?",
                (p_green["id"],),
            ).fetchall()
            assert len(checks) == 1
            assert checks[0]["trigger"] == "create"
            assert checks[0]["verdict"] == "green"

            audit_entries = list_audit(conn, payment_id=p_green["id"])
            actions = {e.action for e in audit_entries}
            assert "payment_created" in actions
            assert "check" in actions
            assert verify_chain(conn).ok is True
        finally:
            conn.close()

    def test_director_and_analyst_cannot_create_payments(
        self, payments_env: tuple[FastAPI, Path, TestClient]
    ) -> None:
        _, _, client = payments_env
        payload = _to_payment_input(_load_queue_by_id()["Q-001"])

        for role_login in ("director", "analyst"):
            _login(client, role_login)
            resp = client.post("/api/v1/payments", json=payload, headers=CSRF)
            assert resp.status_code == 403
            assert resp.json()["code"] == "forbidden_role"

    def test_validation_errors_return_422_with_code(
        self, payments_env: tuple[FastAPI, Path, TestClient]
    ) -> None:
        _, _, client = payments_env
        _login(client, "accountant")
        bad = _to_payment_input(_load_queue_by_id()["Q-001"], amount_kzt=0, doc_date="26-11-2026")
        resp = client.post("/api/v1/payments?lang=en", json=bad, headers=CSRF)
        assert resp.status_code == 422
        body = resp.json()
        assert body["code"] == "validation_error"
        assert isinstance(body["errors"], list) and len(body["errors"]) >= 1


class TestListCountsFiltersAndIsolation:
    def test_list_returns_full_scope_counts_filters_search_and_signed_scope(
        self, payments_env: tuple[FastAPI, Path, TestClient]
    ) -> None:
        _, db_path, client = payments_env
        queue = _load_queue_by_id()
        _login(client, "accountant")

        p1 = client.post("/api/v1/payments", json=_to_payment_input(queue["Q-001"]), headers=CSRF).json()
        p2 = client.post("/api/v1/payments", json=_to_payment_input(queue["Q-002"]), headers=CSRF).json()
        p3 = client.post("/api/v1/payments", json=_to_payment_input(queue["Q-003"]), headers=CSRF).json()
        p4 = client.post("/api/v1/payments", json=_to_payment_input(queue["Q-004"]), headers=CSRF).json()
        p7 = client.post("/api/v1/payments", json=_to_payment_input(queue["Q-007"]), headers=CSRF).json()

        # Move Q-002 to pending_approval and Q-004 to postponed
        assert client.post(f"/api/v1/payments/{p2['id']}/send-to-director", json={"accountant_note": "Проверить"}, headers=CSRF).status_code == 200
        assert client.post(f"/api/v1/payments/{p4['id']}/postpone", json={"note": "Уточнить"}, headers=CSRF).status_code == 200

        # Default scope=queue returns 5 active items with exact counts
        resp = client.get("/api/v1/payments")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 5
        assert len(data["items"]) == 5
        assert data["counts"]["by_status"] == {
            "checked": 3,
            "pending_approval": 1,
            "approved": 0,
            "rejected": 0,
            "postponed": 1,
            "signed": 0,
            "cancelled": 0,
        }
        assert data["counts"]["by_verdict"] == {
            "green": 1,
            "yellow": 1,
            "red": 1,
            "grey": 1,
            "invalid": 1,
        }

        # Filtering by status/verdict + pagination preserves full-scope counts
        filtered = client.get("/api/v1/payments?status=checked&verdict=red&limit=1&offset=0").json()
        assert filtered["total"] == 1
        assert len(filtered["items"]) == 1
        assert filtered["items"][0]["id"] == p3["id"]
        assert filtered["counts"]["by_status"]["pending_approval"] == 1
        assert filtered["counts"]["by_verdict"]["green"] == 1

        # Case-insensitive Cyrillic search (q=алатау matches Q-001 and Q-003)
        search_cyr = client.get("/api/v1/payments?q=алатау").json()
        assert {item["id"] for item in search_cyr["items"]} == {p1["id"], p3["id"]}

        # Search by doc_number (Q-007)
        search_doc = client.get("/api/v1/payments?q=Q-007").json()
        assert [item["id"] for item in search_doc["items"]] == [p7["id"]]

        # Filter by supplier_id (ТОО «Алатау Снаб» in suppliers)
        conn = connect(db_path)
        try:
            sup_row = conn.execute(
                "SELECT id FROM suppliers WHERE bin = ?",
                (queue["Q-001"]["recipient_bin"],),
            ).fetchone()
            assert sup_row is not None
            sup_id = int(sup_row["id"])
        finally:
            conn.close()
        by_sup = client.get(f"/api/v1/payments?supplier_id={sup_id}").json()
        assert [item["id"] for item in by_sup["items"]] == [p1["id"]]

        # scope=signed returns the 150 seeded signed payments cleanly (paginated)
        signed = client.get("/api/v1/payments?scope=signed&limit=10&offset=0").json()
        assert signed["total"] == 150
        assert len(signed["items"]) == 10
        assert signed["counts"]["by_status"]["signed"] == 150
        assert signed["counts"]["by_verdict"]["green"] == 150
        assert all(item["status"] == "signed" for item in signed["items"])
        assert all(item["check"]["verdict"] == "green" for item in signed["items"])

    def test_cross_company_accountant_gets_404_and_empty_list(
        self, payments_env: tuple[FastAPI, Path, TestClient]
    ) -> None:
        prod_app, _, client = payments_env
        queue = _load_queue_by_id()
        _login(client, "accountant")
        created = client.post(
            "/api/v1/payments",
            json=_to_payment_input(queue["Q-001"]),
            headers=CSRF,
        ).json()
        pid = created["id"]

        # Another company's accountant must see empty list and 404 (never 403) on all endpoints
        with TestClient(prod_app) as other_client:
            _login(other_client, "other_accountant")
            assert other_client.get("/api/v1/payments?scope=all").json()["total"] == 0

            assert other_client.get(f"/api/v1/payments/{pid}").status_code == 404
            assert other_client.get(f"/api/v1/payments/{pid}").json()["code"] == "not_found"

            put_resp = other_client.put(
                f"/api/v1/payments/{pid}",
                json=_to_payment_input(queue["Q-001"], amount_kzt=1200000),
                headers=CSRF,
            )
            assert put_resp.status_code == 404
            assert put_resp.json()["code"] == "not_found"

            for suffix in ("recheck", "send-to-director", "postpone", "resume", "cancel"):
                r = other_client.post(f"/api/v1/payments/{pid}/{suffix}", headers=CSRF)
                assert r.status_code == 404, f"{suffix} returned {r.status_code}"
                assert r.json()["code"] == "not_found"

    def test_analyst_sees_analyst_details_while_client_roles_never_do(
        self, payments_env: tuple[FastAPI, Path, TestClient]
    ) -> None:
        prod_app, _, client = payments_env
        queue = _load_queue_by_id()
        _login(client, "accountant")
        p_red = client.post(
            "/api/v1/payments",
            json=_to_payment_input(queue["Q-003"]),
            headers=CSRF,
        ).json()
        pid = p_red["id"]

        # Accountant does NOT get analyst_details even when spoofing X-Role: analyst
        acc_get = client.get(
            f"/api/v1/payments/{pid}?lang=en",
            headers={"X-Role": "analyst"},
        )
        assert acc_get.status_code == 200
        acc_data = acc_get.json()
        assert "analyst_details" not in acc_data["check"]
        assert "internal_analyst_details" not in acc_data["check"]
        assert acc_data["check"]["headline"] != acc_data["check"]["headline_ru"]

        # Director does NOT get analyst_details even when spoofing X-Role: analyst
        with TestClient(prod_app) as dir_client:
            _login(dir_client, "director")
            dir_data = dir_client.get(
                f"/api/v1/payments/{pid}?lang=kk",
                headers={"X-Role": "analyst"},
            ).json()
            assert "analyst_details" not in dir_data["check"]
            assert dir_data["check"]["headline"] != dir_data["check"]["headline_ru"]

        # Analyst DOES get localized analyst_details (and can see payments across all companies)
        with TestClient(prod_app) as ana_client:
            _login(ana_client, "analyst")
            ana_data = ana_client.get(f"/api/v1/payments/{pid}?lang=en").json()
            assert ana_data["check"]["analyst_details"] is not None
            assert ana_data["check"]["analyst_details"]["bcc_account"] is not None
            assert len(ana_data["check"]["analyst_details"]["signal_details"]) >= 1
            assert "internal_analyst_details" not in ana_data["check"]

            # Also verify in list endpoint
            ana_list = ana_client.get("/api/v1/payments?lang=en").json()
            red_in_list = next(item for item in ana_list["items"] if item["id"] == pid)
            assert red_in_list["check"]["analyst_details"] is not None


class TestPermissionsMatrix:
    def test_permissions_match_role_status_and_verdict(
        self, payments_env: tuple[FastAPI, Path, TestClient]
    ) -> None:
        prod_app, _, acc = payments_env
        queue = _load_queue_by_id()
        _login(acc, "accountant")

        p_green = acc.post("/api/v1/payments", json=_to_payment_input(queue["Q-001"]), headers=CSRF).json()
        p_yellow = acc.post("/api/v1/payments", json=_to_payment_input(queue["Q-002"]), headers=CSRF).json()
        p_red = acc.post("/api/v1/payments", json=_to_payment_input(queue["Q-003"]), headers=CSRF).json()
        p_grey = acc.post("/api/v1/payments", json=_to_payment_input(queue["Q-004"]), headers=CSRF).json()

        # Accountant in checked
        assert p_green["permissions"] == {
            "can_edit": True,
            "can_sign": True,
            "sign_requires_ack": False,
            "sign_block_code": None,
            "can_send_to_director": True,
            "can_postpone": True,
            "can_resume": False,
            "can_cancel": True,
            "can_decide": False,
        }
        assert p_yellow["permissions"]["can_sign"] is True
        assert p_yellow["permissions"]["sign_requires_ack"] is True
        assert p_yellow["permissions"]["sign_block_code"] is None

        assert p_grey["permissions"]["can_sign"] is True
        assert p_grey["permissions"]["sign_requires_ack"] is True

        assert p_red["permissions"]["can_sign"] is False
        assert p_red["permissions"]["sign_requires_ack"] is False
        assert p_red["permissions"]["sign_block_code"] == "red_requires_approval"
        assert p_red["permissions"]["can_send_to_director"] is True

        # Send yellow to director -> pending_approval
        p_pending = acc.post(
            f"/api/v1/payments/{p_yellow['id']}/send-to-director",
            json={"accountant_note": "Новый счёт"},
            headers=CSRF,
        ).json()
        assert p_pending["permissions"] == {
            "can_edit": False,
            "can_sign": False,
            "sign_requires_ack": False,
            "sign_block_code": "approval_pending",
            "can_send_to_director": False,
            "can_postpone": False,
            "can_resume": False,
            "can_cancel": False,
            "can_decide": False,
        }

        # Director permissions on checked green/yellow/red and pending_approval
        with TestClient(prod_app) as director:
            _login(director, "director")
            d_green = director.get(f"/api/v1/payments/{p_green['id']}").json()
            assert d_green["permissions"] == {
                "can_edit": False,
                "can_sign": True,
                "sign_requires_ack": False,
                "sign_block_code": None,
                "can_send_to_director": False,
                "can_postpone": False,
                "can_resume": False,
                "can_cancel": False,
                "can_decide": False,
            }
            d_grey = director.get(f"/api/v1/payments/{p_grey['id']}").json()
            assert d_grey["permissions"]["can_sign"] is False
            assert d_grey["permissions"]["sign_block_code"] == "ack_or_approval_required"

            d_pending = director.get(f"/api/v1/payments/{p_yellow['id']}").json()
            assert d_pending["permissions"]["can_decide"] is True
            assert d_pending["permissions"]["can_sign"] is False
            assert d_pending["permissions"]["sign_block_code"] == "approval_pending"

        # Analyst permissions: read-only on everything
        with TestClient(prod_app) as analyst:
            _login(analyst, "analyst")
            for pid in (p_green["id"], p_yellow["id"], p_red["id"]):
                a_view = analyst.get(f"/api/v1/payments/{pid}").json()
                assert a_view["permissions"] == {
                    "can_edit": False,
                    "can_sign": False,
                    "sign_requires_ack": False,
                    "sign_block_code": "forbidden_role",
                    "can_send_to_director": False,
                    "can_postpone": False,
                    "can_resume": False,
                    "can_cancel": False,
                    "can_decide": False,
                }


class TestEditAndStatusTransitions:
    def test_edit_updates_request_sha256_resets_ack_and_avoids_self_duplicate(
        self, payments_env: tuple[FastAPI, Path, TestClient]
    ) -> None:
        _, db_path, client = payments_env
        queue = _load_queue_by_id()
        _login(client, "accountant")

        # Create invalid payment (Q-007)
        created = client.post(
            "/api/v1/payments",
            json=_to_payment_input(queue["Q-007"]),
            headers=CSRF,
        ).json()
        pid = created["id"]
        assert created["check"]["verdict"] == "invalid"

        # Simulate accountant_ack=1 in DB and capture old request_sha256
        conn = connect(db_path)
        try:
            old_row = conn.execute(
                "SELECT request_sha256, check_id FROM payments WHERE id = ?",
                (pid,),
            ).fetchone()
            assert old_row is not None
            old_sha = str(old_row["request_sha256"])
            old_check_id = str(old_row["check_id"])
            with tx(conn):
                conn.execute("UPDATE payments SET accountant_ack = 1 WHERE id = ?", (pid,))
        finally:
            conn.close()

        # Fix the IIK checksum (last digit 1 -> 0 matches ТОО «СтепьЭнергоСервис» in history)
        fixed_payload = _to_payment_input(
            queue["Q-007"],
            recipient_iik="KZ55856KZT5935868570",
        )
        edited = client.put(f"/api/v1/payments/{pid}", json=fixed_payload, headers=CSRF)
        assert edited.status_code == 200
        p_edited = edited.json()
        assert p_edited["status"] == "checked"
        assert p_edited["accountant_ack"] is False
        assert p_edited["check"]["verdict"] == "green"
        assert p_edited["check"]["check_id"] != old_check_id
        # Must NOT flag duplicate_invoice against its own pre-edit record
        assert "duplicate_invoice" not in {s["rule_id"] for s in p_edited["check"]["signals"]}

        conn = connect(db_path)
        try:
            new_row = conn.execute(
                "SELECT request_sha256, accountant_ack FROM payments WHERE id = ?",
                (pid,),
            ).fetchone()
            assert new_row is not None
            assert str(new_row["request_sha256"]) != old_sha
            assert int(new_row["accountant_ack"]) == 0

            checks = conn.execute(
                "SELECT trigger FROM checks WHERE payment_id = ? ORDER BY rowid ASC",
                (pid,),
            ).fetchall()
            assert [r["trigger"] for r in checks] == ["create", "edit"]
            assert verify_chain(conn).ok is True
        finally:
            conn.close()

    def test_put_and_recheck_blocked_in_pending_approval_and_approved(
        self, payments_env: tuple[FastAPI, Path, TestClient]
    ) -> None:
        _, db_path, client = payments_env
        queue = _load_queue_by_id()
        _login(client, "accountant")

        p = client.post(
            "/api/v1/payments",
            json=_to_payment_input(queue["Q-002"]),
            headers=CSRF,
        ).json()
        pid = p["id"]

        # Send to director -> pending_approval
        sent = client.post(
            f"/api/v1/payments/{pid}/send-to-director",
            json={"accountant_note": "Сменился счёт"},
            headers=CSRF,
        )
        assert sent.status_code == 200
        assert sent.json()["status"] == "pending_approval"
        apr_id = sent.json()["approval"]["id"]

        # Repeat send-to-director is idempotent (200, no duplicate approval)
        sent_again = client.post(
            f"/api/v1/payments/{pid}/send-to-director",
            json={"accountant_note": "Повтор"},
            headers=CSRF,
        )
        assert sent_again.status_code == 200
        assert sent_again.json()["approval"]["id"] == apr_id

        # PUT in pending_approval -> 409 not_editable
        edit_resp = client.put(
            f"/api/v1/payments/{pid}",
            json=_to_payment_input(queue["Q-002"], amount_kzt=710000),
            headers=CSRF,
        )
        assert edit_resp.status_code == 409
        assert edit_resp.json()["code"] == "not_editable"

        # recheck in pending_approval -> 409 not_editable
        recheck_resp = client.post(f"/api/v1/payments/{pid}/recheck", headers=CSRF)
        assert recheck_resp.status_code == 409
        assert recheck_resp.json()["code"] == "not_editable"

        # Also verify PUT in approved -> 409 not_editable
        conn = connect(db_path)
        try:
            with tx(conn):
                conn.execute("UPDATE approvals SET status = 'approved' WHERE id = ?", (apr_id,))
                conn.execute("UPDATE payments SET status = 'approved' WHERE id = ?", (pid,))
        finally:
            conn.close()

        edit_approved = client.put(
            f"/api/v1/payments/{pid}",
            json=_to_payment_input(queue["Q-002"], amount_kzt=720000),
            headers=CSRF,
        )
        assert edit_approved.status_code == 409
        assert edit_approved.json()["code"] == "not_editable"

    def test_status_transitions_recheck_postpone_resume_cancel_and_invalid_guards(
        self, payments_env: tuple[FastAPI, Path, TestClient]
    ) -> None:
        _, db_path, client = payments_env
        queue = _load_queue_by_id()
        _login(client, "accountant")

        # Cannot send invalid payment to director
        p_inv = client.post(
            "/api/v1/payments",
            json=_to_payment_input(queue["Q-007"]),
            headers=CSRF,
        ).json()
        send_inv = client.post(f"/api/v1/payments/{p_inv['id']}/send-to-director", headers=CSRF)
        assert send_inv.status_code == 409
        assert send_inv.json()["code"] == "invalid_requisites"

        # Lifecycle: checked -> recheck -> postpone -> edit/resume -> cancel
        p = client.post(
            "/api/v1/payments",
            json=_to_payment_input(queue["Q-001"]),
            headers=CSRF,
        ).json()
        pid = p["id"]

        # Recheck in checked creates new check row
        r_recheck = client.post(f"/api/v1/payments/{pid}/recheck", headers=CSRF)
        assert r_recheck.status_code == 200
        assert r_recheck.json()["check"]["check_id"] != p["check"]["check_id"]

        # Resume while checked -> 409 invalid_transition
        assert client.post(f"/api/v1/payments/{pid}/resume", headers=CSRF).status_code == 409

        # Postpone
        r_post = client.post(
            f"/api/v1/payments/{pid}/postpone",
            json={"note": "Ждём акт"},
            headers=CSRF,
        )
        assert r_post.status_code == 200
        assert r_post.json()["status"] == "postponed"
        assert r_post.json()["permissions"]["can_resume"] is True
        assert r_post.json()["permissions"]["can_edit"] is True
        assert r_post.json()["permissions"]["can_sign"] is False

        # Second postpone -> 409 invalid_transition
        assert client.post(f"/api/v1/payments/{pid}/postpone", headers=CSRF).status_code == 409

        # Resume -> checked with fresh check row (trigger='resume')
        r_resume = client.post(f"/api/v1/payments/{pid}/resume", headers=CSRF)
        assert r_resume.status_code == 200
        assert r_resume.json()["status"] == "checked"
        assert r_resume.json()["check"]["check_id"] != r_recheck.json()["check"]["check_id"]

        # Cancel -> cancelled
        r_cancel = client.post(
            f"/api/v1/payments/{pid}/cancel",
            json={"note": "Отменено по просьбе поставщика"},
            headers=CSRF,
        )
        assert r_cancel.status_code == 200
        assert r_cancel.json()["status"] == "cancelled"
        assert r_cancel.json()["permissions"]["can_edit"] is False
        assert r_cancel.json()["permissions"]["can_cancel"] is False

        # Cancelled payment cannot be edited, postponed, resumed, sent, or cancelled again
        assert client.put(
            f"/api/v1/payments/{pid}",
            json=_to_payment_input(queue["Q-001"]),
            headers=CSRF,
        ).status_code == 409
        for suffix in ("postpone", "resume", "send-to-director", "cancel"):
            resp = client.post(f"/api/v1/payments/{pid}/{suffix}", headers=CSRF)
            assert resp.status_code == 409
            assert resp.json()["code"] == "invalid_transition"

        # Verify checks triggers and full audit chain integrity
        conn = connect(db_path)
        try:
            triggers = [
                r["trigger"]
                for r in conn.execute(
                    "SELECT trigger FROM checks WHERE payment_id = ? ORDER BY rowid ASC",
                    (pid,),
                ).fetchall()
            ]
            assert triggers == ["create", "recheck", "resume"]
            assert verify_chain(conn).ok is True
        finally:
            conn.close()
