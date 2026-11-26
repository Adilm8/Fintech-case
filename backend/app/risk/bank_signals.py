"""Loader and helpers for bank-wide anonymized antifraud signals (data/bank_signals.json).

Loads signals directly inside app/risk/ without modifying app/store.py, caching by
file path + stat signature so edits or regenerations are picked up automatically.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.risk.config import BANK_KNOWN_BIN_MIN_YEARS, DEMO_TODAY

if TYPE_CHECKING:
    from app.store import Store

DEFAULT_DATA_DIR: Path = Path(__file__).resolve().parents[2] / "data"
BANK_SIGNALS_FILENAME: str = "bank_signals.json"

_EMPTY_SIGNALS: dict[str, dict[str, Any]] = {
    "complaints": {},
    "fresh_inflows": {},
    "mule_watchlist": {},
    "bank_known_bin": {},
}

# Cache keyed by resolved file path -> ((mtime_ns, size), normalized_payload)
_CACHE: dict[Path, tuple[tuple[int, int], dict[str, dict[str, Any]]]] = {}


def _normalize_bank_signals(raw: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(raw, dict):
        return {k: {} for k in _EMPTY_SIGNALS}
    return {
        "complaints": dict(raw.get("complaints") or {}),
        "fresh_inflows": dict(raw.get("fresh_inflows") or {}),
        "mule_watchlist": dict(raw.get("mule_watchlist") or {}),
        "bank_known_bin": dict(raw.get("bank_known_bin") or {}),
    }


def load_bank_signals(data_dir: Path | None = None) -> dict[str, dict[str, Any]]:
    """Load bank_signals.json from data_dir, returning empty tables if absent."""
    base_dir = (data_dir or DEFAULT_DATA_DIR).resolve()
    target = base_dir / BANK_SIGNALS_FILENAME
    if not target.exists():
        return {k: {} for k in _EMPTY_SIGNALS}

    stat = target.stat()
    sig = (stat.st_mtime_ns, stat.st_size)
    cached = _CACHE.get(target)
    if cached is not None and cached[0] == sig:
        return cached[1]

    raw = json.loads(target.read_text(encoding="utf-8"))
    normalized = _normalize_bank_signals(raw)
    _CACHE[target] = (sig, normalized)
    return normalized


def clear_bank_signals_cache() -> None:
    """Clear the cached bank_signals.json entries."""
    _CACHE.clear()


def get_bank_signals(
    store: Store | None = None,
    *,
    bank_signals: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Resolve bank-wide signals from explicit override, store attribute, or store.data_dir."""
    if bank_signals is not None:
        return _normalize_bank_signals(bank_signals)
    if store is not None:
        override = getattr(store, "bank_signals", None)
        if isinstance(override, dict):
            return _normalize_bank_signals(override)
        return load_bank_signals(store.data_dir)
    return load_bank_signals(DEFAULT_DATA_DIR)


def is_bank_known_bin(
    recipient_bin: str,
    bank_signals: dict[str, Any],
    *,
    today: date = DEMO_TODAY,
) -> bool:
    """Return True if recipient_bin has long-standing history in BCC (>= BANK_KNOWN_BIN_MIN_YEARS)."""
    known_bins = bank_signals.get("bank_known_bin") or {}
    entry = known_bins.get(recipient_bin)
    if not isinstance(entry, dict):
        return False

    first_seen_raw = entry.get("first_seen_at")
    if isinstance(first_seen_raw, str) and first_seen_raw.strip():
        try:
            first_seen = date.fromisoformat(first_seen_raw[:10])
            age_days = (today - first_seen).days
            return age_days >= int(BANK_KNOWN_BIN_MIN_YEARS * 365)
        except ValueError:
            pass

    years = entry.get("history_years")
    return isinstance(years, (int, float)) and float(years) >= BANK_KNOWN_BIN_MIN_YEARS
