"""Tests for B3: ProdStore, serde, audit_db hash chain, directory, and seed."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

from app.prod.audit_db import GENESIS_HASH, append_audit, list_audit, verify_chain
from app.prod.db import connect, migrate, tx
from app.prod.directory import (
    lookup_supplier_ref,
    register_signed_payment,
    requisites_changed_days_ago,
)
from app.prod.prod_store import ProdStore, get_reference_store
from app.prod.security import utc_now_iso, verify_password
from app.prod.seed import seed_database
from app.prod.serde import dump_full, load_check_result
from app.risk.config import DEMO_TODAY, RULESET_VERSION
from app.risk.engine import check_payment, localize_check_result
from app.schemas import CheckRequest, compute_request_sha256
from app.settings import BACKEND_DIR, Settings
from app.store import DEFAULT_DATA_DIR, Store


def _queue_request(item: dict[str, Any]) -> CheckRequest:
    return CheckRequest(
        payer_id=item["payer_id"],
        recipient_name=item["recipient_name"],
        recipient_bin=item["recipient_bin"],
        recipient_iik=item["recipient_iik"],
        recipient_bik=item["recipient_bik"],
        amount_kzt=float(item["amount_kzt"]),
        purpose=item.get("purpose", ""),
        kbe=item.get("kbe", ""),
        knp=item.get("knp", ""),
    )


class TestSeedAndProdStore:
    def test_seed_refuses_to_run_outside_prod_mode(self, tmp_path: Path) -> None:
        db_file = tmp_path / "refused.db"
        with pytest.raises(RuntimeError, match="APP_MODE=prod"):
            seed_database(
                reset=True,
                db_path=db_file,
                settings_override=Settings(app_mode="demo", db_path=db_file),
            )
        assert not db_file.exists()

        env = {k: v for k, v in os.environ.items() if k != "APP_MODE"}
        env["SHIELD_DB_PATH"] = str(db_file)
        res = subprocess.run(
            [sys.executable, "-m", "app.prod.seed", "--reset"],
            cwd=str(BACKEND_DIR),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert res.returncode != 0
        assert "APP_MODE=prod" in res.stderr
        assert not db_file.exists()

    def test_seed_reset_creates_expected_counts_shifted_dates_and_verdicts(
        self, tmp_path: Path
    ) -> None:
        db_file = tmp_path / "seeded.db"
        today = date(2026, 11, 26)
        seed_pw = "Seed-Test-Password-1!"
        cfg = Settings(
            app_mode="prod",
            db_path=db_file,
            today_override=today,
            seed_password=seed_pw,
        )

        # Snapshot demo JSON file mtimes to verify seed is strictly read-only on demo data
        history_path = DEFAULT_DATA_DIR / "history.json"
        queue_path = DEFAULT_DATA_DIR / "queue.json"
        history_bytes_before = history_path.read_bytes()
        queue_bytes_before = queue_path.read_bytes()

        summary = seed_database(reset=True, with_queue=False, settings_override=cfg)
        assert summary.db_path == db_file
        assert summary.company_id == "client-technostroy"
        assert summary.users_count == 3
        assert summary.signed_payments_count == 150
        assert summary.queue_payments_count == 0
        assert summary.suppliers_count == 12
        assert summary.generated_password is False
        assert summary.password == seed_pw

        assert history_path.read_bytes() == history_bytes_before
        assert queue_path.read_bytes() == queue_bytes_before

        conn = connect(db_file)
        try:
            companies = conn.execute("SELECT * FROM companies").fetchall()
            assert len(companies) == 1
            company = companies[0]
            assert company["id"] == "client-technostroy"

            users = {r["login"]: r for r in conn.execute("SELECT * FROM users").fetchall()}
            assert set(users.keys()) == {"accountant", "director", "analyst"}
            assert users["accountant"]["company_id"] == "client-technostroy"
            assert users["director"]["company_id"] == "client-technostroy"
            assert users["analyst"]["company_id"] is None
            for u in users.values():
                assert str(u["password_hash"]).startswith("scrypt$15$8$1$")
                assert verify_password(seed_pw, str(u["password_hash"])) is True

            # Verify date shifting (today - DEMO_TODAY)
            raw_history = json.loads(history_path.read_text(encoding="utf-8"))["payments"]
            shift = (today - DEMO_TODAY).days
            orig_min = min(date.fromisoformat(p["paid_at"]) for p in raw_history)
            orig_max = max(date.fromisoformat(p["paid_at"]) for p in raw_history)
            db_dates = conn.execute(
                "SELECT MIN(paid_at) AS min_d, MAX(paid_at) AS max_d FROM payments WHERE status = 'signed'"
            ).fetchone()
            assert db_dates["min_d"] == (orig_min + timedelta(days=shift)).isoformat()
            assert db_dates["max_d"] == (orig_max + timedelta(days=shift)).isoformat()

            # Verify supplier directory was built chronologically (150846341552 switched accounts)
            sup_changes = conn.execute(
                """
                SELECT sc.kind, sc.old_value, sc.new_value
                FROM supplier_changes sc
                JOIN suppliers s ON s.id = sc.supplier_id
                WHERE s.bin = '150846341552'
                ORDER BY sc.id ASC
                """
            ).fetchall()
            kinds = [r["kind"] for r in sup_changes]
            assert "account_added" in kinds
            assert "bank_changed" in kinds

            # Compare ProdStore check_payment verdicts against demo Store for queue.json scenarios
            demo_store = Store()
            prod_store = ProdStore(conn, company, reference=get_reference_store(), today=today)
            assert prod_store.default_payer_id == "client-technostroy"
            assert prod_store.known_payer_ids == {"client-technostroy"}
            assert len(prod_store.history) == 150

            queue_items = json.loads(queue_path.read_text(encoding="utf-8"))
            by_id = {item["id"]: item for item in queue_items}
            for qid, expected_verdict in (
                ("Q-001", "green"),
                ("Q-002", "yellow"),
                ("Q-003", "red"),
                ("Q-004", "grey"),
                ("Q-007", "invalid"),
            ):
                req = _queue_request(by_id[qid])
                demo_res = check_payment(
                    req,
                    demo_store,
                    today=DEMO_TODAY,
                    include_recent_memory=False,
                )
                prod_res = check_payment(
                    req,
                    prod_store,
                    today=today,
                    include_recent_memory=False,
                )
                assert demo_res.verdict == expected_verdict
                assert prod_res.verdict == demo_res.verdict, (
                    f"{qid}: prod verdict {prod_res.verdict} != demo {demo_res.verdict}"
                )

            # reload() / reset() must raise NotImplementedError
            with pytest.raises(NotImplementedError):
                prod_store.reload()
            with pytest.raises(NotImplementedError):
                prod_store.reset()
        finally:
            conn.close()

    def test_seed_with_queue_and_cli_generated_password(self, tmp_path: Path) -> None:
        db_file = tmp_path / "cli_seeded.db"
        env = {
            **os.environ,
            "APP_MODE": "prod",
            "SHIELD_DB_PATH": str(db_file),
            "SHIELD_TODAY": "2026-11-26",
        }
        env.pop("SHIELD_SEED_PASSWORD", None)

        res = subprocess.run(
            [sys.executable, "-m", "app.prod.seed", "--reset", "--with-queue"],
            cwd=str(BACKEND_DIR),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert res.returncode == 0, res.stderr
        assert "signed_payments=150" in res.stdout
        assert "queue_payments=10" in res.stdout
        assert "suppliers=12" in res.stdout
        assert "Generated seed password" in res.stdout

        conn = connect(db_file)
        try:
            checked_rows = conn.execute(
                """
                SELECT p.id, c.verdict, c.result_json
                FROM payments p
                JOIN checks c ON c.id = p.check_id
                WHERE p.status = 'checked'
                ORDER BY p.line_no ASC
                """
            ).fetchall()
            assert len(checked_rows) == 10
            verdicts = {r["id"]: r["verdict"] for r in checked_rows}
            assert verdicts["pay-q-001"] == "green"
            assert verdicts["pay-q-002"] == "yellow"
            assert verdicts["pay-q-003"] == "red"
            assert verdicts["pay-q-004"] == "grey"
            assert verdicts["pay-q-007"] == "invalid"

            # Verify stored checks deserialize & re-localize cleanly
            red_row = next(r for r in checked_rows if r["id"] == "pay-q-003")
            loaded_red = load_check_result(red_row["result_json"])
            assert loaded_red.verdict == "red"
            assert loaded_red.internal_analyst_details is not None
            assert loaded_red.analyst_details is None

            # Verify audit chain created by --with-queue is valid
            verify = verify_chain(conn)
            assert verify.ok is True
            assert verify.checked == 10
            assert verify.broken_at is None
        finally:
            conn.close()

    def test_prod_store_trust_and_recent_checks_isolation(self, tmp_path: Path) -> None:
        db_file = tmp_path / "store_ops.db"
        today = date(2026, 11, 26)
        cfg = Settings(
            app_mode="prod",
            db_path=db_file,
            today_override=today,
            seed_password="Seed-Password-2!",
        )
        seed_database(reset=True, settings_override=cfg)

        conn = connect(db_file)
        try:
            company = conn.execute("SELECT * FROM companies LIMIT 1").fetchone()
            director = conn.execute("SELECT id FROM users WHERE role = 'director'").fetchone()
            accountant = conn.execute("SELECT id FROM users WHERE role = 'accountant'").fetchone()
            assert company is not None and director is not None and accountant is not None

            prod_store = ProdStore(conn, company, reference=get_reference_store(), today=today)

            # Q-002 starts yellow; trusting its account makes it green
            queue_items = json.loads((DEFAULT_DATA_DIR / "queue.json").read_text(encoding="utf-8"))
            q2 = _queue_request(next(item for item in queue_items if item["id"] == "Q-002"))
            before = check_payment(q2, prod_store, today=today, include_recent_memory=False)
            assert before.verdict == "yellow"

            prod_store.trust_account(
                q2.recipient_bin,
                q2.recipient_iik,
                director_comment="Подтвердили по телефону из договора",
                decided_by=int(director["id"]),
            )
            assert prod_store.is_trusted(q2.recipient_bin, q2.recipient_iik) is True
            assert prod_store.is_bin_trusted(q2.recipient_bin) is True
            assert (company["id"], q2.recipient_bin, q2.recipient_iik) in prod_store.trusted_accounts

            after = check_payment(q2, prod_store, today=today, include_recent_memory=False)
            assert after.verdict == "green"
            assert after.trusted is True

            # Revoking trust returns verdict to yellow
            with tx(conn):
                conn.execute(
                    "UPDATE trusted_accounts SET revoked_at = ?, revoked_by = ?",
                    (utc_now_iso(), int(director["id"])),
                )
            assert prod_store.is_trusted(q2.recipient_bin, q2.recipient_iik) is False
            after_revoke = check_payment(q2, prod_store, today=today, include_recent_memory=False)
            assert after_revoke.verdict == "yellow"

            # Short-term memory via active unsigned payments triggers duplicate_invoice
            q4 = _queue_request(next(item for item in queue_items if item["id"] == "Q-004"))
            q4_sha = compute_request_sha256(q4, resolved_payer_id=company["id"])
            created_ts = f"{today.isoformat()}T10:00:00+00:00"
            with tx(conn):
                conn.execute(
                    """
                    INSERT INTO payments (
                        id, company_id, source, recipient_name, recipient_bin, recipient_iik,
                        recipient_bik, amount_tiyn, purpose, kbe, knp, request_sha256,
                        status, created_by, created_at, updated_at
                    ) VALUES (
                        'pay-active-1', ?, 'manual', ?, ?, ?, ?, ?, ?, '', '', ?,
                        'checked', ?, ?, ?
                    )
                    """,
                    (
                        company["id"],
                        q4.recipient_name,
                        q4.recipient_bin,
                        q4.recipient_iik,
                        q4.recipient_bik,
                        round(q4.amount_kzt * 100),
                        q4.purpose,
                        q4_sha,
                        int(accountant["id"]),
                        created_ts,
                        created_ts,
                    ),
                )

            # Same request excluded by exclude_request_sha256 -> no duplicate
            same_check = check_payment(q4, prod_store, today=today, include_recent_memory=True)
            assert "duplicate_invoice" not in {s.rule_id for s in same_check.signals}

            # Different amount with the same invoice number in purpose -> triggers duplicate_invoice
            q4_dup = q4.model_copy(update={"amount_kzt": q4.amount_kzt + 1000})
            dup_check = check_payment(q4_dup, prod_store, today=today, include_recent_memory=True)
            assert "duplicate_invoice" in {s.rule_id for s in dup_check.signals}

            # Foreign payer_id gets empty history and recent checks
            assert prod_store.get_client_history("other-company") == []
            assert prod_store.get_recent_checks(q4.recipient_bin, "other-company") == []
        finally:
            conn.close()


class TestCheckResultSerde:
    def test_dump_full_and_load_relocalize_and_gate_analyst_details(self) -> None:
        ref = Store()
        queue_items = json.loads((DEFAULT_DATA_DIR / "queue.json").read_text(encoding="utf-8"))
        q3 = _queue_request(next(item for item in queue_items if item["id"] == "Q-003"))
        q7 = _queue_request(next(item for item in queue_items if item["id"] == "Q-007"))

        raw_red = check_payment(
            q3,
            ref,
            today=DEMO_TODAY,
            lang="ru",
            include_analyst_details=False,
            include_recent_memory=False,
        )
        assert raw_red.verdict == "red"
        assert raw_red.analyst_details is None
        assert raw_red.internal_analyst_details is not None
        assert raw_red.internal_analyst_details.bcc_account is not None
        assert len(raw_red.internal_analyst_details.signal_details) >= 1

        serialized = dump_full(raw_red)
        loaded = load_check_result(serialized)
        assert loaded.verdict == "red"
        assert loaded.headline_key == raw_red.headline_key
        assert loaded.analyst_details is None
        assert loaded.internal_analyst_details is not None

        for lang in ("kk", "en"):
            direct = check_payment(
                q3,
                ref,
                today=DEMO_TODAY,
                lang=lang,
                include_analyst_details=False,
                include_recent_memory=False,
            )
            client_view = localize_check_result(loaded, lang, include_analyst_details=False)
            assert client_view.headline == direct.headline
            assert client_view.headline != client_view.headline_ru
            assert client_view.next_action.text == direct.next_action.text
            assert [s.reason for s in client_view.signals] == [s.reason for s in direct.signals]
            assert client_view.analyst_details is None

            client_dumped = client_view.model_dump()
            assert "analyst_details" not in client_dumped
            assert "internal_analyst_details" not in client_dumped
            assert "headline_key" not in client_dumped

            direct_analyst = check_payment(
                q3,
                ref,
                today=DEMO_TODAY,
                lang=lang,
                include_analyst_details=True,
                include_recent_memory=False,
            )
            analyst_view = localize_check_result(loaded, lang, include_analyst_details=True)
            assert analyst_view.analyst_details is not None
            assert analyst_view.analyst_details.bcc_account is not None
            assert direct_analyst.analyst_details is not None
            assert [sd.reason for sd in analyst_view.analyst_details.signal_details] == [
                sd.reason for sd in direct_analyst.analyst_details.signal_details
            ]

            analyst_dumped = analyst_view.model_dump()
            assert "analyst_details" in analyst_dumped
            assert "internal_analyst_details" not in analyst_dumped

        # Invalid verdict preserves invalid_field_keys for re-localization
        raw_inv = check_payment(q7, ref, today=DEMO_TODAY, lang="ru", include_recent_memory=False)
        loaded_inv = load_check_result(dump_full(raw_inv))
        inv_en = localize_check_result(loaded_inv, "en", include_analyst_details=False)
        inv_kk = localize_check_result(loaded_inv, "kk", include_analyst_details=False)
        assert inv_en.next_action.text != raw_inv.next_action.text_ru
        assert inv_kk.next_action.text != raw_inv.next_action.text_ru
        assert "IIK" in inv_en.next_action.text


class TestSupplierDirectory:
    def test_register_signed_payment_tracks_accounts_bank_and_name_changes(
        self, tmp_path: Path
    ) -> None:
        conn = connect(tmp_path / "dir.db")
        try:
            migrate(conn)
            ts = "2026-11-26T00:00:00+00:00"
            with tx(conn):
                conn.execute(
                    "INSERT INTO companies (id, name, bin, iik, bik, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    ("c1", "ТОО Альфа", "170346704876", "KZ12856KZT1721175500", "KCJBKZKX", ts),
                )

            # 1. First payment -> creates supplier & account, no changes
            sup_id = register_signed_payment(
                conn,
                company_id="c1",
                recipient_bin="160542439625",
                recipient_name="ТОО «Алатау Снаб»",
                recipient_iik="KZ246010005016525808",
                recipient_bik="HSBKKZKX",
                paid_at="2026-09-01",
            )
            sup = conn.execute("SELECT * FROM suppliers WHERE id = ?", (sup_id,)).fetchone()
            assert sup["first_seen_at"] == "2026-09-01"
            assert sup["last_payment_at"] == "2026-09-01"
            assert sup["requisites_changed_at"] is None
            assert conn.execute("SELECT COUNT(*) FROM supplier_changes").fetchone()[0] == 0

            # 2. Repeat payment to same IIK -> increments count, still no changes
            register_signed_payment(
                conn,
                company_id="c1",
                recipient_bin="160542439625",
                recipient_name="ТОО «Алатау Снаб»",
                recipient_iik="KZ246010005016525808",
                recipient_bik="HSBKKZKX",
                paid_at="2026-10-01",
            )
            acc1 = conn.execute(
                "SELECT payments_count, last_used_at FROM supplier_accounts WHERE supplier_id = ?",
                (sup_id,),
            ).fetchone()
            assert acc1["payments_count"] == 2
            assert acc1["last_used_at"] == "2026-10-01"
            assert conn.execute("SELECT COUNT(*) FROM supplier_changes").fetchone()[0] == 0

            # 3. New IIK in a different bank -> account_added + bank_changed + requisites_changed_at
            register_signed_payment(
                conn,
                company_id="c1",
                recipient_bin="160542439625",
                recipient_name="ТОО «Алатау Снаб»",
                recipient_iik="KZ509650006872032298",
                recipient_bik="IRTYKZKA",
                paid_at="2026-11-16",
            )
            changes = conn.execute(
                "SELECT kind, old_value, new_value, occurred_at FROM supplier_changes ORDER BY id ASC"
            ).fetchall()
            assert [(c["kind"], c["old_value"], c["new_value"]) for c in changes] == [
                ("account_added", "KZ246010005016525808", "KZ509650006872032298"),
                ("bank_changed", "HSBKKZKX", "IRTYKZKA"),
            ]
            sup = conn.execute("SELECT * FROM suppliers WHERE id = ?", (sup_id,)).fetchone()
            assert sup["requisites_changed_at"] == "2026-11-16"
            assert requisites_changed_days_ago(sup["requisites_changed_at"], date(2026, 11, 26)) == 10

            # 4. Name change with existing IIK -> name_changed only, does NOT affect requisites_changed_at
            register_signed_payment(
                conn,
                company_id="c1",
                recipient_bin="160542439625",
                recipient_name="  ТОО «Алатау Снаб Плюс»  ",
                recipient_iik="KZ509650006872032298",
                recipient_bik="IRTYKZKA",
                paid_at="2026-11-20",
            )
            sup = conn.execute("SELECT * FROM suppliers WHERE id = ?", (sup_id,)).fetchone()
            assert sup["name"] == "ТОО «Алатау Снаб Плюс»"
            assert sup["requisites_changed_at"] == "2026-11-16"
            assert sup["last_payment_at"] == "2026-11-20"
            last_change = conn.execute(
                "SELECT kind, old_value, new_value FROM supplier_changes ORDER BY id DESC LIMIT 1"
            ).fetchone()
            assert (last_change["kind"], last_change["old_value"], last_change["new_value"]) == (
                "name_changed",
                "ТОО «Алатау Снаб»",
                "ТОО «Алатау Снаб Плюс»",
            )

            # 5. lookup_supplier_ref reports known / account_known / days ago accurately
            known_ref = lookup_supplier_ref(
                conn,
                company_id="c1",
                recipient_bin="160542439625",
                recipient_iik="KZ509650006872032298",
                today=date(2026, 11, 26),
            )
            assert known_ref == {
                "id": sup_id,
                "known": True,
                "account_known": True,
                "requisites_changed_days_ago": 10,
            }
            pending_iik_ref = lookup_supplier_ref(
                conn,
                company_id="c1",
                recipient_bin="160542439625",
                recipient_iik="KZ75856KZT9103291175",
                today=date(2026, 11, 26),
            )
            assert pending_iik_ref["known"] is True
            assert pending_iik_ref["account_known"] is False
            unknown_ref = lookup_supplier_ref(
                conn,
                company_id="c1",
                recipient_bin="210844188013",
                recipient_iik="KZ327220003914781165",
                today=date(2026, 11, 26),
            )
            assert unknown_ref == {
                "id": None,
                "known": False,
                "account_known": False,
                "requisites_changed_days_ago": None,
            }
        finally:
            conn.close()


class TestAuditChain:
    def test_append_list_verify_and_detect_tampering_in_db_copy(self, tmp_path: Path) -> None:
        orig_db = tmp_path / "audit_orig.db"
        conn = connect(orig_db)
        try:
            migrate(conn)
            assert verify_chain(conn).model_dump() == {"ok": True, "checked": 0, "broken_at": None}

            id1 = append_audit(
                conn,
                action="login",
                user_id=1,
                user_login="accountant",
                role="accountant",
                company_id="comp-a",
            )
            id2 = append_audit(
                conn,
                action="check",
                user_id=1,
                user_login="accountant",
                role="accountant",
                company_id="comp-a",
                payment_id="pay-1",
                check_id="chk-1",
                request_sha256="a" * 64,
                ruleset_version=RULESET_VERSION,
                verdict="yellow",
                signal_ids=["iik_changed", "bank_changed"],
                details={"source": "manual"},
            )
            id3 = append_audit(
                conn,
                action="sign_denied",
                user_id=1,
                user_login="accountant",
                role="accountant",
                company_id="comp-a",
                payment_id="pay-1",
                verdict="yellow",
                details={"code": "ack_or_approval_required"},
            )
            assert [id1, id2, id3] == [1, 2, 3]

            # Genesis prev_hash is 64 zeros
            row1 = conn.execute("SELECT prev_hash, entry_hash FROM audit_log WHERE id = 1").fetchone()
            row2 = conn.execute("SELECT prev_hash, entry_hash FROM audit_log WHERE id = 2").fetchone()
            assert row1["prev_hash"] == GENESIS_HASH
            assert row2["prev_hash"] == row1["entry_hash"]

            # Chain is valid
            ok_res = verify_chain(conn)
            assert ok_res.ok is True
            assert ok_res.checked == 3
            assert ok_res.broken_at is None

            # list_audit returns newest first and respects filters
            all_entries = list_audit(conn, company_id="comp-a")
            assert [e.id for e in all_entries] == [3, 2, 1]
            assert all_entries[1].signal_ids == ["iik_changed", "bank_changed"]
            assert all_entries[0].details == {"code": "ack_or_approval_required"}

            filtered = list_audit(conn, payment_id="pay-1", action="sign_denied")
            assert [e.id for e in filtered] == [3]
            assert list_audit(conn, company_id="other-comp") == []
        finally:
            conn.close()

        # Tamper with row 2 in a copy of the DB -> verify_chain reports broken_at=2
        copy_db = tmp_path / "audit_tampered.db"
        shutil.copy2(orig_db, copy_db)
        tamper_conn = connect(copy_db)
        try:
            tamper_conn.execute("DROP TRIGGER audit_no_update")
            tamper_conn.execute("UPDATE audit_log SET verdict = 'green' WHERE id = 2")
            tampered = verify_chain(tamper_conn)
            assert tampered.ok is False
            assert tampered.broken_at == 2
        finally:
            tamper_conn.close()

        # Delete row 2 in another copy -> verify_chain reports broken_at=3 (prev_hash mismatch)
        copy_del = tmp_path / "audit_deleted.db"
        shutil.copy2(orig_db, copy_del)
        del_conn = connect(copy_del)
        try:
            del_conn.execute("DROP TRIGGER audit_no_delete")
            del_conn.execute("DELETE FROM audit_log WHERE id = 2")
            broken_del = verify_chain(del_conn)
            assert broken_del.ok is False
            assert broken_del.broken_at == 3
        finally:
            del_conn.close()
