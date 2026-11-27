"""Модульные и интеграционные тесты привязки проверка <-> подпись (app.prod.signing)."""

from __future__ import annotations

import copy
import json
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.i18n import t
from app.prod import payments_service
from app.prod.app import create_prod_app
from app.prod.audit_db import list_audit, verify_chain
from app.prod.db import connect, tx
from app.prod.deps import CSRF_HEADER_NAME, CSRF_HEADER_VALUE
from app.prod.errors import ProdError
from app.prod.schemas import (
    Payment,
    PaymentPermissions,
    SupplierRef,
    User,
    UserBrief,
)
from app.prod.signing import (
    NCALAYER_LABEL,
    SIMULATED_LABEL,
    SIMULATED_SECRET_ENV,
    CmsSignatureVerifier,
    DocumentMismatchError,
    InvalidSignerError,
    SimulatedSigner,
    VerifiedSignature,
    build_payment_document,
    canonical_json,
    derive_company_secret,
    document_digest,
    verify_document_binding,
    verify_signature,
)
from app.schemas import (
    CheckRequest,
    CheckResult,
    HistorySummary,
    NextAction,
    compute_request_sha256,
)
from app.settings import Settings
from app.store import DEFAULT_DATA_DIR
from tests.prod.conftest import TEST_SEED_PW, TEST_TODAY, build_sign_payload

CSRF: dict[str, str] = {CSRF_HEADER_NAME: CSRF_HEADER_VALUE}


def _sample_payment_dict(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": "pay-001122334455",
        "company_id": "comp-astana-01",
        "doc_number": "1042",
        "doc_date": date(2026, 11, 26),
        "recipient_name": "ТОО КазСтройСнаб",
        "recipient_bin": "180947320524",
        "recipient_iik": "KZ509650006872032298",
        "recipient_bik": "IRTYKZKA",
        "amount_kzt": Decimal("1250000.50"),
        "currency": "KZT",
        "kbe": "17",
        "knp": "710",
        "purpose": "Оплата по счёту № 42 за строительные материалы",
        "status": "checked",
        "updated_at": "2026-11-26T10:00:00+00:00",
        "created_at": "2026-11-26T09:55:00+00:00",
    }
    data.update(overrides)
    return data


def _sample_check_dict(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "check_id": "chk-abcdef123456",
        "ruleset_version": "2026.11.1",
        "verdict": "green",
        "request_sha256": "a" * 64,
    }
    data.update(overrides)
    return data


def _sample_pydantic_payment() -> tuple[Payment, CheckResult]:
    req = CheckRequest(
        payer_id="comp-astana-01",
        recipient_name="ТОО КазСтройСнаб",
        recipient_bin="180947320524",
        recipient_iik="KZ509650006872032298",
        recipient_bik="IRTYKZKA",
        amount_kzt=1250000.5,
        purpose="Оплата по счёту № 42 за строительные материалы",
        kbe="17",
        knp="710",
    )
    check = CheckResult(
        check_id="chk-abcdef123456",
        ruleset_version="2026.11.1",
        verdict="green",
        score=0,
        headline_ru="Платёж выглядит стандартно",
        signals=[],
        comparison=[],
        next_action=NextAction(text_ru="Можно подписывать", primary="sign"),
        history=HistorySummary(payments_count=5),
    )
    payment = Payment(
        id="pay-001122334455",
        company_id="comp-astana-01",
        status="checked",
        source="manual",
        doc_number="1042",
        doc_date="2026-11-26",
        request=req,
        check=check,
        supplier=SupplierRef(
            id=1,
            known=True,
            account_known=True,
            requisites_changed_days_ago=None,
        ),
        permissions=PaymentPermissions(
            can_edit=True,
            can_sign=True,
            sign_requires_ack=False,
            sign_block_code=None,
            can_send_to_director=True,
            can_postpone=True,
            can_resume=False,
            can_cancel=True,
            can_decide=False,
        ),
        created_by=UserBrief(id=1, login="accountant", full_name="Айгуль", role="accountant"),
        created_at="2026-11-26T09:55:00+00:00",
        updated_at="2026-11-26T10:00:00+00:00",
    )
    return payment, check


class TestDocumentDigestDeterminism:
    def test_same_data_different_key_order_yields_identical_digest(self) -> None:
        payment_a = _sample_payment_dict()
        payment_b = {k: payment_a[k] for k in reversed(list(payment_a.keys()))}
        check_a = _sample_check_dict()
        check_b = {k: check_a[k] for k in reversed(list(check_a.keys()))}

        doc_a = build_payment_document(payment_a, check_a)
        doc_b = build_payment_document(payment_b, check_b)

        assert canonical_json(doc_a) == canonical_json(doc_b)
        assert document_digest(doc_a) == document_digest(doc_b)
        assert len(document_digest(doc_a)) == 64

    def test_equivalent_adapters_dict_pydantic_orm_and_amount_representations(self) -> None:
        pydantic_payment, pydantic_check = _sample_pydantic_payment()
        expected_req_sha = compute_request_sha256(
            pydantic_payment.request,
            resolved_payer_id=pydantic_payment.company_id,
        )

        # Вариант 1: Pydantic Payment + CheckResult (без явного request_sha256)
        doc_pydantic = build_payment_document(pydantic_payment, pydantic_check)

        # Вариант 2: плоский dict с amount_tiyn и строкой даты
        payment_tiyn = _sample_payment_dict(
            doc_date="2026-11-26",
            amount_tiyn=125000050,
        )
        payment_tiyn.pop("amount_kzt")
        check_with_sha = _sample_check_dict(request_sha256=expected_req_sha)
        doc_tiyn = build_payment_document(payment_tiyn, check_with_sha)

        # Вариант 3: ORM-подобный объект с Decimal иной точности и date-объектом
        orm_payment = SimpleNamespace(
            **_sample_payment_dict(
                amount_kzt=Decimal("1250000.500"),
                doc_date=date(2026, 11, 26),
            )
        )
        orm_check = SimpleNamespace(
            id="chk-abcdef123456",
            ruleset_version="2026.11.1",
            verdict="green",
            request_sha256=expected_req_sha,
        )
        doc_orm = build_payment_document(orm_payment, orm_check)

        assert doc_pydantic["amount_kzt"] == "1250000.50"
        assert doc_pydantic["doc_date"] == "2026-11-26"
        assert document_digest(doc_pydantic) == document_digest(doc_tiyn)
        assert document_digest(doc_pydantic) == document_digest(doc_orm)

    def test_unstable_fields_do_not_affect_digest_and_none_is_null(self) -> None:
        payment_a = _sample_payment_dict(
            doc_date=None,
            status="checked",
            updated_at="2026-11-26T10:00:00+00:00",
        )
        payment_b = _sample_payment_dict(
            doc_date=None,
            status="approved",
            updated_at="2026-11-26T12:30:45+00:00",
            signed_at="2026-11-26T12:31:00+00:00",
            accountant_ack=True,
        )
        check = _sample_check_dict()

        doc_a = build_payment_document(payment_a, check)
        doc_b = build_payment_document(payment_b, check)

        assert '"doc_date":null' in canonical_json(doc_a)
        assert "updated_at" not in doc_a
        assert "status" not in doc_a
        assert document_digest(doc_a) == document_digest(doc_b)

    @pytest.mark.parametrize(
        ("field", "new_value"),
        [
            ("id", "pay-999999999999"),
            ("company_id", "comp-other-02"),
            ("doc_number", "1043"),
            ("doc_date", date(2026, 11, 27)),
            ("recipient_name", "ТОО Подменный Получатель"),
            ("recipient_bin", "180947320525"),
            ("recipient_iik", "KZ999650006872039999"),
            ("recipient_bik", "KCJBKZKX"),
            ("amount_kzt", Decimal("1250000.51")),
            ("currency", "USD"),
            ("kbe", "19"),
            ("knp", "851"),
            ("purpose", "Оплата по счёту № 42 за другие услуги"),
        ],
    )
    def test_changing_any_payment_field_changes_digest(self, field: str, new_value: Any) -> None:
        base_payment = _sample_payment_dict()
        base_check = _sample_check_dict()
        base_digest = document_digest(build_payment_document(base_payment, base_check))

        mutated_payment = copy.deepcopy(base_payment)
        mutated_payment[field] = new_value
        mutated_digest = document_digest(build_payment_document(mutated_payment, base_check))

        assert mutated_digest != base_digest

    @pytest.mark.parametrize(
        ("field", "new_value"),
        [
            ("check_id", "chk-different999"),
            ("ruleset_version", "2026.12.0"),
            ("verdict", "yellow"),
            ("request_sha256", "b" * 64),
        ],
    )
    def test_changing_any_check_field_changes_digest(self, field: str, new_value: Any) -> None:
        base_payment = _sample_payment_dict()
        base_check = _sample_check_dict()
        base_digest = document_digest(build_payment_document(base_payment, base_check))

        mutated_check = copy.deepcopy(base_check)
        mutated_check[field] = new_value
        mutated_digest = document_digest(build_payment_document(base_payment, mutated_check))

        assert mutated_digest != base_digest


class TestDocumentBindingVerification:
    def test_verify_document_binding_succeeds_when_unchanged(self) -> None:
        payment = _sample_payment_dict()
        check = _sample_check_dict()
        digest = document_digest(build_payment_document(payment, check))

        assert verify_document_binding(digest, payment, check) is None

    def test_verify_document_binding_raises_409_on_toctou_tampering(self) -> None:
        original_payment = _sample_payment_dict()
        check = _sample_check_dict()
        client_digest = document_digest(build_payment_document(original_payment, check))

        # Подмена реквизитов между проверкой и подписанием (TOCTOU)
        tampered_payment = _sample_payment_dict(recipient_iik="KZ118562203199999999")
        expected_digest = document_digest(build_payment_document(tampered_payment, check))

        with pytest.raises(DocumentMismatchError) as exc_info:
            verify_document_binding(client_digest, tampered_payment, check)

        err = exc_info.value
        assert isinstance(err, ProdError)
        assert err.status_code == 409
        assert err.code == "document_mismatch"
        payload = err.to_payload("ru")
        assert payload["code"] == "document_mismatch"
        assert isinstance(payload["detail"], str) and len(payload["detail"]) > 10
        assert expected_digest not in payload["detail"]

    @pytest.mark.parametrize("bad_digest", ["", "0" * 64, "некорректный-дайджест"])
    def test_verify_document_binding_rejects_invalid_client_digests(self, bad_digest: str) -> None:
        payment = _sample_payment_dict()
        check = _sample_check_dict()

        with pytest.raises(DocumentMismatchError) as exc_info:
            verify_document_binding(bad_digest, payment, check)

        assert exc_info.value.status_code == 409
        assert exc_info.value.code == "document_mismatch"


class TestSimulatedSignerAndDispatcher:
    def test_derive_company_secret_isolates_companies_and_respects_env(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv(SIMULATED_SECRET_ENV, "test-master-secret-v1")
        sec_a1 = derive_company_secret("comp-a")
        sec_a2 = derive_company_secret("comp-a")
        sec_b = derive_company_secret("comp-b")

        assert sec_a1 == sec_a2
        assert sec_a1 != sec_b

        monkeypatch.setenv(SIMULATED_SECRET_ENV, "test-master-secret-v2")
        sec_a_rotated = derive_company_secret("comp-a")
        assert sec_a_rotated != sec_a1

    def test_simulated_signer_sign_and_verify(self) -> None:
        assert SIMULATED_LABEL == "Имитация ЭЦП, не NCALayer"

        signer = SimulatedSigner(master_secret="unit-test-secret")
        doc = build_payment_document(_sample_payment_dict(), _sample_check_dict())
        digest = document_digest(doc)

        signature = signer.sign(digest, "comp-astana-01")
        assert len(signature) == 64

        assert signer.verify(digest, signature, "comp-astana-01") is True
        # Изменённый digest
        assert signer.verify("f" * 64, signature, "comp-astana-01") is False
        # Чужая компания
        assert signer.verify(digest, signature, "comp-other-02") is False
        # Испорченная / пустая / не-ASCII подпись
        corrupted = ("0" if signature[0] != "0" else "1") + signature[1:]
        assert signer.verify(digest, corrupted, "comp-astana-01") is False
        assert signer.verify(digest, "", "comp-astana-01") is False
        assert signer.verify(digest, "подпись", "comp-astana-01") is False

    def test_verify_signature_simulated_returns_audit_result(self) -> None:
        signer = SimulatedSigner(master_secret="dispatch-secret")
        digest = document_digest(
            build_payment_document(_sample_payment_dict(), _sample_check_dict())
        )
        sig = signer.sign(digest, "comp-astana-01")

        ok_res = verify_signature(
            "simulated",
            digest,
            sig,
            "comp-astana-01",
            verifier=signer,
        )
        assert ok_res.verified is True
        assert ok_res.signer == "simulated"
        assert ok_res.label == SIMULATED_LABEL
        assert ok_res.simulated is True

        bad_res = verify_signature(
            "simulated",
            digest,
            "0" * 64,
            "comp-astana-01",
            verifier=signer,
        )
        assert bad_res.verified is False
        assert bad_res.signer == "simulated"
        assert bad_res.label == SIMULATED_LABEL

    def test_ncalayer_path_raises_not_implemented_by_default(self) -> None:
        digest = "c" * 64
        cms = CmsSignatureVerifier()

        with pytest.raises(NotImplementedError):
            cms.verify(digest, "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8A", "comp-astana-01")

        with pytest.raises(NotImplementedError):
            verify_signature(
                "ncalayer", digest, "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8A", "comp-astana-01"
            )

    def test_ncalayer_path_supports_custom_verifier(self) -> None:
        class StubCmsVerifier:
            def verify(
                self,
                doc_digest: str,
                signature_cms_b64: str,
                company_id: str,
            ) -> VerifiedSignature:
                assert doc_digest == "d" * 64
                assert signature_cms_b64 == "BASE64CMS=="
                assert company_id == "comp-astana-01"
                return VerifiedSignature(
                    signer_subject="CN=ИВАНОВ ИВАН",
                    signer_iin_bin="900101300123",
                    certificate_serial="1234567890ABCDEF",
                    signed_at="2026-11-26T10:05:00+00:00",
                )

        res = verify_signature(
            "ncalayer",
            "d" * 64,
            "BASE64CMS==",
            "comp-astana-01",
            verifier=StubCmsVerifier(),
        )
        assert res.verified is True
        assert res.signer == "ncalayer"
        assert res.simulated is False
        assert res.details is not None
        assert res.details.signer_iin_bin == "900101300123"

    @pytest.mark.parametrize("bad_signer", ["unknown", "", "pkcs7", "NCALAYER"])
    def test_unknown_signer_raises_validation_error(self, bad_signer: str) -> None:
        with pytest.raises(InvalidSignerError) as exc_info:
            verify_signature(bad_signer, "e" * 64, "sig", "comp-astana-01")

        err = exc_info.value
        assert isinstance(err, ProdError)
        assert isinstance(err, ValueError)
        assert err.status_code == 422
        assert err.code == "validation_error"


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
def signing_api_env(
    seeded_db: Path,
) -> Iterator[tuple[FastAPI, Path, TestClient, TestClient]]:
    cfg = Settings(
        app_mode="prod",
        db_path=seeded_db,
        today_override=TEST_TODAY,
        cookie_secure=False,
    )
    prod_app = create_prod_app(db_path=seeded_db, settings_override=cfg)
    with TestClient(prod_app) as acc_client, TestClient(prod_app) as dir_client:
        _login(acc_client, "accountant")
        _login(dir_client, "director")
        yield prod_app, seeded_db, acc_client, dir_client


class TestSigningBindingAPI:
    def test_payment_dto_exposes_document_digest_and_none_for_unverified_seed(
        self, signing_api_env: tuple[FastAPI, Path, TestClient, TestClient]
    ) -> None:
        _, _, acc, _ = signing_api_env
        queue = _load_queue_by_id()

        created = acc.post(
            "/api/v1/payments",
            json=_to_payment_input(queue["Q-001"]),
            headers=CSRF,
        )
        assert created.status_code == 201
        payment = created.json()
        assert isinstance(payment["document_digest"], str)
        assert len(payment["document_digest"]) == 64

        expected = document_digest(
            build_payment_document(Payment.model_validate(payment), CheckResult.model_validate(payment["check"]))
        )
        assert payment["document_digest"] == expected

        # Seeded historical signed payments have check_id IS NULL -> document_digest must be None
        signed_list = acc.get("/api/v1/payments?scope=signed&limit=5").json()
        assert signed_list["items"]
        assert all(item["document_digest"] is None for item in signed_list["items"])

    def test_valid_digest_and_simulated_signature_signs_and_records_audit_details(
        self, signing_api_env: tuple[FastAPI, Path, TestClient, TestClient]
    ) -> None:
        _, db_path, acc, _ = signing_api_env
        queue = _load_queue_by_id()

        p = acc.post("/api/v1/payments", json=_to_payment_input(queue["Q-001"]), headers=CSRF).json()
        digest = p["document_digest"]
        assert isinstance(digest, str) and len(digest) == 64

        sig = SimulatedSigner().sign(digest, p["company_id"])
        resp = acc.post(
            f"/api/v1/payments/{p['id']}/sign",
            json={
                "document_digest": digest,
                "signature": sig,
                "signer": "simulated",
            },
            headers=CSRF,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "signed"
        assert body["signed_at"] is not None

        conn = connect(db_path)
        try:
            entries = list_audit(conn, payment_id=p["id"], action="sign", limit=5)
            assert len(entries) == 1
            details = entries[0].details
            assert details["document_digest"] == digest
            assert details["signer"] == "simulated"
            assert details["label"] == SIMULATED_LABEL
            assert details["simulated"] is True
            assert verify_chain(conn).ok is True
        finally:
            conn.close()

    def test_simulated_empty_signature_browser_fallback_signs_with_audit_details(
        self, signing_api_env: tuple[FastAPI, Path, TestClient, TestClient]
    ) -> None:
        _, db_path, acc, _ = signing_api_env
        queue = _load_queue_by_id()

        p = acc.post("/api/v1/payments", json=_to_payment_input(queue["Q-001"]), headers=CSRF).json()
        digest = p["document_digest"]

        resp = acc.post(
            f"/api/v1/payments/{p['id']}/sign",
            json={
                "document_digest": digest,
                "signature": "",
                "signer": "simulated",
            },
            headers=CSRF,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "signed"

        conn = connect(db_path)
        try:
            entries = list_audit(conn, payment_id=p["id"], action="sign", limit=5)
            assert len(entries) == 1
            assert entries[0].details["document_digest"] == digest
            assert entries[0].details["signer"] == "simulated"
            assert entries[0].details["label"] == SIMULATED_LABEL
            assert entries[0].details["simulated"] is True
            assert verify_chain(conn).ok is True
        finally:
            conn.close()

    def test_invalid_simulated_signature_rejected_and_logged_without_signing(
        self, signing_api_env: tuple[FastAPI, Path, TestClient, TestClient]
    ) -> None:
        _, db_path, acc, _ = signing_api_env
        queue = _load_queue_by_id()

        p = acc.post("/api/v1/payments", json=_to_payment_input(queue["Q-001"]), headers=CSRF).json()
        resp = acc.post(
            f"/api/v1/payments/{p['id']}/sign",
            json={
                "document_digest": p["document_digest"],
                "signature": "0" * 64,
                "signer": "simulated",
            },
            headers=CSRF,
        )
        assert resp.status_code == 422
        assert resp.json()["code"] == "validation_error"

        # Payment remains unsigned
        after = acc.get(f"/api/v1/payments/{p['id']}").json()
        assert after["status"] == "checked"
        assert after["signed_at"] is None

        conn = connect(db_path)
        try:
            denied = list_audit(conn, payment_id=p["id"], action="sign_denied", limit=5)
            assert len(denied) == 1
            assert denied[0].details["code"] == "validation_error"
            assert verify_chain(conn).ok is True
        finally:
            conn.close()

    def test_wrong_digest_returns_409_document_mismatch_before_recheck_and_does_not_sign(
        self, signing_api_env: tuple[FastAPI, Path, TestClient, TestClient]
    ) -> None:
        _, db_path, acc, _ = signing_api_env
        queue = _load_queue_by_id()

        p = acc.post("/api/v1/payments", json=_to_payment_input(queue["Q-001"]), headers=CSRF).json()
        real_digest = p["document_digest"]
        wrong_digest = "0" * 64
        sig = SimulatedSigner().sign(wrong_digest, p["company_id"])

        conn = connect(db_path)
        try:
            checks_before = conn.execute(
                "SELECT COUNT(*) FROM checks WHERE payment_id = ?",
                (p["id"],),
            ).fetchone()[0]
        finally:
            conn.close()

        for lang in ("ru", "kk", "en"):
            resp = acc.post(
                f"/api/v1/payments/{p['id']}/sign?lang={lang}",
                json={
                    "document_digest": wrong_digest,
                    "signature": sig,
                    "signer": "simulated",
                },
                headers=CSRF,
            )
            assert resp.status_code == 409
            body = resp.json()
            assert body["code"] == "document_mismatch"
            assert body["detail"] == t("error.prod.document_mismatch", lang)
            assert real_digest not in body["detail"]

        # Payment stays checked, no new check rows created (verify_document_binding ran before re-check)
        after = acc.get(f"/api/v1/payments/{p['id']}").json()
        assert after["status"] == "checked"
        assert after["signed_at"] is None

        conn = connect(db_path)
        try:
            checks_after = conn.execute(
                "SELECT COUNT(*) FROM checks WHERE payment_id = ?",
                (p["id"],),
            ).fetchone()[0]
            assert checks_after == checks_before
            denied = list_audit(conn, payment_id=p["id"], action="sign_denied", limit=10)
            assert len(denied) == 3
            assert all(e.details["code"] == "document_mismatch" for e in denied)
            assert verify_chain(conn).ok is True
        finally:
            conn.close()

    @pytest.mark.parametrize(
        "bad_body",
        [
            {},
            {"accountant_ack": False},
            {"signature": "a" * 64, "signer": "simulated"},
            {"document_digest": "a" * 64, "signer": "simulated"},
            {"document_digest": "a" * 64, "signature": "b" * 64},
            {"document_digest": "", "signature": "b" * 64, "signer": "simulated"},
            {"document_digest": "   ", "signature": "b" * 64, "signer": "simulated"},
            {"document_digest": "a" * 64, "signature": "", "signer": "ncalayer"},
            {"document_digest": "a" * 64, "signature": "b" * 64, "signer": "unknown"},
        ],
    )
    def test_missing_or_invalid_binding_fields_return_422_validation_error(
        self,
        signing_api_env: tuple[FastAPI, Path, TestClient, TestClient],
        bad_body: dict[str, Any],
    ) -> None:
        _, _, acc, _ = signing_api_env
        queue = _load_queue_by_id()

        p = acc.post("/api/v1/payments", json=_to_payment_input(queue["Q-001"]), headers=CSRF).json()
        resp = acc.post(
            f"/api/v1/payments/{p['id']}/sign",
            json=bad_body,
            headers=CSRF,
        )
        assert resp.status_code == 422
        assert resp.json()["code"] == "validation_error"
        assert acc.get(f"/api/v1/payments/{p['id']}").json()["status"] == "checked"

    def test_amount_change_between_load_and_sign_returns_409_document_mismatch(
        self, signing_api_env: tuple[FastAPI, Path, TestClient, TestClient]
    ) -> None:
        _, db_path, acc, _ = signing_api_env
        queue = _load_queue_by_id()

        # 1. Load payment and compute signature over its original digest
        original = acc.post(
            "/api/v1/payments",
            json=_to_payment_input(queue["Q-001"], amount_kzt=500_000),
            headers=CSRF,
        ).json()
        stale_digest = original["document_digest"]
        stale_sig = SimulatedSigner().sign(stale_digest, original["company_id"])

        # 2. Edit amount via API before signing -> stale digest must be rejected with 409 document_mismatch
        edited = acc.put(
            f"/api/v1/payments/{original['id']}",
            json=_to_payment_input(queue["Q-001"], amount_kzt=510_000),
            headers=CSRF,
        )
        assert edited.status_code == 200
        new_digest = edited.json()["document_digest"]
        assert new_digest != stale_digest

        r_stale = acc.post(
            f"/api/v1/payments/{original['id']}/sign",
            json={
                "document_digest": stale_digest,
                "signature": stale_sig,
                "signer": "simulated",
            },
            headers=CSRF,
        )
        assert r_stale.status_code == 409
        assert r_stale.json()["code"] == "document_mismatch"
        assert acc.get(f"/api/v1/payments/{original['id']}").json()["status"] == "checked"

        # 3. Also verify direct TOCTOU amount tampering in DB with unchanged check_id is caught
        fresh_sig_before_tamper = SimulatedSigner().sign(new_digest, original["company_id"])
        conn = connect(db_path)
        try:
            with tx(conn):
                conn.execute(
                    "UPDATE payments SET amount_tiyn = ? WHERE id = ?",
                    (520_000 * 100, original["id"]),
                )
        finally:
            conn.close()

        r_toctou = acc.post(
            f"/api/v1/payments/{original['id']}/sign",
            json={
                "document_digest": new_digest,
                "signature": fresh_sig_before_tamper,
                "signer": "simulated",
            },
            headers=CSRF,
        )
        assert r_toctou.status_code == 409
        assert r_toctou.json()["code"] == "document_mismatch"

        # 4. Reloading payment gets updated digest and signing succeeds
        ok = acc.post(
            f"/api/v1/payments/{original['id']}/sign",
            json=build_sign_payload(acc, original["id"]),
            headers=CSRF,
        )
        assert ok.status_code == 200
        assert ok.json()["status"] == "signed"

    def test_ncalayer_signer_returns_501_signature_verification_unavailable_with_audit(
        self, signing_api_env: tuple[FastAPI, Path, TestClient, TestClient]
    ) -> None:
        _, db_path, acc, _ = signing_api_env
        queue = _load_queue_by_id()

        p = acc.post("/api/v1/payments", json=_to_payment_input(queue["Q-001"]), headers=CSRF).json()
        digest = p["document_digest"]

        for lang in ("ru", "kk", "en"):
            resp = acc.post(
                f"/api/v1/payments/{p['id']}/sign?lang={lang}",
                json={
                    "document_digest": digest,
                    "signature": "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8A",
                    "signer": "ncalayer",
                },
                headers=CSRF,
            )
            assert resp.status_code == 501
            body = resp.json()
            assert body["code"] == "signature_verification_unavailable"
            assert body["detail"] == t("error.prod.signature_verification_unavailable", lang)

        # Payment stays unsigned and digest remains unchanged
        after = acc.get(f"/api/v1/payments/{p['id']}").json()
        assert after["status"] == "checked"
        assert after["document_digest"] == digest

        conn = connect(db_path)
        try:
            denied = list_audit(conn, payment_id=p["id"], action="sign_denied", limit=10)
            assert len(denied) == 3
            assert all(e.details["code"] == "signature_verification_unavailable" for e in denied)
            assert verify_chain(conn).ok is True
        finally:
            conn.close()

    def test_ncalayer_with_custom_verifier_records_certificate_details_in_audit(
        self, signing_api_env: tuple[FastAPI, Path, TestClient, TestClient]
    ) -> None:
        _, db_path, acc, _ = signing_api_env
        queue = _load_queue_by_id()

        p = acc.post("/api/v1/payments", json=_to_payment_input(queue["Q-001"]), headers=CSRF).json()
        digest = p["document_digest"]
        assert isinstance(digest, str)

        class StubCmsVerifier:
            def verify(
                self,
                doc_digest: str,
                signature_cms_b64: str,
                company_id: str,
            ) -> VerifiedSignature:
                assert doc_digest == digest
                assert signature_cms_b64 == "BASE64CMS=="
                assert company_id == p["company_id"]
                return VerifiedSignature(
                    signer_subject="CN=НУРЛАНОВА АЙГУЛЬ",
                    signer_iin_bin="900101400123",
                    certificate_serial="ABCDEF0123456789",
                    signed_at="2026-11-26T10:15:00+00:00",
                )

        conn = connect(db_path)
        try:
            u_row = conn.execute("SELECT * FROM users WHERE login = 'accountant'").fetchone()
            assert u_row is not None
            user = User(
                id=int(u_row["id"]),
                login=str(u_row["login"]),
                full_name=str(u_row["full_name"]),
                role=u_row["role"],
                company_id=str(u_row["company_id"]),
            )
            signed = payments_service.sign_payment(
                conn,
                payment_id=p["id"],
                user=user,
                accountant_ack=False,
                today=TEST_TODAY,
                document_digest=digest,
                signature="BASE64CMS==",
                signer="ncalayer",
                signature_verifier=StubCmsVerifier(),
            )
            assert signed.status == "signed"

            entries = list_audit(conn, payment_id=p["id"], action="sign", limit=5)
            assert len(entries) == 1
            details = entries[0].details
            assert details["document_digest"] == digest
            assert details["signer"] == "ncalayer"
            assert details["label"] == NCALAYER_LABEL
            assert details["simulated"] is False
            assert details["certificate"] == {
                "signer_subject": "CN=НУРЛАНОВА АЙГУЛЬ",
                "signer_iin_bin": "900101400123",
                "certificate_serial": "ABCDEF0123456789",
                "signed_at": "2026-11-26T10:15:00+00:00",
            }
            assert verify_chain(conn).ok is True
        finally:
            conn.close()

    def test_batch_sign_green_computes_server_digest_signs_simulated_and_records_audit(
        self, signing_api_env: tuple[FastAPI, Path, TestClient, TestClient]
    ) -> None:
        _, db_path, acc, _ = signing_api_env
        queue = _load_queue_by_id()

        p_green = acc.post(
            "/api/v1/payments",
            json=_to_payment_input(queue["Q-001"]),
            headers=CSRF,
        ).json()
        expected_digest = p_green["document_digest"]
        assert isinstance(expected_digest, str) and len(expected_digest) == 64

        # Even if client passes spoofed digest/signature/signer fields, server ignores them
        # and computes digest + simulated signature server-side.
        resp = acc.post(
            "/api/v1/payments/batch/sign-green",
            json={
                "payment_ids": [p_green["id"]],
                "document_digest": "f" * 64,
                "signature": "spoofed",
                "signer": "ncalayer",
            },
            headers=CSRF,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert [item["id"] for item in body["done"]] == [p_green["id"]]
        assert body["done"][0]["status"] == "signed"
        assert body["skipped"] == []

        conn = connect(db_path)
        try:
            entries = list_audit(conn, payment_id=p_green["id"], action="sign", limit=5)
            assert len(entries) == 1
            details = entries[0].details
            assert details["document_digest"] == expected_digest
            assert details["signer"] == "simulated"
            assert details["label"] == SIMULATED_LABEL
            assert details["simulated"] is True
            assert verify_chain(conn).ok is True
        finally:
            conn.close()
