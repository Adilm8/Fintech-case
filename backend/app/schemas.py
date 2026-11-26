"""Pydantic API and domain schemas for BCC Business Shield."""

from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from typing import Any, Literal

from pydantic import (
    BaseModel,
    Field,
    SerializerFunctionWrapHandler,
    field_validator,
    model_serializer,
    model_validator,
)

from app.risk.config import INVISIBLE_CODEPOINTS, RULESET_VERSION

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
        if (
            ch.isspace()
            or ch in INVISIBLE_CODEPOINTS
            or unicodedata.category(ch) in _INVISIBLE_CATEGORIES
        ):
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
        if not ch.isspace()
        and ch not in INVISIBLE_CODEPOINTS
        and unicodedata.category(ch) not in _INVISIBLE_CATEGORIES
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
    kbe: str = Field(default="", max_length=10)
    knp: str = Field(default="", max_length=10)

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

    @field_validator("recipient_bin", "recipient_iik", "recipient_bik", "kbe", "knp")
    @classmethod
    def _clean_requisites(cls, value: str) -> str:
        return normalize_requisite(value)

    @field_validator("amount_kzt")
    @classmethod
    def _validate_finite_amount(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("Сумма платежа должна быть конечным числом.")
        return value


def compute_request_sha256(req: CheckRequest, *, resolved_payer_id: str | None = None) -> str:
    """Compute canonical, language-independent SHA-256 hex digest of a CheckRequest."""
    canonical_payload = {
        "payer_id": resolved_payer_id if resolved_payer_id is not None else (req.payer_id or ""),
        "recipient_name": req.recipient_name,
        "recipient_bin": req.recipient_bin,
        "recipient_iik": req.recipient_iik,
        "recipient_bik": req.recipient_bik,
        "amount_kzt": float(req.amount_kzt),
        "purpose": req.purpose,
        "kbe": req.kbe,
        "knp": req.knp,
    }
    raw = json.dumps(canonical_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class Evidence(BaseModel):
    """Structured factual evidence behind a triggered risk signal."""

    field: str
    field_label: str = ""
    expected: str | None = None
    actual: str | None = None
    since: str | None = None
    positions: list[int] | None = None
    expected_key: str | None = Field(default=None, exclude=True)
    expected_params: dict[str, Any] = Field(default_factory=dict, exclude=True)
    actual_key: str | None = Field(default=None, exclude=True)
    actual_params: dict[str, Any] = Field(default_factory=dict, exclude=True)

    @model_serializer(mode="wrap")
    def _serialize_evidence(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data = handler(self)
        if data.get("positions") is None:
            data.pop("positions", None)
        if not data.get("field_label"):
            data.pop("field_label", None)
        return data


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
    message_params: dict[str, Any] = Field(default_factory=dict, exclude=True)
    invalid_field_keys: list[str] = Field(default_factory=list, exclude=True)
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


class AnalystSignalDetail(BaseModel):
    """Restricted antifraud detail for a signal redacted from client responses."""

    rule_id: str
    reason_ru: str
    reason: str = ""
    message_key: str | None = Field(default=None, exclude=True)
    message_params: dict[str, Any] = Field(default_factory=dict, exclude=True)
    evidence: Evidence

    @model_validator(mode="after")
    def _default_localized_reason(self) -> AnalystSignalDetail:
        if not self.reason:
            self.reason = self.reason_ru
        return self


class BccAccountAnalystInfo(BaseModel):
    """Internal BCC account metadata visible only to antifraud analysts."""

    iik: str
    owner_bin: str
    owner_name: str
    opened_at: str
    age_days: int
    owner_matches_recipient: bool


class AnalystDetails(BaseModel):
    """Antifraud analyst-only details omitted from standard client responses."""

    bcc_account: BccAccountAnalystInfo | None = None
    signal_details: list[AnalystSignalDetail] = Field(default_factory=list)


class CheckResult(BaseModel):
    """Complete payment risk check verdict and explanation."""

    check_id: str
    ruleset_version: str = RULESET_VERSION
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
    analyst_details: AnalystDetails | None = None
    internal_analyst_details: AnalystDetails | None = Field(default=None, exclude=True)

    @model_validator(mode="after")
    def _default_localized_headline(self) -> CheckResult:
        if not self.headline:
            self.headline = self.headline_ru
        return self

    @model_serializer(mode="wrap")
    def _serialize_check_result(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data = handler(self)
        if data.get("analyst_details") is None:
            data.pop("analyst_details", None)
        return data


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
    kbe: str = ""
    knp: str = ""
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
    knp: str = ""


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
    label_ru: str = ""
    label_kk: str = ""
    label_en: str = ""
    label_text: str = ""
    total: int
    verdicts: VerdictCounts
    stopped_count: int = 0
    escalated_count: int = 0
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
    stopped_count: int = 0
    escalated_count: int = 0
    stopped_rate: float = 0.0
    escalated_rate: float = 0.0
    legit_stopped_count: int = 0
    legit_escalated_count: int = 0


class HistoryReplayMetrics(BaseModel):
    """Chronological replay of the client's 12-month legitimate payment stream."""

    total_payments: int
    verdicts: VerdictCounts
    stopped_count: int
    escalated_count: int
    alert_count: int
    alert_rate: float


class MetricsResponse(BaseModel):
    """Cached evaluation report returned by GET /api/metrics and scripts/evaluate.py."""

    seed: int
    ruleset_version: str = RULESET_VERSION
    dataset_path: str
    positive_verdicts: list[Verdict] = Field(default_factory=lambda: ["yellow", "red"])
    summary: MetricsSummary
    confusion: ConfusionTable
    verdict_by_label: dict[EvalLabel, VerdictCounts]
    by_kind: list[KindMetrics]
    history_replay: HistoryReplayMetrics
    disclaimer_ru: str
    disclaimer_kk: str = ""
    disclaimer_en: str = ""
    disclaimer: str = ""


class AuditEntry(BaseModel):
    """Privacy-preserving audit trail record (hash and identifiers only; no PII/amounts)."""

    timestamp: str
    check_id: str
    request_sha256: str
    ruleset_version: str
    verdict: Verdict
    signal_ids: list[str]
    action: str
    approval_id: str | None = None
