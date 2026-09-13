#!/usr/bin/env bash
# Ensure LandSignal is up and print a clickable HTTPS preview URL.
# Used when the user says: "send me my link"
set -euo pipefail
cd /workspace
mkdir -p /tmp/landsignal

http_ok() { curl -sf -o /dev/null --max-time 2 "$1" 2>/dev/null; }

ensure_app() {
  if http_ok "http://127.0.0.1:3000/" && http_ok "http://127.0.0.1:8000/docs"; then
    return 0
  fi
  if [[ ! -x scripts/cloud-agent-start.sh ]]; then
    echo "Missing scripts/cloud-agent-start.sh" >&2
    exit 1
  fi
  if command -v tmux >/dev/null 2>&1; then
    conf="/exec-daemon/tmux.portal.conf"
    tmux_cmd=(tmux)
    [[ -f "$conf" ]] && tmux_cmd=(tmux -f "$conf")
    "${tmux_cmd[@]}" has-session -t "=landsignal-boot" 2>/dev/null || \
      "${tmux_cmd[@]}" new-session -d -s "landsignal-boot" -c "/workspace" -- bash -l
    "${tmux_cmd[@]}" send-keys -t "landsignal-boot:0.0" 'bash /workspace/scripts/cloud-agent-start.sh' C-m
  else
    bash scripts/cloud-agent-start.sh >>/tmp/landsignal/start.log 2>&1 &
  fi
  for _ in $(seq 1 90); do
    if http_ok "http://127.0.0.1:3000/" && http_ok "http://127.0.0.1:8000/docs"; then
      return 0
    fi
    sleep 1
  done
  echo "ERROR: web/API not ready" >&2
  exit 1
}

ensure_cloudflared() {
  if [[ -x /tmp/cloudflared ]]; then
    echo /tmp/cloudflared
    return
  fi
  if command -v cloudflared >/dev/null 2>&1; then
    command -v cloudflared
    return
  fi
  curl -sL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 \
    -o /tmp/cloudflared
  chmod +x /tmp/cloudflared
  echo /tmp/cloudflared
}

existing_tunnel_url() {
  rg -o 'https://[a-zA-Z0-9.-]+\.trycloudflare\.com' /tmp/landsignal/tunnel.log 2>/dev/null | tail -1 || true
}

ensure_tunnel() {
  local url bin
  url="$(existing_tunnel_url)"
  if [[ -n "$url" ]] && curl -sf -o /dev/null --max-time 15 "$url/" 2>/dev/null; then
    echo "$url"
    return
  fi

  bin="$(ensure_cloudflared)"
  pkill -f 'cloudflared tunnel --url http://127.0.0.1:3000' 2>/dev/null || true
  rm -f /tmp/landsignal/tunnel.log
  touch /tmp/landsignal/tunnel.log

  if command -v tmux >/dev/null 2>&1; then
    conf="/exec-daemon/tmux.portal.conf"
    tmux_cmd=(tmux)
    [[ -f "$conf" ]] && tmux_cmd=(tmux -f "$conf")
    "${tmux_cmd[@]}" has-session -t "=landsignal-tunnel" 2>/dev/null && \
      "${tmux_cmd[@]}" kill-session -t "landsignal-tunnel" || true
    "${tmux_cmd[@]}" new-session -d -s "landsignal-tunnel" -c "/workspace" -- bash -l
    sleep 0.5
    "${tmux_cmd[@]}" send-keys -t "landsignal-tunnel:0.0" \
      "${bin} tunnel --url http://127.0.0.1:3000 --no-autoupdate 2>&1 | tee /tmp/landsignal/tunnel.log" C-m
  else
    "${bin}" tunnel --url http://127.0.0.1:3000 --no-autoupdate \
      > /tmp/landsignal/tunnel.log 2>&1 &
  fi

  for _ in $(seq 1 60); do
    url="$(existing_tunnel_url)"
    if [[ -n "$url" ]]; then
      for __ in $(seq 1 20); do
        if curl -sf -o /dev/null --max-time 15 "$url/" 2>/dev/null; then
          echo "$url"
          return
        fi
        sleep 1
      done
      echo "$url"
      return
    fi
    sleep 1
  done
  echo "ERROR: could not create public tunnel" >&2
  tail -n 30 /tmp/landsignal/tunnel.log >&2 || true
  exit 1
}

ensure_app
ensure_tunnel
