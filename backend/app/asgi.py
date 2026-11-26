"""ASGI entrypoint selecting demo or prod FastAPI application via APP_MODE."""

from __future__ import annotations

from fastapi import FastAPI

from app.settings import Settings, load_settings


def select_app(cfg: Settings | None = None) -> FastAPI:
    """Return the FastAPI application matching APP_MODE ('demo' or 'prod')."""
    resolved = cfg if cfg is not None else load_settings()
    if resolved.app_mode == "prod":
        from app.prod.app import app as prod_app

        return prod_app
    from app.main import app as demo_app

    return demo_app


app: FastAPI = select_app()
