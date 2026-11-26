"""Shared helpers for reading per-company notification and approval-threshold settings."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from app.prod.schemas import NotifyOn

DEFAULT_NOTIFY_ON: NotifyOn = "red_yellow"


@dataclass(frozen=True)
class CompanySettingsState:
    """Resolved settings for a company with defaults when no explicit row exists yet."""

    notify_on: NotifyOn = DEFAULT_NOTIFY_ON
    approval_threshold_tiyn: int | None = None
    updated_at: str | None = None

    @property
    def approval_threshold_kzt(self) -> float | None:
        if self.approval_threshold_tiyn is None:
            return None
        return self.approval_threshold_tiyn / 100.0


def get_company_settings(
    conn: sqlite3.Connection,
    company_id: str,
) -> CompanySettingsState:
    """Return company settings for company_id, falling back to safe defaults."""
    row = conn.execute(
        """
        SELECT notify_on, approval_threshold_tiyn, updated_at
        FROM company_settings
        WHERE company_id = ?
        """,
        (company_id,),
    ).fetchone()
    if row is None:
        return CompanySettingsState()
    raw_threshold = row["approval_threshold_tiyn"]
    return CompanySettingsState(
        notify_on=row["notify_on"],
        approval_threshold_tiyn=int(raw_threshold) if raw_threshold is not None else None,
        updated_at=str(row["updated_at"]) if row["updated_at"] is not None else None,
    )


def load_company_settings_map(
    conn: sqlite3.Connection,
    company_ids: set[str],
) -> dict[str, CompanySettingsState]:
    """Batch-load settings for a set of company IDs."""
    if not company_ids:
        return {}
    ordered = sorted(company_ids)
    placeholders = ",".join("?" for _ in ordered)
    rows = conn.execute(
        f"""
        SELECT company_id, notify_on, approval_threshold_tiyn, updated_at
        FROM company_settings
        WHERE company_id IN ({placeholders})
        """,
        ordered,
    ).fetchall()
    result: dict[str, CompanySettingsState] = {
        cid: CompanySettingsState() for cid in ordered
    }
    for row in rows:
        raw_threshold = row["approval_threshold_tiyn"]
        result[str(row["company_id"])] = CompanySettingsState(
            notify_on=row["notify_on"],
            approval_threshold_tiyn=int(raw_threshold) if raw_threshold is not None else None,
            updated_at=str(row["updated_at"]) if row["updated_at"] is not None else None,
        )
    return result
