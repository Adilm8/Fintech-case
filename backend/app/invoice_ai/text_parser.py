"""No-key fallback: regex extraction of payment fields from the plain text of an invoice.

The text is untrusted data. Nothing here is executed or interpreted; fields are only matched
by fixed patterns and later re-validated by ``validation.validate``.
"""

from __future__ import annotations

import io
import re
from datetime import date

from app.invoice_ai.models import InvoiceExtraction
from app.invoice_ai.validation import INJECTION_WARNING, looks_like_injection

PDF_MISSING_WARNING = "Для разбора PDF без ключа установите pypdf"
SCAN_WARNING = "В PDF нет текстового слоя (скан): без ключа Claude его не разобрать"
IMAGE_WARNING = "Для разбора фото счёта нужен ключ Claude (ANTHROPIC_API_KEY)"
MAX_TEXT_CHARS = 200_000
BASE_CONFIDENCE_CAP = 0.85

_NBSP = "  "
_BUYER_MARKER = re.compile(r"покупател|заказчик|плательщик", re.IGNORECASE)
_BIN = re.compile(
    r"(?:БИН\s*/\s*ИИН|ИИН\s*/\s*БИН|БИН|ИИН|БСН|ЖСН|BIN|IIN)\W{0,6}?"
    rf"(?<!\d)(\d(?:[ {_NBSP}]?\d){{11}})(?!\d)",
    re.IGNORECASE,
)
# KZ + 18 alnum, spaces allowed; the first letter may be a Cyrillic lookalike so that the
# validators can flag it instead of the parser silently missing the account.
_IIK = re.compile(
    rf"(?<![0-9A-Za-zА-Яа-я])[KК]Z(?:[ {_NBSP}]?[0-9A-ZА-Я]){{18}}(?![0-9A-Za-zА-Яа-я])"
)
_IIK_LABELED = re.compile(
    r"(?:ИИК|IBAN|ЖСК|Р/с|р/сч|расч[её]тный\s+сч[её]т|сч[её]т\s+получателя)\W{0,12}$",
    re.IGNORECASE,
)
_BIK = re.compile(r"(?<![A-Za-z0-9])([A-Z]{4}KZ[A-Z]{2})(?![A-Za-z0-9])")
_KBE = re.compile(r"(?:КБе|KBE)\W{0,4}?(?<!\d)(\d{2})(?!\d)", re.IGNORECASE)
_KNP = re.compile(
    r"(?:КНП|KNP|код\s+назначения\s+платежа)\W{0,4}?(?<!\d)(\d{3})(?!\d)", re.IGNORECASE
)
_NUMBER = r"(\d{1,3}(?:[ " + _NBSP + r"]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)"
_AMOUNT_KEYWORDS: tuple[str, ...] = (
    r"всего\s+к\s+оплате",
    r"итого\s+к\s+оплате",
    r"к\s+оплате",
    r"итого",
    r"всего(?!\s+наименован)",
    r"на\s+сумму",
    r"сумма",
)
_AMOUNT_SKIP_LINE = re.compile(
    r"^\s*(?:в\s+том\s+числе|в\s+т\.\s*ч\.|сумма\s+ндс|ндс)", re.IGNORECASE
)
_MONTHS = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
    "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}  # fmt: skip
_DATE = r"(\d{1,2}[./]\d{1,2}[./]\d{2,4}|\d{4}-\d{2}-\d{2}|\d{1,2}\s+[А-Яа-яЁё]+\s+\d{4})"
_INVOICE = re.compile(
    r"сч[её]т(?:[-\s]+фактура)?(?:\s+на\s+оплату)?\s*(?:№|N[oо]?\.?|#)?\s*"
    r"([0-9A-Za-zА-Яа-я][\w\-/]*)\s+от\s+" + _DATE,
    re.IGNORECASE,
)
_INVOICE_DATE_ONLY = re.compile(r"сч[её]т[^\n]{0,40}?\bот\s+" + _DATE, re.IGNORECASE)
_PURPOSE = re.compile(
    r"(?:назначение\s+платежа|основание\s+платежа)\s*[:\-]?\s*([^\n]+)", re.IGNORECASE
)
_NAME_LABELED = re.compile(
    r"(?:поставщик|получатель|бенефициар|продавец|исполнитель)\s*[:\-]?\s*"
    r"((?:ТОО|АО|ИП|ЧК|ПК|КХ|ГУ|РГП)[^\n,]*?)\s*(?:,|\n|$|\s+(?:БИН|ИИН|БСН|ЖСН))",
    re.IGNORECASE,
)
_NAME_QUOTED = re.compile(r"(?:ТОО|АО|ЧК|ПК|КХ)\s*[«\"“„][^»\"”\n]{2,100}[»\"”]")
_NAME_IP = re.compile(r"ИП\s+[А-ЯЁӘІҢҒҮҰҚӨҺ][а-яёәіңғүұқөһ\-]+(?:\s+[А-ЯЁ]\.\s?[А-ЯЁ]\.)?")


def _strip_spaces(value: str) -> str:
    return re.sub(rf"[ {_NBSP}]", "", value)


def _split_scope(text: str) -> str:
    """Return the part of the text before the buyer block (the supplier's requisites)."""
    marker = _BUYER_MARKER.search(text)
    return text[: marker.start()] if marker else text


def _parse_date(raw: str) -> str | None:
    raw = raw.strip().lower()
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
            return date.fromisoformat(raw).isoformat()
        numeric = re.fullmatch(r"(\d{1,2})[./](\d{1,2})[./](\d{2,4})", raw)
        if numeric:
            day, month, year = (int(x) for x in numeric.groups())
            return date(year + 2000 if year < 100 else year, month, day).isoformat()
        words = re.fullmatch(r"(\d{1,2})\s+([а-яё]+)\s+(\d{4})", raw)
        if words and words.group(2) in _MONTHS:
            month = _MONTHS[words.group(2)]
            return date(int(words.group(3)), month, int(words.group(1))).isoformat()
    except ValueError:
        return None
    return None


def _to_float(raw: str) -> float | None:
    try:
        value = float(_strip_spaces(raw).replace(",", "."))
    except ValueError:
        return None
    return value if value > 0 else None


def _find_amount(text: str) -> float | None:
    lines = [ln for ln in text.splitlines() if not _AMOUNT_SKIP_LINE.match(ln)]
    for keyword in _AMOUNT_KEYWORDS:
        pattern = re.compile(keyword + r"[^\d\n]{0,40}" + _NUMBER, re.IGNORECASE)
        found: float | None = None
        for line in lines:
            for match in pattern.finditer(line):
                value = _to_float(match.group(1))
                if value is not None:
                    found = value  # totals are at the bottom: the last match wins
        if found is not None:
            return found
    return None


def _pick_iik(scope: str, warnings: list[str]) -> str | None:
    candidates: list[tuple[str, bool]] = []
    for match in _IIK.finditer(scope):
        before = scope[max(0, match.start() - 40) : match.start()]
        candidates.append((_strip_spaces(match.group(0)), _IIK_LABELED.search(before) is not None))
    if not candidates:
        return None
    labeled = [value for value, is_labeled in candidates if is_labeled]
    chosen = (labeled or [value for value, _ in candidates])[0]
    if len({value for value, _ in candidates}) > 1:
        warnings.append("В документе несколько номеров счетов (ИИК): проверьте выбор вручную")
    return chosen


def _pick_bin(scope: str, warnings: list[str]) -> str | None:
    values = [_strip_spaces(m.group(1)) for m in _BIN.finditer(scope)]
    if not values:
        return None
    if len(set(values)) > 1:
        warnings.append("В документе несколько БИН/ИИН: проверьте выбор вручную")
    return values[0]


def _pick_name(scope: str) -> str | None:
    match = _NAME_LABELED.search(scope)
    if match:
        return match.group(1).strip()
    for pattern in (_NAME_QUOTED, _NAME_IP):
        match = pattern.search(scope)
        if match:
            return match.group(0).strip()
    return None


def _detect_currency(text: str) -> str | None:
    if re.search(r"KZT|тенге|₸|\bтг\b", text, re.IGNORECASE):
        return "KZT"
    for code, pattern in (("USD", r"USD|долл"), ("EUR", r"EUR|евро"), ("RUB", r"RUB|руб")):
        if re.search(pattern, text, re.IGNORECASE):
            return code
    return None


def parse_text(text: str) -> InvoiceExtraction:
    """Extract invoice fields from plain text with fixed regex patterns."""
    text = text[:MAX_TEXT_CHARS].replace("\r\n", "\n").replace("\r", "\n")
    scope = _split_scope(text)
    warnings: list[str] = []

    number: str | None = None
    invoice_date: str | None = None
    invoice = _INVOICE.search(text)
    if invoice:
        number = invoice.group(1).strip()
        invoice_date = _parse_date(invoice.group(2))
    else:
        date_only = _INVOICE_DATE_ONLY.search(text)
        if date_only:
            invoice_date = _parse_date(date_only.group(1))

    purpose_match = _PURPOSE.search(text)
    purpose = purpose_match.group(1).strip() if purpose_match else None
    if purpose is None and number:
        suffix = f" от {invoice_date}" if invoice_date else ""
        purpose = f"Оплата по счёту № {number}{suffix}"

    # Prefer the supplier block; fall back to the whole text if the buyer block comes first.
    bik_match = _BIK.search(scope) or _BIK.search(text)
    kbe_match = _KBE.search(scope) or _KBE.search(text)
    knp_match = _KNP.search(text)

    result = InvoiceExtraction(
        recipient_name=_pick_name(scope) or _pick_name(text),
        recipient_bin=_pick_bin(scope, warnings) or _pick_bin(text, warnings),
        recipient_iik=_pick_iik(scope, warnings) or _pick_iik(text, warnings),
        recipient_bik=bik_match.group(1) if bik_match else None,
        amount_kzt=_find_amount(text),
        purpose=purpose,
        invoice_number=number,
        invoice_date=invoice_date,
        kbe=kbe_match.group(1) if kbe_match else None,
        knp=knp_match.group(1) if knp_match else None,
        currency=_detect_currency(text),
        warnings=warnings,
    )

    weights = {
        "recipient_bin": 0.2, "recipient_iik": 0.25, "recipient_bik": 0.1,
        "recipient_name": 0.15, "amount_kzt": 0.2, "purpose": 0.1,
    }  # fmt: skip
    found = sum(w for field, w in weights.items() if getattr(result, field) is not None)
    result.confidence = round(min(found, BASE_CONFIDENCE_CAP), 2)
    if warnings:
        result.confidence = round(max(0.0, result.confidence - 0.2), 2)
    result.source = "text_rules" if found > 0 else "none"
    if looks_like_injection(text):
        result.warnings.append(INJECTION_WARNING)
    if found == 0:
        result.warnings.append("Не удалось найти реквизиты в тексте документа")
    return result


def extract_pdf_text(data: bytes) -> str | None:
    """Return the text layer of a PDF, or None if ``pypdf`` is not installed.

    Raises ValueError if the PDF cannot be read.
    """
    try:
        import pypdf  # lazy: optional dependency
    except ImportError:
        return None
    try:
        reader = pypdf.PdfReader(io.BytesIO(data))
        if getattr(reader, "is_encrypted", False):
            raise ValueError("PDF защищён паролем")
        parts = [page.extract_text() or "" for page in reader.pages[:20]]
    except ValueError:
        raise
    except Exception as exc:  # pypdf raises many error types on broken files
        raise ValueError("PDF повреждён или не читается") from exc
    return "\n".join(parts)


def _decode_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1251"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def parse_document(data: bytes, mime: str) -> InvoiceExtraction:
    """Fallback extraction for a file; never raises."""
    if mime == "application/pdf":
        try:
            text = extract_pdf_text(data)
        except ValueError as exc:
            return InvoiceExtraction(source="none", warnings=[str(exc)])
        if text is None:
            return InvoiceExtraction(source="none", warnings=[PDF_MISSING_WARNING])
        if not text.strip():
            return InvoiceExtraction(source="none", warnings=[SCAN_WARNING])
        return parse_text(text)
    if mime == "text/plain":
        return parse_text(_decode_text(data))
    return InvoiceExtraction(source="none", warnings=[IMAGE_WARNING])
