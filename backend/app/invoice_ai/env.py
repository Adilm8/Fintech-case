"""Load invoice-AI settings from backend/.env without extra dependencies.

Only ANTHROPIC_* and INVOICE_AI_* keys are read, existing environment
variables always win, and values are never logged.
"""

from __future__ import annotations

import os
from pathlib import Path

_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
_ALLOWED_PREFIXES = ("ANTHROPIC_", "INVOICE_AI_", "EXPLAIN_AI_")


def load_env_file(path: Path = _ENV_FILE) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().removeprefix("export ").strip()
        if not key.startswith(_ALLOWED_PREFIXES) or key in os.environ:
            continue
        os.environ[key] = value.strip().strip('"').strip("'")
