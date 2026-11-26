"""Company profile, user management, and settings endpoints (/api/v1/company/*)."""

from __future__ import annotations

import secrets
import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends

from app.i18n import DEFAULT_LANG, Lang
from app.prod.audit_db import append_audit
from app.prod.company_settings import get_company_settings
from app.prod.db import get_db, tx
from app.prod.deps import LangQuery, company_scope_id, require_role
from app.prod.errors import ProdError
from app.prod.schemas import (
    CompanyDetail,
    CompanySettings,
    CompanyUser,
    InviteUserRequest,
    InviteUserResponse,
    UpdateCompanySettingsRequest,
    UpdateCompanyUserRequest,
    User,
)
from app.prod.security import hash_password, utc_now_iso

router = APIRouter(prefix="/company", tags=["company"])


def _row_to_company_user(row: sqlite3.Row) -> CompanyUser:
    raw_lang = row["default_lang"]
    default_lang: Lang = raw_lang if raw_lang in ("ru", "kk", "en") else "ru"
    return CompanyUser(
        id=int(row["id"]),
        login=str(row["login"]),
        full_name=str(row["full_name"]),
        role=row["role"],
        is_active=bool(row["is_active"]),
        default_lang=default_lang,
        created_at=str(row["created_at"]),
    )


def _require_user_company_id(user: User) -> str:
    company_id = company_scope_id(user)
    if company_id is None:
        raise ProdError(403, "forbidden_role")
    return company_id


@router.get("", response_model=CompanyDetail)
def get_company(
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    user: Annotated[User, Depends(require_role("accountant", "director"))],
    lang: LangQuery = DEFAULT_LANG,
) -> CompanyDetail:
    """Return company metadata and list of company users with roles."""
    _ = lang
    company_id = _require_user_company_id(user)
    comp = conn.execute(
        "SELECT id, name, bin, iik, bik, created_at FROM companies WHERE id = ?",
        (company_id,),
    ).fetchone()
    if comp is None:
        raise ProdError(404, "not_found")

    user_rows = conn.execute(
        """
        SELECT id, login, full_name, role, is_active, default_lang, created_at
        FROM users
        WHERE company_id = ?
        ORDER BY is_active DESC,
                 CASE WHEN role = 'director' THEN 0 ELSE 1 END ASC,
                 id ASC
        """,
        (company_id,),
    ).fetchall()

    return CompanyDetail(
        id=str(comp["id"]),
        name=str(comp["name"]),
        bin=str(comp["bin"]),
        iik=str(comp["iik"]),
        bik=str(comp["bik"]),
        created_at=str(comp["created_at"]),
        users=[_row_to_company_user(r) for r in user_rows],
    )


@router.post("/users", response_model=InviteUserResponse, status_code=201)
def invite_company_user(
    payload: InviteUserRequest,
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    user: Annotated[User, Depends(require_role("director"))],
    lang: LangQuery = DEFAULT_LANG,
) -> InviteUserResponse:
    """Director-only: create a new company user and return a one-time temporary password."""
    _ = lang
    company_id = _require_user_company_id(user)
    temp_password = secrets.token_urlsafe(12)
    pw_hash = hash_password(temp_password)
    now_iso = utc_now_iso()

    with tx(conn):
        existing = conn.execute(
            "SELECT id FROM users WHERE login = ?",
            (payload.login,),
        ).fetchone()
        if existing is not None:
            raise ProdError(409, "login_already_exists")

        try:
            cur = conn.execute(
                """
                INSERT INTO users (
                    company_id, login, full_name, role, password_hash,
                    is_active, default_lang, created_at
                ) VALUES (?, ?, ?, ?, ?, 1, 'ru', ?)
                """,
                (
                    company_id,
                    payload.login,
                    payload.full_name,
                    payload.role,
                    pw_hash,
                    now_iso,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise ProdError(409, "login_already_exists") from exc

        assert cur.lastrowid is not None
        new_id = int(cur.lastrowid)
        append_audit(
            conn,
            action="user_invited",
            timestamp=now_iso,
            user_id=user.id,
            user_login=user.login,
            role=user.role,
            company_id=company_id,
            details={
                "target_user_id": new_id,
                "target_login": payload.login,
                "target_role": payload.role,
            },
        )
        created_row = conn.execute(
            """
            SELECT id, login, full_name, role, is_active, default_lang, created_at
            FROM users
            WHERE id = ?
            """,
            (new_id,),
        ).fetchone()
        assert created_row is not None

    return InviteUserResponse(
        user=_row_to_company_user(created_row),
        temporary_password=temp_password,
    )


@router.put("/users/{target_user_id}", response_model=CompanyUser)
def update_company_user(
    target_user_id: int,
    payload: UpdateCompanyUserRequest,
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    user: Annotated[User, Depends(require_role("director"))],
    lang: LangQuery = DEFAULT_LANG,
) -> CompanyUser:
    """Director-only: update a company user's role and/or active state (protects last director)."""
    _ = lang
    company_id = _require_user_company_id(user)
    now_iso = utc_now_iso()

    with tx(conn):
        target = conn.execute(
            """
            SELECT id, company_id, login, full_name, role, is_active, default_lang, created_at
            FROM users
            WHERE id = ?
            """,
            (target_user_id,),
        ).fetchone()
        if target is None or str(target["company_id"]) != company_id:
            raise ProdError(404, "not_found")

        old_role = str(target["role"])
        old_active = bool(target["is_active"])
        new_role = payload.role if payload.role is not None else old_role
        new_active = payload.is_active if payload.is_active is not None else old_active

        # Never allow demoting or deactivating the last active director of the company
        if old_role == "director" and old_active and (new_role != "director" or not new_active):
            cnt_row = conn.execute(
                """
                SELECT COUNT(*)
                FROM users
                WHERE company_id = ?
                  AND role = 'director'
                  AND is_active = 1
                """,
                (company_id,),
            ).fetchone()
            active_directors = int(cnt_row[0]) if cnt_row is not None else 0
            if active_directors <= 1:
                raise ProdError(409, "last_director_protected")

        conn.execute(
            "UPDATE users SET role = ?, is_active = ? WHERE id = ?",
            (new_role, 1 if new_active else 0, target_user_id),
        )

        revoked_sessions = 0
        if not new_active:
            cur = conn.execute(
                """
                UPDATE sessions
                SET revoked_at = ?
                WHERE user_id = ? AND revoked_at IS NULL
                """,
                (now_iso, target_user_id),
            )
            revoked_sessions = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0

        append_audit(
            conn,
            action="company_user_updated",
            timestamp=now_iso,
            user_id=user.id,
            user_login=user.login,
            role=user.role,
            company_id=company_id,
            details={
                "target_user_id": target_user_id,
                "target_login": str(target["login"]),
                "old_role": old_role,
                "new_role": new_role,
                "old_active": old_active,
                "new_active": new_active,
                "revoked_sessions": revoked_sessions,
            },
        )
        updated_row = conn.execute(
            """
            SELECT id, login, full_name, role, is_active, default_lang, created_at
            FROM users
            WHERE id = ?
            """,
            (target_user_id,),
        ).fetchone()
        assert updated_row is not None

    return _row_to_company_user(updated_row)


@router.get("/settings", response_model=CompanySettings)
def get_settings(
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    user: Annotated[User, Depends(require_role("director"))],
    lang: LangQuery = DEFAULT_LANG,
) -> CompanySettings:
    """Director-only: return company notification filter and approval threshold."""
    _ = lang
    company_id = _require_user_company_id(user)
    state = get_company_settings(conn, company_id)
    return CompanySettings(
        notify_on=state.notify_on,
        approval_threshold_kzt=state.approval_threshold_kzt,
        updated_at=state.updated_at,
    )


@router.put("/settings", response_model=CompanySettings)
def update_settings(
    payload: UpdateCompanySettingsRequest,
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    user: Annotated[User, Depends(require_role("director"))],
    lang: LangQuery = DEFAULT_LANG,
) -> CompanySettings:
    """Director-only: update notify_on and/or approval_threshold_kzt (null disables threshold)."""
    _ = lang
    company_id = _require_user_company_id(user)
    now_iso = utc_now_iso()

    with tx(conn):
        current = get_company_settings(conn, company_id)
        new_notify_on = payload.notify_on if payload.notify_on is not None else current.notify_on
        if "approval_threshold_kzt" in payload.model_fields_set:
            new_threshold_tiyn = (
                round(float(payload.approval_threshold_kzt) * 100)
                if payload.approval_threshold_kzt is not None
                else None
            )
        else:
            new_threshold_tiyn = current.approval_threshold_tiyn

        conn.execute(
            """
            INSERT INTO company_settings (
                company_id, notify_on, approval_threshold_tiyn, updated_at
            ) VALUES (?, ?, ?, ?)
            ON CONFLICT(company_id) DO UPDATE SET
                notify_on = excluded.notify_on,
                approval_threshold_tiyn = excluded.approval_threshold_tiyn,
                updated_at = excluded.updated_at
            """,
            (company_id, new_notify_on, new_threshold_tiyn, now_iso),
        )

        new_threshold_kzt = (
            new_threshold_tiyn / 100.0 if new_threshold_tiyn is not None else None
        )
        append_audit(
            conn,
            action="company_settings_updated",
            timestamp=now_iso,
            user_id=user.id,
            user_login=user.login,
            role=user.role,
            company_id=company_id,
            details={
                "old_notify_on": current.notify_on,
                "new_notify_on": new_notify_on,
                "old_approval_threshold_kzt": current.approval_threshold_kzt,
                "new_approval_threshold_kzt": new_threshold_kzt,
            },
        )

    return CompanySettings(
        notify_on=new_notify_on,
        approval_threshold_kzt=new_threshold_kzt,
        updated_at=now_iso,
    )
