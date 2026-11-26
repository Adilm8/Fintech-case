"""Shared data types, encoding detection, and value parsers for payment file import (§7)."""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Literal

MAX_IMPORT_BYTES: int = 2 * 1024 * 1024
MAX_IMPORT_DOCUMENTS: int = 500
CANDIDATE_ENCODINGS: tuple[str, ...] = ("utf-8-sig", "cp1251", "cp866")

_HINT_TO_ENCODING: dict[str, str] = {
    "utf-8": "utf-8-sig",
    "utf8": "utf-8-sig",
    "windows": "cp1251",
    "cp1251": "cp1251",
    "dos": "cp866",
    "cp866": "cp866",
}

_ENCODING_HINT_RE = re.compile(r"(?im)^\s*Кодировка\s*=\s*([A-Za-z0-9_-]+)\s*$")
_DATE_DMY_RE = re.compile(r"^(\d{1,2})[./-](\d{1,2})[./-](\d{4})$")
_DATE_ISO_RE = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$")


class ImportParseError(ValueError):
    """Base error raised by pure file parsers."""


class EmptyFileError(ImportParseError):
    """Raised when an uploaded file has no content or no payment records."""


class UnsupportedFileError(ImportParseError):
    """Raised when an uploaded file does not match a supported 1C or CSV format."""


@dataclass(frozen=True)
class ParsedDoc:
    """Single parsed payment document ready for PaymentInput validation."""

    line_no: int | None
    doc_number: str
    doc_date: str | None
    recipient_name: str
    recipient_bin: str
    recipient_iik: str
    recipient_bik: str
    amount_kzt: float | None
    purpose: str
    kbe: str = ""
    knp: str = ""
    payer_iik: str | None = None


@dataclass(frozen=True)
class LineError:
    """Row- or document-level parse warning/error."""

    line_no: int | None
    doc_number: str | None
    code: str
    message: str


@dataclass(frozen=True)
class ParsedFile:
    """Pure parse result for a 1C or CSV payment batch."""

    source: Literal["1c", "csv"]
    docs: list[ParsedDoc]
    errors: list[LineError]
    encoding: str


def parse_amount(raw: str | None) -> float | None:
    """Parse amounts like '1360000.00', '1 360 000,00', or '1,360,000.50' into positive float."""
    if raw is None:
        return None
    cleaned = re.sub(r"[\s\u00a0\u202f']+", "", raw.strip())
    if not cleaned:
        return None

    has_comma = "," in cleaned
    has_dot = "." in cleaned
    if has_comma and has_dot:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif has_comma:
        if cleaned.count(",") == 1:
            cleaned = cleaned.replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")

    try:
        dec = Decimal(cleaned)
    except InvalidOperation:
        return None
    if not dec.is_finite() or dec <= 0:
        return None

    value = float(dec)
    if not math.isfinite(value) or value <= 0 or value > 1e12 or round(value * 100) <= 0:
        return None
    return value


def parse_date(raw: str | None) -> str | None:
    """Parse DD.MM.YYYY (1C) or YYYY-MM-DD (ISO) into YYYY-MM-DD, or None if empty/invalid."""
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None

    iso_match = _DATE_ISO_RE.match(text)
    if iso_match is not None:
        year, month, day = map(int, iso_match.groups())
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            return None

    dmy_match = _DATE_DMY_RE.match(text)
    if dmy_match is not None:
        day, month, year = map(int, dmy_match.groups())
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            return None

    return None


def _extract_encoding_hint(text: str) -> str | None:
    match = _ENCODING_HINT_RE.search(text)
    if match is None:
        return None
    return _HINT_TO_ENCODING.get(match.group(1).strip().lower())


def decode_bytes(
    data: bytes,
    *,
    marker_check: Callable[[str], bool] | None = None,
) -> tuple[str, str]:
    """Decode raw bytes trying utf-8-sig -> cp1251 -> cp866 with format marker & hint checks."""
    if not data or not data.strip():
        raise EmptyFileError("Uploaded file is empty.")

    candidates: list[str] = list(CANDIDATE_ENCODINGS)
    if data.startswith(b"\xef\xbb\xbf"):
        candidates = ["utf-8-sig"]

    fallback_match: tuple[str, str] | None = None

    for enc in candidates:
        try:
            text = data.decode(enc)
        except UnicodeDecodeError:
            continue

        hint_enc = _extract_encoding_hint(text)
        if marker_check is not None and not marker_check(text):
            continue

        # If a hint is present and explicitly matches this encoding (or file is valid UTF-8), pick immediately.
        if hint_enc is None or hint_enc == enc or enc == "utf-8-sig":
            return text, enc
        if fallback_match is None:
            fallback_match = (text, enc)

    if fallback_match is not None:
        return fallback_match

    raise UnsupportedFileError("Could not decode file in utf-8, cp1251, or cp866 with valid format markers.")
