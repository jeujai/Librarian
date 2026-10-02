#!/usr/bin/env bash
# Restore Milvus + etcd + MinIO from a physical-volume backup set.
#
# Extracted from restore-all-databases.sh and backup-physical-volumes.sh.
# Restores to the bind-mount directories under <repo>/data (NOT named volumes).
#
# Usage:
#   scripts/restore-milvus-database.sh <backup_dir>
#   scripts/restore-milvus-database.sh --dry-run <backup_dir>
#
# Example:
#   scripts/restore-milvus-database.sh /Volumes/CORSAIR/librarian_database_backups/20260714_095858

set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"

REPO_DIR="$(cd "$(dirname "$COMPOSE_FILE")" && pwd)"
DATA_ROOT="${DATA_ROOT:-${REPO_DIR}/data}"

# Services that make up the Milvus stack
SERVICES_STOP_ORDER=(milvus etcd minio)
SERVICES_START_ORDER=(etcd minio milvus)

# Volume archives to restore: "<archive-basename>:<bind-mount-subdir>"
VOLUMES=(
  "etcd_data:etcd"
  "milvus_data:milvus"
  "minio_data:minio"
)

DRY_RUN=0
FORCE=0
BACKUP_DIR=""

# --- Helpers ---------------------------------------------------------------

RED=$'\033[0;31m'; GREEN=$'\033[0;32m'; YELLOW=$'\033[1;33m'
BLUE=$'\033[0;34m'; PURPLE=$'\033[0;35m'; NC=$'\033[0m'

log()     { printf '%s[%s]%s %s\n' "$BLUE" "$(date +'%H:%M:%S')" "$NC" "$*"; }
success() { printf '%s[SUCCESS]%s %s\n' "$GREEN" "$NC" "$*"; }
warn()    { printf '%s[WARNING]%s %s\n' "$YELLOW" "$NC" "$*" >&2; }
err()     { printf '%s[ERROR]%s %s\n' "$RED" "$NC" "$*" >&2; }
info()    { printf '%s[INFO]%s %s\n' "$PURPLE" "$NC" "$*"; }

usage() {
  sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'
  exit 0
}

# --- Parse args ------------------------------------------------------------

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --force|-y) FORCE=1 ;;
    -h|--help) usage ;;
    -*)        err "unknown arg: $arg"; exit 2 ;;
    *)         BACKUP_DIR="$arg" ;;
  esac
done

if [[ -z "$BACKUP_DIR" ]]; then
  err "backup directory required"
  usage
  exit 2
fi

if [[ ! -d "$BACKUP_DIR" ]]; then
  err "backup directory not found: $BACKUP_DIR"
  exit 2
fi

# --- Preflight -------------------------------------------------------------

# Verify backup archives exist
missing=()
for entry in "${VOLUMES[@]}"; do
  name="${entry%%:*}"
  archive="${BACKUP_DIR}/${name}.tar.gz"
  if [[ ! -f "$archive" ]]; then
    missing+=("$archive")
  fi
done

if (( ${#missing[@]} > 0 )); then
  err "missing backup archives:"
  for m in "${missing[@]}"; do
    err "  $m"
  done
  exit 2
fi

log "restore plan:"
log "  backup dir:  ${BACKUP_DIR}"
log "  data root:   ${DATA_ROOT}"
log "  stop order:  ${SERVICES_STOP_ORDER[*]}"
log "  start order: ${SERVICES_START_ORDER[*]}"
log "  dry-run:     $([[ $DRY_RUN -eq 1 ]] && echo 'yes' || echo 'no')"
echo ""

if [[ $DRY_RUN -eq 1 ]]; then
  success "dry-run: nothing restored"
  exit 0
fi

# --- Confirm ---------------------------------------------------------------

if [[ $FORCE -ne 1 ]]; then
  warn "This will OVERWRITE Milvus, etcd, and MinIO data with the backup!"
  warn "Postgres and Neo4j will NOT be affected."
  echo ""
  read -r -p "Continue? [y/N] " confirmation
  if [[ ! "$confirmation" =~ ^[Yy]$ ]]; then
    log "restore cancelled"
    exit 0
  fi
fi

# --- Stop services ---------------------------------------------------------

log "stopping Milvus stack services"
STOPPED=()
running_set="$(docker compose -f "$COMPOSE_FILE" ps --services --filter status=running 2>/dev/null || true)"
for svc in "${SERVICES_STOP_ORDER[@]}"; do
  if echo "$running_set" | grep -qx "$svc"; then
    STOPPED+=("$svc")
  fi
done

if (( ${#STOPPED[@]} > 0 )); then
  for svc in "${SERVICES_STOP_ORDER[@]}"; do
    for stopped in "${STOPPED[@]}"; do
      if [[ "$svc" == "$stopped" ]]; then
        docker compose -f "$COMPOSE_FILE" stop "$svc"
        break
      fi
    done
  done
  success "stopped: ${STOPPED[*]}"
else
  warn "no Milvus services were running"
fi

# --- Restore volumes -------------------------------------------------------

for entry in "${VOLUMES[@]}"; do
  name="${entry%%:*}"
  subdir="${entry#*:}"
  target="${DATA_ROOT}/${subdir}"
  archive="${BACKUP_DIR}/${name}.tar.gz"

  log "restoring ${name} -> ${target}"

  # Wipe current content and extract backup
  docker run --rm \
    -v "${target}:/data" \
    -v "${BACKUP_DIR}:/backup:ro" \
    alpine:3.19 \
    sh -c "find /data -mindepth 1 -not -name '._*' -delete 2>/dev/null; tar xzf /backup/${name}.tar.gz -C /data"

  success "restored ${name}"
done

# --- Clear RocksMQ ---------------------------------------------------------
# The milvus_data archive's RocksDB directories (rdb_data, rdb_data_meta_kv)
# are frequently incomplete — the backup was taken while Milvus was writing, so
# .ldb/MANIFEST files referenced by CURRENT are missing. Milvus aborts with
# "fail to init rocksmq" on startup. RocksMQ is an ephemeral message queue that
# Milvus rebuilds from etcd metadata, so clearing it is safe and required.

log "clearing RocksMQ state (rdb_data, rdb_data_meta_kv) so Milvus rebuilds it"
rm -rf "${DATA_ROOT}/milvus/rdb_data" "${DATA_ROOT}/milvus/rdb_data_meta_kv"

# --- Restart services ------------------------------------------------------

log "starting Milvus stack services"
if (( ${#STOPPED[@]} > 0 )); then
  for svc in "${SERVICES_START_ORDER[@]}"; do
    for stopped in "${STOPPED[@]}"; do
      if [[ "$svc" == "$stopped" ]]; then
        docker compose -f "$COMPOSE_FILE" up -d "$svc" \
          || warn "failed to start $svc; run 'docker compose up -d $svc' manually"
        break
      fi
    done
  done
else
  log "no services were stopped; starting all Milvus stack services"
  for svc in "${SERVICES_START_ORDER[@]}"; do
    docker compose -f "$COMPOSE_FILE" up -d "$svc" \
      || warn "failed to start $svc; run 'docker compose up -d $svc' manually"
  done
fi

success "restore complete — from ${BACKUP_DIR}"
