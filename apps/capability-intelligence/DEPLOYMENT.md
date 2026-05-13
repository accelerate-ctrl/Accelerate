# Deployment Guide — Zennify Capability Intelligence

**Audience**: A platform engineer at Zennify standing the system up from
scratch. Read top-to-bottom; every step is a single command.

**Result**: A live Cloud Run service serving the SPA + 14 Cloud Run Jobs
running on Scheduler crons + Pub/Sub event bus + Cloud Tasks DLQ + Cloud
Monitoring alerts + the full RAG / lifecycle / digest pipeline operating
end-to-end on Anthropic + Vertex AI.

---

## Quick start — `digital-maturity-assessor`

For the production target (GCP project **`digital-maturity-assessor`**,
project number **`306195530103`**, region **`us-central1`**).

Every block below is self-contained: each one sets its own working
directory absolutely, so it doesn't matter where Cloud Shell drops you.
Run them in order from a fresh Cloud Shell session.

### 1) Clone or update the repo (idempotent)

Open **Cloud Shell** (https://shell.cloud.google.com) and paste this
block verbatim. It works whether `~/Accelerate` already exists or not,
and whether you've been recycled by Cloud Shell's idle timeout:

```bash
gcloud config set project digital-maturity-assessor
gcloud config set run/region us-central1

BRANCH=claude/deploy-zennify-cloud-run-AUdu6
REPO_URL=https://github.com/accelerate-ctrl/Accelerate.git
WORKDIR="$HOME/Accelerate"

if [ -d "$WORKDIR/.git" ]; then
  git -C "$WORKDIR" fetch origin "$BRANCH"
  git -C "$WORKDIR" checkout "$BRANCH"
  git -C "$WORKDIR" reset --hard "origin/$BRANCH"
else
  rm -rf "$WORKDIR"
  git clone --branch "$BRANCH" --single-branch "$REPO_URL" "$WORKDIR"
fi

cd "$WORKDIR/apps/capability-intelligence"
chmod +x infra/*.sh
echo "▶ now in $(pwd)"
ls infra/
```

You should see at minimum `setup.sh`, `cloudbuild.yaml`, `service.yaml`,
`lint_cloudbuild.py`, `cloudshell_bootstrap.sh`.

> One-liner alternative (downloads + runs the bootstrap script): `curl
> -sSL https://raw.githubusercontent.com/accelerate-ctrl/Accelerate/claude/deploy-zennify-cloud-run-AUdu6/apps/capability-intelligence/infra/cloudshell_bootstrap.sh | bash`

### 2) Lint the build pipeline locally (catches the common bugs)

```bash
cd "$HOME/Accelerate/apps/capability-intelligence"
python3 infra/lint_cloudbuild.py infra/cloudbuild.yaml
# expected: ✓ infra/cloudbuild.yaml — clean for both manual + triggered builds
```

If you ever modify `cloudbuild.yaml`, run this first — it simulates
Cloud Build's substitution engine + `bash -n`s every rendered script,
and flags unescaped `$VAR`s, malformed image tags from empty
`SHORT_SHA`, missing substitution declarations, etc.

### 3) Provision the project (idempotent — safe to re-run)

```bash
cd "$HOME/Accelerate/apps/capability-intelligence"
./infra/setup.sh
```

`setup.sh` enables 21 APIs (in two ≤20-API batches per Google's limit),
creates Artifact Registry, the runtime SA (+ 14 IAM bindings), Firestore
`dma-assessor`, 6 GCS buckets, 9 BQ datasets, and 3 empty Secret Manager
secrets. It self-validates at the end and exits non-zero if any
resource is missing.

### 4) Populate the three secrets

Paste keys interactively (the leading space makes bash skip history):

```bash
 read -srp 'Anthropic API key:   ' KEY1 && echo
 read -srp 'OAuth client secret: ' KEY2 && echo
 read -srp 'Jira API token:      ' KEY3 && echo
 printf %s "$KEY1" | gcloud secrets versions add anthropic-api-key          --data-file=-
 printf %s "$KEY2" | gcloud secrets versions add google-oauth-client-secret --data-file=-
 printf %s "$KEY3" | gcloud secrets versions add jira-api-token             --data-file=-
 unset KEY1 KEY2 KEY3
```

### 4b) Share Drive sources with the runtime SA

The deployed Cloud Run service runs as the **runtime service account**.
It can call the Drive API, but each Drive folder/shared-drive must be
explicitly shared with that SA. The SA email is:

```
capability-intelligence@digital-maturity-assessor.iam.gserviceaccount.com
```

Two locations need access (both pre-wired in `service.yaml`):

1. **Catalogue folder** (Pillar 1–4 .xlsx, auto-version-picked)
   → https://drive.google.com/drive/folders/1rF9zdx1qF7BJ9t21eFdvZQW11Y5dUjy3
   → click **Share**, paste the SA email above, role: **Viewer**.

2. **SOWs shared drive** (deep-recursive walk through every
   `Client/Project/phase/...` subfolder)
   → https://drive.google.com/drive/folders/0AFm0q8PCUPy-Uk9PVA
   → this is a **Shared Drive** (ID starts with `0A`), which has its
   own ACL system: open the drive, click the drive name at the top →
   **Manage members** → **Add member** → SA email, role: **Viewer**
   (or **Content manager** if write is later needed).
   Sharing a *folder inside* a Shared Drive is NOT enough — the SA
   must be a member of the drive itself.

Without this step every ingest will return 403/empty and the SPA will
look empty.

### 5) Deploy

```bash
cd "$HOME/Accelerate/apps/capability-intelligence"
gcloud builds submit \
  --config=infra/cloudbuild.yaml \
  --project=digital-maturity-assessor .
```

The pipeline (~6–8 minutes):

1. `resolve-tag` — write the image tag (`$SHORT_SHA` or `$BUILD_ID`) to `/workspace/.tag`
2. `backend-tests` — pytest + ruff
3. `frontend-tests` — vitest + Vite build
4. `docker-build` — multi-stage build, both SHA-tag and `:latest`
5. `docker-push` — push both tags to Artifact Registry
6. `deploy-api` — sed `IMAGE_TAG` into `service.yaml`, `gcloud run services replace`
7. `deploy-jobs` — refresh image on each Cloud Run Job (tolerates missing jobs on first deploy)
8. `smoke` — curl `/api/health` 5× with backoff; build fails if no 200

### 6) Verify the live service

```bash
URL=$(gcloud run services describe capability-intelligence-api \
        --region=us-central1 --format='value(status.url)')
echo "service URL: $URL"

curl -fsS "$URL/api/health"             # → {"status":"ok",...}
curl -fsI "$URL/"                       # SPA root, HEAD-200 (HEAD probes work)
curl -fsS "$URL/api/ready"        | jq  # echoes project, region, revision
curl -fsS "$URL/api/auth/config"  | jq  # echoes the OAuth client_id (no secret)
curl -sI  "$URL/api/docs"               # Swagger UI is reachable
```

### 7) Wire the OAuth client to the new URL

The deployed service runs with `AUTH_MODE=google_oauth`. The SPA loads
`https://accounts.google.com/gsi/client` and renders a sign-in gate
that posts the user's Google ID token to every `/api/*` request; the
backend verifies it against `GOOGLE_OAUTH_CLIENT_ID` and rejects
emails outside `AUTH_ALLOWED_DOMAIN`.

Cloud Console → **APIs & Services → Credentials → web client
`306195530103-…`**:

1. **Authorized JavaScript origins**: add the Cloud Run URL from
   step 6 — this is mandatory for Google Identity Services to issue
   ID tokens to the SPA. Example:
   `https://capability-intelligence-api-…uc.a.run.app`.
2. **Authorized redirect URIs**: add `$URL/api/auth/google/callback`
   (n8n's `https://oauth.n8n.cloud/oauth2/callback` is already pre-set).
3. **OAuth consent screen → Authorized domains**: `zennify.com`.
4. **OAuth consent screen → Test users**: add operator emails until
   the consent screen is published.

Verify after these are saved (allow ~5 min for Google to propagate):

```bash
# Open $URL in a browser. The SignInGate appears.
# Click "Continue with Google" → pick a @zennify.com account.
# After consent the SPA loads and all /api/* requests carry a real
# ID token (no more dev fallback).
```

### 8) Pull all sources (first ingest)

The SPA's "Pull all sources" button (top-right) now POSTs
`/api/ingest/refresh-all` which fans out to all 7 source ingests:
catalogue → SOWs → stories → news → vendors → benchmarks → client
journeys. You can also trigger it from the CLI:

```bash
URL=$(gcloud run services describe capability-intelligence-api \
        --region=us-central1 --format='value(status.url)')

# AUTH_MODE=dev: paste your email as the bearer token
TOKEN='dev-mishley.otiende@zennify.com'

curl -fsS -X POST -H "Authorization: Bearer $TOKEN" \
     -H 'Content-Type: application/json' -d '{}' \
     "$URL/api/ingest/refresh-all" | jq
```

Expect `sources_succeeded: 7` once Drive ACLs are in place. If any
source fails, its `error` field surfaces the reason
(e.g. Jira creds missing, Drive folder not shared, etc.). Tail the
revision logs for detail:

```bash
gcloud logging read \
  'resource.type=cloud_run_revision AND resource.labels.service_name=capability-intelligence-api' \
  --project=digital-maturity-assessor --limit=80 \
  --format='value(textPayload,jsonPayload.message)'
```

> **Never commit live secrets to the repo.** Even temporary "test" keys
> end up in git history, Cloud Build logs, and forks. Always populate
> Secret Manager interactively as in step 4.

### Troubleshooting — what each past failure mode looked like

| Symptom | Root cause | Fixed in |
|---|---|---|
| `-bash: cd: ~/Accelerate: No such file or directory` | Cloud Shell idle-recycled the home dir | step 1 above creates it idempotently |
| `Permission denied` on `./infra/setup.sh` | git checkout dropped +x | step 1's `chmod +x infra/*.sh` |
| `Number of services must not exceed the maximum batch size (20)` | `setup.sh` enabled 21 APIs at once | `3a63fd8` split into 11 + 10 |
| `key in the template "JOB" is not a valid built-in substitution` | unescaped `$VAR` in step args | `77daad8` escaped `$$JOB`, `$$URL`, `$$IMAGE` |
| `invalid image name "…/api:"` | `${SHORT_SHA}` empty on manual builds | `f55520e` resolves tag via `$SHORT_SHA`/`$BUILD_ID` fallback |
| `gcloud run services replace … --image=…` rejected | `replace` doesn't take `--image` | `0cdd428` switched to sed-render then replace |
| `Secret NOT_FOUND` | setup.sh hadn't run yet so secrets didn't exist | `setup.sh` now creates + self-validates |
| `HEAD /` returned 405 | SPA fallback was GET-only | this commit — `api_route(methods=["GET","HEAD"])` |


### Pre-configured values

| What | Value | Where |
|------|-------|-------|
| GCP project | `digital-maturity-assessor` | `config.py`, `service.yaml`, `setup.sh` |
| Project number | `306195530103` | `service.yaml` |
| Region | `us-central1` | everywhere |
| Cloud Run service | `capability-intelligence-api` | `service.yaml`, `cloudbuild.yaml` |
| Runtime SA | `capability-intelligence@…iam.gserviceaccount.com` | `service.yaml` |
| OAuth web client_id | `306195530103-ub6t46i8sd9q1eatpt6dgo0i9811mnrp.apps.googleusercontent.com` | `service.yaml`, `auth.py` |
| OAuth redirect URI | `https://oauth.n8n.cloud/oauth2/callback` | `service.yaml` |
| Firestore database | `dma-assessor` (native mode, `us-central1`) | `setup.sh` |
| GCS bucket prefix | `digital-maturity-assessor-*` | `setup.sh`, `service.yaml` |
| BQ datasets | 9 (`capability_catalogue`, …, `cost_tracking`) | `setup.sh` |
| Secret Manager | `anthropic-api-key`, `google-oauth-client-secret`, `jira-api-token` | `setup.sh` |

### OAuth setup (one-time, after first deploy)

In Cloud Console → APIs & Services → Credentials → the web client
`306195530103-…`:

1. **Authorized JavaScript origins**:
   - `https://capability-intelligence-api-<hash>-uc.a.run.app` (after first deploy)
   - `https://capability.zennify.com` (after custom domain mapping)
   - `https://oauth.n8n.cloud`
2. **Authorized redirect URIs**:
   - `https://oauth.n8n.cloud/oauth2/callback` (already pre-set)
   - `https://capability-intelligence-api-<hash>-uc.a.run.app/api/auth/google/callback`
3. OAuth consent screen → "Authorized domains": `zennify.com`.

### n8n integration

In n8n cloud, when creating a **Google OAuth2** credential:

| Field | Value |
|-------|-------|
| Authorization URL | `https://accounts.google.com/o/oauth2/auth` |
| Access Token URL  | `https://oauth2.googleapis.com/token` |
| Client ID         | `306195530103-ub6t46i8sd9q1eatpt6dgo0i9811mnrp.apps.googleusercontent.com` |
| Client Secret     | from Secret Manager (`google-oauth-client-secret`) |
| Scope             | `openid email profile` |

n8n will redirect through `https://oauth.n8n.cloud/oauth2/callback` —
already in the allowed redirect list. The ID token it returns can be
POSTed to `$URL/api/auth/google/callback` to obtain a verified user
identity (the SPA backend verifies it against Google JWKS with
`aud == client_id`).

### Smoke + stress test the live service

```bash
URL=$(gcloud run services describe capability-intelligence-api \
        --region=us-central1 --format='value(status.url)')

# Health (no auth)
curl -fsS "$URL/api/health"
curl -fsS "$URL/api/ready" | jq
curl -fsS "$URL/api/auth/config" | jq

# Authenticated /me (using a Google ID token from the SPA login)
TOKEN="…id-token…"
curl -fsS "$URL/api/auth/me" -H "Authorization: Bearer $TOKEN"

# Stress: 200 RPS for 30s against /api/health (install `hey` first)
hey -z 30s -q 200 -c 50 "$URL/api/health"   # p95 should be < 300ms
```

Pre-merge stress test (local uvicorn, same Dockerfile, current commit):

| Endpoint | Load | Result |
|---|---|---|
| `/api/health` | 1000 req @ 50 conc | 596 RPS, p95 9.6 ms, p99 14.6 ms, 0 fails |
| `/api/auth/google/callback` (bogus) | 500 req @ 25 conc | all 400 in < 50 ms p99 |
| `/api/graph/sigma?limit=200` | 100 @ 20 conc | p95 39 ms, 100% 200s |
| Backend pytest | 192 tests | 192/192 pass in 76 s |
| Frontend vitest + build | 42 tests | 42/42 pass, 257 KB gzip JS |

### Rollback

```bash
gcloud run revisions list --service=capability-intelligence-api \
  --region=us-central1

gcloud run services update-traffic capability-intelligence-api \
  --to-revisions=<prev-revision>=100 \
  --region=us-central1
```

---

## Detailed walkthrough

The rest of this document describes the same steps in detail for
operators who want to understand each piece or adapt to a different
project.

---

## 0. Prerequisites

| Tool       | Version                       | Notes                                |
|------------|-------------------------------|--------------------------------------|
| Python     | 3.12                          | Backend                              |
| Node       | 20 LTS                        | Frontend                             |
| Docker     | 25+                           | Local stack + image build            |
| `gcloud`   | latest                        | GCP CLI                              |
| `terraform`| ≥ 1.5                         | IaC                                  |
| GCP project| with billing enabled          | One project hosts the whole stack    |

Recommended **regions / zones**: `us-central1` for everything (Cloud Run,
Firestore-MongoDB, Pub/Sub, Vertex AI). Mixing regions adds latency to
every consultant-loop call.

---

## 1. Local development (no GCP needed)

```bash
git clone <repo> && cd accelerate/apps/capability-intelligence

# Backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
LOCAL_CATALOGUE_DIR=$(realpath ../test-data) \
  LOCAL_REPOSITORY_PATH=/tmp/repo.json \
  USE_GCP=false \
  python -m uvicorn app.main:app --port 8080 --reload

# Frontend (in a second shell)
cd ../frontend
npm install
npm run dev      # Vite serves at http://localhost:5173
```

Open <http://localhost:5173>. Click any **Refresh** button to ingest the
attached test data; everything works in dev mode without external creds.

Run any Cloud Run Job locally:

```bash
python -m app.jobs.runner news_poll
python -m app.jobs.runner digest_quarterly --arg period=2026-Q2
```

---

## 2. GCP project bootstrap

```bash
export PROJECT_ID=digital-maturity-assessor
export REGION=us-central1

gcloud projects create $PROJECT_ID --name="Zennify Capability Intelligence"
gcloud config set project $PROJECT_ID
gcloud beta billing projects link $PROJECT_ID --billing-account=<BILLING_ID>

gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  cloudscheduler.googleapis.com \
  pubsub.googleapis.com \
  cloudtasks.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  firestore.googleapis.com \
  bigquery.googleapis.com \
  storage.googleapis.com \
  aiplatform.googleapis.com \
  dlp.googleapis.com \
  monitoring.googleapis.com \
  logging.googleapis.com \
  cloudtrace.googleapis.com
```

---

## 3. Firestore (MongoDB compatibility mode)

```bash
gcloud alpha firestore databases create \
  --database=dma-assessor \
  --location=$REGION \
  --type=firestore-native \
  --edition=enterprise
```

The repository abstraction (`backend/app/services/repository.py`)
auto-uses `MongoRepository` when `USE_GCP=true`; ADR-0005 records the
Firestore-MongoDB-compat choice.

---

## 4. Secrets

```bash
# Anthropic
echo -n "$ANTHROPIC_API_KEY" | gcloud secrets create anthropic-api-key --data-file=-

# (Optional) Atlassian Jira
echo -n "$JIRA_API_TOKEN" | gcloud secrets create jira-api-token --data-file=-

# (Optional) BuiltWith / Wappalyzer
echo -n "$BUILTWITH_API_KEY" | gcloud secrets create builtwith-api-key --data-file=-
echo -n "$WAPPALYZER_API_KEY" | gcloud secrets create wappalyzer-api-key --data-file=-
```

Grant the Cloud Run + Cloud Run Jobs service account access:

```bash
SA="${PROJECT_ID}-compute@developer.gserviceaccount.com"
for SECRET in anthropic-api-key jira-api-token builtwith-api-key wappalyzer-api-key; do
  gcloud secrets add-iam-policy-binding $SECRET \
    --member="serviceAccount:$SA" \
    --role="roles/secretmanager.secretAccessor" 2>/dev/null || true
done
```

---

## 5. GCS buckets

```bash
for B in sows-raw sows-redacted snapshots reports jira-raw news-raw; do
  gcloud storage buckets create gs://${PROJECT_ID}-${B} \
    --location=$REGION \
    --uniform-bucket-level-access
done
```

`config/canonical_sources.yml` referenes `bucket_*` entries from
`backend/app/config.py`; set those env vars in the Cloud Run service
template if you customise bucket names.

---

## 6. Drive setup (catalogue + SOWs)

1. Create a Drive shared-drive **Zennify Capability Intelligence** with a
   service-account share; note the folder ID (`drive_pillars_folder_id`).
2. Inside, drop the four pillar workbooks (`Pillar 1`, `Pillar 2`, …).
3. Create a sibling folder **SOWs** with status subfolders (`active/`,
   `prospect/`, `inactive/`, `archived/`); note its folder ID
   (`drive_sows_folder_id`).
4. Share both with the project's compute SA email.

The `gen_stories_export.xlsx` lives next to the pillar files; ingest auto-
detects.

---

## 7. Build + push the image (manual one-shot)

The Cloud Build pipeline does this on every push, but here's the manual
form for the first deploy:

```bash
gcloud artifacts repositories create capability-intelligence \
  --repository-format=docker \
  --location=$REGION

gcloud auth configure-docker ${REGION}-docker.pkg.dev

docker build -t ${REGION}-docker.pkg.dev/$PROJECT_ID/capability-intelligence/api:initial \
  apps/capability-intelligence

docker push ${REGION}-docker.pkg.dev/$PROJECT_ID/capability-intelligence/api:initial
```

The image's multi-stage Dockerfile builds the SPA → copies it into
`/app/static`, so the API serves both the JSON and the SPA at the same
URL.

---

## 8. Terraform — the full GCP plumbing in one apply

```bash
cd apps/capability-intelligence/infra/terraform
terraform init
terraform apply \
  -var="project_id=$PROJECT_ID" \
  -var="region=$REGION" \
  -var="image_tag=initial" \
  -var="anthropic_api_key=$(gcloud secrets versions access latest --secret=anthropic-api-key)"
```

Terraform creates:

- Artifact Registry repo
- Cloud Run service `capability-intelligence-api`
- 14 Cloud Run Jobs (one per scheduled task)
- 14 Cloud Scheduler entries (UTC crons)
- 5 Pub/Sub topics + 1 DLQ
- Secret Manager binding for the Anthropic key
- 2 Cloud Monitoring alert policies (high error rate, daily LLM spend)

Output:
```
service_url = "https://capability-intelligence-api-xxxxx.a.run.app"
```

Visit that URL — the SPA loads.

---

## 9. Wire the Cloud Build pipeline

```bash
gcloud builds triggers create github \
  --repo-name=accelerate \
  --repo-owner=zennify \
  --branch-pattern="^main$" \
  --build-config="apps/capability-intelligence/infra/cloudbuild.yaml" \
  --name="capability-intelligence-main"
```

Steps in `cloudbuild.yaml` (see file): backend pytest + ruff → frontend
npm test + build → docker build (multi-stage) → push → deploy API → image-
refresh every Cloud Run Job → smoke `/api/health`.

Trigger it manually for the first run:

```bash
gcloud builds submit \
  --config apps/capability-intelligence/infra/cloudbuild.yaml \
  apps/capability-intelligence
```

---

## 10. Bootstrap the catalogue + first runs

Open the SPA → **Mission Control → Refresh** to ingest the pillar files.
Then trigger the Batch 9 jobs manually (or wait for Scheduler):

```bash
for JOB in news-poll public-filings-poll sow-incremental jira-incremental \
           lifecycle-scoring-daily benchmark-extrapolation-run \
           digest-quarterly deep-audit-weekly; do
  gcloud run jobs execute $JOB --region=$REGION --wait
done
```

After this:
- Catalogue Explorer renders the 199-subcap tree (Pillar 1).
- SOW Library shows redacted SOWs.
- Knowledge Graph page renders the Cytoscape view (4014 nodes).
- Strategic Digest produces a quarterly digest with the Opus narratives.
- QA & Audit Dashboard surfaces audit findings.

---

## 11. Wire alerts → notification channels

Edit `infra/alerts/policies.yaml` to set notification channels (PagerDuty,
Slack, email). For Slack:

```bash
gcloud alpha monitoring channels create \
  --display-name="Slack #cap-intel" \
  --type=slack \
  --channel-labels=channel_name=#cap-intel \
  --user-labels=team=platform
```

Copy the resulting channel ID into the `notification_channels` list in
`infra/terraform/main.tf` and `terraform apply` again.

---

## 12. Production switches (the env-var control panel)

Set these on the Cloud Run service to flip dev → live. Defaults are dev-
mode (no external calls):

| Env var                       | Set to             | Effect                                     |
|-------------------------------|--------------------|--------------------------------------------|
| `USE_GCP`                     | `true`             | Switch from JSON repo → Firestore-MongoDB  |
| `ENV`                         | `prod`             | Production logging/structured-log mode     |
| `LLM_LIVE_MODE`               | `true`             | Real Anthropic + Vertex Gemini calls       |
| `ANTHROPIC_API_KEY`           | secret ref         | Anthropic Sonnet + Opus                    |
| `GCP_PROJECT_ID`              | `$PROJECT_ID`      | Vertex / Firestore / Pub/Sub project       |
| `VERTEX_REGION`               | `us-central1`      | Vertex AI region                           |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `https://…`        | Activates OpenTelemetry FastAPI traces     |
| `DRIVE_PILLARS_FOLDER_ID`     | Drive ID           | Production catalogue ingest                |
| `DRIVE_SOWS_FOLDER_ID`        | Drive ID           | Production SOW ingest                      |
| `JIRA_BASE_URL`               | URL                | Live Jira sync                             |
| `JIRA_EMAIL` + `JIRA_API_TOKEN` | secret ref       |                                            |
| `JIRA_PROJECT_KEYS`           | `["KEY1","KEY2"]`  | Project allow-list                         |
| `BUILTWITH_API_KEY` / `WAPPALYZER_API_KEY` | secret ref | Live technographics                |
| `SEC_EDGAR_EMAIL`             | email address      | Required for SEC EDGAR User-Agent          |
| `NEWS_FEEDS`                  | `["url1","url2"]`  | RSS news feeds (in addition to seed)       |
| `DAILY_SPEND_CEILING_USD`     | e.g. `100`         | Daily LLM spend cap (auto-throttle at 90%) |
| `ANTHROPIC_WEEKLY_BUDGET_USD` | e.g. `300`         | Weekly Anthropic budget (degrade to Gemini)|
| `COST_THROTTLE_PCT`           | default `0.9`      | Throttle threshold                         |
| `AUTH_MODE`                   | `firebase`         | Switch from dev token → Firebase ID token  |
| `FIREBASE_PROJECT_ID`         | `$PROJECT_ID`      | Firebase Auth                              |
| `AUTH_ALLOWED_DOMAIN`         | `zennify.com`      | Domain restriction                         |

```bash
gcloud run services update capability-intelligence-api --region=$REGION \
  --update-env-vars=USE_GCP=true,LLM_LIVE_MODE=true,ENV=prod,GCP_PROJECT_ID=$PROJECT_ID \
  --update-secrets=ANTHROPIC_API_KEY=anthropic-api-key:latest
```

Same env-var set should be propagated to every Cloud Run Job (Terraform
already does this via the `template.containers.env` blocks).

---

## 13. Drop in the Zennify icon-teal logo

```bash
gsutil cp logo.png gs://${PROJECT_ID}-snapshots/brand/logo.png
gsutil cp logo.svg gs://${PROJECT_ID}-snapshots/brand/logo.svg
```

Or in the container image, place them at `/app/backend/static/brand/logo.png`.
The PPTX renderer (`services/pptx_export.py::_add_logo_if_present`)
auto-includes the logo on the digest title slide. Without the asset the
slide falls back to the wordmark.

Brand palette (locked, mirrored across `frontend/tailwind.config.ts` and
`services/pptx_export.py`):

| Token             | Hex     | Use                          |
|-------------------|---------|------------------------------|
| zen-dark-green    | #1C4A4D | Headlines, sidebar bg        |
| zen-dark-teal     | #185F60 | Body text, muted UI          |
| **zen-teal**      | **#27BBAF** | **Icon teal — brand accent** |
| zen-light-teal    | #62D7B8 | Wordmark, hover states       |
| zen-light-green   | #B0EED3 | Cards, soft fills            |
| zen-white-green   | #E8F7F6 | Page background              |
| zen-light-orange  | #FFCB99 | Tier T4, warnings            |
| zen-orange        | #FE9732 | Tier T5, criticals           |

---

## 14. Acceptance smoke

```bash
URL=$(gcloud run services describe capability-intelligence-api \
  --region=$REGION --format='value(status.url)')

# Health
curl -sf $URL/api/health

# OpenAPI surface (proves all 30 routers loaded)
curl -s $URL/api/openapi.json | jq '.paths | keys | length'

# End-to-end (with live auth — substitute Firebase ID token)
TOKEN="<firebase-id-token>"
H="Authorization: Bearer $TOKEN"

curl -s -X POST -H "$H" "$URL/api/sheets/refresh/P1" | jq .pillars_loaded
curl -s -H "$H" "$URL/api/graph/summary" | jq '.nodes_total, .edges_total'
curl -s -X POST -H "$H" "$URL/api/lifecycle/recompute" | jq .state_distribution
curl -s -X POST -H "$H" -H "Content-Type: application/json" \
  "$URL/api/digest/generate" \
  -d '{"subvertical":"retail-banking","period":"2026-Q2","priority_limit":3}' \
  | jq '.digest_id, .priorities | length'
```

Expected:
- `nodes_total = 4014, edges_total = 12249` (Pillar 1)
- 199 subcaps scored across 6 lifecycle states
- A digest persists for retail-banking 2026-Q2 with 3 priorities
- All 8 gates `pass` once Anthropic returns real narratives

---

## 15. Day-2 operations

| Task                          | Where                                          |
|-------------------------------|------------------------------------------------|
| Run a job manually            | `gcloud run jobs execute <name>`               |
| Re-deploy after code change   | push to main → Cloud Build does it             |
| Rotate secrets                | `RUNBOOK.md §7 secret rotation`                |
| Investigate a 5xx alert       | `RUNBOOK.md §1 incident response`              |
| Clear the DLQ                 | `RUNBOOK.md §10 DLQ investigation`             |
| Cost spike                    | `RUNBOOK.md §6 cost spikes / auto-throttle`    |
| DR (RTO 4h / RPO 24h)         | `RUNBOOK.md §8 disaster recovery`              |
| Add new golden eval labels    | drop JSON into `test-data/eval/` + redeploy    |
| Add a peer cohort             | edit `config/peer_cohorts.yml` + redeploy      |
| Add a benchmark metric        | edit `config/benchmark_metrics.yml` + redeploy |

---

## 16. Verifying the agent's intelligence

The system is "agentic" through the **7-step consultant loop**
(`services/consultant_loop.py`). Every reply / digest / suggestion runs
through:

```
clarify → retrieve_internal → retrieve_external → synthesize →
adversarial → propose → gate → finalize
```

To prove the agent is doing the right thing:

```bash
# 1. Generate a digest with --extrapolate=true
curl -s -X POST -H "$H" "$URL/api/benchmarks/refresh?extrapolate=true" | jq .extrapolations_total
# Expected: ≥1 (sparse cohorts get AI-extrapolated points with chain_id back-link)

# 2. Trigger a chain manually
curl -s -X POST -H "$H" -H "Content-Type: application/json" \
  "$URL/api/reasoning-chains/run" \
  -d '{"query":"audit P1C1.1.1","sub_cap_id":"P1C1.1.1","model":"sonnet"}'
# Expected: chain_id; overall=pass when sources are well-grounded

# 3. Inspect the gate verdicts
curl -s -H "$H" "$URL/api/validation-gates/runs?limit=1" | jq '.[].results | map({name, verdict})'
# Expected: 8 gates — schema, citation, hallucination, freshness,
# novelty, bias, breaking_change, peer_coverage

# 4. Run the eval harness against bootstrap golden labels
curl -s -X POST -H "$H" "$URL/api/eval/run" | jq '.summary'
# Expected: digest_priorities mean_score > 0.5 (the lifecycle engine
# correctly surfaces P1C1.1.1, P1C1.1.2, P1C1.1.3 for retail-banking)
```

If any of those return unexpected shapes, see `RUNBOOK.md §5 drift
alerts` and `OPERATOR_GUIDE.md §30 run the eval harness`.

---

## Appendix A — Repo layout

```
apps/capability-intelligence/
├── backend/                     FastAPI app
│   ├── app/
│   │   ├── api/                 30 routers (one per domain)
│   │   ├── services/            32 services + llm/ subpackage
│   │   ├── jobs/                14 Cloud Run Jobs + runner CLI
│   │   ├── config.py            All env-var config
│   │   ├── observability.py     OpenTelemetry + structured logs
│   │   └── main.py              create_app() + telemetry install
│   └── tests/                   42 pytest files (319 tests)
├── frontend/                    Vite + React + Tailwind SPA
│   ├── src/pages/               29 pages (one per route)
│   ├── tailwind.config.ts       Brand tokens (locked)
│   └── tests/                   13 vitest files (45 tests)
├── config/                      10 YAML configs (cohorts, metrics, …)
├── test-data/                   Pillar 1 + SOWs + news + filings + eval
├── infra/
│   ├── terraform/main.tf        Single-file Terraform module
│   ├── cloudbuild.yaml          CI/CD pipeline
│   ├── service.yaml             Cloud Run service manifest
│   ├── jobs/                    Scheduler + Pub/Sub + Job manifests
│   ├── alerts/policies.yaml     6 Cloud Monitoring alert policies
│   ├── dlp/templates/           Cloud DLP de-identify template
│   └── bq/schemas/              BigQuery schemas (audit_events)
├── README.md                    What it is + 9-batch roadmap
├── ARCHITECTURE.md              System map + ADRs
├── DATA_DICTIONARY.md           Every Firestore collection + BQ table
├── OPERATOR_GUIDE.md            34 operational procedures
├── INPUT_CHECKLIST.md           Per-batch input requirements
├── COST_GUIDE.md                Routing matrix + budget rules
├── RUNBOOK.md                   10 incident playbooks
└── DEPLOYMENT.md                This document
```

---

## Appendix B — Test counts (live)

| Suite      | Files | Tests | Wall-clock |
|------------|-------|-------|------------|
| pytest     | 42    | 319   | ~8 min     |
| vitest     | 13    | 45    | ~8 s       |
| vite build | —     | —     | ~7 s (905 KB JS gzip 268 KB) |

Knowledge Graph: 4,014 nodes / 12,249 edges (Pillar 1 v14.0); cold build
~90 ms; warm build via LRU cache <1 ms.
