"""Pydantic schemas for production API endpoints (§6.2 contract)."""

from __future__ import annotations

import math
import re
from datetime import date
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, Field, field_validator

from app.i18n import Lang
from app.schemas import (
    CheckRequest,
    CheckResult,
    Verdict,
    VerdictCounts,
    clean_text_field,
    meaningful_length,
    normalize_requisite,
)

Role = Literal["accountant", "director", "analyst"]
PaymentStatus = Literal[
    "checked",
    "pending_approval",
    "approved",
    "rejected",
    "postponed",
    "signed",
    "cancelled",
]
PaymentSource = Literal["manual", "1c", "csv", "seed"]
ProdApprovalStatus = Literal["pending", "approved", "rejected", "superseded"]
PaymentScope = Literal["queue", "signed", "all"]

ALL_PAYMENT_STATUSES: tuple[PaymentStatus, ...] = (
    "checked",
    "pending_approval",
    "approved",
    "rejected",
    "postponed",
    "signed",
    "cancelled",
)


class MetaResponse(BaseModel):
    """Response payload for GET /api/v1/meta."""

    mode: Literal["prod"] = "prod"
    ruleset_version: str


class User(BaseModel):
    """Authenticated user details returned in session payloads."""

    id: int
    login: str
    full_name: str
    role: Role
    company_id: str | None


class UserBrief(BaseModel):
    """Compact user reference embedded in payments, batches, and approvals."""

    id: int
    login: str
    full_name: str
    role: Role


class Company(BaseModel):
    """SME client company profile."""

    id: str
    name: str
    bin: str
    iik: str
    bik: str


class Session(BaseModel):
    """Active user session details."""

    user: User
    company: Company | None


class LoginRequest(BaseModel):
    """Credentials payload for POST /api/v1/auth/login."""

    login: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=256)


class PaymentInput(BaseModel):
    """Create / update payment request body (§6.2). Never accepts payer_id."""

    recipient_name: str = Field(min_length=1, max_length=250)
    recipient_bin: str = Field(max_length=64)
    recipient_iik: str = Field(max_length=64)
    recipient_bik: str = Field(max_length=64)
    amount_kzt: float = Field(gt=0, le=1e12, allow_inf_nan=False)
    purpose: str = Field(default="", max_length=500)
    kbe: str = Field(default="", max_length=10)
    knp: str = Field(default="", max_length=10)
    doc_number: str = Field(default="", max_length=64)
    doc_date: str | None = Field(default=None, max_length=10)

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
    def _validate_amount(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("Сумма платежа должна быть конечным числом.")
        if round(value * 100) <= 0:
            raise ValueError("Сумма платежа должна быть не менее 0.01 ₸.")
        return value

    @field_validator("doc_number")
    @classmethod
    def _clean_doc_number(cls, value: str) -> str:
        return clean_text_field(value)

    @field_validator("doc_date")
    @classmethod
    def _validate_doc_date(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = clean_text_field(value)
        if not cleaned:
            return None
        try:
            parsed = date.fromisoformat(cleaned)
        except ValueError as exc:
            raise ValueError("Дата документа должна быть в формате ГГГГ-ММ-ДД.") from exc
        return parsed.isoformat()

    def to_check_request(self, *, payer_id: str) -> CheckRequest:
        """Convert into a canonical CheckRequest scoped to the authenticated company."""
        return CheckRequest(
            payer_id=payer_id,
            recipient_name=self.recipient_name,
            recipient_bin=self.recipient_bin,
            recipient_iik=self.recipient_iik,
            recipient_bik=self.recipient_bik,
            amount_kzt=self.amount_kzt,
            purpose=self.purpose,
            kbe=self.kbe,
            knp=self.knp,
        )


class SendToDirectorRequest(BaseModel):
    """Request body for POST /api/v1/payments/{id}/send-to-director."""

    accountant_note: str = Field(default="", max_length=1000)


class PaymentNoteRequest(BaseModel):
    """Optional note body for POST /postpone and POST /cancel."""

    note: str = Field(default="", max_length=1000)


class SignPaymentRequest(BaseModel):
    """Optional body for POST /api/v1/payments/{id}/sign."""

    accountant_ack: bool = False


class ProdApprovalDecisionRequest(BaseModel):
    """Director decision payload for POST /api/v1/approvals/{id}/decision."""

    decision: Literal["approved", "rejected"]
    director_comment: str | None = Field(default=None, max_length=1000)
    trust_account: bool = False


class ProdApproval(BaseModel):
    """Full approval resource returned by /api/v1/approvals endpoints (§6.2 Approval)."""

    id: str
    payment_id: str
    request: CheckRequest
    check: CheckResult
    status: ProdApprovalStatus
    accountant_note: str
    director_comment: str | None = None
    trust_account: bool = False
    can_trust: bool = False
    created_by: UserBrief
    created_at: str
    decided_by: UserBrief | None = None
    decided_at: str | None = None


class PaymentPermissions(BaseModel):
    """Server-computed action permissions for the current user and payment state."""

    can_edit: bool
    can_sign: bool
    sign_requires_ack: bool
    sign_block_code: str | None
    can_send_to_director: bool
    can_postpone: bool
    can_resume: bool
    can_cancel: bool
    can_decide: bool


class ApprovalBrief(BaseModel):
    """Compact approval summary embedded inside a Payment response."""

    id: str
    status: ProdApprovalStatus
    accountant_note: str
    director_comment: str | None = None
    trust_account: bool = False
    created_by: UserBrief
    created_at: str
    decided_by: UserBrief | None = None
    decided_at: str | None = None


class SupplierRef(BaseModel):
    """Confirmed supplier directory status for a payment's recipient."""

    id: int | None
    known: bool
    account_known: bool
    requisites_changed_days_ago: int | None


class Payment(BaseModel):
    """Full payment resource returned by /api/v1/payments endpoints."""

    id: str
    company_id: str
    status: PaymentStatus
    source: PaymentSource
    batch_id: str | None = None
    line_no: int | None = None
    doc_number: str = ""
    doc_date: str | None = None
    request: CheckRequest
    check: CheckResult
    approval: ApprovalBrief | None = None
    accountant_ack: bool = False
    supplier: SupplierRef
    duplicate_of: str | None = None
    permissions: PaymentPermissions
    created_by: UserBrief
    created_at: str
    updated_at: str
    signed_by: UserBrief | None = None
    signed_at: str | None = None


class PaymentCounts(BaseModel):
    """Aggregate status and verdict counters across the active scope (unpaginated)."""

    by_status: dict[PaymentStatus, int]
    by_verdict: VerdictCounts


class PaymentList(BaseModel):
    """Paginated payment list with full-scope status and verdict counters."""

    items: list[Payment]
    total: int
    counts: PaymentCounts


ImportSource = Literal["1c", "csv"]
ImportFormat = Literal["auto", "1c", "csv"]


class Batch(BaseModel):
    """Import batch metadata returned by GET /api/v1/batches and ImportResult."""

    id: str
    source: ImportSource
    filename: str
    total: int
    created_count: int
    failed_count: int
    created_by: UserBrief
    created_at: str


class ImportLineError(BaseModel):
    """Row- or document-level warning/error collected during file import."""

    line_no: int | None = None
    doc_number: str | None = None
    code: str
    message: str


class ImportSummary(BaseModel):
    """Aggregate outcome summary for a completed file import."""

    total: int
    created: int
    failed: int
    duplicates: int
    by_verdict: VerdictCounts


class ImportResult(BaseModel):
    """Response payload for POST /api/v1/payments/import (§6.2)."""

    batch: Batch
    items: list[Payment]
    errors: list[ImportLineError]
    summary: ImportSummary


class BatchSignGreenRequest(BaseModel):
    """Optional scope body for POST /api/v1/payments/batch/sign-green."""

    batch_id: str | None = Field(default=None, max_length=64)
    payment_ids: list[str] | None = None


class BatchSendToDirectorRequest(BaseModel):
    """Optional scope and note body for POST /api/v1/payments/batch/send-to-director."""

    batch_id: str | None = Field(default=None, max_length=64)
    payment_ids: list[str] | None = None
    accountant_note: str = Field(default="", max_length=1000)


class BatchSkippedItem(BaseModel):
    """Entry describing why a payment was skipped during a batch operation."""

    id: str
    code: str
    detail: str


class BatchActionResult(BaseModel):
    """Response payload for batch signing and batch approval submission (§6.2)."""

    done: list[Payment]
    skipped: list[BatchSkippedItem]


SupplierChangeKind = Literal["account_added", "bank_changed", "name_changed"]


class Supplier(BaseModel):
    """Confirmed supplier directory summary (§6.2)."""

    id: int
    bin: str
    name: str
    first_seen_at: str
    last_payment_at: str | None = None
    payments_count: int
    total_paid_kzt: float
    accounts_count: int
    requisites_changed_at: str | None = None
    requisites_changed_days_ago: int | None = None
    has_pending_change: bool
    trusted_accounts_count: int


class SupplierAccount(BaseModel):
    """Confirmed supplier bank account with bank name and director trust status (§6.2)."""

    id: int
    iik: str
    bik: str
    bank_name: str | None = None
    first_seen_at: str
    last_used_at: str
    payments_count: int
    trusted: bool
    trusted_at: str | None = None
    trusted_comment: str | None = None


class SupplierChange(BaseModel):
    """Immutable supplier requisite or name change event (§6.2)."""

    id: int
    kind: SupplierChangeKind
    old_value: str | None = None
    new_value: str
    occurred_at: str
    payment_id: str | None = None


class SupplierDetail(Supplier):
    """Supplier card with accounts, chronological changes (newest first), and latest 50 payments."""

    accounts: list[SupplierAccount]
    changes: list[SupplierChange]
    payments: list[Payment]


class UntrustAccountRequest(BaseModel):
    """Director comment payload for revoking account trust (§6.3)."""

    comment: str = Field(min_length=1, max_length=1000)


class AuditUser(BaseModel):
    """Compact user info stored on an audit log entry."""

    id: int
    login: str
    role: Role


class AuditEntry(BaseModel):
    """Tamper-evident audit log entry returned by GET /api/v1/audit."""

    id: int
    timestamp: str
    user: AuditUser | None = None
    action: str
    payment_id: str | None = None
    approval_id: str | None = None
    check_id: str | None = None
    batch_id: str | None = None
    request_sha256: str | None = None
    ruleset_version: str | None = None
    verdict: Verdict | None = None
    signal_ids: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)
    entry_hash: str


class AuditVerifyResult(BaseModel):
    """Integrity verification summary returned by GET /api/v1/audit/verify."""

    ok: bool
    checked: int
    broken_at: int | None = None


CompanyRole = Literal["accountant", "director"]
NotifyOn = Literal["red", "red_yellow"]
ExportFormat = Literal["csv", "pdf"]
NotificationKind = Literal[
    "approval_pending",
    "approval_approved",
    "approval_rejected",
    "sign_denied",
]

_LOGIN_RE = re.compile(r"^[A-Za-z0-9._-]+$")


class UserProfile(BaseModel):
    """Full user profile returned by GET/PUT /api/v1/me."""

    id: int
    login: str
    full_name: str
    role: Role
    company_id: str | None
    default_lang: Lang = "ru"
    company: Company | None = None


class UpdateProfileRequest(BaseModel):
    """Update current user profile payload for PUT /api/v1/me."""

    full_name: str | None = Field(default=None, min_length=1, max_length=120)
    default_lang: Lang | None = None

    @field_validator("full_name")
    @classmethod
    def _clean_full_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = clean_text_field(value)
        if not cleaned or meaningful_length(cleaned) == 0:
            raise ValueError("Укажите имя и фамилию.")
        return cleaned


class ChangePasswordRequest(BaseModel):
    """Password change payload for POST /api/v1/me/password."""

    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=8, max_length=256)


class PasswordChangeResponse(BaseModel):
    """Response payload for POST /api/v1/me/password."""

    ok: bool = True
    revoked_sessions: int


class CompanyUser(BaseModel):
    """Company member details returned under GET /api/v1/company."""

    id: int
    login: str
    full_name: str
    role: CompanyRole
    is_active: bool
    default_lang: Lang = "ru"
    created_at: str


class CompanyDetail(BaseModel):
    """Company profile with users list returned by GET /api/v1/company."""

    id: str
    name: str
    bin: str
    iik: str
    bik: str
    created_at: str
    users: list[CompanyUser]


class InviteUserRequest(BaseModel):
    """Director invite payload for POST /api/v1/company/users."""

    login: str = Field(min_length=3, max_length=64)
    full_name: str = Field(min_length=1, max_length=120)
    role: CompanyRole

    @field_validator("login")
    @classmethod
    def _validate_login(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned or not _LOGIN_RE.match(cleaned):
            raise ValueError(
                "Логин может содержать только латинские буквы, цифры, точку, дефис и подчёркивание."
            )
        return cleaned

    @field_validator("full_name")
    @classmethod
    def _validate_full_name(cls, value: str) -> str:
        cleaned = clean_text_field(value)
        if not cleaned or meaningful_length(cleaned) == 0:
            raise ValueError("Укажите имя и фамилию.")
        return cleaned


class InviteUserResponse(BaseModel):
    """Response for POST /api/v1/company/users returning temporary_password once."""

    user: CompanyUser
    temporary_password: str


class UpdateCompanyUserRequest(BaseModel):
    """Director update payload for PUT /api/v1/company/users/{id}."""

    role: CompanyRole | None = None
    is_active: bool | None = Field(
        default=None,
        validation_alias=AliasChoices("is_active", "active"),
    )


class CompanySettings(BaseModel):
    """Company notification and approval threshold policy (GET/PUT /api/v1/company/settings)."""

    notify_on: NotifyOn = "red_yellow"
    approval_threshold_kzt: float | None = None
    updated_at: str | None = None


class UpdateCompanySettingsRequest(BaseModel):
    """Director update payload for PUT /api/v1/company/settings."""

    notify_on: NotifyOn | None = None
    approval_threshold_kzt: float | None = Field(
        default=None,
        gt=0,
        le=1e12,
        allow_inf_nan=False,
    )

    @field_validator("approval_threshold_kzt")
    @classmethod
    def _validate_threshold(cls, value: float | None) -> float | None:
        if value is None:
            return None
        if not math.isfinite(value):
            raise ValueError("Порог согласования должен быть конечным числом.")
        if round(value * 100) <= 0:
            raise ValueError("Порог согласования должен быть не менее 0.01 ₸.")
        return value


class NotificationItem(BaseModel):
    """Server-derived notification item for GET /api/v1/notifications."""

    id: str
    kind: NotificationKind
    title: str
    message: str
    created_at: str
    read: bool
    payment_id: str | None = None
    approval_id: str | None = None
    verdict: Verdict | None = None
    recipient_name: str | None = None
    amount_kzt: float | None = None
    link: str | None = None


class NotificationList(BaseModel):
    """Response payload for GET /api/v1/notifications."""

    unread_count: int
    items: list[NotificationItem]


class MarkNotificationsReadRequest(BaseModel):
    """Optional request body for POST /api/v1/notifications/read."""

    ids: list[str] | None = Field(
        default=None,
        validation_alias=AliasChoices("ids", "notification_ids"),
    )


class MarkNotificationsReadResponse(BaseModel):
    """Response payload for POST /api/v1/notifications/read."""

    marked: int
    unread_count: int
