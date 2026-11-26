"""Payments API router (/api/v1/payments/*)."""

from __future__ import annotations

import sqlite3
from email.parser import BytesParser
from email.policy import default as email_default_policy
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Query, Request

from app.i18n import DEFAULT_LANG
from app.prod import payments_service
from app.prod.db import get_db
from app.prod.deps import LangQuery, get_app_settings, require_role
from app.prod.errors import ProdError
from app.prod.importers import MAX_IMPORT_BYTES
from app.prod.schemas import (
    Batch,
    BatchActionResult,
    BatchSendToDirectorRequest,
    BatchSignGreenRequest,
    ImportFormat,
    ImportResult,
    Payment,
    PaymentInput,
    PaymentList,
    PaymentNoteRequest,
    PaymentScope,
    PaymentStatus,
    SendToDirectorRequest,
    SignPaymentRequest,
    User,
)
from app.schemas import Verdict
from app.settings import Settings

router = APIRouter(prefix="/payments", tags=["payments"])
batches_router = APIRouter(prefix="/batches", tags=["batches"])


def _extract_multipart_file(content_type: str, raw_body: bytes) -> bytes:
    """Parse multipart/form-data file part via stdlib email.parser (no extra dependencies)."""
    mime_blob = f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode() + raw_body
    msg = BytesParser(policy=email_default_policy).parsebytes(mime_blob)
    if not msg.is_multipart():
        return raw_body
    for part in msg.iter_parts():
        if part.get_filename() is not None or part.get_param("name", header="content-disposition") == "file":
            payload = part.get_payload(decode=True)
            if isinstance(payload, bytes):
                return payload
    return b""


@router.post("/import", response_model=ImportResult, status_code=201)
async def import_payments_endpoint(
    request: Request,
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    user: Annotated[User, Depends(require_role("accountant"))],
    cfg: Annotated[Settings, Depends(get_app_settings)],
    filename: Annotated[str, Query(min_length=1, max_length=255)],
    file_format: Annotated[ImportFormat, Query(alias="format")] = "auto",
    force: Annotated[bool, Query()] = False,
    lang: LangQuery = DEFAULT_LANG,
) -> ImportResult:
    """Import a 1CClientBankExchange or CSV batch (raw bytes or multipart via stdlib)."""
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > MAX_IMPORT_BYTES and not (
                request.headers.get("content-type", "").lower().startswith("multipart/form-data")
            ):
                raise ProdError(413, "file_too_large")
        except ValueError:
            pass

    raw_body = await request.body()
    content_type = request.headers.get("content-type", "")
    if content_type.lower().startswith("multipart/form-data"):
        file_bytes = _extract_multipart_file(content_type, raw_body)
    else:
        file_bytes = raw_body

    return payments_service.import_payments_file(
        conn,
        user=user,
        data=file_bytes,
        filename=filename,
        file_format=file_format,
        force=force,
        today=cfg.today(),
        lang=lang,
    )


@router.post("/batch/sign-green", response_model=BatchActionResult)
def batch_sign_green_endpoint(
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    user: Annotated[User, Depends(require_role("accountant", "director"))],
    cfg: Annotated[Settings, Depends(get_app_settings)],
    payload: Annotated[BatchSignGreenRequest | None, Body()] = None,
    lang: LangQuery = DEFAULT_LANG,
) -> BatchActionResult:
    """Batch-sign only status='checked' payments whose fresh risk verdict is green."""
    batch_id = payload.batch_id if payload is not None else None
    payment_ids = payload.payment_ids if payload is not None else None
    return payments_service.batch_sign_green(
        conn,
        user=user,
        batch_id=batch_id,
        payment_ids=payment_ids,
        today=cfg.today(),
        lang=lang,
    )


@router.post("/batch/send-to-director", response_model=BatchActionResult)
def batch_send_to_director_endpoint(
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    user: Annotated[User, Depends(require_role("accountant"))],
    cfg: Annotated[Settings, Depends(get_app_settings)],
    payload: Annotated[BatchSendToDirectorRequest | None, Body()] = None,
    lang: LangQuery = DEFAULT_LANG,
) -> BatchActionResult:
    """Batch-submit yellow/red/grey checked payments for director approval."""
    batch_id = payload.batch_id if payload is not None else None
    payment_ids = payload.payment_ids if payload is not None else None
    note = payload.accountant_note if payload is not None else ""
    return payments_service.batch_send_to_director(
        conn,
        user=user,
        batch_id=batch_id,
        payment_ids=payment_ids,
        accountant_note=note,
        today=cfg.today(),
        lang=lang,
    )


@batches_router.get("", response_model=list[Batch])
def list_batches_endpoint(
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    user: Annotated[User, Depends(require_role("accountant", "director", "analyst"))],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    lang: LangQuery = DEFAULT_LANG,
) -> list[Batch]:
    """List recent import batches in the user's company scope, newest first."""
    _ = lang
    return payments_service.list_batches(conn, user=user, limit=limit)


@router.get("", response_model=PaymentList)
def list_payments_endpoint(
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    user: Annotated[User, Depends(require_role("accountant", "director", "analyst"))],
    cfg: Annotated[Settings, Depends(get_app_settings)],
    scope: Annotated[PaymentScope, Query()] = "queue",
    status: Annotated[PaymentStatus | None, Query()] = None,
    verdict: Annotated[Verdict | None, Query()] = None,
    batch_id: Annotated[str | None, Query()] = None,
    supplier_id: Annotated[int | None, Query()] = None,
    q: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
    lang: LangQuery = DEFAULT_LANG,
) -> PaymentList:
    """List payments in the requested scope with full-scope status and verdict counters."""
    return payments_service.list_payments(
        conn,
        user=user,
        today=cfg.today(),
        scope=scope,
        status=status,
        verdict=verdict,
        batch_id=batch_id,
        supplier_id=supplier_id,
        q=q,
        limit=limit,
        offset=offset,
        lang=lang,
    )


@router.post("", response_model=Payment, status_code=201)
def create_payment_endpoint(
    payload: PaymentInput,
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    user: Annotated[User, Depends(require_role("accountant"))],
    cfg: Annotated[Settings, Depends(get_app_settings)],
    lang: LangQuery = DEFAULT_LANG,
) -> Payment:
    """Create a manual payment, run risk verification, and return the saved Payment."""
    return payments_service.create_payment(
        conn,
        user=user,
        payload=payload,
        today=cfg.today(),
        lang=lang,
    )


@router.get("/{payment_id}", response_model=Payment)
def get_payment_endpoint(
    payment_id: str,
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    user: Annotated[User, Depends(require_role("accountant", "director", "analyst"))],
    cfg: Annotated[Settings, Depends(get_app_settings)],
    lang: LangQuery = DEFAULT_LANG,
) -> Payment:
    """Retrieve a single payment with localized check results and computed permissions."""
    return payments_service.get_payment(
        conn,
        payment_id=payment_id,
        user=user,
        today=cfg.today(),
        lang=lang,
    )


@router.put("/{payment_id}", response_model=Payment)
def edit_payment_endpoint(
    payment_id: str,
    payload: PaymentInput,
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    user: Annotated[User, Depends(require_role("accountant"))],
    cfg: Annotated[Settings, Depends(get_app_settings)],
    lang: LangQuery = DEFAULT_LANG,
) -> Payment:
    """Edit payment requisites, re-run verification, and reset acknowledgement."""
    return payments_service.edit_payment(
        conn,
        payment_id=payment_id,
        user=user,
        payload=payload,
        today=cfg.today(),
        lang=lang,
    )


@router.post("/{payment_id}/recheck", response_model=Payment)
def recheck_payment_endpoint(
    payment_id: str,
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    user: Annotated[User, Depends(require_role("accountant"))],
    cfg: Annotated[Settings, Depends(get_app_settings)],
    lang: LangQuery = DEFAULT_LANG,
) -> Payment:
    """Re-evaluate an editable payment against current history and trust state."""
    return payments_service.recheck_payment(
        conn,
        payment_id=payment_id,
        user=user,
        today=cfg.today(),
        lang=lang,
    )


@router.post("/{payment_id}/sign", response_model=Payment)
def sign_payment_endpoint(
    payment_id: str,
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    user: Annotated[User, Depends(require_role("accountant", "director"))],
    cfg: Annotated[Settings, Depends(get_app_settings)],
    payload: Annotated[SignPaymentRequest | None, Body()] = None,
    lang: LangQuery = DEFAULT_LANG,
) -> Payment:
    """Re-verify and sign a payment under server-side §5 risk policy enforcement."""
    ack = payload.accountant_ack if payload is not None else False
    return payments_service.sign_payment(
        conn,
        payment_id=payment_id,
        user=user,
        accountant_ack=ack,
        today=cfg.today(),
        lang=lang,
    )


@router.post("/{payment_id}/send-to-director", response_model=Payment)
def send_to_director_endpoint(
    payment_id: str,
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    user: Annotated[User, Depends(require_role("accountant"))],
    cfg: Annotated[Settings, Depends(get_app_settings)],
    payload: Annotated[SendToDirectorRequest | None, Body()] = None,
    lang: LangQuery = DEFAULT_LANG,
) -> Payment:
    """Submit a checked payment to the director for approval."""
    note = payload.accountant_note if payload is not None else ""
    return payments_service.send_to_director(
        conn,
        payment_id=payment_id,
        user=user,
        accountant_note=note,
        today=cfg.today(),
        lang=lang,
    )


@router.post("/{payment_id}/postpone", response_model=Payment)
def postpone_payment_endpoint(
    payment_id: str,
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    user: Annotated[User, Depends(require_role("accountant"))],
    cfg: Annotated[Settings, Depends(get_app_settings)],
    payload: Annotated[PaymentNoteRequest | None, Body()] = None,
    lang: LangQuery = DEFAULT_LANG,
) -> Payment:
    """Postpone a checked payment for later follow-up."""
    note = payload.note if payload is not None else ""
    return payments_service.postpone_payment(
        conn,
        payment_id=payment_id,
        user=user,
        note=note,
        today=cfg.today(),
        lang=lang,
    )


@router.post("/{payment_id}/resume", response_model=Payment)
def resume_payment_endpoint(
    payment_id: str,
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    user: Annotated[User, Depends(require_role("accountant"))],
    cfg: Annotated[Settings, Depends(get_app_settings)],
    lang: LangQuery = DEFAULT_LANG,
) -> Payment:
    """Return a postponed payment to checked status with a fresh risk check."""
    return payments_service.resume_payment(
        conn,
        payment_id=payment_id,
        user=user,
        today=cfg.today(),
        lang=lang,
    )


@router.post("/{payment_id}/cancel", response_model=Payment)
def cancel_payment_endpoint(
    payment_id: str,
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    user: Annotated[User, Depends(require_role("accountant"))],
    cfg: Annotated[Settings, Depends(get_app_settings)],
    payload: Annotated[PaymentNoteRequest | None, Body()] = None,
    lang: LangQuery = DEFAULT_LANG,
) -> Payment:
    """Cancel an active payment."""
    note = payload.note if payload is not None else ""
    return payments_service.cancel_payment(
        conn,
        payment_id=payment_id,
        user=user,
        note=note,
        today=cfg.today(),
        lang=lang,
    )
