#!/usr/bin/env bash
# Boot LandSignal so Cursor can auto-forward http://localhost:3000 into the right-side browser.
# Idempotent: safe to re-run after environment resets.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

export AUTO_DISCOVER_ON_STARTUP="${AUTO_DISCOVER_ON_STARTUP:-false}"
export LAND_ALERTS_MONITOR_ENABLED="${LAND_ALERTS_MONITOR_ENABLED:-false}"

port_up() {
  python3 - "$1" <<'PY'
import socket, sys
port = int(sys.argv[1])
try:
    s = socket.create_connection(("127.0.0.1", port), 0.5)
    s.close()
    raise SystemExit(0)
except OSError:
    raise SystemExit(1)
PY
}

ensure_api_venv() {
  local api="$ROOT/apps/api"
  if [[ ! -x "$api/.venv/bin/uvicorn" ]]; then
    python3 -m venv "$api/.venv"
    "$api/.venv/bin/pip" install -U pip -q
    "$api/.venv/bin/pip" install -e "$api[dev]" -q
  fi
}

ensure_web_modules() {
  local web="$ROOT/apps/web"
  if [[ ! -x "$web/node_modules/.bin/next" ]]; then
    (cd "$web" && npm install --no-fund --no-audit)
  fi
}

# Bind 0.0.0.0 — Cursor's right-side browser port-forward probes IPv4.
ensure_api_venv
ensure_web_modules

if ! port_up 8000; then
  (
    cd "$ROOT/apps/api"
    # Load gitignored secrets if present (never commit apps/api/.env)
    set -a
    # shellcheck disable=SC1091
    [[ -f .env ]] && source .env
    set +a
    nohup .venv/bin/uvicorn landsignal.main:app --host 0.0.0.0 --port 8000 \
      > /tmp/landsignal-api.log 2>&1 &
  )
fi

if ! port_up 3000; then
  (
    cd "$ROOT/apps/web"
    nohup npm run dev -- -H 0.0.0.0 -p 3000 > /tmp/landsignal-web.log 2>&1 &
  )
fi

for i in $(seq 1 90); do
  if port_up 3000 && port_up 8000; then
    # Kick a background inventory fill if empty (best-effort).
    (
      sleep 2
      count="$(curl -s -m 3 http://127.0.0.1:8000/v1/search/meta 2>/dev/null \
        | python3 -c 'import sys,json; print(json.load(sys.stdin).get("inventory_count") or 0)' 2>/dev/null || echo 0)"
      if [[ "${count:-0}" -lt 100 ]]; then
        curl -s -m 5 -X POST \
          'http://127.0.0.1:8000/v1/discover?limit=250000&background=true&fast=true' \
          >/tmp/landsignal-discover.json 2>/dev/null || true
      fi
    ) &
    echo "Ready — open http://localhost:3000 (Cursor plug → port 3000 → Open in Browser)"
    exit 0
  fi
  sleep 1
done

echo "Timed out waiting for LandSignal servers" >&2
echo "--- api log ---" >&2
tail -40 /tmp/landsignal-api.log 2>/dev/null >&2 || true
echo "--- web log ---" >&2
tail -40 /tmp/landsignal-web.log 2>/dev/null >&2 || true
exit 1
