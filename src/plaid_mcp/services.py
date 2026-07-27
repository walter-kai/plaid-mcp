"""Shared Plaid operations used by REST API and local stdio MCP."""

from __future__ import annotations

import uuid
from typing import Any

from plaid_mcp import plaid_client, store
from plaid_mcp.token_crypto import decrypt_token


def create_link_session(
    *,
    country: str = "both",
    label: str | None = None,
    client_user_id: str | None = None,
    countries: list[str] | None = None,
    require_client_user_id: bool = False,
) -> dict[str, Any]:
    """Start a Plaid Hosted Link session for Transactions."""
    if require_client_user_id and not (client_user_id and str(client_user_id).strip()):
        raise ValueError("client_user_id is required")
    user_id = (client_user_id and str(client_user_id).strip()) or f"user-{uuid.uuid4()}"
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


def list_items(*, client_user_id: str | None = None) -> dict[str, Any]:
    items = store.list_items(client_user_id=client_user_id)
    return {"items": items, "count": len(items)}


def accounts_get(
    *,
    item_id: str | None = None,
    access_token: str | None = None,
    client_user_id: str | None = None,
) -> dict[str, Any]:
    token = store.get_access_token(
        item_id=item_id,
        access_token=access_token,
        client_user_id=client_user_id,
    )
    return plaid_client.accounts_get(token)


def transactions_sync(
    *,
    item_id: str | None = None,
    access_token: str | None = None,
    cursor: str | None = None,
    count: int = 500,
    client_user_id: str | None = None,
) -> dict[str, Any]:
    token = store.get_access_token(
        item_id=item_id,
        access_token=access_token,
        client_user_id=client_user_id,
    )
    result = plaid_client.transactions_sync_all(
        token,
        cursor=cursor,
        count=min(max(count, 1), 500),
    )
    if item_id:
        result["item_id"] = item_id
    return result


def remove_item(
    *,
    item_id: str,
    client_user_id: str | None = None,
) -> dict[str, Any]:
    """Revoke the Item at Plaid and delete it from the local store."""
    record = store.assert_item_owner(item_id, client_user_id)
    stored = record.get("access_token")
    if not stored:
        raise KeyError(f"Unknown item_id: {item_id}")
    plain = decrypt_token(str(stored))
    plaid_result: dict[str, Any] = {}
    try:
        plaid_result = plaid_client.item_remove(plain)
    except Exception as exc:  # noqa: BLE001 — still drop local copy if Plaid already revoked
        plaid_result = {"warning": str(exc)}
    store.delete_item(item_id, client_user_id=client_user_id)
    return {
        "removed": True,
        "item_id": item_id,
        "client_user_id": record.get("client_user_id"),
        "plaid": plaid_result,
    }
