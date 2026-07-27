"""Backward-compatible entry for ``plaid-mcp-web`` → unified app."""

from plaid_mcp.app import app, main

__all__ = ["app", "main"]
