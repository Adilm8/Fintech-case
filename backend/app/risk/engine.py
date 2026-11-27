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
    LOOKALIKE_AMOUNT_COMPARE_SIMILARITY,
    RULESET_VERSION,
    SINGLE_SIGNAL_NO_RAISE_MAX,
    THRESHOLD_RED,
    THRESHOLD_YELLOW,
)
from app.risk.names import find_mixed_script_positions
from app.risk.profiles import SupplierProfile, confirm_supplier_accounts, profiles_enabled
from app.risk.rules import (
    build_analyst_details,
    compute_client_p90,
    extract_invoice_number,
    find_lookalike_supplier,
    is_bcc_bank_verified_new_account,
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
    rule_fresh_iik_many_payers,
    rule_iik_bank_code_vs_bik,
    rule_iik_belongs_to_other_counterparty,
    rule_iik_changed,
    rule_iik_format,
    rule_iik_on_watchlist,
    rule_iik_reported_by_clients,
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
from app.schemas import (
    ActionType,
    AnalystDetails,
    CheckRequest,
    CheckResult,
    Evidence,
    FieldDiff,
    HistorySummary,
    NextAction,
    Signal,
    Verdict,
    compute_request_sha256,
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
    """Return 0-based character positions in in_invoice that differ from in_history.

    Returns positions only when at most 4 characters differ; otherwise returns []
    so callers highlight the entire value as a single block.
    """
    positions = [
        idx for idx, ch in enumerate(in_invoice) if idx >= len(in_history) or ch != in_history[idx]
    ]
    total_diffs = len(positions) + max(0, len(in_history) - len(in_invoice))
    if total_diffs > 4:
        return []
    return positions


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

    # Account rows compare with the last confirmed account when the invoice IIK was only paid
    # without confirmation (H1): the table must show the change the signals report.
    acct = last
    if last is not None and any(
        p["recipient_iik"] == req.recipient_iik for p in reference_payments
    ):
        confirmation = confirm_supplier_accounts(reference_payments)
        if req.recipient_iik not in confirmation.known_iiks:
            acct = reference_payments[confirmation.last_known_index]
    acct_seen = acct["paid_at"] if acct is not None else None

    invoice_bank = store.get_bank_name_by_bik(req.recipient_bik) or req.recipient_bik
    history_bank = (
        (store.get_bank_name_by_bik(acct["recipient_bik"]) or acct["recipient_bik"])
        if acct is not None
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

    iik_differs = not is_trusted and acct is not None and req.recipient_iik != acct["recipient_iik"]
    iik_diff_pos = (
        _diff_positions(req.recipient_iik, acct["recipient_iik"])
        if iik_differs and acct is not None
        else []
    )
    bik_differs = not is_trusted and acct is not None and req.recipient_bik != acct["recipient_bik"]
    bank_differs = not is_trusted and acct is not None and invoice_bank != history_bank

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
            in_history=acct["recipient_iik"] if acct is not None else None,
            last_seen=acct_seen,
            differs=iik_differs,
            diff_positions=iik_diff_pos,
        ),
        FieldDiff(
            field="bik",
            in_invoice=req.recipient_bik,
            in_history=acct["recipient_bik"] if acct is not None else None,
            last_seen=acct_seen,
            differs=bik_differs,
        ),
        FieldDiff(
            field="bank",
            in_invoice=invoice_bank,
            in_history=history_bank,
            last_seen=acct_seen,
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


def _build_history_summary_from_profile(
    profile: SupplierProfile | None,
    *,
    compared_with: str | None = None,
) -> HistorySummary:
    if profile is None:
        return HistorySummary(
            payments_count=0,
            last_payment_date=None,
            median_amount_kzt=None,
            compared_with=compared_with,
        )
    return HistorySummary(
        payments_count=profile.payments_count,
        last_payment_date=profile.last_paid_at,
        median_amount_kzt=profile.amount_median,
        compared_with=compared_with,
    )


def _build_comparison_from_profile(
    req: CheckRequest,
    store: Store,
    reference_profile: SupplierProfile | None,
    *,
    has_amount_anomaly: bool,
    is_trusted: bool = False,
) -> list[FieldDiff]:
    """Build FieldDiff rows from a cached SupplierProfile without scanning history."""
    last_seen = reference_profile.last_paid_at if reference_profile is not None else None
    invoice_bank = store.get_bank_name_by_bik(req.recipient_bik) or req.recipient_bik
    # Account rows compare with the last confirmed account when the invoice IIK was only paid
    # without confirmation (H1): the table must show the change the signals report.
    hist_iik: str | None = None
    hist_bik: str | None = None
    history_bank: str | None = None
    acct_seen: str | None = None
    if reference_profile is not None:
        if (
            req.recipient_iik in reference_profile.seen_iiks
            and req.recipient_iik not in reference_profile.known_iiks
        ):
            hist_iik = reference_profile.last_known_iik
            hist_bik = reference_profile.last_known_bik
            history_bank = reference_profile.last_known_bank
            acct_seen = reference_profile.last_known_paid_at
        else:
            hist_iik = reference_profile.last_iik
            hist_bik = reference_profile.last_bik
            history_bank = reference_profile.last_bank
            acct_seen = last_seen

    invoice_amount = _format_kzt(req.amount_kzt)
    history_amount = (
        _format_kzt(reference_profile.last_amount_kzt) if reference_profile is not None else None
    )
    amount_differs = False
    if reference_profile is not None:
        last_amt = reference_profile.last_amount_kzt
        amount_differs = has_amount_anomaly or (
            last_amt > 0 and abs(req.amount_kzt - last_amt) / last_amt >= 0.25
        )

    mixed_name_positions = find_mixed_script_positions(req.recipient_name)
    name_differs = bool(mixed_name_positions) or (
        reference_profile is not None and req.recipient_name != reference_profile.last_name
    )

    iik_differs = not is_trusted and hist_iik is not None and req.recipient_iik != hist_iik
    iik_diff_pos = (
        _diff_positions(req.recipient_iik, hist_iik) if iik_differs and hist_iik is not None else []
    )
    bik_differs = not is_trusted and hist_bik is not None and req.recipient_bik != hist_bik
    bank_differs = not is_trusted and reference_profile is not None and invoice_bank != history_bank

    return [
        FieldDiff(
            field="name",
            in_invoice=req.recipient_name,
            in_history=reference_profile.last_name if reference_profile is not None else None,
            last_seen=last_seen,
            differs=name_differs,
            diff_positions=mixed_name_positions,
        ),
        FieldDiff(
            field="bin",
            in_invoice=req.recipient_bin,
            in_history=reference_profile.recipient_bin if reference_profile is not None else None,
            last_seen=last_seen,
            differs=(
                reference_profile is not None
                and req.recipient_bin != reference_profile.recipient_bin
            ),
        ),
        FieldDiff(
            field="iik",
            in_invoice=req.recipient_iik,
            in_history=hist_iik,
            last_seen=acct_seen,
            differs=iik_differs,
            diff_positions=iik_diff_pos,
        ),
        FieldDiff(
            field="bik",
            in_invoice=req.recipient_bik,
            in_history=hist_bik,
            last_seen=acct_seen,
            differs=bik_differs,
        ),
        FieldDiff(
            field="bank",
            in_invoice=invoice_bank,
            in_history=history_bank,
            last_seen=acct_seen,
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


AMOUNT_SIGNAL_IDS: frozenset[str] = frozenset(
    {"amount_anomaly", "structuring_72h", "new_recipient_accumulated"}
)


def _extract_invalid_field_keys(precheck_signals: list[Signal]) -> list[str]:
    keys: list[str] = []
    for sig in precheck_signals:
        if sig.rule_id == "invalid_bin":
            mapped = ["bin"]
        elif sig.rule_id in ("invalid_iik", "bcc_account_not_found"):
            mapped = ["iik"]
        elif sig.rule_id == "invalid_bik":
            mapped = ["bik"]
        elif sig.rule_id == "iik_bank_code_vs_bik":
            mapped = ["iik", "bik"]
        else:
            mapped = []
        for k in mapped:
            if k not in keys:
                keys.append(k)
    return keys


def _render_invalid_fields_text(field_keys: list[str], lang: Lang) -> str:
    if not field_keys:
        return t("next_action.invalid", lang)
    labels = ", ".join(t(f"invalid_field.{k}", lang) for k in field_keys)
    return t("next_action.invalid_fields", lang, fields=labels)


def _select_headline_key(
    verdict: Verdict,
    *,
    is_trusted: bool = False,
    is_bank_verified: bool = False,
    has_amplifiers: bool = False,
) -> str:
    if is_trusted and verdict == "green":
        return "headline.green_trusted"
    if is_bank_verified and verdict == "green":
        return "headline.green_bank_verified"
    if verdict == "green" and has_amplifiers:
        return "headline.green_with_amplifiers"
    return f"headline.{verdict}"


def _select_next_action_spec(
    verdict: Verdict,
    *,
    signals: list[Signal] | None = None,
    is_bank_verified: bool = False,
    has_amplifiers: bool = False,
    grey_above_client_p90: bool = False,
) -> tuple[str, ActionType, list[ActionType]]:
    ordered = signals or []
    scored = [s for s in ordered if s.severity in ("block", "primary", "amplifier")]
    scored_ids = {s.rule_id for s in scored}

    if verdict == "green":
        if is_bank_verified and not has_amplifiers:
            return "next_action.green_bank_verified", "sign", []
        if has_amplifiers:
            return "next_action.green_with_amplifiers", "sign", []
        return "next_action.green", "sign", []
    if verdict == "yellow":
        if scored_ids and scored_ids <= AMOUNT_SIGNAL_IDS:
            return "next_action.amount_only", "send_to_director", ["sign"]
        if (
            ordered
            and ordered[0].rule_id == "duplicate_invoice"
            and "iik_changed" not in scored_ids
            and "bank_changed" not in scored_ids
        ):
            return "next_action.duplicate_invoice", "send_to_director", ["sign"]
        return "next_action.yellow", "send_to_director", ["sign"]
    if verdict == "red":
        if scored_ids and scored_ids <= AMOUNT_SIGNAL_IDS:
            return "next_action.amount_only", "postpone", ["send_to_director"]
        return "next_action.red", "postpone", ["send_to_director"]
    if verdict == "grey":
        if grey_above_client_p90:
            return "next_action.grey_above_p90", "send_to_director", ["sign"]
        return "next_action.grey", "sign", ["send_to_director"]
    return "next_action.invalid", "postpone", []


def _build_next_action(
    verdict: Verdict,
    *,
    signals: list[Signal] | None = None,
    is_bank_verified: bool = False,
    has_amplifiers: bool = False,
    grey_above_client_p90: bool = False,
    lang: Lang = DEFAULT_LANG,
) -> NextAction:
    if verdict == "invalid":
        field_keys = _extract_invalid_field_keys(signals or [])
        if field_keys:
            return NextAction(
                text_ru=_render_invalid_fields_text(field_keys, "ru"),
                text=_render_invalid_fields_text(field_keys, lang),
                message_key="next_action.invalid_fields",
                invalid_field_keys=field_keys,
                primary="postpone",
                secondary=[],
            )
    msg_key, primary, secondary = _select_next_action_spec(
        verdict,
        signals=signals,
        is_bank_verified=is_bank_verified,
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


def _localize_evidence(ev: Evidence, lang: Lang) -> Evidence:
    field_lbl = (
        t(f"ev.field.{ev.field}", lang)
        if ev.field in ("bin", "iik", "bik", "bank", "name", "amount", "purpose")
        else ev.field_label
    )
    expected = t(ev.expected_key, lang, **ev.expected_params) if ev.expected_key else ev.expected
    actual = t(ev.actual_key, lang, **ev.actual_params) if ev.actual_key else ev.actual
    return ev.model_copy(
        update={
            "field_label": field_lbl,
            "expected": expected,
            "actual": actual,
        }
    )


def _localize_analyst_details(
    details: AnalystDetails | None,
    lang: Lang,
) -> AnalystDetails | None:
    if details is None:
        return None
    localized_signal_details = [
        item.model_copy(
            update={
                "reason": (
                    t(item.message_key, lang, **item.message_params)
                    if item.message_key
                    else item.reason_ru
                ),
                "evidence": _localize_evidence(item.evidence, lang),
            }
        )
        for item in details.signal_details
    ]
    return details.model_copy(update={"signal_details": localized_signal_details})


def localize_check_result(
    result: CheckResult,
    lang: Lang = DEFAULT_LANG,
    *,
    include_analyst_details: bool | None = None,
) -> CheckResult:
    """Return a copy of CheckResult with localized texts and role-appropriate analyst_details."""
    localized_headline = t(result.headline_key, lang) if result.headline_key else result.headline_ru
    localized_signals = [
        sig.model_copy(
            update={
                "reason": (
                    t(sig.message_key, lang, **sig.message_params)
                    if sig.message_key
                    else sig.reason_ru
                ),
                "evidence": _localize_evidence(sig.evidence, lang),
            }
        )
        for sig in result.signals
    ]
    if result.next_action.invalid_field_keys:
        next_text = _render_invalid_fields_text(result.next_action.invalid_field_keys, lang)
    elif result.next_action.message_key:
        next_text = t(
            result.next_action.message_key,
            lang,
            **result.next_action.message_params,
        )
    else:
        next_text = result.next_action.text_ru
    localized_next_action = result.next_action.model_copy(update={"text": next_text})
    source_analyst = result.internal_analyst_details or result.analyst_details
    localized_internal_analyst = _localize_analyst_details(source_analyst, lang)
    show_analyst = (
        result.analyst_details is not None
        if include_analyst_details is None
        else include_analyst_details
    )
    return result.model_copy(
        update={
            "headline": localized_headline,
            "signals": localized_signals,
            "next_action": localized_next_action,
            "analyst_details": localized_internal_analyst if show_analyst else None,
            "internal_analyst_details": localized_internal_analyst,
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
    has_urgent_first = is_first_payment and any(s.rule_id == "urgent_wording" for s in signals)

    if not primary_signals:
        raw_amp = sum(s.points for s in amplifier_signals)
        if has_urgent_first:
            score = min(100, max(raw_amp, THRESHOLD_YELLOW))
        else:
            score = min(raw_amp, AMPLIFIER_ONLY_CAP)
    else:
        score = min(100, sum(s.points for s in scored_signals))

    # A single signal <= 25 points alone must never raise colour (except first_payment + urgent).
    if (
        not has_urgent_first
        and len(scored_signals) == 1
        and scored_signals[0].points <= SINGLE_SIGNAL_NO_RAISE_MAX
    ):
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
    include_analyst_details: bool = False,
    include_recent_memory: bool = True,
    record_in_memory: bool = False,
) -> CheckResult:
    """Run prechecks, risk rules, aggregation, and comparison for a payment request."""
    check_id = f"chk-{uuid.uuid4().hex[:12]}"
    effective_payer_id = store.resolve_payer_id(req.payer_id)
    effective_req = (
        req
        if req.payer_id == effective_payer_id
        else req.model_copy(update={"payer_id": effective_payer_id})
    )
    use_profiles = profiles_enabled()
    profiles = store.get_profiles(effective_payer_id) if use_profiles else None
    supplier_profile = (
        profiles.get_supplier(effective_req.recipient_bin) if profiles is not None else None
    )
    supplier_history = (
        []
        if use_profiles
        else store.get_supplier_history(effective_req.recipient_bin, effective_payer_id)
    )

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

    if not precheck_signals:
        bcc_missing_sig = rule_bcc_account_not_found(effective_req, store, lang=lang)
        if bcc_missing_sig is not None:
            precheck_signals.append(bcc_missing_sig)

    if precheck_signals:
        headline_key = _select_headline_key("invalid")
        empty_analyst = AnalystDetails()
        precheck_comparison = (
            _build_comparison_from_profile(
                effective_req,
                store,
                supplier_profile,
                has_amount_anomaly=False,
                is_trusted=False,
            )
            if use_profiles
            else _build_comparison(
                effective_req,
                store,
                supplier_history,
                has_amount_anomaly=False,
                is_trusted=False,
            )
        )
        precheck_history = (
            _build_history_summary_from_profile(supplier_profile)
            if use_profiles
            else _build_history_summary(supplier_history)
        )
        return CheckResult(
            check_id=check_id,
            verdict="invalid",
            score=0,
            headline_ru=t(headline_key, "ru"),
            headline=t(headline_key, lang),
            headline_key=headline_key,
            signals=precheck_signals,
            comparison=precheck_comparison,
            next_action=_build_next_action("invalid", signals=precheck_signals, lang=lang),
            history=precheck_history,
            trusted=False,
            trusted_info=None,
            analyst_details=empty_analyst if include_analyst_details else None,
            internal_analyst_details=empty_analyst,
        )

    # 1b. Verified state/budget treasury payment (KKMFKZ2A / GCVPKZ2A) -> green fast-path
    if store.is_budget_bank(effective_req.recipient_bik):
        headline_key = "headline.green_budget"
        next_key = "next_action.green_budget"
        empty_analyst = AnalystDetails()
        budget_comparison = (
            _build_comparison_from_profile(
                effective_req,
                store,
                supplier_profile,
                has_amount_anomaly=False,
                is_trusted=False,
            )
            if use_profiles
            else _build_comparison(
                effective_req,
                store,
                supplier_history,
                has_amount_anomaly=False,
                is_trusted=False,
            )
        )
        budget_history = (
            _build_history_summary_from_profile(supplier_profile)
            if use_profiles
            else _build_history_summary(supplier_history)
        )
        return CheckResult(
            check_id=check_id,
            verdict="green",
            score=0,
            headline_ru=t(headline_key, "ru"),
            headline=t(headline_key, lang),
            headline_key=headline_key,
            signals=[],
            comparison=budget_comparison,
            next_action=NextAction(
                text_ru=t(next_key, "ru"),
                text=t(next_key, lang),
                message_key=next_key,
                primary="sign",
                secondary=[],
            ),
            history=budget_history,
            trusted=False,
            trusted_info=None,
            analyst_details=empty_analyst if include_analyst_details else None,
            internal_analyst_details=empty_analyst,
        )

    # 2. Identify comparison / anomaly / summary reference history (direct BIN or lookalike)
    lookalike_match = find_lookalike_supplier(effective_req, store, profiles=profiles)
    comparison_profile: SupplierProfile | None = None
    comparison_history: list[dict[str, Any]] = []
    if use_profiles:
        assert profiles is not None
        if supplier_profile is not None:
            amount_reference_bin = effective_req.recipient_bin
            comparison_profile = supplier_profile
            history_summary = _build_history_summary_from_profile(supplier_profile)
        elif lookalike_match is not None:
            comparison_profile = profiles.get_supplier(lookalike_match["bin"])
            history_summary = _build_history_summary_from_profile(
                comparison_profile,
                compared_with=lookalike_match["name"],
            )
            # Only compare payment amount against matched supplier history when name similarity >= 92;
            # otherwise fall back to overall client profile (p90) to avoid distorted ratios.
            if float(lookalike_match.get("similarity", 0.0)) >= LOOKALIKE_AMOUNT_COMPARE_SIMILARITY:
                amount_reference_bin = lookalike_match["bin"]
            else:
                amount_reference_bin = effective_req.recipient_bin
        else:
            amount_reference_bin = effective_req.recipient_bin
            history_summary = _build_history_summary_from_profile(None)
    elif supplier_history:
        amount_reference_bin = effective_req.recipient_bin
        comparison_history = supplier_history
        history_summary = _build_history_summary(supplier_history)
    elif lookalike_match is not None:
        comparison_history = store.get_supplier_history(lookalike_match["bin"], effective_payer_id)
        history_summary = _build_history_summary(
            comparison_history,
            compared_with=lookalike_match["name"],
        )
        # Only compare payment amount against matched supplier history when name similarity >= 92;
        # otherwise fall back to overall client profile (p90) to avoid distorted ratios.
        if float(lookalike_match.get("similarity", 0.0)) >= LOOKALIKE_AMOUNT_COMPARE_SIMILARITY:
            amount_reference_bin = lookalike_match["bin"]
        else:
            amount_reference_bin = effective_req.recipient_bin
    else:
        amount_reference_bin = effective_req.recipient_bin
        comparison_history = []
        history_summary = _build_history_summary([])

    # 3. Check director trust, BCC bank verification, and evaluate all risk rules
    trusted_info = store.get_trusted_info(
        effective_payer_id,
        effective_req.recipient_bin,
        effective_req.recipient_iik,
    )
    is_trusted = trusted_info is not None
    is_bank_verified = is_bcc_bank_verified_new_account(effective_req, store, profiles=profiles)

    lookalike_sig = (
        rule_lookalike_supplier(
            effective_req,
            store,
            lang=lang,
            profiles=profiles,
            lookalike_match=lookalike_match,
        )
        if use_profiles
        else rule_lookalike_supplier(effective_req, store, lang=lang)
    )
    candidates: list[Signal | None] = [
        rule_bcc_account_other_owner(effective_req, store, lang=lang),
        rule_iik_on_watchlist(effective_req, store, lang=lang),
        rule_iik_reported_by_clients(effective_req, store, lang=lang),
        rule_fresh_iik_many_payers(effective_req, store, today=today, lang=lang),
        lookalike_sig,
        rule_bin_name_mismatch(effective_req, store, lang=lang, profiles=profiles),
        rule_iik_belongs_to_other_counterparty(effective_req, store, lang=lang, profiles=profiles),
        rule_iik_changed(effective_req, store, lang=lang, profiles=profiles),
        rule_bank_changed(effective_req, store, lang=lang, profiles=profiles),
        rule_entity_type_mismatch(effective_req, lang=lang),
        rule_kbe_mismatch(effective_req, lang=lang),
        rule_knp_unusual(effective_req, store, lang=lang, profiles=profiles),
        rule_mixed_script_name(effective_req, lang=lang),
        rule_new_bcc_account(effective_req, store, today=today, lang=lang),
        rule_bin_young(effective_req, today=today, lang=lang),
        rule_amount_anomaly(
            effective_req,
            store,
            reference_bin=amount_reference_bin,
            lang=lang,
            profiles=profiles,
        ),
        rule_duplicate_invoice(
            effective_req,
            store,
            today=today,
            lang=lang,
            include_recent_memory=include_recent_memory,
            profiles=profiles,
        ),
        rule_new_recipient_accumulated(
            effective_req,
            store,
            today=today,
            lang=lang,
            include_recent_memory=include_recent_memory,
            profiles=profiles,
        ),
        rule_structuring_72h(
            effective_req,
            store,
            today=today,
            lang=lang,
            include_recent_memory=include_recent_memory,
            profiles=profiles,
        ),
        rule_first_payment(effective_req, store, lang=lang, profiles=profiles),
        rule_urgent_wording(effective_req, lang=lang),
        rule_trusted_account(effective_req, store, lang=lang),
        rule_bcc_owner_verified(effective_req, store, lang=lang, profiles=profiles),
    ]
    all_signals = [s for s in candidates if s is not None]

    # 4. Aggregate score and verdict; return ALL signals sorted by points (M9)
    verdict, score = aggregate_signals(all_signals)
    ordered_signals = _sort_signals(all_signals)

    has_amount_anomaly = any(s.rule_id in AMOUNT_SIGNAL_IDS for s in all_signals)
    has_amplifiers = any(s.severity == "amplifier" for s in all_signals)

    if verdict == "grey":
        client_p90 = (
            profiles.client_p90
            if profiles is not None
            else compute_client_p90(store, effective_payer_id)
        )
    else:
        client_p90 = None
    grey_above_client_p90 = (
        verdict == "grey" and client_p90 is not None and effective_req.amount_kzt > client_p90
    )

    headline_key = _select_headline_key(
        verdict,
        is_trusted=is_trusted,
        is_bank_verified=is_bank_verified,
        has_amplifiers=has_amplifiers,
    )
    analyst_snapshot = build_analyst_details(
        effective_req,
        store,
        ordered_signals,
        today=today,
        lang=lang,
    )

    if record_in_memory:
        store.record_check(
            effective_req,
            invoice_no=extract_invoice_number(effective_req.purpose),
            today=today,
            request_sha256=compute_request_sha256(
                effective_req, resolved_payer_id=effective_payer_id
            ),
        )

    final_comparison = (
        _build_comparison_from_profile(
            effective_req,
            store,
            comparison_profile,
            has_amount_anomaly=has_amount_anomaly,
            is_trusted=is_trusted,
        )
        if use_profiles
        else _build_comparison(
            effective_req,
            store,
            comparison_history,
            has_amount_anomaly=has_amount_anomaly,
            is_trusted=is_trusted,
        )
    )
    return CheckResult(
        check_id=check_id,
        ruleset_version=RULESET_VERSION,
        verdict=verdict,
        score=score,
        headline_ru=t(headline_key, "ru"),
        headline=t(headline_key, lang),
        headline_key=headline_key,
        signals=ordered_signals,
        comparison=final_comparison,
        next_action=_build_next_action(
            verdict,
            signals=ordered_signals,
            is_bank_verified=is_bank_verified,
            has_amplifiers=has_amplifiers,
            grey_above_client_p90=grey_above_client_p90,
            lang=lang,
        ),
        history=history_summary,
        trusted=is_trusted,
        trusted_info=trusted_info,
        analyst_details=analyst_snapshot if include_analyst_details else None,
        internal_analyst_details=analyst_snapshot,
    )
