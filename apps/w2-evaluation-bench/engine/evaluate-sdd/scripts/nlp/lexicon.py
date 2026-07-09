"""Salesforce mechanism lexicon + locator.

Curated from the vocabulary the ZMS calibration and the release crosswalk
already score against (module/class/pattern-level mechanisms — the same bar
as the components packet's has_specific_mechanism). Multi-word entries match
as phrases; matching is case-insensitive and deterministic.
"""
from __future__ import annotations
import re

SALESFORCE_LEXICON: dict[str, tuple[str, ...]] = {
    # automation
    "Flow": ("record-triggered flow", "screen flow", "subflow", "flow orchestration",
             "scheduled flow", "platform event-triggered flow", "autolaunched flow"),
    "Apex": ("apex trigger", "apex class", "batch apex", "queueable apex",
             "invocable apex", "apex rest", "future method", "trigger handler"),
    "Approval": ("approval process", "approval submission"),
    # data
    "Data model": ("custom object", "standard object", "junction object",
                   "master-detail", "lookup relationship", "record type",
                   "big object", "external object", "field history"),
    "Data quality": ("validation rule", "duplicate rule", "matching rule"),
    # security
    "Security": ("permission set", "permission set group", "profile",
                 "sharing rule", "org-wide default", "owd", "restriction rule",
                 "field-level security", "shield platform encryption",
                 "event monitoring", "session security"),
    # integration
    "Integration": ("named credential", "external credential", "platform event",
                    "change data capture", "outbound message", "rest api",
                    "soap api", "bulk api", "streaming api", "external services",
                    "mulesoft", "middleware", "callout", "integration user",
                    "composite api", "salesforce connect"),
    # analytics / UI
    "Analytics": ("report type", "dashboard", "crm analytics", "data cloud",
                  "reporting snapshot"),
    "UI": ("lightning web component", "lwc", "aura component", "lightning page",
           "dynamic form", "omniscript", "experience cloud", "digital experience"),
    # AI / current-gen
    "AI": ("einstein", "agentforce", "prompt builder", "copilot", "model builder"),
    # delivery
    "Delivery": ("sandbox", "scratch org", "unlocked package", "change set",
                 "devops center", "ci/cd", "sfdx", "metadata api", "test class"),
}

_PHRASES = sorted({p for ps in SALESFORCE_LEXICON.values() for p in ps},
                  key=len, reverse=True)


def _phrase_rx(p: str) -> str:
    # flexible whitespace/hyphen between words; plural-tolerant last word
    # ("record types", "sandboxes") so real designs aren't missed on number.
    return r"\b" + re.escape(p).replace(r"\ ", r"[\s\-]") + r"(?:e?s)?\b"


_RX = re.compile("|".join(_phrase_rx(p) for p in _PHRASES), re.I)
_FAMILY = {p: fam for fam, ps in SALESFORCE_LEXICON.items() for p in ps}

# Fold a raw match ("Record types", "master detail") back to its canonical
# lexicon phrase so counts merge and downstream names are stable.
_CANON = {re.sub(r"[\s\-]+", " ", p): p for p in _PHRASES}

# Single common-English words that only name a Salesforce mechanism in a
# Salesforce context ("children play in the sandbox"). A match on one of
# these counts only when the surrounding window also carries an unambiguous
# mechanism or a platform cue — deterministic, no part-of-speech guessing.
_AMBIGUOUS = {"profile", "dashboard", "sandbox", "middleware", "callout"}
_UNAMBIG_RX = re.compile(
    "|".join(_phrase_rx(p) for p in _PHRASES if p not in _AMBIGUOUS), re.I)
_CUE_RX = re.compile(
    r"\b(salesforce|lightning|apex|orgs?|crm|sobjects?|metadata|sfdx|uat|"
    r"records?|permission|deployments?|deploy|refresh(?:es)?|integrations?|"
    r"api)\b", re.I)
_WINDOW = 120


def _canonical(matched: str) -> str:
    t = re.sub(r"[\s\-]+", " ", matched.lower()).strip()
    for cand in (t, t[:-1], t[:-2]):  # exact, -s, -es
        if cand in _CANON:
            return _CANON[cand]
    return t


def _in_context(blob: str, start: int, end: int) -> bool:
    win = blob[max(0, start - _WINDOW):start] + " " + blob[end:end + _WINDOW]
    return bool(_UNAMBIG_RX.search(win) or _CUE_RX.search(win))


def find_mechanisms(doc: dict) -> list[dict]:
    """-> [{"mechanism","family","section","count"}] sorted by mechanism.
    Deterministic inventory of every lexicon phrase the SDD names, and where.
    Mechanisms are reported under their canonical lexicon phrase; ambiguous
    single words require Salesforce context in the surrounding window."""
    found: dict[tuple[str, str], int] = {}
    for sec in doc["sections"]:
        blob = sec["title"] + "\n" + sec["text"]
        for m in _RX.finditer(blob):
            mech = _canonical(m.group(0))
            if mech in _AMBIGUOUS and not _in_context(blob, m.start(), m.end()):
                continue
            key = (mech, sec["ref"])
            found[key] = found.get(key, 0) + 1
    return [{"mechanism": mech, "family": _FAMILY.get(mech, "?"),
             "section": ref, "count": n}
            for (mech, ref), n in sorted(found.items())]
