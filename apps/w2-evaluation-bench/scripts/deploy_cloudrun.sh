#!/bin/bash
# Deploy the W2 Evaluation Bench server to Google Cloud Run.
#
# Usage:
#   PROJECT=my-gcp-project REGION=us-central1 W2APP_TOKEN=$(openssl rand -hex 24) \
#     bash scripts/deploy_cloudrun.sh
#
# What this sets up and why:
#   * GCS bucket mounted at /data (Cloud Run volume mounts, GCS FUSE): run
#     directories, escrow, and deliverables survive instance restarts.
#   * --max-instances=1: the orchestrator's file-based state assumes a single
#     writer; one instance is ample for an operator tool and removes all
#     cross-instance race concerns.
#   * W2APP_TOKEN: shared-secret auth on every /api route. The service URL is
#     public (Cloud Run --allow-unauthenticated) but the API is not.
#   * The runner is NOT deployed here — it runs on your machine/VM with your
#     Claude subscription and polls this service outbound over HTTPS.
set -euo pipefail
: "${PROJECT:?set PROJECT}"; : "${REGION:=us-central1}"
: "${SERVICE:=w2-eval-bench}"
# Auth (v2.0): per-member tokens (owner-pays affinity, FR-13) via
#   W2APP_TOKENS="alice:tokA,bob:tokB"
# and/or the single shared W2APP_TOKEN (member "operator"). At least one must be set.
if [ -z "${W2APP_TOKEN:-}" ] && [ -z "${W2APP_TOKENS:-}" ]; then
  echo "set W2APP_TOKEN (shared secret) and/or W2APP_TOKENS (member:token,...)" >&2; exit 2
fi
BUCKET="${BUCKET:-${PROJECT}-w2-runs}"

gcloud storage buckets describe "gs://$BUCKET" >/dev/null 2>&1 || \
  gcloud storage buckets create "gs://$BUCKET" --project "$PROJECT" --location "$REGION"

gcloud run deploy "$SERVICE" \
  --project "$PROJECT" --region "$REGION" \
  --source . \
  --allow-unauthenticated \
  --max-instances 1 --concurrency 40 --memory 1Gi --timeout 300 \
  --set-env-vars "W2APP_DATA=/data,W2APP_TOKEN=${W2APP_TOKEN:-},W2APP_TOKENS=${W2APP_TOKENS:-}" \
  --add-volume "name=runs,type=cloud-storage,bucket=$BUCKET" \
  --add-volume-mount "volume=runs,mount-path=/data"

URL=$(gcloud run services describe "$SERVICE" --project "$PROJECT" \
      --region "$REGION" --format 'value(status.url)')

# Post-deploy verification (read-only): health, auth walls, runner payload.
echo
echo "== verifying the live service =="
bash "$(dirname "$0")/remote_smoke.sh" "$URL" || {
  echo "remote smoke FAILED - the service is up but not healthy; see above." >&2
  exit 1
}
echo
echo "Deployed: $URL"
echo "Console:  open $URL and paste the token when prompted."
echo "Members:  each evaluating member installs their personal runner with"
echo "          curl -fsSL $URL/install.sh | bash -s -- --token <their-token>"
echo "Runner (manual): python3 runner/w2_runner.py --server $URL --token <token>"
