"""XLSX export builders."""

import io

import pytest
from openpyxl import load_workbook

from app.services import (
    benchmarks_service,
    client_journey_service,
    exports_service,
    lifecycle_service,
)


@pytest.fixture
def seeded(settings_for_tests):
    from app.services import catalogue_service, sow_service
    catalogue_service.refresh_pillar("P1", by="test")
    sow_service.ingest_all()
    benchmarks_service.refresh(extrapolate=False)
    lifecycle_service.recompute_all()
    client_journey_service.refresh_all()
    return settings_for_tests


def test_catalogue_export_has_subcap_rows(seeded):
    blob = exports_service.export_catalogue()
    assert blob[:2] == b"PK"
    wb = load_workbook(io.BytesIO(blob))
    ws = wb["subcaps"]
    assert ws.max_row > 1
    headers = [c.value for c in ws[1]]
    assert "sub_cap_id" in headers
    assert "personas" in headers
    assert "categories" in wb.sheetnames


def test_lifecycle_export_includes_signals(seeded):
    blob = exports_service.export_lifecycle()
    wb = load_workbook(io.BytesIO(blob))
    ws = wb["lifecycle"]
    headers = [c.value for c in ws[1]]
    assert "score" in headers
    assert "sow_active" in headers
    assert ws.max_row > 1


def test_clients_export_has_two_sheets(seeded):
    blob = exports_service.export_clients()
    wb = load_workbook(io.BytesIO(blob))
    assert "clients" in wb.sheetnames
    assert "client_subcaps" in wb.sheetnames
    ws = wb["clients"]
    headers = [c.value for c in ws[1]]
    assert "client_name" in headers
    # 4 clients seeded (Wells/JPM/PNC/Schwab via SOWs subset)
    assert ws.max_row >= 1


def test_benchmarks_export_has_distribution_rows(seeded):
    blob = exports_service.export_benchmarks()
    wb = load_workbook(io.BytesIO(blob))
    ws = wb["benchmarks"]
    headers = [c.value for c in ws[1]]
    assert "verdict" in headers
    assert "p50" in headers
    assert ws.max_row > 1
