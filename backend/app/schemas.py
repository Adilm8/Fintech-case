"""Pydantic API and domain schemas for BCC Business Shield."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Verdict = Literal["green", "yellow", "red", "grey", "invalid"]
Severity = Literal["block", "primary", "amplifier", "info"]
DiffFieldName = Literal["name", "bin", "iik", "bik", "bank", "amount"]
ActionType = Literal["postpone", "send_to_director", "sign"]
ApprovalStatus = Literal["pending", "approved", "rejected"]


class CheckRequest(BaseModel):
    """Incoming payment requisites to verify before signing."""

    payer_id: str | None = None
    recipient_name: str
    recipient_bin: str
    recipient_iik: str
    recipient_bik: str
    amount_kzt: float = Field(gt=0)
    purpose: str = ""


class Evidence(BaseModel):
    """Structured factual evidence behind a triggered risk signal."""

    field: str
    expected: str | None = None
    actual: str | None = None
    since: str | None = None


class Signal(BaseModel):
    """Single rule evaluation result."""

    rule_id: str
    points: int
    severity: Severity
    reason_ru: str
    evidence: Evidence


class FieldDiff(BaseModel):
    """Comparison row between the invoice being checked and payment history."""

    field: DiffFieldName
    in_invoice: str
    in_history: str | None = None
    last_seen: str | None = None
    differs: bool
    diff_positions: list[int] = Field(default_factory=list)


class NextAction(BaseModel):
    """Recommended user action and plain-language Russian guidance."""

    text_ru: str
    primary: ActionType
    secondary: list[ActionType] = Field(default_factory=list)


class HistorySummary(BaseModel):
    """Summary of past payments to the supplier."""

    payments_count: int
    last_payment_date: str | None = None
    median_amount_kzt: float | None = None


class CheckResult(BaseModel):
    """Complete payment risk check verdict and explanation."""

    check_id: str
    verdict: Verdict
    score: int = Field(ge=0, le=100)
    headline_ru: str
    signals: list[Signal]
    comparison: list[FieldDiff]
    next_action: NextAction
    history: HistorySummary


class Approval(BaseModel):
    """Director approval workflow item."""

    id: str
    request: CheckRequest
    check: CheckResult
    status: ApprovalStatus = "pending"
    accountant_note: str = ""
    director_comment: str | None = None
    trust_account: bool = False
    decided_at: str | None = None


class ApprovalCreateRequest(BaseModel):
    """Request body for submitting a payment for director approval."""

    check_request: CheckRequest
    accountant_note: str = ""


class ApprovalDecisionRequest(BaseModel):
    """Request body for director approval or rejection."""

    decision: Literal["approved", "rejected"]
    director_comment: str | None = None
    trust_account: bool = False


class QueuePaymentItem(BaseModel):
    """Payment in the signing queue with its precomputed risk verdict."""

    id: str
    scenario: str
    created_at: str
    payer_id: str
    recipient_name: str
    recipient_bin: str
    recipient_iik: str
    recipient_bik: str
    amount_kzt: float
    purpose: str
    check: CheckResult


class HistoryPaymentItem(BaseModel):
    """Historical completed supplier payment."""

    id: str
    payer_id: str
    paid_at: str
    recipient_name: str
    recipient_bin: str
    recipient_iik: str
    recipient_bik: str
    amount_kzt: float
    purpose: str


class ClientInfo(BaseModel):
    """SME client profile."""

    payer_id: str
    name: str
    bin: str
    iik: str
    bik: str


class HistoryResponse(BaseModel):
    """Client profile and chronological payment history."""

    client: ClientInfo
    payments: list[HistoryPaymentItem]


class DemoResetResponse(BaseModel):
    """Confirmation payload after resetting in-memory demo state."""

    status: Literal["reset"] = "reset"
    approvals_count: int = 0
    trusted_accounts_count: int = 0
