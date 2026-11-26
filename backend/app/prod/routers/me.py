"""Current user profile and password management endpoints (/api/v1/me/*)."""

from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends

from app.i18n import DEFAULT_LANG, Lang
from app.prod.audit_db import append_audit
from app.prod.db import get_db, tx
from app.prod.deps import AuthContext, LangQuery, current_session
from app.prod.errors import ProdError
from app.prod.schemas import (
    ChangePasswordRequest,
    Company,
    PasswordChangeResponse,
    UpdateProfileRequest,
    UserProfile,
)
from app.prod.security import hash_password, utc_now_iso, verify_password

router = APIRouter(prefix="/me", tags=["profile"])


def _load_profile(conn: sqlite3.Connection, user_id: int) -> UserProfile:
    row = conn.execute(
        """
        SELECT
            u.id AS user_id,
            u.login,
            u.full_name,
            u.role,
            u.company_id,
            u.default_lang,
            c.id AS c_id,
            c.name AS c_name,
            c.bin AS c_bin,
            c.iik AS c_iik,
            c.bik AS c_bik
        FROM users u
        LEFT JOIN companies c ON c.id = u.company_id
        WHERE u.id = ?
        """,
        (user_id,),
    ).fetchone()
    if row is None:
        raise ProdError(404, "not_found")
    company = (
        Company(
            id=str(row["c_id"]),
            name=str(row["c_name"]),
            bin=str(row["c_bin"]),
            iik=str(row["c_iik"]),
            bik=str(row["c_bik"]),
        )
        if row["c_id"] is not None
        else None
    )
    default_lang: Lang = row["default_lang"] if row["default_lang"] in ("ru", "kk", "en") else "ru"
    return UserProfile(
        id=int(row["user_id"]),
        login=str(row["login"]),
        full_name=str(row["full_name"]),
        role=row["role"],
        company_id=str(row["company_id"]) if row["company_id"] is not None else None,
        default_lang=default_lang,
        company=company,
    )


@router.get("", response_model=UserProfile)
def get_my_profile(
    ctx: Annotated[AuthContext, Depends(current_session)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    lang: LangQuery = DEFAULT_LANG,
) -> UserProfile:
    """Return the authenticated user's profile including default language preference."""
    _ = lang
    return _load_profile(conn, ctx.user.id)


@router.put("", response_model=UserProfile)
def update_my_profile(
    payload: UpdateProfileRequest,
    ctx: Annotated[AuthContext, Depends(current_session)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    lang: LangQuery = DEFAULT_LANG,
) -> UserProfile:
    """Update the authenticated user's full_name and/or default_lang and record audit entry."""
    _ = lang
    now_iso = utc_now_iso()
    with tx(conn):
        current = _load_profile(conn, ctx.user.id)
        new_full_name = payload.full_name if payload.full_name is not None else current.full_name
        new_default_lang = (
            payload.default_lang if payload.default_lang is not None else current.default_lang
        )
        conn.execute(
            "UPDATE users SET full_name = ?, default_lang = ? WHERE id = ?",
            (new_full_name, new_default_lang, ctx.user.id),
        )
        append_audit(
            conn,
            action="profile_updated",
            timestamp=now_iso,
            user_id=ctx.user.id,
            user_login=ctx.user.login,
            role=ctx.user.role,
            company_id=ctx.user.company_id,
            details={
                "old_full_name": current.full_name,
                "new_full_name": new_full_name,
                "old_default_lang": current.default_lang,
                "new_default_lang": new_default_lang,
            },
        )
    return _load_profile(conn, ctx.user.id)


@router.post("/password", response_model=PasswordChangeResponse)
def change_my_password(
    payload: ChangePasswordRequest,
    ctx: Annotated[AuthContext, Depends(current_session)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    lang: LangQuery = DEFAULT_LANG,
) -> PasswordChangeResponse:
    """Verify current password, store new scrypt hash, revoke all other sessions, and audit."""
    _ = lang
    row = conn.execute(
        "SELECT password_hash FROM users WHERE id = ?",
        (ctx.user.id,),
    ).fetchone()
    if row is None:
        raise ProdError(404, "not_found")

    if not verify_password(payload.current_password, str(row["password_hash"])):
        with tx(conn):
            append_audit(
                conn,
                action="password_change_failed",
                user_id=ctx.user.id,
                user_login=ctx.user.login,
                role=ctx.user.role,
                company_id=ctx.user.company_id,
                details={"reason": "invalid_current_password"},
            )
        raise ProdError(400, "invalid_current_password")

    if payload.new_password == payload.current_password:
        raise ProdError(422, "password_same_as_current")

    new_hash = hash_password(payload.new_password)
    now_iso = utc_now_iso()
    with tx(conn):
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (new_hash, ctx.user.id),
        )
        cur = conn.execute(
            """
            UPDATE sessions
            SET revoked_at = ?
            WHERE user_id = ?
              AND token_hash != ?
              AND revoked_at IS NULL
            """,
            (now_iso, ctx.user.id, ctx.token_hash),
        )
        revoked_count = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
        append_audit(
            conn,
            action="password_changed",
            timestamp=now_iso,
            user_id=ctx.user.id,
            user_login=ctx.user.login,
            role=ctx.user.role,
            company_id=ctx.user.company_id,
            details={"revoked_sessions": revoked_count},
        )

    return PasswordChangeResponse(ok=True, revoked_sessions=revoked_count)
