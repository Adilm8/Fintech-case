"""Pure server-side signing, approval, trust, and permissions policy (§5)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.prod.schemas import (
    PaymentPermissions,
    PaymentStatus,
    ProdApprovalStatus,
    Role,
)
from app.schemas import CheckResult, Verdict, clean_text_field, meaningful_length

# Kept in lockstep with app.main (verified by unit tests).
MIN_DIRECTOR_COMMENT_LEN: int = 10
TRUST_ALLOWED_SIGNAL_IDS: frozenset[str] = frozenset({"iik_changed", "bank_changed"})

VERDICT_RANK: dict[Verdict, int] = {
    "green": 0,
    "grey": 1,
    "yellow": 2,
    "red": 3,
    "invalid": 4,
}

EDITABLE_STATUSES: frozenset[PaymentStatus] = frozenset({"checked", "rejected", "postponed"})
POSTPONABLE_STATUSES: frozenset[PaymentStatus] = frozenset({"checked", "approved"})
CANCELLABLE_STATUSES: frozenset[PaymentStatus] = frozenset(
    {"checked", "rejected", "postponed", "approved"}
)


@dataclass(frozen=True)
class SignDecision:
    """Result of evaluating the §5 server-side signing rule table."""

    allowed: bool
    block_code: str | None = None
    set_accountant_ack: bool = False
    supersede_approval: bool = False


def verdict_rank(verdict: Verdict) -> int:
    """Return numeric severity rank (green < grey < yellow < red < invalid)."""
    return VERDICT_RANK[verdict]


def verdict_worsened(previous: Verdict, fresh: Verdict) -> bool:
    """Return True if the freshly computed verdict is strictly worse than the previous verdict."""
    return VERDICT_RANK[fresh] > VERDICT_RANK[previous]


def can_trust(check: CheckResult) -> bool:
    """Return True if a payment check is eligible for director account trust (mirrors demo)."""
    if check.verdict != "yellow":
        return False
    has_account_change = any(s.rule_id in TRUST_ALLOWED_SIGNAL_IDS for s in check.signals)
    has_block = any(s.severity == "block" for s in check.signals)
    return has_account_change and not has_block


def validate_director_decision(
    *,
    decision: Literal["approved", "rejected"],
    check: CheckResult,
    director_comment: str | None,
    trust_account: bool,
) -> str | None:
    """Validate director approval rules and return a 422 error code or None if valid."""
    if decision != "approved":
        return None

    if check.verdict == "invalid":
        return "invalid_payment_cannot_approve"

    cleaned_comment = clean_text_field(director_comment) if director_comment is not None else ""
    comment_len = meaningful_length(cleaned_comment)

    if trust_account:
        if not can_trust(check):
            return "trust_not_allowed"
        if comment_len < MIN_DIRECTOR_COMMENT_LEN:
            return "trust_comment_required"

    if check.verdict == "red" and comment_len < MIN_DIRECTOR_COMMENT_LEN:
        return "red_comment_required"

    return None


def pre_sign_status_check(status: PaymentStatus) -> str | None:
    """Evaluate rows 1-4 of the §5 sign-rule table before re-running the risk engine."""
    if status == "signed":
        return "already_signed"
    if status in ("postponed", "cancelled"):
        return "not_signable_status"
    if status == "pending_approval":
        return "approval_pending"
    if status == "rejected":
        return "approval_rejected"
    return None


def sign_decision(
    *,
    role: Role,
    status: PaymentStatus,
    previous_verdict: Verdict,
    fresh_verdict: Verdict,
    payment_request_sha256: str,
    approval_status: ProdApprovalStatus | None,
    approval_request_sha256: str | None,
    accountant_ack: bool,
) -> SignDecision:
    """Evaluate all 11 rows of the §5 server-side signing rule table in exact order."""
    # Rows 1-4: non-signable lifecycle statuses
    pre_block = pre_sign_status_check(status)
    if pre_block is not None:
        return SignDecision(allowed=False, block_code=pre_block)

    # Row 5: fresh verdict worsened compared to the verdict used for the previous check/decision
    if verdict_worsened(previous_verdict, fresh_verdict):
        return SignDecision(
            allowed=False,
            block_code="verdict_changed",
            supersede_approval=True,
        )

    # Row 6: invalid requisites can never be signed
    if fresh_verdict == "invalid":
        return SignDecision(allowed=False, block_code="invalid_requisites")

    # Row 7: matching approved director decision for current request_sha256 (any non-invalid verdict)
    has_matching_approval = (
        approval_status == "approved"
        and approval_request_sha256 is not None
        and approval_request_sha256 == payment_request_sha256
    )
    if has_matching_approval:
        return SignDecision(allowed=True)

    # Row 8: green verdict
    if fresh_verdict == "green":
        return SignDecision(allowed=True)

    # Row 9: red verdict without matching approval
    if fresh_verdict == "red":
        return SignDecision(allowed=False, block_code="red_requires_approval")

    # Row 10: yellow or grey with explicit accountant acknowledgement (accountant role only)
    if fresh_verdict in ("yellow", "grey") and accountant_ack and role == "accountant":
        return SignDecision(allowed=True, set_accountant_ack=True)

    # Row 11: otherwise ack or director approval required
    return SignDecision(allowed=False, block_code="ack_or_approval_required")


def permissions_for(
    *,
    role: Role,
    status: PaymentStatus,
    verdict: Verdict,
    payment_request_sha256: str,
    approval_status: ProdApprovalStatus | None = None,
    approval_request_sha256: str | None = None,
) -> PaymentPermissions:
    """Compute server-authoritative UI and API permissions derived from sign_decision()."""
    is_accountant = role == "accountant"
    is_director = role == "director"

    can_edit = is_accountant and status in EDITABLE_STATUSES
    can_send_to_director = is_accountant and status == "checked" and verdict != "invalid"
    can_postpone = is_accountant and status in POSTPONABLE_STATUSES
    can_resume = is_accountant and status == "postponed"
    can_cancel = is_accountant and status in CANCELLABLE_STATUSES
    can_decide = is_director and status == "pending_approval" and approval_status == "pending"

    if role == "analyst":
        return PaymentPermissions(
            can_edit=False,
            can_sign=False,
            sign_requires_ack=False,
            sign_block_code="forbidden_role",
            can_send_to_director=False,
            can_postpone=False,
            can_resume=False,
            can_cancel=False,
            can_decide=False,
        )

    without_ack = sign_decision(
        role=role,
        status=status,
        previous_verdict=verdict,
        fresh_verdict=verdict,
        payment_request_sha256=payment_request_sha256,
        approval_status=approval_status,
        approval_request_sha256=approval_request_sha256,
        accountant_ack=False,
    )
    if without_ack.allowed:
        can_sign = True
        sign_requires_ack = False
        sign_block_code = None
    else:
        with_ack = sign_decision(
            role=role,
            status=status,
            previous_verdict=verdict,
            fresh_verdict=verdict,
            payment_request_sha256=payment_request_sha256,
            approval_status=approval_status,
            approval_request_sha256=approval_request_sha256,
            accountant_ack=True,
        )
        if with_ack.allowed:
            can_sign = True
            sign_requires_ack = True
            sign_block_code = None
        else:
            can_sign = False
            sign_requires_ack = False
            sign_block_code = without_ack.block_code

    return PaymentPermissions(
        can_edit=can_edit,
        can_sign=can_sign,
        sign_requires_ack=sign_requires_ack,
        sign_block_code=sign_block_code,
        can_send_to_director=can_send_to_director,
        can_postpone=can_postpone,
        can_resume=can_resume,
        can_cancel=can_cancel,
        can_decide=can_decide,
    )
