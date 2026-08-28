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
    if ! python3 -m venv --help >/dev/null 2>&1 || ! python3 -c "import ensurepip" 2>/dev/null; then
      sudo apt-get update -qq >/dev/null 2>&1 || true
      sudo apt-get install -y -qq python3.12-venv python3-venv >/dev/null 2>&1 || true
    fi
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

# Optional alias port used by some Cursor preview bookmarks.
if port_up 3000 && ! port_up 51866; then
  (
    nohup python3 -u - <<'PY' > /tmp/landsignal-51866-proxy.log 2>&1 &
import socket, threading, select
LISTEN, TARGET = 51866, ("127.0.0.1", 3000)
def pipe(a, b):
    try:
        while True:
            r, _, _ = select.select([a], [], [], 120)
            if not r:
                break
            d = a.recv(65536)
            if not d:
                break
            b.sendall(d)
    except Exception:
        pass
    finally:
        for s in (a, b):
            try:
                s.close()
            except Exception:
                pass
srv = socket.socket()
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(("0.0.0.0", LISTEN))
srv.listen(100)
print(f"proxy {LISTEN} -> {TARGET[0]}:{TARGET[1]}", flush=True)
while True:
    c, _ = srv.accept()
    t = socket.socket()
    try:
        t.connect(TARGET)
    except Exception:
        c.close()
        continue
    threading.Thread(target=pipe, args=(c, t), daemon=True).start()
    threading.Thread(target=pipe, args=(t, c), daemon=True).start()
PY
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
          'http://127.0.0.1:8000/v1/discover?limit=80000&background=true&fast=true' \
          >/tmp/landsignal-discover.json 2>/dev/null || true
      fi
    ) &
    echo "Ready — open http://localhost:3000 (or http://localhost:51866 alias)"
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
