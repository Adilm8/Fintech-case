"""Security tests for prod accounts: seed passwords, migration 003, forced password change,
password-change rate limiting, invite login enumeration defense, and full_name role-word guard.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.prod.app import create_prod_app
from app.prod.db import MIGRATIONS_DIR, connect, get_schema_version, migrate, tx
from app.prod.deps import (
    CSRF_HEADER_NAME,
    CSRF_HEADER_VALUE,
    MUST_CHANGE_PASSWORD_HEADER,
    AuthContext,
    serialize_session,
)
from app.prod.schemas import Company, User
from app.prod.security import utc_now, verify_password
from app.prod.seed import seed_database
from app.settings import Settings
from tests.prod.conftest import TEST_SEED_PW, TEST_TODAY

CSRF: dict[str, str] = {CSRF_HEADER_NAME: CSRF_HEADER_VALUE}

_SEED_ENV_VARS: tuple[str, ...] = (
    "SHIELD_SEED_PASSWORD",
    "SHIELD_SEED_PASSWORD_ACCOUNTANT",
    "SHIELD_SEED_PASSWORD_DIRECTOR",
    "SHIELD_SEED_PASSWORD_ANALYST",
)


def _clear_seed_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in _SEED_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def _login(client: TestClient, login: str, password: str = TEST_SEED_PW) -> None:
    resp = client.post(
        "/api/v1/auth/login",
        json={"login": login, "password": password},
        headers=CSRF,
    )
    assert resp.status_code == 200, resp.text


@pytest.fixture
def security_env(
    seeded_db: Path,
) -> Iterator[tuple[FastAPI, Path, TestClient, TestClient]]:
    cfg = Settings(
        app_mode="prod",
        db_path=seeded_db,
        today_override=TEST_TODAY,
        cookie_secure=False,
    )
    prod_app = create_prod_app(db_path=seeded_db, settings_override=cfg)
    with TestClient(prod_app) as acc, TestClient(prod_app) as director:
        _login(acc, "accountant")
        _login(director, "director")
        yield prod_app, seeded_db, acc, director


class TestSeedPasswords:
    def test_random_distinct_passwords_per_role_printed_once_with_flag_set(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _clear_seed_env(monkeypatch)
        db_file = tmp_path / "random_seed.db"
        cfg = Settings(app_mode="prod", db_path=db_file, today_override=TEST_TODAY)

        summary = seed_database(reset=True, with_queue=False, settings_override=cfg)
        captured = capsys.readouterr()

        assert summary.users_count == 3
        assert summary.generated_password is True
        assert summary.used_fallback_password is False
        assert set(summary.passwords.keys()) == {"accountant", "director", "analyst"}
        assert set(summary.generated_passwords.keys()) == {"accountant", "director", "analyst"}

        # All 3 passwords must be distinct and strong
        distinct_pws = set(summary.passwords.values())
        assert len(distinct_pws) == 3
        for pw in distinct_pws:
            assert len(pw) >= 16
            assert any(ch.isupper() for ch in pw)
            assert any(ch.islower() for ch in pw)
            assert any(ch.isdigit() for ch in pw)
            assert any(not ch.isalnum() for ch in pw)

        # Each generated password printed once to stdout; no demo-only fallback warning
        for login, pw in summary.generated_passwords.items():
            assert captured.out.count(pw) == 1
            assert login in captured.out
        assert "demo-only" not in captured.err.lower()
        assert "demo-only" not in captured.out.lower()

        # DB stores scrypt hashes matching each role's unique password and must_change_password=1
        conn = connect(db_file)
        try:
            rows = {
                r["login"]: r
                for r in conn.execute(
                    "SELECT login, password_hash, must_change_password FROM users"
                ).fetchall()
            }
            for login, pw in summary.passwords.items():
                assert verify_password(pw, str(rows[login]["password_hash"])) is True
                assert int(rows[login]["must_change_password"]) == 1
                for other_login, other_pw in summary.passwords.items():
                    if other_login != login:
                        assert verify_password(other_pw, str(rows[login]["password_hash"])) is False
        finally:
            conn.close()

    def test_per_role_env_overrides_and_partial_generation(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _clear_seed_env(monkeypatch)
        monkeypatch.setenv("SHIELD_SEED_PASSWORD_ACCOUNTANT", "Acc-Env-Pass-1!")
        monkeypatch.setenv("SHIELD_SEED_PASSWORD_DIRECTOR", "Dir-Env-Pass-2!")

        db_file = tmp_path / "partial_env.db"
        cfg = Settings(app_mode="prod", db_path=db_file, today_override=TEST_TODAY)

        summary = seed_database(reset=True, with_queue=False, settings_override=cfg)
        captured = capsys.readouterr()

        assert summary.passwords["accountant"] == "Acc-Env-Pass-1!"
        assert summary.passwords["director"] == "Dir-Env-Pass-2!"
        assert set(summary.generated_passwords.keys()) == {"analyst"}
        analyst_pw = summary.generated_passwords["analyst"]
        assert analyst_pw not in ("Acc-Env-Pass-1!", "Dir-Env-Pass-2!")
        assert summary.used_fallback_password is False

        # Only the randomly generated analyst password is printed; explicit env ones are not
        assert captured.out.count(analyst_pw) == 1
        assert "Acc-Env-Pass-1!" not in captured.out
        assert "Dir-Env-Pass-2!" not in captured.out
        assert "demo-only" not in captured.err.lower()

        conn = connect(db_file)
        try:
            rows = {
                r["login"]: r
                for r in conn.execute(
                    "SELECT login, password_hash, must_change_password FROM users"
                ).fetchall()
            }
            assert int(rows["accountant"]["must_change_password"]) == 0
            assert int(rows["director"]["must_change_password"]) == 0
            assert int(rows["analyst"]["must_change_password"]) == 1
            assert verify_password("Acc-Env-Pass-1!", str(rows["accountant"]["password_hash"]))
            assert verify_password("Dir-Env-Pass-2!", str(rows["director"]["password_hash"]))
            assert verify_password(analyst_pw, str(rows["analyst"]["password_hash"]))
        finally:
            conn.close()

    def test_shared_fallback_env_sets_flag_zero_and_prints_demo_only_warning(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _clear_seed_env(monkeypatch)
        db_file = tmp_path / "fallback_seed.db"
        monkeypatch.setenv("APP_MODE", "prod")
        monkeypatch.setenv("SHIELD_DB_PATH", str(db_file))
        monkeypatch.setenv("SHIELD_TODAY", TEST_TODAY.isoformat())
        monkeypatch.setenv("SHIELD_SEED_PASSWORD", "Shared-Fallback-99!")

        summary = seed_database(reset=True, with_queue=False)
        captured = capsys.readouterr()

        assert summary.generated_password is False
        assert summary.generated_passwords == {}
        assert summary.used_fallback_password is True
        assert summary.password == "Shared-Fallback-99!"
        assert "demo-only" in captured.err.lower()
        assert "SHIELD_SEED_PASSWORD" in captured.err

        conn = connect(db_file)
        try:
            rows = conn.execute(
                "SELECT login, password_hash, must_change_password FROM users"
            ).fetchall()
            assert len(rows) == 3
            for r in rows:
                assert int(r["must_change_password"]) == 0
                assert verify_password("Shared-Fallback-99!", str(r["password_hash"]))
        finally:
            conn.close()


class TestMigration003:
    def test_migration_003_adds_must_change_password_and_attempts_table(
        self, tmp_path: Path
    ) -> None:
        db_file = tmp_path / "mig003.db"
        conn = connect(db_file)
        try:
            # Apply 001 and 002 directly to simulate an existing deployment
            for fname in ("001_init.sql", "002_extensions.sql"):
                sql = (MIGRATIONS_DIR / fname).read_text(encoding="utf-8")
                conn.executescript(f"BEGIN IMMEDIATE;\n{sql}\nCOMMIT;")
            assert get_schema_version(conn) == 2

            ts = "2026-11-26T10:00:00+00:00"
            with tx(conn):
                conn.execute(
                    "INSERT INTO companies (id, name, bin, iik, bik, created_at) "
                    "VALUES ('c1', 'ТОО Тест', '111111111111', 'KZ86125KZT5004100100', 'KCJBKZKX', ?)",
                    (ts,),
                )
                conn.execute(
                    "INSERT INTO users (id, company_id, login, full_name, role, password_hash, created_at) "
                    "VALUES (1, 'c1', 'u1', 'Иван Петров', 'accountant', 'scrypt$15$8$1$AA==$AA==', ?)",
                    (ts,),
                )

            assert migrate(conn) == 3
            assert get_schema_version(conn) == 3

            cols = {str(r["name"]): r for r in conn.execute("PRAGMA table_info(users)").fetchall()}
            assert "must_change_password" in cols
            assert int(cols["must_change_password"]["notnull"]) == 1
            assert str(cols["must_change_password"]["dflt_value"]) == "0"

            existing = conn.execute(
                "SELECT must_change_password FROM users WHERE id = 1"
            ).fetchone()
            assert existing is not None and int(existing["must_change_password"]) == 0

            # CHECK constraint rejects non-boolean integer values
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute("UPDATE users SET must_change_password = 2 WHERE id = 1")

            attempt_cols = {
                str(r["name"])
                for r in conn.execute("PRAGMA table_info(password_change_attempts)").fetchall()
            }
            assert {"id", "user_id", "attempted_at"} <= attempt_cols
        finally:
            conn.close()


class TestMustChangePasswordEnforcement:
    def test_invited_user_blocked_on_other_apis_until_password_changed(
        self,
        security_env: tuple[FastAPI, Path, TestClient, TestClient],
    ) -> None:
        prod_app, db_path, _, director = security_env

        inv = director.post(
            "/api/v1/company/users",
            json={
                "login": "new_invitee",
                "full_name": "Алия Серикова",
                "role": "accountant",
            },
            headers=CSRF,
        )
        assert inv.status_code == 201, inv.text
        temp_pw = inv.json()["temporary_password"]
        invited_id = inv.json()["user"]["id"]

        conn = connect(db_path)
        try:
            row = conn.execute(
                "SELECT must_change_password FROM users WHERE id = ?",
                (invited_id,),
            ).fetchone()
            assert row is not None and int(row["must_change_password"]) == 1
        finally:
            conn.close()

        # Verify shared serializer exposes must_change_password
        ctx_sample = AuthContext(
            user=User(
                id=invited_id,
                login="new_invitee",
                full_name="Алия Серикова",
                role="accountant",
                company_id="client-technostroy",
            ),
            company=Company(
                id="client-technostroy",
                name="ТОО ТехноСтрой",
                bin="123456789012",
                iik="KZ86125KZT5004100100",
                bik="KCJBKZKX",
            ),
            token_hash="hash",
            must_change_password=True,
        )
        assert serialize_session(ctx_sample)["must_change_password"] is True

        with TestClient(prod_app) as invitee:
            _login(invitee, "new_invitee", temp_pw)

            # GET /auth/me must work and advertise must_change_password via header
            auth_me = invitee.get("/api/v1/auth/me")
            assert auth_me.status_code == 200
            assert auth_me.headers.get(MUST_CHANGE_PASSWORD_HEADER) == "1"

            # All other API endpoints must return 403 password_change_required
            for method, path, body in (
                ("GET", "/api/v1/me", None),
                ("PUT", "/api/v1/me", {"default_lang": "en"}),
                ("GET", "/api/v1/payments", None),
                ("GET", "/api/v1/company", None),
                ("GET", "/api/v1/suppliers", None),
                ("GET", "/api/v1/approvals", None),
                ("GET", "/api/v1/notifications", None),
            ):
                resp = invitee.request(
                    method,
                    path,
                    json=body,
                    headers=CSRF if method != "GET" else None,
                )
                assert resp.status_code == 403, f"{method} {path} returned {resp.status_code}"
                assert resp.json()["code"] == "password_change_required"

            # POST /auth/logout must still work while must_change_password=1
            logout_resp = invitee.post("/api/v1/auth/logout", headers=CSRF)
            assert logout_resp.status_code == 204

            # Log back in and change password via POST /me/password
            _login(invitee, "new_invitee", temp_pw)
            new_pw = "Fresh-Strong-Pass-2027!"
            ch = invitee.post(
                "/api/v1/me/password",
                json={"current_password": temp_pw, "new_password": new_pw},
                headers=CSRF,
            )
            assert ch.status_code == 200, ch.text
            assert ch.json()["ok"] is True
            assert ch.headers.get(MUST_CHANGE_PASSWORD_HEADER) == "0"

            # Flag is cleared in DB and all endpoints now work
            conn = connect(db_path)
            try:
                row = conn.execute(
                    "SELECT must_change_password FROM users WHERE id = ?",
                    (invited_id,),
                ).fetchone()
                assert row is not None and int(row["must_change_password"]) == 0
            finally:
                conn.close()

            auth_me_after = invitee.get("/api/v1/auth/me")
            assert auth_me_after.status_code == 200
            assert auth_me_after.headers.get(MUST_CHANGE_PASSWORD_HEADER) == "0"
            assert invitee.get("/api/v1/me").status_code == 200
            assert invitee.get("/api/v1/payments").status_code == 200
            assert invitee.get("/api/v1/company").status_code == 200
            assert invitee.get("/api/v1/notifications").status_code == 200

    def test_seeded_random_password_user_requires_password_change(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _clear_seed_env(monkeypatch)
        db_file = tmp_path / "seeded_forced.db"
        cfg = Settings(
            app_mode="prod",
            db_path=db_file,
            today_override=TEST_TODAY,
            cookie_secure=False,
        )
        summary = seed_database(reset=True, with_queue=False, settings_override=cfg)
        acc_pw = summary.passwords["accountant"]

        prod_app = create_prod_app(db_path=db_file, settings_override=cfg)
        with TestClient(prod_app) as client:
            _login(client, "accountant", acc_pw)
            blocked = client.get("/api/v1/payments")
            assert blocked.status_code == 403
            assert blocked.json()["code"] == "password_change_required"

            assert client.get("/api/v1/auth/me").status_code == 200

            changed = client.post(
                "/api/v1/me/password",
                json={"current_password": acc_pw, "new_password": "Rotated-Acc-Pass-2027!"},
                headers=CSRF,
            )
            assert changed.status_code == 200
            assert client.get("/api/v1/payments").status_code == 200


class TestPasswordChangeRateLimit:
    def test_sixth_attempt_returns_429_and_window_expiry_unblocks(
        self,
        security_env: tuple[FastAPI, Path, TestClient, TestClient],
    ) -> None:
        _, db_path, acc, director = security_env

        for _ in range(5):
            r = acc.post(
                "/api/v1/me/password",
                json={"current_password": "wrong-current", "new_password": "Valid-New-Pass-1!"},
                headers=CSRF,
            )
            assert r.status_code == 400
            assert r.json()["code"] == "invalid_current_password"

        # 6th attempt returns 429 (even with wrong password)
        sixth = acc.post(
            "/api/v1/me/password",
            json={"current_password": "wrong-current", "new_password": "Valid-New-Pass-1!"},
            headers=CSRF,
        )
        assert sixth.status_code == 429
        assert sixth.json()["code"] == "too_many_attempts"

        # Subsequent attempt even with the CORRECT current password is still blocked while window is active
        seventh = acc.post(
            "/api/v1/me/password",
            json={"current_password": TEST_SEED_PW, "new_password": "Valid-New-Pass-1!"},
            headers=CSRF,
        )
        assert seventh.status_code == 429

        # Other user is unaffected
        dir_ok = director.post(
            "/api/v1/me/password",
            json={"current_password": TEST_SEED_PW, "new_password": "Dir-New-Pass-2027!"},
            headers=CSRF,
        )
        assert dir_ok.status_code == 200

        # Expire the 15-minute window for accountant -> allowed again
        expired_iso = (utc_now() - timedelta(minutes=16)).isoformat()
        conn = connect(db_path)
        try:
            with tx(conn):
                conn.execute(
                    "UPDATE password_change_attempts SET attempted_at = ?",
                    (expired_iso,),
                )
        finally:
            conn.close()

        after_window = acc.post(
            "/api/v1/me/password",
            json={"current_password": TEST_SEED_PW, "new_password": "Acc-New-Pass-2027!"},
            headers=CSRF,
        )
        assert after_window.status_code == 200

    def test_fewer_than_limit_failures_allow_success_and_reset_counter(
        self,
        security_env: tuple[FastAPI, Path, TestClient, TestClient],
    ) -> None:
        _, db_path, acc, _ = security_env

        # 4 failed attempts (< 5)
        for _ in range(4):
            r = acc.post(
                "/api/v1/me/password",
                json={"current_password": "bad-attempt", "new_password": "New-Pass-2027!"},
                headers=CSRF,
            )
            assert r.status_code == 400

        # Valid change must NOT be blocked and must reset attempt counter
        ok = acc.post(
            "/api/v1/me/password",
            json={"current_password": TEST_SEED_PW, "new_password": "New-Pass-2027!"},
            headers=CSRF,
        )
        assert ok.status_code == 200

        conn = connect(db_path)
        try:
            cnt = int(conn.execute("SELECT COUNT(*) FROM password_change_attempts").fetchone()[0])
            assert cnt == 0
        finally:
            conn.close()

        # After reset, 5 new failures are allowed before the 6th hits 429
        for _ in range(5):
            r = acc.post(
                "/api/v1/me/password",
                json={"current_password": "wrong-again", "new_password": "Another-Pass-2028!"},
                headers=CSRF,
            )
            assert r.status_code == 400
        blocked = acc.post(
            "/api/v1/me/password",
            json={"current_password": "wrong-again", "new_password": "Another-Pass-2028!"},
            headers=CSRF,
        )
        assert blocked.status_code == 429


class TestCompanyInviteAntiEnumeration:
    def test_duplicate_and_invalid_login_return_identical_409_invalid_login(
        self,
        security_env: tuple[FastAPI, Path, TestClient, TestClient],
    ) -> None:
        _, _, _, director = security_env

        cases = [
            "accountant",  # duplicate in same company
            "ACCOUNTANT",  # case-insensitive duplicate in same company
            "other_accountant",  # duplicate in another company
            "OTHER_ACCOUNTANT",  # case-insensitive cross-company duplicate
            "ab",  # too short
            "",  # empty
            "a" * 65,  # too long
            "bad login",  # whitespace
            "user@example.com",  # disallowed symbols
            "логин_кириллица",  # non-latin characters
        ]

        responses = []
        for login_candidate in cases:
            resp = director.post(
                "/api/v1/company/users",
                json={
                    "login": login_candidate,
                    "full_name": "Аскар Беков",
                    "role": "accountant",
                },
                headers=CSRF,
            )
            assert resp.status_code == 409, (
                f"login={login_candidate!r} returned {resp.status_code}: {resp.text}"
            )
            body = resp.json()
            assert body["code"] == "invalid_login"
            assert body["detail"]
            responses.append(body)

        # Every duplicate and invalid-format response must be identical to prevent enumeration
        first = responses[0]
        for idx, body in enumerate(responses[1:], start=1):
            assert body == first, f"Mismatch for login={cases[idx]!r}: {body} != {first}"


class TestProfileFullNameRoleWordGuard:
    @pytest.mark.parametrize(
        "bad_name",
        [
            "Директор",
            "ДИРЕКТОР компании",
            "Иван директор",
            "Генеральный Директор",
            "Director",
            "Chief DIRECTOR",
            "Subdirector",
            "Бухгалтер",
            "ГлавБухгалтер",
            "БУХГАЛТЕР Иванова",
            "accountant",
            "Senior Accountant",
            "MyAccountant",
            "Аналитик",
            "ФинАналитик",
            "АНАЛИТИК банка",
            "analyst",
            "Risk ANALYST",
            "BankAnalyst",
            "Админ",
            "Администратор",
            "СИСАДМИН",
            "admin",
            "SuperAdmin",
            "sys_ADMIN",
        ],
    )
    def test_put_me_rejects_role_words_with_422(
        self,
        security_env: tuple[FastAPI, Path, TestClient, TestClient],
        bad_name: str,
    ) -> None:
        _, _, acc, _ = security_env
        before_name = acc.get("/api/v1/me").json()["full_name"]

        resp = acc.put(
            "/api/v1/me",
            json={"full_name": bad_name},
            headers=CSRF,
        )
        assert resp.status_code == 422, f"Expected 422 for {bad_name!r}, got {resp.status_code}"
        body = resp.json()
        assert body["code"] == "validation_error"
        assert body["detail"]
        assert isinstance(body.get("errors"), list) and body["errors"][0]["field"] == "full_name"

        # Full name was not modified
        assert acc.get("/api/v1/me").json()["full_name"] == before_name

    def test_put_me_accepts_normal_names(
        self,
        security_env: tuple[FastAPI, Path, TestClient, TestClient],
    ) -> None:
        _, _, acc, _ = security_env

        for valid_name in ("Айгуль Нурланова-Серик", "Marat Kasymov", "Аскар Беков"):
            resp = acc.put(
                "/api/v1/me",
                json={"full_name": valid_name},
                headers=CSRF,
            )
            assert resp.status_code == 200, resp.text
            assert resp.json()["full_name"] == valid_name
