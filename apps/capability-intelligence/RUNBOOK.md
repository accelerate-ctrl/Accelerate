# Runbook

Final form. Batch 9 finalises every section below.

## TOC

1. [Incident response](#1-incident-response)
2. [Source pull failures](#2-source-pull-failures)
3. [LLM rate limits / 429s](#3-llm-rate-limits--429s)
4. [BigQuery slot exhaustion](#4-bigquery-slot-exhaustion)
5. [Drift alerts](#5-drift-alerts)
6. [Cost spikes / auto-throttle](#6-cost-spikes--auto-throttle)
7. [Secret rotation](#7-secret-rotation)
8. [Disaster recovery (RTO 4h / RPO 24h)](#8-disaster-recovery)
9. [Backups](#9-backups)
10. [DLQ investigation](#10-dlq-investigation)

---

## 0. Service Level Objectives (added by QA audit fix #13)

Per QA_AUDIT.md fix #13. SLOs are tied to error budgets; deploys are
gated by remaining budget (Cloud Build step queries
`gcloud monitoring slos describe ...`).

| Endpoint                                | p50    | p95    | p99    | Error budget |
|-----------------------------------------|--------|--------|--------|--------------|
| `GET /api/health`                       | 5 ms   | 30 ms  | 50 ms  | 0.1%         |
| `GET /api/catalogue/*`                  | 80 ms  | 300 ms | 500 ms | 0.5%         |
| `GET /api/digest/{id}` (cached)         | 100 ms | 800 ms | 1.5 s  | 1.0%         |
| `POST /api/digest/generate`             | async — SLA 6 h end-to-end                      | 5.0%   |
| `POST /api/chat/messages`               | 1.5 s  | 5 s    | 12 s   | 1.0%         |
| `GET /api/graph/summary`                | 50 ms  | 200 ms | 400 ms | 1.0%         |
| `GET /api/graph/neighborhood/{id}`      | 200 ms | 1 s    | 2 s    | 1.0%         |
| `GET /api/graph/path/...`               | 400 ms | 1 s    | 2 s    | 1.0%         |
| `GET /api/benchmarks/*`                 | 100 ms | 400 ms | 800 ms | 1.0%         |
| `POST /api/lifecycle/recompute`         | 500 ms | 2 s    | 5 s    | 5.0%         |
| `GET /api/exports/*.xlsx`               | 200 ms | 1 s    | 3 s    | 2.0%         |

**Error budget enforcement** — `cloudbuild.yaml` includes a "block-on-budget-exhausted"
step that queries the SLO objects defined in `infra/terraform/main.tf`
and fails the deploy if any SLO has < 5% remaining error budget.

## 1. Incident response

**Trigger**: Cloud Monitoring alert `high-error-rate` fires (5xx > 5% over 5
minutes) or PagerDuty receives `audit.critical_finding`.

1. Acknowledge in PagerDuty.
2. Open the QA & Audit Dashboard (`/audit`) and check the latest report's
   critical findings.
3. If findings include `GATE_FAIL`: open the linked reasoning chain and
   inspect the failing gate. The `hallucination` gate is the most common
   trigger; check whether sources have rotated.
4. If 5xx alerts: `gcloud run services logs tail capability-intelligence-api`
   and look for tracebacks. Most common: Firestore rate limit (429) — switch
   to read-only mode by setting `READ_ONLY=true` env var on the service.
5. Page the data team if catalogue ingest is in flight (Mission Control
   shows yellow/red).

## 2. Source pull failures

**Trigger**: `news_poll` / `public_filings_poll` Job exits non-zero, lands
in DLQ.

1. Check the job logs: `gcloud run jobs executions describe <name>`.
2. Common failures:
   - 403 on RSS feed → source rotated; update `config/canonical_sources.yml`.
   - SEC EDGAR User-Agent rejection → confirm `SEC_EDGAR_EMAIL` is set.
   - Drive folder permission → re-share with the service-account email.
3. Re-run manually: `gcloud run jobs execute <name> --region us-central1`.
4. If the source is permanently dead, mark `polling_method: scrape` →
   `polling_method: disabled` in `canonical_sources.yml`.

## 3. LLM rate limits / 429s

**Trigger**: `llm_costs.spend_today` is healthy but call rate spikes; Anthropic
or Vertex returns 429.

1. The router's `assert_within_budget()` already throttles at 90% of the
   ceiling; if 429s persist below that, lower `daily_spend_ceiling_usd`
   temporarily.
2. Switch high-leverage tasks to Gemini-Pro via setting
   `ANTHROPIC_WEEKLY_BUDGET_USD=0` for the rest of the week.
3. If batch-job rate is the source: stagger Cloud Scheduler crons so news +
   filings don't both fire at :00.

## 4. BigQuery slot exhaustion

**Trigger**: `audit_events` exports lag, BQ query metrics show queued slots.

1. Check active queries: BQ Query Monitor → "Running queries".
2. Identify the heavy query — usually a back-fill of `reasoning_chains` or
   `audit_events`.
3. Reserve flex slots if persistent: `bq mk --reservation --slots=100 …`.
4. Drop low-priority materialised views during incident windows.

## 5. Drift alerts

**Trigger**: `drift_check_daily` reports >5 non-adjacent transitions OR eval
harness `mean_score` regresses by >0.2.

1. Open the Lifecycle Manager and confirm the transitions look implausible.
2. Check the underlying cause: SOWs being mis-attributed (entity resolver
   alias miss?), benchmarks rotating verdicts, news cadence dropping.
3. If false positives dominate: extend the `ADJACENT` set in
   `app/jobs/drift_check_daily.py`.
4. If the eval regression is real: revert the most recent suggestion-apply
   batch via `POST /api/suggestions/{id}/reject`.

## 6. Cost spikes / auto-throttle

**Trigger**: alert `daily-llm-spend` fires.

1. Visit the Validation Gates Log → cost summary; identify which model
   consumed the spike.
2. If `opus`: someone manually triggered digests — verify intent.
3. If `sonnet`: check whether the consultant loop is being re-invoked
   without cache hits — cache hit rate <40% is a smell.
4. Reduce `priority_limit` in the digest job to 3 for the rest of the
   month.

## 7. Secret rotation

Quarterly rotation:

```bash
gcloud secrets versions add anthropic-api-key --data-file=- < new-key.txt
gcloud run services update capability-intelligence-api \
  --update-secrets="ANTHROPIC_API_KEY=anthropic-api-key:latest"
```

The Cloud Run service picks up the new secret on the next instance boot;
existing instances continue with the previous version until they recycle.
Force a recycle by pushing a no-op revision:

```bash
gcloud run deploy capability-intelligence-api --image $CURRENT_IMAGE
```

## 8. Disaster recovery

**RTO**: 4 hours · **RPO**: 24 hours.

If the GCP project is unrecoverable:

1. Bring up a fresh project: `terraform apply -var-file=dr.tfvars`.
2. Restore the latest Firestore export from the cross-project GCS bucket:
   `gcloud firestore import gs://zen-ci-backups-dr/<latest-stamp>`.
3. Re-deploy the latest image tag: pushed by Cloud Build to Artifact Registry
   replicated cross-region.
4. Resume Scheduler entries: `terraform apply` re-creates them; first run
   triggers within 15 minutes for the `*/15` jobs.
5. Verify by hitting `/api/health` + running the eval harness via
   `gcloud run jobs execute eval-run-weekly`.

## 9. Backups

| Resource              | Cadence | Retention    | Tooling                           |
|-----------------------|---------|--------------|-----------------------------------|
| Firestore             | daily   | 30 days      | `gcloud firestore export` cron    |
| GCS object versioning | always  | 90 days      | Bucket lifecycle rule             |
| BigQuery time-travel  | always  | 7 days       | Native BQ feature                 |
| Artifact Registry     | always  | 365 days     | Native AR retention policy        |

## 10. DLQ investigation

**Trigger**: `dead-letter-queue` alert (DLQ depth > 5).

1. Inspect the DLQ subscription:
   `gcloud pubsub subscriptions pull capability-intelligence-dlq --limit 10`.
2. Each message body has the failed event payload + the exception message.
3. Common causes:
   - Stale event schema after a service rename.
   - Pub/Sub publisher quota: increase via
     `gcloud pubsub topics update <topic> --message-retention-duration=7d`.
   - Permanent receiver bug: pull DLQ messages, inspect, fix code, re-deploy.
4. Once root-caused, drain the DLQ:
   `gcloud pubsub subscriptions pull capability-intelligence-dlq --auto-ack`.

---

For operational steps (run a job, check status, refresh a digest), see
`OPERATOR_GUIDE.md`.
