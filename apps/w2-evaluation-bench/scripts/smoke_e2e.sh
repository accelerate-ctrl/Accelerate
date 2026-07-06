#!/bin/bash
# End-to-end smoke: both modes, mock engine, fresh data dir. Exits nonzero on failure.
set -e
cd "$(dirname "$0")/.."
export W2APP_DATA=$(mktemp -d)
PORT=${PORT:-8899}
bash scripts/serve.sh $PORT >/dev/null
trap 'pkill -f "uvicorn serv[e]r.main" 2>/dev/null' EXIT
F=${FIXTURES:-tests/fixtures}
api() { curl -s "$@"; }

echo "== Mode A =="
RID=$(api -X POST localhost:$PORT/api/runs -F brd=@$F/brd.md -F sdd_1=@$F/sdd1.md \
      -F sdd_2=@$F/sdd2.md -F zenagent_is=a | python3 -c "import json,sys;print(json.load(sys.stdin)['run_id'])")
python3 runner/w2_runner.py --server http://localhost:$PORT --engine mock --once --poll 0.3 >/dev/null
api -X POST localhost:$PORT/api/runs/$RID/approve -H 'Content-Type: application/json' \
    -d '{"approve": true}' >/dev/null
python3 runner/w2_runner.py --server http://localhost:$PORT --engine mock --once --poll 0.3 >/dev/null
api localhost:$PORT/api/runs/$RID | python3 -c "
import json,sys; d=json.load(sys.stdin)
assert d['status']=='done', d
assert 'report' in d['artifacts'], d['artifacts']
print('  Mode A done — lift ZA-OTS =', d['digests']['reveal']['headline_lift_za_minus_ots'])"

echo "== Mode B =="
RID=$(api -X POST localhost:$PORT/api/runs -F brd=@$F/brd.md -F sdd_1=@$F/sdd1.md \
      | python3 -c "import json,sys;print(json.load(sys.stdin)['run_id'])")
python3 runner/w2_runner.py --server http://localhost:$PORT --engine mock --once --poll 0.3 >/dev/null
api localhost:$PORT/api/runs/$RID | python3 -c "
import json,sys; d=json.load(sys.stdin)
assert d['status']=='done', d
assert 'report' in d['artifacts'], d['artifacts']
print('  Mode B done —', json.dumps(d['digests']['review']))"
echo "SMOKE PASS"
