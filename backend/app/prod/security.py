"""Password hashing (scrypt), session tokens, and in-memory login rate limiting."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import threading
import time
from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime

SCRYPT_LOG_N: int = 15
SCRYPT_R: int = 8
SCRYPT_P: int = 1
SCRYPT_SALT_BYTES: int = 16
SCRYPT_DKLEN: int = 32
SCRYPT_MAXMEM: int = 64 * 1024 * 1024

SESSION_COOKIE_NAME: str = "shield_session"
LOGIN_MAX_FAILURES: int = 5
LOGIN_WINDOW_SECONDS: float = 15 * 60.0

_dummy_hash_lock = threading.Lock()
_dummy_hash_value: str | None = None


def utc_now() -> datetime:
    """Return current UTC datetime with whole-second precision."""
    return datetime.now(UTC).replace(microsecond=0)


def utc_now_iso() -> str:
    """Return current UTC timestamp formatted as ISO 8601."""
    return utc_now().isoformat()


def hash_password(
    password: str,
    *,
    log_n: int = SCRYPT_LOG_N,
    r: int = SCRYPT_R,
    p: int = SCRYPT_P,
) -> str:
    """Hash a password using stdlib hashlib.scrypt into scrypt$log_n$r$p$salt_b64$hash_b64."""
    salt = secrets.token_bytes(SCRYPT_SALT_BYTES)
    dk = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=1 << log_n,
        r=r,
        p=p,
        maxmem=SCRYPT_MAXMEM,
        dklen=SCRYPT_DKLEN,
    )
    salt_b64 = base64.b64encode(salt).decode("ascii")
    dk_b64 = base64.b64encode(dk).decode("ascii")
    return f"scrypt${log_n}${r}${p}${salt_b64}${dk_b64}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a plaintext password against a stored scrypt hash using constant-time compare."""
    parts = stored_hash.split("$")
    if len(parts) != 6 or parts[0] != "scrypt":
        return False
    try:
        log_n = int(parts[1])
        r = int(parts[2])
        p = int(parts[3])
        if not (1 <= log_n <= 20 and 1 <= r <= 32 and 1 <= p <= 16):
            return False
        salt = base64.b64decode(parts[4].encode("ascii"), validate=True)
        expected = base64.b64decode(parts[5].encode("ascii"), validate=True)
    except (ValueError, UnicodeEncodeError):
        return False
    if not salt or not expected:
        return False

    try:
        derived = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=1 << log_n,
            r=r,
            p=p,
            maxmem=SCRYPT_MAXMEM,
            dklen=len(expected),
        )
    except ValueError:
        return False
    return hmac.compare_digest(derived, expected)


def _get_dummy_hash() -> str:
    global _dummy_hash_value
    if _dummy_hash_value is None:
        with _dummy_hash_lock:
            if _dummy_hash_value is None:
                _dummy_hash_value = hash_password(secrets.token_hex(16))
    return _dummy_hash_value


def verify_dummy_password(password: str) -> None:
    """Execute scrypt work matching a real check so unknown logins take equal time."""
    verify_password(password, _get_dummy_hash())


def generate_session_token() -> str:
    """Generate a cryptographically secure opaque session token for the cookie."""
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    """Return hex SHA-256 digest of a raw session token for database storage."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class LoginRateLimiter:
    """In-memory per-login sliding-window rate limiter (5 failures per 15 minutes)."""

    def __init__(
        self,
        *,
        max_failures: int = LOGIN_MAX_FAILURES,
        window_seconds: float = LOGIN_WINDOW_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._failures: dict[str, deque[float]] = {}

    @staticmethod
    def _normalize(login: str) -> str:
        return login.strip().lower()

    def _prune_locked(self, key: str, now: float) -> deque[float]:
        events = self._failures.get(key)
        if events is None:
            return deque()
        cutoff = now - self.window_seconds
        while events and events[0] <= cutoff:
            events.popleft()
        if not events:
            self._failures.pop(key, None)
        return events

    def is_blocked(self, login: str) -> bool:
        """Return True if login has reached the failed-attempt threshold in the active window."""
        key = self._normalize(login)
        with self._lock:
            now = self._clock()
            events = self._prune_locked(key, now)
            return len(events) >= self.max_failures

    def record_failure(self, login: str) -> int:
        """Record a failed login attempt and return the current failure count in the window."""
        key = self._normalize(login)
        with self._lock:
            now = self._clock()
            events = self._prune_locked(key, now)
            if not events:
                events = deque()
                self._failures[key] = events
            events.append(now)
            return len(events)

    def reset_login(self, login: str) -> None:
        """Clear failed attempts for login after a successful authentication."""
        key = self._normalize(login)
        with self._lock:
            self._failures.pop(key, None)

    def clear(self) -> None:
        """Clear all tracked login attempts."""
        with self._lock:
            self._failures.clear()
