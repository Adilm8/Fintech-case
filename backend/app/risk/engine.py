"""Risk engine orchestrating prechecks, rules, score aggregation, diffs, and verdicts."""

from __future__ import annotations

import statistics
import uuid
from datetime import date
from typing import Any

from app.i18n import DEFAULT_LANG, Lang, t
from app.risk.config import (
    AMPLIFIER_ONLY_CAP,
    DEMO_TODAY,
    SINGLE_SIGNAL_NO_RAISE_MAX,
    THRESHOLD_RED,
    THRESHOLD_YELLOW,
)
from app.risk.names import find_mixed_script_positions
from app.risk.rules import (
    compute_client_p90,
    find_lookalike_supplier,
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
from app.schemas import (
    ActionType,
    CheckRequest,
    CheckResult,
    FieldDiff,
    HistorySummary,
    NextAction,
    Signal,
    Verdict,
)
from app.store import Store

HEADLINES_RU: dict[Verdict, str] = {
    "green": t("headline.green", "ru"),
    "yellow": t("headline.yellow", "ru"),
    "red": t("headline.red", "ru"),
    "grey": t("headline.grey", "ru"),
    "invalid": t("headline.invalid", "ru"),
}

GREEN_WITH_AMPLIFIERS_HEADLINE_RU: str = t("headline.green_with_amplifiers", "ru")
TRUSTED_HEADLINE_RU: str = t("headline.green_trusted", "ru")

SEVERITY_RANK: dict[str, int] = {
    "block": 0,
    "primary": 1,
    "amplifier": 2,
    "info": 3,
}


def _format_kzt(amount: float) -> str:
    return f"{round(amount):,} ₸".replace(",", " ")


def _diff_positions(in_invoice: str, in_history: str) -> list[int]:
    """Return 0-based character positions in in_invoice that differ from in_history."""
    return [
        idx for idx, ch in enumerate(in_invoice) if idx >= len(in_history) or ch != in_history[idx]
    ]


def _build_history_summary(
    payments: list[dict[str, Any]],
    *,
    compared_with: str | None = None,
) -> HistorySummary:
    if not payments:
        return HistorySummary(
            payments_count=0,
            last_payment_date=None,
            median_amount_kzt=None,
            compared_with=compared_with,
        )
    amounts = [float(p["amount_kzt"]) for p in payments]
    return HistorySummary(
        payments_count=len(payments),
        last_payment_date=payments[-1]["paid_at"],
        median_amount_kzt=float(statistics.median(amounts)),
        compared_with=compared_with,
    )


def _build_comparison(
    req: CheckRequest,
    store: Store,
    reference_payments: list[dict[str, Any]],
    *,
    has_amount_anomaly: bool,
    is_trusted: bool = False,
) -> list[FieldDiff]:
    """Build FieldDiff rows for name, bin, iik, bik, bank, and amount."""
    last = reference_payments[-1] if reference_payments else None
    last_seen = last["paid_at"] if last is not None else None

    invoice_bank = store.get_bank_name_by_bik(req.recipient_bik) or req.recipient_bik
    history_bank = (
        (store.get_bank_name_by_bik(last["recipient_bik"]) or last["recipient_bik"])
        if last is not None
        else None
    )

    invoice_amount = _format_kzt(req.amount_kzt)
    history_amount = _format_kzt(float(last["amount_kzt"])) if last is not None else None
    amount_differs = False
    if last is not None:
        last_amt = float(last["amount_kzt"])
        amount_differs = has_amount_anomaly or (
            last_amt > 0 and abs(req.amount_kzt - last_amt) / last_amt >= 0.25
        )

    mixed_name_positions = find_mixed_script_positions(req.recipient_name)
    name_differs = bool(mixed_name_positions) or (
        last is not None and req.recipient_name != last["recipient_name"]
    )

    iik_differs = not is_trusted and last is not None and req.recipient_iik != last["recipient_iik"]
    iik_diff_pos = (
        _diff_positions(req.recipient_iik, last["recipient_iik"])
        if iik_differs and last is not None
        else []
    )
    bik_differs = not is_trusted and last is not None and req.recipient_bik != last["recipient_bik"]
    bank_differs = not is_trusted and last is not None and invoice_bank != history_bank

    return [
        FieldDiff(
            field="name",
            in_invoice=req.recipient_name,
            in_history=last["recipient_name"] if last is not None else None,
            last_seen=last_seen,
            differs=name_differs,
            diff_positions=mixed_name_positions,
        ),
        FieldDiff(
            field="bin",
            in_invoice=req.recipient_bin,
            in_history=last["recipient_bin"] if last is not None else None,
            last_seen=last_seen,
            differs=last is not None and req.recipient_bin != last["recipient_bin"],
        ),
        FieldDiff(
            field="iik",
            in_invoice=req.recipient_iik,
            in_history=last["recipient_iik"] if last is not None else None,
            last_seen=last_seen,
            differs=iik_differs,
            diff_positions=iik_diff_pos,
        ),
        FieldDiff(
            field="bik",
            in_invoice=req.recipient_bik,
            in_history=last["recipient_bik"] if last is not None else None,
            last_seen=last_seen,
            differs=bik_differs,
        ),
        FieldDiff(
            field="bank",
            in_invoice=invoice_bank,
            in_history=history_bank,
            last_seen=last_seen,
            differs=bank_differs,
        ),
        FieldDiff(
            field="amount",
            in_invoice=invoice_amount,
            in_history=history_amount,
            last_seen=last_seen,
            differs=amount_differs,
        ),
    ]


def _select_headline_key(
    verdict: Verdict,
    *,
    is_trusted: bool = False,
    has_amplifiers: bool = False,
) -> str:
    if is_trusted and verdict == "green":
        return "headline.green_trusted"
    if verdict == "green" and has_amplifiers:
        return "headline.green_with_amplifiers"
    return f"headline.{verdict}"


def _select_next_action_spec(
    verdict: Verdict,
    *,
    has_amplifiers: bool = False,
    grey_above_client_p90: bool = False,
) -> tuple[str, ActionType, list[ActionType]]:
    if verdict == "green":
        if has_amplifiers:
            return "next_action.green_with_amplifiers", "sign", []
        return "next_action.green", "sign", []
    if verdict == "yellow":
        return "next_action.yellow", "send_to_director", ["sign"]
    if verdict == "red":
        return "next_action.red", "postpone", ["send_to_director"]
    if verdict == "grey":
        if grey_above_client_p90:
            return "next_action.grey_above_p90", "send_to_director", ["sign"]
        return "next_action.grey", "sign", ["send_to_director"]
    return "next_action.invalid", "postpone", []


def _build_next_action(
    verdict: Verdict,
    *,
    has_amplifiers: bool = False,
    grey_above_client_p90: bool = False,
    lang: Lang = DEFAULT_LANG,
) -> NextAction:
    msg_key, primary, secondary = _select_next_action_spec(
        verdict,
        has_amplifiers=has_amplifiers,
        grey_above_client_p90=grey_above_client_p90,
    )
    return NextAction(
        text_ru=t(msg_key, "ru"),
        text=t(msg_key, lang),
        message_key=msg_key,
        primary=primary,
        secondary=secondary,
    )


def localize_check_result(result: CheckResult, lang: Lang = DEFAULT_LANG) -> CheckResult:
    """Return a copy of CheckResult with localized headline, signals, and next_action text."""
    localized_headline = (
        t(result.headline_key, lang) if result.headline_key else result.headline_ru
    )
    localized_signals = [
        sig.model_copy(
            update={
                "reason": (
                    t(sig.message_key, lang, **sig.message_params)
                    if sig.message_key
                    else sig.reason_ru
                )
            }
        )
        for sig in result.signals
    ]
    localized_next_action = result.next_action.model_copy(
        update={
            "text": (
                t(result.next_action.message_key, lang)
                if result.next_action.message_key
                else result.next_action.text_ru
            )
        }
    )
    return result.model_copy(
        update={
            "headline": localized_headline,
            "signals": localized_signals,
            "next_action": localized_next_action,
        }
    )


def aggregate_signals(signals: list[Signal]) -> tuple[Verdict, int]:
    """Aggregate rule signals into (verdict, score) respecting caps and floor guards."""
    if any(s.severity == "block" for s in signals):
        return "red", 100

    primary_signals = [s for s in signals if s.severity == "primary"]
    amplifier_signals = [s for s in signals if s.severity == "amplifier"]
    scored_signals = primary_signals + amplifier_signals
    is_first_payment = any(s.rule_id == "first_payment" for s in signals)

    if not primary_signals:
        score = min(sum(s.points for s in amplifier_signals), AMPLIFIER_ONLY_CAP)
    else:
        score = min(100, sum(s.points for s in scored_signals))

    # A single signal <= 25 points alone must never raise colour.
    if len(scored_signals) == 1 and scored_signals[0].points <= SINGLE_SIGNAL_NO_RAISE_MAX:
        score = min(score, THRESHOLD_YELLOW - 1)

    if score >= THRESHOLD_RED:
        return "red", score
    if score >= THRESHOLD_YELLOW:
        return "yellow", score
    if is_first_payment:
        return "grey", score
    return "green", score


def _sort_signals(signals: list[Signal]) -> list[Signal]:
    return sorted(
        signals,
        key=lambda s: (-s.points, SEVERITY_RANK.get(s.severity, 99), s.rule_id),
    )


def check_payment(
    req: CheckRequest,
    store: Store,
    *,
    today: date = DEMO_TODAY,
    lang: Lang = DEFAULT_LANG,
) -> CheckResult:
    """Run prechecks, risk rules, aggregation, and comparison for a payment request."""
    check_id = f"chk-{uuid.uuid4().hex[:12]}"
    effective_payer_id = store.resolve_payer_id(req.payer_id)
    effective_req = (
        req
        if req.payer_id == effective_payer_id
        else req.model_copy(update={"payer_id": effective_payer_id})
    )
    supplier_history = store.get_supplier_history(effective_req.recipient_bin, effective_payer_id)

    # 1. Precheck (no scoring; any failure yields invalid)
    precheck_signals: list[Signal] = []
    for sig in (
        rule_bin_format(effective_req, lang=lang),
        rule_iik_format(effective_req, store, lang=lang),
        rule_bik_format(effective_req, store, lang=lang),
    ):
        if sig is not None:
            precheck_signals.append(sig)

    if not precheck_signals:
        bank_match_sig = rule_iik_bank_code_vs_bik(effective_req, store, lang=lang)
        if bank_match_sig is not None:
            precheck_signals.append(bank_match_sig)

    if precheck_signals:
        headline_key = _select_headline_key("invalid")
        return CheckResult(
            check_id=check_id,
            verdict="invalid",
            score=0,
            headline_ru=t(headline_key, "ru"),
            headline=t(headline_key, lang),
            headline_key=headline_key,
            signals=precheck_signals,
            comparison=_build_comparison(
                effective_req,
                store,
                supplier_history,
                has_amount_anomaly=False,
                is_trusted=False,
            ),
            next_action=_build_next_action("invalid", lang=lang),
            history=_build_history_summary(supplier_history),
            trusted=False,
            trusted_info=None,
        )

    # 2. Identify comparison / anomaly / summary reference history (direct BIN or lookalike)
    lookalike_match = find_lookalike_supplier(effective_req, store)
    if supplier_history:
        reference_bin = effective_req.recipient_bin
        comparison_history = supplier_history
        history_summary = _build_history_summary(supplier_history)
    elif lookalike_match is not None:
        reference_bin = lookalike_match["bin"]
        comparison_history = store.get_supplier_history(lookalike_match["bin"], effective_payer_id)
        history_summary = _build_history_summary(
            comparison_history,
            compared_with=lookalike_match["name"],
        )
    else:
        reference_bin = effective_req.recipient_bin
        comparison_history = []
        history_summary = _build_history_summary([])

    # 3. Check director trust and evaluate all risk rules
    trusted_info = store.get_trusted_info(
        effective_payer_id,
        effective_req.recipient_bin,
        effective_req.recipient_iik,
    )
    is_trusted = trusted_info is not None

    candidates: list[Signal | None] = [
        rule_bcc_account_other_owner(effective_req, store, lang=lang),
        rule_lookalike_supplier(effective_req, store, lang=lang),
        rule_bin_name_mismatch(effective_req, store, lang=lang),
        rule_iik_belongs_to_other_counterparty(effective_req, store, lang=lang),
        rule_iik_changed(effective_req, store, lang=lang),
        rule_bank_changed(effective_req, store, lang=lang),
        rule_entity_type_mismatch(effective_req, lang=lang),
        rule_mixed_script_name(effective_req, lang=lang),
        rule_new_bcc_account(effective_req, store, today=today, lang=lang),
        rule_bin_young(effective_req, today=today, lang=lang),
        rule_amount_anomaly(effective_req, store, reference_bin=reference_bin, lang=lang),
        rule_first_payment(effective_req, store, lang=lang),
        rule_urgent_wording(effective_req, lang=lang),
        rule_trusted_account(effective_req, store, lang=lang),
    ]
    all_signals = [s for s in candidates if s is not None]

    # 4. Aggregate score and verdict; return ALL signals sorted by points (M9)
    verdict, score = aggregate_signals(all_signals)
    ordered_signals = _sort_signals(all_signals)

    has_amount_anomaly = any(s.rule_id == "amount_anomaly" for s in all_signals)
    has_amplifiers = any(s.severity == "amplifier" for s in all_signals)

    client_p90 = compute_client_p90(store, effective_payer_id) if verdict == "grey" else None
    grey_above_client_p90 = (
        verdict == "grey" and client_p90 is not None and effective_req.amount_kzt > client_p90
    )

    headline_key = _select_headline_key(
        verdict,
        is_trusted=is_trusted,
        has_amplifiers=has_amplifiers,
    )

    return CheckResult(
        check_id=check_id,
        verdict=verdict,
        score=score,
        headline_ru=t(headline_key, "ru"),
        headline=t(headline_key, lang),
        headline_key=headline_key,
        signals=ordered_signals,
        comparison=_build_comparison(
            effective_req,
            store,
            comparison_history,
            has_amount_anomaly=has_amount_anomaly,
            is_trusted=is_trusted,
        ),
        next_action=_build_next_action(
            verdict,
            has_amplifiers=has_amplifiers,
            grey_above_client_p90=grey_above_client_p90,
            lang=lang,
        ),
        history=history_summary,
        trusted=is_trusted,
        trusted_info=trusted_info,
    )
