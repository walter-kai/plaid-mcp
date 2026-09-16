#!/usr/bin/env bash
# Deploy a waltyao-oriented plaid-mcp upstream (single Cloud Run service, PLAID_APP_MODE=all).
#
# Spearfresh keeps using spearfresh-link + plaid-api (see ./cloudrun.sh). This path is for:
#   waltyao.com → waltyao-api-mcp → plaid-mcp → Plaid
#
# Callbacks are browser-facing on waltyao.com (proxied through waltyao-api-mcp), so Hosted Link
# URIs must be the site host — not the Cloud Run URL:
#   PLAID_REDIRECT_URI=https://waltyao.com/oauth-redirect
#   PLAID_COMPLETION_URI=https://waltyao.com/link-complete
#   PLAID_WEBHOOK_URI=https://waltyao.com/webhook
#
# Required env:
#   PROJECT_ID=project-11368
#   WALTYAO_INVOKER_SA=…@project-11368.iam.gserviceaccount.com   # waltyao-api-mcp runtime SA
#   PLAID_ITEMS_GCS_URI=gs://BUCKET/waltyao-plaid/items.json      # separate from Spearfresh
#
# Optional:
#   REGION=us-central1
#   SERVICE=plaid-mcp
#
# Usage: ./deploy/cloudrun-waltyao.sh

set -euo pipefail

PROJECT_ID="${PROJECT_ID:?set PROJECT_ID}"
REGION="${REGION:-us-central1}"
REPO="${REPO:-cloud-run-source-deploy}"
IMAGE_NAME="${IMAGE_NAME:-plaid-mcp}"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/plaid-mcp/${IMAGE_NAME}:latest"

SERVICE="${SERVICE:-plaid-mcp}"
PLAID_ENV="${PLAID_ENV:-production}"
PLAID_ITEMS_GCS_URI="${PLAID_ITEMS_GCS_URI:?set PLAID_ITEMS_GCS_URI (use a waltyao-specific path)}"
WALTYAO_INVOKER_SA="${WALTYAO_INVOKER_SA:?set WALTYAO_INVOKER_SA (waltyao-api-mcp Cloud Run SA)}"

PLAID_REDIRECT_URI="${PLAID_REDIRECT_URI:-https://waltyao.com/oauth-redirect}"
PLAID_COMPLETION_URI="${PLAID_COMPLETION_URI:-https://waltyao.com/link-complete}"
PLAID_WEBHOOK_URI="${PLAID_WEBHOOK_URI:-https://waltyao.com/webhook}"

echo "Ensuring Artifact Registry repo ${REPO}..."
gcloud artifacts repositories describe "${REPO}" --project="${PROJECT_ID}" --location="${REGION}" >/dev/null 2>&1 \
  || gcloud artifacts repositories create "${REPO}" \
       --project="${PROJECT_ID}" \
       --repository-format=docker \
       --location="${REGION}" \
       --description="Cloud Run source deploy images"

echo "Building ${IMAGE}..."
gcloud builds submit --project="${PROJECT_ID}" --tag "${IMAGE}" .

COMMON_SECRETS="PLAID_CLIENT_ID=plaid-client-id:latest,PLAID_SECRET=plaid-secret:latest"
if gcloud secrets describe plaid-service-key --project="${PROJECT_ID}" >/dev/null 2>&1; then
  COMMON_SECRETS="${COMMON_SECRETS},PLAID_SERVICE_KEY=plaid-service-key:latest"
fi
if gcloud secrets describe plaid-token-encryption-key --project="${PROJECT_ID}" >/dev/null 2>&1; then
  COMMON_SECRETS="${COMMON_SECRETS},PLAID_TOKEN_ENCRYPTION_KEY=plaid-token-encryption-key:latest"
else
  echo "WARNING: secret plaid-token-encryption-key missing — create it before production deploy" >&2
fi

EXTRA_ENV="PLAID_APP_MODE=all,PLAID_ENV=${PLAID_ENV},PLAID_ITEMS_GCS_URI=${PLAID_ITEMS_GCS_URI},PLAID_REDIRECT_URI=${PLAID_REDIRECT_URI},PLAID_COMPLETION_URI=${PLAID_COMPLETION_URI},PLAID_WEBHOOK_URI=${PLAID_WEBHOOK_URI},PUBLIC_BASE_URL=https://waltyao.com"

echo "Deploying private ${SERVICE} (api+link behind one URL)..."
gcloud run deploy "${SERVICE}" \
  --project="${PROJECT_ID}" \
  --image "${IMAGE}" \
  --region "${REGION}" \
  --platform managed \
  --no-allow-unauthenticated \
  --memory 512Mi \
  --cpu 1 \
  --min-instances 0 \
  --max-instances 3 \
  --service-account "${WALTYAO_INVOKER_SA}" \
  --set-env-vars "${EXTRA_ENV}" \
  --set-secrets "${COMMON_SECRETS}"

echo "Granting roles/run.invoker on ${SERVICE} to ${WALTYAO_INVOKER_SA}..."
gcloud run services add-iam-policy-binding "${SERVICE}" \
  --project="${PROJECT_ID}" \
  --region "${REGION}" \
  --member="serviceAccount:${WALTYAO_INVOKER_SA}" \
  --role="roles/run.invoker" \
  --quiet

SERVICE_URL="$(gcloud run services describe "${SERVICE}" --project="${PROJECT_ID}" --region "${REGION}" --format='value(status.url)')"

echo
echo "=== Deployed (waltyao upstream) ==="
echo "Service (private): ${SERVICE_URL}"
echo "  health / api:    ${SERVICE_URL}/health   (requires identity token)"
echo "  rest:            ${SERVICE_URL}/api/v1/*"
echo "  link callbacks:  ${SERVICE_URL}/oauth-redirect|/link-complete|/webhook"
echo
echo "waltyao-api-mcp:"
echo "  PLAID_SERVICE_URL=${SERVICE_URL}"
echo "  Call with Google ID token audience=${SERVICE_URL}"
echo
echo "Plaid Dashboard allowlist (exact):"
echo "  ${PLAID_REDIRECT_URI}"
echo
echo "GCS: grant runtime SA roles/storage.objectAdmin on the Items bucket/object"
echo "See INTEGRATION.md (waltyao caller section)"
