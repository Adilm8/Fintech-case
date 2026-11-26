"""FastAPI application for BCC Business Shield."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.risk.engine import check_payment
from app.schemas import (
    Approval,
    ApprovalCreateRequest,
    ApprovalDecisionRequest,
    CheckRequest,
    CheckResult,
    ClientInfo,
    DemoResetResponse,
    HistoryPaymentItem,
    HistoryResponse,
    QueuePaymentItem,
    clean_text_field,
    meaningful_length,
    normalize_requisite,
)
from app.store import demo_now_iso, store

logger = logging.getLogger(__name__)

CORS_ORIGIN_REGEX: str = (
    r"https?://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+)(:\d+)?"
)

MIN_DIRECTOR_COMMENT_LEN: int = 10
TRUST_ALLOWED_SIGNAL_IDS: frozenset[str] = frozenset({"iik_changed", "bank_changed"})

_FIELD_LABELS_RU: dict[str, str] = {
    "payer_id": "Плательщик",
    "recipient_name": "Название получателя",
    "recipient_bin": "БИН/ИИН получателя",
    "recipient_iik": "ИИК получателя",
    "recipient_bik": "БИК банка",
    "amount_kzt": "Сумма платежа",
    "purpose": "Назначение платежа",
    "accountant_note": "Комментарий бухгалтера",
    "director_comment": "Комментарий директора",
    "decision": "Решение директора",
    "trust_account": "Доверие счёту",
    "check_request": "Данные платежа",
}

app = FastAPI(
    title="BCC Business Shield API",
    description="Pre-signing SME supplier payment verification service.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=CORS_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _translate_validation_error(err: dict[str, Any]) -> tuple[str, str]:
    """Translate a single FastAPI/Pydantic validation error into plain Russian."""
    loc = [str(part) for part in err.get("loc", ()) if part not in ("body", "query", "path")]
    field_key = loc[-1] if loc else ""
    field_label = _FIELD_LABELS_RU.get(field_key, field_key)
    err_type = str(err.get("type", ""))
    ctx = err.get("ctx") or {}
    raw_msg = str(err.get("msg", ""))

    if err_type == "json_invalid":
        return field_key or "body", "Некорректный формат JSON в теле запроса."
    if err_type == "missing":
        msg = "обязательное поле не заполнено."
    elif err_type == "greater_than":
        msg = f"значение должно быть больше {ctx.get('gt', 0)}."
    elif err_type == "less_than_equal":
        msg = f"значение не должно превышать {ctx.get('le', '')}."
    elif err_type == "finite_number":
        msg = "значение должно быть конечным числом (без NaN и бесконечности)."
    elif err_type == "string_too_short":
        msg = f"длина должна быть не менее {ctx.get('min_length', 1)} симв."
    elif err_type == "string_too_long":
        msg = f"длина не должна превышать {ctx.get('max_length', '')} симв."
    elif err_type in ("float_parsing", "float_type", "int_parsing", "int_type"):
        msg = "укажите корректное число."
    elif err_type == "string_type":
        msg = "значение должно быть строкой."
    elif err_type == "bool_parsing":
        msg = "значение должно быть логическим (true/false)."
    elif err_type == "literal_error":
        expected = ctx.get("expected", "")
        msg = f"недопустимое значение (ожидается: {expected})."
    elif err_type == "value_error":
        cleaned = raw_msg.removeprefix("Value error, ").strip()
        return field_key, cleaned or "Некорректное значение поля."
    else:
        msg = "некорректное значение."

    if field_label:
        return field_key, f"{field_label}: {msg}"
    return field_key, msg.capitalize()


@app.exception_handler(RequestValidationError)
async def _validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Return Russian validation errors for HTTP 422 responses."""
    formatted: list[dict[str, str]] = []
    for err in exc.errors():
        field_key, message_ru = _translate_validation_error(err)
        formatted.append({"field": field_key, "message_ru": message_ru})
    detail = (
        "; ".join(item["message_ru"] for item in formatted) or "Ошибка проверки данных запроса."
    )
    return JSONResponse(status_code=422, content={"detail": detail, "errors": formatted})


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return a plain Russian error payload instead of raw 500 stack traces."""
    logger.exception("Unhandled error while processing %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Внутренняя ошибка сервиса. Попробуйте повторить запрос позже."},
    )


def _resolve_request_payer(req: CheckRequest) -> CheckRequest:
    """Apply default client payer_id or reject unknown payer_id with HTTP 422."""
    if req.payer_id is None:
        return req.model_copy(update={"payer_id": store.default_payer_id})
    if not store.is_known_payer(req.payer_id):
        raise HTTPException(
            status_code=422,
            detail=f"Неизвестный плательщик: {req.payer_id}.",
        )
    return req


def _can_trust_approval(approval: Approval) -> bool:
    """Return True if an approval is eligible for director account trust."""
    if approval.check.verdict != "yellow":
        return False
    signals = approval.check.signals
    has_account_change = any(s.rule_id in TRUST_ALLOWED_SIGNAL_IDS for s in signals)
    has_block = any(s.severity == "block" for s in signals)
    return has_account_change and not has_block


@app.post("/api/payments/check", response_model=CheckResult)
def post_check_payment(payload: CheckRequest) -> CheckResult:
    """Verify supplier payment requisites before signing."""
    resolved = _resolve_request_payer(payload)
    return check_payment(resolved, store)


@app.get("/api/payments/queue", response_model=list[QueuePaymentItem])
def get_payments_queue() -> list[QueuePaymentItem]:
    """Return payments awaiting signature with their computed risk verdicts."""
    items: list[QueuePaymentItem] = []
    for raw in store.queue:
        req = CheckRequest(
            payer_id=raw.get("payer_id"),
            recipient_name=raw["recipient_name"],
            recipient_bin=raw["recipient_bin"],
            recipient_iik=raw["recipient_iik"],
            recipient_bik=raw["recipient_bik"],
            amount_kzt=raw["amount_kzt"],
            purpose=raw.get("purpose", ""),
        )
        result = check_payment(req, store)
        items.append(QueuePaymentItem(**raw, check=result))
    return items


@app.get("/api/history", response_model=HistoryResponse)
def get_history() -> HistoryResponse:
    """Return client profile and payment history."""
    return HistoryResponse(
        client=ClientInfo(**store.client),
        payments=[HistoryPaymentItem(**p) for p in store.history],
    )


@app.post("/api/approvals", response_model=Approval)
def post_create_approval(payload: ApprovalCreateRequest) -> Approval:
    """Submit a payment for director approval, deduplicating pending requests."""
    resolved_req = _resolve_request_payer(payload.check_request)
    payer_id = resolved_req.payer_id or store.default_payer_id

    existing = store.find_pending_approval(
        payer_id=payer_id,
        recipient_bin=resolved_req.recipient_bin,
        recipient_iik=resolved_req.recipient_iik,
        amount_kzt=resolved_req.amount_kzt,
    )
    if existing is not None:
        return existing

    result = check_payment(resolved_req, store)
    approval = Approval(
        id=f"apr-{uuid.uuid4().hex[:10]}",
        request=resolved_req,
        check=result,
        status="pending",
        accountant_note=clean_text_field(payload.accountant_note),
    )
    store.approvals.append(approval)
    return approval


@app.get("/api/approvals", response_model=list[Approval])
def get_approvals(
    bin: str | None = Query(default=None),
    iik: str | None = Query(default=None),
) -> list[Approval]:
    """List submitted director approvals with optional BIN and IIK filters."""
    clean_bin = normalize_requisite(bin) if bin is not None else ""
    clean_iik = normalize_requisite(iik) if iik is not None else ""

    results: list[Approval] = []
    for item in store.approvals:
        if clean_bin and item.request.recipient_bin != clean_bin:
            continue
        if clean_iik and item.request.recipient_iik != clean_iik:
            continue
        results.append(item)
    return results


@app.post("/api/approvals/{approval_id}/decision", response_model=Approval)
def post_approval_decision(
    approval_id: str,
    payload: ApprovalDecisionRequest,
) -> Approval:
    """Record the director's decision on a pending approval."""
    approval = store.get_approval(approval_id)
    if approval is None:
        raise HTTPException(status_code=404, detail="Заявка на согласование не найдена.")

    if approval.status != "pending":
        raise HTTPException(status_code=409, detail="Решение по этой заявке уже принято.")

    cleaned_comment = (
        clean_text_field(payload.director_comment) if payload.director_comment is not None else ""
    )
    comment_len = meaningful_length(cleaned_comment)

    if payload.decision == "approved":
        if approval.check.verdict == "invalid":
            raise HTTPException(
                status_code=422,
                detail="Платёж с ошибкой в реквизитах нельзя одобрить.",
            )

        if payload.trust_account:
            if not _can_trust_approval(approval):
                raise HTTPException(
                    status_code=422,
                    detail="Доверие недоступно для этого платежа",
                )
            if comment_len < MIN_DIRECTOR_COMMENT_LEN:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "Для добавления счёта в доверенные обязателен комментарий директора "
                        "(не менее 10 символов)."
                    ),
                )

        if approval.check.verdict == "red" and comment_len < MIN_DIRECTOR_COMMENT_LEN:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Для одобрения платежа с красным вердиктом обязателен комментарий директора "
                    "(не менее 10 символов)."
                ),
            )

    decided_at = demo_now_iso()
    approval.status = payload.decision
    if cleaned_comment:
        approval.director_comment = cleaned_comment
    approval.decided_at = decided_at

    if payload.decision == "approved" and payload.trust_account:
        approval.trust_account = True
        store.trust_account(
            approval.request.recipient_bin,
            approval.request.recipient_iik,
            payer_id=approval.request.payer_id,
            decided_at=decided_at,
            director_comment=cleaned_comment,
        )
    else:
        approval.trust_account = False

    return approval


@app.post("/api/demo/reset", response_model=DemoResetResponse)
def post_demo_reset() -> DemoResetResponse:
    """Clear approvals and trusted accounts and reload synthetic JSON data."""
    store.reset()
    return DemoResetResponse(
        status="reset",
        approvals_count=len(store.approvals),
        trusted_accounts_count=len(store.trusted_accounts),
    )
