"""Optional local stdio MCP for desktop testing. Production Claude MCP lives in waltyao-api-mcp."""

from __future__ import annotations

import uuid
from typing import Any

from fastmcp import FastMCP

from plaid_mcp import services

mcp = FastMCP(
    name="plaid-transactions-local",
    instructions=(
        "LOCAL ONLY. Production Claude should use waltyao-api-mcp. "
        "Connect a bank via Hosted Link, then sync transactions. "
        "Ask US vs Canada; use country='CA', 'US', or 'both'. "
        "Pass a stable opaque client_user_id (user-<uuid>); never email. "
        "Flow: create_link_session → open hosted_link_url → list_items → transactions_sync."
    ),
)


@mcp.tool
def create_link_session(
    country: str = "both",
    label: str | None = None,
    client_user_id: str | None = None,
    countries: list[str] | None = None,
) -> dict[str, Any]:
    """Start a Plaid Hosted Link session for Transactions (local stdio helper)."""
    # Local helper only — production Spearfresh persists user-<uuid> on the user doc.
    resolved = (client_user_id and str(client_user_id).strip()) or f"user-{uuid.uuid4()}"
    return services.create_link_session(
        country=country,
        label=label,
        client_user_id=resolved,
        countries=countries,
        require_client_user_id=True,
    )


@mcp.tool
def list_items() -> dict[str, Any]:
    """List stored Plaid Items available for transaction sync."""
    return services.list_items()


@mcp.tool
def accounts_get(
    item_id: str | None = None,
    access_token: str | None = None,
) -> dict[str, Any]:
    """Fetch accounts for a stored item_id or a raw access_token."""
    return services.accounts_get(item_id=item_id, access_token=access_token)


@mcp.tool
def transactions_sync(
    item_id: str | None = None,
    access_token: str | None = None,
    cursor: str | None = None,
    count: int = 500,
) -> dict[str, Any]:
    """Sync transactions via /transactions/sync with server-side pagination."""
    return services.transactions_sync(
        item_id=item_id,
        access_token=access_token,
        cursor=cursor,
        count=count,
    )


@mcp.tool
def investments_holdings_get(
    item_id: str | None = None,
    access_token: str | None = None,
) -> dict[str, Any]:
    """Fetch investment holdings (positions + securities) for an item. Read-only."""
    return services.investments_holdings_get(item_id=item_id, access_token=access_token)


@mcp.tool
def investments_transactions_get(
    item_id: str | None = None,
    access_token: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    count: int = 500,
) -> dict[str, Any]:
    """Fetch investment transactions (buys, sells, dividends, fees) by date. Read-only."""
    return services.investments_transactions_get(
        item_id=item_id,
        access_token=access_token,
        start_date=start_date,
        end_date=end_date,
        count=count,
    )


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
