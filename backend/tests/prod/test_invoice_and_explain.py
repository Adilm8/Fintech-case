"""Prod-mode tests for /api/invoice/extract and /api/explain auth, CSRF, and graceful fallback."""

from __future__ import annotations

from collections.abc import Generator, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.explain import service as explain_service
from app.main import app as demo_app
from app.prod.app import create_prod_app
from app.prod.deps import CSRF_HEADER_NAME, CSRF_HEADER_VALUE
from app.settings import Settings
from tests.prod.conftest import (
    TEST_PW_ACCOUNTANT,
    TEST_PW_ANALYST,
    TEST_PW_DIRECTOR,
    TEST_SEED_PW,
    TEST_TODAY,
    seed_auth_users,
)

CSRF_HEADERS: dict[str, str] = {CSRF_HEADER_NAME: CSRF_HEADER_VALUE}

SUPPLIER_BIN = "160542439625"
SUPPLIER_IIK = "KZ246010005016525808"
SUPPLIER_BIK = "HSBKKZKX"
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16

SAMPLE_INVOICE_TEXT = f"""Счёт на оплату № 214 от 20 апреля 2026 г.
Бенефициар: ТОО «Алатау Снаб»
БИН/ИИН: {SUPPLIER_BIN}
ИИК: {SUPPLIER_IIK}   Кбе 17
БИК: {SUPPLIER_BIK}    Код назначения платежа 710
Всего к оплате: 1 360 000,00 тенге
Назначение платежа: Оплата по счёту № 214 за строительные материалы
"""

SAMPLE_CHECK: dict[str, Any] = {
    "check_id": "chk-prod-1",
    "verdict": "red",
    "score": 85,
    "headline": "Реквизиты поставщика изменились",
    "headline_ru": "Реквизиты поставщика изменились",
    "signals": [
        {
            "rule_id": "iik_changed",
            "severity": "primary",
            "reason": "У поставщика сменился ИИК.",
            "reason_ru": "У поставщика сменился ИИК.",
        },
        {
            "rule_id": "amount_anomaly",
            "severity": "amplifier",
            "reason": "Сумма значительно выше обычной.",
            "reason_ru": "Сумма значительно выше обычной.",
        },
    ],
    "comparison": [
        {
            "field": "iik",
            "in_invoice": SUPPLIER_IIK,
            "in_history": "KZ111111111111111111",
            "differs": True,
        }
    ],
    "next_action": {
        "text": "Позвоните поставщику по номеру из договора.",
        "text_ru": "Позвоните поставщику по номеру из договора.",
        "primary": "postpone",
    },
    "analyst_details": {
        "bcc_account": {"owner_name": "ТОО Закрытые Данные", "owner_bin": "123456789012"}
    },
}


@pytest.fixture(autouse=True)
def _no_external_api_key(monkeypatch: pytest.MonkeyPatch) -> Generator[None]:
    """Ensure tests run without external API keys and clear explain cache between tests."""
    explain_service._cache.clear()
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setattr(explain_service, "load_env_file", lambda *a, **k: None)
    yield
    explain_service._cache.clear()


@pytest.fixture
def prod_client(
    tmp_path: Path,
    precomputed_password_hashes: dict[str, str],
) -> Iterator[TestClient]:
    db_file = tmp_path / "prod_aux.db"
    seed_auth_users(db_file, precomputed_password_hashes)
    cfg = Settings(app_mode="prod", db_path=db_file, session_ttl_hours=12, cookie_secure=False)
    prod_app: FastAPI = create_prod_app(db_path=db_file, settings_override=cfg)
    with TestClient(prod_app) as client:
        yield client


def _login(client: TestClient, login: str, password: str) -> None:
    resp = client.post(
        "/api/v1/auth/login",
        json={"login": login, "password": password},
        headers=CSRF_HEADERS,
    )
    assert resp.status_code == 200, resp.text


class TestProdInvoiceEndpoint:
    def test_unauthenticated_returns_401(self, prod_client: TestClient) -> None:
        resp_no_header = prod_client.post(
            "/api/invoice/extract?filename=invoice.txt",
            content=SAMPLE_INVOICE_TEXT.encode("utf-8"),
            headers={"Content-Type": "text/plain"},
        )
        assert resp_no_header.status_code == 401
        assert resp_no_header.json()["code"] == "not_authenticated"

        resp_with_header = prod_client.post(
            "/api/invoice/extract?filename=invoice.txt",
            content=SAMPLE_INVOICE_TEXT.encode("utf-8"),
            headers={"Content-Type": "text/plain", **CSRF_HEADERS},
        )
        assert resp_with_header.status_code == 401
        assert resp_with_header.json()["code"] == "not_authenticated"

        resp_spoofed_role = prod_client.post(
            "/api/invoice/extract?filename=invoice.txt",
            content=SAMPLE_INVOICE_TEXT.encode("utf-8"),
            headers={"Content-Type": "text/plain", "X-Role": "analyst", **CSRF_HEADERS},
        )
        assert resp_spoofed_role.status_code == 401
        assert resp_spoofed_role.json()["code"] == "not_authenticated"

    def test_missing_or_wrong_shield_header_rejected_with_403(
        self, prod_client: TestClient
    ) -> None:
        _login(prod_client, "accountant", TEST_PW_ACCOUNTANT)

        no_header = prod_client.post(
            "/api/invoice/extract?filename=invoice.txt",
            content=SAMPLE_INVOICE_TEXT.encode("utf-8"),
            headers={"Content-Type": "text/plain"},
        )
        assert no_header.status_code == 403
        assert no_header.json()["code"] == "csrf_header_missing"

        wrong_header = prod_client.post(
            "/api/invoice/extract?filename=invoice.txt",
            content=SAMPLE_INVOICE_TEXT.encode("utf-8"),
            headers={"Content-Type": "text/plain", CSRF_HEADER_NAME: "0"},
        )
        assert wrong_header.status_code == 403
        assert wrong_header.json()["code"] == "csrf_header_missing"

    @pytest.mark.parametrize(
        ("login", "password"),
        [
            ("accountant", TEST_PW_ACCOUNTANT),
            ("director", TEST_PW_DIRECTOR),
            ("analyst", TEST_PW_ANALYST),
        ],
    )
    def test_logged_in_any_role_with_header_extracts_gracefully_without_key(
        self, prod_client: TestClient, login: str, password: str
    ) -> None:
        _login(prod_client, login, password)

        resp = prod_client.post(
            "/api/invoice/extract?filename=invoice.txt",
            content=SAMPLE_INVOICE_TEXT.encode("utf-8"),
            headers={"Content-Type": "text/plain", **CSRF_HEADERS},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["source"] == "text_rules"
        assert body["recipient_bin"] == SUPPLIER_BIN
        assert body["recipient_iik"] == SUPPLIER_IIK
        assert body["recipient_bik"] == SUPPLIER_BIK
        assert body["amount_kzt"] == 1360000.0

    def test_logged_in_image_without_key_degrades_gracefully(
        self, prod_client: TestClient
    ) -> None:
        _login(prod_client, "accountant", TEST_PW_ACCOUNTANT)

        resp = prod_client.post(
            "/api/invoice/extract?filename=scan.png",
            content=PNG_BYTES,
            headers={"Content-Type": "image/png", **CSRF_HEADERS},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["source"] == "none"
        assert isinstance(body["warnings"], list) and len(body["warnings"]) >= 1

    def test_logged_in_bad_file_returns_expected_http_error(
        self, prod_client: TestClient
    ) -> None:
        _login(prod_client, "accountant", TEST_PW_ACCOUNTANT)

        empty_resp = prod_client.post(
            "/api/invoice/extract?filename=empty.txt",
            content=b"",
            headers={"Content-Type": "text/plain", **CSRF_HEADERS},
        )
        assert empty_resp.status_code == 400

        bad_type_resp = prod_client.post(
            "/api/invoice/extract?filename=evil.pdf",
            content=b"MZ\x90\x00exe",
            headers={"Content-Type": "application/pdf", **CSRF_HEADERS},
        )
        assert bad_type_resp.status_code == 415


class TestProdExplainEndpoint:
    @pytest.mark.parametrize("path", ["/api/explain", "/api/explain/"])
    def test_unauthenticated_returns_401(self, prod_client: TestClient, path: str) -> None:
        resp_no_header = prod_client.post(path, json={"check": SAMPLE_CHECK, "lang": "ru"})
        assert resp_no_header.status_code == 401
        assert resp_no_header.json()["code"] == "not_authenticated"

        resp_with_header = prod_client.post(
            path,
            json={"check": SAMPLE_CHECK, "lang": "ru"},
            headers=CSRF_HEADERS,
        )
        assert resp_with_header.status_code == 401
        assert resp_with_header.json()["code"] == "not_authenticated"

    @pytest.mark.parametrize("path", ["/api/explain", "/api/explain/"])
    def test_missing_or_wrong_shield_header_rejected_with_403(
        self, prod_client: TestClient, path: str
    ) -> None:
        _login(prod_client, "accountant", TEST_PW_ACCOUNTANT)

        no_header = prod_client.post(path, json={"check": SAMPLE_CHECK, "lang": "ru"})
        assert no_header.status_code == 403
        assert no_header.json()["code"] == "csrf_header_missing"

        wrong_header = prod_client.post(
            path,
            json={"check": SAMPLE_CHECK, "lang": "ru"},
            headers={CSRF_HEADER_NAME: "invalid"},
        )
        assert wrong_header.status_code == 403
        assert wrong_header.json()["code"] == "csrf_header_missing"

    @pytest.mark.parametrize(
        ("login", "password"),
        [
            ("accountant", TEST_PW_ACCOUNTANT),
            ("director", TEST_PW_DIRECTOR),
            ("analyst", TEST_PW_ANALYST),
        ],
    )
    def test_logged_in_any_role_with_header_returns_template_without_key(
        self, prod_client: TestClient, login: str, password: str
    ) -> None:
        _login(prod_client, login, password)

        resp = prod_client.post(
            "/api/explain",
            json={"check": SAMPLE_CHECK, "lang": "ru"},
            headers=CSRF_HEADERS,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["source"] == "template"
        assert body["warnings"] == ["no_api_key"]
        assert "У поставщика сменился ИИК." in body["text"]
        assert "Закрытые Данные" not in body["text"]

    def test_revoked_session_returns_401(self, prod_client: TestClient) -> None:
        _login(prod_client, "director", TEST_PW_DIRECTOR)
        assert prod_client.post("/api/v1/auth/logout", headers=CSRF_HEADERS).status_code == 204

        resp_explain = prod_client.post(
            "/api/explain",
            json={"check": SAMPLE_CHECK, "lang": "ru"},
            headers=CSRF_HEADERS,
        )
        assert resp_explain.status_code == 401

        resp_invoice = prod_client.post(
            "/api/invoice/extract?filename=invoice.txt",
            content=SAMPLE_INVOICE_TEXT.encode("utf-8"),
            headers={"Content-Type": "text/plain", **CSRF_HEADERS},
        )
        assert resp_invoice.status_code == 401


class TestProdIsolationAndVerdictIndependence:
    def test_demo_app_routes_remain_unprotected(self, prod_client: TestClient) -> None:
        # Touch prod_client so prod_app is constructed first, confirming router reuse does not
        # leak prod dependencies onto the demo application.
        assert prod_client.post("/api/explain", json={"check": SAMPLE_CHECK}).status_code == 401

        with TestClient(demo_app) as demo:
            exp = demo.post("/api/explain", json={"check": SAMPLE_CHECK, "lang": "ru"})
            assert exp.status_code == 200
            assert exp.json()["source"] == "template"

            inv = demo.post(
                "/api/invoice/extract?filename=invoice.txt",
                content=SAMPLE_INVOICE_TEXT.encode("utf-8"),
                headers={"Content-Type": "text/plain"},
            )
            assert inv.status_code == 200
            assert inv.json()["source"] == "text_rules"

    def test_explain_does_not_alter_payment_verdict(self, seeded_db: Path) -> None:
        cfg = Settings(
            app_mode="prod",
            db_path=seeded_db,
            today_override=TEST_TODAY,
            cookie_secure=False,
        )
        prod_app = create_prod_app(db_path=seeded_db, settings_override=cfg)
        with TestClient(prod_app) as client:
            _login(client, "accountant", TEST_SEED_PW)

            created = client.post(
                "/api/v1/payments",
                json={
                    "recipient_name": "ТОО «КазЛогистик Групп»",
                    "recipient_bin": "180947320524",
                    "recipient_iik": "KZ509650006872032298",
                    "recipient_bik": "IRTYKZKA",
                    "amount_kzt": 700000.0,
                    "purpose": "Оплата транспортно-экспедиционных услуг по счёту № 318",
                },
                headers=CSRF_HEADERS,
            )
            assert created.status_code == 201
            payment = created.json()
            original_check = payment["check"]
            assert original_check["verdict"] in ("yellow", "red", "grey")

            exp = client.post(
                "/api/explain",
                json={"check": original_check, "lang": "ru"},
                headers=CSRF_HEADERS,
            )
            assert exp.status_code == 200
            assert exp.json()["source"] == "template"
            assert exp.json()["text"]

            fetched = client.get(f"/api/v1/payments/{payment['id']}")
            assert fetched.status_code == 200
            assert fetched.json()["check"]["verdict"] == original_check["verdict"]
            assert fetched.json()["check"]["score"] == original_check["score"]
