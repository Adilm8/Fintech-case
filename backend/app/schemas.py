"""Pydantic API and domain schemas for BCC Business Shield."""

from __future__ import annotations

import math
import unicodedata
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

Verdict = Literal["green", "yellow", "red", "grey", "invalid"]
Severity = Literal["block", "primary", "amplifier", "info"]
DiffFieldName = Literal["name", "bin", "iik", "bik", "bank", "amount"]
ActionType = Literal["postpone", "send_to_director", "sign"]
ApprovalStatus = Literal["pending", "approved", "rejected"]

_INVISIBLE_CATEGORIES: frozenset[str] = frozenset({"Cf", "Cc", "Cn", "Cs", "Zl", "Zp", "Zs"})
_INVISIBLE_TEXT_CATEGORIES: frozenset[str] = frozenset({"Cf", "Cc", "Cn", "Cs"})


def normalize_requisite(value: str) -> str:
    """Strip spaces, NBSP, and invisible characters, uppercasing ASCII letters only.

    Non-ASCII characters (including Cyrillic lookalikes) are preserved as-is so
    requisite validators can still detect and report them clearly.
    """
    out: list[str] = []
    for ch in value:
        if ch.isspace() or unicodedata.category(ch) in _INVISIBLE_CATEGORIES:
            continue
        if "a" <= ch <= "z":
            out.append(ch.upper())
        else:
            out.append(ch)
    return "".join(out)


def clean_text_field(value: str) -> str:
    """Remove invisible format/control characters (preserving regular spaces) and strip edges."""
    cleaned = "".join(
        ch
        for ch in value
        if ch in ("\n", "\t") or unicodedata.category(ch) not in _INVISIBLE_TEXT_CATEGORIES
    )
    return cleaned.strip()


def meaningful_length(value: str | None) -> int:
    """Count characters remaining after stripping all whitespace and invisible characters."""
    if not value:
        return 0
    return sum(
        1
        for ch in value
        if not ch.isspace() and unicodedata.category(ch) not in _INVISIBLE_CATEGORIES
    )


class CheckRequest(BaseModel):
    """Incoming payment requisites to verify before signing."""

    payer_id: str | None = Field(default=None, max_length=100)
    recipient_name: str = Field(min_length=1, max_length=250)
    recipient_bin: str = Field(max_length=64)
    recipient_iik: str = Field(max_length=64)
    recipient_bik: str = Field(max_length=64)
    amount_kzt: float = Field(gt=0, le=1e12, allow_inf_nan=False)
    purpose: str = Field(default="", max_length=500)

    @field_validator("payer_id")
    @classmethod
    def _clean_payer_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = clean_text_field(value)
        return cleaned or None

    @field_validator("recipient_name")
    @classmethod
    def _clean_recipient_name(cls, value: str) -> str:
        cleaned = clean_text_field(value)
        if not cleaned or meaningful_length(cleaned) == 0:
            raise ValueError("Укажите название получателя.")
        return cleaned

    @field_validator("recipient_bin", "recipient_iik", "recipient_bik")
    @classmethod
    def _clean_requisites(cls, value: str) -> str:
        return normalize_requisite(value)

    @field_validator("amount_kzt")
    @classmethod
    def _validate_finite_amount(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("Сумма платежа должна быть конечным числом.")
        return value


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
    reason: str = ""
    message_key: str | None = Field(default=None, exclude=True)
    message_params: dict[str, Any] = Field(default_factory=dict, exclude=True)
    evidence: Evidence

    @model_validator(mode="after")
    def _default_localized_reason(self) -> Signal:
        if not self.reason:
            self.reason = self.reason_ru
        return self


class FieldDiff(BaseModel):
    """Comparison row between the invoice being checked and payment history."""

    field: DiffFieldName
    in_invoice: str
    in_history: str | None = None
    last_seen: str | None = None
    differs: bool
    diff_positions: list[int] = Field(default_factory=list)


class NextAction(BaseModel):
    """Recommended user action and plain-language guidance."""

    text_ru: str
    text: str = ""
    message_key: str | None = Field(default=None, exclude=True)
    primary: ActionType
    secondary: list[ActionType] = Field(default_factory=list)

    @model_validator(mode="after")
    def _default_localized_text(self) -> NextAction:
        if not self.text:
            self.text = self.text_ru
        return self


class HistorySummary(BaseModel):
    """Summary of past payments to the supplier."""

    payments_count: int
    last_payment_date: str | None = None
    median_amount_kzt: float | None = None
    compared_with: str | None = None


class TrustedInfo(BaseModel):
    """Audit metadata recorded when the director trusts a supplier account."""

    decided_at: str
    director_comment: str


class CheckResult(BaseModel):
    """Complete payment risk check verdict and explanation."""

    check_id: str
    verdict: Verdict
    score: int = Field(ge=0, le=100)
    headline_ru: str
    headline: str = ""
    headline_key: str | None = Field(default=None, exclude=True)
    signals: list[Signal]
    comparison: list[FieldDiff]
    next_action: NextAction
    history: HistorySummary
    trusted: bool = False
    trusted_info: TrustedInfo | None = None

    @model_validator(mode="after")
    def _default_localized_headline(self) -> CheckResult:
        if not self.headline:
            self.headline = self.headline_ru
        return self


class Approval(BaseModel):
    """Director approval workflow item."""

    id: str
    request: CheckRequest
    check: CheckResult
    status: ApprovalStatus = "pending"
    accountant_note: str = Field(default="", max_length=1000)
    director_comment: str | None = Field(default=None, max_length=1000)
    trust_account: bool = False
    decided_at: str | None = None


class ApprovalCreateRequest(BaseModel):
    """Request body for submitting a payment for director approval."""

    check_request: CheckRequest
    accountant_note: str = Field(default="", max_length=1000)


class ApprovalDecisionRequest(BaseModel):
    """Request body for director approval or rejection."""

    decision: Literal["approved", "rejected"]
    director_comment: str | None = Field(default=None, max_length=1000)
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


EvalLabel = Literal["legit", "attack"]


class VerdictCounts(BaseModel):
    """Breakdown of engine verdicts across a group of evaluation cases."""

    green: int = 0
    yellow: int = 0
    red: int = 0
    grey: int = 0
    invalid: int = 0


class ConfusionTable(BaseModel):
    """Binary confusion matrix where positive means verdict in {'yellow', 'red'}."""

    tp: int
    fn: int
    fp: int
    tn: int


class KindMetrics(BaseModel):
    """Evaluation statistics for a single scenario kind."""

    kind: str
    label: EvalLabel
    total: int
    verdicts: VerdictCounts
    flagged_count: int
    detection_rate: float | None = None
    false_positive_rate: float | None = None


class MetricsSummary(BaseModel):
    """Aggregate detection and false-alarm metrics over the evaluation set."""

    total_cases: int
    total_legit: int
    total_attack: int
    detection_rate: float
    false_positive_rate: float
    precision: float
    f1: float
    accuracy: float


class MetricsResponse(BaseModel):
    """Cached evaluation report returned by GET /api/metrics and scripts/evaluate.py."""

    seed: int
    dataset_path: str
    positive_verdicts: list[Verdict] = Field(default_factory=lambda: ["yellow", "red"])
    summary: MetricsSummary
    confusion: ConfusionTable
    verdict_by_label: dict[EvalLabel, VerdictCounts]
    by_kind: list[KindMetrics]
    disclaimer_ru: str
