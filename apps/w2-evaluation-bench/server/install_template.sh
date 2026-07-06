#!/bin/bash
# W2 Evaluation Bench — per-member runner installer (TR-30).
# Served personalized by GET /install.sh: __W2_SERVER__ is templated in by the
# bench; the member token comes from ?token=… (templated) or --token (safer:
# never appears in a URL or request log — see docs/errata.md E-2).
#
#   curl -fsSL https://<bench>/install.sh | bash -s -- --token <YOUR-TOKEN>
#
# Idempotent: safe to re-run on upgrades or a new laptop (doc 07).
# Flags for CI / manual control: --no-login --no-service --engine <panel|mock>
set -euo pipefail

W2_SERVER="__W2_SERVER__"
W2_TOKEN="__W2_TOKEN__"
ENGINE="panel"
DO_LOGIN=1
DO_SERVICE=1
while [ $# -gt 0 ]; do
  case "$1" in
    --token) W2_TOKEN="$2"; shift 2;;
    --engine) ENGINE="$2"; shift 2;;
    --no-login) DO_LOGIN=0; shift;;
    --no-service) DO_SERVICE=0; shift;;
    *) echo "unknown flag: $1" >&2; exit 2;;
  esac
done
# (glob, not the literal sentinel: the server's templating replaces every
# exact sentinel occurrence, so the guard must not contain one)
case "$W2_TOKEN" in ""|__W2_*)
  echo "ERROR: no bench token. Re-run with:  ... | bash -s -- --token <YOUR-TOKEN>" >&2
  exit 2;;
esac

W2_HOME="$HOME/.w2"
step(){ printf '\n[install] %s\n' "$*"; }

step "1/6 python3 + workspace"
command -v python3 >/dev/null || { echo "python3 (3.10+) is required"; exit 3; }
mkdir -p "$W2_HOME"

step "2/6 runner files -> $W2_HOME/runner"
TMPZ="$(mktemp)"
curl -fsSL -H "X-W2-Token: $W2_TOKEN" "$W2_SERVER/runner.zip" -o "$TMPZ"
rm -rf "$W2_HOME/runner"
python3 - "$TMPZ" "$W2_HOME" <<'PY'
import sys, zipfile
with zipfile.ZipFile(sys.argv[1]) as z:
    z.extractall(sys.argv[2])
PY
rm -f "$TMPZ"

step "3/6 Claude Code CLI"
if ! command -v claude >/dev/null; then
  command -v npm >/dev/null || { echo "npm is required to install Claude Code (https://nodejs.org)"; exit 3; }
  npm install -g @anthropic-ai/claude-code
fi
if [ "$DO_LOGIN" = 1 ]; then
  # Your browser opens Anthropic's own login — sign in with your Team seat.
  # The credential is minted and stored on THIS machine only; it never
  # transits the bench (PRD D14). Skip with --no-login if already logged in.
  if ! claude -p "Reply with exactly: OK" --output-format json >/dev/null 2>&1; then
    echo "[install] opening Anthropic's login for your Team seat (claude setup-token)…"
    claude setup-token || true
  else
    echo "[install] existing Claude subscription login detected — keeping it."
  fi
fi

step "4/6 ~/.w2/env (permissions locked to you)"
ENVF="$W2_HOME/env"
if [ ! -f "$ENVF" ]; then
  cat > "$ENVF" <<EOF
W2_SERVER=$W2_SERVER
W2APP_TOKEN=$W2_TOKEN
W2_ENGINE=$ENGINE
# Org Gemini key (administrator provides; paid tier — set both lines):
#GEMINI_API_KEY=
#W2_GEMINI_TIER=paid
EOF
else
  echo "[install] $ENVF exists — keeping it (edit it to rotate tokens/keys)."
fi
chmod 600 "$ENVF"

step "5/6 background service (starts on login)"
if [ "$DO_SERVICE" = 1 ]; then
  case "$(uname -s)" in
    Darwin)
      PLIST="$HOME/Library/LaunchAgents/com.zennify.w2runner.plist"
      mkdir -p "$(dirname "$PLIST")"
      sed -e "s|__W2_HOME__|$W2_HOME|g" -e "s|__PYTHON__|$(command -v python3)|g" \
          "$W2_HOME/runner/examples/com.zennify.w2runner.plist" > "$PLIST"
      launchctl unload "$PLIST" 2>/dev/null || true
      launchctl load "$PLIST"
      echo "[install] launchd agent loaded: $PLIST" ;;
    Linux)
      UNIT="$HOME/.config/systemd/user/w2-runner.service"
      mkdir -p "$(dirname "$UNIT")"
      sed -e "s|__W2_HOME__|$W2_HOME|g" -e "s|__PYTHON__|$(command -v python3)|g" \
          "$W2_HOME/runner/examples/w2-runner.user.service" > "$UNIT"
      systemctl --user daemon-reload
      systemctl --user enable --now w2-runner
      echo "[install] systemd --user service enabled: w2-runner" ;;
    *) echo "[install] unknown OS — start manually: python3 $W2_HOME/runner/w2_runner.py" ;;
  esac
else
  echo "[install] --no-service: start manually with"
  echo "          set -a; . $ENVF; set +a; python3 $W2_HOME/runner/w2_runner.py"
fi

step "6/6 self-check"
set +e
set -a; . "$ENVF"; set +a
python3 "$W2_HOME/runner/w2_runner.py" --selfcheck --server "$W2_SERVER" --token "$W2_TOKEN"
RC=$?
if [ "$DO_SERVICE" = 1 ]; then
  case "$(uname -s)" in
    Darwin) launchctl list 2>/dev/null | grep -q com.zennify.w2runner \
      && echo "[selfcheck] runner service ........ RUNNING" \
      || echo "[selfcheck] runner service ........ NOT RUNNING (launchctl list)";;
    Linux) systemctl --user is-active --quiet w2-runner 2>/dev/null \
      && echo "[selfcheck] runner service ........ RUNNING" \
      || echo "[selfcheck] runner service ........ NOT RUNNING (systemctl --user status w2-runner)";;
  esac
fi
set -e
if [ $RC -eq 0 ]; then
  echo
  echo "[install] DONE — open the bench: $W2_SERVER  (header should show your runner connected)"
else
  echo
  echo "[install] Self-check reported problems above (installer completed; fix and re-run"
  echo "          python3 $W2_HOME/runner/w2_runner.py --selfcheck). Common fixes: doc 07 troubleshooting."
fi
exit $RC
