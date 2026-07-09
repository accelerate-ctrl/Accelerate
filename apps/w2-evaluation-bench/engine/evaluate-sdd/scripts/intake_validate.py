#!/usr/bin/env python3
"""
intake_validate.py (v3) — Section A helper.

Changes from v2:
- Now takes 3 operator inputs (input artefact + 2 SDDs). Library entry ID is
  resolved in Section B by the ZMS loader shim; operator identity
  resolves from session context (passed via --operator-session-id).
- Minimum-word check relaxed from 500 to 200 to accommodate dense short SDDs
  (per NLP-heavy intake design). The bar is now "non-trivially populated"
  rather than "long enough."
- Format-agnostic structural validation: no SDD section conventions enforced.
- Added --integration-count override (NLP-derived count from orchestrator).

Inputs (CLI):
    --input-artefact, --ots-sdd, --zennagent-sdd
    --output-dir
    --evaluator-model
    [--operator-session-id <id>]          # session-resolved; default 'session'
    [--integration-heavy-override true|false]
    [--integration-count <N>]             # NLP-derived count override
    [--lane-assignment fixed|random]      # default: random

Outputs:
    <output-dir>/section-a-output.json
    <output-dir>/.lane-mapping
    <output-dir>/run-record.json

Returns JSON to stdout. Exit 0 on success; non-zero on reject conditions.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import random
import re
import sys
import uuid
from pathlib import Path

# contracts.py (same scripts/ dir) is the single source of the framework version.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import contracts


MIN_SUBSTANTIVE_WORDS_SDD = 200  # relaxed from 500 for NLP-heavy intake
INTEGRATION_HEAVY_THRESHOLD = 4  # OH §3.1

UI_ARTEFACT_PATTERNS = [
    re.compile(r"<\|im_start\|>", re.IGNORECASE),
    re.compile(r"<\|im_end\|>", re.IGNORECASE),
    re.compile(r"^Human:\s", re.MULTILINE),
    re.compile(r"```tool_use", re.IGNORECASE),
    re.compile(r"function_calls>", re.IGNORECASE),
]

# Distinct-named-systems detection — fallback for when no NLP-derived count is supplied.
NAMED_SYSTEM_PATTERNS = {
    "MuleSoft":              re.compile(r"\bMuleSoft\b", re.IGNORECASE),
    "Boomi":                 re.compile(r"\bBoomi\b", re.IGNORECASE),
    "Workato":               re.compile(r"\bWorkato\b", re.IGNORECASE),
    "Informatica":           re.compile(r"\bInformatica\b", re.IGNORECASE),
    "TIBCO":                 re.compile(r"\bTIBCO\b", re.IGNORECASE),
    "Snowflake":             re.compile(r"\bSnowflake\b", re.IGNORECASE),
    "Workday":               re.compile(r"\bWorkday\b", re.IGNORECASE),
    "NetSuite":              re.compile(r"\bNetSuite\b", re.IGNORECASE),
    "SAP":                   re.compile(r"\bSAP\b"),
    "Oracle":                re.compile(r"\bOracle\b", re.IGNORECASE),
    "DocuSign":              re.compile(r"\bDocuSign\b", re.IGNORECASE),
    "Stripe":                re.compile(r"\bStripe\b", re.IGNORECASE),
    "Plaid":                 re.compile(r"\bPlaid\b", re.IGNORECASE),
    "AWS":                   re.compile(r"\b(AWS|Amazon Web Services)\b", re.IGNORECASE),
    "Azure":                 re.compile(r"\b(Azure|Microsoft Azure)\b", re.IGNORECASE),
    "GCP":                   re.compile(r"\b(GCP|Google Cloud)\b", re.IGNORECASE),
    "Twilio":                re.compile(r"\bTwilio\b", re.IGNORECASE),
    "Slack":                 re.compile(r"\bSlack\b", re.IGNORECASE),
    "Marketo":               re.compile(r"\bMarketo\b", re.IGNORECASE),
    "HubSpot":               re.compile(r"\bHubSpot\b", re.IGNORECASE),
    "Zendesk":               re.compile(r"\bZ[ae]ndesk\b", re.IGNORECASE),
    "ServiceNow":            re.compile(r"\bServiceNow\b", re.IGNORECASE),
    "Jira":                  re.compile(r"\b(Jira|Atlassian)\b", re.IGNORECASE),
    "GitHub":                re.compile(r"\bGitHub\b", re.IGNORECASE),
    "Salesforce Platform Events":     re.compile(r"\bPlatform Events?\b", re.IGNORECASE),
    "Salesforce Change Data Capture": re.compile(r"\b(Change Data Capture|\bCDC\b)\b"),
    "Salesforce Apex Callouts":       re.compile(r"\bApex Callout\b", re.IGNORECASE),
    "Salesforce Named Credentials":   re.compile(r"\bNamed Credentials?\b", re.IGNORECASE),
}

GENERIC_INTEGRATION_PATTERNS = {
    "REST API":  re.compile(r"\bREST\s+API\b", re.IGNORECASE),
    "SOAP":      re.compile(r"\bSOAP\b"),
    "GraphQL":   re.compile(r"\bGraphQL\b", re.IGNORECASE),
    "Webhook":   re.compile(r"\b[Ww]ebhook\b"),
    "OAuth":     re.compile(r"\bOAuth\b"),
    "JWT":       re.compile(r"\bJWT\b"),
    "SSO/SAML":  re.compile(r"\b(SSO|SAML|OIDC)\b"),
}


def generate_run_id() -> str:
    today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    return f"W2-{today}-{uuid.uuid4().hex[:8]}"


def utc_timestamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def read_text(path: Path) -> str:
    """Read text from any text-like file. For docx, try sibling .extracted.txt."""
    if path.suffix.lower() in (".txt", ".md"):
        return path.read_text(encoding="utf-8", errors="replace")
    sibling = path.with_suffix(path.suffix + ".extracted.txt")
    if sibling.exists():
        return sibling.read_text(encoding="utf-8", errors="replace")
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def count_substantive_words(text: str) -> int:
    cleaned = re.sub(r"[#*_>`|\-]", " ", text)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return len([w for w in cleaned.split() if len(w) > 1])


def detect_ui_artefacts(text: str) -> list[str]:
    found = []
    for pattern in UI_ARTEFACT_PATTERNS:
        m = pattern.search(text)
        if m:
            found.append(m.group(0))
    return found


def validate_sdd_structure(label: str, path: Path) -> dict:
    """Structural sanity check only. No section convention enforced."""
    result = {
        "label": label, "path": str(path), "passed": True,
        "reason": None, "word_count": 0, "ui_artefacts": [],
    }
    if not path.exists():
        result.update(passed=False, reason=f"File not found: {path}")
        return result
    text = read_text(path)
    if not text.strip():
        result.update(passed=False, reason="Empty or unreadable file")
        return result
    word_count = count_substantive_words(text)
    result["word_count"] = word_count
    if word_count < MIN_SUBSTANTIVE_WORDS_SDD:
        result.update(passed=False,
                      reason=f"Under {MIN_SUBSTANTIVE_WORDS_SDD} substantive words ({word_count})")
        return result
    artefacts = detect_ui_artefacts(text)
    if artefacts:
        result.update(passed=False, ui_artefacts=artefacts,
                      reason=f"UI artefacts detected: {artefacts[:3]}")
    return result


def detect_distinct_integrations(text: str) -> tuple[int, list[str]]:
    """OH §3.1: 4+ material integration points → integration-heavy.

    Counts distinct named systems + generic integration patterns. Fallback
    when no NLP-derived count is supplied by the orchestrator.
    """
    found_named = [name for name, pat in NAMED_SYSTEM_PATTERNS.items() if pat.search(text)]
    found_generic = [name for name, pat in GENERIC_INTEGRATION_PATTERNS.items() if pat.search(text)]
    detected = found_named + found_generic
    return len(detected), detected


# === v3.7: Applicability flag derivation for ZMS ===
# Each flag corresponds to a ZMS criterion's applicability keyword. The 13 flags
# below are the canonical set (matches ZMS skill's RECOGNISED_FLAGS minus ALL).
# Derivation is regex-based on the operator BRD/input artefact text; conservative
# defaults (False) for any flag we can't infer with confidence — the operator can
# override via the orchestrator if intake misses a flag the engagement requires.

APPLICABILITY_PATTERNS: dict[str, list[re.Pattern]] = {
    "EXTERNAL_USERS": [
        re.compile(r'\bexperience\s+cloud\b', re.IGNORECASE),
        re.compile(r'\bcustomer\s+portal\b', re.IGNORECASE),
        re.compile(r'\bpartner\s+portal\b', re.IGNORECASE),
        re.compile(r'\bexternal\s+(user|portal|community|site)\b', re.IGNORECASE),
        re.compile(r'\bcommunity\s+(user|site|portal)\b', re.IGNORECASE),
    ],
    "REGULATED": [
        re.compile(r'\b(HIPAA|GDPR|SOX|PCI[\s-]?DSS|FedRAMP|GxP)\b'),
        re.compile(r'\bregulated\s+(industry|environment)\b', re.IGNORECASE),
        re.compile(r'\bfinancial\s+services\b', re.IGNORECASE),
        re.compile(r'\bhealthcare\b', re.IGNORECASE),
        re.compile(r'\bgovernment\b', re.IGNORECASE),
        re.compile(r'\bcompliance\s+(requirements?|obligations?|framework)\b', re.IGNORECASE),
    ],
    "REGULATORY_CITATION": [
        re.compile(r'\b(SOX|HIPAA|GDPR)\s*§\s*\d+', re.IGNORECASE),
        re.compile(r'\barticle\s+\d+\s+(of\s+)?(GDPR|HIPAA)', re.IGNORECASE),
        re.compile(r'\b(SOX|HIPAA|GDPR)\s+(section|article|requirement)\s+\d+', re.IGNORECASE),
    ],
    "AUTOMATION": [
        re.compile(r'\b(flow\s+builder|approval\s+process|validation\s+rule)\b', re.IGNORECASE),
        re.compile(r'\bautomation\b', re.IGNORECASE),
        re.compile(r'\bbusiness\s+logic\b', re.IGNORECASE),
        re.compile(r'\bworkflow\b', re.IGNORECASE),
    ],
    "TRIGGERS": [
        re.compile(r'\bapex\s+triggers?\b', re.IGNORECASE),
        re.compile(r'\btrigger\s+framework\b', re.IGNORECASE),
        re.compile(r'\bone\s+trigger\s+per\s+object\b', re.IGNORECASE),
    ],
    "CUSTOM_BUILD": [
        re.compile(r'\bcustom\s+(apex|build|lwc|component|object)\b', re.IGNORECASE),
        re.compile(r'\b(lightning\s+web\s+component|LWC)\b'),
        re.compile(r'\baura\s+component\b', re.IGNORECASE),
    ],
    "UI_IN_SCOPE": [
        re.compile(r'\b(user\s+interface|UI|UX|user\s+experience)\b'),
        re.compile(r'\blightning\s+(page|app|tab|record\s+page)\b', re.IGNORECASE),
        re.compile(r'\bpage\s+layout\b', re.IGNORECASE),
        re.compile(r'\bdynamic\s+forms?\b', re.IGNORECASE),
    ],
    "MULTI_CLOUD": [
        re.compile(r'\b(sales\s+cloud|service\s+cloud|marketing\s+cloud|experience\s+cloud|'
                   r'commerce\s+cloud|health\s+cloud|financial\s+services\s+cloud|'
                   r'data\s+cloud|nonprofit\s+cloud|education\s+cloud|manufacturing\s+cloud)\b',
                   re.IGNORECASE),
    ],
    "CONFIG_DRIVEN": [
        re.compile(r'\bconfiguration[\s-]driven\b', re.IGNORECASE),
        re.compile(r'\bconfigurable\b', re.IGNORECASE),
        re.compile(r'\bcustom\s+metadata\b', re.IGNORECASE),
    ],
    "API": [
        re.compile(r'\b(REST|SOAP)\s+API\b'),
        re.compile(r'\bAPI\s+(integration|consumption|callout|endpoint)\b', re.IGNORECASE),
        re.compile(r'\bexternal\s+(service|API)\b', re.IGNORECASE),
        re.compile(r'\bnamed\s+credentials?\b', re.IGNORECASE),
    ],
    "DATA_MIGRATION": [
        re.compile(r'\bdata\s+migration\b', re.IGNORECASE),
        re.compile(r'\b(load|migrate|migration|extract)\s+(historical|legacy|existing)\s+data\b', re.IGNORECASE),
        re.compile(r'\bdata\s+(loader|workbench)\b', re.IGNORECASE),
        re.compile(r'\bETL\b'),
    ],
    "PHASING": [
        re.compile(r'\b(phase|phases|phasing|phased\s+(delivery|rollout|release))\b', re.IGNORECASE),
        re.compile(r'\b(MVP|pilot|wave\s+\d|release\s+\d)\b', re.IGNORECASE),
        re.compile(r'\bphase\s+\d', re.IGNORECASE),
    ],
}


def derive_applicability_flags(input_text: str, integration_count: int) -> dict[str, bool]:
    """Derive the 13 ZMS applicability flags from the operator BRD/input artefact.

    Returns a dict {FLAG_NAME: bool} for each of the 13 ZMS applicability keys.
    INTEGRATIONS is derived directly from integration_count (≥4 = integration_heavy
    AND triggers INTEGRATIONS flag). Other 12 are regex-based.

    Conservative defaults: False when patterns don't match. The orchestrator can
    override via the run-record post-intake if the engagement requires a flag
    the intake regex didn't catch.
    """
    flags: dict[str, bool] = {}

    # INTEGRATIONS — directly from integration_count
    flags["INTEGRATIONS"] = integration_count >= INTEGRATION_HEAVY_THRESHOLD

    for flag_name, patterns in APPLICABILITY_PATTERNS.items():
        # Special-case MULTI_CLOUD: must match ≥2 different clouds
        if flag_name == "MULTI_CLOUD":
            clouds_matched = set()
            for pat in patterns:
                for m in pat.finditer(input_text):
                    clouds_matched.add(m.group(0).lower())
            flags[flag_name] = len(clouds_matched) >= 2
        else:
            flags[flag_name] = any(pat.search(input_text) for pat in patterns)

    return flags


def resolve_methodology_version(version: str) -> str:
    """Methodology version describes the project's template/knowledge package
    that the ZennAgent lane had access to when generating the ZA SDD. Default
    to 'methodology-current' when not supplied — the project's current
    template state is implicit in which templates are loaded in knowledge.
    """
    return version or "methodology-current"


def assign_blinding(mode: str) -> dict:
    if mode == "fixed":
        return {"Output A": "ZennAgent", "Output B": "off-the-shelf"}
    if random.random() < 0.5:
        return {"Output A": "ZennAgent", "Output B": "off-the-shelf"}
    return {"Output A": "off-the-shelf", "Output B": "ZennAgent"}


def _run_sdd_review(args, result, run_id) -> int:
    """Mode B intake: validate the one SDD, derive applicability flags from the
    input artefact, and write a single-lane section-a output + run record.

    No blinding (one lane, nothing to compare against, so nothing to leak
    toward). Origin is recorded as metadata only and is explicitly barred from
    influencing any downstream finding."""
    sdd_check = validate_sdd_structure("single_sdd", args.single_sdd)
    result["structural_validation"] = {"single_sdd": sdd_check}
    if not sdd_check["passed"]:
        result["reject"] = {"section": "A", "reason_code": "STRUCTURAL_INVALID_SDD",
                            "detail": f"SDD failed: {sdd_check['reason']}"}
        print(json.dumps(result, indent=2))
        return 3

    input_text = read_text(args.input_artefact)
    if args.integration_count is not None:
        result["integration_count"] = args.integration_count
        result["integration_systems_detected"] = ["<NLP-derived; see orchestrator>"]
        result["integration_count_basis"] = "orchestrator-supplied NLP-derived count"
    else:
        count, systems = detect_distinct_integrations(input_text)
        result["integration_count"] = count
        result["integration_systems_detected"] = systems
        result["integration_count_basis"] = (
            f"regex-derived from input artefact: {count} distinct integration patterns detected")

    if args.integration_heavy_override is not None:
        result["run_integration_heavy"] = args.integration_heavy_override == "true"
    else:
        result["run_integration_heavy"] = result["integration_count"] >= INTEGRATION_HEAVY_THRESHOLD

    flags = derive_applicability_flags(input_text, result["integration_count"])
    flags["INTEGRATIONS"] = result["run_integration_heavy"]
    result["applicability_flags"] = flags
    result["applicability_flags_basis"] = {
        "derivation": "regex over operator input artefact text + integration count",
        "default_for_unmatched": False,
        "fired": sorted([k for k, v in flags.items() if v]),
    }

    # Single lane: a fixed, non-blinded label. Origin is metadata only.
    result["sdd_review"] = {
        "sdd_path": str(args.single_sdd),
        "sdd_sha256": sha256_of_file(args.single_sdd),
        "origin_label": args.single_sdd_origin,
        "origin_policy": ("Origin is a report label only. It is NEVER an input to any finding, "
                          "recommendation, or judgement — the SDD review measures the SDD against "
                          "ZMS as a lens identically regardless of which tool produced it."),
        "scoring_enabled": bool(args.enable_single_scoring),
        "scoring_policy": ("Default OFF: Mode B is a qualitative SDD review. Numeric scoring runs "
                           "only when the operator passes --enable-single-scoring (hidden opt-in)."),
        "blinding": "none (single lane; nothing to compare, nothing to leak toward)",
    }
    result["blinding"] = {"mode": "none", "reason": "sdd_review has one lane"}

    methodology_version = resolve_methodology_version(args.methodology_version)
    run_record = {
        "run_id": run_id,
        "run_timestamp": result["run_timestamp"],
        "operator_session_id": args.operator_session_id,
        "run_type": "sdd_review",
        "zms_version": None,
        "zms_frozen_at": None,
        "zms_applicable_criteria_count": None,
        "zms_critical_floor_active": None,
        "model_version": args.evaluator_model,
        "evaluator_model_version": args.evaluator_model,
        "methodology_version": methodology_version,
        "rubric_version": contracts.FRAMEWORK_VERSION,
        "operations_handbook_version": contracts.FRAMEWORK_VERSION,
        "framework_version": contracts.FRAMEWORK_VERSION,
        "input_artefact_sha256": result["input_artefact_sha256"],
        "run_integration_heavy": result["run_integration_heavy"],
        "integration_count": result["integration_count"],
        "applicability_flags": result["applicability_flags"],
        "sdd_review": result["sdd_review"],
        "release_awareness_path": None,   # populated by release_crosswalk in C.5
        "_outputs": {"sdd_review_report_path": None},
    }
    (args.output_dir / "run-record.json").write_text(json.dumps(run_record, indent=2), encoding="utf-8")
    section_a_path = args.output_dir / "section-a-output.json"
    section_a_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    result["files_written"] = {
        "section_a_output": str(section_a_path),
        "run_record": str(args.output_dir / "run-record.json"),
    }
    print(json.dumps(result, indent=2))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-artefact", required=True, type=Path)
    # Comparative (Mode A) inputs — both required together.
    ap.add_argument("--ots-sdd", type=Path, default=None)
    ap.add_argument("--zennagent-sdd", type=Path, default=None)
    # Neutral-isolation intake (preferred for Mode A): the operator supplies two
    # position-neutral candidates and, SEPARATELY, which POSITION is ZenAgent.
    # The identity goes straight to the escrow and is never echoed to stdout or
    # section-a-output.json, so the command the operator types does not tag
    # either SDD path with its lane. Back-compat: --ots-sdd/--zennagent-sdd still
    # work and behave exactly as before.
    ap.add_argument("--candidate-a", type=Path, default=None,
                    help="First candidate SDD (position-neutral; Mode A). Pair with --candidate-b and --zenagent-is.")
    ap.add_argument("--candidate-b", type=Path, default=None,
                    help="Second candidate SDD (position-neutral; Mode A).")
    ap.add_argument("--zenagent-is", choices=["a", "b"], default=None,
                    help="Which neutral candidate is the ZenAgent lane (a|b). Escrowed only; never echoed.")
    # Single-review (Mode B) input — one SDD, origin is OPTIONAL metadata only.
    ap.add_argument("--single-sdd", type=Path, default=None,
                    help="Mode B: the one SDD to review. Mutually exclusive with the lane pair.")
    ap.add_argument("--single-sdd-origin", type=str, default="unspecified",
                    choices=["zenagent", "off_the_shelf", "unspecified"],
                    help="Mode B: optional label only; NEVER influences findings (bias guard).")
    ap.add_argument("--mode", choices=["comparative", "sdd_review", "auto"], default="auto",
                    help="auto: comparative if both lane SDDs present, else sdd_review.")
    ap.add_argument("--enable-single-scoring", action="store_true",
                    help="Mode B hidden opt-in: also run numeric scoring on the single SDD. "
                         "Default OFF — Mode B is a qualitative SDD review.")
    ap.add_argument("--output-dir", required=True, type=Path)
    ap.add_argument("--evaluator-model", required=True,
                    help="The model version Claude is running on. Applied to BOTH lanes by construction.")
    ap.add_argument("--methodology-version", type=str, default=None,
                    help="The Zennify methodology / template package version available to the ZA lane.")
    ap.add_argument("--operator-session-id", type=str, default="session")
    ap.add_argument("--integration-heavy-override", type=str, default=None,
                    choices=["true", "false"])
    ap.add_argument("--integration-count", type=int, default=None,
                    help="NLP-derived integration count override (from orchestrator)")
    ap.add_argument("--lane-assignment", choices=["fixed", "random"], default="random")
    args = ap.parse_args()

    # --- Neutral-candidate normalisation (preferred Mode A intake) ---
    # If the operator supplied position-neutral candidates, map them onto the
    # internal ots/zennagent slots using --zenagent-is. This is the ONLY place
    # the identity is read; from here it flows only into the escrow, exactly as
    # a --zennagent-sdd invocation would. Neither the chosen position nor the
    # mapping is ever written to `result` (stdout / section-a-output.json).
    args._neutral_isolation = False
    if args.candidate_a is not None or args.candidate_b is not None:
        if args.candidate_a is None or args.candidate_b is None:
            print(json.dumps({"reject": {"section": "A", "reason_code": "INCOMPLETE_LANE_PAIR",
                  "detail": "Neutral intake requires BOTH --candidate-a and --candidate-b."}}, indent=2))
            return 2
        if args.zenagent_is is None:
            print(json.dumps({"reject": {"section": "A", "reason_code": "AMBIGUOUS_MODE",
                  "detail": "Neutral intake requires --zenagent-is a|b so the escrow can record the lane."}}, indent=2))
            return 2
        if args.zennagent_sdd is not None or args.ots_sdd is not None:
            print(json.dumps({"reject": {"section": "A", "reason_code": "AMBIGUOUS_MODE",
                  "detail": "Use EITHER --candidate-a/-b (neutral) OR --zennagent-sdd/--ots-sdd, not both."}}, indent=2))
            return 2
        if args.zenagent_is == "a":
            args.zennagent_sdd, args.ots_sdd = args.candidate_a, args.candidate_b
        else:
            args.zennagent_sdd, args.ots_sdd = args.candidate_b, args.candidate_a
        args._neutral_isolation = True

    # --- Mode resolution (explicit and confirmable; never silently guessed) ---
    has_pair = args.ots_sdd is not None and args.zennagent_sdd is not None
    has_single = args.single_sdd is not None
    if args.mode == "auto":
        mode = "comparative" if has_pair else ("sdd_review" if has_single else None)
    else:
        mode = args.mode

    run_id = generate_run_id()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Early, actionable rejects for malformed mode inputs.
    if mode is None:
        out = {"run_id": run_id, "run_type": None,
               "reject": {"section": "A", "reason_code": "NO_SDD_INPUT",
                          "detail": "Provide either both --ots-sdd and --zennagent-sdd "
                                    "(comparative) or --single-sdd (single review)."}}
        print(json.dumps(out, indent=2))
        return 2
    if mode == "comparative" and not has_pair:
        out = {"run_id": run_id, "run_type": "comparative",
               "reject": {"section": "A", "reason_code": "INCOMPLETE_LANE_PAIR",
                          "detail": "Comparative mode requires BOTH --ots-sdd and --zennagent-sdd."}}
        print(json.dumps(out, indent=2))
        return 2
    if mode == "sdd_review" and not has_single:
        out = {"run_id": run_id, "run_type": "sdd_review",
               "reject": {"section": "A", "reason_code": "NO_SINGLE_SDD",
                          "detail": "Single-review mode requires --single-sdd."}}
        print(json.dumps(out, indent=2))
        return 2
    if has_pair and has_single:
        out = {"run_id": run_id, "run_type": None,
               "reject": {"section": "A", "reason_code": "AMBIGUOUS_MODE",
                          "detail": "Provide the lane pair OR --single-sdd, not both."}}
        print(json.dumps(out, indent=2))
        return 2

    result = {
        "run_id": run_id,
        "run_timestamp": utc_timestamp(),
        "operator_session_id": args.operator_session_id,
        "input_artefact_path": str(args.input_artefact),
        "input_artefact_sha256": None,
        "structural_validation": {},
        "integration_count": None,
        "integration_systems_detected": [],
        "integration_count_basis": None,
        "run_integration_heavy": None,
        "evaluator_model": args.evaluator_model,
        "run_type": mode,
        "run_type_basis": (
            "comparative: two candidate SDDs supplied; blinded independent "
            "scoring of Output A / Output B + lift Diagnostic Report."
            if mode == "comparative" else
            "sdd_review: one SDD supplied; qualitative SDD review against ZMS as a "
            "lens (no scoring unless --enable-single-scoring). Origin is metadata only."
        ),
        "blinding": None,
        "reject": None,
    }

    if not args.input_artefact.exists():
        result["reject"] = {"section": "A", "reason_code": "INPUT_NOT_FOUND",
                            "detail": f"Input artefact path does not exist: {args.input_artefact}"}
        print(json.dumps(result, indent=2))
        return 2

    result["input_artefact_sha256"] = sha256_of_file(args.input_artefact)

    # === SINGLE-REVIEW (Mode B) branch ===
    if mode == "sdd_review":
        return _run_sdd_review(args, result, run_id)

    # === COMPARATIVE (Mode A) branch — unchanged behaviour ===
    ots_check = validate_sdd_structure("off_the_shelf_sdd", args.ots_sdd)
    za_check = validate_sdd_structure("zennagent_sdd", args.zennagent_sdd)
    if getattr(args, "_neutral_isolation", False):
        # Neutral intake: do NOT tag the scoring-side record with lane-named
        # keys OR labels. The evaluator sees two neutral candidate slots; the
        # slot->lane binding is escrowed with the lane map, not printed.
        c1 = dict(za_check if args.zenagent_is == "a" else ots_check)
        c2 = dict(ots_check if args.zenagent_is == "a" else za_check)
        c1["label"], c2["label"] = "candidate_1", "candidate_2"
        result["structural_validation"] = {"candidate_1": c1, "candidate_2": c2}
    else:
        result["structural_validation"] = {
            "off_the_shelf_sdd": ots_check, "zennagent_sdd": za_check,
        }
    if not ots_check["passed"]:
        result["reject"] = {"section": "A", "reason_code": "STRUCTURAL_INVALID_SDD",
                            "detail": f"Off-the-shelf SDD failed: {ots_check['reason']}"}
        print(json.dumps(result, indent=2))
        return 3
    if not za_check["passed"]:
        result["reject"] = {"section": "A", "reason_code": "STRUCTURAL_INVALID_SDD",
                            "detail": f"ZennAgent SDD failed: {za_check['reason']}"}
        print(json.dumps(result, indent=2))
        return 4

    # Integration count: NLP-supplied (preferred) or regex-derived (fallback)
    input_text = read_text(args.input_artefact)
    if args.integration_count is not None:
        result["integration_count"] = args.integration_count
        result["integration_systems_detected"] = ["<NLP-derived; see orchestrator>"]
        result["integration_count_basis"] = "orchestrator-supplied NLP-derived count"
    else:
        count, systems = detect_distinct_integrations(input_text)
        result["integration_count"] = count
        result["integration_systems_detected"] = systems
        result["integration_count_basis"] = (
            f"regex-derived from input artefact: {count} distinct integration patterns detected"
        )

    if args.integration_heavy_override is not None:
        result["run_integration_heavy"] = args.integration_heavy_override == "true"
        result["integration_count_basis"] += f" · operator override → {args.integration_heavy_override}"
    else:
        result["run_integration_heavy"] = result["integration_count"] >= INTEGRATION_HEAVY_THRESHOLD

    # === v3.7: Derive ZMS applicability flags ===
    # 13 flags consumed by ZMS criteria. Section B (zms_load.py) reads these
    # from this output and forwards them to the ZMS skill's loader.
    flags = derive_applicability_flags(input_text, result["integration_count"])
    # The INTEGRATIONS flag is canonical; integration_heavy is the rubric-side
    # equivalent. Keep them in sync.
    flags["INTEGRATIONS"] = result["run_integration_heavy"]
    result["applicability_flags"] = flags
    result["applicability_flags_basis"] = {
        "derivation": "regex over operator input artefact text + integration count",
        "default_for_unmatched": False,
        "operator_override_path": "edit section-a-output.json → applicability_flags before invoking zms_load.py",
        "fired": sorted([k for k, v in flags.items() if v]),
    }

    # Resolve methodology version (the project's template/knowledge package
    # available to the ZA lane). Defaults to "methodology-current" when not
    # supplied — the project's current template state is implicit.
    methodology_version = resolve_methodology_version(args.methodology_version)

    # Lane assignment — escrowed, NOT surfaced to the evaluator.
    blinding = assign_blinding(args.lane_assignment)

    # v4.6 — bind the Output labels to FILE PATHS, in two coordinated pieces:
    #
    # (1) The ESCROW now records, per label, both the origin AND the SDD file
    #     path: {"Output A": {"origin": ..., "sdd_path": ...}, ...}. Before
    #     v4.6 the escrow held only label->origin while assign_blinding() was
    #     an independent coin flip, and NOTHING recorded which file the
    #     orchestrator must score as "Output A" — so under the default random
    #     assignment the batch-7 reveal misattributed the lanes (and inverted
    #     the headline lift's sign) whenever the orchestrator's unrecorded
    #     file->label convention disagreed with the flip (~50% of runs).
    #
    # (2) A NON-SECRET `lane_files` map (label -> path, NO origins) is emitted
    #     in stdout and section-a-output.json. This is the artefact batches
    #     3-6 read to know which SDD file is which lane. It is leak-free by
    #     construction under the neutral intake (paths carry no identity), and
    #     under the legacy lane-named intake it reveals nothing the operator
    #     did not already type on the command line.
    origin_to_path = {"ZennAgent": str(args.zennagent_sdd),
                      "off-the-shelf": str(args.ots_sdd)}
    escrow = {label: {"origin": origin, "sdd_path": origin_to_path[origin]}
              for label, origin in blinding.items()}
    lane_files = {label: escrow[label]["sdd_path"] for label in ("Output A", "Output B")}
    lane_mapping_path = args.output_dir / ".lane-mapping"
    lane_mapping_path.write_text(json.dumps(escrow, indent=2), encoding="utf-8")
    result["lane_files"] = lane_files
    result["lane_files_note"] = (
        "Label -> SDD file binding (identity-neutral: paths only, no origins). "
        "Score the file at lane_files['Output A'] as Output A throughout "
        "batches 3-6; the origin behind each label stays in the escrow until "
        "batch 7 reveal.")
    result["blinding"] = {
        "status": "escrowed",
        "lane_assignment_method": args.lane_assignment,
        "neutral_isolation": bool(getattr(args, "_neutral_isolation", False)),
        "lane_mapping_file": str(lane_mapping_path),
        "note": ("Lane identity is escrowed and WITHHELD from the evaluator "
                 "until batch 7 reveal. Do not open the escrow during scoring; "
                 "score Output A / Output B as genuinely unknown lanes."
                 + (" Intake used neutral candidates; the operator supplied the "
                    "lane position out-of-band and it is recorded only in the escrow."
                    if getattr(args, "_neutral_isolation", False) else "")),
    }

    # By construction, both lanes use the same model. The methodology
    # difference is what the lift measures.
    result["evaluator_model_version"] = args.evaluator_model
    result["methodology_version"] = methodology_version
    result["lanes_use_same_model"] = True
    result["lanes_consume_same_input"] = True

    run_record = {
        "run_id": run_id,
        "run_timestamp": result["run_timestamp"],
        "operator_session_id": args.operator_session_id,
        # ZMS calibration fields — populated by zms_load.py in Section B
        "zms_version": None,
        "zms_frozen_at": None,
        "zms_applicable_criteria_count": None,
        "zms_critical_floor_active": None,
        # Structural attestations (true by construction every run):
        "same_input_attestation": "Structural: single input artefact passed to both lanes by construction",
        "same_model_attestation": (
            f"Structural: both lanes generated with model version "
            f"{args.evaluator_model}; the evaluator also uses {args.evaluator_model}. "
            f"Model variance is zero by construction."
        ),
        "methodology_difference_basis": (
            "The ZennAgent lane was generated with the Zennify methodology "
            "project knowledge (templates and guidance) available to the "
            "model. The off-the-shelf lane was generated with no project "
            "knowledge. The lift therefore isolates the contribution of the "
            "methodology, not the model."
        ),
        # Single model version applies to both lanes and to the evaluator:
        "model_version": args.evaluator_model,
        # The methodology / template package version available to the ZA lane:
        "methodology_version": methodology_version,
        # Framework versioning (single-sourced; one consistent v4.6 set):
        "rubric_version": contracts.FRAMEWORK_VERSION,
        "operations_handbook_version": contracts.FRAMEWORK_VERSION,
        "framework_version": contracts.FRAMEWORK_VERSION,
        # Operator-side fields:
        "input_artefact_sha256": result["input_artefact_sha256"],
        "run_integration_heavy": result["run_integration_heavy"],
        "integration_count": result["integration_count"],
        "integration_systems_detected": result["integration_systems_detected"],
        "integration_count_basis": result["integration_count_basis"],
        # v3.7: ZMS applicability flags
        "applicability_flags": result["applicability_flags"],
        # v3.7: Release-awareness — populated by release_awareness_check.py in Section C.5
        "release_awareness_a_path": None,
        "release_awareness_b_path": None,
        "rr_deductions_total_a": None,
        "rr_deductions_total_b": None,
        "_blinding": {
            "output_a_origin": None,  # filled at lane reveal
            "output_b_origin": None,
            "lane_revealed_at": None,
        },
        "_outputs": {
            "content_mapping_path": None,
            "output_a_score_sheet_path": None,
            "output_b_score_sheet_path": None,
            "diagnostic_report_path": None,
        },
    }
    run_record_path = args.output_dir / "run-record.json"
    run_record_path.write_text(json.dumps(run_record, indent=2), encoding="utf-8")

    section_a_path = args.output_dir / "section-a-output.json"
    section_a_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    result["files_written"] = {
        "section_a_output": str(section_a_path),
        "lane_mapping": str(lane_mapping_path),
        "run_record": str(run_record_path),
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
