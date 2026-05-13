#!/usr/bin/env bash
# Bootstrap the digital-maturity-assessor GCP project for Cloud Run.
#
# Idempotent: re-running is safe.
#
# Prereqs (one-time, manual):
#   * gcloud auth login
#   * gcloud config set project digital-maturity-assessor
#   * Billing enabled on the project.
#
# Usage:
#   chmod +x infra/setup.sh
#   ./infra/setup.sh

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-digital-maturity-assessor}"
REGION="${REGION:-us-central1}"
REPO="${REPO:-capability-intelligence}"
RUNTIME_SA="capability-intelligence"
RUNTIME_SA_EMAIL="${RUNTIME_SA}@${PROJECT_ID}.iam.gserviceaccount.com"

echo "▶ project = $PROJECT_ID  region = $REGION"
gcloud config set project "$PROJECT_ID" >/dev/null
gcloud config set run/region "$REGION"  >/dev/null

# ─── 1. Enable APIs ────────────────────────────────────────────────────────
echo "▶ enabling APIs"
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  firestore.googleapis.com \
  storage.googleapis.com \
  bigquery.googleapis.com \
  cloudscheduler.googleapis.com \
  cloudtasks.googleapis.com \
  pubsub.googleapis.com \
  aiplatform.googleapis.com \
  documentai.googleapis.com \
  dlp.googleapis.com \
  drive.googleapis.com \
  sheets.googleapis.com \
  iam.googleapis.com \
  iap.googleapis.com \
  monitoring.googleapis.com \
  logging.googleapis.com \
  cloudtrace.googleapis.com \
  identitytoolkit.googleapis.com \
  --project="$PROJECT_ID"

# ─── 2. Artifact Registry ──────────────────────────────────────────────────
echo "▶ Artifact Registry repo: $REPO"
gcloud artifacts repositories describe "$REPO" --location="$REGION" >/dev/null 2>&1 || \
  gcloud artifacts repositories create "$REPO" \
    --repository-format=docker \
    --location="$REGION" \
    --description="capability-intelligence container images"

# ─── 3. Runtime service account ────────────────────────────────────────────
echo "▶ runtime service account: $RUNTIME_SA_EMAIL"
gcloud iam service-accounts describe "$RUNTIME_SA_EMAIL" >/dev/null 2>&1 || \
  gcloud iam service-accounts create "$RUNTIME_SA" \
    --display-name="Capability Intelligence runtime"

# Minimum roles to operate the service.
for role in \
  roles/datastore.user \
  roles/storage.objectAdmin \
  roles/bigquery.dataEditor \
  roles/bigquery.jobUser \
  roles/secretmanager.secretAccessor \
  roles/pubsub.publisher \
  roles/pubsub.subscriber \
  roles/cloudtasks.enqueuer \
  roles/aiplatform.user \
  roles/documentai.apiUser \
  roles/dlp.user \
  roles/logging.logWriter \
  roles/monitoring.metricWriter \
  roles/cloudtrace.agent \
  roles/run.invoker
do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$RUNTIME_SA_EMAIL" \
    --role="$role" --condition=None --quiet >/dev/null
done

# Cloud Build SA needs to deploy + read Secret Manager.
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
CB_SA="${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com"
for role in roles/run.admin roles/iam.serviceAccountUser roles/secretmanager.secretAccessor; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$CB_SA" \
    --role="$role" --condition=None --quiet >/dev/null
done

# ─── 4. Firestore (native mode, named DB "dma-assessor") ───────────────────
echo "▶ Firestore database: dma-assessor"
gcloud firestore databases describe --database=dma-assessor >/dev/null 2>&1 || \
  gcloud firestore databases create \
    --database=dma-assessor \
    --location="$REGION" \
    --type=firestore-native

# ─── 5. GCS buckets ────────────────────────────────────────────────────────
echo "▶ GCS buckets"
for suffix in sows-raw sows-redacted snapshots reports jira-raw news-raw; do
  bucket="gs://${PROJECT_ID}-${suffix}"
  if ! gcloud storage buckets describe "$bucket" >/dev/null 2>&1; then
    gcloud storage buckets create "$bucket" \
      --location="$REGION" \
      --uniform-bucket-level-access \
      --public-access-prevention
  fi
  case "$suffix" in
    sows-raw|snapshots|jira-raw|news-raw)
      gcloud storage buckets update "$bucket" --versioning >/dev/null
      ;;
  esac
done

# ─── 6. BigQuery datasets ──────────────────────────────────────────────────
echo "▶ BigQuery datasets"
for ds in \
  capability_catalogue \
  continuous_validation \
  benchmarks \
  lifecycle \
  vendor_intel \
  evals \
  evidence_index \
  reasoning_chains \
  cost_tracking
do
  bq --project_id="$PROJECT_ID" show "$ds" >/dev/null 2>&1 || \
    bq --project_id="$PROJECT_ID" --location="$REGION" mk \
      --dataset --description="capability-intelligence: $ds" "$ds"
done

# ─── 7. Secrets ────────────────────────────────────────────────────────────
echo "▶ Secret Manager — create empty secrets if missing"
for secret in anthropic-api-key google-oauth-client-secret jira-api-token; do
  gcloud secrets describe "$secret" >/dev/null 2>&1 || \
    gcloud secrets create "$secret" --replication-policy=automatic
done

# ─── 8. Self-validation ────────────────────────────────────────────────────
echo "▶ self-validating provisioned resources"
fail=0
check() { if eval "$2" >/dev/null 2>&1; then echo "  ✓ $1"; else echo "  ✗ $1"; fail=$((fail+1)); fi; }

check "Artifact Registry repo"   "gcloud artifacts repositories describe $REPO --location=$REGION"
check "Runtime SA"               "gcloud iam service-accounts describe $RUNTIME_SA_EMAIL"
check "Firestore dma-assessor"   "gcloud firestore databases describe --database=dma-assessor"
for suffix in sows-raw sows-redacted snapshots reports jira-raw news-raw; do
  check "Bucket $suffix"         "gcloud storage buckets describe gs://${PROJECT_ID}-${suffix}"
done
for ds in capability_catalogue continuous_validation benchmarks lifecycle vendor_intel evals evidence_index reasoning_chains cost_tracking; do
  check "BQ dataset $ds"         "bq --project_id=$PROJECT_ID show $ds"
done
for s in anthropic-api-key google-oauth-client-secret jira-api-token; do
  check "Secret $s"              "gcloud secrets describe $s"
done

if [ $fail -gt 0 ]; then
  echo "✗ $fail resource(s) missing — see ✗ marks above."
  exit 1
fi

cat <<'EOF'

✓ Bootstrap complete — all resources validated.

Next steps:
  1. Populate secrets:
       echo -n '<KEY>' | gcloud secrets versions add anthropic-api-key --data-file=-
       echo -n '<KEY>' | gcloud secrets versions add google-oauth-client-secret --data-file=-
       echo -n '<KEY>' | gcloud secrets versions add jira-api-token --data-file=-
  2. Trigger the first deploy:
       gcloud builds submit \
         --config=apps/capability-intelligence/infra/cloudbuild.yaml \
         --project=digital-maturity-assessor apps/capability-intelligence
  3. Map a custom domain (optional):
       gcloud beta run domain-mappings create \
         --service=capability-intelligence-api --domain=capability.zennify.com \
         --region=us-central1
EOF
