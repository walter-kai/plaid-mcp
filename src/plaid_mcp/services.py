"""Shared Plaid operations used by REST API and local stdio MCP."""

from __future__ import annotations

import uuid
from typing import Any

from plaid_mcp import plaid_client, store


def create_link_session(
    *,
    country: str = "both",
    label: str | None = None,
    client_user_id: str | None = None,
    countries: list[str] | None = None,
) -> dict[str, Any]:
    """Start a Plaid Hosted Link session for Transactions."""
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


def list_items() -> dict[str, Any]:
    items = store.list_items()
    return {"items": items, "count": len(items)}


def accounts_get(
    *,
    item_id: str | None = None,
    access_token: str | None = None,
) -> dict[str, Any]:
    token = store.get_access_token(item_id=item_id, access_token=access_token)
    return plaid_client.accounts_get(token)


def transactions_sync(
    *,
    item_id: str | None = None,
    access_token: str | None = None,
    cursor: str | None = None,
    count: int = 500,
) -> dict[str, Any]:
    token = store.get_access_token(item_id=item_id, access_token=access_token)
    result = plaid_client.transactions_sync_all(
        token,
        cursor=cursor,
        count=min(max(count, 1), 500),
    )
    if item_id:
        result["item_id"] = item_id
    return result
