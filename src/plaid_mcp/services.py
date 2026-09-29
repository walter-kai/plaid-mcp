"""Shared Plaid operations used by REST API and local stdio MCP."""

from __future__ import annotations

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
    """Start a Plaid Hosted Link session for Transactions.

    Spearfresh (and other callers) should pass a stable opaque ``client_user_id``
    (e.g. ``user-<uuid>``), never email/PII. Random ids are not generated here —
    missing ids fail when ``require_client_user_id`` is set, otherwise Link is
    rejected so Items are never orphaned under an ephemeral key.
    """
    user_id = (client_user_id and str(client_user_id).strip()) or ""
    if require_client_user_id and not user_id:
        raise ValueError("client_user_id is required")
    if not user_id:
        raise ValueError(
            "client_user_id is required (stable opaque id such as user-<uuid>; do not use email)"
        )
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
            "Open hosted_link_url in a browser. When the user finishes, suggest prompts "
            "like “What banks do I have linked?” or “Show my recent transactions” "
            "(wait a few seconds if the new link is not visible yet)."
        ),
    }
    if session.get("canada_note"):
        result["canada_note"] = session["canada_note"]
    return result


def enrich_item_institution(
    *,
    item_id: str,
    access_token: str | None = None,
    client_user_id: str | None = None,
) -> dict[str, Any]:
    """Fetch and persist institution_id / institution_name for a stored Item."""
    record = store.assert_item_owner(item_id, client_user_id)
    token = access_token or store.get_access_token(
        item_id=item_id,
        client_user_id=client_user_id,
    )
    meta = plaid_client.resolve_institution_metadata(token)
    if not meta.get("institution_id") and not meta.get("institution_name"):
        return dict(record)
    updated = store.upsert_item(
        item_id=item_id,
        access_token=token,
        label=record.get("label"),
        client_user_id=record.get("client_user_id"),
        institution_id=meta.get("institution_id"),
        institution_name=meta.get("institution_name"),
        request_id=record.get("request_id"),
    )
    return updated


def list_items(*, client_user_id: str | None = None) -> dict[str, Any]:
    items = store.list_items(client_user_id=client_user_id)
    # Best-effort backfill for Items linked before institution metadata was persisted.
    enriched: list[dict[str, Any]] = []
    for row in items:
        if row.get("institution_id") and row.get("institution_name"):
            enriched.append(row)
            continue
        item_id = row.get("item_id")
        if not isinstance(item_id, str) or not item_id:
            enriched.append(row)
            continue
        try:
            updated = enrich_item_institution(
                item_id=item_id,
                client_user_id=client_user_id or row.get("client_user_id"),
            )
            enriched.append(
                {
                    **row,
                    "institution_id": updated.get("institution_id"),
                    "institution_name": updated.get("institution_name"),
                    "updated_at": updated.get("updated_at") or row.get("updated_at"),
                }
            )
        except Exception:
            enriched.append(row)
    return {"items": enriched, "count": len(enriched)}


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


def transactions_get(
    *,
    item_id: str | None = None,
    access_token: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    count: int = 500,
    client_user_id: str | None = None,
) -> dict[str, Any]:
    token = store.get_access_token(
        item_id=item_id,
        access_token=access_token,
        client_user_id=client_user_id,
    )
    result = plaid_client.transactions_get(
        token,
        start_date=start_date,
        end_date=end_date,
        count=min(max(count, 1), 500),
    )
    if item_id:
        result["item_id"] = item_id
    return result


def investments_holdings_get(
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
    result = plaid_client.investments_holdings_get(token)
    if item_id:
        result["item_id"] = item_id
    return result


def investments_transactions_get(
    *,
    item_id: str | None = None,
    access_token: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    count: int = 500,
    client_user_id: str | None = None,
) -> dict[str, Any]:
    token = store.get_access_token(
        item_id=item_id,
        access_token=access_token,
        client_user_id=client_user_id,
    )
    result = plaid_client.investments_transactions_get(
        token,
        start_date=start_date,
        end_date=end_date,
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


def dedupe_institution_items(
    *,
    client_user_id: str | None,
    institution_id: str | None,
    keep_item_id: str,
) -> list[dict[str, Any]]:
    """Drop other Items for the same user + institution, keeping ``keep_item_id``.

    A "Reconfigure" re-link creates a brand-new Item for an institution the user
    already linked. Without this, the linked-institutions list accumulates a
    duplicate row each time. We revoke and delete the stale Items so re-linking
    updates the connection in place instead of piling up.

    Scoped strictly to one owner: skipped when the owner or institution is
    unknown, so we never touch another user's Items.
    """
    if not client_user_id or not institution_id:
        return []
    removed: list[dict[str, Any]] = []
    for row in store.list_items(client_user_id=client_user_id):
        other_id = row.get("item_id")
        if not isinstance(other_id, str) or not other_id or other_id == keep_item_id:
            continue
        if row.get("institution_id") != institution_id:
            continue
        try:
            removed.append(remove_item(item_id=other_id, client_user_id=client_user_id))
        except Exception:  # noqa: BLE001 — best-effort cleanup; never fail the link
            continue
    return removed
