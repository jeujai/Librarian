#!/bin/bash

# PostgreSQL Restore Script for Multimodal Librarian Local Development
# This script restores PostgreSQL database from backups

set -e

# Configuration
DB_HOST="${POSTGRES_HOST:-localhost}"
DB_PORT="${POSTGRES_PORT:-5432}"
DB_NAME="${POSTGRES_DB:-multimodal_librarian}"
DB_USER="${POSTGRES_USER:-ml_user}"
BACKUP_DIR="${BACKUP_DIR:-./backups/postgresql}"

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

# Check if PostgreSQL is accessible
check_connectivity() {
    log "Checking PostgreSQL connectivity..."
    if ! pg_isready -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" >/dev/null 2>&1; then
        error "Cannot connect to PostgreSQL database"
        exit 1
    fi
    success "PostgreSQL is accessible"
}

# Function to list available backups
list_backups() {
    log "Available backups in $BACKUP_DIR:"
    echo ""
    
    if [[ ! -d "$BACKUP_DIR" ]]; then
        warning "Backup directory does not exist: $BACKUP_DIR"
        return 1
    fi
    
    local backups_found=false
    
    echo "SQL Backups:"
    if find "$BACKUP_DIR" -name "*.sql" -type f | head -1 >/dev/null 2>&1; then
        find "$BACKUP_DIR" -name "*.sql" -type f -exec ls -lh {} \; | sort -k9
        backups_found=true
    else
        echo "  No SQL backups found"
    fi
    
    echo ""
    echo "Compressed Backups:"
    if find "$BACKUP_DIR" -name "*.dump" -type f | head -1 >/dev/null 2>&1; then
        find "$BACKUP_DIR" -name "*.dump" -type f -exec ls -lh {} \; | sort -k9
        backups_found=true
    else
        echo "  No compressed backups found"
    fi
    
    if [[ "$backups_found" == false ]]; then
        warning "No backups found in $BACKUP_DIR"
        return 1
    fi
}

# Function to restore from SQL backup
restore_sql_backup() {
    local backup_file="$1"
    
    if [[ ! -f "$backup_file" ]]; then
        error "Backup file not found: $backup_file"
        return 1
    fi
    
    log "Restoring from SQL backup: $backup_file"
    
    # Ask for confirmation
    echo -n "This will overwrite the current database. Continue? (y/N): "
    read -r confirmation
    if [[ "$confirmation" != "y" && "$confirmation" != "Y" ]]; then
        log "Restore cancelled by user"
        return 0
    fi
    
    # Drop and recreate database (be careful!)
    warning "Dropping and recreating database: $DB_NAME"
    if dropdb -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" "$DB_NAME" 2>/dev/null; then
        log "Database dropped successfully"
    else
        warning "Database drop failed (database might not exist)"
    fi
    
    if createdb -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" "$DB_NAME"; then
        success "Database created successfully"
    else
        error "Failed to create database"
        return 1
    fi
    
    # Restore from backup
    if psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f "$backup_file"; then
        success "Database restored successfully from SQL backup"
    else
        error "Failed to restore from SQL backup"
        return 1
    fi
}

# Function to restore from compressed backup
restore_compressed_backup() {
    local backup_file="$1"
    
    if [[ ! -f "$backup_file" ]]; then
        error "Backup file not found: $backup_file"
        return 1
    fi
    
    log "Restoring from compressed backup: $backup_file"
    
    # Ask for confirmation
    echo -n "This will overwrite the current database. Continue? (y/N): "
    read -r confirmation
    if [[ "$confirmation" != "y" && "$confirmation" != "Y" ]]; then
        log "Restore cancelled by user"
        return 0
    fi
    
    # Drop and recreate database (be careful!)
    warning "Dropping and recreating database: $DB_NAME"
    if dropdb -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" "$DB_NAME" 2>/dev/null; then
        log "Database dropped successfully"
    else
        warning "Database drop failed (database might not exist)"
    fi
    
    if createdb -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" "$DB_NAME"; then
        success "Database created successfully"
    else
        error "Failed to create database"
        return 1
    fi
    
    # Restore from compressed backup
    if pg_restore -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
                  --no-owner --no-privileges "$backup_file"; then
        success "Database restored successfully from compressed backup"
    else
        error "Failed to restore from compressed backup"
        return 1
    fi
}

# Function to restore schema only
restore_schema_only() {
    local backup_file="$1"
    
    if [[ ! -f "$backup_file" ]]; then
        error "Backup file not found: $backup_file"
        return 1
    fi
    
    log "Restoring schema only from: $backup_file"
    
    if psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f "$backup_file"; then
        success "Schema restored successfully"
    else
        error "Failed to restore schema"
        return 1
    fi
}

# Function to get latest backup
get_latest_backup() {
    local backup_type="$1"
    local pattern
    
    case "$backup_type" in
        "full")
            pattern="full_*.sql"
            ;;
        "schema")
            pattern="schema_*.sql"
            ;;
        "data")
            pattern="data_*.sql"
            ;;
        "compressed")
            pattern="compressed_*.dump"
            ;;
        *)
            pattern="*.sql"
            ;;
    esac
    
    find "$BACKUP_DIR" -name "$pattern" -type f -printf '%T@ %p\n' 2>/dev/null | \
    sort -n | tail -1 | cut -d' ' -f2-
}

# Main execution
main() {
    case "${1:-list}" in
        "list")
            list_backups
            ;;
        "latest")
            check_connectivity
            local latest_backup
            latest_backup=$(get_latest_backup "full")
            if [[ -n "$latest_backup" ]]; then
                log "Latest backup found: $latest_backup"
                if [[ "$latest_backup" == *.dump ]]; then
                    restore_compressed_backup "$latest_backup"
                else
                    restore_sql_backup "$latest_backup"
                fi
            else
                error "No backups found"
                exit 1
            fi
            ;;
        "latest-schema")
            check_connectivity
            local latest_schema
            latest_schema=$(get_latest_backup "schema")
            if [[ -n "$latest_schema" ]]; then
                log "Latest schema backup found: $latest_schema"
                restore_schema_only "$latest_schema"
            else
                error "No schema backups found"
                exit 1
            fi
            ;;
        "file")
            if [[ -z "$2" ]]; then
                error "Please specify backup file path"
                echo "Usage: $0 file <backup_file_path>"
                exit 1
            fi
            check_connectivity
            if [[ "$2" == *.dump ]]; then
                restore_compressed_backup "$2"
            else
                restore_sql_backup "$2"
            fi
            ;;
        *)
            echo "Usage: $0 [list|latest|latest-schema|file <path>]"
            echo ""
            echo "Options:"
            echo "  list           - List available backups (default)"
            echo "  latest         - Restore from latest full backup"
            echo "  latest-schema  - Restore schema from latest schema backup"
            echo "  file <path>    - Restore from specific backup file"
            echo ""
            echo "Environment variables:"
            echo "  POSTGRES_HOST  - PostgreSQL host (default: localhost)"
            echo "  POSTGRES_PORT  - PostgreSQL port (default: 5432)"
            echo "  POSTGRES_DB    - Database name (default: multimodal_librarian)"
            echo "  POSTGRES_USER  - Database user (default: ml_user)"
            echo "  BACKUP_DIR     - Backup directory (default: ./backups/postgresql)"
            exit 1
            ;;
    esac
}

# Run main function with all arguments
main "$@"