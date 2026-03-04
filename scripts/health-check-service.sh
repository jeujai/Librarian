#!/bin/bash

# =============================================================================
# Service Health Check Wrapper Script
# =============================================================================
# Provides easy access to individual service health checks and comprehensive
# health monitoring for the local development environment.

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="docker-compose.local.yml"

# Function to print colored output
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to show help
show_help() {
    echo "Service Health Check Wrapper"
    echo ""
    echo "Usage: $0 [SERVICE|COMMAND] [OPTIONS]"
    echo ""
    echo "Services:"
    echo "  postgresql      Check PostgreSQL health"
    echo "  neo4j           Check Neo4j health"
    echo "  milvus          Check Milvus health"
    echo "  redis           Check Redis health"
    echo "  all             Check all services"
    echo ""
    echo "Commands:"
    echo "  status          Show Docker Compose service status"
    echo "  quick           Quick health check (basic connectivity only)"
    echo "  detailed        Detailed health check with full diagnostics"
    echo "  monitor         Continuous monitoring (runs every 30 seconds)"
    echo ""
    echo "Options:"
    echo "  --json          Output in JSON format"
    echo "  --quiet         Minimal output"
    echo "  --parallel      Run checks in parallel (for 'all' command)"
    echo "  --timeout SEC   Set timeout for health checks (default: 60)"
    echo ""
    echo "Examples:"
    echo "  $0 postgresql                    # Check PostgreSQL"
    echo "  $0 all --parallel               # Check all services in parallel"
    echo "  $0 detailed --json              # Detailed check with JSON output"
    echo "  $0 status                       # Show service status"
    echo "  $0 monitor                      # Continuous monitoring"
}

# Function to check if Python script exists
check_script_exists() {
    local script_name="$1"
    local script_path="$SCRIPT_DIR/$script_name"
    
    if [[ ! -f "$script_path" ]]; then
        print_error "Health check script not found: $script_path"
        return 1
    fi
    
    return 0
}

# Function to run individual service health check
run_service_check() {
    local service="$1"
    shift
    local args=("$@")
    
    local script_name="health-check-${service}.py"
    
    if ! check_script_exists "$script_name"; then
        return 1
    fi
    
    print_info "Running health check for $service..."
    python3 "$SCRIPT_DIR/$script_name" "${args[@]}"
}

# Function to run all services health check
run_all_services_check() {
    local args=("$@")
    
    if ! check_script_exists "health-check-all-services.py"; then
        return 1
    fi
    
    print_info "Running health check for all services..."
    python3 "$SCRIPT_DIR/health-check-all-services.py" "${args[@]}"
}

# Function to show Docker Compose status
show_docker_status() {
    print_info "Checking Docker Compose service status..."
    
    if [[ ! -f "$COMPOSE_FILE" ]]; then
        print_error "Docker Compose file not found: $COMPOSE_FILE"
        return 1
    fi
    
    echo ""
    echo "Service Status:"
    echo "==============="
    
    if command -v docker-compose >/dev/null 2>&1; then
        docker-compose -f "$COMPOSE_FILE" ps
    elif command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
        docker compose -f "$COMPOSE_FILE" ps
    else
        print_error "Docker Compose not available"
        return 1
    fi
}

# Function to run quick health check
run_quick_check() {
    print_info "Running quick health check (basic connectivity)..."
    
    # Use the existing basic health check script
    if [[ -f "$SCRIPT_DIR/health-check.sh" ]]; then
        "$SCRIPT_DIR/health-check.sh" "$@"
    else
        print_warning "Basic health check script not found, using comprehensive check..."
        run_all_services_check --quiet "$@"
    fi
}

# Function to run detailed health check
run_detailed_check() {
    print_info "Running detailed health check with full diagnostics..."
    run_all_services_check --include-docker "$@"
}

# Function to run continuous monitoring
run_monitor() {
    local interval=30
    local args=("$@")
    
    print_info "Starting continuous health monitoring (interval: ${interval}s)"
    print_info "Press Ctrl+C to stop monitoring"
    echo ""
    
    while true; do
        echo "$(date '+%Y-%m-%d %H:%M:%S') - Running health check..."
        
        if run_all_services_check --quiet "${args[@]}"; then
            print_success "All services healthy"
        else
            print_warning "Some services have issues"
        fi
        
        echo ""
        sleep "$interval"
    done
}

# Main execution
main() {
    if [[ $# -eq 0 ]]; then
        show_help
        exit 0
    fi
    
    local command="$1"
    shift
    
    case "$command" in
        postgresql|neo4j|milvus|redis)
            run_service_check "$command" "$@"
            ;;
        all)
            run_all_services_check "$@"
            ;;
        status)
            show_docker_status
            ;;
        quick)
            run_quick_check "$@"
            ;;
        detailed)
            run_detailed_check "$@"
            ;;
        monitor)
            run_monitor "$@"
            ;;
        --help|-h|help)
            show_help
            exit 0
            ;;
        *)
            print_error "Unknown command: $command"
            echo ""
            show_help
            exit 1
            ;;
    esac
}

# Run main function with all arguments
main "$@"