"""Tests for the F07 source-independence fix.

The previous dedup treated every URL as its own independent source, so
``occ.gov/news/x`` and ``occ.gov/blog/y`` triangulated as 2-of-2 instead
of 1-of-2. The :func:`source_org_id` helper now collapses by publisher
organisation; G4 and the ERS independence component both consume it.
"""

from app.services.validation_gates_service import (
    distinct_source_orgs,
    gate_g4_independence,
    source_org_id,
)

# ─── source_org_id resolution order ────────────────────────────────────────


def test_explicit_source_org_id_wins():
    s = {"source_org_id": "OCC", "url": "https://example.com/x", "source_id": "fdic"}
    assert source_org_id(s) == "occ"


def test_source_id_resolves_when_no_explicit_org():
    assert source_org_id({"source_id": "occ", "url": "https://fdic.gov/x"}) == "occ"


def test_registrable_domain_from_url():
    assert source_org_id({"url": "https://www.occ.gov/news/2025/abc.html"}) == "occ.gov"
    assert source_org_id({"url": "https://occ.gov/news/2025/abc.html"}) == "occ.gov"
    assert source_org_id({"url": "https://blog.occ.gov/post-1"}) == "occ.gov"


def test_registrable_domain_two_label_public_suffix():
    assert source_org_id({"url": "https://news.bankofengland.co.uk/x"}) == "bankofengland.co.uk"


def test_source_field_fallback_when_no_url():
    # news_service stores the host on the ``source`` field directly.
    assert source_org_id({"source": "www.fdic.gov"}) == "fdic.gov"


def test_primary_source_id_last_resort():
    assert source_org_id({"primary_source_id": "filing-xyz-2024Q1"}) == "filing-xyz-2024q1"


def test_no_recoverable_id_returns_empty():
    assert source_org_id({}) == ""


def test_invalid_input_is_safe():
    assert source_org_id(None) == ""  # type: ignore[arg-type]
    assert source_org_id("notadict") == ""  # type: ignore[arg-type]


# ─── F07 — the actual bug case ─────────────────────────────────────────────


def test_two_urls_same_publisher_collapse_to_one_org():
    sources = [
        {"id": "n1", "url": "https://occ.gov/news/2025-01-01/a"},
        {"id": "n2", "url": "https://occ.gov/blog/2025-02-02/b"},
    ]
    assert distinct_source_orgs(sources) == {"occ.gov"}


def test_two_urls_different_publishers_count_as_two():
    sources = [
        {"id": "n1", "url": "https://occ.gov/news/a"},
        {"id": "n2", "url": "https://fdic.gov/news/b"},
    ]
    assert distinct_source_orgs(sources) == {"occ.gov", "fdic.gov"}


# ─── G4 gate ───────────────────────────────────────────────────────────────


def test_g4_fails_when_only_one_publisher_org():
    """Two articles, one publisher → fail. This is the F07 contract."""
    sources = [
        {"id": "n1", "url": "https://occ.gov/news/a", "tier": "T1"},
        {"id": "n2", "url": "https://occ.gov/blog/b", "tier": "T1"},
    ]
    r = gate_g4_independence({}, sources)
    assert r.verdict == "fail"
    assert "1 distinct publisher" in r.reasoning


def test_g4_passes_when_two_publisher_orgs():
    sources = [
        {"id": "n1", "url": "https://occ.gov/news/a", "tier": "T1"},
        {"id": "n2", "url": "https://fdic.gov/news/b", "tier": "T1"},
    ]
    r = gate_g4_independence({}, sources)
    assert r.verdict == "pass"
    assert "orgs" in r.details
    assert set(r.details["orgs"]) == {"occ.gov", "fdic.gov"}


def test_g4_warns_when_no_sources():
    r = gate_g4_independence({}, [])
    assert r.verdict == "warn"


def test_g4_respects_explicit_source_org_id_override():
    """The ingest layer can label cross-pillar sources with a shared
    ``source_org_id`` even when their URLs differ.
    """
    sources = [
        {"id": "1", "source_org_id": "vendor:salesforce", "url": "https://blog.salesforce.com/a"},
        {"id": "2", "source_org_id": "vendor:salesforce", "url": "https://help.salesforce.com/b"},
    ]
    r = gate_g4_independence({}, sources)
    assert r.verdict == "fail"  # Same org → not independent


def test_g4_handles_filing_primary_source_id():
    """Regulator filings carry their own primary_source_id pattern
    (``filing-{cik}-{period}``). Two filings from the same CIK + period
    must still collapse, but two filings from different CIKs must not.
    """
    sources = [
        {"id": "a", "primary_source_id": "filing-001-2024Q1"},
        {"id": "b", "primary_source_id": "filing-002-2024Q1"},
    ]
    r = gate_g4_independence({}, sources)
    # Two different primary source ids → two distinct orgs → pass
    assert r.verdict == "pass"
