#!/usr/bin/env bash
# Boot LandSignal web + API so Cursor can auto-forward localhost:3000.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Dual-stack (::) so http://localhost:3000 works when localhost resolves to ::1.
export AUTO_DISCOVER_ON_STARTUP="${AUTO_DISCOVER_ON_STARTUP:-false}"
export LAND_ALERTS_MONITOR_ENABLED="${LAND_ALERTS_MONITOR_ENABLED:-false}"

# Idempotent: skip if already listening on 3000 / 8000.
port_up() {
  local p="$1"
  python3 - "$p" <<'PY'
import socket, sys
port = int(sys.argv[1])
ok = False
for family, host in ((socket.AF_INET6, "::1"), (socket.AF_INET, "127.0.0.1")):
    try:
        s = socket.create_connection((host, port), 0.4)
        s.close()
        ok = True
        break
    except OSError:
        pass
sys.exit(0 if ok else 1)
PY
}

if ! port_up 8000; then
  (
    cd "$ROOT/apps/api"
    nohup python3 -m uvicorn landsignal.main:app --host :: --port 8000 \
      > /tmp/landsignal-api.log 2>&1 &
  )
fi

if ! port_up 3000; then
  (
    cd "$ROOT/apps/web"
    nohup npm run dev > /tmp/landsignal-web.log 2>&1 &
  )
fi

# Wait until web answers on localhost (IPv4 or IPv6).
for i in $(seq 1 60); do
  if port_up 3000 && port_up 8000; then
    echo "LandSignal ready: http://localhost:3000  (API :8000)"
    exit 0
  fi
  sleep 1
done

echo "Timed out waiting for LandSignal servers" >&2
exit 1
