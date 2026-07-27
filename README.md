# Plaid service (for spearfresh-ui)

Private **Plaid Transactions** backend split for GCP:

| Cloud Run service | Public? | Role |
|---|---|---|
| `plaid-api` | **No** (IAM invoker) | REST `/api/v1/*` for spearfresh |
| `plaid-link` | **Yes** | Hosted Link redirect / completion / webhook |

Claude OAuth + Claude-facing MCP live in **spearfresh-ui**. Full contract: **[INTEGRATION.md](INTEGRATION.md)**.

## Architecture

```text
Claude → spearfresh-ui (OAuth + MCP)
            → ID token → plaid-api (private) /api/v1/*
Browser/Plaid → plaid-link (public) /oauth-redirect|/webhook
                    ↘ shared GCS Items
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

## Deploy (two services)

```bash
export PROJECT_ID=spearfresh-11368
export REGION=northamerica-northeast2
export SPEARFRESH_INVOKER_SA=your-spearfresh-sa@PROJECT.iam.gserviceaccount.com
export PLAID_ITEMS_GCS_URI=gs://BUCKET/plaid-mcp/items.json
./deploy/cloudrun.sh
```

Then:

1. Register **link** URL `…/oauth-redirect` in Plaid Dashboard  
2. Set spearfresh `PLAID_SERVICE_URL` to the **api** URL  
3. Call API with a Google ID token (`getIdTokenClient`) from the invoker SA  
4. Grant both runtime SAs GCS access on the Items bucket  

## Modes (`PLAID_APP_MODE`)

| Value | Routes |
|---|---|
| `api` | `/health`, `/api/v1/*` |
| `link` | `/health`, `/oauth-redirect`, `/link-complete`, `/webhook` |
| `all` | everything (local default) |

## REST summary

- `POST /api/v1/link/sessions`
- `GET /api/v1/items`
- `POST /api/v1/accounts/get`
- `POST /api/v1/transactions/sync`

Auth on Cloud Run: **IAM**. Optional extra: `X-Plaid-Service-Key`.
