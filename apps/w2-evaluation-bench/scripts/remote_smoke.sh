#!/bin/bash
# remote_smoke.sh — post-deploy verification of a LIVE W2 Evaluation Bench.
#
# Read-only by design: it never creates a run and never uploads a document, so
# it is safe against production. It proves the deployed service is the one the
# release gate certified: surfaces up, auth enforced, runner payload intact,
# escrow unreachable.
#
# Usage:
#   bash scripts/remote_smoke.sh https://<service-url> [member-token]
# Exit 0 = REMOTE SMOKE PASS. Any failed check exits 1 and names the check.
set -u
URL="${1:?usage: remote_smoke.sh <service-url> [member-token]}"
TOKEN="${2:-}"
URL="${URL%/}"
FAIL=0

say()  { printf '  %-46s %s\n' "$1" "$2"; }
code() { curl -s -o /dev/null -w '%{http_code}' --max-time 30 "$@"; }

check() { # check <name> <expected-code> <got-code>
  if [ "$3" = "$2" ]; then say "$1" "OK ($3)"; else say "$1" "FAIL (want $2, got $3)"; FAIL=1; fi
}

echo "== W2 remote smoke against $URL =="

# 1. health + static surfaces (token-exempt)
check "GET /health"                       200 "$(code "$URL/health")"
curl -s --max-time 30 "$URL/health" | grep -q '"ok": *true' \
  && say "healthz body ok:true" "OK" || { say "healthz body ok:true" "FAIL"; FAIL=1; }
check "GET /  (landing)"                  200 "$(code "$URL/")"
ROOT_HTML=$(curl -s --max-time 30 "$URL/")
echo "$ROOT_HTML" | grep -q "Two models. One blinded verdict" \
  && say "/ is the landing page" "OK" || { say "/ is the landing page" "FAIL"; FAIL=1; }
echo "$ROOT_HTML" | grep -q "Evaluation Bench · Console" \
  && { say "/ must not serve the console" "FAIL"; FAIL=1; } \
  || say "/ must not serve the console" "OK"
check "GET /bench (console)"              200 "$(code "$URL/bench")"
curl -s --max-time 30 "$URL/bench" | grep -q "Evaluation Bench · Console" \
  && say "/bench is the console" "OK" || { say "/bench is the console" "FAIL"; FAIL=1; }

# 2. auth is enforced (these MUST be 401 on a tokened deployment)
check "GET /api/runs without token -> 401" 401 "$(code "$URL/api/runs")"
check "GET /install.sh without token -> 401" 401 "$(code "$URL/install.sh")"
check "GET /install.ps1 without token -> 401" 401 "$(code "$URL/install.ps1")"
check "GET /runner.zip without token -> 401" 401 "$(code "$URL/runner.zip")"
check "bad token -> 401" 401 "$(code -H 'X-W2-Token: not-a-real-token' "$URL/api/runs")"

# 3. escrow / traversal is unreachable from outside (401 unauthenticated,
#    404 authenticated — either way, no file is served)
TRAV=$(code "$URL/api/runs/none/download/..%2F..%2Fstate.json${TOKEN:+?token=$TOKEN}")
if [ "$TRAV" = "404" ] || [ "$TRAV" = "401" ]; then
  say "download key traversal blocked" "OK ($TRAV)"
else
  say "download key traversal blocked" "FAIL (got $TRAV)"; FAIL=1
fi

# 4. security headers present
H=$(curl -sI --max-time 30 "$URL/health")
echo "$H" | grep -qi 'x-content-type-options: *nosniff' \
  && say "X-Content-Type-Options: nosniff" "OK" || { say "X-Content-Type-Options" "FAIL"; FAIL=1; }
echo "$H" | grep -qi 'x-frame-options: *deny' \
  && say "X-Frame-Options: DENY" "OK" || { say "X-Frame-Options" "FAIL"; FAIL=1; }

# 5. with a member token: API opens and the runner payload is intact
if [ -n "$TOKEN" ]; then
  check "GET /api/runs with token -> 200" 200 \
    "$(code -H "X-W2-Token: $TOKEN" "$URL/api/runs")"
  check "GET /api/runners with token -> 200" 200 \
    "$(code -H "X-W2-Token: $TOKEN" "$URL/api/runners")"
  TMPZ=$(mktemp)
  curl -s --max-time 60 -H "X-W2-Token: $TOKEN" -o "$TMPZ" "$URL/runner.zip"
  if python3 - "$TMPZ" <<'PY'
import sys, zipfile
names = zipfile.ZipFile(sys.argv[1]).namelist()
need = ["runner/w2_runner.py", "runner/billing_guard.py",
        "runner/gemini_judge.py", "runner/mock_intelligence.py"]
missing = [n for n in need if n not in names]
sys.exit(1 if missing else 0)
PY
  then say "runner.zip contains the full runner" "OK"
  else say "runner.zip contains the full runner" "FAIL (empty or partial zip)"; FAIL=1; fi
  rm -f "$TMPZ"
  curl -s --max-time 30 -H "X-W2-Token: $TOKEN" "$URL/install.sh" \
    | head -3 | grep -q "W2" \
    && say "install.sh is served personalized" "OK" \
    || { say "install.sh is served personalized" "FAIL"; FAIL=1; }
  curl -s --max-time 30 -H "X-W2-Token: $TOKEN" "$URL/install.ps1" \
    | grep -q "W2Server = '$URL'" \
    && say "install.ps1 is served personalized" "OK" \
    || { say "install.ps1 is served personalized" "FAIL"; FAIL=1; }
else
  echo "  (no member token supplied — skipped the authenticated checks;"
  echo "   re-run with a token for full coverage)"
fi

echo
if [ "$FAIL" -eq 0 ]; then echo "REMOTE SMOKE PASS"; else echo "REMOTE SMOKE FAIL"; exit 1; fi
