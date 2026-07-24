# Plaid transactions MCP

Python MCP for Plaid **Transactions**, with Hosted Link + optional **Google OAuth** HTTP server for remote clients (Claude.ai via ngrok).

## Modes

| Mode | Command | Auth |
|---|---|---|
| **stdio** (Claude Desktop / Cursor local) | `uv run plaid-mcp` | None (uses project `.env`) |
| **HTTP** (ngrok + Claude remote MCP) | `uv run plaid-mcp-web` | Google OAuth (Firebase/GCP Web client) |

MCP URL when HTTP is up: `{PUBLIC_BASE_URL}/mcp`

### Tools

1. `create_link_session` — `country="CA"` / `"US"` / `"both"`
2. `list_items`
3. `accounts_get`
4. `transactions_sync` (server-side pagination)

## Local HTTP + Google OAuth (ngrok)

### 1. Google / Firebase

1. In Google Cloud Console (same project as Firebase), create **OAuth 2.0 Client ID** → Web application.
2. Enable **Google** sign-in in Firebase Auth.
3. Add authorized redirect URI:
   ```text
   https://YOUR-NGROK-HOST.ngrok-free.app/auth/callback
   ```
   (Also `http://127.0.0.1:3000/auth/callback` for direct local tests.)
4. Put client id/secret in `.env` as `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET`.

### 2. Configure `.env`

```bash
cp .env.example .env
# Fill PLAID_* , GOOGLE_* , PUBLIC_BASE_URL (your ngrok https origin)
# Optional: ALLOWED_EMAILS=you@gmail.com
```

Plaid Dashboard → Allowed redirect URIs must include:

```text
https://YOUR-NGROK-HOST.ngrok-free.app/oauth-redirect
```

### 3. Run

```bash
uv sync

# terminal 1
uv run plaid-mcp-web    # :3000 — Link routes + /mcp (Google OAuth)

# terminal 2
ngrok http 3000
```

Confirm:

```bash
curl https://YOUR-NGROK-HOST.ngrok-free.app/health
```

### 4. Connect Claude

Add a remote MCP connector with URL:

```text
https://YOUR-NGROK-HOST.ngrok-free.app/mcp
```

Claude should open Google login (no API key). Use an account listed in `ALLOWED_EMAILS` if set.

## Stdio (desktop)

```json
{
  "mcpServers": {
    "plaid-transactions": {
      "command": "uv",
      "args": ["run", "--directory", "/Users/yaoza/Projects/plaid-mcp", "plaid-mcp"]
    }
  }
}
```

Credentials come from the project `.env` (do not put placeholders in the MCP `env` block).

## Canadian banks

Production needs Canada enabled on your Plaid team. Use `country="CA"` to open a Canada-only Link. Sandbox generally includes CA with the sandbox secret.

## Flow

1. `create_link_session`
2. Open `hosted_link_url`, connect bank
3. Webhook stores Item under `data/items.json`
4. `list_items` → `transactions_sync`

## Layout

```text
src/plaid_mcp/
  app.py           # HTTP: Link + Google OAuth MCP
  auth_google.py   # GoogleProvider + email allowlist
  server.py        # stdio MCP
  tools.py         # shared tools
  routes.py        # /health /oauth-redirect /webhook
  plaid_client.py
  store.py
  config.py
```
