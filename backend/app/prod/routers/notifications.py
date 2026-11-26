"""Server-derived notifications endpoints (/api/v1/notifications/*)."""

from __future__ import annotations

import json
import sqlite3
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Query

from app.i18n import DEFAULT_LANG, Lang, t
from app.prod.audit_db import append_audit
from app.prod.company_settings import CompanySettingsState, load_company_settings_map
from app.prod.db import get_db, tx
from app.prod.deps import LangQuery, company_scope_id, current_user
from app.prod.errors import localize_prod_error
from app.prod.schemas import (
    MarkNotificationsReadRequest,
    MarkNotificationsReadResponse,
    NotificationItem,
    NotificationList,
    NotifyOn,
    User,
)
from app.prod.security import utc_now_iso
from app.schemas import Verdict

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _format_kzt(amount_kzt: float) -> str:
    whole = round(amount_kzt)
    if abs(amount_kzt - whole) < 0.005:
        formatted = f"{whole:,}".replace(",", " ")
    else:
        formatted = f"{amount_kzt:,.2f}".replace(",", " ")
    return f"{formatted} ₸"


def _verdict_label(verdict: Verdict | None, lang: Lang) -> str:
    if verdict is None:
        return "—"
    return t(f"prod.verdict.{verdict}", lang)


def _passes_notify_on(
    *,
    notify_on: NotifyOn,
    verdict: Verdict | None,
    threshold_triggered: bool = False,
) -> bool:
    """Filter notification candidates according to company notify_on ('red' | 'red_yellow')."""
    if notify_on == "red":
        return verdict == "red"
    # 'red_yellow': include red, yellow, grey, and threshold-triggered events
    if verdict in ("red", "yellow", "grey"):
        return True
    return threshold_triggered


def _collect_notifications(
    conn: sqlite3.Connection,
    *,
    user: User,
    lang: Lang,
) -> list[NotificationItem]:
    scoped_company = company_scope_id(user)

    read_rows = conn.execute(
        "SELECT notification_id FROM notification_reads WHERE user_id = ?",
        (user.id,),
    ).fetchall()
    read_ids: set[str] = {str(r["notification_id"]) for r in read_rows}

    raw_items: list[dict[str, Any]] = []
    company_ids: set[str] = set()
    if scoped_company is not None:
        company_ids.add(scoped_company)

    # 1. Pending approvals -> for director (own company) and analyst (all companies)
    if user.role in ("director", "analyst"):
        if scoped_company is not None:
            pending_rows = conn.execute(
                """
                SELECT
                    a.id AS approval_id,
                    a.payment_id,
                    a.created_at,
                    p.company_id,
                    p.recipient_name,
                    p.amount_tiyn,
                    c.verdict
                FROM approvals a
                JOIN payments p ON p.id = a.payment_id
                JOIN checks c ON c.id = a.check_id
                WHERE a.status = 'pending' AND p.company_id = ?
                ORDER BY a.created_at DESC, a.rowid DESC
                LIMIT 100
                """,
                (scoped_company,),
            ).fetchall()
        else:
            pending_rows = conn.execute(
                """
                SELECT
                    a.id AS approval_id,
                    a.payment_id,
                    a.created_at,
                    p.company_id,
                    p.recipient_name,
                    p.amount_tiyn,
                    c.verdict
                FROM approvals a
                JOIN payments p ON p.id = a.payment_id
                JOIN checks c ON c.id = a.check_id
                WHERE a.status = 'pending'
                ORDER BY a.created_at DESC, a.rowid DESC
                LIMIT 100
                """
            ).fetchall()

        for row in pending_rows:
            cid = str(row["company_id"])
            company_ids.add(cid)
            raw_items.append(
                {
                    "id": f"apr-pending:{row['approval_id']}",
                    "kind": "approval_pending",
                    "company_id": cid,
                    "created_at": str(row["created_at"]),
                    "payment_id": str(row["payment_id"]),
                    "approval_id": str(row["approval_id"]),
                    "verdict": row["verdict"],
                    "recipient_name": str(row["recipient_name"]),
                    "amount_tiyn": int(row["amount_tiyn"]),
                    "code": None,
                }
            )

    # 2. Decisions on approvals -> for accountant (approvals submitted by them)
    if user.role == "accountant" and scoped_company is not None:
        decision_rows = conn.execute(
            """
            SELECT
                a.id AS approval_id,
                a.payment_id,
                a.status AS decision_status,
                a.decided_at,
                a.created_at,
                p.company_id,
                p.recipient_name,
                p.amount_tiyn,
                c.verdict
            FROM approvals a
            JOIN payments p ON p.id = a.payment_id
            JOIN checks c ON c.id = a.check_id
            WHERE p.company_id = ?
              AND a.created_by = ?
              AND a.status IN ('approved', 'rejected')
              AND a.decided_at IS NOT NULL
            ORDER BY a.decided_at DESC, a.rowid DESC
            LIMIT 100
            """,
            (scoped_company, user.id),
        ).fetchall()

        for row in decision_rows:
            cid = str(row["company_id"])
            company_ids.add(cid)
            kind = (
                "approval_approved"
                if row["decision_status"] == "approved"
                else "approval_rejected"
            )
            raw_items.append(
                {
                    "id": f"apr-decision:{row['approval_id']}",
                    "kind": kind,
                    "company_id": cid,
                    "created_at": str(row["decided_at"] or row["created_at"]),
                    "payment_id": str(row["payment_id"]),
                    "approval_id": str(row["approval_id"]),
                    "verdict": row["verdict"],
                    "recipient_name": str(row["recipient_name"]),
                    "amount_tiyn": int(row["amount_tiyn"]),
                    "code": None,
                }
            )

    # 3. Sign denied events from audit_log
    #    - director: all sign_denied in own company
    #    - accountant: own sign_denied attempts
    #    - analyst: all sign_denied across companies
    if user.role == "director" and scoped_company is not None:
        denied_rows = conn.execute(
            """
            SELECT
                a.id AS audit_id,
                a.timestamp,
                a.company_id,
                a.payment_id,
                a.approval_id,
                a.verdict,
                a.details_json,
                p.recipient_name,
                p.amount_tiyn
            FROM audit_log a
            LEFT JOIN payments p ON p.id = a.payment_id
            WHERE a.action = 'sign_denied' AND a.company_id = ?
            ORDER BY a.id DESC
            LIMIT 100
            """,
            (scoped_company,),
        ).fetchall()
    elif user.role == "accountant" and scoped_company is not None:
        denied_rows = conn.execute(
            """
            SELECT
                a.id AS audit_id,
                a.timestamp,
                a.company_id,
                a.payment_id,
                a.approval_id,
                a.verdict,
                a.details_json,
                p.recipient_name,
                p.amount_tiyn
            FROM audit_log a
            LEFT JOIN payments p ON p.id = a.payment_id
            WHERE a.action = 'sign_denied'
              AND a.company_id = ?
              AND a.user_id = ?
            ORDER BY a.id DESC
            LIMIT 100
            """,
            (scoped_company, user.id),
        ).fetchall()
    else:
        denied_rows = conn.execute(
            """
            SELECT
                a.id AS audit_id,
                a.timestamp,
                a.company_id,
                a.payment_id,
                a.approval_id,
                a.verdict,
                a.details_json,
                p.recipient_name,
                p.amount_tiyn
            FROM audit_log a
            LEFT JOIN payments p ON p.id = a.payment_id
            WHERE a.action = 'sign_denied'
            ORDER BY a.id DESC
            LIMIT 100
            """
        ).fetchall()

    for row in denied_rows:
        cid = str(row["company_id"]) if row["company_id"] is not None else ""
        if cid:
            company_ids.add(cid)
        try:
            details = json.loads(str(row["details_json"])) if row["details_json"] else {}
        except ValueError:
            details = {}
        code = str(details.get("code")) if isinstance(details, dict) and details.get("code") else None
        raw_items.append(
            {
                "id": f"sign-denied:{row['audit_id']}",
                "kind": "sign_denied",
                "company_id": cid,
                "created_at": str(row["timestamp"]),
                "payment_id": str(row["payment_id"]) if row["payment_id"] is not None else None,
                "approval_id": str(row["approval_id"]) if row["approval_id"] is not None else None,
                "verdict": row["verdict"],
                "recipient_name": (
                    str(row["recipient_name"]) if row["recipient_name"] is not None else None
                ),
                "amount_tiyn": (
                    int(row["amount_tiyn"]) if row["amount_tiyn"] is not None else None
                ),
                "code": code,
            }
        )

    settings_map = load_company_settings_map(conn, company_ids)

    items: list[NotificationItem] = []
    for raw in raw_items:
        cid = raw["company_id"]
        c_settings = settings_map.get(cid, CompanySettingsState())
        verdict: Verdict | None = raw["verdict"]
        amount_tiyn: int | None = raw["amount_tiyn"]
        threshold_tiyn = c_settings.approval_threshold_tiyn
        threshold_triggered = raw["code"] == "threshold_requires_approval" or (
            threshold_tiyn is not None
            and amount_tiyn is not None
            and amount_tiyn >= threshold_tiyn
        )

        if not _passes_notify_on(
            notify_on=c_settings.notify_on,
            verdict=verdict,
            threshold_triggered=threshold_triggered,
        ):
            continue

        amount_kzt = amount_tiyn / 100.0 if amount_tiyn is not None else None
        recipient_display = raw["recipient_name"] or (raw["payment_id"] or "—")
        amount_display = _format_kzt(amount_kzt) if amount_kzt is not None else "—"
        kind = raw["kind"]

        if kind == "approval_pending":
            title = t("prod.notif.approval_pending.title", lang)
            message = t(
                "prod.notif.approval_pending.body",
                lang,
                recipient=recipient_display,
                amount=amount_display,
                verdict=_verdict_label(verdict, lang),
            )
            link = (
                f"/payments/{raw['payment_id']}"
                if raw["payment_id"]
                else "/director"
            )
        elif kind == "approval_approved":
            title = t("prod.notif.approval_approved.title", lang)
            message = t(
                "prod.notif.approval_approved.body",
                lang,
                recipient=recipient_display,
                amount=amount_display,
            )
            link = f"/payments/{raw['payment_id']}" if raw["payment_id"] else "/payments"
        elif kind == "approval_rejected":
            title = t("prod.notif.approval_rejected.title", lang)
            message = t(
                "prod.notif.approval_rejected.body",
                lang,
                recipient=recipient_display,
                amount=amount_display,
            )
            link = f"/payments/{raw['payment_id']}" if raw["payment_id"] else "/payments"
        else:
            code = raw["code"] or "not_signable_status"
            reason = localize_prod_error(code, lang)
            title = t("prod.notif.sign_denied.title", lang)
            message = t(
                "prod.notif.sign_denied.body",
                lang,
                recipient=recipient_display,
                amount=amount_display,
                reason=reason,
            )
            link = f"/payments/{raw['payment_id']}" if raw["payment_id"] else "/payments"

        nid = str(raw["id"])
        items.append(
            NotificationItem(
                id=nid,
                kind=kind,
                title=title,
                message=message,
                created_at=str(raw["created_at"]),
                read=nid in read_ids,
                payment_id=raw["payment_id"],
                approval_id=raw["approval_id"],
                verdict=verdict,
                recipient_name=raw["recipient_name"],
                amount_kzt=amount_kzt,
                link=link,
            )
        )

    items.sort(key=lambda item: (item.created_at, item.id), reverse=True)
    return items


@router.get("", response_model=NotificationList)
def get_notifications(
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    user: Annotated[User, Depends(current_user)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    lang: LangQuery = DEFAULT_LANG,
) -> NotificationList:
    """Return server-derived notifications and unread count filtered by company notify_on."""
    all_items = _collect_notifications(conn, user=user, lang=lang)
    unread_count = sum(1 for item in all_items if not item.read)
    return NotificationList(
        unread_count=unread_count,
        items=all_items[:limit],
    )


@router.post("/read", response_model=MarkNotificationsReadResponse)
def mark_notifications_read(
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    user: Annotated[User, Depends(current_user)],
    payload: Annotated[MarkNotificationsReadRequest | None, Body()] = None,
    lang: LangQuery = DEFAULT_LANG,
) -> MarkNotificationsReadResponse:
    """Mark specific notification IDs (or all current notifications) as read for the current user."""
    all_items = _collect_notifications(conn, user=user, lang=lang)
    current_ids = {item.id for item in all_items}

    if payload is not None and payload.ids is not None and len(payload.ids) > 0:
        target_ids = [nid.strip() for nid in payload.ids if nid and nid.strip()]
        mark_all = False
    else:
        target_ids = [item.id for item in all_items if not item.read]
        mark_all = True

    now_iso = utc_now_iso()
    marked = 0
    with tx(conn):
        for nid in dict.fromkeys(target_ids):
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO notification_reads (user_id, notification_id, read_at)
                VALUES (?, ?, ?)
                """,
                (user.id, nid, now_iso),
            )
            if cur.rowcount and cur.rowcount > 0:
                marked += 1

        append_audit(
            conn,
            action="notifications_read",
            timestamp=now_iso,
            user_id=user.id,
            user_login=user.login,
            role=user.role,
            company_id=user.company_id,
            details={"marked_count": marked, "all": mark_all},
        )

    read_rows = conn.execute(
        "SELECT notification_id FROM notification_reads WHERE user_id = ?",
        (user.id,),
    ).fetchall()
    read_set = {str(r["notification_id"]) for r in read_rows}
    remaining_unread = sum(1 for nid in current_ids if nid not in read_set)

    return MarkNotificationsReadResponse(
        marked=marked,
        unread_count=remaining_unread,
    )
