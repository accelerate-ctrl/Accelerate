"""Pre-trained capability cluster service.

Per QA_AUDIT.md §4.2 / spec mandate. The system ships with a set of
``CapabilityCluster`` rows derived from Pillar 1, used as the
canonical capability-shape against which Pillars 2/3/4 are onboarded.
Each cluster carries a 256-dim centroid (the mean of its member-subcap
embeddings via Batch 4's hash-embedding service) and a list of member
``sub_cap_id`` values.

Public surface
--------------

    bootstrap_clusters_from_pillar1(n_clusters=12) -> list[dict]
    assign_to_cluster(capability, threshold=0.75) -> tuple[cluster_id|None, similarity]
    update_centroids() -> dict
    detect_drift(window_days=90) -> list[dict]
    propose_new_cluster(capability, novelty_threshold=0.7) -> dict | None
    list_clusters() -> list[dict]
    get_cluster(cluster_id) -> dict | None
"""

from __future__ import annotations

import logging
import math
import random
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from ..mixins.embedded_qa import has_keys, run_self_test
from ..models.common import schema_version
from .repository import get_repository

logger = logging.getLogger(__name__)

CLUSTER_COLLECTION = "capability_clusters"
DRIFT_COLLECTION = "cluster_drift_events"


@dataclass
class CapabilityCluster:
    cluster_id: str
    name: str
    centroid: list[float]
    member_subcap_ids: list[str] = field(default_factory=list)
    purity: float = 0.0
    last_updated_at: str = ""
    drift_history: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["_schema_version"] = schema_version("capability_cluster")
        return d


# ─── Linear-algebra helpers ─────────────────────────────────────────────────


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


def _mean_vec(vecs: list[list[float]]) -> list[float]:
    if not vecs:
        return [0.0] * 256
    n = len(vecs)
    return [sum(v[i] for v in vecs) / n for i in range(len(vecs[0]))]


# ─── K-means (lightweight, deterministic) ───────────────────────────────────


def _kmeans(
    points: list[tuple[str, list[float]]],
    *,
    k: int,
    max_iter: int = 50,
    seed: int = 42,
) -> dict[int, list[tuple[str, list[float]]]]:
    if len(points) <= k:
        return {i: [p] for i, p in enumerate(points)}
    rng = random.Random(seed)
    centroids = [v for _, v in rng.sample(points, k)]
    assignment: dict[int, list[tuple[str, list[float]]]] = {}
    for _ in range(max_iter):
        new_assignment: dict[int, list[tuple[str, list[float]]]] = {i: [] for i in range(k)}
        for label, vec in points:
            best = max(range(k), key=lambda i: _cosine(centroids[i], vec))
            new_assignment[best].append((label, vec))
        new_centroids = [
            _mean_vec([v for _, v in new_assignment[i]]) if new_assignment[i] else centroids[i]
            for i in range(k)
        ]
        if all(_cosine(new_centroids[i], centroids[i]) > 0.999 for i in range(k)):
            assignment = new_assignment
            centroids = new_centroids
            break
        assignment = new_assignment
        centroids = new_centroids
    # Rebuild centroids with final assignments
    return {i: members for i, members in assignment.items() if members}


# ─── Public API ─────────────────────────────────────────────────────────────


def _embed_subcap(subcap: dict) -> list[float]:
    """Use Batch 4 hash-embedding for the subcap text."""
    from .llm.embeddings import embed_text

    text = " ".join(filter(None, [
        subcap.get("sub_cap_name"),
        subcap.get("description"),
        subcap.get("l1_capability"),
        subcap.get("category_id"),
    ]))
    return embed_text(text or subcap.get("sub_cap_id", ""))


def bootstrap_clusters_from_pillar1(*, n_clusters: int = 12) -> list[dict]:
    """Build the initial cluster set from the current Pillar 1 catalogue.

    Idempotent: re-running replaces the existing cluster set with the
    fresh fit so calibration is reproducible per the manifest.
    """
    repo = get_repository()
    p1_subcaps = [s for s in repo.list("subcaps") if (s.get("pillar_id") or "") == "P1"]
    if not p1_subcaps:
        logger.warning("cluster bootstrap: no P1 subcaps loaded; nothing to cluster")
        return []
    points: list[tuple[str, list[float]]] = [
        (s["sub_cap_id"], _embed_subcap(s)) for s in p1_subcaps
    ]
    assignment = _kmeans(points, k=n_clusters)

    by_subcap = {s["sub_cap_id"]: s for s in p1_subcaps}
    clusters: list[CapabilityCluster] = []
    now = datetime.now(timezone.utc).isoformat()
    for i, members in sorted(assignment.items()):
        member_ids = [label for label, _ in members]
        member_vecs = [vec for _, vec in members]
        centroid = _mean_vec(member_vecs)
        # Purity = fraction of members sharing the dominant Category as proxy
        cats = [by_subcap.get(mid, {}).get("category_id") for mid in member_ids if mid in by_subcap]
        if cats:
            from collections import Counter
            most_common, count = Counter(cats).most_common(1)[0]
            purity = count / len(cats)
            cluster_name = f"cluster-{i:02d} [{most_common}]"
        else:
            purity = 0.0
            cluster_name = f"cluster-{i:02d}"
        clusters.append(CapabilityCluster(
            cluster_id=f"cap-cluster-{i:02d}",
            name=cluster_name,
            centroid=centroid,
            member_subcap_ids=member_ids,
            purity=round(purity, 3),
            last_updated_at=now,
        ))

    # Persist (replace_collection-style: clear + write)
    with repo.defer_persist():
        for existing in repo.list(CLUSTER_COLLECTION):
            repo.delete(CLUSTER_COLLECTION, existing.get("cluster_id", ""))
        for c in clusters:
            payload = c.to_dict()
            qa = run_self_test(
                payload,
                checks=[
                    has_keys("cluster_id", "centroid", "member_subcap_ids"),
                    ("non_empty_centroid", lambda p: len(p.get("centroid") or []) == 256,
                     "centroid must be 256-dim"),
                ],
                schema_version=schema_version("capability_cluster"),
            )
            payload.update(qa.to_dict())
            repo.upsert(CLUSTER_COLLECTION, c.cluster_id, payload)
    return [c.to_dict() for c in clusters]


def list_clusters() -> list[dict]:
    return list(get_repository().list(CLUSTER_COLLECTION))


def get_cluster(cluster_id: str) -> dict | None:
    return get_repository().get(CLUSTER_COLLECTION, cluster_id)


def assign_to_cluster(capability: dict, *, threshold: float = 0.75) -> tuple[str | None, float]:
    """Assign a (P2/P3/P4) capability to an existing cluster, or signal novel."""
    clusters = list_clusters()
    if not clusters:
        return None, 0.0
    vec = _embed_subcap(capability)
    best_id, best_sim = None, 0.0
    for c in clusters:
        sim = _cosine(vec, c.get("centroid") or [0.0] * 256)
        if sim > best_sim:
            best_id, best_sim = c.get("cluster_id"), sim
    if best_sim >= threshold:
        return best_id, round(best_sim, 4)
    return None, round(best_sim, 4)


def update_centroids() -> dict:
    """Re-fit centroids from current member set; emits a drift report."""
    repo = get_repository()
    drifted: list[dict] = []
    now = datetime.now(timezone.utc).isoformat()
    by_subcap = {s["sub_cap_id"]: s for s in repo.list("subcaps")}
    with repo.defer_persist():
        for c in repo.list(CLUSTER_COLLECTION):
            members = [by_subcap[mid] for mid in c.get("member_subcap_ids") or [] if mid in by_subcap]
            if not members:
                continue
            new_centroid = _mean_vec([_embed_subcap(s) for s in members])
            old_centroid = c.get("centroid") or [0.0] * 256
            sim = _cosine(new_centroid, old_centroid)
            drift = 1.0 - sim
            updated = {**c, "centroid": new_centroid, "last_updated_at": now}
            if drift > 0.05:
                drifted.append({"cluster_id": c["cluster_id"], "drift": round(drift, 4)})
                updated["drift_history"] = (c.get("drift_history") or []) + [
                    {"at": now, "drift": round(drift, 4)},
                ]
            repo.upsert(CLUSTER_COLLECTION, c["cluster_id"], updated)
    return {"updated_at": now, "drifted_clusters": drifted}


def detect_drift(*, window_days: int = 90) -> list[dict]:
    """Return cluster-drift events within the window."""
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=window_days)).isoformat()
    out: list[dict] = []
    for c in list_clusters():
        for event in c.get("drift_history") or []:
            if (event.get("at") or "") >= cutoff:
                out.append({"cluster_id": c["cluster_id"], **event})
    return out


def propose_new_cluster(capability: dict, *, novelty_threshold: float = 0.7) -> dict | None:
    """If similarity to every existing centroid is < novelty_threshold,
    propose a new cluster (returns its proposed shape; not persisted)."""
    cluster_id, sim = assign_to_cluster(capability, threshold=novelty_threshold)
    if cluster_id is not None:
        return None
    return {
        "proposed_cluster_id": f"cap-cluster-novel-{capability.get('sub_cap_id', '?')}",
        "seed_subcap_id": capability.get("sub_cap_id"),
        "similarity_to_nearest": sim,
        "centroid": _embed_subcap(capability),
        "_schema_version": schema_version("capability_cluster"),
        "proposed_at": datetime.now(timezone.utc).isoformat(),
    }
