from datetime import datetime, timedelta

from app.services.drive_service import (
    CatalogueFile,
    _parse_version_tuple,
    _pillar_id_from_folder_name,
    _select_active_file,
    list_pillar_files,
)


def test_pillar_id_from_folder_name():
    assert _pillar_id_from_folder_name("Pillar 1") == "P1"
    assert _pillar_id_from_folder_name("P2") == "P2"
    assert _pillar_id_from_folder_name("pillar_3") == "P3"
    assert _pillar_id_from_folder_name("4. Data and AI") == "P4"
    assert _pillar_id_from_folder_name("misc") is None


def test_parse_version_tuple():
    assert _parse_version_tuple("Pillar_1_Capability_Map_v14.0.xlsx") == (14, 0)
    assert _parse_version_tuple("v3_2_old.xlsx") == (3, 2)
    assert _parse_version_tuple("no_version_here.xlsx") is None


def test_select_active_excludes_inactive_picks_highest():
    now = datetime.utcnow()
    files = [
        CatalogueFile(pillar_id="P1", file_id="x1", file_name="P1_v14.0.xlsx", modified_at=now, parsed_version=None, source="local"),
        CatalogueFile(pillar_id="P1", file_id="x2", file_name="P1_v15.0_inactive.xlsx", modified_at=now + timedelta(days=10), parsed_version=None, source="local"),
        CatalogueFile(pillar_id="P1", file_id="x3", file_name="P1_v13.5.xlsx", modified_at=now, parsed_version=None, source="local"),
    ]
    chosen = _select_active_file(files)
    assert chosen.file_id == "x1"


def test_select_active_falls_back_to_modified_time():
    now = datetime.utcnow()
    files = [
        CatalogueFile(pillar_id="P1", file_id="x1", file_name="alpha.xlsx", modified_at=now - timedelta(days=2), parsed_version=None, source="local"),
        CatalogueFile(pillar_id="P1", file_id="x2", file_name="beta.xlsx", modified_at=now, parsed_version=None, source="local"),
    ]
    chosen = _select_active_file(files)
    assert chosen.file_id == "x2"


def test_local_listing_picks_active(settings_for_tests):
    files = list_pillar_files()
    assert "P1" in files
    chosen = files["P1"]
    assert "v14.0" in chosen.file_name
    assert "inactive" not in chosen.file_name.lower()
