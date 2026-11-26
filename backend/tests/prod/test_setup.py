"""Tests for B1: settings, ASGI entrypoint, prod meta/404 isolation, SQLite DB and migrations."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.asgi import select_app
from app.main import app as demo_app
from app.prod.app import create_prod_app
from app.prod.db import connect, get_schema_version, migrate, tx
from app.risk.config import RULESET_VERSION
from app.settings import BACKEND_DIR, Settings, load_settings

EXPECTED_TABLES: set[str] = {
    "companies",
    "company_settings",
    "users",
    "sessions",
    "import_batches",
    "payments",
    "checks",
    "approvals",
    "trusted_accounts",
    "suppliers",
    "supplier_accounts",
    "supplier_changes",
    "audit_log",
    "notification_reads",
}


class TestSettingsAndAsgi:
    def test_default_settings_use_demo_mode(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for var in (
            "APP_MODE",
            "SHIELD_DB_PATH",
            "SHIELD_SESSION_TTL_HOURS",
            "SHIELD_COOKIE_SECURE",
            "SHIELD_TODAY",
            "SHIELD_SEED_PASSWORD",
        ):
            monkeypatch.delenv(var, raising=False)

        cfg = load_settings()
        assert cfg.app_mode == "demo"
        assert cfg.db_path == BACKEND_DIR / "var" / "shield.db"
        assert cfg.session_ttl_hours == 12
        assert cfg.cookie_secure is False
        assert cfg.today_override is None
        assert cfg.seed_password is None
        assert cfg.today() == date.today()

    def test_custom_env_settings_parsed(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        custom_db = tmp_path / "custom.db"
        monkeypatch.setenv("APP_MODE", "prod")
        monkeypatch.setenv("SHIELD_DB_PATH", str(custom_db))
        monkeypatch.setenv("SHIELD_SESSION_TTL_HOURS", "24")
        monkeypatch.setenv("SHIELD_COOKIE_SECURE", "1")
        monkeypatch.setenv("SHIELD_TODAY", "2026-05-15")
        monkeypatch.setenv("SHIELD_SEED_PASSWORD", "test-seed-value")

        cfg = load_settings()
        assert cfg.app_mode == "prod"
        assert cfg.db_path == custom_db
        assert cfg.session_ttl_hours == 24
        assert cfg.cookie_secure is True
        assert cfg.today_override == date(2026, 5, 15)
        assert cfg.today() == date(2026, 5, 15)
        assert cfg.seed_password == "test-seed-value"

    @pytest.mark.parametrize("bad_mode", ["foo", "production", "staging", "1"])
    def test_unknown_app_mode_raises_startup_error(
        self, monkeypatch: pytest.MonkeyPatch, bad_mode: str
    ) -> None:
        monkeypatch.setenv("APP_MODE", bad_mode)
        with pytest.raises(ValueError, match="Unknown APP_MODE"):
            load_settings()
        with pytest.raises(ValueError, match="Unknown APP_MODE"):
            select_app()

    def test_invalid_other_env_values_raise(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("APP_MODE", "prod")
        monkeypatch.setenv("SHIELD_SESSION_TTL_HOURS", "0")
        with pytest.raises(ValueError):
            load_settings()

        monkeypatch.setenv("SHIELD_SESSION_TTL_HOURS", "12")
        monkeypatch.setenv("SHIELD_COOKIE_SECURE", "maybe")
        with pytest.raises(ValueError):
            load_settings()

        monkeypatch.setenv("SHIELD_COOKIE_SECURE", "0")
        monkeypatch.setenv("SHIELD_TODAY", "20-05-2026")
        with pytest.raises(ValueError):
            load_settings()

    def test_select_app_returns_demo_by_default_and_prod_when_configured(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("APP_MODE", raising=False)
        assert select_app() is demo_app

        monkeypatch.setenv("APP_MODE", "demo")
        assert select_app() is demo_app

        monkeypatch.setenv("APP_MODE", "prod")
        selected_prod = select_app()
        assert selected_prod is not demo_app
        assert selected_prod.title == "BCC Business Shield API (Prod)"

    def test_asgi_subprocess_modes_and_invalid_mode_failure(self) -> None:
        base_env = {k: v for k, v in os.environ.items() if k != "APP_MODE"}

        res_default = subprocess.run(
            [sys.executable, "-c", "import app.asgi; print(app.asgi.app.title)"],
            cwd=str(BACKEND_DIR),
            env=base_env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert res_default.returncode == 0, res_default.stderr
        assert res_default.stdout.strip() == "BCC Business Shield API"

        res_prod = subprocess.run(
            [sys.executable, "-c", "import app.asgi; print(app.asgi.app.title)"],
            cwd=str(BACKEND_DIR),
            env={**base_env, "APP_MODE": "prod"},
            capture_output=True,
            text=True,
            check=False,
        )
        assert res_prod.returncode == 0, res_prod.stderr
        assert res_prod.stdout.strip() == "BCC Business Shield API (Prod)"

        res_bad = subprocess.run(
            [sys.executable, "-c", "import app.asgi"],
            cwd=str(BACKEND_DIR),
            env={**base_env, "APP_MODE": "foo"},
            capture_output=True,
            text=True,
            check=False,
        )
        assert res_bad.returncode != 0
        assert "Unknown APP_MODE" in res_bad.stderr

    def test_backend_gitignore_excludes_var_directory(self) -> None:
        lines = {
            line.strip()
            for line in (BACKEND_DIR / ".gitignore").read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        }
        assert "var/" in lines


class TestProdAppMetaAndIsolation:
    def test_meta_returns_prod_and_demo_routes_return_404(self, tmp_path: Path) -> None:
        db_file = tmp_path / "prod.db"
        prod_app = create_prod_app(
            db_path=db_file,
            settings_override=Settings(app_mode="prod", db_path=db_file),
        )
        with TestClient(prod_app) as client:
            resp = client.get("/api/v1/meta")
            assert resp.status_code == 200
            assert resp.json() == {"mode": "prod", "ruleset_version": RULESET_VERSION}

            # Demo endpoints must not exist in prod mode (even without X-Shield-Request)
            for method, path in (
                ("GET", "/api/payments/queue"),
                ("POST", "/api/demo/reset"),
                ("POST", "/api/payments/check"),
                ("GET", "/api/history"),
                ("GET", "/api/approvals"),
                ("GET", "/api/audit"),
                ("GET", "/api/metrics"),
            ):
                demo_resp = client.request(method, path)
                assert demo_resp.status_code == 404, f"{method} {path} returned {demo_resp.status_code}"
                body = demo_resp.json()
                assert body["code"] == "not_found"
                assert body["detail"]

        # Lifespan ran migrations on startup
        conn = connect(db_file)
        try:
            assert get_schema_version(conn) == 2
        finally:
            conn.close()


class TestDatabaseMigrationsAndConstraints:
    def test_migrate_creates_full_schema_and_is_idempotent(self, tmp_path: Path) -> None:
        db_file = tmp_path / "nested" / "shield.db"
        conn = connect(db_file)
        try:
            assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
            assert str(conn.execute("PRAGMA journal_mode").fetchone()[0]).lower() == "wal"

            version_first = migrate(conn)
            assert version_first == 2
            assert get_schema_version(conn) == 2

            tables = {
                row["name"]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                ).fetchall()
            }
            assert tables == EXPECTED_TABLES

            # Insert a row and re-run migrate(): must be a no-op and preserve data
            with tx(conn):
                conn.execute(
                    """
                    INSERT INTO companies (id, name, bin, iik, bik, created_at)
                    VALUES ('cmp-1', 'ТОО Тест', '123456789012', 'KZ86125KZT5004100100', 'KCJBKZKX', '2026-11-26T00:00:00+00:00')
                    """
                )

            version_second = migrate(conn)
            assert version_second == 2
            count = conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
            assert count == 1
        finally:
            conn.close()

    def test_failed_migration_rolls_back_atomically(self, tmp_path: Path) -> None:
        migrations_dir = tmp_path / "migs"
        migrations_dir.mkdir()
        (migrations_dir / "001_good.sql").write_text(
            "CREATE TABLE t1 (id INTEGER PRIMARY KEY);\nPRAGMA user_version = 1;\n",
            encoding="utf-8",
        )
        (migrations_dir / "002_broken.sql").write_text(
            "CREATE TABLE t2 (id INTEGER PRIMARY KEY);\nTHIS IS INVALID SQL;\nPRAGMA user_version = 2;\n",
            encoding="utf-8",
        )

        conn = connect(tmp_path / "mig_test.db")
        try:
            with pytest.raises(sqlite3.OperationalError):
                migrate(conn, migrations_dir=migrations_dir)
            assert get_schema_version(conn) == 1
            tables = {
                row["name"]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            assert "t1" in tables
            assert "t2" not in tables
        finally:
            conn.close()

    def test_append_only_triggers_block_update_and_delete(self, tmp_path: Path) -> None:
        conn = connect(tmp_path / "triggers.db")
        try:
            migrate(conn)
            ts = "2026-11-26T10:00:00+00:00"
            with tx(conn):
                conn.execute(
                    "INSERT INTO companies (id, name, bin, iik, bik, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    ("c1", "ТОО Альфа", "111111111111", "KZ86125KZT5004100100", "KCJBKZKX", ts),
                )
                conn.execute(
                    "INSERT INTO users (id, company_id, login, full_name, role, password_hash, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (1, "c1", "acc", "Бухгалтер", "accountant", "scrypt$15$8$1$AA==$AA==", ts),
                )
                conn.execute(
                    """
                    INSERT INTO payments (
                        id, company_id, source, recipient_name, recipient_bin, recipient_iik,
                        recipient_bik, amount_tiyn, request_sha256, status, created_by, created_at, updated_at
                    ) VALUES (?, ?, 'manual', 'ТОО Поставщик', '222222222222', 'KZ86125KZT5004100100',
                              'KCJBKZKX', 100000, 'sha-1', 'checked', 1, ?, ?)
                    """,
                    ("pay-1", "c1", ts, ts),
                )
                conn.execute(
                    """
                    INSERT INTO checks (
                        id, payment_id, request_sha256, ruleset_version, verdict, score,
                        signal_ids_json, result_json, trigger, created_by, created_at
                    ) VALUES ('chk-1', 'pay-1', 'sha-1', '2026.11.26-r1', 'green', 0, '[]', '{}', 'create', 1, ?)
                    """,
                    (ts,),
                )
                conn.execute(
                    "INSERT INTO suppliers (id, company_id, bin, name, first_seen_at) VALUES (1, 'c1', '222222222222', 'ТОО Поставщик', ?)",
                    (ts,),
                )
                conn.execute(
                    "INSERT INTO supplier_changes (id, supplier_id, kind, old_value, new_value, occurred_at, payment_id) VALUES (1, 1, 'account_added', 'KZ1', 'KZ2', ?, 'pay-1')",
                    (ts,),
                )
                conn.execute(
                    """
                    INSERT INTO audit_log (timestamp, action, prev_hash, entry_hash)
                    VALUES (?, 'login', ?, ?)
                    """,
                    (ts, "0" * 64, "a" * 64),
                )

            with pytest.raises(sqlite3.IntegrityError, match="audit_log is append-only"):
                conn.execute("UPDATE audit_log SET action = 'tampered' WHERE id = 1")
            with pytest.raises(sqlite3.IntegrityError, match="audit_log is append-only"):
                conn.execute("DELETE FROM audit_log WHERE id = 1")

            with pytest.raises(sqlite3.IntegrityError, match="checks is append-only"):
                conn.execute("UPDATE checks SET verdict = 'green' WHERE id = 'chk-1'")
            with pytest.raises(sqlite3.IntegrityError, match="checks is append-only"):
                conn.execute("DELETE FROM checks WHERE id = 'chk-1'")

            with pytest.raises(sqlite3.IntegrityError, match="supplier_changes is append-only"):
                conn.execute("UPDATE supplier_changes SET new_value = 'KZ3' WHERE id = 1")
            with pytest.raises(sqlite3.IntegrityError, match="supplier_changes is append-only"):
                conn.execute("DELETE FROM supplier_changes WHERE id = 1")
        finally:
            conn.close()

    def test_schema_check_and_partial_unique_constraints(self, tmp_path: Path) -> None:
        conn = connect(tmp_path / "constraints.db")
        try:
            migrate(conn)
            ts = "2026-11-26T10:00:00+00:00"
            conn.execute(
                "INSERT INTO companies (id, name, bin, iik, bik, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                ("c1", "ТОО Альфа", "111111111111", "KZ86125KZT5004100100", "KCJBKZKX", ts),
            )

            # Analyst MUST have company_id IS NULL; non-analyst MUST have company_id NOT NULL
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO users (company_id, login, full_name, role, password_hash, created_at) VALUES ('c1', 'a1', 'Analyst', 'analyst', 'x', ?)",
                    (ts,),
                )
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO users (company_id, login, full_name, role, password_hash, created_at) VALUES (NULL, 'acc1', 'Acc', 'accountant', 'x', ?)",
                    (ts,),
                )
            conn.execute(
                "INSERT INTO users (id, company_id, login, full_name, role, password_hash, created_at) VALUES (1, 'c1', 'acc', 'Acc', 'accountant', 'x', ?)",
                (ts,),
            )
            conn.execute(
                "INSERT INTO users (id, company_id, login, full_name, role, password_hash, created_at) VALUES (2, NULL, 'an', 'Analyst', 'analyst', 'x', ?)",
                (ts,),
            )

            # Duplicate non-forced batch blocked, forced re-upload allowed
            conn.execute(
                """
                INSERT INTO import_batches (id, company_id, created_by, source, filename, file_sha256, total, created_count, failed_count, created_at)
                VALUES ('bat-1', 'c1', 1, '1c', 'a.txt', 'sha-file', 1, 1, 0, ?)
                """,
                (ts,),
            )
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    """
                    INSERT INTO import_batches (id, company_id, created_by, source, filename, file_sha256, total, created_count, failed_count, created_at)
                    VALUES ('bat-2', 'c1', 1, '1c', 'a.txt', 'sha-file', 1, 1, 0, ?)
                    """,
                    (ts,),
                )
            conn.execute(
                """
                INSERT INTO import_batches (id, company_id, created_by, source, filename, file_sha256, total, created_count, failed_count, is_forced, created_at)
                VALUES ('bat-3', 'c1', 1, '1c', 'a.txt', 'sha-file', 1, 1, 0, 1, ?)
                """,
                (ts,),
            )

            # tx() rolls back on exception and supports nested savepoints
            with pytest.raises(RuntimeError), tx(conn):
                conn.execute(
                    "INSERT INTO companies (id, name, bin, iik, bik, created_at) VALUES ('c2', 'ТОО Бета', '222222222222', 'KZ2', 'KCJBKZKX', ?)",
                    (ts,),
                )
                raise RuntimeError("abort")
            assert conn.execute("SELECT COUNT(*) FROM companies WHERE id = 'c2'").fetchone()[0] == 0

            with tx(conn):
                conn.execute(
                    "INSERT INTO companies (id, name, bin, iik, bik, created_at) VALUES ('c2', 'ТОО Бета', '222222222222', 'KZ2', 'KCJBKZKX', ?)",
                    (ts,),
                )
                with pytest.raises(RuntimeError), tx(conn):
                    conn.execute(
                        "INSERT INTO companies (id, name, bin, iik, bik, created_at) VALUES ('c3', 'ТОО Гамма', '333333333333', 'KZ3', 'KCJBKZKX', ?)",
                        (ts,),
                    )
                    raise RuntimeError("inner rollback")
            assert conn.execute("SELECT COUNT(*) FROM companies WHERE id = 'c2'").fetchone()[0] == 1
            assert conn.execute("SELECT COUNT(*) FROM companies WHERE id = 'c3'").fetchone()[0] == 0
        finally:
            conn.close()
