"""Pure parser for CSV payment batch files with ';' or ',' delimiter (§7)."""

from __future__ import annotations

import csv
import io

from app.prod.importers.common import (
    MAX_IMPORT_DOCUMENTS,
    EmptyFileError,
    LineError,
    ParsedDoc,
    ParsedFile,
    UnsupportedFileError,
    cap_errors,
    decode_bytes,
    parse_amount,
    parse_date,
)
from app.schemas import clean_text_field, normalize_requisite

_COLUMN_ALIASES: dict[str, str] = {
    "recipient_name": "recipient_name",
    "получатель": "recipient_name",
    "recipient_bin": "recipient_bin",
    "бин": "recipient_bin",
    "бин/иин": "recipient_bin",
    "иин": "recipient_bin",
    "recipient_iik": "recipient_iik",
    "иик": "recipient_iik",
    "recipient_bik": "recipient_bik",
    "бик": "recipient_bik",
    "amount_kzt": "amount_kzt",
    "сумма": "amount_kzt",
    "purpose": "purpose",
    "назначение": "purpose",
    "kbe": "kbe",
    "кбе": "kbe",
    "knp": "knp",
    "кнп": "knp",
    "doc_number": "doc_number",
    "номер": "doc_number",
    "doc_date": "doc_date",
    "дата": "doc_date",
    "payer_iik": "payer_iik",
    "иик плательщика": "payer_iik",
}

REQUIRED_CSV_FIELDS: frozenset[str] = frozenset(
    {
        "recipient_name",
        "recipient_bin",
        "recipient_iik",
        "recipient_bik",
        "amount_kzt",
    }
)


def _detect_delimiter_and_map(header_line: str) -> tuple[str, dict[int, str]] | None:
    """Detect ';' or ',' from header_line and return (delimiter, col_index -> canonical field)."""
    semi_count = header_line.count(";")
    comma_count = header_line.count(",")
    order = (";", ",") if semi_count >= comma_count else (",", ";")

    for delim in order:
        if delim not in header_line:
            continue
        parsed_headers = next(csv.reader([header_line], delimiter=delim), [])
        col_map: dict[int, str] = {}
        for idx, raw_name in enumerate(parsed_headers):
            normalized = clean_text_field(raw_name).casefold()
            canonical = _COLUMN_ALIASES.get(normalized)
            if canonical is not None and canonical not in col_map.values():
                col_map[idx] = canonical
        if REQUIRED_CSV_FIELDS.issubset(col_map.values()):
            return delim, col_map
    return None


def _has_valid_csv_header(text: str) -> bool:
    for line in text.splitlines():
        if line.strip():
            return _detect_delimiter_and_map(line) is not None
    return False


def parse_csv(data: bytes) -> ParsedFile:
    """Parse CSV bytes (';' or ',') into ParsedDoc entries and line-level errors."""
    text, encoding = decode_bytes(data, marker_check=_has_valid_csv_header)

    reader_input = io.StringIO(text)
    header_line = ""
    header_line_no = 0
    for idx, line in enumerate(text.splitlines(), start=1):
        if line.strip():
            header_line = line
            header_line_no = idx
            break

    detected = _detect_delimiter_and_map(header_line)
    if detected is None:
        raise UnsupportedFileError("CSV header is missing required payment columns.")
    delimiter, col_map = detected

    # Re-read full text with csv.reader so quoted multiline cells are handled cleanly
    rows = list(csv.reader(reader_input, delimiter=delimiter))
    data_start_idx = header_line_no  # 0-based index immediately after header_line_no

    docs: list[ParsedDoc] = []
    errors: list[LineError] = []
    seen_rows = 0

    for offset, row in enumerate(rows[data_start_idx:], start=header_line_no + 1):
        if not any(cell.strip() for cell in row):
            continue
        seen_rows += 1

        values: dict[str, str] = {}
        for col_idx, field_name in col_map.items():
            values[field_name] = row[col_idx].strip() if col_idx < len(row) else ""

        doc_num = clean_text_field(values.get("doc_number", ""))

        if len(docs) >= MAX_IMPORT_DOCUMENTS:
            errors.append(
                LineError(
                    line_no=offset,
                    doc_number=doc_num or None,
                    code="too_many_documents",
                    message=f"Превышен лимит документов в файле ({MAX_IMPORT_DOCUMENTS}).",
                )
            )
            continue

        payer_raw = values.get("payer_iik", "")
        payer_iik = normalize_requisite(payer_raw) if payer_raw else None

        docs.append(
            ParsedDoc(
                line_no=offset,
                doc_number=doc_num,
                doc_date=parse_date(values.get("doc_date")),
                recipient_name=clean_text_field(values.get("recipient_name", "")),
                recipient_bin=values.get("recipient_bin", ""),
                recipient_iik=values.get("recipient_iik", ""),
                recipient_bik=values.get("recipient_bik", ""),
                amount_kzt=parse_amount(values.get("amount_kzt")),
                purpose=values.get("purpose", ""),
                kbe=values.get("kbe", ""),
                knp=values.get("knp", ""),
                payer_iik=payer_iik,
            )
        )

    if seen_rows == 0:
        raise EmptyFileError("CSV file contains header only and no payment rows.")

    capped_errors, errors_omitted = cap_errors(errors)
    return ParsedFile(
        source="csv",
        docs=docs,
        errors=capped_errors,
        encoding=encoding,
        errors_omitted=errors_omitted,
    )
