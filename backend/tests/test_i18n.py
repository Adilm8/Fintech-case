"""Unit tests for ru / kk / en internationalization across i18n catalog, validators, engine, and handlers."""

from __future__ import annotations

import string

import pytest
from fastapi import HTTPException

from app.i18n import (
    FIELD_LABELS,
    KIND_LABELS,
    MESSAGES,
    SUPPORTED_LANGS,
    Lang,
    field_label,
    kind_label,
    resolve_lang,
    t,
)
from app.main import (
    _format_validation_message,
    get_approvals,
    get_payments_queue,
    post_approval_decision,
    post_check_payment,
    post_create_approval,
)
from app.risk.engine import check_payment, localize_check_result
from app.schemas import ApprovalCreateRequest, ApprovalDecisionRequest, CheckRequest
from app.store import Store, store
from app.validators.kz import iik_check, iik_ok


def _placeholders(template: str) -> set[str]:
    return {
        field_name
        for _, field_name, _, _ in string.Formatter().parse(template)
        if field_name is not None
    }


def _queue_req(data_store: Store, qid: str) -> CheckRequest:
    item = next(q for q in data_store.queue if q["id"] == qid)
    return CheckRequest(
        payer_id=item["payer_id"],
        recipient_name=item["recipient_name"],
        recipient_bin=item["recipient_bin"],
        recipient_iik=item["recipient_iik"],
        recipient_bik=item["recipient_bik"],
        amount_kzt=item["amount_kzt"],
        purpose=item["purpose"],
    )


class TestI18nCatalogIntegrity:
    def test_every_message_has_all_languages_and_matching_placeholders(self) -> None:
        assert len(MESSAGES) >= 40
        for key, variants in MESSAGES.items():
            assert set(variants.keys()) == set(SUPPORTED_LANGS), f"Missing lang in {key}"
            ru_ph = _placeholders(variants["ru"])
            for lang in SUPPORTED_LANGS:
                text = variants[lang]
                assert isinstance(text, str) and text.strip(), f"Empty {lang} text for {key}"
                assert _placeholders(text) == ru_ph, f"Placeholder mismatch in {key} ({lang})"

    def test_every_field_label_has_all_languages(self) -> None:
        assert "lang" in FIELD_LABELS
        for field_key, variants in FIELD_LABELS.items():
            assert set(variants.keys()) == set(SUPPORTED_LANGS)
            for lang in SUPPORTED_LANGS:
                assert field_label(field_key, lang).strip()

    def test_every_kind_label_has_all_languages(self) -> None:
        assert len(KIND_LABELS) >= 20
        kz_letters = set("әғқңөұүһіӘҒҚҢӨҰҮҺІ")
        for kind_key, variants in KIND_LABELS.items():
            assert set(variants.keys()) == set(SUPPORTED_LANGS), f"Missing lang in {kind_key}"
            for lang in SUPPORTED_LANGS:
                assert kind_label(kind_key, lang).strip()
            assert any(ch in kz_letters for ch in variants["kk"]), (
                f"Expected Kazakh-specific letter in KIND_LABELS[{kind_key!r}]"
            )

    def test_kazakh_catalog_uses_authentic_kazakh_cyrillic_letters(self) -> None:
        kz_letters = set("әғқңөұүһіӘҒҚҢӨҰҮҺІ")
        kk_texts = [variants["kk"] for variants in MESSAGES.values()]

        # Every Kazakh message must use genuine Kazakh Cyrillic orthography (not Russian-folded)
        all_kk = "\n".join(kk_texts)
        for expected_char in ("ә", "ғ", "қ", "ң", "ө", "ұ", "ү", "і"):
            assert expected_char in all_kk.lower(), f"Missing Kazakh letter {expected_char!r}"

        # Key user-facing verdict headlines and advice contain Kazakh-specific letters
        for key in (
            "headline.green",
            "headline.yellow",
            "headline.red",
            "headline.grey",
            "next_action.green",
            "next_action.yellow",
            "next_action.red",
            "rule.iik_changed",
            "rule.lookalike_supplier",
            "rule.bcc_account_other_owner",
            "rule.entity_type_mismatch_legal_iin",
            "rule.urgent_wording",
        ):
            kk_text = MESSAGES[key]["kk"]
            assert any(ch in kz_letters for ch in kk_text), (
                f"Expected Kazakh-specific letter in {key}: {kk_text!r}"
            )

    def test_resolve_lang_defaults_unknown_to_ru(self) -> None:
        assert resolve_lang(None) == "ru"
        assert resolve_lang("") == "ru"
        assert resolve_lang("ru") == "ru"
        assert resolve_lang("kk") == "kk"
        assert resolve_lang("en") == "en"
        assert resolve_lang("de") == "ru"


class TestValidatorAndEngineI18n:
    def test_iik_check_returns_key_and_iik_ok_localizes(self) -> None:
        ok, key, params = iik_check("KZ86125KZT500410010")
        assert ok is False
        assert key == "iik.length"
        assert params == {"length": 19}

        _, ru_msg = iik_ok("KZ86125KZT500410010", lang="ru")
        _, kk_msg = iik_ok("KZ86125KZT500410010", lang="kk")
        _, en_msg = iik_ok("KZ86125KZT500410010", lang="en")
        assert ru_msg == "ИИК должен состоять из 20 символов (сейчас 19)."
        assert kk_msg is not None and "20" in kk_msg and "19" in kk_msg and kk_msg != ru_msg
        assert en_msg is not None and "20" in en_msg and "19" in en_msg and en_msg != ru_msg

    @pytest.mark.parametrize("qid", ["Q-001", "Q-002", "Q-003", "Q-004", "Q-007", "Q-009", "Q-010"])
    def test_check_payment_preserves_ru_fields_and_populates_localized_fields(
        self, qid: str
    ) -> None:
        local_store = Store()
        req = _queue_req(local_store, qid)
        res_ru = check_payment(req, local_store, lang="ru")
        res_kk = check_payment(req, local_store, lang="kk")
        res_en = check_payment(req, local_store, lang="en")

        assert res_ru.headline == res_ru.headline_ru
        assert res_ru.next_action.text == res_ru.next_action.text_ru
        for sig in res_ru.signals:
            assert sig.reason == sig.reason_ru
            assert sig.message_key is not None

        for lang_code, res in (("kk", res_kk), ("en", res_en)):
            assert res.verdict == res_ru.verdict
            assert res.score == res_ru.score
            assert res.headline_ru == res_ru.headline_ru
            assert res.headline != res.headline_ru, f"{qid} {lang_code} headline not localized"
            assert res.next_action.text_ru == res_ru.next_action.text_ru
            assert res.next_action.text != res.next_action.text_ru
            assert len(res.signals) == len(res_ru.signals)
            for sig, sig_ru in zip(res.signals, res_ru.signals, strict=True):
                assert sig.rule_id == sig_ru.rule_id
                assert sig.reason_ru == sig_ru.reason_ru
                assert sig.reason != sig.reason_ru
                assert sig.message_key is not None

            # Re-localizing the ru CheckResult matches computing directly in that language
            reloc = localize_check_result(res_ru, lang_code)
            assert reloc.headline == res.headline
            assert reloc.next_action.text == res.next_action.text
            assert [s.reason for s in reloc.signals] == [s.reason for s in res.signals]
            assert [s.evidence.field_label for s in reloc.signals] == [
                s.evidence.field_label for s in res.signals
            ]
            assert [s.evidence.expected for s in reloc.signals] == [
                s.evidence.expected for s in res.signals
            ]
            assert [s.evidence.actual for s in reloc.signals] == [
                s.evidence.actual for s in res.signals
            ]

            # Serialized payload includes localized fields and hides internal message_key
            dumped = res.model_dump()
            assert dumped["headline"] == res.headline
            assert dumped["headline_ru"] == res.headline_ru
            assert dumped["next_action"]["text"] == res.next_action.text
            assert "headline_key" not in dumped
            assert "message_key" not in dumped["next_action"]
            if dumped["signals"]:
                sig0 = dumped["signals"][0]
                assert "reason" in sig0
                assert "reason_ru" in sig0
                assert "message_key" not in sig0
                assert sig0["evidence"]["field_label"]
                assert "expected_key" not in sig0["evidence"]
                assert "actual_key" not in sig0["evidence"]


class TestHandlersI18nDirect:
    def test_handlers_localize_responses_and_errors(self) -> None:
        store.reset()
        try:
            q_kk = get_payments_queue(lang="kk")
            q_en = get_payments_queue(lang="en")
            assert len(q_kk) == 10 and len(q_en) == 10
            assert q_kk[0].check.headline == t("headline.green", "kk")
            assert q_en[0].check.headline == t("headline.green", "en")
            assert q_en[0].check.headline_ru == t("headline.green", "ru")

            yellow_req = _queue_req(store, "Q-002").model_copy(update={"amount_kzt": 700_000})
            checked_en = post_check_payment(yellow_req, lang="en")
            assert checked_en.headline == t("headline.yellow", "en")
            assert checked_en.headline_ru == t("headline.yellow", "ru")

            # Create approval in ru, then read in kk and decide in en
            apr = post_create_approval(ApprovalCreateRequest(check_request=yellow_req), lang="ru")
            assert apr.check.headline == t("headline.yellow", "ru")

            listed_kk = get_approvals(bin=None, iik=None, lang="kk")
            assert len(listed_kk) == 1
            assert listed_kk[0].check.headline == t("headline.yellow", "kk")
            assert listed_kk[0].check.headline_ru == t("headline.yellow", "ru")
            assert listed_kk[0].check.signals[0].reason == t("rule.iik_changed", "kk")

            # Localized 422 when trust comment is too short
            with pytest.raises(HTTPException) as exc_info:
                post_approval_decision(
                    apr.id,
                    ApprovalDecisionRequest(
                        decision="approved",
                        director_comment="short",
                        trust_account=True,
                    ),
                    lang="en",
                )
            assert exc_info.value.status_code == 422
            assert exc_info.value.detail == t("error.trust_comment_required", "en")

            # Localized 404 for unknown approval in kk
            with pytest.raises(HTTPException) as exc_404:
                post_approval_decision(
                    "apr-missing",
                    ApprovalDecisionRequest(decision="rejected"),
                    lang="kk",
                )
            assert exc_404.value.status_code == 404
            assert exc_404.value.detail == t("error.approval_not_found", "kk")

            # Localized validation error formatting
            for lang_code in ("ru", "kk", "en"):
                lang_typed: Lang = lang_code
                _, msg = _format_validation_message(
                    {"loc": ("query", "lang"), "type": "literal_error", "ctx": {"expected": "'ru', 'kk' or 'en'"}},
                    lang_typed,
                )
                assert field_label("lang", lang_typed) in msg
        finally:
            store.reset()
