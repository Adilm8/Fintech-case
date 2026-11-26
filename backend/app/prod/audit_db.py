"""SQLite append-only audit log with SHA-256 hash chaining and integrity verification."""

from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
from typing import Any

from app.prod.db import tx
from app.prod.schemas import AuditEntry, AuditUser, AuditVerifyResult, Role
from app.prod.security import utc_now_iso
from app.schemas import Verdict

GENESIS_HASH: str = "0" * 64


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def compute_entry_hash(
    *,
    prev_hash: str,
    timestamp: str,
    user_id: int | None,
    user_login: str | None,
    role: str | None,
    company_id: str | None,
    action: str,
    payment_id: str | None,
    approval_id: str | None,
    check_id: str | None,
    batch_id: str | None,
    request_sha256: str | None,
    ruleset_version: str | None,
    verdict: str | None,
    signal_ids_json: str,
    details_json: str,
) -> str:
    """Compute SHA-256(prev_hash + canonical_json(entry fields excluding hashes))."""
    payload = {
        "timestamp": timestamp,
        "user_id": user_id,
        "user_login": user_login,
        "role": role,
        "company_id": company_id,
        "action": action,
        "payment_id": payment_id,
        "approval_id": approval_id,
        "check_id": check_id,
        "batch_id": batch_id,
        "request_sha256": request_sha256,
        "ruleset_version": ruleset_version,
        "verdict": verdict,
        "signal_ids_json": signal_ids_json,
        "details_json": details_json,
    }
    raw = prev_hash + _canonical_json(payload)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def append_audit(
    conn: sqlite3.Connection,
    *,
    action: str,
    timestamp: str | None = None,
    user_id: int | None = None,
    user_login: str | None = None,
    role: Role | None = None,
    company_id: str | None = None,
    payment_id: str | None = None,
    approval_id: str | None = None,
    check_id: str | None = None,
    batch_id: str | None = None,
    request_sha256: str | None = None,
    ruleset_version: str | None = None,
    verdict: Verdict | None = None,
    signal_ids: list[str] | None = None,
    details: dict[str, Any] | None = None,
) -> int:
    """Append a hash-chained row to audit_log inside a BEGIN IMMEDIATE transaction/savepoint."""
    ts = timestamp or utc_now_iso()
    signal_ids_json = _canonical_json(list(signal_ids) if signal_ids is not None else [])
    details_json = _canonical_json(dict(details) if details is not None else {})

    with tx(conn):
        last = conn.execute(
            "SELECT entry_hash FROM audit_log ORDER BY id DESC LIMIT 1"
        ).fetchone()
        prev_hash = str(last["entry_hash"]) if last is not None else GENESIS_HASH
        entry_hash = compute_entry_hash(
            prev_hash=prev_hash,
            timestamp=ts,
            user_id=user_id,
            user_login=user_login,
            role=role,
            company_id=company_id,
            action=action,
            payment_id=payment_id,
            approval_id=approval_id,
            check_id=check_id,
            batch_id=batch_id,
            request_sha256=request_sha256,
            ruleset_version=ruleset_version,
            verdict=verdict,
            signal_ids_json=signal_ids_json,
            details_json=details_json,
        )
        cur = conn.execute(
            """
            INSERT INTO audit_log (
                timestamp, user_id, user_login, role, company_id, action,
                payment_id, approval_id, check_id, batch_id,
                request_sha256, ruleset_version, verdict,
                signal_ids_json, details_json, prev_hash, entry_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ts,
                user_id,
                user_login,
                role,
                company_id,
                action,
                payment_id,
                approval_id,
                check_id,
                batch_id,
                request_sha256,
                ruleset_version,
                verdict,
                signal_ids_json,
                details_json,
                prev_hash,
                entry_hash,
            ),
        )
        assert cur.lastrowid is not None
        return int(cur.lastrowid)


def _row_to_audit_entry(row: sqlite3.Row) -> AuditEntry:
    user: AuditUser | None = None
    if row["user_id"] is not None and row["user_login"] is not None and row["role"] is not None:
        user = AuditUser(
            id=int(row["user_id"]),
            login=str(row["user_login"]),
            role=row["role"],
        )

    raw_signals = json.loads(str(row["signal_ids_json"])) if row["signal_ids_json"] else []
    raw_details = json.loads(str(row["details_json"])) if row["details_json"] else {}

    return AuditEntry(
        id=int(row["id"]),
        timestamp=str(row["timestamp"]),
        user=user,
        action=str(row["action"]),
        payment_id=str(row["payment_id"]) if row["payment_id"] is not None else None,
        approval_id=str(row["approval_id"]) if row["approval_id"] is not None else None,
        check_id=str(row["check_id"]) if row["check_id"] is not None else None,
        batch_id=str(row["batch_id"]) if row["batch_id"] is not None else None,
        request_sha256=str(row["request_sha256"]) if row["request_sha256"] is not None else None,
        ruleset_version=(
            str(row["ruleset_version"]) if row["ruleset_version"] is not None else None
        ),
        verdict=row["verdict"],
        signal_ids=[str(s) for s in raw_signals],
        details=dict(raw_details) if isinstance(raw_details, dict) else {},
        entry_hash=str(row["entry_hash"]),
    )


def list_audit(
    conn: sqlite3.Connection,
    *,
    company_id: str | None = None,
    payment_id: str | None = None,
    action: str | None = None,
    limit: int = 100,
) -> list[AuditEntry]:
    """Return newest-first audit log entries filtered by optional company/payment/action."""
    clauses: list[str] = []
    params: list[Any] = []
    if company_id is not None:
        clauses.append("company_id = ?")
        params.append(company_id)
    if payment_id is not None:
        clauses.append("payment_id = ?")
        params.append(payment_id)
    if action is not None:
        clauses.append("action = ?")
        params.append(action)

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    bounded_limit = max(1, min(int(limit), 1000))
    params.append(bounded_limit)

    rows = conn.execute(
        f"SELECT * FROM audit_log {where_sql} ORDER BY id DESC LIMIT ?",
        params,
    ).fetchall()
    return [_row_to_audit_entry(row) for row in rows]


def verify_chain(conn: sqlite3.Connection) -> AuditVerifyResult:
    """Verify the entire audit_log SHA-256 hash chain from genesis to the latest entry."""
    rows = conn.execute("SELECT * FROM audit_log ORDER BY id ASC").fetchall()
    expected_prev = GENESIS_HASH
    checked = 0

    for row in rows:
        checked += 1
        row_id = int(row["id"])
        stored_prev = str(row["prev_hash"])
        if not hmac.compare_digest(stored_prev, expected_prev):
            return AuditVerifyResult(ok=False, checked=checked, broken_at=row_id)

        expected_hash = compute_entry_hash(
            prev_hash=expected_prev,
            timestamp=str(row["timestamp"]),
            user_id=int(row["user_id"]) if row["user_id"] is not None else None,
            user_login=str(row["user_login"]) if row["user_login"] is not None else None,
            role=str(row["role"]) if row["role"] is not None else None,
            company_id=str(row["company_id"]) if row["company_id"] is not None else None,
            action=str(row["action"]),
            payment_id=str(row["payment_id"]) if row["payment_id"] is not None else None,
            approval_id=str(row["approval_id"]) if row["approval_id"] is not None else None,
            check_id=str(row["check_id"]) if row["check_id"] is not None else None,
            batch_id=str(row["batch_id"]) if row["batch_id"] is not None else None,
            request_sha256=(
                str(row["request_sha256"]) if row["request_sha256"] is not None else None
            ),
            ruleset_version=(
                str(row["ruleset_version"]) if row["ruleset_version"] is not None else None
            ),
            verdict=str(row["verdict"]) if row["verdict"] is not None else None,
            signal_ids_json=str(row["signal_ids_json"]),
            details_json=str(row["details_json"]),
        )
        stored_hash = str(row["entry_hash"])
        if not hmac.compare_digest(stored_hash, expected_hash):
            return AuditVerifyResult(ok=False, checked=checked, broken_at=row_id)

        expected_prev = stored_hash

    return AuditVerifyResult(ok=True, checked=checked, broken_at=None)
