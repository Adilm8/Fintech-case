"""Append-only JSONL audit trail storing hashes and rule IDs without plaintext PII/amounts."""

from __future__ import annotations

import json
import threading
from pathlib import Path

from app.schemas import AuditEntry

_AUDIT_LOCK = threading.Lock()


def append_audit_entry(path: Path, entry: AuditEntry) -> None:
    """Append a single AuditEntry as a JSON line to path."""
    line = json.dumps(entry.model_dump(exclude_none=True), ensure_ascii=False) + "\n"
    with _AUDIT_LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line)


def read_audit_entries(path: Path, *, limit: int = 100) -> list[AuditEntry]:
    """Read the last `limit` AuditEntry records from a JSONL audit log file."""
    if limit <= 0 or not path.exists():
        return []
    with _AUDIT_LOCK:
        raw_lines = path.read_text(encoding="utf-8").splitlines()
    entries: list[AuditEntry] = []
    for raw in raw_lines[-limit:]:
        stripped = raw.strip()
        if not stripped:
            continue
        try:
            entries.append(AuditEntry(**json.loads(stripped)))
        except (json.JSONDecodeError, ValueError):
            continue
    return entries
