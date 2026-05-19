"""Tests for the v7.0-schema-aware persona parser (PRD FR-1, AC-4)."""

from app.models.common import PersonaFamily
from app.services.ingestion.persona_parser import (
    PersonaRef,
    parse_persona_names,
    parse_personas,
)


def test_empty_inputs_return_empty_list():
    assert parse_personas(None) == []
    assert parse_personas("") == []
    assert parse_personas("   ") == []


def test_single_persona_no_role():
    refs = parse_personas("CDO")
    assert len(refs) == 1
    assert refs[0].canonical_name == "CDO"
    assert refs[0].role_description is None
    assert refs[0].family == PersonaFamily.C_SUITE


def test_single_persona_with_role():
    refs = parse_personas("CDO (Chief Data Officer)")
    assert len(refs) == 1
    assert refs[0].canonical_name == "CDO"
    assert refs[0].role_description == "Chief Data Officer"
    assert refs[0].family == PersonaFamily.C_SUITE


def test_semicolon_separated_personas():
    refs = parse_personas("CDO; LOB Heads")
    assert [r.canonical_name for r in refs] == ["CDO", "LOB Heads"]
    assert refs[0].family == PersonaFamily.C_SUITE
    assert refs[1].family == PersonaFamily.OPERATIONS


def test_comma_inside_paren_is_not_a_top_level_delimiter():
    """The bug case from the design docs.

    ``CDO (Chief Data Officer, Data Lead); LOB Heads`` should yield exactly
    2 personas, not 3. The old ``re.split(r"[,;\\n]", ...)`` regex would
    split inside the parenthetical and produce
    ``["CDO (Chief Data Officer", "Data Lead)", "LOB Heads"]``.
    """
    refs = parse_personas("CDO (Chief Data Officer, Data Lead); LOB Heads (Line of Business Leads)")
    assert len(refs) == 2
    assert refs[0].canonical_name == "CDO"
    assert refs[0].role_description == "Chief Data Officer, Data Lead"
    assert refs[1].canonical_name == "LOB Heads"
    assert refs[1].role_description == "Line of Business Leads"


def test_newline_is_a_top_level_delimiter():
    refs = parse_personas("CDO (Chief Data Officer)\nCTO (Chief Technology Officer)")
    assert [r.canonical_name for r in refs] == ["CDO", "CTO"]


def test_family_mapping_falls_back_to_operations_for_unknown():
    refs = parse_personas("Some Made-Up Title")
    assert len(refs) == 1
    assert refs[0].family == PersonaFamily.OPERATIONS


def test_family_mapping_substring_match():
    """``Head of Data`` should match the ``data`` family hint."""
    refs = parse_personas("Head of Data Engineering")
    assert len(refs) == 1
    # 'data engineer' is in the family map → technology
    assert refs[0].family == PersonaFamily.TECHNOLOGY


def test_persona_ref_serializes_with_schema_version_alias():
    ref = parse_personas("CDO")[0]
    dumped = ref.model_dump(by_alias=True)
    assert dumped["_schema_version"] == "persona-ref-v1"
    assert dumped["canonical_name"] == "CDO"
    assert dumped["family"] == "c_suite"


def test_parse_persona_names_convenience_wrapper():
    names = parse_persona_names("CDO (Chief Data Officer, Data Lead); LOB Heads")
    assert names == ["CDO", "LOB Heads"]


def test_raw_token_is_preserved():
    refs = parse_personas("  CDO  (Chief Data Officer)  ;  CTO  ")
    assert refs[0].raw.startswith("CDO")
    assert refs[1].raw == "CTO"


def test_unmatched_paren_does_not_crash():
    refs = parse_personas("CDO (Chief Data Officer; CTO")
    # The outer ``;`` is inside the unclosed paren so the whole thing is
    # one token; we still surface it rather than drop it.
    assert len(refs) >= 1
    assert refs[0].canonical_name.startswith("CDO")


def test_returns_persona_ref_instances():
    refs = parse_personas("CDO")
    assert isinstance(refs[0], PersonaRef)


def test_v14_comma_separated_back_compat():
    """The v14 fixture uses commas as the top-level delimiter and never
    carries parentheticals. The schema-aware tokenizer must still split
    these correctly during the v14 -> v7.0 migration window.
    """
    refs = parse_personas("CIO, CDO, Chief Strategy Officer, Strategy & Planning Lead")
    assert [r.canonical_name for r in refs] == [
        "CIO",
        "CDO",
        "Chief Strategy Officer",
        "Strategy & Planning Lead",
    ]


def test_v7_paren_content_preserved_when_commas_present():
    """When parentheses are present, commas inside them must NOT split
    even though the cell also has top-level semicolons.
    """
    refs = parse_personas("Risk Officer (Risk, Compliance, Model Risk); Audit Lead")
    assert len(refs) == 2
    assert refs[0].canonical_name == "Risk Officer"
    assert refs[0].role_description == "Risk, Compliance, Model Risk"
    assert refs[1].canonical_name == "Audit Lead"
