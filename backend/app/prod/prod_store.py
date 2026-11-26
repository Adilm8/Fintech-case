"""SQLite-backed Store subclass used by the risk engine in production mode."""

from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, date, datetime, timedelta
from typing import Any

from app.prod.db import tx
from app.prod.schemas import Company
from app.prod.security import utc_now_iso
from app.risk.config import DEMO_TODAY
from app.schemas import CheckRequest, TrustedInfo, compute_request_sha256
from app.settings import load_settings
from app.store import Store

_reference_lock = threading.Lock()
_reference_store: Store | None = None


def get_reference_store() -> Store:
    """Return a shared read-only Store instance for static banks/registry/BCC reference data."""
    global _reference_store
    if _reference_store is None:
        with _reference_lock:
            if _reference_store is None:
                _reference_store = Store()
    return _reference_store


def _company_to_client_dict(company: Company | sqlite3.Row | dict[str, Any]) -> dict[str, str]:
    if isinstance(company, Company):
        return {
            "payer_id": company.id,
            "name": company.name,
            "bin": company.bin,
            "iik": company.iik,
            "bik": company.bik,
        }
    if isinstance(company, sqlite3.Row):
        mapping = dict(company)
    else:
        mapping = company
    payer_id = str(mapping.get("id") or mapping.get("payer_id") or "")
    if not payer_id:
        raise ValueError("Company record must include 'id' or 'payer_id'.")
    return {
        "payer_id": payer_id,
        "name": str(mapping["name"]),
        "bin": str(mapping["bin"]),
        "iik": str(mapping["iik"]),
        "bik": str(mapping["bik"]),
    }


def _parse_iso_utc(raw: str) -> datetime:
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


class ProdStore(Store):
    """Per-request Store subclass reading company history, trust, and recent checks from SQLite."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        company: Company | sqlite3.Row | dict[str, Any],
        reference: Store | None = None,
        today: date | None = None,
        *,
        exclude_payment_id: str | None = None,
    ) -> None:
        # Intentionally do NOT call Store.__init__(); share read-only reference tables by reference.
        ref = reference if reference is not None else get_reference_store()
        self.data_dir = ref.data_dir
        self.banks_path = ref.banks_path
        self.audit_log_path = ref.audit_log_path
        self.banks = ref.banks
        self.banks_by_bik = ref.banks_by_bik
        self.banks_by_code = ref.banks_by_code
        self.registry = ref.registry
        self.bcc_accounts = ref.bcc_accounts

        self.conn: sqlite3.Connection = conn
        self.client: dict[str, str] = _company_to_client_dict(company)
        self.company_id: str = self.client["payer_id"]
        self.today: date = today if today is not None else load_settings().today()
        self.exclude_payment_id: str | None = exclude_payment_id

        self.queue: list[dict[str, Any]] = []
        self.approvals = []
        self.recent_checks: list[dict[str, Any]] = []
        self._history_cache: list[dict[str, Any]] | None = None

    def invalidate_history_cache(self) -> None:
        """Clear cached signed payment history (e.g. after signing within the same request)."""
        self._history_cache = None

    @property
    def default_payer_id(self) -> str:
        return self.company_id

    @property
    def known_payer_ids(self) -> set[str]:
        return {self.company_id}

    @property
    def history(self) -> list[dict[str, Any]]:
        return self.get_client_history(self.company_id)

    def get_client_history(self, payer_id: str | None = None) -> list[dict[str, Any]]:
        """Load signed payments for this company in history.json shape, cached per ProdStore."""
        resolved = self.resolve_payer_id(payer_id)
        if resolved != self.company_id:
            return []
        if self._history_cache is None:
            rows = self.conn.execute(
                """
                SELECT
                    id, company_id, paid_at, signed_at, created_at,
                    recipient_name, recipient_bin, recipient_iik, recipient_bik,
                    amount_tiyn, purpose, knp
                FROM payments
                WHERE company_id = ? AND status = 'signed'
                ORDER BY COALESCE(paid_at, substr(signed_at, 1, 10), substr(created_at, 1, 10)) ASC,
                         id ASC
                """,
                (self.company_id,),
            ).fetchall()
            items: list[dict[str, Any]] = []
            for row in rows:
                paid_raw = row["paid_at"] or row["signed_at"] or row["created_at"]
                paid_date = str(paid_raw)[:10]
                items.append(
                    {
                        "id": str(row["id"]),
                        "payer_id": str(row["company_id"]),
                        "paid_at": paid_date,
                        "recipient_name": str(row["recipient_name"]),
                        "recipient_bin": str(row["recipient_bin"]),
                        "recipient_iik": str(row["recipient_iik"]),
                        "recipient_bik": str(row["recipient_bik"]),
                        "amount_kzt": int(row["amount_tiyn"]) / 100.0,
                        "purpose": str(row["purpose"]),
                        "knp": str(row["knp"]),
                    }
                )
            items.sort(key=lambda p: (p["paid_at"], p["id"]))
            self._history_cache = items
        return list(self._history_cache)

    def get_trusted_info(
        self,
        payer_id: str | None,
        recipient_bin: str,
        recipient_iik: str,
    ) -> TrustedInfo | None:
        resolved = self.resolve_payer_id(payer_id)
        if resolved != self.company_id:
            return None
        row = self.conn.execute(
            """
            SELECT decided_at, director_comment
            FROM trusted_accounts
            WHERE company_id = ?
              AND recipient_bin = ?
              AND recipient_iik = ?
              AND revoked_at IS NULL
            LIMIT 1
            """,
            (self.company_id, recipient_bin, recipient_iik),
        ).fetchone()
        if row is None:
            return None
        return TrustedInfo(
            decided_at=str(row["decided_at"]),
            director_comment=str(row["director_comment"]),
        )

    def is_bin_trusted(self, recipient_bin: str, *, payer_id: str | None = None) -> bool:
        resolved = self.resolve_payer_id(payer_id)
        if resolved != self.company_id:
            return False
        row = self.conn.execute(
            """
            SELECT 1
            FROM trusted_accounts
            WHERE company_id = ? AND recipient_bin = ? AND revoked_at IS NULL
            LIMIT 1
            """,
            (self.company_id, recipient_bin),
        ).fetchone()
        return row is not None

    def get_trusted_entries_for_payer(
        self,
        payer_id: str | None = None,
    ) -> list[tuple[str, str, TrustedInfo]]:
        resolved = self.resolve_payer_id(payer_id)
        if resolved != self.company_id:
            return []
        rows = self.conn.execute(
            """
            SELECT recipient_bin, recipient_iik, decided_at, director_comment
            FROM trusted_accounts
            WHERE company_id = ? AND revoked_at IS NULL
            ORDER BY id ASC
            """,
            (self.company_id,),
        ).fetchall()
        return [
            (
                str(r["recipient_bin"]),
                str(r["recipient_iik"]),
                TrustedInfo(
                    decided_at=str(r["decided_at"]),
                    director_comment=str(r["director_comment"]),
                ),
            )
            for r in rows
        ]

    @property
    def trusted_accounts(self) -> dict[tuple[str, str, str], TrustedInfo]:
        return {
            (self.company_id, bin_val, iik_val): info
            for bin_val, iik_val, info in self.get_trusted_entries_for_payer(self.company_id)
        }

    def trust_account(
        self,
        recipient_bin: str,
        recipient_iik: str,
        *,
        payer_id: str | None = None,
        decided_at: str | None = None,
        director_comment: str = "",
        approval_id: str | None = None,
        decided_by: int | None = None,
    ) -> TrustedInfo:
        resolved = self.resolve_payer_id(payer_id)
        if resolved != self.company_id:
            raise ValueError(f"Cannot trust account for foreign company {resolved!r}.")
        if decided_by is None:
            raise ValueError("decided_by user id is required when trusting an account in ProdStore.")
        ts = decided_at or utc_now_iso()
        with tx(self.conn):
            existing = self.conn.execute(
                """
                SELECT id FROM trusted_accounts
                WHERE company_id = ? AND recipient_bin = ? AND recipient_iik = ? AND revoked_at IS NULL
                """,
                (self.company_id, recipient_bin, recipient_iik),
            ).fetchone()
            if existing is not None:
                self.conn.execute(
                    """
                    UPDATE trusted_accounts
                    SET approval_id = ?, director_comment = ?, decided_by = ?, decided_at = ?
                    WHERE id = ?
                    """,
                    (approval_id, director_comment, decided_by, ts, int(existing["id"])),
                )
            else:
                self.conn.execute(
                    """
                    INSERT INTO trusted_accounts (
                        company_id, recipient_bin, recipient_iik,
                        approval_id, director_comment, decided_by, decided_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        self.company_id,
                        recipient_bin,
                        recipient_iik,
                        approval_id,
                        director_comment,
                        decided_by,
                        ts,
                    ),
                )
        return TrustedInfo(decided_at=ts, director_comment=director_comment)

    def get_recent_checks(
        self,
        recipient_bin: str,
        payer_id: str | None = None,
        *,
        within_days: int | None = None,
        within_hours: float | None = None,
        now: datetime | None = None,
        today: date | None = None,
        exclude_request_sha256: str | None = None,
    ) -> list[dict[str, Any]]:
        """Read active unsigned payments for (company, recipient_bin) as short-term check memory."""
        resolved = self.resolve_payer_id(payer_id)
        if resolved != self.company_id:
            return []

        effective_today = today if today is not None else self.today
        ref_dt = now or datetime.combine(
            effective_today,
            datetime.now(UTC).time().replace(microsecond=0),
            tzinfo=UTC,
        )
        query = """
            SELECT
                id, company_id, recipient_bin, recipient_iik, recipient_name,
                amount_tiyn, purpose, request_sha256, created_at
            FROM payments
            WHERE company_id = ?
              AND recipient_bin = ?
              AND status IN ('checked', 'pending_approval', 'approved')
        """
        params: list[Any] = [self.company_id, recipient_bin]
        if self.exclude_payment_id is not None:
            query += " AND id != ?"
            params.append(self.exclude_payment_id)
        query += " ORDER BY created_at ASC, id ASC"
        rows = self.conn.execute(query, params).fetchall()

        results: list[dict[str, Any]] = []
        for row in rows:
            req_sha = str(row["request_sha256"])
            if exclude_request_sha256 is not None and req_sha == exclude_request_sha256:
                continue
            try:
                entry_dt = _parse_iso_utc(str(row["created_at"]))
            except ValueError:
                continue
            delta = max(ref_dt - entry_dt, timedelta(0))
            if within_hours is not None and delta > timedelta(hours=within_hours):
                continue
            if within_days is not None and delta > timedelta(days=within_days):
                continue
            results.append(
                {
                    "payer_id": str(row["company_id"]),
                    "recipient_bin": str(row["recipient_bin"]),
                    "recipient_iik": str(row["recipient_iik"]),
                    "recipient_name": str(row["recipient_name"]),
                    "amount_kzt": int(row["amount_tiyn"]) / 100.0,
                    "purpose": str(row["purpose"]),
                    "invoice_no": None,
                    "request_sha256": req_sha,
                    "checked_at": str(row["created_at"]),
                }
            )
        return results

    def record_check(
        self,
        req: CheckRequest,
        *,
        invoice_no: str | None = None,
        checked_at: datetime | None = None,
        today: date = DEMO_TODAY,
        request_sha256: str | None = None,
    ) -> dict[str, Any]:
        """No-op in prod mode because the payments table itself serves as short-term memory."""
        resolved = self.resolve_payer_id(req.payer_id)
        req_hash = request_sha256 or compute_request_sha256(req, resolved_payer_id=resolved)
        ts = checked_at or datetime.combine(
            today,
            datetime.now(UTC).time().replace(microsecond=0),
            tzinfo=UTC,
        )
        return {
            "payer_id": resolved,
            "recipient_bin": req.recipient_bin,
            "recipient_iik": req.recipient_iik,
            "recipient_name": req.recipient_name,
            "amount_kzt": float(req.amount_kzt),
            "purpose": req.purpose,
            "invoice_no": invoice_no,
            "request_sha256": req_hash,
            "checked_at": ts.isoformat(),
        }

    def clear_recent_draft(
        self,
        *,
        payer_id: str | None,
        recipient_bin: str,
        recipient_iik: str,
        amount_kzt: float,
    ) -> None:
        """No-op in prod mode."""
        return

    def reload(self) -> None:
        raise NotImplementedError("ProdStore does not support reload(); instantiate per request.")

    def reset(self) -> None:
        raise NotImplementedError("ProdStore does not support reset().")
