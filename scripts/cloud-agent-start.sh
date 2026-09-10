#!/usr/bin/env bash
# Per-boot Cloud Agent supervisor — keeps LandSignal web (:3000) + API (:8000) up.
# - Binds 0.0.0.0 (required for Cursor port-forward / plug icon)
# - Does not kill healthy servers (consecutive failures + /v1/health)
# - Auto-restarts if a process dies
# - Mirrors IDE plug port 51866 → 3000 when needed
# - Stays attached for the life of the machine
set -euo pipefail

cd /workspace
mkdir -p /tmp/landsignal

export AUTH_SECRET="${AUTH_SECRET:-landsignal-dev-auth-secret-change-me}"
export AUTH_DEMO_OAUTH="${AUTH_DEMO_OAUTH:-true}"
export AUTH_TRUST_HOST="${AUTH_TRUST_HOST:-true}"
export NEXT_PUBLIC_API_URL="${NEXT_PUBLIC_API_URL:-/v1}"
export LANDSIGNAL_API_ORIGIN="${LANDSIGNAL_API_ORIGIN:-http://127.0.0.1:8000}"
# Index live public inventory on boot so Show matches is never empty on cold start.
export AUTO_DISCOVER_ON_STARTUP="${AUTO_DISCOVER_ON_STARTUP:-true}"
export LAND_ALERTS_MONITOR_ENABLED="${LAND_ALERTS_MONITOR_ENABLED:-false}"

API_PID=""
WEB_PID=""
PROXY_PID=""
API_FAILS=0
WEB_FAILS=0

http_ok() {
  local url="$1"
  local timeout="${2:-8}"
  curl -sf -o /dev/null --max-time "${timeout}" "${url}" 2>/dev/null
}

port_listening() {
  python3 - "$1" <<'PY'
import socket, sys
port = int(sys.argv[1])
try:
    s = socket.create_connection(("127.0.0.1", port), 0.4)
    s.close()
    raise SystemExit(0)
except OSError:
    raise SystemExit(1)
PY
}

free_port() {
  local port="$1"
  if command -v fuser >/dev/null 2>&1; then
    fuser -k "${port}/tcp" >/dev/null 2>&1 || true
  fi
  if command -v lsof >/dev/null 2>&1; then
    local pids
    pids="$(lsof -t -iTCP:"${port}" -sTCP:LISTEN 2>/dev/null || true)"
    if [[ -n "${pids}" ]]; then
      # shellcheck disable=SC2086
      kill ${pids} >/dev/null 2>&1 || true
      sleep 0.5
      # shellcheck disable=SC2086
      kill -9 ${pids} >/dev/null 2>&1 || true
    fi
  fi
}

ensure_deps() {
  if [[ ! -x apps/api/.venv/bin/uvicorn ]] || [[ ! -d apps/web/node_modules/next ]]; then
    echo "[landsignal-start] deps missing — running install"
    bash scripts/cloud-agent-install.sh
  fi
}

ensure_plug_proxy() {
  # IDE often probes :51866 while Next listens on :3000.
  if http_ok "http://127.0.0.1:51866/" 3; then
    return 0
  fi
  if command -v socat >/dev/null 2>&1; then
    echo "[landsignal-start] mirroring :51866 → :3000 via socat"
    socat TCP-LISTEN:51866,bind=0.0.0.0,fork,reuseaddr TCP:127.0.0.1:3000 \
      >> /tmp/landsignal/plug-proxy.log 2>&1 &
    PROXY_PID=$!
  else
    echo "[landsignal-start] mirroring :51866 → :3000 via python plug proxy"
    python3 scripts/plug-port-proxy.py >> /tmp/landsignal/plug-proxy.log 2>&1 &
    PROXY_PID=$!
  fi
  echo "${PROXY_PID}" > /tmp/landsignal/plug-proxy.pid
}

start_api() {
  # Prefer lightweight health — /docs can stall under heavy discover.
  if http_ok "http://127.0.0.1:8000/v1/health" 8 || http_ok "http://127.0.0.1:8000/docs" 8; then
    echo "[landsignal-start] API already healthy on :8000"
    return 0
  fi
  if port_listening 8000; then
    echo "[landsignal-start] :8000 occupied but unhealthy — reclaiming"
    free_port 8000
    sleep 1
  fi
  echo "[landsignal-start] launching API on 0.0.0.0:8000"
  (
    cd apps/api
    exec .venv/bin/uvicorn landsignal.main:app --host 0.0.0.0 --port 8000
  ) >> /tmp/landsignal/api.log 2>&1 &
  API_PID=$!
  echo "${API_PID}" > /tmp/landsignal/api.pid
}

start_web() {
  if http_ok "http://127.0.0.1:3000/" 8; then
    echo "[landsignal-start] web already healthy on :3000"
    return 0
  fi
  if port_listening 3000; then
    echo "[landsignal-start] :3000 occupied but unhealthy — reclaiming"
    free_port 3000
    sleep 1
  fi
  echo "[landsignal-start] launching web on 0.0.0.0:3000"
  (
    cd apps/web
    exec npx --no-install next dev -H 0.0.0.0 -p 3000
  ) >> /tmp/landsignal/web.log 2>&1 &
  WEB_PID=$!
  echo "${WEB_PID}" > /tmp/landsignal/web.pid
}

wait_ready() {
  local url="$1"
  local label="$2"
  local i
  for i in $(seq 1 120); do
    if http_ok "${url}" 8; then
      echo "[landsignal-start] ${label} ready (${url})"
      return 0
    fi
    sleep 1
  done
  echo "[landsignal-start] ERROR: ${label} failed to become ready at ${url}" >&2
  echo "[landsignal-start] --- ${label} log (tail) ---" >&2
  if [[ "${label}" == "API" ]]; then
    tail -n 40 /tmp/landsignal/api.log >&2 || true
  else
    tail -n 40 /tmp/landsignal/web.log >&2 || true
  fi
  return 1
}

alive() {
  local pid="$1"
  [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null
}

cleanup() {
  # Only kill processes we started in this supervisor.
  if alive "${API_PID:-}"; then kill "${API_PID}" >/dev/null 2>&1 || true; fi
  if alive "${WEB_PID:-}"; then kill "${WEB_PID}" >/dev/null 2>&1 || true; fi
  if alive "${PROXY_PID:-}"; then kill "${PROXY_PID}" >/dev/null 2>&1 || true; fi
}
trap cleanup EXIT INT TERM

ensure_deps
start_api
start_web
wait_ready "http://127.0.0.1:8000/v1/health" "API" || wait_ready "http://127.0.0.1:8000/docs" "API"
wait_ready "http://127.0.0.1:3000/" "web"
ensure_plug_proxy

echo "[landsignal-start] READY — Cursor plug → port 3000 (or 51866 mirror)"
echo "[landsignal-start] API also on port 8000; logs in /tmp/landsignal/"

# Self-heal loop: require consecutive failures so discover CPU spikes don't wipe memory inventory.
while true; do
  if http_ok "http://127.0.0.1:8000/v1/health" 8 || http_ok "http://127.0.0.1:8000/docs" 8; then
    API_FAILS=0
  else
    API_FAILS=$((API_FAILS + 1))
    echo "[landsignal-start] API health miss (${API_FAILS}/3)"
    if [[ "${API_FAILS}" -ge 3 ]]; then
      echo "[landsignal-start] API unhealthy — restarting"
      free_port 8000
      sleep 1
      API_PID=""
      API_FAILS=0
      start_api
      wait_ready "http://127.0.0.1:8000/v1/health" "API" || wait_ready "http://127.0.0.1:8000/docs" "API" || true
    fi
  fi

  if http_ok "http://127.0.0.1:3000/" 8; then
    WEB_FAILS=0
  else
    WEB_FAILS=$((WEB_FAILS + 1))
    echo "[landsignal-start] web health miss (${WEB_FAILS}/3)"
    if [[ "${WEB_FAILS}" -ge 3 ]]; then
      echo "[landsignal-start] web unhealthy — restarting"
      free_port 3000
      sleep 1
      WEB_PID=""
      WEB_FAILS=0
      start_web
      wait_ready "http://127.0.0.1:3000/" "web" || true
    fi
  fi

  if ! http_ok "http://127.0.0.1:51866/" 3; then
    ensure_plug_proxy
  fi

  sleep 8
done
