#!/usr/bin/env bash
# Start Librarian data services in dependency-correct order.
#
# etcd and minio MUST be healthy before Milvus starts.
# Postgres, Neo4j, and Redis are independent and can start in any order.
#
# Usage:
#   scripts/start-databases.sh
#   scripts/start-databases.sh --dry-run      # print plan, do nothing
#   scripts/start-databases.sh --help

set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
PROJECT="${PROJECT:-librarian}"

# Start order: dependencies first, milvus last (needs etcd + minio healthy).
SERVICES_START_ORDER=(
  etcd
  minio
  postgres
  neo4j
  redis
  milvus
)

DRY_RUN=0

# --- Helpers ---------------------------------------------------------------

RED=$'\033[0;31m'; GREEN=$'\033[0;32m'; YELLOW=$'\033[1;33m'
BLUE=$'\033[0;34m'; NC=$'\033[0m'

log()     { printf '%s[%s]%s %s\n' "$BLUE" "$(date +'%H:%M:%S')" "$NC" "$*"; }
success() { printf '%s[ok]%s  %s\n' "$GREEN" "$NC" "$*"; }
warn()    { printf '%s[warn]%s %s\n' "$YELLOW" "$NC" "$*" >&2; }
err()     { printf '%s[err]%s  %s\n' "$RED" "$NC" "$*" >&2; }

usage() {
  sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'
  exit 0
}

require_tool() {
  command -v "$1" >/dev/null 2>&1 || { err "required tool not found: $1"; exit 2; }
}

# --- Parse args ------------------------------------------------------------

for arg in "$@"; do
  case "$arg" in
    --dry-run)  DRY_RUN=1 ;;
    -h|--help)  usage ;;
    *)          err "unknown arg: $arg"; exit 2 ;;
  esac
done

# --- Preflight -------------------------------------------------------------

require_tool docker

if ! docker compose version >/dev/null 2>&1; then
  err "docker compose plugin is required"
  exit 2
fi

log "start plan:"
log "  compose file:  ${COMPOSE_FILE}"
log "  start order:   ${SERVICES_START_ORDER[*]}"

if [[ $DRY_RUN -eq 1 ]]; then
  success "dry-run: nothing started"
  exit 0
fi

# --- Identify stopped services ---------------------------------------------

running_set="$(docker compose -f "$COMPOSE_FILE" ps --services --filter status=running 2>/dev/null || true)"
TO_START=()
for svc in "${SERVICES_START_ORDER[@]}"; do
  if ! grep -qx "$svc" <<< "$running_set"; then
    TO_START+=("$svc")
  fi
done

if (( ${#TO_START[@]} == 0 )); then
  warn "all services are already running"
  exit 0
fi

log "starting: ${TO_START[*]}"

# --- Start one at a time in order ------------------------------------------

for svc in "${SERVICES_START_ORDER[@]}"; do
  for stopped in "${TO_START[@]}"; do
    if [[ "$svc" == "$stopped" ]]; then
      docker compose -f "$COMPOSE_FILE" start "$svc"
      break
    fi
  done
done

success "started: ${TO_START[*]}"

# Set up SSH tunnel for reliable WebSocket (bypasses gvproxy bug)
if [[ -x "$(dirname "$0")/ssh-tunnel.sh" ]]; then
  "$(dirname "$0")/ssh-tunnel.sh"
fi
