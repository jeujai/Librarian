#!/bin/bash

# PostgreSQL Management Script for Multimodal Librarian Local Development
# This script provides common database management operations

set -e

# Configuration
DB_HOST="${POSTGRES_HOST:-localhost}"
DB_PORT="${POSTGRES_PORT:-5432}"
DB_NAME="${POSTGRES_DB:-multimodal_librarian}"
DB_USER="${POSTGRES_USER:-ml_user}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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
    if ! pg_isready -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" >/dev/null 2>&1; then
        error "Cannot connect to PostgreSQL database"
        return 1
    fi
    return 0
}

# Function to run health check
health_check() {
    log "Running PostgreSQL health check..."
    
    if ! check_connectivity; then
        error "Database is not accessible"
        return 1
    fi
    
    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
         -f "$SCRIPT_DIR/health_check.sql" -t -A -F'|'
}

# Function to show database status
show_status() {
    log "PostgreSQL Database Status"
    echo "=========================="
    
    if ! check_connectivity; then
        error "Database is not accessible"
        return 1
    fi
    
    echo "Connection Details:"
    echo "  Host: $DB_HOST"
    echo "  Port: $DB_PORT"
    echo "  Database: $DB_NAME"
    echo "  User: $DB_USER"
    echo ""
    
    # Database version
    echo "Version:"
    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
         -c "SELECT version();" -t
    echo ""
    
    # Database size
    echo "Database Size:"
    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
         -c "SELECT pg_size_pretty(pg_database_size('$DB_NAME'));" -t
    echo ""
    
    # Active connections
    echo "Active Connections:"
    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
         -c "SELECT count(*) FROM pg_stat_activity WHERE state = 'active';" -t
    echo ""
    
    # Table count
    echo "Tables:"
    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
         -c "SELECT count(*) FROM information_schema.tables WHERE table_schema NOT IN ('information_schema', 'pg_catalog');" -t
}

# Function to run maintenance
run_maintenance() {
    log "Running database maintenance..."
    
    if ! check_connectivity; then
        error "Database is not accessible"
        return 1
    fi
    
    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
         -c "SELECT * FROM maintenance.routine_maintenance();"
}

# Function to show table sizes
show_table_sizes() {
    log "Table sizes in database: $DB_NAME"
    
    if ! check_connectivity; then
        error "Database is not accessible"
        return 1
    fi
    
    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
         -c "SELECT * FROM monitoring.get_table_sizes();" \
         -x
}

# Function to show active connections
show_connections() {
    log "Active connections to database: $DB_NAME"
    
    if ! check_connectivity; then
        error "Database is not accessible"
        return 1
    fi
    
    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
         -c "SELECT * FROM monitoring.active_connections;" \
         -x
}

# Function to analyze all tables
analyze_tables() {
    log "Analyzing all tables..."
    
    if ! check_connectivity; then
        error "Database is not accessible"
        return 1
    fi
    
    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
         -c "SELECT analyze_all_tables();"
    
    success "All tables analyzed"
}

# Function to vacuum all tables
vacuum_tables() {
    log "Vacuuming all tables..."
    
    if ! check_connectivity; then
        error "Database is not accessible"
        return 1
    fi
    
    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
         -c "SELECT vacuum_all_tables();"
    
    success "All tables vacuumed"
}

# Function to reset database (dangerous!)
reset_database() {
    warning "This will completely reset the database!"
    echo -n "Are you sure you want to continue? Type 'RESET' to confirm: "
    read -r confirmation
    
    if [[ "$confirmation" != "RESET" ]]; then
        log "Database reset cancelled"
        return 0
    fi
    
    log "Resetting database..."
    
    # Drop database
    if dropdb -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" "$DB_NAME" 2>/dev/null; then
        log "Database dropped"
    else
        warning "Database drop failed (might not exist)"
    fi
    
    # Create database
    if createdb -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" "$DB_NAME"; then
        success "Database created"
    else
        error "Failed to create database"
        return 1
    fi
    
    # Run initialization scripts
    log "Running initialization scripts..."
    for script in "$SCRIPT_DIR/init"/*.sql; do
        if [[ -f "$script" ]]; then
            log "Running: $(basename "$script")"
            psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f "$script"
        fi
    done
    
    # Run application schema
    if [[ -f "$SCRIPT_DIR/../../src/multimodal_librarian/database/init_db.sql" ]]; then
        log "Running application schema..."
        psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
             -f "$SCRIPT_DIR/../../src/multimodal_librarian/database/init_db.sql"
    fi
    
    success "Database reset completed"
}

# Function to create backup
create_backup() {
    "$SCRIPT_DIR/backup.sh" "$@"
}

# Function to restore backup
restore_backup() {
    "$SCRIPT_DIR/restore.sh" "$@"
}

# Function to open psql shell
open_shell() {
    log "Opening PostgreSQL shell..."
    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME"
}

# Main execution
main() {
    case "${1:-status}" in
        "status")
            show_status
            ;;
        "health")
            health_check
            ;;
        "maintenance")
            run_maintenance
            ;;
        "tables")
            show_table_sizes
            ;;
        "connections")
            show_connections
            ;;
        "analyze")
            analyze_tables
            ;;
        "vacuum")
            vacuum_tables
            ;;
        "reset")
            reset_database
            ;;
        "backup")
            shift
            create_backup "$@"
            ;;
        "restore")
            shift
            restore_backup "$@"
            ;;
        "shell")
            open_shell
            ;;
        *)
            echo "PostgreSQL Management Script for Multimodal Librarian"
            echo "Usage: $0 [command] [options]"
            echo ""
            echo "Commands:"
            echo "  status       - Show database status (default)"
            echo "  health       - Run health check"
            echo "  maintenance  - Run routine maintenance"
            echo "  tables       - Show table sizes"
            echo "  connections  - Show active connections"
            echo "  analyze      - Analyze all tables"
            echo "  vacuum       - Vacuum all tables"
            echo "  reset        - Reset database (DANGEROUS!)"
            echo "  backup       - Create backup (see backup.sh for options)"
            echo "  restore      - Restore backup (see restore.sh for options)"
            echo "  shell        - Open PostgreSQL shell"
            echo ""
            echo "Environment variables:"
            echo "  POSTGRES_HOST  - PostgreSQL host (default: localhost)"
            echo "  POSTGRES_PORT  - PostgreSQL port (default: 5432)"
            echo "  POSTGRES_DB    - Database name (default: multimodal_librarian)"
            echo "  POSTGRES_USER  - Database user (default: ml_user)"
            exit 1
            ;;
    esac
}

# Run main function with all arguments
main "$@"