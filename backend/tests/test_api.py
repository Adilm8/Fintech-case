"""API integration tests using FastAPI TestClient."""

from __future__ import annotations

import json
import random
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.risk.config import DEMO_TODAY
from app.store import store
from scripts.generate_data import generate_iin


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


class TestCorsAndInfrastructure:
    @pytest.mark.parametrize(
        "origin",
        [
            "http://localhost:3000",
            "https://localhost:8443",
            "http://127.0.0.1:3000",
            "http://192.168.1.42:3000",
            "https://10.0.0.15:8080",
            "http://10.12.34.56",
        ],
    )
    def test_cors_allows_local_and_private_network_origins(
        self, client: TestClient, origin: str
    ) -> None:
        resp = client.options(
            "/api/payments/queue",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.status_code == 200
        assert resp.headers.get("access-control-allow-origin") == origin

    @pytest.mark.parametrize(
        "origin",
        [
            "https://evil.example.com",
            "http://localhost.evil.com",
            "http://172.16.0.1:3000",
        ],
    )
    def test_cors_rejects_external_origins(self, client: TestClient, origin: str) -> None:
        resp = client.options(
            "/api/payments/queue",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.headers.get("access-control-allow-origin") is None

    def test_global_exception_handler_returns_russian_500(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _boom(*args, **kwargs):
            raise RuntimeError("unexpected failure")

        monkeypatch.setattr("app.main.check_payment", _boom)
        non_raising_client = TestClient(app, raise_server_exceptions=False)
        queue = store.queue
        resp = non_raising_client.post(
            "/api/payments/check",
            json=_queue_item_to_check_request(queue[0]),
        )
        assert resp.status_code == 500
        body = resp.json()
        assert "detail" in body
        assert "внутренняя ошибка" in body["detail"].lower()


class TestPaymentsSchemaValidationAndHistory:
    def test_get_payments_queue_precomputes_all_four_verdicts(self, client: TestClient) -> None:
        resp = client.get("/api/payments/queue")
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 10
        assert [item["id"] for item in items[:4]] == ["Q-001", "Q-002", "Q-003", "Q-004"]
        assert [item["scenario"] for item in items[:4]] == ["green", "yellow", "red", "grey"]
        for item in items:
            assert item["check"]["verdict"] == item["scenario"]
            assert item["check"]["trusted"] is False
            assert item["check"]["trusted_info"] is None

        red_item = next(item for item in items if item["scenario"] == "red")
        assert len(red_item["check"]["signals"]) >= 7
        assert red_item["check"]["history"]["compared_with"] == "ТОО «Алатау Снаб»"
        name_diff = next(d for d in red_item["check"]["comparison"] if d["field"] == "name")
        assert name_diff["differs"] is True
        assert name_diff["diff_positions"] == [12]

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

    def test_red_scenario_remains_red_across_all_three_variants_via_api(
        self, client: TestClient
    ) -> None:
        queue = client.get("/api/payments/queue").json()
        red_item = next(q for q in queue if q["scenario"] == "red")
        red_req = _queue_item_to_check_request(red_item)

        # (a) With BCC owner block
        res_a = client.post("/api/payments/check", json=red_req)
        assert res_a.status_code == 200
        assert res_a.json()["verdict"] == "red"

        # (b) With Вектор Трейд's own BIN (no BCC block)
        vektor_bin = store.bcc_accounts[red_req["recipient_iik"]]["owner_bin"]
        res_b = client.post("/api/payments/check", json={**red_req, "recipient_bin": vektor_bin})
        assert res_b.status_code == 200
        assert res_b.json()["verdict"] == "red"

        # (c) With an external IIK not in BCC registry
        from scripts.generate_data import generate_iik

        ext_iik = generate_iik(random.Random(1404), "722", prefix="000")
        res_c = client.post(
            "/api/payments/check",
            json={**red_req, "recipient_iik": ext_iik, "recipient_bik": "CASPKZKA"},
        )
        assert res_c.status_code == 200
        assert res_c.json()["verdict"] == "red"

    def test_requisites_normalization_strips_spaces_nbsp_invisible_and_uppercases_ascii(
        self, client: TestClient
    ) -> None:
        queue = client.get("/api/payments/queue").json()
        green_req = _queue_item_to_check_request(queue[0])

        messy_req = {
            **green_req,
            "recipient_bin": f" {green_req['recipient_bin'][:4]}\u00a0{green_req['recipient_bin'][4:]}\u200b ",
            "recipient_iik": f" {green_req['recipient_iik'][:4].lower()} \u200b{green_req['recipient_iik'][4:].lower()}\ufeff ",
            "recipient_bik": f"\u00a0{green_req['recipient_bik'].lower()}\u200c ",
        }
        resp = client.post("/api/payments/check", json=messy_req)
        assert resp.status_code == 200
        body = resp.json()
        assert body["verdict"] == "green"

        # Cyrillic lookalike inside IIK must still be rejected as invalid (not mangled)
        cyrillic_iik = "\u041a" + green_req["recipient_iik"][1:].lower()
        cyr_resp = client.post(
            "/api/payments/check",
            json={**green_req, "recipient_iik": f" {cyrillic_iik}\u00a0"},
        )
        assert cyr_resp.status_code == 200
        assert cyr_resp.json()["verdict"] == "invalid"
        assert "кириллич" in cyr_resp.json()["signals"][0]["reason_ru"].lower()

    def test_default_and_unknown_payer_id(self, client: TestClient) -> None:
        queue = client.get("/api/payments/queue").json()
        green_req = _queue_item_to_check_request(queue[0])

        # Omitted payer_id defaults to client from store
        without_payer = {k: v for k, v in green_req.items() if k != "payer_id"}
        resp_default = client.post("/api/payments/check", json=without_payer)
        assert resp_default.status_code == 200
        assert resp_default.json()["verdict"] == "green"
        assert resp_default.json()["history"]["payments_count"] >= 5

        # Unknown payer_id returns 422 with Russian detail
        resp_unknown = client.post(
            "/api/payments/check",
            json={**green_req, "payer_id": "unknown-client-999"},
        )
        assert resp_unknown.status_code == 422
        assert "неизвестный плательщик" in resp_unknown.json()["detail"].lower()

    @pytest.mark.parametrize(
        ("field", "bad_value"),
        [
            ("amount_kzt", 0),
            ("amount_kzt", -100),
            ("amount_kzt", 1e12 + 1),
            ("recipient_name", ""),
            ("recipient_name", "   \u200b  "),
            ("recipient_name", "А" * 251),
            ("purpose", "П" * 501),
        ],
    )
    def test_schema_constraints_return_russian_422(
        self, client: TestClient, field: str, bad_value: object
    ) -> None:
        queue = client.get("/api/payments/queue").json()
        req = {**_queue_item_to_check_request(queue[0]), field: bad_value}
        resp = client.post("/api/payments/check", json=req)
        assert resp.status_code == 422
        body = resp.json()
        assert "detail" in body
        assert any("\u0400" <= ch <= "\u04ff" for ch in body["detail"])

    @pytest.mark.parametrize("raw_amount", ["NaN", "Infinity", "-Infinity"])
    def test_inf_nan_amount_rejected_with_russian_422(
        self, client: TestClient, raw_amount: str
    ) -> None:
        queue = client.get("/api/payments/queue").json()
        base = _queue_item_to_check_request(queue[0])
        base["amount_kzt"] = 123
        raw_json = json.dumps(base, ensure_ascii=False).replace("123", raw_amount, 1)
        resp = client.post(
            "/api/payments/check",
            content=raw_json.encode("utf-8"),
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 422
        assert any("\u0400" <= ch <= "\u04ff" for ch in resp.json()["detail"])

    def test_comment_max_length_validation(self, client: TestClient) -> None:
        queue = client.get("/api/payments/queue").json()
        yellow_req = _queue_item_to_check_request(
            next(q for q in queue if q["scenario"] == "yellow")
        )

        too_long_note = client.post(
            "/api/approvals",
            json={"check_request": yellow_req, "accountant_note": "Б" * 1001},
        )
        assert too_long_note.status_code == 422
        assert any("\u0400" <= ch <= "\u04ff" for ch in too_long_note.json()["detail"])

        approval_id = client.post(
            "/api/approvals",
            json={"check_request": yellow_req, "accountant_note": "Нормальная заметка"},
        ).json()["id"]
        too_long_comment = client.post(
            f"/api/approvals/{approval_id}/decision",
            json={
                "decision": "approved",
                "director_comment": "Д" * 1001,
                "trust_account": True,
            },
        )
        assert too_long_comment.status_code == 422
        assert any("\u0400" <= ch <= "\u04ff" for ch in too_long_comment.json()["detail"])

    def test_get_history(self, client: TestClient) -> None:
        resp = client.get("/api/history")
        assert resp.status_code == 200
        body = resp.json()
        assert body["client"]["name"] == "ТОО «ТехноСтрой Астана»"
        assert len(body["payments"]) == 150

    def test_get_metrics_returns_cached_evaluation_report(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        resp1 = client.get("/api/metrics")
        assert resp1.status_code == 200
        body1 = resp1.json()
        assert body1["seed"] == 42
        assert body1["positive_verdicts"] == ["yellow", "red"]
        assert body1["summary"]["total_cases"] == 400
        assert body1["summary"]["total_legit"] == 200
        assert body1["summary"]["total_attack"] == 200
        for metric_key in ("detection_rate", "false_positive_rate", "precision", "f1", "accuracy"):
            assert 0.0 <= body1["summary"][metric_key] <= 1.0
        assert set(body1["confusion"].keys()) == {"tp", "fn", "fp", "tn"}
        assert body1["confusion"]["tp"] + body1["confusion"]["fn"] == 200
        assert body1["confusion"]["fp"] + body1["confusion"]["tn"] == 200
        assert set(body1["verdict_by_label"].keys()) == {"legit", "attack"}
        assert len(body1["by_kind"]) >= 10
        for row in body1["by_kind"]:
            if row["label"] == "attack":
                assert row["detection_rate"] is not None
                assert row["false_positive_rate"] is None
            else:
                assert row["false_positive_rate"] is not None
                assert row["detection_rate"] is None
        assert "синтетич" in body1["disclaimer_ru"].lower()

        # Subsequent call must use the cached metrics without re-running evaluate_dataset
        def _must_not_recompute(*args, **kwargs):
            raise AssertionError("GET /api/metrics should serve cached result")

        monkeypatch.setattr("app.main.evaluate_dataset", _must_not_recompute)
        resp2 = client.get("/api/metrics")
        assert resp2.status_code == 200
        assert resp2.json() == body1


class TestApprovalWorkflowAndTrustModel:
    def test_yellow_approve_with_trust_turns_green_trusted_and_reset_reverts(
        self, client: TestClient
    ) -> None:
        queue = client.get("/api/payments/queue").json()
        yellow_item = next(q for q in queue if q["scenario"] == "yellow")
        yellow_req = _queue_item_to_check_request(yellow_item)

        # 1. Initial check is yellow and not trusted
        initial = client.post("/api/payments/check", json=yellow_req)
        assert initial.status_code == 200
        assert initial.json()["verdict"] == "yellow"
        assert initial.json()["trusted"] is False
        assert initial.json()["trusted_info"] is None

        # 2. Accountant submits for director approval (and duplicate returns the same pending item)
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

        duplicate = client.post(
            "/api/approvals",
            json={
                "check_request": {k: v for k, v in yellow_req.items() if k != "payer_id"},
                "accountant_note": "Повторная отправка",
            },
        )
        assert duplicate.status_code == 200
        assert duplicate.json()["id"] == approval_id
        assert len(client.get("/api/approvals").json()) == 1

        # 3. Filtering GET /api/approvals by bin & iik
        filtered = client.get(
            "/api/approvals",
            params={
                "bin": f" {yellow_req['recipient_bin']} ",
                "iik": yellow_req["recipient_iik"].lower(),
            },
        )
        assert filtered.status_code == 200
        assert [a["id"] for a in filtered.json()] == [approval_id]
        assert client.get("/api/approvals", params={"bin": "000000000000"}).json() == []

        # 4. Short/invisible comment for trust_account -> 422
        for short_comment in (None, "", "   \u200b\u00a0  ", "о к 1 2 3 4 5"):
            resp_short = client.post(
                f"/api/approvals/{approval_id}/decision",
                json={
                    "decision": "approved",
                    "director_comment": short_comment,
                    "trust_account": True,
                },
            )
            assert resp_short.status_code == 422

        # 5. Director approves and marks account as trusted with valid comment (>=10 chars)
        director_comment = "Подтвердил по телефону из договора."
        decided = client.post(
            f"/api/approvals/{approval_id}/decision",
            json={
                "decision": "approved",
                "director_comment": director_comment,
                "trust_account": True,
            },
        )
        assert decided.status_code == 200
        decided_body = decided.json()
        assert decided_body["status"] == "approved"
        assert decided_body["trust_account"] is True
        assert decided_body["decided_at"].startswith(DEMO_TODAY.isoformat())

        # Trust is stored by (payer_id, bin, iik) with decided_at & director_comment
        trust_key = (
            yellow_req["payer_id"],
            yellow_req["recipient_bin"],
            yellow_req["recipient_iik"],
        )
        assert trust_key in store.trusted_accounts
        assert store.trusted_accounts[trust_key].decided_at == decided_body["decided_at"]
        assert store.trusted_accounts[trust_key].director_comment == director_comment

        # 6. Re-deciding an already decided approval -> 409
        repeat_decision = client.post(
            f"/api/approvals/{approval_id}/decision",
            json={"decision": "rejected"},
        )
        assert repeat_decision.status_code == 409

        # 7. Re-check of the same payment is green + trusted + headline + comparison overrides
        rechecked = client.post("/api/payments/check", json=yellow_req)
        assert rechecked.status_code == 200
        rechecked_body = rechecked.json()
        assert rechecked_body["verdict"] == "green"
        assert rechecked_body["score"] == 0
        assert rechecked_body["trusted"] is True
        assert rechecked_body["trusted_info"] == {
            "decided_at": decided_body["decided_at"],
            "director_comment": director_comment,
        }
        assert rechecked_body["headline_ru"] == "Счёт подтверждён директором"
        assert [s["rule_id"] for s in rechecked_body["signals"]] == ["trusted_account"]
        assert (
            "Новый счёт подтверждён директором 20.04.2026"
            in (rechecked_body["signals"][0]["reason_ru"])
        )
        for field_name in ("iik", "bik", "bank"):
            row = next(d for d in rechecked_body["comparison"] if d["field"] == field_name)
            assert row["differs"] is False

        updated_queue = client.get("/api/payments/queue").json()
        updated_yellow = next(q for q in updated_queue if q["scenario"] == "yellow")
        assert updated_yellow["check"]["verdict"] == "green"
        assert updated_yellow["check"]["trusted"] is True

        # 8. Reset clears approvals and trusted dict -> yellow returns to yellow
        reset_resp = client.post("/api/demo/reset")
        assert reset_resp.status_code == 200
        assert reset_resp.json() == {
            "status": "reset",
            "approvals_count": 0,
            "trusted_accounts_count": 0,
        }
        assert client.get("/api/approvals").json() == []
        after_reset = client.post("/api/payments/check", json=yellow_req).json()
        assert after_reset["verdict"] == "yellow"
        assert after_reset["trusted"] is False
        assert after_reset["trusted_info"] is None

    def test_trust_account_disallowed_for_non_eligible_verdicts_and_signals(
        self, client: TestClient
    ) -> None:
        queue = client.get("/api/payments/queue").json()
        long_comment = "Проверено и подтверждено директором"

        # Green, red, and grey cannot be trusted -> 422 "Доверие недоступно для этого платежа"
        for scenario in ("green", "red", "grey"):
            item = next(q for q in queue if q["scenario"] == scenario)
            approval_id = client.post(
                "/api/approvals",
                json={"check_request": _queue_item_to_check_request(item)},
            ).json()["id"]
            resp = client.post(
                f"/api/approvals/{approval_id}/decision",
                json={
                    "decision": "approved",
                    "director_comment": long_comment,
                    "trust_account": True,
                },
            )
            assert resp.status_code == 422
            assert resp.json()["detail"] == "Доверие недоступно для этого платежа"

        # Yellow WITHOUT iik_changed/bank_changed (entity_type_mismatch 25 + urgent_wording 10 = 35)
        grey_item = next(q for q in queue if q["scenario"] == "grey")
        rng = random.Random(707)
        yellow_no_account_change = {
            **_queue_item_to_check_request(grey_item),
            "recipient_bin": generate_iin(rng),
            "purpose": "Оплата срочно по счёту",
        }
        created = client.post(
            "/api/approvals",
            json={"check_request": yellow_no_account_change},
        ).json()
        assert created["check"]["verdict"] == "yellow"
        resp = client.post(
            f"/api/approvals/{created['id']}/decision",
            json={
                "decision": "approved",
                "director_comment": long_comment,
                "trust_account": True,
            },
        )
        assert resp.status_code == 422
        assert resp.json()["detail"] == "Доверие недоступно для этого платежа"

    def test_red_approval_requires_10_char_comment_while_rejection_requires_none(
        self, client: TestClient
    ) -> None:
        queue = client.get("/api/payments/queue").json()
        red_item = next(q for q in queue if q["scenario"] == "red")
        red_req = _queue_item_to_check_request(red_item)

        approval = client.post(
            "/api/approvals",
            json={"check_request": red_req, "accountant_note": "Подозрительный счёт"},
        ).json()
        assert approval["check"]["verdict"] == "red"
        approval_id = approval["id"]

        # Approving red without >=10 meaningful chars -> 422
        for bad_comment in (None, "", "   ", "\u200b" * 15, "1 2 3 4 5 6 7 8 9"):
            resp = client.post(
                f"/api/approvals/{approval_id}/decision",
                json={
                    "decision": "approved",
                    "director_comment": bad_comment,
                    "trust_account": False,
                },
            )
            assert resp.status_code == 422

        # Rejecting red requires NO comment at all -> 200
        reject_resp = client.post(
            f"/api/approvals/{approval_id}/decision",
            json={"decision": "rejected", "director_comment": None, "trust_account": True},
        )
        assert reject_resp.status_code == 200
        body = reject_resp.json()
        assert body["status"] == "rejected"
        assert body["trust_account"] is False
        assert store.trusted_accounts == {}

        # A new pending approval for red can be approved (without trust) with >=10 meaningful chars
        approval2_id = client.post(
            "/api/approvals",
            json={"check_request": red_req, "accountant_note": "Повторный запрос"},
        ).json()["id"]
        approve_resp = client.post(
            f"/api/approvals/{approval2_id}/decision",
            json={
                "decision": "approved",
                "director_comment": "Лично перезвонил директору поставщика и подтвердил платёж",
                "trust_account": False,
            },
        )
        assert approve_resp.status_code == 200
        assert approve_resp.json()["status"] == "approved"
        assert approve_resp.json()["trust_account"] is False

    def test_invalid_payment_cannot_be_approved_but_can_be_rejected(
        self, client: TestClient
    ) -> None:
        queue = client.get("/api/payments/queue").json()
        invalid_req = {
            **_queue_item_to_check_request(queue[0]),
            "recipient_iik": "KZ86125KZT5004100101",
        }
        approval = client.post(
            "/api/approvals",
            json={"check_request": invalid_req},
        ).json()
        assert approval["check"]["verdict"] == "invalid"

        approve_resp = client.post(
            f"/api/approvals/{approval['id']}/decision",
            json={
                "decision": "approved",
                "director_comment": "Попытка одобрить ошибочный счёт",
                "trust_account": False,
            },
        )
        assert approve_resp.status_code == 422

        reject_resp = client.post(
            f"/api/approvals/{approval['id']}/decision",
            json={"decision": "rejected"},
        )
        assert reject_resp.status_code == 200
        assert reject_resp.json()["status"] == "rejected"

    def test_existing_director_comment_not_overwritten_by_none(self, client: TestClient) -> None:
        queue = client.get("/api/payments/queue").json()
        yellow_req = _queue_item_to_check_request(
            next(q for q in queue if q["scenario"] == "yellow")
        )
        approval_id = client.post(
            "/api/approvals",
            json={"check_request": yellow_req},
        ).json()["id"]

        stored = store.get_approval(approval_id)
        assert stored is not None
        stored.director_comment = "Предварительная заметка директора"

        resp = client.post(
            f"/api/approvals/{approval_id}/decision",
            json={"decision": "rejected", "director_comment": None},
        )
        assert resp.status_code == 200
        assert resp.json()["director_comment"] == "Предварительная заметка директора"

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
                "director_comment": None,
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


class TestI18nApiEndpoints:
    def test_check_and_queue_support_ru_kk_en_with_backwards_compatibility(
        self, client: TestClient
    ) -> None:
        q_ru = client.get("/api/payments/queue").json()
        q_kk = client.get("/api/payments/queue", params={"lang": "kk"}).json()
        q_en = client.get("/api/payments/queue", params={"lang": "en"}).json()

        assert len(q_ru) == len(q_kk) == len(q_en) == 10
        assert q_ru[0]["check"]["headline"] == q_ru[0]["check"]["headline_ru"]
        assert q_kk[0]["check"]["headline_ru"] == q_ru[0]["check"]["headline_ru"]
        assert q_en[0]["check"]["headline_ru"] == q_ru[0]["check"]["headline_ru"]
        assert q_kk[0]["check"]["headline"] != q_ru[0]["check"]["headline_ru"]
        assert q_en[0]["check"]["headline"] != q_ru[0]["check"]["headline_ru"]

        red_req = _queue_item_to_check_request(next(q for q in q_ru if q["id"] == "Q-003"))
        chk_ru = client.post("/api/payments/check", params={"lang": "ru"}, json=red_req)
        chk_kk = client.post("/api/payments/check", params={"lang": "kk"}, json=red_req)
        chk_en = client.post("/api/payments/check", params={"lang": "en"}, json=red_req)
        assert chk_ru.status_code == 200
        assert chk_kk.status_code == 200
        assert chk_en.status_code == 200

        body_ru = chk_ru.json()
        body_kk = chk_kk.json()
        body_en = chk_en.json()
        assert body_ru["headline"] == body_ru["headline_ru"]
        assert body_ru["next_action"]["text"] == body_ru["next_action"]["text_ru"]
        for sig in body_ru["signals"]:
            assert sig["reason"] == sig["reason_ru"]

        assert body_kk["verdict"] == body_en["verdict"] == "red"
        assert body_kk["headline_ru"] == body_en["headline_ru"] == "Похоже на подмену"
        assert body_kk["headline"] != body_kk["headline_ru"]
        assert body_en["headline"] != body_en["headline_ru"]
        assert body_kk["next_action"]["text"] != body_kk["next_action"]["text_ru"]
        assert body_en["next_action"]["text"] != body_en["next_action"]["text_ru"]
        kz_letters = set("әғқңөұүһіӘҒҚҢӨҰҮҺІ")
        assert any(ch in kz_letters for ch in body_kk["headline"])
        assert any(ch in kz_letters for ch in body_kk["next_action"]["text"])
        for sig in body_kk["signals"]:
            assert sig["reason"].strip() and sig["reason"] != sig["reason_ru"]
            assert any(ch in kz_letters for ch in sig["reason"])
        for sig in body_en["signals"]:
            assert sig["reason"].strip() and sig["reason"] != sig["reason_ru"]

    def test_approvals_and_errors_localize_by_lang_param(self, client: TestClient) -> None:
        queue = client.get("/api/payments/queue").json()
        yellow_req = _queue_item_to_check_request(next(q for q in queue if q["id"] == "Q-002"))

        created = client.post(
            "/api/approvals",
            params={"lang": "kk"},
            json={"check_request": yellow_req, "accountant_note": "Тексеру"},
        )
        assert created.status_code == 200
        created_body = created.json()
        assert created_body["check"]["headline_ru"] == "Есть изменения"
        assert created_body["check"]["headline"] != created_body["check"]["headline_ru"]

        # Stored approval re-localizes to English on GET /api/approvals?lang=en
        listed_en = client.get("/api/approvals", params={"lang": "en"})
        assert listed_en.status_code == 200
        item_en = listed_en.json()[0]
        assert item_en["check"]["headline"] == "Changes detected"
        assert item_en["check"]["headline_ru"] == "Есть изменения"

        # Localized 422 business error on decision
        bad_decision = client.post(
            f"/api/approvals/{created_body['id']}/decision",
            params={"lang": "en"},
            json={"decision": "approved", "director_comment": "short", "trust_account": True},
        )
        assert bad_decision.status_code == 422
        assert "10 characters" in bad_decision.json()["detail"]

        # Localized 404 error
        missing_kk = client.post(
            "/api/approvals/apr-missing/decision",
            params={"lang": "kk"},
            json={"decision": "rejected"},
        )
        assert missing_kk.status_code == 404
        assert "табылмады" in missing_kk.json()["detail"]

        # Localized 422 request validation error
        invalid_amt = client.post(
            "/api/payments/check",
            params={"lang": "en"},
            json={**yellow_req, "amount_kzt": -100},
        )
        assert invalid_amt.status_code == 422
        assert "Payment amount" in invalid_amt.json()["detail"]

    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("GET", "/api/payments/queue"),
            ("GET", "/api/approvals"),
        ],
    )
    def test_unknown_lang_returns_422(self, client: TestClient, method: str, path: str) -> None:
        resp = client.request(method, path, params={"lang": "fr"})
        assert resp.status_code == 422

    def test_unknown_lang_on_post_check_and_approvals_returns_422(
        self, client: TestClient
    ) -> None:
        queue = client.get("/api/payments/queue").json()
        req = _queue_item_to_check_request(queue[0])

        r_check = client.post("/api/payments/check", params={"lang": "de"}, json=req)
        assert r_check.status_code == 422

        r_apr = client.post(
            "/api/approvals",
            params={"lang": "de"},
            json={"check_request": req},
        )
        assert r_apr.status_code == 422

        r_dec = client.post(
            "/api/approvals/apr-any/decision",
            params={"lang": "de"},
            json={"decision": "rejected"},
        )
        assert r_dec.status_code == 422
