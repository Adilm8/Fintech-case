"""Password hashing (scrypt), session tokens/expiry, and in-memory login rate limiting."""

from __future__ import annotations

import base64
import hashlib
import hmac
import math
import secrets
import sqlite3
import threading
import time
from collections import OrderedDict, deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

SCRYPT_LOG_N: int = 15
SCRYPT_R: int = 8
SCRYPT_P: int = 1
SCRYPT_SALT_BYTES: int = 16
SCRYPT_DKLEN: int = 32
SCRYPT_MAXMEM: int = 64 * 1024 * 1024
SCRYPT_MAX_CONCURRENT: int = 4

SESSION_COOKIE_NAME: str = "shield_session"
SECURE_SESSION_COOKIE_NAME: str = "__Host-shield_session"
LOGIN_MAX_FAILURES: int = 5
LOGIN_WINDOW_SECONDS: float = 15 * 60.0
LOGIN_MAX_DELAY_SECONDS: float = 30.0
LOGIN_IP_MAX_FAILURES: int = 20
LOGIN_MAX_TRACKED_KEYS: int = 10_000
LOGIN_KEY_MAX_LEN: int = 64
UNKNOWN_AUDIT_WINDOW_SECONDS: float = 5 * 60.0
UNKNOWN_AUDIT_MAX_IPS: int = 10_000
UNKNOWN_AUDIT_LOGIN_MAX_LEN: int = 32

_scrypt_semaphore = threading.BoundedSemaphore(SCRYPT_MAX_CONCURRENT)
_dummy_hash_lock = threading.Lock()
_dummy_hash_value: str | None = None


def utc_now() -> datetime:
    """Return current UTC datetime with whole-second precision."""
    return datetime.now(UTC).replace(microsecond=0)


def utc_now_iso() -> str:
    """Return current UTC timestamp formatted as ISO 8601."""
    return utc_now().isoformat()


def _coerce_utc(value: str | datetime) -> datetime:
    parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def hash_password(
    password: str,
    *,
    log_n: int = SCRYPT_LOG_N,
    r: int = SCRYPT_R,
    p: int = SCRYPT_P,
) -> str:
    """Hash a password using stdlib hashlib.scrypt into scrypt$log_n$r$p$salt_b64$hash_b64."""
    salt = secrets.token_bytes(SCRYPT_SALT_BYTES)
    _scrypt_semaphore.acquire()
    try:
        dk = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=1 << log_n,
            r=r,
            p=p,
            maxmem=SCRYPT_MAXMEM,
            dklen=SCRYPT_DKLEN,
        )
    finally:
        _scrypt_semaphore.release()
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
        _scrypt_semaphore.acquire()
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
        finally:
            _scrypt_semaphore.release()
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


def session_cookie_name(secure: bool) -> str:
    """Return __Host- prefixed cookie name when Secure cookies are active, else plain name."""
    return SECURE_SESSION_COOKIE_NAME if secure else SESSION_COOKIE_NAME


def read_session_token(cookies: Mapping[str, str], secure: bool) -> str | None:
    """Read the session token strictly from the cookie matching the configured security mode."""
    value = cookies.get(session_cookie_name(secure))
    return value if value else None


def session_expiry(
    created_at: datetime,
    now: datetime,
    *,
    ttl_seconds: int,
    idle_seconds: int,
) -> datetime:
    """Compute sliding session deadline capped by both absolute TTL and idle timeout."""
    created_utc = _coerce_utc(created_at)
    now_utc = _coerce_utc(now)
    absolute_deadline = created_utc + timedelta(seconds=ttl_seconds)
    idle_deadline = now_utc + timedelta(seconds=idle_seconds)
    return min(absolute_deadline, idle_deadline)


def slide_session_expiry(
    conn: sqlite3.Connection,
    *,
    token_hash: str,
    created_at: str | datetime,
    expires_at: str | datetime,
    ttl_seconds: int,
    idle_seconds: int,
    now: datetime | None = None,
    min_step_seconds: int = 60,
) -> datetime:
    """Extend sessions.expires_at when throttled step elapsed, capped at created_at + ttl."""
    current_time = _coerce_utc(now) if now is not None else utc_now()
    created_dt = _coerce_utc(created_at)
    stored_expires_dt = _coerce_utc(expires_at)
    new_deadline = session_expiry(
        created_dt,
        current_time,
        ttl_seconds=ttl_seconds,
        idle_seconds=idle_seconds,
    )
    if new_deadline <= stored_expires_dt:
        return stored_expires_dt
    if new_deadline - stored_expires_dt < timedelta(seconds=min_step_seconds):
        return stored_expires_dt

    try:
        if getattr(conn, "isolation_level", None) is None:
            conn.execute(
                "UPDATE sessions SET expires_at = ? WHERE token_hash = ? AND revoked_at IS NULL",
                (new_deadline.isoformat(), token_hash),
            )
        else:
            with conn:
                conn.execute(
                    "UPDATE sessions SET expires_at = ? "
                    "WHERE token_hash = ? AND revoked_at IS NULL",
                    (new_deadline.isoformat(), token_hash),
                )
    except sqlite3.OperationalError:
        return stored_expires_dt
    return new_deadline


@dataclass
class _UnknownLoginBucket:
    started_at: float
    count: int
    last_login: str


class UnknownLoginAuditAggregator:
    """Thread-safe per-IP aggregator bounding unknown-login rows in append-only audit_log."""

    def __init__(
        self,
        *,
        window_seconds: float = UNKNOWN_AUDIT_WINDOW_SECONDS,
        max_tracked_ips: int = UNKNOWN_AUDIT_MAX_IPS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.window_seconds = window_seconds
        self.max_tracked_ips = max(1, max_tracked_ips)
        self._clock = clock
        self._lock = threading.Lock()
        self._buckets: OrderedDict[str, _UnknownLoginBucket] = OrderedDict()

    @staticmethod
    def _normalize_ip(ip: str) -> str:
        cleaned = ip.strip()[:LOGIN_KEY_MAX_LEN]
        return cleaned if cleaned else "unknown"

    @staticmethod
    def _truncate_login(login: str) -> str:
        return login.strip()[:UNKNOWN_AUDIT_LOGIN_MAX_LEN]

    def _flush_expired_locked(self, now: float) -> list[dict[str, Any]]:
        emitted: list[dict[str, Any]] = []
        expired_keys: list[str] = []
        for ip, bucket in self._buckets.items():
            if now - bucket.started_at >= self.window_seconds:
                expired_keys.append(ip)
            else:
                break
        for ip in expired_keys:
            bucket = self._buckets.pop(ip)
            if bucket.count > 1:
                emitted.append(
                    {
                        "ip": ip,
                        "count": bucket.count,
                        "login": bucket.last_login,
                        "aggregated": True,
                    }
                )
        return emitted

    def flush_expired(self) -> list[dict[str, Any]]:
        """Flush expired IP buckets with suppressed attempts and return summary payloads."""
        with self._lock:
            now = self._clock()
            return self._flush_expired_locked(now)

    def note(self, ip: str, login: str) -> list[dict[str, Any]]:
        """Record an unknown-login failure and return audit payloads to persist immediately."""
        norm_ip = self._normalize_ip(ip)
        short_login = self._truncate_login(login)
        with self._lock:
            now = self._clock()
            emitted = self._flush_expired_locked(now)

            existing = self._buckets.get(norm_ip)
            if existing is not None:
                existing.count += 1
                existing.last_login = short_login
                return emitted

            while len(self._buckets) >= self.max_tracked_ips:
                old_ip, old_bucket = self._buckets.popitem(last=False)
                if old_bucket.count > 1:
                    emitted.append(
                        {
                            "ip": old_ip,
                            "count": old_bucket.count,
                            "login": old_bucket.last_login,
                            "aggregated": True,
                        }
                    )

            self._buckets[norm_ip] = _UnknownLoginBucket(
                started_at=now,
                count=1,
                last_login=short_login,
            )
            emitted.append(
                {
                    "ip": norm_ip,
                    "count": 1,
                    "login": short_login,
                    "aggregated": False,
                }
            )
            return emitted

    def clear(self) -> None:
        """Clear all tracked unknown-login audit buckets."""
        with self._lock:
            self._buckets.clear()


class LoginRateLimiter:
    """In-memory progressive-delay per-login and sliding-window per-IP rate limiter."""

    def __init__(
        self,
        *,
        max_failures: int = LOGIN_MAX_FAILURES,
        window_seconds: float = LOGIN_WINDOW_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        ip_max_failures: int = LOGIN_IP_MAX_FAILURES,
        max_delay_seconds: float = LOGIN_MAX_DELAY_SECONDS,
        max_tracked_keys: int = LOGIN_MAX_TRACKED_KEYS,
    ) -> None:
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self.ip_max_failures = ip_max_failures
        self.max_delay_seconds = max_delay_seconds
        self.max_tracked_keys = max(1, max_tracked_keys)
        self._clock = clock
        self._lock = threading.Lock()
        self._failures: OrderedDict[str, deque[float]] = OrderedDict()
        self._ip_failures: OrderedDict[str, deque[float]] = OrderedDict()
        self._unknown_audit: UnknownLoginAuditAggregator | None = None

    @property
    def unknown_audit(self) -> UnknownLoginAuditAggregator:
        """Lazily attach an UnknownLoginAuditAggregator sharing this limiter's clock."""
        with self._lock:
            if self._unknown_audit is None:
                self._unknown_audit = UnknownLoginAuditAggregator(clock=self._clock)
            return self._unknown_audit

    @staticmethod
    def _normalize(login: str) -> str:
        return login.strip().lower()[:LOGIN_KEY_MAX_LEN]

    @staticmethod
    def _normalize_ip(ip: str) -> str:
        cleaned = ip.strip().lower()[:LOGIN_KEY_MAX_LEN]
        return cleaned if cleaned else "unknown"

    def _delay_for_count(self, count: int) -> float:
        if count < self.max_failures:
            return 0.0
        exponent = min(count - self.max_failures + 1, 10)
        return min(self.max_delay_seconds, float(1 << exponent))

    def _prune_key_locked(
        self,
        store: OrderedDict[str, deque[float]],
        key: str,
        now: float,
    ) -> deque[float]:
        events = store.get(key)
        if events is None:
            return deque()
        cutoff = now - self.window_seconds
        while events and events[0] <= cutoff:
            events.popleft()
        if not events:
            store.pop(key, None)
        return events

    def _enforce_cap_locked(
        self,
        store: OrderedDict[str, deque[float]],
        now: float,
    ) -> None:
        if len(store) < self.max_tracked_keys:
            return
        cutoff = now - self.window_seconds
        while store:
            oldest_key = next(iter(store))
            oldest_events = store[oldest_key]
            while oldest_events and oldest_events[0] <= cutoff:
                oldest_events.popleft()
            if not oldest_events:
                store.pop(oldest_key)
            else:
                break
        while len(store) >= self.max_tracked_keys:
            store.popitem(last=False)

    def _record_locked(
        self,
        store: OrderedDict[str, deque[float]],
        key: str,
        now: float,
    ) -> int:
        events = self._prune_key_locked(store, key, now)
        if events:
            events.append(now)
            store.move_to_end(key)
            return len(events)
        self._enforce_cap_locked(store, now)
        store[key] = deque([now])
        return 1

    def _login_remaining_locked(self, key: str, now: float) -> float:
        events = self._prune_key_locked(self._failures, key, now)
        if len(events) < self.max_failures:
            return 0.0
        delay = self._delay_for_count(len(events))
        remaining = (events[-1] + delay) - now
        return max(0.0, remaining)

    def retry_after(self, login: str) -> int:
        """Return remaining progressive retry delay in whole seconds (ceil), or 0 if allowed."""
        key = self._normalize(login)
        with self._lock:
            now = self._clock()
            remaining = self._login_remaining_locked(key, now)
            return math.ceil(remaining) if remaining > 0.0 else 0

    def is_blocked(self, login: str) -> bool:
        """Return True only while a progressive retry delay is currently active for login."""
        key = self._normalize(login)
        with self._lock:
            now = self._clock()
            return self._login_remaining_locked(key, now) > 0.0

    def record_failure(self, login: str) -> int:
        """Record a processed failed login attempt and return current failure count in window."""
        key = self._normalize(login)
        with self._lock:
            now = self._clock()
            return self._record_locked(self._failures, key, now)

    def reset_login(self, login: str) -> None:
        """Clear failed attempts for login after a successful authentication."""
        key = self._normalize(login)
        with self._lock:
            self._failures.pop(key, None)

    def is_ip_blocked(self, ip: str) -> bool:
        """Return True if ip has reached the failed-attempt limit in the active window."""
        key = self._normalize_ip(ip)
        with self._lock:
            now = self._clock()
            events = self._prune_key_locked(self._ip_failures, key, now)
            return len(events) >= self.ip_max_failures

    def ip_retry_after(self, ip: str) -> int:
        """Return seconds (ceil) until the oldest failure for ip expires, or 0 if allowed."""
        key = self._normalize_ip(ip)
        with self._lock:
            now = self._clock()
            events = self._prune_key_locked(self._ip_failures, key, now)
            if len(events) < self.ip_max_failures:
                return 0
            remaining = (events[0] + self.window_seconds) - now
            return max(1, math.ceil(remaining)) if remaining > 0.0 else 0

    def record_ip_failure(self, ip: str) -> int:
        """Record a processed failed login attempt for ip and return count in the window."""
        key = self._normalize_ip(ip)
        with self._lock:
            now = self._clock()
            return self._record_locked(self._ip_failures, key, now)

    def clear(self) -> None:
        """Clear all tracked login attempts, IP failures, and unknown-login audit buckets."""
        with self._lock:
            self._failures.clear()
            self._ip_failures.clear()
            agg = self._unknown_audit
        if agg is not None:
            agg.clear()
