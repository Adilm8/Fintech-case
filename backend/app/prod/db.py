"""SQLite connection, transaction, and numbered SQL migration helpers."""

from __future__ import annotations

import re
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from fastapi import Request

from app.settings import load_settings

MIGRATIONS_DIR: Path = Path(__file__).resolve().parent / "migrations"
_MIGRATION_RE = re.compile(r"^(\d+)_.*\.sql$")


def _sql_lower(value: str | None) -> str:
    return value.casefold() if value is not None else ""


def connect(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Open a SQLite connection configured with WAL mode, foreign keys, and Row factory."""
    resolved = db_path if db_path is not None else load_settings().db_path
    path_str = str(resolved)
    if path_str != ":memory:":
        Path(resolved).parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(
        path_str,
        timeout=30.0,
        isolation_level=None,
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    conn.create_function("py_lower", 1, _sql_lower)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


@contextmanager
def tx(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Run statements inside a BEGIN IMMEDIATE transaction (or nested SAVEPOINT)."""
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
        except BaseException:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        else:
            if conn.in_transaction:
                conn.execute("COMMIT")
        return

    savepoint = f"sp_{uuid.uuid4().hex[:12]}"
    conn.execute(f"SAVEPOINT {savepoint}")
    try:
        yield conn
    except BaseException:
        conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
        conn.execute(f"RELEASE SAVEPOINT {savepoint}")
        raise
    else:
        conn.execute(f"RELEASE SAVEPOINT {savepoint}")


def _discover_migrations(migrations_dir: Path = MIGRATIONS_DIR) -> list[tuple[int, Path]]:
    found: list[tuple[int, Path]] = []
    if not migrations_dir.exists():
        return found
    for path in migrations_dir.iterdir():
        if not path.is_file():
            continue
        match = _MIGRATION_RE.match(path.name)
        if match is None:
            continue
        found.append((int(match.group(1)), path))
    found.sort(key=lambda item: (item[0], item[1].name))
    return found


def get_schema_version(conn: sqlite3.Connection) -> int:
    """Return current SQLite PRAGMA user_version."""
    row = conn.execute("PRAGMA user_version").fetchone()
    return int(row[0]) if row is not None else 0


def migrate(
    conn: sqlite3.Connection,
    *,
    migrations_dir: Path = MIGRATIONS_DIR,
) -> int:
    """Apply all pending NNN_*.sql migrations atomically and return final user_version."""
    current = get_schema_version(conn)
    for version, sql_path in _discover_migrations(migrations_dir):
        if version <= current:
            continue
        sql = sql_path.read_text(encoding="utf-8")
        wrapped = f"BEGIN IMMEDIATE;\n{sql}\nCOMMIT;"
        try:
            conn.executescript(wrapped)
        except BaseException:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        current = get_schema_version(conn)
        if current < version:
            conn.execute(f"PRAGMA user_version = {int(version)}")
            current = version
    return current


def get_db(request: Request) -> Iterator[sqlite3.Connection]:
    """FastAPI dependency providing a per-request SQLite connection."""
    db_path = getattr(request.app.state, "db_path", None)
    conn = connect(db_path)
    try:
        yield conn
    finally:
        conn.close()
