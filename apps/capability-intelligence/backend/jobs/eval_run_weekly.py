"""Cloud Run Job: eval_run_weekly.

Activated in a later batch (see ARCHITECTURE.md). Batch 0 ships placeholders so
the manifests in infra/jobs/ have stable entry points.
"""


def run() -> None:
    raise NotImplementedError("eval_run_weekly not yet implemented")


if __name__ == "__main__":
    run()
