from app.services import graph_service as gs


def test_classify_stage_known_keywords():
    assert gs.classify_stage("MARKET INTELLIGENCE & VERTICAL TARGETING") == "VCC-01"
    assert gs.classify_stage("BACK OFFICE OPS, COMPLIANCE & PLATFORM") == "VCC-08"
    assert gs.classify_stage("ADVISOR PLATFORM & DATA") == "VCC-03"
    assert gs.classify_stage("PRODUCT STRATEGY & DEVELOPMENT") == "VCC-04"


def test_classify_stage_unknown_returns_vcc00():
    assert gs.classify_stage("xyz unknown stage") == "VCC-00"


def test_extract_uc_tag():
    assert gs.extract_uc_tag("[AI_AUTHOR]: AI-assisted authoring") == "AI_AUTHOR"
    assert gs.extract_uc_tag("AI_AUTHOR") is None  # needs brackets
    assert gs.extract_uc_tag(None) is None


def test_family_for_tag():
    assert gs.family_for_tag("AI_AUTHOR") == "strategic"
    assert gs.family_for_tag("WORKFLOW_CADENCE") == "workflow"
    assert gs.family_for_tag("AUDIT_TRAIL") == "governance_risk"
    assert gs.family_for_tag("REG_REPORTING") == "reporting_validation"
    assert gs.family_for_tag("UNKNOWN_TAG") is None
