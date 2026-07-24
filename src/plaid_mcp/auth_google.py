"""Google OAuth (Firebase/GCP) provider for the HTTP MCP server."""

from __future__ import annotations

import logging
from typing import Any

from fastmcp.server.auth.providers.google import GoogleProvider
from fastmcp.server.dependencies import get_access_token
from fastmcp.server.middleware import Middleware, MiddlewareContext

from plaid_mcp.config import get_settings

logger = logging.getLogger(__name__)


def build_google_auth() -> GoogleProvider:
    """Create FastMCP GoogleProvider from env (local-friendly defaults)."""
    settings = get_settings()
    if not settings.google_oauth_client_id or not settings.google_oauth_client_secret:
        raise ValueError(
            "Set GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET for HTTP OAuth. "
            "Create a Web OAuth client in Google Cloud Console (same project as Firebase) "
            "with redirect URI {base}/auth/callback".format(
                base=settings.public_base_url.rstrip("/")
            )
        )

    kwargs: dict[str, Any] = {
        "client_id": settings.google_oauth_client_id,
        "client_secret": settings.google_oauth_client_secret,
        "base_url": settings.public_base_url.rstrip("/"),
        "required_scopes": [
            "openid",
            "https://www.googleapis.com/auth/userinfo.email",
            "https://www.googleapis.com/auth/userinfo.profile",
        ],
        # Local single-process: in-memory client_storage is fine.
        "require_authorization_consent": False,
    }
    if settings.jwt_signing_key:
        kwargs["jwt_signing_key"] = settings.jwt_signing_key

    return GoogleProvider(**kwargs)


class AllowedEmailMiddleware(Middleware):
    """Reject authenticated callers whose email is not in ALLOWED_EMAILS."""

    def __init__(self, allowed_emails: frozenset[str]) -> None:
        super().__init__()
        self._allowed = {email.lower() for email in allowed_emails}

    async def on_call_tool(self, context: MiddlewareContext, call_next):  # type: ignore[no-untyped-def]
        if self._allowed:
            token = get_access_token()
            claims = getattr(token, "claims", None) or {}
            email = (claims.get("email") or claims.get("user_email") or "").strip().lower()
            if not email or email not in self._allowed:
                raise PermissionError(
                    f"Google account {email or '(unknown)'} is not in ALLOWED_EMAILS"
                )
        return await call_next(context)

    async def on_list_tools(self, context: MiddlewareContext, call_next):  # type: ignore[no-untyped-def]
        # Allow listing tools once authenticated; email gate applies to tool calls.
        return await call_next(context)
