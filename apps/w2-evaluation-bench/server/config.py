"""w2app configuration — paths and engine wiring.

The application is a thin, deterministic shell around the v4.6 evaluate-sdd /
zms engine (vendored under engine/). It performs ZERO model calls itself: every
act of model judgment is exported as a work packet executed by an operator-side
runner under that operator's Claude subscription (Agent SDK credit). The server
deliberately contains no Anthropic SDK / API client — grep for 'anthropic' in
server/ to verify.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent
ENGINE_ROOT = APP_ROOT / "engine" / "evaluate-sdd"
ZMS_ROOT = APP_ROOT / "engine" / "zms"
SCRIPTS = ENGINE_ROOT / "scripts"
DATA_DIR = Path(os.environ.get("W2APP_DATA", APP_ROOT / "data"))
RUNS_DIR = DATA_DIR / "runs"
RUNS_DIR.mkdir(parents=True, exist_ok=True)

# Make the engine importable (contracts, validators, builders are libraries here).
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

# The escrow filename inside a run dir. In this application the WHOLE run dir is
# server-side; the escrow is additionally protected by never being served over
# any API route (see main.py: artifact downloads are whitelisted, and the
# packet payload builder never reads it).
ESCROW_NAME = ".lane-mapping"

# Scoring protocol (v2.0). "dual-judge" is the product: every scoring unit is
# judged once by each of contracts.JUDGES from byte-identical blinded packets,
# then merged by evidence-ruled consensus (server/consensus.py). "five-pass" is
# the frozen v1.1 protocol, retained ONLY for regression comparison (PRD D6,
# TRD section 4) — never exposed in the UI.
EVAL_PROTOCOL = os.environ.get("EVAL_PROTOCOL", "dual-judge")
if EVAL_PROTOCOL not in ("dual-judge", "five-pass"):
    raise RuntimeError(
        f"EVAL_PROTOCOL must be 'dual-judge' or 'five-pass', got {EVAL_PROTOCOL!r}")

PYTHON = sys.executable
