"""Pure risk evaluation rules for BCC Business Shield.

Each rule is a pure function returning Signal | None with a single plain-language
Russian sentence and structured evidence.
"""

from __future__ import annotations

import statistics
from datetime import date

from app.risk.config import (
    AMOUNT_ANOMALY_MIN_HISTORY,
    BCC_BANK_CODE,
    BCC_BIK,
    DEMO_TODAY,
    LOOKALIKE_SIMILARITY_THRESHOLD,
    NEW_BCC_ACCOUNT_MAX_DAYS,
    URGENT_PHRASES,
    WEIGHT_BANK_CHANGED_AMPLIFIER,
    WEIGHT_BIN_NAME_MISMATCH,
    WEIGHT_ENTITY_TYPE_MISMATCH,
    WEIGHT_IIK_CHANGED,
    WEIGHT_LOOKALIKE_SUPPLIER,
    WEIGHT_NEW_BCC_ACCOUNT,
    WEIGHT_URGENT_WORDING,
)
from app.risk.names import detect_legal_form_kind, name_similarity
from app.schemas import CheckRequest, Evidence, Signal
from app.store import Store
from app.validators.kz import (
    bik_matches_iik,
    bik_ok,
    bin_iin_checksum_ok,
    bin_kind,
    iik_bank_code,
    iik_ok,
)


def _format_kzt(amount: float) -> str:
    return f"{round(amount):,} ₸".replace(",", " ")


# --- Precheck rules (produce invalid verdict, no score) ---


def rule_bin_format(req: CheckRequest) -> Signal | None:
    """Validate BIN/IIN format, 5th digit classification, and mod-11 checksum."""
    if bin_iin_checksum_ok(req.recipient_bin) and bin_kind(req.recipient_bin) is not None:
        return None
    return Signal(
        rule_id="invalid_bin",
        points=0,
        severity="block",
        reason_ru="В БИН/ИИН получателя ошибка — такого номера не существует.",
        evidence=Evidence(
            field="bin",
            expected="12 цифр с верной контрольной суммой",
            actual=req.recipient_bin,
        ),
    )


def rule_iik_format(req: CheckRequest) -> Signal | None:
    """Validate IIK format, Cyrillic lookalikes, and IBAN mod-97 checksum."""
    ok, error_ru = iik_ok(req.recipient_iik)
    if ok:
        return None
    return Signal(
        rule_id="invalid_iik",
        points=0,
        severity="block",
        reason_ru=error_ru or "В ИИК ошибка — такого счёта не существует.",
        evidence=Evidence(
            field="iik",
            expected="20 символов формата KZ...",
            actual=req.recipient_iik,
        ),
    )


def rule_bik_format(req: CheckRequest, store: Store) -> Signal | None:
    """Validate that BIK is 8 characters and exists in banks.json."""
    if bik_ok(req.recipient_bik, path=store.banks_path):
        return None
    return Signal(
        rule_id="invalid_bik",
        points=0,
        severity="block",
        reason_ru="Указан неверный или неизвестный БИК банка получателя.",
        evidence=Evidence(
            field="bik",
            expected="8-символьный БИК банка РК",
            actual=req.recipient_bik,
        ),
    )


def rule_iik_bank_code_vs_bik(req: CheckRequest, store: Store) -> Signal | None:
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
    return Signal(
        rule_id="iik_bank_code_vs_bik",
        points=0,
        severity="block",
        reason_ru="Код банка в номере счёта не совпадает с указанным БИК.",
        evidence=Evidence(
            field="bik",
            expected=expected_str,
            actual=actual_str,
        ),
    )


# --- Blocking & risk scoring rules ---


def rule_bcc_account_other_owner(req: CheckRequest, store: Store) -> Signal | None:
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
    return Signal(
        rule_id="bcc_account_other_owner",
        points=100,
        severity="block",
        reason_ru=(
            f"Этот счёт в БЦК оформлен на другую компанию ({owner_name}), "
            "а не на указанного получателя."
        ),
        evidence=Evidence(
            field="iik",
            expected=f"счёт на БИН {req.recipient_bin}",
            actual=f"владелец {owner_name} (БИН {owner_bin})",
            since=account.get("opened_at"),
        ),
    )


def find_lookalike_supplier(req: CheckRequest, store: Store) -> dict[str, str] | None:
    """Find the closest known client supplier with similarity >= 85 and a different BIN."""
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
        score = name_similarity(req.recipient_name, supplier["name"])
        if score >= LOOKALIKE_SIMILARITY_THRESHOLD and score > best_score:
            best_score = score
            best_match = supplier

    return best_match


def rule_lookalike_supplier(req: CheckRequest, store: Store) -> Signal | None:
    """Detect supplier name impersonation (similarity >= 85 to a known supplier, different BIN)."""
    match = find_lookalike_supplier(req, store)
    if match is None:
        return None
    return Signal(
        rule_id="lookalike_supplier",
        points=WEIGHT_LOOKALIKE_SUPPLIER,
        severity="primary",
        reason_ru=(
            f"Название получателя почти совпадает с вашим поставщиком {match['name']}, "
            "но указан другой БИН."
        ),
        evidence=Evidence(
            field="name",
            expected=f"{match['name']} (БИН {match['bin']})",
            actual=f"{req.recipient_name} (БИН {req.recipient_bin})",
            since=match["first_seen"],
        ),
    )


def rule_bin_name_mismatch(req: CheckRequest, store: Store) -> Signal | None:
    """Flag when the recipient name does not match the legal entity registered for this BIN."""
    registered_name = store.registry.get(req.recipient_bin)
    if registered_name is None:
        return None

    if name_similarity(req.recipient_name, registered_name) >= LOOKALIKE_SIMILARITY_THRESHOLD:
        return None

    return Signal(
        rule_id="bin_name_mismatch",
        points=WEIGHT_BIN_NAME_MISMATCH,
        severity="primary",
        reason_ru=f"По этому БИН в реестре числится другая компания — {registered_name}.",
        evidence=Evidence(
            field="bin",
            expected=registered_name,
            actual=req.recipient_name,
        ),
    )


def rule_iik_changed(req: CheckRequest, store: Store) -> Signal | None:
    """Flag a new, untrusted IIK for a known supplier BIN."""
    supplier_history = store.get_supplier_history(req.recipient_bin, req.payer_id)
    if not supplier_history:
        return None
    if store.is_trusted(req.recipient_bin, req.recipient_iik):
        return None

    known_iiks = {p["recipient_iik"] for p in supplier_history}
    if req.recipient_iik in known_iiks:
        return None

    last_payment = supplier_history[-1]
    return Signal(
        rule_id="iik_changed",
        points=WEIGHT_IIK_CHANGED,
        severity="primary",
        reason_ru="У этого поставщика указан новый номер счёта, на который вы раньше не платили.",
        evidence=Evidence(
            field="iik",
            expected=last_payment["recipient_iik"],
            actual=req.recipient_iik,
            since=last_payment["paid_at"],
        ),
    )


def rule_bank_changed(req: CheckRequest, store: Store) -> Signal | None:
    """Amplifier (+15, once) when a known supplier switches to a new untrusted IIK in another bank."""
    supplier_history = store.get_supplier_history(req.recipient_bin, req.payer_id)
    if not supplier_history:
        return None
    if store.is_trusted(req.recipient_bin, req.recipient_iik):
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
    return Signal(
        rule_id="bank_changed",
        points=WEIGHT_BANK_CHANGED_AMPLIFIER,
        severity="amplifier",
        reason_ru=f"Сменился банк поставщика: раньше платежи шли в {old_bank}, а теперь в {new_bank}.",
        evidence=Evidence(
            field="bank",
            expected=old_bank,
            actual=new_bank,
            since=last_payment["paid_at"],
        ),
    )


def rule_entity_type_mismatch(req: CheckRequest) -> Signal | None:
    """Flag mismatch between legal form in name (ТОО vs ИП) and BIN/IIN 5th digit."""
    expected_kind = detect_legal_form_kind(req.recipient_name)
    actual_kind = bin_kind(req.recipient_bin)
    if expected_kind is None or actual_kind is None or expected_kind == actual_kind:
        return None

    if expected_kind == "bin":
        reason_ru = "В названии указана компания, но вместо БИН введён ИИН физлица."
        expected_label = "БИН юрлица"
        actual_label = "ИИН физлица"
    else:
        reason_ru = "В названии указан ИП, но вместо ИИН введён БИН юрлица."
        expected_label = "ИИН физлица"
        actual_label = "БИН юрлица"

    return Signal(
        rule_id="entity_type_mismatch",
        points=WEIGHT_ENTITY_TYPE_MISMATCH,
        severity="primary",
        reason_ru=reason_ru,
        evidence=Evidence(
            field="bin",
            expected=expected_label,
            actual=actual_label,
        ),
    )


def rule_new_bcc_account(
    req: CheckRequest,
    store: Store,
    *,
    today: date = DEMO_TODAY,
) -> Signal | None:
    """Flag a BCC account opened less than 30 days before today."""
    account = store.bcc_accounts.get(req.recipient_iik)
    if account is None:
        return None

    opened_at = date.fromisoformat(account["opened_at"])
    age_days = (today - opened_at).days
    if age_days < 0 or age_days >= NEW_BCC_ACCOUNT_MAX_DAYS:
        return None

    return Signal(
        rule_id="new_bcc_account",
        points=WEIGHT_NEW_BCC_ACCOUNT,
        severity="primary",
        reason_ru=f"Счёт в БЦК открыт совсем недавно — {age_days} дн. назад.",
        evidence=Evidence(
            field="iik",
            expected=f"счёт старше {NEW_BCC_ACCOUNT_MAX_DAYS} дней",
            actual=f"открыт {age_days} дн. назад ({account['opened_at']})",
            since=account["opened_at"],
        ),
    )


def rule_amount_anomaly(
    req: CheckRequest,
    store: Store,
    *,
    reference_bin: str | None = None,
) -> Signal | None:
    """Amplifier (10..25 pts) when payment amount sharply exceeds supplier median + MAD."""
    target_bin = reference_bin or req.recipient_bin
    supplier_history = store.get_supplier_history(target_bin, req.payer_id)
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
    if mad > 0:
        mod_z = 0.6745 * (req.amount_kzt - median_amount) / mad
        if mod_z < 3.5:
            return None
        if ratio >= 3.0 or mod_z >= 10.0:
            points = 25
        elif ratio >= 2.5 or mod_z >= 7.0:
            points = 20
        elif ratio >= 2.0 or mod_z >= 5.0:
            points = 15
        else:
            points = 10
    else:
        if ratio >= 3.0:
            points = 25
        elif ratio >= 2.5:
            points = 20
        elif ratio >= 2.0:
            points = 15
        else:
            points = 10

    return Signal(
        rule_id="amount_anomaly",
        points=points,
        severity="amplifier",
        reason_ru=(
            f"Сумма платежа в {ratio:.1f} раза выше обычной для этого поставщика "
            f"(обычно около {_format_kzt(median_amount)})."
        ),
        evidence=Evidence(
            field="amount",
            expected=f"около {_format_kzt(median_amount)}",
            actual=_format_kzt(req.amount_kzt),
            since=supplier_history[0]["paid_at"],
        ),
    )


def rule_first_payment(req: CheckRequest, store: Store) -> Signal | None:
    """Info signal when the client has no payment history with this recipient BIN."""
    supplier_history = store.get_supplier_history(req.recipient_bin, req.payer_id)
    if supplier_history:
        return None
    return Signal(
        rule_id="first_payment",
        points=0,
        severity="info",
        reason_ru="Вы ещё ни разу не платили этому поставщику — сравнить реквизиты не с чем.",
        evidence=Evidence(
            field="bin",
            expected="предыдущие платежи в истории",
            actual="0 платежей",
        ),
    )


def rule_urgent_wording(req: CheckRequest) -> Signal | None:
    """Amplifier (+10 pts) when payment purpose contains urgency or requisite-change phrasing."""
    purpose_lower = (req.purpose or "").lower()
    matched = [phrase for phrase in URGENT_PHRASES if phrase in purpose_lower]
    if not matched:
        return None

    return Signal(
        rule_id="urgent_wording",
        points=WEIGHT_URGENT_WORDING,
        severity="amplifier",
        reason_ru=(
            "В назначении платежа есть формулировка срочности или смены реквизитов — "
            "частый признак подмены счёта."
        ),
        evidence=Evidence(
            field="purpose",
            expected="обычное назначение платежа",
            actual=", ".join(matched),
        ),
    )
