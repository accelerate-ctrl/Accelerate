from app.services.hallucination import detect_unsupported_claims


def test_detects_no_citation():
    issues = detect_unsupported_claims([{"text": "foo bar baz quux", "sources": []}], [])
    assert issues
    assert issues[0]["reason"] == "no citations"


def test_detects_zero_overlap():
    src = {"id": "s1", "text": "tomatoes basil garden compost"}
    claim = {"text": "blockchain quantum cryptography algorithms", "sources": ["s1"]}
    issues = detect_unsupported_claims([claim], [src])
    assert issues
    assert issues[0]["overlap"] == 0


def test_passes_when_overlap_meets_threshold():
    src = {"id": "s1", "text": "digital banking strategy retail customer onboarding"}
    claim = {"text": "digital banking retail strategy", "sources": ["s1"]}
    issues = detect_unsupported_claims([claim], [src])
    assert not issues


def test_handles_unknown_source_id():
    src = {"id": "s1", "text": "anything"}
    claim = {"text": "foo bar baz quux", "sources": ["s2"]}
    issues = detect_unsupported_claims([claim], [src])
    assert issues
