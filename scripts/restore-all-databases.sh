#!/bin/bash

# Comprehensive Database Restore Script for Multimodal Librarian Local Development
# This script restores all database services (PostgreSQL, Neo4j, Milvus, Redis) from backups

set -e

# Configuration
BACKUP_ROOT_DIR="${BACKUP_DIR:-./backups}"
RESTORE_TYPE="${RESTORE_TYPE:-latest}"
PARALLEL_RESTORES="${PARALLEL_RESTORES:-false}"
FORCE_RESTORE="${FORCE_RESTORE:-false}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
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

info() {
    echo -e "${PURPLE}[INFO]${NC} $1"
}

# Check if backup directories exist
check_backup_directories() {
    log "Checking backup directories..."
    
    local missing_dirs=()
    
    for db_dir in postgresql neo4j milvus redis system; do
        if [[ ! -d "$BACKUP_ROOT_DIR/$db_dir" ]]; then
            missing_dirs+=("$db_dir")
        fi
    done
    
    if [[ ${#missing_dirs[@]} -gt 0 ]]; then
        warning "Missing backup directories: ${missing_dirs[*]}"
        info "Available backup directories:"
        for db_dir in "$BACKUP_ROOT_DIR"/*; do
            if [[ -d "$db_dir" ]]; then
                echo "  - $(basename "$db_dir")"
            fi
        done
    else
        success "All backup directories found"
    fi
}

# Check if services are running
check_services() {
    log "Checking database services status..."
    
    local services_status=()
    
    # Check PostgreSQL
    if pg_isready -h "${POSTGRES_HOST:-localhost}" -p "${POSTGRES_PORT:-5432}" -U "${POSTGRES_USER:-ml_user}" -d "${POSTGRES_DB:-multimodal_librarian}" >/dev/null 2>&1; then
        services_status+=("PostgreSQL: ✓")
    else
        services_status+=("PostgreSQL: ✗")
    fi
    
    # Check Neo4j
    if cypher-shell -a "bolt://${NEO4J_HOST:-localhost}:${NEO4J_PORT:-7687}" -u "${NEO4J_USER:-neo4j}" -p "${NEO4J_PASSWORD:-ml_password}" "RETURN 1" >/dev/null 2>&1; then
        services_status+=("Neo4j: ✓")
    else
        services_status+=("Neo4j: ✗")
    fi
    
    # Check Milvus
    if curl -s -f "http://${MILVUS_HOST:-localhost}:${MILVUS_HTTP_PORT:-9091}/healthz" >/dev/null 2>&1; then
        services_status+=("Milvus: ✓")
    else
        services_status+=("Milvus: ✗")
    fi
    
    # Check Redis
    if redis-cli -h "${REDIS_HOST:-localhost}" -p "${REDIS_PORT:-6379}" ping >/dev/null 2>&1; then
        services_status+=("Redis: ✓")
    else
        services_status+=("Redis: ✗")
    fi
    
    # Display status
    for status in "${services_status[@]}"; do
        if [[ "$status" == *"✓"* ]]; then
            success "$status"
        else
            warning "$status"
        fi
    done
    
    # Count available services
    local available_count=$(printf '%s\n' "${services_status[@]}" | grep -c "✓" || true)
    local total_count=${#services_status[@]}
    
    info "Services available: $available_count/$total_count"
    
    if [[ $available_count -eq 0 ]]; then
        error "No database services are available. Please start the services first."
        exit 1
    fi
}

# List available backups for all databases
list_all_backups() {
    log "Available backups across all databases:"
    echo ""
    
    for db_name in postgresql neo4j milvus redis; do
        local db_backup_dir="$BACKUP_ROOT_DIR/$db_name"
        if [[ -d "$db_backup_dir" ]]; then
            echo "=== $db_name backups ==="
            
            local backup_count=$(find "$db_backup_dir" -type f \( -name "*.sql" -o -name "*.cypher" -o -name "*.json" -o -name "*.rdb" -o -name "*.dump" \) 2>/dev/null | wc -l)
            
            if [[ $backup_count -gt 0 ]]; then
                echo "Total backups: $backup_count"
                echo "Recent backups:"
                find "$db_backup_dir" -type f \( -name "*.sql" -o -name "*.cypher" -o -name "*.json" -o -name "*.rdb" -o -name "*.dump" \) -mtime -7 -exec ls -lh {} \; 2>/dev/null | head -5 | while read -r line; do
                    echo "  $line"
                done
            else
                echo "No backups found"
            fi
            echo ""
        else
            echo "=== $db_name backups ==="
            echo "Backup directory not found: $db_backup_dir"
            echo ""
        fi
    done
}

# Get latest backup file for a database
get_latest_backup() {
    local db_name="$1"
    local backup_type="${2:-full}"
    local db_backup_dir="$BACKUP_ROOT_DIR/$db_name"
    
    if [[ ! -d "$db_backup_dir" ]]; then
        return 1
    fi
    
    case "$db_name" in
        "postgresql")
            case "$backup_type" in
                "schema")
                    find "$db_backup_dir" -name "schema_*.sql" -type f -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -1 | cut -d' ' -f2-
                    ;;
                "data")
                    find "$db_backup_dir" -name "data_*.sql" -type f -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -1 | cut -d' ' -f2-
                    ;;
                "compressed")
                    find "$db_backup_dir" -name "compressed_*.dump" -type f -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -1 | cut -d' ' -f2-
                    ;;
                *)
                    find "$db_backup_dir" -name "full_*.sql" -type f -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -1 | cut -d' ' -f2-
                    ;;
            esac
            ;;
        "neo4j")
            case "$backup_type" in
                "schema")
                    find "$db_backup_dir" -name "schema_*.cypher" -type f -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -1 | cut -d' ' -f2-
                    ;;
                "json")
                    find "$db_backup_dir" -name "json_export_*.json" -type f -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -1 | cut -d' ' -f2-
                    ;;
                *)
                    find "$db_backup_dir" -name "cypher_export_*.cypher" -type f -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -1 | cut -d' ' -f2-
                    ;;
            esac
            ;;
        "milvus")
            find "$db_backup_dir" -name "system_info_*.json" -type f -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -1 | cut -d' ' -f2-
            ;;
        "redis")
            find "$db_backup_dir" -name "redis_dump_*.rdb" -type f -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -1 | cut -d' ' -f2-
            ;;
    esac
}

# Restore PostgreSQL
restore_postgresql() {
    log "Starting PostgreSQL restore..."
    
    local restore_script="./database/postgresql/restore.sh"
    if [[ -f "$restore_script" ]]; then
        case "$RESTORE_TYPE" in
            "latest")
                BACKUP_DIR="$BACKUP_ROOT_DIR/postgresql" "$restore_script" latest
                ;;
            "schema")
                BACKUP_DIR="$BACKUP_ROOT_DIR/postgresql" "$restore_script" latest-schema
                ;;
            "file")
                if [[ -n "$RESTORE_FILE" ]]; then
                    BACKUP_DIR="$BACKUP_ROOT_DIR/postgresql" "$restore_script" file "$RESTORE_FILE"
                else
                    error "RESTORE_FILE not specified for file restore"
                    return 1
                fi
                ;;
            *)
                BACKUP_DIR="$BACKUP_ROOT_DIR/postgresql" "$restore_script" latest
                ;;
        esac
    else
        warning "PostgreSQL restore script not found at $restore_script"
        return 1
    fi
}

# Restore Neo4j
restore_neo4j() {
    log "Starting Neo4j restore..."
    
    local restore_script="./scripts/restore-neo4j.sh"
    if [[ -f "$restore_script" ]]; then
        case "$RESTORE_TYPE" in
            "latest")
                BACKUP_DIR="$BACKUP_ROOT_DIR/neo4j" "$restore_script" latest
                ;;
            "schema")
                BACKUP_DIR="$BACKUP_ROOT_DIR/neo4j" "$restore_script" schema
                ;;
            "file")
                if [[ -n "$RESTORE_FILE" ]]; then
                    BACKUP_DIR="$BACKUP_ROOT_DIR/neo4j" "$restore_script" file "$RESTORE_FILE"
                else
                    error "RESTORE_FILE not specified for file restore"
                    return 1
                fi
                ;;
            *)
                BACKUP_DIR="$BACKUP_ROOT_DIR/neo4j" "$restore_script" latest
                ;;
        esac
    else
        warning "Neo4j restore script not found at $restore_script"
        return 1
    fi
}

# Restore Milvus
restore_milvus() {
    log "Starting Milvus restore..."
    
    local restore_script="./scripts/restore-milvus.py"
    if [[ -f "$restore_script" ]]; then
        case "$RESTORE_TYPE" in
            "latest")
                BACKUP_DIR="$BACKUP_ROOT_DIR/milvus" python3 "$restore_script" system --latest
                ;;
            "file")
                if [[ -n "$RESTORE_FILE" ]]; then
                    BACKUP_DIR="$BACKUP_ROOT_DIR/milvus" python3 "$restore_script" file --file "$RESTORE_FILE"
                else
                    error "RESTORE_FILE not specified for file restore"
                    return 1
                fi
                ;;
            *)
                BACKUP_DIR="$BACKUP_ROOT_DIR/milvus" python3 "$restore_script" system --latest
                ;;
        esac
    else
        warning "Milvus restore script not found at $restore_script"
        return 1
    fi
}

# Restore Redis
restore_redis() {
    log "Starting Redis restore..."
    
    local restore_script="./scripts/restore-redis.sh"
    if [[ -f "$restore_script" ]]; then
        case "$RESTORE_TYPE" in
            "latest")
                BACKUP_DIR="$BACKUP_ROOT_DIR/redis" "$restore_script" latest
                ;;
            "file")
                if [[ -n "$RESTORE_FILE" ]]; then
                    BACKUP_DIR="$BACKUP_ROOT_DIR/redis" "$restore_script" file "$RESTORE_FILE"
                else
                    error "RESTORE_FILE not specified for file restore"
                    return 1
                fi
                ;;
            *)
                BACKUP_DIR="$BACKUP_ROOT_DIR/redis" "$restore_script" latest
                ;;
        esac
    else
        warning "Redis restore script not found at $restore_script"
        return 1
    fi
}

# Confirm restore operation
confirm_restore() {
    if [[ "$FORCE_RESTORE" == "true" ]]; then
        return 0
    fi
    
    warning "This operation will overwrite existing database data!"
    echo ""
    echo "Restore configuration:"
    echo "  Backup directory: $BACKUP_ROOT_DIR"
    echo "  Restore type: $RESTORE_TYPE"
    echo "  Parallel restores: $PARALLEL_RESTORES"
    echo ""
    
    echo -n "Are you sure you want to continue? (y/N): "
    read -r confirmation
    if [[ "$confirmation" != "y" && "$confirmation" != "Y" ]]; then
        log "Restore cancelled by user"
        exit 0
    fi
}

# Run restores in parallel
run_parallel_restores() {
    log "Running database restores in parallel..."
    
    local pids=()
    local restore_results=()
    
    # Start PostgreSQL restore
    if pg_isready -h "${POSTGRES_HOST:-localhost}" -p "${POSTGRES_PORT:-5432}" -U "${POSTGRES_USER:-ml_user}" -d "${POSTGRES_DB:-multimodal_librarian}" >/dev/null 2>&1; then
        restore_postgresql &
        pids+=($!)
        restore_results+=("PostgreSQL")
    fi
    
    # Start Neo4j restore
    if cypher-shell -a "bolt://${NEO4J_HOST:-localhost}:${NEO4J_PORT:-7687}" -u "${NEO4J_USER:-neo4j}" -p "${NEO4J_PASSWORD:-ml_password}" "RETURN 1" >/dev/null 2>&1; then
        restore_neo4j &
        pids+=($!)
        restore_results+=("Neo4j")
    fi
    
    # Start Milvus restore
    if curl -s -f "http://${MILVUS_HOST:-localhost}:${MILVUS_HTTP_PORT:-9091}/healthz" >/dev/null 2>&1; then
        restore_milvus &
        pids+=($!)
        restore_results+=("Milvus")
    fi
    
    # Start Redis restore
    if redis-cli -h "${REDIS_HOST:-localhost}" -p "${REDIS_PORT:-6379}" ping >/dev/null 2>&1; then
        restore_redis &
        pids+=($!)
        restore_results+=("Redis")
    fi
    
    # Wait for all restores to complete
    local failed_restores=()
    for i in "${!pids[@]}"; do
        local pid=${pids[$i]}
        local service=${restore_results[$i]}
        
        if wait "$pid"; then
            success "$service restore completed"
        else
            error "$service restore failed"
            failed_restores+=("$service")
        fi
    done
    
    # Report results
    if [[ ${#failed_restores[@]} -eq 0 ]]; then
        success "All parallel restores completed successfully"
    else
        warning "Some restores failed: ${failed_restores[*]}"
    fi
}

# Run restores sequentially
run_sequential_restores() {
    log "Running database restores sequentially..."
    
    local failed_restores=()
    
    # PostgreSQL restore
    if pg_isready -h "${POSTGRES_HOST:-localhost}" -p "${POSTGRES_PORT:-5432}" -U "${POSTGRES_USER:-ml_user}" -d "${POSTGRES_DB:-multimodal_librarian}" >/dev/null 2>&1; then
        if restore_postgresql; then
            success "PostgreSQL restore completed"
        else
            error "PostgreSQL restore failed"
            failed_restores+=("PostgreSQL")
        fi
    else
        warning "PostgreSQL not available, skipping restore"
    fi
    
    # Neo4j restore
    if cypher-shell -a "bolt://${NEO4J_HOST:-localhost}:${NEO4J_PORT:-7687}" -u "${NEO4J_USER:-neo4j}" -p "${NEO4J_PASSWORD:-ml_password}" "RETURN 1" >/dev/null 2>&1; then
        if restore_neo4j; then
            success "Neo4j restore completed"
        else
            error "Neo4j restore failed"
            failed_restores+=("Neo4j")
        fi
    else
        warning "Neo4j not available, skipping restore"
    fi
    
    # Milvus restore
    if curl -s -f "http://${MILVUS_HOST:-localhost}:${MILVUS_HTTP_PORT:-9091}/healthz" >/dev/null 2>&1; then
        if restore_milvus; then
            success "Milvus restore completed"
        else
            error "Milvus restore failed"
            failed_restores+=("Milvus")
        fi
    else
        warning "Milvus not available, skipping restore"
    fi
    
    # Redis restore
    if redis-cli -h "${REDIS_HOST:-localhost}" -p "${REDIS_PORT:-6379}" ping >/dev/null 2>&1; then
        if restore_redis; then
            success "Redis restore completed"
        else
            error "Redis restore failed"
            failed_restores+=("Redis")
        fi
    else
        warning "Redis not available, skipping restore"
    fi
    
    # Report results
    if [[ ${#failed_restores[@]} -eq 0 ]]; then
        success "All sequential restores completed successfully"
    else
        warning "Some restores failed: ${failed_restores[*]}"
    fi
}

# Verify restored data
verify_restored_data() {
    log "Verifying restored data..."
    
    local verification_errors=0
    
    # Verify PostgreSQL
    if pg_isready -h "${POSTGRES_HOST:-localhost}" -p "${POSTGRES_PORT:-5432}" -U "${POSTGRES_USER:-ml_user}" -d "${POSTGRES_DB:-multimodal_librarian}" >/dev/null 2>&1; then
        local table_count=$(psql -h "${POSTGRES_HOST:-localhost}" -p "${POSTGRES_PORT:-5432}" -U "${POSTGRES_USER:-ml_user}" -d "${POSTGRES_DB:-multimodal_librarian}" -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';" 2>/dev/null | xargs || echo "0")
        if [[ $table_count -gt 0 ]]; then
            success "PostgreSQL verification passed ($table_count tables found)"
        else
            error "PostgreSQL verification failed (no tables found)"
            verification_errors=$((verification_errors + 1))
        fi
    fi
    
    # Verify Neo4j
    if cypher-shell -a "bolt://${NEO4J_HOST:-localhost}:${NEO4J_PORT:-7687}" -u "${NEO4J_USER:-neo4j}" -p "${NEO4J_PASSWORD:-ml_password}" "RETURN 1" >/dev/null 2>&1; then
        local node_count=$(cypher-shell -a "bolt://${NEO4J_HOST:-localhost}:${NEO4J_PORT:-7687}" -u "${NEO4J_USER:-neo4j}" -p "${NEO4J_PASSWORD:-ml_password}" "MATCH (n) RETURN count(n)" --format plain 2>/dev/null | tail -1 | xargs || echo "0")
        if [[ $node_count -gt 0 ]]; then
            success "Neo4j verification passed ($node_count nodes found)"
        else
            warning "Neo4j verification: no nodes found (may be expected for empty restore)"
        fi
    fi
    
    # Verify Milvus
    if curl -s -f "http://${MILVUS_HOST:-localhost}:${MILVUS_HTTP_PORT:-9091}/healthz" >/dev/null 2>&1; then
        success "Milvus verification passed (service is accessible)"
    fi
    
    # Verify Redis
    if redis-cli -h "${REDIS_HOST:-localhost}" -p "${REDIS_PORT:-6379}" ping >/dev/null 2>&1; then
        local key_count=$(redis-cli -h "${REDIS_HOST:-localhost}" -p "${REDIS_PORT:-6379}" dbsize 2>/dev/null || echo "0")
        success "Redis verification passed ($key_count keys found)"
    fi
    
    if [[ $verification_errors -eq 0 ]]; then
        success "All database verifications passed"
    else
        warning "$verification_errors database verifications failed"
    fi
    
    return $verification_errors
}

# Show restore summary
show_restore_summary() {
    log "Database restore summary:"
    echo ""
    
    echo "Restore Configuration:"
    echo "  Backup directory: $BACKUP_ROOT_DIR"
    echo "  Restore type: $RESTORE_TYPE"
    echo "  Parallel execution: $PARALLEL_RESTORES"
    echo "  Force restore: $FORCE_RESTORE"
    echo ""
    
    echo "Database Status After Restore:"
    
    # PostgreSQL status
    if pg_isready -h "${POSTGRES_HOST:-localhost}" -p "${POSTGRES_PORT:-5432}" -U "${POSTGRES_USER:-ml_user}" -d "${POSTGRES_DB:-multimodal_librarian}" >/dev/null 2>&1; then
        local pg_size=$(psql -h "${POSTGRES_HOST:-localhost}" -p "${POSTGRES_PORT:-5432}" -U "${POSTGRES_USER:-ml_user}" -d "${POSTGRES_DB:-multimodal_librarian}" -t -c "SELECT pg_size_pretty(pg_database_size('${POSTGRES_DB:-multimodal_librarian}'));" 2>/dev/null | xargs || echo "Unknown")
        echo "  PostgreSQL: ✓ (Size: $pg_size)"
    else
        echo "  PostgreSQL: ✗"
    fi
    
    # Neo4j status
    if cypher-shell -a "bolt://${NEO4J_HOST:-localhost}:${NEO4J_PORT:-7687}" -u "${NEO4J_USER:-neo4j}" -p "${NEO4J_PASSWORD:-ml_password}" "RETURN 1" >/dev/null 2>&1; then
        echo "  Neo4j: ✓"
    else
        echo "  Neo4j: ✗"
    fi
    
    # Milvus status
    if curl -s -f "http://${MILVUS_HOST:-localhost}:${MILVUS_HTTP_PORT:-9091}/healthz" >/dev/null 2>&1; then
        echo "  Milvus: ✓"
    else
        echo "  Milvus: ✗"
    fi
    
    # Redis status
    if redis-cli -h "${REDIS_HOST:-localhost}" -p "${REDIS_PORT:-6379}" ping >/dev/null 2>&1; then
        echo "  Redis: ✓"
    else
        echo "  Redis: ✗"
    fi
}

# Main execution
main() {
    log "Starting comprehensive database restore"
    
    case "${1:-latest}" in
        "latest"|"schema"|"file")
            RESTORE_TYPE="$1"
            if [[ "$1" == "file" && -n "$2" ]]; then
                RESTORE_FILE="$2"
            fi
            
            check_backup_directories
            check_services
            confirm_restore
            
            if [[ "$PARALLEL_RESTORES" == "true" ]]; then
                run_parallel_restores
            else
                run_sequential_restores
            fi
            
            verify_restored_data
            ;;
        "list")
            list_all_backups
            ;;
        "verify")
            check_services
            verify_restored_data
            ;;
        "help"|"--help"|"-h")
            echo "Usage: $0 [latest|schema|file <path>|list|verify|help]"
            echo ""
            echo "Restore Types:"
            echo "  latest      - Restore from latest backups (default)"
            echo "  schema      - Restore schema-only from latest schema backups"
            echo "  file <path> - Restore from specific backup file"
            echo ""
            echo "Information:"
            echo "  list        - List available backups"
            echo "  verify      - Verify current database state"
            echo "  help        - Show this help message"
            echo ""
            echo "Environment Variables:"
            echo "  BACKUP_DIR         - Root backup directory (default: ./backups)"
            echo "  PARALLEL_RESTORES  - Run restores in parallel (default: false)"
            echo "  FORCE_RESTORE      - Skip confirmation prompts (default: false)"
            echo "  RESTORE_TYPE       - Default restore type (default: latest)"
            echo ""
            echo "Database Connection Variables:"
            echo "  POSTGRES_HOST, POSTGRES_PORT, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB"
            echo "  NEO4J_HOST, NEO4J_PORT, NEO4J_USER, NEO4J_PASSWORD"
            echo "  MILVUS_HOST, MILVUS_PORT, MILVUS_HTTP_PORT"
            echo "  REDIS_HOST, REDIS_PORT"
            echo ""
            echo "Examples:"
            echo "  $0 latest                    # Restore all databases from latest backups"
            echo "  $0 schema                    # Restore schemas only"
            echo "  $0 file /path/to/backup.sql  # Restore from specific file"
            echo "  PARALLEL_RESTORES=true $0    # Run restores in parallel"
            echo "  FORCE_RESTORE=true $0        # Skip confirmation prompts"
            exit 0
            ;;
        *)
            error "Unknown action: $1"
            echo "Use '$0 help' for usage information"
            exit 1
            ;;
    esac
    
    # Show summary after restore operations
    if [[ "$1" != "list" && "$1" != "verify" ]]; then
        echo ""
        show_restore_summary
    fi
    
    success "Database restore operation completed"
}

# Run main function with all arguments
main "$@"