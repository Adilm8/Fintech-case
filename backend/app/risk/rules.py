"""Pure risk evaluation rules for BCC Business Shield.

Each rule is a pure function returning Signal | None using i18n message keys + parameters
and structured evidence.
"""

from __future__ import annotations

import math
import re
import statistics
import unicodedata
from datetime import date
from typing import Any

from app.i18n import DEFAULT_LANG, Lang, t
from app.risk.config import (
    AMOUNT_ANOMALY_MIN_HISTORY,
    BCC_BANK_CODE,
    BCC_BIK,
    BIN_YOUNG_MAX_MONTHS,
    CLIENT_P90_MIN_HISTORY,
    DEMO_TODAY,
    LOOKALIKE_SIMILARITY_THRESHOLD,
    LOOKALIKE_TOKEN_SET_MIN_LEN,
    LOOKALIKE_TOKEN_SET_THRESHOLD,
    NEW_BCC_ACCOUNT_MAX_DAYS,
    URGENT_PHRASES,
    WEIGHT_AMOUNT_ANOMALY_PRIMARY,
    WEIGHT_BANK_CHANGED_AMPLIFIER,
    WEIGHT_BIN_NAME_MISMATCH,
    WEIGHT_BIN_YOUNG,
    WEIGHT_ENTITY_TYPE_MISMATCH,
    WEIGHT_ENTITY_TYPE_MISMATCH_LEGAL_IIN,
    WEIGHT_IIK_BELONGS_TO_OTHER_COUNTERPARTY,
    WEIGHT_IIK_CHANGED,
    WEIGHT_LOOKALIKE_SUPPLIER,
    WEIGHT_MIXED_SCRIPT_NAME,
    WEIGHT_NEW_BCC_ACCOUNT,
    WEIGHT_URGENT_WORDING,
)
from app.risk.names import (
    detect_legal_form_kind,
    find_mixed_script_positions,
    map_homoglyphs,
    name_similarity,
    normalize_company_name,
    token_set_similarity,
)
from app.schemas import CheckRequest, Evidence, Severity, Signal
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


def compute_client_p90(store: Store, payer_id: str | None = None) -> float | None:
    """Compute the 90th percentile of all historical payment amounts for the client."""
    history = store.get_client_history(payer_id)
    if len(history) < CLIENT_P90_MIN_HISTORY:
        return None
    amounts = sorted(float(p["amount_kzt"]) for p in history if float(p["amount_kzt"]) > 0)
    if len(amounts) < CLIENT_P90_MIN_HISTORY:
        return None
    pos = 0.9 * (len(amounts) - 1)
    lo = math.floor(pos)
    hi = math.ceil(pos)
    return amounts[lo] + (amounts[hi] - amounts[lo]) * (pos - lo)


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
        evidence=Evidence(
            field="bin",
            expected="12 цифр с верной контрольной суммой",
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
        evidence=Evidence(
            field="iik",
            expected="20 символов формата KZ...",
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
        evidence=Evidence(
            field="bik",
            expected="8-символьный БИК банка РК",
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
    expected_str = (
        f"код {expected_bank['code']} ({expected_bank['bik']})"
        if expected_bank is not None
        else req.recipient_bik
    )
    actual_str = f"код {code} ({actual_bank['bik']})" if actual_bank is not None else f"код {code}"
    return _make_signal(
        rule_id="iik_bank_code_vs_bik",
        points=0,
        severity="block",
        message_key="rule.iik_bank_code_vs_bik",
        evidence=Evidence(
            field="bik",
            expected=expected_str,
            actual=actual_str,
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
    """Block payment when a BCC IIK belongs to a different BIN in BCC's account registry."""
    is_bcc = iik_bank_code(req.recipient_iik) == BCC_BANK_CODE or req.recipient_bik == BCC_BIK
    if not is_bcc:
        return None

    account = store.bcc_accounts.get(req.recipient_iik)
    if account is None:
        return None

    owner_bin = account["owner_bin"]
    if owner_bin == req.recipient_bin:
        return None

    owner_name = account.get("owner_name") or store.registry.get(owner_bin) or owner_bin
    return _make_signal(
        rule_id="bcc_account_other_owner",
        points=100,
        severity="block",
        message_key="rule.bcc_account_other_owner",
        evidence=Evidence(
            field="iik",
            expected=f"счёт на БИН {req.recipient_bin}",
            actual=f"владелец {owner_name} (БИН {owner_bin})",
            since=account.get("opened_at"),
        ),
        lang=lang,
        owner_name=owner_name,
    )


def find_lookalike_supplier(req: CheckRequest, store: Store) -> dict[str, str] | None:
    """Find the closest known client supplier with lookalike similarity and a different BIN.

    Skipped (M1) if recipient_bin already has its own payment history or is trusted.
    Triggers on:
    - exact match after normalization/homoglyph folding regardless of length,
    - similarity >= 85, or
    - H4: all normalized tokens of a known supplier (len >= 8) contained in the new name
      with token_set_ratio >= 95.
    """
    if store.get_supplier_history(req.recipient_bin, req.payer_id):
        return None
    if store.is_bin_trusted(req.recipient_bin, payer_id=req.payer_id):
        return None

    norm_req = normalize_company_name(req.recipient_name)
    if not norm_req:
        return None
    req_tokens = set(norm_req.split())

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

    best_match: dict[str, str] | None = None
    best_score = 0.0
    for supplier in suppliers_by_bin.values():
        norm_sup = normalize_company_name(supplier["name"])
        if not norm_sup:
            continue

        matched_score = 0.0
        if norm_req == norm_sup:
            # Exact match after folding regardless of length.
            matched_score = 100.0
        else:
            sim = name_similarity(req.recipient_name, supplier["name"])
            if sim >= LOOKALIKE_SIMILARITY_THRESHOLD:
                matched_score = sim
            else:
                # H4: all tokens of known supplier contained in the new name.
                sup_tokens = set(norm_sup.split())
                if len(norm_sup) >= LOOKALIKE_TOKEN_SET_MIN_LEN and sup_tokens.issubset(req_tokens):
                    ts_score = token_set_similarity(req.recipient_name, supplier["name"])
                    if ts_score >= LOOKALIKE_TOKEN_SET_THRESHOLD:
                        matched_score = ts_score

        if matched_score > best_score:
            best_score = matched_score
            best_match = supplier

    return best_match


def rule_lookalike_supplier(
    req: CheckRequest,
    store: Store,
    *,
    lang: Lang = DEFAULT_LANG,
) -> Signal | None:
    """Detect supplier name impersonation against known client suppliers with a different BIN."""
    match = find_lookalike_supplier(req, store)
    if match is None:
        return None
    return _make_signal(
        rule_id="lookalike_supplier",
        points=WEIGHT_LOOKALIKE_SUPPLIER,
        severity="primary",
        message_key="rule.lookalike_supplier",
        evidence=Evidence(
            field="name",
            expected=f"{match['name']} (БИН {match['bin']})",
            actual=f"{req.recipient_name} (БИН {req.recipient_bin})",
            since=match["first_seen"],
        ),
        lang=lang,
        supplier_name=match["name"],
    )


def rule_mixed_script_name(req: CheckRequest, *, lang: Lang = DEFAULT_LANG) -> Signal | None:
    """Flag Latin or Greek letters embedded inside Cyrillic words in recipient_name."""
    positions = find_mixed_script_positions(req.recipient_name)
    if not positions:
        return None
    return _make_signal(
        rule_id="mixed_script_name",
        points=WEIGHT_MIXED_SCRIPT_NAME,
        severity="primary",
        message_key="rule.mixed_script_name",
        evidence=Evidence(
            field="name",
            expected="один алфавит в пределах слова",
            actual=req.recipient_name,
        ),
        lang=lang,
    )


def rule_bin_name_mismatch(
    req: CheckRequest,
    store: Store,
    *,
    lang: Lang = DEFAULT_LANG,
) -> Signal | None:
    """Flag when the recipient name does not match the legal entity registered for this BIN.

    Downgrades to info (0 pts) if the exact (BIN, IIK) pair is already in payment history (M3).
    """
    registered_name = store.registry.get(req.recipient_bin)
    if registered_name is None:
        return None

    if name_similarity(req.recipient_name, registered_name) >= LOOKALIKE_SIMILARITY_THRESHOLD:
        return None

    supplier_history = store.get_supplier_history(req.recipient_bin, req.payer_id)
    pair_in_history = any(p["recipient_iik"] == req.recipient_iik for p in supplier_history)

    if pair_in_history:
        return _make_signal(
            rule_id="bin_name_mismatch",
            points=0,
            severity="info",
            message_key="rule.bin_name_mismatch_history",
            evidence=Evidence(
                field="bin",
                expected=registered_name,
                actual=req.recipient_name,
                since=supplier_history[-1]["paid_at"],
            ),
            lang=lang,
            registered_name=registered_name,
        )

    return _make_signal(
        rule_id="bin_name_mismatch",
        points=WEIGHT_BIN_NAME_MISMATCH,
        severity="primary",
        message_key="rule.bin_name_mismatch",
        evidence=Evidence(
            field="bin",
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
) -> Signal | None:
    """Flag when the IIK was previously paid or trusted under a different supplier BIN (M7)."""
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
            evidence=Evidence(
                field="iik",
                expected=f"счёт для БИН {req.recipient_bin}",
                actual=f"использовался для {other_name} (БИН {other_bin})",
                since=last_other["paid_at"],
            ),
            lang=lang,
            other_name=other_name,
        )

    for trusted_bin, trusted_iik, info in store.get_trusted_entries_for_payer(req.payer_id):
        if trusted_iik == req.recipient_iik and trusted_bin != req.recipient_bin:
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
                evidence=Evidence(
                    field="iik",
                    expected=f"счёт для БИН {req.recipient_bin}",
                    actual=f"доверен для {other_name} (БИН {trusted_bin})",
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
) -> Signal | None:
    """Flag a new, untrusted IIK for a known supplier BIN."""
    supplier_history = store.get_supplier_history(req.recipient_bin, req.payer_id)
    if not supplier_history:
        return None
    if store.is_trusted(req.recipient_bin, req.recipient_iik, payer_id=req.payer_id):
        return None

    known_iiks = {p["recipient_iik"] for p in supplier_history}
    if req.recipient_iik in known_iiks:
        return None

    last_payment = supplier_history[-1]
    return _make_signal(
        rule_id="iik_changed",
        points=WEIGHT_IIK_CHANGED,
        severity="primary",
        message_key="rule.iik_changed",
        evidence=Evidence(
            field="iik",
            expected=last_payment["recipient_iik"],
            actual=req.recipient_iik,
            since=last_payment["paid_at"],
        ),
        lang=lang,
    )


def rule_bank_changed(
    req: CheckRequest,
    store: Store,
    *,
    lang: Lang = DEFAULT_LANG,
) -> Signal | None:
    """Amplifier (+15, once) when a known supplier switches to a new untrusted IIK in another bank."""
    supplier_history = store.get_supplier_history(req.recipient_bin, req.payer_id)
    if not supplier_history:
        return None
    if store.is_trusted(req.recipient_bin, req.recipient_iik, payer_id=req.payer_id):
        return None

    known_iiks = {p["recipient_iik"] for p in supplier_history}
    if req.recipient_iik in known_iiks:
        return None

    known_biks = {p["recipient_bik"] for p in supplier_history}
    if req.recipient_bik in known_biks:
        return None

    last_payment = supplier_history[-1]
    old_bank = (
        store.get_bank_name_by_bik(last_payment["recipient_bik"]) or last_payment["recipient_bik"]
    )
    new_bank = store.get_bank_name_by_bik(req.recipient_bik) or req.recipient_bik
    return _make_signal(
        rule_id="bank_changed",
        points=WEIGHT_BANK_CHANGED_AMPLIFIER,
        severity="amplifier",
        message_key="rule.bank_changed",
        evidence=Evidence(
            field="bank",
            expected=old_bank,
            actual=new_bank,
            since=last_payment["paid_at"],
        ),
        lang=lang,
        old_bank=old_bank,
        new_bank=new_bank,
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
            evidence=Evidence(
                field="bin",
                expected="БИН юрлица",
                actual="ИИН физлица",
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
        evidence=Evidence(
            field="bin",
            expected="ИИН физлица",
            actual="БИН юрлица",
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
    """Flag a BCC account opened less than 30 days before today."""
    account = store.bcc_accounts.get(req.recipient_iik)
    if account is None:
        return None

    opened_at = date.fromisoformat(account["opened_at"])
    age_days = (today - opened_at).days
    if age_days < 0 or age_days >= NEW_BCC_ACCOUNT_MAX_DAYS:
        return None

    return _make_signal(
        rule_id="new_bcc_account",
        points=WEIGHT_NEW_BCC_ACCOUNT,
        severity="primary",
        message_key="rule.new_bcc_account",
        evidence=Evidence(
            field="iik",
            expected=f"счёт старше {NEW_BCC_ACCOUNT_MAX_DAYS} дней",
            actual=f"открыт {age_days} дн. назад ({account['opened_at']})",
            since=account["opened_at"],
        ),
        lang=lang,
        age_days=age_days,
    )


def rule_amount_anomaly(
    req: CheckRequest,
    store: Store,
    *,
    reference_bin: str | None = None,
    lang: Lang = DEFAULT_LANG,
) -> Signal | None:
    """Evaluate payment amount against supplier median + MAD, or client p90 on first payment (H2).

    - Known supplier (>=5 payments):
      * ratio >= 3.0 or robust z >= 10 -> primary, 35 pts
      * moderate outlier (ratio >= 1.5 and robust z >= 3.5) -> amplifier, 10..20 pts
    - First payment (no supplier history):
      * amount > client p90 -> amplifier, 10..20 pts
    """
    target_bin = reference_bin or req.recipient_bin
    supplier_history = store.get_supplier_history(target_bin, req.payer_id)

    if len(supplier_history) == 0:
        client_p90 = compute_client_p90(store, req.payer_id)
        if client_p90 is None or client_p90 <= 0 or req.amount_kzt <= client_p90:
            return None
        ratio_p90 = req.amount_kzt / client_p90
        if ratio_p90 >= 2.0:
            points = 20
        elif ratio_p90 >= 1.5:
            points = 15
        else:
            points = 10
        client_p90_kzt = _format_kzt(client_p90)
        return _make_signal(
            rule_id="amount_anomaly",
            points=points,
            severity="amplifier",
            message_key="rule.amount_anomaly_first_p90",
            evidence=Evidence(
                field="amount",
                expected=f"не выше {client_p90_kzt} (p90 клиента)",
                actual=_format_kzt(req.amount_kzt),
            ),
            lang=lang,
            client_p90_kzt=client_p90_kzt,
        )

    if len(supplier_history) < AMOUNT_ANOMALY_MIN_HISTORY:
        return None

    amounts = [float(p["amount_kzt"]) for p in supplier_history]
    median_amount = statistics.median(amounts)
    if median_amount <= 0:
        return None

    ratio = req.amount_kzt / median_amount
    if ratio < 1.5:
        return None

    mad = statistics.median([abs(x - median_amount) for x in amounts])
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
        evidence=Evidence(
            field="amount",
            expected=f"около {median_kzt}",
            actual=_format_kzt(req.amount_kzt),
            since=supplier_history[0]["paid_at"],
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
) -> Signal | None:
    """Info signal when the client has no payment history with this recipient BIN."""
    supplier_history = store.get_supplier_history(req.recipient_bin, req.payer_id)
    if supplier_history:
        return None
    return _make_signal(
        rule_id="first_payment",
        points=0,
        severity="info",
        message_key="rule.first_payment",
        evidence=Evidence(
            field="bin",
            expected="предыдущие платежи в истории",
            actual="0 платежей",
        ),
        lang=lang,
    )


def _fold_urgent_text(text: str) -> str:
    """Normalize purpose text for urgent wording checks (NFKC, strip Cf, homoglyph/KZ fold)."""
    nfkc = unicodedata.normalize("NFKC", text)
    no_cf = "".join(ch for ch in nfkc if unicodedata.category(ch) != "Cf")
    return map_homoglyphs(no_cf.upper().replace("Ё", "Е")).lower()


_URGENT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (
        phrase,
        re.compile(
            r"(?<!\w)"
            + r"\s+".join(re.escape(part) for part in _fold_urgent_text(phrase).split())
            + r"(?!\w)",
            flags=re.UNICODE,
        ),
    )
    for phrase in URGENT_PHRASES
)


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
    reg_year = 2000 + yy if yy <= current_yy else 1900 + yy
    months_diff = (today.year - reg_year) * 12 + (today.month - mm)
    if months_diff < 0 or months_diff >= BIN_YOUNG_MAX_MONTHS:
        return None

    reg_date = f"{mm:02d}.{reg_year}"
    return _make_signal(
        rule_id="bin_young",
        points=WEIGHT_BIN_YOUNG,
        severity="amplifier",
        message_key="rule.bin_young",
        evidence=Evidence(
            field="bin",
            expected=f"регистрация компании от {BIN_YOUNG_MAX_MONTHS} месяцев",
            actual=f"зарегистрирована {reg_date} ({months_diff} мес. назад)",
            since=f"{reg_year:04d}-{mm:02d}",
        ),
        lang=lang,
        reg_date=reg_date,
    )


def rule_urgent_wording(req: CheckRequest, *, lang: Lang = DEFAULT_LANG) -> Signal | None:
    """Amplifier (+10 pts) when purpose contains whole-word urgency or requisite-change wording (L2)."""
    folded = _fold_urgent_text(req.purpose or "")
    if not folded:
        return None

    matched = [phrase for phrase, pattern in _URGENT_PATTERNS if pattern.search(folded)]
    if not matched:
        return None

    return _make_signal(
        rule_id="urgent_wording",
        points=WEIGHT_URGENT_WORDING,
        severity="amplifier",
        message_key="rule.urgent_wording",
        evidence=Evidence(
            field="purpose",
            expected="обычное назначение платежа",
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
        evidence=Evidence(
            field="iik",
            expected=req.recipient_iik,
            actual=info.director_comment or "Подтверждено директором",
            since=info.decided_at,
        ),
        lang=lang,
        date_label=date_label,
    )
