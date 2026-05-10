#!/usr/bin/env bash
# Zennify Capability Intelligence — GCP setup script.
#
# Usage:
#   GCP_PROJECT_ID=digital-maturity-assessor REGION=us-central1 \
#     bash apps/capability-intelligence/scripts/setup.sh
#
# Idempotent: safe to re-run. Prints copy-paste config block at end.
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-digital-maturity-assessor}"
REGION="${REGION:-us-central1}"
FIRESTORE_DB_ID="${FIRESTORE_DB_ID:-dma-assessor}"
SA_NAME="capability-intel-sa"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
SA_KEY_FILE="${SA_KEY_FILE:-./capability-intel-sa.json}"
ARTIFACT_REPO="capability-intelligence"
DRIVE_FOLDER_ID="${DRIVE_FOLDER_ID:-1rF9zdx1qF7BJ9t21eFdvZQW11Y5dUjy3}"

echo "==> Project: ${PROJECT_ID} | Region: ${REGION} | Firestore DB: ${FIRESTORE_DB_ID}"
gcloud config set project "${PROJECT_ID}" >/dev/null

echo "==> Enabling APIs (one-time)…"
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  firestore.googleapis.com \
  bigquery.googleapis.com \
  aiplatform.googleapis.com \
  secretmanager.googleapis.com \
  cloudscheduler.googleapis.com \
  pubsub.googleapis.com \
  cloudtasks.googleapis.com \
  dlp.googleapis.com \
  documentai.googleapis.com \
  drive.googleapis.com \
  sheets.googleapis.com \
  iamcredentials.googleapis.com \
  iam.googleapis.com \
  identitytoolkit.googleapis.com \
  storage.googleapis.com \
  --quiet

echo "==> Creating service account ${SA_EMAIL}…"
if ! gcloud iam service-accounts describe "${SA_EMAIL}" >/dev/null 2>&1; then
  gcloud iam service-accounts create "${SA_NAME}" \
    --display-name "Capability Intelligence Service Account"
else
  echo "   already exists"
fi

echo "==> Granting roles to ${SA_EMAIL}…"
for role in \
  roles/datastore.user \
  roles/bigquery.dataEditor \
  roles/bigquery.jobUser \
  roles/storage.objectAdmin \
  roles/aiplatform.user \
  roles/dlp.user \
  roles/documentai.apiUser \
  roles/secretmanager.secretAccessor \
  roles/run.invoker \
  roles/logging.logWriter \
  roles/cloudtrace.agent
do
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${SA_EMAIL}" --role="${role}" \
    --condition=None --quiet >/dev/null
done

echo "==> Generating SA key (writes to ${SA_KEY_FILE})…"
if [ ! -f "${SA_KEY_FILE}" ]; then
  gcloud iam service-accounts keys create "${SA_KEY_FILE}" --iam-account "${SA_EMAIL}"
else
  echo "   key file already exists; not overwriting"
fi

echo "==> Creating Firestore database '${FIRESTORE_DB_ID}' in MongoDB-compatibility mode…"
if ! gcloud firestore databases describe --database="${FIRESTORE_DB_ID}" >/dev/null 2>&1; then
  # Firestore with MongoDB compatibility — flag name as of 2025-Q1.
  # If the flag is renamed in your gcloud version, see RUNBOOK.md.
  gcloud firestore databases create \
    --database="${FIRESTORE_DB_ID}" \
    --location="${REGION}" \
    --type=firestore-native \
    --edition=enterprise \
    --quiet || {
      echo "WARN: enterprise/MongoDB-compatible flag not supported by this gcloud."
      echo "      Create the database manually in the Cloud Console with"
      echo "      'Firestore Enterprise edition' + 'MongoDB compatibility' enabled,"
      echo "      then re-run this script."
      exit 1
    }
else
  echo "   already exists"
fi

echo "==> Creating GCS buckets…"
for b in sows-raw sows-redacted snapshots reports jira-raw news-raw firestore-backups; do
  BUCKET="${PROJECT_ID}-${b}"
  if ! gcloud storage buckets describe "gs://${BUCKET}" >/dev/null 2>&1; then
    gcloud storage buckets create "gs://${BUCKET}" --location="${REGION}" --uniform-bucket-level-access
  fi
done

echo "==> Creating BigQuery datasets…"
for d in capability_catalogue continuous_validation benchmarks lifecycle vendor_intel evals evidence_index reasoning_chains cost_tracking audit_events; do
  bq --location="${REGION}" mk --dataset --description="$d" "${PROJECT_ID}:${d}" 2>/dev/null || true
done

echo "==> Creating Artifact Registry repo for the container image…"
if ! gcloud artifacts repositories describe "${ARTIFACT_REPO}" --location="${REGION}" >/dev/null 2>&1; then
  gcloud artifacts repositories create "${ARTIFACT_REPO}" \
    --repository-format=docker --location="${REGION}" --description="Capability Intelligence images"
fi

echo
echo "============================================================"
echo "DONE. Copy these values into apps/capability-intelligence/.env:"
echo "============================================================"
cat <<EOF
ENV=prod
USE_GCP=true
GCP_PROJECT_ID=${PROJECT_ID}
GCP_REGION=${REGION}
FIRESTORE_DATABASE_ID=${FIRESTORE_DB_ID}
GOOGLE_APPLICATION_CREDENTIALS=${SA_KEY_FILE}

DRIVE_PILLARS_FOLDER_ID=${DRIVE_FOLDER_ID}

BUCKET_SOWS_RAW=${PROJECT_ID}-sows-raw
BUCKET_SOWS_REDACTED=${PROJECT_ID}-sows-redacted
BUCKET_SNAPSHOTS=${PROJECT_ID}-snapshots
BUCKET_REPORTS=${PROJECT_ID}-reports
BUCKET_JIRA_RAW=${PROJECT_ID}-jira-raw
BUCKET_NEWS_RAW=${PROJECT_ID}-news-raw

# Firestore MongoDB-compatibility connection string.
# After 'gcloud firestore databases create' above succeeds, look up the
# host in the Cloud Console (Firestore -> Databases -> ${FIRESTORE_DB_ID}
# -> Connection details -> MongoDB endpoint) and paste below:
FIRESTORE_MONGO_URI=mongodb://${SA_EMAIL}:<TOKEN>@<HOST>:443/${FIRESTORE_DB_ID}?authMechanism=MONGODB-OIDC&loadBalanced=true&tls=true
EOF
echo
echo "FINAL STEPS YOU MUST DO MANUALLY:"
echo "  1. Share the Drive folder ${DRIVE_FOLDER_ID} with ${SA_EMAIL} (Viewer)."
echo "  2. Look up the Firestore MongoDB endpoint host in the Console"
echo "     and paste the FIRESTORE_MONGO_URI value into your .env."
echo "  3. (Optional, for Firebase Auth domain restriction)"
echo "     Configure your Firebase project to allow only @zennify.com sign-ins."
