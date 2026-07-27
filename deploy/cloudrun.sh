#!/usr/bin/env bash
# Deploy TWO Cloud Run services from the same image:
#   plaid-link  — public (Hosted Link redirect / completion / webhook)
#   plaid-api   — private IAM (spearfresh invokes with identity token)
#
# Prerequisites:
#   gcloud auth login && gcloud config set project YOUR_PROJECT_ID
#   Enable: run, artifactregistry, secretmanager, storage, cloudbuild
#
# Secrets (once):
#   printf '%s' "$PLAID_CLIENT_ID" | gcloud secrets create plaid-client-id --data-file=-
#   printf '%s' "$PLAID_SECRET" | gcloud secrets create plaid-secret --data-file=-
#   openssl rand -hex 32 | gcloud secrets create plaid-service-key --data-file=-   # optional 2nd factor
#
# Required env:
#   PROJECT_ID
#   PLAID_ITEMS_GCS_URI=gs://BUCKET/plaid-mcp/items.json
#   SPEARFRESH_INVOKER_SA=spearfresh-runtime@PROJECT.iam.gserviceaccount.com
#
# After first deploy, set redirect URIs to the *link* service URL and redeploy both
# (or update env on both services).
#
# Usage: ./deploy/cloudrun.sh

set -euo pipefail

PROJECT_ID="${PROJECT_ID:?set PROJECT_ID}"
REGION="${REGION:-northamerica-northeast2}"
REPO="${REPO:-plaid-mcp}"
IMAGE_NAME="${IMAGE_NAME:-plaid-mcp}"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/${IMAGE_NAME}:latest"

LINK_SERVICE="${LINK_SERVICE:-plaid-link}"
API_SERVICE="${API_SERVICE:-plaid-api}"

PLAID_ENV="${PLAID_ENV:-production}"
PLAID_ITEMS_GCS_URI="${PLAID_ITEMS_GCS_URI:?set PLAID_ITEMS_GCS_URI}"
SPEARFRESH_INVOKER_SA="${SPEARFRESH_INVOKER_SA:?set SPEARFRESH_INVOKER_SA (Cloud Run SA for spearfresh)}"

# Optional until first deploy knows the link URL — pass placeholders then update.
PLAID_REDIRECT_URI="${PLAID_REDIRECT_URI:-}"
PLAID_COMPLETION_URI="${PLAID_COMPLETION_URI:-}"
PLAID_WEBHOOK_URI="${PLAID_WEBHOOK_URI:-}"
PLACEHOLDER_URIS=0
if [[ -z "${PLAID_REDIRECT_URI}" ]]; then
  PLACEHOLDER_URIS=1
  PLAID_REDIRECT_URI="https://placeholder.invalid/oauth-redirect"
  PLAID_COMPLETION_URI="https://placeholder.invalid/link-complete"
  PLAID_WEBHOOK_URI="https://placeholder.invalid/webhook"
fi

echo "Ensuring Artifact Registry repo ${REPO}..."
gcloud artifacts repositories describe "${REPO}" --location="${REGION}" >/dev/null 2>&1 \
  || gcloud artifacts repositories create "${REPO}" \
       --repository-format=docker \
       --location="${REGION}" \
       --description="plaid-mcp images"

echo "Building ${IMAGE}..."
gcloud builds submit --tag "${IMAGE}" .

COMMON_SECRETS="PLAID_CLIENT_ID=plaid-client-id:latest,PLAID_SECRET=plaid-secret:latest"
# Service key is optional; attach if the secret exists.
if gcloud secrets describe plaid-service-key >/dev/null 2>&1; then
  COMMON_SECRETS="${COMMON_SECRETS},PLAID_SERVICE_KEY=plaid-service-key:latest"
fi

deploy_link() {
  local extra_env="PLAID_APP_MODE=link,PLAID_ENV=${PLAID_ENV},PLAID_ITEMS_GCS_URI=${PLAID_ITEMS_GCS_URI},PLAID_REDIRECT_URI=${PLAID_REDIRECT_URI},PLAID_COMPLETION_URI=${PLAID_COMPLETION_URI},PLAID_WEBHOOK_URI=${PLAID_WEBHOOK_URI}"

  echo "Deploying public ${LINK_SERVICE}..."
  gcloud run deploy "${LINK_SERVICE}" \
    --image "${IMAGE}" \
    --region "${REGION}" \
    --platform managed \
    --allow-unauthenticated \
    --memory 512Mi \
    --cpu 1 \
    --min-instances 0 \
    --max-instances 3 \
    --set-env-vars "${extra_env}" \
    --set-secrets "${COMMON_SECRETS}"
}

deploy_api() {
  local extra_env="PLAID_APP_MODE=api,PLAID_ENV=${PLAID_ENV},PLAID_ITEMS_GCS_URI=${PLAID_ITEMS_GCS_URI},PLAID_REDIRECT_URI=${PLAID_REDIRECT_URI},PLAID_COMPLETION_URI=${PLAID_COMPLETION_URI},PLAID_WEBHOOK_URI=${PLAID_WEBHOOK_URI}"

  echo "Deploying private ${API_SERVICE}..."
  gcloud run deploy "${API_SERVICE}" \
    --image "${IMAGE}" \
    --region "${REGION}" \
    --platform managed \
    --no-allow-unauthenticated \
    --memory 512Mi \
    --cpu 1 \
    --min-instances 0 \
    --max-instances 3 \
    --set-env-vars "${extra_env}" \
    --set-secrets "${COMMON_SECRETS}"

  echo "Granting roles/run.invoker on ${API_SERVICE} to ${SPEARFRESH_INVOKER_SA}..."
  gcloud run services add-iam-policy-binding "${API_SERVICE}" \
    --region "${REGION}" \
    --member="serviceAccount:${SPEARFRESH_INVOKER_SA}" \
    --role="roles/run.invoker"
}

deploy_link
LINK_URL="$(gcloud run services describe "${LINK_SERVICE}" --region "${REGION}" --format='value(status.url)')"

if [[ "${PLACEHOLDER_URIS}" -eq 1 ]]; then
  PLAID_REDIRECT_URI="${LINK_URL}/oauth-redirect"
  PLAID_COMPLETION_URI="${LINK_URL}/link-complete"
  PLAID_WEBHOOK_URI="${LINK_URL}/webhook"
  echo "Updating callback URIs to link service:"
  echo "  ${PLAID_REDIRECT_URI}"
  deploy_link
fi

deploy_api
API_URL="$(gcloud run services describe "${API_SERVICE}" --region "${REGION}" --format='value(status.url)')"

echo
echo "=== Deployed ==="
echo "Link (public):  ${LINK_URL}"
echo "  health:       ${LINK_URL}/health"
echo "  oauth:        ${LINK_URL}/oauth-redirect   ← register in Plaid Dashboard"
echo "  complete:     ${LINK_URL}/link-complete"
echo "  webhook:      ${LINK_URL}/webhook"
echo
echo "API (private):  ${API_URL}"
echo "  health:       ${API_URL}/health   (requires identity token)"
echo "  rest:         ${API_URL}/api/v1/*"
echo
echo "spearfresh-ui:"
echo "  PLAID_SERVICE_URL=${API_URL}"
echo "  Call with Google ID token audience=${API_URL} as the Cloud Run invoker SA"
echo "  Optional: PLAID_SERVICE_KEY if secret plaid-service-key is attached"
echo
echo "Plaid Dashboard: allowlist ${PLAID_REDIRECT_URI}"
echo "GCS: grant both runtime SAs roles/storage.objectAdmin on the Items bucket"
echo "See INTEGRATION.md"
