"""Authentication endpoints: login, logout, and current session lookup."""

from __future__ import annotations

import sqlite3
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.i18n import DEFAULT_LANG
from app.prod.audit_db import append_audit
from app.prod.db import get_db, tx
from app.prod.deps import (
    AuthContext,
    LangQuery,
    current_session,
    get_app_settings,
    get_login_limiter,
)
from app.prod.errors import ProdError
from app.prod.schemas import Company, LoginRequest, Session, User
from app.prod.security import (
    SESSION_COOKIE_NAME,
    LoginRateLimiter,
    generate_session_token,
    hash_session_token,
    utc_now,
    utc_now_iso,
    verify_dummy_password,
    verify_password,
)
from app.settings import Settings

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=Session)
def post_login(
    payload: LoginRequest,
    response: Response,
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    cfg: Annotated[Settings, Depends(get_app_settings)],
    limiter: Annotated[LoginRateLimiter, Depends(get_login_limiter)],
    lang: LangQuery = DEFAULT_LANG,
) -> Session:
    """Verify credentials, create an opaque session cookie, and return session info."""
    _ = lang
    login_clean = payload.login.strip()
    if limiter.is_blocked(login_clean):
        raise ProdError(429, "too_many_attempts")

    row = conn.execute(
        """
        SELECT
            u.id AS user_id,
            u.login,
            u.full_name,
            u.role,
            u.company_id,
            u.password_hash,
            u.is_active,
            c.id AS c_id,
            c.name AS c_name,
            c.bin AS c_bin,
            c.iik AS c_iik,
            c.bik AS c_bik
        FROM users u
        LEFT JOIN companies c ON c.id = u.company_id
        WHERE u.login = ?
        """,
        (login_clean,),
    ).fetchone()

    if row is None or int(row["is_active"]) != 1:
        verify_dummy_password(payload.password)
        limiter.record_failure(login_clean)
        with tx(conn):
            append_audit(
                conn,
                action="login_failed",
                user_id=int(row["user_id"]) if row is not None else None,
                user_login=str(row["login"]) if row is not None else login_clean,
                role=row["role"] if row is not None else None,
                company_id=(
                    str(row["company_id"])
                    if row is not None and row["company_id"] is not None
                    else None
                ),
                details={"reason": "invalid_credentials"},
            )
        raise ProdError(401, "invalid_credentials")

    if not verify_password(payload.password, str(row["password_hash"])):
        limiter.record_failure(login_clean)
        with tx(conn):
            append_audit(
                conn,
                action="login_failed",
                user_id=int(row["user_id"]),
                user_login=str(row["login"]),
                role=row["role"],
                company_id=str(row["company_id"]) if row["company_id"] is not None else None,
                details={"reason": "invalid_credentials"},
            )
        raise ProdError(401, "invalid_credentials")

    limiter.reset_login(login_clean)

    token = generate_session_token()
    token_hash = hash_session_token(token)
    now = utc_now()
    ttl_seconds = cfg.session_ttl_hours * 3600
    expires_at = (now + timedelta(seconds=ttl_seconds)).isoformat()

    with tx(conn):
        conn.execute(
            """
            INSERT INTO sessions (token_hash, user_id, created_at, expires_at)
            VALUES (?, ?, ?, ?)
            """,
            (token_hash, int(row["user_id"]), now.isoformat(), expires_at),
        )
        append_audit(
            conn,
            action="login",
            timestamp=now.isoformat(),
            user_id=int(row["user_id"]),
            user_login=str(row["login"]),
            role=row["role"],
            company_id=str(row["company_id"]) if row["company_id"] is not None else None,
        )

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=cfg.cookie_secure,
        path="/",
        max_age=ttl_seconds,
    )

    user = User(
        id=int(row["user_id"]),
        login=str(row["login"]),
        full_name=str(row["full_name"]),
        role=row["role"],
        company_id=str(row["company_id"]) if row["company_id"] is not None else None,
    )
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
    return Session(user=user, company=company)


@router.post("/logout", status_code=204)
def post_logout(
    ctx: Annotated[AuthContext, Depends(current_session)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    cfg: Annotated[Settings, Depends(get_app_settings)],
    lang: LangQuery = DEFAULT_LANG,
) -> Response:
    """Revoke the current session token and clear the session cookie."""
    _ = lang
    now_iso = utc_now_iso()
    with tx(conn):
        conn.execute(
            "UPDATE sessions SET revoked_at = ? WHERE token_hash = ?",
            (now_iso, ctx.token_hash),
        )
        append_audit(
            conn,
            action="logout",
            timestamp=now_iso,
            user_id=ctx.user.id,
            user_login=ctx.user.login,
            role=ctx.user.role,
            company_id=ctx.user.company_id,
        )

    resp = Response(status_code=204)
    resp.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        samesite="lax",
        secure=cfg.cookie_secure,
    )
    return resp


@router.get("/me", response_model=Session)
def get_me(
    ctx: Annotated[AuthContext, Depends(current_session)],
    lang: LangQuery = DEFAULT_LANG,
) -> Session:
    """Return the authenticated user and company for the active session."""
    _ = lang
    return Session(user=ctx.user, company=ctx.company)
