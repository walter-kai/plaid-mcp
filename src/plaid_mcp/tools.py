"""Shared FastMCP tool registration for stdio and HTTP servers."""

from __future__ import annotations

import uuid
from typing import Any

from fastmcp import FastMCP

from plaid_mcp import plaid_client, store

INSTRUCTIONS = (
    "Connect a real bank via Hosted Link, then sync transactions. "
    "Always ask whether the bank is in the US or Canada before linking. "
    "Use create_link_session with country='CA' for Canadian banks, "
    "country='US' for US banks, or country='both' to show both. "
    "Flow: create_link_session → user opens hosted_link_url → list_items → "
    "transactions_sync (optionally accounts_get)."
)


def create_mcp(*, auth: Any = None) -> FastMCP:
    """Build a FastMCP instance with Plaid tools (optional Google OAuth auth)."""
    mcp = FastMCP(
        name="plaid-transactions",
        instructions=INSTRUCTIONS,
        auth=auth,
    )
    register_tools(mcp)
    return mcp


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    def create_link_session(
        country: str = "both",
        label: str | None = None,
        client_user_id: str | None = None,
        countries: list[str] | None = None,
    ) -> dict[str, Any]:
        """Start a Plaid Hosted Link session for Transactions.

        Args:
            country: Which banks to show. Use "CA" for Canada-only (RBC, TD, etc.),
                "US" for United States-only, or "both" for US + Canada.
            label: Optional label stored with the Item after Link completes.
            client_user_id: Optional stable user id; a random one is generated if omitted.
            countries: Optional explicit list like ["CA"] or ["US","CA"]. Overrides
                ``country`` when provided.

        Returns a hosted_link_url the user must open in a browser to connect a bank.
        After they finish, the webhook stores an access_token; call list_items next.
        """
        user_id = client_user_id or f"user-{uuid.uuid4()}"
        session = plaid_client.create_hosted_link_session(
            client_user_id=user_id,
            label=label,
            countries=countries,
            country=None if countries else country,
        )
        link_token = session.get("link_token")
        if link_token:
            store.remember_pending_link(
                link_token=link_token,
                client_user_id=user_id,
                label=label,
            )
        result = {
            "hosted_link_url": session.get("hosted_link_url"),
            "link_token": link_token,
            "expiration": session.get("expiration"),
            "client_user_id": user_id,
            "label": label,
            "countries": session.get("countries"),
            "env": session.get("env"),
            "next_step": (
                "Open hosted_link_url in a browser. When finished, call list_items, "
                "then transactions_sync with the new item_id."
            ),
        }
        if session.get("canada_note"):
            result["canada_note"] = session["canada_note"]
        return result

    @mcp.tool
    def list_items() -> dict[str, Any]:
        """List stored Plaid Items (access tokens) available for transaction sync."""
        items = store.list_items()
        return {"items": items, "count": len(items)}

    @mcp.tool
    def accounts_get(
        item_id: str | None = None,
        access_token: str | None = None,
    ) -> dict[str, Any]:
        """Fetch accounts for a stored item_id or a raw access_token."""
        token = store.get_access_token(item_id=item_id, access_token=access_token)
        return plaid_client.accounts_get(token)

    @mcp.tool
    def transactions_sync(
        item_id: str | None = None,
        access_token: str | None = None,
        cursor: str | None = None,
        count: int = 500,
    ) -> dict[str, Any]:
        """Sync transactions via /transactions/sync with server-side pagination.

        Omit cursor for the first pull. Pass next_cursor from a previous response
        for incremental updates. First sync after Link may return empty pages until
        Plaid finishes preparing data — retry after a short wait.
        """
        token = store.get_access_token(item_id=item_id, access_token=access_token)
        result = plaid_client.transactions_sync_all(
            token,
            cursor=cursor,
            count=min(max(count, 1), 500),
        )
        if item_id:
            result["item_id"] = item_id
        return result
