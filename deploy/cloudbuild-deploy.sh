#!/usr/bin/env bash
# Invoked from cloudbuild.yaml — deploy spearfresh-link + plaid-api in waltyao (project-11368).
set -euo pipefail

: "${AR_HOSTNAME:?}"
: "${AR_PROJECT_ID:?}"
: "${AR_REPOSITORY:?}"
: "${COMMIT_SHA:?}"
: "${BUILD_ID:?}"
: "${DEPLOY_REGION:?}"
: "${LINK_SERVICE:?}"
: "${API_SERVICE:?}"
: "${PLAID_ITEMS_GCS_URI:?}"
: "${SPEARFRESH_INVOKER_SA:?}"

TRIGGER_ID="${TRIGGER_ID:-}"

IMAGE="${AR_HOSTNAME}/${AR_PROJECT_ID}/${AR_REPOSITORY}/plaid-mcp/plaid-mcp:${COMMIT_SHA}"

COMMON_SECRETS="PLAID_CLIENT_ID=plaid-client-id:latest,PLAID_SECRET=plaid-secret:latest,PLAID_TOKEN_ENCRYPTION_KEY=plaid-token-encryption-key:latest"
if gcloud secrets describe plaid-service-key --project="${AR_PROJECT_ID}" >/dev/null 2>&1; then
  COMMON_SECRETS="${COMMON_SECRETS},PLAID_SERVICE_KEY=plaid-service-key:latest"
fi

LABELS="managed-by=gcp-cloud-build-deploy-cloud-run,commit-sha=${COMMIT_SHA},gcb-build-id=${BUILD_ID}"
if [[ -n "${TRIGGER_ID}" ]]; then
  LABELS="${LABELS},gcb-trigger-id=${TRIGGER_ID}"
fi

deploy_link() {
  local base_url="$1"
  gcloud run deploy "${LINK_SERVICE}" \
    --project="${AR_PROJECT_ID}" \
    --image "${IMAGE}" \
    --region "${DEPLOY_REGION}" \
    --platform managed \
    --allow-unauthenticated \
    --memory 512Mi \
    --cpu 1 \
    --min-instances 0 \
    --max-instances 3 \
    --service-account "${SPEARFRESH_INVOKER_SA}" \
    --set-env-vars "PLAID_APP_MODE=link,PLAID_ENV=production,PLAID_ITEMS_GCS_URI=${PLAID_ITEMS_GCS_URI},PLAID_REDIRECT_URI=${base_url}/oauth-redirect,PLAID_COMPLETION_URI=${base_url}/link-complete,PLAID_WEBHOOK_URI=${base_url}/webhook" \
    --set-secrets "${COMMON_SECRETS}" \
    --labels "${LABELS}" \
    --quiet
}

deploy_link "https://placeholder.invalid"
LINK_URL="$(gcloud run services describe "${LINK_SERVICE}" --project="${AR_PROJECT_ID}" --region="${DEPLOY_REGION}" --format='value(status.url)')"
deploy_link "${LINK_URL}"

gcloud run deploy "${API_SERVICE}" \
  --project="${AR_PROJECT_ID}" \
  --image "${IMAGE}" \
  --region="${DEPLOY_REGION}" \
  --platform managed \
  --no-allow-unauthenticated \
  --memory 512Mi \
  --cpu 1 \
  --min-instances 0 \
  --max-instances 3 \
  --service-account "${SPEARFRESH_INVOKER_SA}" \
  --set-env-vars "PLAID_APP_MODE=api,PLAID_ENV=production,PLAID_ITEMS_GCS_URI=${PLAID_ITEMS_GCS_URI},PLAID_REDIRECT_URI=${LINK_URL}/oauth-redirect,PLAID_COMPLETION_URI=${LINK_URL}/link-complete,PLAID_WEBHOOK_URI=${LINK_URL}/webhook" \
  --set-secrets "${COMMON_SECRETS}" \
  --labels "${LABELS}" \
  --quiet

gcloud run services add-iam-policy-binding "${API_SERVICE}" \
  --project="${AR_PROJECT_ID}" \
  --region="${DEPLOY_REGION}" \
  --member="serviceAccount:${SPEARFRESH_INVOKER_SA}" \
  --role="roles/run.invoker" \
  --quiet

API_URL="$(gcloud run services describe "${API_SERVICE}" --project="${AR_PROJECT_ID}" --region="${DEPLOY_REGION}" --format='value(status.url)')"
echo "Link (public): ${LINK_URL}"
echo "API (private): ${API_URL}"
