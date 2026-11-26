"""Lossless serialization for CheckResult preserving exclude=True fields."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel

from app.schemas import CheckResult


def _dump_value(value: Any) -> Any:
    """Recursively convert Pydantic models using all model_fields (including exclude=True)."""
    if isinstance(value, BaseModel):
        return {
            field_name: _dump_value(getattr(value, field_name))
            for field_name in type(value).model_fields
        }
    if isinstance(value, list):
        return [_dump_value(item) for item in value]
    if isinstance(value, tuple):
        return [_dump_value(item) for item in value]
    if isinstance(value, dict):
        return {str(k): _dump_value(v) for k, v in value.items()}
    return value


def dump_full_dict(result: CheckResult) -> dict[str, Any]:
    """Dump CheckResult to a dict including all exclude=True i18n and analyst fields."""
    dumped = _dump_value(result)
    assert isinstance(dumped, dict)
    return dumped


def dump_full(result: CheckResult) -> str:
    """Serialize CheckResult to compact JSON preserving exclude=True fields for DB storage."""
    return json.dumps(dump_full_dict(result), ensure_ascii=False, separators=(",", ":"))


def load_check_result(raw: str | bytes | dict[str, Any]) -> CheckResult:
    """Restore CheckResult from dump_full JSON (or dict), keeping exclude=True fields intact."""
    data = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
    return CheckResult.model_validate(data)
