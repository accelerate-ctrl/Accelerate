"""Persona parser — v7.0 schema-aware (PRD FR-1, AC-4).

The previous implementation used ``re.split(r"[,;\\n]", cell)`` which shreds
v7.0 Personas cells like::

    CDO (Chief Data Officer, Data Lead); LOB Heads (Line of Business Leads)

into ``["CDO (Chief Data Officer", "Data Lead)", "LOB Heads (Line of Business Leads)"]``
because the comma inside the parenthetical is taken as a delimiter. This
module splits only on top-level delimiters (``;`` and newline), then
extracts the canonical persona name and the parenthetical role
description into a structured :class:`PersonaRef`.

Canonical persona names are mapped to one of the five :class:`PersonaFamily`
values from PRD §4. Unknown names map to ``PersonaFamily.OPERATIONS`` as a
neutral default — the canonical persona registry (Phase 3) will later
override this with curated mappings.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

from app.models.common import PersonaFamily, schema_version


class PersonaRef(BaseModel):
    """A single persona reference parsed out of a v7.0 Personas cell."""

    canonical_name: str = Field(..., description="Canonical persona name, e.g. 'CDO'")
    role_description: str | None = Field(
        None,
        description="Parenthetical role description, e.g. 'Chief Data Officer, Data Lead'",
    )
    family: PersonaFamily = Field(
        PersonaFamily.OPERATIONS,
        description="Persona family bucket for the persona switcher",
    )
    raw: str = Field(..., description="Original token as it appeared in the cell")
    schema_version_: str = Field(
        default_factory=lambda: schema_version("persona_ref"),
        alias="_schema_version",
    )

    model_config = {"populate_by_name": True}


# ─── Canonical name → family mapping ───────────────────────────────────────
#
# Conservative starter mapping. Pillar leads will extend the canonical
# persona registry in Phase 3 (task 1-005 follow-up); for now we cover the
# personas that appear in the v7.0 Pillar 1 workbook plus the obvious
# cross-pillar tokens. Unknown names default to OPERATIONS so they still
# render in the persona switcher's neutral bucket.

_FAMILY_MAP: dict[str, PersonaFamily] = {
    # C-suite
    "ceo": PersonaFamily.C_SUITE,
    "cfo": PersonaFamily.C_SUITE,
    "coo": PersonaFamily.C_SUITE,
    "cto": PersonaFamily.C_SUITE,
    "cio": PersonaFamily.C_SUITE,
    "cdo": PersonaFamily.C_SUITE,
    "ciso": PersonaFamily.C_SUITE,
    "cmo": PersonaFamily.C_SUITE,
    "cco": PersonaFamily.C_SUITE,  # chief compliance
    "cro": PersonaFamily.C_SUITE,
    "chief data officer": PersonaFamily.C_SUITE,
    "chief technology officer": PersonaFamily.C_SUITE,
    "chief information officer": PersonaFamily.C_SUITE,
    "chief risk officer": PersonaFamily.C_SUITE,
    "chief operating officer": PersonaFamily.C_SUITE,
    "chief financial officer": PersonaFamily.C_SUITE,
    "chief executive officer": PersonaFamily.C_SUITE,
    # Technology
    "architect": PersonaFamily.TECHNOLOGY,
    "engineer": PersonaFamily.TECHNOLOGY,
    "developer": PersonaFamily.TECHNOLOGY,
    "data engineer": PersonaFamily.TECHNOLOGY,
    "ml engineer": PersonaFamily.TECHNOLOGY,
    "data scientist": PersonaFamily.TECHNOLOGY,
    "platform engineer": PersonaFamily.TECHNOLOGY,
    "salesforce admin": PersonaFamily.TECHNOLOGY,
    "salesforce developer": PersonaFamily.TECHNOLOGY,
    "integration architect": PersonaFamily.TECHNOLOGY,
    # Operations / business
    "lob head": PersonaFamily.OPERATIONS,
    "lob heads": PersonaFamily.OPERATIONS,
    "product owner": PersonaFamily.OPERATIONS,
    "product manager": PersonaFamily.OPERATIONS,
    "program manager": PersonaFamily.OPERATIONS,
    "business analyst": PersonaFamily.OPERATIONS,
    "operations manager": PersonaFamily.OPERATIONS,
    "operations lead": PersonaFamily.OPERATIONS,
    "branch manager": PersonaFamily.OPERATIONS,
    "service ops": PersonaFamily.OPERATIONS,
    # Risk + compliance
    "risk officer": PersonaFamily.RISK_COMPLIANCE,
    "compliance officer": PersonaFamily.RISK_COMPLIANCE,
    "audit lead": PersonaFamily.RISK_COMPLIANCE,
    "internal audit": PersonaFamily.RISK_COMPLIANCE,
    "model risk": PersonaFamily.RISK_COMPLIANCE,
    "fraud analyst": PersonaFamily.RISK_COMPLIANCE,
    "aml analyst": PersonaFamily.RISK_COMPLIANCE,
    "regulatory affairs": PersonaFamily.RISK_COMPLIANCE,
    # Frontline / customer facing
    "relationship manager": PersonaFamily.FRONTLINE,
    "advisor": PersonaFamily.FRONTLINE,
    "agent": PersonaFamily.FRONTLINE,
    "broker": PersonaFamily.FRONTLINE,
    "underwriter": PersonaFamily.FRONTLINE,
    "claims adjuster": PersonaFamily.FRONTLINE,
    "loan officer": PersonaFamily.FRONTLINE,
    "csr": PersonaFamily.FRONTLINE,
    "teller": PersonaFamily.FRONTLINE,
    "customer service": PersonaFamily.FRONTLINE,
    "wealth advisor": PersonaFamily.FRONTLINE,
}


def _family_for(canonical_name: str) -> PersonaFamily:
    """Look up the family for a canonical persona name, case-insensitively.

    Falls back to ``PersonaFamily.OPERATIONS`` for unknown names so the
    persona switcher renders them in a neutral bucket rather than dropping
    them silently.
    """
    key = canonical_name.strip().lower()
    if key in _FAMILY_MAP:
        return _FAMILY_MAP[key]
    # Substring match for compound names ("Head of Data" → matches "data")
    for k, fam in _FAMILY_MAP.items():
        if k in key:
            return fam
    return PersonaFamily.OPERATIONS


# Splits the cell on ``;`` or newlines only when the delimiter is at the
# top level (depth-0 parens). ``,`` is NOT a top-level delimiter for the
# v7.0 schema — commas legitimately appear inside parenthetical role
# descriptions.
_NAME_AND_ROLE = re.compile(r"^\s*(?P<name>[^()]+?)\s*(?:\((?P<role>[^)]*)\))?\s*$")


def _split_top_level(cell: str) -> list[str]:
    """Split a string on the appropriate top-level delimiters.

    Schema-aware:
    - **v14** cells use ``,`` as the delimiter and never carry parenthetical
      role descriptions (e.g. ``"CIO, CDO, Chief Strategy Officer"``).
    - **v7.0** cells use ``;`` (and newlines) and put role descriptions in
      parentheses that legitimately contain commas
      (e.g. ``"CDO (Chief Data Officer, Data Lead); LOB Heads (...)"``).

    We detect the schema by looking for parentheses in the cell. When
    parentheses are present, only ``;`` and newlines split at top-level
    parens-depth-0 (commas are inside-paren content). When parentheses are
    absent, commas, semicolons, and newlines all split at depth 0. This
    keeps the v7.0 contract correct while remaining backward-compatible
    with v14 fixtures during the migration window.
    """
    has_parens = "(" in cell
    out: list[str] = []
    buf: list[str] = []
    depth = 0
    for ch in cell:
        if ch == "(":
            depth += 1
            buf.append(ch)
        elif ch == ")":
            depth = max(0, depth - 1)
            buf.append(ch)
        elif depth == 0 and (
            ch == ";"
            or ch == "\n"
            or (ch == "," and not has_parens)
        ):
            token = "".join(buf).strip()
            if token:
                out.append(token)
            buf = []
        else:
            buf.append(ch)
    tail = "".join(buf).strip()
    if tail:
        out.append(tail)
    return out


def parse_personas(cell: Any) -> list[PersonaRef]:
    """Parse a v7.0 ``Personas`` cell into structured PersonaRefs.

    Handles all of:
    - ``"CDO; LOB Heads"`` → 2 refs, no role
    - ``"CDO (Chief Data Officer)"`` → 1 ref with role
    - ``"CDO (Chief Data Officer, Data Lead); LOB Heads (Line of Business)"`` →
      2 refs with roles (the comma inside the first parenthetical does NOT
      split the cell)
    - Empty / None → ``[]``
    """
    if cell is None:
        return []
    s = str(cell).strip()
    if not s:
        return []

    refs: list[PersonaRef] = []
    for token in _split_top_level(s):
        match = _NAME_AND_ROLE.match(token)
        if match:
            name = match.group("name").strip()
            role = (match.group("role") or "").strip() or None
        else:
            # Token is unparseable (e.g. contains stray parens); fall back
            # to treating the whole thing as the canonical name. We still
            # surface it rather than drop it so audit/QA can flag it.
            name = token
            role = None
        if not name:
            continue
        refs.append(PersonaRef(
            canonical_name=name,
            role_description=role,
            family=_family_for(name),
            raw=token,
        ))
    return refs


def parse_persona_names(cell: Any) -> list[str]:
    """Convenience wrapper that returns only canonical names.

    Used by call sites that haven't migrated to the structured
    :class:`PersonaRef` model yet.
    """
    return [ref.canonical_name for ref in parse_personas(cell)]
