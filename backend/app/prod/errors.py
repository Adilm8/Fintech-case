"""Structured localized error definitions for production API endpoints."""

from __future__ import annotations

from typing import Any

from app.i18n import DEFAULT_LANG, MESSAGES, Lang

PROD_ERROR_CODES: frozenset[str] = frozenset(
    {
        "not_authenticated",
        "invalid_credentials",
        "forbidden_role",
        "csrf_header_missing",
        "not_found",
        "already_signed",
        "not_signable_status",
        "approval_pending",
        "approval_rejected",
        "verdict_changed",
        "invalid_requisites",
        "red_requires_approval",
        "identity_requires_approval",
        "ack_or_approval_required",
        "not_editable",
        "invalid_transition",
        "approval_already_decided",
        "approval_superseded",
        "duplicate_file",
        "file_too_large",
        "validation_error",
        "unsupported_file",
        "empty_file",
        "red_comment_required",
        "trust_comment_required",
        "trust_not_allowed",
        "invalid_payment_cannot_approve",
        "too_many_attempts",
        "internal_error",
        "invalid_current_password",
        "password_same_as_current",
        "login_already_exists",
        "last_director_protected",
        "threshold_requires_approval",
        "invalid_date_range",
        "pdf_unavailable",
        "document_mismatch",
        "signature_verification_unavailable",
        "approval_required_after_rejection",
        "threshold_aggregate",
        "duplicate_requires_approval",
        "invalid_login",
        "password_change_required",
    }
)


def localize_prod_error(code: str, lang: Lang = DEFAULT_LANG, **params: Any) -> str:
    """Resolve a localized message for a prod API error code from app.i18n.MESSAGES."""
    entry = MESSAGES.get(f"error.prod.{code}")
    if entry is None:
        entry = MESSAGES.get(f"error.{code}")
    if entry is not None:
        template = entry[lang]
        return template.format(**params) if params else template
    return code


class ProdError(Exception):
    """Domain/HTTP error rendered as {'detail': ..., 'code': ..., **extra}."""

    def __init__(
        self,
        status_code: int,
        code: str,
        *,
        detail: str | None = None,
        params: dict[str, Any] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(detail or code)
        self.status_code = status_code
        self.code = code
        self.detail = detail
        self.params = params or {}
        self.extra = extra or {}

    def to_payload(self, lang: Lang = DEFAULT_LANG) -> dict[str, Any]:
        """Serialize error payload with localized detail and machine-readable code."""
        message = (
            self.detail
            if self.detail is not None
            else localize_prod_error(self.code, lang, **self.params)
        )
        payload: dict[str, Any] = {"detail": message, "code": self.code}
        if self.extra:
            payload.update(self.extra)
        return payload
