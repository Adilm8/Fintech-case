"""Tests for generated synthetic datasets and demo scenario invariants."""

from __future__ import annotations

import json
import statistics
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

from app.i18n import KIND_LABELS
from app.risk.config import BCC_BANK_CODE, BCC_BIK, DEMO_TODAY, RULESET_VERSION
from app.risk.evaluation import evaluate_dataset, format_metrics_report
from app.validators.kz import (
    bik_matches_iik,
    bik_ok,
    bin_iin_checksum_ok,
    bin_kind,
    iik_bank_code,
    iik_ok,
)
from scripts.generate_data import generate_all
from scripts.generate_eval import generate_eval_set

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
        banks_raw = _load_json("banks.json")
        assert "National Bank of Kazakhstan" in banks_raw["note"]
        assert BCC_BANK_CODE == "856"
        assert any(b["code"] == "856" and b["bik"] == "KCJBKZKX" for b in banks_raw["banks"])
        assert any(b["code"] == "125" and b["bik"] == "NBRKKZKX" for b in banks_raw["banks"])

        registry: dict[str, str] = _load_json("registry.json")
        bcc_accounts: dict[str, dict[str, str]] = _load_json("bcc_accounts.json")
        history: dict = _load_json("history.json")
        queue: list[dict] = _load_json("queue.json")

        # Registry BINs / IINs
        assert len(registry) >= 15
        for bin_num, company_name in registry.items():
            assert bin_iin_checksum_ok(bin_num), f"Invalid registry BIN/IIN: {bin_num}"
            expected_kind = "iin" if company_name.startswith("ИП ") else "bin"
            assert bin_kind(bin_num) == expected_kind
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

        # Queue payments (invalid scenario intentionally contains an IIK typo)
        for item in queue:
            assert bin_iin_checksum_ok(item["recipient_bin"])
            assert bik_ok(item["recipient_bik"])
            assert item["amount_kzt"] > 0
            if item["scenario"] == "invalid":
                ok, _ = iik_ok(item["recipient_iik"])
                assert not ok, f"Expected invalid IIK for {item['id']}"
            else:
                ok, err = iik_ok(item["recipient_iik"])
                assert ok, f"Invalid queue IIK {item['recipient_iik']}: {err}"
                assert bik_matches_iik(item["recipient_bik"], item["recipient_iik"])

    def test_history_constraints(self) -> None:
        history = _load_json("history.json")
        payments = history["payments"]

        assert 140 <= len(payments) <= 165
        twelve_months_ago = DEMO_TODAY - timedelta(days=366)
        paid_dates: list[date] = []
        for p in payments:
            paid_at = date.fromisoformat(p["paid_at"])
            assert twelve_months_ago <= paid_at < DEMO_TODAY
            paid_dates.append(paid_at)
        assert (max(paid_dates) - min(paid_dates)).days >= 330

        by_supplier = Counter(p["recipient_name"] for p in payments)
        assert len(by_supplier) == 12
        for supplier_name, count in by_supplier.items():
            assert count >= 5, f"{supplier_name} has fewer than 5 payments: {count}"

        # Diverse banks from official banks.json
        distinct_biks = {p["recipient_bik"] for p in payments}
        assert len(distinct_biks) >= 10

        # Small and large suppliers both present
        amounts = [p["amount_kzt"] for p in payments]
        assert min(amounts) < 100_000
        assert max(amounts) > 3_000_000

        # IE supplier with valid IIN present in history
        ie_payments = [p for p in payments if p["recipient_name"] == "ИП Байжанов К.Т."]
        assert len(ie_payments) >= 10
        assert all(bin_kind(p["recipient_bin"]) == "iin" for p in ie_payments)

        # One supplier legally switched bank account mid-year (later payments go to new IIK)
        kran_payments = [p for p in payments if p["recipient_name"] == "ТОО «ЕвразияКранМонтаж»"]
        assert len(kran_payments) == 12
        early_iiks = {p["recipient_iik"] for p in kran_payments[:6]}
        late_iiks = {p["recipient_iik"] for p in kran_payments[6:]}
        assert len(early_iiks) == 1 and len(late_iiks) == 1
        assert early_iiks != late_iiks

        # Алатау Снаб on Halyk Bank IIK with ~1 350 000 median
        alatau_payments = [p for p in payments if p["recipient_name"] == "ТОО «Алатау Снаб»"]
        assert len(alatau_payments) >= 10
        assert all(p["recipient_bik"] == "HSBKKZKX" for p in alatau_payments)
        assert all(iik_bank_code(p["recipient_iik"]) == "601" for p in alatau_payments)
        alatau_median = statistics.median(p["amount_kzt"] for p in alatau_payments)
        assert 1_300_000 <= alatau_median <= 1_400_000

        # КазЛогистик Групп present with >= 10 payments
        kazlog_payments = [p for p in payments if p["recipient_name"] == "ТОО «КазЛогистик Групп»"]
        assert len(kazlog_payments) >= 10

    def test_queue_demo_scenarios(self) -> None:
        registry: dict[str, str] = _load_json("registry.json")
        bcc_accounts: dict[str, dict[str, str]] = _load_json("bcc_accounts.json")
        history = _load_json("history.json")
        queue: list[dict] = _load_json("queue.json")

        assert len(queue) == 10
        assert [item["id"] for item in queue[:4]] == ["Q-001", "Q-002", "Q-003", "Q-004"]
        assert [item["scenario"] for item in queue[:4]] == ["green", "yellow", "red", "grey"]
        assert len({item["id"] for item in queue}) == 10

        by_id = {item["id"]: item for item in queue}
        payments = history["payments"]

        alatau_history = [p for p in payments if p["recipient_name"] == "ТОО «Алатау Снаб»"]
        alatau_bin = alatau_history[0]["recipient_bin"]
        alatau_iik = alatau_history[0]["recipient_iik"]
        alatau_median = statistics.median(p["amount_kzt"] for p in alatau_history)

        kazlog_history = [p for p in payments if p["recipient_name"] == "ТОО «КазЛогистик Групп»"]
        kazlog_bin = kazlog_history[0]["recipient_bin"]
        kazlog_iik = kazlog_history[0]["recipient_iik"]
        kazlog_bik = kazlog_history[0]["recipient_bik"]

        # Q-001 (Green): same supplier, same Halyk IIK, usual amount and preserved text
        green = by_id["Q-001"]
        assert green["recipient_name"] == "ТОО «Алатау Снаб»"
        assert green["recipient_bin"] == alatau_bin
        assert green["recipient_iik"] == alatau_iik
        assert green["recipient_bik"] == "HSBKKZKX"
        assert green["amount_kzt"] == 1_360_000
        assert (
            green["purpose"]
            == "Оплата по счёту № 214 за строительные материалы по договору № 14-А"
        )
        assert abs(green["amount_kzt"] - alatau_median) / alatau_median < 0.1

        # Q-002 (Yellow): regular supplier КазЛогистик Групп, new valid IIK in another bank
        yellow = by_id["Q-002"]
        assert yellow["recipient_name"] == "ТОО «КазЛогистик Групп»"
        assert yellow["recipient_bin"] == kazlog_bin
        assert yellow["recipient_iik"] != kazlog_iik
        assert yellow["recipient_bik"] != kazlog_bik
        assert yellow["recipient_iik"] not in bcc_accounts
        assert yellow["amount_kzt"] == 700_000
        assert yellow["purpose"] == "Оплата транспортно-экспедиционных услуг по счёту № 318"

        # Q-003 (Red): Latin C lookalike, different BIN, BCC account owned by Вектор Трейд
        red = by_id["Q-003"]
        assert red["recipient_name"] == 'ТОО "Алатау \u0043наб"'
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
        assert (
            red["purpose"]
            == "Оплата по договору № 14-А за поставку оборудования, срочно, по новым реквизитам"
        )

        # Q-004 (Grey): first payment to a new valid supplier not in history
        grey = by_id["Q-004"]
        history_bins = {p["recipient_bin"] for p in payments}
        assert grey["recipient_bin"] not in history_bins
        assert registry[grey["recipient_bin"]] == grey["recipient_name"]
        assert grey["amount_kzt"] == 240_000
        assert grey["purpose"] == "Оплата за полиграфическую продукцию по счёту № 19"

        # Q-005..Q-010: new realistic scenarios
        assert by_id["Q-005"]["scenario"] == "green"
        assert by_id["Q-005"]["recipient_name"] == "ТОО «АстанаБетонСервис»"
        assert by_id["Q-006"]["scenario"] == "green"
        assert by_id["Q-006"]["recipient_name"] == "ТОО «ЕвразияКранМонтаж»"
        assert by_id["Q-007"]["scenario"] == "invalid"
        assert by_id["Q-008"]["scenario"] == "green"
        assert bin_kind(by_id["Q-008"]["recipient_bin"]) == "iin"
        assert by_id["Q-009"]["scenario"] == "red"
        assert "\u04b1" in by_id["Q-009"]["recipient_name"]  # Kazakh ұ
        assert by_id["Q-010"]["scenario"] == "yellow"
        assert bin_kind(by_id["Q-010"]["recipient_bin"]) == "iin"


class TestEvaluationDatasetAndMetrics:
    def test_eval_set_exists_is_deterministic_and_valid(self, tmp_path: Path) -> None:
        committed_path = DATA_DIR / "eval_set.json"
        assert committed_path.exists(), "Missing data/eval_set.json"

        regen_path = generate_eval_set(data_dir=DATA_DIR, output_path=tmp_path / "eval_set.json")
        assert regen_path.read_text(encoding="utf-8") == committed_path.read_text(encoding="utf-8")

        raw = json.loads(committed_path.read_text(encoding="utf-8"))
        cases = raw["cases"]
        assert raw["seed"] == 42
        assert len(cases) == 400
        assert sum(1 for c in cases if c["label"] == "legit") == 200
        assert sum(1 for c in cases if c["label"] == "attack") == 200

        kinds = {c["kind"] for c in cases}
        assert {
            "legit_same",
            "legit_new_supplier",
            "legit_account_change_confirmed",
            "legit_seasonal_amount",
            "legit_budget_payment",
            "attack_iik_swap_same_bin",
            "attack_lookalike_name",
            "attack_unicode_and_digit_evasion",
            "attack_bcc_other_owner",
            "attack_iin_dropper",
            "attack_amount_inflation",
            "attack_duplicate_invoice",
            "attack_structuring_72h",
            "attack_typo_free_valid_drop",
        }.issubset(kinds)
        for kind in kinds:
            assert kind in KIND_LABELS, f"Missing KIND_LABELS entry for {kind}"

        for case in cases:
            assert case["label"] in ("legit", "attack")
            assert isinstance(case["kind"], str) and case["kind"].strip()
            req = case["request"]
            assert bin_iin_checksum_ok(req["recipient_bin"])
            assert bin_kind(req["recipient_bin"]) is not None
            ok, err = iik_ok(req["recipient_iik"])
            assert ok, f"Invalid eval IIK in {case['id']}: {err}"
            assert bik_ok(req["recipient_bik"])
            assert bik_matches_iik(req["recipient_bik"], req["recipient_iik"])
            assert req["amount_kzt"] > 0

    def test_evaluate_dataset_returns_consistent_metrics_and_disclaimer(self) -> None:
        metrics = evaluate_dataset(DATA_DIR)
        assert metrics.seed == 42
        assert metrics.ruleset_version == RULESET_VERSION
        assert metrics.positive_verdicts == ["yellow", "red"]
        assert metrics.summary.total_cases == 400
        assert metrics.summary.total_legit == 200
        assert metrics.summary.total_attack == 200
        assert 0.0 <= metrics.summary.detection_rate <= 1.0
        assert 0.0 <= metrics.summary.stopped_rate <= 1.0
        assert 0.0 <= metrics.summary.escalated_rate <= 1.0
        assert metrics.summary.stopped_count + metrics.summary.escalated_count == metrics.confusion.tp
        assert 0.0 <= metrics.summary.false_positive_rate <= 1.0
        assert 0.0 <= metrics.summary.precision <= 1.0
        assert 0.0 <= metrics.summary.f1 <= 1.0
        assert 0.0 <= metrics.summary.accuracy <= 1.0
        assert metrics.confusion.tp + metrics.confusion.fn == 200
        assert metrics.confusion.fp + metrics.confusion.tn == 200
        assert metrics.verdict_by_label["legit"].invalid == 0
        assert metrics.verdict_by_label["attack"].invalid == 0
        assert sum(row.total for row in metrics.by_kind) == 400
        for row in metrics.by_kind:
            assert row.label_ru.strip() and row.label_kk.strip() and row.label_en.strip()
            assert row.label_text == row.label_ru
            if row.label == "attack":
                assert row.detection_rate is not None and row.false_positive_rate is None
            else:
                assert row.false_positive_rate is not None and row.detection_rate is None
        assert "синтетич" in metrics.disclaimer_ru.lower()
        assert "той же командой" in metrics.disclaimer_ru.lower()
        assert metrics.disclaimer_kk.strip() and metrics.disclaimer_en.strip()
        assert metrics.history_replay.total_payments == 150
        assert metrics.history_replay.verdicts.red == 0
        assert 0.0 <= metrics.history_replay.alert_rate <= 1.0

        report = format_metrics_report(metrics)
        assert "Confusion Table" in report
        assert "Stopped (red)" in report
        assert "Escalated (yellow)" in report
        assert "History Replay" in report
        assert "disclaimer_ru:" in report
        assert "attack_typo_free_valid_drop" in report
