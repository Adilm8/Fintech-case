"""Pydantic model of the fields extracted from a supplier invoice."""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class InvoiceExtraction(BaseModel):
    """Payment fields read from a Kazakhstan «счёт на оплату».

    Also used as the structured-output schema for the model, so every field is optional:
    an absent field must stay null instead of being guessed.
    """

    model_config = ConfigDict(extra="ignore")

    recipient_name: str | None = Field(
        default=None, description="Supplier (payee) legal name, e.g. ТОО «Название»; null if absent"
    )
    recipient_bin: str | None = Field(
        default=None, description="Supplier BIN/IIN: exactly 12 digits, no spaces; null if absent"
    )
    recipient_iik: str | None = Field(
        default=None,
        description="Supplier account number (ИИК/IBAN): KZ + 18 chars, uppercase, no spaces",
    )
    recipient_bik: str | None = Field(
        default=None, description="Bank BIK/SWIFT of the supplier bank: 8 letters, e.g. KCJBKZKX"
    )
    amount_kzt: float | None = Field(
        default=None,
        description="Total amount to pay as a plain number (no spaces); null if absent",
    )
    purpose: str | None = Field(default=None, description="Payment purpose (назначение платежа)")
    invoice_number: str | None = Field(default=None, description="Invoice number without «№»")
    invoice_date: str | None = Field(default=None, description="Invoice date as YYYY-MM-DD")
    kbe: str | None = Field(default=None, description="КБе code, 2 digits")
    knp: str | None = Field(default=None, description="КНП payment purpose code, 3 digits")
    currency: str | None = Field(default=None, description="ISO currency code, e.g. KZT")
    confidence: float = Field(
        default=0.0, description="Extraction confidence from 0 to 1 (1 = every field is clear)"
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Short Russian notes about missing, unreadable or suspicious fields",
    )
    source: Literal["claude", "text_rules", "none"] = Field(
        default="none", description="Which extractor produced the values"
    )

    @field_validator("confidence", mode="after")
    @classmethod
    def _clamp_confidence(cls, value: float) -> float:
        if not math.isfinite(value):
            return 0.0
        return min(1.0, max(0.0, value))

    @field_validator("amount_kzt", mode="after")
    @classmethod
    def _finite_amount(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            return None
        return value
