"""Director approval endpoints (/api/v1/approvals/*)."""

from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.i18n import DEFAULT_LANG
from app.prod import payments_service
from app.prod.db import get_db
from app.prod.deps import LangQuery, get_app_settings, require_role
from app.prod.schemas import (
    ProdApproval,
    ProdApprovalDecisionRequest,
    ProdApprovalStatus,
    User,
)
from app.settings import Settings

router = APIRouter(prefix="/approvals", tags=["approvals"])


@router.get("", response_model=list[ProdApproval])
def list_approvals_endpoint(
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    user: Annotated[User, Depends(require_role("accountant", "director", "analyst"))],
    status: Annotated[ProdApprovalStatus | None, Query()] = None,
    lang: LangQuery = DEFAULT_LANG,
) -> list[ProdApproval]:
    """List approval requests (default: all except superseded, pending first then newest)."""
    return payments_service.list_approvals(
        conn,
        user=user,
        status=status,
        lang=lang,
    )


@router.post("/{approval_id}/decision", response_model=ProdApproval)
def decide_approval_endpoint(
    approval_id: str,
    payload: ProdApprovalDecisionRequest,
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    user: Annotated[User, Depends(require_role("director"))],
    cfg: Annotated[Settings, Depends(get_app_settings)],
    lang: LangQuery = DEFAULT_LANG,
) -> ProdApproval:
    """Record the director's approval or rejection decision."""
    return payments_service.decide_approval(
        conn,
        approval_id=approval_id,
        user=user,
        payload=payload,
        today=cfg.today(),
        lang=lang,
    )
