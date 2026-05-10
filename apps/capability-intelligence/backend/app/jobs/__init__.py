"""Cloud Run Jobs — production task entrypoints.

Per spec §20 / ARCHITECTURE Batch 9.

Each module here exposes a ``run()`` callable that performs one unit of
batch work (news ingest, lifecycle recompute, digest gen, etc.). Cloud
Run Jobs invoke ``python -m app.jobs.runner <name>``; the runner wraps
the call in OpenTelemetry-friendly structured logging and emits a
Pub/Sub completion event on success.

The 14 jobs are:

    news_poll                       hourly
    public_filings_poll             daily
    jira_incremental                15-min
    sow_incremental                 hourly
    sow_full_reindex                weekly
    lifecycle_scoring_daily         daily
    benchmark_extrapolation_run     weekly
    benchmark_recompute_quarterly   quarterly
    digest_quarterly                quarterly
    deep_audit_weekly               weekly
    eval_run_weekly                 weekly
    citation_verify_daily           daily
    drift_check_daily               daily
    evidence_promotion_nightly      nightly

Schedules live in ``infra/jobs/scheduler.yaml``.
"""
