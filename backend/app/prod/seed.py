"""Database seeder for production mode: `python -m app.prod.seed [--reset] [--with-queue]`."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import string
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from app.prod.audit_db import append_audit
from app.prod.db import connect, migrate, tx
from app.prod.directory import register_signed_payment
from app.prod.prod_store import ProdStore, get_reference_store
from app.prod.security import hash_password, utc_now_iso
from app.prod.serde import dump_full
from app.risk.config import DEMO_TODAY
from app.risk.engine import check_payment
from app.schemas import CheckRequest, compute_request_sha256
from app.settings import Settings, load_settings
from app.store import DEFAULT_DATA_DIR, Store

SEED_USERS: tuple[tuple[str, str, str], ...] = (
    ("accountant", "Айгуль Нурланова", "accountant"),
    ("director", "Марат Касымов", "director"),
    ("analyst", "Динара Сабитова", "analyst"),
)


_PW_UPPER: str = string.ascii_uppercase
_PW_LOWER: str = string.ascii_lowercase
_PW_DIGITS: str = string.digits
_PW_SYMBOLS: str = "-_!@#%"
_PW_ALPHABET: str = _PW_UPPER + _PW_LOWER + _PW_DIGITS + _PW_SYMBOLS
_GENERATED_PASSWORD_LENGTH: int = 20


def _generate_strong_password(length: int = _GENERATED_PASSWORD_LENGTH) -> str:
    """Generate a cryptographically strong password with mixed character classes."""
    target_len = max(length, 16)
    chars = [
        secrets.choice(_PW_UPPER),
        secrets.choice(_PW_LOWER),
        secrets.choice(_PW_DIGITS),
        secrets.choice(_PW_SYMBOLS),
        *(secrets.choice(_PW_ALPHABET) for _ in range(target_len - 4)),
    ]
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


def _resolve_seed_password(role: str, fallback_password: str | None) -> tuple[str, bool, bool]:
    """Resolve password for a seeded role.

    Returns (plaintext_password, is_generated, used_fallback).
    Priority: SHIELD_SEED_PASSWORD_<ROLE> -> explicit fallback -> fresh random password.
    """
    role_env_key = f"SHIELD_SEED_PASSWORD_{role.upper()}"
    role_env_val = os.environ.get(role_env_key)
    if role_env_val:
        return role_env_val, False, False
    if fallback_password:
        return fallback_password, False, True
    return _generate_strong_password(), True, False


@dataclass(frozen=True)
class SeedSummary:
    """Summary returned after seeding the production SQLite database."""

    db_path: Path
    company_id: str
    users_count: int
    signed_payments_count: int
    queue_payments_count: int
    suppliers_count: int
    password: str
    generated_password: bool
    passwords: dict[str, str] = field(default_factory=dict)
    generated_passwords: dict[str, str] = field(default_factory=dict)
    used_fallback_password: bool = False


def _remove_db_files(db_path: Path) -> None:
    for candidate in (db_path, Path(f"{db_path}-wal"), Path(f"{db_path}-shm")):
        if candidate.exists():
            candidate.unlink()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def seed_database(
    *,
    reset: bool = False,
    with_queue: bool = False,
    db_path: Path | None = None,
    data_dir: Path | None = None,
    today: date | None = None,
    password: str | None = None,
    settings_override: Settings | None = None,
    reference: Store | None = None,
    require_prod_mode: bool = True,
) -> SeedSummary:
    """Populate the prod SQLite database from synthetic demo JSON files (read-only)."""
    cfg = settings_override if settings_override is not None else load_settings()
    if require_prod_mode and cfg.app_mode != "prod":
        raise RuntimeError("Seed command requires APP_MODE=prod.")

    resolved_db_path = db_path if db_path is not None else cfg.db_path
    resolved_data_dir = (data_dir if data_dir is not None else DEFAULT_DATA_DIR).resolve()
    effective_today = today if today is not None else cfg.today()

    if reset:
        _remove_db_files(resolved_db_path)

    fallback_password = password if password is not None else cfg.seed_password
    if fallback_password == "":
        fallback_password = None

    raw_history = _read_json(resolved_data_dir / "history.json")
    client_raw: dict[str, Any] = dict(raw_history["client"])
    company_id = str(client_raw["payer_id"])
    history_payments: list[dict[str, Any]] = list(raw_history.get("payments", []))
    history_payments.sort(key=lambda p: (str(p.get("paid_at", "")), str(p.get("id", ""))))

    shift_days = (effective_today - DEMO_TODAY).days
    now_iso = utc_now_iso()

    resolved_passwords: dict[str, str] = {}
    generated_passwords: dict[str, str] = {}
    used_fallback_password = False

    conn = connect(resolved_db_path)
    try:
        migrate(conn)

        with tx(conn):
            existing_company = conn.execute(
                "SELECT id FROM companies WHERE id = ?",
                (company_id,),
            ).fetchone()
            if existing_company is None:
                conn.execute(
                    """
                    INSERT INTO companies (id, name, bin, iik, bik, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        company_id,
                        str(client_raw["name"]),
                        str(client_raw["bin"]),
                        str(client_raw["iik"]),
                        str(client_raw["bik"]),
                        now_iso,
                    ),
                )

            user_ids: dict[str, int] = {}
            for login, full_name, role in SEED_USERS:
                existing_user = conn.execute(
                    "SELECT id FROM users WHERE login = ?",
                    (login,),
                ).fetchone()
                if existing_user is not None:
                    user_ids[login] = int(existing_user["id"])
                else:
                    user_password, is_generated, used_fallback = _resolve_seed_password(
                        role,
                        fallback_password,
                    )
                    resolved_passwords[login] = user_password
                    if is_generated:
                        generated_passwords[login] = user_password
                    if used_fallback:
                        used_fallback_password = True
                    must_change = 1 if is_generated else 0
                    user_company = None if role == "analyst" else company_id
                    cur = conn.execute(
                        """
                        INSERT INTO users (
                            company_id, login, full_name, role, password_hash,
                            is_active, must_change_password, created_at
                        ) VALUES (?, ?, ?, ?, ?, 1, ?, ?)
                        """,
                        (
                            user_company,
                            login,
                            full_name,
                            role,
                            hash_password(user_password),
                            must_change,
                            now_iso,
                        ),
                    )
                    assert cur.lastrowid is not None
                    user_ids[login] = int(cur.lastrowid)

            accountant_id = user_ids["accountant"]
            director_id = user_ids["director"]

            for item in history_payments:
                pay_id = f"pay-{str(item['id']).lower()}"
                already = conn.execute(
                    "SELECT 1 FROM payments WHERE id = ?",
                    (pay_id,),
                ).fetchone()
                if already is not None:
                    continue

                orig_date = date.fromisoformat(str(item["paid_at"])[:10])
                shifted_date = (orig_date + timedelta(days=shift_days)).isoformat()
                signed_ts = f"{shifted_date}T09:00:00+00:00"

                req = CheckRequest(
                    payer_id=company_id,
                    recipient_name=str(item["recipient_name"]),
                    recipient_bin=str(item["recipient_bin"]),
                    recipient_iik=str(item["recipient_iik"]),
                    recipient_bik=str(item["recipient_bik"]),
                    amount_kzt=float(item["amount_kzt"]),
                    purpose=str(item.get("purpose", "")),
                    kbe=str(item.get("kbe", "")),
                    knp=str(item.get("knp", "")),
                )
                req_sha = compute_request_sha256(req, resolved_payer_id=company_id)
                amount_tiyn = round(float(req.amount_kzt) * 100)

                conn.execute(
                    """
                    INSERT INTO payments (
                        id, company_id, source, batch_id, line_no, doc_number, doc_date,
                        recipient_name, recipient_bin, recipient_iik, recipient_bik,
                        amount_tiyn, purpose, kbe, knp, request_sha256,
                        status, check_id, approval_id, accountant_ack,
                        created_by, created_at, updated_at, signed_by, signed_at, paid_at
                    ) VALUES (
                        ?, ?, 'seed', NULL, NULL, ?, ?,
                        ?, ?, ?, ?,
                        ?, ?, ?, ?, ?,
                        'signed', NULL, NULL, 0,
                        ?, ?, ?, ?, ?, ?
                    )
                    """,
                    (
                        pay_id,
                        company_id,
                        str(item["id"]),
                        shifted_date,
                        req.recipient_name,
                        req.recipient_bin,
                        req.recipient_iik,
                        req.recipient_bik,
                        amount_tiyn,
                        req.purpose,
                        req.kbe,
                        req.knp,
                        req_sha,
                        accountant_id,
                        signed_ts,
                        signed_ts,
                        director_id,
                        signed_ts,
                        shifted_date,
                    ),
                )
                register_signed_payment(
                    conn,
                    company_id=company_id,
                    recipient_bin=req.recipient_bin,
                    recipient_name=req.recipient_name,
                    recipient_iik=req.recipient_iik,
                    recipient_bik=req.recipient_bik,
                    paid_at=shifted_date,
                    payment_id=pay_id,
                )

            if with_queue:
                ref_store = reference if reference is not None else get_reference_store()
                company_row = conn.execute(
                    "SELECT * FROM companies WHERE id = ?",
                    (company_id,),
                ).fetchone()
                assert company_row is not None
                prod_store = ProdStore(
                    conn,
                    company_row,
                    reference=ref_store,
                    today=effective_today,
                )
                queue_items: list[dict[str, Any]] = list(
                    _read_json(resolved_data_dir / "queue.json")
                )
                for idx, raw_q in enumerate(queue_items, start=1):
                    pay_id = f"pay-{str(raw_q['id']).lower()}"
                    already_q = conn.execute(
                        "SELECT 1 FROM payments WHERE id = ?",
                        (pay_id,),
                    ).fetchone()
                    if already_q is not None:
                        continue

                    req = CheckRequest(
                        payer_id=company_id,
                        recipient_name=str(raw_q["recipient_name"]),
                        recipient_bin=str(raw_q["recipient_bin"]),
                        recipient_iik=str(raw_q["recipient_iik"]),
                        recipient_bik=str(raw_q["recipient_bik"]),
                        amount_kzt=float(raw_q["amount_kzt"]),
                        purpose=str(raw_q.get("purpose", "")),
                        kbe=str(raw_q.get("kbe", "")),
                        knp=str(raw_q.get("knp", "")),
                    )
                    req_sha = compute_request_sha256(req, resolved_payer_id=company_id)
                    result = check_payment(
                        req,
                        prod_store,
                        today=effective_today,
                        lang="ru",
                        include_analyst_details=False,
                        include_recent_memory=True,
                        record_in_memory=False,
                    )
                    amount_tiyn = round(float(req.amount_kzt) * 100)
                    signal_ids = [s.rule_id for s in result.signals]

                    conn.execute(
                        """
                        INSERT INTO payments (
                            id, company_id, source, batch_id, line_no, doc_number, doc_date,
                            recipient_name, recipient_bin, recipient_iik, recipient_bik,
                            amount_tiyn, purpose, kbe, knp, request_sha256,
                            status, check_id, approval_id, accountant_ack,
                            created_by, created_at, updated_at, signed_by, signed_at, paid_at
                        ) VALUES (
                            ?, ?, 'manual', NULL, ?, ?, ?,
                            ?, ?, ?, ?,
                            ?, ?, ?, ?, ?,
                            'checked', ?, NULL, 0,
                            ?, ?, ?, NULL, NULL, NULL
                        )
                        """,
                        (
                            pay_id,
                            company_id,
                            idx,
                            str(raw_q["id"]),
                            effective_today.isoformat(),
                            req.recipient_name,
                            req.recipient_bin,
                            req.recipient_iik,
                            req.recipient_bik,
                            amount_tiyn,
                            req.purpose,
                            req.kbe,
                            req.knp,
                            req_sha,
                            result.check_id,
                            accountant_id,
                            now_iso,
                            now_iso,
                        ),
                    )
                    conn.execute(
                        """
                        INSERT INTO checks (
                            id, payment_id, request_sha256, ruleset_version,
                            verdict, score, signal_ids_json, result_json,
                            trigger, created_by, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'create', ?, ?)
                        """,
                        (
                            result.check_id,
                            pay_id,
                            req_sha,
                            result.ruleset_version,
                            result.verdict,
                            result.score,
                            json.dumps(signal_ids, ensure_ascii=False),
                            dump_full(result),
                            accountant_id,
                            now_iso,
                        ),
                    )
                    append_audit(
                        conn,
                        action="check",
                        timestamp=now_iso,
                        user_id=accountant_id,
                        user_login="accountant",
                        role="accountant",
                        company_id=company_id,
                        payment_id=pay_id,
                        check_id=result.check_id,
                        request_sha256=req_sha,
                        ruleset_version=result.ruleset_version,
                        verdict=result.verdict,
                        signal_ids=signal_ids,
                    )

        users_count = int(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0])
        signed_count = int(
            conn.execute("SELECT COUNT(*) FROM payments WHERE status = 'signed'").fetchone()[0]
        )
        queue_count = int(
            conn.execute("SELECT COUNT(*) FROM payments WHERE status = 'checked'").fetchone()[0]
        )
        suppliers_count = int(conn.execute("SELECT COUNT(*) FROM suppliers").fetchone()[0])

        if used_fallback_password:
            print(
                "WARNING: SHIELD_SEED_PASSWORD shared fallback is demo-only; "
                "set SHIELD_SEED_PASSWORD_<ROLE> per role or omit it to generate "
                "distinct random passwords.",
                file=sys.stderr,
            )
        for login, gen_password in generated_passwords.items():
            print(f"Generated seed password (printed once) for {login}: {gen_password}")

        unique_passwords = set(resolved_passwords.values())
        shared_password = next(iter(unique_passwords)) if len(unique_passwords) == 1 else ""

        return SeedSummary(
            db_path=resolved_db_path,
            company_id=company_id,
            users_count=users_count,
            signed_payments_count=signed_count,
            queue_payments_count=queue_count,
            suppliers_count=suppliers_count,
            password=shared_password,
            generated_password=bool(generated_passwords),
            passwords=resolved_passwords,
            generated_passwords=generated_passwords,
            used_fallback_password=used_fallback_password,
        )
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for `python -m app.prod.seed`."""
    parser = argparse.ArgumentParser(description="Seed BCC Business Shield prod SQLite database.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete existing SQLite database before applying migrations and seeding.",
    )
    parser.add_argument(
        "--with-queue",
        action="store_true",
        help="Also import demo queue.json payments as checked payments in the signing queue.",
    )
    args = parser.parse_args(argv)

    try:
        summary = seed_database(reset=args.reset, with_queue=args.with_queue)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    print(
        f"Seeded {summary.db_path}: company={summary.company_id}, "
        f"users={summary.users_count}, signed_payments={summary.signed_payments_count}, "
        f"queue_payments={summary.queue_payments_count}, suppliers={summary.suppliers_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
