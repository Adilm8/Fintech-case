"""End-to-end risk engine tests for all demo scenarios, invalid requisites, and scoring guards."""

from __future__ import annotations

import random
from datetime import timedelta

from app.risk.config import BCC_BANK_CODE, BCC_BIK, DEMO_TODAY
from app.risk.engine import aggregate_signals, check_payment
from app.schemas import CheckRequest, Evidence, Signal
from app.store import Store
from scripts.generate_data import generate_iik, generate_iin


def _request_from_queue(store: Store, scenario: str) -> CheckRequest:
    item = next(q for q in store.queue if q["scenario"] == scenario)
    return CheckRequest(
        payer_id=item["payer_id"],
        recipient_name=item["recipient_name"],
        recipient_bin=item["recipient_bin"],
        recipient_iik=item["recipient_iik"],
        recipient_bik=item["recipient_bik"],
        amount_kzt=item["amount_kzt"],
        purpose=item["purpose"],
    )


class TestDemoScenarios:
    def test_green_scenario(self) -> None:
        store = Store()
        result = check_payment(_request_from_queue(store, "green"), store)

        assert result.verdict == "green"
        assert result.score == 0
        assert result.headline_ru == "Всё как раньше"
        assert result.signals == []
        assert result.next_action.primary == "sign"
        assert result.history.payments_count >= 5
        assert result.history.median_amount_kzt == 1_350_000
        assert all(not diff.differs for diff in result.comparison)

    def test_yellow_scenario_and_trust_turns_green(self) -> None:
        store = Store()
        req = _request_from_queue(store, "yellow")
        result = check_payment(req, store)

        assert result.verdict == "yellow"
        assert result.score == 50  # iik_changed (35) + bank_changed (15)
        assert result.headline_ru == "Есть изменения"
        assert [s.rule_id for s in result.signals] == ["iik_changed", "bank_changed"]
        assert result.next_action.primary == "send_to_director"
        assert "sign" in result.next_action.secondary
        assert (
            result.next_action.text_ru
            == "Позвоните поставщику по номеру из договора, а не из письма с новыми реквизитами, и подтвердите счёт."
        )

        iik_diff = next(d for d in result.comparison if d.field == "iik")
        bank_diff = next(d for d in result.comparison if d.field == "bank")
        assert iik_diff.differs is True
        assert len(iik_diff.diff_positions) > 0
        assert bank_diff.differs is True

        # Trusting the account makes re-check green
        store.trust_account(req.recipient_bin, req.recipient_iik)
        rechecked = check_payment(req, store)
        assert rechecked.verdict == "green"
        assert rechecked.score == 0

    def test_red_scenario(self) -> None:
        store = Store()
        result = check_payment(_request_from_queue(store, "red"), store)

        assert result.verdict == "red"
        assert result.score == 100
        assert result.headline_ru == "Похоже на подмену"
        assert 1 <= len(result.signals) <= 4
        # Reasons are sorted descending by points
        points = [s.points for s in result.signals]
        assert points == sorted(points, reverse=True)

        rule_ids = [s.rule_id for s in result.signals]
        assert rule_ids[0] == "bcc_account_other_owner"
        assert "lookalike_supplier" in rule_ids
        assert "bin_name_mismatch" in rule_ids

        assert result.next_action.primary == "postpone"
        assert "send_to_director" in result.next_action.secondary
        assert "sign" not in result.next_action.secondary

        # Comparison table compares against the impersonated supplier ТОО «Алатау Снаб»
        name_diff = next(d for d in result.comparison if d.field == "name")
        iik_diff = next(d for d in result.comparison if d.field == "iik")
        amount_diff = next(d for d in result.comparison if d.field == "amount")
        assert name_diff.in_history == "ТОО «Алатау Снаб»"
        assert name_diff.differs is True
        assert iik_diff.differs is True
        assert len(iik_diff.diff_positions) > 0
        assert amount_diff.differs is True

    def test_grey_scenario(self) -> None:
        store = Store()
        result = check_payment(_request_from_queue(store, "grey"), store)

        assert result.verdict == "grey"
        assert result.score == 0
        assert result.headline_ru == "Нет истории для сравнения"
        assert [s.rule_id for s in result.signals] == ["first_payment"]
        assert result.history.payments_count == 0
        assert result.history.last_payment_date is None
        assert result.history.median_amount_kzt is None
        assert (
            result.next_action.text_ru
            == "Проверьте БИН поставщика в реестре и подтвердите реквизиты по телефону из договора."
        )
        assert all(d.in_history is None and not d.differs for d in result.comparison)


class TestInvalidPrechecks:
    def test_invalid_iik_checksum(self) -> None:
        store = Store()
        req = _request_from_queue(store, "green").model_copy(
            update={"recipient_iik": "KZ86125KZT5004100101"}
        )
        result = check_payment(req, store)

        assert result.verdict == "invalid"
        assert result.score == 0
        assert result.headline_ru == "Ошибка в реквизитах"
        assert result.signals[0].rule_id == "invalid_iik"
        assert result.next_action.text_ru == "Исправьте реквизиты: такого счёта не существует."
        assert result.next_action.primary == "postpone"

    def test_invalid_iik_cyrillic_lookalike(self) -> None:
        store = Store()
        req = _request_from_queue(store, "green").model_copy(
            update={"recipient_iik": "\u041aZ86125KZT5004100100"}
        )
        result = check_payment(req, store)

        assert result.verdict == "invalid"
        assert "кириллич" in result.signals[0].reason_ru.lower()

    def test_invalid_iik_bank_code_vs_bik_mismatch(self) -> None:
        store = Store()
        req = _request_from_queue(store, "green").model_copy(update={"recipient_bik": BCC_BIK})
        result = check_payment(req, store)

        assert result.verdict == "invalid"
        assert result.signals[0].rule_id == "iik_bank_code_vs_bik"


class TestScoringGuards:
    def test_single_signal_le_25_does_not_raise_colour(self) -> None:
        store = Store()
        # Case A: regular BCC supplier whose account was opened 10 days ago (only 1 signal = 25 pts)
        step_payment = next(
            p for p in store.history if p["recipient_name"] == "ТОО «СтепьЭнергоСервис»"
        )
        store.bcc_accounts[step_payment["recipient_iik"]]["opened_at"] = (
            DEMO_TODAY - timedelta(days=10)
        ).isoformat()
        req = CheckRequest(
            payer_id=step_payment["payer_id"],
            recipient_name=step_payment["recipient_name"],
            recipient_bin=step_payment["recipient_bin"],
            recipient_iik=step_payment["recipient_iik"],
            recipient_bik=step_payment["recipient_bik"],
            amount_kzt=540_000,
            purpose="Оплата по счёту",
        )
        result = check_payment(req, store)
        assert [s.rule_id for s in result.signals] == ["new_bcc_account"]
        assert result.score == 25
        assert result.verdict == "green"

        # Case B: first payment with entity_type_mismatch alone (25 pts) stays grey, not yellow
        rng = random.Random(505)
        grey_req = _request_from_queue(store, "grey").model_copy(
            update={"recipient_bin": generate_iin(rng)}
        )
        res_grey = check_payment(grey_req, store)
        assert res_grey.score == 25
        assert res_grey.verdict == "grey"

    def test_amplifiers_alone_are_capped_at_29(self) -> None:
        store = Store()
        # Regular supplier with BOTH amount_anomaly (25 amplifier) AND urgent_wording (10 amplifier)
        # Raw amplifier sum = 35, must be capped at 29 -> verdict remains green!
        req = _request_from_queue(store, "green").model_copy(
            update={
                "amount_kzt": 5_000_000,
                "purpose": "Оплата за материалы, срочно, по новым реквизитам",
            }
        )
        result = check_payment(req, store)
        rule_ids = {s.rule_id for s in result.signals}
        assert rule_ids == {"amount_anomaly", "urgent_wording"}
        assert result.score == 29
        assert result.verdict == "green"

    def test_primary_plus_amplifier_can_raise_to_yellow_and_red(self) -> None:
        # Direct aggregation check: entity_type_mismatch (25) + urgent_wording (10) = 35 -> yellow
        verdict, score = aggregate_signals(
            [
                Signal(
                    rule_id="entity_type_mismatch",
                    points=25,
                    severity="primary",
                    reason_ru="Mismatch",
                    evidence=Evidence(field="bin"),
                ),
                Signal(
                    rule_id="urgent_wording",
                    points=10,
                    severity="amplifier",
                    reason_ru="Urgent",
                    evidence=Evidence(field="purpose"),
                ),
            ]
        )
        assert verdict == "yellow"
        assert score == 35

        # First payment with lookalike (60) + urgent (10) = 70 -> red even without history
        verdict_red, score_red = aggregate_signals(
            [
                Signal(
                    rule_id="first_payment",
                    points=0,
                    severity="info",
                    reason_ru="First",
                    evidence=Evidence(field="bin"),
                ),
                Signal(
                    rule_id="lookalike_supplier",
                    points=60,
                    severity="primary",
                    reason_ru="Lookalike",
                    evidence=Evidence(field="name"),
                ),
                Signal(
                    rule_id="urgent_wording",
                    points=10,
                    severity="amplifier",
                    reason_ru="Urgent",
                    evidence=Evidence(field="purpose"),
                ),
            ]
        )
        assert verdict_red == "red"
        assert score_red == 70

    def test_unused_bcc_iik_for_new_supplier_no_false_block(self) -> None:
        store = Store()
        rng = random.Random(606)
        req = _request_from_queue(store, "grey").model_copy(
            update={
                "recipient_iik": generate_iik(rng, BCC_BANK_CODE),
                "recipient_bik": BCC_BIK,
            }
        )
        result = check_payment(req, store)
        assert result.verdict == "grey"
