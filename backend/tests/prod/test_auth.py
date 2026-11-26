"""Tests for B2: authentication, scrypt passwords, session cookies, CSRF header, and roles."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from typing import Annotated

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient

from app.prod.app import create_prod_app
from app.prod.audit_db import list_audit, verify_chain
from app.prod.db import connect, tx
from app.prod.deps import (
    CSRF_HEADER_NAME,
    CSRF_HEADER_VALUE,
    ensure_company_access,
    require_role,
)
from app.prod.schemas import User
from app.prod.security import (
    SESSION_COOKIE_NAME,
    LoginRateLimiter,
    hash_password,
    hash_session_token,
    utc_now,
    verify_password,
)
from app.settings import Settings
from tests.prod.conftest import (
    TEST_PW_ACCOUNTANT as PW_ACCOUNTANT,
)
from tests.prod.conftest import (
    TEST_PW_ANALYST as PW_ANALYST,
)
from tests.prod.conftest import (
    TEST_PW_DIRECTOR as PW_DIRECTOR,
)
from tests.prod.conftest import (
    TEST_PW_INACTIVE as PW_INACTIVE,
)
from tests.prod.conftest import (
    seed_auth_users,
)

CSRF_HEADERS: dict[str, str] = {CSRF_HEADER_NAME: CSRF_HEADER_VALUE}


def _attach_test_role_routes(prod_app: FastAPI) -> None:
    probe = APIRouter(prefix="/api/v1/_test")

    @probe.get("/director-only")
    def _director_only(user: Annotated[User, Depends(require_role("director"))]) -> dict[str, str]:
        return {"login": user.login, "role": user.role}

    @probe.get("/signers")
    def _signers(
        user: Annotated[User, Depends(require_role("accountant", "director"))],
    ) -> dict[str, str]:
        return {"login": user.login, "role": user.role}

    @probe.get("/company/{company_id}")
    def _company_check(
        company_id: str,
        user: Annotated[User, Depends(require_role("accountant", "director", "analyst"))],
    ) -> dict[str, str]:
        ensure_company_access(user, company_id)
        return {"company_id": company_id, "role": user.role}

    prod_app.include_router(probe)


@pytest.fixture
def prod_env(
    tmp_path: Path,
    precomputed_password_hashes: dict[str, str],
) -> Iterator[tuple[FastAPI, Path, TestClient]]:
    db_file = tmp_path / "auth.db"
    seed_auth_users(db_file, precomputed_password_hashes)
    cfg = Settings(app_mode="prod", db_path=db_file, session_ttl_hours=12, cookie_secure=False)
    prod_app = create_prod_app(db_path=db_file, settings_override=cfg)
    _attach_test_role_routes(prod_app)
    with TestClient(prod_app) as client:
        yield prod_app, db_file, client


class TestPasswordHashingAndRateLimiter:
    def test_scrypt_hash_format_random_salt_and_verification(self) -> None:
        h1 = hash_password("MySecret123!")
        h2 = hash_password("MySecret123!")
        assert h1 != h2
        assert h1.startswith("scrypt$15$8$1$")
        assert len(h1.split("$")) == 6
        assert "MySecret123!" not in h1

        assert verify_password("MySecret123!", h1) is True
        assert verify_password("MySecret123!", h2) is True
        assert verify_password("WrongSecret!", h1) is False
        assert verify_password("MySecret123!", "invalid-format") is False
        assert verify_password("MySecret123!", "scrypt$99$8$1$AA==$AA==") is False

    def test_rate_limiter_window_expiry_and_reset(self) -> None:
        now = [1000.0]
        limiter = LoginRateLimiter(max_failures=5, window_seconds=900.0, clock=lambda: now[0])

        for i in range(5):
            assert limiter.is_blocked("Accountant") is False
            assert limiter.record_failure("accountant") == i + 1
        assert limiter.is_blocked("ACCOUNTANT") is True
        assert limiter.is_blocked("director") is False

        # Advance past 15 minutes
        now[0] += 901.0
        assert limiter.is_blocked("accountant") is False

        # Reset clears recorded failures
        limiter.record_failure("director")
        limiter.reset_login("DIRECTOR")
        assert limiter.is_blocked("director") is False


class TestAuthFlowAndSecurity:
    def test_me_without_cookie_returns_401(
        self, prod_env: tuple[FastAPI, Path, TestClient]
    ) -> None:
        _, _, client = prod_env
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 401
        body = resp.json()
        assert body["code"] == "not_authenticated"
        assert body["detail"]

    def test_login_sets_httponly_cookie_and_no_plaintext_secrets_in_db(
        self, prod_env: tuple[FastAPI, Path, TestClient]
    ) -> None:
        _, db_file, client = prod_env
        resp = client.post(
            "/api/v1/auth/login",
            json={"login": "Accountant", "password": PW_ACCOUNTANT},
            headers=CSRF_HEADERS,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["user"] == {
            "id": 1,
            "login": "accountant",
            "full_name": "Айгуль Нурланова",
            "role": "accountant",
            "company_id": "comp-a",
        }
        assert body["company"] == {
            "id": "comp-a",
            "name": "ТОО Астана Строй",
            "bin": "200140001234",
            "iik": "KZ86125KZT5004100100",
            "bik": "KCJBKZKX",
        }

        set_cookie = resp.headers.get("set-cookie", "")
        assert f"{SESSION_COOKIE_NAME}=" in set_cookie
        assert "httponly" in set_cookie.lower()
        assert "samesite=lax" in set_cookie.lower()
        assert "path=/" in set_cookie.lower()
        assert "max-age=43200" in set_cookie.lower()

        raw_token = client.cookies.get(SESSION_COOKIE_NAME)
        assert raw_token is not None and len(raw_token) >= 32

        # Verify /auth/me works with cookie
        me_resp = client.get("/api/v1/auth/me")
        assert me_resp.status_code == 200
        assert me_resp.json() == body

        # Verify DB contains no plaintext passwords or raw session tokens
        conn = connect(db_file)
        try:
            user_hashes = [
                r["password_hash"]
                for r in conn.execute("SELECT password_hash FROM users").fetchall()
            ]
            for pw in (PW_ACCOUNTANT, PW_DIRECTOR, PW_ANALYST, PW_INACTIVE):
                assert all(pw not in h for h in user_hashes)
            assert all(h.startswith("scrypt$15$8$1$") for h in user_hashes)

            session_rows = conn.execute(
                "SELECT token_hash, user_id, revoked_at FROM sessions"
            ).fetchall()
            assert len(session_rows) == 1
            expected_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
            assert session_rows[0]["token_hash"] == expected_hash
            assert session_rows[0]["token_hash"] != raw_token
            assert session_rows[0]["revoked_at"] is None
        finally:
            conn.close()

    def test_auth_events_logged_in_audit_chain_without_secrets(
        self, prod_env: tuple[FastAPI, Path, TestClient]
    ) -> None:
        _, db_file, client = prod_env

        # 1. Unknown login failure
        assert (
            client.post(
                "/api/v1/auth/login",
                json={"login": "ghost_user", "password": "wrong-password"},
                headers=CSRF_HEADERS,
            ).status_code
            == 401
        )
        # 2. Known user wrong password failure
        assert (
            client.post(
                "/api/v1/auth/login",
                json={"login": "accountant", "password": "wrong-password"},
                headers=CSRF_HEADERS,
            ).status_code
            == 401
        )
        # 3. Successful login
        assert (
            client.post(
                "/api/v1/auth/login",
                json={"login": "accountant", "password": PW_ACCOUNTANT},
                headers=CSRF_HEADERS,
            ).status_code
            == 200
        )
        raw_token = client.cookies.get(SESSION_COOKIE_NAME)
        assert raw_token is not None
        # 4. Logout
        assert client.post("/api/v1/auth/logout", headers=CSRF_HEADERS).status_code == 204

        conn = connect(db_file)
        try:
            verify = verify_chain(conn)
            assert verify.ok is True
            assert verify.checked == 4
            assert verify.broken_at is None

            entries = list_audit(conn, limit=10)
            assert [e.action for e in entries] == [
                "logout",
                "login",
                "login_failed",
                "login_failed",
            ]
            assert entries[0].user is not None and entries[0].user.login == "accountant"
            assert entries[1].user is not None and entries[1].user.login == "accountant"
            assert entries[2].user is not None and entries[2].user.login == "accountant"
            assert entries[3].user is None

            raw_rows = conn.execute("SELECT details_json FROM audit_log").fetchall()
            joined = " ".join(str(r["details_json"]) for r in raw_rows)
            assert PW_ACCOUNTANT not in joined
            assert "wrong-password" not in joined
            assert raw_token not in joined
        finally:
            conn.close()

    def test_analyst_session_has_null_company(
        self, prod_env: tuple[FastAPI, Path, TestClient]
    ) -> None:
        _, _, client = prod_env
        resp = client.post(
            "/api/v1/auth/login",
            json={"login": "analyst", "password": PW_ANALYST},
            headers=CSRF_HEADERS,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["user"]["role"] == "analyst"
        assert body["user"]["company_id"] is None
        assert body["company"] is None

    def test_cookie_secure_flag_respected(
        self,
        tmp_path: Path,
        precomputed_password_hashes: dict[str, str],
    ) -> None:
        db_file = tmp_path / "secure.db"
        seed_auth_users(db_file, precomputed_password_hashes)
        cfg = Settings(app_mode="prod", db_path=db_file, cookie_secure=True)
        prod_app = create_prod_app(db_path=db_file, settings_override=cfg)
        with TestClient(prod_app) as client:
            resp = client.post(
                "/api/v1/auth/login",
                json={"login": "director", "password": PW_DIRECTOR},
                headers=CSRF_HEADERS,
            )
            assert resp.status_code == 200
            set_cookie = resp.headers.get("set-cookie", "").lower()
            assert "secure" in set_cookie
            assert "httponly" in set_cookie

    @pytest.mark.parametrize("lang", ["ru", "kk", "en"])
    def test_wrong_password_and_unknown_login_return_identical_401(
        self, prod_env: tuple[FastAPI, Path, TestClient], lang: str
    ) -> None:
        prod_app, _, client = prod_env
        prod_app.state.login_limiter.clear()

        wrong_pw = client.post(
            f"/api/v1/auth/login?lang={lang}",
            json={"login": "accountant", "password": "definitely-wrong-password"},
            headers=CSRF_HEADERS,
        )
        unknown_user = client.post(
            f"/api/v1/auth/login?lang={lang}",
            json={"login": "no_such_user", "password": "definitely-wrong-password"},
            headers=CSRF_HEADERS,
        )
        disabled_user = client.post(
            f"/api/v1/auth/login?lang={lang}",
            json={"login": "disabled_user", "password": PW_INACTIVE},
            headers=CSRF_HEADERS,
        )

        assert wrong_pw.status_code == 401
        assert unknown_user.status_code == 401
        assert disabled_user.status_code == 401
        assert wrong_pw.json() == unknown_user.json() == disabled_user.json()
        assert wrong_pw.json()["code"] == "invalid_credentials"

    def test_sixth_failed_login_returns_429(
        self, prod_env: tuple[FastAPI, Path, TestClient]
    ) -> None:
        _, _, client = prod_env
        for _ in range(5):
            r = client.post(
                "/api/v1/auth/login",
                json={"login": "accountant", "password": "bad-password"},
                headers=CSRF_HEADERS,
            )
            assert r.status_code == 401
            assert r.json()["code"] == "invalid_credentials"

        # 6th attempt must be rate-limited even with correct password
        sixth = client.post(
            "/api/v1/auth/login",
            json={"login": "accountant", "password": PW_ACCOUNTANT},
            headers=CSRF_HEADERS,
        )
        assert sixth.status_code == 429
        assert sixth.json()["code"] == "too_many_attempts"

        # Different user is not blocked
        other = client.post(
            "/api/v1/auth/login",
            json={"login": "director", "password": PW_DIRECTOR},
            headers=CSRF_HEADERS,
        )
        assert other.status_code == 200

    def test_logout_revokes_session_and_old_cookie_returns_401(
        self, prod_env: tuple[FastAPI, Path, TestClient]
    ) -> None:
        prod_app, db_file, client = prod_env
        login_resp = client.post(
            "/api/v1/auth/login",
            json={"login": "director", "password": PW_DIRECTOR},
            headers=CSRF_HEADERS,
        )
        assert login_resp.status_code == 200
        old_token = client.cookies.get(SESSION_COOKIE_NAME)
        assert old_token is not None

        logout_resp = client.post("/api/v1/auth/logout", headers=CSRF_HEADERS)
        assert logout_resp.status_code == 204
        assert logout_resp.content == b""

        # Using the revoked cookie directly in a fresh client still fails with 401
        with TestClient(prod_app) as replay_client:
            replay_client.cookies.set(SESSION_COOKIE_NAME, old_token)
            me_after = replay_client.get("/api/v1/auth/me")
            assert me_after.status_code == 401
            assert me_after.json()["code"] == "not_authenticated"

        # Confirm revoked_at was persisted in DB
        conn = connect(db_file)
        try:
            row = conn.execute(
                "SELECT revoked_at FROM sessions WHERE token_hash = ?",
                (hash_session_token(old_token),),
            ).fetchone()
            assert row is not None and row["revoked_at"] is not None
        finally:
            conn.close()

    def test_expired_session_returns_401(
        self, prod_env: tuple[FastAPI, Path, TestClient]
    ) -> None:
        _, db_file, client = prod_env
        login_resp = client.post(
            "/api/v1/auth/login",
            json={"login": "accountant", "password": PW_ACCOUNTANT},
            headers=CSRF_HEADERS,
        )
        assert login_resp.status_code == 200
        token = client.cookies.get(SESSION_COOKIE_NAME)
        assert token is not None

        expired_ts = (utc_now() - timedelta(minutes=1)).isoformat()
        conn = connect(db_file)
        try:
            with tx(conn):
                conn.execute(
                    "UPDATE sessions SET expires_at = ? WHERE token_hash = ?",
                    (expired_ts, hash_session_token(token)),
                )
        finally:
            conn.close()

        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 401
        assert resp.json()["code"] == "not_authenticated"

    def test_post_without_csrf_header_returns_403(
        self, prod_env: tuple[FastAPI, Path, TestClient]
    ) -> None:
        _, _, client = prod_env

        no_header = client.post(
            "/api/v1/auth/login",
            json={"login": "accountant", "password": PW_ACCOUNTANT},
        )
        assert no_header.status_code == 403
        assert no_header.json()["code"] == "csrf_header_missing"

        wrong_header = client.post(
            "/api/v1/auth/login",
            json={"login": "accountant", "password": PW_ACCOUNTANT},
            headers={CSRF_HEADER_NAME: "0"},
        )
        assert wrong_header.status_code == 403
        assert wrong_header.json()["code"] == "csrf_header_missing"

        # Log in properly, then verify logout without CSRF header is also 403
        ok = client.post(
            "/api/v1/auth/login",
            json={"login": "accountant", "password": PW_ACCOUNTANT},
            headers=CSRF_HEADERS,
        )
        assert ok.status_code == 200
        logout_no_csrf = client.post("/api/v1/auth/logout")
        assert logout_no_csrf.status_code == 403
        assert logout_no_csrf.json()["code"] == "csrf_header_missing"

    def test_require_role_enforces_roles_and_ignores_x_role_header(
        self, prod_env: tuple[FastAPI, Path, TestClient]
    ) -> None:
        _, _, client = prod_env

        # Unauthenticated -> 401
        unauth = client.get("/api/v1/_test/director-only")
        assert unauth.status_code == 401
        assert unauth.json()["code"] == "not_authenticated"

        # Accountant cannot access director-only, even with spoofed X-Role header
        client.post(
            "/api/v1/auth/login",
            json={"login": "accountant", "password": PW_ACCOUNTANT},
            headers=CSRF_HEADERS,
        )
        denied = client.get(
            "/api/v1/_test/director-only",
            headers={"X-Role": "director"},
        )
        assert denied.status_code == 403
        assert denied.json()["code"] == "forbidden_role"

        # Accountant can access signers route
        allowed = client.get("/api/v1/_test/signers")
        assert allowed.status_code == 200
        assert allowed.json() == {"login": "accountant", "role": "accountant"}

        # Cross-company access returns 404 (not 403)
        assert client.get("/api/v1/_test/company/comp-a").status_code == 200
        cross = client.get("/api/v1/_test/company/comp-b")
        assert cross.status_code == 404
        assert cross.json()["code"] == "not_found"

        # Director can access director-only
        client.post(
            "/api/v1/auth/login",
            json={"login": "director", "password": PW_DIRECTOR},
            headers=CSRF_HEADERS,
        )
        dir_ok = client.get("/api/v1/_test/director-only")
        assert dir_ok.status_code == 200
        assert dir_ok.json() == {"login": "director", "role": "director"}

        # Analyst cannot access signers, but can view any company
        client.post(
            "/api/v1/auth/login",
            json={"login": "analyst", "password": PW_ANALYST},
            headers=CSRF_HEADERS,
        )
        assert client.get("/api/v1/_test/signers").status_code == 403
        assert client.get("/api/v1/_test/company/comp-a").status_code == 200
        assert client.get("/api/v1/_test/company/comp-b").status_code == 200

    def test_validation_error_returns_422_with_code_and_localized_errors(
        self, prod_env: tuple[FastAPI, Path, TestClient]
    ) -> None:
        _, _, client = prod_env
        resp = client.post(
            "/api/v1/auth/login?lang=en",
            json={"login": ""},
            headers=CSRF_HEADERS,
        )
        assert resp.status_code == 422
        body = resp.json()
        assert body["code"] == "validation_error"
        assert isinstance(body["errors"], list) and len(body["errors"]) >= 1
        assert body.get("detail")
