from pathlib import Path

from app.services.repository import InMemoryRepository


def test_in_memory_basic_crud(tmp_path: Path):
    repo = InMemoryRepository(persist_path=str(tmp_path / "repo.json"))
    repo.upsert("subcaps", "P1C1.1.1", {"sub_cap_id": "P1C1.1.1", "name": "x"})
    assert repo.get("subcaps", "P1C1.1.1")["name"] == "x"
    assert repo.count("subcaps") == 1
    repo.upsert_many("subcaps", [("P1C1.1.2", {"name": "y"}), ("P1C1.1.3", {"name": "z"})])
    assert repo.count("subcaps") == 3


def test_in_memory_persistence(tmp_path: Path):
    p = tmp_path / "repo.json"
    repo = InMemoryRepository(persist_path=str(p))
    repo.upsert("flags", "f1", {"flag_id": "f1", "kind": "MAPPING_REGRESSION"})
    assert p.exists()
    repo2 = InMemoryRepository(persist_path=str(p))
    assert repo2.get("flags", "f1")["kind"] == "MAPPING_REGRESSION"


def test_in_memory_filter_and_distinct():
    repo = InMemoryRepository()
    repo.upsert("subcaps", "a", {"pillar_id": "P1", "tier": "T1"})
    repo.upsert("subcaps", "b", {"pillar_id": "P1", "tier": "T2"})
    repo.upsert("subcaps", "c", {"pillar_id": "P2", "tier": "T1"})
    assert repo.count("subcaps", {"pillar_id": "P1"}) == 2
    assert sorted(repo.distinct("subcaps", "pillar_id")) == ["P1", "P2"]


def test_replace_collection_drops_existing():
    repo = InMemoryRepository()
    repo.upsert_many("subcaps", [("a", {"v": 1}), ("b", {"v": 2})])
    repo.replace_collection("subcaps", [("c", {"v": 3})])
    assert repo.count("subcaps") == 1
    assert repo.get("subcaps", "a") is None
    assert repo.get("subcaps", "c") == {"v": 3}
