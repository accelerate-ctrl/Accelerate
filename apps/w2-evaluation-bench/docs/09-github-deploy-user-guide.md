# 09 — User Guide: Deploying to Cloud Run from GitHub

Audience: the operator deploying the W2 Evaluation Bench **from the GitHub
repository** — first from Cloud Shell (no local tooling needed), then wired
up so every push deploys itself. Prerequisite: Part A of
`docs/08-cloud-run-deployment-guide.md` is done (project, OAuth client,
service account, bucket, tokens, Artifact Registry). Placeholders:

| Placeholder | Meaning | Example |
|---|---|---|
| `<PROJECT>` | GCP project id | `zennify-w2-bench` |
| `<REGION>` | Cloud Run region | `us-central1` |
| `<BRANCH>` | Branch to deploy | `claude/w2-eval-bench-v2-8fi9uv` (or `main` after merge) |

Repository facts this guide relies on: repo **`accelerate-ctrl/Accelerate`**,
app in subdirectory **`apps/w2-evaluation-bench/`**, release tag
**`w2-evaluation-bench-v2.0`**, pipeline file
**`apps/w2-evaluation-bench/deploy/cloudbuild.yaml`**.

---

## Path 1 — first deploy from GitHub via Cloud Shell (10 minutes)

Use this for the initial provisioning deploy (it sets env vars, secrets and
the volume — things the continuous pipeline deliberately never touches).

**1. Open Cloud Shell** — console.cloud.google.com → the `>_` icon (top
right). It has `gcloud` and `git` preinstalled and is already authenticated
as you.

**2. Clone the repo and check out the release:**

```bash
git clone https://github.com/accelerate-ctrl/Accelerate.git
cd Accelerate
git checkout w2-evaluation-bench-v2.0        # the pinned release tag
# (or: git checkout <BRANCH> for the latest on the branch)
cd apps/w2-evaluation-bench
```

If the repo is private, Cloud Shell will prompt for credentials — use your
GitHub username + a fine-grained personal access token with read-only
`Contents` permission on this one repo (GitHub → Settings → Developer
settings → Fine-grained tokens). Revoke it after cloning if you like; the
continuous path below never uses it.

**3. Deploy** (this is doc 08 Step 7; both forms work — script or explicit):

```bash
gcloud config set project <PROJECT>
PROJECT=<PROJECT> REGION=<REGION> \
W2APP_TOKENS="$(gcloud secrets versions access latest --secret w2app-tokens)" \
  bash scripts/deploy_cloudrun.sh
```

The script creates the bucket if missing, builds from source (Cloud Build
runs the Dockerfile; `.gcloudignore` keeps run data out of the upload),
deploys with `--max-instances 1` + the `/data` volume, then **automatically
runs `scripts/remote_smoke.sh` against the live URL** — the deploy fails
loudly if any live check fails. Success looks like:

```
REMOTE SMOKE PASS
Deployed: https://w2-eval-bench-xxxxxxxx-uc.a.run.app
```

**4. Verify with a token** (the script's automatic smoke runs tokenless;
this adds the authenticated half — API access, full runner.zip, installer):

```bash
bash scripts/remote_smoke.sh https://<your-service-url> <a-member-token>
```

Then continue with member onboarding (doc 08, Step 10).

---

## Path 2 — continuous deploys: push to GitHub → live on Cloud Run

After Path 1 has provisioned the service once, wire GitHub to Cloud Build so
every push to the branch builds, tests, deploys, and re-verifies itself using
the committed pipeline (`deploy/cloudbuild.yaml`).

**1. Connect the repository.** Console → **Cloud Build → Repositories →
Connect repository** (host: GitHub). A GitHub authorization window opens —
this is the "Google Cloud Build" GitHub App asking for access; grant it to
the `accelerate-ctrl` account and select **only** the `Accelerate`
repository. (This authorization is the second row of doc 08's credential
map — no OAuth client of yours is involved.)

**2. Create the trigger.** Console → **Cloud Build → Triggers → Create
trigger**:

| Field | Value |
|---|---|
| Name | `w2-bench-deploy` |
| Region | `<REGION>` |
| Event | Push to a branch |
| Repository | `accelerate-ctrl/Accelerate` |
| Branch (regex) | `^claude/w2-eval-bench-v2-8fi9uv$` (or `^main$` after merge) |
| Included files filter | `apps/w2-evaluation-bench/**` — pushes elsewhere in the monorepo don't redeploy the bench |
| Configuration | Cloud Build configuration file |
| Location | `apps/w2-evaluation-bench/deploy/cloudbuild.yaml` |
| Substitution variables | `_REGION=<REGION>`, `_SERVICE=w2-eval-bench`, `_AR_REPO=w2-bench` |
| Service account | the build SA from doc 08 Step 3 |

CLI equivalent:

```bash
gcloud builds triggers create github \
  --project <PROJECT> --region <REGION> \
  --name w2-bench-deploy \
  --repo-owner accelerate-ctrl --repo-name Accelerate \
  --branch-pattern '^claude/w2-eval-bench-v2-8fi9uv$' \
  --included-files 'apps/w2-evaluation-bench/**' \
  --build-config apps/w2-evaluation-bench/deploy/cloudbuild.yaml \
  --substitutions _REGION=<REGION>,_SERVICE=w2-eval-bench,_AR_REPO=w2-bench
```

**3. What the pipeline does on every push** (in order, and it stops at the
first failure):

1. **Unit gate** — installs requirements and runs the full 57-test suite
   from the repo. A red test never reaches production.
2. **Build** — builds the app's Dockerfile from `apps/w2-evaluation-bench/`.
3. **Push** — tags the image with the commit SHA into Artifact Registry
   (`<REGION>-docker.pkg.dev/<PROJECT>/w2-bench/w2-eval-bench:<sha>`), so
   every deployed revision is traceable to an exact commit.
4. **Deploy** — `gcloud run deploy --image ...` — an image-only update.
   Your env vars, `W2APP_TOKENS` secret binding, volume mount, and
   `--max-instances 1` from the provisioning deploy are **preserved**; the
   pipeline cannot accidentally unset them.
5. **Remote smoke** — runs `scripts/remote_smoke.sh` against the live URL;
   the build goes red if the deployed service fails any live check.

**4. Use it:**

```bash
git push origin <BRANCH>
# watch: Console → Cloud Build → History, or
gcloud builds list --region <REGION> --limit 3
```

A green build = deployed **and** live-verified. Roll back by re-running the
trigger on the previous commit (Cloud Build → History → Rebuild), or:

```bash
gcloud run services update-traffic w2-eval-bench --region <REGION> \
  --to-revisions <previous-revision>=100
```

**A note on the console's "Continuously deploy from repository" button:**
Cloud Run's built-in button assumes the Dockerfile sits at the repo root and
skips tests entirely. Because this app lives in a monorepo subdirectory and
its contract is "verified at every boundary", use the trigger + pipeline
above instead — same effort, and you keep the unit gate and the post-deploy
smoke.

---

## Troubleshooting

| Symptom | Cause → fix |
|---|---|
| Build fails at `unit-tests` | The push broke the suite — fix locally (`python3 -m unittest discover -s tests`), push again. Nothing was deployed. |
| Build fails at `deploy`: permission denied | Build SA missing `roles/run.admin` or `roles/iam.serviceAccountUser` on the runtime SA (doc 08 Step 3). |
| `REMOTE SMOKE FAIL: GET /api/runs without token -> 401` got 200 | The service has no tokens configured — the provisioning deploy didn't bind the `w2app-tokens` secret. Re-run doc 08 Step 7. |
| `runner.zip contains the full runner FAIL` | You're deploying an image built before the QA fix that added `COPY runner/` — pull latest and redeploy. |
| `health` check FAIL / data_dir_writable false | Volume mount missing or bucket IAM missing `objectAdmin` for the runtime SA (doc 08 Steps 4/7). |
| Trigger never fires | Branch regex doesn't match, or the push only touched files outside `apps/w2-evaluation-bench/**`. |
| Members' installs fail with 401 | Token not in the current `w2app-tokens` secret version, or service not yet updated to `:latest`. |
| Console shows cost > $0.00 / run halts with 402 | Working as designed: a runner fell back to API billing. That member re-runs `claude logout && claude login` with plan credentials; see README billing guards. |

## Security notes specific to the GitHub path

- The GitHub App authorization is read-only on this one repo and revocable
  at GitHub → Settings → Applications.
- No secret ever lives in the repo: tokens are in Secret Manager, the
  Anthropic credential never leaves member laptops, the Gemini key never
  leaves runner env files. `.gcloudignore` keeps local `data/` (client
  documents) out of source uploads; trigger builds clone from GitHub, where
  `data/` is git-ignored anyway.
- Anyone with push rights to `<BRANCH>` can change production — protect the
  branch (GitHub → Settings → Branches → require PR review) once the trigger
  is live.
