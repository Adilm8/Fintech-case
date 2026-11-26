"""FastAPI application for BCC Business Shield production mode (/api/v1/*)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.i18n import resolve_lang
from app.main import _unhandled_exception_handler, _validation_exception_handler
from app.prod.db import connect, migrate
from app.prod.deps import require_csrf_header
from app.prod.errors import ProdError, localize_prod_error
from app.prod.routers import approvals as approvals_router
from app.prod.routers import audit as audit_router
from app.prod.routers import auth as auth_router
from app.prod.routers import meta as meta_router
from app.prod.routers import payments as payments_router
from app.prod.routers import suppliers as suppliers_router
from app.prod.security import LoginRateLimiter
from app.settings import Settings, load_settings


def create_prod_app(
    *,
    db_path: Path | str | None = None,
    settings_override: Settings | None = None,
) -> FastAPI:
    """Build and configure a production-mode FastAPI instance."""
    cfg = settings_override if settings_override is not None else load_settings()
    resolved_db_path: Path | str = db_path if db_path is not None else cfg.db_path

    @asynccontextmanager
    async def _lifespan(prod_app: FastAPI) -> AsyncIterator[None]:
        conn = connect(prod_app.state.db_path)
        try:
            migrate(conn)
        finally:
            conn.close()
        yield

    prod_app = FastAPI(
        title="BCC Business Shield API (Prod)",
        description="Production-mode pre-signing SME supplier payment verification service.",
        version="0.1.0",
        lifespan=_lifespan,
    )
    prod_app.state.db_path = resolved_db_path
    prod_app.state.settings = cfg
    prod_app.state.login_limiter = LoginRateLimiter()

    @prod_app.exception_handler(ProdError)
    async def _prod_error_handler(request: Request, exc: ProdError) -> JSONResponse:
        lang = resolve_lang(request.query_params.get("lang"))
        return JSONResponse(status_code=exc.status_code, content=exc.to_payload(lang))

    @prod_app.exception_handler(RequestValidationError)
    async def _prod_validation_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        base_resp = await _validation_exception_handler(request, exc)
        body = json.loads(bytes(base_resp.body).decode("utf-8"))
        body["code"] = "validation_error"
        return JSONResponse(status_code=base_resp.status_code, content=body)

    @prod_app.exception_handler(StarletteHTTPException)
    async def _prod_http_exception_handler(
        request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        lang = resolve_lang(request.query_params.get("lang"))
        if exc.status_code == 404:
            return JSONResponse(
                status_code=404,
                content={
                    "detail": localize_prod_error("not_found", lang),
                    "code": "not_found",
                },
            )
        if isinstance(exc.detail, dict) and "code" in exc.detail:
            return JSONResponse(status_code=exc.status_code, content=exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": str(exc.detail), "code": f"http_{exc.status_code}"},
        )

    @prod_app.exception_handler(Exception)
    async def _prod_unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        base_resp = await _unhandled_exception_handler(request, exc)
        body = json.loads(bytes(base_resp.body).decode("utf-8"))
        body["code"] = "internal_error"
        return JSONResponse(status_code=base_resp.status_code, content=body)

    api_v1 = APIRouter(prefix="/api/v1", dependencies=[Depends(require_csrf_header)])
    api_v1.include_router(meta_router.router)
    api_v1.include_router(auth_router.router)
    api_v1.include_router(payments_router.router)
    api_v1.include_router(payments_router.batches_router)
    api_v1.include_router(approvals_router.router)
    api_v1.include_router(suppliers_router.router)
    api_v1.include_router(audit_router.router)
    api_v1.include_router(audit_router.metrics_router)
    prod_app.include_router(api_v1)

    return prod_app


app: FastAPI = create_prod_app()
