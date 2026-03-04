#!/bin/bash

# Comprehensive Database Management Script for Multimodal Librarian
# This script provides a unified interface for all database operations including
# reset, cleanup, backup, restore, and maintenance tasks.

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
NC='\033[0m' # No Color

# Logging functions
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

header() {
    echo -e "${WHITE}$1${NC}"
}

# Show main help
show_help() {
    cat << EOF
$(header "Database Management Script for Multimodal Librarian")

USAGE:
    $0 <COMMAND> [OPTIONS]

COMMANDS:
    $(header "Reset Operations:")
    reset-all           Reset all databases (PostgreSQL, Neo4j, Milvus, Redis)
    reset-postgresql    Reset only PostgreSQL database
    reset-neo4j         Reset only Neo4j database
    reset-milvus        Reset only Milvus/OpenSearch database
    reset-redis         Reset only Redis database

    $(header "Cleanup Operations:")
    cleanup             Clean old data from databases
    cleanup-age         Clean data older than specified days
    cleanup-size        Clean data when databases exceed size limits
    cleanup-temp        Clean temporary and cache data only

    $(header "Backup & Restore:")
    backup              Create backup of all databases
    backup-single       Create backup of specific database
    restore             Restore from backup
    restore-single      Restore specific database from backup

    $(header "Maintenance:")
    health              Check health of all database services
    status              Show status and statistics of all databases
    optimize            Optimize database performance (VACUUM, etc.)
    migrate             Run database migrations

    $(header "Development:")
    seed                Seed databases with sample data
    dev-reset           Quick development reset (data only, with seed)
    dev-setup           Set up development environment from scratch

    $(header "Information:")
    list-backups        List available backups
    show-config         Show current database configuration
    help                Show this help message

GLOBAL OPTIONS:
    --environment <env>     Force environment (local|aws)
    --backup-dir <dir>      Backup directory (default: ./backups)
    --force                 Skip confirmation prompts (dangerous!)
    --dry-run               Show what would be done without making changes
    --verbose               Enable verbose output
    --quiet                 Suppress non-error output

EXAMPLES:
    # Quick development reset with sample data
    $0 dev-reset

    # Full production-safe reset with backup
    $0 reset-all --backup --environment local

    # Clean data older than 30 days
    $0 cleanup-age 30

    # Check database health
    $0 health

    # Create backup before maintenance
    $0 backup && $0 optimize

    # Reset specific database
    $0 reset-postgresql --data-only --migrate

ENVIRONMENT VARIABLES:
    ML_ENVIRONMENT          Set environment (local|aws)
    DATABASE_TYPE           Set database type (local|aws)
    BACKUP_DIR              Default backup directory
    
    Database Connection Variables:
    POSTGRES_HOST, POSTGRES_PORT, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB
    NEO4J_HOST, NEO4J_PORT, NEO4J_USER, NEO4J_PASSWORD
    MILVUS_HOST, MILVUS_PORT
    REDIS_HOST, REDIS_PORT

SAFETY FEATURES:
    - Confirmation prompts for destructive operations
    - Automatic backup creation for reset operations
    - Dry run mode to preview changes
    - Environment detection and validation
    - Service health checks before operations
    - Comprehensive error handling and logging

For command-specific help, use: $0 <command> --help

EOF
}

# Check prerequisites
check_prerequisites() {
    local missing_tools=()
    
    # Check Python
    if ! command -v python3 >/dev/null 2>&1; then
        missing_tools+=("python3")
    fi
    
    # Check database tools (only warn, don't fail)
    local optional_tools=("pg_isready" "psql" "cypher-shell" "redis-cli" "curl")
    local missing_optional=()
    
    for tool in "${optional_tools[@]}"; do
        if ! command -v "$tool" >/dev/null 2>&1; then
            missing_optional+=("$tool")
        fi
    done
    
    if [[ ${#missing_tools[@]} -gt 0 ]]; then
        error "Missing required tools: ${missing_tools[*]}"
        info "Please install the missing tools and try again"
        exit 1
    fi
    
    if [[ ${#missing_optional[@]} -gt 0 ]]; then
        warning "Missing optional tools: ${missing_optional[*]}"
        info "Some database operations may not work properly"
    fi
}

# Check if services are running
check_services() {
    log "Checking database services..."
    
    local services_status=()
    
    # PostgreSQL
    if pg_isready -h "${POSTGRES_HOST:-localhost}" -p "${POSTGRES_PORT:-5432}" -U "${POSTGRES_USER:-ml_user}" -d "${POSTGRES_DB:-multimodal_librarian}" >/dev/null 2>&1; then
        services_status+=("PostgreSQL: ✓")
    else
        services_status+=("PostgreSQL: ✗")
    fi
    
    # Neo4j
    if cypher-shell -a "bolt://${NEO4J_HOST:-localhost}:${NEO4J_PORT:-7687}" -u "${NEO4J_USER:-neo4j}" -p "${NEO4J_PASSWORD:-ml_password}" "RETURN 1" >/dev/null 2>&1; then
        services_status+=("Neo4j: ✓")
    else
        services_status+=("Neo4j: ✗")
    fi
    
    # Milvus
    if curl -s -f "http://${MILVUS_HOST:-localhost}:${MILVUS_HTTP_PORT:-9091}/healthz" >/dev/null 2>&1; then
        services_status+=("Milvus: ✓")
    else
        services_status+=("Milvus: ✗")
    fi
    
    # Redis
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
    
    return $available_count
}

# Show environment information
show_environment() {
    header "Environment Information"
    echo "  ML_ENVIRONMENT: ${ML_ENVIRONMENT:-not set}"
    echo "  DATABASE_TYPE: ${DATABASE_TYPE:-not set}"
    echo "  Current directory: $(pwd)"
    echo "  Script directory: $SCRIPT_DIR"
    echo "  Project root: $PROJECT_ROOT"
    echo ""
}

# Parse global options
parse_global_options() {
    GLOBAL_ARGS=()
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --environment)
                if [[ -n "$2" ]]; then
                    export ML_ENVIRONMENT="$2"
                    GLOBAL_ARGS+=("--environment" "$2")
                    shift 2
                else
                    error "--environment requires a value"
                    exit 1
                fi
                ;;
            --backup-dir)
                if [[ -n "$2" ]]; then
                    export BACKUP_DIR="$2"
                    GLOBAL_ARGS+=("--backup-dir" "$2")
                    shift 2
                else
                    error "--backup-dir requires a value"
                    exit 1
                fi
                ;;
            --force)
                GLOBAL_ARGS+=("--force")
                shift
                ;;
            --dry-run)
                GLOBAL_ARGS+=("--dry-run")
                shift
                ;;
            --verbose|-v)
                GLOBAL_ARGS+=("--verbose")
                shift
                ;;
            --quiet|-q)
                GLOBAL_ARGS+=("--quiet")
                shift
                ;;
            *)
                # Not a global option, return remaining args
                echo "$@"
                return
                ;;
        esac
    done
}

# Execute Python script with global args
execute_python_script() {
    local script_name="$1"
    shift
    local script_path="$SCRIPT_DIR/$script_name"
    
    if [[ ! -f "$script_path" ]]; then
        error "Script not found: $script_path"
        return 1
    fi
    
    python3 "$script_path" "${GLOBAL_ARGS[@]}" "$@"
}

# Execute shell script with global args
execute_shell_script() {
    local script_name="$1"
    shift
    local script_path="$SCRIPT_DIR/$script_name"
    
    if [[ ! -f "$script_path" ]]; then
        error "Script not found: $script_path"
        return 1
    fi
    
    # Convert global args to environment variables for shell scripts
    for arg in "${GLOBAL_ARGS[@]}"; do
        case "$arg" in
            --force) export FORCE_OPERATION=true ;;
            --dry-run) export DRY_RUN=true ;;
            --verbose) export VERBOSE=true ;;
            --quiet) export QUIET=true ;;
        esac
    done
    
    "$script_path" "$@"
}

# Command implementations
cmd_reset_all() {
    log "Executing full database reset..."
    execute_python_script "reset-all-databases.py" --all "$@"
}

cmd_reset_postgresql() {
    log "Executing PostgreSQL reset..."
    execute_python_script "reset-postgresql.py" "$@"
}

cmd_reset_neo4j() {
    log "Executing Neo4j reset..."
    # For now, use the general reset script with neo4j filter
    execute_python_script "reset-all-databases.py" --databases neo4j "$@"
}

cmd_reset_milvus() {
    log "Executing Milvus reset..."
    execute_python_script "reset-all-databases.py" --databases milvus "$@"
}

cmd_reset_redis() {
    log "Executing Redis reset..."
    execute_python_script "reset-all-databases.py" --databases redis "$@"
}

cmd_cleanup() {
    log "Executing database cleanup..."
    execute_python_script "cleanup-database-data.py" "$@"
}

cmd_cleanup_age() {
    local days="$1"
    if [[ -z "$days" ]]; then
        error "cleanup-age requires number of days"
        info "Usage: $0 cleanup-age <days>"
        return 1
    fi
    shift
    
    log "Cleaning data older than $days days..."
    execute_python_script "cleanup-database-data.py" --age "$days" "$@"
}

cmd_cleanup_size() {
    local max_size="$1"
    if [[ -z "$max_size" ]]; then
        error "cleanup-size requires maximum size"
        info "Usage: $0 cleanup-size <size> (e.g., 1GB, 500MB)"
        return 1
    fi
    shift
    
    log "Cleaning databases exceeding $max_size..."
    execute_python_script "cleanup-database-data.py" --max-size "$max_size" "$@"
}

cmd_cleanup_temp() {
    log "Cleaning temporary and cache data..."
    execute_python_script "cleanup-database-data.py" --age 1 --types temp,cache "$@"
}

cmd_backup() {
    log "Creating database backup..."
    execute_shell_script "backup-all-databases.sh" "$@"
}

cmd_backup_single() {
    local database="$1"
    if [[ -z "$database" ]]; then
        error "backup-single requires database name"
        info "Usage: $0 backup-single <postgresql|neo4j|milvus|redis>"
        return 1
    fi
    shift
    
    log "Creating backup for $database..."
    # Use specific backup scripts if they exist
    case "$database" in
        postgresql)
            execute_shell_script "backup-postgresql.sh" "$@" || execute_shell_script "backup-all-databases.sh" "$@"
            ;;
        *)
            execute_shell_script "backup-all-databases.sh" "$@"
            ;;
    esac
}

cmd_restore() {
    log "Restoring from backup..."
    execute_shell_script "restore-all-databases.sh" "$@"
}

cmd_restore_single() {
    local database="$1"
    if [[ -z "$database" ]]; then
        error "restore-single requires database name"
        info "Usage: $0 restore-single <postgresql|neo4j|milvus|redis>"
        return 1
    fi
    shift
    
    log "Restoring $database from backup..."
    execute_shell_script "restore-all-databases.sh" "$@"
}

cmd_health() {
    log "Checking database health..."
    
    show_environment
    
    local available_count
    available_count=$(check_services)
    
    # Also run Python health check if available
    if [[ -f "$SCRIPT_DIR/reset-all-databases.py" ]]; then
        echo ""
        log "Running detailed health check..."
        execute_python_script "reset-all-databases.py" --all --dry-run 2>/dev/null || true
    fi
    
    echo ""
    if [[ $available_count -gt 0 ]]; then
        success "Database health check completed"
    else
        error "No databases are available"
        return 1
    fi
}

cmd_status() {
    log "Getting database status and statistics..."
    
    show_environment
    check_services
    
    # Show database sizes and statistics
    echo ""
    header "Database Statistics"
    
    # PostgreSQL stats
    if pg_isready -h "${POSTGRES_HOST:-localhost}" -p "${POSTGRES_PORT:-5432}" -U "${POSTGRES_USER:-ml_user}" -d "${POSTGRES_DB:-multimodal_librarian}" >/dev/null 2>&1; then
        local pg_size=$(psql -h "${POSTGRES_HOST:-localhost}" -p "${POSTGRES_PORT:-5432}" -U "${POSTGRES_USER:-ml_user}" -d "${POSTGRES_DB:-multimodal_librarian}" -t -c "SELECT pg_size_pretty(pg_database_size('${POSTGRES_DB:-multimodal_librarian}'));" 2>/dev/null | xargs || echo "Unknown")
        local pg_tables=$(psql -h "${POSTGRES_HOST:-localhost}" -p "${POSTGRES_PORT:-5432}" -U "${POSTGRES_USER:-ml_user}" -d "${POSTGRES_DB:-multimodal_librarian}" -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';" 2>/dev/null | xargs || echo "0")
        echo "  PostgreSQL: $pg_size, $pg_tables tables"
    else
        echo "  PostgreSQL: Not accessible"
    fi
    
    # Neo4j stats
    if cypher-shell -a "bolt://${NEO4J_HOST:-localhost}:${NEO4J_PORT:-7687}" -u "${NEO4J_USER:-neo4j}" -p "${NEO4J_PASSWORD:-ml_password}" "RETURN 1" >/dev/null 2>&1; then
        local neo4j_nodes=$(cypher-shell -a "bolt://${NEO4J_HOST:-localhost}:${NEO4J_PORT:-7687}" -u "${NEO4J_USER:-neo4j}" -p "${NEO4J_PASSWORD:-ml_password}" "MATCH (n) RETURN count(n)" --format plain 2>/dev/null | tail -1 | xargs || echo "0")
        echo "  Neo4j: $neo4j_nodes nodes"
    else
        echo "  Neo4j: Not accessible"
    fi
    
    # Redis stats
    if redis-cli -h "${REDIS_HOST:-localhost}" -p "${REDIS_PORT:-6379}" ping >/dev/null 2>&1; then
        local redis_keys=$(redis-cli -h "${REDIS_HOST:-localhost}" -p "${REDIS_PORT:-6379}" dbsize 2>/dev/null || echo "0")
        local redis_memory=$(redis-cli -h "${REDIS_HOST:-localhost}" -p "${REDIS_PORT:-6379}" info memory 2>/dev/null | grep "used_memory_human:" | cut -d: -f2 | tr -d '\r' || echo "Unknown")
        echo "  Redis: $redis_keys keys, $redis_memory memory"
    else
        echo "  Redis: Not accessible"
    fi
    
    # Milvus stats
    if curl -s -f "http://${MILVUS_HOST:-localhost}:${MILVUS_HTTP_PORT:-9091}/healthz" >/dev/null 2>&1; then
        echo "  Milvus: Accessible"
    else
        echo "  Milvus: Not accessible"
    fi
}

cmd_optimize() {
    log "Optimizing database performance..."
    
    # PostgreSQL optimization
    if pg_isready -h "${POSTGRES_HOST:-localhost}" -p "${POSTGRES_PORT:-5432}" -U "${POSTGRES_USER:-ml_user}" -d "${POSTGRES_DB:-multimodal_librarian}" >/dev/null 2>&1; then
        log "Running PostgreSQL VACUUM ANALYZE..."
        psql -h "${POSTGRES_HOST:-localhost}" -p "${POSTGRES_PORT:-5432}" -U "${POSTGRES_USER:-ml_user}" -d "${POSTGRES_DB:-multimodal_librarian}" -c "VACUUM ANALYZE;" >/dev/null 2>&1 && success "PostgreSQL optimization completed" || warning "PostgreSQL optimization failed"
    fi
    
    # Redis optimization (if needed)
    if redis-cli -h "${REDIS_HOST:-localhost}" -p "${REDIS_PORT:-6379}" ping >/dev/null 2>&1; then
        log "Redis is accessible (no optimization needed)"
    fi
    
    success "Database optimization completed"
}

cmd_migrate() {
    log "Running database migrations..."
    
    # Run Python migration script if it exists
    local migration_script="$PROJECT_ROOT/src/multimodal_librarian/database/migrations.py"
    if [[ -f "$migration_script" ]]; then
        cd "$PROJECT_ROOT"
        python3 -m multimodal_librarian.database.migrations
    else
        warning "Migration script not found"
        return 1
    fi
}

cmd_seed() {
    log "Seeding databases with sample data..."
    
    # Run seed scripts if they exist
    local seed_script="$SCRIPT_DIR/seed-all-sample-data.py"
    if [[ -f "$seed_script" ]]; then
        execute_python_script "seed-all-sample-data.py" "$@"
    else
        warning "Seed script not found"
        return 1
    fi
}

cmd_dev_reset() {
    log "Performing development reset..."
    
    # Quick development reset: data only + seed
    execute_python_script "reset-all-databases.py" --all --force "$@" &&
    cmd_seed --force
}

cmd_dev_setup() {
    log "Setting up development environment..."
    
    # Full development setup
    cmd_reset_all --force "$@" &&
    cmd_migrate &&
    cmd_seed --force
}

cmd_list_backups() {
    log "Listing available backups..."
    
    local backup_dir="${BACKUP_DIR:-./backups}"
    if [[ -d "$backup_dir" ]]; then
        execute_shell_script "backup-all-databases.sh" stats
    else
        warning "Backup directory not found: $backup_dir"
    fi
}

cmd_show_config() {
    header "Database Configuration"
    show_environment
    
    echo "Connection Settings:"
    echo "  PostgreSQL: ${POSTGRES_HOST:-localhost}:${POSTGRES_PORT:-5432}/${POSTGRES_DB:-multimodal_librarian}"
    echo "  Neo4j: ${NEO4J_HOST:-localhost}:${NEO4J_PORT:-7687}"
    echo "  Milvus: ${MILVUS_HOST:-localhost}:${MILVUS_PORT:-19530}"
    echo "  Redis: ${REDIS_HOST:-localhost}:${REDIS_PORT:-6379}"
    echo ""
    
    echo "Available Scripts:"
    for script in "$SCRIPT_DIR"/*.py "$SCRIPT_DIR"/*.sh; do
        if [[ -f "$script" && -x "$script" ]]; then
            echo "  $(basename "$script")"
        fi
    done
}

# Main execution
main() {
    # Check prerequisites
    check_prerequisites
    
    # Parse global options first
    local remaining_args
    remaining_args=($(parse_global_options "$@"))
    
    # Get command
    local command="${remaining_args[0]:-help}"
    local cmd_args=("${remaining_args[@]:1}")
    
    # Execute command
    case "$command" in
        reset-all)          cmd_reset_all "${cmd_args[@]}" ;;
        reset-postgresql)   cmd_reset_postgresql "${cmd_args[@]}" ;;
        reset-neo4j)        cmd_reset_neo4j "${cmd_args[@]}" ;;
        reset-milvus)       cmd_reset_milvus "${cmd_args[@]}" ;;
        reset-redis)        cmd_reset_redis "${cmd_args[@]}" ;;
        cleanup)            cmd_cleanup "${cmd_args[@]}" ;;
        cleanup-age)        cmd_cleanup_age "${cmd_args[@]}" ;;
        cleanup-size)       cmd_cleanup_size "${cmd_args[@]}" ;;
        cleanup-temp)       cmd_cleanup_temp "${cmd_args[@]}" ;;
        backup)             cmd_backup "${cmd_args[@]}" ;;
        backup-single)      cmd_backup_single "${cmd_args[@]}" ;;
        restore)            cmd_restore "${cmd_args[@]}" ;;
        restore-single)     cmd_restore_single "${cmd_args[@]}" ;;
        health)             cmd_health "${cmd_args[@]}" ;;
        status)             cmd_status "${cmd_args[@]}" ;;
        optimize)           cmd_optimize "${cmd_args[@]}" ;;
        migrate)            cmd_migrate "${cmd_args[@]}" ;;
        seed)               cmd_seed "${cmd_args[@]}" ;;
        dev-reset)          cmd_dev_reset "${cmd_args[@]}" ;;
        dev-setup)          cmd_dev_setup "${cmd_args[@]}" ;;
        list-backups)       cmd_list_backups "${cmd_args[@]}" ;;
        show-config)        cmd_show_config "${cmd_args[@]}" ;;
        help|--help|-h)     show_help ;;
        *)
            error "Unknown command: $command"
            echo "Use '$0 help' for usage information"
            exit 1
            ;;
    esac
}

# Handle script interruption
trap 'error "Script interrupted by user"; exit 1' INT TERM

# Run main function with all arguments
main "$@"