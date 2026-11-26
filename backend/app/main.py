"""FastAPI application for BCC Business Shield."""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.i18n import DEFAULT_LANG, Lang, field_label, resolve_lang, t
from app.risk.engine import check_payment, localize_check_result
from app.risk.evaluation import DEFAULT_EVAL_FILENAME, evaluate_dataset
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
    MetricsResponse,
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

_VALUE_ERROR_KEYS: dict[str, str] = {
    "Укажите название получателя.": "val.recipient_name_required",
    "Сумма платежа должна быть конечным числом.": "val.amount_finite",
}

_cached_metrics: MetricsResponse | None = None


def get_cached_metrics(*, lang: Lang = DEFAULT_LANG) -> MetricsResponse:
    """Return cached evaluation metrics, computing once on demand if not preloaded at startup."""
    global _cached_metrics
    if _cached_metrics is None:
        eval_path = store.data_dir / DEFAULT_EVAL_FILENAME
        if not eval_path.exists():
            raise HTTPException(
                status_code=503,
                detail=t("error.metrics_missing", lang),
            )
        _cached_metrics = evaluate_dataset(store.data_dir, eval_path=eval_path)
    return _cached_metrics


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Precompute and cache evaluation metrics at application startup."""
    eval_path = store.data_dir / DEFAULT_EVAL_FILENAME
    if eval_path.exists():
        get_cached_metrics()
    else:
        logger.warning("Evaluation dataset missing at startup: %s", eval_path)
    yield


app = FastAPI(
    title="BCC Business Shield API",
    description="Pre-signing SME supplier payment verification service.",
    version="0.1.0",
    lifespan=_lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=CORS_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _format_validation_message(err: dict[str, Any], lang: Lang) -> tuple[str, str]:
    """Translate a single FastAPI/Pydantic validation error into the requested language."""
    loc = [str(part) for part in err.get("loc", ()) if part not in ("body", "query", "path")]
    field_key = loc[-1] if loc else ""
    label = field_label(field_key, lang)
    err_type = str(err.get("type", ""))
    ctx = err.get("ctx") or {}
    raw_msg = str(err.get("msg", ""))

    if err_type == "json_invalid":
        return field_key or "body", t("val.json_invalid", lang)
    if err_type == "value_error":
        cleaned = raw_msg.removeprefix("Value error, ").strip()
        mapped_key = _VALUE_ERROR_KEYS.get(cleaned)
        if mapped_key is not None:
            return field_key, t(mapped_key, lang)
        return field_key, cleaned or t("val.value_error_fallback", lang)

    if err_type == "missing":
        msg = t("val.missing", lang)
    elif err_type == "greater_than":
        msg = t("val.greater_than", lang, gt=ctx.get("gt", 0))
    elif err_type == "less_than_equal":
        msg = t("val.less_than_equal", lang, le=ctx.get("le", ""))
    elif err_type == "finite_number":
        msg = t("val.finite_number", lang)
    elif err_type == "string_too_short":
        msg = t("val.string_too_short", lang, min_length=ctx.get("min_length", 1))
    elif err_type == "string_too_long":
        msg = t("val.string_too_long", lang, max_length=ctx.get("max_length", ""))
    elif err_type in ("float_parsing", "float_type", "int_parsing", "int_type"):
        msg = t("val.number_invalid", lang)
    elif err_type == "string_type":
        msg = t("val.string_type", lang)
    elif err_type == "bool_parsing":
        msg = t("val.bool_parsing", lang)
    elif err_type == "literal_error":
        msg = t("val.literal_error", lang, expected=ctx.get("expected", ""))
    else:
        msg = t("val.generic", lang)

    if label:
        return field_key, f"{label}: {msg}"
    return field_key, msg.capitalize()


@app.exception_handler(RequestValidationError)
async def _validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Return localized validation errors for HTTP 422 responses."""
    lang = resolve_lang(request.query_params.get("lang"))
    formatted: list[dict[str, str]] = []
    for err in exc.errors():
        field_key, message_ru = _format_validation_message(err, "ru")
        _, message = _format_validation_message(err, lang)
        formatted.append({"field": field_key, "message_ru": message_ru, "message": message})
    detail = (
        "; ".join(item["message"] for item in formatted) or t("error.validation_fallback", lang)
    )
    return JSONResponse(status_code=422, content={"detail": detail, "errors": formatted})


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return a plain-language localized error payload instead of raw 500 stack traces."""
    logger.exception("Unhandled error while processing %s %s", request.method, request.url.path)
    lang = resolve_lang(request.query_params.get("lang"))
    return JSONResponse(
        status_code=500,
        content={"detail": t("error.internal", lang)},
    )


def _resolve_request_payer(req: CheckRequest, *, lang: Lang = DEFAULT_LANG) -> CheckRequest:
    """Apply default client payer_id or reject unknown payer_id with HTTP 422."""
    if req.payer_id is None:
        return req.model_copy(update={"payer_id": store.default_payer_id})
    if not store.is_known_payer(req.payer_id):
        raise HTTPException(
            status_code=422,
            detail=t("error.unknown_payer", lang, payer_id=req.payer_id),
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


def _localize_approval(approval: Approval, lang: Lang) -> Approval:
    return approval.model_copy(update={"check": localize_check_result(approval.check, lang)})


LangQuery = Annotated[Lang, Query()]


@app.post("/api/payments/check", response_model=CheckResult)
def post_check_payment(
    payload: CheckRequest,
    lang: LangQuery = DEFAULT_LANG,
) -> CheckResult:
    """Verify supplier payment requisites before signing."""
    resolved = _resolve_request_payer(payload, lang=lang)
    return check_payment(resolved, store, lang=lang)


@app.get("/api/payments/queue", response_model=list[QueuePaymentItem])
def get_payments_queue(lang: LangQuery = DEFAULT_LANG) -> list[QueuePaymentItem]:
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
        result = check_payment(req, store, lang=lang)
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
def post_create_approval(
    payload: ApprovalCreateRequest,
    lang: LangQuery = DEFAULT_LANG,
) -> Approval:
    """Submit a payment for director approval, deduplicating pending requests."""
    resolved_req = _resolve_request_payer(payload.check_request, lang=lang)
    payer_id = resolved_req.payer_id or store.default_payer_id

    existing = store.find_pending_approval(
        payer_id=payer_id,
        recipient_bin=resolved_req.recipient_bin,
        recipient_iik=resolved_req.recipient_iik,
        amount_kzt=resolved_req.amount_kzt,
    )
    if existing is not None:
        return _localize_approval(existing, lang)

    result = check_payment(resolved_req, store, lang=lang)
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
    lang: LangQuery = DEFAULT_LANG,
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
        results.append(_localize_approval(item, lang))
    return results


@app.post("/api/approvals/{approval_id}/decision", response_model=Approval)
def post_approval_decision(
    approval_id: str,
    payload: ApprovalDecisionRequest,
    lang: LangQuery = DEFAULT_LANG,
) -> Approval:
    """Record the director's decision on a pending approval."""
    approval = store.get_approval(approval_id)
    if approval is None:
        raise HTTPException(status_code=404, detail=t("error.approval_not_found", lang))

    if approval.status != "pending":
        raise HTTPException(status_code=409, detail=t("error.approval_already_decided", lang))

    cleaned_comment = (
        clean_text_field(payload.director_comment) if payload.director_comment is not None else ""
    )
    comment_len = meaningful_length(cleaned_comment)

    if payload.decision == "approved":
        if approval.check.verdict == "invalid":
            raise HTTPException(
                status_code=422,
                detail=t("error.invalid_payment_cannot_approve", lang),
            )

        if payload.trust_account:
            if not _can_trust_approval(approval):
                raise HTTPException(
                    status_code=422,
                    detail=t("error.trust_not_allowed", lang),
                )
            if comment_len < MIN_DIRECTOR_COMMENT_LEN:
                raise HTTPException(
                    status_code=422,
                    detail=t("error.trust_comment_required", lang),
                )

        if approval.check.verdict == "red" and comment_len < MIN_DIRECTOR_COMMENT_LEN:
            raise HTTPException(
                status_code=422,
                detail=t("error.red_comment_required", lang),
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

    return _localize_approval(approval, lang)


@app.get("/api/metrics", response_model=MetricsResponse)
def get_metrics() -> MetricsResponse:
    """Return cached evaluation metrics over the labeled synthetic dataset."""
    return get_cached_metrics()


@app.post("/api/demo/reset", response_model=DemoResetResponse)
def post_demo_reset() -> DemoResetResponse:
    """Clear approvals and trusted accounts and reload synthetic JSON data."""
    store.reset()
    return DemoResetResponse(
        status="reset",
        approvals_count=len(store.approvals),
        trusted_accounts_count=len(store.trusted_accounts),
    )
