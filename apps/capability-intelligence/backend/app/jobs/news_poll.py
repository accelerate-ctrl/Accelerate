"""Cloud Run Job: news_poll.

Polls every configured news/trends source via :func:`news_service.refresh`.
Emits ``digest.generated`` event family is NOT triggered here; lifecycle
recompute consumes the freshly indexed sources.

Schedule: hourly  (see infra/jobs/scheduler.yaml).
"""

from __future__ import annotations

from dataclasses import asdict

from ..services import news_service


def run() -> dict:
    summary = news_service.refresh()
    return asdict(summary)


if __name__ == "__main__":
    import json
    print(json.dumps(run(), default=str, indent=2))
