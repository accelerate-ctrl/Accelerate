# 08 — Cloud Run Deployment Plan (complete, component by component)

This is the full production deployment plan for the W2 Evaluation Bench v2.0
on Google Cloud Run, starting from the creation of the OAuth client in the
project and ending with a verified live service and onboarded members. Every
command is copy-pasteable; placeholders are in `<angle brackets>`. The
companion **user guide for deploying from GitHub** is
`docs/09-github-deploy-user-guide.md`.

## 0. The credential map — read this first

Four different credentials exist in this system. Knowing which is which
prevents every common deployment mistake:

| Credential | Where it is created | What it is for | Where it lives |
|---|---|---|---|
| **Google OAuth client** (consent screen + OAuth 2.0 Client ID) | GCP project, Step 2 | Used by **Identity-Aware Proxy (IAP)** if you enable the optional Google-sign-in wall in front of the browser surfaces (Step 9). It is **not** the app's login — the bench deliberately has no in-app Google sign-in (PRD D14). | GCP project |
| **Cloud Build ↔ GitHub authorization** | Cloud Build "Connect repository" flow (doc 09) | Lets Cloud Build watch the GitHub repo and deploy on push. This is an OAuth *authorization* of Google's GitHub App, not a client you create. | GitHub + GCP |
| **Member tokens** (`W2APP_TOKENS`) | You generate them, Step 5 | The app's own auth: every `/api` call, the installer, and the runner present one. Random shared secrets, one per member — not OAuth. | Secret Manager → Cloud Run env |
| **Anthropic subscription OAuth** (`claude setup-token`) | Each member's laptop during runner install (Step 10) | Lets that member's runner execute Claude packets under their Team seat. Never enters GCP, never enters the container image. | Member laptop (`~/.claude` / `~/.w2/env`, 0600) |

Also runner-side only: `GEMINI_API_KEY` (paid tier). The **server never holds
it** — Gemini is called by the member runners, so the key goes into each
runner's `~/.w2/env`, not into Cloud Run.

Architecture being deployed (from the README): the Cloud Run service is the
deterministic brain (zero model calls, no credentials in the image); member
laptops run the intelligence layer and poll the service outbound over HTTPS.
That is why this plan has a cloud half (Steps 1–9) and a member half
(Step 10).

---

## Part A — one-time project foundation

### Step 1 — project, billing, APIs

```bash
gcloud auth login
export PROJECT=<your-project-id>          # e.g. zennify-w2-bench
export REGION=us-central1                 # pick your region once, keep it
gcloud projects create "$PROJECT" 2>/dev/null || true   # skip if it exists
gcloud config set project "$PROJECT"
# Billing must be linked (Console → Billing) before Cloud Run will deploy.

gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  storage.googleapis.com \
  secretmanager.googleapis.com \
  iap.googleapis.com
```

Roles you need on the project to execute this plan: `Owner`, or the set
{`Cloud Run Admin`, `Cloud Build Editor`, `Artifact Registry Admin`,
`Storage Admin`, `Secret Manager Admin`, `Service Account Admin`,
`Service Usage Admin`}.

### Step 2 — create the OAuth client in the project

Console → **APIs & Services → OAuth consent screen** (newer consoles label
this **Google Auth Platform → Branding**):

1. **User type:** `Internal` (your Workspace org only — correct for a company
   bench; `External` would open the consent screen to any Google account).
2. **App name:** `W2 Evaluation Bench` · support email: `accelerate@zennify.com`
   · authorized domain: your Workspace domain. Save.
3. Console → **APIs & Services → Credentials → + Create credentials →
   OAuth client ID**:
   - Application type: **Web application**
   - Name: `w2-bench-iap`
   - Leave redirect URIs empty for now — **if** you enable IAP via a load
     balancer in Step 9, come back and add
     `https://iap.googleapis.com/v1/oauth/clientIds/<CLIENT_ID>:handleRedirect`
     (the console shows the exact URI when you wire IAP).
4. Record the **Client ID** and **Client secret**.

Plain statement of what this buys you: the OAuth client is the identity
foundation for the optional IAP wall (Step 9). The bench itself authenticates
members with `W2APP_TOKENS` regardless. If you choose to skip IAP, nothing
else in this plan consumes this client — but creating it now costs nothing
and keeps Step 9 a pure toggle. (Newer IAP setups can also use a
Google-managed client automatically; creating your own keeps you on the
documented, org-controlled path.)

### Step 3 — service accounts and least privilege

```bash
# Runtime identity for the Cloud Run service (don't run as the default SA):
gcloud iam service-accounts create w2-bench-run \
  --display-name "W2 bench Cloud Run runtime"

export RUN_SA="w2-bench-run@${PROJECT}.iam.gserviceaccount.com"
```

Grants it needs (bucket + secret access are added in Steps 4–5 where the
resources are created; it needs nothing else — the service calls no Google
API besides its mounted volume).

For the GitHub pipeline (doc 09), the **build** service account —
`<PROJECT_NUMBER>-compute@developer.gserviceaccount.com` on new projects
(Cloud Build's default since 2024), or
`<PROJECT_NUMBER>@cloudbuild.gserviceaccount.com` on older ones — needs:

```bash
export PROJECT_NUMBER=$(gcloud projects describe "$PROJECT" --format 'value(projectNumber)')
export BUILD_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
for role in roles/run.admin roles/artifactregistry.writer roles/logging.logWriter; do
  gcloud projects add-iam-policy-binding "$PROJECT" \
    --member "serviceAccount:$BUILD_SA" --role "$role"
done
# let the build deploy *as* the runtime SA:
gcloud iam service-accounts add-iam-policy-binding "$RUN_SA" \
  --member "serviceAccount:$BUILD_SA" --role roles/iam.serviceAccountUser
```

### Step 4 — the run-data bucket (component: persistent store)

Run directories, deliverables, and the blinding escrow live on a GCS bucket
mounted at `/data` (Cloud Run volume mount, GCS FUSE). One bucket, one
region, uniform access:

```bash
export BUCKET="${PROJECT}-w2-runs"
gcloud storage buckets create "gs://$BUCKET" \
  --project "$PROJECT" --location "$REGION" \
  --uniform-bucket-level-access

gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" \
  --member "serviceAccount:$RUN_SA" --role roles/storage.objectAdmin
```

This bucket holds client documents and the escrow — do **not** grant
`allUsers` anything on it, ever. (The escrow is additionally protected in the
app: no API route can serve it.)

### Step 5 — member tokens (component: app auth) in Secret Manager

Generate one token per evaluating member; the format is
`member:token,member:token,...`:

```bash
ALICE=$(openssl rand -hex 24); BOB=$(openssl rand -hex 24)
echo "alice token: $ALICE"    # deliver to Alice over a secure channel
echo "bob token:   $BOB"      # deliver to Bob   over a secure channel

printf 'alice:%s,bob:%s' "$ALICE" "$BOB" | \
  gcloud secrets create w2app-tokens --data-file=- --replication-policy automatic

gcloud secrets add-iam-policy-binding w2app-tokens \
  --member "serviceAccount:$RUN_SA" --role roles/secretmanager.secretAccessor
```

Member names become the `owner` stamp on runs (owner-pays affinity, FR-13),
so use real, stable member ids. Rotation later = `gcloud secrets versions add`
+ redeploy (Step 12).

### Step 6 — Artifact Registry (component: image store; used by the GitHub pipeline)

```bash
gcloud artifacts repositories create w2-bench \
  --repository-format docker --location "$REGION" \
  --description "W2 Evaluation Bench images"
```

(A pure `--source` deploy in Step 7 auto-manages a `cloud-run-source-deploy`
repo; creating `w2-bench` now is for the doc-09 pipeline, which tags images
by commit SHA.)

---

## Part B — deploy and verify the service

### Step 7 — first deploy (provisioning deploy)

From a clone of the repo (see doc 09 §2 for cloning from GitHub / Cloud
Shell), inside `apps/w2-evaluation-bench/`:

```bash
gcloud run deploy w2-eval-bench \
  --project "$PROJECT" --region "$REGION" \
  --source . \
  --service-account "$RUN_SA" \
  --allow-unauthenticated \
  --max-instances 1 --concurrency 40 --memory 1Gi --timeout 300 \
  --set-env-vars "W2APP_DATA=/data" \
  --set-secrets "W2APP_TOKENS=w2app-tokens:latest" \
  --add-volume "name=runs,type=cloud-storage,bucket=$BUCKET" \
  --add-volume-mount "volume=runs,mount-path=/data"
```

What each flag is doing (these are load-bearing, not decoration):

- `--source .` — Cloud Build builds the app's Dockerfile; `.gcloudignore`
  keeps `data/` (client documents) and repo noise out of the upload.
- `--allow-unauthenticated` — the *URL* is public; every `/api` route,
  `/install.sh` and `/runner.zip` still demand a member token (verified by
  remote smoke below). Required so member runners and the console can reach
  the service without Google identities. If you enable IAP in Step 9 this
  changes — read that step's caveat first.
- `--max-instances 1` — the orchestrator is a single-writer file state
  machine; one instance is a correctness requirement, not a cost tweak.
- `--set-secrets` — tokens come from Secret Manager at runtime; they are
  never in the image or the revision spec.
- volume + mount — the Step-4 bucket appears at `/data`.

Alternative: `scripts/deploy_cloudrun.sh` wraps this same deploy (plus bucket
creation and the post-deploy smoke) for env-var-driven one-command use:

```bash
PROJECT=$PROJECT REGION=$REGION BUCKET=$BUCKET \
W2APP_TOKENS="alice:$ALICE,bob:$BOB" bash scripts/deploy_cloudrun.sh
```

(The script passes tokens as env vars — fine for a first spin; the
Secret-Manager form above is the production posture.)

### Step 8 — verify the live service (component: post-deploy gate)

```bash
export URL=$(gcloud run services describe w2-eval-bench \
  --region "$REGION" --format 'value(status.url)')

bash scripts/remote_smoke.sh "$URL" "$ALICE"
```

`REMOTE SMOKE PASS` proves, against production, read-only: `/health` is
live and the data dir is writable; landing + console serve; all three auth
walls return 401 without a token; a traversal attempt is blocked; security
headers are present; `runner.zip` contains the complete runner; the installer
is served personalized. **Do not onboard members until this passes.**
`scripts/deploy_cloudrun.sh` runs it automatically after every deploy; the
GitHub pipeline (doc 09) runs it as its final step.

Optional monitoring: point a Cloud Monitoring uptime check at
`$URL/health` (expect 200 containing `"ok": true`).

### Step 9 — optional: the IAP wall (uses the Step-2 OAuth client)

Skip this step for the standard posture (public URL + member tokens — the
architecture the runners are built for). Enable it only if policy requires
Google sign-in in front of the **browser** surfaces, and understand the
trade-off first:

> **Caveat:** IAP intercepts *every* request to the service. Member runners
> poll `/api/packets/next` with only an `X-W2-Token` header, and the
> installer is fetched with `curl` — with IAP in front, both get an IAP
> sign-in challenge and fail, unless every runner also presents a Google
> OIDC identity token for a principal you allow-list (extra per-machine
> setup: a service-account key or `gcloud auth print-identity-token`
> wrapper, plus `roles/iap.httpsResourceAccessor` per member). IAP here is
> a *second* wall in addition to member tokens, never a replacement.

- **Direct integration (no load balancer)** — recent gcloud releases expose
  IAP directly on Cloud Run (rolled out through 2025; check
  `gcloud beta run deploy --help | grep -i iap`):
  `gcloud beta run deploy w2-eval-bench --region $REGION --iap` then grant
  members `roles/iap.httpsResourceAccessor`. Remove
  `--allow-unauthenticated` semantics per the current IAP-for-Cloud-Run
  documentation.
- **Classic path** — external HTTPS load balancer → serverless NEG →
  backend service with IAP enabled, using the Step-2 OAuth client ID/secret;
  then restrict the run service's ingress to
  `internal-and-cloud-load-balancing` so the wall can't be bypassed via the
  `run.app` URL.

### Step 10 — onboard each evaluating member (component: personal runners)

Prereqs per member: a **Claude Team seat**, and the org's **paid-tier
Gemini API key**. Send each member their token from Step 5 and this one
command (macOS or Linux/WSL):

```bash
curl -fsSL $URL/install.sh | bash -s -- --token <their-token>
```

What it does on their machine (doc 07 has the long form): installs Claude
Code if missing → opens Anthropic's own login for their Team seat
(`claude setup-token`; the credential never leaves their machine) → installs
the runner as a user-level service (launchd / `systemd --user`) → writes
`~/.w2/env` (0600) → runs `w2_runner.py --selfcheck`, which must print all
PASS lines (billing guards G1–G3, bench reachability, Gemini tier).

The member then adds the Gemini key to `~/.w2/env`:

```
GEMINI_API_KEY=<org paid-tier key>
W2_GEMINI_TIER=paid
```

and restarts the service (`launchctl kickstart -k gui/$UID/com.zennify.w2runner`
or `systemctl --user restart w2-runner`). Verify from anywhere:

```bash
curl -s -H "X-W2-Token: <any-member-token>" $URL/api/runners
```

— every onboarded member should appear with a recent `last_seen`; the console
header shows "your runner: connected".

### Step 11 — first production run (acceptance)

1. Open `$URL` → **Open the bench** → paste a member token when prompted.
2. Upload a BRD + two SDDs (Mode A). The run is one-touch: watch the stage
   rail walk S0→reveal; the owner's runner picks up packets within its poll
   interval (~3 s).
3. Acceptance checks: per-judge usage line shows `reported API cost $0.00
   (must stay 0.00)`; the concurrence meter populates after consensus; the
   Diagnostic Report downloads and contains judge provenance, the agreement
   table, and (if any) the dissent annex; `run-record.json` is in the
   deliverables.
4. Anthropic Console for the org must show **zero API spend** for the window
   — the definitive billing check (guards G1–G5 + the 402 tripwire enforce
   this continuously).

---

## Part C — operations

### Step 12 — routine operations

- **Update the app**: push to GitHub → the doc-09 trigger builds, tests,
  deploys, and re-runs remote smoke. (Or re-run Step 7 manually.) Env vars,
  secrets and the volume are preserved across image-only deploys.
- **Rotate a member token**: `gcloud secrets versions add w2app-tokens
  --data-file=-` with the full new `member:token,...` string, then
  `gcloud run services update w2-eval-bench --region $REGION
  --update-secrets W2APP_TOKENS=w2app-tokens:latest` (new revision picks it
  up); the member re-runs the install command with the new token.
- **Logs**: `gcloud run services logs read w2-eval-bench --region $REGION`.
  Watch for `BILLING_TRIPWIRE` (a run halted deliberately) and
  `last_rejected_result` 400s (a malformed runner).
- **Backup**: the bucket *is* the state; GCS versioning on `gs://$BUCKET`
  gives point-in-time recovery of runs and deliverables.
- **Teardown**: delete the service, then the bucket (client documents!),
  secret, and Artifact Registry repo — in that order.

### Deployment checklist (print this)

- [ ] Step 1: APIs enabled, billing linked
- [ ] Step 2: OAuth consent screen `Internal` + client `w2-bench-iap` recorded
- [ ] Step 3: `w2-bench-run` SA created; build SA granted run.admin + SA-user
- [ ] Step 4: bucket created, uniform access, runtime SA objectAdmin, no public access
- [ ] Step 5: per-member tokens generated, `w2app-tokens` secret created, tokens delivered securely
- [ ] Step 6: Artifact Registry `w2-bench` created
- [ ] Step 7: service deployed (max-instances 1, volume at /data, secrets wired)
- [ ] Step 8: `REMOTE SMOKE PASS` against the live URL
- [ ] Step 9: IAP decision recorded (on with runner caveat handled / off)
- [ ] Step 10: every member's selfcheck PASS + visible in `/api/runners`
- [ ] Step 11: first Mode A run end-to-end, $0.00 API cost, report downloaded
- [ ] Doc 09: GitHub trigger created and one push-to-deploy verified
