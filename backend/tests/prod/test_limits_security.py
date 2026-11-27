"""Tests for prod-mode hardening: rate limiting, audit aggregation, cookies, idle TTL, and limits."""

from __future__ import annotations

import asyncio
import sqlite3
import threading
import time
from collections.abc import AsyncIterator, Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient

from app.prod import security as security_mod
from app.prod.app import create_prod_app
from app.prod.audit_db import list_audit, verify_chain
from app.prod.db import connect, get_db, migrate, tx
from app.prod.deps import (
    CSRF_HEADER_NAME,
    CSRF_HEADER_VALUE,
    AuthContext,
    current_session,
    get_app_settings,
)
from app.prod.errors import ProdError
from app.prod.importers import (
    MAX_IMPORT_BODY_BYTES,
    MAX_IMPORT_BYTES,
    MAX_IMPORT_DOCUMENTS,
    MAX_REPORTED_ERRORS,
    MULTIPART_OVERHEAD_BYTES,
    LineError,
    cap_errors,
    parse_1c,
    parse_csv,
    read_body_limited,
)
from app.prod.routers import auth as auth_router
from app.prod.schemas import User
from app.prod.security import (
    LOGIN_IP_MAX_FAILURES,
    SCRYPT_MAX_CONCURRENT,
    SECURE_SESSION_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    LoginRateLimiter,
    UnknownLoginAuditAggregator,
    hash_password,
    hash_session_token,
    read_session_token,
    session_cookie_name,
    session_expiry,
    slide_session_expiry,
    utc_now,
    verify_dummy_password,
    verify_password,
)
from app.settings import DEFAULT_SESSION_IDLE_MINUTES, Settings, load_settings
from tests.prod.conftest import (
    TEST_PW_ACCOUNTANT,
    TEST_PW_DIRECTOR,
    seed_auth_users,
)

CSRF_HEADERS: dict[str, str] = {CSRF_HEADER_NAME: CSRF_HEADER_VALUE}


class _FakeRequest:
    """Minimal async request stand-in for testing read_body_limited without network I/O."""

    def __init__(self, chunks: list[bytes], headers: dict[str, str] | None = None) -> None:
        self._chunks = chunks
        self.headers: dict[str, str] = headers or {}
        self.chunks_consumed = 0

    async def stream(self) -> AsyncIterator[bytes]:
        for chunk in self._chunks:
            self.chunks_consumed += 1
            yield chunk


@pytest.fixture
def prod_env(
    tmp_path: Path,
    precomputed_password_hashes: dict[str, str],
) -> Iterator[tuple[FastAPI, Path, TestClient]]:
    db_file = tmp_path / "hardening.db"
    seed_auth_users(db_file, precomputed_password_hashes)
    cfg = Settings(
        app_mode="prod",
        db_path=db_file,
        session_ttl_hours=12,
        session_idle_minutes=60,
        cookie_secure=False,
    )
    prod_app = create_prod_app(db_path=db_file, settings_override=cfg)
    with TestClient(prod_app) as client:
        yield prod_app, db_file, client


class TestLoginRateLimiterUnit:
    def test_progressive_delay_schedule_and_non_extension_on_429(self) -> None:
        now = [1000.0]
        limiter = LoginRateLimiter(clock=lambda: now[0])

        # First 4 failures carry no delay.
        for expected_count in range(1, 5):
            assert limiter.is_blocked("Director") is False
            assert limiter.retry_after("Director") == 0
            assert limiter.record_failure("director") == expected_count
            assert limiter.is_blocked("director") is False
            assert limiter.retry_after("director") == 0

        # Failures 5..10 produce progressive delays: 2, 4, 8, 16, 30, 30 seconds.
        expected_delays = [2, 4, 8, 16, 30, 30]
        for idx, expected_delay in enumerate(expected_delays, start=5):
            assert limiter.record_failure("DIRECTOR") == idx
            assert limiter.is_blocked("director") is True
            assert limiter.retry_after("director") == expected_delay

            # Checking mid-delay does not record a failure or extend the delay.
            now[0] += 0.5
            assert limiter.is_blocked("director") is True
            assert limiter.retry_after("director") == expected_delay

            # Once the delay elapses, the account is immediately unblocked.
            now[0] += expected_delay - 0.5
            assert limiter.is_blocked("director") is False
            assert limiter.retry_after("director") == 0

        # Success resets the per-login counter completely.
        limiter.reset_login("director")
        assert limiter.record_failure("director") == 1
        assert limiter.is_blocked("director") is False

    def test_failure_window_expiry_and_memory_cap(self) -> None:
        now = [500.0]
        limiter = LoginRateLimiter(
            max_failures=5,
            window_seconds=900.0,
            clock=lambda: now[0],
            max_tracked_keys=5,
        )
        for _ in range(5):
            limiter.record_failure("user_a")
        assert limiter.is_blocked("user_a") is True

        # Advancing past window ages out all prior failures.
        now[0] += 901.0
        assert limiter.is_blocked("user_a") is False
        assert limiter.record_failure("user_a") == 1

        # Memory cap evicts oldest-touched entries and truncates keys to 64 chars.
        long_login = "x" * 100
        limiter.record_failure(long_login)
        assert len(next(iter(limiter._failures))) <= 64
        for idx in range(10):
            now[0] += 1.0
            limiter.record_failure(f"login_{idx}")
            limiter.record_ip_failure(f"10.0.0.{idx}")
        assert len(limiter._failures) <= 5
        assert len(limiter._ip_failures) <= 5


class TestLoginRateLimitHTTP:
    def test_director_not_permanently_locked_and_recovers_after_delay(
        self,
        prod_env: tuple[FastAPI, Path, TestClient],
    ) -> None:
        prod_app, _, client = prod_env
        now = [2000.0]
        prod_app.state.login_limiter = LoginRateLimiter(clock=lambda: now[0])

        for _ in range(5):
            resp = client.post(
                "/api/v1/auth/login",
                json={"login": "director", "password": "wrong-password"},
                headers=CSRF_HEADERS,
            )
            assert resp.status_code == 401
            assert resp.json()["code"] == "invalid_credentials"

        # Immediate 6th attempt returns 429 with retry_after and does NOT extend the delay.
        blocked = client.post(
            "/api/v1/auth/login",
            json={"login": "director", "password": TEST_PW_DIRECTOR},
            headers=CSRF_HEADERS,
        )
        assert blocked.status_code == 429
        body = blocked.json()
        assert body["code"] == "too_many_attempts"
        assert body["retry_after"] == 2

        # Repeated blocked attempts during the delay do not push unlock further out.
        now[0] += 1.0
        still_blocked = client.post(
            "/api/v1/auth/login",
            json={"login": "director", "password": "wrong-password"},
            headers=CSRF_HEADERS,
        )
        assert still_blocked.status_code == 429
        assert still_blocked.json()["retry_after"] == 1

        # Once the 2-second delay elapses, director logs in with the right password.
        now[0] += 1.0
        ok = client.post(
            "/api/v1/auth/login",
            json={"login": "director", "password": TEST_PW_DIRECTOR},
            headers=CSRF_HEADERS,
        )
        assert ok.status_code == 200
        assert ok.json()["user"]["login"] == "director"

    def test_ip_flood_stops_at_20_and_expires_with_clock(
        self,
        prod_env: tuple[FastAPI, Path, TestClient],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        prod_app, _, client = prod_env
        now = [3000.0]
        prod_app.state.login_limiter = LoginRateLimiter(clock=lambda: now[0])
        monkeypatch.setattr(auth_router, "verify_dummy_password", lambda _pw: None)
        monkeypatch.setattr(
            auth_router,
            "verify_password",
            lambda pw, _stored: pw == TEST_PW_DIRECTOR,
        )

        # Spread 20 failures across distinct logins so per-login delay never triggers.
        for idx in range(LOGIN_IP_MAX_FAILURES):
            resp = client.post(
                "/api/v1/auth/login",
                json={"login": f"spray_user_{idx}", "password": "bad"},
                headers=CSRF_HEADERS,
            )
            assert resp.status_code == 401

        # 21st attempt from the same IP is blocked even for another valid user.
        ip_blocked = client.post(
            "/api/v1/auth/login",
            json={"login": "director", "password": TEST_PW_DIRECTOR},
            headers=CSRF_HEADERS,
        )
        assert ip_blocked.status_code == 429
        payload = ip_blocked.json()
        assert payload["code"] == "too_many_attempts"
        assert payload["retry_after"] == 900

        # Advancing past the 15-minute window lifts the IP block.
        now[0] += 901.0
        recovered = client.post(
            "/api/v1/auth/login",
            json={"login": "director", "password": TEST_PW_DIRECTOR},
            headers=CSRF_HEADERS,
        )
        assert recovered.status_code == 200
        assert recovered.json()["user"]["login"] == "director"


class TestUnknownLoginAuditAggregation:
    def test_aggregator_unit_window_summary_and_truncation(self) -> None:
        now = [100.0]
        agg = UnknownLoginAuditAggregator(clock=lambda: now[0])
        long_login_1 = "ghost_first_" + ("a" * 50)
        long_login_last = "ghost_last_" + ("z" * 50)

        first = agg.note("192.0.2.10", long_login_1)
        assert len(first) == 1
        assert first[0] == {
            "ip": "192.0.2.10",
            "count": 1,
            "login": long_login_1[:32],
            "aggregated": False,
        }
        assert len(first[0]["login"]) == 32

        # Subsequent attempts inside the 5-minute window are counted without emitting rows.
        for step in range(4):
            now[0] += 30.0
            login_val = long_login_last if step == 3 else f"mid_{step}"
            assert agg.note("192.0.2.10", login_val) == []

        # After 5 minutes from window start, flush_expired emits one summary row with total 5.
        now[0] = 400.0
        flushed = agg.flush_expired()
        assert flushed == [
            {
                "ip": "192.0.2.10",
                "count": 5,
                "login": long_login_last[:32],
                "aggregated": True,
            }
        ]
        assert agg.flush_expired() == []

    def test_unknown_logins_http_bounded_audit_and_valid_chain(
        self,
        prod_env: tuple[FastAPI, Path, TestClient],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        prod_app, db_file, client = prod_env
        now = [5000.0]
        prod_app.state.login_limiter = LoginRateLimiter(clock=lambda: now[0])
        monkeypatch.setattr(auth_router, "verify_dummy_password", lambda _pw: None)

        long_unknown = "nonexistent_" + ("q" * 40)
        for idx in range(8):
            now[0] += 5.0
            resp = client.post(
                "/api/v1/auth/login",
                json={"login": f"{long_unknown}_{idx}", "password": "bad"},
                headers=CSRF_HEADERS,
            )
            assert resp.status_code == 401

        conn = connect(db_file)
        try:
            entries_mid = list_audit(conn, action="login_failed", limit=50)
            assert len(entries_mid) == 1
            assert entries_mid[0].details["count"] == 1
            assert entries_mid[0].details["aggregated"] is False
            assert entries_mid[0].details["ip"] == "testclient"
            assert verify_chain(conn).ok is True
        finally:
            conn.close()

        # After 5 minutes, next unknown attempt flushes the summary and starts a new bucket.
        now[0] += 305.0
        after_window = client.post(
            "/api/v1/auth/login",
            json={"login": "another_ghost_user", "password": "bad"},
            headers=CSRF_HEADERS,
        )
        assert after_window.status_code == 401

        conn = connect(db_file)
        try:
            entries = list_audit(conn, action="login_failed", limit=50)
            # 3 rows total for 9 attempts: window-1 immediate, window-1 summary, window-2 immediate.
            assert len(entries) == 3
            counts_and_flags = [(e.details["count"], e.details["aggregated"]) for e in entries]
            assert counts_and_flags == [(1, False), (8, True), (1, False)]
            for entry in entries:
                assert entry.details["ip"] == "testclient"

            raw_logins = [
                str(r["user_login"])
                for r in conn.execute("SELECT user_login FROM audit_log").fetchall()
            ]
            assert all(len(val) <= 32 for val in raw_logins)
            assert verify_chain(conn).ok is True
        finally:
            conn.close()


class TestScryptSemaphore:
    def test_scrypt_concurrency_capped_at_four(self, monkeypatch: pytest.MonkeyPatch) -> None:
        assert SCRYPT_MAX_CONCURRENT == 4

        state_lock = threading.Lock()
        active = 0
        max_active = 0

        def _fake_scrypt(
            password: bytes,
            *,
            salt: bytes,
            n: int,
            r: int,
            p: int,
            maxmem: int = 0,
            dklen: int = 64,
        ) -> bytes:
            nonlocal active, max_active
            _ = (password, salt, n, r, p, maxmem)
            with state_lock:
                active += 1
                max_active = max(max_active, active)
            try:
                time.sleep(0.03)
                return b"\xab" * dklen
            finally:
                with state_lock:
                    active -= 1

        monkeypatch.setattr(security_mod.hashlib, "scrypt", _fake_scrypt)
        sample_hash = hash_password("seed-password")
        max_active = 0

        def _worker(idx: int) -> bool:
            if idx % 3 == 0:
                return hash_password(f"pw-{idx}").startswith("scrypt$")
            if idx % 3 == 1:
                return verify_password(f"pw-{idx}", sample_hash)
            verify_dummy_password(f"pw-{idx}")
            return True

        with ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(_worker, range(12)))

        assert all(results)
        assert 2 <= max_active <= SCRYPT_MAX_CONCURRENT


class TestSettingsAndCookies:
    def _clear_cookie_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for key in (
            "APP_MODE",
            "SHIELD_COOKIE_SECURE",
            "SHIELD_COOKIE_INSECURE",
            "SHIELD_SESSION_IDLE_MINUTES",
        ):
            monkeypatch.delenv(key, raising=False)

    def test_cookie_secure_and_idle_minutes_env_matrix(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._clear_cookie_env(monkeypatch)
        demo_cfg = load_settings()
        assert demo_cfg.app_mode == "demo"
        assert demo_cfg.cookie_secure is False
        assert demo_cfg.session_idle_minutes == DEFAULT_SESSION_IDLE_MINUTES == 60

        monkeypatch.setenv("APP_MODE", "prod")
        prod_default = load_settings()
        assert prod_default.cookie_secure is True

        monkeypatch.setenv("SHIELD_COOKIE_INSECURE", "1")
        assert load_settings().cookie_secure is False

        monkeypatch.setenv("SHIELD_COOKIE_SECURE", "1")
        with pytest.raises(ValueError, match="Conflicting"):
            load_settings()

        monkeypatch.delenv("SHIELD_COOKIE_INSECURE", raising=False)
        monkeypatch.setenv("SHIELD_COOKIE_SECURE", "0")
        assert load_settings().cookie_secure is False

        monkeypatch.setenv("SHIELD_SESSION_IDLE_MINUTES", "45")
        assert load_settings().session_idle_minutes == 45

        monkeypatch.setenv("SHIELD_SESSION_IDLE_MINUTES", "0")
        with pytest.raises(ValueError):
            load_settings()

    def test_cookie_names_read_token_and_logout_deletion(
        self,
        tmp_path: Path,
        precomputed_password_hashes: dict[str, str],
    ) -> None:
        assert session_cookie_name(True) == SECURE_SESSION_COOKIE_NAME == "__Host-shield_session"
        assert session_cookie_name(False) == SESSION_COOKIE_NAME == "shield_session"

        assert read_session_token({SECURE_SESSION_COOKIE_NAME: "tok-s"}, True) == "tok-s"
        assert read_session_token({SESSION_COOKIE_NAME: "tok-plain"}, True) is None
        assert read_session_token({SESSION_COOKIE_NAME: "tok-plain"}, False) == "tok-plain"
        assert read_session_token({SECURE_SESSION_COOKIE_NAME: "tok-s"}, False) is None

        # 1. cookie_secure=True sets __Host-shield_session with Secure, HttpOnly, Path=/, no Domain
        secure_db = tmp_path / "secure_cookie.db"
        seed_auth_users(secure_db, precomputed_password_hashes)
        secure_cfg = Settings(app_mode="prod", db_path=secure_db, cookie_secure=True)
        secure_app = create_prod_app(db_path=secure_db, settings_override=secure_cfg)

        with TestClient(secure_app) as client:
            login_resp = client.post(
                "/api/v1/auth/login",
                json={"login": "director", "password": TEST_PW_DIRECTOR},
                headers=CSRF_HEADERS,
            )
            assert login_resp.status_code == 200
            set_cookie = login_resp.headers.get("set-cookie", "")
            assert set_cookie.startswith(f"{SECURE_SESSION_COOKIE_NAME}=")
            lowered = set_cookie.lower()
            assert "secure" in lowered
            assert "httponly" in lowered
            assert "path=/" in lowered
            assert "domain=" not in lowered

            # Verify logout clears __Host-shield_session (override session dep cleanly for logout).
            conn = connect(secure_db)
            try:
                tok_hash = str(conn.execute("SELECT token_hash FROM sessions").fetchone()[0])
            finally:
                conn.close()

            secure_app.dependency_overrides[current_session] = lambda: AuthContext(
                user=User(
                    id=2,
                    login="director",
                    full_name="Марат Касымов",
                    role="director",
                    company_id="comp-a",
                ),
                company=None,
                token_hash=tok_hash,
            )
            logout_resp = client.post("/api/v1/auth/logout", headers=CSRF_HEADERS)
            assert logout_resp.status_code == 204
            del_cookie = logout_resp.headers.get("set-cookie", "")
            assert del_cookie.startswith(f"{SECURE_SESSION_COOKIE_NAME}=")
            assert "max-age=0" in del_cookie.lower()
            assert "secure" in del_cookie.lower()
            assert "domain=" not in del_cookie.lower()

        # 2. cookie_secure=False uses shield_session on login and logout.
        plain_db = tmp_path / "plain_cookie.db"
        seed_auth_users(plain_db, precomputed_password_hashes)
        plain_cfg = Settings(app_mode="prod", db_path=plain_db, cookie_secure=False)
        plain_app = create_prod_app(db_path=plain_db, settings_override=plain_cfg)

        with TestClient(plain_app) as client:
            login_resp = client.post(
                "/api/v1/auth/login",
                json={"login": "director", "password": TEST_PW_DIRECTOR},
                headers=CSRF_HEADERS,
            )
            assert login_resp.status_code == 200
            set_cookie = login_resp.headers.get("set-cookie", "")
            assert set_cookie.startswith(f"{SESSION_COOKIE_NAME}=")
            assert "secure" not in set_cookie.lower()

            logout_resp = client.post("/api/v1/auth/logout", headers=CSRF_HEADERS)
            assert logout_resp.status_code == 204
            del_cookie = logout_resp.headers.get("set-cookie", "")
            assert del_cookie.startswith(f"{SESSION_COOKIE_NAME}=")
            assert "max-age=0" in del_cookie.lower()


class TestSessionIdleTimeout:
    def test_session_expiry_and_slide_unit(
        self,
        tmp_path: Path,
        precomputed_password_hashes: dict[str, str],
    ) -> None:
        db_file = tmp_path / "idle_unit.db"
        seed_auth_users(db_file, precomputed_password_hashes)

        created = datetime(2026, 11, 26, 10, 0, 0, tzinfo=UTC)
        ttl_sec = 12 * 3600
        idle_sec = 60 * 60
        initial_exp = session_expiry(created, created, ttl_seconds=ttl_sec, idle_seconds=idle_sec)
        assert initial_exp == created + timedelta(minutes=60)

        # Never extends beyond created_at + absolute TTL.
        near_abs = created + timedelta(hours=11, minutes=30)
        assert session_expiry(
            created, near_abs, ttl_seconds=ttl_sec, idle_seconds=idle_sec
        ) == created + timedelta(hours=12)

        conn = connect(db_file)
        try:
            migrate(conn)
            token_hash = hash_session_token("raw-test-token")
            with tx(conn):
                conn.execute(
                    """
                    INSERT INTO sessions (token_hash, user_id, created_at, expires_at)
                    VALUES (?, 1, ?, ?)
                    """,
                    (token_hash, created.isoformat(), initial_exp.isoformat()),
                )

            # Within 60s throttle: no DB update performed.
            t_30s = created + timedelta(seconds=30)
            eff_throttled = slide_session_expiry(
                conn,
                token_hash=token_hash,
                created_at=created.isoformat(),
                expires_at=initial_exp.isoformat(),
                ttl_seconds=ttl_sec,
                idle_seconds=idle_sec,
                now=t_30s,
            )
            assert eff_throttled == initial_exp
            stored = conn.execute(
                "SELECT expires_at FROM sessions WHERE token_hash = ?", (token_hash,)
            ).fetchone()["expires_at"]
            assert stored == initial_exp.isoformat()

            # After 5 minutes: slides expires_at forward by 5 minutes.
            t_5m = created + timedelta(minutes=5)
            eff_slid = slide_session_expiry(
                conn,
                token_hash=token_hash,
                created_at=created.isoformat(),
                expires_at=initial_exp.isoformat(),
                ttl_seconds=ttl_sec,
                idle_seconds=idle_sec,
                now=t_5m,
            )
            expected_5m = t_5m + timedelta(minutes=60)
            assert eff_slid == expected_5m
            stored_after = conn.execute(
                "SELECT expires_at FROM sessions WHERE token_hash = ?", (token_hash,)
            ).fetchone()["expires_at"]
            assert stored_after == expected_5m.isoformat()

            # Near absolute TTL: caps at created_at + 12h.
            eff_capped = slide_session_expiry(
                conn,
                token_hash=token_hash,
                created_at=created.isoformat(),
                expires_at=expected_5m.isoformat(),
                ttl_seconds=ttl_sec,
                idle_seconds=idle_sec,
                now=near_abs,
            )
            assert eff_capped == created + timedelta(hours=12)

            # Locked SQLite OperationalError is swallowed without raising.
            class _LockedConn:
                isolation_level = None

                def execute(self, *_args: object, **_kwargs: object) -> None:
                    raise sqlite3.OperationalError("database is locked")

            eff_locked = slide_session_expiry(
                _LockedConn(),  # type: ignore[arg-type]
                token_hash=token_hash,
                created_at=created.isoformat(),
                expires_at=initial_exp.isoformat(),
                ttl_seconds=ttl_sec,
                idle_seconds=idle_sec,
                now=t_5m,
            )
            assert eff_locked == initial_exp
        finally:
            conn.close()

    def test_login_sets_idle_expiry_and_probe_enforces_idle_timeout(
        self,
        prod_env: tuple[FastAPI, Path, TestClient],
    ) -> None:
        prod_app, db_file, client = prod_env

        probe = APIRouter(prefix="/api/v1/_test")

        @probe.get("/slide-ping")
        def _slide_ping(
            ctx: Annotated[AuthContext, Depends(current_session)],
            conn: Annotated[sqlite3.Connection, Depends(get_db)],
            cfg: Annotated[Settings, Depends(get_app_settings)],
        ) -> dict[str, str]:
            row = conn.execute(
                "SELECT created_at, expires_at FROM sessions WHERE token_hash = ?",
                (ctx.token_hash,),
            ).fetchone()
            assert row is not None
            effective = slide_session_expiry(
                conn,
                token_hash=ctx.token_hash,
                created_at=str(row["created_at"]),
                expires_at=str(row["expires_at"]),
                ttl_seconds=cfg.session_ttl_hours * 3600,
                idle_seconds=cfg.session_idle_minutes * 60,
            )
            return {"expires_at": effective.isoformat()}

        prod_app.include_router(probe)

        login_resp = client.post(
            "/api/v1/auth/login",
            json={"login": "accountant", "password": TEST_PW_ACCOUNTANT},
            headers=CSRF_HEADERS,
        )
        assert login_resp.status_code == 200
        raw_token = client.cookies.get(SESSION_COOKIE_NAME)
        assert raw_token is not None
        token_hash = hash_session_token(raw_token)

        # Initial stored expires_at is created_at + 60 min (idle), NOT + 12 hours.
        conn = connect(db_file)
        try:
            row = conn.execute(
                "SELECT created_at, expires_at FROM sessions WHERE token_hash = ?",
                (token_hash,),
            ).fetchone()
            assert row is not None
            created_dt = datetime.fromisoformat(str(row["created_at"]))
            expires_dt = datetime.fromisoformat(str(row["expires_at"]))
            assert expires_dt - created_dt == timedelta(minutes=60)

            # Simulate 20 minutes elapsed since last activity (still active, eligible to slide).
            earlier_exp = (utc_now() + timedelta(minutes=40)).isoformat()
            with tx(conn):
                conn.execute(
                    "UPDATE sessions SET expires_at = ? WHERE token_hash = ?",
                    (earlier_exp, token_hash),
                )
        finally:
            conn.close()

        ping_ok = client.get("/api/v1/_test/slide-ping")
        assert ping_ok.status_code == 200
        slid_dt = datetime.fromisoformat(ping_ok.json()["expires_at"])
        assert slid_dt >= utc_now() + timedelta(minutes=59)

        # Idle-expired session (expires_at in the past) gets 401.
        conn = connect(db_file)
        try:
            expired_ts = (utc_now() - timedelta(minutes=1)).isoformat()
            with tx(conn):
                conn.execute(
                    "UPDATE sessions SET expires_at = ? WHERE token_hash = ?",
                    (expired_ts, token_hash),
                )
        finally:
            conn.close()

        ping_expired = client.get("/api/v1/_test/slide-ping")
        assert ping_expired.status_code == 401
        assert ping_expired.json()["code"] == "not_authenticated"


class TestImportBodyAndErrorLimits:
    def test_constants_and_read_body_limited(self) -> None:
        assert MULTIPART_OVERHEAD_BYTES == 64 * 1024
        assert MAX_IMPORT_BODY_BYTES == MAX_IMPORT_BYTES + MULTIPART_OVERHEAD_BYTES

        # 1. Small body succeeds.
        small_req = _FakeRequest([b"abc", b"def"], headers={"Content-Length": "6"})
        assert asyncio.run(read_body_limited(small_req, 10)) == b"abcdef"  # type: ignore[arg-type]
        assert small_req.chunks_consumed == 2

        # 2. Exactly max_bytes succeeds.
        exact_req = _FakeRequest([b"12345", b"67890"])
        assert asyncio.run(read_body_limited(exact_req, 10)) == b"1234567890"  # type: ignore[arg-type]
        assert exact_req.chunks_consumed == 2

        # 3. Content-Length > max rejects immediately without reading stream.
        header_big_req = _FakeRequest([b"never-read"], headers={"Content-Length": "11"})
        with pytest.raises(ProdError) as exc_info:
            asyncio.run(read_body_limited(header_big_req, 10))  # type: ignore[arg-type]
        assert exc_info.value.status_code == 413
        assert exc_info.value.code == "file_too_large"
        assert header_big_req.chunks_consumed == 0

        # 4. Chunked upload with no Content-Length stops right when limit is exceeded.
        chunked_req = _FakeRequest([b"1234", b"5678", b"90AB", b"never-reached-1", b"never-2"])
        with pytest.raises(ProdError) as chunk_exc:
            asyncio.run(read_body_limited(chunked_req, 10))  # type: ignore[arg-type]
        assert chunk_exc.value.status_code == 413
        assert chunk_exc.value.code == "file_too_large"
        assert chunked_req.chunks_consumed == 3

        # 5. Lying Content-Length (too small) is still caught while streaming.
        lying_req = _FakeRequest([b"123456", b"789012", b"tail"], headers={"Content-Length": "5"})
        with pytest.raises(ProdError) as lying_exc:
            asyncio.run(read_body_limited(lying_req, 10))  # type: ignore[arg-type]
        assert lying_exc.value.status_code == 413
        assert lying_exc.value.code == "file_too_large"
        assert lying_req.chunks_consumed == 2

    def test_cap_errors_and_parsers_truncate_after_limit(self) -> None:
        assert MAX_REPORTED_ERRORS == 50

        # 3 errors untouched.
        three = [
            LineError(line_no=i, doc_number=f"D-{i}", code="too_many_documents", message="err")
            for i in range(1, 4)
        ]
        kept_three, omitted_three = cap_errors(three)
        assert kept_three == three
        assert omitted_three == 0

        # 120 errors -> 50 + 1 summary row, errors_omitted == 70.
        many = [
            LineError(line_no=i, doc_number=f"D-{i}", code="too_many_documents", message="err")
            for i in range(1, 121)
        ]
        kept_many, omitted_many = cap_errors(many)
        assert len(kept_many) == 51
        assert omitted_many == 70
        assert kept_many[:50] == many[:50]
        summary = kept_many[-1]
        assert summary.line_no is None
        assert summary.doc_number is None
        assert summary.code == "errors_truncated"
        assert "50" in summary.message
        assert "70" in summary.message

        # parse_csv with 500 valid + 120 extra rows yields 51 errors and errors_omitted == 70.
        header = "recipient_name;recipient_bin;recipient_iik;recipient_bik;amount_kzt;doc_number\n"
        row_tpl = "ТОО Тест;160542439625;KZ246010005016525808;HSBKKZKX;10000;C-{i}\n"
        big_csv = (
            header + "".join(row_tpl.format(i=i) for i in range(MAX_IMPORT_DOCUMENTS + 120))
        ).encode("utf-8")
        parsed_csv = parse_csv(big_csv)
        assert len(parsed_csv.docs) == MAX_IMPORT_DOCUMENTS
        assert len(parsed_csv.errors) == 51
        assert parsed_csv.errors_omitted == 70
        assert parsed_csv.errors[-1].code == "errors_truncated"

        # parse_1c also caps reported errors using cap_errors.
        unsupported_block = "СекцияДокумент=Банковский ордер\nНомер=U-{i}\nКонецДокумента\n"
        big_1c = (
            "1CClientBankExchange\nВерсияФормата=1.03\nКодировка=UTF-8\n"
            + "".join(unsupported_block.format(i=i) for i in range(75))
            + "КонецФайла\n"
        ).encode("utf-8")
        parsed_1c = parse_1c(big_1c)
        assert len(parsed_1c.docs) == 0
        assert len(parsed_1c.errors) == 51
        assert parsed_1c.errors_omitted == 25
        assert parsed_1c.errors[-1].code == "errors_truncated"
