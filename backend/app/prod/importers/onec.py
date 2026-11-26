"""Pure parser for 1CClientBankExchange payment batch files (§7)."""

from __future__ import annotations

import re

from app.prod.importers.common import (
    MAX_IMPORT_DOCUMENTS,
    EmptyFileError,
    LineError,
    ParsedDoc,
    ParsedFile,
    UnsupportedFileError,
    decode_bytes,
    parse_amount,
    parse_date,
)
from app.schemas import clean_text_field, normalize_requisite

_HEADER_MARKER = "1CClientBankExchange"
_CYRILLIC_1C_MARKERS: tuple[str, ...] = (
    "СекцияДокумент=",
    "Кодировка=",
    "ВерсияФормата=",
    "КонецФайла",
    "СекцияРасчСчет",
)

_RECIPIENT_NAME_KEYS = ("Получатель", "Получатель1", "ПолучательНаименование")
_RECIPIENT_BIN_KEYS = (
    "ПолучательБИН_ИИН",
    "ПолучательБИН",
    "ПолучательИИН",
    "ПолучательИНН",
)
_RECIPIENT_IIK_KEYS = ("ПолучательИИК", "ПолучательСчет", "ПолучательРасчСчет")
_RECIPIENT_BIK_KEYS = ("ПолучательБИК", "ПолучательБанкБИК")
_KNP_KEYS = ("КодНазначенияПлатежа", "КНП")
_KBE_KEYS = ("ПолучательКБЕ", "КБЕ")
_DOC_NUMBER_KEYS = ("Номер", "НомерДокумента")
_DOC_DATE_KEYS = ("Дата", "ДатаДокумента")
_PAYER_IIK_KEYS = ("ПлательщикИИК", "ПлательщикСчет", "ПлательщикРасчСчет")
_PURPOSE_PARTS_KEYS = tuple(f"НазначениеПлатежа{i}" for i in range(1, 7))


def _is_1c_text(text: str) -> bool:
    first_line = ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            first_line = stripped
            break
    if not first_line.startswith(_HEADER_MARKER):
        return False
    # Require at least one recognized Cyrillic 1C keyword so cp866 bytes decoded as cp1251 do not false-match.
    return any(marker in text for marker in _CYRILLIC_1C_MARKERS)


def _first_field(fields: dict[str, str], keys: tuple[str, ...]) -> str:
    for key in keys:
        val = fields.get(key, "").strip()
        if val:
            return val
    return ""


def _normalize_doc_type(raw_type: str) -> str:
    return re.sub(r"\s+", "", raw_type.strip().lower()).replace("ё", "е")


def _extract_purpose(fields: dict[str, str]) -> str:
    direct = fields.get("НазначениеПлатежа", "").strip()
    if direct:
        return direct
    parts = [fields.get(k, "").strip() for k in _PURPOSE_PARTS_KEYS]
    return " ".join(p for p in parts if p)


def parse_1c(data: bytes) -> ParsedFile:
    """Parse 1CClientBankExchange bytes into ParsedDoc entries and document-level warnings."""
    text, encoding = decode_bytes(data, marker_check=_is_1c_text)

    docs: list[ParsedDoc] = []
    errors: list[LineError] = []

    in_account_section = False
    in_doc = False
    doc_type = ""
    doc_start_line = 0
    fields: dict[str, str] = {}
    seen_documents = 0

    def _finalize_doc() -> None:
        nonlocal seen_documents
        seen_documents += 1
        doc_num = clean_text_field(_first_field(fields, _DOC_NUMBER_KEYS))

        if _normalize_doc_type(doc_type) != "платежноепоручение":
            errors.append(
                LineError(
                    line_no=doc_start_line,
                    doc_number=doc_num or None,
                    code="unsupported_document_type",
                    message=f"Документ типа «{doc_type or 'неизвестный'}» пропущен (поддерживаются только платёжные поручения).",
                )
            )
            return

        if len(docs) >= MAX_IMPORT_DOCUMENTS:
            errors.append(
                LineError(
                    line_no=doc_start_line,
                    doc_number=doc_num or None,
                    code="too_many_documents",
                    message=f"Превышен лимит документов в файле ({MAX_IMPORT_DOCUMENTS}).",
                )
            )
            return

        payer_raw = _first_field(fields, _PAYER_IIK_KEYS)
        payer_iik = normalize_requisite(payer_raw) if payer_raw else None

        docs.append(
            ParsedDoc(
                line_no=doc_start_line,
                doc_number=doc_num,
                doc_date=parse_date(_first_field(fields, _DOC_DATE_KEYS)),
                recipient_name=clean_text_field(_first_field(fields, _RECIPIENT_NAME_KEYS)),
                recipient_bin=_first_field(fields, _RECIPIENT_BIN_KEYS),
                recipient_iik=_first_field(fields, _RECIPIENT_IIK_KEYS),
                recipient_bik=_first_field(fields, _RECIPIENT_BIK_KEYS),
                amount_kzt=parse_amount(fields.get("Сумма")),
                purpose=_extract_purpose(fields),
                kbe=_first_field(fields, _KBE_KEYS),
                knp=_first_field(fields, _KNP_KEYS),
                payer_iik=payer_iik,
            )
        )

    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue

        if line == "СекцияРасчСчет":
            in_account_section = True
            continue
        if line == "КонецРасчСчет":
            in_account_section = False
            continue
        if in_account_section:
            continue

        if line.startswith("СекцияДокумент="):
            if in_doc:
                _finalize_doc()
            in_doc = True
            doc_type = line.split("=", 1)[1].strip()
            doc_start_line = line_no
            fields = {}
            continue

        if line == "КонецДокумента":
            if in_doc:
                _finalize_doc()
                in_doc = False
                doc_type = ""
                fields = {}
            continue

        if line == "КонецФайла":
            if in_doc:
                _finalize_doc()
                in_doc = False
                fields = {}
            break

        if in_doc and "=" in line:
            key, val = line.split("=", 1)
            key_clean = key.strip()
            val_clean = val.strip()
            if key_clean and (key_clean not in fields or not fields[key_clean]):
                fields[key_clean] = val_clean

    if in_doc:
        _finalize_doc()

    if seen_documents == 0:
        if _HEADER_MARKER in text:
            raise EmptyFileError("1C file contains no payment documents.")
        raise UnsupportedFileError("Unrecognized 1C file structure.")

    return ParsedFile(source="1c", docs=docs, errors=errors, encoding=encoding)
