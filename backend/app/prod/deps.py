"""FastAPI dependencies for authentication, role checks, CSRF header, and company scope."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Query, Request

from app.i18n import DEFAULT_LANG, Lang
from app.prod.db import get_db
from app.prod.errors import ProdError
from app.prod.schemas import Company, Role, User
from app.prod.security import (
    SESSION_COOKIE_NAME,
    LoginRateLimiter,
    hash_session_token,
    utc_now,
)
from app.settings import Settings, load_settings

CSRF_HEADER_NAME: str = "X-Shield-Request"
CSRF_HEADER_VALUE: str = "1"
_SAFE_METHODS: frozenset[str] = frozenset({"GET", "HEAD", "OPTIONS"})

LangQuery = Annotated[Lang, Query()]


@dataclass(frozen=True)
class AuthContext:
    """Resolved authenticated user, company (None for analyst), and session token hash."""

    user: User
    company: Company | None
    token_hash: str


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
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> AuthContext:
    """Authenticate request strictly from the shield_session cookie (ignores X-Role)."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise ProdError(401, "not_authenticated")

    token_hash = hash_session_token(token)
    row = conn.execute(
        """
        SELECT
            s.token_hash,
            s.expires_at,
            s.revoked_at,
            u.id AS user_id,
            u.login,
            u.full_name,
            u.role,
            u.company_id,
            u.is_active,
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
    if expires_at <= utc_now():
        raise ProdError(401, "not_authenticated")

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
    return AuthContext(user=user, company=company, token_hash=token_hash)


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
