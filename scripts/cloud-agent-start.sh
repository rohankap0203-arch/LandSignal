#!/usr/bin/env bash
# Per-boot Cloud Agent start — LandSignal web (:3000) + API (:8000).
# Stays attached so both processes remain up for the life of the machine.
set -euo pipefail

cd /workspace

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
    fi
  fi
}

wait_http() {
  local url="$1"
  local label="$2"
  local i
  for i in $(seq 1 90); do
    if curl -sf -o /dev/null --max-time 2 "${url}"; then
      echo "[landsignal-start] ${label} ready (${url})"
      return 0
    fi
    sleep 1
  done
  echo "[landsignal-start] ERROR: ${label} failed to become ready at ${url}" >&2
  return 1
}

echo "[landsignal-start] freeing ports 3000/8000"
free_port 3000
free_port 8000
sleep 1

if [[ ! -x apps/api/.venv/bin/uvicorn ]]; then
  echo "[landsignal-start] ERROR: API venv missing — run install first" >&2
  exit 1
fi
if [[ ! -d apps/web/node_modules/next ]]; then
  echo "[landsignal-start] ERROR: web node_modules missing — run install first" >&2
  exit 1
fi

export AUTH_SECRET="${AUTH_SECRET:-landsignal-dev-auth-secret-change-me}"
export AUTH_DEMO_OAUTH="${AUTH_DEMO_OAUTH:-true}"
export AUTH_TRUST_HOST="${AUTH_TRUST_HOST:-true}"
export NEXT_PUBLIC_API_URL="${NEXT_PUBLIC_API_URL:-/v1}"
export LANDSIGNAL_API_ORIGIN="${LANDSIGNAL_API_ORIGIN:-http://127.0.0.1:8000}"

mkdir -p /tmp/landsignal
echo "[landsignal-start] launching API on 0.0.0.0:8000"
(
  cd apps/api
  exec .venv/bin/uvicorn landsignal.main:app --host 0.0.0.0 --port 8000 --reload
) > /tmp/landsignal/api.log 2>&1 &
API_PID=$!

echo "[landsignal-start] launching web on 0.0.0.0:3000"
(
  cd apps/web
  exec npm run dev -- -H 0.0.0.0 -p 3000
) > /tmp/landsignal/web.log 2>&1 &
WEB_PID=$!

cleanup() {
  kill "${API_PID}" "${WEB_PID}" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

wait_http "http://127.0.0.1:8000/docs" "API"
wait_http "http://127.0.0.1:3000/" "web"

echo "[landsignal-start] LandSignal is up — open the forwarded port for 3000 (not a stale preview URL)"
echo "[landsignal-start] API pid=${API_PID} web pid=${WEB_PID} (logs in /tmp/landsignal/)"

# Stay attached so the environment keeps both servers alive.
wait "${API_PID}" "${WEB_PID}"
