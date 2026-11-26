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
from app.risk.rules import (
    find_lookalike_supplier,
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


def _build_history_summary(payments: list[dict[str, Any]]) -> HistorySummary:
    if not payments:
        return HistorySummary(
            payments_count=0,
            last_payment_date=None,
            median_amount_kzt=None,
        )
    amounts = [float(p["amount_kzt"]) for p in payments]
    return HistorySummary(
        payments_count=len(payments),
        last_payment_date=payments[-1]["paid_at"],
        median_amount_kzt=float(statistics.median(amounts)),
    )


def _build_comparison(
    req: CheckRequest,
    store: Store,
    reference_payments: list[dict[str, Any]],
    *,
    has_amount_anomaly: bool,
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

    iik_diff_pos = (
        _diff_positions(req.recipient_iik, last["recipient_iik"]) if last is not None else []
    )

    return [
        FieldDiff(
            field="name",
            in_invoice=req.recipient_name,
            in_history=last["recipient_name"] if last is not None else None,
            last_seen=last_seen,
            differs=last is not None and req.recipient_name != last["recipient_name"],
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
            differs=last is not None and req.recipient_iik != last["recipient_iik"],
            diff_positions=iik_diff_pos,
        ),
        FieldDiff(
            field="bik",
            in_invoice=req.recipient_bik,
            in_history=last["recipient_bik"] if last is not None else None,
            last_seen=last_seen,
            differs=last is not None and req.recipient_bik != last["recipient_bik"],
        ),
        FieldDiff(
            field="bank",
            in_invoice=invoice_bank,
            in_history=history_bank,
            last_seen=last_seen,
            differs=last is not None and invoice_bank != history_bank,
        ),
        FieldDiff(
            field="amount",
            in_invoice=invoice_amount,
            in_history=history_amount,
            last_seen=last_seen,
            differs=amount_differs,
        ),
    ]


def _build_next_action(verdict: Verdict) -> NextAction:
    if verdict == "green":
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
    supplier_history = store.get_supplier_history(req.recipient_bin, req.payer_id)

    # 1. Precheck (no scoring; any failure yields invalid)
    precheck_signals: list[Signal] = []
    for sig in (
        rule_bin_format(req),
        rule_iik_format(req),
        rule_bik_format(req, store),
    ):
        if sig is not None:
            precheck_signals.append(sig)

    if not precheck_signals:
        bank_match_sig = rule_iik_bank_code_vs_bik(req, store)
        if bank_match_sig is not None:
            precheck_signals.append(bank_match_sig)

    if precheck_signals:
        return CheckResult(
            check_id=check_id,
            verdict="invalid",
            score=0,
            headline_ru=HEADLINES_RU["invalid"],
            signals=precheck_signals[:4],
            comparison=_build_comparison(
                req,
                store,
                supplier_history,
                has_amount_anomaly=False,
            ),
            next_action=_build_next_action("invalid"),
            history=_build_history_summary(supplier_history),
        )

    # 2. Identify comparison / anomaly reference history (direct BIN or lookalike supplier)
    lookalike_match = find_lookalike_supplier(req, store)
    reference_bin = (
        req.recipient_bin
        if supplier_history
        else (lookalike_match["bin"] if lookalike_match is not None else req.recipient_bin)
    )
    comparison_history = (
        supplier_history
        if supplier_history
        else (
            store.get_supplier_history(lookalike_match["bin"], req.payer_id)
            if lookalike_match is not None
            else []
        )
    )

    # 3. Evaluate risk rules
    candidates: list[Signal | None] = [
        rule_bcc_account_other_owner(req, store),
        rule_lookalike_supplier(req, store),
        rule_bin_name_mismatch(req, store),
        rule_iik_changed(req, store),
        rule_bank_changed(req, store),
        rule_entity_type_mismatch(req),
        rule_new_bcc_account(req, store, today=today),
        rule_amount_anomaly(req, store, reference_bin=reference_bin),
        rule_first_payment(req, store),
        rule_urgent_wording(req),
    ]
    all_signals = [s for s in candidates if s is not None]

    # 4. Aggregate score and verdict
    verdict, score = aggregate_signals(all_signals)
    has_amount_anomaly = any(s.rule_id == "amount_anomaly" for s in all_signals)

    # Keep up to 4 strongest reasons sorted by severity & points.
    ordered_signals = _sort_signals(all_signals)
    if verdict in ("yellow", "red"):
        ordered_signals = [s for s in ordered_signals if s.severity != "info"]
    top_signals = ordered_signals[:4]

    return CheckResult(
        check_id=check_id,
        verdict=verdict,
        score=score,
        headline_ru=HEADLINES_RU[verdict],
        signals=top_signals,
        comparison=_build_comparison(
            req,
            store,
            comparison_history,
            has_amount_anomaly=has_amount_anomaly,
        ),
        next_action=_build_next_action(verdict),
        history=_build_history_summary(supplier_history),
    )
