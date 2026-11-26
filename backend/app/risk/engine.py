"""Risk engine orchestrating prechecks, rules, score aggregation, diffs, and verdicts."""

from __future__ import annotations

import statistics
import uuid
from datetime import date
from typing import Any

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
    "green": "Всё как раньше",
    "yellow": "Есть изменения",
    "red": "Похоже на подмену",
    "grey": "Нет истории для сравнения",
    "invalid": "Ошибка в реквизитах",
}

GREEN_WITH_AMPLIFIERS_HEADLINE_RU: str = "Реквизиты знакомые, но есть замечания"
TRUSTED_HEADLINE_RU: str = "Счёт подтверждён директором"

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


def _build_next_action(
    verdict: Verdict,
    *,
    has_amplifiers: bool = False,
    grey_above_client_p90: bool = False,
) -> NextAction:
    if verdict == "green":
        if has_amplifiers:
            return NextAction(
                text_ru=(
                    "Реквизиты поставщика знакомые, но проверьте замечания ниже перед подписанием."
                ),
                primary="sign",
                secondary=[],
            )
        return NextAction(
            text_ru="Реквизиты и сумма совпадают с вашей историей платежей — можно подписывать.",
            primary="sign",
            secondary=[],
        )
    if verdict == "yellow":
        return NextAction(
            text_ru=(
                "Позвоните поставщику по номеру из договора, "
                "а не из письма с новыми реквизитами, и подтвердите счёт."
            ),
            primary="send_to_director",
            secondary=["sign"],
        )
    if verdict == "red":
        return NextAction(
            text_ru=(
                "Не подписывайте платёж. Позвоните поставщику по номеру из договора, "
                "а не из письма с новыми реквизитами."
            ),
            primary="postpone",
            secondary=["send_to_director"],
        )
    if verdict == "grey":
        if grey_above_client_p90:
            return NextAction(
                text_ru=(
                    "Крупный первый платёж новому поставщику: проверьте БИН в реестре, "
                    "подтвердите реквизиты по телефону из договора и согласуйте с директором."
                ),
                primary="send_to_director",
                secondary=["sign"],
            )
        return NextAction(
            text_ru="Проверьте БИН поставщика в реестре и подтвердите реквизиты по телефону из договора.",
            primary="sign",
            secondary=["send_to_director"],
        )
    return NextAction(
        text_ru="Исправьте реквизиты: такого счёта не существует.",
        primary="postpone",
        secondary=[],
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
        rule_bin_format(effective_req),
        rule_iik_format(effective_req, store),
        rule_bik_format(effective_req, store),
    ):
        if sig is not None:
            precheck_signals.append(sig)

    if not precheck_signals:
        bank_match_sig = rule_iik_bank_code_vs_bik(effective_req, store)
        if bank_match_sig is not None:
            precheck_signals.append(bank_match_sig)

    if precheck_signals:
        return CheckResult(
            check_id=check_id,
            verdict="invalid",
            score=0,
            headline_ru=HEADLINES_RU["invalid"],
            signals=precheck_signals,
            comparison=_build_comparison(
                effective_req,
                store,
                supplier_history,
                has_amount_anomaly=False,
                is_trusted=False,
            ),
            next_action=_build_next_action("invalid"),
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
        rule_bcc_account_other_owner(effective_req, store),
        rule_lookalike_supplier(effective_req, store),
        rule_bin_name_mismatch(effective_req, store),
        rule_iik_belongs_to_other_counterparty(effective_req, store),
        rule_iik_changed(effective_req, store),
        rule_bank_changed(effective_req, store),
        rule_entity_type_mismatch(effective_req),
        rule_mixed_script_name(effective_req),
        rule_new_bcc_account(effective_req, store, today=today),
        rule_bin_young(effective_req, today=today),
        rule_amount_anomaly(effective_req, store, reference_bin=reference_bin),
        rule_first_payment(effective_req, store),
        rule_urgent_wording(effective_req),
        rule_trusted_account(effective_req, store),
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

    if is_trusted and verdict == "green":
        headline_ru = TRUSTED_HEADLINE_RU
    elif verdict == "green" and has_amplifiers:
        headline_ru = GREEN_WITH_AMPLIFIERS_HEADLINE_RU
    else:
        headline_ru = HEADLINES_RU[verdict]

    return CheckResult(
        check_id=check_id,
        verdict=verdict,
        score=score,
        headline_ru=headline_ru,
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
        ),
        history=history_summary,
        trusted=is_trusted,
        trusted_info=trusted_info,
    )
