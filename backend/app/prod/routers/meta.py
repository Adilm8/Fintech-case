"""Public metadata endpoint for production mode."""

from __future__ import annotations

from fastapi import APIRouter

from app.i18n import DEFAULT_LANG
from app.prod.deps import LangQuery
from app.prod.schemas import MetaResponse
from app.risk.config import RULESET_VERSION

router = APIRouter(tags=["meta"])


@router.get("/meta", response_model=MetaResponse)
def get_meta(lang: LangQuery = DEFAULT_LANG) -> MetaResponse:
    """Return runtime mode and active risk ruleset version."""
    _ = lang
    return MetaResponse(mode="prod", ruleset_version=RULESET_VERSION)
