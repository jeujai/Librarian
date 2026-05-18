#!/usr/bin/env bash
# Restore a physical-volume backup set created by backup-physical-volumes.sh.
#
# Refuses to run while the matching services are up. By default restores every
# volume in the backup set; use --volumes to restrict.
#
# Usage:
#   scripts/restore-physical-volumes.sh --from /Volumes/CORSAIR/librarian_database_backups/20260508_170000
#   scripts/restore-physical-volumes.sh --from <dir> --volumes postgres_data,neo4j_data
#   scripts/restore-physical-volumes.sh --from <dir> --force          # skip confirmation
#   scripts/restore-physical-volumes.sh --from <dir> --keep-running   # DANGER: restore without stopping

set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
PROJECT="${PROJECT:-librarian}"

SERVICES_STOP_ORDER=(milvus etcd minio postgres neo4j redis)
SERVICES_START_ORDER=(etcd minio postgres neo4j redis milvus)

FROM=""
ONLY_VOLUMES=""
FORCE=0
KEEP_RUNNING=0

RED=$'\033[0;31m'; GREEN=$'\033[0;32m'; YELLOW=$'\033[1;33m'
BLUE=$'\033[0;34m'; NC=$'\033[0m'
log()     { printf '%s[%s]%s %s\n' "$BLUE" "$(date +'%H:%M:%S')" "$NC" "$*"; }
success() { printf '%s[ok]%s  %s\n' "$GREEN" "$NC" "$*"; }
warn()    { printf '%s[warn]%s %s\n' "$YELLOW" "$NC" "$*" >&2; }
err()     { printf '%s[err]%s  %s\n' "$RED" "$NC" "$*" >&2; }

usage() { sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 0; }

while (( "$#" )); do
  case "$1" in
    --from)         FROM="$2"; shift 2 ;;
    --volumes)      ONLY_VOLUMES="$2"; shift 2 ;;
    --force)        FORCE=1; shift ;;
    --keep-running) KEEP_RUNNING=1; shift ;;
    -h|--help)      usage ;;
    *)              err "unknown arg: $1"; exit 2 ;;
  esac
done

if [[ -z "$FROM" ]]; then
  err "--from <backup-set-dir> is required"
  exit 2
fi
if [[ ! -d "$FROM" ]]; then
  err "not a directory: $FROM"
  exit 2
fi
if [[ ! -f "$FROM/manifest.txt" ]]; then
  err "manifest.txt missing in $FROM (not a backup set?)"
  exit 2
fi

# Build list of archives to restore.
if [[ -n "$ONLY_VOLUMES" ]]; then
  IFS=',' read -r -a VOLUMES <<< "$ONLY_VOLUMES"
else
  VOLUMES=()
  while IFS= read -r vol; do
    [[ -n "$vol" ]] && VOLUMES+=("$vol")
  done < <(awk 'NR>6 {print $1}' "$FROM/manifest.txt")
fi

if (( ${#VOLUMES[@]} == 0 )); then
  err "no volumes selected for restore"
  exit 2
fi

log "restore plan:"
log "  from:    $FROM"
log "  project: $PROJECT"
log "  volumes: ${VOLUMES[*]}"
log "  stop:    $([[ $KEEP_RUNNING -eq 1 ]] && echo 'no (UNSAFE)' || echo 'yes')"

if [[ $FORCE -ne 1 ]]; then
  read -r -p "Restore will OVERWRITE the above docker volumes. Continue? [y/N] " ans
  [[ "$ans" =~ ^[Yy]$ ]] || { warn "aborted"; exit 1; }
fi

# Refuse while services are up unless --keep-running was explicitly set.
running=()
running_set="$(docker compose -f "$COMPOSE_FILE" ps --services --filter status=running 2>/dev/null || true)"
for svc in "${SERVICES_STOP_ORDER[@]}"; do
  if grep -qx "$svc" <<< "$running_set"; then
    running+=("$svc")
  fi
done

if (( ${#running[@]} > 0 )) && [[ $KEEP_RUNNING -ne 1 ]]; then
  log "stopping services in dependency order: ${running[*]}"
  for svc in "${SERVICES_STOP_ORDER[@]}"; do
    for r in "${running[@]}"; do
      [[ "$svc" == "$r" ]] && docker compose -f "$COMPOSE_FILE" stop "$svc" && break
    done
  done
fi

# Restore each volume.
for v in "${VOLUMES[@]}"; do
  archive="${FROM}/${v}.tar.gz"
  if [[ ! -f "$archive" ]]; then
    err "archive missing: $archive"
    exit 2
  fi
  full="${PROJECT}_${v}"
  log "restoring $archive -> $full"

  # Make sure the volume exists; create empty if not.
  docker volume inspect "$full" >/dev/null 2>&1 || docker volume create "$full" >/dev/null

  # Wipe and extract in one alpine pass.
  docker run --rm \
    -v "${full}:/data" \
    -v "${FROM}:/backup:ro" \
    alpine:3.19 \
    sh -c "find /data -mindepth 1 -delete && tar -xzf /backup/${v}.tar.gz -C /data"
  success "  restored $v"
done

if (( ${#running[@]} > 0 )) && [[ $KEEP_RUNNING -ne 1 ]]; then
  log "starting services in dependency order"
  for svc in "${SERVICES_START_ORDER[@]}"; do
    for r in "${running[@]}"; do
      [[ "$svc" == "$r" ]] && docker compose -f "$COMPOSE_FILE" start "$svc" && break
    done
  done
fi

success "restore complete"
