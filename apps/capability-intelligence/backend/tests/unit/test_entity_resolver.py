from app.services import entity_resolver as er


def test_exact_alias_match():
    er.reset_cache_for_tests()
    r = er.resolve("WFC", kind="client")
    assert r.canonical == "Wells Fargo"
    assert r.method == "exact_alias"
    assert r.confidence == 100.0


def test_fuzzy_match_close_spelling():
    er.reset_cache_for_tests()
    r = er.resolve("Wells Fargo Bank", kind="client")
    assert r.canonical == "Wells Fargo"
    assert r.method in {"exact_alias", "fuzzy"}


def test_passthrough_unknown():
    er.reset_cache_for_tests()
    r = er.resolve("Acme Holdings", kind="client")
    assert r.canonical == "Acme Holdings"
    assert r.method == "passthrough"
    assert r.confidence == 0


def test_kind_isolation():
    er.reset_cache_for_tests()
    # 'OCC' is a regulator alias, not a client alias
    r_client = er.resolve("OCC", kind="client")
    r_reg = er.resolve("OCC", kind="regulator")
    assert r_reg.canonical == "OCC"
    assert r_reg.method == "exact_alias"
    assert r_client.method == "passthrough"
