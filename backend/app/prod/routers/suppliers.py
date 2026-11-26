"""Confirmed supplier directory endpoints (/api/v1/suppliers/*)."""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from app.i18n import DEFAULT_LANG, Lang
from app.prod import payments_service, policy
from app.prod.audit_db import append_audit
from app.prod.db import get_db, tx
from app.prod.deps import (
    LangQuery,
    company_scope_id,
    ensure_company_access,
    get_app_settings,
    require_role,
)
from app.prod.directory import requisites_changed_days_ago
from app.prod.errors import ProdError
from app.prod.prod_store import get_reference_store
from app.prod.schemas import (
    Supplier,
    SupplierAccount,
    SupplierChange,
    SupplierDetail,
    UntrustAccountRequest,
    User,
)
from app.prod.security import utc_now_iso
from app.schemas import clean_text_field, meaningful_length
from app.settings import Settings

router = APIRouter(prefix="/suppliers", tags=["suppliers"])


def _build_supplier_summary(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    *,
    today: date,
) -> Supplier:
    supplier_id = int(row["id"])
    company_id = str(row["company_id"])
    sup_bin = str(row["bin"])

    pay_stats = conn.execute(
        """
        SELECT COUNT(*) AS cnt, COALESCE(SUM(amount_tiyn), 0) AS total_tiyn
        FROM payments
        WHERE company_id = ? AND recipient_bin = ? AND status = 'signed'
        """,
        (company_id, sup_bin),
    ).fetchone()
    payments_count = int(pay_stats["cnt"]) if pay_stats is not None else 0
    total_paid_kzt = (int(pay_stats["total_tiyn"]) / 100.0) if pay_stats is not None else 0.0

    accounts_count = int(
        conn.execute(
            "SELECT COUNT(*) FROM supplier_accounts WHERE supplier_id = ?",
            (supplier_id,),
        ).fetchone()[0]
    )

    trusted_accounts_count = int(
        conn.execute(
            """
            SELECT COUNT(*) FROM trusted_accounts
            WHERE company_id = ? AND recipient_bin = ? AND revoked_at IS NULL
            """,
            (company_id, sup_bin),
        ).fetchone()[0]
    )

    pending_row = conn.execute(
        """
        SELECT 1
        FROM payments p
        WHERE p.company_id = ?
          AND p.recipient_bin = ?
          AND p.status NOT IN ('signed', 'cancelled')
          AND NOT EXISTS (
              SELECT 1 FROM supplier_accounts sa
              WHERE sa.supplier_id = ? AND sa.iik = p.recipient_iik
          )
        LIMIT 1
        """,
        (company_id, sup_bin, supplier_id),
    ).fetchone()

    req_changed_at = (
        str(row["requisites_changed_at"]) if row["requisites_changed_at"] is not None else None
    )
    days_ago = requisites_changed_days_ago(req_changed_at, today)

    return Supplier(
        id=supplier_id,
        bin=sup_bin,
        name=str(row["name"]),
        first_seen_at=str(row["first_seen_at"]),
        last_payment_at=(
            str(row["last_payment_at"]) if row["last_payment_at"] is not None else None
        ),
        payments_count=payments_count,
        total_paid_kzt=total_paid_kzt,
        accounts_count=accounts_count,
        requisites_changed_at=req_changed_at,
        requisites_changed_days_ago=days_ago,
        has_pending_change=pending_row is not None,
        trusted_accounts_count=trusted_accounts_count,
    )


def build_supplier_detail(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    *,
    viewer: User,
    today: date,
    lang: Lang = DEFAULT_LANG,
) -> SupplierDetail:
    """Hydrate a SupplierDetail with accounts, change chronology, and latest 50 payments."""
    summary = _build_supplier_summary(conn, row, today=today)
    company_id = str(row["company_id"])
    ref_store = get_reference_store()

    acc_rows = conn.execute(
        """
        SELECT * FROM supplier_accounts
        WHERE supplier_id = ?
        ORDER BY last_used_at DESC, id DESC
        """,
        (summary.id,),
    ).fetchall()

    trusted_by_iik: dict[str, sqlite3.Row] = {}
    for trow in conn.execute(
        """
        SELECT id, recipient_iik, decided_at, director_comment
        FROM trusted_accounts
        WHERE company_id = ? AND recipient_bin = ? AND revoked_at IS NULL
        ORDER BY id DESC
        """,
        (company_id, summary.bin),
    ).fetchall():
        trusted_by_iik[str(trow["recipient_iik"])] = trow

    accounts: list[SupplierAccount] = []
    seen_iiks: set[str] = set()
    for acc in acc_rows:
        iik = str(acc["iik"])
        bik = str(acc["bik"])
        seen_iiks.add(iik)
        t_row = trusted_by_iik.get(iik)
        accounts.append(
            SupplierAccount(
                id=int(acc["id"]),
                iik=iik,
                bik=bik,
                bank_name=ref_store.get_bank_name_by_bik(bik),
                first_seen_at=str(acc["first_seen_at"]),
                last_used_at=str(acc["last_used_at"]),
                payments_count=int(acc["payments_count"]),
                trusted=t_row is not None,
                trusted_at=str(t_row["decided_at"]) if t_row is not None else None,
                trusted_comment=str(t_row["director_comment"]) if t_row is not None else None,
            )
        )

    # Include accounts trusted by the director before any payment to them has been signed
    for iik, t_row in trusted_by_iik.items():
        if iik in seen_iiks:
            continue
        bank_code = iik[4:7] if len(iik) >= 7 else ""
        bank_rec = ref_store.banks_by_code.get(bank_code)
        bik = bank_rec["bik"] if bank_rec is not None else ""
        bank_name = bank_rec["name"] if bank_rec is not None else None
        decided_at = str(t_row["decided_at"])
        accounts.append(
            SupplierAccount(
                id=-int(t_row["id"]),
                iik=iik,
                bik=bik,
                bank_name=bank_name,
                first_seen_at=decided_at,
                last_used_at=decided_at,
                payments_count=0,
                trusted=True,
                trusted_at=decided_at,
                trusted_comment=str(t_row["director_comment"]),
            )
        )

    change_rows = conn.execute(
        """
        SELECT * FROM supplier_changes
        WHERE supplier_id = ?
        ORDER BY occurred_at DESC, id DESC
        """,
        (summary.id,),
    ).fetchall()
    changes = [
        SupplierChange(
            id=int(ch["id"]),
            kind=ch["kind"],
            old_value=str(ch["old_value"]) if ch["old_value"] is not None else None,
            new_value=str(ch["new_value"]),
            occurred_at=str(ch["occurred_at"]),
            payment_id=str(ch["payment_id"]) if ch["payment_id"] is not None else None,
        )
        for ch in change_rows
    ]

    pay_rows = conn.execute(
        """
        SELECT * FROM payments
        WHERE company_id = ? AND recipient_bin = ?
        ORDER BY created_at DESC, rowid DESC
        LIMIT 50
        """,
        (company_id, summary.bin),
    ).fetchall()
    payments = payments_service.hydrate_payments(
        conn,
        pay_rows,
        viewer=viewer,
        today=today,
        lang=lang,
    )

    return SupplierDetail(
        **summary.model_dump(),
        accounts=accounts,
        changes=changes,
        payments=payments,
    )


@router.get("", response_model=list[Supplier])
def list_suppliers_endpoint(
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    user: Annotated[User, Depends(require_role("accountant", "director", "analyst"))],
    cfg: Annotated[Settings, Depends(get_app_settings)],
    q: Annotated[str | None, Query()] = None,
    changed_within_days: Annotated[int | None, Query(ge=0, le=3650)] = None,
    lang: LangQuery = DEFAULT_LANG,
) -> list[Supplier]:
    """List confirmed suppliers sorted by requisites_changed_at DESC NULLS LAST, name ASC."""
    _ = lang
    today = cfg.today()
    clauses: list[str] = []
    params: list[Any] = []

    scoped_company = company_scope_id(user)
    if scoped_company is not None:
        clauses.append("s.company_id = ?")
        params.append(scoped_company)

    if q is not None and q.strip():
        needle = f"%{q.strip().casefold()}%"
        clauses.append("(py_lower(s.name) LIKE ? OR py_lower(s.bin) LIKE ?)")
        params.extend([needle, needle])

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"""
        SELECT s.*
        FROM suppliers s
        {where_sql}
        ORDER BY (s.requisites_changed_at IS NULL) ASC,
                 s.requisites_changed_at DESC,
                 py_lower(s.name) ASC,
                 s.id ASC
        """,
        params,
    ).fetchall()

    suppliers = [_build_supplier_summary(conn, row, today=today) for row in rows]
    if changed_within_days is not None:
        suppliers = [
            sup
            for sup in suppliers
            if sup.requisites_changed_days_ago is not None
            and sup.requisites_changed_days_ago <= changed_within_days
        ]
    return suppliers


@router.get("/{supplier_id}", response_model=SupplierDetail)
def get_supplier_endpoint(
    supplier_id: int,
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    user: Annotated[User, Depends(require_role("accountant", "director", "analyst"))],
    cfg: Annotated[Settings, Depends(get_app_settings)],
    lang: LangQuery = DEFAULT_LANG,
) -> SupplierDetail:
    """Return supplier card with accounts, change history (newest first), and latest 50 payments."""
    row = conn.execute("SELECT * FROM suppliers WHERE id = ?", (supplier_id,)).fetchone()
    if row is None:
        raise ProdError(404, "not_found")
    ensure_company_access(user, str(row["company_id"]))
    return build_supplier_detail(conn, row, viewer=user, today=cfg.today(), lang=lang)


@router.post("/{supplier_id}/accounts/{account_id}/untrust", response_model=SupplierDetail)
def untrust_supplier_account_endpoint(
    supplier_id: int,
    account_id: int,
    payload: UntrustAccountRequest,
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    user: Annotated[User, Depends(require_role("director"))],
    cfg: Annotated[Settings, Depends(get_app_settings)],
    lang: LangQuery = DEFAULT_LANG,
) -> SupplierDetail:
    """Revoke director trust on a supplier account (sets revoked_at and logs trust_revoked)."""
    cleaned_comment = clean_text_field(payload.comment)
    if meaningful_length(cleaned_comment) < policy.MIN_DIRECTOR_COMMENT_LEN:
        raise ProdError(422, "trust_comment_required")

    with tx(conn):
        sup_row = conn.execute("SELECT * FROM suppliers WHERE id = ?", (supplier_id,)).fetchone()
        if sup_row is None:
            raise ProdError(404, "not_found")
        company_id = str(sup_row["company_id"])
        ensure_company_access(user, company_id)
        sup_bin = str(sup_row["bin"])

        if account_id > 0:
            acc_row = conn.execute(
                "SELECT * FROM supplier_accounts WHERE id = ? AND supplier_id = ?",
                (account_id, supplier_id),
            ).fetchone()
            if acc_row is None:
                raise ProdError(404, "not_found")
            target_iik = str(acc_row["iik"])
            trust_row = conn.execute(
                """
                SELECT * FROM trusted_accounts
                WHERE company_id = ? AND recipient_bin = ? AND recipient_iik = ? AND revoked_at IS NULL
                LIMIT 1
                """,
                (company_id, sup_bin, target_iik),
            ).fetchone()
            if trust_row is None:
                raise ProdError(409, "invalid_transition")
        elif account_id < 0:
            trust_row = conn.execute(
                """
                SELECT * FROM trusted_accounts
                WHERE id = ? AND company_id = ? AND recipient_bin = ? AND revoked_at IS NULL
                LIMIT 1
                """,
                (-account_id, company_id, sup_bin),
            ).fetchone()
            if trust_row is None:
                raise ProdError(404, "not_found")
            target_iik = str(trust_row["recipient_iik"])
        else:
            raise ProdError(404, "not_found")

        now_iso = utc_now_iso()
        conn.execute(
            "UPDATE trusted_accounts SET revoked_at = ?, revoked_by = ? WHERE id = ?",
            (now_iso, user.id, int(trust_row["id"])),
        )
        append_audit(
            conn,
            action="trust_revoked",
            timestamp=now_iso,
            user_id=user.id,
            user_login=user.login,
            role=user.role,
            company_id=company_id,
            approval_id=str(trust_row["approval_id"]) if trust_row["approval_id"] is not None else None,
            details={
                "supplier_id": supplier_id,
                "account_id": account_id,
                "recipient_bin": sup_bin,
                "recipient_iik": target_iik,
                "comment": cleaned_comment,
            },
        )

    refreshed = conn.execute("SELECT * FROM suppliers WHERE id = ?", (supplier_id,)).fetchone()
    assert refreshed is not None
    return build_supplier_detail(conn, refreshed, viewer=user, today=cfg.today(), lang=lang)
