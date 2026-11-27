"""Каноническая привязка проверки к подписи платежа (защита от TOCTOU).

Модуль работает только с уже загруженными данными и не обращается к БД.

ВАЖНО: класс ``SimulatedSigner`` реализует исключительно ИМИТАЦИЮ ЭЦП на базе
локального HMAC-SHA256 для демонстрационного режима и тестирования. Он НЕ является
NCALayer / ЭЦП НУЦ РК и НЕ имеет юридической силы.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel

from app.prod.errors import ProdError
from app.schemas import CheckRequest, compute_request_sha256

DOCUMENT_SCHEMA_VERSION: int = 1
DEFAULT_CURRENCY: str = "KZT"

SIMULATED_LABEL: str = "Имитация ЭЦП, не NCALayer"
NCALAYER_LABEL: str = "ЭЦП НУЦ РК (NCALayer)"

SIMULATED_SECRET_ENV: str = "PROD_SIM_SIGN_SECRET"
# Безопасное демонстрационное значение по умолчанию.
# ИМИТАЦИЯ ЭЦП, не NCALayer, не имеет юридической силы и не предназначено для продакшена.
DEFAULT_DEMO_MASTER_SECRET: str = "bcc-shield-demo-simulated-hmac-secret-not-for-production"

SignerKind = Literal["simulated", "ncalayer"]

_AMOUNT_QUANT = Decimal("0.01")
_MISSING = object()


class DocumentMismatchError(ProdError):
    """HTTP 409 при несовпадении дайджеста подписываемого документа с текущими данными."""

    def __init__(
        self,
        detail: str | None = None,
        *,
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(409, "document_mismatch", detail=detail, extra=extra)


class InvalidSignerError(ProdError, ValueError):
    """Ошибка валидации HTTP 422 при передаче неизвестного типа подписанта."""

    def __init__(self, signer: object) -> None:
        message = (
            f"Неподдерживаемый способ подписания: {signer!r}. "
            "Допустимые значения: 'simulated', 'ncalayer'."
        )
        super().__init__(422, "validation_error", detail=message)


@dataclass(frozen=True)
class VerifiedSignature:
    """Подтверждённые атрибуты реальной криптографической подписи (CMS/PKCS#7)."""

    signer_subject: str
    signer_iin_bin: str
    certificate_serial: str
    signed_at: str


@dataclass(frozen=True)
class SignatureVerificationResult:
    """Итог проверки подписи для записи в журнал аудита."""

    verified: bool
    signer: SignerKind
    label: str
    simulated: bool
    details: VerifiedSignature | None = None


def _get_field(source: Any, *names: str, default: Any = _MISSING) -> Any:
    """Извлечь первое найденное поле из dict, sqlite3.Row, Pydantic-объекта или ORM-сущности."""
    if source is None:
        return default
    if isinstance(source, sqlite3.Row):
        keys = set(source.keys())
        for name in names:
            if name in keys:
                return source[name]
        return default
    if isinstance(source, Mapping):
        for name in names:
            if name in source:
                return source[name]
        return default
    if isinstance(source, BaseModel):
        model_fields = type(source).model_fields
        for name in names:
            if name in model_fields or hasattr(source, name):
                return getattr(source, name)
        return default
    for name in names:
        if hasattr(source, name):
            return getattr(source, name)
    return default


def _get_payment_field(payment: Any, nested_req: Any, *names: str, default: Any = _MISSING) -> Any:
    value = _get_field(payment, *names, default=_MISSING)
    if value is not _MISSING:
        return value
    if nested_req is not None:
        return _get_field(nested_req, *names, default=default)
    return default


def _format_decimal_amount(value: Any) -> str | None:
    """Привести сумму к канонической строке с двумя знаками после запятой."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise TypeError("Сумма платежа не может быть булевым значением.")
    try:
        if isinstance(value, Decimal):
            dec = value
        elif isinstance(value, int):
            dec = Decimal(value)
        elif isinstance(value, float):
            if not math.isfinite(value):
                raise ValueError("Сумма платежа должна быть конечным числом.")
            dec = Decimal(str(value))
        elif isinstance(value, str):
            cleaned = value.strip()
            if not cleaned:
                return None
            dec = Decimal(cleaned)
        else:
            raise TypeError(f"Неподдерживаемый тип суммы платежа: {type(value).__name__}.")
    except InvalidOperation as exc:
        raise ValueError("Некорректный формат суммы платежа.") from exc

    if not dec.is_finite():
        raise ValueError("Сумма платежа должна быть конечным числом.")
    return str(dec.quantize(_AMOUNT_QUANT, rounding=ROUND_HALF_UP))


def _extract_amount_str(payment: Any, nested_req: Any) -> str | None:
    raw_kzt = _get_field(payment, "amount_kzt", "amount", default=_MISSING)
    if raw_kzt is not _MISSING:
        return _format_decimal_amount(raw_kzt)

    raw_tiyn = _get_field(payment, "amount_tiyn", default=_MISSING)
    if raw_tiyn is not _MISSING:
        if raw_tiyn is None:
            return None
        if isinstance(raw_tiyn, bool):
            raise TypeError("Сумма в тиынах не может быть булевым значением.")
        return _format_decimal_amount(Decimal(int(raw_tiyn)) / Decimal(100))

    if nested_req is not None:
        nested_kzt = _get_field(nested_req, "amount_kzt", "amount", default=_MISSING)
        if nested_kzt is not _MISSING:
            return _format_decimal_amount(nested_kzt)
    return None


def _format_iso_date(value: Any) -> str | None:
    if value is _MISSING or value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    return str(value)


def _format_text(value: Any, *, default: str | None = "") -> str | None:
    if value is _MISSING:
        return default
    if value is None:
        return None
    return str(value)


def _resolve_request_sha256(
    payment: Any,
    check: Any,
    nested_req: Any,
    *,
    company_id: str | None,
    recipient_name: str | None,
    recipient_bin: str | None,
    recipient_iik: str | None,
    recipient_bik: str | None,
    amount_kzt: str | None,
    purpose: str | None,
    kbe: str | None,
    knp: str | None,
) -> str | None:
    from_check = _get_field(check, "request_sha256", default=_MISSING)
    if from_check is not _MISSING:
        return None if from_check is None else str(from_check)

    from_payment = _get_field(payment, "request_sha256", default=_MISSING)
    if from_payment is not _MISSING:
        return None if from_payment is None else str(from_payment)

    if isinstance(nested_req, CheckRequest):
        return compute_request_sha256(nested_req, resolved_payer_id=company_id or "")

    if recipient_name is not None and amount_kzt is not None:
        canonical_req = {
            "payer_id": company_id or "",
            "recipient_name": recipient_name,
            "recipient_bin": recipient_bin or "",
            "recipient_iik": recipient_iik or "",
            "recipient_bik": recipient_bik or "",
            "amount_kzt": float(Decimal(amount_kzt)),
            "purpose": purpose or "",
            "kbe": kbe or "",
            "knp": knp or "",
        }
        raw = json.dumps(canonical_req, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    return None


def build_payment_document(payment: Any, check: Any) -> dict[str, Any]:
    """Собрать канонический платёжный документ, связывающий реквизиты и результат проверки.

    Принимает dict, ``sqlite3.Row``, Pydantic-схему (``Payment`` / ``CheckResult``)
    или произвольный ORM/датакласс-объект. Нестабильные служебные поля
    (``updated_at``, ``created_at``, ``status``, ``signed_at`` и т.п.) намеренно не включаются.
    """
    nested_req = _get_field(payment, "request", default=None)

    payment_id = _format_text(
        _get_field(payment, "id", "payment_id", default=_MISSING), default=None
    )
    company_id = _format_text(
        _get_payment_field(payment, nested_req, "company_id", "payer_id", default=_MISSING),
        default=None,
    )
    doc_number = _format_text(_get_field(payment, "doc_number", default=_MISSING), default="")
    doc_date = _format_iso_date(_get_field(payment, "doc_date", "date", default=_MISSING))

    recipient_name = _format_text(
        _get_payment_field(payment, nested_req, "recipient_name", default=_MISSING),
        default=None,
    )
    recipient_bin = _format_text(
        _get_payment_field(payment, nested_req, "recipient_bin", default=_MISSING),
        default=None,
    )
    recipient_iik = _format_text(
        _get_payment_field(
            payment, nested_req, "recipient_iik", "recipient_iban", "iban", default=_MISSING
        ),
        default=None,
    )
    recipient_bik = _format_text(
        _get_payment_field(payment, nested_req, "recipient_bik", "bik", default=_MISSING),
        default=None,
    )
    amount_kzt = _extract_amount_str(payment, nested_req)

    raw_currency = _get_payment_field(payment, nested_req, "currency", default=_MISSING)
    if raw_currency is _MISSING:
        currency: str | None = DEFAULT_CURRENCY
    elif raw_currency is None:
        currency = None
    else:
        currency = str(raw_currency).strip().upper() or DEFAULT_CURRENCY

    kbe = _format_text(_get_payment_field(payment, nested_req, "kbe", default=_MISSING), default="")
    knp = _format_text(_get_payment_field(payment, nested_req, "knp", default=_MISSING), default="")
    purpose = _format_text(
        _get_payment_field(payment, nested_req, "purpose", default=_MISSING),
        default="",
    )

    check_id = _format_text(_get_field(check, "check_id", "id", default=_MISSING), default=None)
    ruleset_version = _format_text(
        _get_field(check, "ruleset_version", default=_MISSING),
        default=None,
    )
    verdict = _format_text(_get_field(check, "verdict", default=_MISSING), default=None)
    request_sha256 = _resolve_request_sha256(
        payment,
        check,
        nested_req,
        company_id=company_id,
        recipient_name=recipient_name,
        recipient_bin=recipient_bin,
        recipient_iik=recipient_iik,
        recipient_bik=recipient_bik,
        amount_kzt=amount_kzt,
        purpose=purpose,
        kbe=kbe,
        knp=knp,
    )

    return {
        "schema_version": DOCUMENT_SCHEMA_VERSION,
        "payment_id": payment_id,
        "company_id": company_id,
        "doc_number": doc_number,
        "doc_date": doc_date,
        "recipient_name": recipient_name,
        "recipient_bin": recipient_bin,
        "recipient_iik": recipient_iik,
        "recipient_bik": recipient_bik,
        "amount_kzt": amount_kzt,
        "currency": currency,
        "kbe": kbe,
        "knp": knp,
        "purpose": purpose,
        "request_sha256": request_sha256,
        "check_id": check_id,
        "ruleset_version": ruleset_version,
        "verdict": verdict,
    }


def _normalize_json_value(value: Any) -> Any:
    """Нормализовать значения перед канонической JSON-сериализацией."""
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, Decimal):
        return _format_decimal_amount(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Канонический JSON не допускает NaN или бесконечность.")
        return value
    if isinstance(value, Mapping):
        return {str(k): _normalize_json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize_json_value(item) for item in value]
    raise TypeError(f"Тип {type(value).__name__} не поддерживается в каноническом документе.")


def canonical_json(doc: Mapping[str, Any]) -> str:
    """Сериализовать документ в детерминированный компактный UTF-8 JSON."""
    normalized = _normalize_json_value(doc)
    return json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def document_digest(doc: Mapping[str, Any]) -> str:
    """Вычислить hex SHA-256 от канонического JSON платёжного документа."""
    raw = canonical_json(doc).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def verify_document_binding(client_digest: str, payment: Any, check: Any) -> None:
    """Проверить, что подписанный клиентом digest совпадает с текущими данными платежа и проверки.

    Пересчитывает digest по сохранённым на сервере данным и сравнивает через
    ``hmac.compare_digest``. При несовпадении бросает ``DocumentMismatchError`` (HTTP 409,
    код ``document_mismatch``) без раскрытия ожидаемого дайджеста.
    """
    expected = document_digest(build_payment_document(payment, check))
    if not isinstance(client_digest, str) or not client_digest:
        raise DocumentMismatchError()
    if not hmac.compare_digest(client_digest.encode("utf-8"), expected.encode("utf-8")):
        raise DocumentMismatchError()


def derive_company_secret(
    company_id: str,
    master_secret: str | bytes | None = None,
) -> bytes:
    """Вычислить локальный HMAC-секрет компании для демонстрационной имитации подписи.

    ИМИТАЦИЯ ЭЦП, не NCALayer, не имеет юридической силы.
    Если ``master_secret`` не передан явно, берётся значение переменной окружения
    ``PROD_SIM_SIGN_SECRET`` или демонстрационный ключ по умолчанию.
    """
    if not isinstance(company_id, str) or not company_id.strip():
        raise ValueError("Идентификатор компании (company_id) должен быть непустой строкой.")

    resolved_secret = (
        master_secret
        if master_secret is not None
        else (os.getenv(SIMULATED_SECRET_ENV) or DEFAULT_DEMO_MASTER_SECRET)
    )
    key_bytes = (
        resolved_secret
        if isinstance(resolved_secret, bytes)
        else str(resolved_secret).encode("utf-8")
    )
    if not key_bytes:
        key_bytes = DEFAULT_DEMO_MASTER_SECRET.encode("utf-8")

    return hmac.new(
        key_bytes,
        f"company-sim-sign-v1:{company_id.strip()}".encode(),
        hashlib.sha256,
    ).digest()


class SimulatedSigner:
    """ИМИТАЦИЯ ЭЦП на основе HMAC-SHA256 с локальным секретом компании.

    ВНИМАНИЕ: это демонстрационная ИМИТАЦИЯ ЭЦП, не NCALayer и не квалифицированная
    электронная подпись НУЦ РК. Сформированная подпись НЕ имеет юридической силы
    и используется только для демонстрации привязки проверки к подписанию.
    """

    label: str = SIMULATED_LABEL

    def __init__(self, master_secret: str | bytes | None = None) -> None:
        self._master_secret = master_secret

    def sign(self, digest: str, company_id: str) -> str:
        """Вычислить демонстрационную HMAC-SHA256 подпись (hex) для digest и company_id."""
        if not isinstance(digest, str) or not digest:
            raise ValueError("Дайджест документа должен быть непустой строкой.")
        company_secret = derive_company_secret(company_id, self._master_secret)
        return hmac.new(
            company_secret,
            digest.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def verify(self, digest: str, signature: str, company_id: str) -> bool:
        """Проверить демонстрационную HMAC-SHA256 подпись через ``hmac.compare_digest``."""
        if (
            not isinstance(digest, str)
            or not digest
            or not isinstance(signature, str)
            or not signature
            or not isinstance(company_id, str)
            or not company_id.strip()
        ):
            return False
        expected = self.sign(digest, company_id)
        return hmac.compare_digest(signature.encode("utf-8"), expected.encode("utf-8"))


@runtime_checkable
class SignatureVerifier(Protocol):
    """Интерфейс серверного верификатора криптографических подписей."""

    def verify(
        self,
        document_digest: str,
        signature_cms_b64: str,
        company_id: str,
    ) -> VerifiedSignature:
        """Проверить CMS/PKCS#7 подпись и вернуть атрибуты подписавшего сертификата."""
        ...


class CmsSignatureVerifier:
    """Заглушка серверного верификатора ЭЦП НУЦ РК (CMS/PKCS#7, NCALayer).

    Как работает NCALayer на стороне клиента:
    - NCALayer — локальное настольное приложение НУЦ РК, слушающее локальный
      WebSocket-интерфейс ``wss://127.0.0.1:13579``.
    - Браузер отправляет JSON-запрос в стандартный модуль
      ``kz.gov.pki.knca.commonUtils`` (например, ``createCMSSignatureFromBase64``),
      передавая хэш/данные платёжного документа.
    - Выбор хранилища ключей (PKCS12, eToken, Kaztoken и др.) и ввод пароля
      выполняются исключительно в окне самого NCALayer; закрытый ключ и пароль
      никогда не передаются в веб-приложение или на сервер.
    - В ответ NCALayer возвращает подпись в формате CMS/PKCS#7 (Base64).

    Что обязательно нужно проверять на сервере в промышленной эксплуатации:
    1. Целостность криптографической подписи CMS/PKCS#7 (алгоритмы ГОСТ / RSA
       по стандартам НУЦ РК).
    2. Построение и валидация цепочки доверия до корневых и промежуточных
       сертификатов НУЦ РК / КУЦ РК.
    3. Срок действия сертификата (``notBefore`` / ``notAfter``) и метку времени
       подписания (TSP), если она требуется политикой банка.
    4. Статус отзыва сертификата по актуальным спискам CRL и/или через OCSP-сервис
       НУЦ РК.
    5. Строгое совпадение подписанных данных внутри CMS-контейнера с ожидаемым
       серверным ``document_digest`` (защита от подмены документа).
    6. Совпадение БИН/ИИН из атрибутов сертификата (Subject DN) с реквизитами
       компании (``company_id``) и проверку полномочий (роли) подписанта на право
       подписи платёжных документов.

    В демонстрационной версии серверная криптографическая проверка CMS/PKCS#7
    не реализована: вызов ``verify()`` намеренно бросает ``NotImplementedError``.
    """

    def verify(
        self,
        document_digest: str,
        signature_cms_b64: str,
        company_id: str,
    ) -> VerifiedSignature:
        """Проверка CMS/PKCS#7 подписи НУЦ РК не реализована в демо-режиме."""
        _ = (document_digest, signature_cms_b64, company_id)
        raise NotImplementedError(
            "Серверная проверка CMS/PKCS#7 подписи NCALayer (НУЦ РК) не реализована "
            "в демонстрационной версии: требуется криптопровайдер с проверкой цепочки "
            "НУЦ РК, CRL/OCSP и сопоставлением БИН/ИИН."
        )


def verify_signature(
    signer: str,
    document_digest: str,
    signature: str,
    company_id: str,
    *,
    verifier: SignatureVerifier | SimulatedSigner | None = None,
) -> SignatureVerificationResult:
    """Проверить подпись документа в зависимости от выбранного типа подписанта.

    - ``signer == "simulated"`` -> проверка через ``SimulatedSigner.verify``.
    - ``signer == "ncalayer"`` -> проверка через ``SignatureVerifier`` (по умолчанию
      ``CmsSignatureVerifier``, который пробрасывает ``NotImplementedError``).
    - Любое иное значение ``signer`` -> ``InvalidSignerError`` (HTTP 422).
    """
    if signer == "simulated":
        sim = verifier if isinstance(verifier, SimulatedSigner) else SimulatedSigner()
        is_valid = sim.verify(document_digest, signature, company_id)
        return SignatureVerificationResult(
            verified=is_valid,
            signer="simulated",
            label=SIMULATED_LABEL,
            simulated=True,
            details=None,
        )

    if signer == "ncalayer":
        cms_verifier: SignatureVerifier
        if verifier is not None and not isinstance(verifier, SimulatedSigner):
            cms_verifier = verifier
        else:
            cms_verifier = CmsSignatureVerifier()
        verified_sig = cms_verifier.verify(document_digest, signature, company_id)
        return SignatureVerificationResult(
            verified=True,
            signer="ncalayer",
            label=NCALAYER_LABEL,
            simulated=False,
            details=verified_sig,
        )

    raise InvalidSignerError(signer)
