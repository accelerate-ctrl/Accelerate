"""Cloud Run Job: jira_incremental.

Pulls new / updated Jira issues since the last run. 15-minute cadence
in production; in dev (no Atlassian creds), the underlying call cleanly
no-ops with an empty result.
"""

from __future__ import annotations

from ..services import stories_service


def run() -> dict:
    n, source, issues = stories_service.ingest_jira()
    return {"jira_loaded": n, "source": source, "schema_issues": issues}
