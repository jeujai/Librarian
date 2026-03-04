#!/bin/bash

# Database Reset Script Wrapper for Multimodal Librarian
# This script provides a convenient shell interface to the Python reset script

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/reset-all-databases.py"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
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

# Check if Python script exists
check_python_script() {
    if [[ ! -f "$PYTHON_SCRIPT" ]]; then
        error "Python reset script not found: $PYTHON_SCRIPT"
        exit 1
    fi
}

# Check Python environment
check_python_environment() {
    if ! command -v python3 >/dev/null 2>&1; then
        error "Python 3 is required but not installed"
        exit 1
    fi
    
    # Check if we're in a virtual environment or have the required packages
    if ! python3 -c "import sys; sys.path.insert(0, 'src'); from multimodal_librarian.clients.database_client_factory import DatabaseClientFactory" 2>/dev/null; then
        warning "Required Python packages may not be installed"
        info "Make sure you have installed the project dependencies:"
        info "  pip install -r requirements.txt"
        info "  pip install -r requirements-dev.txt"
    fi
}

# Show help
show_help() {
    cat << EOF
Database Reset Script for Multimodal Librarian

USAGE:
    $0 [OPTIONS] [COMMAND]

COMMANDS:
    all                     Reset all databases (default)
    postgresql              Reset only PostgreSQL
    neo4j                   Reset only Neo4j
    milvus                  Reset only Milvus (local) or OpenSearch (AWS)
    redis                   Reset only Redis
    custom <db1,db2,...>    Reset specific databases

OPTIONS:
    --backup                Create backup before reset
    --force                 Skip confirmation prompts (dangerous!)
    --dry-run               Show what would be reset without making changes
    --environment <env>     Force environment (local|aws)
    --backup-dir <dir>      Backup directory (default: ./backups)
    --verbose               Enable verbose output
    --quiet                 Suppress non-error output
    --help                  Show this help message

ENVIRONMENT VARIABLES:
    ML_ENVIRONMENT          Set environment (local|aws)
    DATABASE_TYPE           Set database type (local|aws)
    BACKUP_DIR              Default backup directory
    
    Database Connection Variables:
    POSTGRES_HOST, POSTGRES_PORT, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB
    NEO4J_HOST, NEO4J_PORT, NEO4J_USER, NEO4J_PASSWORD
    MILVUS_HOST, MILVUS_PORT
    REDIS_HOST, REDIS_PORT

EXAMPLES:
    # Reset all databases with confirmation
    $0 all

    # Reset all databases with backup
    $0 all --backup

    # Reset only PostgreSQL and Neo4j
    $0 custom postgresql,neo4j

    # Force reset without confirmation (dangerous!)
    $0 all --force

    # Dry run to see what would be reset
    $0 all --dry-run

    # Reset in specific environment
    $0 all --environment local

    # Reset with custom backup directory
    $0 all --backup --backup-dir /path/to/backups

SAFETY FEATURES:
    - Confirmation prompts before destructive operations
    - Automatic backup creation (with --backup flag)
    - Dry run mode to preview changes
    - Environment detection and validation
    - Service health checks before reset
    - Comprehensive error handling and logging

WARNING:
    This script will permanently delete all data in the specified databases.
    Always create backups before running reset operations in production-like environments.

EOF
}

# Parse command line arguments
parse_arguments() {
    local command=""
    local python_args=()
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            all)
                command="all"
                python_args+=("--all")
                shift
                ;;
            postgresql|neo4j|milvus|opensearch|redis)
                command="single"
                python_args+=("--databases" "$1")
                shift
                ;;
            custom)
                if [[ -n "$2" ]]; then
                    command="custom"
                    python_args+=("--databases" "$2")
                    shift 2
                else
                    error "Custom command requires database list"
                    exit 1
                fi
                ;;
            --backup)
                python_args+=("--backup")
                shift
                ;;
            --force)
                python_args+=("--force")
                shift
                ;;
            --dry-run)
                python_args+=("--dry-run")
                shift
                ;;
            --environment)
                if [[ -n "$2" ]]; then
                    python_args+=("--environment" "$2")
                    shift 2
                else
                    error "--environment requires a value"
                    exit 1
                fi
                ;;
            --backup-dir)
                if [[ -n "$2" ]]; then
                    python_args+=("--backup-dir" "$2")
                    shift 2
                else
                    error "--backup-dir requires a value"
                    exit 1
                fi
                ;;
            --verbose|-v)
                python_args+=("--verbose")
                shift
                ;;
            --quiet|-q)
                python_args+=("--quiet")
                shift
                ;;
            --help|-h)
                show_help
                exit 0
                ;;
            *)
                error "Unknown option: $1"
                echo "Use '$0 --help' for usage information"
                exit 1
                ;;
        esac
    done
    
    # Default to 'all' if no command specified
    if [[ -z "$command" ]]; then
        python_args+=("--all")
    fi
    
    echo "${python_args[@]}"
}

# Check if services are running (basic check)
check_services_running() {
    log "Checking if database services are running..."
    
    local services_checked=0
    local services_running=0
    
    # Check PostgreSQL
    if pg_isready -h "${POSTGRES_HOST:-localhost}" -p "${POSTGRES_PORT:-5432}" -U "${POSTGRES_USER:-ml_user}" -d "${POSTGRES_DB:-multimodal_librarian}" >/dev/null 2>&1; then
        success "PostgreSQL: Running"
        services_running=$((services_running + 1))
    else
        warning "PostgreSQL: Not accessible"
    fi
    services_checked=$((services_checked + 1))
    
    # Check Neo4j
    if cypher-shell -a "bolt://${NEO4J_HOST:-localhost}:${NEO4J_PORT:-7687}" -u "${NEO4J_USER:-neo4j}" -p "${NEO4J_PASSWORD:-ml_password}" "RETURN 1" >/dev/null 2>&1; then
        success "Neo4j: Running"
        services_running=$((services_running + 1))
    else
        warning "Neo4j: Not accessible"
    fi
    services_checked=$((services_checked + 1))
    
    # Check Milvus
    if curl -s -f "http://${MILVUS_HOST:-localhost}:${MILVUS_HTTP_PORT:-9091}/healthz" >/dev/null 2>&1; then
        success "Milvus: Running"
        services_running=$((services_running + 1))
    else
        warning "Milvus: Not accessible"
    fi
    services_checked=$((services_checked + 1))
    
    # Check Redis
    if redis-cli -h "${REDIS_HOST:-localhost}" -p "${REDIS_PORT:-6379}" ping >/dev/null 2>&1; then
        success "Redis: Running"
        services_running=$((services_running + 1))
    else
        warning "Redis: Not accessible"
    fi
    services_checked=$((services_checked + 1))
    
    info "Services running: $services_running/$services_checked"
    
    if [[ $services_running -eq 0 ]]; then
        error "No database services are accessible"
        info "Please start the database services first:"
        info "  docker-compose -f docker-compose.local.yml up -d"
        exit 1
    fi
}

# Show environment information
show_environment_info() {
    log "Environment Information:"
    echo "  ML_ENVIRONMENT: ${ML_ENVIRONMENT:-not set}"
    echo "  DATABASE_TYPE: ${DATABASE_TYPE:-not set}"
    echo "  Current directory: $(pwd)"
    echo "  Python script: $PYTHON_SCRIPT"
    echo ""
}

# Main execution
main() {
    log "Starting database reset operation"
    
    # Check prerequisites
    check_python_script
    check_python_environment
    
    # Show environment info
    show_environment_info
    
    # Parse arguments
    local python_args
    python_args=($(parse_arguments "$@"))
    
    # Check if services are running (unless it's a dry run)
    if [[ ! " ${python_args[*]} " =~ " --dry-run " ]]; then
        check_services_running
    fi
    
    # Execute Python script
    log "Executing reset operation..."
    if python3 "$PYTHON_SCRIPT" "${python_args[@]}"; then
        success "Database reset completed successfully"
        return 0
    else
        error "Database reset failed"
        return 1
    fi
}

# Handle script interruption
trap 'error "Script interrupted by user"; exit 1' INT TERM

# Run main function with all arguments
main "$@"