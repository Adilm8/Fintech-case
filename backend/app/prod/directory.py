"""Confirmed supplier directory maintained strictly on signed payments (§8)."""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import Any

from app.prod.db import tx
from app.schemas import clean_text_field, normalize_requisite


def requisites_changed_days_ago(
    requisites_changed_at: str | None,
    today: date,
) -> int | None:
    """Return days elapsed between requisites_changed_at and today, or None if never changed."""
    if not requisites_changed_at:
        return None
    try:
        changed_dt = date.fromisoformat(requisites_changed_at[:10])
    except ValueError:
        return None
    return max(0, (today - changed_dt).days)


def register_signed_payment(
    conn: sqlite3.Connection,
    *,
    company_id: str,
    recipient_bin: str,
    recipient_name: str,
    recipient_iik: str,
    recipient_bik: str,
    paid_at: str,
    payment_id: str | None = None,
) -> int:
    """Update suppliers, supplier_accounts, and supplier_changes for a signed payment.

    Rules (§8):
    1. Unknown (company, bin): create supplier and account; emit no change event.
    2. Known supplier, new IIK: add account, emit 'account_added' (old_value = last used IIK),
       and emit 'bank_changed' if BIK changed vs last used account; update requisites_changed_at.
    3. Different cleaned name vs stored: emit 'name_changed' and update supplier name;
       does not touch requisites_changed_at.
    4. Update last_payment_at, last_used_at, and payment counters.
    """
    norm_bin = normalize_requisite(recipient_bin)
    norm_iik = normalize_requisite(recipient_iik)
    norm_bik = normalize_requisite(recipient_bik)
    cleaned_name = clean_text_field(recipient_name)
    paid_at_str = str(paid_at)

    with tx(conn):
        sup = conn.execute(
            "SELECT * FROM suppliers WHERE company_id = ? AND bin = ?",
            (company_id, norm_bin),
        ).fetchone()

        if sup is None:
            cur = conn.execute(
                """
                INSERT INTO suppliers (
                    company_id, bin, name, first_seen_at, last_payment_at, requisites_changed_at
                ) VALUES (?, ?, ?, ?, ?, NULL)
                """,
                (company_id, norm_bin, cleaned_name, paid_at_str, paid_at_str),
            )
            assert cur.lastrowid is not None
            supplier_id = int(cur.lastrowid)
            conn.execute(
                """
                INSERT INTO supplier_accounts (
                    supplier_id, iik, bik, first_seen_at, last_used_at, payments_count
                ) VALUES (?, ?, ?, ?, ?, 1)
                """,
                (supplier_id, norm_iik, norm_bik, paid_at_str, paid_at_str),
            )
            return supplier_id

        supplier_id = int(sup["id"])
        existing_acc = conn.execute(
            "SELECT * FROM supplier_accounts WHERE supplier_id = ? AND iik = ?",
            (supplier_id, norm_iik),
        ).fetchone()

        new_req_changed_at: str | None = (
            str(sup["requisites_changed_at"]) if sup["requisites_changed_at"] is not None else None
        )

        if existing_acc is None:
            last_acc = conn.execute(
                """
                SELECT iik, bik
                FROM supplier_accounts
                WHERE supplier_id = ?
                ORDER BY last_used_at DESC, id DESC
                LIMIT 1
                """,
                (supplier_id,),
            ).fetchone()
            old_iik = str(last_acc["iik"]) if last_acc is not None else None
            old_bik = str(last_acc["bik"]) if last_acc is not None else None

            conn.execute(
                """
                INSERT INTO supplier_accounts (
                    supplier_id, iik, bik, first_seen_at, last_used_at, payments_count
                ) VALUES (?, ?, ?, ?, ?, 1)
                """,
                (supplier_id, norm_iik, norm_bik, paid_at_str, paid_at_str),
            )
            conn.execute(
                """
                INSERT INTO supplier_changes (
                    supplier_id, kind, old_value, new_value, occurred_at, payment_id
                ) VALUES (?, 'account_added', ?, ?, ?, ?)
                """,
                (supplier_id, old_iik, norm_iik, paid_at_str, payment_id),
            )
            if old_bik is not None and old_bik != norm_bik:
                conn.execute(
                    """
                    INSERT INTO supplier_changes (
                        supplier_id, kind, old_value, new_value, occurred_at, payment_id
                    ) VALUES (?, 'bank_changed', ?, ?, ?, ?)
                    """,
                    (supplier_id, old_bik, norm_bik, paid_at_str, payment_id),
                )
            if new_req_changed_at is None or paid_at_str >= new_req_changed_at:
                new_req_changed_at = paid_at_str
        else:
            prev_used = str(existing_acc["last_used_at"])
            updated_used = max(paid_at_str, prev_used)
            conn.execute(
                """
                UPDATE supplier_accounts
                SET last_used_at = ?, payments_count = payments_count + 1
                WHERE id = ?
                """,
                (updated_used, int(existing_acc["id"])),
            )

        stored_name = clean_text_field(str(sup["name"]))
        updated_name = str(sup["name"])
        if cleaned_name and cleaned_name != stored_name:
            conn.execute(
                """
                INSERT INTO supplier_changes (
                    supplier_id, kind, old_value, new_value, occurred_at, payment_id
                ) VALUES (?, 'name_changed', ?, ?, ?, ?)
                """,
                (supplier_id, str(sup["name"]), cleaned_name, paid_at_str, payment_id),
            )
            updated_name = cleaned_name

        prev_last_payment = (
            str(sup["last_payment_at"]) if sup["last_payment_at"] is not None else None
        )
        updated_last_payment = (
            paid_at_str
            if prev_last_payment is None or paid_at_str >= prev_last_payment
            else prev_last_payment
        )
        conn.execute(
            """
            UPDATE suppliers
            SET name = ?, last_payment_at = ?, requisites_changed_at = ?
            WHERE id = ?
            """,
            (updated_name, updated_last_payment, new_req_changed_at, supplier_id),
        )
        return supplier_id


def lookup_supplier_ref(
    conn: sqlite3.Connection,
    *,
    company_id: str,
    recipient_bin: str,
    recipient_iik: str,
    today: date,
) -> dict[str, Any]:
    """Compute SupplierRef fields for a payment against confirmed directory state."""
    norm_bin = normalize_requisite(recipient_bin)
    norm_iik = normalize_requisite(recipient_iik)
    sup = conn.execute(
        "SELECT id, requisites_changed_at FROM suppliers WHERE company_id = ? AND bin = ?",
        (company_id, norm_bin),
    ).fetchone()
    if sup is None:
        return {
            "id": None,
            "known": False,
            "account_known": False,
            "requisites_changed_days_ago": None,
        }
    supplier_id = int(sup["id"])
    acc = conn.execute(
        "SELECT 1 FROM supplier_accounts WHERE supplier_id = ? AND iik = ? LIMIT 1",
        (supplier_id, norm_iik),
    ).fetchone()
    req_changed_at = (
        str(sup["requisites_changed_at"]) if sup["requisites_changed_at"] is not None else None
    )
    return {
        "id": supplier_id,
        "known": True,
        "account_known": acc is not None,
        "requisites_changed_days_ago": requisites_changed_days_ago(req_changed_at, today),
    }
