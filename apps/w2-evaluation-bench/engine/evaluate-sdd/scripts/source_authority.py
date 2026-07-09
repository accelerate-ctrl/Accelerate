#!/usr/bin/env python3
"""source_authority.py  (Claim 5 — single source of R23 truth)

ONE canonical Salesforce-source-authority check, imported by release_crosswalk,
score_sheet_populate, evidence/report validators, and the Mode B validator, so
the R23 rule cannot drift between scripts. Uses canonical host parsing — a URL
where 'salesforce.com' appears only in the path or query string is REJECTED.
"""
from __future__ import annotations
import re
from urllib.parse import urlparse

# Approved Salesforce-controlled hosts. Any *.salesforce.com subdomain is admitted
# via the suffix rule.
SALESFORCE_DOMAINS = {
    "help.salesforce.com", "architect.salesforce.com", "developer.salesforce.com",
    "releasenotes.docs.salesforce.com", "trailhead.salesforce.com",
    "salesforce.com", "www.salesforce.com", "admin.salesforce.com",
    "ideas.salesforce.com", "trust.salesforce.com",
}


def is_salesforce_url(url: str) -> bool:
    """True only when the URL's HOST is a Salesforce-controlled domain (or a
    *.salesforce.com subdomain). Path/query occurrences do NOT count, so
    https://evil.example.com/x?ref=help.salesforce.com is correctly REJECTED."""
    if not url or not isinstance(url, str):
        return False
    try:
        host = urlparse(url.strip()).hostname
    except Exception:
        return False
    if not host:
        # urlparse needs a scheme; try prefixing then re-parse for bare hosts
        m = re.match(r"^([a-z0-9.-]+)", url.strip().lower())
        host = m.group(1) if m else None
    if not host:
        return False
    host = host.lower()
    return host in SALESFORCE_DOMAINS or any(host.endswith("." + d) for d in SALESFORCE_DOMAINS)
