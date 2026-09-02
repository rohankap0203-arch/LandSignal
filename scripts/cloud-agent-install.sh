#!/usr/bin/env bash
# Idempotent Cloud Agent install — deps only (no long-running servers).
set -euo pipefail

cd /workspace

echo "[landsignal-install] ensuring Python venv tooling"
if ! python3 -c "import ensurepip" 2>/dev/null; then
  if command -v sudo >/dev/null 2>&1; then
    sudo apt-get update -qq
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3.12-venv python3-pip
  else
    apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3.12-venv python3-pip
  fi
fi

echo "[landsignal-install] web dependencies"
npm --prefix apps/web install --no-fund --no-audit

echo "[landsignal-install] API virtualenv + package"
if [[ ! -x apps/api/.venv/bin/python ]]; then
  python3 -m venv apps/api/.venv
fi
apps/api/.venv/bin/pip install -U pip -q
apps/api/.venv/bin/pip install -e "apps/api[dev]" -q

echo "[landsignal-install] done"
