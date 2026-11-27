"""Shared pytest fixtures for production-mode tests.

Precomputes real scrypt (n=2^15, r=8, p=1) hashes once per test session so tests
stay fast without weakening production password hashing parameters.
"""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.prod.db import connect, migrate, tx
from app.prod.security import hash_password, utc_now
from app.prod.seed import seed_database
from app.prod.signing import SignerKind, SimulatedSigner
from app.settings import Settings

TEST_PW_ACCOUNTANT = "Acc-Pass-2026!"
TEST_PW_DIRECTOR = "Dir-Pass-2026!"
TEST_PW_ANALYST = "Ana-Pass-2026!"
TEST_PW_INACTIVE = "Inact-Pass-2026!"
TEST_SEED_PW = "Seed-Pass-2026!"
TEST_TODAY = date(2026, 11, 26)


@pytest.fixture(scope="session")
def precomputed_password_hashes() -> dict[str, str]:
    """Compute real production-strength scrypt password hashes once per session."""
    return {
        "accountant": hash_password(TEST_PW_ACCOUNTANT),
        "director": hash_password(TEST_PW_DIRECTOR),
        "analyst": hash_password(TEST_PW_ANALYST),
        "disabled_user": hash_password(TEST_PW_INACTIVE),
        "other_accountant": hash_password(TEST_SEED_PW),
    }


def seed_auth_users(db_path: Path, hashes: dict[str, str]) -> None:
    """Create two companies and four standard test users using precomputed scrypt hashes."""
    conn = connect(db_path)
    try:
        migrate(conn)
        now = utc_now().isoformat()
        with tx(conn):
            conn.execute(
                """
                INSERT INTO companies (id, name, bin, iik, bik, created_at)
                VALUES
                    ('comp-a', 'ТОО Астана Строй', '200140001234', 'KZ86125KZT5004100100', 'KCJBKZKX', ?),
                    ('comp-b', 'ТОО Другая Компания', '200140009999', 'KZ228562203112345678', 'KCJBKZKX', ?)
                """,
                (now, now),
            )
            conn.execute(
                """
                INSERT INTO users (id, company_id, login, full_name, role, password_hash, is_active, created_at)
                VALUES
                    (1, 'comp-a', 'accountant', 'Айгуль Нурланова', 'accountant', ?, 1, ?),
                    (2, 'comp-a', 'director', 'Марат Касымов', 'director', ?, 1, ?),
                    (3, NULL, 'analyst', 'Динара Сабитова', 'analyst', ?, 1, ?),
                    (4, 'comp-a', 'disabled_user', 'Отключённый', 'accountant', ?, 0, ?)
                """,
                (
                    hashes["accountant"],
                    now,
                    hashes["director"],
                    now,
                    hashes["analyst"],
                    now,
                    hashes["disabled_user"],
                    now,
                ),
            )
    finally:
        conn.close()


@pytest.fixture(scope="session")
def seeded_template_db(
    tmp_path_factory: pytest.TempPathFactory,
    precomputed_password_hashes: dict[str, str],
) -> Path:
    """Create a session-wide seeded prod DB with 150 history payments + a second tenant company."""
    tpl_dir = tmp_path_factory.mktemp("prod_seed_tpl")
    tpl_path = tpl_dir / "template.db"
    cfg = Settings(
        app_mode="prod",
        db_path=tpl_path,
        today_override=TEST_TODAY,
        seed_password=TEST_SEED_PW,
    )
    seed_database(reset=True, with_queue=False, settings_override=cfg)

    conn = connect(tpl_path)
    try:
        now = utc_now().isoformat()
        with tx(conn):
            conn.execute(
                """
                INSERT INTO companies (id, name, bin, iik, bik, created_at)
                VALUES ('comp-other', 'ТОО Другой Клиент', '190540009876', 'KZ228562203112345678', 'KCJBKZKX', ?)
                """,
                (now,),
            )
            conn.execute(
                """
                INSERT INTO users (company_id, login, full_name, role, password_hash, is_active, created_at)
                VALUES ('comp-other', 'other_accountant', 'Самат Омаров', 'accountant', ?, 1, ?)
                """,
                (precomputed_password_hashes["other_accountant"], now),
            )
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        conn.close()
    return tpl_path


@pytest.fixture
def seeded_db(tmp_path: Path, seeded_template_db: Path) -> Path:
    """Copy the pre-seeded template DB into a fresh per-test file."""
    dst = tmp_path / "prod_test.db"
    shutil.copy2(seeded_template_db, dst)
    return dst


def build_sign_payload(
    client: TestClient,
    payment_id: str,
    *,
    accountant_ack: bool = False,
    signer: SignerKind = "simulated",
) -> dict[str, Any]:
    """Fetch current payment document_digest via GET and compute a simulated signature payload."""
    resp = client.get(f"/api/v1/payments/{payment_id}")
    assert resp.status_code == 200, resp.text
    payment = resp.json()
    digest = payment.get("document_digest") or ("0" * 64)
    company_id = str(payment["company_id"])
    signature = (
        SimulatedSigner().sign(digest, company_id)
        if signer == "simulated"
        else "BASE64CMS=="
    )
    payload: dict[str, Any] = {
        "document_digest": digest,
        "signature": signature,
        "signer": signer,
    }
    if accountant_ack:
        payload["accountant_ack"] = True
    return payload
