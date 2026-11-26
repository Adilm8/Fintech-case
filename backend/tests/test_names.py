"""Tests for company name normalization, homoglyph folding, mixed-script detection, and similarity."""

from __future__ import annotations

import pytest

from app.risk.names import (
    canonical_cyrillic_token,
    confusable_skeleton,
    detect_legal_form_kind,
    extract_ie_initials,
    find_mixed_script_positions,
    is_generic_company_token,
    load_confusables,
    map_homoglyphs,
    map_latin_lookalikes,
    name_similarity,
    normalize_company_name,
    normalize_company_name_translated,
    normalize_company_name_translit,
    sanitize_unicode,
    token_set_similarity,
    transliterate_cyr_to_lat,
    transliterate_lat_to_cyr,
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

    def test_tr39_confusables_file_and_unicode_sanitization(self) -> None:
        table = load_confusables()
        assert table["\u0251"] == "а"  # IPA alpha
        assert table["\u13df"] == "С"  # Cherokee TLI
        assert len(table) >= 80

        # Mn (combining acute), Me (enclosing circle), Cf (ZWSP/WJ/BOM),
        # CGJ U+034F, variation selectors U+FE00..FE0F, Hangul/Braille fillers U+115F/1160/3164/2800
        obfuscated = (
            "ТОО «А\u0301\u20ddл\u034fа\ufe0fт\u115fа\u1160у\u3164 "
            "С\u2800н\u200bа\u200c\u200d\u2060б\ufeff»"
        )
        assert sanitize_unicode(obfuscated) == "ТОО «Алатау Снаб»"
        assert normalize_company_name(obfuscated) == "алатау снаб"

        # IPA alpha + Cherokee TLI skeleton
        spoofed = "ТОО «\u0251латау \u13dfнаб»"
        assert confusable_skeleton("ɑᏟ") == "АС"
        assert normalize_company_name(spoofed) == "алатау снаб"
        assert name_similarity("ТОО «Алатау Снаб»", spoofed) == 100.0

    def test_exotic_scripts_always_flagged_while_brand_tokens_spared(self) -> None:
        # Exotic scripts (IPA, Cherokee, Greek, fullwidth, Armenian, palochka) flagged even alone
        assert find_mixed_script_positions("ТОО «\u0251латау Снаб»") == [5]
        assert find_mixed_script_positions("ТОО «Алатау \u13dfнаб»") == [12]
        assert find_mixed_script_positions("ТОО «\u13df\u13aa»") == [5, 6]
        assert find_mixed_script_positions("ТОО «\uff21латау Снаб»") == [5]
        assert find_mixed_script_positions("ТОО «Ал\u0585тау»") == [7]
        assert find_mixed_script_positions("ТОО «Б\u04cfрлік»") == [6]

        # Invisible characters cannot split a word to bypass mixed-script detection
        assert find_mixed_script_positions("ТОО «Алатау \u0043\u3164наб»") == [12]
        assert find_mixed_script_positions("ТОО «Алатау \u0043\u0301наб»") == [12]
        assert find_mixed_script_positions("ТОО «Алатау \u0043\u2800наб»") == [12]

        # Whole Latin brand tokens attached to or alongside Cyrillic must NOT be flagged
        for legit_brand in (
            "ТОО «ЭкоSTAR»",
            "ТОО «QazaqСтрой»",
            "ТОО «АгроMAX»",
            "ТОО «ITСервис»",
            "ТОО «ProСтрой»",
            "ТОО «Эко STAR»",
            "ТОО «Qazaq Строй»",
            "ТОО «Alatau Snab»",
            "ТОО «НұрМеталлПоставка»",
            "ЖШС «Береке Құрылыс»",
        ):
            assert find_mixed_script_positions(legit_brand) == [], legit_brand

    def test_confusable_digits_inside_cyrillic_words_vs_legit_numbers(self) -> None:
        # Embedded confusable digits inside Cyrillic words -> flagged with exact 0-based positions
        assert find_mixed_script_positions("ТОО «Ка3Л0гистик»") == [7, 9]
        assert find_mixed_script_positions("ТОО «Сн0б»") == [7]
        assert find_mixed_script_positions("ТОО «КазПо4та»") == [10]
        assert find_mixed_script_positions("ТОО «Каз6етон»") == [8]
        assert find_mixed_script_positions("ТОО «Б1рл1к»") == [6, 9]
        assert find_mixed_script_positions("ТОО «0фис»") == [5]
        assert find_mixed_script_positions("ТОО «3авод»") == [5]
        assert find_mixed_script_positions("ТОО «Ка3Л0гIстик Групп»") == [7, 9, 11]

        # Legitimate numbers and standalone numeric tokens must NOT be flagged
        for legit_num in (
            "ТОО «Алматы-2»",
            "ТОО «Строй 2020»",
            "ТОО «1С-Рейтинг»",
            "ТОО «Бетон М350»",
            "ТОО «Арматура А500С»",
            "ТОО «Астана24»",
            "ТОО «Склад1»",
            "ТОО «B2B Трейд»",
        ):
            assert find_mixed_script_positions(legit_num) == [], legit_num

    def test_transliteration_ru_lat_roundtrip_and_similarity(self) -> None:
        assert transliterate_lat_to_cyr("alatau snab") == "алатау снаб"
        assert transliterate_cyr_to_lat("алатау снаб") == "alatau snab"
        cyr, lat = normalize_company_name_translit('LLP "Alatau Snab"')
        assert cyr == "алатау снаб"
        assert lat == "alatau snab"
        assert name_similarity("ТОО «Алатау Снаб»", 'ТОО "Alatau Snab"') == 100.0
        assert name_similarity("ТОО «Kaspi Pay»", "ТОО «Каспи Пей»") >= 85.0


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


class TestGenericTokensTranslationAndIeInitials:
    def test_generic_token_classification_is_script_and_case_invariant(self) -> None:
        for tok in (
            "сервис",
            "Сервис",
            "СЕРВИС",
            "servis",
            "SERVIS",
            "service",
            "SERVICE",
            "снаб",
            "СНАБ",
            "snab",
            "supply",
            "монтаж",
            "МОНТАЖ",
            "montazh",
            "групп",
            "grupp",
            "group",
            "астана",
            "АСТАНА",
            "astana",
            "караганда",
        ):
            assert is_generic_company_token(tok) is True, tok

        for brand in (
            "алатау",
            "АЛАТАУ",
            "alatau",
            "тазасу",
            "tazasu",
            "цементпром",
            "номадклауд",
        ):
            assert is_generic_company_token(brand) is False, brand

        assert canonical_cyrillic_token("servis") == "сервис"
        assert canonical_cyrillic_token("СЕРВИС") == "сервис"
        assert canonical_cyrillic_token("supply") == "снаб"

    def test_translated_company_name_normalization(self) -> None:
        assert normalize_company_name_translated("ТОО «Alatau Supply»") == "алатау снаб"
        assert normalize_company_name_translated('LLP "Alatau Supply"') == "алатау снаб"
        assert normalize_company_name_translated('LLP "Trading House Alatau"') == "торговый дом алатау"
        assert normalize_company_name_translated('ТОО "Almaty Service"') == "алматы сервис"

    def test_extract_ie_initials(self) -> None:
        assert extract_ie_initials("ИП Байжанов К.Т.") == ("к", "т")
        assert extract_ie_initials("ИП Байжанова А.К.") == ("а", "к")
        assert extract_ie_initials("ИП К.Т. Байжанов") == ("к", "т")
        assert extract_ie_initials("IP Baizhanov K.T.") == ("к", "т")
        assert extract_ie_initials("ЖК Байжанов Қ.Т.") == ("к", "т")
        assert extract_ie_initials("ИП Байжанов Кайрат Талгатович") == ("к", "т")
        assert extract_ie_initials("ИП Байжанова Асель Канатовна") == ("а", "к")
        assert extract_ie_initials("ИП Байжанов Сервис") == ()
        assert extract_ie_initials("ИП Байжанов") == ()
        # Trailing initials А.К. / А.О. on an IE must not be misread as dotted А.Қ. / А.О.
        assert detect_legal_form_kind("ИП Байжанова А.К.") == "iin"
        assert detect_legal_form_kind("ИП Сериков А.О.") == "iin"
        assert detect_legal_form_kind("А.О. «КазТранс»") == "bin"
