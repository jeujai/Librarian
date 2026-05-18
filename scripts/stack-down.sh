#!/usr/bin/env bash
# Orderly shutdown of the Librarian Docker Compose stack.
#
# Phases (top-down, dependents first):
#   1. Edge:        nginx
#   2. App layer:   app, celery-worker
#   3. Milvus:      milvus      (must stop BEFORE etcd/minio so it flushes)
#   4. Infra:       etcd, minio, postgres, neo4j, redis, model-server
#   5. Misc:        searxng (if running)
#
# Usage:
#   scripts/stack-down.sh                 # graceful stop, containers preserved
#   scripts/stack-down.sh --remove        # docker compose down (remove containers)
#   scripts/stack-down.sh --remove --volumes   # DESTRUCTIVE: also delete named volumes
#   scripts/stack-down.sh --timeout 30    # per-service stop timeout (default 60s)

set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
TIMEOUT="${TIMEOUT:-60}"
REMOVE=0
REMOVE_VOLUMES=0

PHASES=(
  "nginx"
  "app celery-worker"
  "milvus"
  "etcd minio postgres neo4j redis model-server"
  "searxng"
)

RED=$'\033[0;31m'; GREEN=$'\033[0;32m'; YELLOW=$'\033[1;33m'
BLUE=$'\033[0;34m'; NC=$'\033[0m'
log()     { printf '%s[%s]%s %s\n' "$BLUE" "$(date +'%H:%M:%S')" "$NC" "$*"; }
success() { printf '%s[ok]%s  %s\n' "$GREEN" "$NC" "$*"; }
warn()    { printf '%s[warn]%s %s\n' "$YELLOW" "$NC" "$*" >&2; }
err()     { printf '%s[err]%s  %s\n' "$RED" "$NC" "$*" >&2; }

usage() { sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'; exit 0; }

while (( "$#" )); do
  case "$1" in
    --remove)      REMOVE=1; shift ;;
    --volumes)     REMOVE_VOLUMES=1; shift ;;
    --timeout)     TIMEOUT="$2"; shift 2 ;;
    -h|--help)     usage ;;
    *)             err "unknown arg: $1"; exit 2 ;;
  esac
done

if [[ $REMOVE_VOLUMES -eq 1 && $REMOVE -ne 1 ]]; then
  err "--volumes requires --remove"
  exit 2
fi

if ! docker compose -f "$COMPOSE_FILE" version >/dev/null 2>&1; then
  err "docker compose or compose file not available: $COMPOSE_FILE"
  exit 2
fi

running_set="$(docker compose -f "$COMPOSE_FILE" ps --services --filter status=running 2>/dev/null || true)"
if [[ -z "$running_set" ]]; then
  warn "no services are running"
  [[ $REMOVE -eq 1 ]] || exit 0
fi

log "stopping stack in dependency-aware phases (timeout ${TIMEOUT}s/service)"
for phase in "${PHASES[@]}"; do
  read -r -a svcs <<< "$phase"
  to_stop=()
  for s in "${svcs[@]}"; do
    grep -qx "$s" <<< "$running_set" && to_stop+=("$s")
  done
  if (( ${#to_stop[@]} == 0 )); then
    continue
  fi
  log "phase: stop ${to_stop[*]}"
  docker compose -f "$COMPOSE_FILE" stop -t "$TIMEOUT" "${to_stop[@]}"
  success "  stopped ${to_stop[*]}"
done

if [[ $REMOVE -eq 1 ]]; then
  args=(-f "$COMPOSE_FILE" down --remove-orphans -t "$TIMEOUT")
  if [[ $REMOVE_VOLUMES -eq 1 ]]; then
    warn "DESTRUCTIVE: --volumes will delete all named volumes"
    read -r -p "Type 'DELETE' to confirm: " ans
    [[ "$ans" == "DELETE" ]] || { warn "aborted"; exit 1; }
    args+=(-v)
  fi
  log "docker compose ${args[*]}"
  docker compose "${args[@]}"
fi

success "stack down complete"
