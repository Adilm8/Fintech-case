"""Unit tests for each pure risk rule: clean, attack, and edge cases."""

from __future__ import annotations

import random
from datetime import timedelta

import pytest

from app.risk.config import BCC_BANK_CODE, BCC_BIK, DEMO_TODAY, URGENT_PHRASES
from app.risk.rules import (
    compute_client_p90,
    rule_amount_anomaly,
    rule_bank_changed,
    rule_bcc_account_other_owner,
    rule_bik_format,
    rule_bin_format,
    rule_bin_name_mismatch,
    rule_bin_young,
    rule_entity_type_mismatch,
    rule_first_payment,
    rule_iik_bank_code_vs_bik,
    rule_iik_belongs_to_other_counterparty,
    rule_iik_changed,
    rule_iik_format,
    rule_lookalike_supplier,
    rule_mixed_script_name,
    rule_new_bcc_account,
    rule_trusted_account,
    rule_urgent_wording,
)
from app.schemas import CheckRequest
from app.store import Store
from app.validators.kz import iban_mod97, make_bin_iin, make_iik
from scripts.generate_data import generate_bin, generate_iik, generate_iin


def _make_store() -> Store:
    return Store()


def _green_request(store: Store) -> CheckRequest:
    item = next(q for q in store.queue if q["scenario"] == "green")
    return CheckRequest(
        payer_id=item["payer_id"],
        recipient_name=item["recipient_name"],
        recipient_bin=item["recipient_bin"],
        recipient_iik=item["recipient_iik"],
        recipient_bik=item["recipient_bik"],
        amount_kzt=item["amount_kzt"],
        purpose=item["purpose"],
    )


class TestPrecheckRules:
    def test_bin_format_clean_attack_edge(self) -> None:
        store = _make_store()
        req = _green_request(store)
        assert rule_bin_format(req) is None

        bad_checksum = req.model_copy(update={"recipient_bin": req.recipient_bin[:-1] + "0"})
        if bad_checksum.recipient_bin == req.recipient_bin:
            bad_checksum = req.model_copy(update={"recipient_bin": req.recipient_bin[:-1] + "1"})
        sig = rule_bin_format(bad_checksum)
        assert sig is not None and sig.rule_id == "invalid_bin" and sig.severity == "block"

        bad_kind = req.model_copy(update={"recipient_bin": "200180000001"})
        assert rule_bin_format(bad_kind) is not None

        # L1: reject all-zeros and invalid month even with valid checksum
        assert rule_bin_format(req.model_copy(update={"recipient_bin": "000000000000"})) is not None
        assert (
            rule_bin_format(req.model_copy(update={"recipient_bin": make_bin_iin("20134000001")}))
            is not None
        )

    def test_iik_format_clean_attack_edge(self) -> None:
        store = _make_store()
        req = _green_request(store)
        assert rule_iik_format(req, store) is None

        bad_mod = req.model_copy(update={"recipient_iik": "KZ86125KZT5004100101"})
        sig = rule_iik_format(bad_mod, store)
        assert sig is not None and sig.rule_id == "invalid_iik"

        cyrillic = req.model_copy(update={"recipient_iik": "\u041aZ86125KZT5004100100"})
        sig_cyr = rule_iik_format(cyrillic, store)
        assert sig_cyr is not None and "кириллич" in sig_cyr.reason_ru.lower()

        # M4: unknown 3-digit bank code and non-digit bank code (even with valid mod-97) -> invalid
        unknown_bank_iik = make_iik("999", "KZT5004100100")
        sig_unknown = rule_iik_format(
            req.model_copy(update={"recipient_iik": unknown_bank_iik}), store
        )
        assert sig_unknown is not None and sig_unknown.rule_id == "invalid_iik"

        rem = iban_mod97("KZ00ABCKZT5004100100")
        alpha_bank_iik = f"KZ{98 - rem:02d}ABCKZT5004100100"
        sig_alpha = rule_iik_format(req.model_copy(update={"recipient_iik": alpha_bank_iik}), store)
        assert sig_alpha is not None and sig_alpha.rule_id == "invalid_iik"

    def test_bik_format_clean_attack_edge(self) -> None:
        store = _make_store()
        req = _green_request(store)
        assert rule_bik_format(req, store) is None

        unknown = req.model_copy(update={"recipient_bik": "XXXXKZKX"})
        sig = rule_bik_format(unknown, store)
        assert sig is not None and sig.rule_id == "invalid_bik"

        short = req.model_copy(update={"recipient_bik": "KCJB"})
        assert rule_bik_format(short, store) is not None

    def test_iik_bank_code_vs_bik_clean_attack_edge(self) -> None:
        store = _make_store()
        req = _green_request(store)
        assert rule_iik_bank_code_vs_bik(req, store) is None

        mismatch = req.model_copy(update={"recipient_bik": BCC_BIK})
        sig = rule_iik_bank_code_vs_bik(mismatch, store)
        assert sig is not None and sig.rule_id == "iik_bank_code_vs_bik"

        malformed = req.model_copy(update={"recipient_iik": "BAD"})
        assert rule_iik_bank_code_vs_bik(malformed, store) is None


class TestRiskRules:
    def test_bcc_account_other_owner_clean_attack_edge(self) -> None:
        store = _make_store()
        step_payment = next(
            p for p in store.history if p["recipient_name"] == "ТОО «СтепьЭнергоСервис»"
        )
        clean_req = CheckRequest(
            payer_id=step_payment["payer_id"],
            recipient_name=step_payment["recipient_name"],
            recipient_bin=step_payment["recipient_bin"],
            recipient_iik=step_payment["recipient_iik"],
            recipient_bik=step_payment["recipient_bik"],
            amount_kzt=540_000,
            purpose="Оплата",
        )
        assert rule_bcc_account_other_owner(clean_req, store) is None

        red_item = next(q for q in store.queue if q["scenario"] == "red")
        red_req = CheckRequest(**{k: red_item[k] for k in CheckRequest.model_fields})
        sig = rule_bcc_account_other_owner(red_req, store)
        assert sig is not None
        assert sig.rule_id == "bcc_account_other_owner"
        assert sig.severity == "block"
        assert "Вектор Трейд" in sig.reason_ru

        assert rule_bcc_account_other_owner(_green_request(store), store) is None
        rng = random.Random(101)
        unknown_bcc_iik = generate_iik(rng, BCC_BANK_CODE)
        edge_req = clean_req.model_copy(update={"recipient_iik": unknown_bcc_iik})
        assert rule_bcc_account_other_owner(edge_req, store) is None

    def test_lookalike_supplier_clean_attack_m1_h4_and_exact_short(self) -> None:
        store = _make_store()
        assert rule_lookalike_supplier(_green_request(store), store) is None

        grey_item = next(q for q in store.queue if q["scenario"] == "grey")
        grey_req = CheckRequest(**{k: grey_item[k] for k in CheckRequest.model_fields})
        assert rule_lookalike_supplier(grey_req, store) is None

        # Attack 1: Latin C lookalike with different BIN
        red_item = next(q for q in store.queue if q["scenario"] == "red")
        red_req = CheckRequest(**{k: red_item[k] for k in CheckRequest.model_fields})
        sig = rule_lookalike_supplier(red_req, store)
        assert sig is not None
        assert sig.rule_id == "lookalike_supplier"
        assert sig.points == 60
        assert sig.severity == "primary"

        # Attack 2 (H4): all normalized tokens of known supplier (len >= 8) contained in new name
        h4_req = red_req.model_copy(
            update={"recipient_name": "ТОО «Алатау Снаб Трейдинг Казахстан»"}
        )
        sig_h4 = rule_lookalike_supplier(h4_req, store)
        assert sig_h4 is not None and sig_h4.rule_id == "lookalike_supplier"

        # Attack 3 (M2): exact match after folding triggers regardless of short length (< 8)
        rng = random.Random(111)
        short_hist_bin = generate_bin(rng)
        short_attack_bin = generate_bin(rng)
        store.history.append(
            {
                "id": "HIST-SHORT",
                "payer_id": store.default_payer_id,
                "paid_at": "2026-03-01",
                "recipient_name": "ТОО «АВС»",
                "recipient_bin": short_hist_bin,
                "recipient_iik": generate_iik(rng, "601", prefix="000"),
                "recipient_bik": "HSBKKZKX",
                "amount_kzt": 100_000,
                "purpose": "Оплата",
            }
        )
        short_exact_req = red_req.model_copy(
            update={
                "recipient_name": "Т.О.О. «ABC»",  # Latin homoglyphs -> exact match "авс"
                "recipient_bin": short_attack_bin,
            }
        )
        sig_short = rule_lookalike_supplier(short_exact_req, store)
        assert sig_short is not None and sig_short.rule_id == "lookalike_supplier"

        # Short supplier name (< 8 chars) must NOT trigger H4 on extra words
        short_extra_req = red_req.model_copy(
            update={
                "recipient_name": "ТОО «АВС Глобал Строй Инвест»",
                "recipient_bin": short_attack_bin,
            }
        )
        assert rule_lookalike_supplier(short_extra_req, store) is None

        # M1: skipped if recipient_bin already has its own payment history
        kazlog_item = next(q for q in store.queue if q["scenario"] == "yellow")
        kazlog_own_hist = red_req.model_copy(update={"recipient_bin": kazlog_item["recipient_bin"]})
        assert rule_lookalike_supplier(kazlog_own_hist, store) is None

        # M1: skipped if recipient_bin is trusted for this payer
        store.trust_account(
            red_req.recipient_bin,
            red_req.recipient_iik,
            payer_id=red_req.payer_id,
            director_comment="Подтверждено директором",
        )
        assert rule_lookalike_supplier(red_req, store) is None

        # Edge: similarity below threshold (< 85) and not containing all supplier tokens
        store2 = _make_store()
        edge_req = red_req.model_copy(update={"recipient_name": "ТОО «Алатау Инжиниринг Плюс»"})
        assert rule_lookalike_supplier(edge_req, store2) is None

    def test_mixed_script_name_rule(self) -> None:
        store = _make_store()
        assert rule_mixed_script_name(_green_request(store)) is None

        # Separate Latin legal form LLP is NOT mixed-script inside a Cyrillic word
        assert (
            rule_mixed_script_name(
                _green_request(store).model_copy(update={"recipient_name": 'LLP "Алатау Снаб"'})
            )
            is None
        )

        # Red scenario has Latin C inside Cyrillic "Cнаб" -> primary 30
        red_item = next(q for q in store.queue if q["scenario"] == "red")
        red_req = CheckRequest(**{k: red_item[k] for k in CheckRequest.model_fields})
        sig = rule_mixed_script_name(red_req)
        assert sig is not None
        assert sig.rule_id == "mixed_script_name"
        assert sig.severity == "primary"
        assert sig.points == 30

    def test_bin_name_mismatch_clean_attack_and_m3_history_downgrade(self) -> None:
        store = _make_store()
        assert rule_bin_name_mismatch(_green_request(store), store) is None

        red_item = next(q for q in store.queue if q["scenario"] == "red")
        red_req = CheckRequest(**{k: red_item[k] for k in CheckRequest.model_fields})
        sig = rule_bin_name_mismatch(red_req, store)
        assert sig is not None
        assert sig.rule_id == "bin_name_mismatch"
        assert sig.points == 50
        assert sig.severity == "primary"
        assert "Атлант Ресурс" in sig.reason_ru

        # M3: when exact (BIN, IIK) pair is already in history, downgrade to info (0 pts)
        green_req = _green_request(store)
        renamed_req = green_req.model_copy(update={"recipient_name": "ТОО «Алатау Новый Бренд»"})
        sig_m3 = rule_bin_name_mismatch(renamed_req, store)
        assert sig_m3 is not None
        assert sig_m3.rule_id == "bin_name_mismatch"
        assert sig_m3.severity == "info"
        assert sig_m3.points == 0

        # Edge: BIN absent from synthetic registry -> None
        rng = random.Random(202)
        unlisted_bin = generate_bin(rng)
        edge_req = red_req.model_copy(update={"recipient_bin": unlisted_bin})
        assert rule_bin_name_mismatch(edge_req, store) is None

    def test_iik_belongs_to_other_counterparty_history_and_trusted(self) -> None:
        store = _make_store()
        green_req = _green_request(store)
        assert rule_iik_belongs_to_other_counterparty(green_req, store) is None

        # Attack 1 (history): new/other BIN reusing Алатау Снаб's historical IIK -> primary 50
        rng = random.Random(808)
        other_bin = generate_bin(rng)
        reused_hist_req = green_req.model_copy(
            update={"recipient_name": "ТОО «Другой Поставщик»", "recipient_bin": other_bin}
        )
        sig_hist = rule_iik_belongs_to_other_counterparty(reused_hist_req, store)
        assert sig_hist is not None
        assert sig_hist.rule_id == "iik_belongs_to_other_counterparty"
        assert sig_hist.severity == "primary"
        assert sig_hist.points == 50
        assert "Этот счёт раньше принадлежал вашему поставщику ТОО «Алатау Снаб»." == (
            sig_hist.reason_ru
        )

        # Attack 2 (trusted): IIK was trusted under КазЛогистик Групп, now sent with another BIN
        yellow_item = next(q for q in store.queue if q["scenario"] == "yellow")
        store.trust_account(
            yellow_item["recipient_bin"],
            yellow_item["recipient_iik"],
            payer_id=yellow_item["payer_id"],
            director_comment="Подтверждён директором",
        )
        reused_trusted_req = CheckRequest(
            payer_id=yellow_item["payer_id"],
            recipient_name="ТОО «Другой Поставщик»",
            recipient_bin=other_bin,
            recipient_iik=yellow_item["recipient_iik"],
            recipient_bik=yellow_item["recipient_bik"],
            amount_kzt=500_000,
            purpose="Оплата",
        )
        sig_trusted = rule_iik_belongs_to_other_counterparty(reused_trusted_req, store)
        assert sig_trusted is not None
        assert sig_trusted.rule_id == "iik_belongs_to_other_counterparty"
        assert sig_trusted.points == 50
        assert "ТОО «КазЛогистик Групп»" in sig_trusted.reason_ru

    def test_iik_changed_and_bank_changed_clean_attack_edge(self) -> None:
        store = _make_store()
        green_req = _green_request(store)
        assert rule_iik_changed(green_req, store) is None
        assert rule_bank_changed(green_req, store) is None

        yellow_item = next(q for q in store.queue if q["scenario"] == "yellow")
        yellow_req = CheckRequest(**{k: yellow_item[k] for k in CheckRequest.model_fields})
        sig_iik = rule_iik_changed(yellow_req, store)
        sig_bank = rule_bank_changed(yellow_req, store)
        assert sig_iik is not None and sig_iik.points == 35 and sig_iik.severity == "primary"
        assert sig_bank is not None and sig_bank.points == 15 and sig_bank.severity == "amplifier"

        rng = random.Random(303)
        new_halyk_iik = generate_iik(rng, "601", prefix="000")
        same_bank_req = green_req.model_copy(update={"recipient_iik": new_halyk_iik})
        assert rule_iik_changed(same_bank_req, store) is not None
        assert rule_bank_changed(same_bank_req, store) is None

        store.trust_account(
            yellow_req.recipient_bin,
            yellow_req.recipient_iik,
            payer_id=yellow_req.payer_id,
            director_comment="Подтвердил реквизиты по телефону",
        )
        assert rule_iik_changed(yellow_req, store) is None
        assert rule_bank_changed(yellow_req, store) is None
        sig_trusted = rule_trusted_account(yellow_req, store)
        assert sig_trusted is not None
        assert sig_trusted.rule_id == "trusted_account"
        assert sig_trusted.severity == "info"
        assert "подтверждён директором" in sig_trusted.reason_ru.lower()

        other_payer_req = yellow_req.model_copy(update={"payer_id": "client-other"})
        assert rule_trusted_account(other_payer_req, store) is None

        grey_item = next(q for q in store.queue if q["scenario"] == "grey")
        grey_req = CheckRequest(**{k: grey_item[k] for k in CheckRequest.model_fields})
        assert rule_iik_changed(grey_req, store) is None
        assert rule_bank_changed(grey_req, store) is None

    def test_entity_type_mismatch_h3_weights_and_ie_bin_6(self) -> None:
        store = _make_store()
        req = _green_request(store)
        rng = random.Random(404)
        valid_iin = generate_iin(rng)
        joint_ie_bin_6 = generate_bin(rng, entity_digit=6)

        # Clean: ТОО with BIN, ИП with IIN, ИП with joint-venture BIN (5th digit 6)
        assert rule_entity_type_mismatch(req) is None
        assert (
            rule_entity_type_mismatch(
                req.model_copy(update={"recipient_name": "ИП Сериков", "recipient_bin": valid_iin})
            )
            is None
        )
        assert (
            rule_entity_type_mismatch(
                req.model_copy(
                    update={"recipient_name": "ИП Сериков", "recipient_bin": joint_ie_bin_6}
                )
            )
            is None
        )

        # Attack (H3): ТОО/АО/LLP/ЖШС with IIN -> primary 40
        for legal_name in (
            "ТОО «Алатау Снаб»",
            "АО «КазТранс»",
            'LLP "Alatau"',
            "ЖШС «Алатау»",
            "Товарищество с ограниченной ответственностью «Алатау»",
        ):
            sig_legal_iin = rule_entity_type_mismatch(
                req.model_copy(update={"recipient_name": legal_name, "recipient_bin": valid_iin})
            )
            assert sig_legal_iin is not None
            assert sig_legal_iin.severity == "primary"
            assert sig_legal_iin.points == 40

        # Attack: ИП with corporate BIN (5th digit 4) -> remains 25
        sig_ip_bin = rule_entity_type_mismatch(
            req.model_copy(update={"recipient_name": "ИП Ахметов"})
        )
        assert sig_ip_bin is not None and sig_ip_bin.points == 25

        # Edge: no legal form in name -> None
        assert (
            rule_entity_type_mismatch(
                req.model_copy(update={"recipient_name": "Алатау Снаб", "recipient_bin": valid_iin})
            )
            is None
        )

    def test_new_bcc_account_clean_attack_edge(self) -> None:
        store = _make_store()
        step_payment = next(
            p for p in store.history if p["recipient_name"] == "ТОО «СтепьЭнергоСервис»"
        )
        old_req = CheckRequest(
            payer_id=step_payment["payer_id"],
            recipient_name=step_payment["recipient_name"],
            recipient_bin=step_payment["recipient_bin"],
            recipient_iik=step_payment["recipient_iik"],
            recipient_bik=step_payment["recipient_bik"],
            amount_kzt=540_000,
            purpose="Оплата",
        )
        assert rule_new_bcc_account(old_req, store) is None

        red_item = next(q for q in store.queue if q["scenario"] == "red")
        red_req = CheckRequest(**{k: red_item[k] for k in CheckRequest.model_fields})
        sig = rule_new_bcc_account(red_req, store, today=DEMO_TODAY)
        assert sig is not None and sig.rule_id == "new_bcc_account" and sig.points == 25

        opened = DEMO_TODAY - timedelta(days=12)
        exact_30_today = opened + timedelta(days=30)
        assert rule_new_bcc_account(red_req, store, today=exact_30_today) is None
        assert rule_new_bcc_account(_green_request(store), store) is None

    def test_amount_anomaly_h2_primary_amplifier_and_first_payment_p90(self) -> None:
        store = _make_store()
        green_req = _green_request(store)

        # Clean: usual amount ~1 360 000 vs median 1 350 000
        assert rule_amount_anomaly(green_req, store) is None

        # Attack (H2): ratio >= 3 or robust z >= 10 -> primary 35
        huge_req = green_req.model_copy(update={"amount_kzt": 4_900_000})
        sig = rule_amount_anomaly(huge_req, store)
        assert sig is not None
        assert sig.rule_id == "amount_anomaly"
        assert sig.severity == "primary"
        assert sig.points == 35

        # Moderate outlier (ratio < 3, 3.5 <= robust z < 10) -> amplifier 10..20
        store_wide = _make_store()
        wide_amounts = [800_000, 900_000, 1_000_000, 1_100_000, 1_200_000]
        alatau_entries = [
            p for p in store_wide.history if p["recipient_bin"] == green_req.recipient_bin
        ]
        store_wide.history = [
            p for p in store_wide.history if p["recipient_bin"] != green_req.recipient_bin
        ]
        for entry, amt in zip(alatau_entries[:5], wide_amounts, strict=True):
            store_wide.history.append({**entry, "amount_kzt": amt})
        mod_sig = rule_amount_anomaly(
            green_req.model_copy(update={"amount_kzt": 2_100_000}), store_wide
        )
        assert mod_sig is not None
        assert mod_sig.severity == "amplifier"
        assert 10 <= mod_sig.points <= 20

        # Edge 1: 1..4 past payments -> None (insufficient supplier history)
        store.history = [
            p for p in store.history if p["recipient_bin"] != green_req.recipient_bin
        ] + store.get_supplier_history(green_req.recipient_bin)[:4]
        assert rule_amount_anomaly(huge_req, store) is None

        # Edge 2: zero MAD (identical past payments): 2.6x -> amplifier 20, 3.5x -> primary 35
        store2 = _make_store()
        for p in store2.history:
            if p["recipient_bin"] == green_req.recipient_bin:
                p["amount_kzt"] = 1_000_000
        assert (
            rule_amount_anomaly(green_req.model_copy(update={"amount_kzt": 1_000_000}), store2)
            is None
        )
        sig_zero_mad_mid = rule_amount_anomaly(
            green_req.model_copy(update={"amount_kzt": 2_600_000}), store2
        )
        assert sig_zero_mad_mid is not None
        assert sig_zero_mad_mid.severity == "amplifier"
        assert sig_zero_mad_mid.points == 20

        sig_zero_mad_high = rule_amount_anomaly(
            green_req.model_copy(update={"amount_kzt": 3_500_000}), store2
        )
        assert sig_zero_mad_high is not None
        assert sig_zero_mad_high.severity == "primary"
        assert sig_zero_mad_high.points == 35

        # First payment (H2): amplifier relative to client p90
        store3 = _make_store()
        p90 = compute_client_p90(store3)
        assert p90 is not None and p90 > 2_000_000
        grey_item = next(q for q in store3.queue if q["scenario"] == "grey")
        grey_req = CheckRequest(**{k: grey_item[k] for k in CheckRequest.model_fields})
        assert rule_amount_anomaly(grey_req, store3) is None

        big_first = grey_req.model_copy(update={"amount_kzt": p90 + 500_000})
        sig_p90 = rule_amount_anomaly(big_first, store3)
        assert sig_p90 is not None
        assert sig_p90.rule_id == "amount_anomaly"
        assert sig_p90.severity == "amplifier"
        assert 10 <= sig_p90.points <= 20

    def test_first_payment_clean_and_new(self) -> None:
        store = _make_store()
        assert rule_first_payment(_green_request(store), store) is None

        grey_item = next(q for q in store.queue if q["scenario"] == "grey")
        grey_req = CheckRequest(**{k: grey_item[k] for k in CheckRequest.model_fields})
        sig = rule_first_payment(grey_req, store)
        assert sig is not None and sig.rule_id == "first_payment" and sig.severity == "info"
        assert sig.points == 0

    def test_bin_young_l1_clean_attack_and_boundary(self) -> None:
        store = _make_store()
        req = _green_request(store)
        # Established supplier (2016) -> None
        assert rule_bin_young(req, today=DEMO_TODAY) is None

        # Young company registered 5 months before DEMO_TODAY (2025-11 vs 2026-04) -> amplifier 15
        young_bin = make_bin_iin("25114000001")
        sig = rule_bin_young(req.model_copy(update={"recipient_bin": young_bin}), today=DEMO_TODAY)
        assert sig is not None
        assert sig.rule_id == "bin_young"
        assert sig.severity == "amplifier"
        assert sig.points == 15

        # Boundary: 11 months ago (2025-05) triggers; exactly 12 months ago (2025-04) does not
        bin_11m = make_bin_iin("25054000001")
        bin_12m = make_bin_iin("25044000001")
        assert (
            rule_bin_young(req.model_copy(update={"recipient_bin": bin_11m}), today=DEMO_TODAY)
            is not None
        )
        assert (
            rule_bin_young(req.model_copy(update={"recipient_bin": bin_12m}), today=DEMO_TODAY)
            is None
        )

        # Edge: IIN returns None (not a BIN)
        rng = random.Random(1201)
        assert (
            rule_bin_young(
                req.model_copy(update={"recipient_bin": generate_iin(rng)}), today=DEMO_TODAY
            )
            is None
        )

    @pytest.mark.parametrize("phrase", URGENT_PHRASES)
    def test_urgent_wording_detects_all_phrases(self, phrase: str) -> None:
        store = _make_store()
        req = _green_request(store)
        assert rule_urgent_wording(req) is None

        attack = req.model_copy(update={"purpose": f"Оплата по счёту, {phrase.upper()}!"})
        sig = rule_urgent_wording(attack)
        assert sig is not None
        assert sig.rule_id == "urgent_wording"
        assert sig.points == 10
        assert sig.severity == "amplifier"

    def test_urgent_wording_l2_word_boundaries_and_homoglyphs(self) -> None:
        store = _make_store()
        req = _green_request(store)

        # Must NOT fire on words containing "срочно" as a substring
        for safe_purpose in (
            "Оплата по договору, несрочно",
            "Досрочно погашение аренды по счёту № 5",
        ):
            assert rule_urgent_wording(req.model_copy(update={"purpose": safe_purpose})) is None

        # Must fire on homoglyphs, ё/е variants, Kazakh folded spelling, and Cf invisibles
        for spoofed_purpose in (
            "Оплата по счёту, cрoчн0!",  # Latin c, o and digit 0
            "Оплата на новый счет",  # е instead of ё
            "Төлем с\u200bмена реквизитов",  # Cf invisible char
            "Төлем шугыл түрде",  # Kazakh folded шұғыл
            "Жедел төлем № 14",
        ):
            sig = rule_urgent_wording(req.model_copy(update={"purpose": spoofed_purpose}))
            assert sig is not None and sig.rule_id == "urgent_wording"
