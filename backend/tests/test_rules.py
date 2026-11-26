"""Unit tests for each pure risk rule: clean, attack, and edge cases."""

from __future__ import annotations

import random
from datetime import timedelta

import pytest

from app.risk.config import BCC_BANK_CODE, BCC_BIK, DEMO_TODAY, URGENT_PHRASES
from app.risk.rules import (
    rule_amount_anomaly,
    rule_bank_changed,
    rule_bcc_account_other_owner,
    rule_bik_format,
    rule_bin_format,
    rule_bin_name_mismatch,
    rule_entity_type_mismatch,
    rule_first_payment,
    rule_iik_bank_code_vs_bik,
    rule_iik_changed,
    rule_iik_format,
    rule_lookalike_supplier,
    rule_new_bcc_account,
    rule_urgent_wording,
)
from app.schemas import CheckRequest
from app.store import Store
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

        # Edge: valid checksum is impossible / 5th digit 8 is not a valid BIN or IIN
        bad_kind = req.model_copy(update={"recipient_bin": "200180000001"})
        assert rule_bin_format(bad_kind) is not None

    def test_iik_format_clean_attack_edge(self) -> None:
        store = _make_store()
        req = _green_request(store)
        assert rule_iik_format(req) is None

        # Attack/typo: bad mod-97 checksum
        bad_mod = req.model_copy(update={"recipient_iik": "KZ86125KZT5004100101"})
        sig = rule_iik_format(bad_mod)
        assert sig is not None and sig.rule_id == "invalid_iik"

        # Edge: Cyrillic lookalike letter produces clear Russian message
        cyrillic = req.model_copy(update={"recipient_iik": "\u041aZ86125KZT5004100100"})
        sig_cyr = rule_iik_format(cyrillic)
        assert sig_cyr is not None and "кириллич" in sig_cyr.reason_ru.lower()

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
        req = _green_request(store)  # Halyk 601 / HSBKKZKX
        assert rule_iik_bank_code_vs_bik(req, store) is None

        # Mismatch: Halyk IIK with BCC BIK
        mismatch = req.model_copy(update={"recipient_bik": BCC_BIK})
        sig = rule_iik_bank_code_vs_bik(mismatch, store)
        assert sig is not None and sig.rule_id == "iik_bank_code_vs_bik"

        # Edge: malformed IIK does not double-fire bank_code_vs_bik
        malformed = req.model_copy(update={"recipient_iik": "BAD"})
        assert rule_iik_bank_code_vs_bik(malformed, store) is None


class TestRiskRules:
    def test_bcc_account_other_owner_clean_attack_edge(self) -> None:
        store = _make_store()
        # Clean: BCC supplier paying to its own BCC account
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

        # Attack: red scenario BCC account owned by Вектор Трейд
        red_item = next(q for q in store.queue if q["scenario"] == "red")
        red_req = CheckRequest(**{k: red_item[k] for k in CheckRequest.model_fields})
        sig = rule_bcc_account_other_owner(red_req, store)
        assert sig is not None
        assert sig.rule_id == "bcc_account_other_owner"
        assert sig.severity == "block"
        assert "Вектор Трейд" in sig.reason_ru

        # Edge: non-BCC account and unknown BCC IIK return None
        assert rule_bcc_account_other_owner(_green_request(store), store) is None
        rng = random.Random(101)
        unknown_bcc_iik = generate_iik(rng, BCC_BANK_CODE)
        edge_req = clean_req.model_copy(update={"recipient_iik": unknown_bcc_iik})
        assert rule_bcc_account_other_owner(edge_req, store) is None

    def test_lookalike_supplier_clean_attack_edge(self) -> None:
        store = _make_store()
        # Clean: same supplier with same BIN
        assert rule_lookalike_supplier(_green_request(store), store) is None

        # Clean: unrelated new supplier (grey)
        grey_item = next(q for q in store.queue if q["scenario"] == "grey")
        grey_req = CheckRequest(**{k: grey_item[k] for k in CheckRequest.model_fields})
        assert rule_lookalike_supplier(grey_req, store) is None

        # Attack: Latin C lookalike with different BIN
        red_item = next(q for q in store.queue if q["scenario"] == "red")
        red_req = CheckRequest(**{k: red_item[k] for k in CheckRequest.model_fields})
        sig = rule_lookalike_supplier(red_req, store)
        assert sig is not None
        assert sig.rule_id == "lookalike_supplier"
        assert sig.points == 60
        assert sig.severity == "primary"

        # Edge: similarity below threshold (< 85) with different BIN
        edge_req = red_req.model_copy(update={"recipient_name": "ТОО «Алатау Инжиниринг Плюс»"})
        assert rule_lookalike_supplier(edge_req, store) is None

    def test_bin_name_mismatch_clean_attack_edge(self) -> None:
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

        # Edge: BIN absent from synthetic registry -> None
        rng = random.Random(202)
        unlisted_bin = generate_bin(rng)
        edge_req = red_req.model_copy(update={"recipient_bin": unlisted_bin})
        assert rule_bin_name_mismatch(edge_req, store) is None

    def test_iik_changed_and_bank_changed_clean_attack_edge(self) -> None:
        store = _make_store()
        green_req = _green_request(store)
        assert rule_iik_changed(green_req, store) is None
        assert rule_bank_changed(green_req, store) is None

        # Attack 1: yellow scenario (new IIK in a different bank)
        yellow_item = next(q for q in store.queue if q["scenario"] == "yellow")
        yellow_req = CheckRequest(**{k: yellow_item[k] for k in CheckRequest.model_fields})
        sig_iik = rule_iik_changed(yellow_req, store)
        sig_bank = rule_bank_changed(yellow_req, store)
        assert sig_iik is not None and sig_iik.points == 35 and sig_iik.severity == "primary"
        assert sig_bank is not None and sig_bank.points == 15 and sig_bank.severity == "amplifier"

        # Attack 2: new IIK in the SAME bank (Halyk 601) -> iik_changed only, no bank_changed
        rng = random.Random(303)
        new_halyk_iik = generate_iik(rng, "601", prefix="000")
        same_bank_req = green_req.model_copy(update={"recipient_iik": new_halyk_iik})
        assert rule_iik_changed(same_bank_req, store) is not None
        assert rule_bank_changed(same_bank_req, store) is None

        # Edge 1: trusted account suppresses both signals
        store.trust_account(yellow_req.recipient_bin, yellow_req.recipient_iik)
        assert rule_iik_changed(yellow_req, store) is None
        assert rule_bank_changed(yellow_req, store) is None

        # Edge 2: first-time supplier (grey) returns None
        grey_item = next(q for q in store.queue if q["scenario"] == "grey")
        grey_req = CheckRequest(**{k: grey_item[k] for k in CheckRequest.model_fields})
        assert rule_iik_changed(grey_req, store) is None
        assert rule_bank_changed(grey_req, store) is None

    def test_entity_type_mismatch_clean_attack_edge(self) -> None:
        store = _make_store()
        req = _green_request(store)
        rng = random.Random(404)
        valid_iin = generate_iin(rng)

        # Clean: ТОО with BIN, ИП with IIN
        assert rule_entity_type_mismatch(req) is None
        assert (
            rule_entity_type_mismatch(
                req.model_copy(update={"recipient_name": "ИП Сериков", "recipient_bin": valid_iin})
            )
            is None
        )

        # Attack: ТОО with IIN
        sig_too_iin = rule_entity_type_mismatch(req.model_copy(update={"recipient_bin": valid_iin}))
        assert sig_too_iin is not None and sig_too_iin.points == 25

        # Attack: ИП with BIN
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
        # Clean: old BCC account (> 30 days)
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

        # Attack: red BCC account opened 12 days before DEMO_TODAY
        red_item = next(q for q in store.queue if q["scenario"] == "red")
        red_req = CheckRequest(**{k: red_item[k] for k in CheckRequest.model_fields})
        sig = rule_new_bcc_account(red_req, store, today=DEMO_TODAY)
        assert sig is not None and sig.rule_id == "new_bcc_account" and sig.points == 25

        # Edge: exactly 30 days old -> NOT flagged (< 30 days only)
        opened = DEMO_TODAY - timedelta(days=12)
        exact_30_today = opened + timedelta(days=30)
        assert rule_new_bcc_account(red_req, store, today=exact_30_today) is None

        # Edge: non-BCC account -> None
        assert rule_new_bcc_account(_green_request(store), store) is None

    def test_amount_anomaly_clean_attack_edge(self) -> None:
        store = _make_store()
        green_req = _green_request(store)

        # Clean: usual amount ~1 360 000 vs median 1 350 000
        assert rule_amount_anomaly(green_req, store) is None

        # Attack: 4 900 000 (~3.63x median) -> max 25 amplifier
        huge_req = green_req.model_copy(update={"amount_kzt": 4_900_000})
        sig = rule_amount_anomaly(huge_req, store)
        assert sig is not None
        assert sig.rule_id == "amount_anomaly"
        assert sig.severity == "amplifier"
        assert 10 <= sig.points <= 25
        assert sig.points == 25

        # Edge 1: < 5 past payments -> None even for 10x amount
        store.history = [
            p for p in store.history if p["recipient_bin"] != green_req.recipient_bin
        ] + store.get_supplier_history(green_req.recipient_bin)[:4]
        assert rule_amount_anomaly(huge_req, store) is None

        # Edge 2: zero MAD (5 identical past payments) still detects a large jump
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
        assert sig_zero_mad_mid is not None and sig_zero_mad_mid.points == 20
        sig_zero_mad_high = rule_amount_anomaly(
            green_req.model_copy(update={"amount_kzt": 3_500_000}), store2
        )
        assert sig_zero_mad_high is not None and sig_zero_mad_high.points == 25

    def test_first_payment_clean_and_new(self) -> None:
        store = _make_store()
        assert rule_first_payment(_green_request(store), store) is None

        grey_item = next(q for q in store.queue if q["scenario"] == "grey")
        grey_req = CheckRequest(**{k: grey_item[k] for k in CheckRequest.model_fields})
        sig = rule_first_payment(grey_req, store)
        assert sig is not None and sig.rule_id == "first_payment" and sig.severity == "info"
        assert sig.points == 0

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
