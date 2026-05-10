"""Catalogue spine. Schema mirrors the Pillar 1 capability map (sheet 2_Capability_Map)."""
from pydantic import BaseModel, Field

from .common import LifecycleState


class Subcap(BaseModel):
    sub_cap_id: str
    sub_cap_name: str
    pillar_id: str
    category_id: str
    l1_capability: str
    description: str | None = None
    solution_type: str | None = None
    tier: str = "T1"  # subcap tier: T1 | T2 (different from source tier)
    personas: list[str] = Field(default_factory=list)
    l3_platforms: list[str] = Field(default_factory=list)
    l4_features: list[str] = Field(default_factory=list)
    use_cases: list[str] = Field(default_factory=list)
    story_refs: list[str] = Field(default_factory=list)
    zennify_status: str | None = None
    lifecycle_state: LifecycleState = LifecycleState.ACTIVE


class L1Capability(BaseModel):
    category_id: str
    name: str
    pillar_id: str


class Pillar(BaseModel):
    pillar_id: str  # P1..P4
    name: str
    description: str | None = None
