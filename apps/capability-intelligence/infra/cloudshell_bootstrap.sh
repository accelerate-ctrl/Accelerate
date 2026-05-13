#!/usr/bin/env bash
# Cloud Shell one-shot deploy from a fresh clone.
#
# Usage (from any Cloud Shell home directory):
#
#   curl -sSL https://raw.githubusercontent.com/accelerate-ctrl/Accelerate/claude/deploy-zennify-cloud-run-AUdu6/apps/capability-intelligence/infra/cloudshell_bootstrap.sh | bash
#
# Or, if you already have the repo cloned:
#
#   bash /path/to/apps/capability-intelligence/infra/cloudshell_bootstrap.sh
#
# Steps:
#   1. Clone (or pull) the repo at $HOME/Accelerate.
#   2. chmod +x on every script under infra/ (git on Cloud Shell sometimes
#      strips the exec bit).
#   3. Run infra/setup.sh — creates APIs, SA, Firestore, GCS, BQ, secrets.
#   4. Stop here, print the secret-population commands. Operator pastes the
#      live keys interactively (no key ever lands in this script).
#   5. After keys are pasted, run `gcloud builds submit` to deploy.
#
# Idempotent — re-running is safe.

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-digital-maturity-assessor}"
REGION="${REGION:-us-central1}"
BRANCH="${BRANCH:-claude/deploy-zennify-cloud-run-AUdu6}"
REPO_URL="${REPO_URL:-https://github.com/accelerate-ctrl/Accelerate.git}"
WORKDIR="${WORKDIR:-$HOME/Accelerate}"

echo "▶ project = $PROJECT_ID   region = $REGION"
echo "▶ workdir = $WORKDIR        branch = $BRANCH"

gcloud config set project "$PROJECT_ID" >/dev/null
gcloud config set run/region "$REGION"  >/dev/null

# 1. Clone or pull.
if [ -d "$WORKDIR/.git" ]; then
  echo "▶ updating existing clone"
  git -C "$WORKDIR" fetch origin "$BRANCH"
  git -C "$WORKDIR" checkout "$BRANCH"
  git -C "$WORKDIR" pull --ff-only origin "$BRANCH"
else
  echo "▶ cloning $REPO_URL"
  git clone --branch "$BRANCH" --single-branch "$REPO_URL" "$WORKDIR"
fi

APP_DIR="$WORKDIR/apps/capability-intelligence"
cd "$APP_DIR"

# 2. Restore exec bit (Cloud Shell git checkout occasionally drops it).
chmod +x infra/*.sh

# 3. Bootstrap GCP resources.
echo "▶ running infra/setup.sh"
./infra/setup.sh

# 4. Tell the operator what to do next.
cat <<EOF

────────────────────────────────────────────────────────────────────────
Bootstrap done. Two manual steps remain.

A. Populate Secret Manager (paste keys interactively, never as args):

   read -srp 'Anthropic API key: '       ANTHROPIC_KEY   && echo
   read -srp 'Google OAuth secret: '     OAUTH_SECRET    && echo
   read -srp 'Jira API token (optional): ' JIRA_TOKEN    && echo

   echo -n "\$ANTHROPIC_KEY" | gcloud secrets versions add anthropic-api-key         --data-file=-
   echo -n "\$OAUTH_SECRET"  | gcloud secrets versions add google-oauth-client-secret --data-file=-
   echo -n "\$JIRA_TOKEN"    | gcloud secrets versions add jira-api-token            --data-file=-
   unset ANTHROPIC_KEY OAUTH_SECRET JIRA_TOKEN

B. Trigger the first deploy:

   cd $APP_DIR
   gcloud builds submit \\
     --config=infra/cloudbuild.yaml \\
     --project=$PROJECT_ID .

Then verify:

   URL=\$(gcloud run services describe capability-intelligence-api \\
           --region=$REGION --format='value(status.url)')
   curl -fsS "\$URL/api/health"
   curl -fsS "\$URL/api/ready" | jq
────────────────────────────────────────────────────────────────────────
EOF
