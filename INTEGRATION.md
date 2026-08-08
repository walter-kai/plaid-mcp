# Integration contract for spearfresh-ui (and sibling agents)

> **Audience:** agents/humans in `/Users/yaoza/Projects/spearfresh-ui`  
> **This repo:** Plaid Hosted Link + private REST API  
> **Not here:** Claude OAuth / Claude-facing MCP (spearfresh owns that)

## Architecture

Two Cloud Run services, one image (`PLAID_APP_MODE`):

```text
Claude ──OAuth+MCP──► spearfresh-ui
                         │
                         │ HTTPS + Google ID token (roles/run.invoker)
                         │ optional X-Plaid-Service-Key
                         ▼
                    plaid-api (PRIVATE)  /api/v1/*
                         │
                         ▼
                      Plaid API

Browser / Plaid ──────► spearfresh-link (PUBLIC)
                         /oauth-redirect  /link-complete  /webhook
                         │
                         └─ writes Items to shared GCS
```

| Service | Mode | Auth | Purpose |
|---|---|---|---|
| `spearfresh-link` | `link` | Public | Shared callbacks (Plaid now; Stripe etc. later) |
| `plaid-api` | `api` | Cloud Run IAM (no unauthenticated) | REST for spearfresh |

Shared GCS (`PLAID_ITEMS_GCS_URI`) so webhook (link) and readers (api) see the same Items.

## What spearfresh-ui must do

### 1. Claude MCP tools (in spearfresh)

Wrap REST → MCP (Claude never calls plaid-* directly):

| MCP tool | HTTP |
|---|---|
| `plaid_create_link_session` | `POST {PLAID_SERVICE_URL}/api/v1/link/sessions` |
| `plaid_list_items` | `GET {PLAID_SERVICE_URL}/api/v1/items` |
| `plaid_accounts_get` | `POST {PLAID_SERVICE_URL}/api/v1/accounts/get` |
| `plaid_transactions_sync` | `POST {PLAID_SERVICE_URL}/api/v1/transactions/sync` |

Flow: ask US/CA → create session → user opens `hosted_link_url` → list items → sync.

### 2. Call private `plaid-api` with IAM (required)

```bash
PLAID_SERVICE_URL=https://plaid-api-xxxxx.run.app   # API service URL only
```

From the spearfresh **Cloud Run / GCE SA** that was granted `roles/run.invoker` on `plaid-api`:

**Node (google-auth-library):**

```js
import { GoogleAuth } from "google-auth-library";

const auth = new GoogleAuth();
const client = await auth.getIdTokenClient(process.env.PLAID_SERVICE_URL);
const res = await client.request({
  url: `${process.env.PLAID_SERVICE_URL}/api/v1/items`,
  method: "GET",
  headers: {
    // Optional second factor if plaid-service-key secret is configured:
    // "X-Plaid-Service-Key": process.env.PLAID_SERVICE_KEY,
  },
});
```

Audience for the ID token **must** be the API service URL (`PLAID_SERVICE_URL`).

Do **not** use the public link URL for API calls.

### 3. Optional service key

If Secret `plaid-service-key` is mounted on `plaid-api`, also send:

```http
X-Plaid-Service-Key: <PLAID_SERVICE_KEY>
```

Do **not** put the service key in `Authorization` when using IAM — that header carries the Google ID token.

## REST API (on plaid-api)

### `POST /api/v1/link/sessions`

```json
{ "country": "both", "label": null, "client_user_id": "user-72f8d0e7-0810-4958-8412-b358a6a147eb", "countries": null, "require_client_user_id": true }
```

`country`: `"US"` | `"CA"` | `"both"`. Returns `hosted_link_url`, `link_token`, …

For Spearfresh dashboard Connectors and MCP tools, always pass a **stable opaque** `client_user_id` (format `user-<uuid>`, stored on the Spearfresh user as `plaidClientUserId`) and set `require_client_user_id: true`. **Do not use email or other PII** as `client_user_id`.

### `GET /api/v1/items?client_user_id=user-<uuid>`

Lists Items for that user only (access tokens redacted to prefix). Omit `client_user_id` only for trusted admin/debug callers — Spearfresh must always pass it.

When `institution_id` / `institution_name` are missing, list performs a best-effort backfill via `/item/get` + `/institutions/get_by_id` and persists the result.

### `DELETE /api/v1/items/{item_id}?client_user_id=user-<uuid>`

Calls Plaid `/item/remove`, deletes the Item from the encrypted store. Returns 403 if `client_user_id` does not own the item.

### `POST /api/v1/accounts/get`

```json
{ "item_id": "...", "client_user_id": "user-<uuid>" }
```

### `POST /api/v1/transactions/sync`

```json
{ "item_id": "...", "cursor": null, "count": 500, "client_user_id": "user-<uuid>" }
```

Server paginates; returns `added` / `modified` / `removed` / `next_cursor`.

## Token storage (plaid-mcp only)

- Item `access_token`s are stored **only** in plaid-mcp (`PLAID_ITEMS_PATH` locally or `PLAID_ITEMS_GCS_URI` in Cloud Run).
- Values are **AES-256-GCM** encrypted (`enc:v1:iv:tag:ciphertext`) using `PLAID_TOKEN_ENCRYPTION_KEY` (required when `PLAID_ENV=production`).
- Spearfresh must **not** store Plaid access tokens in Firestore user docs. Spearfresh may store non-secret `connectors.plaid` metadata (`connected`, `itemIds`, institutions) plus the opaque `plaidClientUserId`.
- On Hosted Link `SESSION_FINISHED`, plaid-mcp exchanges the public token, calls `/item/get` + `/institutions/get_by_id`, and persists `institution_id` / `institution_name` on the Item record.
- `public_token` is not retained after exchange.

## Public link service (spearfresh-link)

Configure **on plaid-mcp deploy** (not spearfresh):

```text
PLAID_REDIRECT_URI=https://spearfresh-link-….run.app/oauth-redirect
PLAID_COMPLETION_URI=https://spearfresh-link-….run.app/link-complete
PLAID_WEBHOOK_URI=https://spearfresh-link-….run.app/webhook
```

Register **exactly** `…/oauth-redirect` in Plaid Dashboard → Allowed redirect URIs.

spearfresh does not proxy these.

## Env cheat sheet

**spearfresh-ui**

```bash
PLAID_SERVICE_URL=https://plaid-api-….run.app
# PLAID_SERVICE_KEY=...   # only if second factor enabled
```

Runtime SA must have `roles/run.invoker` on `plaid-api` (deploy script sets this via `SPEARFRESH_INVOKER_SA`).

**plaid-mcp (both services)**

```bash
PLAID_CLIENT_ID / PLAID_SECRET / PLAID_ENV
PLAID_ITEMS_GCS_URI=gs://…
PLAID_TOKEN_ENCRYPTION_KEY=…   # Secret Manager: plaid-token-encryption-key
PLAID_REDIRECT_URI / PLAID_COMPLETION_URI / PLAID_WEBHOOK_URI  # link hostname
PLAID_APP_MODE=api|link
```

## Local dev

Single process, both surfaces:

```bash
PLAID_APP_MODE=all uv run plaid-mcp-web   # :3000
```

Optional: `PLAID_SERVICE_KEY` to exercise API auth locally. No IAM locally.

## Deploy

```bash
export PROJECT_ID=spearfresh-11368
export REGION=northamerica-northeast2
export SPEARFRESH_INVOKER_SA=spearfresh-runtime@PROJECT.iam.gserviceaccount.com
export PLAID_ITEMS_GCS_URI=gs://BUCKET/plaid-mcp/items.json
./deploy/cloudrun.sh
```

Grant both Cloud Run runtime SAs `roles/storage.objectAdmin` on the Items bucket.

## Ownership

| Concern | Owner |
|---|---|
| Claude connector + OAuth | spearfresh-ui |
| Plaid secrets, Link, webhook, REST | plaid-mcp |
| Invoker IAM on plaid-api | deploy + spearfresh SA |
