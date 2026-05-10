from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

FlagSeverity = Literal["LOW", "MEDIUM", "HIGH", "BLOCKING"]
FlagKind = Literal[
    "MAPPING_REGRESSION",
    "THEME_ALIGNMENT",
    "SCHEMA_INCOMPLETE",
    "MISSING_PILLAR",
    "DUPLICATE_SUBCAP_ID",
    "ORPHAN_SUBCAP",
    "INGEST_FAILURE",
    "DRIFT_ALERT",
]


class ChangeFlag(BaseModel):
    flag_id: str
    kind: FlagKind
    severity: FlagSeverity = "MEDIUM"
    target_type: str  # "pillar" | "subcap" | "category" | "version" | "ingest"
    target_id: str
    title: str
    detail: str
    detected_at: datetime
    detected_by: str = "system"
    resolved_at: datetime | None = None
    resolved_by: str | None = None
    resolution_note: str | None = None
    extra: dict = Field(default_factory=dict)
