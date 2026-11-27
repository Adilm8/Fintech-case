"""Pure risk evaluation rules for BCC Business Shield.

Each rule is a pure function returning Signal | None using i18n message keys + parameters
and structured evidence.
"""

from __future__ import annotations

import math
import re
import statistics
from datetime import date
from typing import Any

from rapidfuzz import fuzz

from app.i18n import DEFAULT_LANG, Lang, t
from app.risk.bank_signals import get_bank_signals, is_bank_known_bin
from app.risk.config import (
    AMOUNT_ANOMALY_MIN_HISTORY,
    AMOUNT_FIRST_PAYMENT_RED_P90_MULT,
    AMOUNT_FIRST_PAYMENT_YELLOW_P90_MULT,
    AMOUNT_SUPPLIER_EXTREME_P90_MULT,
    BANK_COMPLAINTS_BLOCK_COUNT,
    BANK_COMPLAINTS_MIN_COUNT,
    BANK_FRESH_INFLOWS_HIGH_PAYERS,
    BANK_FRESH_INFLOWS_MEDIUM_PAYERS,
    BANK_FRESH_INFLOWS_WINDOW_DAYS,
    BCC_BANK_CODE,
    BCC_BIK,
    BIN_YOUNG_MAX_MONTHS,
    CLIENT_P90_MIN_HISTORY,
    DEMO_TODAY,
    DUPLICATE_INVOICE_WINDOW_DAYS,
    ENTITY_WRAPPER_PHRASES,
    KBE_INDIVIDUAL_CODES,
    KBE_LEGAL_ENTITY_CODES,
    LOOKALIKE_BLOCK_SIMILARITY_THRESHOLD,
    LOOKALIKE_DISTINCTIVE_FUZZY_THRESHOLD,
    LOOKALIKE_DISTINCTIVE_PREFIX_FUZZY_THRESHOLD,
    LOOKALIKE_DISTINCTIVE_THRESHOLD,
    LOOKALIKE_DISTINCTIVE_TOKEN_MIN_LEN,
    LOOKALIKE_DISTINCTIVE_WRAPPER_MIN_LEN,
    LOOKALIKE_PREFIX_MIN_LEN,
    LOOKALIKE_SIMILARITY_THRESHOLD,
    LOOKALIKE_TOKEN_SET_MIN_LEN,
    NEW_BCC_ACCOUNT_MAX_DAYS,
    NEW_RECIPIENT_ACCUM_WINDOW_DAYS,
    STRUCTURING_PAIR_MIN_RATIO,
    STRUCTURING_PRIMARY_RATIO,
    STRUCTURING_SPLIT_MIN_COUNT,
    STRUCTURING_SPLIT_MIN_RATIO,
    STRUCTURING_WINDOW_HOURS,
    URGENT_CYRILLIC_STEMS,
    URGENT_LATIN_PHRASES,
    URGENT_LATIN_STEMS,
    URGENT_PHRASES,
    WEIGHT_AMOUNT_ANOMALY_EXTREME,
    WEIGHT_AMOUNT_ANOMALY_PRIMARY,
    WEIGHT_BANK_CHANGED_AMPLIFIER,
    WEIGHT_BANK_CHANGED_HIGH_AMOUNT,
    WEIGHT_BIN_NAME_MISMATCH,
    WEIGHT_BIN_YOUNG,
    WEIGHT_DUPLICATE_INVOICE,
    WEIGHT_ENTITY_TYPE_MISMATCH,
    WEIGHT_ENTITY_TYPE_MISMATCH_LEGAL_IIN,
    WEIGHT_FRESH_IIK_MANY_PAYERS_HIGH,
    WEIGHT_FRESH_IIK_MANY_PAYERS_MEDIUM,
    WEIGHT_IIK_BELONGS_TO_OTHER_COUNTERPARTY,
    WEIGHT_IIK_CHANGED,
    WEIGHT_IIK_REPORTED_BY_CLIENTS,
    WEIGHT_KBE_MISMATCH_INDIVIDUAL_BIN,
    WEIGHT_KBE_MISMATCH_LEGAL_IIN,
    WEIGHT_KNP_UNUSUAL,
    WEIGHT_LOOKALIKE_SUPPLIER,
    WEIGHT_MIXED_SCRIPT_NAME,
    WEIGHT_NEW_BCC_ACCOUNT,
    WEIGHT_NEW_RECIPIENT_ACCUM_MAX,
    WEIGHT_NEW_RECIPIENT_ACCUM_MIN,
    WEIGHT_STRUCTURING_AMPLIFIER,
    WEIGHT_STRUCTURING_PRIMARY,
    WEIGHT_URGENT_WORDING,
)
from app.risk.names import (
    confusable_skeleton,
    detect_legal_form_kind,
    extract_ie_initials,
    find_mixed_script_positions,
    is_generic_company_token,
    name_similarity,
    normalize_company_name,
    normalize_company_name_translated,
    normalize_company_name_translit,
    sanitize_unicode,
    transliterate_cyr_to_lat,
)
from app.risk.profiles import ClientProfiles, confirm_supplier_accounts, profiles_enabled
from app.schemas import (
    AnalystDetails,
    AnalystSignalDetail,
    BccAccountAnalystInfo,
    CheckRequest,
    Evidence,
    Severity,
    Signal,
    compute_request_sha256,
)
from app.store import Store
from app.validators.kz import (
    bik_matches_iik,
    bik_ok,
    bin_iin_checksum_ok,
    bin_kind,
    bin_registration_yymm,
    iik_bank_code,
    iik_check,
)


def _format_kzt(amount: float) -> str:
    return f"{round(amount):,} ₸".replace(",", " ")


def _make_evidence(
    field: str,
    *,
    lang: Lang = DEFAULT_LANG,
    expected: str | None = None,
    expected_key: str | None = None,
    expected_params: dict[str, Any] | None = None,
    actual: str | None = None,
    actual_key: str | None = None,
    actual_params: dict[str, Any] | None = None,
    since: str | None = None,
    positions: list[int] | None = None,
) -> Evidence:
    """Build a localized Evidence payload with re-localizable i18n keys."""
    exp_p = dict(expected_params or {})
    act_p = dict(actual_params or {})
    exp_val = t(expected_key, lang, **exp_p) if expected_key else expected
    act_val = t(actual_key, lang, **act_p) if actual_key else actual
    field_lbl_key = f"ev.field.{field}"
    field_lbl = (
        t(field_lbl_key, lang)
        if field in ("bin", "iik", "bik", "bank", "name", "amount", "purpose")
        else field
    )
    return Evidence(
        field=field,
        field_label=field_lbl,
        expected=exp_val,
        actual=act_val,
        since=since,
        positions=positions,
        expected_key=expected_key,
        expected_params=exp_p,
        actual_key=actual_key,
        actual_params=act_p,
    )


def _make_signal(
    rule_id: str,
    points: int,
    severity: Severity,
    message_key: str,
    evidence: Evidence,
    *,
    lang: Lang = DEFAULT_LANG,
    **params: Any,
) -> Signal:
    """Build a Signal whose text is rendered from an i18n message key and parameters."""
    return Signal(
        rule_id=rule_id,
        points=points,
        severity=severity,
        reason_ru=t(message_key, "ru", **params),
        reason=t(message_key, lang, **params),
        message_key=message_key,
        message_params=dict(params),
        evidence=evidence,
    )


_UNSET: Any = object()


def _resolve_profiles(
    store: Store,
    payer_id: str | None,
    profiles: ClientProfiles | None,
) -> ClientProfiles | None:
    """Return provided profiles, or fetch from store unless BCC_DISABLE_PROFILES is active."""
    if profiles is not None:
        return profiles
    if not profiles_enabled():
        return None
    return store.get_profiles(payer_id)


def _compute_percentile(sorted_amounts: list[float], pct: float) -> float:
    pos = pct * (len(sorted_amounts) - 1)
    lo = math.floor(pos)
    hi = math.ceil(pos)
    return sorted_amounts[lo] + (sorted_amounts[hi] - sorted_amounts[lo]) * (pos - lo)


def compute_client_p90(
    store: Store,
    payer_id: str | None = None,
    *,
    profiles: ClientProfiles | None = None,
) -> float | None:
    """Compute the 90th percentile of all historical payment amounts for the client."""
    prof = _resolve_profiles(store, payer_id, profiles)
    if prof is not None:
        return prof.client_p90
    history = store.get_client_history(payer_id)
    if len(history) < CLIENT_P90_MIN_HISTORY:
        return None
    amounts = sorted(float(p["amount_kzt"]) for p in history if float(p["amount_kzt"]) > 0)
    if len(amounts) < CLIENT_P90_MIN_HISTORY:
        return None
    return _compute_percentile(amounts, 0.9)


def compute_client_median(
    store: Store,
    payer_id: str | None = None,
    *,
    profiles: ClientProfiles | None = None,
) -> float | None:
    """Compute the median of all historical payment amounts for the client."""
    prof = _resolve_profiles(store, payer_id, profiles)
    if prof is not None:
        return prof.client_median
    history = store.get_client_history(payer_id)
    amounts = [float(p["amount_kzt"]) for p in history if float(p["amount_kzt"]) > 0]
    if len(amounts) < CLIENT_P90_MIN_HISTORY:
        return None
    return float(statistics.median(amounts))


_INVOICE_EXPLICIT_RE = re.compile(
    r"(?<!\w)(?:счет(?:у|а|ом|е)?|сч\.?|шот(?:қа|ы)?|инвойс(?:у|а)?|invoice|inv\.?)"
    r"\s*(?:№|#|n[o°]?\.?)?\s*(\d+[a-zа-я0-9/-]*)",
    flags=re.UNICODE,
)
_INVOICE_STANDALONE_RE = re.compile(
    r"(?:№|#|(?<!\w)no\.?)\s*(\d+[a-zа-я0-9/-]*)",
    flags=re.UNICODE,
)
_NON_INVOICE_PREFIX_RE = re.compile(
    r"(?:договор\w*|соглашени\w*|контракт\w*|приложени\w*|доп\.?\s*соглаш\w*)\s*$",
    flags=re.UNICODE,
)


def extract_invoice_number(purpose: str | None) -> str | None:
    """Extract normalized invoice number ('№ 214', 'счёт № 214', 'сч. 214') from payment purpose.

    Ignores contract/agreement numbers like 'по договору № 14-А' or 'по доп. соглашению № 2'.
    """
    if not purpose:
        return None
    cleaned = sanitize_unicode(purpose).lower().replace("ё", "е")
    explicit = _INVOICE_EXPLICIT_RE.search(cleaned)
    if explicit is not None:
        return explicit.group(1).strip("-/")

    for match in _INVOICE_STANDALONE_RE.finditer(cleaned):
        before = cleaned[: match.start()]
        if _NON_INVOICE_PREFIX_RE.search(before):
            continue
        return match.group(1).strip("-/")
    return None


def is_bcc_bank_verified_new_account(
    req: CheckRequest,
    store: Store,
    *,
    profiles: ClientProfiles | None = None,
) -> bool:
    """Return True when a known supplier switches to a new BCC IIK owned by the exact same BIN."""
    prof = _resolve_profiles(store, req.payer_id, profiles)
    if prof is not None:
        sup = prof.get_supplier(req.recipient_bin)
        if sup is None:
            return False
        if store.is_trusted(req.recipient_bin, req.recipient_iik, payer_id=req.payer_id):
            return False
        if req.recipient_iik in sup.known_iiks:
            return False
    else:
        supplier_history = store.get_supplier_history(req.recipient_bin, req.payer_id)
        if not supplier_history:
            return False
        if store.is_trusted(req.recipient_bin, req.recipient_iik, payer_id=req.payer_id):
            return False
        if req.recipient_iik in confirm_supplier_accounts(supplier_history).known_iiks:
            return False
    if iik_bank_code(req.recipient_iik) != BCC_BANK_CODE:
        return False
    account = store.bcc_accounts.get(req.recipient_iik)
    return account is not None and account.get("owner_bin") == req.recipient_bin


# --- Precheck rules (produce invalid verdict, no score) ---


def rule_bin_format(req: CheckRequest, *, lang: Lang = DEFAULT_LANG) -> Signal | None:
    """Validate BIN/IIN format, 5th digit classification, and mod-11 checksum."""
    if bin_iin_checksum_ok(req.recipient_bin) and bin_kind(req.recipient_bin) is not None:
        return None
    return _make_signal(
        rule_id="invalid_bin",
        points=0,
        severity="block",
        message_key="rule.invalid_bin",
        evidence=_make_evidence(
            "bin",
            lang=lang,
            expected_key="ev.bin_expected",
            actual=req.recipient_bin,
        ),
        lang=lang,
    )


def rule_iik_format(
    req: CheckRequest,
    store: Store | None = None,
    *,
    lang: Lang = DEFAULT_LANG,
) -> Signal | None:
    """Validate IIK format, Cyrillic lookalikes, IBAN mod-97, and known bank code (M4)."""
    banks_path = store.banks_path if store is not None else None
    ok, msg_key, params = iik_check(
        req.recipient_iik,
        check_bank_code=True,
        banks_path=banks_path,
    )
    if ok:
        return None
    return _make_signal(
        rule_id="invalid_iik",
        points=0,
        severity="block",
        message_key=msg_key or "rule.invalid_iik_fallback",
        evidence=_make_evidence(
            "iik",
            lang=lang,
            expected_key="ev.iik_expected",
            actual=req.recipient_iik,
        ),
        lang=lang,
        **params,
    )


def rule_bik_format(
    req: CheckRequest,
    store: Store,
    *,
    lang: Lang = DEFAULT_LANG,
) -> Signal | None:
    """Validate that BIK is 8 characters and exists in banks.json."""
    if bik_ok(req.recipient_bik, path=store.banks_path):
        return None
    return _make_signal(
        rule_id="invalid_bik",
        points=0,
        severity="block",
        message_key="rule.invalid_bik",
        evidence=_make_evidence(
            "bik",
            lang=lang,
            expected_key="ev.bik_expected",
            actual=req.recipient_bik,
        ),
        lang=lang,
    )


def rule_iik_bank_code_vs_bik(
    req: CheckRequest,
    store: Store,
    *,
    lang: Lang = DEFAULT_LANG,
) -> Signal | None:
    """Verify that the 3-digit bank code in IIK matches the specified BIK."""
    code = iik_bank_code(req.recipient_iik)
    if code is None or not bik_ok(req.recipient_bik, path=store.banks_path):
        return None
    if bik_matches_iik(req.recipient_bik, req.recipient_iik, path=store.banks_path):
        return None

    expected_bank = store.banks_by_bik.get(req.recipient_bik)
    actual_bank = store.banks_by_code.get(code)
    exp_key = "ev.bank_code_bik" if expected_bank is not None else None
    exp_params = (
        {"code": expected_bank["code"], "bik": expected_bank["bik"]}
        if expected_bank is not None
        else None
    )
    act_key = "ev.bank_code_bik" if actual_bank is not None else "ev.bank_code_only"
    act_params = (
        {"code": code, "bik": actual_bank["bik"]} if actual_bank is not None else {"code": code}
    )
    return _make_signal(
        rule_id="iik_bank_code_vs_bik",
        points=0,
        severity="block",
        message_key="rule.iik_bank_code_vs_bik",
        evidence=_make_evidence(
            "bik",
            lang=lang,
            expected=None if exp_key else req.recipient_bik,
            expected_key=exp_key,
            expected_params=exp_params,
            actual_key=act_key,
            actual_params=act_params,
        ),
        lang=lang,
    )


def rule_bcc_account_not_found(
    req: CheckRequest,
    store: Store,
    *,
    lang: Lang = DEFAULT_LANG,
) -> Signal | None:
    """Reject a syntactically valid BCC (856) IIK that does not exist in bcc_accounts."""
    if iik_bank_code(req.recipient_iik) != BCC_BANK_CODE:
        return None
    if req.recipient_iik in store.bcc_accounts:
        return None
    return _make_signal(
        rule_id="bcc_account_not_found",
        points=0,
        severity="block",
        message_key="rule.bcc_account_not_found",
        evidence=_make_evidence(
            "iik",
            lang=lang,
            expected_key="ev.bcc_active_expected",
            actual=req.recipient_iik,
        ),
        lang=lang,
    )


# --- Blocking & risk scoring rules ---


def rule_bcc_account_other_owner(
    req: CheckRequest,
    store: Store,
    *,
    lang: Lang = DEFAULT_LANG,
) -> Signal | None:
    """Block payment when a BCC IIK belongs to a different BIN in BCC's account registry.

    Client-facing output omits account owner name, owner BIN, and opening date to preserve
    banking secrecy; full details are exposed only via analyst_details for X-Role: analyst.
    """
    is_bcc = iik_bank_code(req.recipient_iik) == BCC_BANK_CODE or req.recipient_bik == BCC_BIK
    if not is_bcc:
        return None

    account = store.bcc_accounts.get(req.recipient_iik)
    if account is None:
        return None

    owner_bin = account["owner_bin"]
    if owner_bin == req.recipient_bin:
        return None

    return _make_signal(
        rule_id="bcc_account_other_owner",
        points=100,
        severity="block",
        message_key="rule.bcc_account_other_owner",
        evidence=_make_evidence(
            "iik",
            lang=lang,
            expected_key="ev.bcc_owner_expected",
            actual_key="ev.bcc_owner_mismatch",
            since=None,
        ),
        lang=lang,
    )


def rule_iik_reported_by_clients(
    req: CheckRequest,
    store: Store,
    *,
    lang: Lang = DEFAULT_LANG,
    bank_signals: dict[str, Any] | None = None,
) -> Signal | None:
    """Flag an IIK reported as fraudulent by other BCC clients (1-2 -> primary 60; >=3 -> block).

    Client-facing message and evidence remain anonymous and bucketed without reporter identities,
    exact counts, or report dates; exact metadata is exposed only via analyst_details.
    """
    signals_data = get_bank_signals(store, bank_signals=bank_signals)
    entry = signals_data["complaints"].get(req.recipient_iik)
    if not isinstance(entry, dict):
        return None

    count = int(entry.get("count", 0))
    if count < BANK_COMPLAINTS_MIN_COUNT:
        return None

    if count >= BANK_COMPLAINTS_BLOCK_COUNT:
        return _make_signal(
            rule_id="iik_reported_by_clients",
            points=100,
            severity="block",
            message_key="rule.iik_reported_by_clients_many",
            evidence=_make_evidence(
                "iik",
                lang=lang,
                expected_key="ev.bank_complaints_expected",
                actual_key="ev.bank_complaints_actual_many",
                since=None,
            ),
            lang=lang,
        )

    return _make_signal(
        rule_id="iik_reported_by_clients",
        points=WEIGHT_IIK_REPORTED_BY_CLIENTS,
        severity="primary",
        message_key="rule.iik_reported_by_clients",
        evidence=_make_evidence(
            "iik",
            lang=lang,
            expected_key="ev.bank_complaints_expected",
            actual_key="ev.bank_complaints_actual_some",
            since=None,
        ),
        lang=lang,
    )


def rule_iik_on_watchlist(
    req: CheckRequest,
    store: Store,
    *,
    lang: Lang = DEFAULT_LANG,
    bank_signals: dict[str, Any] | None = None,
) -> Signal | None:
    """Block payment when the recipient IIK appears on the antifraud center mule watchlist."""
    signals_data = get_bank_signals(store, bank_signals=bank_signals)
    entry = signals_data["mule_watchlist"].get(req.recipient_iik)
    if entry is None or entry is False:
        return None

    return _make_signal(
        rule_id="iik_on_watchlist",
        points=100,
        severity="block",
        message_key="rule.iik_on_watchlist",
        evidence=_make_evidence(
            "iik",
            lang=lang,
            expected_key="ev.watchlist_expected",
            actual_key="ev.watchlist_actual",
            since=None,
        ),
        lang=lang,
    )


def rule_fresh_iik_many_payers(
    req: CheckRequest,
    store: Store,
    *,
    today: date = DEMO_TODAY,
    lang: Lang = DEFAULT_LANG,
    bank_signals: dict[str, Any] | None = None,
) -> Signal | None:
    """Flag a fresh account receiving first-time payments from >=3 (>=5) unrelated BCC clients.

    Exempts recipients whose BIN has long-standing history in BCC (bank_known_bin).
    Client-facing text uses only anonymous bucketed ranges (3+ / 5+); exact payer counts
    and cumulative volumes appear only in analyst_details.
    """
    signals_data = get_bank_signals(store, bank_signals=bank_signals)
    entry = signals_data["fresh_inflows"].get(req.recipient_iik)
    if not isinstance(entry, dict):
        return None

    distinct_payers = int(entry.get("distinct_payers_7d", 0))
    if distinct_payers < BANK_FRESH_INFLOWS_MEDIUM_PAYERS:
        return None

    if is_bank_known_bin(req.recipient_bin, signals_data, today=today):
        return None

    if distinct_payers >= BANK_FRESH_INFLOWS_HIGH_PAYERS:
        points = WEIGHT_FRESH_IIK_MANY_PAYERS_HIGH
        msg_key = "rule.fresh_iik_many_payers_many"
        actual_key = "ev.fresh_inflows_actual_high"
    else:
        points = WEIGHT_FRESH_IIK_MANY_PAYERS_MEDIUM
        msg_key = "rule.fresh_iik_many_payers"
        actual_key = "ev.fresh_inflows_actual_medium"

    return _make_signal(
        rule_id="fresh_iik_many_payers",
        points=points,
        severity="primary",
        message_key=msg_key,
        evidence=_make_evidence(
            "iik",
            lang=lang,
            expected_key="ev.fresh_inflows_expected",
            actual_key=actual_key,
            since=None,
        ),
        lang=lang,
    )


def _classify_supplier_distinctive_tokens(sup_cyr_tokens: list[str]) -> tuple[list[str], list[str]]:
    """Decide distinctive vs generic tokens ONCE on lower-case Cyrillic and project to Latin."""
    distinctive_cyr = [
        tok
        for tok in sup_cyr_tokens
        if len(tok) >= LOOKALIKE_DISTINCTIVE_TOKEN_MIN_LEN and not is_generic_company_token(tok)
    ]
    distinctive_lat = [transliterate_cyr_to_lat(tok) for tok in distinctive_cyr]
    return distinctive_cyr, distinctive_lat


def _common_prefix_len(a: str, b: str) -> int:
    limit = min(len(a), len(b))
    i = 0
    while i < limit and a[i] == b[i]:
        i += 1
    return i


def _strip_wrapper_phrases(tokens: list[str]) -> list[str]:
    """Remove entity wrapper phrases (e.g. 'торговый дом', 'тд', 'фирма') from Cyrillic tokens."""
    out: list[str] = []
    i = 0
    n = len(tokens)
    while i < n:
        matched_len = 0
        for phrase in ENTITY_WRAPPER_PHRASES:
            plen = len(phrase)
            if plen <= n - i and tuple(tokens[i : i + plen]) == phrase:
                matched_len = max(matched_len, plen)
        if matched_len > 0:
            i += matched_len
        else:
            out.append(tokens[i])
            i += 1
    return out


def _ie_initials_compatible(
    cand_name: str,
    sup_name: str,
    cand_bin: str,
    sup_bin: str,
) -> bool:
    """For IE-to-IE comparisons, require initials to match (different initials -> different person)."""
    cand_is_ie = detect_legal_form_kind(cand_name) == "iin" or bin_kind(cand_bin) == "iin"
    sup_is_ie = detect_legal_form_kind(sup_name) == "iin" or bin_kind(sup_bin) == "iin"
    if not (cand_is_ie and sup_is_ie):
        return True

    sup_init = extract_ie_initials(sup_name)
    if not sup_init:
        return True
    cand_init = extract_ie_initials(cand_name)
    if not cand_init:
        return False

    min_len = min(len(cand_init), len(sup_init))
    return cand_init[:min_len] == sup_init[:min_len]


def _all_supplier_tokens_matched(sup_tokens: list[str], cand_tokens: list[str]) -> bool:
    """Return True if every supplier token matches a candidate token exactly or as a prefix."""
    if not sup_tokens or not cand_tokens:
        return False
    for st in sup_tokens:
        if len(st) >= LOOKALIKE_PREFIX_MIN_LEN:
            if not any(ct == st or ct.startswith(st) for ct in cand_tokens):
                return False
        elif st not in cand_tokens:
            return False
    return True


def _has_distinctive_token_match(
    distinctive_tokens: list[str],
    cand_tokens: list[str],
    cand_compact: str,
) -> bool:
    """Return True if a supplier distinctive token matches a non-generic candidate token."""
    if not distinctive_tokens or not cand_tokens:
        return False
    cand_non_generic = [ct for ct in cand_tokens if not is_generic_company_token(ct)]
    for dt in distinctive_tokens:
        if any(ct == dt or ct.startswith(dt) for ct in cand_non_generic):
            return True
        if dt in cand_compact:
            return True
        if len(dt) >= 5:
            for ct in cand_non_generic:
                if len(ct) < 5:
                    continue
                tok_sim = float(fuzz.ratio(ct, dt))
                if tok_sim >= LOOKALIKE_DISTINCTIVE_FUZZY_THRESHOLD:
                    return True
                if (
                    _common_prefix_len(ct, dt) >= 4
                    and tok_sim >= LOOKALIKE_DISTINCTIVE_PREFIX_FUZZY_THRESHOLD
                    and abs(len(ct) - len(dt)) <= 2
                ):
                    return True
    return False


def _matches_abbreviated_supplier(
    cand_cyr_tokens: list[str],
    sup_cyr_tokens: list[str],
    distinctive_cyr: list[str],
) -> bool:
    """Detect initial-letter abbreviation of a distinctive token + matching companion token(s).

    Example: 'ТОО «А-Снаб»' (['а', 'снаб']) against 'ТОО «Алатау Снаб»' (['алатау', 'снаб']).
    """
    if (
        len(sup_cyr_tokens) < 2
        or len(cand_cyr_tokens) != len(sup_cyr_tokens)
        or not distinctive_cyr
    ):
        return False
    distinctive_set = set(distinctive_cyr)
    has_abbr = False
    has_full = False
    for ct, st in zip(cand_cyr_tokens, sup_cyr_tokens, strict=True):
        if 1 <= len(ct) <= 2 and st in distinctive_set and st.startswith(ct):
            has_abbr = True
        elif len(st) >= LOOKALIKE_PREFIX_MIN_LEN and (ct == st or ct.startswith(st)):
            has_full = True
        else:
            return False
    return has_abbr and has_full


def _true_pair_similarity(cand: str, sup: str) -> float:
    """Compute true normalized similarity (0..100) without containment inflation."""
    if not cand or not sup:
        return 0.0
    cand_compact = "".join(cand.split())
    sup_compact = "".join(sup.split())
    if cand == sup or cand_compact == sup_compact:
        return 100.0
    return max(
        float(fuzz.ratio(cand, sup)),
        float(fuzz.token_sort_ratio(cand, sup)),
        float(fuzz.ratio(cand_compact, sup_compact)),
    )


def _score_lookalike_pair(
    cand: str,
    sup: str,
    distinctive_tokens: list[str],
) -> tuple[float, float]:
    """Return (match_score, true_similarity) for a normalized candidate/supplier pair."""
    if not cand or not sup:
        return 0.0, 0.0

    cand_tokens = cand.split()
    sup_tokens = sup.split()
    cand_compact = "".join(cand_tokens)
    sup_compact = "".join(sup_tokens)

    # 1. Exact match after folding or transliteration (including spacing differences), any length.
    if cand == sup or cand_compact == sup_compact:
        return 100.0, 100.0

    sim = max(
        float(fuzz.ratio(cand, sup)),
        float(fuzz.token_sort_ratio(cand, sup)),
        float(fuzz.ratio(cand_compact, sup_compact)),
    )

    has_generic_split = bool(distinctive_tokens) and len(distinctive_tokens) < len(sup_tokens)
    distinctive_ok = (not has_generic_split) or _has_distinctive_token_match(
        distinctive_tokens, cand_tokens, cand_compact
    )

    # 2. High overall similarity (>= 85); guard against generic-word inflation when supplier mixes
    #    distinctive and generic tokens (e.g. 'Актау Снаб' vs 'Алатау Снаб').
    if sim >= LOOKALIKE_SIMILARITY_THRESHOLD and distinctive_ok:
        return sim, sim

    # 3. Full supplier prefix/token containment (for supplier names >= 8 compact chars).
    if len(sup_compact) >= LOOKALIKE_TOKEN_SET_MIN_LEN:
        if sup_compact in cand_compact:
            return max(sim, LOOKALIKE_SIMILARITY_THRESHOLD), sim
        if _all_supplier_tokens_matched(sup_tokens, cand_tokens):
            return max(
                sim, float(fuzz.token_set_ratio(cand, sup)), LOOKALIKE_SIMILARITY_THRESHOLD
            ), sim

    # 4. Distinctive token match with lowered similarity threshold (~70).
    if sim >= LOOKALIKE_DISTINCTIVE_THRESHOLD and _has_distinctive_token_match(
        distinctive_tokens, cand_tokens, cand_compact
    ):
        return sim, sim

    return 0.0, sim


def find_lookalike_supplier(
    req: CheckRequest,
    store: Store,
    *,
    profiles: ClientProfiles | None = None,
) -> dict[str, Any] | None:
    """Find the closest known client supplier with lookalike similarity and a different BIN.

    Skipped (M1) if recipient_bin already has its own payment history or is trusted.
    Decides distinctive vs generic supplier tokens ONCE on lower-case Cyrillic and carries
    that decision to transliterated/cased forms. For IE pairs, requires matching initials.
    Returns dict with bin, name, first_seen, similarity (true normalized similarity 0..100),
    and match_score.
    """
    prof = _resolve_profiles(store, req.payer_id, profiles)
    if prof is not None:
        if prof.get_supplier(req.recipient_bin) is not None:
            return None
    elif store.get_supplier_history(req.recipient_bin, req.payer_id):
        return None
    if store.is_bin_trusted(req.recipient_bin, payer_id=req.payer_id):
        return None

    norm_req = normalize_company_name(req.recipient_name)
    cyr_req, lat_req = normalize_company_name_translit(req.recipient_name)
    trans_req = normalize_company_name_translated(req.recipient_name)
    if not norm_req and not cyr_req:
        return None

    cand_is_ie = (
        detect_legal_form_kind(req.recipient_name) == "iin" or bin_kind(req.recipient_bin) == "iin"
    )

    if prof is not None:
        cand_ie_init = extract_ie_initials(req.recipient_name) if cand_is_ie else ()
        norm_req_tokens = norm_req.split()
        cyr_req_tokens = cyr_req.split()
        trans_req_tokens = trans_req.split()
        trans_req_compact = "".join(trans_req_tokens)
        cand_core = _strip_wrapper_phrases(trans_req_tokens) if trans_req_tokens else []

        best_match: dict[str, Any] | None = None
        best_score = 0.0
        best_similarity = 0.0
        for supplier in prof.suppliers.values():
            if supplier.recipient_bin == req.recipient_bin:
                continue
            if cand_is_ie and supplier.is_ie and supplier.ie_initials:
                if not cand_ie_init:
                    continue
                min_len = min(len(cand_ie_init), len(supplier.ie_initials))
                if cand_ie_init[:min_len] != supplier.ie_initials[:min_len]:
                    continue

            norm_sup = supplier.normalized_name
            cyr_sup = supplier.translit_cyr
            lat_sup = supplier.translit_lat
            trans_sup = supplier.translated_name
            if not norm_sup and not cyr_sup:
                continue

            sup_base_cyr_tokens = list(supplier.base_cyr_tokens)
            distinctive_cyr = list(supplier.distinctive_cyr_tokens)
            distinctive_lat = list(supplier.distinctive_lat_tokens)
            sup_is_ie = supplier.is_ie

            view_results = (
                _score_lookalike_pair(norm_req, norm_sup, distinctive_cyr),
                _score_lookalike_pair(cyr_req, cyr_sup, distinctive_cyr),
                _score_lookalike_pair(lat_req, lat_sup, distinctive_lat),
            )
            matched_score = max(score for score, _ in view_results)
            true_sim = max(sim for _, sim in view_results)

            # 5. Translated business-term equivalence (e.g. 'Alatau Supply' -> 'алатау снаб').
            if trans_req and trans_sup and distinctive_cyr:
                trans_sim = _true_pair_similarity(trans_req, trans_sup)
                if trans_sim >= LOOKALIKE_SIMILARITY_THRESHOLD and _has_distinctive_token_match(
                    distinctive_cyr, trans_req_tokens, trans_req_compact
                ):
                    matched_score = max(
                        matched_score,
                        min(trans_sim, LOOKALIKE_BLOCK_SIMILARITY_THRESHOLD - 1.0),
                    )

            # 6. Entity-wrapper clone (e.g. 'Торговый дом Алатау' -> ['алатау'] vs 'Алатау Снаб').
            if (
                not sup_is_ie
                and trans_req
                and distinctive_cyr
                and cand_core
                and cand_core != trans_req_tokens
                and len("".join(distinctive_cyr)) >= LOOKALIKE_DISTINCTIVE_WRAPPER_MIN_LEN
                and cand_core == distinctive_cyr
            ):
                matched_score = max(matched_score, LOOKALIKE_DISTINCTIVE_THRESHOLD)

            # 7. Initial-letter abbreviation of distinctive brand token (e.g. 'А-Снаб' vs 'Алатау Снаб').
            if not sup_is_ie and not cand_is_ie and distinctive_cyr:
                for cand_toks in (norm_req_tokens, cyr_req_tokens, trans_req_tokens):
                    if _matches_abbreviated_supplier(
                        cand_toks, sup_base_cyr_tokens, distinctive_cyr
                    ):
                        matched_score = max(matched_score, LOOKALIKE_DISTINCTIVE_THRESHOLD)
                        break

            if matched_score > best_score or (
                matched_score > 0.0 and matched_score == best_score and true_sim > best_similarity
            ):
                best_score = matched_score
                best_similarity = true_sim
                best_match = {
                    "bin": supplier.recipient_bin,
                    "name": supplier.first_name,
                    "first_seen": supplier.first_paid_at,
                    "similarity": true_sim,
                    "match_score": matched_score,
                }

        return best_match

    history = store.get_client_history(req.payer_id)
    suppliers_by_bin: dict[str, dict[str, str]] = {}
    for payment in history:
        sup_bin = payment["recipient_bin"]
        if sup_bin == req.recipient_bin:
            continue
        if sup_bin not in suppliers_by_bin:
            suppliers_by_bin[sup_bin] = {
                "bin": sup_bin,
                "name": payment["recipient_name"],
                "first_seen": payment["paid_at"],
            }

    best_match = None
    best_score = 0.0
    best_similarity = 0.0
    for supplier_raw in suppliers_by_bin.values():
        if not _ie_initials_compatible(
            req.recipient_name,
            supplier_raw["name"],
            req.recipient_bin,
            supplier_raw["bin"],
        ):
            continue

        norm_sup = normalize_company_name(supplier_raw["name"])
        cyr_sup, lat_sup = normalize_company_name_translit(supplier_raw["name"])
        trans_sup = normalize_company_name_translated(supplier_raw["name"])
        if not norm_sup and not cyr_sup:
            continue

        sup_base_cyr_tokens = norm_sup.split() or cyr_sup.split()
        distinctive_cyr, distinctive_lat = _classify_supplier_distinctive_tokens(
            sup_base_cyr_tokens
        )
        sup_is_ie = (
            detect_legal_form_kind(supplier_raw["name"]) == "iin"
            or bin_kind(supplier_raw["bin"]) == "iin"
        )

        view_results = (
            _score_lookalike_pair(norm_req, norm_sup, distinctive_cyr),
            _score_lookalike_pair(cyr_req, cyr_sup, distinctive_cyr),
            _score_lookalike_pair(lat_req, lat_sup, distinctive_lat),
        )
        matched_score = max(score for score, _ in view_results)
        true_sim = max(sim for _, sim in view_results)

        # 5. Translated business-term equivalence (e.g. 'Alatau Supply' -> 'алатау снаб').
        if trans_req and trans_sup and distinctive_cyr:
            trans_sim = _true_pair_similarity(trans_req, trans_sup)
            trans_req_tokens = trans_req.split()
            if trans_sim >= LOOKALIKE_SIMILARITY_THRESHOLD and _has_distinctive_token_match(
                distinctive_cyr, trans_req_tokens, "".join(trans_req_tokens)
            ):
                matched_score = max(
                    matched_score,
                    min(trans_sim, LOOKALIKE_BLOCK_SIMILARITY_THRESHOLD - 1.0),
                )

        # 6. Entity-wrapper clone (e.g. 'Торговый дом Алатау' -> ['алатау'] vs 'Алатау Снаб').
        if not sup_is_ie and trans_req and distinctive_cyr:
            trans_req_tokens = trans_req.split()
            cand_core = _strip_wrapper_phrases(trans_req_tokens)
            if (
                cand_core
                and cand_core != trans_req_tokens
                and len("".join(distinctive_cyr)) >= LOOKALIKE_DISTINCTIVE_WRAPPER_MIN_LEN
                and cand_core == distinctive_cyr
            ):
                matched_score = max(matched_score, LOOKALIKE_DISTINCTIVE_THRESHOLD)

        # 7. Initial-letter abbreviation of distinctive brand token (e.g. 'А-Снаб' vs 'Алатау Снаб').
        if not sup_is_ie and not cand_is_ie and distinctive_cyr:
            for cand_toks in (norm_req.split(), cyr_req.split(), trans_req.split()):
                if _matches_abbreviated_supplier(cand_toks, sup_base_cyr_tokens, distinctive_cyr):
                    matched_score = max(matched_score, LOOKALIKE_DISTINCTIVE_THRESHOLD)
                    break

        if matched_score > best_score or (
            matched_score > 0.0 and matched_score == best_score and true_sim > best_similarity
        ):
            best_score = matched_score
            best_similarity = true_sim
            best_match = {
                **supplier_raw,
                "similarity": true_sim,
                "match_score": matched_score,
            }

    return best_match


def rule_lookalike_supplier(
    req: CheckRequest,
    store: Store,
    *,
    lang: Lang = DEFAULT_LANG,
    profiles: ClientProfiles | None = None,
    lookalike_match: Any = _UNSET,
) -> Signal | None:
    """Detect supplier name impersonation against known client suppliers with a different BIN.

    Exact or near-exact normalized match (similarity >= 95) with a different BIN escalates to
    block (red, 100 pts) regardless of BIN age because a legal entity's BIN never changes.
    Fuzzy/variant/wrapper/translated/abbreviated lookalikes return primary (60 pts).
    """
    match = (
        find_lookalike_supplier(req, store, profiles=profiles)
        if lookalike_match is _UNSET
        else lookalike_match
    )
    if match is None:
        return None

    is_exact = float(match.get("similarity", 0.0)) >= LOOKALIKE_BLOCK_SIMILARITY_THRESHOLD
    points = 100 if is_exact else WEIGHT_LOOKALIKE_SUPPLIER
    severity: Severity = "block" if is_exact else "primary"
    message_key = "rule.lookalike_supplier_exact" if is_exact else "rule.lookalike_supplier"

    return _make_signal(
        rule_id="lookalike_supplier",
        points=points,
        severity=severity,
        message_key=message_key,
        evidence=_make_evidence(
            "name",
            lang=lang,
            expected_key="ev.name_bin",
            expected_params={"name": match["name"], "bin": match["bin"]},
            actual_key="ev.name_bin",
            actual_params={"name": req.recipient_name, "bin": req.recipient_bin},
            since=match["first_seen"],
        ),
        lang=lang,
        supplier_name=match["name"],
    )


def rule_mixed_script_name(req: CheckRequest, *, lang: Lang = DEFAULT_LANG) -> Signal | None:
    """Flag foreign-script letters or confusable digits embedded inside Cyrillic words."""
    positions = find_mixed_script_positions(req.recipient_name)
    if not positions:
        return None
    return _make_signal(
        rule_id="mixed_script_name",
        points=WEIGHT_MIXED_SCRIPT_NAME,
        severity="primary",
        message_key="rule.mixed_script_name",
        evidence=_make_evidence(
            "name",
            lang=lang,
            expected_key="ev.single_script_expected",
            actual_key="ev.mixed_script_actual",
        ),
        lang=lang,
    )


def rule_bin_name_mismatch(
    req: CheckRequest,
    store: Store,
    *,
    lang: Lang = DEFAULT_LANG,
    profiles: ClientProfiles | None = None,
) -> Signal | None:
    """Flag when the recipient name does not match the legal entity registered for this BIN.

    Downgrades to info (0 pts) if the exact (BIN, IIK) pair is already in payment history (M3).
    """
    registered_name = store.registry.get(req.recipient_bin)
    if registered_name is None:
        return None

    if name_similarity(req.recipient_name, registered_name) >= LOOKALIKE_SIMILARITY_THRESHOLD:
        return None

    prof = _resolve_profiles(store, req.payer_id, profiles)
    if prof is not None:
        sup = prof.get_supplier(req.recipient_bin)
        pair_in_history = sup is not None and req.recipient_iik in sup.known_iiks
        since_date = sup.last_paid_at if sup is not None else None
    else:
        supplier_history = store.get_supplier_history(req.recipient_bin, req.payer_id)
        pair_in_history = (
            req.recipient_iik in confirm_supplier_accounts(supplier_history).known_iiks
        )
        since_date = supplier_history[-1]["paid_at"] if supplier_history else None

    if pair_in_history:
        return _make_signal(
            rule_id="bin_name_mismatch",
            points=0,
            severity="info",
            message_key="rule.bin_name_mismatch_history",
            evidence=_make_evidence(
                "bin",
                lang=lang,
                expected=registered_name,
                actual=req.recipient_name,
                since=since_date,
            ),
            lang=lang,
            registered_name=registered_name,
        )

    return _make_signal(
        rule_id="bin_name_mismatch",
        points=WEIGHT_BIN_NAME_MISMATCH,
        severity="primary",
        message_key="rule.bin_name_mismatch",
        evidence=_make_evidence(
            "bin",
            lang=lang,
            expected=registered_name,
            actual=req.recipient_name,
        ),
        lang=lang,
        registered_name=registered_name,
    )


def rule_iik_belongs_to_other_counterparty(
    req: CheckRequest,
    store: Store,
    *,
    lang: Lang = DEFAULT_LANG,
    profiles: ClientProfiles | None = None,
) -> Signal | None:
    """Flag when the IIK was previously paid or trusted under a different supplier BIN (M7)."""
    prof = _resolve_profiles(store, req.payer_id, profiles)
    if prof is not None:
        last_usage = prof.find_other_counterparty_for_iik(req.recipient_iik, req.recipient_bin)
        if last_usage is not None:
            return _make_signal(
                rule_id="iik_belongs_to_other_counterparty",
                points=WEIGHT_IIK_BELONGS_TO_OTHER_COUNTERPARTY,
                severity="primary",
                message_key="rule.iik_belongs_to_other_counterparty",
                evidence=_make_evidence(
                    "iik",
                    lang=lang,
                    expected_key="ev.account_for_bin",
                    expected_params={"bin": req.recipient_bin},
                    actual_key="ev.used_for_other",
                    actual_params={
                        "name": last_usage.recipient_name,
                        "bin": last_usage.recipient_bin,
                    },
                    since=last_usage.paid_at,
                ),
                lang=lang,
                other_name=last_usage.recipient_name,
            )
    else:
        history = store.get_client_history(req.payer_id)
        other_payments = [
            p
            for p in history
            if p["recipient_iik"] == req.recipient_iik and p["recipient_bin"] != req.recipient_bin
        ]
        if other_payments:
            last_other = other_payments[-1]
            other_name = last_other["recipient_name"]
            other_bin = last_other["recipient_bin"]
            return _make_signal(
                rule_id="iik_belongs_to_other_counterparty",
                points=WEIGHT_IIK_BELONGS_TO_OTHER_COUNTERPARTY,
                severity="primary",
                message_key="rule.iik_belongs_to_other_counterparty",
                evidence=_make_evidence(
                    "iik",
                    lang=lang,
                    expected_key="ev.account_for_bin",
                    expected_params={"bin": req.recipient_bin},
                    actual_key="ev.used_for_other",
                    actual_params={"name": other_name, "bin": other_bin},
                    since=last_other["paid_at"],
                ),
                lang=lang,
                other_name=other_name,
            )

    for trusted_bin, trusted_iik, info in store.get_trusted_entries_for_payer(req.payer_id):
        if trusted_iik == req.recipient_iik and trusted_bin != req.recipient_bin:
            if prof is not None:
                other_sup = prof.get_supplier(trusted_bin)
                other_name = (
                    other_sup.last_name
                    if other_sup is not None
                    else store.registry.get(trusted_bin, f"БИН {trusted_bin}")
                )
            else:
                other_hist = store.get_supplier_history(trusted_bin, req.payer_id)
                other_name = (
                    other_hist[-1]["recipient_name"]
                    if other_hist
                    else store.registry.get(trusted_bin, f"БИН {trusted_bin}")
                )
            return _make_signal(
                rule_id="iik_belongs_to_other_counterparty",
                points=WEIGHT_IIK_BELONGS_TO_OTHER_COUNTERPARTY,
                severity="primary",
                message_key="rule.iik_belongs_to_other_counterparty",
                evidence=_make_evidence(
                    "iik",
                    lang=lang,
                    expected_key="ev.account_for_bin",
                    expected_params={"bin": req.recipient_bin},
                    actual_key="ev.trusted_for_other",
                    actual_params={"name": other_name, "bin": trusted_bin},
                    since=info.decided_at,
                ),
                lang=lang,
                other_name=other_name,
            )

    return None


def rule_iik_changed(
    req: CheckRequest,
    store: Store,
    *,
    lang: Lang = DEFAULT_LANG,
    profiles: ClientProfiles | None = None,
) -> Signal | None:
    """Flag a new, untrusted IIK for a known supplier BIN (skipped if BCC-verified same BIN)."""
    prof = _resolve_profiles(store, req.payer_id, profiles)
    if prof is not None:
        sup = prof.get_supplier(req.recipient_bin)
        if sup is None:
            return None
        if store.is_trusted(req.recipient_bin, req.recipient_iik, payer_id=req.payer_id):
            return None
        if is_bcc_bank_verified_new_account(req, store, profiles=prof):
            return None
        if req.recipient_iik in sup.known_iiks:
            return None
        expected_iik = sup.last_known_iik
        since_date = sup.last_known_paid_at
    else:
        supplier_history = store.get_supplier_history(req.recipient_bin, req.payer_id)
        if not supplier_history:
            return None
        if store.is_trusted(req.recipient_bin, req.recipient_iik, payer_id=req.payer_id):
            return None
        if is_bcc_bank_verified_new_account(req, store):
            return None

        confirmation = confirm_supplier_accounts(supplier_history)
        if req.recipient_iik in confirmation.known_iiks:
            return None

        last_payment = supplier_history[confirmation.last_known_index]
        expected_iik = last_payment["recipient_iik"]
        since_date = last_payment["paid_at"]

    return _make_signal(
        rule_id="iik_changed",
        points=WEIGHT_IIK_CHANGED,
        severity="primary",
        message_key="rule.iik_changed",
        evidence=_make_evidence(
            "iik",
            lang=lang,
            expected=expected_iik,
            actual=req.recipient_iik,
            since=since_date,
        ),
        lang=lang,
    )


def rule_bank_changed(
    req: CheckRequest,
    store: Store,
    *,
    lang: Lang = DEFAULT_LANG,
    profiles: ClientProfiles | None = None,
) -> Signal | None:
    """Flag a known supplier switching to a new untrusted IIK in another bank."""
    prof = _resolve_profiles(store, req.payer_id, profiles)
    if prof is not None:
        sup = prof.get_supplier(req.recipient_bin)
        if sup is None:
            return None
        if store.is_trusted(req.recipient_bin, req.recipient_iik, payer_id=req.payer_id):
            return None
        if is_bcc_bank_verified_new_account(req, store, profiles=prof):
            return None
        if req.recipient_iik in sup.known_iiks:
            return None
        if req.recipient_bik in sup.known_biks:
            return None
        median_amount = sup.amount_median
        old_bank = sup.last_known_bank
        since_date = sup.last_known_paid_at
    else:
        supplier_history = store.get_supplier_history(req.recipient_bin, req.payer_id)
        if not supplier_history:
            return None
        if store.is_trusted(req.recipient_bin, req.recipient_iik, payer_id=req.payer_id):
            return None
        if is_bcc_bank_verified_new_account(req, store):
            return None

        confirmation = confirm_supplier_accounts(supplier_history)
        if req.recipient_iik in confirmation.known_iiks:
            return None

        if req.recipient_bik in confirmation.known_biks:
            return None

        last_payment = supplier_history[confirmation.last_known_index]
        median_amount = statistics.median(float(p["amount_kzt"]) for p in supplier_history)
        old_bank = (
            store.get_bank_name_by_bik(last_payment["recipient_bik"])
            or last_payment["recipient_bik"]
        )
        since_date = last_payment["paid_at"]

    points = (
        WEIGHT_BANK_CHANGED_HIGH_AMOUNT
        if req.amount_kzt >= median_amount
        else WEIGHT_BANK_CHANGED_AMPLIFIER
    )
    new_bank = store.get_bank_name_by_bik(req.recipient_bik) or req.recipient_bik
    return _make_signal(
        rule_id="bank_changed",
        points=points,
        severity="amplifier",
        message_key="rule.bank_changed",
        evidence=_make_evidence(
            "bank",
            lang=lang,
            expected=old_bank,
            actual=new_bank,
            since=since_date,
        ),
        lang=lang,
        old_bank=old_bank,
        new_bank=new_bank,
    )


def rule_kbe_mismatch(req: CheckRequest, *, lang: Lang = DEFAULT_LANG) -> Signal | None:
    """Flag mismatch between optional KBe code (17 legal / 19 individual) and BIN/IIN kind."""
    if not req.kbe:
        return None
    actual_kind = bin_kind(req.recipient_bin)
    if actual_kind is None:
        return None

    if req.kbe in KBE_LEGAL_ENTITY_CODES and actual_kind == "iin":
        return _make_signal(
            rule_id="kbe_mismatch",
            points=WEIGHT_KBE_MISMATCH_LEGAL_IIN,
            severity="primary",
            message_key="rule.kbe_mismatch_legal_iin",
            evidence=_make_evidence(
                "bin",
                lang=lang,
                expected_key="ev.kbe_17_expected",
                actual_key="ev.individual_iin",
            ),
            lang=lang,
        )

    if (
        req.kbe in KBE_INDIVIDUAL_CODES
        and actual_kind == "bin"
        and (len(req.recipient_bin) != 12 or req.recipient_bin[4] != "6")
    ):
        return _make_signal(
            rule_id="kbe_mismatch",
            points=WEIGHT_KBE_MISMATCH_INDIVIDUAL_BIN,
            severity="primary",
            message_key="rule.kbe_mismatch_individual_bin",
            evidence=_make_evidence(
                "bin",
                lang=lang,
                expected_key="ev.kbe_19_expected",
                actual_key="ev.legal_bin",
            ),
            lang=lang,
        )
    return None


def rule_knp_unusual(
    req: CheckRequest,
    store: Store,
    *,
    lang: Lang = DEFAULT_LANG,
    profiles: ClientProfiles | None = None,
) -> Signal | None:
    """Amplifier (+15 pts) when optional KNP differs from supplier's historical KNP values."""
    if not req.knp:
        return None
    prof = _resolve_profiles(store, req.payer_id, profiles)
    if prof is not None:
        sup = prof.get_supplier(req.recipient_bin)
        if sup is None or not sup.known_knps or req.knp in sup.known_knps:
            return None
        known_knps = sorted(sup.known_knps)
        since_date = sup.last_paid_at
    else:
        supplier_history = store.get_supplier_history(req.recipient_bin, req.payer_id)
        known_knps = sorted(
            {str(p.get("knp", "")).strip() for p in supplier_history if p.get("knp")}
        )
        if not known_knps or req.knp in known_knps:
            return None
        since_date = supplier_history[-1]["paid_at"]
    expected_knp = ", ".join(known_knps)
    return _make_signal(
        rule_id="knp_unusual",
        points=WEIGHT_KNP_UNUSUAL,
        severity="amplifier",
        message_key="rule.knp_unusual",
        evidence=_make_evidence(
            "purpose",
            lang=lang,
            expected_key="ev.knp_label",
            expected_params={"knp": expected_knp},
            actual_key="ev.knp_label",
            actual_params={"knp": req.knp},
            since=since_date,
        ),
        lang=lang,
        actual_knp=req.knp,
        expected_knp=expected_knp,
    )


def rule_entity_type_mismatch(req: CheckRequest, *, lang: Lang = DEFAULT_LANG) -> Signal | None:
    """Flag mismatch between legal form in name (ТОО vs ИП) and BIN/IIN 5th digit (H3).

    - Legal entity (ТОО/АО/LLP/ЖШС) with IIN -> primary 40.
    - Individual entrepreneur (ИП) with joint-venture BIN (5th digit 6) -> no mismatch.
    - Individual entrepreneur (ИП) with corporate BIN (5th digit 4/5) -> primary 25.
    """
    expected_kind = detect_legal_form_kind(req.recipient_name)
    actual_kind = bin_kind(req.recipient_bin)
    if expected_kind is None or actual_kind is None or expected_kind == actual_kind:
        return None

    if expected_kind == "bin":
        return _make_signal(
            rule_id="entity_type_mismatch",
            points=WEIGHT_ENTITY_TYPE_MISMATCH_LEGAL_IIN,
            severity="primary",
            message_key="rule.entity_type_mismatch_legal_iin",
            evidence=_make_evidence(
                "bin",
                lang=lang,
                expected_key="ev.legal_bin",
                actual_key="ev.individual_iin",
            ),
            lang=lang,
        )

    # In Kazakhstan, joint-venture IE (ИП(С)) legitimately uses a BIN with 5th digit '6'.
    if len(req.recipient_bin) == 12 and req.recipient_bin[4] == "6":
        return None

    return _make_signal(
        rule_id="entity_type_mismatch",
        points=WEIGHT_ENTITY_TYPE_MISMATCH,
        severity="primary",
        message_key="rule.entity_type_mismatch_ie_bin",
        evidence=_make_evidence(
            "bin",
            lang=lang,
            expected_key="ev.individual_iin",
            actual_key="ev.legal_bin",
        ),
        lang=lang,
    )


def rule_new_bcc_account(
    req: CheckRequest,
    store: Store,
    *,
    today: date = DEMO_TODAY,
    lang: Lang = DEFAULT_LANG,
) -> Signal | None:
    """Flag a BCC account opened less than 30 days before today without disclosing opening date."""
    account = store.bcc_accounts.get(req.recipient_iik)
    if account is None:
        return None

    opened_at = date.fromisoformat(account["opened_at"])
    age_days = max(0, (today - opened_at).days)
    if age_days >= NEW_BCC_ACCOUNT_MAX_DAYS:
        return None

    return _make_signal(
        rule_id="new_bcc_account",
        points=WEIGHT_NEW_BCC_ACCOUNT,
        severity="primary",
        message_key="rule.new_bcc_account",
        evidence=_make_evidence(
            "iik",
            lang=lang,
            expected_key="ev.new_bcc_expected",
            actual_key="ev.new_bcc_actual",
            since=None,
        ),
        lang=lang,
    )


def build_analyst_details(
    req: CheckRequest,
    store: Store,
    signals: list[Signal],
    *,
    today: date = DEMO_TODAY,
    lang: Lang = DEFAULT_LANG,
    bank_signals: dict[str, Any] | None = None,
) -> AnalystDetails:
    """Build restricted antifraud analyst details (banking secrecy, bank-wide counts, offsets)."""
    bcc_info: BccAccountAnalystInfo | None = None
    account = store.bcc_accounts.get(req.recipient_iik)
    if account is not None:
        owner_bin = account["owner_bin"]
        owner_name = account.get("owner_name") or store.registry.get(owner_bin) or owner_bin
        opened_at_str = account["opened_at"]
        age_days = max(0, (today - date.fromisoformat(opened_at_str)).days)
        bcc_info = BccAccountAnalystInfo(
            iik=req.recipient_iik,
            owner_bin=owner_bin,
            owner_name=owner_name,
            opened_at=opened_at_str,
            age_days=age_days,
            owner_matches_recipient=(owner_bin == req.recipient_bin),
        )

    bankwide_rule_ids = {"iik_reported_by_clients", "iik_on_watchlist", "fresh_iik_many_payers"}
    signals_data = (
        get_bank_signals(store, bank_signals=bank_signals)
        if any(s.rule_id in bankwide_rule_ids for s in signals)
        else None
    )

    details: list[AnalystSignalDetail] = []
    for sig in signals:
        if sig.rule_id == "bcc_account_other_owner" and bcc_info is not None:
            params = {
                "owner_name": bcc_info.owner_name,
                "owner_bin": bcc_info.owner_bin,
            }
            details.append(
                AnalystSignalDetail(
                    rule_id="bcc_account_other_owner",
                    reason_ru=t("analyst.bcc_account_other_owner", "ru", **params),
                    reason=t("analyst.bcc_account_other_owner", lang, **params),
                    message_key="analyst.bcc_account_other_owner",
                    message_params=params,
                    evidence=_make_evidence(
                        "iik",
                        lang=lang,
                        expected_key="ev.analyst_bcc_expected",
                        expected_params={"bin": req.recipient_bin},
                        actual_key="ev.analyst_bcc_actual",
                        actual_params={
                            "owner_name": bcc_info.owner_name,
                            "owner_bin": bcc_info.owner_bin,
                        },
                        since=bcc_info.opened_at,
                    ),
                )
            )
        elif sig.rule_id == "new_bcc_account" and bcc_info is not None:
            params = {
                "age_days": bcc_info.age_days,
                "opened_at": bcc_info.opened_at,
            }
            details.append(
                AnalystSignalDetail(
                    rule_id="new_bcc_account",
                    reason_ru=t("analyst.new_bcc_account", "ru", **params),
                    reason=t("analyst.new_bcc_account", lang, **params),
                    message_key="analyst.new_bcc_account",
                    message_params=params,
                    evidence=_make_evidence(
                        "iik",
                        lang=lang,
                        expected_key="ev.analyst_new_bcc_expected",
                        expected_params={"days": NEW_BCC_ACCOUNT_MAX_DAYS},
                        actual_key="ev.analyst_new_bcc_actual",
                        actual_params={
                            "age_days": bcc_info.age_days,
                            "opened_at": bcc_info.opened_at,
                        },
                        since=bcc_info.opened_at,
                    ),
                )
            )
        elif sig.rule_id == "mixed_script_name":
            positions = find_mixed_script_positions(req.recipient_name)
            pos_label = ", ".join(str(p) for p in positions)
            chars_label = ", ".join(f"{p}:{req.recipient_name[p]}" for p in positions)
            params = {"positions": pos_label}
            details.append(
                AnalystSignalDetail(
                    rule_id="mixed_script_name",
                    reason_ru=t("analyst.mixed_script_name", "ru", **params),
                    reason=t("analyst.mixed_script_name", lang, **params),
                    message_key="analyst.mixed_script_name",
                    message_params=params,
                    evidence=_make_evidence(
                        "name",
                        lang=lang,
                        expected_key="ev.single_script_expected",
                        actual=chars_label,
                        positions=positions,
                    ),
                )
            )
        elif sig.rule_id == "iik_reported_by_clients" and signals_data is not None:
            comp = signals_data["complaints"].get(req.recipient_iik)
            if isinstance(comp, dict):
                count = int(comp.get("count", 0))
                last_reported_at = str(comp.get("last_reported_at") or "-")
                params = {"count": count, "last_reported_at": last_reported_at}
                details.append(
                    AnalystSignalDetail(
                        rule_id="iik_reported_by_clients",
                        reason_ru=t("analyst.iik_reported_by_clients", "ru", **params),
                        reason=t("analyst.iik_reported_by_clients", lang, **params),
                        message_key="analyst.iik_reported_by_clients",
                        message_params=params,
                        evidence=_make_evidence(
                            "iik",
                            lang=lang,
                            expected_key="ev.bank_complaints_expected",
                            actual_key="ev.analyst_complaints_actual",
                            actual_params=params,
                            since=last_reported_at if last_reported_at != "-" else None,
                        ),
                    )
                )
        elif sig.rule_id == "iik_on_watchlist" and signals_data is not None:
            watch = signals_data["mule_watchlist"].get(req.recipient_iik)
            if watch is not None and watch is not False:
                entry = watch if isinstance(watch, dict) else {}
                source = str(entry.get("source") or "Антифрод-центр НБ РК")
                category = str(entry.get("category") or "dropper_account")
                added_at = str(entry.get("added_at") or "-")
                params = {"source": source, "category": category, "added_at": added_at}
                details.append(
                    AnalystSignalDetail(
                        rule_id="iik_on_watchlist",
                        reason_ru=t("analyst.iik_on_watchlist", "ru", **params),
                        reason=t("analyst.iik_on_watchlist", lang, **params),
                        message_key="analyst.iik_on_watchlist",
                        message_params=params,
                        evidence=_make_evidence(
                            "iik",
                            lang=lang,
                            expected_key="ev.watchlist_expected",
                            actual_key="ev.analyst_watchlist_actual",
                            actual_params=params,
                            since=added_at if added_at != "-" else None,
                        ),
                    )
                )
        elif sig.rule_id == "fresh_iik_many_payers" and signals_data is not None:
            inflow = signals_data["fresh_inflows"].get(req.recipient_iik)
            if isinstance(inflow, dict):
                distinct_payers = int(inflow.get("distinct_payers_7d", 0))
                total_amount = float(inflow.get("total_amount_kzt_7d", 0))
                window_days = int(inflow.get("window_days", BANK_FRESH_INFLOWS_WINDOW_DAYS))
                total_kzt = _format_kzt(total_amount)
                params = {
                    "distinct_payers": distinct_payers,
                    "window_days": window_days,
                    "total_kzt": total_kzt,
                }
                details.append(
                    AnalystSignalDetail(
                        rule_id="fresh_iik_many_payers",
                        reason_ru=t("analyst.fresh_iik_many_payers", "ru", **params),
                        reason=t("analyst.fresh_iik_many_payers", lang, **params),
                        message_key="analyst.fresh_iik_many_payers",
                        message_params=params,
                        evidence=_make_evidence(
                            "iik",
                            lang=lang,
                            expected_key="ev.analyst_fresh_inflows_expected",
                            expected_params={
                                "threshold": BANK_FRESH_INFLOWS_MEDIUM_PAYERS,
                                "window_days": window_days,
                            },
                            actual_key="ev.analyst_fresh_inflows_actual",
                            actual_params=params,
                        ),
                    )
                )

    return AnalystDetails(bcc_account=bcc_info, signal_details=details)


def rule_amount_anomaly(
    req: CheckRequest,
    store: Store,
    *,
    reference_bin: str | None = None,
    lang: Lang = DEFAULT_LANG,
    profiles: ClientProfiles | None = None,
) -> Signal | None:
    """Evaluate payment amount against supplier median + MAD, or client p90 on first payment (H2).

    - Known supplier (>=5 payments):
      * ratio >= 3.0 or robust z >= 10 -> primary, 35 pts
      * moderate outlier (ratio >= 1.5 and robust z >= 3.5) -> amplifier, 10..20 pts
    - First payment (no supplier history):
      * amount > client p90 -> amplifier, 10..20 pts
    """
    target_bin = reference_bin or req.recipient_bin
    prof = _resolve_profiles(store, req.payer_id, profiles)
    if prof is not None:
        sup = prof.get_supplier(target_bin)
        has_history = sup is not None
        payments_count = sup.payments_count if sup is not None else 0
    else:
        sup = None
        supplier_history = store.get_supplier_history(target_bin, req.payer_id)
        has_history = len(supplier_history) > 0
        payments_count = len(supplier_history)

    if not has_history:
        client_p90 = (
            prof.client_p90 if prof is not None else compute_client_p90(store, req.payer_id)
        )
        if client_p90 is None or client_p90 <= 0 or req.amount_kzt <= client_p90:
            return None
        ratio_p90 = req.amount_kzt / client_p90
        first_severity: Severity
        if ratio_p90 > AMOUNT_FIRST_PAYMENT_RED_P90_MULT:
            first_severity = "primary"
            points = WEIGHT_AMOUNT_ANOMALY_EXTREME
        elif ratio_p90 > AMOUNT_FIRST_PAYMENT_YELLOW_P90_MULT:
            first_severity = "primary"
            points = WEIGHT_AMOUNT_ANOMALY_PRIMARY
        elif ratio_p90 >= 2.0:
            first_severity = "amplifier"
            points = 20
        elif ratio_p90 >= 1.5:
            first_severity = "amplifier"
            points = 15
        else:
            first_severity = "amplifier"
            points = 10
        client_p90_kzt = _format_kzt(client_p90)
        return _make_signal(
            rule_id="amount_anomaly",
            points=points,
            severity=first_severity,
            message_key="rule.amount_anomaly_first_p90",
            evidence=_make_evidence(
                "amount",
                lang=lang,
                expected_key="ev.amount_p90_expected",
                expected_params={"amount": client_p90_kzt},
                actual=_format_kzt(req.amount_kzt),
            ),
            lang=lang,
            client_p90_kzt=client_p90_kzt,
        )

    if payments_count < AMOUNT_ANOMALY_MIN_HISTORY:
        return None

    if sup is not None:
        median_amount = sup.amount_median
        supplier_p90 = sup.amount_p90
        mad = sup.amount_mad
        first_paid_at = sup.first_paid_at
    else:
        amounts = [float(p["amount_kzt"]) for p in supplier_history]
        median_amount = statistics.median(amounts)
        supplier_p90 = _compute_percentile(sorted(amounts), 0.9)
        mad = statistics.median([abs(x - median_amount) for x in amounts])
        first_paid_at = supplier_history[0]["paid_at"]

    if median_amount <= 0:
        return None

    ratio = req.amount_kzt / median_amount
    if supplier_p90 > 0 and req.amount_kzt >= AMOUNT_SUPPLIER_EXTREME_P90_MULT * supplier_p90:
        median_kzt = _format_kzt(median_amount)
        return _make_signal(
            rule_id="amount_anomaly",
            points=WEIGHT_AMOUNT_ANOMALY_EXTREME,
            severity="primary",
            message_key="rule.amount_anomaly_supplier",
            evidence=_make_evidence(
                "amount",
                lang=lang,
                expected_key="ev.amount_around",
                expected_params={"amount": median_kzt},
                actual=_format_kzt(req.amount_kzt),
                since=first_paid_at,
            ),
            lang=lang,
            ratio=f"{ratio:.1f}",
            median_kzt=median_kzt,
        )

    if ratio < 1.5:
        return None

    severity: Severity
    if mad > 0:
        mod_z = 0.6745 * (req.amount_kzt - median_amount) / mad
        if mod_z < 3.5:
            return None
        if ratio >= 3.0 or mod_z >= 10.0:
            severity = "primary"
            points = WEIGHT_AMOUNT_ANOMALY_PRIMARY
        elif ratio >= 2.5 or mod_z >= 7.0:
            severity = "amplifier"
            points = 20
        elif ratio >= 2.0 or mod_z >= 5.0:
            severity = "amplifier"
            points = 15
        else:
            severity = "amplifier"
            points = 10
    else:
        if ratio >= 3.0:
            severity = "primary"
            points = WEIGHT_AMOUNT_ANOMALY_PRIMARY
        elif ratio >= 2.5:
            severity = "amplifier"
            points = 20
        elif ratio >= 2.0:
            severity = "amplifier"
            points = 15
        else:
            severity = "amplifier"
            points = 10

    median_kzt = _format_kzt(median_amount)
    return _make_signal(
        rule_id="amount_anomaly",
        points=points,
        severity=severity,
        message_key="rule.amount_anomaly_supplier",
        evidence=_make_evidence(
            "amount",
            lang=lang,
            expected_key="ev.amount_around",
            expected_params={"amount": median_kzt},
            actual=_format_kzt(req.amount_kzt),
            since=first_paid_at,
        ),
        lang=lang,
        ratio=f"{ratio:.1f}",
        median_kzt=median_kzt,
    )


def rule_first_payment(
    req: CheckRequest,
    store: Store,
    *,
    lang: Lang = DEFAULT_LANG,
    profiles: ClientProfiles | None = None,
) -> Signal | None:
    """Info signal when the client has no payment history with this recipient BIN."""
    prof = _resolve_profiles(store, req.payer_id, profiles)
    if prof is not None:
        if prof.get_supplier(req.recipient_bin) is not None:
            return None
    elif store.get_supplier_history(req.recipient_bin, req.payer_id):
        return None
    return _make_signal(
        rule_id="first_payment",
        points=0,
        severity="info",
        message_key="rule.first_payment",
        evidence=_make_evidence(
            "bin",
            lang=lang,
            expected_key="ev.first_payment_expected",
            actual_key="ev.first_payment_actual",
        ),
        lang=lang,
    )


_DOTTED_LETTERS_RE = re.compile(
    r"(?<!\w)(?:[^\W\d_]\s*[\.\-_]+\s*){2,}[^\W\d_](?!\w)",
    flags=re.UNICODE,
)
_SPACED_LETTERS_RE = re.compile(
    r"(?<!\w)(?:[^\W\d_]\s+){3,}[^\W\d_](?!\w)",
    flags=re.UNICODE,
)


def _collapse_obfuscated_letters(text: str) -> str:
    """Join single letters separated by dots/hyphens ('с.р.о.ч.н.о') or spaces ('с р о ч н о')."""
    step1 = _DOTTED_LETTERS_RE.sub(lambda m: re.sub(r"[\s.\-_]+", "", m.group(0)), text)
    return _SPACED_LETTERS_RE.sub(lambda m: re.sub(r"\s+", "", m.group(0)), step1)


def _fold_urgent_text(text: str) -> str:
    """Normalize purpose text for Cyrillic urgent wording checks using TR39 confusable skeleton."""
    return confusable_skeleton(text).lower()


def _build_phrase_pattern(folded_phrase: str) -> re.Pattern[str]:
    return re.compile(
        r"(?<!\w)" + r"\s+".join(re.escape(part) for part in folded_phrase.split()) + r"(?!\w)",
        flags=re.UNICODE,
    )


_CYR_URGENT_PHRASES: tuple[str, ...] = tuple(p for p in URGENT_PHRASES if not p.isascii())

_URGENT_CYR_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (
        stem,
        re.compile(
            r"(?<!\w)" + re.escape(_fold_urgent_text(stem)) + r"\w*(?!\w)", flags=re.UNICODE
        ),
    )
    for stem in URGENT_CYRILLIC_STEMS
) + tuple(
    (phrase, _build_phrase_pattern(_fold_urgent_text(phrase))) for phrase in _CYR_URGENT_PHRASES
)

_URGENT_LAT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (
        stem,
        re.compile(r"(?<!\w)" + re.escape(stem.lower()) + r"[a-z]*(?!\w)", flags=re.UNICODE),
    )
    for stem in URGENT_LATIN_STEMS
) + tuple((phrase, _build_phrase_pattern(phrase.lower())) for phrase in URGENT_LATIN_PHRASES)


def rule_bin_young(
    req: CheckRequest,
    *,
    today: date = DEMO_TODAY,
    lang: Lang = DEFAULT_LANG,
) -> Signal | None:
    """Amplifier (+15 pts) when recipient BIN was registered less than 12 months before today (L1)."""
    yymm = bin_registration_yymm(req.recipient_bin)
    if yymm is None:
        return None

    yy, mm = yymm
    current_yy = today.year % 100
    reg_year = 2000 + yy if yy <= current_yy + 5 else 1900 + yy
    months_diff = max(0, (today.year - reg_year) * 12 + (today.month - mm))
    if months_diff >= BIN_YOUNG_MAX_MONTHS:
        return None

    reg_date = f"{mm:02d}.{reg_year}"
    return _make_signal(
        rule_id="bin_young",
        points=WEIGHT_BIN_YOUNG,
        severity="amplifier",
        message_key="rule.bin_young",
        evidence=_make_evidence(
            "bin",
            lang=lang,
            expected_key="ev.bin_young_expected",
            expected_params={"months": BIN_YOUNG_MAX_MONTHS},
            actual_key="ev.bin_young_actual",
            actual_params={"reg_date": reg_date, "months": months_diff},
            since=f"{reg_year:04d}-{mm:02d}",
        ),
        lang=lang,
        reg_date=reg_date,
    )


def rule_urgent_wording(req: CheckRequest, *, lang: Lang = DEFAULT_LANG) -> Signal | None:
    """Amplifier (+10 pts) when purpose contains urgency or requisite-change wording (L2)."""
    raw = sanitize_unicode(req.purpose or "")
    if not raw:
        return None

    collapsed = _collapse_obfuscated_letters(raw)
    cyr_views = (_fold_urgent_text(raw), _fold_urgent_text(collapsed))
    lat_views = (raw.lower(), collapsed.lower())

    matched: list[str] = []
    for label, pattern in _URGENT_CYR_PATTERNS:
        if any(pattern.search(v) for v in cyr_views) and label not in matched:
            matched.append(label)
    for label, pattern in _URGENT_LAT_PATTERNS:
        if any(pattern.search(v) for v in lat_views) and label not in matched:
            matched.append(label)

    if not matched:
        return None

    return _make_signal(
        rule_id="urgent_wording",
        points=WEIGHT_URGENT_WORDING,
        severity="amplifier",
        message_key="rule.urgent_wording",
        evidence=_make_evidence(
            "purpose",
            lang=lang,
            expected_key="ev.urgent_expected",
            actual=", ".join(matched),
        ),
        lang=lang,
    )


def rule_trusted_account(
    req: CheckRequest,
    store: Store,
    *,
    lang: Lang = DEFAULT_LANG,
) -> Signal | None:
    """Info signal indicating the account was explicitly confirmed by the director."""
    info = store.get_trusted_info(req.payer_id, req.recipient_bin, req.recipient_iik)
    if info is None:
        return None

    date_part = info.decided_at[:10]
    try:
        date_label = date.fromisoformat(date_part).strftime("%d.%m.%Y")
    except ValueError:
        date_label = date_part

    return _make_signal(
        rule_id="trusted_account",
        points=0,
        severity="info",
        message_key="rule.trusted_account",
        evidence=_make_evidence(
            "iik",
            lang=lang,
            expected=req.recipient_iik,
            actual=info.director_comment or None,
            actual_key=None if info.director_comment else "ev.trusted_default",
            since=info.decided_at,
        ),
        lang=lang,
        date_label=date_label,
    )


def rule_bcc_owner_verified(
    req: CheckRequest,
    store: Store,
    *,
    lang: Lang = DEFAULT_LANG,
    profiles: ClientProfiles | None = None,
) -> Signal | None:
    """Info signal when a known supplier's new BCC IIK is confirmed to belong to the same BIN."""
    if not is_bcc_bank_verified_new_account(req, store, profiles=profiles):
        return None
    return _make_signal(
        rule_id="bcc_owner_verified",
        points=0,
        severity="info",
        message_key="rule.bcc_owner_verified",
        evidence=_make_evidence(
            "iik",
            lang=lang,
            expected_key="ev.bcc_owner_expected",
            actual_key="ev.bcc_owner_verified",
            since=None,
        ),
        lang=lang,
    )


def rule_duplicate_invoice(
    req: CheckRequest,
    store: Store,
    *,
    today: date = DEMO_TODAY,
    lang: Lang = DEFAULT_LANG,
    include_recent_memory: bool = True,
    profiles: ClientProfiles | None = None,
) -> Signal | None:
    """Flag duplicate invoice number to the same recipient within 90 days (history + memory)."""
    invoice_no = extract_invoice_number(req.purpose)
    if not invoice_no:
        return None

    prof = _resolve_profiles(store, req.payer_id, profiles)
    matched_dates: list[str] = []
    if prof is None or prof.get_supplier(req.recipient_bin) is not None:
        for p in store.get_supplier_history(req.recipient_bin, req.payer_id):
            paid_at_str = str(p.get("paid_at", ""))
            try:
                paid_dt = date.fromisoformat(paid_at_str[:10])
            except ValueError:
                continue
            days_ago = max(0, (today - paid_dt).days)
            if days_ago > DUPLICATE_INVOICE_WINDOW_DAYS:
                continue
            if extract_invoice_number(p.get("purpose", "")) == invoice_no:
                matched_dates.append(paid_at_str[:10])

    if include_recent_memory:
        req_hash = compute_request_sha256(
            req, resolved_payer_id=store.resolve_payer_id(req.payer_id)
        )
        for entry in store.get_recent_checks(
            req.recipient_bin,
            req.payer_id,
            within_days=DUPLICATE_INVOICE_WINDOW_DAYS,
            today=today,
            exclude_request_sha256=req_hash,
        ):
            entry_inv = entry.get("invoice_no") or extract_invoice_number(entry.get("purpose", ""))
            if entry_inv == invoice_no:
                matched_dates.append(str(entry["checked_at"])[:10])

    if not matched_dates:
        return None

    prev_date = max(matched_dates)
    return _make_signal(
        rule_id="duplicate_invoice",
        points=WEIGHT_DUPLICATE_INVOICE,
        severity="primary",
        message_key="rule.duplicate_invoice",
        evidence=_make_evidence(
            "purpose",
            lang=lang,
            expected_key="ev.duplicate_invoice_expected",
            actual_key="ev.duplicate_invoice_actual",
            actual_params={"invoice_no": invoice_no},
            since=prev_date,
        ),
        lang=lang,
        invoice_no=invoice_no,
        prev_date=prev_date,
    )


def rule_new_recipient_accumulated(
    req: CheckRequest,
    store: Store,
    *,
    today: date = DEMO_TODAY,
    lang: Lang = DEFAULT_LANG,
    include_recent_memory: bool = True,
    profiles: ClientProfiles | None = None,
) -> Signal | None:
    """Flag cumulative amount to a new recipient across multiple checks within 7 days."""
    if not include_recent_memory:
        return None
    prof = _resolve_profiles(store, req.payer_id, profiles)
    if prof is not None:
        if prof.get_supplier(req.recipient_bin) is not None:
            return None
    elif store.get_supplier_history(req.recipient_bin, req.payer_id):
        return None

    req_hash = compute_request_sha256(req, resolved_payer_id=store.resolve_payer_id(req.payer_id))
    recent = store.get_recent_checks(
        req.recipient_bin,
        req.payer_id,
        within_days=NEW_RECIPIENT_ACCUM_WINDOW_DAYS,
        today=today,
        exclude_request_sha256=req_hash,
    )
    if not recent:
        return None

    count = len(recent) + 1
    accum_total = sum(float(c["amount_kzt"]) for c in recent) + req.amount_kzt
    client_p90 = prof.client_p90 if prof is not None else compute_client_p90(store, req.payer_id)
    client_median = (
        prof.client_median if prof is not None else compute_client_median(store, req.payer_id)
    )

    severity: Severity
    if client_p90 and accum_total > AMOUNT_FIRST_PAYMENT_RED_P90_MULT * client_p90:
        severity = "primary"
        points = WEIGHT_AMOUNT_ANOMALY_EXTREME
    elif client_p90 and accum_total > AMOUNT_FIRST_PAYMENT_YELLOW_P90_MULT * client_p90:
        severity = "primary"
        points = WEIGHT_AMOUNT_ANOMALY_PRIMARY
    elif client_p90 and accum_total > client_p90:
        severity = "amplifier"
        points = WEIGHT_NEW_RECIPIENT_ACCUM_MAX
    elif (client_median and accum_total >= client_median) or count >= 3:
        severity = "amplifier"
        points = WEIGHT_NEW_RECIPIENT_ACCUM_MIN
    else:
        return None

    total_kzt = _format_kzt(accum_total)
    return _make_signal(
        rule_id="new_recipient_accumulated",
        points=points,
        severity=severity,
        message_key="rule.new_recipient_accumulated",
        evidence=_make_evidence(
            "amount",
            lang=lang,
            expected=_format_kzt(client_p90) if client_p90 else None,
            expected_key=None if client_p90 else "ev.accum_expected_fallback",
            actual_key="ev.accum_actual",
            actual_params={
                "total": total_kzt,
                "days": NEW_RECIPIENT_ACCUM_WINDOW_DAYS,
                "count": count,
            },
            since=str(recent[0]["checked_at"])[:10],
        ),
        lang=lang,
        total_kzt=total_kzt,
        count=count,
    )


def rule_structuring_72h(
    req: CheckRequest,
    store: Store,
    *,
    today: date = DEMO_TODAY,
    lang: Lang = DEFAULT_LANG,
    include_recent_memory: bool = True,
    profiles: ClientProfiles | None = None,
) -> Signal | None:
    """Detect payment splitting over 72 hours (history + in-memory checks) against median."""
    prof = _resolve_profiles(store, req.payer_id, profiles)
    sup = prof.get_supplier(req.recipient_bin) if prof is not None else None
    supplier_history = (
        store.get_supplier_history(req.recipient_bin, req.payer_id)
        if (prof is None or sup is not None)
        else []
    )
    window_days = max(1, STRUCTURING_WINDOW_HOURS // 24)

    hist_72h = []
    for p in supplier_history:
        try:
            paid_dt = date.fromisoformat(str(p.get("paid_at", ""))[:10])
        except ValueError:
            continue
        days_ago = (today - paid_dt).days
        if 0 <= days_ago <= window_days:
            hist_72h.append(p)

    req_hash = compute_request_sha256(req, resolved_payer_id=store.resolve_payer_id(req.payer_id))
    checks_72h = (
        store.get_recent_checks(
            req.recipient_bin,
            req.payer_id,
            within_hours=float(STRUCTURING_WINDOW_HOURS),
            today=today,
            exclude_request_sha256=req_hash,
        )
        if include_recent_memory
        else []
    )
    count = len(hist_72h) + len(checks_72h) + 1
    if count < 2:
        return None

    total_72h = (
        sum(float(p["amount_kzt"]) for p in hist_72h)
        + sum(float(c["amount_kzt"]) for c in checks_72h)
        + req.amount_kzt
    )

    severity: Severity
    has_supplier_history = (sup is not None) if prof is not None else bool(supplier_history)
    if has_supplier_history:
        if sup is not None:
            if sup.positive_amount_median is None or sup.positive_amount_median <= 0:
                return None
            median_amount = sup.positive_amount_median
            supplier_p90 = sup.positive_amount_p90 or 0.0
        else:
            amounts = [
                float(p["amount_kzt"]) for p in supplier_history if float(p["amount_kzt"]) > 0
            ]
            if not amounts:
                return None
            median_amount = float(statistics.median(amounts))
            if median_amount <= 0:
                return None
            supplier_p90 = _compute_percentile(sorted(amounts), 0.9)
        ratio = total_72h / median_amount

        if supplier_p90 > 0 and total_72h >= AMOUNT_SUPPLIER_EXTREME_P90_MULT * supplier_p90:
            severity = "primary"
            points = WEIGHT_AMOUNT_ANOMALY_EXTREME
        elif ratio >= STRUCTURING_PRIMARY_RATIO or (
            count >= STRUCTURING_SPLIT_MIN_COUNT and ratio >= 2.0
        ):
            severity = "primary"
            points = WEIGHT_STRUCTURING_PRIMARY
        elif ratio >= STRUCTURING_PAIR_MIN_RATIO or (
            count >= STRUCTURING_SPLIT_MIN_COUNT and ratio >= STRUCTURING_SPLIT_MIN_RATIO
        ):
            severity = "amplifier"
            points = WEIGHT_STRUCTURING_AMPLIFIER
        else:
            return None
        ref_amount_kzt = _format_kzt(median_amount)
    else:
        client_median = (
            prof.client_median if prof is not None else compute_client_median(store, req.payer_id)
        )
        client_p90 = (
            prof.client_p90 if prof is not None else compute_client_p90(store, req.payer_id)
        )
        if not client_median or client_median <= 0:
            return None
        ratio = total_72h / client_median
        if client_p90 and total_72h > AMOUNT_FIRST_PAYMENT_RED_P90_MULT * client_p90:
            severity = "primary"
            points = WEIGHT_AMOUNT_ANOMALY_EXTREME
        elif client_p90 and total_72h > AMOUNT_FIRST_PAYMENT_YELLOW_P90_MULT * client_p90:
            severity = "primary"
            points = WEIGHT_STRUCTURING_PRIMARY
        elif count >= STRUCTURING_SPLIT_MIN_COUNT and ratio >= STRUCTURING_SPLIT_MIN_RATIO:
            severity = "amplifier"
            points = WEIGHT_STRUCTURING_AMPLIFIER
        else:
            return None
        ref_amount_kzt = _format_kzt(client_median)

    total_kzt = _format_kzt(total_72h)
    return _make_signal(
        rule_id="structuring_72h",
        points=points,
        severity=severity,
        message_key="rule.structuring_72h",
        evidence=_make_evidence(
            "amount",
            lang=lang,
            expected_key="ev.amount_around",
            expected_params={"amount": ref_amount_kzt},
            actual_key="ev.structuring_actual",
            actual_params={
                "total": total_kzt,
                "hours": STRUCTURING_WINDOW_HOURS,
                "count": count,
            },
        ),
        lang=lang,
        count=count,
        total_kzt=total_kzt,
        ratio=f"{ratio:.1f}",
    )
