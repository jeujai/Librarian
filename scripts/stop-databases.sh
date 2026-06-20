#!/usr/bin/env bash
# Stop Librarian data services in dependency-correct order.
#
# Milvus MUST stop before etcd/minio so it flushes cleanly.
# Postgres, Neo4j, and Redis are independent and can stop in any order.
#
# Usage:
#   scripts/stop-databases.sh
#   scripts/stop-databases.sh --dry-run      # print plan, do nothing
#   scripts/stop-databases.sh --help

set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
PROJECT="${PROJECT:-librarian}"

# Stop order: milvus first (flushes to etcd/minio), then its dependencies,
# then independent services.
SERVICES_STOP_ORDER=(
  milvus
  etcd
  minio
  postgres
  neo4j
  redis
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

log "stop plan:"
log "  compose file:  ${COMPOSE_FILE}"
log "  stop order:    ${SERVICES_STOP_ORDER[*]}"

if [[ $DRY_RUN -eq 1 ]]; then
  success "dry-run: nothing stopped"
  exit 0
fi

# --- Identify running services ---------------------------------------------

running_set="$(docker compose -f "$COMPOSE_FILE" ps --services --filter status=running 2>/dev/null || true)"
TO_STOP=()
for svc in "${SERVICES_STOP_ORDER[@]}"; do
  if grep -qx "$svc" <<< "$running_set"; then
    TO_STOP+=("$svc")
  fi
done

if (( ${#TO_STOP[@]} == 0 )); then
  warn "no matching services are running"
  exit 0
fi

log "stopping: ${TO_STOP[*]}"

# --- Stop one at a time in order -------------------------------------------

for svc in "${SERVICES_STOP_ORDER[@]}"; do
  for running in "${TO_STOP[@]}"; do
    if [[ "$svc" == "$running" ]]; then
      docker compose -f "$COMPOSE_FILE" stop "$svc"
      break
    fi
  done
done

success "stopped: ${TO_STOP[*]}"
