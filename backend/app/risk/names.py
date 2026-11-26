"""Company name normalization, homoglyph folding, and fuzzy similarity."""

from __future__ import annotations

import re
from typing import Literal

from rapidfuzz import fuzz

# Latin uppercase letters visually identical to Cyrillic letters.
LATIN_TO_CYRILLIC: dict[int, str] = str.maketrans(
    {
        "A": "А",
        "B": "В",
        "C": "С",
        "E": "Е",
        "H": "Н",
        "K": "К",
        "M": "М",
        "O": "О",
        "P": "Р",
        "T": "Т",
        "X": "Х",
        "Y": "У",
    }
)

# Legal entity prefixes dropped before comparing core company names.
LEGAL_FORM_TOKENS: frozenset[str] = frozenset(
    {
        "ТОО",
        "АО",
        "ИП",
        "ЖШС",
        "АҚ",
        "ЖК",
        "LLP",
        "TOO",
        "AO",
        "IP",
        "JSC",
        "IE",
    }
)

LEGAL_ENTITY_TOKENS: frozenset[str] = frozenset(
    {"ТОО", "АО", "ЖШС", "АҚ", "LLP", "TOO", "AO", "JSC"}
)
INDIVIDUAL_ENTREPRENEUR_TOKENS: frozenset[str] = frozenset({"ИП", "ЖК", "IP", "IE"})

_NON_WORD_RE = re.compile(r"[^\w]+", flags=re.UNICODE)


def _tokenize_raw(name: str) -> list[str]:
    cleaned = _NON_WORD_RE.sub(" ", name.upper().replace("Ё", "Е"))
    return [tok for tok in cleaned.split() if tok]


def map_latin_lookalikes(text: str) -> str:
    """Replace uppercase Latin homoglyphs (A,B,C,E,H,K,M,O,P,T,X,Y) with Cyrillic equivalents."""
    return text.translate(LATIN_TO_CYRILLIC)


def normalize_company_name(name: str) -> str:
    """Normalize a Kazakhstan company name for lookalike comparison.

    Drops legal forms (ТОО/АО/ИП/ЖШС/LLP/TOO), quotes, punctuation, and case,
    and folds Latin lookalike characters into Cyrillic.
    """
    if not isinstance(name, str) or not name.strip():
        return ""

    raw_tokens = _tokenize_raw(name)
    normalized_tokens: list[str] = []
    for token in raw_tokens:
        if token in LEGAL_FORM_TOKENS:
            continue
        folded = map_latin_lookalikes(token)
        if folded in LEGAL_FORM_TOKENS:
            continue
        normalized_tokens.append(folded)

    return " ".join(normalized_tokens).lower()


def name_similarity(name_a: str, name_b: str) -> float:
    """Return 0..100 similarity score between two company names using RapidFuzz."""
    norm_a = normalize_company_name(name_a)
    norm_b = normalize_company_name(name_b)
    if not norm_a or not norm_b:
        return 0.0
    return float(max(fuzz.ratio(norm_a, norm_b), fuzz.token_sort_ratio(norm_a, norm_b)))


def detect_legal_form_kind(name: str) -> Literal["bin", "iin"] | None:
    """Infer whether a company name indicates a legal entity ('bin') or IE ('iin').

    Returns None when no explicit legal form token is present.
    """
    if not isinstance(name, str) or not name.strip():
        return None

    for token in _tokenize_raw(name):
        folded = map_latin_lookalikes(token)
        if token in LEGAL_ENTITY_TOKENS or folded in LEGAL_ENTITY_TOKENS:
            return "bin"
        if token in INDIVIDUAL_ENTREPRENEUR_TOKENS or folded in INDIVIDUAL_ENTREPRENEUR_TOKENS:
            return "iin"
    return None
