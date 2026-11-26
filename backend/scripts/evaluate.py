"""CLI runner to evaluate the payment risk engine on data/eval_set.json."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.risk.evaluation import evaluate_dataset, format_metrics_report


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Evaluate BCC Business Shield risk engine.")
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Print metrics as JSON instead of a human-readable table.",
    )
    parser.add_argument(
        "--eval-path",
        type=Path,
        default=None,
        help="Optional path to eval_set.json (defaults to data/eval_set.json).",
    )
    args = parser.parse_args()

    metrics = evaluate_dataset(eval_path=args.eval_path)
    if args.as_json:
        print(json.dumps(metrics.model_dump(), ensure_ascii=False, indent=2))
    else:
        print(format_metrics_report(metrics))


if __name__ == "__main__":
    main()
