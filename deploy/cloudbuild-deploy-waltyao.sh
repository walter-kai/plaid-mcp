#!/usr/bin/env bash
# Invoked from cloudbuild-waltyao.yaml — deploy single private plaid-mcp for waltyao.
set -euo pipefail

: "${AR_HOSTNAME:?}"
: "${AR_PROJECT_ID:?}"
: "${AR_REPOSITORY:?}"
: "${COMMIT_SHA:?}"
: "${BUILD_ID:?}"
: "${DEPLOY_REGION:?}"
: "${SERVICE:?}"
: "${PLAID_ITEMS_GCS_URI:?}"
: "${WALTYAO_INVOKER_SA:?}"
: "${PLAID_REDIRECT_URI:?}"
: "${PLAID_COMPLETION_URI:?}"
: "${PLAID_WEBHOOK_URI:?}"

TRIGGER_ID="${TRIGGER_ID:-}"

IMAGE="${AR_HOSTNAME}/${AR_PROJECT_ID}/${AR_REPOSITORY}/plaid-mcp/plaid-mcp:${COMMIT_SHA}"

COMMON_SECRETS="PLAID_CLIENT_ID=plaid-client-id:latest,PLAID_SECRET=plaid-secret:latest,PLAID_TOKEN_ENCRYPTION_KEY=plaid-token-encryption-key:latest"
if gcloud secrets describe plaid-service-key --project="${AR_PROJECT_ID}" >/dev/null 2>&1; then
  COMMON_SECRETS="${COMMON_SECRETS},PLAID_SERVICE_KEY=plaid-service-key:latest"
fi

LABELS="managed-by=gcp-cloud-build-deploy-cloud-run,commit-sha=${COMMIT_SHA},gcb-build-id=${BUILD_ID},caller=waltyao"
if [[ -n "${TRIGGER_ID}" ]]; then
  LABELS="${LABELS},gcb-trigger-id=${TRIGGER_ID}"
fi

EXTRA_ENV="PLAID_APP_MODE=all,PLAID_ENV=production,PLAID_ITEMS_GCS_URI=${PLAID_ITEMS_GCS_URI},PLAID_REDIRECT_URI=${PLAID_REDIRECT_URI},PLAID_COMPLETION_URI=${PLAID_COMPLETION_URI},PLAID_WEBHOOK_URI=${PLAID_WEBHOOK_URI},PUBLIC_BASE_URL=https://waltyao.com"

gcloud run deploy "${SERVICE}" \
  --project="${AR_PROJECT_ID}" \
  --image "${IMAGE}" \
  --region "${DEPLOY_REGION}" \
  --platform managed \
  --no-allow-unauthenticated \
  --memory 512Mi \
  --cpu 1 \
  --min-instances 0 \
  --max-instances 3 \
  --service-account "${WALTYAO_INVOKER_SA}" \
  --set-env-vars "${EXTRA_ENV}" \
  --set-secrets "${COMMON_SECRETS}" \
  --labels "${LABELS}" \
  --quiet

gcloud run services add-iam-policy-binding "${SERVICE}" \
  --project="${AR_PROJECT_ID}" \
  --region="${DEPLOY_REGION}" \
  --member="serviceAccount:${WALTYAO_INVOKER_SA}" \
  --role="roles/run.invoker" \
  --quiet

SERVICE_URL="$(gcloud run services describe "${SERVICE}" --project="${AR_PROJECT_ID}" --region="${DEPLOY_REGION}" --format='value(status.url)')"
echo "plaid-mcp (waltyao, private): ${SERVICE_URL}"
echo "Plaid Dashboard allowlist: ${PLAID_REDIRECT_URI}"
