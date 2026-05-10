from app.services.sow_service import chunk_text, extract_mentions


def test_chunk_text_paragraph_aware():
    text = ("para one " * 100) + "\n\n" + ("para two " * 100) + "\n\n" + ("para three " * 100)
    chunks = chunk_text(text, target_chars=600, overlap=50)
    assert len(chunks) >= 2
    # Each chunk roughly within target
    assert all(len(c) <= 1200 for c in chunks)


def test_extract_mentions_exact_id():
    chunks = ["We will deliver P1C1.1.1 (Digital Strategy Document) for the client."]
    subcaps = [{"sub_cap_id": "P1C1.1.1", "sub_cap_name": "Digital Strategy Document"}]
    mentions = extract_mentions(chunks, subcaps)
    assert len(mentions) == 1
    assert mentions[0].sub_cap_id == "P1C1.1.1"
    assert mentions[0].method == "exact_id"
    assert mentions[0].confidence >= 99


def test_extract_mentions_name_only():
    chunks = ["The Digital Strategy Document is the central artefact."]
    subcaps = [{"sub_cap_id": "P1C1.1.1", "sub_cap_name": "Digital Strategy Document"}]
    mentions = extract_mentions(chunks, subcaps)
    assert len(mentions) == 1
    assert mentions[0].method == "name_substring"


def test_extract_mentions_no_double_count():
    """If a chunk has BOTH the ID and the name, only the exact-ID hit counts."""
    chunks = ["P1C1.1.1 Digital Strategy Document"]
    subcaps = [{"sub_cap_id": "P1C1.1.1", "sub_cap_name": "Digital Strategy Document"}]
    mentions = extract_mentions(chunks, subcaps)
    assert len([m for m in mentions if m.sub_cap_id == "P1C1.1.1"]) == 1
