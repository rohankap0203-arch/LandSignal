#!/usr/bin/env bash
# Ensure LandSignal is up and print the clickable preview URL.
# Used when the user says: "send me my link"
set -euo pipefail
cd /workspace

if [[ ! -x scripts/cloud-agent-start.sh ]]; then
  echo "Missing scripts/cloud-agent-start.sh" >&2
  exit 1
fi

http_ok() { curl -sf -o /dev/null --max-time 2 "$1" 2>/dev/null; }

if ! http_ok "http://127.0.0.1:3000/" || ! http_ok "http://127.0.0.1:8000/docs"; then
  # Start supervisor in background tmux if not already healthy
  if command -v tmux >/dev/null 2>&1; then
    conf="/exec-daemon/tmux.portal.conf"
    [[ -f "$conf" ]] || conf=""
    tmux_cmd=(tmux)
    [[ -n "$conf" ]] && tmux_cmd=(tmux -f "$conf")
    "${tmux_cmd[@]}" has-session -t "=landsignal-boot" 2>/dev/null || \
      "${tmux_cmd[@]}" new-session -d -s "landsignal-boot" -c "/workspace" -- bash -l
    "${tmux_cmd[@]}" send-keys -t "landsignal-boot:0.0" 'bash /workspace/scripts/cloud-agent-start.sh' C-m
  else
    bash scripts/cloud-agent-start.sh >/tmp/landsignal/start-foreground.log 2>&1 &
  fi
  for i in $(seq 1 90); do
    if http_ok "http://127.0.0.1:3000/" && http_ok "http://127.0.0.1:8000/docs"; then
      break
    fi
    sleep 1
  done
fi

if ! http_ok "http://127.0.0.1:3000/"; then
  echo "ERROR: web not ready on :3000" >&2
  exit 1
fi

# Preferred Cursor mapping is remote:P -> local:P (forum guidance).
# Random locals like :51866 are stale fallbacks — do not recommend them.
echo "http://127.0.0.1:3000/"
