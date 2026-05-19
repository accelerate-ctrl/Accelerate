"""Manual pillar-upload endpoint — POST /api/sheets/upload."""
from __future__ import annotations

from io import BytesIO

import openpyxl


def _empty_workbook(missing_capmap: bool = False) -> bytes:
    wb = openpyxl.Workbook()
    wb.active.title = "1_Overview"
    wb.active["A1"] = "Section"
    if not missing_capmap:
        ws = wb.create_sheet("2_Capability_Map")
        ws.append(["Category", "L1_Capability", "Sub_Cap_ID", "Sub_Cap_Name"])
        ws.append(["Cat1", "L1A", "P2C1.1.1", "Test Subcap"])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_upload_rejects_unknown_pillar(client, auth_headers):
    r = client.post(
        "/api/sheets/upload",
        headers=auth_headers,
        data={"pillar_id": "P9"},
        files={"file": ("p.xlsx", _empty_workbook(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r.status_code == 400
    assert "pillar_id" in r.json()["detail"]


def test_upload_rejects_non_xlsx(client, auth_headers):
    r = client.post(
        "/api/sheets/upload",
        headers=auth_headers,
        data={"pillar_id": "P2"},
        files={"file": ("p.txt", b"hello", "text/plain")},
    )
    assert r.status_code == 400


def test_upload_rejects_empty_body(client, auth_headers):
    r = client.post(
        "/api/sheets/upload",
        headers=auth_headers,
        data={"pillar_id": "P2"},
        files={"file": ("p.xlsx", b"", "application/octet-stream")},
    )
    assert r.status_code == 400


def test_upload_minimal_workbook_round_trip(client, auth_headers):
    r = client.post(
        "/api/sheets/upload",
        headers=auth_headers,
        data={"pillar_id": "P2"},
        files={"file": ("test_p2.xlsx", _empty_workbook(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pillars_loaded"] == ["P2"]
    assert body["counts_by_pillar"]["P2"]["subcaps"] == 1
    assert body["run_id"].startswith("upload-P2-")

    # State endpoint should now reflect the upload.
    state = client.get("/api/sheets/state", headers=auth_headers).json()
    p2 = next(p for p in state["pillars"] if p["pillar_id"] == "P2")
    assert p2["schema_status"] == "complete"
    assert p2["source_file_name"] == "test_p2.xlsx"
    assert p2["row_counts"]["subcaps"] == 1


def test_upload_flags_schema_deviation(client, auth_headers):
    """A workbook missing 2_Capability_Map should raise a flag and surface
    incomplete schema status — the parser persists what it can but the
    pillar doc carries the deviation so the UI shows a banner."""
    r = client.post(
        "/api/sheets/upload",
        headers=auth_headers,
        data={"pillar_id": "P3"},
        files={"file": ("broken.xlsx", _empty_workbook(missing_capmap=True), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    # parse_workbook returns an incomplete ParseResult rather than raising,
    # so we still get a 200 with a flag.
    assert r.status_code == 200
    body = r.json()
    # No subcaps loaded → ingest_uploaded_workbook still persists the pillar
    # doc with incomplete status.
    state = client.get("/api/sheets/state", headers=auth_headers).json()
    p3 = next(p for p in state["pillars"] if p["pillar_id"] == "P3")
    assert p3["schema_status"] == "incomplete"
    # Should have raised an SCHEMA_INCOMPLETE flag.
    assert body["flags_raised"], "expected schema deviation flag"
