"""Unit tests for each pure risk rule: clean, attack, and edge cases."""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

import pytest

from app.risk.config import BCC_BANK_CODE, BCC_BIK, DEMO_TODAY, URGENT_PHRASES
from app.risk.rules import (
    build_analyst_details,
    compute_client_p90,
    extract_invoice_number,
    rule_amount_anomaly,
    rule_bank_changed,
    rule_bcc_account_not_found,
    rule_bcc_account_other_owner,
    rule_bcc_owner_verified,
    rule_bik_format,
    rule_bin_format,
    rule_bin_name_mismatch,
    rule_bin_young,
    rule_duplicate_invoice,
    rule_entity_type_mismatch,
    rule_first_payment,
    rule_iik_bank_code_vs_bik,
    rule_iik_belongs_to_other_counterparty,
    rule_iik_changed,
    rule_iik_format,
    rule_kbe_mismatch,
    rule_knp_unusual,
    rule_lookalike_supplier,
    rule_mixed_script_name,
    rule_new_bcc_account,
    rule_new_recipient_accumulated,
    rule_structuring_72h,
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

    def test_bcc_account_not_found_precheck(self) -> None:
        store = _make_store()
        # Non-BCC IIK -> None
        assert rule_bcc_account_not_found(_green_request(store), store) is None
        # Existing BCC IIK -> None
        step_payment = next(
            p for p in store.history if p["recipient_name"] == "ТОО «СтепьЭнергоСервис»"
        )
        known_bcc_req = _green_request(store).model_copy(
            update={"recipient_iik": step_payment["recipient_iik"], "recipient_bik": BCC_BIK}
        )
        assert rule_bcc_account_not_found(known_bcc_req, store) is None
        # Valid synthetic BCC 856 IIK absent from bcc_accounts -> block signal
        unknown_bcc = generate_iik(random.Random(5051), BCC_BANK_CODE)
        sig = rule_bcc_account_not_found(
            known_bcc_req.model_copy(update={"recipient_iik": unknown_bcc}), store
        )
        assert sig is not None
        assert sig.rule_id == "bcc_account_not_found"
        assert sig.severity == "block"
        assert sig.reason_ru == "Счёт в BCC не найден."


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
        red_req = CheckRequest(**{k: red_item[k] for k in CheckRequest.model_fields if k in red_item})
        sig = rule_bcc_account_other_owner(red_req, store)
        assert sig is not None
        assert sig.rule_id == "bcc_account_other_owner"
        assert sig.severity == "block"
        assert sig.reason_ru == "Счёт в BCC оформлен не на указанного получателя."
        # Banking secrecy: client signal & evidence must never disclose owner name, BIN, or date
        bcc_entry = store.bcc_accounts[red_req.recipient_iik]
        for leaked in (bcc_entry["owner_name"], "Вектор Трейд", bcc_entry["owner_bin"], bcc_entry["opened_at"]):
            assert leaked not in sig.reason_ru
            assert leaked not in sig.reason
            assert leaked not in (sig.evidence.expected or "")
            assert leaked not in (sig.evidence.actual or "")
            assert leaked not in (sig.evidence.since or "")
        assert sig.evidence.since is None

        # Analyst details expose internal BCC owner & opening date
        analyst = build_analyst_details(red_req, store, [sig], today=DEMO_TODAY)
        assert analyst.bcc_account is not None
        assert analyst.bcc_account.owner_name == "ТОО «Вектор Трейд»"
        assert analyst.bcc_account.owner_bin == bcc_entry["owner_bin"]
        assert analyst.bcc_account.opened_at == bcc_entry["opened_at"]
        assert analyst.bcc_account.owner_matches_recipient is False
        assert len(analyst.signal_details) == 1
        assert "Вектор Трейд" in analyst.signal_details[0].reason_ru
        assert bcc_entry["owner_bin"] in (analyst.signal_details[0].evidence.actual or "")

        assert rule_bcc_account_other_owner(_green_request(store), store) is None
        rng = random.Random(101)
        unknown_bcc_iik = generate_iik(rng, BCC_BANK_CODE)
        edge_req = clean_req.model_copy(update={"recipient_iik": unknown_bcc_iik})
        assert rule_bcc_account_other_owner(edge_req, store) is None

    def test_lookalike_supplier_clean_attack_m1_h4_and_exact_short(self) -> None:
        store = _make_store()
        assert rule_lookalike_supplier(_green_request(store), store) is None

        grey_item = next(q for q in store.queue if q["scenario"] == "grey")
        grey_req = CheckRequest(**{k: grey_item[k] for k in CheckRequest.model_fields if k in grey_item})
        assert rule_lookalike_supplier(grey_req, store) is None

        # Attack 1: Latin C lookalike with different BIN (similarity 100 >= 95 -> block red)
        red_item = next(q for q in store.queue if q["scenario"] == "red")
        red_req = CheckRequest(**{k: red_item[k] for k in CheckRequest.model_fields if k in red_item})
        sig = rule_lookalike_supplier(red_req, store)
        assert sig is not None
        assert sig.rule_id == "lookalike_supplier"
        assert sig.points == 100
        assert sig.severity == "block"

        # Attack 2 (H4): all normalized tokens of known supplier (len >= 8) contained in new name
        # True similarity < 95 -> primary 60 (yellow alone)
        h4_req = red_req.model_copy(
            update={"recipient_name": "ТОО «Алатау Снаб Трейдинг Казахстан»"}
        )
        sig_h4 = rule_lookalike_supplier(h4_req, store)
        assert sig_h4 is not None and sig_h4.rule_id == "lookalike_supplier"
        assert sig_h4.points == 60
        assert sig_h4.severity == "primary"

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

        # Requirement 3: prefix/token variants, transliteration, and Unicode confusables -> lookalike
        for variant_name in (
            "ТОО «Алатау Снабжение»",
            "ТОО «АлатауСнабСервис»",
            "ТОО «Алатау Снабкомплект»",
            "ТОО «Alatau Snab»",
            'LLP "Alatau Snab"',
            "ТОО «Alatau Snabzhenie»",
            "ТОО «Алатау \u13dfнаб»",
            "ТОО «\u0251латау Снаб»",
            "ТОО «Алат\u3164ау\u2800 Сн\u0301аб\ufe0f»",
        ):
            sig_var = rule_lookalike_supplier(
                red_req.model_copy(update={"recipient_name": variant_name}),
                store2,
            )
            assert sig_var is not None, f"Expected lookalike for {variant_name!r}"
            assert sig_var.rule_id == "lookalike_supplier"
            assert "Алатау Снаб" in sig_var.reason_ru

        # Exception preserved: known supplier with its own history is NOT flagged even on variant name
        green_req = _green_request(store2)
        assert (
            rule_lookalike_supplier(
                green_req.model_copy(update={"recipient_name": "ТОО «Алатау Снабжение»"}),
                store2,
            )
            is None
        )
        assert (
            rule_lookalike_supplier(
                green_req.model_copy(update={"recipient_name": "ТОО «Alatau Snab»"}),
                store2,
            )
            is None
        )

    def test_k2_exact_name_different_bin_is_block_and_variants_detected(self) -> None:
        from app.risk.engine import check_payment

        store = _make_store()
        rng = random.Random(20262)
        old_other_bin = generate_bin(rng, year=15, month=4)  # 11-year-old BIN (not young)
        ext_iik = generate_iik(rng, "965", prefix="000")
        base_req = CheckRequest(
            payer_id=store.default_payer_id,
            recipient_name="ТОО «Алатау Снаб»",
            recipient_bin=old_other_bin,
            recipient_iik=ext_iik,
            recipient_bik="IRTYKZKA",
            amount_kzt=1_350_000,
            purpose="Оплата по счёту № 810",
        )

        # Exact name of known supplier with different OLD BIN -> block (red, 100)
        sig_exact = rule_lookalike_supplier(base_req, store)
        assert sig_exact is not None
        assert sig_exact.severity == "block"
        assert sig_exact.points == 100
        res_exact = check_payment(base_req, store)
        assert res_exact.verdict == "red"
        assert res_exact.score == 100

        # Near-exact single-char typo (similarity >= 95) with old BIN -> block (red, 100)
        typo_req = base_req.model_copy(update={"recipient_name": "ТОО «Алатау Снабб»"})
        sig_typo = rule_lookalike_supplier(typo_req, store)
        assert sig_typo is not None and sig_typo.severity == "block" and sig_typo.points == 100
        assert check_payment(typo_req, store).verdict == "red"

        # K2 variants against ТОО «Алатау Снаб» -> caught as lookalike (at least yellow)
        for variant_name in (
            "ТОО «Торговый дом Алатау»",
            "ТОО «А-Снаб»",
            "ТОО «Alatau Supply»",
            "ТОО «Алатоо Снаб»",
        ):
            var_req = base_req.model_copy(update={"recipient_name": variant_name})
            sig_var = rule_lookalike_supplier(var_req, store)
            assert sig_var is not None, f"Expected lookalike for {variant_name!r}"
            assert sig_var.rule_id == "lookalike_supplier"
            assert "Алатау Снаб" in sig_var.reason_ru
            res_var = check_payment(var_req, store)
            assert res_var.verdict in ("yellow", "red"), f"{variant_name!r} got {res_var.verdict}"

    def test_k3_generic_words_ie_initials_and_amount_similarity_guard(self) -> None:
        from app.risk.engine import check_payment

        store = _make_store()
        rng = random.Random(20263)

        # Legitimate new corporate suppliers sharing generic words -> NOT flagged (grey, 0)
        for legit_corp in (
            "ТОО «Астана Сервис»",
            "ТОО «Монтаж Сервис»",
            "ТОО «Алматы Сервис»",
            "ТОО «Актау Снаб»",
            'ТОО "Almaty Service"',
            'ТОО "Astana Trade Group"',
        ):
            corp_req = CheckRequest(
                payer_id=store.default_payer_id,
                recipient_name=legit_corp,
                recipient_bin=generate_bin(rng, year=18, month=6),
                recipient_iik=generate_iik(rng, "722", prefix="000"),
                recipient_bik="CASPKZKA",
                amount_kzt=950_000,
                purpose="Оплата услуг по договору, счёт № 820",
            )
            assert rule_lookalike_supplier(corp_req, store) is None, legit_corp
            res = check_payment(corp_req, store)
            assert res.verdict == "grey", f"{legit_corp!r} falsely got {res.verdict} ({res.score})"
            assert res.score == 0

        # IE with different initials against ИП Байжанов К.Т. -> NOT flagged (grey, 0)
        for legit_ie in (
            "ИП Байжанова А.К.",
            "ИП Байжанов А.С.",
            "ИП Байжанова Асель Канатовна",
        ):
            ie_req = CheckRequest(
                payer_id=store.default_payer_id,
                recipient_name=legit_ie,
                recipient_bin=generate_iin(rng),
                recipient_iik=generate_iik(rng, "722", prefix="000"),
                recipient_bik="CASPKZKA",
                amount_kzt=900_000,
                purpose="Оплата подрядных работ по акту № 825",
            )
            assert rule_lookalike_supplier(ie_req, store) is None, legit_ie
            res_ie = check_payment(ie_req, store)
            assert res_ie.verdict == "grey", f"{legit_ie!r} falsely got {res_ie.verdict}"
            assert res_ie.score == 0

        # IE with SAME initials and different IIN -> exact clone -> block (red, 100)
        clone_ie_req = CheckRequest(
            payer_id=store.default_payer_id,
            recipient_name="ИП Байжанов К.Т.",
            recipient_bin=generate_iin(rng),
            recipient_iik=generate_iik(rng, "722", prefix="000"),
            recipient_bik="CASPKZKA",
            amount_kzt=190_000,
            purpose="Оплата услуг по акту № 826",
        )
        sig_clone_ie = rule_lookalike_supplier(clone_ie_req, store)
        assert sig_clone_ie is not None and sig_clone_ie.severity == "block"
        assert check_payment(clone_ie_req, store).verdict == "red"

        # Amount comparison guard: lookalike with similarity < 92 must compare amount against
        # client p90 (not matched supplier's low median). ТазаСу Сервис has median 56k;
        # a 600k payment to "ТОО «ТазаСу Сервис Групп Казахстан»" (sim < 92) must NOT trigger
        # supplier amount_anomaly (stays yellow 60, not red 95).
        low_sim_req = CheckRequest(
            payer_id=store.default_payer_id,
            recipient_name="ТОО «ТазаСу Сервис Групп Казахстан»",
            recipient_bin=generate_bin(rng, year=18, month=3),
            recipient_iik=generate_iik(rng, "722", prefix="000"),
            recipient_bik="CASPKZKA",
            amount_kzt=600_000,
            purpose="Оплата по счёту № 830",
        )
        res_low_sim = check_payment(low_sim_req, store)
        assert res_low_sim.verdict == "yellow"
        assert res_low_sim.score == 60
        assert [s.rule_id for s in res_low_sim.signals] == ["lookalike_supplier", "first_payment"]

    def test_mixed_script_name_rule(self) -> None:
        store = _make_store()
        assert rule_mixed_script_name(_green_request(store)) is None

        # Separate Latin legal form, whole Latin brand tokens, and legit numbers are NOT flagged
        for safe_name in (
            'LLP "Алатау Снаб"',
            "ТОО «ЭкоSTAR»",
            "ТОО «QazaqСтрой»",
            "ТОО «Алматы-2»",
            "ТОО «Строй 2020»",
            "ТОО «1С-Рейтинг»",
        ):
            assert (
                rule_mixed_script_name(_green_request(store).model_copy(update={"recipient_name": safe_name}))
                is None
            ), safe_name

        # Red scenario has Latin C inside Cyrillic "Cнаб" -> primary 30
        red_item = next(q for q in store.queue if q["scenario"] == "red")
        red_req = CheckRequest(**{k: red_item[k] for k in CheckRequest.model_fields if k in red_item})
        sig = rule_mixed_script_name(red_req)
        assert sig is not None
        assert sig.rule_id == "mixed_script_name"
        assert sig.severity == "primary"
        assert sig.points == 30
        assert "цифры вместо букв" in sig.reason_ru

        # Digits 0/3 inside Cyrillic word -> flagged, analyst_details has exact character positions
        digits_req = red_req.model_copy(update={"recipient_name": "ТОО «Ка3Л0гистик»"})
        sig_dig = rule_mixed_script_name(digits_req)
        assert sig_dig is not None and sig_dig.rule_id == "mixed_script_name"
        assert "Ка3Л0гистик" not in (sig_dig.evidence.actual or "")
        analyst_dig = build_analyst_details(digits_req, store, [sig_dig], today=DEMO_TODAY)
        assert len(analyst_dig.signal_details) == 1
        assert analyst_dig.signal_details[0].evidence.positions == [7, 9]

    def test_bin_name_mismatch_clean_attack_and_m3_history_downgrade(self) -> None:
        store = _make_store()
        assert rule_bin_name_mismatch(_green_request(store), store) is None

        red_item = next(q for q in store.queue if q["scenario"] == "red")
        red_req = CheckRequest(**{k: red_item[k] for k in CheckRequest.model_fields if k in red_item})
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
        yellow_req = CheckRequest(**{k: yellow_item[k] for k in CheckRequest.model_fields if k in yellow_item})
        at_median = yellow_req.model_copy(update={"amount_kzt": 820_000})
        sig_iik = rule_iik_changed(at_median, store)
        sig_bank = rule_bank_changed(at_median, store)
        # Amount 820_000 >= median 820_000 -> 30 pts (escalates 35 + 30 = 65 -> red)
        assert sig_iik is not None and sig_iik.points == 35 and sig_iik.severity == "primary"
        assert sig_bank is not None and sig_bank.points == 30 and sig_bank.severity == "amplifier"

        # Below supplier median -> standard +15 amplifier (35 + 15 = 50 -> yellow)
        low_amt_sig = rule_bank_changed(yellow_req.model_copy(update={"amount_kzt": 700_000}), store)
        assert low_amt_sig is not None and low_amt_sig.points == 15

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
        grey_req = CheckRequest(**{k: grey_item[k] for k in CheckRequest.model_fields if k in grey_item})
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
        red_req = CheckRequest(**{k: red_item[k] for k in CheckRequest.model_fields if k in red_item})
        sig = rule_new_bcc_account(red_req, store, today=DEMO_TODAY)
        assert sig is not None and sig.rule_id == "new_bcc_account" and sig.points == 25
        assert sig.reason_ru == "Счёт получателя открыт недавно."
        bcc_entry = store.bcc_accounts[red_req.recipient_iik]
        for leaked in (bcc_entry["opened_at"], "12", bcc_entry["owner_name"], bcc_entry["owner_bin"]):
            assert leaked not in sig.reason_ru
            assert leaked not in sig.reason
            assert leaked not in (sig.evidence.expected or "")
            assert leaked not in (sig.evidence.actual or "")
            assert leaked not in (sig.evidence.since or "")
        assert sig.evidence.since is None

        analyst = build_analyst_details(red_req, store, [sig], today=DEMO_TODAY)
        assert analyst.bcc_account is not None
        assert analyst.bcc_account.opened_at == bcc_entry["opened_at"]
        assert analyst.bcc_account.age_days == 12
        assert len(analyst.signal_details) == 1
        assert bcc_entry["opened_at"] in analyst.signal_details[0].reason_ru
        assert analyst.signal_details[0].evidence.since == bcc_entry["opened_at"]

        opened = DEMO_TODAY - timedelta(days=12)
        exact_30_today = opened + timedelta(days=30)
        assert rule_new_bcc_account(red_req, store, today=exact_30_today) is None
        assert rule_new_bcc_account(_green_request(store), store) is None

        # Boundary (Item 14): account opened after DEMO_TODAY -> treated as 0 days (young), not ignored
        future_today = opened - timedelta(days=5)
        sig_future = rule_new_bcc_account(red_req, store, today=future_today)
        assert sig_future is not None and sig_future.rule_id == "new_bcc_account"
        analyst_future = build_analyst_details(red_req, store, [sig_future], today=future_today)
        assert analyst_future.bcc_account is not None and analyst_future.bcc_account.age_days == 0

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
        grey_req = CheckRequest(**{k: grey_item[k] for k in CheckRequest.model_fields if k in grey_item})
        assert rule_amount_anomaly(grey_req, store3) is None

        big_first = grey_req.model_copy(update={"amount_kzt": p90 + 500_000})
        sig_p90 = rule_amount_anomaly(big_first, store3)
        assert sig_p90 is not None
        assert sig_p90.rule_id == "amount_anomaly"
        assert sig_p90.severity == "amplifier"
        assert 10 <= sig_p90.points <= 20

        # Item 4: first payment > 3x client p90 -> primary 35 (yellow); > 10x -> primary 65 (red)
        sig_3x = rule_amount_anomaly(
            grey_req.model_copy(update={"amount_kzt": p90 * 3.5}), store3
        )
        assert sig_3x is not None and sig_3x.severity == "primary" and sig_3x.points == 35
        sig_10x = rule_amount_anomaly(
            grey_req.model_copy(update={"amount_kzt": p90 * 10.5}), store3
        )
        assert sig_10x is not None and sig_10x.severity == "primary" and sig_10x.points == 65

        # Item 4: known supplier >= 10x supplier p90 -> primary 65 (red)
        sig_sup_10x = rule_amount_anomaly(
            _green_request(store3).model_copy(update={"amount_kzt": 20_000_000}), store3
        )
        assert sig_sup_10x is not None and sig_sup_10x.severity == "primary" and sig_sup_10x.points == 65

    def test_first_payment_clean_and_new(self) -> None:
        store = _make_store()
        assert rule_first_payment(_green_request(store), store) is None

        grey_item = next(q for q in store.queue if q["scenario"] == "grey")
        grey_req = CheckRequest(**{k: grey_item[k] for k in CheckRequest.model_fields if k in grey_item})
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

        # Boundary (Item 14): BIN registered after DEMO_TODAY -> treated as 0 months (young)
        future_same_yr_bin = make_bin_iin("26064000001")
        future_next_yr_bin = make_bin_iin("27014000001")
        sig_f1 = rule_bin_young(
            req.model_copy(update={"recipient_bin": future_same_yr_bin}), today=DEMO_TODAY
        )
        sig_f2 = rule_bin_young(
            req.model_copy(update={"recipient_bin": future_next_yr_bin}), today=DEMO_TODAY
        )
        assert sig_f1 is not None and sig_f1.rule_id == "bin_young"
        assert sig_f2 is not None and sig_f2.rule_id == "bin_young"

        # Edge: IIN returns None (not a BIN)
        rng = random.Random(1201)
        assert (
            rule_bin_young(
                req.model_copy(update={"recipient_bin": generate_iin(rng)}), today=DEMO_TODAY
            )
            is None
        )

    def test_kbe_mismatch_and_knp_unusual_rules(self) -> None:
        store = _make_store()
        green_req = _green_request(store)
        rng = random.Random(1313)
        valid_iin = generate_iin(rng)
        joint_bin_6 = generate_bin(rng, entity_digit=6)

        # Default empty kbe/knp -> rules skipped (backwards compatible)
        assert rule_kbe_mismatch(green_req) is None
        assert rule_knp_unusual(green_req, store) is None

        # KBe=17 with individual IIN triggers primary 40 even when "ТОО" is omitted from name
        no_opf_iin = green_req.model_copy(
            update={"recipient_name": "Алатау Снаб", "recipient_bin": valid_iin, "kbe": "17"}
        )
        sig_kbe = rule_kbe_mismatch(no_opf_iin)
        assert sig_kbe is not None
        assert sig_kbe.rule_id == "kbe_mismatch"
        assert sig_kbe.severity == "primary"
        assert sig_kbe.points == 40

        # KBe=17 with BIN and KBe=19 with IIN or joint-venture BIN(6) -> clean
        assert rule_kbe_mismatch(green_req.model_copy(update={"kbe": "17"})) is None
        assert rule_kbe_mismatch(no_opf_iin.model_copy(update={"kbe": "19"})) is None
        assert (
            rule_kbe_mismatch(
                green_req.model_copy(update={"recipient_bin": joint_bin_6, "kbe": "19"})
            )
            is None
        )
        # KBe=19 with corporate BIN(4) -> mismatch
        sig_19_bin = rule_kbe_mismatch(green_req.model_copy(update={"kbe": "19"}))
        assert sig_19_bin is not None and sig_19_bin.points == 25

        # KNP matching supplier history (710 for Алатау Снаб) -> None; different KNP -> amplifier 15
        assert rule_knp_unusual(green_req.model_copy(update={"knp": "710"}), store) is None
        sig_knp = rule_knp_unusual(green_req.model_copy(update={"knp": "859"}), store)
        assert sig_knp is not None
        assert sig_knp.rule_id == "knp_unusual"
        assert sig_knp.severity == "amplifier"
        assert sig_knp.points == 15

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

        # Must NOT fire on words containing "срочно" as a substring (including spaced/translit)
        for safe_purpose in (
            "Оплата по договору, несрочно",
            "Досрочно погашение аренды по счёту № 5",
            "Оплата по договору, н е с р о ч н о",
            "Oplata nesrochno po schetu",
            "Dosrochno pogashenie",
        ):
            assert rule_urgent_wording(req.model_copy(update={"purpose": safe_purpose})) is None

        # Must fire on stems, English, translit, spaced/dotted letters, homoglyphs, and invisibles
        for spoofed_purpose in (
            "Оплата по счёту, cрoчн0!",  # Latin c, o and digit 0
            "Оплата на новый счет",  # е instead of ё
            "Оплата на новый расчётный счёт",
            "Смена обслуживающего банка по договору",
            "Смена банка получателя",
            "Оплата срочный заказ сегодня",
            "Срочная поставка оборудования",
            "Төлем с\u200bмена реквизитов",  # Cf invisible char
            "Төлем шугыл түрде",  # Kazakh folded шұғыл
            "Жедел төлем № 14",
            "Urgent payment for invoice 77",
            "Payment using new bank details",
            "Invoice with changed bank account",
            "Oplata srochno po dogovoru",
            "Оплата по счёту, с р о ч н о!",
            "Оплата по счёту, с.р.о.ч.н.о!",
            "Invoice u r g e n t please",
            "Oplata s.r.o.c.h.n.o!",
        ):
            sig = rule_urgent_wording(req.model_copy(update={"purpose": spoofed_purpose}))
            assert sig is not None and sig.rule_id == "urgent_wording", spoofed_purpose

    def test_duplicate_invoice_90d_history_and_memory(self) -> None:
        assert extract_invoice_number("Оплата по счёту № 214 по договору № 14-А") == "214"
        assert extract_invoice_number("Оплата сч. 214 за товары") == "214"
        assert extract_invoice_number("Оплата № 214") == "214"
        assert extract_invoice_number("Оплата по договору № 14-А без счёта") is None
        assert extract_invoice_number("Оплата по доп. соглашению № 2 (договор № 19-К)") is None

        store = _make_store()
        green_req = _green_request(store)
        # Unique invoice -> None
        assert rule_duplicate_invoice(green_req, store, today=DEMO_TODAY) is None

        # Invoice #113 paid to Алатау Снаб 11 days ago (within 90d) -> primary 35
        dup_hist = green_req.model_copy(update={"purpose": "Оплата сч. 113 за материалы"})
        sig_hist = rule_duplicate_invoice(dup_hist, store, today=DEMO_TODAY)
        assert sig_hist is not None
        assert sig_hist.rule_id == "duplicate_invoice"
        assert sig_hist.severity == "primary" and sig_hist.points == 35
        assert "Возможна повторная оплата счёта" in sig_hist.reason_ru

        # Invoice #101 paid 356 days ago (> 90d) -> None
        old_inv = green_req.model_copy(update={"purpose": "Оплата по счёту № 101"})
        assert rule_duplicate_invoice(old_inv, store, today=DEMO_TODAY) is None

        # Recorded in-memory check -> triggers duplicate_invoice
        store.record_check(green_req, invoice_no="214", today=DEMO_TODAY)
        sig_mem = rule_duplicate_invoice(
            green_req.model_copy(update={"purpose": "Оплата № 214"}), store, today=DEMO_TODAY
        )
        assert sig_mem is not None and sig_mem.rule_id == "duplicate_invoice"

    def test_new_recipient_accumulated_7d_and_structuring_72h(self) -> None:
        store = _make_store()
        grey_item = next(q for q in store.queue if q["scenario"] == "grey")
        grey_req = CheckRequest(**{k: grey_item[k] for k in CheckRequest.model_fields if k in grey_item})
        assert rule_new_recipient_accumulated(grey_req, store, today=DEMO_TODAY) is None

        # Old check (> 7d ago) ignored
        old_dt = datetime(DEMO_TODAY.year, DEMO_TODAY.month, DEMO_TODAY.day, 10, 0, tzinfo=UTC) - timedelta(days=10)
        store.record_check(grey_req.model_copy(update={"amount_kzt": 2_000_000}), checked_at=old_dt)
        assert rule_new_recipient_accumulated(grey_req, store, today=DEMO_TODAY) is None

        # Recent check within 7 days pushes accumulated total above client median -> amplifier
        recent_dt = datetime(DEMO_TODAY.year, DEMO_TODAY.month, DEMO_TODAY.day, 9, 0, tzinfo=UTC) - timedelta(days=2)
        store.record_check(grey_req.model_copy(update={"amount_kzt": 1_200_000}), checked_at=recent_dt)
        sig_acc = rule_new_recipient_accumulated(
            grey_req.model_copy(update={"amount_kzt": 900_000}), store, today=DEMO_TODAY
        )
        assert sig_acc is not None
        assert sig_acc.rule_id == "new_recipient_accumulated"
        assert sig_acc.severity == "amplifier"

        # Item 15: 3 payments of ~40% median (540_000 vs 1_350_000) within 72h -> structuring_72h
        store2 = _make_store()
        green_req = _green_request(store2)
        chunk = green_req.model_copy(update={"amount_kzt": 540_000})
        assert rule_structuring_72h(chunk, store2, today=DEMO_TODAY) is None
        t0 = datetime(DEMO_TODAY.year, DEMO_TODAY.month, DEMO_TODAY.day, 8, 0, tzinfo=UTC)
        store2.record_check(chunk.model_copy(update={"purpose": "Оплата сч. 901"}), invoice_no="901", checked_at=t0 - timedelta(hours=20))
        assert rule_structuring_72h(chunk.model_copy(update={"purpose": "Оплата сч. 902"}), store2, today=DEMO_TODAY) is None
        store2.record_check(chunk.model_copy(update={"purpose": "Оплата сч. 902"}), invoice_no="902", checked_at=t0 - timedelta(hours=10))
        sig_split = rule_structuring_72h(chunk.model_copy(update={"purpose": "Оплата сч. 903"}), store2, today=DEMO_TODAY)
        assert sig_split is not None
        assert sig_split.rule_id == "structuring_72h"
        assert sig_split.severity == "amplifier" and sig_split.points == 20

    def test_bcc_owner_verified_same_bin_new_iik(self) -> None:
        store = _make_store()
        green_req = _green_request(store)
        new_bcc_iik = generate_iik(random.Random(1010), BCC_BANK_CODE, prefix="KZT")
        store.bcc_accounts[new_bcc_iik] = {
            "owner_bin": green_req.recipient_bin,
            "owner_name": green_req.recipient_name,
            "opened_at": (DEMO_TODAY - timedelta(days=90)).isoformat(),
        }
        bcc_req = green_req.model_copy(update={"recipient_iik": new_bcc_iik, "recipient_bik": BCC_BIK})
        assert rule_iik_changed(bcc_req, store) is None
        assert rule_bank_changed(bcc_req, store) is None
        sig = rule_bcc_owner_verified(bcc_req, store)
        assert sig is not None and sig.rule_id == "bcc_owner_verified" and sig.points == 0
        assert sig.reason_ru == "Счёт подтверждён банком: принадлежит этому поставщику."
        assert green_req.recipient_bin not in sig.reason_ru
        assert green_req.recipient_bin not in (sig.evidence.actual or "")
        assert sig.evidence.since is None
