"""Request and response models of the explain endpoint."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ExplainRequest(BaseModel):
    """A CheckResult-like dict (extra fields are ignored) and the answer language."""

    check: dict[str, Any]
    lang: str = Field(default="ru", max_length=8)


class ExplainResponse(BaseModel):
    """Short explanation text; warnings are machine codes (for example ``rate_limited``)."""

    text: str
    source: Literal["claude", "template"]
    warnings: list[str] = Field(default_factory=list)
