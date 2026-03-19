#!/bin/bash
# Docker Cleanup Script for Multimodal Librarian
#
# This script cleans up Docker resources that can accumulate and cause
# disk space issues, particularly the build cache which can grow to 80+ GB.
#
# Usage:
#   ./scripts/docker-cleanup.sh           # Interactive mode
#   ./scripts/docker-cleanup.sh --force   # Non-interactive mode
#   ./scripts/docker-cleanup.sh --dry-run # Show what would be cleaned
#
# Recommended: Run weekly via cron or launchd
#   0 3 * * 0 /path/to/librarian/scripts/docker-cleanup.sh --force >> /var/log/docker-cleanup.log 2>&1

set -e

FORCE=false
DRY_RUN=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --force|-f)
            FORCE=true
            shift
            ;;
        --dry-run|-n)
            DRY_RUN=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--force|-f] [--dry-run|-n]"
            exit 1
            ;;
    esac
done

echo "=========================================="
echo "Docker Cleanup for Multimodal Librarian"
echo "=========================================="
echo "Date: $(date)"
echo ""

# Show current disk usage
echo "Current Docker disk usage:"
docker system df
echo ""

# Calculate reclaimable space
RECLAIMABLE=$(docker system df --format '{{.Reclaimable}}' | head -1)
echo "Estimated reclaimable space: $RECLAIMABLE"
echo ""

if [ "$DRY_RUN" = true ]; then
    echo "[DRY RUN] Would clean:"
    echo "  - Stopped containers"
    echo "  - Unused networks"
    echo "  - Dangling images"
    echo "  - Build cache"
    echo ""
    echo "Run without --dry-run to actually clean."
    exit 0
fi

if [ "$FORCE" = false ]; then
    read -p "Proceed with cleanup? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Cleanup cancelled."
        exit 0
    fi
fi

echo ""
echo "Cleaning up Docker resources..."
echo ""

# Clean build cache (the main culprit)
echo "1. Cleaning build cache..."
docker builder prune -f
echo ""

# Clean unused images
echo "2. Cleaning dangling images..."
docker image prune -f
echo ""

# Clean stopped containers (but not running ones)
echo "3. Cleaning stopped containers..."
docker container prune -f
echo ""

# Clean unused networks
echo "4. Cleaning unused networks..."
docker network prune -f
echo ""

# Show final disk usage
echo ""
echo "=========================================="
echo "Cleanup complete!"
echo "=========================================="
echo ""
echo "Final Docker disk usage:"
docker system df
echo ""
echo "Date: $(date)"
