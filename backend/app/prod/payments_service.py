"""Business logic for payments CRUD, status transitions, signing gateway, and approvals."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from typing import Any

from pydantic import ValidationError

from app.i18n import DEFAULT_LANG, Lang, t
from app.prod import policy
from app.prod.audit_db import append_audit
from app.prod.company_settings import get_company_settings, load_company_settings_map
from app.prod.db import tx
from app.prod.deps import company_scope_id, ensure_company_access
from app.prod.directory import lookup_supplier_ref, register_signed_payment
from app.prod.errors import ProdError, localize_prod_error
from app.prod.importers import (
    MAX_IMPORT_BYTES,
    EmptyFileError,
    UnsupportedFileError,
    parse_1c,
    parse_csv,
)
from app.prod.prod_store import ProdStore, get_reference_store
from app.prod.schemas import (
    ALL_PAYMENT_STATUSES,
    ApprovalBrief,
    Batch,
    BatchActionResult,
    BatchSkippedItem,
    ImportFormat,
    ImportLineError,
    ImportResult,
    ImportSummary,
    Payment,
    PaymentCounts,
    PaymentInput,
    PaymentList,
    PaymentPermissions,
    PaymentScope,
    PaymentSource,
    PaymentStatus,
    ProdApproval,
    ProdApprovalDecisionRequest,
    ProdApprovalStatus,
    Role,
    SupplierRef,
    User,
    UserBrief,
)
from app.prod.security import utc_now_iso
from app.prod.serde import dump_full, load_check_result
from app.prod.signing import (
    DocumentMismatchError,
    InvalidSignerError,
    SignatureVerificationResult,
    SignatureVerifier,
    SignerKind,
    SimulatedSigner,
    build_payment_document,
    verify_document_binding,
    verify_signature,
)
from app.prod.signing import (
    document_digest as compute_document_digest,
)
from app.risk.config import RULESET_VERSION
from app.risk.engine import check_payment, localize_check_result
from app.schemas import (
    CheckRequest,
    CheckResult,
    HistorySummary,
    NextAction,
    Verdict,
    VerdictCounts,
    clean_text_field,
    compute_request_sha256,
    normalize_requisite,
)

EDITABLE_STATUSES: frozenset[PaymentStatus] = policy.EDITABLE_STATUSES
POSTPONABLE_STATUSES: frozenset[PaymentStatus] = policy.POSTPONABLE_STATUSES
CANCELLABLE_STATUSES: frozenset[PaymentStatus] = policy.CANCELLABLE_STATUSES
ACTIVE_PAYMENT_STATUSES: tuple[PaymentStatus, ...] = (
    "checked",
    "pending_approval",
    "approved",
    "rejected",
    "postponed",
)
AGGREGATE_THRESHOLD_WINDOW_HOURS: int = 72
AGGREGATE_THRESHOLD_STATUSES: tuple[PaymentStatus, ...] = (
    "signed",
    "checked",
    "pending_approval",
    "approved",
    "postponed",
)
DUPLICATE_SOURCE_STATUSES: tuple[PaymentStatus, ...] = (
    "signed",
    "checked",
    "pending_approval",
    "approved",
)


def compute_payment_permissions(
    *,
    role: Role,
    status: PaymentStatus,
    verdict: Verdict,
    payment_request_sha256: str,
    approval_status: ProdApprovalStatus | None = None,
    approval_request_sha256: str | None = None,
    signal_ids: Iterable[str] | None = None,
) -> PaymentPermissions:
    """Delegate permission calculation to policy.permissions_for (single source of truth)."""
    return policy.permissions_for(
        role=role,
        status=status,
        verdict=verdict,
        payment_request_sha256=payment_request_sha256,
        approval_status=approval_status,
        approval_request_sha256=approval_request_sha256,
        signal_ids=signal_ids,
    )


def load_company_row(conn: sqlite3.Connection, company_id: str) -> sqlite3.Row:
    """Fetch a company row by id or raise 404."""
    row = conn.execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone()
    if row is None:
        raise ProdError(404, "not_found")
    return row


def insert_check_row(
    conn: sqlite3.Connection,
    *,
    payment_id: str,
    request_sha256: str,
    result: CheckResult,
    trigger: str,
    created_by: int | None,
    created_at: str,
) -> None:
    """Persist a CheckResult snapshot (with exclude=True keys) in the append-only checks table."""
    signal_ids = [s.rule_id for s in result.signals]
    conn.execute(
        """
        INSERT INTO checks (
            id, payment_id, request_sha256, ruleset_version,
            verdict, score, signal_ids_json, result_json,
            trigger, created_by, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            result.check_id,
            payment_id,
            request_sha256,
            result.ruleset_version,
            result.verdict,
            result.score,
            json.dumps(signal_ids, ensure_ascii=False),
            dump_full(result),
            trigger,
            created_by,
            created_at,
        ),
    )


def _synthesize_seed_check(payment_id: str, lang: Lang) -> CheckResult:
    """Build a client-safe green CheckResult for historical seed payments with check_id IS NULL."""
    return CheckResult(
        check_id=f"chk-seed-{payment_id}",
        ruleset_version=RULESET_VERSION,
        verdict="green",
        score=0,
        headline_ru=t("headline.green", "ru"),
        headline=t("headline.green", lang),
        headline_key="headline.green",
        signals=[],
        comparison=[],
        next_action=NextAction(
            text_ru=t("next_action.green", "ru"),
            text=t("next_action.green", lang),
            message_key="next_action.green",
            primary="sign",
            secondary=[],
        ),
        history=HistorySummary(payments_count=0),
        trusted=False,
        trusted_info=None,
        analyst_details=None,
        internal_analyst_details=None,
    )


def _load_users_brief(
    conn: sqlite3.Connection,
    user_ids: set[int],
    cache: dict[int, UserBrief],
) -> None:
    missing = [uid for uid in user_ids if uid not in cache]
    if not missing:
        return
    placeholders = ",".join("?" for _ in missing)
    rows = conn.execute(
        f"SELECT id, login, full_name, role FROM users WHERE id IN ({placeholders})",
        missing,
    ).fetchall()
    for row in rows:
        uid = int(row["id"])
        cache[uid] = UserBrief(
            id=uid,
            login=str(row["login"]),
            full_name=str(row["full_name"]),
            role=row["role"],
        )


def _find_duplicate_map(
    conn: sqlite3.Connection,
    rows: list[sqlite3.Row],
) -> dict[str, str | None]:
    """Resolve duplicate_of against the earliest signed or active-pending match per company.

    Signed matches take priority over pending matches so an unsigned copy always references
    an already-signed original. Rejected, cancelled, and postponed rows are excluded as sources.
    """
    result: dict[str, str | None] = {}
    pairs: set[tuple[str, str]] = set()
    for row in rows:
        pid = str(row["id"])
        if row["status"] in ("signed", "cancelled"):
            result[pid] = None
        else:
            pairs.add((str(row["company_id"]), str(row["request_sha256"])))

    status_ph = ",".join("?" for _ in DUPLICATE_SOURCE_STATUSES)
    earliest_by_pair: dict[tuple[str, str], str] = {}
    for comp_id, sha in pairs:
        first = conn.execute(
            f"""
            SELECT id
            FROM payments
            WHERE company_id = ?
              AND request_sha256 = ?
              AND status IN ({status_ph})
            ORDER BY CASE WHEN status = 'signed' THEN 0 ELSE 1 END ASC,
                     created_at ASC,
                     COALESCE(line_no, 0) ASC,
                     rowid ASC
            LIMIT 1
            """,
            (comp_id, sha, *DUPLICATE_SOURCE_STATUSES),
        ).fetchone()
        if first is not None:
            earliest_by_pair[(comp_id, sha)] = str(first["id"])

    for row in rows:
        pid = str(row["id"])
        if pid in result:
            continue
        first_id = earliest_by_pair.get((str(row["company_id"]), str(row["request_sha256"])))
        result[pid] = first_id if first_id is not None and first_id != pid else None
    return result


def _load_rejected_payment_ids(
    conn: sqlite3.Connection,
    payment_ids: Iterable[str],
) -> set[str]:
    """Return payment IDs that have at least one director-rejected approval in history."""
    ids = list(dict.fromkeys(payment_ids))
    if not ids:
        return set()
    ph = ",".join("?" for _ in ids)
    rows = conn.execute(
        f"SELECT DISTINCT payment_id FROM approvals WHERE status = 'rejected' AND payment_id IN ({ph})",
        ids,
    ).fetchall()
    return {str(r["payment_id"]) for r in rows}


def _load_rejected_requisites_by_company(
    conn: sqlite3.Connection,
    company_ids: Iterable[str],
) -> set[tuple[str, str, str]]:
    """Return (company_id, norm_bin, norm_iik) tuples ever rejected by a director.

    Derived strictly from existing approvals (status='rejected') and append-only audit_log
    ('decision:rejected') without modifying the database schema.
    """
    cids = list(dict.fromkeys(company_ids))
    if not cids:
        return set()
    ph = ",".join("?" for _ in cids)
    rejected: set[tuple[str, str, str]] = set()

    apr_rows = conn.execute(
        f"""
        SELECT DISTINCT p.company_id, p.recipient_bin, p.recipient_iik
        FROM approvals a
        JOIN payments p ON p.id = a.payment_id
        WHERE p.company_id IN ({ph})
          AND a.status = 'rejected'
          AND a.request_sha256 = p.request_sha256
        """,
        cids,
    ).fetchall()
    for r in apr_rows:
        rejected.add(
            (
                str(r["company_id"]),
                normalize_requisite(str(r["recipient_bin"])),
                normalize_requisite(str(r["recipient_iik"])),
            )
        )

    audit_rows = conn.execute(
        f"""
        SELECT company_id, details_json
        FROM audit_log
        WHERE company_id IN ({ph}) AND action = 'decision:rejected'
        """,
        cids,
    ).fetchall()
    for r in audit_rows:
        comp_id = str(r["company_id"]) if r["company_id"] is not None else ""
        if not comp_id:
            continue
        try:
            details = json.loads(str(r["details_json"]))
        except (TypeError, ValueError):
            continue
        if not isinstance(details, dict):
            continue
        raw_bin = details.get("recipient_bin")
        raw_iik = details.get("recipient_iik")
        if isinstance(raw_bin, str) and isinstance(raw_iik, str) and raw_bin and raw_iik:
            rejected.add(
                (comp_id, normalize_requisite(raw_bin), normalize_requisite(raw_iik))
            )

    return rejected


def _has_rejected_payment_history(conn: sqlite3.Connection, payment_id: str) -> bool:
    """Return True if this payment has ever had an approval with status='rejected'."""
    row = conn.execute(
        "SELECT 1 FROM approvals WHERE payment_id = ? AND status = 'rejected' LIMIT 1",
        (payment_id,),
    ).fetchone()
    return row is not None


def _is_rejected_requisites(
    conn: sqlite3.Connection,
    company_id: str,
    recipient_bin: str,
    recipient_iik: str,
) -> bool:
    """Return True if (company_id, recipient_bin, recipient_iik) was ever rejected by a director."""
    key = (
        company_id,
        normalize_requisite(recipient_bin),
        normalize_requisite(recipient_iik),
    )
    return key in _load_rejected_requisites_by_company(conn, (company_id,))


def _parse_iso_utc(raw: str | None) -> datetime | None:
    """Parse an ISO-8601 timestamp or YYYY-MM-DD date string into a UTC-aware datetime."""
    if not raw:
        return None
    text = str(raw).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        if len(text) == 10:
            parsed_date = date.fromisoformat(text)
            return datetime(
                parsed_date.year,
                parsed_date.month,
                parsed_date.day,
                tzinfo=UTC,
            )
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def sum_supplier_payments_window_tiyn(
    conn: sqlite3.Connection,
    *,
    company_id: str,
    recipient_bin: str,
    recipient_iik: str,
    exclude_payment_id: str | None = None,
    now: datetime | None = None,
    window_hours: int = AGGREGATE_THRESHOLD_WINDOW_HOURS,
) -> int:
    """Sum amount_tiyn of non-rejected/non-cancelled payments to the same BIN or IIK in the rolling window.

    Includes signed payments (timestamped by signed_at, falling back to updated_at/created_at/paid_at)
    and active/pending payments (checked, pending_approval, approved, postponed; timestamped by
    created_at, falling back to updated_at). Excludes rejected, cancelled, and exclude_payment_id.
    """
    norm_bin = normalize_requisite(recipient_bin)
    norm_iik = normalize_requisite(recipient_iik)
    match_clauses: list[str] = []
    params: list[Any] = [company_id]
    if norm_bin:
        match_clauses.append("recipient_bin = ?")
        params.append(norm_bin)
    if norm_iik:
        match_clauses.append("recipient_iik = ?")
        params.append(norm_iik)
    if not match_clauses:
        return 0

    status_ph = ",".join("?" for _ in AGGREGATE_THRESHOLD_STATUSES)
    params.extend(AGGREGATE_THRESHOLD_STATUSES)

    exclude_sql = ""
    if exclude_payment_id is not None:
        exclude_sql = "AND id != ?"
        params.append(exclude_payment_id)

    rows = conn.execute(
        f"""
        SELECT amount_tiyn, status, signed_at, created_at, updated_at, paid_at
        FROM payments
        WHERE company_id = ?
          AND ({' OR '.join(match_clauses)})
          AND status IN ({status_ph})
          {exclude_sql}
        """,
        params,
    ).fetchall()

    if now is not None:
        ref_dt = now.replace(tzinfo=UTC) if now.tzinfo is None else now.astimezone(UTC)
    else:
        parsed_now = _parse_iso_utc(utc_now_iso())
        assert parsed_now is not None
        ref_dt = parsed_now
    window_start = ref_dt - timedelta(hours=window_hours)

    total_tiyn = 0
    for row in rows:
        if row["status"] == "signed":
            raw_ts = row["signed_at"] or row["updated_at"] or row["created_at"] or row["paid_at"]
        else:
            raw_ts = row["created_at"] or row["updated_at"]
        row_dt = _parse_iso_utc(str(raw_ts) if raw_ts is not None else None)
        if row_dt is not None and row_dt >= window_start:
            total_tiyn += int(row["amount_tiyn"])
    return total_tiyn


def _payment_row_to_check_request(row: sqlite3.Row) -> CheckRequest:
    return CheckRequest(
        payer_id=str(row["company_id"]),
        recipient_name=str(row["recipient_name"]),
        recipient_bin=str(row["recipient_bin"]),
        recipient_iik=str(row["recipient_iik"]),
        recipient_bik=str(row["recipient_bik"]),
        amount_kzt=int(row["amount_tiyn"]) / 100.0,
        purpose=str(row["purpose"]),
        kbe=str(row["kbe"]),
        knp=str(row["knp"]),
    )


def hydrate_payments(
    conn: sqlite3.Connection,
    rows: list[sqlite3.Row],
    *,
    viewer: User,
    today: date,
    lang: Lang = DEFAULT_LANG,
) -> list[Payment]:
    """Convert payment DB rows into full localized §6.2 Payment models for viewer."""
    if not rows:
        return []

    include_analyst = viewer.role == "analyst"

    check_ids = [str(r["check_id"]) for r in rows if r["check_id"] is not None]
    checks_by_id: dict[str, sqlite3.Row] = {}
    if check_ids:
        ph = ",".join("?" for _ in check_ids)
        for crow in conn.execute(
            f"SELECT id, request_sha256, ruleset_version, verdict, result_json FROM checks WHERE id IN ({ph})",
            check_ids,
        ).fetchall():
            checks_by_id[str(crow["id"])] = crow

    approval_ids = [str(r["approval_id"]) for r in rows if r["approval_id"] is not None]
    approvals_by_id: dict[str, sqlite3.Row] = {}
    if approval_ids:
        ph = ",".join("?" for _ in approval_ids)
        for arow in conn.execute(
            f"SELECT * FROM approvals WHERE id IN ({ph})",
            approval_ids,
        ).fetchall():
            approvals_by_id[str(arow["id"])] = arow

    user_ids: set[int] = set()
    for r in rows:
        user_ids.add(int(r["created_by"]))
        if r["signed_by"] is not None:
            user_ids.add(int(r["signed_by"]))
    for arow in approvals_by_id.values():
        user_ids.add(int(arow["created_by"]))
        if arow["decided_by"] is not None:
            user_ids.add(int(arow["decided_by"]))

    users_cache: dict[int, UserBrief] = {}
    _load_users_brief(conn, user_ids, users_cache)
    dup_map = _find_duplicate_map(conn, rows)
    company_ids = {str(r["company_id"]) for r in rows}
    settings_map = load_company_settings_map(conn, company_ids)
    rejected_payment_ids = _load_rejected_payment_ids(conn, [str(r["id"]) for r in rows])
    rejected_requisites = _load_rejected_requisites_by_company(conn, company_ids)

    payments: list[Payment] = []
    for row in rows:
        pid = str(row["id"])
        comp_id = str(row["company_id"])
        status: PaymentStatus = row["status"]
        source: PaymentSource = row["source"]

        req = _payment_row_to_check_request(row)

        check_row = checks_by_id.get(str(row["check_id"])) if row["check_id"] is not None else None
        if check_row is not None:
            stored_check = load_check_result(str(check_row["result_json"]))
            localized_check = localize_check_result(
                stored_check,
                lang,
                include_analyst_details=include_analyst,
            )
            doc_digest: str | None = compute_document_digest(
                build_payment_document(row, check_row)
            )
        else:
            localized_check = _synthesize_seed_check(pid, lang)
            doc_digest = None

        approval_brief: ApprovalBrief | None = None
        appr_status: ProdApprovalStatus | None = None
        appr_sha: str | None = None
        if row["approval_id"] is not None:
            arow = approvals_by_id.get(str(row["approval_id"]))
            if arow is not None and arow["status"] != "superseded":
                appr_status = arow["status"]
                appr_sha = str(arow["request_sha256"])
                approval_brief = ApprovalBrief(
                    id=str(arow["id"]),
                    status=appr_status,
                    accountant_note=str(arow["accountant_note"]),
                    director_comment=(
                        str(arow["director_comment"])
                        if arow["director_comment"] is not None
                        else None
                    ),
                    trust_account=bool(arow["trust_account"]),
                    created_by=users_cache[int(arow["created_by"])],
                    created_at=str(arow["created_at"]),
                    decided_by=(
                        users_cache[int(arow["decided_by"])]
                        if arow["decided_by"] is not None
                        else None
                    ),
                    decided_at=str(arow["decided_at"]) if arow["decided_at"] is not None else None,
                )

        sup_ref = SupplierRef(
            **lookup_supplier_ref(
                conn,
                company_id=comp_id,
                recipient_bin=str(row["recipient_bin"]),
                recipient_iik=str(row["recipient_iik"]),
                today=today,
            )
        )

        comp_settings = settings_map.get(comp_id)
        threshold_tiyn = (
            comp_settings.approval_threshold_tiyn if comp_settings is not None else None
        )
        agg_72h_tiyn: int | None = None
        if threshold_tiyn is not None and threshold_tiyn > 0:
            agg_72h_tiyn = sum_supplier_payments_window_tiyn(
                conn,
                company_id=comp_id,
                recipient_bin=str(row["recipient_bin"]),
                recipient_iik=str(row["recipient_iik"]),
                exclude_payment_id=pid,
            )
        req_key = (
            comp_id,
            normalize_requisite(str(row["recipient_bin"])),
            normalize_requisite(str(row["recipient_iik"])),
        )
        perms = policy.permissions_for(
            role=viewer.role,
            status=status,
            verdict=localized_check.verdict,
            payment_request_sha256=str(row["request_sha256"]),
            approval_status=appr_status,
            approval_request_sha256=appr_sha,
            amount_tiyn=int(row["amount_tiyn"]),
            approval_threshold_tiyn=threshold_tiyn,
            aggregate_72h_tiyn=agg_72h_tiyn,
            signal_ids=[s.rule_id for s in localized_check.signals],
            prior_rejection=pid in rejected_payment_ids,
            prior_rejected_requisites=req_key in rejected_requisites,
            is_duplicate=dup_map[pid] is not None,
        )

        payments.append(
            Payment(
                id=pid,
                company_id=comp_id,
                status=status,
                source=source,
                batch_id=str(row["batch_id"]) if row["batch_id"] is not None else None,
                line_no=int(row["line_no"]) if row["line_no"] is not None else None,
                doc_number=str(row["doc_number"]),
                doc_date=str(row["doc_date"]) if row["doc_date"] is not None else None,
                request=req,
                check=localized_check,
                document_digest=doc_digest,
                approval=approval_brief,
                accountant_ack=bool(row["accountant_ack"]),
                supplier=sup_ref,
                duplicate_of=dup_map[pid],
                permissions=perms,
                created_by=users_cache[int(row["created_by"])],
                created_at=str(row["created_at"]),
                updated_at=str(row["updated_at"]),
                signed_by=(
                    users_cache[int(row["signed_by"])] if row["signed_by"] is not None else None
                ),
                signed_at=str(row["signed_at"]) if row["signed_at"] is not None else None,
            )
        )

    return payments


def hydrate_payment(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    *,
    viewer: User,
    today: date,
    lang: Lang = DEFAULT_LANG,
) -> Payment:
    """Hydrate a single payment row into a Payment DTO."""
    return hydrate_payments(conn, [row], viewer=viewer, today=today, lang=lang)[0]


def _get_payment_row_for_user(
    conn: sqlite3.Connection,
    payment_id: str,
    user: User,
) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM payments WHERE id = ?", (payment_id,)).fetchone()
    if row is None:
        raise ProdError(404, "not_found")
    ensure_company_access(user, str(row["company_id"]))
    return row


def create_payment_in_tx(
    conn: sqlite3.Connection,
    *,
    user: User,
    payload: PaymentInput,
    today: date,
    source: PaymentSource = "manual",
    batch_id: str | None = None,
    line_no: int | None = None,
    prod_store: ProdStore | None = None,
    now_iso: str | None = None,
    emit_created_audit: bool = True,
) -> tuple[str, CheckResult]:
    """Insert a new checked payment and its initial check inside an active transaction."""
    company_id = company_scope_id(user)
    if company_id is None:
        raise ProdError(403, "forbidden_role")

    ts = now_iso or utc_now_iso()
    req = payload.to_check_request(payer_id=company_id)
    req_sha = compute_request_sha256(req, resolved_payer_id=company_id)
    amount_tiyn = round(float(req.amount_kzt) * 100)
    payment_id = f"pay-{uuid.uuid4().hex[:12]}"

    store = prod_store
    if store is None:
        company_row = load_company_row(conn, company_id)
        store = ProdStore(conn, company_row, reference=get_reference_store(), today=today)

    result = check_payment(
        req,
        store,
        today=today,
        lang="ru",
        include_analyst_details=False,
        include_recent_memory=True,
        record_in_memory=False,
    )
    signal_ids = [s.rule_id for s in result.signals]

    conn.execute(
        """
        INSERT INTO payments (
            id, company_id, source, batch_id, line_no, doc_number, doc_date,
            recipient_name, recipient_bin, recipient_iik, recipient_bik,
            amount_tiyn, purpose, kbe, knp, request_sha256,
            status, check_id, approval_id, accountant_ack,
            created_by, created_at, updated_at, signed_by, signed_at, paid_at
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?, ?, ?,
            'checked', ?, NULL, 0,
            ?, ?, ?, NULL, NULL, NULL
        )
        """,
        (
            payment_id,
            company_id,
            source,
            batch_id,
            line_no,
            payload.doc_number,
            payload.doc_date,
            req.recipient_name,
            req.recipient_bin,
            req.recipient_iik,
            req.recipient_bik,
            amount_tiyn,
            req.purpose,
            req.kbe,
            req.knp,
            req_sha,
            result.check_id,
            user.id,
            ts,
            ts,
        ),
    )
    insert_check_row(
        conn,
        payment_id=payment_id,
        request_sha256=req_sha,
        result=result,
        trigger="create",
        created_by=user.id,
        created_at=ts,
    )
    if emit_created_audit:
        append_audit(
            conn,
            action="payment_created",
            timestamp=ts,
            user_id=user.id,
            user_login=user.login,
            role=user.role,
            company_id=company_id,
            payment_id=payment_id,
            check_id=result.check_id,
            batch_id=batch_id,
            request_sha256=req_sha,
            ruleset_version=result.ruleset_version,
            verdict=result.verdict,
            signal_ids=signal_ids,
            details={"source": source},
        )
    append_audit(
        conn,
        action="check",
        timestamp=ts,
        user_id=user.id,
        user_login=user.login,
        role=user.role,
        company_id=company_id,
        payment_id=payment_id,
        check_id=result.check_id,
        batch_id=batch_id,
        request_sha256=req_sha,
        ruleset_version=result.ruleset_version,
        verdict=result.verdict,
        signal_ids=signal_ids,
        details={"trigger": "create"},
    )
    return payment_id, result


def create_payment(
    conn: sqlite3.Connection,
    *,
    user: User,
    payload: PaymentInput,
    today: date,
    lang: Lang = DEFAULT_LANG,
) -> Payment:
    """Create a manual payment, run risk verification, write check + audit, and return Payment."""
    with tx(conn):
        payment_id, _ = create_payment_in_tx(
            conn,
            user=user,
            payload=payload,
            today=today,
            source="manual",
        )
    row = _get_payment_row_for_user(conn, payment_id, user)
    return hydrate_payment(conn, row, viewer=user, today=today, lang=lang)


def get_payment(
    conn: sqlite3.Connection,
    *,
    payment_id: str,
    user: User,
    today: date,
    lang: Lang = DEFAULT_LANG,
) -> Payment:
    """Fetch a single payment with company isolation (404 on foreign company)."""
    row = _get_payment_row_for_user(conn, payment_id, user)
    return hydrate_payment(conn, row, viewer=user, today=today, lang=lang)


def _empty_payment_list() -> PaymentList:
    return PaymentList(
        items=[],
        total=0,
        counts=PaymentCounts(
            by_status=dict.fromkeys(ALL_PAYMENT_STATUSES, 0),
            by_verdict=VerdictCounts(),
        ),
    )


def list_payments(
    conn: sqlite3.Connection,
    *,
    user: User,
    today: date,
    scope: PaymentScope = "queue",
    status: PaymentStatus | None = None,
    verdict: Verdict | None = None,
    batch_id: str | None = None,
    supplier_id: int | None = None,
    q: str | None = None,
    limit: int = 200,
    offset: int = 0,
    lang: Lang = DEFAULT_LANG,
) -> PaymentList:
    """List payments with filtering, pagination, and full-scope status/verdict counters."""
    scope_clauses: list[str] = []
    scope_params: list[Any] = []

    scoped_company = company_scope_id(user)
    if scoped_company is not None:
        scope_clauses.append("p.company_id = ?")
        scope_params.append(scoped_company)

    if scope == "queue":
        scope_clauses.append("p.status NOT IN ('signed', 'cancelled')")
    elif scope == "signed":
        scope_clauses.append("p.status = 'signed'")

    if batch_id is not None and batch_id.strip():
        scope_clauses.append("p.batch_id = ?")
        scope_params.append(batch_id.strip())

    if supplier_id is not None:
        sup = conn.execute(
            "SELECT company_id, bin FROM suppliers WHERE id = ?",
            (supplier_id,),
        ).fetchone()
        if sup is None:
            return _empty_payment_list()
        if scoped_company is not None and str(sup["company_id"]) != scoped_company:
            return _empty_payment_list()
        scope_clauses.append("p.company_id = ? AND p.recipient_bin = ?")
        scope_params.extend([str(sup["company_id"]), str(sup["bin"])])

    if q is not None and q.strip():
        needle = f"%{q.strip().casefold()}%"
        scope_clauses.append(
            "(py_lower(p.recipient_name) LIKE ? OR py_lower(p.recipient_bin) LIKE ? "
            "OR py_lower(p.recipient_iik) LIKE ? OR py_lower(p.doc_number) LIKE ?)"
        )
        scope_params.extend([needle, needle, needle, needle])

    scope_where = f"WHERE {' AND '.join(scope_clauses)}" if scope_clauses else ""

    by_status: dict[PaymentStatus, int] = dict.fromkeys(ALL_PAYMENT_STATUSES, 0)
    verdict_tally: dict[str, int] = {
        "green": 0,
        "yellow": 0,
        "red": 0,
        "grey": 0,
        "invalid": 0,
    }
    count_rows = conn.execute(
        f"""
        SELECT p.status, COALESCE(c.verdict, 'green') AS verdict, COUNT(*) AS cnt
        FROM payments p
        LEFT JOIN checks c ON c.id = p.check_id
        {scope_where}
        GROUP BY p.status, COALESCE(c.verdict, 'green')
        """,
        scope_params,
    ).fetchall()
    for crow in count_rows:
        st: PaymentStatus = crow["status"]
        vd = str(crow["verdict"])
        cnt = int(crow["cnt"])
        if st in by_status:
            by_status[st] += cnt
        if vd in verdict_tally:
            verdict_tally[vd] += cnt

    item_clauses = list(scope_clauses)
    item_params = list(scope_params)
    if status is not None:
        item_clauses.append("p.status = ?")
        item_params.append(status)
    if verdict is not None:
        item_clauses.append("COALESCE(c.verdict, 'green') = ?")
        item_params.append(verdict)
    item_where = f"WHERE {' AND '.join(item_clauses)}" if item_clauses else ""

    total_row = conn.execute(
        f"""
        SELECT COUNT(*)
        FROM payments p
        LEFT JOIN checks c ON c.id = p.check_id
        {item_where}
        """,
        item_params,
    ).fetchone()
    total = int(total_row[0]) if total_row is not None else 0

    bounded_limit = max(1, min(int(limit), 500))
    bounded_offset = max(0, int(offset))
    page_rows = conn.execute(
        f"""
        SELECT p.*
        FROM payments p
        LEFT JOIN checks c ON c.id = p.check_id
        {item_where}
        ORDER BY p.created_at DESC, COALESCE(p.line_no, 2147483647) ASC, p.rowid DESC
        LIMIT ? OFFSET ?
        """,
        [*item_params, bounded_limit, bounded_offset],
    ).fetchall()

    items = hydrate_payments(conn, page_rows, viewer=user, today=today, lang=lang)
    return PaymentList(
        items=items,
        total=total,
        counts=PaymentCounts(
            by_status=by_status,
            by_verdict=VerdictCounts(**verdict_tally),
        ),
    )


def list_payments_for_export(
    conn: sqlite3.Connection,
    *,
    user: User,
    today: date,
    scope: PaymentScope = "all",
    status: PaymentStatus | None = None,
    verdict: Verdict | None = None,
    batch_id: str | None = None,
    q: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 1000,
    lang: Lang = DEFAULT_LANG,
) -> list[Payment]:
    """Return filtered payments for CSV/PDF export, respecting company scope and date range."""
    parsed_from: date | None = None
    parsed_to: date | None = None
    if date_from is not None and date_from.strip():
        try:
            parsed_from = date.fromisoformat(date_from.strip())
        except ValueError as exc:
            raise ProdError(422, "validation_error") from exc
    if date_to is not None and date_to.strip():
        try:
            parsed_to = date.fromisoformat(date_to.strip())
        except ValueError as exc:
            raise ProdError(422, "validation_error") from exc
    if parsed_from is not None and parsed_to is not None and parsed_from > parsed_to:
        raise ProdError(422, "invalid_date_range")

    clauses: list[str] = []
    params: list[Any] = []

    scoped_company = company_scope_id(user)
    if scoped_company is not None:
        clauses.append("p.company_id = ?")
        params.append(scoped_company)

    if scope == "queue":
        clauses.append("p.status NOT IN ('signed', 'cancelled')")
    elif scope == "signed":
        clauses.append("p.status = 'signed'")

    if status is not None:
        clauses.append("p.status = ?")
        params.append(status)
    if verdict is not None:
        clauses.append("COALESCE(c.verdict, 'green') = ?")
        params.append(verdict)
    if batch_id is not None and batch_id.strip():
        clauses.append("p.batch_id = ?")
        params.append(batch_id.strip())
    if q is not None and q.strip():
        needle = f"%{q.strip().casefold()}%"
        clauses.append(
            "(py_lower(p.recipient_name) LIKE ? OR py_lower(p.recipient_bin) LIKE ? "
            "OR py_lower(p.recipient_iik) LIKE ? OR py_lower(p.doc_number) LIKE ?)"
        )
        params.extend([needle, needle, needle, needle])

    date_expr = "substr(COALESCE(p.paid_at, NULLIF(p.doc_date, ''), p.created_at), 1, 10)"
    if parsed_from is not None:
        clauses.append(f"{date_expr} >= ?")
        params.append(parsed_from.isoformat())
    if parsed_to is not None:
        clauses.append(f"{date_expr} <= ?")
        params.append(parsed_to.isoformat())

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    bounded_limit = max(1, min(int(limit), 2000))
    rows = conn.execute(
        f"""
        SELECT p.*
        FROM payments p
        LEFT JOIN checks c ON c.id = p.check_id
        {where_sql}
        ORDER BY p.created_at DESC, COALESCE(p.line_no, 2147483647) ASC, p.rowid DESC
        LIMIT ?
        """,
        [*params, bounded_limit],
    ).fetchall()
    return hydrate_payments(conn, rows, viewer=user, today=today, lang=lang)


def edit_payment(
    conn: sqlite3.Connection,
    *,
    payment_id: str,
    user: User,
    payload: PaymentInput,
    today: date,
    lang: Lang = DEFAULT_LANG,
) -> Payment:
    """Edit payment requisites in checked/rejected/postponed, recheck, and reset ack/approvals."""
    with tx(conn):
        row = _get_payment_row_for_user(conn, payment_id, user)
        status: PaymentStatus = row["status"]
        if status not in EDITABLE_STATUSES:
            raise ProdError(409, "not_editable")

        company_id = str(row["company_id"])
        old_sha = str(row["request_sha256"])
        req = payload.to_check_request(payer_id=company_id)
        new_sha = compute_request_sha256(req, resolved_payer_id=company_id)
        amount_tiyn = round(float(req.amount_kzt) * 100)
        now_iso = utc_now_iso()

        company_row = load_company_row(conn, company_id)
        prod_store = ProdStore(
            conn,
            company_row,
            reference=get_reference_store(),
            today=today,
            exclude_payment_id=payment_id,
        )
        result = check_payment(
            req,
            prod_store,
            today=today,
            lang="ru",
            include_analyst_details=False,
            include_recent_memory=True,
            record_in_memory=False,
        )
        signal_ids = [s.rule_id for s in result.signals]

        active_approvals = conn.execute(
            """
            SELECT id FROM approvals
            WHERE payment_id = ? AND status IN ('pending', 'approved')
            """,
            (payment_id,),
        ).fetchall()
        for arow in active_approvals:
            apr_id = str(arow["id"])
            conn.execute(
                "UPDATE approvals SET status = 'superseded' WHERE id = ?",
                (apr_id,),
            )
            append_audit(
                conn,
                action="approval_superseded",
                timestamp=now_iso,
                user_id=user.id,
                user_login=user.login,
                role=user.role,
                company_id=company_id,
                payment_id=payment_id,
                approval_id=apr_id,
                request_sha256=new_sha,
                details={"reason": "payment_edited"},
            )

        conn.execute(
            """
            UPDATE payments
            SET doc_number = ?,
                doc_date = ?,
                recipient_name = ?,
                recipient_bin = ?,
                recipient_iik = ?,
                recipient_bik = ?,
                amount_tiyn = ?,
                purpose = ?,
                kbe = ?,
                knp = ?,
                request_sha256 = ?,
                status = 'checked',
                check_id = ?,
                approval_id = NULL,
                accountant_ack = 0,
                updated_at = ?
            WHERE id = ?
            """,
            (
                payload.doc_number,
                payload.doc_date,
                req.recipient_name,
                req.recipient_bin,
                req.recipient_iik,
                req.recipient_bik,
                amount_tiyn,
                req.purpose,
                req.kbe,
                req.knp,
                new_sha,
                result.check_id,
                now_iso,
                payment_id,
            ),
        )
        insert_check_row(
            conn,
            payment_id=payment_id,
            request_sha256=new_sha,
            result=result,
            trigger="edit",
            created_by=user.id,
            created_at=now_iso,
        )
        edit_details: dict[str, Any] = {"old_request_sha256": old_sha}
        if status == "rejected":
            edit_details["previous_status"] = status
        append_audit(
            conn,
            action="payment_edited",
            timestamp=now_iso,
            user_id=user.id,
            user_login=user.login,
            role=user.role,
            company_id=company_id,
            payment_id=payment_id,
            check_id=result.check_id,
            request_sha256=new_sha,
            ruleset_version=result.ruleset_version,
            verdict=result.verdict,
            signal_ids=signal_ids,
            details=edit_details,
        )
        append_audit(
            conn,
            action="check",
            timestamp=now_iso,
            user_id=user.id,
            user_login=user.login,
            role=user.role,
            company_id=company_id,
            payment_id=payment_id,
            check_id=result.check_id,
            request_sha256=new_sha,
            ruleset_version=result.ruleset_version,
            verdict=result.verdict,
            signal_ids=signal_ids,
            details={"trigger": "edit"},
        )

    updated = _get_payment_row_for_user(conn, payment_id, user)
    return hydrate_payment(conn, updated, viewer=user, today=today, lang=lang)


def recheck_payment(
    conn: sqlite3.Connection,
    *,
    payment_id: str,
    user: User,
    today: date,
    lang: Lang = DEFAULT_LANG,
) -> Payment:
    """Re-run risk evaluation on an editable payment and record a new check row."""
    with tx(conn):
        row = _get_payment_row_for_user(conn, payment_id, user)
        status: PaymentStatus = row["status"]
        if status not in EDITABLE_STATUSES:
            raise ProdError(409, "not_editable")

        company_id = str(row["company_id"])
        req = _payment_row_to_check_request(row)
        req_sha = str(row["request_sha256"])
        now_iso = utc_now_iso()

        company_row = load_company_row(conn, company_id)
        prod_store = ProdStore(
            conn,
            company_row,
            reference=get_reference_store(),
            today=today,
            exclude_payment_id=payment_id,
        )
        result = check_payment(
            req,
            prod_store,
            today=today,
            lang="ru",
            include_analyst_details=False,
            include_recent_memory=True,
            record_in_memory=False,
        )
        signal_ids = [s.rule_id for s in result.signals]

        insert_check_row(
            conn,
            payment_id=payment_id,
            request_sha256=req_sha,
            result=result,
            trigger="recheck",
            created_by=user.id,
            created_at=now_iso,
        )
        conn.execute(
            """
            UPDATE payments
            SET check_id = ?, accountant_ack = 0, updated_at = ?
            WHERE id = ?
            """,
            (result.check_id, now_iso, payment_id),
        )
        append_audit(
            conn,
            action="check",
            timestamp=now_iso,
            user_id=user.id,
            user_login=user.login,
            role=user.role,
            company_id=company_id,
            payment_id=payment_id,
            check_id=result.check_id,
            request_sha256=req_sha,
            ruleset_version=result.ruleset_version,
            verdict=result.verdict,
            signal_ids=signal_ids,
            details={"trigger": "recheck"},
        )

    updated = _get_payment_row_for_user(conn, payment_id, user)
    return hydrate_payment(conn, updated, viewer=user, today=today, lang=lang)


def send_to_director(
    conn: sqlite3.Connection,
    *,
    payment_id: str,
    user: User,
    accountant_note: str,
    today: date,
    lang: Lang = DEFAULT_LANG,
) -> Payment:
    """Submit a checked payment for director approval (idempotent when already pending_approval)."""
    cleaned_note = clean_text_field(accountant_note)
    with tx(conn):
        row = _get_payment_row_for_user(conn, payment_id, user)
        status: PaymentStatus = row["status"]
        if status == "pending_approval":
            return hydrate_payment(conn, row, viewer=user, today=today, lang=lang)
        if status != "checked":
            raise ProdError(409, "invalid_transition")

        check_id = row["check_id"]
        if check_id is None:
            raise ProdError(409, "invalid_transition")
        check_row = conn.execute(
            "SELECT verdict, ruleset_version, signal_ids_json FROM checks WHERE id = ?",
            (str(check_id),),
        ).fetchone()
        if check_row is None:
            raise ProdError(409, "invalid_transition")
        if str(check_row["verdict"]) == "invalid":
            raise ProdError(409, "invalid_requisites")

        company_id = str(row["company_id"])
        req_sha = str(row["request_sha256"])
        apr_id = f"apr-{uuid.uuid4().hex[:10]}"
        now_iso = utc_now_iso()
        signal_ids = json.loads(str(check_row["signal_ids_json"]))

        conn.execute(
            """
            INSERT INTO approvals (
                id, payment_id, check_id, request_sha256, status,
                accountant_note, director_comment, trust_account,
                created_by, created_at, decided_by, decided_at
            ) VALUES (?, ?, ?, ?, 'pending', ?, NULL, 0, ?, ?, NULL, NULL)
            """,
            (apr_id, payment_id, str(check_id), req_sha, cleaned_note, user.id, now_iso),
        )
        conn.execute(
            """
            UPDATE payments
            SET status = 'pending_approval', approval_id = ?, updated_at = ?
            WHERE id = ?
            """,
            (apr_id, now_iso, payment_id),
        )
        append_audit(
            conn,
            action="send_to_director",
            timestamp=now_iso,
            user_id=user.id,
            user_login=user.login,
            role=user.role,
            company_id=company_id,
            payment_id=payment_id,
            approval_id=apr_id,
            check_id=str(check_id),
            request_sha256=req_sha,
            ruleset_version=str(check_row["ruleset_version"]),
            verdict=check_row["verdict"],
            signal_ids=[str(s) for s in signal_ids],
            details={"accountant_note": cleaned_note} if cleaned_note else {},
        )

    updated = _get_payment_row_for_user(conn, payment_id, user)
    return hydrate_payment(conn, updated, viewer=user, today=today, lang=lang)


def postpone_payment(
    conn: sqlite3.Connection,
    *,
    payment_id: str,
    user: User,
    note: str,
    today: date,
    lang: Lang = DEFAULT_LANG,
) -> Payment:
    """Move a checked or approved payment to postponed status."""
    cleaned_note = clean_text_field(note)
    with tx(conn):
        row = _get_payment_row_for_user(conn, payment_id, user)
        if row["status"] not in POSTPONABLE_STATUSES:
            raise ProdError(409, "invalid_transition")

        now_iso = utc_now_iso()
        conn.execute(
            "UPDATE payments SET status = 'postponed', updated_at = ? WHERE id = ?",
            (now_iso, payment_id),
        )
        append_audit(
            conn,
            action="postpone",
            timestamp=now_iso,
            user_id=user.id,
            user_login=user.login,
            role=user.role,
            company_id=str(row["company_id"]),
            payment_id=payment_id,
            check_id=str(row["check_id"]) if row["check_id"] is not None else None,
            request_sha256=str(row["request_sha256"]),
            details={"note": cleaned_note} if cleaned_note else {},
        )

    updated = _get_payment_row_for_user(conn, payment_id, user)
    return hydrate_payment(conn, updated, viewer=user, today=today, lang=lang)


def resume_payment(
    conn: sqlite3.Connection,
    *,
    payment_id: str,
    user: User,
    today: date,
    lang: Lang = DEFAULT_LANG,
) -> Payment:
    """Resume a postponed payment back to checked status with a fresh risk check."""
    with tx(conn):
        row = _get_payment_row_for_user(conn, payment_id, user)
        if row["status"] != "postponed":
            raise ProdError(409, "invalid_transition")

        company_id = str(row["company_id"])
        req = _payment_row_to_check_request(row)
        req_sha = str(row["request_sha256"])
        now_iso = utc_now_iso()

        company_row = load_company_row(conn, company_id)
        prod_store = ProdStore(
            conn,
            company_row,
            reference=get_reference_store(),
            today=today,
            exclude_payment_id=payment_id,
        )
        result = check_payment(
            req,
            prod_store,
            today=today,
            lang="ru",
            include_analyst_details=False,
            include_recent_memory=True,
            record_in_memory=False,
        )
        signal_ids = [s.rule_id for s in result.signals]

        insert_check_row(
            conn,
            payment_id=payment_id,
            request_sha256=req_sha,
            result=result,
            trigger="resume",
            created_by=user.id,
            created_at=now_iso,
        )
        conn.execute(
            """
            UPDATE payments
            SET status = 'checked', check_id = ?, accountant_ack = 0, updated_at = ?
            WHERE id = ?
            """,
            (result.check_id, now_iso, payment_id),
        )
        append_audit(
            conn,
            action="resume",
            timestamp=now_iso,
            user_id=user.id,
            user_login=user.login,
            role=user.role,
            company_id=company_id,
            payment_id=payment_id,
            check_id=result.check_id,
            request_sha256=req_sha,
            ruleset_version=result.ruleset_version,
            verdict=result.verdict,
            signal_ids=signal_ids,
        )
        append_audit(
            conn,
            action="check",
            timestamp=now_iso,
            user_id=user.id,
            user_login=user.login,
            role=user.role,
            company_id=company_id,
            payment_id=payment_id,
            check_id=result.check_id,
            request_sha256=req_sha,
            ruleset_version=result.ruleset_version,
            verdict=result.verdict,
            signal_ids=signal_ids,
            details={"trigger": "resume"},
        )

    updated = _get_payment_row_for_user(conn, payment_id, user)
    return hydrate_payment(conn, updated, viewer=user, today=today, lang=lang)


def cancel_payment(
    conn: sqlite3.Connection,
    *,
    payment_id: str,
    user: User,
    note: str,
    today: date,
    lang: Lang = DEFAULT_LANG,
) -> Payment:
    """Cancel a payment from checked, rejected, postponed, or approved status."""
    cleaned_note = clean_text_field(note)
    with tx(conn):
        row = _get_payment_row_for_user(conn, payment_id, user)
        if row["status"] not in CANCELLABLE_STATUSES:
            raise ProdError(409, "invalid_transition")

        now_iso = utc_now_iso()
        conn.execute(
            "UPDATE payments SET status = 'cancelled', updated_at = ? WHERE id = ?",
            (now_iso, payment_id),
        )
        append_audit(
            conn,
            action="cancel",
            timestamp=now_iso,
            user_id=user.id,
            user_login=user.login,
            role=user.role,
            company_id=str(row["company_id"]),
            payment_id=payment_id,
            check_id=str(row["check_id"]) if row["check_id"] is not None else None,
            request_sha256=str(row["request_sha256"]),
            details={"note": cleaned_note} if cleaned_note else {},
        )

    updated = _get_payment_row_for_user(conn, payment_id, user)
    return hydrate_payment(conn, updated, viewer=user, today=today, lang=lang)


def _record_sign_denied(
    conn: sqlite3.Connection,
    *,
    user: User,
    company_id: str,
    payment_id: str,
    code: str,
    approval_id: str | None = None,
    check_id: str | None = None,
    request_sha256: str | None = None,
    ruleset_version: str | None = None,
    verdict: Verdict | None = None,
    signal_ids: list[str] | None = None,
    extra_details: dict[str, Any] | None = None,
) -> None:
    """Record a sign_denied audit entry in a short independent transaction."""
    details: dict[str, Any] = {"code": code}
    if extra_details:
        details.update(extra_details)
    with tx(conn):
        append_audit(
            conn,
            action="sign_denied",
            user_id=user.id,
            user_login=user.login,
            role=user.role,
            company_id=company_id,
            payment_id=payment_id,
            approval_id=approval_id,
            check_id=check_id,
            request_sha256=request_sha256,
            ruleset_version=ruleset_version,
            verdict=verdict,
            signal_ids=signal_ids,
            details=details,
        )


def sign_payment(
    conn: sqlite3.Connection,
    *,
    payment_id: str,
    user: User,
    accountant_ack: bool,
    today: date,
    lang: Lang = DEFAULT_LANG,
    prod_store: ProdStore | None = None,
    document_digest: str | None = None,
    signature: str | None = None,
    signer: SignerKind | None = None,
    signature_verifier: SignatureVerifier | SimulatedSigner | None = None,
    server_simulated: bool = False,
    now: datetime | None = None,
) -> Payment:
    """Enforce the §5 server-side signing gateway inside BEGIN IMMEDIATE and sign if allowed."""
    if user.role not in ("accountant", "director"):
        raise ProdError(403, "forbidden_role")

    if not server_simulated:
        if document_digest is None or not document_digest.strip():
            raise ProdError(422, "validation_error")
        if signer is None or signature is None:
            raise ProdError(422, "validation_error")

    denied_code: str | None = None
    denied_status: int = 409
    denied_reason: str | None = None
    denied_new_signal_ids: list[str] = []
    denied_ctx: dict[str, Any] = {}
    verdict_changed_flag = False

    with tx(conn):
        row = _get_payment_row_for_user(conn, payment_id, user)
        company_id = str(row["company_id"])
        status: PaymentStatus = row["status"]
        req_sha = str(row["request_sha256"])
        current_check_id = str(row["check_id"]) if row["check_id"] is not None else None
        current_approval_id = str(row["approval_id"]) if row["approval_id"] is not None else None

        # Rows 1-4: reject non-signable statuses before re-running risk engine
        pre_block = policy.pre_sign_status_check(status)
        if pre_block is not None:
            prev_verdict: Verdict | None = None
            if current_check_id is not None:
                crow = conn.execute(
                    "SELECT verdict FROM checks WHERE id = ?",
                    (current_check_id,),
                ).fetchone()
                if crow is not None:
                    prev_verdict = crow["verdict"]
            denied_code = pre_block
            denied_ctx = {
                "company_id": company_id,
                "approval_id": current_approval_id,
                "check_id": current_check_id,
                "request_sha256": req_sha,
                "verdict": prev_verdict,
                "extra_details": {"accountant_ack": accountant_ack},
            }
        else:
            current_check_row = (
                conn.execute(
                    "SELECT id, request_sha256, ruleset_version, verdict FROM checks WHERE id = ?",
                    (current_check_id,),
                ).fetchone()
                if current_check_id is not None
                else None
            )

            binding_ok = True
            effective_digest: str | None = None
            if server_simulated:
                if current_check_row is not None:
                    effective_digest = compute_document_digest(
                        build_payment_document(row, current_check_row)
                    )
            elif document_digest is not None:
                if current_check_row is None:
                    binding_ok = False
                else:
                    try:
                        verify_document_binding(document_digest, row, current_check_row)
                        effective_digest = document_digest
                    except DocumentMismatchError:
                        binding_ok = False

            if not binding_ok:
                denied_code = "document_mismatch"
                denied_status = 409
                denied_ctx = {
                    "company_id": company_id,
                    "approval_id": current_approval_id,
                    "check_id": current_check_id,
                    "request_sha256": req_sha,
                    "ruleset_version": (
                        str(current_check_row["ruleset_version"])
                        if current_check_row is not None
                        else None
                    ),
                    "verdict": (
                        current_check_row["verdict"] if current_check_row is not None else None
                    ),
                    "extra_details": {
                        "accountant_ack": accountant_ack,
                        **({"signer": signer} if signer is not None else {}),
                    },
                }
            else:
                approval_status: ProdApprovalStatus | None = None
                approval_sha: str | None = None
                ref_check_id: str | None = current_check_id

                if current_approval_id is not None:
                    arow = conn.execute(
                        "SELECT id, status, check_id, request_sha256 FROM approvals WHERE id = ?",
                        (current_approval_id,),
                    ).fetchone()
                    if arow is not None and arow["status"] != "superseded":
                        approval_status = arow["status"]
                        approval_sha = str(arow["request_sha256"])
                        if approval_status == "approved":
                            ref_check_id = str(arow["check_id"])

                previous_verdict: Verdict = "green"
                previous_signal_ids: list[str] = []
                if ref_check_id is not None:
                    prev_crow = conn.execute(
                        "SELECT verdict, signal_ids_json FROM checks WHERE id = ?",
                        (ref_check_id,),
                    ).fetchone()
                    if prev_crow is not None:
                        previous_verdict = prev_crow["verdict"]
                        try:
                            parsed_prev = json.loads(str(prev_crow["signal_ids_json"]))
                            if isinstance(parsed_prev, list):
                                previous_signal_ids = [str(s) for s in parsed_prev]
                        except (TypeError, ValueError):
                            previous_signal_ids = []

                # Row 5: always re-run risk engine at signing time (trigger='sign')
                req = _payment_row_to_check_request(row)
                store = prod_store
                if store is None:
                    company_row = load_company_row(conn, company_id)
                    store = ProdStore(
                        conn,
                        company_row,
                        reference=get_reference_store(),
                        today=today,
                        exclude_payment_id=payment_id,
                    )
                prev_excluded = store.exclude_payment_id
                store.exclude_payment_id = payment_id
                try:
                    fresh_result = check_payment(
                        req,
                        store,
                        today=today,
                        lang="ru",
                        include_analyst_details=False,
                        include_recent_memory=True,
                        record_in_memory=False,
                    )
                finally:
                    store.exclude_payment_id = prev_excluded

                now_iso = utc_now_iso()
                fresh_signals = [s.rule_id for s in fresh_result.signals]
                new_critical_signals = (
                    policy.find_new_critical_signals(previous_signal_ids, fresh_result.signals)
                    if approval_status == "approved"
                    else []
                )
                dup_of = _find_duplicate_map(conn, [row]).get(payment_id)

                comp_settings = get_company_settings(conn, company_id)
                has_prior_rejection = _has_rejected_payment_history(conn, payment_id)
                has_rejected_requisites = _is_rejected_requisites(
                    conn,
                    company_id,
                    req.recipient_bin,
                    req.recipient_iik,
                )
                agg_72h_tiyn: int | None = None
                if (
                    comp_settings.approval_threshold_tiyn is not None
                    and comp_settings.approval_threshold_tiyn > 0
                ):
                    ref_dt = (
                        now
                        if now is not None
                        else (
                            today
                            if isinstance(today, datetime)
                            else _parse_iso_utc(now_iso)
                        )
                    )
                    agg_72h_tiyn = sum_supplier_payments_window_tiyn(
                        conn,
                        company_id=company_id,
                        recipient_bin=req.recipient_bin,
                        recipient_iik=req.recipient_iik,
                        exclude_payment_id=payment_id,
                        now=ref_dt,
                    )
                decision = policy.sign_decision(
                    role=user.role,
                    status=status,
                    previous_verdict=previous_verdict,
                    fresh_verdict=fresh_result.verdict,
                    payment_request_sha256=req_sha,
                    approval_status=approval_status,
                    approval_request_sha256=approval_sha,
                    accountant_ack=accountant_ack,
                    amount_tiyn=int(row["amount_tiyn"]),
                    approval_threshold_tiyn=comp_settings.approval_threshold_tiyn,
                    aggregate_72h_tiyn=agg_72h_tiyn,
                    signal_ids=fresh_signals,
                    prior_rejection=has_prior_rejection,
                    prior_rejected_requisites=has_rejected_requisites,
                    is_duplicate=dup_of is not None,
                    previous_signal_ids=previous_signal_ids,
                    fresh_signals=fresh_result.signals,
                )

                if not decision.allowed:
                    assert decision.block_code is not None
                    insert_check_row(
                        conn,
                        payment_id=payment_id,
                        request_sha256=req_sha,
                        result=fresh_result,
                        trigger="sign",
                        created_by=user.id,
                        created_at=now_iso,
                    )
                    denied_code = decision.block_code
                    denied_reason = decision.block_reason
                    if decision.supersede_approval:
                        verdict_changed_flag = True
                        supersede_reason = (
                            "new_signals"
                            if decision.block_reason == "new_signals"
                            else "verdict_changed"
                        )
                        supersede_details: dict[str, Any] = {
                            "reason": supersede_reason,
                            "previous_verdict": previous_verdict,
                            "fresh_verdict": fresh_result.verdict,
                        }
                        if supersede_reason == "new_signals":
                            denied_new_signal_ids = list(new_critical_signals)
                            supersede_details["new_signal_ids"] = denied_new_signal_ids
                        active_approvals = conn.execute(
                            """
                            SELECT id FROM approvals
                            WHERE payment_id = ? AND status IN ('pending', 'approved')
                            """,
                            (payment_id,),
                        ).fetchall()
                        for arow in active_approvals:
                            apr_id = str(arow["id"])
                            conn.execute(
                                "UPDATE approvals SET status = 'superseded' WHERE id = ?",
                                (apr_id,),
                            )
                            append_audit(
                                conn,
                                action="approval_superseded",
                                timestamp=now_iso,
                                user_id=user.id,
                                user_login=user.login,
                                role=user.role,
                                company_id=company_id,
                                payment_id=payment_id,
                                approval_id=apr_id,
                                check_id=fresh_result.check_id,
                                request_sha256=req_sha,
                                ruleset_version=fresh_result.ruleset_version,
                                verdict=fresh_result.verdict,
                                signal_ids=fresh_signals,
                                details=supersede_details,
                            )
                        conn.execute(
                            """
                            UPDATE payments
                            SET check_id = ?,
                                status = 'checked',
                                approval_id = NULL,
                                accountant_ack = 0,
                                updated_at = ?
                            WHERE id = ?
                            """,
                            (fresh_result.check_id, now_iso, payment_id),
                        )
                    else:
                        conn.execute(
                            "UPDATE payments SET check_id = ?, updated_at = ? WHERE id = ?",
                            (fresh_result.check_id, now_iso, payment_id),
                        )

                    append_audit(
                        conn,
                        action="check",
                        timestamp=now_iso,
                        user_id=user.id,
                        user_login=user.login,
                        role=user.role,
                        company_id=company_id,
                        payment_id=payment_id,
                        check_id=fresh_result.check_id,
                        request_sha256=req_sha,
                        ruleset_version=fresh_result.ruleset_version,
                        verdict=fresh_result.verdict,
                        signal_ids=fresh_signals,
                        details={"trigger": "sign"},
                    )
                    denied_extra: dict[str, Any] = (
                        {
                            "previous_verdict": previous_verdict,
                            "fresh_verdict": fresh_result.verdict,
                            "accountant_ack": accountant_ack,
                        }
                        if verdict_changed_flag
                        else {"accountant_ack": accountant_ack}
                    )
                    if denied_reason == "new_signals":
                        denied_extra["reason"] = "new_signals"
                        denied_extra["new_signal_ids"] = denied_new_signal_ids
                    elif denied_reason == "threshold_aggregate":
                        denied_extra["reason"] = "threshold_aggregate"
                        denied_extra["aggregate_72h_tiyn"] = agg_72h_tiyn or 0
                        denied_extra["total_72h_tiyn"] = int(row["amount_tiyn"]) + (
                            agg_72h_tiyn or 0
                        )
                        denied_extra["threshold_tiyn"] = comp_settings.approval_threshold_tiyn
                    if denied_code == "duplicate_requires_approval" and dup_of is not None:
                        denied_extra["duplicate_of"] = dup_of
                    denied_ctx = {
                        "company_id": company_id,
                        "approval_id": current_approval_id,
                        "check_id": fresh_result.check_id,
                        "request_sha256": req_sha,
                        "ruleset_version": fresh_result.ruleset_version,
                        "verdict": fresh_result.verdict,
                        "signal_ids": fresh_signals,
                        "extra_details": denied_extra,
                    }
                else:
                    # Verify cryptographic / simulated signature BEFORE mutating payment status
                    sig_result: SignatureVerificationResult | None = None
                    if server_simulated:
                        if effective_digest is None:
                            effective_digest = compute_document_digest(
                                build_payment_document(row, fresh_result)
                            )
                        sim_signer = (
                            signature_verifier
                            if isinstance(signature_verifier, SimulatedSigner)
                            else SimulatedSigner()
                        )
                        server_sig = sim_signer.sign(effective_digest, company_id)
                        sig_result = verify_signature(
                            "simulated",
                            effective_digest,
                            server_sig,
                            company_id,
                            verifier=sim_signer,
                        )
                    elif signer is not None and signature is not None:
                        assert effective_digest is not None
                        if signer == "simulated" and signature == "":
                            sim_signer = (
                                signature_verifier
                                if isinstance(signature_verifier, SimulatedSigner)
                                else SimulatedSigner()
                            )
                            computed_sig = sim_signer.sign(effective_digest, company_id)
                            sig_result = verify_signature(
                                "simulated",
                                effective_digest,
                                computed_sig,
                                company_id,
                                verifier=sim_signer,
                            )
                        elif signer == "ncalayer" and not signature.strip():
                            denied_code = "validation_error"
                            denied_status = 422
                            denied_ctx = {
                                "company_id": company_id,
                                "approval_id": current_approval_id,
                                "check_id": current_check_id,
                                "request_sha256": req_sha,
                                "ruleset_version": fresh_result.ruleset_version,
                                "verdict": fresh_result.verdict,
                                "signal_ids": fresh_signals,
                                "extra_details": {
                                    "accountant_ack": accountant_ack,
                                    "signer": signer,
                                    "document_digest": effective_digest,
                                    "reason": "empty_signature",
                                },
                            }
                        else:
                            try:
                                sig_result = verify_signature(
                                    signer,
                                    effective_digest,
                                    signature,
                                    company_id,
                                    verifier=signature_verifier,
                                )
                            except NotImplementedError:
                                denied_code = "signature_verification_unavailable"
                                denied_status = 501
                                denied_ctx = {
                                    "company_id": company_id,
                                    "approval_id": current_approval_id,
                                    "check_id": current_check_id,
                                    "request_sha256": req_sha,
                                    "ruleset_version": fresh_result.ruleset_version,
                                    "verdict": fresh_result.verdict,
                                    "signal_ids": fresh_signals,
                                    "extra_details": {
                                        "accountant_ack": accountant_ack,
                                        "signer": signer,
                                        "document_digest": effective_digest,
                                    },
                                }
                            except InvalidSignerError:
                                denied_code = "validation_error"
                                denied_status = 422
                                denied_ctx = {
                                    "company_id": company_id,
                                    "approval_id": current_approval_id,
                                    "check_id": current_check_id,
                                    "request_sha256": req_sha,
                                    "ruleset_version": fresh_result.ruleset_version,
                                    "verdict": fresh_result.verdict,
                                    "signal_ids": fresh_signals,
                                    "extra_details": {
                                        "accountant_ack": accountant_ack,
                                        "signer": str(signer),
                                        "document_digest": effective_digest,
                                    },
                                }
                            else:
                                if not sig_result.verified:
                                    denied_code = "validation_error"
                                    denied_status = 422
                                    denied_ctx = {
                                        "company_id": company_id,
                                        "approval_id": current_approval_id,
                                        "check_id": current_check_id,
                                        "request_sha256": req_sha,
                                        "ruleset_version": fresh_result.ruleset_version,
                                        "verdict": fresh_result.verdict,
                                        "signal_ids": fresh_signals,
                                        "extra_details": {
                                            "accountant_ack": accountant_ack,
                                            "signer": sig_result.signer,
                                            "label": sig_result.label,
                                            "simulated": sig_result.simulated,
                                            "document_digest": effective_digest,
                                            "reason": "invalid_signature",
                                        },
                                    }

                    if denied_code is None:
                        insert_check_row(
                            conn,
                            payment_id=payment_id,
                            request_sha256=req_sha,
                            result=fresh_result,
                            trigger="sign",
                            created_by=user.id,
                            created_at=now_iso,
                        )
                        new_ack = 1 if decision.set_accountant_ack else int(row["accountant_ack"])
                        paid_at_str = today.isoformat()
                        cur = conn.execute(
                            """
                            UPDATE payments
                            SET status = 'signed',
                                check_id = ?,
                                accountant_ack = ?,
                                signed_by = ?,
                                signed_at = ?,
                                paid_at = ?,
                                updated_at = ?
                            WHERE id = ? AND status IN ('checked', 'approved')
                            """,
                            (
                                fresh_result.check_id,
                                new_ack,
                                user.id,
                                now_iso,
                                paid_at_str,
                                now_iso,
                                payment_id,
                            ),
                        )
                        if cur.rowcount != 1:
                            denied_code = "already_signed"
                            denied_ctx = {
                                "company_id": company_id,
                                "approval_id": current_approval_id,
                                "check_id": fresh_result.check_id,
                                "request_sha256": req_sha,
                                "ruleset_version": fresh_result.ruleset_version,
                                "verdict": fresh_result.verdict,
                                "signal_ids": fresh_signals,
                            }
                        else:
                            if not has_rejected_requisites:
                                register_signed_payment(
                                    conn,
                                    company_id=company_id,
                                    recipient_bin=req.recipient_bin,
                                    recipient_name=req.recipient_name,
                                    recipient_iik=req.recipient_iik,
                                    recipient_bik=req.recipient_bik,
                                    paid_at=paid_at_str,
                                    payment_id=payment_id,
                                )
                            store.invalidate_history_cache()

                            sign_details: dict[str, Any] = {
                                "accountant_ack": bool(new_ack),
                            }
                            if sig_result is not None and effective_digest is not None:
                                sign_details.update(
                                    {
                                        "document_digest": effective_digest,
                                        "signer": sig_result.signer,
                                        "label": sig_result.label,
                                        "simulated": sig_result.simulated,
                                    }
                                )
                                if sig_result.details is not None:
                                    sign_details["certificate"] = {
                                        "signer_subject": sig_result.details.signer_subject,
                                        "signer_iin_bin": sig_result.details.signer_iin_bin,
                                        "certificate_serial": sig_result.details.certificate_serial,
                                        "signed_at": sig_result.details.signed_at,
                                    }

                            append_audit(
                                conn,
                                action="check",
                                timestamp=now_iso,
                                user_id=user.id,
                                user_login=user.login,
                                role=user.role,
                                company_id=company_id,
                                payment_id=payment_id,
                                check_id=fresh_result.check_id,
                                request_sha256=req_sha,
                                ruleset_version=fresh_result.ruleset_version,
                                verdict=fresh_result.verdict,
                                signal_ids=fresh_signals,
                                details={"trigger": "sign"},
                            )
                            append_audit(
                                conn,
                                action="sign",
                                timestamp=now_iso,
                                user_id=user.id,
                                user_login=user.login,
                                role=user.role,
                                company_id=company_id,
                                payment_id=payment_id,
                                approval_id=current_approval_id,
                                check_id=fresh_result.check_id,
                                request_sha256=req_sha,
                                ruleset_version=fresh_result.ruleset_version,
                                verdict=fresh_result.verdict,
                                signal_ids=fresh_signals,
                                details=sign_details,
                            )

    if denied_code is not None:
        _record_sign_denied(
            conn,
            user=user,
            payment_id=payment_id,
            code=denied_code,
            **denied_ctx,
        )
        if verdict_changed_flag:
            refreshed = _get_payment_row_for_user(conn, payment_id, user)
            updated_payment = hydrate_payment(conn, refreshed, viewer=user, today=today, lang=lang)
            vc_extra: dict[str, Any] = {"payment": updated_payment.model_dump(mode="json")}
            if denied_reason == "new_signals":
                vc_extra["reason"] = "new_signals"
                vc_extra["new_signal_ids"] = denied_new_signal_ids
            raise ProdError(
                409,
                "verdict_changed",
                extra=vc_extra,
            )
        if denied_reason == "threshold_aggregate":
            raise ProdError(
                denied_status,
                denied_code,
                detail=localize_prod_error("threshold_aggregate", lang),
                extra={"reason": "threshold_aggregate"},
            )
        raise ProdError(denied_status, denied_code)

    signed_row = _get_payment_row_for_user(conn, payment_id, user)
    return hydrate_payment(conn, signed_row, viewer=user, today=today, lang=lang)


def _hydrate_approvals(
    conn: sqlite3.Connection,
    rows: list[sqlite3.Row],
    *,
    viewer: User,
    lang: Lang = DEFAULT_LANG,
) -> list[ProdApproval]:
    if not rows:
        return []

    include_analyst = viewer.role == "analyst"

    user_ids: set[int] = set()
    for r in rows:
        user_ids.add(int(r["created_by"]))
        if r["decided_by"] is not None:
            user_ids.add(int(r["decided_by"]))
    users_cache: dict[int, UserBrief] = {}
    _load_users_brief(conn, user_ids, users_cache)
    rejected_requisites = _load_rejected_requisites_by_company(
        conn, {str(r["company_id"]) for r in rows}
    )

    items: list[ProdApproval] = []
    for r in rows:
        req = CheckRequest(
            payer_id=str(r["company_id"]),
            recipient_name=str(r["recipient_name"]),
            recipient_bin=str(r["recipient_bin"]),
            recipient_iik=str(r["recipient_iik"]),
            recipient_bik=str(r["recipient_bik"]),
            amount_kzt=int(r["amount_tiyn"]) / 100.0,
            purpose=str(r["purpose"]),
            kbe=str(r["kbe"]),
            knp=str(r["knp"]),
        )
        stored_check = load_check_result(str(r["result_json"]))
        localized_check = localize_check_result(
            stored_check,
            lang,
            include_analyst_details=include_analyst,
        )
        req_is_rejected = (
            str(r["company_id"]),
            normalize_requisite(str(r["recipient_bin"])),
            normalize_requisite(str(r["recipient_iik"])),
        ) in rejected_requisites
        items.append(
            ProdApproval(
                id=str(r["id"]),
                payment_id=str(r["payment_id"]),
                request=req,
                check=localized_check,
                status=r["status"],
                accountant_note=str(r["accountant_note"]),
                director_comment=(
                    str(r["director_comment"]) if r["director_comment"] is not None else None
                ),
                trust_account=bool(r["trust_account"]),
                can_trust=policy.can_trust(stored_check) and not req_is_rejected,
                created_by=users_cache[int(r["created_by"])],
                created_at=str(r["created_at"]),
                decided_by=(
                    users_cache[int(r["decided_by"])] if r["decided_by"] is not None else None
                ),
                decided_at=str(r["decided_at"]) if r["decided_at"] is not None else None,
            )
        )
    return items


def list_approvals(
    conn: sqlite3.Connection,
    *,
    user: User,
    status: ProdApprovalStatus | None = None,
    lang: Lang = DEFAULT_LANG,
) -> list[ProdApproval]:
    """List approvals (default: all except superseded), pending first then newest."""
    clauses: list[str] = []
    params: list[Any] = []

    scoped_company = company_scope_id(user)
    if scoped_company is not None:
        clauses.append("p.company_id = ?")
        params.append(scoped_company)

    if status is not None:
        clauses.append("a.status = ?")
        params.append(status)
    else:
        clauses.append("a.status != 'superseded'")

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"""
        SELECT
            a.*,
            p.company_id,
            p.recipient_name,
            p.recipient_bin,
            p.recipient_iik,
            p.recipient_bik,
            p.amount_tiyn,
            p.purpose,
            p.kbe,
            p.knp,
            c.result_json
        FROM approvals a
        JOIN payments p ON p.id = a.payment_id
        JOIN checks c ON c.id = a.check_id
        {where_sql}
        ORDER BY CASE WHEN a.status = 'pending' THEN 0 ELSE 1 END ASC,
                 a.created_at DESC,
                 a.rowid DESC
        """,
        params,
    ).fetchall()
    return _hydrate_approvals(conn, rows, viewer=user, lang=lang)


def decide_approval(
    conn: sqlite3.Connection,
    *,
    approval_id: str,
    user: User,
    payload: ProdApprovalDecisionRequest,
    today: date,
    lang: Lang = DEFAULT_LANG,
) -> ProdApproval:
    """Record director approval or rejection with demo-equivalent 422 rules and optional trust."""
    if user.role != "director":
        raise ProdError(403, "forbidden_role")

    with tx(conn):
        row = conn.execute(
            """
            SELECT
                a.*,
                p.company_id,
                p.recipient_name,
                p.recipient_bin,
                p.recipient_iik,
                p.recipient_bik,
                p.amount_tiyn,
                p.purpose,
                p.kbe,
                p.knp,
                c.result_json
            FROM approvals a
            JOIN payments p ON p.id = a.payment_id
            JOIN checks c ON c.id = a.check_id
            WHERE a.id = ?
            """,
            (approval_id,),
        ).fetchone()
        if row is None:
            raise ProdError(404, "not_found")

        company_id = str(row["company_id"])
        ensure_company_access(user, company_id)

        current_status: ProdApprovalStatus = row["status"]
        if current_status == "superseded":
            raise ProdError(409, "approval_superseded")
        if current_status != "pending":
            raise ProdError(409, "approval_already_decided")

        stored_check = load_check_result(str(row["result_json"]))
        req_bin = normalize_requisite(str(row["recipient_bin"]))
        req_iik = normalize_requisite(str(row["recipient_iik"]))
        requisites_previously_rejected = _is_rejected_requisites(
            conn, company_id, req_bin, req_iik
        )
        validation_err = policy.validate_director_decision(
            decision=payload.decision,
            check=stored_check,
            director_comment=payload.director_comment,
            trust_account=payload.trust_account,
            requisites_previously_rejected=requisites_previously_rejected,
        )
        if validation_err is not None:
            raise ProdError(422, validation_err)

        cleaned_comment = (
            clean_text_field(payload.director_comment)
            if payload.director_comment is not None
            else ""
        )
        stored_comment = cleaned_comment if cleaned_comment else None
        grant_trust = (
            payload.decision == "approved"
            and payload.trust_account
            and not requisites_previously_rejected
        )
        now_iso = utc_now_iso()
        payment_id = str(row["payment_id"])
        new_payment_status: PaymentStatus = (
            "approved" if payload.decision == "approved" else "rejected"
        )

        conn.execute(
            """
            UPDATE approvals
            SET status = ?,
                director_comment = ?,
                trust_account = ?,
                decided_by = ?,
                decided_at = ?
            WHERE id = ?
            """,
            (
                payload.decision,
                stored_comment,
                1 if grant_trust else 0,
                user.id,
                now_iso,
                approval_id,
            ),
        )
        conn.execute(
            "UPDATE payments SET status = ?, updated_at = ? WHERE id = ?",
            (new_payment_status, now_iso, payment_id),
        )

        if grant_trust:
            company_row = load_company_row(conn, company_id)
            prod_store = ProdStore(
                conn,
                company_row,
                reference=get_reference_store(),
                today=today,
            )
            prod_store.trust_account(
                str(row["recipient_bin"]),
                str(row["recipient_iik"]),
                decided_at=now_iso,
                director_comment=cleaned_comment,
                approval_id=approval_id,
                decided_by=user.id,
            )

        action_label = f"decision:{payload.decision}" + ("_trusted" if grant_trust else "")
        decision_details: dict[str, Any] = {
            "director_comment": stored_comment,
            "trust_account": grant_trust,
        }
        if payload.decision == "rejected":
            decision_details["recipient_bin"] = req_bin
            decision_details["recipient_iik"] = req_iik
        append_audit(
            conn,
            action=action_label,
            timestamp=now_iso,
            user_id=user.id,
            user_login=user.login,
            role=user.role,
            company_id=company_id,
            payment_id=payment_id,
            approval_id=approval_id,
            check_id=str(row["check_id"]),
            request_sha256=str(row["request_sha256"]),
            ruleset_version=stored_check.ruleset_version,
            verdict=stored_check.verdict,
            signal_ids=[s.rule_id for s in stored_check.signals],
            details=decision_details,
        )

    refreshed = conn.execute(
        """
        SELECT
            a.*,
            p.company_id,
            p.recipient_name,
            p.recipient_bin,
            p.recipient_iik,
            p.recipient_bik,
            p.amount_tiyn,
            p.purpose,
            p.kbe,
            p.knp,
            c.result_json
        FROM approvals a
        JOIN payments p ON p.id = a.payment_id
        JOIN checks c ON c.id = a.check_id
        WHERE a.id = ?
        """,
        (approval_id,),
    ).fetchone()
    assert refreshed is not None
    return _hydrate_approvals(conn, [refreshed], viewer=user, lang=lang)[0]


def _detect_auto_format(data: bytes) -> str:
    stripped = data.removeprefix(b"\xef\xbb\xbf")
    for raw_line in stripped.splitlines():
        line = raw_line.strip()
        if line:
            return "1c" if line.startswith(b"1CClientBankExchange") else "csv"
    return "csv"


def import_payments_file(
    conn: sqlite3.Connection,
    *,
    user: User,
    data: bytes,
    filename: str,
    file_format: ImportFormat = "auto",
    force: bool = False,
    today: date,
    lang: Lang = DEFAULT_LANG,
) -> ImportResult:
    """Parse and import a 1C or CSV payment batch atomically in a single transaction (§7)."""
    if user.role != "accountant":
        raise ProdError(403, "forbidden_role")
    company_id = company_scope_id(user)
    if company_id is None:
        raise ProdError(403, "forbidden_role")

    if len(data) > MAX_IMPORT_BYTES:
        raise ProdError(413, "file_too_large")
    if not data or not data.strip():
        raise ProdError(422, "empty_file")

    clean_filename = clean_text_field(filename) or "upload"
    chosen = _detect_auto_format(data) if file_format == "auto" else file_format
    try:
        parsed = parse_1c(data) if chosen == "1c" else parse_csv(data)
    except EmptyFileError as exc:
        raise ProdError(422, "empty_file") from exc
    except UnsupportedFileError as exc:
        raise ProdError(422, "unsupported_file") from exc

    file_sha256 = hashlib.sha256(data).hexdigest()
    now_iso = utc_now_iso()
    batch_id = f"bat-{uuid.uuid4().hex[:12]}"

    errors: list[ImportLineError] = [
        ImportLineError(
            line_no=err.line_no,
            doc_number=err.doc_number,
            code=err.code,
            message=err.message,
        )
        for err in parsed.errors
    ]
    created_ids: list[str] = []
    verdict_counts: dict[str, int] = {
        "green": 0,
        "yellow": 0,
        "red": 0,
        "grey": 0,
        "invalid": 0,
    }

    with tx(conn):
        existing_batch = conn.execute(
            "SELECT id FROM import_batches WHERE company_id = ? AND file_sha256 = ? LIMIT 1",
            (company_id, file_sha256),
        ).fetchone()
        if existing_batch is not None and not force:
            raise ProdError(409, "duplicate_file")

        company_row = load_company_row(conn, company_id)
        company_iik = normalize_requisite(str(company_row["iik"]))
        prod_store = ProdStore(
            conn,
            company_row,
            reference=get_reference_store(),
            today=today,
        )

        # Insert batch row before child payments (FK payments.batch_id -> import_batches.id)
        conn.execute(
            """
            INSERT INTO import_batches (
                id, company_id, created_by, source, filename, file_sha256,
                total, created_count, failed_count, errors_json, is_forced, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, 0, 0, 0, '[]', ?, ?)
            """,
            (
                batch_id,
                company_id,
                user.id,
                parsed.source,
                clean_filename,
                file_sha256,
                1 if force else 0,
                now_iso,
            ),
        )

        for doc in parsed.docs:
            doc_num = doc.doc_number or None
            if doc.payer_iik and normalize_requisite(doc.payer_iik) != company_iik:
                errors.append(
                    ImportLineError(
                        line_no=doc.line_no,
                        doc_number=doc_num,
                        code="payer_mismatch",
                        message=(
                            f"Счёт плательщика ({doc.payer_iik}) не совпадает со счётом компании "
                            f"({company_iik})."
                        ),
                    )
                )
                continue

            if doc.amount_kzt is None:
                errors.append(
                    ImportLineError(
                        line_no=doc.line_no,
                        doc_number=doc_num,
                        code="validation_error",
                        message="Сумма платежа не указана или имеет неверный формат.",
                    )
                )
                continue

            try:
                payment_input = PaymentInput(
                    recipient_name=doc.recipient_name,
                    recipient_bin=doc.recipient_bin,
                    recipient_iik=doc.recipient_iik,
                    recipient_bik=doc.recipient_bik,
                    amount_kzt=doc.amount_kzt,
                    purpose=doc.purpose,
                    kbe=doc.kbe,
                    knp=doc.knp,
                    doc_number=doc.doc_number,
                    doc_date=doc.doc_date,
                )
            except ValidationError as exc:
                first_msg = exc.errors()[0].get("msg", "Ошибка заполнения полей платежа.")
                errors.append(
                    ImportLineError(
                        line_no=doc.line_no,
                        doc_number=doc_num,
                        code="validation_error",
                        message=str(first_msg).removeprefix("Value error, "),
                    )
                )
                continue

            pay_id, check_res = create_payment_in_tx(
                conn,
                user=user,
                payload=payment_input,
                today=today,
                source=parsed.source,
                batch_id=batch_id,
                line_no=doc.line_no,
                prod_store=prod_store,
                now_iso=now_iso,
                emit_created_audit=False,
            )
            created_ids.append(pay_id)
            verdict_counts[check_res.verdict] += 1

        # The capped list carries one summary row; omitted rows are real failures.
        failed_total = len(errors) + parsed.errors_omitted - (1 if parsed.errors_omitted else 0)
        total = len(created_ids) + failed_total
        errors_json = json.dumps([e.model_dump() for e in errors], ensure_ascii=False)
        conn.execute(
            """
            UPDATE import_batches
            SET total = ?, created_count = ?, failed_count = ?, errors_json = ?
            WHERE id = ?
            """,
            (total, len(created_ids), failed_total, errors_json, batch_id),
        )
        append_audit(
            conn,
            action="import",
            timestamp=now_iso,
            user_id=user.id,
            user_login=user.login,
            role=user.role,
            company_id=company_id,
            batch_id=batch_id,
            details={
                "source": parsed.source,
                "filename": clean_filename,
                "file_sha256": file_sha256,
                "encoding": parsed.encoding,
                "force": force,
                "total": total,
                "created": len(created_ids),
                "failed": failed_total,
            },
        )

    rows = conn.execute(
        """
        SELECT * FROM payments
        WHERE batch_id = ?
        ORDER BY COALESCE(line_no, 2147483647) ASC, rowid ASC
        """,
        (batch_id,),
    ).fetchall()
    items = hydrate_payments(conn, rows, viewer=user, today=today, lang=lang)
    duplicates_count = sum(1 for item in items if item.duplicate_of is not None)

    batch_model = Batch(
        id=batch_id,
        source=parsed.source,
        filename=clean_filename,
        total=total,
        created_count=len(created_ids),
        failed_count=failed_total,
        created_by=UserBrief(
            id=user.id,
            login=user.login,
            full_name=user.full_name,
            role=user.role,
        ),
        created_at=now_iso,
    )
    return ImportResult(
        batch=batch_model,
        items=items,
        errors=errors,
        summary=ImportSummary(
            total=batch_model.total,
            created=len(items),
            failed=failed_total,
            duplicates=duplicates_count,
            by_verdict=VerdictCounts(**verdict_counts),
        ),
    )


def list_batches(
    conn: sqlite3.Connection,
    *,
    user: User,
    limit: int = 50,
) -> list[Batch]:
    """List recent import batches for the user's company scope, newest first."""
    scoped_company = company_scope_id(user)
    bounded_limit = max(1, min(int(limit), 200))

    if scoped_company is not None:
        rows = conn.execute(
            """
            SELECT * FROM import_batches
            WHERE company_id = ?
            ORDER BY created_at DESC, rowid DESC
            LIMIT ?
            """,
            (scoped_company, bounded_limit),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT * FROM import_batches
            ORDER BY created_at DESC, rowid DESC
            LIMIT ?
            """,
            (bounded_limit,),
        ).fetchall()

    if not rows:
        return []

    user_ids = {int(r["created_by"]) for r in rows}
    users_cache: dict[int, UserBrief] = {}
    _load_users_brief(conn, user_ids, users_cache)

    return [
        Batch(
            id=str(r["id"]),
            source=r["source"],
            filename=str(r["filename"]),
            total=int(r["total"]),
            created_count=int(r["created_count"]),
            failed_count=int(r["failed_count"]),
            created_by=users_cache[int(r["created_by"])],
            created_at=str(r["created_at"]),
        )
        for r in rows
    ]


def _resolve_batch_candidates(
    conn: sqlite3.Connection,
    *,
    company_id: str,
    batch_id: str | None,
    payment_ids: list[str] | None,
) -> tuple[list[sqlite3.Row], list[str]]:
    """Resolve ordered candidate payment rows and missing/foreign payment IDs for batch actions."""
    if payment_ids is not None:
        unique_ids = list(dict.fromkeys(pid.strip() for pid in payment_ids if pid and pid.strip()))
        if not unique_ids:
            return [], []
        ph = ",".join("?" for _ in unique_ids)
        query = f"SELECT * FROM payments WHERE company_id = ? AND id IN ({ph})"
        params: list[Any] = [company_id, *unique_ids]
        if batch_id is not None and batch_id.strip():
            query += " AND batch_id = ?"
            params.append(batch_id.strip())
        fetched = {str(r["id"]): r for r in conn.execute(query, params).fetchall()}
        rows: list[sqlite3.Row] = []
        missing: list[str] = []
        for pid in unique_ids:
            if pid in fetched:
                rows.append(fetched[pid])
            else:
                missing.append(pid)
        return rows, missing

    clauses = ["company_id = ?", "status NOT IN ('signed', 'cancelled')"]
    params = [company_id]
    if batch_id is not None and batch_id.strip():
        clauses.append("batch_id = ?")
        params.append(batch_id.strip())
    rows = conn.execute(
        f"""
        SELECT * FROM payments
        WHERE {' AND '.join(clauses)}
        ORDER BY created_at ASC, COALESCE(line_no, 2147483647) ASC, rowid ASC
        """,
        params,
    ).fetchall()
    return rows, []


def batch_sign_green(
    conn: sqlite3.Connection,
    *,
    user: User,
    batch_id: str | None,
    payment_ids: list[str] | None,
    today: date,
    lang: Lang = DEFAULT_LANG,
) -> BatchActionResult:
    """Sign only status='checked' payments whose fresh check verdict is 'green'; skip others."""
    if user.role not in ("accountant", "director"):
        raise ProdError(403, "forbidden_role")
    company_id = company_scope_id(user)
    if company_id is None:
        raise ProdError(403, "forbidden_role")

    candidates, missing_ids = _resolve_batch_candidates(
        conn,
        company_id=company_id,
        batch_id=batch_id,
        payment_ids=payment_ids,
    )

    company_row = load_company_row(conn, company_id)
    shared_store = ProdStore(
        conn,
        company_row,
        reference=get_reference_store(),
        today=today,
    )

    done: list[Payment] = []
    skipped: list[BatchSkippedItem] = [
        BatchSkippedItem(
            id=pid,
            code="not_found",
            detail=localize_prod_error("not_found", lang),
        )
        for pid in missing_ids
    ]

    for row in candidates:
        pid = str(row["id"])
        status: PaymentStatus = row["status"]
        if status != "checked":
            code = policy.pre_sign_status_check(status) or "invalid_transition"
            skipped.append(
                BatchSkippedItem(
                    id=pid,
                    code=code,
                    detail=localize_prod_error(code, lang),
                )
            )
            continue

        try:
            signed = sign_payment(
                conn,
                payment_id=pid,
                user=user,
                accountant_ack=False,
                today=today,
                lang=lang,
                prod_store=shared_store,
                server_simulated=True,
            )
        except ProdError as exc:
            skipped.append(
                BatchSkippedItem(
                    id=pid,
                    code=exc.code,
                    detail=(
                        exc.detail
                        if exc.detail is not None
                        else localize_prod_error(exc.code, lang)
                    ),
                )
            )
        else:
            done.append(signed)

    return BatchActionResult(done=done, skipped=skipped)


def batch_send_to_director(
    conn: sqlite3.Connection,
    *,
    user: User,
    batch_id: str | None,
    payment_ids: list[str] | None,
    accountant_note: str,
    today: date,
    lang: Lang = DEFAULT_LANG,
) -> BatchActionResult:
    """Send status='checked' yellow/red/grey payments to director; skip green and invalid."""
    if user.role != "accountant":
        raise ProdError(403, "forbidden_role")
    company_id = company_scope_id(user)
    if company_id is None:
        raise ProdError(403, "forbidden_role")

    candidates, missing_ids = _resolve_batch_candidates(
        conn,
        company_id=company_id,
        batch_id=batch_id,
        payment_ids=payment_ids,
    )
    comp_settings = get_company_settings(conn, company_id)
    threshold_tiyn = comp_settings.approval_threshold_tiyn
    rejected_payment_ids = _load_rejected_payment_ids(conn, [str(r["id"]) for r in candidates])
    rejected_requisites = _load_rejected_requisites_by_company(conn, (company_id,))
    dup_map = _find_duplicate_map(conn, candidates)

    done: list[Payment] = []
    skipped: list[BatchSkippedItem] = [
        BatchSkippedItem(
            id=pid,
            code="not_found",
            detail=localize_prod_error("not_found", lang),
        )
        for pid in missing_ids
    ]

    for row in candidates:
        pid = str(row["id"])
        status: PaymentStatus = row["status"]
        if status != "checked":
            skipped.append(
                BatchSkippedItem(
                    id=pid,
                    code="invalid_transition",
                    detail=localize_prod_error("invalid_transition", lang),
                )
            )
            continue

        check_id = row["check_id"]
        verdict: str = "green"
        if check_id is not None:
            crow = conn.execute(
                "SELECT verdict FROM checks WHERE id = ?",
                (str(check_id),),
            ).fetchone()
            if crow is not None:
                verdict = str(crow["verdict"])

        if verdict == "invalid":
            skipped.append(
                BatchSkippedItem(
                    id=pid,
                    code="invalid_requisites",
                    detail=localize_prod_error("invalid_requisites", lang),
                )
            )
            continue
        req_key = (
            company_id,
            normalize_requisite(str(row["recipient_bin"])),
            normalize_requisite(str(row["recipient_iik"])),
        )
        needs_approval_after_rejection = (
            pid in rejected_payment_ids or req_key in rejected_requisites
        )
        exceeds_threshold = False
        if threshold_tiyn is not None and threshold_tiyn > 0:
            row_amt = int(row["amount_tiyn"])
            if row_amt >= threshold_tiyn:
                exceeds_threshold = True
            else:
                agg_72h = sum_supplier_payments_window_tiyn(
                    conn,
                    company_id=company_id,
                    recipient_bin=str(row["recipient_bin"]),
                    recipient_iik=str(row["recipient_iik"]),
                    exclude_payment_id=pid,
                )
                exceeds_threshold = (row_amt + agg_72h) >= threshold_tiyn
        is_duplicate = dup_map.get(pid) is not None
        if (
            verdict == "green"
            and not needs_approval_after_rejection
            and not exceeds_threshold
            and not is_duplicate
        ):
            skipped.append(
                BatchSkippedItem(
                    id=pid,
                    code="invalid_transition",
                    detail=localize_prod_error("invalid_transition", lang),
                )
            )
            continue

        try:
            sent = send_to_director(
                conn,
                payment_id=pid,
                user=user,
                accountant_note=accountant_note,
                today=today,
                lang=lang,
            )
        except ProdError as exc:
            skipped.append(
                BatchSkippedItem(
                    id=pid,
                    code=exc.code,
                    detail=(
                        exc.detail
                        if exc.detail is not None
                        else localize_prod_error(exc.code, lang)
                    ),
                )
            )
        else:
            done.append(sent)

    return BatchActionResult(done=done, skipped=skipped)
