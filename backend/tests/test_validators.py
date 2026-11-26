"""Tests for Kazakhstan payment requisite validators and bank catalog."""

from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from app.validators.kz import (
    bik_matches_iik,
    bik_ok,
    bin_iin_checksum_ok,
    bin_kind,
    bin_registration_yymm,
    compute_bin_iin_check_digit,
    get_bank_by_bik,
    get_bank_by_code,
    iban_mod97,
    iik_bank_code,
    iik_ok,
    load_banks,
    make_bin_iin,
    make_iik,
)
from scripts.generate_data import generate_bin, generate_iik, generate_iin

BCC_SAMPLE_IIK = "KZ86125KZT5004100100"
BANKS_JSON_PATH = Path(__file__).resolve().parents[1] / "data" / "banks.json"


class TestBinIin:
    def test_first_pass_weights_valid(self) -> None:
        # 20014000000: weighted sum = 2*1 + 1*4 + 4*5 = 26 -> 26 % 11 = 4
        bin_num = make_bin_iin("20014000000")
        assert bin_num == "200140000004"
        assert bin_iin_checksum_ok(bin_num) is True

    def test_second_pass_weights_valid(self) -> None:
        # 20014100000: first pass sum = 32 (32 % 11 = 10);
        # second pass sum = 48 (48 % 11 = 4).
        assert compute_bin_iin_check_digit("20014100000") == 4
        assert bin_iin_checksum_ok("200141000004") is True
        assert bin_iin_checksum_ok("200141000000") is False

    def test_double_remainder_ten_is_invalid(self) -> None:
        # 20014202000: first pass sum = 54 (54 % 11 = 10);
        # second pass sum = 76 (76 % 11 = 10) -> invalid for every last digit.
        assert compute_bin_iin_check_digit("20014202000") is None
        for d in range(10):
            assert bin_iin_checksum_ok(f"20014202000{d}") is False
        with pytest.raises(ValueError):
            make_bin_iin("20014202000")

    @pytest.mark.parametrize(
        "bad_value",
        [
            "",
            "20014000000",  # 11 digits
            "2001400000040",  # 13 digits
            "200140000005",  # wrong check digit
            "20014000000A",  # letter
            "200140 00004",  # space
            "٢٠٠١٤٠٠٠٠٠٠٤",  # non-ASCII digits
        ],
    )
    def test_bin_iin_invalid_inputs(self, bad_value: str) -> None:
        assert bin_iin_checksum_ok(bad_value) is False

    @pytest.mark.parametrize(
        ("fifth_digit", "expected"),
        [
            ("0", "iin"),
            ("1", "iin"),
            ("2", "iin"),
            ("3", "iin"),
            ("4", "bin"),
            ("5", "bin"),
            ("6", "bin"),
            ("7", None),
            ("8", None),
            ("9", None),
        ],
    )
    def test_bin_kind_classification(self, fifth_digit: str, expected: str | None) -> None:
        sample = f"2001{fifth_digit}0000000"
        assert bin_kind(sample) == expected

    def test_bin_kind_malformed(self) -> None:
        assert bin_kind("123") is None
        assert bin_kind("20014000000X") is None

    def test_bin_registration_yymm_for_bin_only(self) -> None:
        bin_num = make_bin_iin("18094000001")
        assert bin_registration_yymm(bin_num) == (18, 9)

        # IIN must return None even with valid month
        iin_num = make_bin_iin("90051530001")
        assert bin_kind(iin_num) == "iin"
        assert bin_registration_yymm(iin_num) is None

        # Invalid month on a BIN must return None
        assert bin_registration_yymm("200040000000") is None
        assert bin_registration_yymm("201340000000") is None


class TestIik:
    def test_bcc_example_passes_mod97(self) -> None:
        assert iban_mod97(BCC_SAMPLE_IIK) == 1
        assert make_iik("125", "KZT5004100100") == BCC_SAMPLE_IIK
        ok, err = iik_ok(BCC_SAMPLE_IIK)
        assert ok is True
        assert err is None

    def test_invalid_checksum_rejected(self) -> None:
        ok, err = iik_ok("KZ86125KZT5004100101")
        assert ok is False
        assert err is not None
        assert "контрольной суммы" in err.lower() or "не существует" in err.lower()

    @pytest.mark.parametrize(
        "cyrillic_iik",
        [
            "\u041aZ86125KZT5004100100",  # Cyrillic К instead of Latin K
            "KZ86125KZ\u04225004100100",  # Cyrillic Т instead of Latin T
            "KZ86125\u041aZT5004100100",  # Cyrillic К in currency
        ],
    )
    def test_cyrillic_lookalikes_rejected_with_clear_message(self, cyrillic_iik: str) -> None:
        ok, err = iik_ok(cyrillic_iik)
        assert ok is False
        assert err is not None
        assert "кириллич" in err.lower()

    @pytest.mark.parametrize(
        "bad_iik",
        [
            "",
            "KZ86125KZT500410010",  # 19 chars
            "KZ86125KZT50041001000",  # 21 chars
            "kz86125kzt5004100100",  # lowercase
            "KZ86125kzt5004100100",  # mixed case
            "RU86125KZT5004100100",  # wrong country prefix
            "KZ86 125KZT500410010",  # contains space
            "KZ86-125KZT500410010",  # contains hyphen
            "KZAB125KZT5004100100",  # non-digit check digits
        ],
    )
    def test_iik_format_errors(self, bad_iik: str) -> None:
        ok, err = iik_ok(bad_iik)
        assert ok is False
        assert err is not None

    def test_iik_bank_code(self) -> None:
        assert iik_bank_code(BCC_SAMPLE_IIK) == "125"
        assert iik_bank_code("KZ006010000000000000") == "601"
        assert iik_bank_code("KZ86") is None
        assert iik_bank_code("KZ86ABC0000000000000") is None


class TestBanksAndBik:
    def test_banks_json_exists_and_marked(self) -> None:
        assert BANKS_JSON_PATH.exists()
        raw = json.loads(BANKS_JSON_PATH.read_text(encoding="utf-8"))
        assert "to verify against NB RK reference" in raw["note"]
        banks = load_banks()
        assert len(banks) >= 10
        bcc = get_bank_by_code("125")
        assert bcc is not None
        assert bcc["bik"] == "KCJBKZKX"
        for bank in banks:
            assert len(bank["bik"]) == 8
            assert len(bank["code"]) == 3

    def test_bik_ok(self) -> None:
        assert bik_ok("KCJBKZKX") is True
        assert bik_ok("HSBKKZKX") is True
        assert bik_ok("CASPKZKA") is True
        assert bik_ok("UNKNOWNX") is False
        assert bik_ok("kcjbkzkx") is False
        assert bik_ok("KCJBKZK") is False
        assert bik_ok("\u041aCJBKZKX") is False  # Cyrillic К

    def test_bik_matches_iik(self) -> None:
        assert bik_matches_iik("KCJBKZKX", BCC_SAMPLE_IIK) is True
        assert bik_matches_iik("HSBKKZKX", BCC_SAMPLE_IIK) is False
        assert bik_matches_iik("UNKNOWNX", BCC_SAMPLE_IIK) is False
        assert bik_matches_iik("KCJBKZKX", "BAD") is False

        halyk = get_bank_by_bik("HSBKKZKX")
        assert halyk is not None
        halyk_iik = make_iik(halyk["code"], "0001234567890")
        assert iik_ok(halyk_iik) == (True, None)
        assert bik_matches_iik("HSBKKZKX", halyk_iik) is True
        assert bik_matches_iik("KCJBKZKX", halyk_iik) is False


class TestGeneratorHelpers:
    def test_seeded_generators_produce_valid_requisites(self) -> None:
        rng1 = random.Random(42)
        rng2 = random.Random(42)

        bins1 = [generate_bin(rng1) for _ in range(10)]
        bins2 = [generate_bin(rng2) for _ in range(10)]
        assert bins1 == bins2
        for b in bins1:
            assert bin_iin_checksum_ok(b) is True
            assert bin_kind(b) == "bin"
            assert bin_registration_yymm(b) is not None

        iins = [generate_iin(rng1) for _ in range(10)]
        for iin in iins:
            assert bin_iin_checksum_ok(iin) is True
            assert bin_kind(iin) == "iin"
            assert bin_registration_yymm(iin) is None

        for bank in load_banks():
            iik = generate_iik(rng1, bank["code"])
            assert iik_ok(iik) == (True, None)
            assert bik_matches_iik(bank["bik"], iik) is True
