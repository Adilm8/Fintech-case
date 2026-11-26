"""Language-independent evaluation runner for the payment risk engine."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from app.risk.config import DEMO_TODAY
from app.risk.engine import check_payment
from app.schemas import (
    CheckRequest,
    ConfusionTable,
    EvalLabel,
    KindMetrics,
    MetricsResponse,
    MetricsSummary,
    Verdict,
    VerdictCounts,
)
from app.store import DEFAULT_DATA_DIR, Store

POSITIVE_VERDICTS: frozenset[Verdict] = frozenset({"yellow", "red"})
DEFAULT_EVAL_FILENAME: str = "eval_set.json"

EVAL_DISCLAIMER_RU: str = (
    "Честное предупреждение: оценочный набор синтетический и сгенерирован той же командой, "
    "которая разрабатывала правила проверки, на основе синтетической истории одного клиента. "
    "Метрики показывают поведение движка на заданных сценариях, не отражают реальную "
    "банковскую статистику мошенничества и не заменяют проверку на исторических боевых данных. "
    "Известные слепые зоны (чистый дроп в стороннем банке без истории, умеренное завышение "
    "суммы без смены реквизитов, ИИН-дроп без ОПФ в названии и первая неподтверждённая смена "
    "счёта) намеренно сохранены в наборе без подгонки детектора."
)


def _round4(value: float) -> float:
    return round(value, 4)


def _count_verdicts(verdicts: list[Verdict]) -> VerdictCounts:
    counts: dict[str, int] = {"green": 0, "yellow": 0, "red": 0, "grey": 0, "invalid": 0}
    for v in verdicts:
        counts[v] += 1
    return VerdictCounts(**counts)


def evaluate_cases(
    cases: list[dict[str, Any]],
    *,
    data_dir: Path | None = None,
    seed: int = 42,
    dataset_path: str = "data/eval_set.json",
) -> MetricsResponse:
    """Evaluate labeled payment cases on an isolated Store without mutating shared app state.

    Metric computation depends strictly on structured enums (`verdict`, `label`, `kind`)
    and never inspects localized text fields.
    """
    isolated_store = Store(data_dir=data_dir or DEFAULT_DATA_DIR)

    tp = 0
    fn = 0
    fp = 0
    tn = 0

    verdicts_by_label: dict[EvalLabel, list[Verdict]] = {"legit": [], "attack": []}
    kind_order: list[str] = []
    kind_labels: dict[str, EvalLabel] = {}
    verdicts_by_kind: dict[str, list[Verdict]] = defaultdict(list)

    for case in cases:
        label: EvalLabel = case["label"]
        kind = str(case["kind"])
        if kind not in kind_labels:
            kind_order.append(kind)
            kind_labels[kind] = label

        req = CheckRequest(**case["request"])
        is_pre_trusted = bool(case.get("trusted", False))
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
        try:
            result = check_payment(req, isolated_store, today=DEMO_TODAY)
        finally:
            if is_pre_trusted:
                isolated_store.trusted_accounts.pop(trust_key, None)

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
        total = len(v_list)
        flagged = sum(1 for v in v_list if v in POSITIVE_VERDICTS)
        rate = _round4(flagged / total) if total > 0 else 0.0
        by_kind.append(
            KindMetrics(
                kind=kind,
                label=label,
                total=total,
                verdicts=_count_verdicts(v_list),
                flagged_count=flagged,
                detection_rate=rate if label == "attack" else None,
                false_positive_rate=rate if label == "legit" else None,
            )
        )

    total_attack = tp + fn
    total_legit = fp + tn
    total_cases = total_attack + total_legit

    detection_rate = tp / total_attack if total_attack > 0 else 0.0
    false_positive_rate = fp / total_legit if total_legit > 0 else 0.0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    f1 = (
        2 * precision * detection_rate / (precision + detection_rate)
        if (precision + detection_rate) > 0
        else 0.0
    )
    accuracy = (tp + tn) / total_cases if total_cases > 0 else 0.0

    return MetricsResponse(
        seed=seed,
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
        ),
        confusion=ConfusionTable(tp=tp, fn=fn, fp=fp, tn=tn),
        verdict_by_label={
            "legit": _count_verdicts(verdicts_by_label["legit"]),
            "attack": _count_verdicts(verdicts_by_label["attack"]),
        },
        by_kind=by_kind,
        disclaimer_ru=EVAL_DISCLAIMER_RU,
    )


def evaluate_dataset(
    data_dir: Path | None = None,
    *,
    eval_path: Path | None = None,
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
    )


def format_metrics_report(metrics: MetricsResponse) -> str:
    """Format MetricsResponse as a readable plain-text report for CLI output."""
    lines: list[str] = []
    lines.append(
        f"=== Evaluation Report ({metrics.dataset_path}, seed={metrics.seed}, "
        f"n={metrics.summary.total_cases}) ==="
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
    lines.append(f"  Detection rate (attack yellow/red): {s.detection_rate * 100:5.1f}% ({c.tp}/{s.total_attack})")
    lines.append(f"  False positive rate (legit y/r)   : {s.false_positive_rate * 100:5.1f}% ({c.fp}/{s.total_legit})")
    lines.append(f"  Precision                         : {s.precision * 100:5.1f}%")
    lines.append(f"  F1 score                          : {s.f1 * 100:5.1f}%")
    lines.append(f"  Accuracy                          : {s.accuracy * 100:5.1f}%")
    lines.append("")
    lines.append(f"disclaimer_ru: {metrics.disclaimer_ru}")
    return "\n".join(lines)
