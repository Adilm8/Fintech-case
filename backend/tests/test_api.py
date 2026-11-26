"""API integration tests using FastAPI TestClient."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.store import store


@pytest.fixture(autouse=True)
def _reset_store() -> Generator[None]:
    store.reset()
    yield
    store.reset()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _queue_item_to_check_request(item: dict) -> dict:
    return {
        "payer_id": item["payer_id"],
        "recipient_name": item["recipient_name"],
        "recipient_bin": item["recipient_bin"],
        "recipient_iik": item["recipient_iik"],
        "recipient_bik": item["recipient_bik"],
        "amount_kzt": item["amount_kzt"],
        "purpose": item["purpose"],
    }


class TestPaymentsAndHistoryEndpoints:
    def test_cors_allows_localhost_3000(self, client: TestClient) -> None:
        resp = client.options(
            "/api/payments/queue",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.status_code == 200
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"

    def test_get_payments_queue_precomputes_all_four_verdicts(self, client: TestClient) -> None:
        resp = client.get("/api/payments/queue")
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 4
        for item in items:
            assert item["check"]["verdict"] == item["scenario"]

    def test_post_payments_check_valid_and_invalid(self, client: TestClient) -> None:
        queue = client.get("/api/payments/queue").json()
        green_req = _queue_item_to_check_request(queue[0])

        ok_resp = client.post("/api/payments/check", json=green_req)
        assert ok_resp.status_code == 200
        assert ok_resp.json()["verdict"] == "green"

        bad_req = {**green_req, "recipient_iik": "KZ86125KZT5004100101"}
        bad_resp = client.post("/api/payments/check", json=bad_req)
        assert bad_resp.status_code == 200
        assert bad_resp.json()["verdict"] == "invalid"
        assert bad_resp.json()["headline_ru"] == "Ошибка в реквизитах"

    def test_get_history(self, client: TestClient) -> None:
        resp = client.get("/api/history")
        assert resp.status_code == 200
        body = resp.json()
        assert body["client"]["name"] == "ТОО «ТехноСтрой Астана»"
        assert len(body["payments"]) == 30


class TestApprovalWorkflow:
    def test_yellow_approve_with_trust_turns_green_and_reset_reverts(
        self, client: TestClient
    ) -> None:
        queue = client.get("/api/payments/queue").json()
        yellow_item = next(q for q in queue if q["scenario"] == "yellow")
        yellow_req = _queue_item_to_check_request(yellow_item)

        # 1. Initial check is yellow
        initial = client.post("/api/payments/check", json=yellow_req)
        assert initial.status_code == 200
        assert initial.json()["verdict"] == "yellow"

        # 2. Accountant submits for director approval
        created = client.post(
            "/api/approvals",
            json={
                "check_request": yellow_req,
                "accountant_note": "Поставщик прислал письмо о смене банка.",
            },
        )
        assert created.status_code == 200
        approval = created.json()
        assert approval["status"] == "pending"
        assert approval["check"]["verdict"] == "yellow"
        approval_id = approval["id"]

        listed = client.get("/api/approvals")
        assert listed.status_code == 200
        assert len(listed.json()) == 1
        assert listed.json()[0]["id"] == approval_id

        # 3. Director approves and marks account as trusted
        decided = client.post(
            f"/api/approvals/{approval_id}/decision",
            json={
                "decision": "approved",
                "director_comment": "Подтвердил по телефону из договора.",
                "trust_account": True,
            },
        )
        assert decided.status_code == 200
        decided_body = decided.json()
        assert decided_body["status"] == "approved"
        assert decided_body["trust_account"] is True
        assert decided_body["decided_at"] is not None

        # 4. Re-check of the same payment is now green (both direct check and queue)
        rechecked = client.post("/api/payments/check", json=yellow_req)
        assert rechecked.status_code == 200
        assert rechecked.json()["verdict"] == "green"
        assert rechecked.json()["score"] == 0

        updated_queue = client.get("/api/payments/queue").json()
        updated_yellow = next(q for q in updated_queue if q["scenario"] == "yellow")
        assert updated_yellow["check"]["verdict"] == "green"

        # 5. Reset clears approvals and trusted set -> yellow returns to yellow
        reset_resp = client.post("/api/demo/reset")
        assert reset_resp.status_code == 200
        assert reset_resp.json() == {
            "status": "reset",
            "approvals_count": 0,
            "trusted_accounts_count": 0,
        }
        assert client.get("/api/approvals").json() == []
        after_reset = client.post("/api/payments/check", json=yellow_req)
        assert after_reset.json()["verdict"] == "yellow"

    def test_red_decision_requires_director_comment(self, client: TestClient) -> None:
        queue = client.get("/api/payments/queue").json()
        red_item = next(q for q in queue if q["scenario"] == "red")
        red_req = _queue_item_to_check_request(red_item)

        approval = client.post(
            "/api/approvals",
            json={"check_request": red_req, "accountant_note": "Подозрительный счёт"},
        ).json()
        assert approval["check"]["verdict"] == "red"
        approval_id = approval["id"]

        # Missing, empty, and whitespace-only comments all return 422
        for bad_comment in (None, "", "   "):
            resp = client.post(
                f"/api/approvals/{approval_id}/decision",
                json={
                    "decision": "rejected",
                    "director_comment": bad_comment,
                    "trust_account": False,
                },
            )
            assert resp.status_code == 422

        # Non-empty comment succeeds
        ok_resp = client.post(
            f"/api/approvals/{approval_id}/decision",
            json={
                "decision": "rejected",
                "director_comment": "Подтвердили у поставщика — письмо поддельное.",
                "trust_account": True,  # rejected must never trust
            },
        )
        assert ok_resp.status_code == 200
        body = ok_resp.json()
        assert body["status"] == "rejected"
        assert body["trust_account"] is False
        assert store.trusted_accounts == set()

    def test_rejected_yellow_never_trusts_account(self, client: TestClient) -> None:
        queue = client.get("/api/payments/queue").json()
        yellow_item = next(q for q in queue if q["scenario"] == "yellow")
        yellow_req = _queue_item_to_check_request(yellow_item)

        approval_id = client.post(
            "/api/approvals",
            json={"check_request": yellow_req, "accountant_note": "Проверить"},
        ).json()["id"]

        decided = client.post(
            f"/api/approvals/{approval_id}/decision",
            json={
                "decision": "rejected",
                "director_comment": "Не подтверждено",
                "trust_account": True,
            },
        )
        assert decided.status_code == 200
        assert decided.json()["trust_account"] is False

        rechecked = client.post("/api/payments/check", json=yellow_req)
        assert rechecked.json()["verdict"] == "yellow"

    def test_decision_for_unknown_approval_returns_404(self, client: TestClient) -> None:
        resp = client.post(
            "/api/approvals/apr-missing/decision",
            json={"decision": "rejected", "director_comment": "Нет заявки"},
        )
        assert resp.status_code == 404
