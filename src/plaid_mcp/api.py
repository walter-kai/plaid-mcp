"""Private REST API for spearfresh (or other apps) to call Plaid operations."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from plaid_mcp import services

router = APIRouter(prefix="/api/v1", tags=["plaid"])


class CreateLinkSessionBody(BaseModel):
    country: str = "both"
    label: str | None = None
    client_user_id: str | None = None
    countries: list[str] | None = None


class ItemRefBody(BaseModel):
    item_id: str | None = None
    access_token: str | None = None


class TransactionsSyncBody(ItemRefBody):
    cursor: str | None = None
    count: int = Field(default=500, ge=1, le=500)


@router.post("/link/sessions")
def create_link_session(body: CreateLinkSessionBody) -> dict[str, Any]:
    """Create a Hosted Link session; returns hosted_link_url for the user."""
    try:
        return services.create_link_session(
            country=body.country,
            label=body.label,
            client_user_id=body.client_user_id,
            countries=body.countries,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 — surface Plaid errors cleanly
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/items")
def list_items() -> dict[str, Any]:
    """List stored Plaid Items (access tokens redacted)."""
    return services.list_items()


@router.post("/accounts/get")
def accounts_get(body: ItemRefBody) -> dict[str, Any]:
    """Fetch accounts for an item_id or raw access_token."""
    try:
        return services.accounts_get(
            item_id=body.item_id,
            access_token=body.access_token,
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/transactions/sync")
def transactions_sync(body: TransactionsSyncBody) -> dict[str, Any]:
    """Sync transactions with server-side pagination."""
    try:
        return services.transactions_sync(
            item_id=body.item_id,
            access_token=body.access_token,
            cursor=body.cursor,
            count=body.count,
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc
