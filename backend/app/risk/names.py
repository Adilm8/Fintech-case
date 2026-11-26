"""Company name normalization, homoglyph folding, mixed-script detection, and fuzzy similarity."""

from __future__ import annotations

import re
import unicodedata
from typing import Literal

from rapidfuzz import fuzz

# Latin uppercase letters visually identical to Cyrillic letters (plus Latin I -> І).
LATIN_TO_CYRILLIC: dict[int, str] = str.maketrans(
    {
        "A": "А",
        "B": "В",
        "C": "С",
        "E": "Е",
        "H": "Н",
        "I": "І",
        "K": "К",
        "M": "М",
        "O": "О",
        "P": "Р",
        "T": "Т",
        "X": "Х",
        "Y": "У",
    }
)

# Greek uppercase/lowercase lookalikes and confusable digits (0 -> О, 3 -> З).
EXTENDED_HOMOGLYPHS: dict[int, str] = str.maketrans(
    {
        "A": "А",
        "B": "В",
        "C": "С",
        "E": "Е",
        "H": "Н",
        "I": "І",
        "K": "К",
        "M": "М",
        "O": "О",
        "P": "Р",
        "T": "Т",
        "X": "Х",
        "Y": "У",
        # Greek uppercase Α Β Ε Η Ι Κ Μ Ν Ο Ρ Τ Υ Χ and lowercase ο
        "\u0391": "А",
        "\u0392": "В",
        "\u0395": "Е",
        "\u0397": "Н",
        "\u0399": "І",
        "\u039a": "К",
        "\u039c": "М",
        "\u039d": "Н",
        "\u039f": "О",
        "\u03bf": "О",
        "\u03a1": "Р",
        "\u03a4": "Т",
        "\u03a5": "У",
        "\u03a7": "Х",
        # Confusable digits
        "0": "О",
        "3": "З",
    }
)

# Kazakh Cyrillic letters folded to base Russian Cyrillic equivalents.
KAZAKH_FOLD: dict[int, str] = str.maketrans(
    {
        "Ә": "А",
        "Ғ": "Г",
        "Қ": "К",
        "Ң": "Н",
        "Ө": "О",
        "Ұ": "У",
        "Ү": "У",
        "Һ": "Х",
        "І": "И",
    }
)

# Short legal form tokens (both raw and folded variants).
LEGAL_ENTITY_TOKENS: frozenset[str] = frozenset(
    {"ТОО", "АО", "ЖШС", "АҚ", "АК", "LLP", "TOO", "AO", "JSC"}
)
INDIVIDUAL_ENTREPRENEUR_TOKENS: frozenset[str] = frozenset({"ИП", "ЖК", "IP", "IE"})
LEGAL_FORM_TOKENS: frozenset[str] = LEGAL_ENTITY_TOKENS | INDIVIDUAL_ENTREPRENEUR_TOKENS

# Full legal entity phrases (ru / kz / en), normalized to uppercase single-spaced words.
_FULL_LEGAL_ENTITY_PHRASES: tuple[tuple[str, ...], ...] = (
    ("ТОВАРИЩЕСТВО", "С", "ОГРАНИЧЕННОЙ", "ОТВЕТСТВЕННОСТЬЮ"),
    ("АКЦИОНЕРНОЕ", "ОБЩЕСТВО"),
    ("ЖАУАПКЕРШІЛІГІ", "ШЕКТЕУЛІ", "СЕРІКТЕСТІК"),
    ("ЖАУАПКЕРШІЛІГІ", "ШЕКТЕУЛІ", "СЕРІКТЕСТІГІ"),
    ("ЖАУАПКЕРШИЛИГИ", "ШЕКТЕУЛИ", "СЕРИКТЕСТИК"),
    ("ЖАУАПКЕРШИЛИГИ", "ШЕКТЕУЛИ", "СЕРИКТЕСТИГИ"),
    ("АКЦИОНЕРЛІК", "ҚОҒАМ"),
    ("АКЦИОНЕРЛІК", "ҚОҒАМЫ"),
    ("АКЦИОНЕРЛИК", "КОГАМ"),
    ("АКЦИОНЕРЛИК", "КОГАМЫ"),
    ("LIMITED", "LIABILITY", "PARTNERSHIP"),
    ("JOINT", "STOCK", "COMPANY"),
)

_FULL_IE_PHRASES: tuple[tuple[str, ...], ...] = (
    ("ИНДИВИДУАЛЬНЫЙ", "ПРЕДПРИНИМАТЕЛЬ"),
    ("ЖЕКЕ", "КӘСІПКЕР"),
    ("ЖЕКЕ", "КАСИПКЕР"),
    ("INDIVIDUAL", "ENTREPRENEUR"),
)

_ALL_FULL_PHRASES: tuple[tuple[str, ...], ...] = _FULL_LEGAL_ENTITY_PHRASES + _FULL_IE_PHRASES

# Dotted abbreviations like Т.О.О., T.O.O., А.О., И.П., Ж.Ш.С., L.L.P., J.S.C.
_DOTTED_LEGAL_ENTITY_RE = re.compile(
    r"(?<!\w)(?:"
    r"[ТT\u03a4]\s*\.\s*[ОO0\u039f]\s*\.\s*[ОO0\u039f]"
    r"|[АA\u0391]\s*\.\s*[ОO0\u039f]"
    r"|[АA\u0391]\s*\.\s*[ҚКK\u039a]"
    r"|Ж\s*\.\s*Ш\s*\.\s*[СC]"
    r"|L\s*\.\s*L\s*\.\s*[PР\u03a1]"
    r"|J\s*\.\s*S\s*\.\s*[CС]"
    r")\.?(?!\w)",
    flags=re.UNICODE,
)

_DOTTED_IE_RE = re.compile(
    r"(?<!\w)(?:"
    r"[ИІI\u0399]\s*\.\s*[ПPР\u03a1]"
    r"|Ж\s*\.\s*[КK\u039a]"
    r"|[IІ\u0399]\s*\.\s*[EЕ\u0395]"
    r")\.?(?!\w)",
    flags=re.UNICODE,
)

_NON_WORD_RE = re.compile(r"[^\w]+", flags=re.UNICODE)


def _strip_cf(text: str) -> str:
    return "".join(ch for ch in text if unicodedata.category(ch) != "Cf")


def _preprocess_upper(name: str) -> str:
    """Apply NFKC, remove Cf invisible characters, uppercase, and fold Ё -> Е."""
    return _strip_cf(unicodedata.normalize("NFKC", name)).upper().replace("Ё", "Е")


def _fold_token(token: str) -> str:
    """Apply homoglyph (Latin, Greek, digits 0/3, I->І) and Kazakh letter folding."""
    return token.translate(EXTENDED_HOMOGLYPHS).translate(KAZAKH_FOLD)


def _folded_phrases(phrases: tuple[tuple[str, ...], ...]) -> tuple[tuple[str, ...], ...]:
    seen: list[tuple[str, ...]] = []
    for phrase in phrases:
        folded = tuple(_fold_token(w) for w in phrase)
        if phrase not in seen:
            seen.append(phrase)
        if folded not in seen:
            seen.append(folded)
    return tuple(seen)


_FOLDED_LEGAL_ENTITY_PHRASES = _folded_phrases(_FULL_LEGAL_ENTITY_PHRASES)
_FOLDED_IE_PHRASES = _folded_phrases(_FULL_IE_PHRASES)
_FOLDED_ALL_PHRASES = _folded_phrases(_ALL_FULL_PHRASES)
_FOLDED_LEGAL_FORM_TOKENS: frozenset[str] = frozenset(
    {_fold_token(tok) for tok in LEGAL_FORM_TOKENS} | LEGAL_FORM_TOKENS
)


def _strip_phrase_sequences(
    tokens: list[str],
    phrases: tuple[tuple[str, ...], ...],
) -> list[str]:
    """Remove contiguous token sequences matching any phrase in phrases."""
    out: list[str] = []
    i = 0
    n = len(tokens)
    while i < n:
        matched_len = 0
        for phrase in phrases:
            plen = len(phrase)
            if plen <= n - i and tuple(tokens[i : i + plen]) == phrase:
                matched_len = max(matched_len, plen)
        if matched_len > 0:
            i += matched_len
        else:
            out.append(tokens[i])
            i += 1
    return out


def _contains_phrase_sequence(
    tokens: list[str],
    phrases: tuple[tuple[str, ...], ...],
) -> bool:
    n = len(tokens)
    for phrase in phrases:
        plen = len(phrase)
        for i in range(n - plen + 1):
            if tuple(tokens[i : i + plen]) == phrase:
                return True
    return False


def map_latin_lookalikes(text: str) -> str:
    """Replace uppercase Latin homoglyphs (A,B,C,E,H,I,K,M,O,P,T,X,Y) with Cyrillic equivalents."""
    return text.translate(LATIN_TO_CYRILLIC)


def map_homoglyphs(text: str) -> str:
    """Fold Latin/Greek lookalikes, confusable digits (0/3), and Kazakh letters into Cyrillic."""
    return _fold_token(text)


def normalize_company_name(name: str) -> str:
    """Normalize a Kazakhstan company name for lookalike comparison.

    Applies NFKC, strips Cf invisible chars, drops short/dotted/full legal forms
    (ru/kz/en), punctuation, quotes and case, and folds Latin/Greek/digit homoglyphs
    and Kazakh letters into base Cyrillic.
    """
    if not isinstance(name, str) or not name.strip():
        return ""

    upper = _preprocess_upper(name)
    upper = _DOTTED_LEGAL_ENTITY_RE.sub(" ", upper)
    upper = _DOTTED_IE_RE.sub(" ", upper)

    raw_tokens = [tok for tok in _NON_WORD_RE.sub(" ", upper).split() if tok]
    raw_tokens = _strip_phrase_sequences(raw_tokens, _ALL_FULL_PHRASES)

    folded_tokens: list[str] = []
    for token in raw_tokens:
        if token in LEGAL_FORM_TOKENS:
            continue
        folded = _fold_token(token)
        if folded in _FOLDED_LEGAL_FORM_TOKENS:
            continue
        folded_tokens.append(folded)

    folded_tokens = _strip_phrase_sequences(folded_tokens, _FOLDED_ALL_PHRASES)
    return " ".join(folded_tokens).lower()


def name_similarity(name_a: str, name_b: str) -> float:
    """Return 0..100 similarity score between two company names using RapidFuzz."""
    norm_a = normalize_company_name(name_a)
    norm_b = normalize_company_name(name_b)
    if not norm_a or not norm_b:
        return 0.0
    if norm_a == norm_b:
        return 100.0
    return float(max(fuzz.ratio(norm_a, norm_b), fuzz.token_sort_ratio(norm_a, norm_b)))


def token_set_similarity(name_a: str, name_b: str) -> float:
    """Return RapidFuzz token_set_ratio (0..100) on normalized company names."""
    norm_a = normalize_company_name(name_a)
    norm_b = normalize_company_name(name_b)
    if not norm_a or not norm_b:
        return 0.0
    return float(fuzz.token_set_ratio(norm_a, norm_b))


def detect_legal_form_kind(name: str) -> Literal["bin", "iin"] | None:
    """Infer whether a company name indicates a legal entity ('bin') or IE ('iin').

    Handles short forms (ТОО/АО/ЖШС/LLP/TOO/ИП/ЖК/IP/IE), dotted forms (Т.О.О., И.П.),
    and full phrases in Russian, Kazakh, and English.
    """
    if not isinstance(name, str) or not name.strip():
        return None

    upper = _preprocess_upper(name)
    if _DOTTED_LEGAL_ENTITY_RE.search(upper):
        return "bin"
    if _DOTTED_IE_RE.search(upper):
        return "iin"

    raw_tokens = [tok for tok in _NON_WORD_RE.sub(" ", upper).split() if tok]
    folded_tokens = [_fold_token(tok) for tok in raw_tokens]

    if _contains_phrase_sequence(raw_tokens, _FULL_LEGAL_ENTITY_PHRASES) or (
        _contains_phrase_sequence(folded_tokens, _FOLDED_LEGAL_ENTITY_PHRASES)
    ):
        return "bin"
    if _contains_phrase_sequence(raw_tokens, _FULL_IE_PHRASES) or (
        _contains_phrase_sequence(folded_tokens, _FOLDED_IE_PHRASES)
    ):
        return "iin"

    for token, folded in zip(raw_tokens, folded_tokens, strict=True):
        if token in LEGAL_ENTITY_TOKENS or folded in LEGAL_ENTITY_TOKENS:
            return "bin"
        if token in INDIVIDUAL_ENTREPRENEUR_TOKENS or folded in INDIVIDUAL_ENTREPRENEUR_TOKENS:
            return "iin"
    return None


def _is_cyrillic_letter(ch: str) -> bool:
    return ch.isalpha() and ("\u0400" <= ch <= "\u052f")


def _is_foreign_script_letter(ch: str) -> bool:
    """Return True for Latin or Greek letters (including fullwidth) that may spoof Cyrillic."""
    norm = unicodedata.normalize("NFKC", ch)
    if not norm or not any(c.isalpha() for c in norm):
        return False
    return any(
        ("A" <= c <= "Z")
        or ("a" <= c <= "z")
        or ("\u0370" <= c <= "\u03ff")
        or ("\u1f00" <= c <= "\u1fff")
        for c in norm
    )


def find_mixed_script_positions(name: str) -> list[int]:
    """Return 0-based positions of foreign-script letters (Latin/Greek) inside Cyrillic words.

    Separate purely Latin words (e.g. 'LLP' or 'Kaspi') are not flagged.
    """
    if not isinstance(name, str) or not name:
        return []

    positions: list[int] = []
    word_indices: list[int] = []

    def _flush_word() -> None:
        if not word_indices:
            return
        has_cyr = any(_is_cyrillic_letter(name[idx]) for idx in word_indices)
        foreign = [idx for idx in word_indices if _is_foreign_script_letter(name[idx])]
        if has_cyr and foreign:
            positions.extend(foreign)
        word_indices.clear()

    for idx, ch in enumerate(name):
        if ch.isalpha() or unicodedata.category(ch) == "Cf":
            word_indices.append(idx)
        else:
            _flush_word()
    _flush_word()

    return positions
