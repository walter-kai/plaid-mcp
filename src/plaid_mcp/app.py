"""Unified FastAPI app: Plaid Link routes + Google-OAuth FastMCP at /mcp."""

from __future__ import annotations

import uvicorn
from fastapi import FastAPI

from plaid_mcp.auth_google import AllowedEmailMiddleware, build_google_auth
from plaid_mcp.config import get_settings
from plaid_mcp.routes import register_link_routes
from plaid_mcp.tools import create_mcp


def create_app() -> FastAPI:
    settings = get_settings()
    auth = build_google_auth()
    mcp = create_mcp(auth=auth)
    if settings.allowed_emails:
        mcp.add_middleware(AllowedEmailMiddleware(settings.allowed_emails))

    mcp_app = mcp.http_app(path="/", stateless_http=True)
    app = FastAPI(
        title="Plaid MCP",
        version="0.1.0",
        lifespan=mcp_app.lifespan,
    )
    register_link_routes(app)
    app.mount("/mcp", mcp_app)
    return app


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "plaid_mcp.app:create_app",
        factory=True,
        host=settings.web_host,
        port=settings.web_port,
        reload=False,
    )


if __name__ == "__main__":
    main()
