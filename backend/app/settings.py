"""Environment-driven settings for BCC Business Shield backend (stdlib only).

In ``APP_MODE=prod`` session cookies default to ``Secure`` (using the ``__Host-``
cookie prefix). For local plain ``http://localhost`` prod runs you MUST set
``SHIELD_COOKIE_INSECURE=1`` because browsers drop ``Secure`` and ``__Host-``
cookies over plain HTTP.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

AppMode = Literal["demo", "prod"]

BACKEND_DIR: Path = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH: Path = BACKEND_DIR / "var" / "shield.db"
DEFAULT_SESSION_TTL_HOURS: int = 12
DEFAULT_SESSION_IDLE_MINUTES: int = 60

_TRUTHY: frozenset[str] = frozenset({"1", "true", "yes"})
_FALSY: frozenset[str] = frozenset({"0", "false", "no", ""})


@dataclass(frozen=True)
class Settings:
    """Runtime backend configuration parsed from environment variables."""

    app_mode: AppMode = "demo"
    db_path: Path = DEFAULT_DB_PATH
    session_ttl_hours: int = DEFAULT_SESSION_TTL_HOURS
    cookie_secure: bool = False
    today_override: date | None = None
    seed_password: str | None = None
    session_idle_minutes: int = DEFAULT_SESSION_IDLE_MINUTES

    def today(self) -> date:
        """Return effective current date (SHIELD_TODAY if set, else local date.today())."""
        return self.today_override if self.today_override is not None else date.today()


def _parse_app_mode(raw: str | None) -> AppMode:
    if raw is None or not raw.strip():
        return "demo"
    normalized = raw.strip().lower()
    if normalized == "demo":
        return "demo"
    if normalized == "prod":
        return "prod"
    raise ValueError(f"Unknown APP_MODE={raw!r}; expected 'demo' or 'prod'.")


def _parse_positive_int(name: str, raw: str | None, default: int) -> int:
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw.strip())
    except ValueError as exc:
        raise ValueError(f"Invalid integer for {name}={raw!r}.") from exc
    if value <= 0:
        raise ValueError(f"{name} must be > 0, got {value}.")
    return value


def _parse_bool(name: str, raw: str | None, default: bool) -> bool:
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in _TRUTHY:
        return True
    if normalized in _FALSY:
        return False
    raise ValueError(f"Invalid boolean for {name}={raw!r}; expected 0 or 1.")


def _parse_optional_date(name: str, raw: str | None) -> date | None:
    if raw is None or not raw.strip():
        return None
    try:
        return date.fromisoformat(raw.strip())
    except ValueError as exc:
        raise ValueError(f"Invalid ISO date for {name}={raw!r}; expected YYYY-MM-DD.") from exc


def load_settings() -> Settings:
    """Read and validate settings from current process environment variables."""
    app_mode = _parse_app_mode(os.environ.get("APP_MODE"))

    raw_db_path = os.environ.get("SHIELD_DB_PATH", "").strip()
    db_path = Path(raw_db_path).expanduser() if raw_db_path else DEFAULT_DB_PATH

    session_ttl_hours = _parse_positive_int(
        "SHIELD_SESSION_TTL_HOURS",
        os.environ.get("SHIELD_SESSION_TTL_HOURS"),
        DEFAULT_SESSION_TTL_HOURS,
    )
    session_idle_minutes = _parse_positive_int(
        "SHIELD_SESSION_IDLE_MINUTES",
        os.environ.get("SHIELD_SESSION_IDLE_MINUTES"),
        DEFAULT_SESSION_IDLE_MINUTES,
    )

    # SHIELD_COOKIE_INSECURE=1 is REQUIRED for local http://localhost prod runs
    # because browsers drop Secure cookies and __Host- cookies on plain HTTP.
    raw_cookie_insecure = os.environ.get("SHIELD_COOKIE_INSECURE")
    raw_cookie_secure = os.environ.get("SHIELD_COOKIE_SECURE")
    cookie_insecure = _parse_bool("SHIELD_COOKIE_INSECURE", raw_cookie_insecure, False)
    cookie_secure_explicit: bool | None = (
        None
        if raw_cookie_secure is None or not raw_cookie_secure.strip()
        else _parse_bool("SHIELD_COOKIE_SECURE", raw_cookie_secure, False)
    )
    if cookie_insecure and cookie_secure_explicit is True:
        raise ValueError(
            "Conflicting cookie settings: SHIELD_COOKIE_INSECURE=1 cannot be combined "
            "with SHIELD_COOKIE_SECURE=1."
        )
    if cookie_insecure:
        cookie_secure = False
    elif cookie_secure_explicit is not None:
        cookie_secure = cookie_secure_explicit
    else:
        cookie_secure = app_mode == "prod"

    today_override = _parse_optional_date("SHIELD_TODAY", os.environ.get("SHIELD_TODAY"))

    raw_seed_pw = os.environ.get("SHIELD_SEED_PASSWORD")
    seed_password = raw_seed_pw if raw_seed_pw else None

    return Settings(
        app_mode=app_mode,
        db_path=db_path,
        session_ttl_hours=session_ttl_hours,
        cookie_secure=cookie_secure,
        today_override=today_override,
        seed_password=seed_password,
        session_idle_minutes=session_idle_minutes,
    )


settings: Settings = load_settings()
