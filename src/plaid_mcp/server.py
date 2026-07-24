"""FastMCP stdio server (local Claude Desktop / Cursor — no Google OAuth)."""

from __future__ import annotations

from plaid_mcp.tools import create_mcp

mcp = create_mcp(auth=None)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
