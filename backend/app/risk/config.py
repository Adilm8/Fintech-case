"""Risk scoring weights, thresholds, and deterministic demo constants."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from typing import Protocol

# Fixed reference date for synthetic data generation and recency checks.
DEMO_TODAY: date = date(2026, 4, 20)

# Active risk ruleset identifier returned in CheckResult and audit log records.
RULESET_VERSION: str = "2026.11.26-r3"

# Bank CenterCredit identifiers (matching data/banks.json: BCC code 856, BIK KCJBKZKX).
BCC_BANK_CODE: str = "856"
BCC_BIK: str = "KCJBKZKX"

# Verdict score thresholds (green < 30, yellow 30..64, red >= 65).
THRESHOLD_YELLOW: int = 30
THRESHOLD_RED: int = 65

# Amplifiers alone cannot exceed this cap (prevents amplifiers alone from turning yellow).
AMPLIFIER_ONLY_CAP: int = 29

# A single signal at or below this point value alone does not raise colour.
SINGLE_SIGNAL_NO_RAISE_MAX: int = 25

# Primary and standalone signal weights.
WEIGHT_FRESH_IIK_MANY_PAYERS_HIGH: int = 70
WEIGHT_AMOUNT_ANOMALY_EXTREME: int = 65
WEIGHT_LOOKALIKE_SUPPLIER: int = 60
WEIGHT_IIK_REPORTED_BY_CLIENTS: int = 60
WEIGHT_BIN_NAME_MISMATCH: int = 50
WEIGHT_IIK_BELONGS_TO_OTHER_COUNTERPARTY: int = 50
WEIGHT_FRESH_IIK_MANY_PAYERS_MEDIUM: int = 50
WEIGHT_ENTITY_TYPE_MISMATCH_LEGAL_IIN: int = 40
WEIGHT_KBE_MISMATCH_LEGAL_IIN: int = 40
WEIGHT_IIK_CHANGED: int = 35
WEIGHT_DUPLICATE_INVOICE: int = 35
WEIGHT_AMOUNT_ANOMALY_PRIMARY: int = 35
WEIGHT_STRUCTURING_PRIMARY: int = 35
WEIGHT_MIXED_SCRIPT_NAME: int = 30
WEIGHT_BANK_CHANGED_HIGH_AMOUNT: int = 30
WEIGHT_ENTITY_TYPE_MISMATCH: int = 25
WEIGHT_KBE_MISMATCH_INDIVIDUAL_BIN: int = 25
WEIGHT_NEW_BCC_ACCOUNT: int = 25

# Amplifier weights.
WEIGHT_STRUCTURING_AMPLIFIER: int = 20
WEIGHT_NEW_RECIPIENT_ACCUM_MIN: int = 15
WEIGHT_NEW_RECIPIENT_ACCUM_MAX: int = 25
WEIGHT_BANK_CHANGED_AMPLIFIER: int = 15
WEIGHT_BIN_YOUNG: int = 15
WEIGHT_KNP_UNUSUAL: int = 15
WEIGHT_URGENT_WORDING: int = 10
WEIGHT_AMOUNT_ANOMALY_MIN: int = 10
WEIGHT_AMOUNT_ANOMALY_MAX: int = 25

# Memory & structuring windows and thresholds.
DUPLICATE_INVOICE_WINDOW_DAYS: int = 90
NEW_RECIPIENT_ACCUM_WINDOW_DAYS: int = 7
STRUCTURING_WINDOW_HOURS: int = 72
STRUCTURING_SPLIT_MIN_COUNT: int = 3
STRUCTURING_SPLIT_MIN_RATIO: float = 1.15
STRUCTURING_PAIR_MIN_RATIO: float = 1.5
STRUCTURING_PRIMARY_RATIO: float = 3.0

# Amount anomaly multipliers (p90-based escalations).
AMOUNT_SUPPLIER_EXTREME_P90_MULT: float = 10.0
AMOUNT_FIRST_PAYMENT_YELLOW_P90_MULT: float = 3.0
AMOUNT_FIRST_PAYMENT_RED_P90_MULT: float = 10.0

# KBe beneficiary codes (17 = corporate legal entity, 19 = individual / IE).
KBE_LEGAL_ENTITY_CODES: frozenset[str] = frozenset({"17"})
KBE_INDIVIDUAL_CODES: frozenset[str] = frozenset({"19"})

# Rule parameters.
LOOKALIKE_BLOCK_SIMILARITY_THRESHOLD: float = 95.0
LOOKALIKE_AMOUNT_COMPARE_SIMILARITY: float = 92.0
LOOKALIKE_SIMILARITY_THRESHOLD: float = 85.0
LOOKALIKE_DISTINCTIVE_THRESHOLD: float = 70.0
LOOKALIKE_DISTINCTIVE_FUZZY_THRESHOLD: float = 80.0
LOOKALIKE_DISTINCTIVE_PREFIX_FUZZY_THRESHOLD: float = 65.0
LOOKALIKE_DISTINCTIVE_WRAPPER_MIN_LEN: int = 5
LOOKALIKE_DISTINCTIVE_TOKEN_MIN_LEN: int = 4
LOOKALIKE_PREFIX_MIN_LEN: int = 4
LOOKALIKE_TOKEN_SET_THRESHOLD: float = 95.0
LOOKALIKE_TOKEN_SET_MIN_LEN: int = 8
NEW_BCC_ACCOUNT_MAX_DAYS: int = 30
BIN_YOUNG_MAX_MONTHS: int = 12
AMOUNT_ANOMALY_MIN_HISTORY: int = 5
CLIENT_P90_MIN_HISTORY: int = 5

# Bank-wide cross-client signal thresholds.
BANK_COMPLAINTS_MIN_COUNT: int = 1
BANK_COMPLAINTS_BLOCK_COUNT: int = 3
BANK_FRESH_INFLOWS_WINDOW_DAYS: int = 7
BANK_FRESH_INFLOWS_MEDIUM_PAYERS: int = 3
BANK_FRESH_INFLOWS_HIGH_PAYERS: int = 5
BANK_KNOWN_BIN_MIN_YEARS: float = 2.0

# Antifraud analyst role header value (X-Role: analyst).
ANALYST_ROLE_VALUE: str = "analyst"

# Signal rule IDs casting doubt on recipient identity: yellow/grey payments carrying any of these
# cannot be signed via accountant acknowledgement and must go through director approval.
# Kept in sync with frontend/src/lib/identitySignals.ts.
IDENTITY_SIGNAL_IDS: frozenset[str] = frozenset(
    {
        "lookalike_supplier",
        "bin_name_mismatch",
        "entity_type_mismatch",
        "kbe_mismatch",
        "iik_belongs_to_other_counterparty",
        "mixed_script_name",
        "iik_reported_by_clients",
        "fresh_iik_many_payers",
    }
)


class _TrustSignalLike(Protocol):
    rule_id: str
    severity: str
    points: int


# Account-change signal rule IDs eligible for director account trust.
# Kept in sync with frontend/src/lib/approvals.ts.
TRUST_ALLOWED_SIGNAL_IDS: frozenset[str] = frozenset({"iik_changed", "bank_changed"})

# Weighted signals that always forbid director account trust next to an account change
# (in addition to IDENTITY_SIGNAL_IDS): pressure wording typical for invoice substitution.
TRUST_FORBIDDEN_SIGNAL_IDS: frozenset[str] = frozenset({"urgent_wording"})


def can_trust_check(verdict: str, signals: Iterable[_TrustSignalLike]) -> bool:
    """Return True if a check result is eligible for director account trust.

    One rule for ``yellow`` and ``red`` (H2):
    - no ``block``-level signal;
    - the weighted (non zero-weight ``info``) signals are a subset of
      ``TRUST_ALLOWED_SIGNAL_IDS`` and contain ``iik_changed``;
    - explicitly: no weighted identity signal (``IDENTITY_SIGNAL_IDS``) and no
      ``urgent_wording`` (kept even if ``TRUST_ALLOWED_SIGNAL_IDS`` grows later);
    - zero-weight ``info`` signals are allowed.

    Mirrored by ``canTrustApproval`` in ``frontend/src/lib/approvals.ts``.
    """
    if verdict not in ("yellow", "red"):
        return False
    sig_list = list(signals)
    if any(s.severity == "block" for s in sig_list):
        return False
    weighted = {s.rule_id for s in sig_list if not (s.severity == "info" and s.points == 0)}
    if weighted & (IDENTITY_SIGNAL_IDS | TRUST_FORBIDDEN_SIGNAL_IDS):
        return False
    return "iik_changed" in weighted and weighted <= TRUST_ALLOWED_SIGNAL_IDS


# H1 «прогрев счёта»: a supplier IIK counts as known history only after confirmation.
# Confirmed if: it is the supplier's first account in history; a payment to it was approved by
# the director; it comes from legacy/imported history without signing metadata; or there are
# at least ACCOUNT_CONFIRM_MIN_PAYMENTS signed payments to it spanning
# ACCOUNT_CONFIRM_MIN_SPAN_DAYS days or more.
ACCOUNT_CONFIRM_MIN_PAYMENTS: int = 2
ACCOUNT_CONFIRM_MIN_SPAN_DAYS: int = 14

# Digits that visually spoof Cyrillic letters when embedded inside Cyrillic words.
CONFUSABLE_DIGITS: frozenset[str] = frozenset({"0", "3", "4", "6", "1"})

# Unicode categories and invisible filler codepoints stripped before name comparison.
IGNORABLE_UNICODE_CATEGORIES: frozenset[str] = frozenset({"Mn", "Me", "Cf"})
INVISIBLE_CODEPOINTS: frozenset[str] = frozenset(
    {
        "\u00ad",  # SOFT HYPHEN
        "\u034f",  # COMBINING GRAPHEME JOINER
        "\u115f",  # HANGUL CHOSEONG FILLER
        "\u1160",  # HANGUL JUNGSEONG FILLER
        "\u200b",  # ZERO WIDTH SPACE
        "\u200c",  # ZERO WIDTH NON-JOINER
        "\u200d",  # ZERO WIDTH JOINER
        "\u2060",  # WORD JOINER
        "\u2800",  # BRAILLE PATTERN BLANK
        "\u3164",  # HANGUL FILLER
        "\ufeff",  # ZERO WIDTH NO-BREAK SPACE / BOM
        "\uffa0",  # HALFWIDTH HANGUL FILLER
        *(chr(cp) for cp in range(0xFE00, 0xFE10)),  # VARIATION SELECTORS FE00..FE0F
    }
)

# Common generic business tokens that do not qualify as distinctive brand tokens on their own.
# Classification is always performed once on canonical lower-case Cyrillic form.
GENERIC_COMPANY_TOKENS: frozenset[str] = frozenset(
    {
        "авто",
        "актау",
        "актобе",
        "алматы",
        "альянс",
        "астана",
        "атырау",
        "балхаш",
        "бизнес",
        "гк",
        "групп",
        "группа",
        "девелопмент",
        "дом",
        "доставка",
        "жезказган",
        "импорт",
        "инвест",
        "инжиниринг",
        "казахстан",
        "капитал",
        "караганда",
        "кз",
        "кокшетау",
        "коммерц",
        "компани",
        "компания",
        "комплект",
        "комплектация",
        "консалтинг",
        "контракт",
        "костанай",
        "кызылорда",
        "логистик",
        "логистика",
        "маркет",
        "мастер",
        "материалы",
        "монтаж",
        "оборудование",
        "опт",
        "оскемен",
        "павлодар",
        "партнер",
        "петропавл",
        "плюс",
        "поставка",
        "поставки",
        "предприятие",
        "принт",
        "пром",
        "ремонт",
        "ресурс",
        "семей",
        "сервис",
        "сервисы",
        "системы",
        "снаб",
        "снабжение",
        "софт",
        "строй",
        "стройматериалы",
        "талдыкорган",
        "тараз",
        "тд",
        "темиртау",
        "техника",
        "торг",
        "торговый",
        "транс",
        "трейд",
        "трейдинг",
        "туркестан",
        "уральск",
        "услуги",
        "фирма",
        "холдинг",
        "центр",
        "шымкент",
        "экибастуз",
        "экспорт",
        "электро",
        "энерго",
        "almaty",
        "astana",
        "group",
        "kz",
        "plus",
        "service",
        "snab",
        "soft",
        "supply",
        "trade",
        "trading",
    }
)

# Entity wrapper phrases (canonical Cyrillic lower-case) that wrap a brand without changing domain.
ENTITY_WRAPPER_PHRASES: tuple[tuple[str, ...], ...] = (
    ("торговый", "дом"),
    ("группа", "компаний"),
    ("компания",),
    ("фирма",),
    ("тд",),
    ("гк",),
)

# Multi-word English business phrases mapped to canonical Cyrillic lower-case tokens.
BUSINESS_PHRASE_TRANSLATIONS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("trading", "house"), ("торговый", "дом")),
    (("trade", "house"), ("торговый", "дом")),
    (("group", "of", "companies"), ("группа", "компаний")),
)

# Common English business terms mapped to canonical Cyrillic lower-case equivalents.
BUSINESS_TERM_TRANSLATIONS: dict[str, str] = {
    "supply": "снаб",
    "supplies": "снаб",
    "supplier": "поставка",
    "delivery": "поставка",
    "group": "групп",
    "logistics": "логистик",
    "logistic": "логистик",
    "service": "сервис",
    "services": "сервис",
    "trade": "трейд",
    "trading": "трейдинг",
    "house": "дом",
    "metal": "металл",
    "metals": "металл",
    "energy": "энерго",
    "power": "энерго",
    "concrete": "бетон",
    "cement": "цемент",
    "crane": "кран",
    "office": "офис",
    "soft": "софт",
    "software": "софт",
    "cloud": "клауд",
    "build": "строй",
    "building": "строй",
    "construction": "строй",
    "print": "принт",
    "printing": "принт",
    "insulation": "изоляция",
    "thermal": "тепло",
    "heat": "тепло",
    "mount": "монтаж",
    "mounting": "монтаж",
    "holding": "холдинг",
    "center": "центр",
    "centre": "центр",
    "plus": "плюс",
    "invest": "инвест",
    "engineering": "инжиниринг",
    "resource": "ресурс",
    "resources": "ресурс",
    "materials": "материалы",
    "material": "материалы",
    "import": "импорт",
    "export": "экспорт",
    "systems": "системы",
    "system": "системы",
    "company": "компания",
    "companies": "компаний",
    "firm": "фирма",
    "industrial": "пром",
    "industry": "пром",
    "capital": "капитал",
    "partner": "партнер",
    "alliance": "альянс",
    "business": "бизнес",
    "market": "маркет",
    "master": "мастер",
    "contract": "контракт",
    "commerce": "коммерц",
    "development": "девелопмент",
    "wholesale": "опт",
    "repair": "ремонт",
    "consulting": "консалтинг",
    "equipment": "оборудование",
    "kz": "кз",
}

# Phonetic transliteration tables (Latin <-> Cyrillic) for cross-script lookalike detection.
LATIN_TO_CYRILLIC_DIGRAPHS: tuple[tuple[str, str], ...] = (
    ("shch", "щ"),
    ("zh", "ж"),
    ("kh", "х"),
    ("ts", "ц"),
    ("ch", "ч"),
    ("sh", "ш"),
    ("yu", "ю"),
    ("ya", "я"),
    ("yo", "е"),
    ("ye", "е"),
    ("ph", "ф"),
    ("gh", "г"),
    ("ck", "к"),
    ("ou", "у"),
)

LATIN_TO_CYRILLIC_SINGLE: dict[str, str] = {
    "a": "а",
    "b": "б",
    "d": "д",
    "e": "е",
    "f": "ф",
    "g": "г",
    "h": "х",
    "i": "и",
    "j": "ж",
    "k": "к",
    "l": "л",
    "m": "м",
    "n": "н",
    "o": "о",
    "p": "п",
    "q": "к",
    "r": "р",
    "s": "с",
    "t": "т",
    "u": "у",
    "v": "в",
    "w": "в",
    "x": "кс",
    "y": "ы",
    "z": "з",
}

CYRILLIC_TO_LATIN_MAP: dict[str, str] = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "e",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "kh",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "shch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
    "ә": "a",
    "ғ": "g",
    "қ": "k",
    "ң": "n",
    "ө": "o",
    "ұ": "u",
    "ү": "u",
    "һ": "h",
    "і": "i",
}

URGENT_PHRASES: tuple[str, ...] = (
    "срочно",
    "сегодня",
    "новые реквизиты",
    "изменились реквизиты",
    "по новым реквизитам",
    "смена реквизитов",
    "новый счёт",
    "новый расчётный счёт",
    "смена банка",
    "смена обслуживающего банка",
    "шұғыл",
    "жедел",
    "urgent",
    "new bank details",
    "changed bank account",
    "srochno",
)

# Stem prefixes matched at word start (negations like "несрочно"/"досрочно" do NOT match).
URGENT_CYRILLIC_STEMS: tuple[str, ...] = (
    "срочн",
    "шұғыл",
    "жедел",
)

URGENT_LATIN_STEMS: tuple[str, ...] = (
    "urgent",
    "srochn",
)

URGENT_LATIN_PHRASES: tuple[str, ...] = (
    "new bank details",
    "changed bank account",
)
