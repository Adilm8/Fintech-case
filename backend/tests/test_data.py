"""Tests for generated synthetic datasets and demo scenario invariants."""

from __future__ import annotations

import json
import statistics
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

from app.risk.config import BCC_BANK_CODE, BCC_BIK, DEMO_TODAY
from app.validators.kz import (
    bik_matches_iik,
    bik_ok,
    bin_iin_checksum_ok,
    bin_kind,
    iik_bank_code,
    iik_ok,
)
from scripts.generate_data import generate_all

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def _load_json(filename: str):
    return json.loads((DATA_DIR / filename).read_text(encoding="utf-8"))


class TestGeneratedDatasets:
    def test_all_expected_files_exist(self) -> None:
        for name in (
            "banks.json",
            "registry.json",
            "bcc_accounts.json",
            "history.json",
            "queue.json",
        ):
            assert (DATA_DIR / name).exists(), f"Missing generated file: {name}"

    def test_regeneration_is_deterministic(self, tmp_path: Path) -> None:
        paths = generate_all(output_dir=tmp_path)
        for path in paths.values():
            committed = (DATA_DIR / path.name).read_text(encoding="utf-8")
            regenerated = path.read_text(encoding="utf-8")
            assert regenerated == committed, f"Non-deterministic output for {path.name}"

    def test_all_bins_and_iiks_pass_validation_and_bank_consistency(self) -> None:
        registry: dict[str, str] = _load_json("registry.json")
        bcc_accounts: dict[str, dict[str, str]] = _load_json("bcc_accounts.json")
        history: dict = _load_json("history.json")
        queue: list[dict] = _load_json("queue.json")

        # Registry BINs
        assert len(registry) >= 8
        for bin_num, company_name in registry.items():
            assert bin_iin_checksum_ok(bin_num), f"Invalid registry BIN: {bin_num}"
            assert bin_kind(bin_num) == "bin"
            assert company_name.strip()

        # BCC accounts
        for iik, info in bcc_accounts.items():
            ok, err = iik_ok(iik)
            assert ok, f"Invalid BCC IIK {iik}: {err}"
            assert iik_bank_code(iik) == BCC_BANK_CODE
            assert bik_matches_iik(BCC_BIK, iik)
            assert bin_iin_checksum_ok(info["owner_bin"])
            assert info["owner_bin"] in registry
            opened = date.fromisoformat(info["opened_at"])
            assert opened <= DEMO_TODAY

        # Client in history
        client = history["client"]
        assert client["name"] == "ТОО «ТехноСтрой Астана»"
        assert bin_iin_checksum_ok(client["bin"])
        assert iik_ok(client["iik"]) == (True, None)
        assert bik_ok(client["bik"])
        assert bik_matches_iik(client["bik"], client["iik"])

        # History payments
        for payment in history["payments"]:
            assert bin_iin_checksum_ok(payment["recipient_bin"])
            ok, err = iik_ok(payment["recipient_iik"])
            assert ok, f"Invalid history IIK {payment['recipient_iik']}: {err}"
            assert bik_ok(payment["recipient_bik"])
            assert bik_matches_iik(payment["recipient_bik"], payment["recipient_iik"])
            assert payment["amount_kzt"] > 0

        # Queue payments
        for item in queue:
            assert bin_iin_checksum_ok(item["recipient_bin"])
            ok, err = iik_ok(item["recipient_iik"])
            assert ok, f"Invalid queue IIK {item['recipient_iik']}: {err}"
            assert bik_ok(item["recipient_bik"])
            assert bik_matches_iik(item["recipient_bik"], item["recipient_iik"])
            assert item["amount_kzt"] > 0

    def test_history_constraints(self) -> None:
        history = _load_json("history.json")
        payments = history["payments"]

        assert 25 <= len(payments) <= 35
        six_months_ago = DEMO_TODAY - timedelta(days=183)
        for p in payments:
            paid_at = date.fromisoformat(p["paid_at"])
            assert six_months_ago <= paid_at < DEMO_TODAY

        by_supplier = Counter(p["recipient_name"] for p in payments)
        assert len(by_supplier) == 5
        for supplier_name, count in by_supplier.items():
            assert count >= 5, f"{supplier_name} has fewer than 5 payments: {count}"

        # Алатау Снаб on Halyk Bank IIK with ~1 350 000 median
        alatau_payments = [p for p in payments if p["recipient_name"] == "ТОО «Алатау Снаб»"]
        assert len(alatau_payments) >= 5
        assert all(p["recipient_bik"] == "HSBKKZKX" for p in alatau_payments)
        assert all(iik_bank_code(p["recipient_iik"]) == "601" for p in alatau_payments)
        alatau_median = statistics.median(p["amount_kzt"] for p in alatau_payments)
        assert 1_300_000 <= alatau_median <= 1_400_000

        # КазЛогистик Групп present with >= 5 payments
        kazlog_payments = [p for p in payments if p["recipient_name"] == "ТОО «КазЛогистик Групп»"]
        assert len(kazlog_payments) >= 5

    def test_queue_demo_scenarios(self) -> None:
        registry: dict[str, str] = _load_json("registry.json")
        bcc_accounts: dict[str, dict[str, str]] = _load_json("bcc_accounts.json")
        history = _load_json("history.json")
        queue: list[dict] = _load_json("queue.json")

        assert len(queue) == 4
        scenarios = [item["scenario"] for item in queue]
        assert scenarios == ["green", "yellow", "red", "grey"]
        assert len({item["id"] for item in queue}) == 4

        by_scenario = {item["scenario"]: item for item in queue}
        payments = history["payments"]

        alatau_history = [p for p in payments if p["recipient_name"] == "ТОО «Алатау Снаб»"]
        alatau_bin = alatau_history[0]["recipient_bin"]
        alatau_iik = alatau_history[0]["recipient_iik"]
        alatau_median = statistics.median(p["amount_kzt"] for p in alatau_history)

        kazlog_history = [p for p in payments if p["recipient_name"] == "ТОО «КазЛогистик Групп»"]
        kazlog_bin = kazlog_history[0]["recipient_bin"]
        kazlog_iik = kazlog_history[0]["recipient_iik"]
        kazlog_bik = kazlog_history[0]["recipient_bik"]

        # Green: same supplier, same Halyk IIK, usual amount
        green = by_scenario["green"]
        assert green["recipient_name"] == "ТОО «Алатау Снаб»"
        assert green["recipient_bin"] == alatau_bin
        assert green["recipient_iik"] == alatau_iik
        assert green["recipient_bik"] == "HSBKKZKX"
        assert abs(green["amount_kzt"] - alatau_median) / alatau_median < 0.1

        # Yellow: regular supplier КазЛогистик Групп, new valid IIK in another bank, usual amount
        yellow = by_scenario["yellow"]
        assert yellow["recipient_name"] == "ТОО «КазЛогистик Групп»"
        assert yellow["recipient_bin"] == kazlog_bin
        assert yellow["recipient_iik"] != kazlog_iik
        assert yellow["recipient_bik"] != kazlog_bik
        assert yellow["recipient_iik"] not in bcc_accounts

        # Red: Latin C lookalike, different BIN, BCC account owned by Вектор Трейд opened 12d ago,
        # amount 4 900 000 (~3.6x median), urgent wording in purpose.
        red = by_scenario["red"]
        assert "\u0043" in red["recipient_name"]  # Latin C
        assert "Алатау" in red["recipient_name"]
        assert red["recipient_bin"] != alatau_bin
        assert red["recipient_bik"] == BCC_BIK
        assert red["recipient_iik"] in bcc_accounts

        red_bcc = bcc_accounts[red["recipient_iik"]]
        assert red_bcc["owner_bin"] != red["recipient_bin"]
        assert registry[red_bcc["owner_bin"]] == "ТОО «Вектор Трейд»"
        assert red_bcc["opened_at"] == (DEMO_TODAY - timedelta(days=12)).isoformat()

        assert red["amount_kzt"] == 4_900_000
        ratio = red["amount_kzt"] / alatau_median
        assert 3.4 <= ratio <= 3.8
        assert "срочно, по новым реквизитам" in red["purpose"].lower()

        # Grey: first payment to a new valid supplier not in history
        grey = by_scenario["grey"]
        history_bins = {p["recipient_bin"] for p in payments}
        assert grey["recipient_bin"] not in history_bins
        assert registry[grey["recipient_bin"]] == grey["recipient_name"]
        assert grey["amount_kzt"] < 500_000
