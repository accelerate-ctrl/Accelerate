from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CatalogueVersion(BaseModel):
    version_id: str  # ULID-like sortable string
    label: str | None = None
    created_at: datetime
    created_by: str
    summary: str | None = None
    pillar_counts: dict[str, int] = Field(default_factory=dict)  # P1: 199, ...
    snapshot_uri: str | None = None  # gs://bucket/path or local file
    source_files: dict[str, dict[str, Any]] = Field(default_factory=dict)  # pillar_id -> {file_id, name, modified_at, version}
    is_current: bool = False


class VersionDiff(BaseModel):
    version_a: str
    version_b: str
    added_subcaps: list[str] = Field(default_factory=list)
    removed_subcaps: list[str] = Field(default_factory=list)
    modified_subcaps: list[dict[str, Any]] = Field(default_factory=list)
    added_categories: list[str] = Field(default_factory=list)
    removed_categories: list[str] = Field(default_factory=list)
    pillar_count_deltas: dict[str, int] = Field(default_factory=dict)
