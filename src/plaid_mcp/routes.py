"""Plaid Hosted Link HTTP routes (mounted on the unified FastAPI app)."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

from plaid_mcp import plaid_client, store
from plaid_mcp.config import get_settings


def _page(title: str, body: str) -> HTMLResponse:
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title}</title>
  <style>
    body {{
      font-family: ui-sans-serif, system-ui, -apple-system, sans-serif;
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      background: #0f1419;
      color: #e7ecf3;
    }}
    main {{
      max-width: 32rem;
      padding: 2rem;
      line-height: 1.5;
    }}
    h1 {{ font-size: 1.35rem; margin: 0 0 0.75rem; }}
    p {{ margin: 0.4rem 0; color: #b7c0cc; }}
    code {{ color: #d7e3ff; }}
  </style>
</head>
<body>
  <main>
    <h1>{title}</h1>
    {body}
  </main>
</body>
</html>
"""
    return HTMLResponse(html)


def register_link_routes(app: FastAPI) -> None:
    @app.get("/health")
    def health() -> dict[str, Any]:
        settings = get_settings()
        return {
            "ok": True,
            "env": settings.env,
            "public_base_url": settings.public_base_url,
            "redirect_uri": settings.redirect_uri,
            "completion_uri": settings.completion_uri,
            "webhook_uri": settings.webhook_uri,
            "mcp_url": f"{settings.public_base_url}/mcp",
            "google_oauth_configured": bool(
                settings.google_oauth_client_id and settings.google_oauth_client_secret
            ),
        }

    @app.get("/oauth-redirect")
    def oauth_redirect(request: Request) -> HTMLResponse:
        received = str(request.url)
        return _page(
            "Plaid OAuth redirect",
            f"""
            <p>Bank OAuth returned here. If Link does not resume automatically, close this tab and return to Hosted Link.</p>
            <p><code>{received}</code></p>
            """,
        )

    @app.get("/link-complete")
    def link_complete() -> HTMLResponse:
        return _page(
            "Bank connected",
            """
            <p>Hosted Link finished. Return to Claude/Cursor and call <code>list_items</code>, then <code>transactions_sync</code>.</p>
            <p>If nothing appears yet, wait a few seconds for the <code>SESSION_FINISHED</code> webhook.</p>
            """,
        )

    @app.post("/webhook")
    async def webhook(request: Request) -> JSONResponse:
        try:
            payload = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid json"}, status_code=400)

        webhook_type = payload.get("webhook_type")
        webhook_code = payload.get("webhook_code")

        if webhook_type == "LINK" and webhook_code == "SESSION_FINISHED":
            status = payload.get("status")
            link_token = payload.get("link_token")
            public_tokens = payload.get("public_tokens") or []
            pending = store.pop_pending_link(link_token)
            saved = []

            if status == "success":
                for public_token in public_tokens:
                    exchanged = plaid_client.exchange_public_token(public_token)
                    item_id = exchanged.get("item_id")
                    access_token = exchanged.get("access_token")
                    if not item_id or not access_token:
                        continue
                    record = store.upsert_item(
                        item_id=item_id,
                        access_token=access_token,
                        label=(pending or {}).get("label"),
                        client_user_id=(pending or {}).get("client_user_id"),
                        public_token=public_token,
                        request_id=exchanged.get("request_id"),
                    )
                    saved.append(
                        {
                            "item_id": record["item_id"],
                            "label": record.get("label"),
                        }
                    )

            return JSONResponse(
                {
                    "received": True,
                    "webhook_type": webhook_type,
                    "webhook_code": webhook_code,
                    "status": status,
                    "saved": saved,
                }
            )

        return JSONResponse(
            {
                "received": True,
                "webhook_type": webhook_type,
                "webhook_code": webhook_code,
            }
        )
