"""Tests for company name normalization, homoglyph folding, mixed-script detection, and similarity."""

from __future__ import annotations

import pytest

from app.risk.names import (
    detect_legal_form_kind,
    find_mixed_script_positions,
    map_homoglyphs,
    map_latin_lookalikes,
    name_similarity,
    normalize_company_name,
    token_set_similarity,
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
            # Dotted legal forms (M2)
            ("Т.О.О. «Алатау Снаб»", "алатау снаб"),
            ("T.O.O. «Алатау Снаб»", "алатау снаб"),
            ("Ж.Ш.С. «Алатау Снаб»", "алатау снаб"),
            ("L.L.P. «Алатау Снаб»", "алатау снаб"),
            ("И.П. Сериков", "сериков"),
            # Full legal forms in ru / kz / en (M2)
            ("Товарищество с ограниченной ответственностью «Алатау Снаб»", "алатау снаб"),
            ("Жауапкершілігі шектеулі серіктестік «Алатау Снаб»", "алатау снаб"),
            ("Limited Liability Partnership «Алатау Снаб»", "алатау снаб"),
            ("Акционерное общество «КазТрансГаз»", "казтрансгаз"),
            ("Индивидуальный предприниматель Сериков", "сериков"),
        ],
    )
    def test_drops_legal_forms_quotes_punctuation_and_case(self, raw: str, expected: str) -> None:
        assert normalize_company_name(raw) == expected

    def test_maps_all_latin_lookalikes_to_cyrillic(self) -> None:
        latin_all = "ABCEHKMOPTXY"
        cyrillic_expected = "АВСЕНКМОРТХУ"
        assert map_latin_lookalikes(latin_all) == cyrillic_expected

    def test_nfkc_invisible_cf_greek_digits_and_kazakh_folding(self) -> None:
        # NFKC fullwidth Latin A + Cf invisible characters (ZWSP, soft hyphen, BOM)
        assert normalize_company_name("ТОО «\uff21лат\u200bау Сн\u00adаб\ufeff»") == "алатау снаб"

        # Greek homoglyphs Α Β Ε Η Ι Κ Μ Ν Ο Ρ Τ Υ Χ and lowercase ο
        assert map_homoglyphs(
            "\u0391\u0392\u0395\u0397\u0399\u039a\u039c\u039d\u039f\u03a1\u03a4\u03a5\u03a7\u03bf"
        ) == ("АВЕНИКМНОРТУХО")
        assert normalize_company_name("ТОО «\u0391латау Снаб»") == "алатау снаб"
        assert normalize_company_name("ТОО «КазЛ\u03bfгистик Групп»") == "казлогистик групп"

        # Confusable digits 0 -> О, 3 -> З, Latin I -> І -> И
        assert normalize_company_name("ТОО «Ка3Л0гIстик Групп»") == "казлогистик групп"

        # Kazakh letter folding: Ә->А Ғ->Г Қ->К Ң->Н Ө->О Ұ Ү->У Һ->Х І->И
        assert map_homoglyphs("ӘҒҚҢӨҰҮҺІ") == "АГКНОУУХИ"
        assert normalize_company_name("ТОО «ҚазЛогистІк Грүпп»") == "казлогистик групп"

    def test_demo_latin_c_lookalike_normalizes_identically(self) -> None:
        real_name = "ТОО «Алатау Снаб»"
        spoofed_name = 'ТОО "Алатау \u0043наб"'  # Latin C
        assert normalize_company_name(real_name) == normalize_company_name(spoofed_name)
        assert name_similarity(real_name, spoofed_name) == 100.0

    def test_mixed_script_legal_form_is_dropped(self) -> None:
        # Latin T and O mixed with Cyrillic О
        assert normalize_company_name("T\u041eO «Алатау Снаб»") == "алатау снаб"

    def test_similarity_and_token_set_similarity(self) -> None:
        assert name_similarity("ТОО «Алатау Снаб»", "ТОО «Алатау Снабб»") >= 85.0
        assert name_similarity("ТОО «Алатау Снаб»", "ТОО «Снаб Алатау»") >= 85.0
        assert name_similarity("ТОО «Алатау Снаб»", "ТОО «Сарыарка Принт»") < 50.0
        assert name_similarity("", "ТОО «Алатау Снаб»") == 0.0
        assert (
            token_set_similarity("ТОО «Алатау Снаб Трейд Казахстан»", "ТОО «Алатау Снаб»") >= 95.0
        )


class TestMixedScriptDetection:
    def test_detects_latin_and_greek_inside_cyrillic_words(self) -> None:
        spoofed = 'ТОО "Алатау \u0043наб"'
        positions = find_mixed_script_positions(spoofed)
        assert positions == [12]
        assert spoofed[positions[0]] == "C"

        greek_spoofed = "ТОО «\u0391латау Снаб»"
        assert find_mixed_script_positions(greek_spoofed) == [5]

    def test_clean_cyrillic_and_separate_latin_words_not_flagged(self) -> None:
        assert find_mixed_script_positions("ТОО «Алатау Снаб»") == []
        assert find_mixed_script_positions('LLP "Алатау Снаб"') == []
        assert find_mixed_script_positions("ТОО «Kaspi Pay»") == []
        assert find_mixed_script_positions("") == []


class TestDetectLegalFormKind:
    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("ТОО «Алатау Снаб»", "bin"),
            ("Т.О.О. «Алатау Снаб»", "bin"),
            ("Товарищество с ограниченной ответственностью «Алатау Снаб»", "bin"),
            ("Жауапкершілігі шектеулі серіктестік «Алатау Снаб»", "bin"),
            ("Limited Liability Partnership Alatau", "bin"),
            ('TOO "Alatau"', "bin"),
            ('LLP "Alatau"', "bin"),
            ("АО «КазПочта»", "bin"),
            ("ЖШС «Алатау»", "bin"),
            ("T\u041eO «Смешанный»", "bin"),
            ("ИП Ахметов", "iin"),
            ("И.П. Ахметов", "iin"),
            ("Индивидуальный предприниматель Ахметов", "iin"),
            ("Жеке кәсіпкер Ахметов", "iin"),
            ("ЖК Сериков", "iin"),
            ("IP Serikov", "iin"),
            ("Алатау Снаб", None),
            ("", None),
        ],
    )
    def test_detect_legal_form_kind(self, name: str, expected: str | None) -> None:
        assert detect_legal_form_kind(name) == expected
