"""End-to-end risk engine tests for demo scenarios, Part 2 rules, invalid requisites, and guards."""

from __future__ import annotations

import random
from datetime import timedelta

from app.risk.config import BCC_BANK_CODE, BCC_BIK, DEMO_TODAY
from app.risk.engine import aggregate_signals, check_payment
from app.risk.rules import compute_client_p90
from app.schemas import CheckRequest, Evidence, Signal
from app.store import Store
from app.validators.kz import iban_mod97, make_bin_iin, make_iik
from scripts.generate_data import generate_bin, generate_iik, generate_iin


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
        assert result.history.compared_with is None
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

        # Trusting the account makes re-check green with trusted metadata and comparison overrides
        trust_info = store.trust_account(
            req.recipient_bin,
            req.recipient_iik,
            payer_id=req.payer_id,
            director_comment="Подтвердили новые реквизиты по телефону",
        )
        rechecked = check_payment(req, store)
        assert rechecked.verdict == "green"
        assert rechecked.score == 0
        assert rechecked.trusted is True
        assert rechecked.trusted_info == trust_info
        assert rechecked.headline_ru == "Счёт подтверждён директором"
        assert [s.rule_id for s in rechecked.signals] == ["trusted_account"]
        assert "Новый счёт подтверждён директором" in rechecked.signals[0].reason_ru
        for field_name in ("iik", "bik", "bank"):
            diff_row = next(d for d in rechecked.comparison if d.field == field_name)
            assert diff_row.differs is False
            assert diff_row.diff_positions == []

    def test_red_scenario_returns_all_signals_sorted_and_lookalike_history(self) -> None:
        store = Store()
        result = check_payment(_request_from_queue(store, "red"), store)

        assert result.verdict == "red"
        assert result.score == 100
        assert result.headline_ru == "Похоже на подмену"

        # M9: ALL signals returned (not truncated to 4), sorted descending by points
        assert len(result.signals) >= 7
        points = [s.points for s in result.signals]
        assert points == sorted(points, reverse=True)

        rule_ids = [s.rule_id for s in result.signals]
        assert rule_ids[0] == "bcc_account_other_owner"
        assert {
            "bcc_account_other_owner",
            "lookalike_supplier",
            "bin_name_mismatch",
            "amount_anomaly",
            "mixed_script_name",
            "new_bcc_account",
            "urgent_wording",
        }.issubset(set(rule_ids))

        # M9: history uses the lookalike supplier's history with compared_with populated
        assert result.history.compared_with == "ТОО «Алатау Снаб»"
        assert result.history.payments_count == 13
        assert result.history.median_amount_kzt == 1_350_000
        assert result.history.last_payment_date is not None

        assert result.next_action.primary == "postpone"
        assert "send_to_director" in result.next_action.secondary
        assert "sign" not in result.next_action.secondary

        # Comparison table highlights mixed-script char position in name and IIK diffs
        name_diff = next(d for d in result.comparison if d.field == "name")
        iik_diff = next(d for d in result.comparison if d.field == "iik")
        amount_diff = next(d for d in result.comparison if d.field == "amount")
        assert name_diff.in_history == "ТОО «Алатау Снаб»"
        assert name_diff.differs is True
        assert name_diff.diff_positions == [12]
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
        assert result.history.compared_with is None
        assert result.next_action.primary == "sign"
        assert (
            result.next_action.text_ru
            == "Проверьте БИН поставщика в реестре и подтвердите реквизиты по телефону из договора."
        )
        assert all(d.in_history is None and not d.differs for d in result.comparison)

    def test_additional_queue_scenarios_q005_to_q010(self) -> None:
        store = Store()
        by_id = {item["id"]: item for item in store.queue}

        for qid in ("Q-005", "Q-006", "Q-007", "Q-008", "Q-009", "Q-010"):
            item = by_id[qid]
            req = CheckRequest(
                payer_id=item["payer_id"],
                recipient_name=item["recipient_name"],
                recipient_bin=item["recipient_bin"],
                recipient_iik=item["recipient_iik"],
                recipient_bik=item["recipient_bik"],
                amount_kzt=item["amount_kzt"],
                purpose=item["purpose"],
            )
            res = check_payment(req, store)
            assert res.verdict == item["scenario"], f"{qid}: {res.verdict} != {item['scenario']}"

        # Q-009 Kazakh-letter lookalike compares against ТОО «НурМеталлПоставка»
        q9 = by_id["Q-009"]
        res_q9 = check_payment(
            CheckRequest(**{k: q9[k] for k in CheckRequest.model_fields}),
            store,
        )
        assert res_q9.verdict == "red"
        assert res_q9.history.compared_with == "ТОО «НурМеталлПоставка»"
        assert {"lookalike_supplier", "bin_young"}.issubset({s.rule_id for s in res_q9.signals})

        # Q-010 legal entity with IIN triggers entity_type_mismatch -> yellow
        q10 = by_id["Q-010"]
        res_q10 = check_payment(
            CheckRequest(**{k: q10[k] for k in CheckRequest.model_fields}),
            store,
        )
        assert res_q10.verdict == "yellow"
        assert any(s.rule_id == "entity_type_mismatch" for s in res_q10.signals)


class TestPart2RulesInEngine:
    def test_h2_large_amount_raises_to_yellow_and_green_with_amplifier_changes_text(self) -> None:
        store = Store()
        # 3.7x median -> amount_anomaly primary 35 -> yellow
        big_req = _request_from_queue(store, "green").model_copy(update={"amount_kzt": 5_000_000})
        big_res = check_payment(big_req, store)
        assert big_res.verdict == "yellow"
        assert big_res.score == 35
        assert big_res.signals[0].rule_id == "amount_anomaly"
        assert big_res.signals[0].severity == "primary"

        # Green with an amplifier (urgent_wording 10) must NOT claim amount/everything matches
        urgent_green_req = _request_from_queue(store, "green").model_copy(
            update={"purpose": "Оплата по счёту № 214, срочно"}
        )
        urgent_res = check_payment(urgent_green_req, store)
        assert urgent_res.verdict == "green"
        assert urgent_res.score == 10
        assert urgent_res.headline_ru != "Всё как раньше"
        assert "сумма совпада" not in urgent_res.next_action.text_ru.lower()

    def test_h2_grey_above_client_p90_requires_send_to_director(self) -> None:
        store = Store()
        p90 = compute_client_p90(store)
        assert p90 is not None
        grey_big = _request_from_queue(store, "grey").model_copy(
            update={"amount_kzt": p90 + 1_000_000}
        )
        res = check_payment(grey_big, store)
        assert res.verdict == "grey"
        assert res.next_action.primary == "send_to_director"
        assert any(s.rule_id == "amount_anomaly" and s.severity == "amplifier" for s in res.signals)

    def test_h3_legal_entity_with_iin_raises_to_yellow_while_ie_bin_6_clean(self) -> None:
        store = Store()
        rng = random.Random(901)
        grey_req = _request_from_queue(store, "grey")

        # ТОО with IIN -> 40 pts -> yellow
        legal_iin_res = check_payment(
            grey_req.model_copy(update={"recipient_bin": generate_iin(rng)}),
            store,
        )
        assert legal_iin_res.verdict == "yellow"
        assert legal_iin_res.score == 40
        assert any(
            s.rule_id == "entity_type_mismatch" and s.points == 40 for s in legal_iin_res.signals
        )

        # ИП with joint-venture BIN (5th digit 6) -> no entity_type_mismatch -> grey (score 0)
        ie_bin_6 = generate_bin(rng, entity_digit=6)
        ie_res = check_payment(
            grey_req.model_copy(
                update={"recipient_name": "ИП Сарыарка", "recipient_bin": ie_bin_6}
            ),
            store,
        )
        assert ie_res.verdict == "grey"
        assert ie_res.score == 0
        assert all(s.rule_id != "entity_type_mismatch" for s in ie_res.signals)

    def test_mixed_script_alone_raises_yellow_with_name_diff_positions(self) -> None:
        store = Store()
        grey_req = _request_from_queue(store, "grey")
        # Replace Cyrillic 'а' with Latin 'a' inside "Сарыарка" (index 6)
        spoofed_name = "ТОО «С\u0061рыарка Принт»"
        res = check_payment(grey_req.model_copy(update={"recipient_name": spoofed_name}), store)
        assert res.verdict == "yellow"
        assert res.score == 30
        assert any(s.rule_id == "mixed_script_name" and s.points == 30 for s in res.signals)
        name_diff = next(d for d in res.comparison if d.field == "name")
        assert name_diff.differs is True
        assert name_diff.diff_positions == [6]

    def test_m3_bin_name_mismatch_with_known_pair_stays_green(self) -> None:
        store = Store()
        req = _request_from_queue(store, "green").model_copy(
            update={"recipient_name": "ТОО «Алатау Новое Название»"}
        )
        res = check_payment(req, store)
        assert res.verdict == "green"
        assert res.score == 0
        sig = next(s for s in res.signals if s.rule_id == "bin_name_mismatch")
        assert sig.severity == "info"
        assert sig.points == 0

    def test_m7_iik_belongs_to_other_counterparty_raises_yellow(self) -> None:
        store = Store()
        rng = random.Random(909)
        green_req = _request_from_queue(store, "green")
        other_req = green_req.model_copy(
            update={
                "recipient_name": "ТОО «Новая Компания»",
                "recipient_bin": generate_bin(rng),
                "amount_kzt": 500_000,
            }
        )
        res = check_payment(other_req, store)
        assert res.verdict == "yellow"
        assert res.score == 50
        sig = next(s for s in res.signals if s.rule_id == "iik_belongs_to_other_counterparty")
        assert sig.severity == "primary"
        assert sig.points == 50
        assert "ТОО «Алатау Снаб»" in sig.reason_ru


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

    def test_m4_unknown_or_non_digit_bank_code_in_iik_returns_invalid(self) -> None:
        store = Store()
        base = _request_from_queue(store, "green")

        # Unknown 3-digit code 999 with valid mod-97 -> invalid
        unknown_iik = make_iik("999", "KZT5004100100")
        res_unknown = check_payment(base.model_copy(update={"recipient_iik": unknown_iik}), store)
        assert res_unknown.verdict == "invalid"
        assert res_unknown.signals[0].rule_id == "invalid_iik"

        # Non-digit bank code ABC with valid mod-97 -> invalid
        rem = iban_mod97("KZ00ABCKZT5004100100")
        alpha_iik = f"KZ{98 - rem:02d}ABCKZT5004100100"
        res_alpha = check_payment(base.model_copy(update={"recipient_iik": alpha_iik}), store)
        assert res_alpha.verdict == "invalid"
        assert res_alpha.signals[0].rule_id == "invalid_iik"

    def test_l1_all_zero_and_invalid_month_bin_return_invalid(self) -> None:
        store = Store()
        base = _request_from_queue(store, "green")

        res_zeros = check_payment(base.model_copy(update={"recipient_bin": "000000000000"}), store)
        assert res_zeros.verdict == "invalid"
        assert res_zeros.signals[0].rule_id == "invalid_bin"

        res_month = check_payment(
            base.model_copy(update={"recipient_bin": make_bin_iin("20134000001")}), store
        )
        assert res_month.verdict == "invalid"
        assert res_month.signals[0].rule_id == "invalid_bin"


class TestRedScenarioRegressionVariants:
    """Item 14: verify the red scenario remains red in all three variants."""

    def test_variant_a_with_bcc_owner_block(self) -> None:
        store = Store()
        red_req = _request_from_queue(store, "red")
        res = check_payment(red_req, store)

        assert res.verdict == "red"
        assert res.score == 100
        assert any(
            s.rule_id == "bcc_account_other_owner" and s.severity == "block" for s in res.signals
        )

    def test_variant_b_fraudster_uses_own_vektor_trade_bin(self) -> None:
        store = Store()
        red_req = _request_from_queue(store, "red")
        vektor_bin = store.bcc_accounts[red_req.recipient_iik]["owner_bin"]

        variant_b = red_req.model_copy(update={"recipient_bin": vektor_bin})
        res = check_payment(variant_b, store)

        assert res.verdict == "red"
        assert res.score >= 65
        rule_ids = {s.rule_id for s in res.signals}
        assert "bcc_account_other_owner" not in rule_ids
        assert {"lookalike_supplier", "bin_name_mismatch", "amount_anomaly", "bin_young"}.issubset(
            rule_ids
        )

    def test_variant_c_iik_not_in_bcc_accounts_registry(self) -> None:
        store = Store()
        red_req = _request_from_queue(store, "red")
        rng = random.Random(1403)
        external_kaspi_iik = generate_iik(rng, "722", prefix="000")

        variant_c = red_req.model_copy(
            update={
                "recipient_iik": external_kaspi_iik,
                "recipient_bik": "CASPKZKA",
            }
        )
        res = check_payment(variant_c, store)

        assert res.verdict == "red"
        assert res.score >= 65
        rule_ids = {s.rule_id for s in res.signals}
        assert "bcc_account_other_owner" not in rule_ids
        assert "new_bcc_account" not in rule_ids
        assert {
            "lookalike_supplier",
            "bin_name_mismatch",
            "amount_anomaly",
            "mixed_script_name",
        }.issubset(rule_ids)


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

        # Case B: first payment with ИП + corporate BIN (5th digit 4) = 25 pts alone stays grey
        rng = random.Random(505)
        grey_req = _request_from_queue(store, "grey").model_copy(
            update={
                "recipient_name": "ИП Сарыарка",
                "recipient_bin": generate_bin(rng, entity_digit=4),
            }
        )
        res_grey = check_payment(grey_req, store)
        assert res_grey.score == 25
        assert res_grey.verdict == "grey"

    def test_amplifiers_alone_are_capped_at_29(self) -> None:
        store = Store()
        green_req = _request_from_queue(store, "green")
        # Give supplier a wide MAD so 2.2x is a 20-pt amplifier (ratio < 3.0 and mod_z < 10.0),
        # combined with urgent_wording (10-pt amplifier) -> raw 30 capped at 29 -> green.
        wide_amounts = [800_000, 900_000, 1_000_000, 1_100_000, 1_200_000]
        alatau_entries = [p for p in store.history if p["recipient_bin"] == green_req.recipient_bin]
        store.history = [p for p in store.history if p["recipient_bin"] != green_req.recipient_bin]
        for entry, amt in zip(alatau_entries[:5], wide_amounts, strict=True):
            store.history.append({**entry, "amount_kzt": amt})

        req = green_req.model_copy(
            update={
                "amount_kzt": 2_200_000,
                "purpose": "Оплата за материалы, срочно, по новым реквизитам",
            }
        )
        result = check_payment(req, store)
        rule_ids = {s.rule_id for s in result.signals}
        assert rule_ids == {"amount_anomaly", "urgent_wording"}
        assert result.score == 29
        assert result.verdict == "green"
        assert result.headline_ru != "Всё как раньше"

    def test_primary_plus_amplifier_can_raise_to_yellow_and_red(self) -> None:
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
