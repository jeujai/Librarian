#!/usr/bin/env bash
# Orderly start-up of the Librarian Docker Compose stack, waiting for each
# phase to go healthy before starting the next.
#
# Phases (bottom-up, dependencies first):
#   1. Milvus deps:  etcd, minio
#   2. Databases:    postgres, neo4j, redis
#   3. Models:       model-server
#   4. Milvus:       milvus           (needs etcd + minio healthy first)
#   5. App:          app, celery-worker
#   6. Edge:         nginx            (optional, only if profile active)
#   7. Extras:       searxng          (optional)
#
# Usage:
#   scripts/stack-up.sh                       # start all phases
#   scripts/stack-up.sh --skip nginx,searxng  # skip specific services
#   scripts/stack-up.sh --only-deps           # start only infra (phases 1-3)
#   scripts/stack-up.sh --timeout 120         # per-phase wait timeout (default 180s)

set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
WAIT_TIMEOUT="${WAIT_TIMEOUT:-180}"
POLL_INTERVAL=2
SKIP=""
ONLY_DEPS=0

# Each entry: "phase-label|svc1 svc2 ..."
PHASES=(
  "milvus-deps|etcd minio"
  "databases|postgres neo4j redis"
  "models|model-server"
  "milvus|milvus"
  "app|app celery-worker"
  "edge|nginx"
  "extras|searxng"
)

RED=$'\033[0;31m'; GREEN=$'\033[0;32m'; YELLOW=$'\033[1;33m'
BLUE=$'\033[0;34m'; NC=$'\033[0m'
log()     { printf '%s[%s]%s %s\n' "$BLUE" "$(date +'%H:%M:%S')" "$NC" "$*"; }
success() { printf '%s[ok]%s  %s\n' "$GREEN" "$NC" "$*"; }
warn()    { printf '%s[warn]%s %s\n' "$YELLOW" "$NC" "$*" >&2; }
err()     { printf '%s[err]%s  %s\n' "$RED" "$NC" "$*" >&2; }

usage() { sed -n '2,22p' "$0" | sed 's/^# \{0,1\}//'; exit 0; }

while (( "$#" )); do
  case "$1" in
    --skip)      SKIP="$2"; shift 2 ;;
    --only-deps) ONLY_DEPS=1; shift ;;
    --timeout)   WAIT_TIMEOUT="$2"; shift 2 ;;
    -h|--help)   usage ;;
    *)           err "unknown arg: $1"; exit 2 ;;
  esac
done

if ! docker compose -f "$COMPOSE_FILE" version >/dev/null 2>&1; then
  err "docker compose or compose file not available: $COMPOSE_FILE"
  exit 2
fi

skip_set=""
if [[ -n "$SKIP" ]]; then
  skip_set="${SKIP//,/ }"
fi

should_skip() {
  local svc="$1"
  for s in $skip_set; do [[ "$svc" == "$s" ]] && return 0; done
  return 1
}

# Returns "healthy" | "starting" | "running" | "unhealthy" | "none"
service_health() {
  local svc="$1"
  local cid
  cid="$(docker compose -f "$COMPOSE_FILE" ps -q "$svc" 2>/dev/null || true)"
  if [[ -z "$cid" ]]; then
    echo "none"; return
  fi
  # Inspect once; prefer Health.Status when a healthcheck is defined.
  local hs rs
  hs="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$cid" 2>/dev/null || true)"
  rs="$(docker inspect -f '{{.State.Status}}' "$cid" 2>/dev/null || true)"
  if [[ -n "$hs" ]]; then echo "$hs"; else echo "$rs"; fi
}

# Wait until every service in the list is "healthy" (if it has a healthcheck)
# or "running" (if it does not). Times out per WAIT_TIMEOUT.
wait_for() {
  local deadline=$(( $(date +%s) + WAIT_TIMEOUT ))
  local pending=("$@")
  while (( ${#pending[@]} > 0 )); do
    local still=()
    for svc in "${pending[@]}"; do
      local st; st="$(service_health "$svc")"
      case "$st" in
        healthy|running) ;;  # good
        unhealthy)
          err "service became unhealthy: $svc"
          docker compose -f "$COMPOSE_FILE" logs --tail 30 "$svc" >&2 || true
          return 1
          ;;
        none)
          err "service not found: $svc (typo?)"
          return 1
          ;;
        *) still+=("$svc") ;;
      esac
    done
    if (( ${#still[@]} == 0 )); then
      return 0
    fi
    if (( $(date +%s) > deadline )); then
      err "timeout after ${WAIT_TIMEOUT}s waiting for: ${still[*]}"
      for svc in "${still[@]}"; do
        warn "=== logs: $svc ==="
        docker compose -f "$COMPOSE_FILE" logs --tail 30 "$svc" >&2 || true
      done
      return 1
    fi
    sleep "$POLL_INTERVAL"
    pending=("${still[@]}")
  done
}

log "starting stack in dependency-aware phases"
for entry in "${PHASES[@]}"; do
  label="${entry%%|*}"
  svcs="${entry#*|}"
  read -r -a svc_array <<< "$svcs"

  if [[ $ONLY_DEPS -eq 1 ]]; then
    case "$label" in
      milvus-deps|databases|models) ;;
      *) log "--only-deps: skipping phase [$label]"; continue ;;
    esac
  fi

  phase_list=()
  for s in "${svc_array[@]}"; do
    if should_skip "$s"; then
      warn "  skip $s (user-requested)"
      continue
    fi
    phase_list+=("$s")
  done

  if (( ${#phase_list[@]} == 0 )); then
    continue
  fi

  log "phase [$label]: up ${phase_list[*]}"
  # -d detached, --no-deps so compose doesn't pull in siblings we don't want yet
  docker compose -f "$COMPOSE_FILE" up -d --no-deps "${phase_list[@]}"
  log "  waiting for health (timeout ${WAIT_TIMEOUT}s)"
  if wait_for "${phase_list[@]}"; then
    success "  phase [$label] healthy"
  else
    err "phase [$label] failed to become healthy"
    exit 1
  fi
done

log "final status:"
docker compose -f "$COMPOSE_FILE" ps
success "stack up complete"
