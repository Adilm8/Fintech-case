"""Tests for B6: 1C and CSV importers, encodings, sample files, duplicates, and import API."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.prod.app import create_prod_app
from app.prod.audit_db import list_audit, verify_chain
from app.prod.db import connect
from app.prod.deps import CSRF_HEADER_NAME, CSRF_HEADER_VALUE
from app.prod.importers import (
    MAX_IMPORT_BYTES,
    MAX_IMPORT_DOCUMENTS,
    EmptyFileError,
    UnsupportedFileError,
    parse_1c,
    parse_amount,
    parse_csv,
    parse_date,
)
from app.settings import Settings
from app.store import DEFAULT_DATA_DIR
from tests.prod.conftest import TEST_SEED_PW, TEST_TODAY

CSRF: dict[str, str] = {CSRF_HEADER_NAME: CSRF_HEADER_VALUE}
OCTET_HEADERS: dict[str, str] = {
    **CSRF,
    "Content-Type": "application/octet-stream",
}
SAMPLES_DIR: Path = DEFAULT_DATA_DIR / "samples"
EXPECTED_SAMPLE_VERDICTS: list[str] = ["green", "yellow", "red", "grey", "invalid"]


def _login(client: TestClient, login: str, password: str = TEST_SEED_PW) -> None:
    resp = client.post(
        "/api/v1/auth/login",
        json={"login": login, "password": password},
        headers=CSRF,
    )
    assert resp.status_code == 200, resp.text


@pytest.fixture
def import_env(seeded_db: Path) -> Iterator[tuple[FastAPI, Path, TestClient]]:
    cfg = Settings(
        app_mode="prod",
        db_path=seeded_db,
        today_override=TEST_TODAY,
        cookie_secure=False,
    )
    prod_app = create_prod_app(db_path=seeded_db, settings_override=cfg)
    with TestClient(prod_app) as client:
        _login(client, "accountant")
        yield prod_app, seeded_db, client


class TestImportersUnit:
    def test_parse_amount_and_date_variants(self) -> None:
        assert parse_amount("1360000.00") == 1_360_000.0
        assert parse_amount("1 360 000,00") == 1_360_000.0
        assert parse_amount("1\u00a0360\u00a0000,50") == 1_360_000.5
        assert parse_amount("1,360,000.25") == 1_360_000.25
        assert parse_amount("0") is None
        assert parse_amount("-500") is None
        assert parse_amount("not-a-number") is None
        assert parse_amount("") is None

        assert parse_date("26.11.2026") == "2026-11-26"
        assert parse_date("2026-11-26") == "2026-11-26"
        assert parse_date("32.13.2026") is None
        assert parse_date("") is None

    def test_sample_1c_is_cp1251_and_same_in_utf8_and_cp866(self) -> None:
        raw_cp1251 = (SAMPLES_DIR / "sample_1c.txt").read_bytes()

        # Verify file on disk is genuine cp1251 (not UTF-8)
        with pytest.raises(UnicodeDecodeError):
            raw_cp1251.decode("utf-8")

        text = raw_cp1251.decode("cp1251")
        parsed_cp1251 = parse_1c(raw_cp1251)
        assert parsed_cp1251.encoding == "cp1251"
        assert len(parsed_cp1251.docs) == 5
        assert len(parsed_cp1251.errors) == 1
        assert parsed_cp1251.errors[0].code == "unsupported_document_type"
        # Multi-line НазначениеПлатежа1..2 concatenated on doc 103
        doc_103 = next(d for d in parsed_cp1251.docs if d.doc_number == "103")
        assert "срочно" in doc_103.purpose
        assert "оборудования" in doc_103.purpose

        # Re-encode identical text into utf-8, utf-8-sig, and cp866 (with & without DOS hint)
        for label, payload, expected_enc in (
            ("utf-8", text.encode("utf-8"), "utf-8-sig"),
            ("utf-8-bom", text.encode("utf-8-sig"), "utf-8-sig"),
            ("cp866-unchanged-hint", text.encode("cp866"), "cp866"),
            (
                "cp866-dos-hint",
                text.replace("Кодировка=Windows", "Кодировка=DOS").encode("cp866"),
                "cp866",
            ),
        ):
            parsed_other = parse_1c(payload)
            assert parsed_other.encoding == expected_enc, label
            assert parsed_other.docs == parsed_cp1251.docs, label
            assert parsed_other.errors == parsed_cp1251.errors, label

    def test_csv_semicolon_and_comma_and_max_documents_limit(self) -> None:
        raw_semi = (SAMPLES_DIR / "sample.csv").read_bytes()
        parsed_semi = parse_csv(raw_semi)
        assert parsed_semi.source == "csv"
        assert len(parsed_semi.docs) == 5
        assert parsed_semi.errors == []

        comma_csv = (
            "recipient_name,recipient_bin,recipient_iik,recipient_bik,amount_kzt,purpose,doc_number,doc_date\n"
            '"ТОО ""Алатау Снаб""",160542439625,KZ246010005016525808,HSBKKZKX,1360000.00,'
            '"Оплата за материалы, счет № 801",C-1,2026-11-26\n'
        ).encode()
        parsed_comma = parse_csv(comma_csv)
        assert len(parsed_comma.docs) == 1
        assert parsed_comma.docs[0].recipient_name == 'ТОО "Алатау Снаб"'
        assert parsed_comma.docs[0].purpose == "Оплата за материалы, счет № 801"
        assert parsed_comma.docs[0].doc_date == "2026-11-26"

        # > 500 documents: first 500 parsed, extras reported as too_many_documents
        header = "recipient_name;recipient_bin;recipient_iik;recipient_bik;amount_kzt;doc_number\n"
        row = "ТОО Тест;160542439625;KZ246010005016525808;HSBKKZKX;10000;D-{i}\n"
        big_csv = (header + "".join(row.format(i=i) for i in range(MAX_IMPORT_DOCUMENTS + 3))).encode("utf-8")
        parsed_big = parse_csv(big_csv)
        assert len(parsed_big.docs) == MAX_IMPORT_DOCUMENTS
        assert len(parsed_big.errors) == 3
        assert all(e.code == "too_many_documents" for e in parsed_big.errors)

        with pytest.raises(EmptyFileError):
            parse_csv(header.encode("utf-8"))
        with pytest.raises(UnsupportedFileError):
            parse_csv(b"col1;col2\nval1;val2\n")


class TestImportAPI:
    def test_import_sample_1c_cp1251_verdicts_audit_batches_and_duplicates(
        self, import_env: tuple[FastAPI, Path, TestClient]
    ) -> None:
        _, db_path, client = import_env
        raw_cp1251 = (SAMPLES_DIR / "sample_1c.txt").read_bytes()

        resp = client.post(
            "/api/v1/payments/import?filename=sample_1c.txt",
            content=raw_cp1251,
            headers=OCTET_HEADERS,
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()

        assert data["batch"]["source"] == "1c"
        assert data["batch"]["filename"] == "sample_1c.txt"
        assert data["batch"]["total"] == 6
        assert data["batch"]["created_count"] == 5
        assert data["batch"]["failed_count"] == 1

        assert len(data["items"]) == 5
        assert [item["check"]["verdict"] for item in data["items"]] == EXPECTED_SAMPLE_VERDICTS
        assert [item["doc_number"] for item in data["items"]] == ["101", "102", "103", "104", "105"]
        assert all(item["duplicate_of"] is None for item in data["items"])
        assert all(item["source"] == "1c" for item in data["items"])

        assert len(data["errors"]) == 1
        assert data["errors"][0]["code"] == "unsupported_document_type"
        assert data["errors"][0]["doc_number"] == "106"

        assert data["summary"] == {
            "total": 6,
            "created": 5,
            "failed": 1,
            "duplicates": 0,
            "by_verdict": {"green": 1, "yellow": 1, "red": 1, "grey": 1, "invalid": 1},
        }

        batch_id = data["batch"]["id"]
        first_ids = [item["id"] for item in data["items"]]

        # GET /api/v1/batches & GET /api/v1/payments?batch_id=...
        batches = client.get("/api/v1/batches").json()
        assert len(batches) == 1
        assert batches[0]["id"] == batch_id

        by_batch = client.get(f"/api/v1/payments?batch_id={batch_id}").json()
        assert by_batch["total"] == 5

        # Repeat upload without force=1 -> 409 duplicate_file
        dup_resp = client.post(
            "/api/v1/payments/import?filename=sample_1c.txt",
            content=raw_cp1251,
            headers=OCTET_HEADERS,
        )
        assert dup_resp.status_code == 409
        assert dup_resp.json()["code"] == "duplicate_file"

        # Repeat upload WITH force=1 -> 201, all 5 items have duplicate_of pointing to batch 1
        forced_resp = client.post(
            "/api/v1/payments/import?filename=sample_1c.txt&force=1",
            content=raw_cp1251,
            headers=OCTET_HEADERS,
        )
        assert forced_resp.status_code == 201, forced_resp.text
        forced = forced_resp.json()
        assert forced["batch"]["id"] != batch_id
        assert forced["summary"]["duplicates"] == 5
        assert [item["duplicate_of"] for item in forced["items"]] == first_ids

        # Repeat upload without force=1 STILL returns 409 duplicate_file
        dup_again = client.post(
            "/api/v1/payments/import?filename=sample_1c.txt",
            content=raw_cp1251,
            headers=OCTET_HEADERS,
        )
        assert dup_again.status_code == 409
        assert dup_again.json()["code"] == "duplicate_file"

        # Verify import_batches (is_forced 0 & 1) and audit_log (import + check entries) + valid chain
        conn = connect(db_path)
        try:
            b_rows = conn.execute(
                "SELECT id, is_forced, file_sha256, created_count, failed_count FROM import_batches ORDER BY rowid ASC"
            ).fetchall()
            assert len(b_rows) == 2
            assert b_rows[0]["is_forced"] == 0
            assert b_rows[1]["is_forced"] == 1
            assert b_rows[0]["file_sha256"] == b_rows[1]["file_sha256"]

            import_audits = list_audit(conn, action="import")
            assert len(import_audits) == 2
            check_audits = list_audit(conn, action="check")
            assert len(check_audits) == 10
            assert verify_chain(conn).ok is True
        finally:
            conn.close()

    @pytest.mark.parametrize("encoding", ["utf-8", "cp866"])
    def test_import_sample_1c_in_utf8_and_cp866_gives_same_verdicts(
        self,
        seeded_db: Path,
        encoding: str,
    ) -> None:
        cfg = Settings(
            app_mode="prod",
            db_path=seeded_db,
            today_override=TEST_TODAY,
            cookie_secure=False,
        )
        prod_app = create_prod_app(db_path=seeded_db, settings_override=cfg)
        raw_text = (SAMPLES_DIR / "sample_1c.txt").read_bytes().decode("cp1251")
        encoded_bytes = raw_text.encode(encoding)

        with TestClient(prod_app) as client:
            _login(client, "accountant")
            resp = client.post(
                f"/api/v1/payments/import?filename=sample_{encoding}.txt",
                content=encoded_bytes,
                headers=OCTET_HEADERS,
            )
            assert resp.status_code == 201, resp.text
            data = resp.json()
            assert [item["check"]["verdict"] for item in data["items"]] == EXPECTED_SAMPLE_VERDICTS
            assert len(data["errors"]) == 1
            assert data["errors"][0]["code"] == "unsupported_document_type"

    def test_import_csv_semicolon_comma_and_multipart_stdlib(
        self, import_env: tuple[FastAPI, Path, TestClient]
    ) -> None:
        _, _, client = import_env

        # 1. Sample CSV with ';' delimiter
        raw_csv = (SAMPLES_DIR / "sample.csv").read_bytes()
        r_semi = client.post(
            "/api/v1/payments/import?filename=sample.csv",
            content=raw_csv,
            headers=OCTET_HEADERS,
        )
        assert r_semi.status_code == 201, r_semi.text
        d_semi = r_semi.json()
        assert d_semi["batch"]["source"] == "csv"
        assert [item["check"]["verdict"] for item in d_semi["items"]] == EXPECTED_SAMPLE_VERDICTS
        assert d_semi["errors"] == []

        # 2. Comma-delimited CSV with duplicate row + invalid amount row
        comma_csv = (
            "recipient_name,recipient_bin,recipient_iik,recipient_bik,amount_kzt,purpose,doc_number,doc_date\n"
            '"ТОО ""Алатау Снаб""",160542439625,KZ246010005016525808,HSBKKZKX,1350000.00,'
            '"Оплата, счет № 901",M-1,2026-11-26\n'
            '"ТОО ""Алатау Снаб""",160542439625,KZ246010005016525808,HSBKKZKX,1350000.00,'
            '"Оплата, счет № 901",M-1,2026-11-26\n'
            '"ТОО ""Алатау Снаб""",160542439625,KZ246010005016525808,HSBKKZKX,bad_sum,'
            '"Ошибка суммы",M-3,2026-11-26\n'
        ).encode()
        r_comma = client.post(
            "/api/v1/payments/import?filename=comma.csv&format=csv",
            content=comma_csv,
            headers=OCTET_HEADERS,
        )
        assert r_comma.status_code == 201, r_comma.text
        d_comma = r_comma.json()
        assert d_comma["summary"]["created"] == 2
        assert d_comma["summary"]["failed"] == 1
        assert d_comma["summary"]["duplicates"] == 1
        assert d_comma["items"][0]["duplicate_of"] is None
        assert d_comma["items"][1]["duplicate_of"] == d_comma["items"][0]["id"]
        assert d_comma["errors"][0]["code"] == "validation_error"

    def test_import_multipart_stdlib_without_extra_dependencies(
        self, import_env: tuple[FastAPI, Path, TestClient]
    ) -> None:
        _, _, client = import_env
        raw_csv = (SAMPLES_DIR / "sample.csv").read_bytes()
        r_mp = client.post(
            "/api/v1/payments/import?filename=mp_sample.csv",
            files={"file": ("mp_sample.csv", raw_csv, "text/csv")},
            headers=CSRF,
        )
        assert r_mp.status_code == 201, r_mp.text
        assert [item["check"]["verdict"] for item in r_mp.json()["items"]] == EXPECTED_SAMPLE_VERDICTS

    def test_import_size_limit_garbage_empty_payer_mismatch_and_roles(
        self, import_env: tuple[FastAPI, Path, TestClient]
    ) -> None:
        prod_app, db_path, client = import_env

        # 1. File > 2 MB -> 413 file_too_large
        oversized = b"x" * (MAX_IMPORT_BYTES + 1)
        r_big = client.post(
            "/api/v1/payments/import?filename=huge.txt",
            content=oversized,
            headers=OCTET_HEADERS,
        )
        assert r_big.status_code == 413
        assert r_big.json()["code"] == "file_too_large"

        # 2. Empty file -> 422 empty_file
        r_empty = client.post(
            "/api/v1/payments/import?filename=empty.txt",
            content=b"   \r\n",
            headers=OCTET_HEADERS,
        )
        assert r_empty.status_code == 422
        assert r_empty.json()["code"] == "empty_file"

        # 3. Garbage bytes -> 422 unsupported_file
        r_garbage = client.post(
            "/api/v1/payments/import?filename=random.bin",
            content=b"\x89PNG\r\n\x1a\nnot a valid 1c or csv file\x00\xff",
            headers=OCTET_HEADERS,
        )
        assert r_garbage.status_code == 422
        assert r_garbage.json()["code"] == "unsupported_file"

        # 4. Payer account of another company -> payer_mismatch error, payment NOT created
        foreign_1c = (
            "1CClientBankExchange\n"
            "ВерсияФормата=1.03\n"
            "Кодировка=UTF-8\n"
            "СекцияДокумент=Платежное поручение\n"
            "Номер=999\n"
            "Дата=26.11.2026\n"
            "Сумма=500000.00\n"
            "ПлательщикИИК=KZ228562203112345678\n"
            'Получатель=ТОО "Алатау Снаб"\n'
            "ПолучательБИН_ИИН=160542439625\n"
            "ПолучательИИК=KZ246010005016525808\n"
            "ПолучательБИК=HSBKKZKX\n"
            "НазначениеПлатежа=Чужой счет плательщика\n"
            "КонецДокумента\n"
            "КонецФайла\n"
        ).encode()
        r_foreign = client.post(
            "/api/v1/payments/import?filename=foreign.txt",
            content=foreign_1c,
            headers=OCTET_HEADERS,
        )
        assert r_foreign.status_code == 201
        d_foreign = r_foreign.json()
        assert d_foreign["summary"]["created"] == 0
        assert d_foreign["summary"]["failed"] == 1
        assert d_foreign["errors"][0]["code"] == "payer_mismatch"
        assert d_foreign["errors"][0]["doc_number"] == "999"

        # 5. Director and analyst cannot import -> 403 forbidden_role
        for role_login in ("director", "analyst"):
            with TestClient(prod_app) as other:
                _login(other, role_login)
                denied = other.post(
                    "/api/v1/payments/import?filename=sample.csv",
                    content=(SAMPLES_DIR / "sample.csv").read_bytes(),
                    headers=OCTET_HEADERS,
                )
                assert denied.status_code == 403
                assert denied.json()["code"] == "forbidden_role"

        # 6. Cross-company accountant cannot see client-technostroy's batches
        with TestClient(prod_app) as other_acc:
            _login(other_acc, "other_accountant")
            assert other_acc.get("/api/v1/batches").json() == []

        conn = connect(db_path)
        try:
            assert verify_chain(conn).ok is True
        finally:
            conn.close()
