"""Company name normalization, TR39 confusable skeleton, transliteration, and mixed-script detection."""

from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Literal

from rapidfuzz import fuzz

from app.risk.config import (
    CONFUSABLE_DIGITS,
    CYRILLIC_TO_LATIN_MAP,
    IGNORABLE_UNICODE_CATEGORIES,
    INVISIBLE_CODEPOINTS,
    LATIN_TO_CYRILLIC_DIGRAPHS,
    LATIN_TO_CYRILLIC_SINGLE,
)

DEFAULT_CONFUSABLES_PATH: Path = (
    Path(__file__).resolve().parents[2] / "data" / "confusables_subset.json"
)

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

# Allowed Kazakh Cyrillic letters (in addition to Russian А-Я, а-я, Ё, ё).
_KAZAKH_CYRILLIC: frozenset[str] = frozenset("ӘҒҚҢӨҰҮҺІәғқңөұүһі")

# Basic ASCII Latin characters that visually spoof Cyrillic letters.
_LATIN_HOMOGLYPH_CHARS: frozenset[str] = frozenset("ABCEHIKMOPTXYaceikmopxy")

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


@lru_cache(maxsize=4)
def _load_confusables_cached(
    resolved_path: Path,
) -> tuple[dict[str, str], dict[int, str], dict[int, str]]:
    raw = json.loads(resolved_path.read_text(encoding="utf-8"))
    raw_mappings = raw["mappings"] if isinstance(raw, dict) and "mappings" in raw else raw
    mappings = {str(k): str(v) for k, v in raw_mappings.items()}
    full_trans = str.maketrans(mappings)
    non_latin_trans = str.maketrans(
        {k: v for k, v in mappings.items() if not (k.isascii() and k.isalpha())}
    )
    return mappings, full_trans, non_latin_trans


def load_confusables(path: Path | None = None) -> dict[str, str]:
    """Load the static TR39-style Cyrillic confusables mapping from JSON."""
    target = (path or DEFAULT_CONFUSABLES_PATH).resolve()
    mappings, _, _ = _load_confusables_cached(target)
    return dict(mappings)


def clear_confusables_cache() -> None:
    """Clear the cached confusables mapping table."""
    _load_confusables_cached.cache_clear()


def is_ignorable_unicode(ch: str) -> bool:
    """Return True for Mn/Me/Cf marks and explicit invisible filler codepoints."""
    return ch in INVISIBLE_CODEPOINTS or unicodedata.category(ch) in IGNORABLE_UNICODE_CATEGORIES


def strip_invisible_and_marks(text: str) -> str:
    """Remove all Mn/Me/Cf marks and invisible filler codepoints from text."""
    return "".join(ch for ch in text if not is_ignorable_unicode(ch))


def sanitize_unicode(text: str) -> str:
    """Strip Mn/Me/Cf marks and invisible fillers before applying NFKC normalization."""
    stripped = strip_invisible_and_marks(text)
    normalized = unicodedata.normalize("NFKC", stripped)
    return strip_invisible_and_marks(normalized)


def confusable_skeleton(text: str, *, path: Path | None = None) -> str:
    """Produce a TR39-style uppercase Cyrillic confusable skeleton for comparison.

    Strips ignorable/invisible characters before NFKC, applies confusables_subset.json
    mappings (Latin, Greek, Cherokee, IPA, Coptic, Armenian, digits), folds Ё->Е and
    Kazakh Cyrillic letters into base Cyrillic.
    """
    if not isinstance(text, str) or not text:
        return ""
    target = (path or DEFAULT_CONFUSABLES_PATH).resolve()
    _, full_trans, _ = _load_confusables_cached(target)
    sanitized = sanitize_unicode(text)
    mapped = sanitized.translate(full_trans)
    upper = mapped.upper().replace("Ё", "Е").translate(full_trans)
    return upper.translate(KAZAKH_FOLD)


def _apply_non_latin_confusables(text: str, *, path: Path | None = None) -> str:
    target = (path or DEFAULT_CONFUSABLES_PATH).resolve()
    _, _, non_latin_trans = _load_confusables_cached(target)
    return text.translate(non_latin_trans)


def _preprocess_upper(name: str) -> str:
    """Strip Mn/Me/Cf/invisibles, apply NFKC, fold non-Latin confusables, uppercase, Ё -> Е."""
    sanitized = sanitize_unicode(name)
    exotic_folded = _apply_non_latin_confusables(sanitized)
    return exotic_folded.upper().replace("Ё", "Е")


def _fold_token(token: str) -> str:
    """Apply TR39 confusable skeleton folding to a single token."""
    return confusable_skeleton(token)


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
    """Fold TR39 confusables (Latin/Greek/Cherokee/IPA/digits) and Kazakh letters into Cyrillic."""
    return confusable_skeleton(text)


def transliterate_lat_to_cyr(text: str) -> str:
    """Phonetic Latin-to-Cyrillic transliteration on lowercase text."""
    lower = text.lower()
    out: list[str] = []
    i = 0
    n = len(lower)
    while i < n:
        matched = False
        for src, dst in LATIN_TO_CYRILLIC_DIGRAPHS:
            if lower.startswith(src, i):
                out.append(dst)
                i += len(src)
                matched = True
                break
        if matched:
            continue
        ch = lower[i]
        if ch == "c":
            next_ch = lower[i + 1] if i + 1 < n else ""
            out.append("с" if next_ch in ("e", "i", "y") else "к")
        elif ch in LATIN_TO_CYRILLIC_SINGLE:
            out.append(LATIN_TO_CYRILLIC_SINGLE[ch])
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def transliterate_cyr_to_lat(text: str) -> str:
    """Phonetic Cyrillic-to-Latin transliteration on lowercase text."""
    lower = text.lower()
    return "".join(CYRILLIC_TO_LATIN_MAP.get(ch, ch) for ch in lower)


def normalize_company_name(name: str) -> str:
    """Normalize a Kazakhstan company name for visual lookalike comparison.

    Strips Mn/Me/Cf and invisible fillers before NFKC, drops short/dotted/full legal forms
    (ru/kz/en), punctuation, quotes and case, and applies the TR39 confusable skeleton
    and Kazakh letter folding into base Cyrillic.
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


def normalize_company_name_translit(name: str) -> tuple[str, str]:
    """Return (cyrillic_phonetic, latin_phonetic) normalized forms without Latin visual folding.

    Preserves ASCII Latin letters for phonetic transliteration (e.g. 'Alatau Snab' -> 'алатау снаб')
    while still stripping invisible characters, NFKC, exotic confusables, and legal forms.
    """
    if not isinstance(name, str) or not name.strip():
        return "", ""

    upper = _preprocess_upper(name)
    upper = _DOTTED_LEGAL_ENTITY_RE.sub(" ", upper)
    upper = _DOTTED_IE_RE.sub(" ", upper)

    raw_tokens = [tok for tok in _NON_WORD_RE.sub(" ", upper).split() if tok]
    raw_tokens = _strip_phrase_sequences(raw_tokens, _ALL_FULL_PHRASES)

    kept_tokens: list[str] = []
    for token in raw_tokens:
        if token in LEGAL_FORM_TOKENS:
            continue
        if token.translate(KAZAKH_FOLD) in LEGAL_FORM_TOKENS:
            continue
        kept_tokens.append(token.translate(KAZAKH_FOLD))

    kept_tokens = _strip_phrase_sequences(kept_tokens, _FOLDED_ALL_PHRASES)
    base = " ".join(kept_tokens).lower()
    if not base:
        return "", ""
    return transliterate_lat_to_cyr(base), transliterate_cyr_to_lat(base)


def _pair_fuzzy_ratio(norm_a: str, norm_b: str) -> float:
    if not norm_a or not norm_b:
        return 0.0
    if norm_a == norm_b:
        return 100.0
    return float(max(fuzz.ratio(norm_a, norm_b), fuzz.token_sort_ratio(norm_a, norm_b)))


def name_similarity(name_a: str, name_b: str) -> float:
    """Return 0..100 similarity score between two company names (visual skeleton + transliteration)."""
    norm_a = normalize_company_name(name_a)
    norm_b = normalize_company_name(name_b)
    if not norm_a or not norm_b:
        return 0.0

    best = _pair_fuzzy_ratio(norm_a, norm_b)
    if best == 100.0:
        return 100.0

    cyr_a, lat_a = normalize_company_name_translit(name_a)
    cyr_b, lat_b = normalize_company_name_translit(name_b)
    return max(best, _pair_fuzzy_ratio(cyr_a, cyr_b), _pair_fuzzy_ratio(lat_a, lat_b))


def token_set_similarity(name_a: str, name_b: str) -> float:
    """Return RapidFuzz token_set_ratio (0..100) across visual skeleton and transliterated forms."""
    norm_a = normalize_company_name(name_a)
    norm_b = normalize_company_name(name_b)
    if not norm_a or not norm_b:
        return 0.0

    best = float(fuzz.token_set_ratio(norm_a, norm_b))
    cyr_a, lat_a = normalize_company_name_translit(name_a)
    cyr_b, lat_b = normalize_company_name_translit(name_b)
    if cyr_a and cyr_b:
        best = max(best, float(fuzz.token_set_ratio(cyr_a, cyr_b)))
    if lat_a and lat_b:
        best = max(best, float(fuzz.token_set_ratio(lat_a, lat_b)))
    return best


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


def _is_allowed_cyrillic_letter(ch: str) -> bool:
    """Return True for Russian and Kazakh Cyrillic letters only."""
    return ("\u0410" <= ch <= "\u044f") or ch in ("Ё", "ё") or ch in _KAZAKH_CYRILLIC


def _is_basic_latin_letter(ch: str) -> bool:
    """Return True for basic ASCII Latin letters A-Z, a-z."""
    return ("A" <= ch <= "Z") or ("a" <= ch <= "z")


def _is_brand_latin_run(
    runs: list[tuple[str, list[tuple[int, str]]]],
    run_index: int,
) -> bool:
    """Return True if a Latin run inside a Cyrillic+Latin word looks like a brand token."""
    _, items = runs[run_index]
    if len(items) < 2:
        return False

    # Contains at least one Latin letter that does not visually mimic Cyrillic (e.g. STAR, Qazaq).
    if any(ch not in _LATIN_HOMOGLYPH_CHARS for _, ch in items):
        return True

    # Multi-letter all-homoglyph Latin brand token at a clear CamelCase / case boundary
    # (e.g. 'ITСервис', 'АгроMAX', 'ЭкоBio').
    if run_index == 0 and len(runs) > 1:
        next_kind, next_items = runs[1]
        if next_kind == "cyr" and next_items[0][1].isupper():
            return True
    if run_index == len(runs) - 1 and run_index > 0:
        prev_kind, prev_items = runs[run_index - 1]
        if prev_kind == "cyr" and prev_items[-1][1].islower() and items[0][1].isupper():
            return True

    return False


def _is_ascii_digit(ch: str) -> bool:
    return "0" <= ch <= "9"


def find_mixed_script_positions(name: str) -> list[int]:
    """Return 0-based positions of suspicious mixed-script, exotic-script, or confusable-digit chars.

    - Any letter outside Russian Cyrillic + Kazakh Cyrillic + basic ASCII Latin (e.g. Greek,
      Cherokee, IPA, fullwidth, Coptic, Armenian, rare Cyrillic) is always flagged.
    - Ignorable marks and invisible fillers (Mn/Me/Cf, ZW*, Hangul/Braille fillers) bridge across
      characters so attackers cannot split words to evade detection.
    - Pure Latin tokens (e.g. 'LLP', 'Kaspi') and whole Latin brand sub-tokens attached to Cyrillic
      (e.g. 'ЭкоSTAR', 'QazaqСтрой') are NOT flagged; only embedded Latin lookalikes inside
      otherwise Cyrillic words are flagged.
    - Confusable single digits (0/3/4/6/1) embedded inside Cyrillic words (e.g. 'Ка3Л0гистик') are
      flagged, while standalone numeric tokens and multi-digit numbers ('Алматы-2', 'Строй 2020',
      '1С', 'М350') are not flagged.
    """
    if not isinstance(name, str) or not name:
        return []

    positions: list[int] = []
    word_chars: list[tuple[int, str]] = []

    def _flush_word() -> None:
        if not word_chars:
            return

        # 1. Classify characters; any letter outside RU/KZ Cyrillic + basic ASCII Latin -> flag.
        classified: list[tuple[int, str, str]] = []
        has_cyr = False
        has_lat = False
        has_dig = False
        for idx, ch in word_chars:
            if _is_allowed_cyrillic_letter(ch):
                has_cyr = True
                classified.append((idx, ch, "cyr"))
            elif _is_basic_latin_letter(ch):
                has_lat = True
                classified.append((idx, ch, "lat"))
            elif _is_ascii_digit(ch):
                has_dig = True
                classified.append((idx, ch, "dig"))
            else:
                positions.append(idx)

        # 2. Mixed Cyrillic + basic Latin or confusable digits within the same word.
        if has_cyr and (has_lat or has_dig):
            runs: list[tuple[str, list[tuple[int, str]]]] = []
            for idx, ch, kind in classified:
                if runs and runs[-1][0] == kind:
                    runs[-1][1].append((idx, ch))
                else:
                    runs.append((kind, [(idx, ch)]))

            for run_idx, (kind, items) in enumerate(runs):
                if kind == "lat":
                    if _is_brand_latin_run(runs, run_idx):
                        continue
                    if all(ch in _LATIN_HOMOGLYPH_CHARS for _, ch in items):
                        positions.extend(idx for idx, _ in items)
                elif kind == "dig":
                    if len(items) != 1:
                        continue
                    idx, digit = items[0]
                    if digit not in CONFUSABLE_DIGITS:
                        continue
                    prev_is_cyr = run_idx > 0 and runs[run_idx - 1][0] == "cyr"
                    next_is_cyr = run_idx < len(runs) - 1 and runs[run_idx + 1][0] == "cyr"
                    is_leading_spoof = (
                        run_idx == 0
                        and next_is_cyr
                        and digit in {"0", "3", "4", "6"}
                        and runs[1][1][0][1].islower()
                    )
                    is_trailing_spoof = (
                        run_idx == len(runs) - 1
                        and prev_is_cyr
                        and (
                            digit == "0"
                            or (digit == "6" and runs[run_idx - 1][1][-1][1].islower())
                        )
                    )
                    if (prev_is_cyr and next_is_cyr) or is_leading_spoof or is_trailing_spoof:
                        positions.append(idx)

        word_chars.clear()

    for idx, ch in enumerate(name):
        if is_ignorable_unicode(ch):
            continue
        if ch.isalpha() or ch.isdigit():
            word_chars.append((idx, ch))
        else:
            _flush_word()
    _flush_word()

    return sorted(set(positions))
