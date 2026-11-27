"""Authentication endpoints: login, logout, and current session lookup."""

from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

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
    LoginRateLimiter,
    generate_session_token,
    hash_session_token,
    session_cookie_name,
    session_expiry,
    utc_now,
    utc_now_iso,
    verify_dummy_password,
    verify_password,
)
from app.settings import Settings

router = APIRouter(prefix="/auth", tags=["auth"])


def _client_ip(request: Request) -> str:
    """Return direct peer address; do not trust X-Forwarded-For as clients can spoof it."""
    if request.client is not None and request.client.host:
        return request.client.host
    return "unknown"


@router.post("/login", response_model=Session)
def post_login(
    request: Request,
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
    client_ip = _client_ip(request)

    ip_retry = limiter.ip_retry_after(client_ip)
    if ip_retry > 0:
        raise ProdError(429, "too_many_attempts", extra={"retry_after": ip_retry})

    login_retry = limiter.retry_after(login_clean)
    if login_retry > 0:
        raise ProdError(429, "too_many_attempts", extra={"retry_after": login_retry})

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
            u.must_change_password,
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

    if row is None:
        verify_dummy_password(payload.password)
        limiter.record_failure(login_clean)
        limiter.record_ip_failure(client_ip)
        audit_events = limiter.unknown_audit.note(client_ip, login_clean)
        if audit_events:
            with tx(conn):
                for event in audit_events:
                    append_audit(
                        conn,
                        action="login_failed",
                        user_id=None,
                        user_login=str(event["login"]),
                        role=None,
                        company_id=None,
                        details={
                            "reason": "invalid_credentials",
                            "ip": event["ip"],
                            "count": event["count"],
                            "aggregated": event["aggregated"],
                        },
                    )
        raise ProdError(401, "invalid_credentials")

    if int(row["is_active"]) != 1:
        verify_dummy_password(payload.password)
        limiter.record_failure(login_clean)
        limiter.record_ip_failure(client_ip)
        with tx(conn):
            append_audit(
                conn,
                action="login_failed",
                user_id=int(row["user_id"]),
                user_login=str(row["login"]),
                role=row["role"],
                company_id=str(row["company_id"]) if row["company_id"] is not None else None,
                details={"reason": "invalid_credentials", "ip": client_ip},
            )
        raise ProdError(401, "invalid_credentials")

    if not verify_password(payload.password, str(row["password_hash"])):
        limiter.record_failure(login_clean)
        limiter.record_ip_failure(client_ip)
        with tx(conn):
            append_audit(
                conn,
                action="login_failed",
                user_id=int(row["user_id"]),
                user_login=str(row["login"]),
                role=row["role"],
                company_id=str(row["company_id"]) if row["company_id"] is not None else None,
                details={"reason": "invalid_credentials", "ip": client_ip},
            )
        raise ProdError(401, "invalid_credentials")

    limiter.reset_login(login_clean)

    token = generate_session_token()
    token_hash = hash_session_token(token)
    now = utc_now()
    ttl_seconds = cfg.session_ttl_hours * 3600
    idle_seconds = cfg.session_idle_minutes * 60
    expires_at = session_expiry(
        now,
        now,
        ttl_seconds=ttl_seconds,
        idle_seconds=idle_seconds,
    ).isoformat()

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
        key=session_cookie_name(cfg.cookie_secure),
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
    return Session(
        user=user,
        company=company,
        must_change_password=bool(row["must_change_password"]),
    )


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
        key=session_cookie_name(cfg.cookie_secure),
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
    return Session(
        user=ctx.user,
        company=ctx.company,
        must_change_password=ctx.must_change_password,
    )
