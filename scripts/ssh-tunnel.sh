#!/usr/bin/env bash
# Set up SSH tunnel to bypass Colima gvproxy WebSocket bug.
#
# Colima's gvproxy port forwarding drops WebSocket frames sent after
# outbound API calls (e.g., Gemini). SSH tunneling bypasses gvproxy
# and provides reliable WebSocket connectivity.
#
# Usage:
#   scripts/ssh-tunnel.sh            # start the tunnel
#   scripts/ssh-tunnel.sh --stop     # stop the tunnel
#   scripts/ssh-tunnel.sh --status   # check if tunnel is running

set -euo pipefail

TUNNEL_PORT="${TUNNEL_PORT:-8000}"
ACTION="${1:-start}"

RED=$'\033[0;31m'; GREEN=$'\033[0;32m'; YELLOW=$'\033[1;33m'
BLUE=$'\033[0;34m'; NC=$'\033[0m'

log()     { printf '%s[%s]%s %s\n' "$BLUE" "$(date +'%H:%M:%S')" "$NC" "$*"; }
success() { printf '%s[ok]%s  %s\n' "$GREEN" "$NC" "$*"; }
warn()    { printf '%s[warn]%s %s\n' "$YELLOW" "$NC" "$*" >&2; }
err()     { printf '%s[err]%s  %s\n' "$RED" "$NC" "$*" >&2; }

# --- Paths ---
COLIMA_DIR="${HOME}/.colima/_lima/colima"
IDENTITY_FILE="${HOME}/.colima/_lima/_config/user"
CONTROL_PATH="${COLIMA_DIR}/ssh.sock"

# --- Helpers ---

get_ssh_port() {
  grep -o '"sshLocalPort":[0-9]*' "${COLIMA_DIR}/ha.stdout.log" 2>/dev/null \
    | tail -1 | cut -d: -f2
}

get_app_ip() {
  docker inspect librarian-app-1 \
    --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' 2>/dev/null
}

tunnel_running() {
  ssh -S "$CONTROL_PATH" -O check 127.0.0.1 2>/dev/null
}

port_forward_exists() {
  ssh -S "$CONTROL_PATH" -O forward 127.0.0.1 2>&1 | grep -q "localhost:${TUNNEL_PORT}"
}

# --- Status ---

if [[ "$ACTION" == "--status" ]]; then
  if tunnel_running; then
    success "SSH tunnel control master is active"
    exit 0
  else
    warn "SSH tunnel control master is NOT active"
    exit 1
  fi
fi

# --- Stop ---

if [[ "$ACTION" == "--stop" ]]; then
  if tunnel_running; then
    ssh -S "$CONTROL_PATH" -O exit 127.0.0.1 2>/dev/null
    success "SSH tunnel stopped"
  else
    warn "SSH tunnel was not running"
  fi
  exit 0
fi

# --- Start ---

if [[ "$ACTION" != "start" ]]; then
  err "unknown action: $ACTION (use start, --stop, or --status)"
  exit 2
fi

# Already running with correct port forward?
if tunnel_running && port_forward_exists; then
  warn "SSH tunnel control master already active with port ${TUNNEL_PORT}"
  exit 0
fi

SSH_PORT=$(get_ssh_port)
if [[ -z "$SSH_PORT" ]]; then
  err "could not determine Colima SSH port"
  exit 3
fi

APP_IP=$(get_app_ip)
if [[ -z "$APP_IP" ]]; then
  err "could not determine app container IP"
  exit 4
fi

log "Setting up SSH tunnel: 0.0.0.0:${TUNNEL_PORT} -> ${APP_IP}:8000 (via Colima VM:${SSH_PORT})"

ssh -F /dev/null \
  -o IdentityFile="$IDENTITY_FILE" \
  -o StrictHostKeyChecking=no \
  -o UserKnownHostsFile=/dev/null \
  -o NoHostAuthenticationForLocalhost=yes \
  -o GSSAPIAuthentication=no \
  -o PreferredAuthentications=publickey \
  -o Compression=no \
  -o BatchMode=yes \
  -o IdentitiesOnly=yes \
  -o User=jeujaiwu \
  -o ControlMaster=auto \
  -o ControlPath="$CONTROL_PATH" \
  -o ControlPersist=yes \
  -L "${TUNNEL_PORT}:${APP_IP}:8000" \
  -N -f \
  -p "$SSH_PORT" \
  127.0.0.1

success "SSH tunnel active: localhost:${TUNNEL_PORT} -> app:8000"
