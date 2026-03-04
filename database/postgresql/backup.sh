#!/bin/bash

# PostgreSQL Backup Script for Multimodal Librarian Local Development
# This script creates backups of the PostgreSQL database

set -e

# Configuration
DB_HOST="${POSTGRES_HOST:-localhost}"
DB_PORT="${POSTGRES_PORT:-5432}"
DB_NAME="${POSTGRES_DB:-multimodal_librarian}"
DB_USER="${POSTGRES_USER:-ml_user}"
BACKUP_DIR="${BACKUP_DIR:-./backups/postgresql}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Create backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR"

# Check if PostgreSQL is accessible
log "Checking PostgreSQL connectivity..."
if ! pg_isready -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" >/dev/null 2>&1; then
    error "Cannot connect to PostgreSQL database"
    exit 1
fi
success "PostgreSQL is accessible"

# Function to create schema-only backup
create_schema_backup() {
    local backup_file="$BACKUP_DIR/schema_${DB_NAME}_${TIMESTAMP}.sql"
    log "Creating schema backup: $backup_file"
    
    if pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
               --schema-only --no-owner --no-privileges \
               --file="$backup_file"; then
        success "Schema backup created successfully"
        echo "Schema backup: $backup_file"
    else
        error "Failed to create schema backup"
        return 1
    fi
}

# Function to create data-only backup
create_data_backup() {
    local backup_file="$BACKUP_DIR/data_${DB_NAME}_${TIMESTAMP}.sql"
    log "Creating data backup: $backup_file"
    
    if pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
               --data-only --no-owner --no-privileges \
               --file="$backup_file"; then
        success "Data backup created successfully"
        echo "Data backup: $backup_file"
    else
        error "Failed to create data backup"
        return 1
    fi
}

# Function to create full backup
create_full_backup() {
    local backup_file="$BACKUP_DIR/full_${DB_NAME}_${TIMESTAMP}.sql"
    log "Creating full backup: $backup_file"
    
    if pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
               --no-owner --no-privileges \
               --file="$backup_file"; then
        success "Full backup created successfully"
        echo "Full backup: $backup_file"
    else
        error "Failed to create full backup"
        return 1
    fi
}

# Function to create compressed backup
create_compressed_backup() {
    local backup_file="$BACKUP_DIR/compressed_${DB_NAME}_${TIMESTAMP}.dump"
    log "Creating compressed backup: $backup_file"
    
    if pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
               --format=custom --compress=9 --no-owner --no-privileges \
               --file="$backup_file"; then
        success "Compressed backup created successfully"
        echo "Compressed backup: $backup_file"
    else
        error "Failed to create compressed backup"
        return 1
    fi
}

# Function to clean up old backups (keep last 7 days)
cleanup_old_backups() {
    log "Cleaning up old backups (keeping last 7 days)..."
    
    if find "$BACKUP_DIR" -name "*.sql" -type f -mtime +7 -delete 2>/dev/null; then
        success "Old SQL backups cleaned up"
    fi
    
    if find "$BACKUP_DIR" -name "*.dump" -type f -mtime +7 -delete 2>/dev/null; then
        success "Old dump backups cleaned up"
    fi
}

# Function to show backup statistics
show_backup_stats() {
    log "Backup statistics:"
    echo "Backup directory: $BACKUP_DIR"
    echo "Total backups: $(find "$BACKUP_DIR" -type f \( -name "*.sql" -o -name "*.dump" \) | wc -l)"
    echo "Total size: $(du -sh "$BACKUP_DIR" 2>/dev/null | cut -f1 || echo "Unknown")"
    echo ""
    echo "Recent backups:"
    find "$BACKUP_DIR" -type f \( -name "*.sql" -o -name "*.dump" \) -mtime -1 -exec ls -lh {} \; | head -10
}

# Main execution
main() {
    log "Starting PostgreSQL backup for database: $DB_NAME"
    
    case "${1:-full}" in
        "schema")
            create_schema_backup
            ;;
        "data")
            create_data_backup
            ;;
        "compressed")
            create_compressed_backup
            ;;
        "full")
            create_full_backup
            ;;
        "all")
            create_schema_backup
            create_data_backup
            create_compressed_backup
            ;;
        "cleanup")
            cleanup_old_backups
            ;;
        "stats")
            show_backup_stats
            ;;
        *)
            echo "Usage: $0 [schema|data|compressed|full|all|cleanup|stats]"
            echo ""
            echo "Options:"
            echo "  schema     - Create schema-only backup"
            echo "  data       - Create data-only backup"
            echo "  compressed - Create compressed binary backup"
            echo "  full       - Create full SQL backup (default)"
            echo "  all        - Create all types of backups"
            echo "  cleanup    - Remove backups older than 7 days"
            echo "  stats      - Show backup statistics"
            exit 1
            ;;
    esac
    
    # Always show stats after backup operations
    if [[ "$1" != "stats" && "$1" != "cleanup" ]]; then
        echo ""
        show_backup_stats
    fi
    
    success "Backup operation completed"
}

# Run main function with all arguments
main "$@"