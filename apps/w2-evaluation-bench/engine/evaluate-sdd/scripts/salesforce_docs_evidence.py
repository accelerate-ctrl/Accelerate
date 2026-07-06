#!/usr/bin/env python3
"""salesforce_docs_evidence.py — map captured Salesforce Docs MCP output into the
release-currency evidence schema that release_crosswalk.resolve consumes.

WHY THIS EXISTS
  references/salesforce-docs-mcp.md designs the Salesforce Docs connector as the
  PRIMARY, highest-trust evidence source for the release-currency crosswalk
  (every result carries an official *.salesforce.com URL, so it passes the R23
  source-authority guard with no relaxation). That reference left one step to be
  done by hand: "record (url, title, snippet, as_of) into release-evidence.json".
  This helper makes that step deterministic, testable, and auditable instead.

ARCHITECTURE (unchanged from the web_search contract)
  The ORCHESTRATOR owns the network. For each mechanism query emitted by
  `release_crosswalk.py extract`, the orchestrator calls
  `salesforce_docs_search` (and optionally `salesforce_docs_fetch` for a
  definitive sentence), and CAPTURES the raw tool output keyed by mechanism_key
  into a capture file. This helper — which performs NO network I/O — converts
  that capture into the exact `release-evidence-<lane>.json` schema. Then
  `release_crosswalk.py resolve` runs as before. The scripts stay offline and
  deterministic; only the orchestrator touches the connector.

CAPTURE INPUT SCHEMA (what the orchestrator writes; tolerant of shapes)
  {
    "lane": "A",
    "as_of": "2026-06-29",                # optional; defaults to today
    "searches": {
      "workflow_rules": <raw salesforce_docs_search result>,
      "process_builder": <raw salesforce_docs_search result>,
      ...
    }
  }
  Each <raw ... result> may be:
    - the connector's native object {"chunks": [ {content, url, documentPath,
      metadata:{title,...}}, ... ]}, OR
    - a {"results":[...]} / {"items":[...]} list, OR
    - a bare list of chunk-like dicts.
  The helper extracts (url, title, snippet, as_of) from each and drops any item
  lacking a url (resolve needs a url to weigh authority).

OUTPUT  (exactly what resolve reads)
  { "lane": "A", "results": { "<mechanism_key>": [ {url,title,snippet,as_of}, ... ] } }

This helper does NOT classify status or set deductions — that is resolve's job,
under the unchanged source-authority policy. It only shapes evidence.
"""
from __future__ import annotations
import argparse, json, re, sys
from datetime import date
from pathlib import Path


def _chunks_of(raw) -> list:
    """Pull the list of chunk-like dicts out of whatever shape the orchestrator
    captured. Tolerant by design so a minor connector-format change doesn't break
    the pipeline."""
    if raw is None:
        return []
    if isinstance(raw, list):
        return [c for c in raw if isinstance(c, dict)]
    if isinstance(raw, dict):
        for key in ("chunks", "results", "items", "data"):
            v = raw.get(key)
            if isinstance(v, list):
                return [c for c in v if isinstance(c, dict)]
        # a single chunk dict
        if raw.get("url") or raw.get("content") or raw.get("documentPath"):
            return [raw]
    return []


def _release_from(chunk: dict) -> str | None:
    """Best-effort Salesforce release number (e.g. 260) from the documentPath or
    url, captured as provenance only — never used to set status."""
    for field in ("documentPath", "url"):
        s = str(chunk.get(field, ""))
        m = re.search(r"(?:release=|/)(\d{3})(?:-\d-\d|\b)", s)
        if m:
            return m.group(1)
    return None


def chunk_to_evidence(chunk: dict, as_of_default: str) -> dict | None:
    """Map one connector chunk to one evidence item {url,title,snippet,as_of}.
    Returns None if there is no url (resolve cannot weigh authority without one)."""
    url = chunk.get("url") or ""
    if not url:
        return None
    title = (chunk.get("metadata") or {}).get("title") or chunk.get("title") or ""
    # snippet: prefer the rich doc content the connector returns; fall back to any
    # snippet/excerpt field. Collapse whitespace so the classifier reads cleanly.
    snippet = chunk.get("content") or chunk.get("snippet") or chunk.get("excerpt") or ""
    snippet = re.sub(r"\s+", " ", str(snippet)).strip()
    item = {"url": url, "title": str(title).strip(), "snippet": snippet,
            "as_of": as_of_default}
    rel = _release_from(chunk)
    if rel:
        item["salesforce_release"] = rel          # provenance only
        item["source"] = "salesforce_docs_mcp"
    else:
        item["source"] = "salesforce_docs_mcp"
    return item


def build_evidence(capture: dict, as_of_default: str | None = None) -> dict:
    lane = capture.get("lane", "A")
    as_of = capture.get("as_of") or as_of_default or date.today().isoformat()
    searches = capture.get("searches") or capture.get("by_mechanism") or {}
    results: dict[str, list] = {}
    for mech_key, raw in searches.items():
        items = []
        for chunk in _chunks_of(raw):
            ev = chunk_to_evidence(chunk, as_of)
            if ev:
                items.append(ev)
        # de-dup identical urls within a mechanism (connector often returns the
        # same lifecycle banner across several pages)
        seen, deduped = set(), []
        for ev in items:
            k = (ev["url"], ev["snippet"][:120])
            if k not in seen:
                seen.add(k)
                deduped.append(ev)
        results[mech_key] = deduped
    return {"lane": lane, "results": results,
            "evidence_source": "salesforce_docs_mcp",
            "note": ("Built from captured Salesforce Docs MCP output. resolve applies "
                     "the unchanged R23 source-authority policy; MCP URLs are "
                     "Salesforce-controlled by construction.")}


def main() -> int:
    ap = argparse.ArgumentParser(description="Map captured Salesforce Docs MCP "
                                 "output into release-evidence-<lane>.json.")
    ap.add_argument("--capture", required=True, type=Path,
                    help="JSON the orchestrator wrote: {lane, as_of?, searches:{mech:raw}}")
    ap.add_argument("--lane", default=None, help="override lane (else from capture)")
    ap.add_argument("--as-of", default=None, help="YYYY-MM-DD (else capture.as_of or today)")
    ap.add_argument("--output", required=True, type=Path,
                    help="where to write release-evidence-<lane>.json")
    args = ap.parse_args()
    capture = json.loads(args.capture.read_text())
    if args.lane:
        capture["lane"] = args.lane
    ev = build_evidence(capture, args.as_of)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(ev, indent=2))
    n = sum(len(v) for v in ev["results"].values())
    print(json.dumps({"status": "ok", "lane": ev["lane"],
                      "mechanisms": len(ev["results"]),
                      "evidence_items": n, "output": str(args.output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
