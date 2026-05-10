from enum import Enum


class ClaimLabel(str, Enum):
    FACT = "FACT"
    INFERENCE = "INFERENCE"
    HYPOTHESIS = "HYPOTHESIS"
    CEILING_ESTIMATE = "CEILING_ESTIMATE"


class SourceTier(str, Enum):
    T1 = "T1"  # primary regulators / official partner platform
    T2 = "T2"  # trade publications / analyst & strategy firms (cited)
    T3 = "T3"  # ESG / AI research
    T4 = "T4"  # technographic signals
    T5 = "T5"  # vendor self-promotion / press releases


class LifecycleState(str, Enum):
    ACTIVE = "active"
    HIGH_VALUE = "high_value"
    DECAY = "decay"
    INACTIVE = "inactive"
    PROPOSED = "proposed"
    RETIRED = "retired"


class MaturityLevel(str, Enum):
    M1 = "M1"
    M2 = "M2"
    M3 = "M3"
    M4 = "M4"
    M5 = "M5"
