"""HTTP apps: ``api`` (private), ``link`` (public callbacks), or ``all`` (local)."""

from __future__ import annotations

import os
import secrets
from typing import Literal

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from plaid_mcp.api import router as api_router
from plaid_mcp.config import get_settings
from plaid_mcp.routes import register_link_routes

AppMode = Literal["api", "link", "all"]


def resolve_mode() -> AppMode:
    raw = os.getenv("PLAID_APP_MODE", "all").strip().lower()
    if raw not in ("api", "link", "all"):
        raise ValueError(
            f"PLAID_APP_MODE must be api|link|all; got {raw!r}"
        )
    return raw  # type: ignore[return-value]


class ServiceKeyMiddleware(BaseHTTPMiddleware):
    """Optional app-level key for /api/* (defense in depth under Cloud Run IAM).

    Accepts:
      Authorization: Bearer <PLAID_SERVICE_KEY>
      X-Plaid-Service-Key: <key>

    Skipped when PLAID_SERVICE_KEY is unset (IAM-only or local open API).
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path == "/api" or path.startswith("/api/"):
            settings = get_settings()
            expected = settings.service_key
            if expected:
                provided = _extract_service_key(request)
                if not _keys_match(provided, expected):
                    return JSONResponse(
                        {
                            "error": "unauthorized",
                            "detail": (
                                "Missing or invalid service key. "
                                "Send Authorization: Bearer <PLAID_SERVICE_KEY> "
                                "or X-Plaid-Service-Key."
                            ),
                        },
                        status_code=401,
                    )
        return await call_next(request)


def _keys_match(provided: str | None, expected: str) -> bool:
    if not provided:
        return False
    if len(provided) != len(expected):
        return False
    return secrets.compare_digest(provided, expected)


def _extract_service_key(request: Request) -> str | None:
    # Prefer dedicated header so Authorization can carry a Cloud Run ID token.
    header_key = request.headers.get("x-plaid-service-key", "").strip()
    if header_key:
        return header_key
    auth = request.headers.get("authorization", "").strip()
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
        # Google ID tokens are JWTs (header.payload.sig). Do not treat as service key.
        if token.count(".") == 2:
            return None
        return token
    return None


def create_app(mode: AppMode | None = None) -> FastAPI:
    mode = mode or resolve_mode()
    app = FastAPI(
        title=f"Plaid service ({mode})",
        version="0.3.0",
        description=(
            "Plaid backend for spearfresh-ui. "
            "mode=api: private REST. mode=link: public Hosted Link callbacks. "
            "mode=all: both (local/dev)."
        ),
    )

    @app.get("/health")
    def health():
        settings = get_settings()
        return {
            "ok": True,
            "mode": mode,
            "env": settings.env,
            "redirect_uri": settings.redirect_uri,
            "completion_uri": settings.completion_uri,
            "webhook_uri": settings.webhook_uri,
            "items_backend": "gcs" if settings.items_gcs_uri else "local",
            "api_auth": bool(settings.service_key),
        }

    if mode in ("link", "all"):
        register_link_routes(app, include_health=False)

    if mode in ("api", "all"):
        app.include_router(api_router)
        app.add_middleware(ServiceKeyMiddleware)

    return app


# Default ASGI target for uvicorn / Cloud Run.
app = create_app()


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "plaid_mcp.app:app",
        host=settings.web_host,
        port=settings.web_port,
        reload=False,
    )


if __name__ == "__main__":
    main()
