"""Tests for the red-scenario demo invoice sample (alatau lookalike, Q-003)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.invoice_ai import claude_extractor, service, text_parser
from app.main import app
from app.store import store
from app.validators.kz import bik_matches_iik, bik_ok, bin_iin_checksum_ok, iik_check

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SAMPLE_PATH = REPO_ROOT / "frontend" / "public" / "samples" / "demo-invoice-alatau.txt"
BACKEND_SAMPLE_PATH = REPO_ROOT / "backend" / "data" / "samples" / "demo-invoice-alatau.txt"
QUEUE_PATH = REPO_ROOT / "backend" / "data" / "queue.json"

EXPECTED_NAME = "ТОО «Алатау Cнаб»"  # Latin 'C' (U+0043) in "Cнаб"
EXPECTED_BIN = "240646118785"
EXPECTED_IIK = "KZ51856KZT2486117574"
EXPECTED_BIK = "KCJBKZKX"
EXPECTED_AMOUNT = 4_900_000.0


def _load_q003() -> dict[str, Any]:
    queue = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
    for item in queue:
        if item["id"] == "Q-003":
            return item
    raise AssertionError("Q-003 scenario not found in backend/data/queue.json")


def test_demo_sample_file_exists_and_matches_backend_copy() -> None:
    assert FRONTEND_SAMPLE_PATH.is_file(), f"Missing sample: {FRONTEND_SAMPLE_PATH}"
    assert BACKEND_SAMPLE_PATH.is_file(), f"Missing reference copy: {BACKEND_SAMPLE_PATH}"

    frontend_bytes = FRONTEND_SAMPLE_PATH.read_bytes()
    backend_bytes = BACKEND_SAMPLE_PATH.read_bytes()
    assert frontend_bytes, "Demo invoice sample must not be empty"
    assert frontend_bytes == backend_bytes

    text = frontend_bytes.decode("utf-8")
    assert "Алатау Cнаб" in text  # Latin C (U+0043)
    assert "Алатау Снаб" not in text  # must not accidentally use Cyrillic С


def test_demo_sample_matches_q003_and_passes_kz_validators() -> None:
    q003 = _load_q003()
    assert q003["scenario"] == "red"
    assert q003["recipient_bin"] == EXPECTED_BIN
    assert q003["recipient_iik"] == EXPECTED_IIK
    assert q003["recipient_bik"] == EXPECTED_BIK
    assert float(q003["amount_kzt"]) == EXPECTED_AMOUNT

    assert bin_iin_checksum_ok(EXPECTED_BIN)
    ok, err_key, _ = iik_check(EXPECTED_IIK)
    assert ok, f"IIK failed validator: {err_key}"
    assert bik_ok(EXPECTED_BIK)
    assert bik_matches_iik(EXPECTED_BIK, EXPECTED_IIK)


def test_demo_sample_parse_document_and_extract_invoice_without_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Even when an API key is configured, text/plain must stay local and never invoke the SDK.
    def _forbid_parse(**_kwargs: Any) -> Any:
        raise AssertionError("External extractor must not be called for text/plain")

    fake_sdk = SimpleNamespace(
        Anthropic=lambda: SimpleNamespace(messages=SimpleNamespace(parse=_forbid_parse))
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-demo-no-network")
    monkeypatch.setattr(claude_extractor, "_import_anthropic", lambda: fake_sdk)

    raw = FRONTEND_SAMPLE_PATH.read_bytes()
    parsed_direct = text_parser.parse_document(raw, "text/plain")
    extracted = service.extract_invoice(raw, "text/plain", FRONTEND_SAMPLE_PATH.name)

    for result in (parsed_direct, extracted):
        assert result.source == "text_rules"
        assert result.recipient_name == EXPECTED_NAME
        assert "\u0043наб" in (result.recipient_name or "")
        assert "\u0421наб" not in (result.recipient_name or "")
        assert result.recipient_bin == EXPECTED_BIN
        assert result.recipient_iik == EXPECTED_IIK
        assert result.recipient_bik == EXPECTED_BIK
        assert result.amount_kzt == EXPECTED_AMOUNT
        assert result.currency == "KZT"
        assert result.kbe == "17"
        assert result.knp == "710"
        assert result.invoice_number == "309"
        assert result.invoice_date == "2026-04-20"
        purpose_lower = (result.purpose or "").lower()
        assert "срочно" in purpose_lower
        assert "новым реквизитам" in purpose_lower
        assert result.warnings == []
        assert result.confidence >= 0.8


def test_demo_sample_extract_to_check_returns_red_verdict(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setattr(store, "audit_log_path", tmp_path / "audit.jsonl")

    raw = FRONTEND_SAMPLE_PATH.read_bytes()
    client = TestClient(app)

    extract_resp = client.post(
        f"/api/invoice/extract?filename={FRONTEND_SAMPLE_PATH.name}",
        content=raw,
        headers={"Content-Type": "text/plain"},
    )
    assert extract_resp.status_code == 200
    extracted = extract_resp.json()
    assert extracted["source"] == "text_rules"
    assert extracted["recipient_name"] == EXPECTED_NAME
    assert extracted["amount_kzt"] == EXPECTED_AMOUNT

    check_payload = {
        "recipient_name": extracted["recipient_name"],
        "recipient_bin": extracted["recipient_bin"],
        "recipient_iik": extracted["recipient_iik"],
        "recipient_bik": extracted["recipient_bik"],
        "amount_kzt": extracted["amount_kzt"],
        "purpose": extracted["purpose"],
        "kbe": extracted["kbe"] or "",
        "knp": extracted["knp"] or "",
    }
    check_resp = client.post("/api/payments/check", json=check_payload)
    assert check_resp.status_code == 200
    result = check_resp.json()

    assert result["verdict"] == "red"
    assert result["score"] == 100

    signal_ids = {sig["rule_id"] for sig in result["signals"]}
    expected_signals = {
        "lookalike_supplier",
        "mixed_script_name",
        "bcc_account_other_owner",
        "bin_name_mismatch",
        "amount_anomaly",
        "new_bcc_account",
        "urgent_wording",
    }
    assert expected_signals.issubset(signal_ids), (
        f"Missing expected signals: {expected_signals - signal_ids}; got {signal_ids}"
    )

    assert result["history"]["compared_with"] == "ТОО «Алатау Снаб»"
    comparison_by_field = {row["field"]: row for row in result["comparison"]}
    for field in ("name", "bin", "iik", "bik", "bank", "amount"):
        assert comparison_by_field[field]["differs"] is True
    assert comparison_by_field["name"]["diff_positions"], (
        "Mixed-script Latin 'C' position should be highlighted in name diff"
    )
