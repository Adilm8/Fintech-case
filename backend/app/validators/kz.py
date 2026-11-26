"""Validators for Kazakhstan payment requisites (BIN/IIN, IIK/IBAN, BIK)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, NotRequired, TypedDict

from app.i18n import DEFAULT_LANG, Lang, t

WEIGHTS_FIRST: tuple[int, ...] = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11)
WEIGHTS_SECOND: tuple[int, ...] = (3, 4, 5, 6, 7, 8, 9, 10, 11, 1, 2)

BIN_FIFTH_DIGITS: frozenset[str] = frozenset({"4", "5", "6"})
IIN_FIFTH_DIGITS: frozenset[str] = frozenset({"0", "1", "2", "3"})

DEFAULT_BANKS_PATH: Path = Path(__file__).resolve().parents[2] / "data" / "banks.json"


class BankRecord(TypedDict):
    """Kazakhstan bank directory entry."""

    code: str
    bik: str
    name: str
    budget: NotRequired[bool]


def _is_ascii_digits(value: str) -> bool:
    return value.isascii() and value.isdigit()


def _is_ascii_upper_alnum(value: str) -> bool:
    return all(("0" <= ch <= "9") or ("A" <= ch <= "Z") for ch in value)


def _has_cyrillic(value: str) -> bool:
    return any("\u0400" <= ch <= "\u052f" for ch in value)


def compute_bin_iin_check_digit(prefix11: str) -> int | None:
    """Compute the 12th check digit for an 11-digit KZ BIN/IIN prefix.

    Uses weights 1..11 mod 11; if the remainder is 10, retries with weights
    3,4,5,6,7,8,9,10,11,1,2 mod 11. Returns None if the prefix is malformed or
    the second remainder is also 10 (invalid combination per KZ standard).
    """
    if not isinstance(prefix11, str) or len(prefix11) != 11 or not _is_ascii_digits(prefix11):
        return None

    digits = [int(ch) for ch in prefix11]
    remainder = sum(d * w for d, w in zip(digits, WEIGHTS_FIRST, strict=True)) % 11
    if remainder == 10:
        remainder = sum(d * w for d, w in zip(digits, WEIGHTS_SECOND, strict=True)) % 11
    if remainder == 10:
        return None
    return remainder


def make_bin_iin(prefix11: str) -> str:
    """Append a valid 12th check digit to an 11-digit BIN/IIN prefix."""
    check_digit = compute_bin_iin_check_digit(prefix11)
    if check_digit is None:
        raise ValueError(f"Cannot compute valid BIN/IIN check digit for prefix: {prefix11!r}")
    return f"{prefix11}{check_digit}"


def bin_iin_checksum_ok(value: str) -> bool:
    """Return True if value is a valid 12-digit KZ BIN or IIN.

    Rejects all-zero values (000000000000), invalid months outside 01..12, and bad checksums.
    """
    if not isinstance(value, str) or len(value) != 12 or not _is_ascii_digits(value):
        return False
    if value == "000000000000":
        return False
    month = int(value[2:4])
    if not (1 <= month <= 12):
        return False
    expected = compute_bin_iin_check_digit(value[:11])
    return expected is not None and int(value[11]) == expected


def bin_kind(value: str) -> Literal["bin", "iin"] | None:
    """Classify a 12-digit number as 'bin' or 'iin' using the 5th digit.

    Digits 4, 5, 6 identify legal entity / joint-venture BIN types.
    Digits 0, 1, 2, 3 identify individual IINs (day-of-month tens digit).
    Returns None for malformed values or invalid 5th digits (7, 8, 9).
    """
    if not isinstance(value, str) or len(value) != 12 or not _is_ascii_digits(value):
        return None
    fifth = value[4]
    if fifth in BIN_FIFTH_DIGITS:
        return "bin"
    if fifth in IIN_FIFTH_DIGITS:
        return "iin"
    return None


def bin_registration_yymm(value: str) -> tuple[int, int] | None:
    """Extract (YY, MM) registration date from a BIN.

    Returns None if value is an IIN, malformed, or has an invalid month.
    """
    if bin_kind(value) != "bin":
        return None
    yy = int(value[0:2])
    mm = int(value[2:4])
    if not (1 <= mm <= 12):
        return None
    return (yy, mm)


def iban_mod97(value: str) -> int:
    """Compute ISO 13616 IBAN mod-97 remainder for an uppercase ASCII alphanumeric IBAN."""
    rearranged = value[4:] + value[:4]
    numeric_parts: list[str] = []
    for ch in rearranged:
        if "0" <= ch <= "9":
            numeric_parts.append(ch)
        elif "A" <= ch <= "Z":
            numeric_parts.append(str(ord(ch) - ord("A") + 10))
        else:
            raise ValueError(f"Unsupported IBAN character: {ch!r}")
    return int("".join(numeric_parts)) % 97


def compute_iik_check_digits(bank_code: str, account_body: str) -> str:
    """Compute the 2 IBAN check digits for a KZ IIK from its 3-digit bank code and 13-char body."""
    if not isinstance(bank_code, str) or len(bank_code) != 3 or not _is_ascii_digits(bank_code):
        raise ValueError(f"Bank code must be 3 ASCII digits, got: {bank_code!r}")
    if (
        not isinstance(account_body, str)
        or len(account_body) != 13
        or not _is_ascii_upper_alnum(account_body)
    ):
        raise ValueError(
            f"Account body must be 13 uppercase ASCII alphanumeric chars, got: {account_body!r}"
        )
    remainder = iban_mod97(f"KZ00{bank_code}{account_body}")
    check = 98 - remainder
    return f"{check:02d}"


def make_iik(bank_code: str, account_body: str) -> str:
    """Build a valid 20-char KZ IIK with correct ISO 13616 mod-97 check digits."""
    check = compute_iik_check_digits(bank_code, account_body)
    return f"KZ{check}{bank_code}{account_body}"


def iik_check(
    value: str,
    *,
    check_bank_code: bool = True,
    banks_path: Path | None = None,
) -> tuple[bool, str | None, dict[str, Any]]:
    """Validate a Kazakhstan IIK and return (ok, i18n_message_key, params).

    Explicitly detects Cyrillic lookalike characters and validates bank code digits
    and membership in banks.json (M4) when check_bank_code is True.
    """
    if not isinstance(value, str) or not value:
        return False, "iik.empty", {}

    if _has_cyrillic(value):
        return False, "iik.cyrillic", {}

    if len(value) != 20:
        return False, "iik.length", {"length": len(value)}

    if value != value.upper():
        return False, "iik.uppercase", {}

    if not value.startswith("KZ"):
        return False, "iik.prefix_kz", {}

    if not _is_ascii_upper_alnum(value):
        return False, "iik.alnum", {}

    if not _is_ascii_digits(value[2:4]):
        return False, "iik.check_digits", {}

    if iban_mod97(value) != 1:
        return False, "iik.checksum", {}

    code = value[4:7]
    if not _is_ascii_digits(code):
        return False, "iik.bank_code_digits", {}

    if check_bank_code and get_bank_by_code(code, path=banks_path) is None:
        return False, "iik.unknown_bank_code", {"code": code}

    return True, None, {}


def iik_ok(
    value: str,
    *,
    check_bank_code: bool = True,
    banks_path: Path | None = None,
    lang: Lang = DEFAULT_LANG,
) -> tuple[bool, str | None]:
    """Validate a Kazakhstan IIK (20-char KZ IBAN).

    Returns (True, None) when valid, or (False, localized_error_message).
    """
    ok, msg_key, params = iik_check(
        value,
        check_bank_code=check_bank_code,
        banks_path=banks_path,
    )
    if ok or msg_key is None:
        return True, None
    return False, t(msg_key, lang, **params)


def iik_bank_code(value: str) -> str | None:
    """Extract the 3-digit bank code (positions 5-7, 1-based) from an IIK."""
    if not isinstance(value, str) or len(value) < 7:
        return None
    code = value[4:7]
    if not _is_ascii_digits(code):
        return None
    return code


@lru_cache(maxsize=4)
def _load_banks_cached(resolved_path: Path) -> tuple[BankRecord, ...]:
    raw = json.loads(resolved_path.read_text(encoding="utf-8"))
    items = raw["banks"] if isinstance(raw, dict) else raw
    records: list[BankRecord] = []
    for item in items:
        rec = BankRecord(
            code=str(item["code"]),
            bik=str(item["bik"]),
            name=str(item["name"]),
        )
        if item.get("budget"):
            rec["budget"] = True
        records.append(rec)
    return tuple(records)


def clear_banks_cache() -> None:
    """Clear the cached bank directory (used after regenerating banks.json)."""
    _load_banks_cached.cache_clear()


def load_banks(path: Path | None = None) -> list[BankRecord]:
    """Load the KZ bank directory from JSON."""
    target = (path or DEFAULT_BANKS_PATH).resolve()
    return list(_load_banks_cached(target))


def get_bank_by_bik(bik: str, path: Path | None = None) -> BankRecord | None:
    """Look up a bank record by its 8-character BIK."""
    if not isinstance(bik, str) or len(bik) != 8 or not _is_ascii_upper_alnum(bik):
        return None
    for bank in load_banks(path):
        if bank["bik"] == bik:
            return bank
    return None


def get_bank_by_code(code: str, path: Path | None = None) -> BankRecord | None:
    """Look up a bank record by its 3-digit IIK bank code."""
    if not isinstance(code, str) or len(code) != 3 or not _is_ascii_digits(code):
        return None
    for bank in load_banks(path):
        if bank["code"] == code:
            return bank
    return None


def bik_ok(bik: str, path: Path | None = None) -> bool:
    """Return True if bik is a valid 8-character BIK present in data/banks.json."""
    return get_bank_by_bik(bik, path=path) is not None


def bik_matches_iik(bik: str, iik: str, path: Path | None = None) -> bool:
    """Return True if the bank code in iik (chars 5-7) matches bik in data/banks.json."""
    bank = get_bank_by_bik(bik, path=path)
    if bank is None:
        return False
    code = iik_bank_code(iik)
    if code is None:
        return False
    return bank["code"] == code
