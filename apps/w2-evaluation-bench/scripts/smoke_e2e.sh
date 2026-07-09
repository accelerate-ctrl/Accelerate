#!/bin/bash
# End-to-end smoke v2 (plan 6.1) — the release gate. Mock engine, fresh data
# dirs, exits nonzero on any failure, prints SMOKE PASS at the end.
#
#   1. Mode A HANDS-FREE: done with ZERO approve calls (SM-1 single-touch),
#      >=1 dissent in the bundles, agreement stats present (T-6).
#   2. Mode A PAUSED: awaiting_checkpoint -> approve -> done (T-6).
#   3. Mode B: done + contested finding + dissent annex data (T-6).
#   4. T-11: server billing tripwire (402 + run error), duplicate-result
#      write-once, malformed-result 400 (packet stays open).
#   5. T-7: auth matrix + owner affinity + heartbeats (separate tokened server).
#   6. T-8: escrow never served; only the reveal path references it.
#   7. T-9: no Anthropic/Google SDK in server/.
#   8. T-10: EVAL_PROTOCOL=five-pass legacy run still green (frozen v4.6 path).
#
# Under EVAL_PROTOCOL=five-pass this script runs the LEGACY flow end to end
# (sections 1-3 adapt; dual-judge-only asserts are skipped) so the frozen
# path keeps its own green gate.
set -e
cd "$(dirname "$0")/.."
fail(){ echo "SMOKE FAIL: $*" >&2; exit 1; }
api(){ curl -s "$@"; }
PORT=${PORT:-8899}
F=${FIXTURES:-tests/fixtures}
DUAL=1
[ "${EVAL_PROTOCOL:-dual-judge}" = "five-pass" ] && DUAL=0
export W2APP_DATA=$(mktemp -d)
bash scripts/serve.sh $PORT >/dev/null
trap 'pkill -f "uvicorn serv[e]r.main" 2>/dev/null' EXIT

if [ "$DUAL" = 1 ]; then
echo "== 1. Mode A (hands-free dual-judge: single touch, dissents, agreement) =="
RID=$(api -X POST localhost:$PORT/api/runs -F brd=@$F/brd.md -F sdd_1=@$F/sdd1.md \
      -F sdd_2=@$F/sdd2.md -F zenagent_is=a | python3 -c "import json,sys;print(json.load(sys.stdin)['run_id'])")
python3 runner/w2_runner.py --server http://localhost:$PORT --engine mock --once --poll 0.3 >/dev/null
api localhost:$PORT/api/runs/$RID | W2D="$W2APP_DATA" RID="$RID" python3 -c "
import json, sys, os
d = json.load(sys.stdin)
assert d['status'] == 'done', ('not done WITHOUT approve (hands-free)', d.get('error'))
assert d.get('checkpoint_approved_by', '').startswith('auto'), d.get('checkpoint_approved_by')
cons = d['digests']['consensus']
for lab, c in cons.items():
    assert c.get('verdict_agreement_rate') is not None, (lab, c)
    assert c.get('reliability'), (lab, c)
nd = sum(c.get('dissents') or 0 for c in cons.values())
assert nd >= 1, 'no dissents in consensus digests'
rev = d['digests']['reveal']
assert rev.get('judge_lifts') and rev.get('lift_band') is not None
assert 'report' in d['artifacts'], d['artifacts']
rd = os.environ['W2D'] + '/runs/' + os.environ['RID']
ba = json.load(open(rd + '/output-a-scoring-bundle.json'))
assert ba.get('judge_independence_attestation'), 'R28 attestation missing from bundle'
print('  Mode A hands-free done - lift ZA-OTS =', rev['headline_lift_za_minus_ots'],
      '| band', rev['lift_band'], '| dissents', nd)"

echo "== 2. Mode A (paused D.5 checkpoint: opt-in pause -> approve -> done) =="
RIDP=$(api -X POST localhost:$PORT/api/runs -F brd=@$F/brd.md -F sdd_1=@$F/sdd1.md \
      -F sdd_2=@$F/sdd2.md -F zenagent_is=b -F auto_approve_checkpoint=false \
      | python3 -c "import json,sys;print(json.load(sys.stdin)['run_id'])")
python3 runner/w2_runner.py --server http://localhost:$PORT --engine mock --once --poll 0.3 >/dev/null
ST=$(api localhost:$PORT/api/runs/$RIDP | python3 -c "import json,sys;print(json.load(sys.stdin)['status'])")
[ "$ST" = "awaiting_checkpoint" ] || fail "paused run is $ST, expected awaiting_checkpoint"
api -X POST localhost:$PORT/api/runs/$RIDP/approve -H 'Content-Type: application/json' \
    -d '{"approve": true}' >/dev/null
python3 runner/w2_runner.py --server http://localhost:$PORT --engine mock --once --poll 0.3 >/dev/null
api localhost:$PORT/api/runs/$RIDP | python3 -c "
import json, sys
d = json.load(sys.stdin)
assert d['status'] == 'done', (d['status'], d.get('error'))
assert d.get('checkpoint_approved_by') != 'auto (pre-authorized at intake)'
print('  Mode A paused-checkpoint done - lift =',
      d['digests']['reveal']['headline_lift_za_minus_ots'])"

echo "== 3. Mode B (dual-judge review: contested flags) =="
RIDB=$(api -X POST localhost:$PORT/api/runs -F brd=@$F/brd.md -F sdd_1=@$F/sdd1.md \
      | python3 -c "import json,sys;print(json.load(sys.stdin)['run_id'])")
python3 runner/w2_runner.py --server http://localhost:$PORT --engine mock --once --poll 0.3 >/dev/null
api localhost:$PORT/api/runs/$RIDB | python3 -c "import json,sys;d=json.load(sys.stdin);assert d['status']=='done',d.get('error');print('  Mode B done -', json.dumps(d['digests']['review']))"
W2D="$W2APP_DATA" RIDB="$RIDB" python3 -c "
import json, os
rd = os.environ['W2D'] + '/runs/' + os.environ['RIDB']
b = json.load(open(rd + '/sdd-review-bundle.json'))
assert len(b.get('dissents') or []) >= 1, 'no Mode B dissents'
cf = [f['id'] for f in b['findings'] if f.get('contested')]
assert cf, 'no contested findings'
provs = {f.get('judge_provenance') for f in b['findings']}
assert 'agreed' in provs and 'dissent' in provs, provs
print('  contested findings:', cf, '| dissents:', len(b['dissents']))"

echo "== 4. T-11 billing tripwire + write-once + shape rejection =="
RIDT=$(api -X POST localhost:$PORT/api/runs -F brd=@$F/brd.md -F sdd_1=@$F/sdd1.md \
      | python3 -c "import json,sys;print(json.load(sys.stdin)['run_id'])")
PID=$(api "localhost:$PORT/api/runs/$RIDT" | python3 -c "import json,sys;print(json.load(sys.stdin)['open_packets'][0]['packet_id'])")
PIDQ=$(PID="$PID" python3 -c "import urllib.parse,os;print(urllib.parse.quote(os.environ['PID'], safe=''))")
CODE=$(curl -s -o /tmp/w2_shape.json -w "%{http_code}" -X POST \
  "localhost:$PORT/api/packets/$RIDT/$PIDQ/result" -H 'Content-Type: application/json' \
  -d '{"result": {"wrong": "shape"}, "usage": {}}')
[ "$CODE" = "400" ] || fail "malformed result returned $CODE, expected 400"
api localhost:$PORT/api/runs/$RIDT | python3 -c "
import json, sys
d = json.load(sys.stdin)
assert d['status'] == 'awaiting_packets' and d['open_packets'], 'run advanced on malformed result'
assert d.get('last_rejected_result'), 'rejection not surfaced in state'"
CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
  "localhost:$PORT/api/packets/$RIDT/$PIDQ/result" -H 'Content-Type: application/json' \
  -d '{"result": {"components": []}, "usage": {"total_cost_usd": 1.23}}')
[ "$CODE" = "402" ] || fail "nonzero-cost result returned $CODE, expected 402"
api localhost:$PORT/api/runs/$RIDT | python3 -c "
import json, sys
d = json.load(sys.stdin)
assert d['status'] == 'error' and 'BILLING_TRIPWIRE' in (d.get('error') or ''), d
print('  402 tripwire fired and halted the run loudly')"
DONE_PID=$(python3 -c "import urllib.parse;print(urllib.parse.quote('components:Output A', safe=''))")
NOTE=$(curl -s -X POST "localhost:$PORT/api/packets/$RID/$DONE_PID/result" \
  -H 'Content-Type: application/json' -d '{"result": {"components": []}, "usage": {}}' \
  | python3 -c "import json,sys;print(json.load(sys.stdin).get('note',''))")
echo "$NOTE" | grep -q "duplicate" || fail "duplicate result was not ignored: $NOTE"
echo "  write-once: duplicate result POST acknowledged and ignored"

echo "== 5. T-7 auth matrix + owner affinity + heartbeats =="
AUTH_PORT=${AUTH_PORT:-8890}
W2APP_DATA_AUTH=$(mktemp -d)
( W2APP_DATA="$W2APP_DATA_AUTH" W2APP_TOKENS="alice:tokA,bob:tokB" \
  setsid nohup python3 -m uvicorn server.main:app --port $AUTH_PORT --log-level warning \
  > /tmp/uvicorn-auth.log 2>&1 < /dev/null & )
sleep 2.5
[ "$(curl -s -o /dev/null -w '%{http_code}' localhost:$AUTH_PORT/api/runs)" = "401" ] || fail "no-token not 401"
[ "$(curl -s -o /dev/null -w '%{http_code}' -H 'X-W2-Token: nope' localhost:$AUTH_PORT/api/runs)" = "401" ] || fail "bad-token not 401"
RIDA2=$(curl -s -H "X-W2-Token: tokA" -X POST localhost:$AUTH_PORT/api/runs \
  -F brd=@$F/brd.md -F sdd_1=@$F/sdd1.md | python3 -c "import json,sys;print(json.load(sys.stdin)['run_id'])")
BOB=$(curl -s -H "X-W2-Token: tokB" "localhost:$AUTH_PORT/api/packets/next?runner_id=r-bob" \
  | python3 -c "import json,sys;print(json.load(sys.stdin).get('packet_id'))")
[ "$BOB" = "None" ] || fail "affinity broken: bob got alice's packet $BOB"
ALICE=$(curl -s -H "X-W2-Token: tokA" "localhost:$AUTH_PORT/api/packets/next?runner_id=r-alice" \
  | python3 -c "import json,sys;print(json.load(sys.stdin).get('packet_id'))")
[ "$ALICE" != "None" ] || fail "alice did not receive her own packet"
curl -s -H "X-W2-Token: tokA" localhost:$AUTH_PORT/api/runners | python3 -c "
import json, sys
rs = {r['member'] for r in json.load(sys.stdin)}
assert {'alice', 'bob'} <= rs, rs"
[ "$(curl -s -o /dev/null -w '%{http_code}' "localhost:$AUTH_PORT/api/runs/$RIDA2?token=tokA")" = "200" ] || fail "download token query param"
INST=$(curl -s "localhost:$AUTH_PORT/install.sh?token=tokA")
echo "$INST" | grep -q 'W2_TOKEN="tokA"' || fail "installer not personalized"
echo "$INST" | bash -n || fail "installer template not valid bash"
[ "$(curl -s -o /dev/null -w '%{http_code}' localhost:$AUTH_PORT/install.sh)" = "401" ] || fail "installer served without token"
curl -s -H "X-W2-Token: tokA" localhost:$AUTH_PORT/runner.zip -o /tmp/w2_runner_zip
python3 -c "
import zipfile
names = zipfile.ZipFile('/tmp/w2_runner_zip').namelist()
assert 'runner/w2_runner.py' in names and 'runner/billing_guard.py' in names, names
assert 'runner/examples/w2-runner.user.service' in names, names"
pkill -f "uvicorn server.main:app --port $AUTH_PORT" 2>/dev/null || true
rm -rf "$W2APP_DATA_AUTH"
echo "  401 matrix, affinity, heartbeats, personalized installer, runner.zip: OK"

echo "== 6. T-8 escrow never served / never read outside the reveal =="
for key in lane_mapping escrow .lane-mapping; do
  CODE=$(curl -s -o /dev/null -w "%{http_code}" "localhost:$PORT/api/runs/$RID/download/$key")
  [ "$CODE" = "404" ] || fail "escrow-ish download key '$key' returned $CODE"
done
REFS=$(cd server && grep -rlE "lane.mapping|ESCROW_NAME" *.py | sort | tr '\n' ' ')
[ "$REFS" = "config.py orchestrator.py storage.py " ] || fail "unexpected escrow references in server/: $REFS"
grep -q "ESCROW_NAME\|lane.mapping" server/prompts.py && fail "packet builder references the escrow"
grep -q "ESCROW_NAME\|lane.mapping" server/packets.py && fail "packet store references the escrow"
grep -n "ESCROW_NAME" server/orchestrator.py | grep -v "lane_reveal_apply\|lane-mapping\", str(rd / ESCROW_NAME)\|from .config" \
  | grep -q "ESCROW_NAME" && fail "orchestrator reads the escrow outside the reveal invocation"
echo "  escrow: unreachable via routes; referenced only by config/download-guard/reveal-arg"

echo "== 7. T-9 no model-SDK imports in server/ =="
# Model SDKs only: google.oauth2 / google.auth are Workspace IDENTITY
# libraries (server/auth.py sign-in verification), not model clients.
BAD=$(grep -rEn "import anthropic|from anthropic|google\.generativeai|import genai|from google\.genai|import vertexai|from vertexai|import openai" server/*.py || true)
[ -z "$BAD" ] || fail "model SDK import found in server/: $BAD"
echo "  server/ holds no Anthropic or Google client"

echo "== 8. T-13 pre-intelligence layer engaged (artifact, packet, digest) =="
RD="$W2APP_DATA/runs/$RID"
[ -f "$RD/pre-analysis-A.json" ] && [ -f "$RD/pre-analysis-B.json" ] \
  || { echo "SMOKE FAIL: pre-analysis artifacts missing"; exit 1; }
PK=$(ls "$RD"/packets/pass*claude-code.packet.json | head -1)
grep -q "PRE-ANALYSIS (deterministic, advisory)" "$PK" \
  || { echo "SMOKE FAIL: pass packet not enriched with pre-analysis"; exit 1; }
W2D="$W2APP_DATA" RID="$RID" python3 -c "
import json, os
st = json.load(open(os.environ['W2D'] + '/runs/' + os.environ['RID'] + '/state.json'))
pa = st['digests'].get('pre_analysis') or {}
assert set(pa) == {'Output A', 'Output B'}, pa
a = pa['Output A']
assert a['criteria'] > 0 and a['evidence_coverage'] > 0, a
assert a['requirements_total'] >= 5 and a['traceability_rate'] > 0, a
pre = json.load(open(os.environ['W2D'] + '/runs/' + os.environ['RID'] + '/pre-analysis-A.json'))
assert pre['preintel_version'] and pre['mechanisms'], 'mechanism index empty'
print('  pre-intel: coverage %.0f%% traceability %.0f%% mechanisms %d' % (
      a['evidence_coverage']*100, a['traceability_rate']*100, len(pre['mechanisms'])))
"

echo "== 9. T-10 legacy five-pass protocol (frozen v4.6 path) =="
LEG_PORT=${LEG_PORT:-8889}
W2APP_DATA_LEG=$(mktemp -d)
( W2APP_DATA="$W2APP_DATA_LEG" EVAL_PROTOCOL=five-pass \
  setsid nohup python3 -m uvicorn server.main:app --port $LEG_PORT --log-level warning \
  > /tmp/uvicorn-legacy.log 2>&1 < /dev/null & )
sleep 2.5
RIDL=$(api -X POST localhost:$LEG_PORT/api/runs -F brd=@$F/brd.md -F sdd_1=@$F/sdd1.md \
      -F sdd_2=@$F/sdd2.md -F zenagent_is=a -F auto_approve_checkpoint=false \
      | python3 -c "import json,sys;print(json.load(sys.stdin)['run_id'])")
python3 runner/w2_runner.py --server http://localhost:$LEG_PORT --engine mock --once --poll 0.3 >/dev/null
api -X POST localhost:$LEG_PORT/api/runs/$RIDL/approve -H 'Content-Type: application/json' \
    -d '{"approve": true}' >/dev/null
python3 runner/w2_runner.py --server http://localhost:$LEG_PORT --engine mock --once --poll 0.3 >/dev/null
api localhost:$LEG_PORT/api/runs/$RIDL | python3 -c "
import json, sys
d = json.load(sys.stdin)
assert d['status'] == 'done', (d['status'], d.get('error'))
assert d.get('protocol') == 'five-pass'
assert 'report' in d['artifacts']
print('  legacy five-pass done - lift ZA-OTS =', d['digests']['reveal']['headline_lift_za_minus_ots'])"
pkill -f "uvicorn server.main:app --port $LEG_PORT" 2>/dev/null || true
rm -rf "$W2APP_DATA_LEG"

else
# ---- EVAL_PROTOCOL=five-pass invocation: run the LEGACY flow end to end ----
echo "== Mode A (five-pass legacy) =="
RID=$(api -X POST localhost:$PORT/api/runs -F brd=@$F/brd.md -F sdd_1=@$F/sdd1.md \
      -F sdd_2=@$F/sdd2.md -F zenagent_is=a -F auto_approve_checkpoint=false \
      | python3 -c "import json,sys;print(json.load(sys.stdin)['run_id'])")
python3 runner/w2_runner.py --server http://localhost:$PORT --engine mock --once --poll 0.3 >/dev/null
api -X POST localhost:$PORT/api/runs/$RID/approve -H 'Content-Type: application/json' \
    -d '{"approve": true}' >/dev/null
python3 runner/w2_runner.py --server http://localhost:$PORT --engine mock --once --poll 0.3 >/dev/null
api localhost:$PORT/api/runs/$RID | python3 -c "
import json,sys; d=json.load(sys.stdin)
assert d['status']=='done', (d['status'], d.get('error'))
assert 'report' in d['artifacts'], d['artifacts']
print('  Mode A done - lift ZA-OTS =', d['digests']['reveal']['headline_lift_za_minus_ots'])"
echo "== Mode B (five-pass legacy) =="
RIDB=$(api -X POST localhost:$PORT/api/runs -F brd=@$F/brd.md -F sdd_1=@$F/sdd1.md \
      | python3 -c "import json,sys;print(json.load(sys.stdin)['run_id'])")
python3 runner/w2_runner.py --server http://localhost:$PORT --engine mock --once --poll 0.3 >/dev/null
api localhost:$PORT/api/runs/$RIDB | python3 -c "
import json,sys; d=json.load(sys.stdin)
assert d['status']=='done', (d['status'], d.get('error'))
assert 'report' in d['artifacts'], d['artifacts']
print('  Mode B done -', json.dumps(d['digests']['review']))"
fi

echo "SMOKE PASS"
