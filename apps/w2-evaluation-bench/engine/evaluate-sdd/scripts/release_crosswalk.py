#!/usr/bin/env python3
"""
release_crosswalk.py — Section C.5 of evaluate-sdd v4.6.

Live Salesforce release-currency crosswalk. Detects Salesforce features a
candidate SDD NAMES that are retired, no longer supported, or superseded by a
newer version the SDD did not adopt, and recommends the Salesforce-named
successor without inventing one.

DESIGN (established by live testing):
  help.salesforce.com is a JavaScript single-page app — a direct HTTP fetch
  returns only a "Loading..." shell. Salesforce's authoritative content does,
  however, reach the web-search index with rich, citable snippets. So the live
  path is SEARCH-DRIVEN, not fetch-driven, and it runs as a TWO-CALL CONTRACT:

    1. `extract`  (this script, no network) — scan the SDD, emit the list of
                  named mechanisms and a targeted web_search query for each.
    2. <orchestrator runs web_search for each query>  — the orchestrator owns
                  the network step (web tooling is available at deploy time);
                  it writes the snippets+URLs+dates into an evidence file.
    3. `resolve`  (this script, no network) — apply the source-authority policy
                  to the evidence + the minimal dated register, classify each
                  mechanism, and emit the lane findings JSON.

This keeps the network step where it works and the deterministic, testable
logic in the script. No SPA fetch is ever attempted.

SOURCE-AUTHORITY POLICY (the precision guard):
  A status of retired / end_of_support / superseded may be asserted ONLY when a
  Salesforce-controlled URL (R23 whitelist) is among the evidence. Third-party
  sources are stored as corroboration but can NEVER raise a status on their own
  (this is what prevents the Workflow-Rules error, where blogs say "retired" but
  Salesforce says "end of support"). If neither live Salesforce evidence nor the
  register confirms a status, the mechanism resolves to in_force_unverified —
  surfaced for SA review, never silently dropped, never deducted.

  The live path is PRIMARY; the register is a minimal backstop (see
  data/release-register.json). When live Salesforce evidence contradicts a
  register entry, live wins and the finding is flagged register_stale.

RECOMMENDATION SOURCING (no invention — Tier model):
  Tier 1: successor named in the confirming Salesforce snippet.
  Tier 2: the register entry's `supersession` field (itself Salesforce-sourced).
  Tier 3: contracts.SUCCESSOR_UNSOURCED ("SA to confirm current successor").
  Version successors resolve LIVE (current GA), never hardcoded.

Usage:
    # 1. extract
    python3 release_crosswalk.py extract \\
        --sdd-path <sdd> --lane A --run-id <id> --output-dir <run>
    #    -> writes <run>/release-queries-A.json  (mechanisms + search queries)

    # 2. orchestrator runs web_search per query, writes
    #    <run>/release-evidence-A.json  (see EVIDENCE SCHEMA below)

    # 3. resolve
    python3 release_crosswalk.py resolve \\
        --queries <run>/release-queries-A.json \\
        --evidence <run>/release-evidence-A.json \\
        --lane A --run-id <id> --output-dir <run> [--as-of YYYY-MM-DD]
    #    -> writes <run>/release-awareness-A.json + digest to stdout

    # Offline / no-evidence fallback (register-only) is automatic if the
    # evidence file is absent or empty: resolve still runs, every mechanism is
    # classified register_based or unverified, and the digest flags
    # live_path_used=false.

EVIDENCE SCHEMA (what the orchestrator writes):
    {
      "lane": "A",
      "results": {
        "<mechanism_key>": [
          {"url": "https://help.salesforce.com/...", "title": "...",
           "snippet": "...", "as_of": "2026-06-12"}
        ]
      }
    }

Backwards compatibility: release_awareness_check.py remains as a thin shim that
delegates to this module's single-call path (extract+register-only resolve) so
any caller of the old name keeps working.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

try:
    import contracts
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import contracts

SCRIPT_DIR = Path(__file__).resolve().parent
REGISTER_PATH = SCRIPT_DIR.parent / "data" / "release-register.json"

# =============================================================================
# Domain authority whitelist (R23)
# =============================================================================
SALESFORCE_DOMAINS = {
    "help.salesforce.com",
    "architect.salesforce.com",
    "developer.salesforce.com",
    "releasenotes.docs.salesforce.com",
    "trailhead.salesforce.com",
    "salesforce.com",
    "www.salesforce.com",
    "admin.salesforce.com",
    "ideas.salesforce.com",
    "trust.salesforce.com",
}


def is_salesforce_url(url: str) -> bool:
    """True if URL is on the Salesforce-controlled domain whitelist (R23).
    Delegates to the shared source_authority helper (single source of truth);
    falls back to a local host-parse if that import is unavailable."""
    try:
        from source_authority import is_salesforce_url as _shared
        return _shared(url)
    except Exception:
        pass
    if not url or not isinstance(url, str):
        return False
    from urllib.parse import urlparse
    host = (urlparse(url.strip()).hostname or "").lower()
    return host in SALESFORCE_DOMAINS or any(host.endswith("." + d) for d in SALESFORCE_DOMAINS)


# =============================================================================
# Mechanism extraction register
# =============================================================================
# (key, compiled pattern, display name). Lean and high-signal; the live path
# resolves status, so this list only has to RECOGNISE named mechanisms, not
# carry their lifecycle. A generic API-version catcher handles version numbers.
MECHANISM_PATTERNS: list[tuple[str, re.Pattern, str]] = [
    ("workflow_rules", re.compile(r"\bworkflow\s+rules?\b", re.I), "Workflow Rules"),
    ("process_builder", re.compile(r"\bprocess\s+builder\b", re.I), "Process Builder"),
    ("classic_ui", re.compile(r"\b(salesforce\s+)?classic\s+ui\b", re.I), "Salesforce Classic UI"),
    ("classic_console", re.compile(r"\bclassic\s+console\b", re.I), "Classic Console"),
    ("aura_component", re.compile(r"\baura\s+components?\b", re.I), "Aura Components"),
    ("soap_login", re.compile(r"\bsoap\b[^.]{0,40}?\blogin\s*\(\s*\)", re.I), "SOAP API login()"),
    ("bulk_api_v1", re.compile(r"\bbulk\s+api\s+(1\.0|v1)\b", re.I), "Bulk API 1.0"),
    ("js_buttons", re.compile(r"\bjavascript\s+buttons?\b", re.I), "JavaScript Buttons"),
    ("scontrols", re.compile(r"\bs-?controls?\b", re.I), "S-Controls"),
    ("attachments", re.compile(r"\battachments?\b(?!\s+to)", re.I), "Attachments (legacy)"),
    ("notes_legacy", re.compile(r"\b(legacy|classic)\s+notes\b", re.I), "Legacy Notes"),
    ("connected_apps_legacy", re.compile(r"\b(legacy\s+)?connected\s+apps?\b", re.I), "Connected Apps (legacy)"),
    ("communities_legacy", re.compile(r"\b(salesforce\s+)?communities?\b(?!\s+cloud)", re.I), "Communities (renamed Experience Cloud)"),
    # Generic explicit API version — captures the integer for the version rule.
    ("api_version_explicit", re.compile(r"\bapi\s+(?:version\s+)?v?(\d+)(?:\.0)?\b", re.I), "API Version (explicit)"),
    # Currently-supported anchors (tracked so the audit trail shows them in_force).
    ("flow_builder", re.compile(r"\bflow\s+builder\b|\brecord-triggered\s+flow\b", re.I), "Flow"),
    ("lwc", re.compile(r"\blightning\s+web\s+components?\b|\blwcs?\b", re.I), "Lightning Web Components"),
]

# Mechanisms that are renames, not lifecycle events — informational only.
RENAME_ONLY = {"communities_legacy"}


# =============================================================================
# Register loading
# =============================================================================
class RegisterLoadError(Exception):
    """Raised when the register file exists but is corrupt/unreadable/invalid.

    A MISSING register is a legitimate live-only configuration (returns an empty
    register with status 'absent'). A register that is PRESENT but broken is an
    operator error that must fail loud rather than silently zeroing out the
    entire release-currency surface (the v3.8.0 silent-degradation gap)."""


def load_register_status(path: Path = REGISTER_PATH) -> tuple[dict, str]:
    """Load the register and report HOW it loaded. Returns (register, status).

    status is one of:
      'loaded'   - present, valid JSON, >=1 well-formed entry
      'absent'   - file not present (legitimate live-only mode)
    Raises RegisterLoadError when the file is present but malformed, unreadable,
    structurally wrong, or contains zero/invalid entries -- conditions that
    previously degraded silently to an empty dict.

    Entry validation (fail-closed): every entry must carry a 'status' in the
    taxonomy, a Salesforce-controlled 'salesforce_source' (R23), and 'match_keys'.
    A single corrupt entry fails the whole load rather than being skipped, so a
    half-broken register cannot quietly under-report."""
    if not path.exists():
        return {}, "absent"
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as e:
        raise RegisterLoadError(f"register present at {path} but unreadable: {e}") from e
    try:
        reg = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RegisterLoadError(f"register at {path} is not valid JSON: {e}") from e
    if not isinstance(reg, dict):
        raise RegisterLoadError(f"register at {path} is not a JSON object")
    entries = reg.get("entries")
    if not isinstance(entries, list) or len(entries) == 0:
        raise RegisterLoadError(
            f"register at {path} loaded but has zero entries -- this would zero out "
            f"all register-based findings. If live-only operation is intended, remove "
            f"the file instead of shipping an empty one.")
    valid_statuses = set(contracts.RELEASE_STATUS)
    for i, e in enumerate(entries):
        if not isinstance(e, dict):
            raise RegisterLoadError(f"register entry {i} is not an object")
        mech = e.get("mechanism", f"<entry {i}>")
        if e.get("status") not in valid_statuses:
            raise RegisterLoadError(
                f"register entry '{mech}' has invalid status {e.get('status')!r}; "
                f"must be one of {sorted(valid_statuses)}")
        if not is_salesforce_url(e.get("salesforce_source", "")):
            raise RegisterLoadError(
                f"register entry '{mech}' lacks a Salesforce-controlled source (R23): "
                f"{e.get('salesforce_source')!r}")
        if not e.get("match_keys"):
            raise RegisterLoadError(f"register entry '{mech}' has no match_keys")
    return reg, "loaded"


def load_register(path: Path = REGISTER_PATH, strict: bool = True) -> dict:
    """Load the minimal dated register.

    strict=True (default): a present-but-broken register raises RegisterLoadError
    (loud failure -- the v3.8.1 hardening). A genuinely absent register returns {}
    for legitimate live-only operation.

    strict=False: legacy lenient behaviour (broken register -> {}); retained only
    for callers that must never raise. New code should use strict mode or
    load_register_status directly."""
    try:
        reg, _status = load_register_status(path)
        return reg
    except RegisterLoadError:
        if strict:
            raise
        return {}


def register_entry_for(register: dict, mechanism_key: str, mechanism_name: str) -> Optional[dict]:
    """Find the register entry whose match_keys include this mechanism key."""
    for entry in register.get("entries", []):
        if mechanism_key in (entry.get("match_keys") or []):
            return entry
    return None


# =============================================================================
# Finding model
# =============================================================================
@dataclass
class Finding:
    finding_id: str
    mechanism_name: str
    mechanism_key: str
    status: str                       # one of contracts.RELEASE_STATUS
    rr_severity: Optional[str]        # "Major" for confirmed-not-in-force, else None
    rr_deduction: int                 # binary RR model: 0 (in_force) / -1 (unverified, live ran) / -3 (not-in-force)
    confidence: str                   # one of contracts.RELEASE_CONFIDENCE
    salesforce_source: str            # whitelisted URL (R23) or "" if unverified
    corroboration: list[str]          # non-Salesforce URLs seen (never authoritative)
    as_of: Optional[str]              # status as-of date
    recommended_successor: str        # sourced; never invented (Tier model)
    successor_tier: int               # 1 live / 2 register / 3 unsourced
    consequence: str                  # status-derived design consequence
    register_stale: bool              # live contradicted the register
    evidence_note: str
    source_retrieved_at: str
    review_by: Optional[str] = None   # register entry's review_by date (register-based findings)
    sdd_mentions: list[dict] = field(default_factory=list)


# =============================================================================
# Extraction (Stage 1 — deterministic, no network)
# =============================================================================
def extract_mentions(text: str, max_quote_words: int = 25) -> dict[str, dict]:
    """Scan SDD for named mechanisms.

    Returns {mechanism_key: {"name", "mentions": [{section, quote, char_offset}],
    "api_versions": set}}. For api_version_explicit, the captured integers are
    collected so the version rule can be applied at resolve time."""
    section_re = re.compile(r"(?:^|\n)(?:#+|§|Section\s+)\s*([\d.]+\s+[^\n]+)", re.I)
    sections = list(section_re.finditer(text))

    def find_section(pos: int) -> str:
        last = None
        for m in sections:
            if m.start() <= pos:
                last = m.group(1).strip()[:60]
            else:
                break
        return last or "(top of document)"

    out: dict[str, dict] = {}
    for key, pattern, name in MECHANISM_PATTERNS:
        for match in pattern.finditer(text):
            start = max(0, match.start() - 100)
            end = min(len(text), match.end() + 100)
            window = " ".join(text[start:end].split())
            words = window.split()
            if len(words) > max_quote_words:
                mid = len(words) // 2
                lo = max(0, mid - max_quote_words // 2)
                window = " ".join(words[lo:lo + max_quote_words])
            rec = out.setdefault(key, {"name": name, "mentions": [], "api_versions": set()})
            rec["mentions"].append({
                "section": find_section(match.start()),
                "quote": window,
                "char_offset": match.start(),
            })
            if key == "api_version_explicit" and match.groups():
                try:
                    rec["api_versions"].add(int(match.group(1)))
                except (ValueError, IndexError):
                    pass
    return out


def build_query(mechanism_key: str, mechanism_name: str, api_versions: Optional[set] = None) -> str:
    """A targeted search query for live verification of one mechanism's status."""
    if mechanism_key == "api_version_explicit" and api_versions:
        lo = min(api_versions)
        return f"Salesforce API version {lo}.0 retired deprecated supported current GA release notes"
    base = mechanism_name.split(" (")[0]
    return f"Salesforce {base} retired end of support deprecated superseded replacement site:salesforce.com"


def normalize_feature_key(name: str) -> str:
    """Stable mechanism_key for a model-identified Salesforce feature name.

    Lowercase, collapse non-alphanumerics to single underscores, strip ends.
    Used so a model-supplied feature dedupes against the regex floor and the
    register match_keys where they coincide (e.g. "Workflow Rules" ->
    "workflow_rules"). Deterministic and pure.
    """
    import re as _re
    key = _re.sub(r"[^a-z0-9]+", "_", (name or "").strip().lower()).strip("_")
    return key or "unnamed_feature"


def build_currency_query(mechanism_name: str) -> str:
    """Query for a feature whose CURRENT status we want confirmed, not just its
    deprecation. Seeks both 'is this current/GA' and 'was it superseded/retired',
    so a current feature resolves to in_force (live-confirmed) and a dying one
    surfaces its successor. Salesforce-domain-scoped (verdict still requires a
    Salesforce-controlled source at resolve time, R23)."""
    base = mechanism_name.split(" (")[0]
    return (f"Salesforce {base} current GA release notes status "
            f"retired end of support deprecated superseded replacement site:salesforce.com")


def do_extract(text: str, lane: str, run_id: str,
               model_features: Optional[list] = None) -> dict:
    """Stage 1 output: mechanisms + per-mechanism search queries.

    The regex floor (extract_mentions) ALWAYS runs and guarantees the known set
    is never missed. `model_features` is an optional, additive superset supplied
    by the orchestrator after reading the SDD: a list of Salesforce features the
    model identified by name, each {"name", optional "section"/"quote"/
    "char_offset"}. Model features dedupe against the floor by normalized key, so
    the SDD's actual content — not the hardcoded list — drives what gets verified
    this run. Verdicts are still set only by Salesforce-controlled sources at
    resolve time (R23); the model sets the agenda, not the truth.
    """
    mentions = extract_mentions(text)
    queries = []
    seen_keys = set()
    for key, rec in mentions.items():
        seen_keys.add(key)
        queries.append({
            "mechanism_key": key,
            "mechanism_name": rec["name"],
            "api_versions": sorted(rec["api_versions"]) if rec["api_versions"] else [],
            "query": build_query(key, rec["name"], rec["api_versions"]),
            "mentions": rec["mentions"][:5],
            "source": "regex_floor",
        })

    floor_count = len(queries)
    model_count = 0
    for feat in (model_features or []):
        name = (feat.get("name") if isinstance(feat, dict) else str(feat)) or ""
        name = name.strip()
        if not name:
            continue
        key = normalize_feature_key(name)
        if key in seen_keys:
            continue  # already covered by the regex floor (or an earlier model feature)
        seen_keys.add(key)
        mentions_list = []
        if isinstance(feat, dict) and (feat.get("section") or feat.get("quote")):
            mentions_list = [{
                "section": (feat.get("section") or "(model-identified)")[:60],
                "quote": " ".join((feat.get("quote") or "").split())[:300],
                "char_offset": feat.get("char_offset"),
            }]
        queries.append({
            "mechanism_key": key,
            "mechanism_name": name,
            "api_versions": [],
            "query": build_currency_query(name),
            "mentions": mentions_list,
            "source": "model_identified",
        })
        model_count += 1

    return {
        "stage": "extract",
        "run_id": run_id,
        "lane": lane.upper(),
        "mechanisms_found": len(queries),
        "mechanisms_from_regex_floor": floor_count,
        "mechanisms_from_model": model_count,
        "queries": queries,
    }


# =============================================================================
# Resolution (Stage 3 — deterministic, no network)
# =============================================================================
# Keyword signals used ONLY against Salesforce-controlled snippets to choose a
# status. Order matters: end_of_support must beat retired when the snippet says
# "no longer supported ... continue to run" (the precision case).
def classify_from_salesforce_snippet(snippet: str, mechanism_aliases=None) -> Optional[str]:
    s = snippet.lower()
    aliases = [a.lower().strip() for a in (mechanism_aliases or []) if a and str(a).strip()]

    # SUBJECT-AWARE POSITIVE GUARD (v4.2.4): a doc that RECOMMENDS the queried
    # mechanism is endorsing it as the successor — it is NOT evidence that this
    # mechanism is superseded. Rich first-party docs (e.g. the Salesforce Docs MCP)
    # frequently say "we recommend using <mechanism> whenever possible" about a
    # CURRENT feature; the bare "recommend using" trigger below would otherwise
    # misclassify that current feature as superseded (false -3). When the
    # recommendation names THIS mechanism, treat it as a positive currency signal.
    recommends_this = False
    for a in aliases:
        for pat in (f"recommend using {a}", f"recommend that you use {a}",
                    f"recommend {a}", f"using {a} whenever possible",
                    f"use {a} whenever possible", f"{a} whenever possible",
                    f"{a} is the recommended", f"{a} is recommended",
                    f"{a} is the current", f"{a} is the modern",
                    # v4.6: real developer.salesforce.com phrasing observed in
                    # live testing ("Use Lightning Web Components (LWC) where
                    # possible for new development", "Always choose Lightning
                    # Web Components unless...").
                    f"use {a} where possible", f"use {a} (lwc) where possible",
                    f"{a} where possible", f"always choose {a}",
                    f"choose {a} unless"):
            if pat in s:
                recommends_this = True
                break
        if recommends_this:
            break

    # End-of-support signature: explicitly still runs, only support stops.
    if ((("no longer support" in s or "end of support" in s or "ends support" in s
          or "no longer provides" in s or "support and updates" in s and "have ended" in s
          or "support has ended" in s or "support have ended" in s))
            and ("continue to run" in s or "continue to function" in s
                 or "keep running" in s or "still run" in s or "not a retirement" in s)):
        return "end_of_support"
    # Hard retirement: calls fail / unavailable / retired & unavailable.
    if ((("retired" in s and ("unavailable" in s or "will fail" in s or "calls fail" in s
                              or "410" in s or "500" in s or "no longer be available" in s
                              or "won't be available" in s or "disrupted" in s))
            or "has been retired" in s or "now fail" in s)):
        return "retired"
    # Explicit end-of-support phrasing wins over migrate/successor language: a
    # snippet that says "end of support" AND "migrate to Flow" is an end_of_support
    # fact (the feature still runs), not a bare supersession. This precedence fix
    # keeps the REPORTED status precise even though the deduction is identical.
    if ("end of support" in s or "ends support" in s or "no longer supported" in s
            or "no longer support" in s
            or ("support" in s and ("have ended" in s or "has ended" in s))):
        return "end_of_support"
    # Superseded / recommended successor for new work. Match phrases that point
    # AWAY from the named feature toward a different successor — NOT the bare word
    # "recommended", which also appears in positive "current recommended platform"
    # statements about the feature itself. SKIP entirely when the doc is
    # recommending THIS mechanism (handled by recommends_this -> in_force below).
    if not recommends_this and (
            "we recommend" in s or "recommends " in s or "maintenance mode" in s
            or "use flow" in s or "migrate to" in s or "is the modern" in s
            or "instead of" in s or "successor" in s or "superseded" in s
            or "recommended for new" in s or "recommend using" in s
            # v4.6: real Salesforce doc phrasing that points AWAY from the
            # queried mechanism toward a different standard ("Use Lightning Web
            # Components (LWC) where possible for new development", "Always
            # choose Lightning Web Components unless...", "see Migrate Aura
            # Components"). Only reached when recommends_this is False, i.e.
            # the recommended thing is NOT this mechanism.
            or "where possible for new development" in s
            or "always choose" in s
            or ("where possible" in s and ("use " in s or "choose " in s))
            or "legacy components" in s):
        return "superseded"
    # Scheduled but not yet effective retirement -> treat as superseded (plan migration).
    if not recommends_this and ("will be retired" in s or "scheduled to be retired" in s
                                or "retirement" in s):
        return "superseded"
    if "no longer supported" in s:
        return "end_of_support"
    # Positive currency signal (ordered LAST so any deprecation phrase above wins):
    # a Salesforce source affirmatively stating the feature is current / GA /
    # recommended lets a named feature resolve to in_force (live_confirmed) rather
    # than degrading to in_force_unverified. recommends_this (above) is included so
    # a doc endorsing THIS mechanism grounds it as current.
    if (recommends_this
        or (("generally available" in s or "is ga" in s or "now ga" in s
             or "current release" in s or "is the current" in s or "is current" in s
             or "fully supported" in s or "is supported" in s
             or "recommended approach" in s or "current recommended" in s)
            and "no longer" not in s and "retired" not in s and "end of support" not in s)):
        return "in_force"
    return None


SUCCESSOR_RE = re.compile(
    r"(?:migrate to|move to|use|replaced by|recommend(?:s|ed)?(?: that you use| using)?|"
    r"switch to|upgrade to)\s+([A-Z][A-Za-z0-9 .()/+-]{2,60})")


def extract_successor_from_snippet(snippet: str) -> Optional[str]:
    """Tier-1 successor: pull a Salesforce-named replacement from the snippet."""
    m = SUCCESSOR_RE.search(snippet)
    if m:
        cand = m.group(1).strip().rstrip(".")
        # Trim trailing clause noise
        cand = re.split(r"\b(?:for|to|in|when|which|that|and)\b", cand)[0].strip()
        if 2 <= len(cand) <= 60:
            return cand
    return None


def resolve_mechanism(q: dict, evidence_results: list[dict], register: dict,
                      as_of_default: str) -> dict:
    """Apply the source-authority policy to one mechanism's evidence + register.

    Returns a dict of resolved fields (status, confidence, source, successor,
    tier, etc.). NEVER asserts retired/end_of_support/superseded without a
    Salesforce-controlled source."""
    key = q["mechanism_key"]
    name = q["mechanism_name"]
    reg = register_entry_for(register, key, name)

    # Partition evidence by authority.
    sf_evidence = [e for e in evidence_results if is_salesforce_url(e.get("url", ""))]
    third_party = [e.get("url", "") for e in evidence_results
                   if e.get("url") and not is_salesforce_url(e.get("url", ""))]

    # Renames are informational, never lifecycle deductions.
    if key in RENAME_ONLY:
        return _result("in_force", "live_confirmed" if sf_evidence else "register_based",
                       sf_evidence[0]["url"] if sf_evidence else (reg or {}).get("salesforce_source", ""),
                       third_party, as_of_default,
                       "Use current 'Experience Cloud' nomenclature; this is a rename, not a lifecycle event.",
                       1 if sf_evidence else 2,
                       "Informational: renamed feature; no lifecycle action required.",
                       False, "Rename only — no retirement or supersession.")

    # --- LIVE PATH (primary) ---
    # MECHANISM-RELEVANCE GATE (v4.3): a Salesforce-controlled snippet may only set
    # a lifecycle status for THIS mechanism if the snippet actually mentions the
    # mechanism (its name or an approved synonym). Otherwise a snippet about a
    # different feature (e.g. Flow) could wrongly classify the target (e.g. Workflow
    # Rules) just because it carries a positive/negative currency signal. Off-topic
    # Salesforce evidence is demoted to unverified, never used to assert status.
    def _mechanism_mentioned(snippet: str) -> bool:
        s = (snippet or "").lower()
        syns = [name.lower(), key.replace("_", " ").lower()]
        syns += [a.lower() for a in (reg or {}).get("synonyms", [])]
        syns.append(name.split(" (")[0].lower())
        # Distinctive head token: a snippet often uses the short form ("Aura" for
        # "Aura Components"). Accept the first significant word of the name if it is
        # distinctive (>=4 chars, not a generic word).
        _GENERIC = {"salesforce", "classic", "legacy", "standard", "custom", "data", "api"}
        for tok in name.split():
            tl = tok.lower().strip("()")
            if len(tl) >= 4 and tl not in _GENERIC:
                syns.append(tl)
                break
        if any(syn and syn in s for syn in syns):
            return True
        # Anaphora allowance: a snippet retrieved for THIS mechanism may refer to it
        # as "this feature/component/api/tool" rather than by name. Accept that ONLY
        # when no OTHER known mechanism is named in the snippet (so a Flow snippet in
        # the Workflow-Rules case is still rejected, because it names "Flow").
        if re.search(r"\bthis (feature|component|tool|api|capability|functionality)\b", s):
            other_named = [nm for (k2, _p, nm) in MECHANISM_PATTERNS
                           if k2 != key and nm.split(" (")[0].lower() in s]
            if not other_named:
                return True
        return False

    live_status = None
    live_source = ""
    live_successor = None
    live_as_of = as_of_default
    relevant_sf_evidence = [e for e in sf_evidence if _mechanism_mentioned(
        (e.get("title", "") + " " + e.get("snippet", "")))]
    off_topic_sf = len(sf_evidence) - len(relevant_sf_evidence)
    # Aliases of THIS mechanism, so the classifier can tell "we recommend using
    # <this mechanism>" (positive, in_force) from "migrate to <other>" (superseded).
    _mech_aliases = [name, key, key.replace("_", " ")]
    if "lwc" in key or "lightning web" in name.lower():
        _mech_aliases += ["lightning web components", "lwc", "lightning web component"]
    for e in relevant_sf_evidence:
        # v4.6 (live-path efficacy): classify on TITLE + snippet. Live testing
        # showed help.salesforce.com results reach the search index as an SPA
        # "Loading..." shell whose classifiable fact lives in the TITLE (e.g.
        # "Workflow Rules & Process Builder End of Support"); classifying the
        # snippet alone discarded that signal and forced a register fallback.
        classify_text = " ".join(
            t for t in (e.get("title", ""), e.get("snippet", "")) if t)
        st = classify_from_salesforce_snippet(classify_text, _mech_aliases)
        if st:
            live_status = _max_severity_status(live_status, st)
            if not live_source:
                live_source = e.get("url", "")
                live_as_of = e.get("as_of") or as_of_default
            # v4.6: never mine a "successor" out of a positive-currency source —
            # a doc recommending THIS mechanism otherwise yields a finding whose
            # recommended_successor is the mechanism itself (self-referential).
            if not live_successor and st != "in_force":
                live_successor = extract_successor_from_snippet(classify_text)

    # Apply the API version rule when relevant (live or register).
    version_note = ""
    if key == "api_version_explicit":
        versions = sorted(set(q.get("api_versions") or []))
        rule = (reg or {}).get("version_rule") or {}
        floor = rule.get("retired_at_or_below", 30)
        below = [v for v in versions if v <= floor]
        above = [v for v in versions if v > floor]
        if below:
            # A retired API version is a hard, Salesforce-confirmable fact.
            # v4.6 fix (confidence honesty): only LIVE Salesforce evidence may
            # take the live_confirmed branch. A register-only confirmation falls
            # through to the register special-case below and is labelled
            # register_based — previously it borrowed the register URL here and
            # exited as live_confirmed even in a fully offline run, overstating
            # verification coverage.
            if sf_evidence:
                live_status = "retired"
                version_note = (f"SDD names API version(s) {', '.join(str(v)+'.0' for v in below)} "
                                f"at or below the retired floor {floor}.0.")
                if above:
                    version_note += (f" (Also names {', '.join(str(v)+'.0' for v in above)}, "
                                     "which are above the floor.)")
                if not live_source:
                    live_source = sf_evidence[0].get("url", "")
            elif reg:
                version_note = (f"SDD names API version(s) {', '.join(str(v)+'.0' for v in below)} "
                                f"at or below the retired floor {floor}.0.")
                if above:
                    version_note += (f" (Also names {', '.join(str(v)+'.0' for v in above)}, "
                                     "which are above the floor.)")
        elif above:
            # Only above-floor versions named — not a retirement; informational.
            version_note = (f"SDD names API version(s) {', '.join(str(v)+'.0' for v in above)}; "
                            "above the retired floor. Confirm it is a currently-supported version.")

    if live_status and (live_source or live_status == "retired"):
        # Successor: Tier 1 (live snippet) -> Tier 2 (register) -> Tier 3.
        # v4.6: an in_force finding is current — there is nothing to succeed it,
        # so it carries no recommended_successor (previously a positive
        # "we recommend using X" snippet made X its own successor).
        if live_status == "in_force":
            successor, tier = "", 3
        else:
            successor, tier = _pick_successor(live_successor, reg)
        stale = bool(reg and reg.get("status") and reg["status"] != live_status)
        note = (version_note + " " if version_note else "") + \
               "Status asserted from Salesforce-controlled source (live)."
        if stale:
            note += f" NOTE: register said '{reg['status']}'; live evidence overrode it (register_stale)."
        return _result(live_status, "live_confirmed", live_source, third_party,
                       live_as_of, successor, tier,
                       _consequence(live_status, reg), stale, note.strip())

    # --- REGISTER PATH (backstop) ---
    # Special-case the API-version mechanism: the register entry's "retired"
    # status applies ONLY when a below-floor version was named. An above-floor
    # version must not inherit "retired" from the register.
    if key == "api_version_explicit":
        versions = sorted(set(q.get("api_versions") or []))
        rule = (reg or {}).get("version_rule") or {}
        floor = rule.get("retired_at_or_below", 30)
        if reg and any(v <= floor for v in versions):
            successor, tier = _pick_successor(None, reg)
            note = (version_note + " " if version_note else "") + \
                   "Retired API version per dated register (no live confirmation this run)."
            return _result("retired", "register_based", reg.get("salesforce_source", ""),
                           third_party, reg.get("as_of", as_of_default), successor, tier,
                           reg.get("consequence") or _consequence("retired", reg),
                           False, note.strip())
        # Above-floor or unknown version: not a retirement. Surface for confirmation.
        return _result("in_force_unverified", "unverified", "", third_party, as_of_default,
                       contracts.SUCCESSOR_UNSOURCED, 3,
                       "Named API version is above the retired floor; confirm it is currently supported.",
                       False, version_note or "API version named; no retirement applies.")

    if reg and reg.get("status") in contracts.RELEASE_STATUS and reg["status"] != "in_force_unverified":
        successor, tier = _pick_successor(None, reg)
        note = (version_note + " " if version_note else "") + \
               "Status from dated register (no live Salesforce confirmation captured this run)."
        return _result(reg["status"], "register_based", reg.get("salesforce_source", ""),
                       third_party, reg.get("as_of", as_of_default), successor, tier,
                       reg.get("consequence") or _consequence(reg["status"], reg),
                       False, note.strip())

    # --- UNVERIFIED (conservative default) ---
    # Third-party sources, even many, cannot assert a status.
    tp_note = ""
    if third_party:
        tp_note = (f" {len(third_party)} non-Salesforce source(s) were seen but cannot assert a "
                   "status (source-authority policy).")
    if off_topic_sf:
        tp_note += (f" {off_topic_sf} Salesforce source(s) were seen but did not mention "
                    f"'{name}' (or a synonym), so they cannot classify it (mechanism-relevance guard).")
    return _result("in_force_unverified", "unverified", "", third_party, as_of_default,
                   contracts.SUCCESSOR_UNSOURCED, 3,
                   "Could not confirm lifecycle status against a Salesforce-controlled source. "
                   "Surfaced for manual SA verification; no deduction applied.",
                   False,
                   (version_note + " " if version_note else "")
                   + "No Salesforce-controlled source confirmed a non-current status." + tp_note)


def _max_severity_status(a: Optional[str], b: str) -> str:
    """Pick the more severe of two statuses (retired > end_of_support/superseded)."""
    order = {"retired": 3, "end_of_support": 2, "superseded": 2, "in_force": 1,
             "in_force_unverified": 0, None: -1}
    return b if order.get(b, -1) >= order.get(a, -1) else a


def _pick_successor(live_successor: Optional[str], reg: Optional[dict]) -> tuple[str, int]:
    """Tier 1 live snippet -> Tier 2 register -> Tier 3 unsourced. No invention."""
    if live_successor:
        return live_successor, 1
    if reg and reg.get("supersession"):
        return reg["supersession"], 2
    return contracts.SUCCESSOR_UNSOURCED, 3


def _consequence(status: str, reg: Optional[dict]) -> str:
    if reg and reg.get("consequence"):
        return reg["consequence"]
    return {
        "retired": "Blocking: the named mechanism is retired; the design will not deploy or will fail at run time.",
        "end_of_support": "Technical debt: still runs but Salesforce no longer provides support or bug fixes.",
        "superseded": "Outdated choice: a newer Salesforce-recommended standard exists; the SDD adopted the older one.",
        "in_force": "Current and appropriate.",
        "in_force_unverified": "Status unconfirmed; SA to verify.",
    }.get(status, "")


def _result(status, confidence, source, corroboration, as_of, successor, tier,
            consequence, stale, note) -> dict:
    return {
        "status": status,
        "confidence": confidence,
        "salesforce_source": source,
        "corroboration": corroboration,
        "as_of": as_of,
        "recommended_successor": successor,
        "successor_tier": tier,
        "consequence": consequence,
        "register_stale": stale,
        "evidence_note": note,
    }


def do_resolve(queries_doc: dict, evidence_doc: dict, register: dict, lane: str,
               run_id: str, as_of_default: str) -> tuple[list[Finding], bool]:
    """Stage 3: classify every extracted mechanism. Returns (findings, live_path_used)."""
    raw_results = (evidence_doc or {}).get("results", {})
    # Robustness: a structurally-malformed evidence file (valid JSON but
    # `results` is not a dict keyed by mechanism_key) must degrade gracefully
    # to the register/unverified path, never crash the batch. Coerce anything
    # that is not a dict to an empty map and warn on stderr so the operator
    # sees it; the normal degradation banner ("live path not used") then fires.
    if isinstance(raw_results, dict):
        results_map = raw_results or {}
    else:
        print("WARNING: release-evidence 'results' is not an object keyed by "
              "mechanism_key; ignoring malformed evidence and falling back to "
              "register/unverified classification.", file=sys.stderr)
        results_map = {}
    live_path_used = bool(results_map)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    findings: list[Finding] = []
    seq = 1
    for q in queries_doc.get("queries", []):
        mech_key = q.get("mechanism_key")
        ev = results_map.get(mech_key, []) if mech_key is not None else []
        # An evidence value for a mechanism must be a list; tolerate a single
        # dict by wrapping it, and ignore anything else.
        if isinstance(ev, dict):
            ev = [ev]
        elif not isinstance(ev, list):
            ev = []
        r = resolve_mechanism(q, ev, register, as_of_default)
        sev = contracts.RELEASE_STATUS_SEVERITY.get(r["status"])
        ded = contracts.RELEASE_SEVERITY_DEDUCTION.get(r["status"], 0)
        # Offline guard (confidence-based binary model): in_force_unverified
        # deducts ONLY when the live path actually ran this lane. If there was no
        # web access (live_path_used = False), every mechanism is unverified for
        # a TOOLING reason, not a design flaw, so it must not be penalised.
        if r["status"] == "in_force_unverified" and not live_path_used:
            ded = 0
        # Carry the register entry's review_by date so the assembler can flag a
        # register-based finding whose backing fact is past its review date.
        reg_entry = register_entry_for(register, q["mechanism_key"], q["mechanism_name"])
        review_by = (reg_entry or {}).get("review_by") if r["confidence"] == "register_based" else None
        findings.append(Finding(
            finding_id=f"RR-{lane.upper()}-{seq:03d}",
            mechanism_name=q["mechanism_name"],
            mechanism_key=q["mechanism_key"],
            status=r["status"],
            rr_severity=sev,
            rr_deduction=ded,
            confidence=r["confidence"],
            salesforce_source=r["salesforce_source"],
            corroboration=r["corroboration"],
            as_of=r["as_of"],
            recommended_successor=r["recommended_successor"],
            successor_tier=r["successor_tier"],
            consequence=r["consequence"],
            register_stale=r["register_stale"],
            evidence_note=r["evidence_note"],
            source_retrieved_at=now,
            review_by=review_by,
            sdd_mentions=q.get("mentions", [])[:5],
        ))
        seq += 1
    return findings, live_path_used


# =============================================================================
# SDD reading
# =============================================================================
def read_sdd_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        return path.read_text(encoding="utf-8", errors="replace")
    if suffix == ".docx":
        try:
            import docx2txt  # type: ignore
            return docx2txt.process(str(path))
        except ImportError:
            pass
        import zipfile
        with zipfile.ZipFile(path) as z:
            with z.open("word/document.xml") as f:
                xml = f.read().decode("utf-8", errors="replace")
        return re.sub(r"<[^>]+>", " ", xml)
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader  # type: ignore
            reader = PdfReader(str(path))
            return "\n".join(p.extract_text() or "" for p in reader.pages)
        except ImportError:
            pass
    raise ValueError(f"Unsupported SDD format: {suffix}. Use .md, .txt, .docx, or .pdf")


# =============================================================================
# Summary + output assembly (shared by resolve and the compat shim)
# =============================================================================
def assemble_output(findings: list[Finding], lane: str, run_id: str, sdd_path: str,
                    live_path_used: bool, register_status: str = "loaded",
                    register_as_of: str | None = None) -> dict:
    raw_total = sum(f.rr_deduction for f in findings)
    capped_total = max(raw_total, contracts.RR_CUMULATIVE_CAP)
    by_status: dict[str, int] = {}
    by_confidence: dict[str, int] = {}
    for f in findings:
        by_status[f.status] = by_status.get(f.status, 0) + 1
        by_confidence[f.confidence] = by_confidence.get(f.confidence, 0) + 1
    successors = [{"mechanism": f.mechanism_name, "successor": f.recommended_successor,
                   "tier": f.successor_tier, "status": f.status}
                  for f in findings if f.status not in ("in_force",)]
    stale = [f.finding_id for f in findings if f.register_stale]

    # Verification coverage (v3.8.1): make explicit how much of the audit was
    # actually verified, so a reviewer never mistakes 'no findings' for 'nothing
    # to find'. Counts mechanisms (excluding current/in_force) by how they were
    # resolved, and emits a plain-language degradation banner when verification
    # was weak.
    noncurrent = [f for f in findings if f.status not in ("in_force",)]
    live_n = sum(1 for f in noncurrent if f.confidence == "live_confirmed")
    reg_n = sum(1 for f in noncurrent if f.confidence == "register_based")
    unv_n = sum(1 for f in findings if f.confidence == "unverified")
    detected = len(findings)
    verified = live_n + reg_n
    banners = []
    if register_status == "absent" and not live_path_used:
        banners.append("DEGRADED: no register present AND no live evidence supplied -- "
                       "every mechanism is unverified. Findings are detection-only; "
                       "no lifecycle status was confirmed.")
    elif not live_path_used:
        banners.append("PARTIAL: live web-search path not used this run; statuses are "
                       "register-based or unverified. Enable web_search at deploy time "
                       "for live confirmation.")
    if detected and unv_n == detected:
        banners.append("ALL-UNVERIFIED: no mechanism was confirmed against a Salesforce "
                       "source or the register. Treat as a coverage gap, not a clean bill.")
    # v4.6 (F21): "live ran" is not "live confirmed". When the live path was
    # used but confirmed nothing (or almost nothing) against a Salesforce
    # source — the empirically common outcome under the generic web_search
    # fallback, where help.salesforce.com surfaces as an SPA shell — say so
    # plainly, so a reader never mistakes register-carried coverage for live
    # verification. Surfaced only; statuses and deductions are unchanged.
    if live_path_used and detected:
        live_all = sum(1 for f in findings if f.confidence == "live_confirmed")
        if live_all == 0 or (live_all / detected) < 0.25:
            banners.append(
                f"WEAK-LIVE: the live evidence path ran but confirmed only "
                f"{live_all}/{detected} mechanism(s) against a Salesforce-controlled "
                "source; statuses are predominantly register-based or unverified. "
                "Prefer the Salesforce Docs MCP as the evidence source for real "
                "live confirmation; unverified deductions in this state reflect "
                "channel limits as much as SDD quality.")

    # Register review-date staleness (Phase-2): a register-based finding whose
    # backing entry is past its review_by date is asserting a lifecycle fact
    # that nobody has re-confirmed against Salesforce within the review window.
    # This is distinct from register_stale (live evidence contradicted the
    # register THIS run); here there was no live evidence and the register fact
    # itself may have aged out. Surfaced as a banner only — never changes the
    # status or deduction (conservative: we still trust the dated fact, but flag
    # it for re-confirmation).
    if register_as_of:
        overdue = []
        for f in findings:
            rb = getattr(f, "review_by", None)
            if f.confidence == "register_based" and rb and str(rb) < str(register_as_of):
                overdue.append(f"{f.mechanism_name} (review_by {rb})")
        if overdue:
            banners.append(
                "REGISTER-STALE: register-based status for " + "; ".join(overdue) +
                f" is past its review_by date (run as-of {register_as_of}). "
                "Re-confirm against the Salesforce source before relying on the deduction.")

    coverage = {
        "mechanisms_detected": detected,
        "noncurrent_flagged": len(noncurrent),
        "verified_live": live_n,
        "verified_register": reg_n,
        "unverified": unv_n,
        "verified_fraction": round(verified / detected, 3) if detected else None,
        "register_status": register_status,
        "live_path_used": live_path_used,
        "degradation_banners": banners,
    }
    return {
        "section": "C.5",
        "run_id": run_id,
        "lane": lane.upper(),
        "sdd_path": sdd_path,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "live_path_used": live_path_used,
        "register_status": register_status,
        "findings": [asdict(f) for f in findings],
        "summary": {
            "findings_total": len(findings),
            "by_status": by_status,
            "by_confidence": by_confidence,
            "rr_deductions_raw_total": raw_total,
            "rr_deductions_capped_total": capped_total,
            "register_stale_finding_ids": stale,
            "recommended_successors": successors,
            "verification_coverage": coverage,
        },
    }


# =============================================================================
# CLI
# =============================================================================
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Section C.5: live release crosswalk")
    sub = parser.add_subparsers(dest="command", required=True)

    pe = sub.add_parser("extract", help="Stage 1: list mechanisms + search queries")
    pe.add_argument("--sdd-path", required=True)
    pe.add_argument("--lane", required=True, choices=["A", "B", "a", "b"])
    pe.add_argument("--run-id", required=True)
    pe.add_argument("--output-dir", required=True)
    pe.add_argument("--features", required=False,
                    help="Optional JSON file of model-identified Salesforce features "
                         "(list of {name, section?, quote?, char_offset?}) or {\"features\": [...]}. "
                         "Additive to the regex floor; lets the SDD's content drive what is verified.")

    pr = sub.add_parser("resolve", help="Stage 3: classify mechanisms from evidence + register")
    pr.add_argument("--queries", required=True)
    pr.add_argument("--evidence", required=False, help="Orchestrator evidence file (optional; register-only if absent)")
    pr.add_argument("--lane", required=True, choices=["A", "B", "a", "b"])
    pr.add_argument("--run-id", required=True)
    pr.add_argument("--output-dir", required=True)
    pr.add_argument("--as-of", default=datetime.now(timezone.utc).date().isoformat())

    args = parser.parse_args(argv)
    lane = args.lane.upper()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.command == "extract":
        sdd_path = Path(args.sdd_path)
        if not sdd_path.exists():
            print(f"ERROR: SDD not at {sdd_path}", file=sys.stderr)
            return 2
        try:
            text = read_sdd_text(sdd_path)
        except (ValueError, OSError) as e:
            print(f"ERROR: cannot read SDD: {e}", file=sys.stderr)
            return 2
        # Optional model-identified feature list (Option 1: SDD content drives
        # what is verified). Malformed/missing -> falls back to regex floor only.
        model_features = None
        if getattr(args, "features", None) and Path(args.features).exists():
            try:
                fdoc = json.loads(Path(args.features).read_text(encoding="utf-8"))
                if isinstance(fdoc, dict):
                    model_features = fdoc.get("features", [])
                elif isinstance(fdoc, list):
                    model_features = fdoc
                if not isinstance(model_features, list):
                    print("WARNING: --features file is not a list or {features:[...]}; "
                          "ignoring and using the regex floor only.", file=sys.stderr)
                    model_features = None
            except (json.JSONDecodeError, OSError) as e:
                print(f"WARNING: cannot read --features file ({e}); "
                      "using the regex floor only.", file=sys.stderr)
                model_features = None
        doc = do_extract(text, lane, args.run_id, model_features=model_features)
        out_path = out_dir / f"release-queries-{lane}.json"
        out_path.write_text(json.dumps(doc, indent=2, ensure_ascii=False))
        print(json.dumps({"status": "ok", "stage": "extract", "lane": lane,
                          "mechanisms_found": doc["mechanisms_found"],
                          "mechanisms_from_regex_floor": doc.get("mechanisms_from_regex_floor"),
                          "mechanisms_from_model": doc.get("mechanisms_from_model"),
                          "queries_path": str(out_path),
                          "note": "Run web_search for each query, write release-evidence-"
                                  f"{lane}.json, then call resolve."}, indent=2))
        return 0

    # resolve
    queries_doc = json.loads(Path(args.queries).read_text(encoding="utf-8"))
    evidence_doc = {}
    if args.evidence and Path(args.evidence).exists():
        try:
            evidence_doc = json.loads(Path(args.evidence).read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            evidence_doc = {}
    # v3.8.1: load loud. A present-but-broken register is an operator error and
    # must not degrade silently to zero findings.
    try:
        register, register_status = load_register_status()
    except RegisterLoadError as e:
        print(json.dumps({"status": "error", "section": "C.5", "stage": "resolve",
                          "reason_code": "REGISTER_LOAD_FAILED", "detail": str(e),
                          "remedy": "Fix or remove the register file. Removing it entirely "
                                    "enables legitimate live-only mode; a present file must "
                                    "be valid."}, indent=2), file=sys.stderr)
        return 4
    findings, live_used = do_resolve(queries_doc, evidence_doc, register, lane,
                                     args.run_id, args.as_of)
    output = assemble_output(findings, lane, args.run_id,
                             queries_doc.get("sdd_path", ""), live_used,
                             register_status=register_status,
                             register_as_of=args.as_of)
    out_path = out_dir / f"release-awareness-{lane}.json"
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    cov = output["summary"]["verification_coverage"]
    digest = {
        "status": "ok", "section": "C.5", "stage": "resolve", "run_id": args.run_id,
        "lane": lane, "live_path_used": live_used, "register_status": register_status,
        "findings_count": len(findings),
        "by_status": output["summary"]["by_status"],
        "by_confidence": output["summary"]["by_confidence"],
        "verification_coverage": {"verified_fraction": cov["verified_fraction"],
                                   "verified_live": cov["verified_live"],
                                   "verified_register": cov["verified_register"],
                                   "unverified": cov["unverified"]},
        "degradation_banners": cov["degradation_banners"],
        "rr_deductions_capped_total": output["summary"]["rr_deductions_capped_total"],
        "register_stale_finding_ids": output["summary"]["register_stale_finding_ids"],
        "findings_path": str(out_path),
    }
    print(json.dumps(digest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
