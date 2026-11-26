"""Deterministic post-validation of extracted fields (never trust the extractor silently)."""

from __future__ import annotations

import re
from datetime import date

from app.i18n import t
from app.invoice_ai.models import InvoiceExtraction
from app.validators.kz import bik_matches_iik, bik_ok, bin_iin_checksum_ok, iik_check

MAX_NAME_LEN = 200
MAX_PURPOSE_LEN = 500
MAX_WARNING_LEN = 200
MAX_WARNINGS = 12
PENALTY = 0.25
IDENTITY_CONFIDENCE_CAP = 0.5

_CURRENCY_ALIASES = {"₸": "KZT", "ТЕНГЕ": "KZT", "ТГ": "KZT", "KZT": "KZT"}
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_INJECTION = re.compile(
    r"игнорируй|игнорировать|не\s+учитывай|забудь\s+(?:все|предыдущ)|"
    r"ignore\s+(?:all|any|the|previous|prior|above)|disregard\s+(?:all|the|previous)|"
    r"system\s+prompt|you\s+are\s+now|\bnew\s+instructions?\b|"
    r"(?:укажи|замени|подставь|используй)\s+(?:в\s+ответе\s+)?(?:иик|бин|бик|реквизит)",
    re.IGNORECASE,
)

INJECTION_WARNING = "В документе найден текст, похожий на инструкции для ИИ, — он проигнорирован"


def looks_like_injection(text: str | None) -> bool:
    """True if the text contains phrases that look like instructions aimed at an AI."""
    return bool(text) and _INJECTION.search(text or "") is not None


def _clean(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(_CONTROL_CHARS.sub(" ", str(value)).split())
    return cleaned[:limit] or None


def normalize(ex: InvoiceExtraction) -> InvoiceExtraction:
    """Return a copy with trimmed/normalised values (does not judge validity)."""
    data = ex.model_copy(deep=True)
    data.recipient_name = _clean(data.recipient_name, MAX_NAME_LEN)
    data.purpose = _clean(data.purpose, MAX_PURPOSE_LEN)
    data.invoice_number = _clean(data.invoice_number, 40)

    bin_value = _clean(data.recipient_bin, 40)
    if bin_value is not None:
        compact = re.sub(r"[\s\-\u00a0]", "", bin_value)
        bin_value = compact if compact.isdigit() else bin_value
    data.recipient_bin = bin_value

    iik_value = _clean(data.recipient_iik, 60)
    data.recipient_iik = re.sub(r"[\s\-\u00a0]", "", iik_value).upper() if iik_value else None

    bik_value = _clean(data.recipient_bik, 20)
    data.recipient_bik = re.sub(r"\s", "", bik_value).upper() if bik_value else None

    for field in ("kbe", "knp"):
        raw = _clean(getattr(data, field), 20)
        digits = re.sub(r"\D", "", raw) if raw else ""
        setattr(data, field, digits or raw)

    currency = _clean(data.currency, 20)
    if currency:
        currency = _CURRENCY_ALIASES.get(currency.upper(), currency.upper())
    data.currency = currency

    date_value = _clean(data.invoice_date, 20)
    data.invoice_date = date_value
    data.warnings = [w for w in (_clean(w, MAX_WARNING_LEN) for w in data.warnings) if w]
    return data


def _valid_iso_date(value: str) -> bool:
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value))


def validate(ex: InvoiceExtraction) -> InvoiceExtraction:
    """Normalise and re-check every field with the deterministic KZ validators.

    Invalid values are kept (so the user sees what the document says and the rule engine flags
    it) but get a warning and lower the confidence. Idempotent: running it twice adds nothing.
    """
    data = normalize(ex)
    warnings = list(data.warnings)
    penalty = 0.0
    identity_failed = False

    def add(message: str, *, identity: bool = False, penalize: bool = True) -> None:
        nonlocal penalty, identity_failed
        if message in warnings:
            return
        warnings.append(message)
        if penalize:
            penalty += PENALTY
        if identity:
            identity_failed = True

    # BIN / IIN
    if not data.recipient_bin:
        add("Не найден БИН/ИИН поставщика", penalize=False)
    elif not bin_iin_checksum_ok(data.recipient_bin):
        add("БИН не прошёл проверку: неверный формат или контрольная сумма", identity=True)

    # IIK
    if not data.recipient_iik:
        add("Не найден ИИК поставщика", penalize=False)
    else:
        ok, key, params = iik_check(data.recipient_iik)
        if not ok and key:
            add(f"ИИК не прошёл проверку: {t(key, 'ru', **params)}", identity=True)

    # BIK
    if not data.recipient_bik:
        add("Не найден БИК банка поставщика", penalize=False)
    elif not bik_ok(data.recipient_bik):
        add("БИК не найден в справочнике банков", identity=True)
    elif data.recipient_iik and not bik_matches_iik(data.recipient_bik, data.recipient_iik):
        add("Код банка в ИИК не совпадает с БИК", identity=True)

    # Amount
    if data.amount_kzt is None:
        add("Не найдена сумма к оплате", penalize=False)
    elif data.amount_kzt <= 0:
        data.amount_kzt = None
        add("Сумма в счёте некорректна (не больше нуля) и не подставлена")

    # Currency
    if data.currency and data.currency != "KZT":
        add(f"Валюта счёта не тенге ({data.currency}): проверьте сумму")

    # Dates and codes
    if data.invoice_date and not _valid_iso_date(data.invoice_date):
        data.invoice_date = None
        add("Дата счёта не распознана")
    if data.kbe and not re.fullmatch(r"\d{2}", data.kbe):
        add("КБе имеет неверный формат")
    if data.knp and not re.fullmatch(r"\d{3}", data.knp):
        add("КНП имеет неверный формат")

    # Text that tries to talk to the model
    if any(looks_like_injection(v) for v in (data.recipient_name, data.purpose, *data.warnings)):
        add(INJECTION_WARNING, penalize=False)

    confidence = max(0.0, data.confidence - penalty)
    if identity_failed:
        confidence = min(confidence, IDENTITY_CONFIDENCE_CAP)
    data.confidence = round(confidence, 2)
    data.warnings = warnings[:MAX_WARNINGS]
    return data
