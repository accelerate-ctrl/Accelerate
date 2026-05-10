"""Cloud Run Job: sow_full_reindex.

Activated in a later batch (see ARCHITECTURE.md). Batch 0 ships placeholders so
the manifests in infra/jobs/ have stable entry points.
"""


def run() -> None:
    raise NotImplementedError("sow_full_reindex not yet implemented")


if __name__ == "__main__":
    run()
