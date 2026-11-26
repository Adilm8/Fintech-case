"""End-to-end risk engine tests for demo scenarios, Part 2 rules, invalid requisites, and guards."""

from __future__ import annotations

import random
from datetime import timedelta

from app.risk.config import BCC_BANK_CODE, BCC_BIK, DEMO_TODAY, RULESET_VERSION
from app.risk.engine import aggregate_signals, check_payment, localize_check_result
from app.risk.evaluation import run_history_replay
from app.risk.rules import compute_client_p90
from app.schemas import CheckRequest, Evidence, Signal, compute_request_sha256
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
        q2_req = _request_from_queue(store, "yellow")
        # At/above the supplier median (820_000) the same change escalates to red
        q2_result = check_payment(q2_req.model_copy(update={"amount_kzt": 820_000}), store)
        assert q2_result.verdict == "red"
        assert q2_result.score == 65  # iik_changed (35) + bank_changed (30)
        assert [s.rule_id for s in q2_result.signals] == ["iik_changed", "bank_changed"]

        # Below supplier median (700_000 < 820_000) -> yellow (50), eligible for trust
        req = q2_req.model_copy(update={"amount_kzt": 700_000})
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

        # Item 17: trusted account must NOT suppress differs=True on amount or name rows
        changed_amt_name = req.model_copy(
            update={"amount_kzt": 1_500_000, "recipient_name": "ТОО «КазЛогистик Новый»"}
        )
        rechecked_diff = check_payment(changed_amt_name, store)
        assert rechecked_diff.trusted is True
        for field_name in ("iik", "bik", "bank"):
            diff_row = next(d for d in rechecked_diff.comparison if d.field == field_name)
            assert diff_row.differs is False
        amt_row = next(d for d in rechecked_diff.comparison if d.field == "amount")
        name_row = next(d for d in rechecked_diff.comparison if d.field == "name")
        assert amt_row.differs is True
        assert name_row.differs is True

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
            CheckRequest(**{k: q9[k] for k in CheckRequest.model_fields if k in q9}),
            store,
        )
        assert res_q9.verdict == "red"
        assert res_q9.history.compared_with == "ТОО «НурМеталлПоставка»"
        assert {"lookalike_supplier", "bin_young"}.issubset({s.rule_id for s in res_q9.signals})

        # Q-010 legal entity with IIN triggers entity_type_mismatch -> yellow
        q10 = by_id["Q-010"]
        res_q10 = check_payment(
            CheckRequest(**{k: q10[k] for k in CheckRequest.model_fields if k in q10}),
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
        assert "ИИК" in result.next_action.text_ru
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

    def test_unknown_bcc_856_iik_returns_invalid(self) -> None:
        store = Store()
        rng = random.Random(606)
        req = _request_from_queue(store, "grey").model_copy(
            update={
                "recipient_iik": generate_iik(rng, BCC_BANK_CODE),
                "recipient_bik": BCC_BIK,
            }
        )
        result = check_payment(req, store)
        assert result.verdict == "invalid"
        assert result.signals[0].rule_id == "bcc_account_not_found"
        assert result.signals[0].reason_ru == "Счёт в BCC не найден."

    def test_step2_severity_escalations_budget_and_kbe_knp(self) -> None:
        store = Store()
        p90 = compute_client_p90(store)
        assert p90 is not None
        grey_req = _request_from_queue(store, "grey")
        green_req = _request_from_queue(store, "green")

        # Item 4a: known supplier >= 10x supplier p90 -> red
        res_sup_10x = check_payment(green_req.model_copy(update={"amount_kzt": 20_000_000}), store)
        assert res_sup_10x.verdict == "red" and res_sup_10x.score >= 65

        # Item 4b: new recipient > 3x client p90 -> yellow + send_to_director; > 10x -> red
        res_new_3x = check_payment(grey_req.model_copy(update={"amount_kzt": p90 * 3.5}), store)
        assert res_new_3x.verdict == "yellow"
        assert res_new_3x.next_action.primary == "send_to_director"

        res_new_10x = check_payment(grey_req.model_copy(update={"amount_kzt": p90 * 10.5}), store)
        assert res_new_10x.verdict == "red" and res_new_10x.score >= 65

        # Item 4c: first payment + urgent wording -> yellow (no 29 cap)
        res_first_urgent = check_payment(
            grey_req.model_copy(update={"purpose": "Оплата по счёту, срочно!"}), store
        )
        assert res_first_urgent.verdict == "yellow" and res_first_urgent.score >= 30

        # Item 6: budget treasury payments (KKMFKZ2A / 070 and GCVPKZ2A / 009) -> green
        rng = random.Random(607)
        for code, bik in (("070", "KKMFKZ2A"), ("009", "GCVPKZ2A")):
            budget_req = grey_req.model_copy(
                update={
                    "recipient_name": "ГУ «Управление государственных доходов»",
                    "recipient_iik": generate_iik(rng, code, prefix="000"),
                    "recipient_bik": bik,
                    "amount_kzt": 5_000_000,
                    "purpose": "Налог КПН, срочно сегодня",
                }
            )
            res_ru = check_payment(budget_req, store, lang="ru")
            res_kk = check_payment(budget_req, store, lang="kk")
            res_en = check_payment(budget_req, store, lang="en")
            assert res_ru.verdict == "green" and res_ru.score == 0
            assert res_ru.headline_ru == "Бюджетный платёж: реквизиты казначейства верны"
            assert res_kk.headline != res_ru.headline_ru
            assert res_en.headline != res_ru.headline_ru
            assert res_ru.next_action.primary == "sign"

            # Mismatched BIK on treasury IIK still returns invalid
            bad_budget = check_payment(
                budget_req.model_copy(update={"recipient_bik": "HSBKKZKX"}), store
            )
            assert bad_budget.verdict == "invalid"

        # Item 13: KBe=17 + IIN without "ТОО" in name -> yellow (40); unusual KNP -> amplifier
        kbe_req = grey_req.model_copy(
            update={
                "recipient_name": "СнабСтрой Центр",
                "recipient_bin": generate_iin(rng),
                "kbe": "17",
            }
        )
        res_kbe = check_payment(kbe_req, store)
        assert res_kbe.verdict == "yellow" and res_kbe.score == 40
        assert any(s.rule_id == "kbe_mismatch" for s in res_kbe.signals)

        res_knp = check_payment(green_req.model_copy(update={"knp": "859"}), store)
        assert res_knp.verdict == "green" and res_knp.score == 15
        assert any(s.rule_id == "knp_unusual" for s in res_knp.signals)

    def test_step3_next_action_bank_verified_duplicate_and_structuring(self) -> None:
        store = Store()
        green_req = _request_from_queue(store, "green")

        # Item 9: amount-only yellow and red get amount-specific next_action (ru/kk/en)
        amt_yellow = check_payment(green_req.model_copy(update={"amount_kzt": 5_000_000}), store, lang="ru")
        assert amt_yellow.verdict == "yellow"
        assert (
            amt_yellow.next_action.text_ru
            == "Сумма необычно большая для этого поставщика: проверьте счёт и договор."
        )
        amt_yellow_en = check_payment(green_req.model_copy(update={"amount_kzt": 5_000_000}), store, lang="en")
        assert "unusually large" in amt_yellow_en.next_action.text.lower()

        # Item 9: invalid names the specific bad field (BIN / IIK / BIK)
        bad_bin = check_payment(green_req.model_copy(update={"recipient_bin": "000000000000"}), store, lang="ru")
        assert bad_bin.verdict == "invalid" and "БИН/ИИН" in bad_bin.next_action.text_ru
        bad_bik = check_payment(green_req.model_copy(update={"recipient_bik": "XXXXKZKX"}), store, lang="en")
        assert bad_bik.verdict == "invalid" and "BIK" in bad_bik.next_action.text

        # Item 10: same BIN + new BCC IIK owned by this BIN -> green + bank-verified headline, no secret leak
        new_bcc_iik = generate_iik(random.Random(1011), BCC_BANK_CODE, prefix="KZT")
        store.bcc_accounts[new_bcc_iik] = {
            "owner_bin": green_req.recipient_bin,
            "owner_name": green_req.recipient_name,
            "opened_at": (DEMO_TODAY - timedelta(days=120)).isoformat(),
        }
        bcc_req = green_req.model_copy(update={"recipient_iik": new_bcc_iik, "recipient_bik": BCC_BIK})
        verified_res = check_payment(bcc_req, store, lang="ru")
        assert verified_res.verdict == "green" and verified_res.score == 0
        assert verified_res.headline_ru == "Счёт подтверждён банком: принадлежит этому поставщику"
        assert [s.rule_id for s in verified_res.signals] == ["bcc_owner_verified"]
        assert "analyst_details" not in verified_res.model_dump()

        # Item 10: amount signals STILL apply on bank-verified BCC account
        verified_big = check_payment(bcc_req.model_copy(update={"amount_kzt": 5_000_000}), store)
        assert verified_big.verdict == "yellow"
        assert any(s.rule_id == "amount_anomaly" for s in verified_big.signals)
        assert "Сумма необычно большая" in verified_big.next_action.text_ru

        # Item 8: duplicate invoice from history within 90 days -> yellow
        dup_res = check_payment(
            green_req.model_copy(update={"purpose": "Оплата по счёту № 113"}), store
        )
        assert dup_res.verdict == "yellow"
        assert any(s.rule_id == "duplicate_invoice" for s in dup_res.signals)
        assert "повторная оплата счёта" in dup_res.next_action.text_ru.lower()

        # Item 15: 3 sequential payments of ~40% median (540_000) -> 3rd triggers structuring_72h
        store_s = Store()
        chunk = green_req.model_copy(update={"amount_kzt": 540_000})
        r1 = check_payment(chunk.model_copy(update={"purpose": "Оплата сч. 911"}), store_s, record_in_memory=True)
        r2 = check_payment(chunk.model_copy(update={"purpose": "Оплата сч. 912"}), store_s, record_in_memory=True)
        r3 = check_payment(chunk.model_copy(update={"purpose": "Оплата сч. 913"}), store_s, record_in_memory=True)
        assert r1.signals == [] and r2.signals == []
        assert any(s.rule_id == "structuring_72h" for s in r3.signals)
        assert r3.score == 20 and r3.verdict == "green"

        # 3 sequential payments summing >= 3x median -> primary (yellow) with amount-only advice
        store_s2 = Store()
        big_chunk = green_req.model_copy(update={"amount_kzt": 1_500_000})
        check_payment(big_chunk.model_copy(update={"purpose": "Оплата сч. 921"}), store_s2, record_in_memory=True)
        check_payment(big_chunk.model_copy(update={"purpose": "Оплата сч. 922"}), store_s2, record_in_memory=True)
        r3_big = check_payment(big_chunk.model_copy(update={"purpose": "Оплата сч. 923"}), store_s2, record_in_memory=True)
        assert r3_big.verdict == "yellow"
        assert any(s.rule_id == "structuring_72h" and s.severity == "primary" for s in r3_big.signals)
        assert "Сумма необычно большая" in r3_big.next_action.text_ru

    def test_client_check_omits_analyst_details_and_analyst_flag_exposes_them(self) -> None:
        store = Store()
        red_req = _request_from_queue(store, "red")
        bcc_entry = store.bcc_accounts[red_req.recipient_iik]

        client_res = check_payment(red_req, store, lang="ru")
        assert client_res.analyst_details is None
        dumped_client = client_res.model_dump()
        assert "analyst_details" not in dumped_client
        assert "internal_analyst_details" not in dumped_client
        dumped_str = str(dumped_client)
        for secret in (
            bcc_entry["owner_name"],
            "Вектор Трейд",
            bcc_entry["owner_bin"],
            bcc_entry["opened_at"],
        ):
            assert secret not in dumped_str

        analyst_res = check_payment(red_req, store, lang="en", include_analyst_details=True)
        assert analyst_res.analyst_details is not None
        assert analyst_res.analyst_details.bcc_account is not None
        assert analyst_res.analyst_details.bcc_account.owner_name == bcc_entry["owner_name"]
        assert analyst_res.analyst_details.bcc_account.owner_bin == bcc_entry["owner_bin"]
        assert analyst_res.analyst_details.bcc_account.opened_at == bcc_entry["opened_at"]
        dumped_analyst = analyst_res.model_dump()
        assert "analyst_details" in dumped_analyst
        assert "internal_analyst_details" not in dumped_analyst

    def test_step4_dedup_evidence_relocalization_and_history_replay(self) -> None:
        store = Store()
        green_req = _request_from_queue(store, "green")

        # 1. Canonical sha256 is stable for identical request and changes on modified fields
        h1 = compute_request_sha256(green_req)
        h2 = compute_request_sha256(green_req.model_copy())
        h3 = compute_request_sha256(green_req.model_copy(update={"amount_kzt": green_req.amount_kzt + 1}))
        assert len(h1) == 64
        assert h1 == h2 and h1 != h3

        # Identical re-check with record_in_memory=True stays deduplicated
        res1 = check_payment(green_req, store, lang="ru", record_in_memory=True)
        res2 = check_payment(green_req, store, lang="kk", record_in_memory=True)
        res3 = check_payment(green_req, store, lang="en", record_in_memory=True)
        assert res1.ruleset_version == RULESET_VERSION
        assert res1.verdict == res2.verdict == res3.verdict == "green"
        assert len(store.recent_checks) == 1

        # 2. localize_check_result re-localizes evidence field_label, expected, actual
        q3_req = _request_from_queue(store, "red")
        red_ru = check_payment(q3_req, store, lang="ru")
        red_en = check_payment(q3_req, store, lang="en")
        reloc_en = localize_check_result(red_ru, "en")
        for s_reloc, s_direct in zip(reloc_en.signals, red_en.signals, strict=True):
            assert s_reloc.evidence.field_label == s_direct.evidence.field_label
            assert s_reloc.evidence.expected == s_direct.evidence.expected
            assert s_reloc.evidence.actual == s_direct.evidence.actual

        # 3. Chronological history_replay runs in isolation and leaves store untouched
        before_recent = list(store.recent_checks)
        replay = run_history_replay()
        assert replay.total_payments == 150
        assert (
            replay.verdicts.green
            + replay.verdicts.yellow
            + replay.verdicts.red
            + replay.verdicts.grey
            + replay.verdicts.invalid
            == 150
        )
        assert replay.verdicts.red == 0
        assert replay.alert_count == replay.verdicts.yellow + replay.verdicts.red
        assert store.recent_checks == before_recent
