"""Shared pytest fixtures ensuring tests never write to the live data/audit.jsonl."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest

from app.store import store


@pytest.fixture(autouse=True)
def _isolate_audit_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[None]:
    monkeypatch.setattr(store, "audit_log_path", tmp_path / "audit.jsonl")
    yield
