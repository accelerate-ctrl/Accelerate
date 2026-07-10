"""Self-gathered release evidence: the bench's own web retrieval for the
Salesforce release crosswalk.

Makes the pre-intelligence layer semi-autonomous: instead of depending on a
web-capable judge to run the crosswalk searches, the server gathers the
evidence itself — keyless HTML search (DuckDuckGo endpoint, no API key),
filtered at retrieval to Salesforce-controlled domains (the same R23 rule the
validator enforces), deduplicated and capped deterministically.

Covenant unchanged: retrieval is PREPARATION, not judgment. The gathered
snippets flow into the engine's `release_crosswalk.py resolve`, which alone
classifies status (and only from *.salesforce.com snippets); the R23
validator remains the enforcement point; review_evidence still writes the
advisory relevance/domain audit. A judge packet remains the fallback when
the crawl returns nothing (offline, blocked egress, empty results).

Test seam: W2_EVIDENCE_FIXTURE=<path.json> serves evidence from a canned
{mechanism_key: [items], "*": [items]} map instead of the network — the
normalize/filter path is identical, so wiring tests run offline.
"""
from __future__ import annotations
import json
import os
import time
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

from .release_support import _domain_ok

USER_AGENT = "Mozilla/5.0 (compatible; W2EvalBench/2.0; release-crosswalk)"
SEARCH_ENDPOINT = "https://html.duckduckgo.com/html/?q="
# Prefer primary documentation surfaces when ranking gathered items.
_DOMAIN_RANK = {"help.salesforce.com": 0, "developer.salesforce.com": 1,
                "admin.salesforce.com": 2, "www.salesforce.com": 3}


def _http_get(url: str, timeout: float = 8.0) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        # Search engines answer bot challenges with 2xx-but-not-200 (DDG
        # sends 202 "anomaly" pages from data-center IPs). Treat anything
        # but a real 200 as a failed search so the caller moves on and the
        # judge-packet fallback engages instead of parsing a challenge page.
        if r.status != 200:
            raise OSError(f"search endpoint answered {r.status}")
        return r.read().decode("utf-8", "replace")


def _decode_result_url(href: str) -> str:
    """DDG result links arrive as //duckduckgo.com/l/?uddg=<urlencoded>."""
    if "uddg=" in (href or ""):
        qs = urllib.parse.parse_qs(urllib.parse.urlsplit(href).query)
        vals = qs.get("uddg")
        if vals:
            return vals[0]
    return href or ""


class _ResultParser(HTMLParser):
    """Pairs each result link (a.result__a) with its snippet
    (a/div.result__snippet), order-preserving."""

    def __init__(self):
        super().__init__()
        self.results: list[dict] = []
        self._in = None  # "title" | "snippet"

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class") or ""
        if "result__a" in cls:
            self._in = "title"
            self.results.append({"url": _decode_result_url(a.get("href", "")),
                                 "title": "", "snippet": ""})
        elif "result__snippet" in cls and self.results:
            self._in = "snippet"

    def handle_endtag(self, tag):
        if tag == "a" and self._in == "title":
            self._in = None
        elif self._in == "snippet" and tag in ("a", "div", "td"):
            self._in = None

    def handle_data(self, data):
        if self._in and self.results:
            key = "title" if self._in == "title" else "snippet"
            self.results[-1][key] += data


def _parse_results(html: str) -> list[dict]:
    p = _ResultParser()
    try:
        p.feed(html or "")
    except Exception:
        pass
    return [{"url": r["url"].strip(), "title": " ".join(r["title"].split()),
             "snippet": " ".join(r["snippet"].split())}
            for r in p.results if r["url"].strip()]


def _rank(url: str) -> int:
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    return _DOMAIN_RANK.get(host, 9)


def _normalize(items: list[dict], cap: int, as_of: str) -> list[dict]:
    """Salesforce-domain filter (R23 at retrieval), URL-dedupe, stable rank
    by documentation-surface preference then original order, cap."""
    seen, out = set(), []
    for i, it in enumerate(items or []):
        url = (it.get("url") or "").strip()
        if not url or url in seen or not _domain_ok(url):
            continue
        seen.add(url)
        out.append((_rank(url), i, {"url": url,
                                    "title": (it.get("title") or "").strip(),
                                    "snippet": (it.get("snippet") or "").strip(),
                                    "as_of": it.get("as_of") or as_of}))
    out.sort(key=lambda t: (t[0], t[1]))
    return [it for _, _, it in out[:cap]]


def gather_evidence(queries: list[dict], *, fetch=None, per_mechanism: int = 3,
                    max_searches: int = 2, deadline_s: float = 75.0) -> dict:
    """-> {"as_of","source","evidence": {mechanism_key: [{url,title,snippet,
    as_of}]}} — the exact shape release_crosswalk.py resolve consumes.
    Search plan per mechanism: the salesforce-scoped nlp variant first, the
    engine's own query second; stop at the first search with on-domain hits.
    A global deadline bounds a whole lane's crawl; mechanisms past the
    deadline simply get no items (resolve falls back to the register)."""
    as_of = time.strftime("%Y-%m-%d")
    fixture = os.environ.get("W2_EVIDENCE_FIXTURE")
    out: dict = {}
    if fixture:
        fx = json.loads(Path(fixture).read_text())
        for q in queries or []:
            key = q.get("mechanism_key")
            if key:
                out[key] = _normalize(fx.get(key, fx.get("*", [])),
                                      per_mechanism, as_of)
        return {"as_of": as_of, "source": "self-crawl(fixture)", "evidence": out}
    fetch = fetch or _http_get
    t0 = time.monotonic()
    for q in queries or []:
        key = q.get("mechanism_key")
        if not key:
            continue
        if time.monotonic() - t0 > deadline_s:
            out[key] = []
            continue
        plans = [(q.get("nlp_variants") or [""])[0], q.get("query") or ""]
        found: list[dict] = []
        for s in [p for p in plans if p][:max_searches]:
            try:
                html = fetch(SEARCH_ENDPOINT + urllib.parse.quote(s))
            except Exception:
                continue
            found = [r for r in _parse_results(html) if _domain_ok(r["url"])]
            if found:
                break
        out[key] = _normalize(found, per_mechanism, as_of)
    return {"as_of": as_of, "source": "self-crawl", "evidence": out}
