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
: "${SERVICE:=w2-eval-bench}"; : "${W2APP_TOKEN:?set W2APP_TOKEN (shared secret)}"
BUCKET="${BUCKET:-${PROJECT}-w2-runs}"

gcloud storage buckets describe "gs://$BUCKET" >/dev/null 2>&1 || \
  gcloud storage buckets create "gs://$BUCKET" --project "$PROJECT" --location "$REGION"

gcloud run deploy "$SERVICE" \
  --project "$PROJECT" --region "$REGION" \
  --source . \
  --allow-unauthenticated \
  --max-instances 1 --concurrency 40 --memory 1Gi --timeout 300 \
  --set-env-vars "W2APP_DATA=/data,W2APP_TOKEN=$W2APP_TOKEN" \
  --add-volume "name=runs,type=cloud-storage,bucket=$BUCKET" \
  --add-volume-mount "volume=runs,mount-path=/data"

URL=$(gcloud run services describe "$SERVICE" --project "$PROJECT" \
      --region "$REGION" --format 'value(status.url)')
echo
echo "Deployed: $URL"
echo "Console:  open $URL and paste the token when prompted."
echo "Runner:   python3 runner/w2_runner.py --server $URL --token '$W2APP_TOKEN'"
