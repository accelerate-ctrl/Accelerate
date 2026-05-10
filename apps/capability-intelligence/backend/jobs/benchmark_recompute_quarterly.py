"""Cloud Run Job: benchmark_recompute_quarterly.

Activated in a later batch (see ARCHITECTURE.md). Batch 0 ships placeholders so
the manifests in infra/jobs/ have stable entry points.
"""


def run() -> None:
    raise NotImplementedError("benchmark_recompute_quarterly not yet implemented")


if __name__ == "__main__":
    run()
