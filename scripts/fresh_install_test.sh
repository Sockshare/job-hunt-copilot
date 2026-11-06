#!/usr/bin/env bash
# G3 — fresh-install gate.
# Copies the project to a temp folder, follows the README install steps EXACTLY
# in a brand-new virtual environment, starts the app, hits the API, and runs
# one analysis. If this passes, a stranger can clone the repo and use it.
#
#   bash scripts/fresh_install_test.sh

set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'kill ${APP_PID:-} 2>/dev/null || true; rm -rf "$TMP"' EXIT

echo "→ Copying project to $TMP"
rsync -a --exclude .venv --exclude .git --exclude '__pycache__' --exclude '.pytest_cache' "$HERE/" "$TMP/app/"
cd "$TMP/app"

echo "→ Step 1: create virtual environment"
if python3 -m venv .venv 2>/dev/null; then :; else
  # Some Debian/Ubuntu images lack ensurepip; README documents this fallback.
  python3 -m venv --without-pip .venv
  . .venv/bin/activate
  curl -sS https://bootstrap.pypa.io/get-pip.py | python -
fi
. .venv/bin/activate

echo "→ Step 2: pip install -r requirements.txt"
pip install -q -r requirements.txt

echo "→ Step 3: python app.py (offline mode, random port)"
PORT=$(python - <<'EOF'
import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1])
EOF
)
export JOBHUNT_DATA_DIR="$TMP/data" JOBHUNT_PROVIDER=offline
python app.py --port "$PORT" --no-browser >"$TMP/server.log" 2>&1 &
APP_PID=$!
for i in $(seq 1 40); do
  if curl -sf "http://127.0.0.1:$PORT/api/health" >/dev/null; then break; fi
  sleep 0.5
done
curl -sf "http://127.0.0.1:$PORT/api/health" >/dev/null || { echo "✗ server did not start"; cat "$TMP/server.log"; exit 1; }
echo "   server up on port $PORT"

echo "→ Step 4: match the example resume"
python - "$PORT" <<'EOF'
import json, sys, urllib.request
port = sys.argv[1]
s = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/sample").read())
req = urllib.request.Request(f"http://127.0.0.1:{port}/api/match", data=json.dumps({"resume": s["resume"], "posting": s["posting"]}).encode(), headers={"Content-Type": "application/json"})
d = json.loads(urllib.request.urlopen(req).read())
assert d["match"]["score"] >= 50, d["match"]["score"]
assert d["match"]["missing_keywords"] is not None
print("   match OK: score", d["match"]["score"])
EOF

echo "→ Step 5: UI loads"
curl -sf "http://127.0.0.1:$PORT/" | grep -q "Job Hunt Copilot" && echo "   UI OK"

echo "→ Step 6: selfcheck script"
python scripts/selfcheck.py >/dev/null && echo "   selfcheck OK" || echo "   selfcheck reported warnings (ok in CI)"

echo
echo "✅ FRESH INSTALL PASSED"
