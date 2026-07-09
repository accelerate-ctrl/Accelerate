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
_RX = re.compile("|".join(r"\b" + re.escape(p).replace(r"\ ", r"[\s\-]") + r"\b"
                          for p in _PHRASES), re.I)
_FAMILY = {p: fam for fam, ps in SALESFORCE_LEXICON.items() for p in ps}


def find_mechanisms(doc: dict) -> list[dict]:
    """-> [{"mechanism","family","section","count"}] sorted by mechanism.
    Deterministic inventory of every lexicon phrase the SDD names, and where."""
    found: dict[tuple[str, str], int] = {}
    for sec in doc["sections"]:
        for m in _RX.finditer(sec["title"] + "\n" + sec["text"]):
            key = (m.group(0).lower(), sec["ref"])
            found[key] = found.get(key, 0) + 1
    return [{"mechanism": mech, "family": _FAMILY.get(mech, "?"),
             "section": ref, "count": n}
            for (mech, ref), n in sorted(found.items())]
