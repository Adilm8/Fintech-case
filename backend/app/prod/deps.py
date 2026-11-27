"""FastAPI dependencies for authentication, role checks, CSRF header, and company scope."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import Depends, Query, Request, Response

from app.i18n import DEFAULT_LANG, MESSAGES, Lang
from app.prod.db import get_db
from app.prod.errors import ProdError
from app.prod.schemas import Company, Role, User
from app.prod.security import (
    LoginRateLimiter,
    hash_session_token,
    read_session_token,
    slide_session_expiry,
    utc_now,
)
from app.settings import Settings, load_settings

CSRF_HEADER_NAME: str = "X-Shield-Request"
CSRF_HEADER_VALUE: str = "1"
MUST_CHANGE_PASSWORD_HEADER: str = "X-Shield-Must-Change-Password"
_SAFE_METHODS: frozenset[str] = frozenset({"GET", "HEAD", "OPTIONS"})
_PASSWORD_CHANGE_ALLOWED_ROUTES: frozenset[tuple[str, str]] = frozenset(
    {
        ("GET", "/api/v1/auth/me"),
        ("POST", "/api/v1/auth/logout"),
        ("POST", "/api/v1/me/password"),
    }
)

LangQuery = Annotated[Lang, Query()]


@dataclass(frozen=True)
class AuthContext:
    """Resolved authenticated user, company (None for analyst), session hash, and password flag."""

    user: User
    company: Company | None
    token_hash: str
    must_change_password: bool = False


def serialize_session(ctx: AuthContext) -> dict[str, Any]:
    """Serialize an AuthContext into a session payload including must_change_password."""
    return {
        "user": ctx.user.model_dump(),
        "company": ctx.company.model_dump() if ctx.company is not None else None,
        "must_change_password": ctx.must_change_password,
    }


def _is_password_change_allowed(request: Request) -> bool:
    path = request.url.path.rstrip("/") or "/"
    return (request.method.upper(), path) in _PASSWORD_CHANGE_ALLOWED_ROUTES


def require_csrf_header(request: Request) -> None:
    """Require X-Shield-Request: 1 on all non-GET state-changing requests."""
    if request.method.upper() in _SAFE_METHODS:
        return
    header_val = (request.headers.get(CSRF_HEADER_NAME) or "").strip()
    if header_val != CSRF_HEADER_VALUE:
        raise ProdError(403, "csrf_header_missing")


def get_app_settings(request: Request) -> Settings:
    """Return runtime settings attached to app state (or loaded from env)."""
    attached = getattr(request.app.state, "settings", None)
    if isinstance(attached, Settings):
        return attached
    return load_settings()


def get_login_limiter(request: Request) -> LoginRateLimiter:
    """Return the process/app login rate limiter instance."""
    limiter = getattr(request.app.state, "login_limiter", None)
    if isinstance(limiter, LoginRateLimiter):
        return limiter
    limiter = LoginRateLimiter()
    request.app.state.login_limiter = limiter
    return limiter


def _parse_iso_utc(raw: str) -> datetime:
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def current_session(
    request: Request,
    response: Response,
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> AuthContext:
    """Authenticate request strictly from the session cookie (ignores X-Role)."""
    cfg = get_app_settings(request)
    token = read_session_token(request.cookies, cfg.cookie_secure)
    if not token:
        raise ProdError(401, "not_authenticated")

    token_hash = hash_session_token(token)
    row = conn.execute(
        """
        SELECT
            s.token_hash,
            s.created_at,
            s.expires_at,
            s.revoked_at,
            u.id AS user_id,
            u.login,
            u.full_name,
            u.role,
            u.company_id,
            u.is_active,
            u.must_change_password,
            c.id AS c_id,
            c.name AS c_name,
            c.bin AS c_bin,
            c.iik AS c_iik,
            c.bik AS c_bik
        FROM sessions s
        JOIN users u ON u.id = s.user_id
        LEFT JOIN companies c ON c.id = u.company_id
        WHERE s.token_hash = ?
        """,
        (token_hash,),
    ).fetchone()

    if row is None:
        raise ProdError(401, "not_authenticated")
    if row["revoked_at"] is not None:
        raise ProdError(401, "not_authenticated")
    if int(row["is_active"]) != 1:
        raise ProdError(401, "not_authenticated")

    try:
        expires_at = _parse_iso_utc(str(row["expires_at"]))
    except ValueError as exc:
        raise ProdError(401, "not_authenticated") from exc
    now = utc_now()
    if expires_at <= now:
        raise ProdError(401, "not_authenticated")

    slide_session_expiry(
        conn,
        token_hash=token_hash,
        created_at=str(row["created_at"]),
        expires_at=str(row["expires_at"]),
        ttl_seconds=cfg.session_ttl_hours * 3600,
        idle_seconds=cfg.session_idle_minutes * 60,
        now=now,
    )

    must_change_password = bool(row["must_change_password"])
    response.headers[MUST_CHANGE_PASSWORD_HEADER] = "1" if must_change_password else "0"
    if must_change_password and not _is_password_change_allowed(request):
        detail = (
            None
            if "error.prod.password_change_required" in MESSAGES
            else "Password change is required before accessing other endpoints."
        )
        raise ProdError(403, "password_change_required", detail=detail)

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
    return AuthContext(
        user=user,
        company=company,
        token_hash=token_hash,
        must_change_password=must_change_password,
    )


def current_user(
    ctx: Annotated[AuthContext, Depends(current_session)],
) -> User:
    """Return the authenticated User from the current session."""
    return ctx.user


def require_role(*roles: Role) -> Callable[..., User]:
    """Dependency factory ensuring the current user has one of the allowed roles."""
    allowed = frozenset(roles)

    def _check_role(user: Annotated[User, Depends(current_user)]) -> User:
        if user.role not in allowed:
            raise ProdError(403, "forbidden_role")
        return user

    return _check_role


def company_scope_id(user: User) -> str | None:
    """Return company_id to scope queries by, or None for bank analysts (all companies)."""
    if user.role == "analyst":
        return None
    if not user.company_id:
        raise ProdError(403, "forbidden_role")
    return user.company_id


def ensure_company_access(user: User, target_company_id: str) -> None:
    """Enforce company tenant isolation, raising 404 (never 403) for cross-company objects."""
    if user.role == "analyst":
        return
    if user.company_id != target_company_id:
        raise ProdError(404, "not_found")


def get_lang(lang: LangQuery = DEFAULT_LANG) -> Lang:
    """Validate and return the ?lang query parameter."""
    return lang
