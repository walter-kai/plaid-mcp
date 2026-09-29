"""Private REST API for waltyao-api-mcp to call Plaid operations."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from plaid_mcp import services

router = APIRouter(prefix="/api/v1", tags=["plaid"])


class CreateLinkSessionBody(BaseModel):
    country: str = "both"
    label: str | None = None
    client_user_id: str | None = None
    countries: list[str] | None = None
    require_client_user_id: bool = False


class ItemRefBody(BaseModel):
    item_id: str | None = None
    access_token: str | None = None
    client_user_id: str | None = None


class TransactionsSyncBody(ItemRefBody):
    cursor: str | None = None
    count: int = Field(default=500, ge=1, le=500)


class TransactionsGetBody(ItemRefBody):
    start_date: str | None = None
    end_date: str | None = None
    count: int = Field(default=500, ge=1, le=500)


class InvestmentsTransactionsBody(ItemRefBody):
    start_date: str | None = None
    end_date: str | None = None
    count: int = Field(default=500, ge=1, le=500)


class RemoveItemBody(BaseModel):
    client_user_id: str | None = None


@router.post("/link/sessions")
def create_link_session(body: CreateLinkSessionBody) -> dict[str, Any]:
    """Create a Hosted Link session; returns hosted_link_url for the user."""
    try:
        return services.create_link_session(
            country=body.country,
            label=body.label,
            client_user_id=body.client_user_id,
            countries=body.countries,
            require_client_user_id=body.require_client_user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 — surface Plaid errors cleanly
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/items")
def list_items(
    client_user_id: str | None = Query(default=None),
) -> dict[str, Any]:
    """List stored Plaid Items (access tokens redacted). Filter by client_user_id when set."""
    return services.list_items(client_user_id=client_user_id)


@router.delete("/items/{item_id}")
def delete_item(
    item_id: str,
    client_user_id: str | None = Query(default=None),
) -> dict[str, Any]:
    """Revoke Item at Plaid and delete from store. Enforce ownership when client_user_id is set."""
    try:
        return services.remove_item(item_id=item_id, client_user_id=client_user_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/accounts/get")
def accounts_get(body: ItemRefBody) -> dict[str, Any]:
    """Fetch accounts for an item_id or raw access_token."""
    try:
        return services.accounts_get(
            item_id=body.item_id,
            access_token=body.access_token,
            client_user_id=body.client_user_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
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
            client_user_id=body.client_user_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/transactions/get")
def transactions_get(body: TransactionsGetBody) -> dict[str, Any]:
    """Fetch transactions between dates straight from Plaid (no local storage)."""
    try:
        return services.transactions_get(
            item_id=body.item_id,
            access_token=body.access_token,
            start_date=body.start_date,
            end_date=body.end_date,
            count=body.count,
            client_user_id=body.client_user_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/investments/holdings/get")
def investments_holdings_get(body: ItemRefBody) -> dict[str, Any]:
    """Fetch investment holdings (positions + securities) for an item. Read-only."""
    try:
        return services.investments_holdings_get(
            item_id=body.item_id,
            access_token=body.access_token,
            client_user_id=body.client_user_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/investments/transactions/get")
def investments_transactions_get(body: InvestmentsTransactionsBody) -> dict[str, Any]:
    """Fetch investment transactions (buys, sells, dividends, fees) by date. Read-only."""
    try:
        return services.investments_transactions_get(
            item_id=body.item_id,
            access_token=body.access_token,
            start_date=body.start_date,
            end_date=body.end_date,
            count=body.count,
            client_user_id=body.client_user_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc
