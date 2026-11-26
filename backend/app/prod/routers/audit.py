"""Audit trail, hash-chain verification, and analyst evaluation metrics endpoints."""

from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.i18n import DEFAULT_LANG
from app.main import get_cached_metrics
from app.prod.audit_db import list_audit, verify_chain
from app.prod.db import get_db
from app.prod.deps import LangQuery, company_scope_id, require_role
from app.prod.schemas import AuditEntry, AuditVerifyResult, User
from app.risk.evaluation import localize_metrics
from app.schemas import MetricsResponse

router = APIRouter(prefix="/audit", tags=["audit"])
metrics_router = APIRouter(tags=["metrics"])


@router.get("", response_model=list[AuditEntry])
def get_audit_endpoint(
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    user: Annotated[User, Depends(require_role("director", "analyst"))],
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    payment_id: Annotated[str | None, Query()] = None,
    action: Annotated[str | None, Query()] = None,
    lang: LangQuery = DEFAULT_LANG,
) -> list[AuditEntry]:
    """Return newest-first audit log entries (company-scoped for director, global for analyst)."""
    _ = lang
    return list_audit(
        conn,
        company_id=company_scope_id(user),
        payment_id=payment_id.strip() if payment_id and payment_id.strip() else None,
        action=action.strip() if action and action.strip() else None,
        limit=limit,
    )


@router.get("/verify", response_model=AuditVerifyResult)
def verify_audit_endpoint(
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    user: Annotated[User, Depends(require_role("analyst"))],
    lang: LangQuery = DEFAULT_LANG,
) -> AuditVerifyResult:
    """Verify integrity of the entire SHA-256 audit log hash chain (analyst only)."""
    _ = (user, lang)
    return verify_chain(conn)


@metrics_router.get("/metrics", response_model=MetricsResponse)
def get_prod_metrics_endpoint(
    user: Annotated[User, Depends(require_role("analyst"))],
    lang: LangQuery = DEFAULT_LANG,
) -> MetricsResponse:
    """Return localized evaluation dataset metrics (analyst role only, matches demo /api/metrics)."""
    _ = user
    return localize_metrics(get_cached_metrics(lang=lang), lang)
