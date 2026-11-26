"""API integration tests using FastAPI TestClient."""

from __future__ import annotations

import json
import random
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.risk.config import DEMO_TODAY, RULESET_VERSION
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
            expected_verdict = item["scenario"]
            assert item["check"]["verdict"] == expected_verdict
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
        yellow_req = {
            **_queue_item_to_check_request(next(q for q in queue if q["id"] == "Q-002")),
            "amount_kzt": 700_000,
        }

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
        yellow_item = next(q for q in queue if q["id"] == "Q-002")
        # Below supplier median (700_000 < 820_000) -> yellow (50), eligible for director trust
        yellow_req = {**_queue_item_to_check_request(yellow_item), "amount_kzt": 700_000}

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
        updated_yellow = next(q for q in updated_queue if q["id"] == "Q-002")
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
        yellow_item = next(q for q in queue if q["id"] == "Q-002")
        yellow_req = {**_queue_item_to_check_request(yellow_item), "amount_kzt": 700_000}

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
        yellow_req = {
            **_queue_item_to_check_request(next(q for q in queue if q["id"] == "Q-002")),
            "amount_kzt": 700_000,
        }

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

    def test_unknown_lang_on_post_check_and_approvals_returns_422(self, client: TestClient) -> None:
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


class TestBankingSecrecyAndAnalystRole:
    def test_client_endpoints_never_leak_bcc_owner_bin_or_open_date(
        self, client: TestClient
    ) -> None:
        red_item = next(q for q in store.queue if q["id"] == "Q-003")
        red_req = _queue_item_to_check_request(red_item)
        bcc_entry = store.bcc_accounts[red_item["recipient_iik"]]
        forbidden = (
            bcc_entry["owner_name"],
            "Вектор Трейд",
            bcc_entry["owner_bin"],
            bcc_entry["opened_at"],
            "12 дн",
        )

        # 1. POST /api/payments/check without X-Role (and with non-analyst roles)
        for headers in ({}, {"X-Role": "client"}, {"X-Role": "user"}, {"X-Role": ""}):
            for lang in ("ru", "kk", "en"):
                resp = client.post(
                    "/api/payments/check",
                    params={"lang": lang},
                    headers=headers,
                    json=red_req,
                )
                assert resp.status_code == 200
                body = resp.json()
                assert "analyst_details" not in body
                serialized = json.dumps(body, ensure_ascii=False)
                for secret in forbidden:
                    assert secret not in serialized, (
                        f"Leaked {secret!r} in check ({lang}, {headers})"
                    )

                other_sig = next(
                    s for s in body["signals"] if s["rule_id"] == "bcc_account_other_owner"
                )
                new_sig = next(s for s in body["signals"] if s["rule_id"] == "new_bcc_account")
                assert other_sig["reason_ru"] == "Счёт в BCC оформлен не на указанного получателя."
                assert new_sig["reason_ru"] == "Счёт получателя открыт недавно."
                assert other_sig["evidence"]["since"] is None
                assert new_sig["evidence"]["since"] is None

        # 2. GET /api/payments/queue without X-Role
        queue_resp = client.get("/api/payments/queue")
        assert queue_resp.status_code == 200
        queue_body = queue_resp.json()
        for item in queue_body:
            assert "analyst_details" not in item["check"]
        q3_text = json.dumps(
            next(item for item in queue_body if item["id"] == "Q-003"),
            ensure_ascii=False,
        )
        for secret in forbidden:
            assert secret not in q3_text, f"Leaked {secret!r} in Q-003 of /api/payments/queue"
        queue_text = json.dumps(queue_body, ensure_ascii=False)
        for secret in (bcc_entry["owner_name"], "Вектор Трейд", bcc_entry["owner_bin"], "12 дн"):
            assert secret not in queue_text, f"Leaked {secret!r} in /api/payments/queue"

        # 3. GET /api/metrics contains no bank secrets
        metrics_text = json.dumps(client.get("/api/metrics").json(), ensure_ascii=False)
        for secret in forbidden:
            assert secret not in metrics_text

        # 4. Approvals created by analyst must NOT leak to subsequent client reads
        analyst_created = client.post(
            "/api/approvals",
            headers={"X-Role": "analyst"},
            json={"check_request": red_req, "accountant_note": "Проверка"},
        )
        assert analyst_created.status_code == 200
        assert "analyst_details" in analyst_created.json()["check"]

        client_listed = client.get("/api/approvals")
        assert client_listed.status_code == 200
        client_listed_body = client_listed.json()
        assert len(client_listed_body) == 1
        assert "analyst_details" not in client_listed_body[0]["check"]
        listed_text = json.dumps(client_listed_body, ensure_ascii=False)
        for secret in forbidden:
            assert secret not in listed_text, f"Leaked {secret!r} in GET /api/approvals"

        # Deduplicated POST /api/approvals without analyst header also hides analyst_details
        client_dedup = client.post(
            "/api/approvals",
            json={"check_request": red_req, "accountant_note": "Повтор"},
        )
        assert client_dedup.status_code == 200
        assert "analyst_details" not in client_dedup.json()["check"]

        # Decision without analyst header hides analyst_details
        apr_id = client_listed_body[0]["id"]
        client_decided = client.post(
            f"/api/approvals/{apr_id}/decision",
            json={"decision": "rejected"},
        )
        assert client_decided.status_code == 200
        assert "analyst_details" not in client_decided.json()["check"]

    def test_analyst_role_header_exposes_analyst_details_and_positions(
        self, client: TestClient
    ) -> None:
        red_item = next(q for q in store.queue if q["id"] == "Q-003")
        red_req = _queue_item_to_check_request(red_item)
        bcc_entry = store.bcc_accounts[red_item["recipient_iik"]]

        # POST /api/payments/check with X-Role: analyst (case-insensitive)
        resp = client.post(
            "/api/payments/check",
            params={"lang": "en"},
            headers={"X-Role": "Analyst"},
            json=red_req,
        )
        assert resp.status_code == 200
        body = resp.json()
        details = body["analyst_details"]
        assert details["bcc_account"]["owner_name"] == bcc_entry["owner_name"]
        assert details["bcc_account"]["owner_bin"] == bcc_entry["owner_bin"]
        assert details["bcc_account"]["opened_at"] == bcc_entry["opened_at"]
        assert details["bcc_account"]["age_days"] == 12
        assert details["bcc_account"]["owner_matches_recipient"] is False

        by_rule = {d["rule_id"]: d for d in details["signal_details"]}
        assert {"bcc_account_other_owner", "new_bcc_account", "mixed_script_name"} <= set(by_rule)
        assert bcc_entry["owner_name"] in by_rule["bcc_account_other_owner"]["reason"]
        assert bcc_entry["opened_at"] in by_rule["new_bcc_account"]["reason"]
        assert by_rule["mixed_script_name"]["evidence"]["positions"] == [12]

        # GET /api/payments/queue with X-Role: analyst
        q_resp = client.get("/api/payments/queue", headers={"X-Role": "analyst"})
        assert q_resp.status_code == 200
        q3 = next(item for item in q_resp.json() if item["id"] == "Q-003")
        assert q3["check"]["analyst_details"]["bcc_account"]["owner_bin"] == bcc_entry["owner_bin"]

        # Digits inside Cyrillic word: client hides positions, analyst receives exact offsets
        digits_req = {**red_req, "recipient_name": "ТОО «Ка3Л0гистик»"}
        client_dig = client.post("/api/payments/check", json=digits_req).json()
        assert "analyst_details" not in client_dig
        assert any(s["rule_id"] == "mixed_script_name" for s in client_dig["signals"])

        analyst_dig = client.post(
            "/api/payments/check",
            headers={"X-Role": "analyst"},
            json=digits_req,
        ).json()
        ms_detail = next(
            d
            for d in analyst_dig["analyst_details"]["signal_details"]
            if d["rule_id"] == "mixed_script_name"
        )
        assert ms_detail["evidence"]["positions"] == [7, 9]

    def test_budget_unknown_bcc_and_kbe_knp_via_api(self, client: TestClient) -> None:
        from scripts.generate_data import generate_iik

        grey_item = next(q for q in store.queue if q["id"] == "Q-004")
        base_req = _queue_item_to_check_request(grey_item)
        rng = random.Random(2026)

        # Budget payment to KKMFKZ2A (070) -> green with treasury headline in ru/kk/en
        budget_req = {
            **base_req,
            "recipient_name": "ГУ «Комитет казначейства МФ РК»",
            "recipient_iik": generate_iik(rng, "070", prefix="000"),
            "recipient_bik": "KKMFKZ2A",
        }
        b_ru = client.post("/api/payments/check", params={"lang": "ru"}, json=budget_req).json()
        b_kk = client.post("/api/payments/check", params={"lang": "kk"}, json=budget_req).json()
        b_en = client.post("/api/payments/check", params={"lang": "en"}, json=budget_req).json()
        assert b_ru["verdict"] == "green" and b_ru["score"] == 0
        assert b_ru["headline_ru"] == "Бюджетный платёж: реквизиты казначейства верны"
        assert b_kk["headline"] != b_ru["headline_ru"]
        assert b_en["headline"] != b_ru["headline_ru"]

        # Valid BCC 856 IIK absent from bcc_accounts -> invalid
        missing_bcc = {
            **base_req,
            "recipient_iik": generate_iik(rng, "856", prefix="KZT"),
            "recipient_bik": "KCJBKZKX",
        }
        m_resp = client.post("/api/payments/check", json=missing_bcc).json()
        assert m_resp["verdict"] == "invalid"
        assert m_resp["signals"][0]["rule_id"] == "bcc_account_not_found"
        assert m_resp["signals"][0]["reason_ru"] == "Счёт в BCC не найден."

        # Optional KBe=17 with individual IIN and no legal-form prefix -> yellow
        kbe_req = {
            **base_req,
            "recipient_name": "СнабСтрой Центр",
            "recipient_bin": generate_iin(rng),
            "kbe": "17",
        }
        kbe_resp = client.post("/api/payments/check", json=kbe_req).json()
        assert kbe_resp["verdict"] == "yellow"
        assert any(s["rule_id"] == "kbe_mismatch" for s in kbe_resp["signals"])

    def test_memory_duplicate_accumulated_structuring_and_bank_verified_via_api(
        self, client: TestClient
    ) -> None:
        from datetime import timedelta

        from scripts.generate_data import generate_iik

        green_req = _queue_item_to_check_request(next(q for q in store.queue if q["id"] == "Q-001"))
        grey_req = _queue_item_to_check_request(next(q for q in store.queue if q["id"] == "Q-004"))

        # 1. Duplicate invoice across two POST /api/payments/check calls -> 2nd turns yellow
        first = client.post("/api/payments/check?commit=true", json=green_req).json()
        assert first["verdict"] == "green"
        second = client.post(
            "/api/payments/check?commit=true",
            json={**green_req, "purpose": "Повтор сч. 214 за материалы"},
        ).json()
        assert second["verdict"] == "yellow"
        assert any(s["rule_id"] == "duplicate_invoice" for s in second["signals"])

        # Reset clears memory
        client.post("/api/demo/reset")

        # 2. Structuring: 3 payments of 40% median (540_000) in a row -> 3rd triggers structuring_72h
        for inv_no in (951, 952):
            res = client.post(
                "/api/payments/check?commit=true",
                json={**green_req, "amount_kzt": 540_000, "purpose": f"Оплата по счёту № {inv_no}"},
            ).json()
            assert res["verdict"] == "green"
            assert all(s["rule_id"] != "structuring_72h" for s in res["signals"])
        third = client.post(
            "/api/payments/check?commit=true",
            json={**green_req, "amount_kzt": 540_000, "purpose": "Оплата по счёту № 953"},
        ).json()
        assert any(s["rule_id"] == "structuring_72h" for s in third["signals"])

        # 3. Accumulated amount to same new recipient across checks within 7 days -> amplifier
        client.post(
            "/api/payments/check?commit=true",
            json={**grey_req, "amount_kzt": 1_000_000, "purpose": "Оплата сч. 701"},
        )
        acc_resp = client.post(
            "/api/payments/check?commit=true",
            json={**grey_req, "amount_kzt": 1_000_000, "purpose": "Оплата сч. 702"},
        ).json()
        assert any(s["rule_id"] == "new_recipient_accumulated" for s in acc_resp["signals"])

        # 4. Same BIN + new BCC IIK owned by this BIN -> green + bank-verified headline
        client.post("/api/demo/reset")
        new_bcc_iik = generate_iik(random.Random(3030), "856", prefix="KZT")
        store.bcc_accounts[new_bcc_iik] = {
            "owner_bin": green_req["recipient_bin"],
            "owner_name": green_req["recipient_name"],
            "opened_at": (DEMO_TODAY - timedelta(days=100)).isoformat(),
        }
        verified = client.post(
            "/api/payments/check",
            json={**green_req, "recipient_iik": new_bcc_iik, "recipient_bik": "KCJBKZKX"},
        ).json()
        assert verified["verdict"] == "green"
        assert verified["headline_ru"] == "Счёт подтверждён банком: принадлежит этому поставщику"
        assert "analyst_details" not in verified


class TestStep4DedupMetricsLocalizationAndAudit:
    def test_identical_recheck_across_languages_is_deduplicated_in_memory(
        self, client: TestClient
    ) -> None:
        green_req = _queue_item_to_check_request(next(q for q in store.queue if q["id"] == "Q-001"))
        grey_req = _queue_item_to_check_request(next(q for q in store.queue if q["id"] == "Q-004"))

        # 1. Re-checking the exact same form across ru/kk/en must NOT trigger duplicate_invoice
        for lang in ("ru", "kk", "en", "ru"):
            resp = client.post("/api/payments/check", params={"lang": lang, "commit": "true"}, json=green_req).json()
            assert resp["verdict"] == "green"
            assert all(s["rule_id"] != "duplicate_invoice" for s in resp["signals"])

        # 2. Re-checking identical 40% chunk 4 times must NOT trigger structuring_72h
        chunk = {**green_req, "amount_kzt": 540_000, "purpose": "Оплата по счёту № 981"}
        for lang in ("ru", "kk", "en", "ru"):
            resp = client.post("/api/payments/check", params={"lang": lang, "commit": "true"}, json=chunk).json()
            assert resp["verdict"] == "green"
            assert all(s["rule_id"] != "structuring_72h" for s in resp["signals"])

        # 3. Re-checking identical new-recipient payment must NOT trigger new_recipient_accumulated
        big_new = {**grey_req, "amount_kzt": 1_200_000, "purpose": "Аванс по счёту № 811"}
        for lang in ("ru", "kk", "en"):
            resp = client.post("/api/payments/check", params={"lang": lang, "commit": "true"}, json=big_new).json()
            assert all(s["rule_id"] != "new_recipient_accumulated" for s in resp["signals"])

        # 4. A genuinely different second payment to the same new recipient DOES trigger it
        second_new = {**grey_req, "amount_kzt": 1_200_000, "purpose": "Аванс по счёту № 812"}
        resp2 = client.post("/api/payments/check?commit=true", json=second_new).json()
        assert any(s["rule_id"] == "new_recipient_accumulated" for s in resp2["signals"])

    def test_evidence_and_metrics_are_localized_with_stopped_escalated_and_history_replay(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Localized evidence labels & expected/actual on POST /api/payments/check
        q2_req = _queue_item_to_check_request(next(q for q in store.queue if q["id"] == "Q-002"))
        ev_ru = client.post("/api/payments/check", params={"lang": "ru", "commit": "true"}, json=q2_req).json()
        ev_kk = client.post("/api/payments/check", params={"lang": "kk", "commit": "true"}, json=q2_req).json()
        ev_en = client.post("/api/payments/check", params={"lang": "en", "commit": "true"}, json=q2_req).json()

        sig_ru = next(s for s in ev_ru["signals"] if s["rule_id"] == "iik_changed")
        sig_kk = next(s for s in ev_kk["signals"] if s["rule_id"] == "iik_changed")
        sig_en = next(s for s in ev_en["signals"] if s["rule_id"] == "iik_changed")
        assert sig_ru["evidence"]["field_label"] == "ИИК"
        assert sig_kk["evidence"]["field_label"] == "ЖСК (ИИК)"
        assert sig_en["evidence"]["field_label"] == "IIK"
        assert "expected_key" not in sig_en["evidence"]
        assert "actual_key" not in sig_en["evidence"]

        # Q-003 red evidence expected/actual localized cleanly without leaking bank secrets
        q3_req = _queue_item_to_check_request(next(q for q in store.queue if q["id"] == "Q-003"))
        q3_en = client.post("/api/payments/check", params={"lang": "en"}, json=q3_req).json()
        q3_kk = client.post("/api/payments/check", params={"lang": "kk"}, json=q3_req).json()
        bcc_sig_en = next(s for s in q3_en["signals"] if s["rule_id"] == "bcc_account_other_owner")
        bcc_sig_kk = next(s for s in q3_kk["signals"] if s["rule_id"] == "bcc_account_other_owner")
        assert "does not match" in (bcc_sig_en["evidence"]["actual"] or "").lower()
        assert bcc_sig_kk["evidence"]["actual"] != bcc_sig_en["evidence"]["actual"]
        assert "Вектор Трейд" not in json.dumps(q3_en, ensure_ascii=False)
        assert "Вектор Трейд" not in json.dumps(q3_kk, ensure_ascii=False)

        # GET /api/metrics?lang=ru|kk|en
        m_ru = client.get("/api/metrics", params={"lang": "ru"}).json()
        assert m_ru["ruleset_version"] == RULESET_VERSION
        assert m_ru["disclaimer"] == m_ru["disclaimer_ru"]
        assert m_ru["disclaimer_kk"] != m_ru["disclaimer_ru"]
        assert m_ru["disclaimer_en"] != m_ru["disclaimer_ru"]

        summary = m_ru["summary"]
        assert summary["stopped_count"] == m_ru["verdict_by_label"]["attack"]["red"]
        assert summary["escalated_count"] == m_ru["verdict_by_label"]["attack"]["yellow"]
        assert summary["stopped_count"] + summary["escalated_count"] == m_ru["confusion"]["tp"]
        assert 0.0 <= summary["stopped_rate"] <= 1.0
        assert 0.0 <= summary["escalated_rate"] <= 1.0

        replay = m_ru["history_replay"]
        assert replay["total_payments"] == 150
        v = replay["verdicts"]
        assert v["green"] + v["yellow"] + v["red"] + v["grey"] + v["invalid"] == 150
        assert replay["alert_count"] == v["yellow"] + v["red"]
        assert replay["alert_rate"] == round(replay["alert_count"] / 150, 4)

        # Cached localization across languages must not recompute evaluate_dataset
        def _must_not_recompute(*args, **kwargs):
            raise AssertionError("GET /api/metrics should serve cached result across languages")

        monkeypatch.setattr("app.main.evaluate_dataset", _must_not_recompute)
        m_kk = client.get("/api/metrics", params={"lang": "kk"}).json()
        m_en = client.get("/api/metrics", params={"lang": "en"}).json()

        assert m_kk["disclaimer"] == m_ru["disclaimer_kk"]
        assert m_en["disclaimer"] == m_ru["disclaimer_en"]
        for row_ru, row_kk, row_en in zip(
            m_ru["by_kind"], m_kk["by_kind"], m_en["by_kind"], strict=True
        ):
            assert row_ru["label_text"] == row_ru["label_ru"]
            assert row_kk["label_text"] == row_ru["label_kk"]
            assert row_en["label_text"] == row_ru["label_en"]
            assert row_kk["label_text"] != row_ru["label_text"]
            assert row_en["label_text"] != row_ru["label_text"]

        # Unsupported lang returns 422
        assert client.get("/api/metrics", params={"lang": "fr"}).status_code == 422

    def test_append_only_audit_log_ruleset_version_and_privacy(self, client: TestClient) -> None:
        from pathlib import Path

        live_audit = Path(__file__).resolve().parents[1] / "data" / "audit.jsonl"
        assert store.audit_log_path != live_audit
        live_before = live_audit.read_bytes() if live_audit.exists() else None

        q3_item = next(q for q in store.queue if q["id"] == "Q-003")
        q3_req = _queue_item_to_check_request(q3_item)
        q2_item = next(q for q in store.queue if q["id"] == "Q-002")
        q2_yellow = {**_queue_item_to_check_request(q2_item), "amount_kzt": 700_000}

        # 1. ruleset_version is returned on /check, /queue, /approvals, /decision
        chk = client.post("/api/payments/check", json=q3_req).json()
        assert chk["ruleset_version"] == RULESET_VERSION

        queue = client.get("/api/payments/queue").json()
        assert all(item["check"]["ruleset_version"] == RULESET_VERSION for item in queue)

        apr = client.post(
            "/api/approvals",
            json={"check_request": q2_yellow, "accountant_note": "Смена банка"},
        ).json()
        assert apr["check"]["ruleset_version"] == RULESET_VERSION

        dec = client.post(
            f"/api/approvals/{apr['id']}/decision",
            json={
                "decision": "approved",
                "director_comment": "Подтвердили реквизиты звонком поставщику",
                "trust_account": True,
            },
        ).json()
        assert dec["check"]["ruleset_version"] == RULESET_VERSION

        # 2. Verify temporary audit.jsonl exists, live data/audit.jsonl was NOT created
        assert store.audit_log_path.exists()
        live_after = live_audit.read_bytes() if live_audit.exists() else None
        assert live_after == live_before  # tests never write to the live audit log
        raw_log = store.audit_log_path.read_text(encoding="utf-8")

        # 3. Privacy check: ZERO plaintext names, BINs, IIKs, amounts, or purposes in audit log
        bcc_entry = store.bcc_accounts[q3_req["recipient_iik"]]
        forbidden = (
            q3_req["recipient_name"],
            "Алатау",
            "КазЛогистик",
            bcc_entry["owner_name"],
            "Вектор Трейд",
            q3_req["recipient_bin"],
            q3_req["recipient_iik"],
            q2_yellow["recipient_bin"],
            q2_yellow["recipient_iik"],
            bcc_entry["owner_bin"],
            "4900000",
            "700000",
            "Смена банка",
            "Подтвердили реквизиты",
        )
        for secret in forbidden:
            assert secret not in raw_log, f"Plaintext PII/secret {secret!r} found in audit.jsonl"

        # 4. GET /api/audit returns latest entries with strict schema
        audit_resp = client.get("/api/audit")
        assert audit_resp.status_code == 200
        entries = audit_resp.json()
        assert len(entries) == 2
        allowed_keys = {
            "timestamp",
            "check_id",
            "request_sha256",
            "ruleset_version",
            "verdict",
            "signal_ids",
            "action",
            "approval_id",
        }
        for entry in entries:
            assert set(entry.keys()) <= allowed_keys
            assert len(entry["request_sha256"]) == 64
            assert entry["ruleset_version"] == RULESET_VERSION

        assert entries[0]["action"] == "check"
        assert entries[0]["verdict"] == "red"
        assert "bcc_account_other_owner" in entries[0]["signal_ids"]
        assert entries[1]["action"] == "decision:approved_trusted"
        assert entries[1]["approval_id"] == apr["id"]

        # 5. limit parameter returns latest N entries and validates 1..1000
        limited = client.get("/api/audit", params={"limit": 1}).json()
        assert len(limited) == 1
        assert limited[0]["action"] == "decision:approved_trusted"

        assert client.get("/api/audit", params={"limit": 0}).status_code == 422
        assert client.get("/api/audit", params={"limit": 1001}).status_code == 422


def test_dry_run_checks_do_not_change_verdict_on_repeated_edits() -> None:
    """Editing the same draft several times must not trigger memory rules (review K1)."""
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    client.post("/api/demo/reset")
    item = next(q for q in client.get("/api/payments/queue").json() if q["id"] == "Q-001")
    req = {
        k: item[k]
        for k in (
            "recipient_name",
            "recipient_bin",
            "recipient_iik",
            "recipient_bik",
            "amount_kzt",
            "purpose",
        )
    }
    verdicts = []
    for delta in (0, 1, 2, 3):
        body = {**req, "amount_kzt": req["amount_kzt"] + delta}
        verdicts.append(client.post("/api/payments/check", json=body).json()["verdict"])
    client.post("/api/demo/reset")
    assert verdicts == ["green"] * 4
