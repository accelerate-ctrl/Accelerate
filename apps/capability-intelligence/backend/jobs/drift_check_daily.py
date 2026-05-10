"""Cloud Run Job: drift_check_daily.

Activated in a later batch (see ARCHITECTURE.md). Batch 0 ships placeholders so
the manifests in infra/jobs/ have stable entry points.
"""


def run() -> None:
    raise NotImplementedError("drift_check_daily not yet implemented")


if __name__ == "__main__":
    run()
