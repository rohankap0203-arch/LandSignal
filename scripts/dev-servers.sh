#!/usr/bin/env bash
# Boot LandSignal so Cursor can auto-forward http://localhost:3000 into the right-side browser.
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

# Bind 0.0.0.0 — Cursor's right-side browser port-forward probes IPv4.
if ! port_up 8000; then
  (
    cd "$ROOT/apps/api"
    nohup python3 -m uvicorn landsignal.main:app --host 0.0.0.0 --port 8000 \
      > /tmp/landsignal-api.log 2>&1 &
  )
fi

if ! port_up 3000; then
  (
    cd "$ROOT/apps/web"
    nohup npm run dev > /tmp/landsignal-web.log 2>&1 &
  )
fi

for i in $(seq 1 60); do
  if port_up 3000 && port_up 8000; then
    echo "Ready — open http://localhost:3000 (Cursor plug → port 3000 → Open in Browser)"
    exit 0
  fi
  sleep 1
done
echo "Timed out waiting for LandSignal servers" >&2
exit 1
