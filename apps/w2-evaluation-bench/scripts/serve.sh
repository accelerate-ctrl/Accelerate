#!/bin/bash
cd "$(dirname "$0")/.."
pkill -f 'uvicorn serv[e]r.main' 2>/dev/null
sleep 1
setsid nohup python3 -m uvicorn server.main:app --port "${1:-8787}" --log-level warning \
  > /tmp/uvicorn.log 2>&1 < /dev/null &
sleep 2
curl -s -m 3 "http://localhost:${1:-8787}/api/runs" > /dev/null && echo "server up on :${1:-8787}"
