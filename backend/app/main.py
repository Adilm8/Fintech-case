"""FastAPI application for BCC Business Shield."""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.audit import append_audit_entry, read_audit_entries
from app.explain import router as explain_router
from app.i18n import DEFAULT_LANG, Lang, field_label, resolve_lang, t
from app.invoice_ai.env import load_env_file
from app.invoice_ai.service import router as invoice_router
from app.risk.config import (
    ANALYST_ROLE_VALUE,
    can_trust_check,
)
from app.risk.config import (
    TRUST_ALLOWED_SIGNAL_IDS as _TRUST_ALLOWED_SIGNAL_IDS,
)
from app.risk.engine import check_payment, localize_check_result
from app.risk.evaluation import DEFAULT_EVAL_FILENAME, evaluate_dataset, localize_metrics
from app.schemas import (
    Approval,
    ApprovalCreateRequest,
    ApprovalDecisionRequest,
    AuditEntry,
    CheckRequest,
    CheckResult,
    ClientInfo,
    DemoResetResponse,
    HistoryPaymentItem,
    HistoryResponse,
    MetricsResponse,
    QueuePaymentItem,
    clean_text_field,
    compute_request_sha256,
    meaningful_length,
    normalize_requisite,
)
from app.store import demo_now_iso, store

logger = logging.getLogger(__name__)

CORS_ORIGIN_REGEX: str = (
    r"https?://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+)(:\d+)?"
)

MIN_DIRECTOR_COMMENT_LEN: int = 10
TRUST_ALLOWED_SIGNAL_IDS: frozenset[str] = _TRUST_ALLOWED_SIGNAL_IDS

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

load_env_file()
app.include_router(invoice_router)
app.include_router(explain_router)

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
    detail = "; ".join(item["message"] for item in formatted) or t(
        "error.validation_fallback", lang
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
    return can_trust_check(approval.check.verdict, approval.check.signals)


def _is_analyst_role(x_role: str | None) -> bool:
    """Return True only when request explicitly carries X-Role: analyst."""
    return (x_role or "").strip().lower() == ANALYST_ROLE_VALUE


def _localize_approval(
    approval: Approval,
    lang: Lang,
    *,
    include_analyst_details: bool = False,
) -> Approval:
    return approval.model_copy(
        update={
            "check": localize_check_result(
                approval.check,
                lang,
                include_analyst_details=include_analyst_details,
            )
        }
    )


LangQuery = Annotated[Lang, Query()]
RoleHeader = Annotated[str | None, Header(alias="X-Role")]


@app.post("/api/payments/check", response_model=CheckResult)
def post_check_payment(
    payload: CheckRequest,
    lang: LangQuery = DEFAULT_LANG,
    x_role: RoleHeader = None,
    commit: Annotated[bool, Query()] = False,
) -> CheckResult:
    """Verify supplier payment requisites before signing.

    Checks are dry runs by default: drafts, edits and attack-console probes are
    not remembered. Only `commit=true` (an intent to pay) feeds short-term memory
    used by the duplicate-invoice, structuring and accumulation rules.
    """
    resolved = _resolve_request_payer(payload, lang=lang)
    result = check_payment(
        resolved,
        store,
        lang=lang,
        include_analyst_details=_is_analyst_role(x_role),
        record_in_memory=commit,
    )
    append_audit_entry(
        store.audit_log_path,
        AuditEntry(
            timestamp=demo_now_iso(),
            check_id=result.check_id,
            request_sha256=compute_request_sha256(
                resolved,
                resolved_payer_id=store.resolve_payer_id(resolved.payer_id),
            ),
            ruleset_version=result.ruleset_version,
            verdict=result.verdict,
            signal_ids=[s.rule_id for s in result.signals],
            action="check",
        ),
    )
    return result


@app.get("/api/payments/queue", response_model=list[QueuePaymentItem])
def get_payments_queue(
    lang: LangQuery = DEFAULT_LANG,
    x_role: RoleHeader = None,
) -> list[QueuePaymentItem]:
    """Return payments awaiting signature with their computed risk verdicts."""
    include_analyst = _is_analyst_role(x_role)
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
            kbe=raw.get("kbe", ""),
            knp=raw.get("knp", ""),
        )
        result = check_payment(
            req,
            store,
            lang=lang,
            include_analyst_details=include_analyst,
            include_recent_memory=False,
        )
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
    x_role: RoleHeader = None,
) -> Approval:
    """Submit a payment for director approval, deduplicating pending requests."""
    resolved_req = _resolve_request_payer(payload.check_request, lang=lang)
    payer_id = resolved_req.payer_id or store.default_payer_id
    include_analyst = _is_analyst_role(x_role)

    existing = store.find_pending_approval(
        payer_id=payer_id,
        recipient_bin=resolved_req.recipient_bin,
        recipient_iik=resolved_req.recipient_iik,
        amount_kzt=resolved_req.amount_kzt,
    )
    if existing is not None:
        return _localize_approval(existing, lang, include_analyst_details=include_analyst)

    # Clear any just-checked draft of this exact payment before evaluating for approval
    store.clear_recent_draft(
        payer_id=payer_id,
        recipient_bin=resolved_req.recipient_bin,
        recipient_iik=resolved_req.recipient_iik,
        amount_kzt=resolved_req.amount_kzt,
    )
    # Always store client-safe CheckResult (analyst_details=None) in shared in-memory state.
    result = check_payment(resolved_req, store, lang=lang, include_analyst_details=False)
    approval = Approval(
        id=f"apr-{uuid.uuid4().hex[:10]}",
        request=resolved_req,
        check=result,
        status="pending",
        accountant_note=clean_text_field(payload.accountant_note),
    )
    store.approvals.append(approval)
    return _localize_approval(approval, lang, include_analyst_details=include_analyst)


@app.get("/api/approvals", response_model=list[Approval])
def get_approvals(
    bin: str | None = Query(default=None),
    iik: str | None = Query(default=None),
    lang: LangQuery = DEFAULT_LANG,
    x_role: RoleHeader = None,
) -> list[Approval]:
    """List submitted director approvals with optional BIN and IIK filters."""
    clean_bin = normalize_requisite(bin) if bin is not None else ""
    clean_iik = normalize_requisite(iik) if iik is not None else ""
    include_analyst = _is_analyst_role(x_role)

    results: list[Approval] = []
    for item in store.approvals:
        if clean_bin and item.request.recipient_bin != clean_bin:
            continue
        if clean_iik and item.request.recipient_iik != clean_iik:
            continue
        results.append(_localize_approval(item, lang, include_analyst_details=include_analyst))
    return results


@app.post("/api/approvals/{approval_id}/decision", response_model=Approval)
def post_approval_decision(
    approval_id: str,
    payload: ApprovalDecisionRequest,
    lang: LangQuery = DEFAULT_LANG,
    x_role: RoleHeader = None,
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

    store.clear_recent_draft(
        payer_id=approval.request.payer_id,
        recipient_bin=approval.request.recipient_bin,
        recipient_iik=approval.request.recipient_iik,
        amount_kzt=approval.request.amount_kzt,
    )
    action_label = f"decision:{payload.decision}" + ("_trusted" if approval.trust_account else "")
    append_audit_entry(
        store.audit_log_path,
        AuditEntry(
            timestamp=decided_at,
            check_id=approval.check.check_id,
            request_sha256=compute_request_sha256(
                approval.request,
                resolved_payer_id=store.resolve_payer_id(approval.request.payer_id),
            ),
            ruleset_version=approval.check.ruleset_version,
            verdict=approval.check.verdict,
            signal_ids=[s.rule_id for s in approval.check.signals],
            action=action_label,
            approval_id=approval.id,
        ),
    )

    return _localize_approval(
        approval,
        lang,
        include_analyst_details=_is_analyst_role(x_role),
    )


@app.get("/api/audit", response_model=list[AuditEntry])
def get_audit_log(limit: int = Query(default=100, ge=1, le=1000)) -> list[AuditEntry]:
    """Return the latest privacy-preserving audit entries (hash & rule IDs only)."""
    return read_audit_entries(store.audit_log_path, limit=limit)


@app.get("/api/metrics", response_model=MetricsResponse)
def get_metrics(lang: LangQuery = DEFAULT_LANG) -> MetricsResponse:
    """Return cached evaluation metrics and chronological history replay."""
    return localize_metrics(get_cached_metrics(lang=lang), lang)


@app.post("/api/demo/reset", response_model=DemoResetResponse)
def post_demo_reset() -> DemoResetResponse:
    """Clear approvals and trusted accounts and reload synthetic JSON data."""
    store.reset()
    return DemoResetResponse(
        status="reset",
        approvals_count=len(store.approvals),
        trusted_accounts_count=len(store.trusted_accounts),
    )
