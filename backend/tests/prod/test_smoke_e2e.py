"""End-to-end smoke test for full production workflow, restart persistence, and demo isolation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.asgi import select_app
from app.prod.app import create_prod_app
from app.prod.deps import CSRF_HEADER_NAME, CSRF_HEADER_VALUE
from app.prod.seed import seed_database
from app.settings import Settings
from app.store import DEFAULT_DATA_DIR
from tests.prod.conftest import TEST_SEED_PW, TEST_TODAY

CSRF: dict[str, str] = {CSRF_HEADER_NAME: CSRF_HEADER_VALUE}
OCTET_HEADERS: dict[str, str] = {**CSRF, "Content-Type": "application/octet-stream"}
SAMPLES_DIR: Path = DEFAULT_DATA_DIR / "samples"


def _login(client: TestClient, login: str, password: str = TEST_SEED_PW) -> None:
    resp = client.post(
        "/api/v1/auth/login",
        json={"login": login, "password": password},
        headers=CSRF,
    )
    assert resp.status_code == 200, resp.text


def test_default_asgi_serves_demo_and_hides_prod_meta(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APP_MODE", raising=False)
    demo_app = select_app()
    with TestClient(demo_app) as client:
        q_resp = client.get("/api/payments/queue")
        assert q_resp.status_code == 200
        assert len(q_resp.json()) == 10

        prod_meta = client.get("/api/v1/meta")
        assert prod_meta.status_code == 404


def test_full_prod_e2e_workflow_and_restart_persistence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "e2e_shield.db"
    monkeypatch.setenv("APP_MODE", "prod")
    monkeypatch.setenv("SHIELD_DB_PATH", str(db_path))
    monkeypatch.setenv("SHIELD_TODAY", TEST_TODAY.isoformat())
    monkeypatch.setenv("SHIELD_SEED_PASSWORD", TEST_SEED_PW)

    # 1. Seed temp DB with --reset and --with-queue (1 company, 3 users, 150 signed, 10 queue, 12 suppliers)
    summary = seed_database(reset=True, with_queue=True)
    assert summary.users_count == 3
    assert summary.signed_payments_count == 150
    assert summary.queue_payments_count == 10
    assert summary.suppliers_count == 12

    cfg = Settings(
        app_mode="prod",
        db_path=db_path,
        today_override=TEST_TODAY,
        cookie_secure=False,
    )
    prod_app = create_prod_app(db_path=db_path, settings_override=cfg)

    with (
        TestClient(prod_app) as acc,
        TestClient(prod_app) as director,
        TestClient(prod_app) as analyst,
    ):
        # Verify prod app exposes /api/v1/meta and hides demo routes
        assert acc.get("/api/v1/meta").status_code == 200
        assert acc.get("/api/payments/queue").status_code == 404
        assert acc.post("/api/demo/reset").status_code == 404

        # 2. Accountant login & create a manual green payment
        _login(acc, "accountant")
        queue_raw = json.loads((DEFAULT_DATA_DIR / "queue.json").read_text(encoding="utf-8"))
        q8 = next(item for item in queue_raw if item["id"] == "Q-008")
        manual_resp = acc.post(
            "/api/v1/payments",
            json={
                "recipient_name": q8["recipient_name"],
                "recipient_bin": q8["recipient_bin"],
                "recipient_iik": q8["recipient_iik"],
                "recipient_bik": q8["recipient_bik"],
                "amount_kzt": q8["amount_kzt"],
                "purpose": "Ручной тестовый платёж по акту № 950",
                "doc_number": "MAN-1",
                "doc_date": TEST_TODAY.isoformat(),
            },
            headers=CSRF,
        )
        assert manual_resp.status_code == 201
        manual_id = manual_resp.json()["id"]
        assert manual_resp.json()["check"]["verdict"] == "green"

        # 3. Import sample_1c.txt (cp1251, 6 docs -> 5 payments + 1 warning)
        # Note: because --with-queue already has active pay-q-002 (КазЛогистик Групп),
        # doc 102 escalates via structuring_72h on top of iik+bank change; pay-q-002 is yellow.
        imp_resp = acc.post(
            "/api/v1/payments/import?filename=sample_1c.txt",
            content=(SAMPLES_DIR / "sample_1c.txt").read_bytes(),
            headers=OCTET_HEADERS,
        )
        assert imp_resp.status_code == 201
        imp_data = imp_resp.json()
        batch_id = imp_data["batch"]["id"]
        assert len(imp_data["items"]) == 5
        assert len(imp_data["errors"]) == 1
        by_doc = {item["doc_number"]: item for item in imp_data["items"]}
        assert by_doc["101"]["check"]["verdict"] == "green"
        assert by_doc["103"]["check"]["verdict"] == "red"
        assert by_doc["104"]["check"]["verdict"] == "grey"
        assert by_doc["105"]["check"]["verdict"] == "invalid"

        green_id = by_doc["101"]["id"]
        red_imported_id = by_doc["103"]["id"]
        invalid_id = by_doc["105"]["id"]

        # 4. Batch sign-green on the imported batch -> signs ONLY green (doc 101)
        sg_resp = acc.post(
            "/api/v1/payments/batch/sign-green",
            json={"batch_id": batch_id},
            headers=CSRF,
        )
        assert sg_resp.status_code == 200
        assert [p["id"] for p in sg_resp.json()["done"]] == [green_id]
        assert len(sg_resp.json()["skipped"]) == 4

        # 5. Batch send-to-director on the imported batch -> sends non-green/non-invalid; leaves invalid untouched
        sd_resp = acc.post(
            "/api/v1/payments/batch/send-to-director",
            json={"batch_id": batch_id, "accountant_note": "На согласование директору"},
            headers=CSRF,
        )
        assert sd_resp.status_code == 200
        assert {p["id"] for p in sd_resp.json()["done"]} == {
            by_doc["102"]["id"],
            red_imported_id,
            by_doc["104"]["id"],
        }
        assert [s["id"] for s in sd_resp.json()["skipped"]] == [invalid_id]
        assert sd_resp.json()["skipped"][0]["code"] == "invalid_requisites"

        # Also send seeded yellow pay-q-002 to director (eligible for trust_account)
        send_q2 = acc.post(
            "/api/v1/payments/pay-q-002/send-to-director",
            json={"accountant_note": "Подтвердите смену банка поставщика"},
            headers=CSRF,
        )
        assert send_q2.status_code == 200
        assert send_q2.json()["check"]["verdict"] == "yellow"
        apr_yellow_id = send_q2.json()["approval"]["id"]

        # 6. Director login: approve yellow (pay-q-002) WITH trust, reject red (doc 103)
        _login(director, "director")
        aprs = director.get("/api/v1/approvals").json()
        apr_by_pay = {a["payment_id"]: a for a in aprs}
        apr_red_id = apr_by_pay[red_imported_id]["id"]
        assert apr_by_pay["pay-q-002"]["can_trust"] is True

        dec_yellow = director.post(
            f"/api/v1/approvals/{apr_yellow_id}/decision",
            json={
                "decision": "approved",
                "director_comment": "Подтвердили смену счёта по телефону из договора",
                "trust_account": True,
            },
            headers=CSRF,
        )
        assert dec_yellow.status_code == 200
        assert dec_yellow.json()["status"] == "approved"
        assert dec_yellow.json()["trust_account"] is True

        dec_red = director.post(
            f"/api/v1/approvals/{apr_red_id}/decision",
            json={"decision": "rejected", "director_comment": "Подмена реквизитов, не оплачивать"},
            headers=CSRF,
        )
        assert dec_red.status_code == 200
        assert dec_red.json()["status"] == "rejected"

        # 7. Accountant signs approved yellow payment (pay-q-002); trying to sign rejected red -> 409 approval_rejected
        sign_approved = acc.post(
            "/api/v1/payments/pay-q-002/sign",
            json={},
            headers=CSRF,
        )
        assert sign_approved.status_code == 200
        assert sign_approved.json()["status"] == "signed"

        sign_rejected = acc.post(
            f"/api/v1/payments/{red_imported_id}/sign",
            json={"accountant_ack": True},
            headers=CSRF,
        )
        assert sign_rejected.status_code == 409
        assert sign_rejected.json()["code"] == "approval_rejected"

        # 8. Direct API attempt to sign an unapproved red payment (seeded pay-q-003) -> 409 red_requires_approval + sign_denied
        sign_unapproved_red = acc.post(
            "/api/v1/payments/pay-q-003/sign",
            json={"accountant_ack": True},
            headers=CSRF,
        )
        assert sign_unapproved_red.status_code == 409
        assert sign_unapproved_red.json()["code"] == "red_requires_approval"

        # 9. Analyst verifies sign_denied in audit log, hash chain integrity, and metrics
        _login(analyst, "analyst")
        denied_entries = analyst.get(
            "/api/v1/audit?payment_id=pay-q-003&action=sign_denied"
        ).json()
        assert len(denied_entries) == 1
        assert denied_entries[0]["details"]["code"] == "red_requires_approval"

        verify_resp = analyst.get("/api/v1/audit/verify")
        assert verify_resp.status_code == 200
        verify_data = verify_resp.json()
        assert verify_data["ok"] is True
        assert verify_data["checked"] >= 20
        assert verify_data["broken_at"] is None

        metrics_resp = analyst.get("/api/v1/metrics")
        assert metrics_resp.status_code == 200
        assert metrics_resp.json()["summary"]["total_cases"] == 400

    # 10. Simulate backend restart: brand-new app instance pointed at the exact same SQLite DB
    restarted_app = create_prod_app(db_path=db_path, settings_override=cfg)
    with TestClient(restarted_app) as restarted_acc, TestClient(restarted_app) as restarted_analyst:
        _login(restarted_acc, "accountant")
        _login(restarted_analyst, "analyst")

        assert restarted_acc.get(f"/api/v1/payments/{manual_id}").json()["status"] == "checked"
        assert restarted_acc.get(f"/api/v1/payments/{green_id}").json()["status"] == "signed"
        assert restarted_acc.get("/api/v1/payments/pay-q-002").json()["status"] == "signed"
        assert (
            restarted_acc.get(f"/api/v1/payments/{red_imported_id}").json()["status"] == "rejected"
        )

        # Signed count is 150 (seed) + 2 (doc 101 green + approved pay-q-002) = 152
        signed_list = restarted_acc.get("/api/v1/payments?scope=signed&limit=5").json()
        assert signed_list["total"] == 152

        # Batch persisted
        batches = restarted_acc.get("/api/v1/batches").json()
        assert any(b["id"] == batch_id for b in batches)

        # Supplier directory recorded the newly signed yellow account change and trust
        klg = restarted_acc.get("/api/v1/suppliers?q=180947320524").json()[0]
        assert klg["accounts_count"] == 2
        assert klg["trusted_accounts_count"] == 1
        assert klg["requisites_changed_days_ago"] == 0

        # Audit chain remains intact after restart
        verify_after = restarted_analyst.get("/api/v1/audit/verify").json()
        assert verify_after["ok"] is True
        assert verify_after["broken_at"] is None
