"""Invoice extraction service: Claude when available, regex fallback otherwise.

Mount ``router`` in the FastAPI app: ``app.include_router(invoice_ai.service.router)``.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool

from app.invoice_ai import claude_extractor, text_parser
from app.invoice_ai.errors import ExtractorUnavailable, InvoiceFileError
from app.invoice_ai.models import InvoiceExtraction
from app.invoice_ai.validation import validate

NO_AI_NOTE = "ИИ-разбор недоступен ({reason}): использован разбор по шаблонам"


def extract_invoice(data: bytes, mime: str, filename: str = "") -> InvoiceExtraction:
    """Extract payment fields from an invoice file.

    Tries Claude first; falls back to the regex parser when Claude is unavailable. Always
    re-validates the result with the KZ validators. Raises InvoiceFileError for a bad file.
    """
    real_mime = claude_extractor.resolve_mime(data, mime, filename)

    result: InvoiceExtraction | None = None
    unavailable: ExtractorUnavailable | None = None
    try:
        result = claude_extractor.extract_with_claude(data, real_mime, filename)
    except ExtractorUnavailable as exc:
        unavailable = exc

    if result is None:
        result = text_parser.parse_document(data, real_mime)
        if unavailable is not None and not unavailable.quiet:
            result.warnings.append(NO_AI_NOTE.format(reason=unavailable))
    return validate(result)


router = APIRouter(prefix="/api/invoice", tags=["invoice"])


async def _read_limited(request: Request) -> bytes:
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > claude_extractor.MAX_FILE_BYTES:
        raise InvoiceFileError("Файл больше 10 МБ", 413)
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > claude_extractor.MAX_FILE_BYTES:
            raise InvoiceFileError("Файл больше 10 МБ", 413)
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/extract", response_model=InvoiceExtraction)
async def extract_endpoint(
    request: Request, filename: str = Query(default="", max_length=255)
) -> InvoiceExtraction:
    """Read the raw request body (Content-Type = file MIME) and return prefill fields."""
    try:
        data = await _read_limited(request)
        mime = request.headers.get("content-type", "")
        return await run_in_threadpool(extract_invoice, data, mime, filename)
    except InvoiceFileError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
