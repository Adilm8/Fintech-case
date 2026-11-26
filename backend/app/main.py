"""FastAPI application for BCC Business Shield."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.risk.engine import check_payment
from app.schemas import (
    Approval,
    ApprovalCreateRequest,
    ApprovalDecisionRequest,
    CheckRequest,
    CheckResult,
    ClientInfo,
    DemoResetResponse,
    HistoryPaymentItem,
    HistoryResponse,
    QueuePaymentItem,
)
from app.store import store

app = FastAPI(
    title="BCC Business Shield API",
    description="Pre-signing SME supplier payment verification service.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/api/payments/check", response_model=CheckResult)
def post_check_payment(payload: CheckRequest) -> CheckResult:
    """Verify supplier payment requisites before signing."""
    return check_payment(payload, store)


@app.get("/api/payments/queue", response_model=list[QueuePaymentItem])
def get_payments_queue() -> list[QueuePaymentItem]:
    """Return payments awaiting signature with their computed risk verdicts."""
    items: list[QueuePaymentItem] = []
    for raw in store.queue:
        req = CheckRequest(
            payer_id=raw.get("payer_id"),
            recipient_name=raw["recipient_name"],
            recipient_bin=raw["recipient_bin"],
            recipient_iik=raw["recipient_iik"],
            recipient_bik=raw["recipient_bik"],
            amount_kzt=raw["amount_kzt"],
            purpose=raw.get("purpose", ""),
        )
        result = check_payment(req, store)
        items.append(QueuePaymentItem(**raw, check=result))
    return items


@app.get("/api/history", response_model=HistoryResponse)
def get_history() -> HistoryResponse:
    """Return client profile and payment history."""
    return HistoryResponse(
        client=ClientInfo(**store.client),
        payments=[HistoryPaymentItem(**p) for p in store.history],
    )


@app.post("/api/approvals", response_model=Approval)
def post_create_approval(payload: ApprovalCreateRequest) -> Approval:
    """Submit a payment for director approval."""
    result = check_payment(payload.check_request, store)
    approval = Approval(
        id=f"apr-{uuid.uuid4().hex[:10]}",
        request=payload.check_request,
        check=result,
        status="pending",
        accountant_note=payload.accountant_note,
    )
    store.approvals.append(approval)
    return approval


@app.get("/api/approvals", response_model=list[Approval])
def get_approvals() -> list[Approval]:
    """List all submitted director approvals."""
    return list(store.approvals)


@app.post("/api/approvals/{approval_id}/decision", response_model=Approval)
def post_approval_decision(
    approval_id: str,
    payload: ApprovalDecisionRequest,
) -> Approval:
    """Record the director's decision on a pending approval."""
    approval = store.get_approval(approval_id)
    if approval is None:
        raise HTTPException(status_code=404, detail="Заявка на согласование не найдена.")

    comment = payload.director_comment.strip() if payload.director_comment else ""
    if approval.check.verdict == "red" and not comment:
        raise HTTPException(
            status_code=422,
            detail="Для красного вердикта комментарий директора обязателен.",
        )

    approval.status = payload.decision
    approval.director_comment = comment or None
    approval.decided_at = datetime.now(UTC).replace(microsecond=0).isoformat()

    if payload.decision == "approved" and payload.trust_account:
        approval.trust_account = True
        store.trust_account(approval.request.recipient_bin, approval.request.recipient_iik)
    else:
        approval.trust_account = False

    return approval


@app.post("/api/demo/reset", response_model=DemoResetResponse)
def post_demo_reset() -> DemoResetResponse:
    """Clear approvals and trusted accounts and reload synthetic JSON data."""
    store.reset()
    return DemoResetResponse(
        status="reset",
        approvals_count=len(store.approvals),
        trusted_accounts_count=len(store.trusted_accounts),
    )
