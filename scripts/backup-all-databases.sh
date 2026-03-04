#!/bin/bash

# Comprehensive Database Backup Script for Multimodal Librarian Local Development
# This script creates backups of all database services (PostgreSQL, Neo4j, Milvus, Redis)

set -e

# Configuration
BACKUP_ROOT_DIR="${BACKUP_DIR:-./backups}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
PARALLEL_BACKUPS="${PARALLEL_BACKUPS:-true}"
BACKUP_TYPE="${BACKUP_TYPE:-full}"

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

# Create backup directories
create_backup_directories() {
    log "Creating backup directories..."
    
    mkdir -p "$BACKUP_ROOT_DIR"/{postgresql,neo4j,milvus,redis,system}
    
    success "Backup directories created"
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

# Backup PostgreSQL
backup_postgresql() {
    log "Starting PostgreSQL backup..."
    
    local backup_script="./database/postgresql/backup.sh"
    if [[ -f "$backup_script" ]]; then
        BACKUP_DIR="$BACKUP_ROOT_DIR/postgresql" "$backup_script" "$BACKUP_TYPE"
    else
        warning "PostgreSQL backup script not found at $backup_script"
        return 1
    fi
}

# Backup Neo4j
backup_neo4j() {
    log "Starting Neo4j backup..."
    
    local backup_script="./scripts/backup-neo4j.sh"
    if [[ -f "$backup_script" ]]; then
        BACKUP_DIR="$BACKUP_ROOT_DIR/neo4j" "$backup_script" "$BACKUP_TYPE"
    else
        warning "Neo4j backup script not found at $backup_script"
        return 1
    fi
}

# Backup Milvus
backup_milvus() {
    log "Starting Milvus backup..."
    
    local backup_script="./scripts/backup-milvus.py"
    if [[ -f "$backup_script" ]]; then
        BACKUP_DIR="$BACKUP_ROOT_DIR/milvus" python3 "$backup_script" all --type "$BACKUP_TYPE"
    else
        warning "Milvus backup script not found at $backup_script"
        return 1
    fi
}

# Backup Redis
backup_redis() {
    log "Starting Redis backup..."
    
    local redis_backup_dir="$BACKUP_ROOT_DIR/redis"
    mkdir -p "$redis_backup_dir"
    
    # Create Redis backup using BGSAVE
    if redis-cli -h "${REDIS_HOST:-localhost}" -p "${REDIS_PORT:-6379}" BGSAVE >/dev/null 2>&1; then
        # Wait for background save to complete
        while redis-cli -h "${REDIS_HOST:-localhost}" -p "${REDIS_PORT:-6379}" LASTSAVE | grep -q "$(redis-cli -h "${REDIS_HOST:-localhost}" -p "${REDIS_PORT:-6379}" LASTSAVE)"; do
            sleep 1
        done
        
        # Copy the dump file
        if command -v docker-compose >/dev/null 2>&1; then
            docker-compose -f docker-compose.local.yml exec -T redis cp /data/dump.rdb "/backups/redis_dump_${TIMESTAMP}.rdb" 2>/dev/null || {
                # Fallback: copy from host if volume is mounted
                if [[ -f "./data/redis/dump.rdb" ]]; then
                    cp "./data/redis/dump.rdb" "$redis_backup_dir/redis_dump_${TIMESTAMP}.rdb"
                    success "Redis backup created: $redis_backup_dir/redis_dump_${TIMESTAMP}.rdb"
                else
                    warning "Could not locate Redis dump file"
                    return 1
                fi
            }
        else
            warning "Docker not available, cannot backup Redis"
            return 1
        fi
    else
        warning "Failed to create Redis backup"
        return 1
    fi
}

# Create system backup (metadata about the backup)
create_system_backup() {
    log "Creating system backup metadata..."
    
    local system_backup_file="$BACKUP_ROOT_DIR/system/backup_metadata_${TIMESTAMP}.json"
    
    # Collect system information
    cat > "$system_backup_file" << EOF
{
  "backup_timestamp": "$(date -Iseconds)",
  "backup_type": "$BACKUP_TYPE",
  "environment": {
    "ML_ENVIRONMENT": "${ML_ENVIRONMENT:-local}",
    "DATABASE_TYPE": "${DATABASE_TYPE:-local}"
  },
  "services": {
    "postgresql": {
      "host": "${POSTGRES_HOST:-localhost}",
      "port": "${POSTGRES_PORT:-5432}",
      "database": "${POSTGRES_DB:-multimodal_librarian}",
      "user": "${POSTGRES_USER:-ml_user}"
    },
    "neo4j": {
      "host": "${NEO4J_HOST:-localhost}",
      "port": "${NEO4J_PORT:-7687}",
      "user": "${NEO4J_USER:-neo4j}"
    },
    "milvus": {
      "host": "${MILVUS_HOST:-localhost}",
      "port": "${MILVUS_PORT:-19530}"
    },
    "redis": {
      "host": "${REDIS_HOST:-localhost}",
      "port": "${REDIS_PORT:-6379}"
    }
  },
  "backup_structure": {
    "postgresql": "$BACKUP_ROOT_DIR/postgresql",
    "neo4j": "$BACKUP_ROOT_DIR/neo4j",
    "milvus": "$BACKUP_ROOT_DIR/milvus",
    "redis": "$BACKUP_ROOT_DIR/redis",
    "system": "$BACKUP_ROOT_DIR/system"
  }
}
EOF
    
    success "System backup metadata created: $system_backup_file"
}

# Run backups in parallel
run_parallel_backups() {
    log "Running database backups in parallel..."
    
    local pids=()
    local backup_results=()
    
    # Start PostgreSQL backup
    if pg_isready -h "${POSTGRES_HOST:-localhost}" -p "${POSTGRES_PORT:-5432}" -U "${POSTGRES_USER:-ml_user}" -d "${POSTGRES_DB:-multimodal_librarian}" >/dev/null 2>&1; then
        backup_postgresql &
        pids+=($!)
        backup_results+=("PostgreSQL")
    fi
    
    # Start Neo4j backup
    if cypher-shell -a "bolt://${NEO4J_HOST:-localhost}:${NEO4J_PORT:-7687}" -u "${NEO4J_USER:-neo4j}" -p "${NEO4J_PASSWORD:-ml_password}" "RETURN 1" >/dev/null 2>&1; then
        backup_neo4j &
        pids+=($!)
        backup_results+=("Neo4j")
    fi
    
    # Start Milvus backup
    if curl -s -f "http://${MILVUS_HOST:-localhost}:${MILVUS_HTTP_PORT:-9091}/healthz" >/dev/null 2>&1; then
        backup_milvus &
        pids+=($!)
        backup_results+=("Milvus")
    fi
    
    # Start Redis backup
    if redis-cli -h "${REDIS_HOST:-localhost}" -p "${REDIS_PORT:-6379}" ping >/dev/null 2>&1; then
        backup_redis &
        pids+=($!)
        backup_results+=("Redis")
    fi
    
    # Wait for all backups to complete
    local failed_backups=()
    for i in "${!pids[@]}"; do
        local pid=${pids[$i]}
        local service=${backup_results[$i]}
        
        if wait "$pid"; then
            success "$service backup completed"
        else
            error "$service backup failed"
            failed_backups+=("$service")
        fi
    done
    
    # Report results
    if [[ ${#failed_backups[@]} -eq 0 ]]; then
        success "All parallel backups completed successfully"
    else
        warning "Some backups failed: ${failed_backups[*]}"
    fi
}

# Run backups sequentially
run_sequential_backups() {
    log "Running database backups sequentially..."
    
    local failed_backups=()
    
    # PostgreSQL backup
    if pg_isready -h "${POSTGRES_HOST:-localhost}" -p "${POSTGRES_PORT:-5432}" -U "${POSTGRES_USER:-ml_user}" -d "${POSTGRES_DB:-multimodal_librarian}" >/dev/null 2>&1; then
        if backup_postgresql; then
            success "PostgreSQL backup completed"
        else
            error "PostgreSQL backup failed"
            failed_backups+=("PostgreSQL")
        fi
    else
        warning "PostgreSQL not available, skipping backup"
    fi
    
    # Neo4j backup
    if cypher-shell -a "bolt://${NEO4J_HOST:-localhost}:${NEO4J_PORT:-7687}" -u "${NEO4J_USER:-neo4j}" -p "${NEO4J_PASSWORD:-ml_password}" "RETURN 1" >/dev/null 2>&1; then
        if backup_neo4j; then
            success "Neo4j backup completed"
        else
            error "Neo4j backup failed"
            failed_backups+=("Neo4j")
        fi
    else
        warning "Neo4j not available, skipping backup"
    fi
    
    # Milvus backup
    if curl -s -f "http://${MILVUS_HOST:-localhost}:${MILVUS_HTTP_PORT:-9091}/healthz" >/dev/null 2>&1; then
        if backup_milvus; then
            success "Milvus backup completed"
        else
            error "Milvus backup failed"
            failed_backups+=("Milvus")
        fi
    else
        warning "Milvus not available, skipping backup"
    fi
    
    # Redis backup
    if redis-cli -h "${REDIS_HOST:-localhost}" -p "${REDIS_PORT:-6379}" ping >/dev/null 2>&1; then
        if backup_redis; then
            success "Redis backup completed"
        else
            error "Redis backup failed"
            failed_backups+=("Redis")
        fi
    else
        warning "Redis not available, skipping backup"
    fi
    
    # Report results
    if [[ ${#failed_backups[@]} -eq 0 ]]; then
        success "All sequential backups completed successfully"
    else
        warning "Some backups failed: ${failed_backups[*]}"
    fi
}

# Clean up old backups across all databases
cleanup_old_backups() {
    log "Cleaning up old backups (keeping last 7 days)..."
    
    local cleanup_count=0
    
    # Clean up each database backup directory
    for db_dir in "$BACKUP_ROOT_DIR"/{postgresql,neo4j,milvus,redis,system}; do
        if [[ -d "$db_dir" ]]; then
            local files_before=$(find "$db_dir" -type f | wc -l)
            find "$db_dir" -type f -mtime +7 -delete 2>/dev/null || true
            local files_after=$(find "$db_dir" -type f | wc -l)
            local deleted=$((files_before - files_after))
            cleanup_count=$((cleanup_count + deleted))
            
            if [[ $deleted -gt 0 ]]; then
                log "Cleaned up $deleted files from $db_dir"
            fi
        fi
    done
    
    if [[ $cleanup_count -gt 0 ]]; then
        success "Cleaned up $cleanup_count old backup files total"
    else
        log "No old backup files to clean up"
    fi
}

# Show comprehensive backup statistics
show_backup_stats() {
    log "Comprehensive backup statistics:"
    echo "Backup root directory: $BACKUP_ROOT_DIR"
    echo ""
    
    if [[ ! -d "$BACKUP_ROOT_DIR" ]]; then
        warning "Backup directory does not exist"
        return 1
    fi
    
    # Overall statistics
    local total_files=$(find "$BACKUP_ROOT_DIR" -type f | wc -l)
    local total_size=$(du -sh "$BACKUP_ROOT_DIR" 2>/dev/null | cut -f1 || echo "Unknown")
    
    echo "Overall Statistics:"
    echo "  Total backup files: $total_files"
    echo "  Total size: $total_size"
    echo ""
    
    # Per-database statistics
    for db_name in postgresql neo4j milvus redis system; do
        local db_dir="$BACKUP_ROOT_DIR/$db_name"
        if [[ -d "$db_dir" ]]; then
            local db_files=$(find "$db_dir" -type f | wc -l)
            local db_size=$(du -sh "$db_dir" 2>/dev/null | cut -f1 || echo "Unknown")
            
            echo "$db_name backups:"
            echo "  Files: $db_files"
            echo "  Size: $db_size"
            
            # Show recent files
            local recent_files=$(find "$db_dir" -type f -mtime -1 | head -3)
            if [[ -n "$recent_files" ]]; then
                echo "  Recent files:"
                echo "$recent_files" | while read -r file; do
                    echo "    $(basename "$file")"
                done
            fi
            echo ""
        fi
    done
}

# Verify backup integrity
verify_backups() {
    log "Verifying backup integrity..."
    
    local verification_errors=0
    
    # Verify PostgreSQL backups
    for sql_file in "$BACKUP_ROOT_DIR/postgresql"/*.sql; do
        if [[ -f "$sql_file" ]]; then
            if ! grep -q "PostgreSQL database dump\|CREATE\|INSERT" "$sql_file" 2>/dev/null; then
                error "PostgreSQL backup appears corrupted: $(basename "$sql_file")"
                verification_errors=$((verification_errors + 1))
            fi
        fi
    done
    
    # Verify Neo4j backups
    for cypher_file in "$BACKUP_ROOT_DIR/neo4j"/*.cypher; do
        if [[ -f "$cypher_file" ]]; then
            if ! grep -q "CREATE\|MERGE\|MATCH" "$cypher_file" 2>/dev/null; then
                error "Neo4j backup appears corrupted: $(basename "$cypher_file")"
                verification_errors=$((verification_errors + 1))
            fi
        fi
    done
    
    # Verify Milvus backups
    for json_file in "$BACKUP_ROOT_DIR/milvus"/**/*.json; do
        if [[ -f "$json_file" ]]; then
            if ! python3 -m json.tool "$json_file" >/dev/null 2>&1; then
                error "Milvus backup appears corrupted: $(basename "$json_file")"
                verification_errors=$((verification_errors + 1))
            fi
        fi
    done
    
    # Verify Redis backups
    for rdb_file in "$BACKUP_ROOT_DIR/redis"/*.rdb; do
        if [[ -f "$rdb_file" ]]; then
            # Basic file size check (RDB files should not be empty)
            if [[ ! -s "$rdb_file" ]]; then
                error "Redis backup appears empty: $(basename "$rdb_file")"
                verification_errors=$((verification_errors + 1))
            fi
        fi
    done
    
    if [[ $verification_errors -eq 0 ]]; then
        success "All backups passed integrity verification"
    else
        warning "$verification_errors backup files failed verification"
    fi
    
    return $verification_errors
}

# Main execution
main() {
    log "Starting comprehensive database backup"
    
    case "${1:-full}" in
        "full"|"schema"|"data"|"compressed")
            BACKUP_TYPE="$1"
            create_backup_directories
            check_services
            
            if [[ "$PARALLEL_BACKUPS" == "true" ]]; then
                run_parallel_backups
            else
                run_sequential_backups
            fi
            
            create_system_backup
            ;;
        "cleanup")
            cleanup_old_backups
            ;;
        "stats")
            show_backup_stats
            ;;
        "verify")
            verify_backups
            ;;
        "help"|"--help"|"-h")
            echo "Usage: $0 [full|schema|data|compressed|cleanup|stats|verify|help]"
            echo ""
            echo "Backup Types:"
            echo "  full        - Create full backups of all databases (default)"
            echo "  schema      - Create schema-only backups"
            echo "  data        - Create data-only backups"
            echo "  compressed  - Create compressed backups"
            echo ""
            echo "Maintenance:"
            echo "  cleanup     - Remove backups older than 7 days"
            echo "  stats       - Show backup statistics"
            echo "  verify      - Verify backup integrity"
            echo "  help        - Show this help message"
            echo ""
            echo "Environment Variables:"
            echo "  BACKUP_DIR         - Root backup directory (default: ./backups)"
            echo "  PARALLEL_BACKUPS   - Run backups in parallel (default: true)"
            echo "  BACKUP_TYPE        - Default backup type (default: full)"
            echo ""
            echo "Database Connection Variables:"
            echo "  POSTGRES_HOST, POSTGRES_PORT, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB"
            echo "  NEO4J_HOST, NEO4J_PORT, NEO4J_USER, NEO4J_PASSWORD"
            echo "  MILVUS_HOST, MILVUS_PORT, MILVUS_HTTP_PORT"
            echo "  REDIS_HOST, REDIS_PORT"
            exit 0
            ;;
        *)
            error "Unknown action: $1"
            echo "Use '$0 help' for usage information"
            exit 1
            ;;
    esac
    
    # Show stats after backup operations
    if [[ "$1" != "stats" && "$1" != "cleanup" && "$1" != "verify" ]]; then
        echo ""
        show_backup_stats
    fi
    
    success "Database backup operation completed"
}

# Run main function with all arguments
main "$@"