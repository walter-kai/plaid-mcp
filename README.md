# Plaid service (spearfresh + waltyao)

Private **Plaid Transactions** backend. Same image, two deploy shapes:

| Deploy | Cloud Run | Public? | Caller |
|---|---|---|---|
| Spearfresh | `spearfresh-link` + `plaid-api` | link yes / api no | spearfresh-mcp |
| Walt Yao | `plaid-mcp` (`PLAID_APP_MODE=all`) | **no** (IAM) | waltyao-api-mcp → waltyao.com proxies callbacks |

Claude OAuth + Claude-facing MCP live in the product MCP servers. Full contract: **[INTEGRATION.md](INTEGRATION.md)**.

## Architecture

```text
# Spearfresh
Claude → spearfresh-mcp → ID token → plaid-api
Browser/Plaid → spearfresh-link /oauth-redirect|/webhook → Spearfresh GCS

# Walt Yao
Browser → waltyao.com → waltyao-api-mcp → ID token → plaid-mcp (api+link)
Plaid Hosted Link / webhooks use https://waltyao.com/… (proxied)
Items GCS: …/waltyao-plaid/items.json (separate from Spearfresh)
```

## Local (both modes in one process)

```bash
cp .env.example .env
uv sync
PLAID_APP_MODE=all uv run plaid-mcp-web   # :3000
```

- API: `http://127.0.0.1:3000/api/v1/...`
- Link: `http://127.0.0.1:3000/oauth-redirect` etc.

Optional local stdio MCP: `uv run plaid-mcp` (debug only).

## Deploy

**Spearfresh (defaults unchanged — `cloudbuild.yaml`):**

```bash
export PROJECT_ID=spearfresh-11368
export REGION=northamerica-northeast2
export SPEARFRESH_INVOKER_SA=your-spearfresh-sa@PROJECT.iam.gserviceaccount.com
export PLAID_ITEMS_GCS_URI=gs://BUCKET/plaid-mcp/items.json
./deploy/cloudrun.sh
```

**Walt Yao (`cloudbuild-waltyao.yaml`):**

```bash
export PROJECT_ID=project-11368
export REGION=us-central1
export WALTYAO_INVOKER_SA=firebase-adminsdk-fbsvc@project-11368.iam.gserviceaccount.com
export PLAID_ITEMS_GCS_URI=gs://run-sources-project-11368-us-central1/waltyao-plaid/items.json
./deploy/cloudrun-waltyao.sh
```

Then:

1. Allowlist `https://waltyao.com/oauth-redirect` (and Spearfresh link URL for Spearfresh) in Plaid Dashboard  
2. Set caller `PLAID_SERVICE_URL` to the **api** / `plaid-mcp` URL  
3. Call with a Google ID token (`getIdTokenClient`) from the invoker SA  
4. Grant runtime SA(s) GCS access on the Items bucket  

## Modes (`PLAID_APP_MODE`)

| Value | Routes |
|---|---|
| `api` | `/health`, `/api/v1/*` |
| `link` | `/health`, `/oauth-redirect`, `/link-complete`, `/webhook` |
| `all` | everything (local default; also Walt Yao single-service deploy) |

## REST summary

- `POST /api/v1/link/sessions`
- `GET /api/v1/items`
- `POST /api/v1/accounts/get`
- `POST /api/v1/transactions/sync`

Auth on Cloud Run: **IAM**. Optional extra: `X-Plaid-Service-Key`.
