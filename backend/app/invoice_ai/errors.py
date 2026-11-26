"""Typed errors of the invoice extraction package."""

from __future__ import annotations


class InvoiceAIError(Exception):
    """Base class for invoice extraction errors."""


class ExtractorUnavailable(InvoiceAIError):
    """The Claude extractor cannot be used right now (no SDK/key, refusal, API error).

    quiet marks the expected no-key setup, which is not worth a warning for the user.
    """

    def __init__(self, message: str, *, quiet: bool = False) -> None:
        super().__init__(message)
        self.quiet = quiet


class InvoiceFileError(InvoiceAIError):
    """The uploaded file is unusable (empty, too large, unsupported type)."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code
