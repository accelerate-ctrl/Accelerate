"""Catalogue spine. Schema mirrors the Pillar 1 capability map sheets."""
from datetime import datetime

from pydantic import BaseModel, Field

from .common import LifecycleState


class Pillar(BaseModel):
    pillar_id: str  # P1..P4
    name: str
    description: str | None = None
    schema_status: str = "complete"  # "complete" | "incomplete" | "missing"
    source_file_id: str | None = None
    source_file_name: str | None = None
    source_file_modified_at: datetime | None = None
    source_version: str | None = None  # e.g. "v14.0"


class Category(BaseModel):
    category_id: str
    pillar_id: str
    name: str


class L1Capability(BaseModel):
    l1_id: str  # we synthesize as "<category_id>.<l1_name_slug>" if not present
    category_id: str
    pillar_id: str
    name: str


class Subcap(BaseModel):
    sub_cap_id: str
    sub_cap_name: str
    pillar_id: str
    category_id: str
    l1_capability: str
    description: str | None = None
    solution_type: str | None = None
    tier: str = "T1"  # subcap tier T1 | T2
    personas: list[str] = Field(default_factory=list)
    l3_platforms: list[str] = Field(default_factory=list)
    l4_features: list[str] = Field(default_factory=list)
    use_cases: list[str] = Field(default_factory=list)
    story_refs: list[str] = Field(default_factory=list)
    zennify_status: str | None = None
    lifecycle_state: LifecycleState = LifecycleState.ACTIVE


class UseCase(BaseModel):
    use_case_id: str  # e.g. P1C1.1.1.UC1
    sub_cap_id: str
    label: str  # e.g. "AI_AUTHOR"
    description: str | None = None


class L3Platform(BaseModel):
    l3_id: str
    vendor: str | None = None
    name: str
    category: str | None = None
    description: str | None = None
    detailed_capabilities: str | None = None
    setup_path: str | None = None
    prerequisites: str | None = None
    customization_extension_points: str | None = None
    common_combinations: str | None = None
    pricing_tier_notes: str | None = None
    linked_l4_features: str | None = None
    linked_sub_caps_top5: str | None = None
    reference_url: str | None = None


class L4Feature(BaseModel):
    sub_cap_id: str
    l3_platform_id: str | None = None
    feature_name: str
    vendor: str | None = None
    feature_type: str | None = None
    customization_level: str | None = None
    detailed_description: str | None = None
    configuration_path: str | None = None
    use_case_ids_using_feature: str | None = None
    reference_url: str | None = None


class MaturityDescriptor(BaseModel):
    sub_cap_id: str
    sub_cap_name: str
    category_id: str
    l1_capability: str
    m1: str | None = None
    m1_features: str | None = None
    m2: str | None = None
    m2_features: str | None = None
    m3: str | None = None
    m3_features: str | None = None
    m4: str | None = None
    m4_features: str | None = None
    m5: str | None = None
    m5_features: str | None = None
