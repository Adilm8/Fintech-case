"""Tests for company name normalization, homoglyph folding, and RapidFuzz similarity."""

from __future__ import annotations

import pytest

from app.risk.names import (
    detect_legal_form_kind,
    map_latin_lookalikes,
    name_similarity,
    normalize_company_name,
)


class TestNormalizeCompanyName:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("ТОО «Алатау Снаб»", "алатау снаб"),
            ('ТОО "Алатау Снаб"', "алатау снаб"),
            ("АО «КазТрансГаз»", "казтрансгаз"),
            ("ИП Иванов И.И.", "иванов и и"),
            ("ЖШС «Алатау-Снаб»", "алатау снаб"),
            ('LLP "Алатау Снаб"', "алатау снаб"),
            ('TOO "Алатау Снаб"', "алатау снаб"),
            ("   ТОО   «АЛАТАУ   СНАБ»! ", "алатау снаб"),
        ],
    )
    def test_drops_legal_forms_quotes_punctuation_and_case(self, raw: str, expected: str) -> None:
        assert normalize_company_name(raw) == expected

    def test_maps_all_latin_lookalikes_to_cyrillic(self) -> None:
        latin_all = "ABCEHKMOPTXY"
        cyrillic_expected = "АВСЕНКМОРТХУ"
        assert map_latin_lookalikes(latin_all) == cyrillic_expected

    def test_demo_latin_c_lookalike_normalizes_identically(self) -> None:
        real_name = "ТОО «Алатау Снаб»"
        spoofed_name = 'ТОО "Алатау \u0043наб"'  # Latin C
        assert normalize_company_name(real_name) == normalize_company_name(spoofed_name)
        assert name_similarity(real_name, spoofed_name) == 100.0

    def test_mixed_script_legal_form_is_dropped(self) -> None:
        # Latin T and O mixed with Cyrillic О
        assert normalize_company_name("T\u041eO «Алатау Снаб»") == "алатау снаб"

    def test_similarity_distinguishes_lookalikes_from_different_companies(self) -> None:
        assert name_similarity("ТОО «Алатау Снаб»", "ТОО «Алатау Снабб»") >= 85.0
        assert name_similarity("ТОО «Алатау Снаб»", "ТОО «Снаб Алатау»") >= 85.0
        assert name_similarity("ТОО «Алатау Снаб»", "ТОО «Сарыарка Принт»") < 50.0
        assert name_similarity("", "ТОО «Алатау Снаб»") == 0.0


class TestDetectLegalFormKind:
    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("ТОО «Алатау Снаб»", "bin"),
            ('TOO "Alatau"', "bin"),
            ('LLP "Alatau"', "bin"),
            ("АО «КазПочта»", "bin"),
            ("ЖШС «Алатау»", "bin"),
            ("T\u041eO «Смешанный»", "bin"),
            ("ИП Ахметов", "iin"),
            ("ЖК Сериков", "iin"),
            ("IP Serikov", "iin"),
            ("Алатау Снаб", None),
            ("", None),
        ],
    )
    def test_detect_legal_form_kind(self, name: str, expected: str | None) -> None:
        assert detect_legal_form_kind(name) == expected
