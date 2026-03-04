#!/usr/bin/env bash
# Rebuild local Docker images and prune old ones to prevent disk exhaustion.
# Compatible with bash 3.x (macOS default).
#
# Usage:
#   ./scripts/rebuild-local.sh                # rebuild app + celery-worker
#   ./scripts/rebuild-local.sh --all          # rebuild all services (incl. model-server)
#   ./scripts/rebuild-local.sh --reset        # also reset document data after rebuild
#
set -euo pipefail

SERVICES="app celery-worker"
RESET=false

for arg in "$@"; do
    case "$arg" in
        --all)    SERVICES="app celery-worker model-server" ;;
        --reset)  RESET=true ;;
        *)        echo "Unknown arg: $arg"; exit 1 ;;
    esac
done

echo "=== Rebuild Local Images ==="
echo "Services: $SERVICES"
echo ""

# Step 1: Stop the services we're rebuilding
echo "[1/5] Stopping services..."
docker compose stop $SERVICES

# Step 2: Record current image IDs (bash 3.x compatible — use temp file)
echo "[2/5] Capturing current image IDs..."
OLD_IDS_FILE=$(mktemp)
for svc in $SERVICES; do
    img=$(docker compose images --quiet "$svc" 2>/dev/null || true)
    if [ -n "$img" ]; then
        echo "$svc=$img" >> "$OLD_IDS_FILE"
    fi
done

# Step 3: Rebuild
echo "[3/5] Building images..."
docker compose build $SERVICES

# Step 4: Prune old images
echo "[4/5] Pruning old application images..."

# Remove dangling images (intermediate build layers with no tag)
dangling=$(docker images -f "dangling=true" -q 2>/dev/null || true)
if [ -n "$dangling" ]; then
    count=$(echo "$dangling" | wc -l | tr -d ' ')
    echo "  Removing $count dangling images..."
    echo "$dangling" | xargs docker rmi -f 2>/dev/null || true
fi

# Remove old tagged images that are no longer current
while IFS='=' read -r svc old_id; do
    [ -z "$old_id" ] && continue
    new_id=$(docker compose images --quiet "$svc" 2>/dev/null || true)
    if [ -n "$new_id" ] && [ "$old_id" != "$new_id" ]; then
        echo "  Removing old image for $svc ($old_id)..."
        docker rmi -f "$old_id" 2>/dev/null || true
    fi
done < "$OLD_IDS_FILE"
rm -f "$OLD_IDS_FILE"

# Prune stale build cache
docker builder prune -f --filter "until=24h" 2>/dev/null || true

echo ""
echo "  Docker disk usage:"
docker system df 2>/dev/null | head -5

# Step 5: Restart
echo ""
echo "[5/5] Starting services..."
docker compose up -d $SERVICES

echo ""
echo "=== Rebuild complete ==="

if $RESET; then
    echo ""
    echo "Waiting 10s for services to initialize..."
    sleep 10
    echo "Resetting document data..."
    docker exec librarian-app-1 python /app/scripts/reset_document_data.py --yes
fi
