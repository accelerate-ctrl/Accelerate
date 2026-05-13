from app.services.sheets_parser import parse_workbook


def test_parse_pillar1_attached_file(pillar1_file):
    result = parse_workbook(pillar1_file)
    assert result.pillar_id == "P1"
    assert result.schema_status == "complete"
    assert len(result.subcaps) >= 100, "expected ~199 subcaps in Pillar 1 v14.0"
    # Spot-check a known subcap
    sids = {s["sub_cap_id"] for s in result.subcaps}
    assert "P1C1.1.1" in sids
    # L3, L4, maturity, themes
    assert len(result.l3_platforms) >= 30
    assert len(result.l4_features) >= 100
    assert len(result.maturity_descriptors) >= 100
    assert len(result.theme_mappings) >= 10


def test_parse_returns_pillar_metadata(pillar1_file):
    result = parse_workbook(pillar1_file)
    assert result.pillars[0]["pillar_id"] == "P1"
    assert "Strategic" in result.pillars[0]["name"]


def test_parse_handles_missing_sheets():
    # Build a tiny xlsx in memory missing 2_Capability_Map → should report incomplete
    from io import BytesIO

    import openpyxl
    wb = openpyxl.Workbook()
    wb.active.title = "1_Overview"
    wb.active["A1"] = "header"
    buf = BytesIO()
    wb.save(buf)
    result = parse_workbook(buf.getvalue(), default_pillar_id="P2")
    assert result.schema_status == "incomplete"
    assert result.pillar_id == "P2"
