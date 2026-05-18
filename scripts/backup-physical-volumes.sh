#!/usr/bin/env bash
# Physical (byte-level) backup of Librarian Docker named volumes to CORSAIR.
#
# Strategy: Route B from the backup design notes.
#   1. Stop the data services so no process is mid-write.
#   2. Mount each named volume read-only into a throwaway alpine container.
#   3. tar+gzip the volume contents to the target directory on CORSAIR.
#   4. Start the data services again.
#
# Required services are stopped together (etcd + minio + milvus must be
# captured at the same moment to keep Milvus state consistent).
#
# Usage:
#   scripts/backup-physical-volumes.sh                # backup all volumes
#   scripts/backup-physical-volumes.sh --no-stop      # skip stop/start (unsafe)
#   scripts/backup-physical-volumes.sh --dry-run      # print plan, do nothing
#   scripts/backup-physical-volumes.sh --help
#
# Environment overrides:
#   BACKUP_ROOT   (default /Volumes/CORSAIR/librarian_database_backups)
#   COMPOSE_FILE  (default docker-compose.yml)
#   PROJECT       (default librarian)   # Docker Compose project/volume prefix
#   RETENTION_DAYS (default 0 = keep all backup sets forever; set to N>0 to
#                   auto-prune sets older than N days)

set -euo pipefail

BACKUP_ROOT="${BACKUP_ROOT:-/Volumes/CORSAIR/librarian_database_backups}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
PROJECT="${PROJECT:-librarian}"
RETENTION_DAYS="${RETENTION_DAYS:-0}"

# Volumes to back up. Order matters only for logging.
VOLUMES=(
  postgres_data
  neo4j_data
  neo4j_logs
  milvus_data
  etcd_data
  minio_data
  redis_data
)

# Compose services to stop before snapshot, in stop-order (reverse-dep).
# milvus MUST stop before etcd/minio so it flushes cleanly.
# model_cache volume is excluded because it is a rebuildable HuggingFace cache.
SERVICES_STOP_ORDER=(
  milvus      # depends on etcd + minio, stop first so it flushes
  etcd        # milvus dep
  minio       # milvus dep
  postgres    # independent
  neo4j       # independent
  redis       # independent
)
# Reverse of stop-order = dependency-correct start-order.
SERVICES_START_ORDER=(
  etcd
  minio
  postgres
  neo4j
  redis
  milvus      # needs etcd + minio healthy first
)

# Flags
DO_STOP=1
DRY_RUN=0

# --- Helpers ---------------------------------------------------------------

RED=$'\033[0;31m'; GREEN=$'\033[0;32m'; YELLOW=$'\033[1;33m'
BLUE=$'\033[0;34m'; NC=$'\033[0m'

log()     { printf '%s[%s]%s %s\n' "$BLUE" "$(date +'%H:%M:%S')" "$NC" "$*"; }
success() { printf '%s[ok]%s  %s\n' "$GREEN" "$NC" "$*"; }
warn()    { printf '%s[warn]%s %s\n' "$YELLOW" "$NC" "$*" >&2; }
err()     { printf '%s[err]%s  %s\n' "$RED" "$NC" "$*" >&2; }

usage() {
  sed -n '2,24p' "$0" | sed 's/^# \{0,1\}//'
  exit 0
}

require_tool() {
  command -v "$1" >/dev/null 2>&1 || { err "required tool not found: $1"; exit 2; }
}

# --- Parse args ------------------------------------------------------------

for arg in "$@"; do
  case "$arg" in
    --no-stop)  DO_STOP=0 ;;
    --dry-run)  DRY_RUN=1 ;;
    -h|--help)  usage ;;
    *)          err "unknown arg: $arg"; exit 2 ;;
  esac
done

# --- Preflight -------------------------------------------------------------

require_tool docker
require_tool date

if ! docker compose version >/dev/null 2>&1; then
  err "docker compose plugin is required"
  exit 2
fi

if [[ ! -d "$BACKUP_ROOT" ]]; then
  err "backup root does not exist: $BACKUP_ROOT"
  err "mount the CORSAIR drive or set BACKUP_ROOT"
  exit 2
fi

if [[ ! -w "$BACKUP_ROOT" ]]; then
  err "backup root is not writable: $BACKUP_ROOT"
  exit 2
fi

# Confirm every volume exists before we start stopping things.
missing=()
for v in "${VOLUMES[@]}"; do
  if ! docker volume inspect "${PROJECT}_${v}" >/dev/null 2>&1; then
    missing+=("${PROJECT}_${v}")
  fi
done
if (( ${#missing[@]} > 0 )); then
  err "missing docker volumes: ${missing[*]}"
  exit 2
fi

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
TARGET_DIR="${BACKUP_ROOT}/${TIMESTAMP}"
MANIFEST="${TARGET_DIR}/manifest.txt"

log "backup plan:"
log "  project:       ${PROJECT}"
log "  compose file:  ${COMPOSE_FILE}"
log "  target dir:    ${TARGET_DIR}"
log "  volumes:       ${VOLUMES[*]}"
log "  stop order:    ${SERVICES_STOP_ORDER[*]}"
log "  start order:   ${SERVICES_START_ORDER[*]}"
log "  stop services: $([[ $DO_STOP -eq 1 ]] && echo 'yes' || echo 'no (UNSAFE)')"
log "  dry-run:       $([[ $DRY_RUN -eq 1 ]] && echo 'yes' || echo 'no')"

if [[ $DRY_RUN -eq 1 ]]; then
  success "dry-run: nothing written"
  exit 0
fi

mkdir -p "$TARGET_DIR"

# --- Stop data services ---------------------------------------------------

STARTED_SERVICES=()
cleanup() {
  if (( ${#STARTED_SERVICES[@]} > 0 )); then
    # Restart in dependency-correct order, only restarting services we stopped.
    log "restarting services in dependency order"
    for svc in "${SERVICES_START_ORDER[@]}"; do
      for stopped in "${STARTED_SERVICES[@]}"; do
        if [[ "$svc" == "$stopped" ]]; then
          docker compose -f "$COMPOSE_FILE" start "$svc" \
            || warn "failed to restart $svc; run 'docker compose start $svc' manually"
          break
        fi
      done
    done
  fi
}
trap cleanup EXIT

if [[ $DO_STOP -eq 1 ]]; then
  log "stopping services for consistent snapshot (stop-order respects milvus→etcd/minio)"
  # Remember which services were actually running so we only restart those.
  running_set="$(docker compose -f "$COMPOSE_FILE" ps --services --filter status=running 2>/dev/null || true)"
  for svc in "${SERVICES_STOP_ORDER[@]}"; do
    if grep -qx "$svc" <<< "$running_set"; then
      STARTED_SERVICES+=("$svc")
    fi
  done

  if (( ${#STARTED_SERVICES[@]} > 0 )); then
    # Stop one-at-a-time in the documented order so milvus flushes before etcd/minio.
    for svc in "${SERVICES_STOP_ORDER[@]}"; do
      for stopped in "${STARTED_SERVICES[@]}"; do
        if [[ "$svc" == "$stopped" ]]; then
          docker compose -f "$COMPOSE_FILE" stop "$svc"
          break
        fi
      done
    done
    success "stopped: ${STARTED_SERVICES[*]}"
  else
    warn "no matching services were running; proceeding"
  fi
else
  warn "--no-stop was provided; snapshots may be inconsistent if services write mid-copy"
fi

# --- Snapshot each volume -------------------------------------------------

{
  echo "timestamp: $TIMESTAMP"
  echo "project:   $PROJECT"
  echo "host:      $(hostname)"
  echo "docker:    $(docker --version)"
  echo "compose:   $(docker compose version --short 2>/dev/null || echo unknown)"
  echo "stopped:   $([[ $DO_STOP -eq 1 ]] && echo yes || echo no)"
  echo
  printf '%-20s %-40s %s\n' "volume" "archive" "sha256"
} > "$MANIFEST"

for v in "${VOLUMES[@]}"; do
  full="${PROJECT}_${v}"
  archive="${v}.tar.gz"
  log "archiving ${full} -> ${archive}"
  docker run --rm \
    -v "${full}:/data:ro" \
    -v "${TARGET_DIR}:/backup" \
    alpine:3.19 \
    sh -c "tar -C /data -czf /backup/${archive} ."

  # sha256 checksum inside a container so we do not rely on host tools
  checksum="$(docker run --rm \
    -v "${TARGET_DIR}:/backup:ro" \
    alpine:3.19 \
    sh -c "sha256sum /backup/${archive} | awk '{print \$1}'")"
  printf '%-20s %-40s %s\n' "$v" "$archive" "$checksum" >> "$MANIFEST"
  success "  $(ls -lh "${TARGET_DIR}/${archive}" | awk '{print $5}')  ${checksum:0:12}..."
done

# --- Retention ------------------------------------------------------------

if [[ "$RETENTION_DAYS" -gt 0 ]]; then
  log "pruning backup sets older than ${RETENTION_DAYS} days"
  find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d -mtime "+${RETENTION_DAYS}" -print -exec rm -rf {} + \
    | sed 's/^/  removed: /' || true
else
  log "retention: keeping all backup sets (RETENTION_DAYS=0)"
fi

success "backup complete: ${TARGET_DIR}"
