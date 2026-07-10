"""Self-gathered release evidence (nlp/web_evidence.py): search-result
parsing, the R23 domain rule applied at retrieval, deterministic
normalization, and the fixture seam the smoke uses. All offline — the
fetcher is injected; no network is touched."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine" / "evaluate-sdd" / "scripts"))

from nlp.web_evidence import gather_evidence, _parse_results  # noqa: E402

QUERIES = [{"mechanism_key": "shield_platform_encryption",
            "mechanism_name": "Shield Platform Encryption",
            "query": "Shield Platform Encryption Salesforce status",
            "nlp_variants": ['"Shield Platform Encryption" site:help.salesforce.com'],
            "source": "regex_floor"}]

DDG_HTML = """
<div class="result">
 <a rel="nofollow" class="result__a"
    href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fhelp.salesforce.com%2Fs%2FarticleView%3Fid%3Dsecurity_pe">
   Shield <b>Platform Encryption</b></a>
 <a class="result__snippet" href="#">Encrypt data at rest with Shield Platform Encryption.</a>
</div>
<div class="result">
 <a rel="nofollow" class="result__a" href="https://someblog.example.com/sf-tips">Ten tips</a>
 <a class="result__snippet" href="#">unrelated advice</a>
</div>
<div class="result">
 <a rel="nofollow" class="result__a"
    href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fhelp.salesforce.com%2Fs%2FarticleView%3Fid%3Dsecurity_pe">
   duplicate of the first</a>
 <a class="result__snippet" href="#">same URL again</a>
</div>
<div class="result">
 <a rel="nofollow" class="result__a"
    href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fdeveloper.salesforce.com%2Fdocs%2Fpe">
   Platform Encryption developer guide</a>
 <a class="result__snippet" href="#">Developer guide.</a>
</div>
"""


class ParseAndFilter(unittest.TestCase):
    def test_parse_decodes_and_pairs(self):
        rows = _parse_results(DDG_HTML)
        self.assertEqual(rows[0]["url"],
                         "https://help.salesforce.com/s/articleView?id=security_pe")
        self.assertIn("Platform Encryption", rows[0]["title"])
        self.assertIn("Encrypt data at rest", rows[0]["snippet"])
        self.assertEqual(rows[1]["url"], "https://someblog.example.com/sf-tips")

    def test_gather_filters_dedupes_and_shapes(self):
        out = gather_evidence(QUERIES, fetch=lambda url: DDG_HTML)
        items = out["evidence"]["shield_platform_encryption"]
        urls = [i["url"] for i in items]
        # off-domain dropped, duplicate collapsed, help.* ranked first
        self.assertEqual(urls, [
            "https://help.salesforce.com/s/articleView?id=security_pe",
            "https://developer.salesforce.com/docs/pe"])
        for i in items:
            self.assertEqual(set(i), {"url", "title", "snippet", "as_of"})
            self.assertTrue(i["as_of"])
        self.assertEqual(out["source"], "self-crawl")

    def test_empty_or_failing_search_yields_no_items(self):
        out = gather_evidence(QUERIES, fetch=lambda url: "<html></html>")
        self.assertEqual(out["evidence"]["shield_platform_encryption"], [])

        def boom(url):
            raise OSError("egress blocked")
        out2 = gather_evidence(QUERIES, fetch=boom)
        self.assertEqual(out2["evidence"]["shield_platform_encryption"], [])

    def test_deterministic_processing(self):
        a = gather_evidence(QUERIES, fetch=lambda url: DDG_HTML)
        b = gather_evidence(QUERIES, fetch=lambda url: DDG_HTML)
        self.assertEqual(a, b)


class FixtureSeam(unittest.TestCase):
    def test_fixture_served_through_same_normalizer(self):
        fx = {"*": [
            {"url": "https://help.salesforce.com/s/articleView?id=flow",
             "title": "Flow", "snippet": "Flow Builder is generally available."},
            {"url": "https://random-blog.io/post", "title": "off-domain",
             "snippet": "must be filtered even from a fixture"}]}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(fx, f)
            path = f.name
        os.environ["W2_EVIDENCE_FIXTURE"] = path
        try:
            out = gather_evidence(QUERIES)
            items = out["evidence"]["shield_platform_encryption"]
            self.assertEqual([i["url"] for i in items],
                             ["https://help.salesforce.com/s/articleView?id=flow"])
            self.assertEqual(out["source"], "self-crawl(fixture)")
        finally:
            os.environ.pop("W2_EVIDENCE_FIXTURE", None)
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
