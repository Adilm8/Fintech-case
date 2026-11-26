"""Language-independent evaluation runner and chronological history replay."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from app.i18n import DEFAULT_LANG, Lang, kind_label, t
from app.risk.config import DEMO_TODAY, RULESET_VERSION
from app.risk.engine import check_payment
from app.risk.rules import extract_invoice_number
from app.schemas import (
    CheckRequest,
    ConfusionTable,
    EvalLabel,
    HistoryReplayMetrics,
    KindMetrics,
    MetricsResponse,
    MetricsSummary,
    Verdict,
    VerdictCounts,
)
from app.store import DEFAULT_DATA_DIR, Store

POSITIVE_VERDICTS: frozenset[Verdict] = frozenset({"yellow", "red"})
DEFAULT_EVAL_FILENAME: str = "eval_set.json"
EVAL_DISCLAIMER_RU: str = t("metrics.disclaimer", "ru")


def _round4(value: float) -> float:
    return round(value, 4)


def _count_verdicts(verdicts: list[Verdict]) -> VerdictCounts:
    counts: dict[str, int] = {"green": 0, "yellow": 0, "red": 0, "grey": 0, "invalid": 0}
    for v in verdicts:
        counts[v] += 1
    return VerdictCounts(**counts)


def run_history_replay(data_dir: Path | None = None) -> HistoryReplayMetrics:
    """Replay the client's 12-month legitimate payment stream chronologically without future leakage.

    Each historical payment is evaluated strictly against payments dated earlier in an isolated
    Store instance, leaving shared application state untouched.
    """
    isolated_store = Store(data_dir=data_dir or DEFAULT_DATA_DIR)
    chronological = list(isolated_store.history)
    isolated_store.history = []
    isolated_store.recent_checks.clear()

    verdicts: list[Verdict] = []
    for payment in chronological:
        req = CheckRequest(
            payer_id=payment.get("payer_id"),
            recipient_name=payment["recipient_name"],
            recipient_bin=payment["recipient_bin"],
            recipient_iik=payment["recipient_iik"],
            recipient_bik=payment["recipient_bik"],
            amount_kzt=float(payment["amount_kzt"]),
            purpose=payment.get("purpose", ""),
            knp=payment.get("knp", ""),
        )
        pay_date = date.fromisoformat(str(payment["paid_at"])[:10])
        result = check_payment(
            req,
            isolated_store,
            today=pay_date,
            include_recent_memory=False,
            record_in_memory=False,
        )
        verdicts.append(result.verdict)
        isolated_store.history.append(payment)

    counts = _count_verdicts(verdicts)
    total = len(verdicts)
    stopped = counts.red
    escalated = counts.yellow
    alerts = stopped + escalated
    alert_rate = _round4(alerts / total) if total > 0 else 0.0
    return HistoryReplayMetrics(
        total_payments=total,
        verdicts=counts,
        stopped_count=stopped,
        escalated_count=escalated,
        alert_count=alerts,
        alert_rate=alert_rate,
    )


def evaluate_cases(
    cases: list[dict[str, Any]],
    *,
    data_dir: Path | None = None,
    seed: int = 42,
    dataset_path: str = "data/eval_set.json",
    lang: Lang = DEFAULT_LANG,
) -> MetricsResponse:
    """Evaluate labeled payment cases on an isolated Store without mutating shared app state."""
    base_dir = (data_dir or DEFAULT_DATA_DIR).resolve()
    isolated_store = Store(data_dir=base_dir)

    tp = 0
    fn = 0
    fp = 0
    tn = 0

    verdicts_by_label: dict[EvalLabel, list[Verdict]] = {"legit": [], "attack": []}
    kind_order: list[str] = []
    kind_labels: dict[str, EvalLabel] = {}
    verdicts_by_kind: dict[str, list[Verdict]] = defaultdict(list)

    base_dt = datetime(DEMO_TODAY.year, DEMO_TODAY.month, DEMO_TODAY.day, 12, 0, tzinfo=UTC)

    for case in cases:
        label: EvalLabel = case["label"]
        kind = str(case["kind"])
        if kind not in kind_labels:
            kind_order.append(kind)
            kind_labels[kind] = label

        req = CheckRequest(**case["request"])
        is_pre_trusted = bool(case.get("trusted", False))
        prior_checks: list[dict[str, Any]] = list(case.get("prior_checks", []))
        payer_id = isolated_store.resolve_payer_id(req.payer_id)
        trust_key = (payer_id, req.recipient_bin, req.recipient_iik)

        if is_pre_trusted:
            isolated_store.trust_account(
                req.recipient_bin,
                req.recipient_iik,
                payer_id=payer_id,
                decided_at=f"{DEMO_TODAY.isoformat()}T09:00:00+00:00",
                director_comment="Подтверждено директором по телефону из договора.",
            )
        for prior in prior_checks:
            prior_req = CheckRequest(**prior["request"])
            hours_ago = float(prior.get("hours_ago", 12))
            isolated_store.record_check(
                prior_req,
                invoice_no=extract_invoice_number(prior_req.purpose),
                checked_at=base_dt - timedelta(hours=hours_ago),
                today=DEMO_TODAY,
            )
        try:
            result = check_payment(
                req,
                isolated_store,
                today=DEMO_TODAY,
                include_recent_memory=bool(prior_checks),
                record_in_memory=False,
            )
        finally:
            if is_pre_trusted:
                isolated_store.trusted_accounts.pop(trust_key, None)
            if prior_checks:
                isolated_store.recent_checks.clear()

        verdict: Verdict = result.verdict
        is_flagged = verdict in POSITIVE_VERDICTS

        verdicts_by_label[label].append(verdict)
        verdicts_by_kind[kind].append(verdict)

        if label == "attack":
            if is_flagged:
                tp += 1
            else:
                fn += 1
        else:
            if is_flagged:
                fp += 1
            else:
                tn += 1

    by_kind: list[KindMetrics] = []
    for kind in kind_order:
        label = kind_labels[kind]
        v_list = verdicts_by_kind[kind]
        counts = _count_verdicts(v_list)
        total = len(v_list)
        flagged = counts.yellow + counts.red
        rate = _round4(flagged / total) if total > 0 else 0.0
        by_kind.append(
            KindMetrics(
                kind=kind,
                label=label,
                label_ru=kind_label(kind, "ru"),
                label_kk=kind_label(kind, "kk"),
                label_en=kind_label(kind, "en"),
                label_text=kind_label(kind, lang),
                total=total,
                verdicts=counts,
                stopped_count=counts.red,
                escalated_count=counts.yellow,
                flagged_count=flagged,
                detection_rate=rate if label == "attack" else None,
                false_positive_rate=rate if label == "legit" else None,
            )
        )

    total_attack = tp + fn
    total_legit = fp + tn
    total_cases = total_attack + total_legit

    attack_counts = _count_verdicts(verdicts_by_label["attack"])
    legit_counts = _count_verdicts(verdicts_by_label["legit"])

    detection_rate = tp / total_attack if total_attack > 0 else 0.0
    false_positive_rate = fp / total_legit if total_legit > 0 else 0.0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    f1 = (
        2 * precision * detection_rate / (precision + detection_rate)
        if (precision + detection_rate) > 0
        else 0.0
    )
    accuracy = (tp + tn) / total_cases if total_cases > 0 else 0.0
    stopped_rate = attack_counts.red / total_attack if total_attack > 0 else 0.0
    escalated_rate = attack_counts.yellow / total_attack if total_attack > 0 else 0.0

    replay = run_history_replay(base_dir)
    disclaimer_ru = t("metrics.disclaimer", "ru")
    disclaimer_kk = t("metrics.disclaimer", "kk")
    disclaimer_en = t("metrics.disclaimer", "en")

    return MetricsResponse(
        seed=seed,
        ruleset_version=RULESET_VERSION,
        dataset_path=dataset_path,
        positive_verdicts=["yellow", "red"],
        summary=MetricsSummary(
            total_cases=total_cases,
            total_legit=total_legit,
            total_attack=total_attack,
            detection_rate=_round4(detection_rate),
            false_positive_rate=_round4(false_positive_rate),
            precision=_round4(precision),
            f1=_round4(f1),
            accuracy=_round4(accuracy),
            stopped_count=attack_counts.red,
            escalated_count=attack_counts.yellow,
            stopped_rate=_round4(stopped_rate),
            escalated_rate=_round4(escalated_rate),
            legit_stopped_count=legit_counts.red,
            legit_escalated_count=legit_counts.yellow,
        ),
        confusion=ConfusionTable(tp=tp, fn=fn, fp=fp, tn=tn),
        verdict_by_label={
            "legit": legit_counts,
            "attack": attack_counts,
        },
        by_kind=by_kind,
        history_replay=replay,
        disclaimer_ru=disclaimer_ru,
        disclaimer_kk=disclaimer_kk,
        disclaimer_en=disclaimer_en,
        disclaimer=t("metrics.disclaimer", lang),
    )


def localize_metrics(metrics: MetricsResponse, lang: Lang = DEFAULT_LANG) -> MetricsResponse:
    """Return a lightweight localized view of a cached MetricsResponse without recomputing."""
    localized_kinds = [
        row.model_copy(update={"label_text": kind_label(row.kind, lang)})
        for row in metrics.by_kind
    ]
    return metrics.model_copy(
        update={
            "by_kind": localized_kinds,
            "disclaimer": t("metrics.disclaimer", lang),
        }
    )


def evaluate_dataset(
    data_dir: Path | None = None,
    *,
    eval_path: Path | None = None,
    lang: Lang = DEFAULT_LANG,
) -> MetricsResponse:
    """Load eval_set.json and run the risk engine over all cases."""
    base_dir = (data_dir or DEFAULT_DATA_DIR).resolve()
    target_path = (eval_path or (base_dir / DEFAULT_EVAL_FILENAME)).resolve()
    payload = json.loads(target_path.read_text(encoding="utf-8"))
    cases = list(payload["cases"])
    seed = int(payload.get("seed", 42))
    return evaluate_cases(
        cases,
        data_dir=base_dir,
        seed=seed,
        dataset_path=f"data/{target_path.name}",
        lang=lang,
    )


def format_metrics_report(metrics: MetricsResponse) -> str:
    """Format MetricsResponse as a readable plain-text report for CLI output."""
    lines: list[str] = []
    lines.append(
        f"=== Evaluation Report ({metrics.dataset_path}, seed={metrics.seed}, "
        f"ruleset={metrics.ruleset_version}, n={metrics.summary.total_cases}) ==="
    )
    lines.append("")
    lines.append(
        f"{'kind':34s} {'label':6s} {'n':>4s} {'grn':>4s} {'yel':>4s} {'red':>4s} "
        f"{'gry':>4s} {'inv':>4s} {'rate':>9s}"
    )
    lines.append("-" * 82)
    for row in metrics.by_kind:
        v = row.verdicts
        if row.label == "attack":
            rate_str = f"det {(row.detection_rate or 0.0) * 100:5.1f}%"
        else:
            rate_str = f"fpr {(row.false_positive_rate or 0.0) * 100:5.1f}%"
        lines.append(
            f"{row.kind:34s} {row.label:6s} {row.total:4d} {v.green:4d} {v.yellow:4d} "
            f"{v.red:4d} {v.grey:4d} {v.invalid:4d} {rate_str:>9s}"
        )

    lines.append("")
    lines.append("Confusion Table (positive = yellow/red):")
    c = metrics.confusion
    lines.append(f"  Actual attack : TP = {c.tp:3d} (flagged), FN = {c.fn:3d} (missed)")
    lines.append(f"  Actual legit  : FP = {c.fp:3d} (false alarm), TN = {c.tn:3d} (clear)")

    lines.append("")
    lines.append("Verdict Distribution by Label:")
    for lbl in ("legit", "attack"):
        vc = metrics.verdict_by_label[lbl]
        lines.append(
            f"  {lbl:6s}: green={vc.green:3d}, yellow={vc.yellow:3d}, "
            f"red={vc.red:3d}, grey={vc.grey:3d}, invalid={vc.invalid:3d}"
        )

    s = metrics.summary
    lines.append("")
    lines.append("Summary:")
    lines.append(
        f"  Detection rate (attack yellow/red): {s.detection_rate * 100:5.1f}% ({c.tp}/{s.total_attack})"
    )
    lines.append(
        f"    - Stopped (red)                 : {s.stopped_rate * 100:5.1f}% ({s.stopped_count}/{s.total_attack})"
    )
    lines.append(
        f"    - Escalated (yellow)            : {s.escalated_rate * 100:5.1f}% ({s.escalated_count}/{s.total_attack})"
    )
    lines.append(
        f"  False positive rate (legit y/r)   : {s.false_positive_rate * 100:5.1f}% "
        f"({c.fp}/{s.total_legit}; red={s.legit_stopped_count}, yellow={s.legit_escalated_count})"
    )
    lines.append(f"  Precision                         : {s.precision * 100:5.1f}%")
    lines.append(f"  F1 score                          : {s.f1 * 100:5.1f}%")
    lines.append(f"  Accuracy                          : {s.accuracy * 100:5.1f}%")

    hr = metrics.history_replay
    hv = hr.verdicts
    lines.append("")
    lines.append(
        f"History Replay (chronological, n={hr.total_payments}): "
        f"green={hv.green}, yellow={hv.yellow}, red={hv.red}, grey={hv.grey}, "
        f"alert_rate={hr.alert_rate * 100:5.1f}% ({hr.alert_count}/{hr.total_payments})"
    )
    lines.append("")
    lines.append(f"disclaimer_ru: {metrics.disclaimer_ru}")
    return "\n".join(lines)
