#!/bin/bash
#
# Restart All Services Script
#
# Provides a comprehensive restart solution for all local development services
# with proper dependency management, health checking, and recovery procedures.
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
COMPOSE_FILE="docker-compose.local.yml"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
TIMEOUT=300
FORCE=false
BACKUP=false
VERBOSE=false

# Function to print colored output
print_status() {
    echo -e "${BLUE}[$(date '+%H:%M:%S')]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[$(date '+%H:%M:%S')]${NC} ✅ $1"
}

print_warning() {
    echo -e "${YELLOW}[$(date '+%H:%M:%S')]${NC} ⚠️  $1"
}

print_error() {
    echo -e "${RED}[$(date '+%H:%M:%S')]${NC} ❌ $1"
}

print_info() {
    echo -e "${CYAN}[$(date '+%H:%M:%S')]${NC} 💡 $1"
}

print_debug() {
    if [[ "$VERBOSE" == "true" ]]; then
        echo -e "${PURPLE}[$(date '+%H:%M:%S')]${NC} 🔍 $1"
    fi
}

# Function to show help
show_help() {
    echo "Restart All Services Script"
    echo
    echo "Usage: $0 [OPTIONS]"
    echo
    echo "Options:"
    echo "  --compose-file FILE    Docker Compose file (default: docker-compose.local.yml)"
    echo "  --timeout SECONDS      Maximum wait time for operations (default: 300)"
    echo "  --force               Continue even if some operations fail"
    echo "  --backup              Create backup before restart"
    echo "  --verbose             Enable verbose output"
    echo "  --help                Show this help message"
    echo
    echo "Examples:"
    echo "  $0                           # Standard restart"
    echo "  $0 --backup --verbose        # Restart with backup and verbose output"
    echo "  $0 --force --timeout 600     # Force restart with extended timeout"
}

# Function to check if Docker Compose is available
check_docker_compose() {
    print_status "Checking Docker Compose availability..."
    
    if command -v docker-compose >/dev/null 2>&1; then
        DOCKER_COMPOSE_CMD="docker-compose"
        print_debug "Using docker-compose command"
    elif command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
        DOCKER_COMPOSE_CMD="docker compose"
        print_debug "Using docker compose command"
    else
        print_error "Docker Compose not available"
        exit 1
    fi
    
    print_success "Docker Compose is available"
}

# Function to check if compose file exists
check_compose_file() {
    print_status "Checking compose file: $COMPOSE_FILE"
    
    if [[ ! -f "$COMPOSE_FILE" ]]; then
        print_error "Compose file not found: $COMPOSE_FILE"
        exit 1
    fi
    
    print_success "Compose file found"
}

# Function to create backup
create_backup() {
    if [[ "$BACKUP" != "true" ]]; then
        return 0
    fi
    
    print_status "Creating backup before restart..."
    
    local backup_script="$SCRIPT_DIR/backup-all-databases.sh"
    
    if [[ -f "$backup_script" ]]; then
        print_info "Running backup script..."
        
        if "$backup_script"; then
            print_success "Backup completed successfully"
        else
            print_warning "Backup failed, but continuing with restart"
            if [[ "$FORCE" != "true" ]]; then
                read -p "Continue without backup? (y/N): " -n 1 -r
                echo
                if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                    print_error "Restart cancelled"
                    exit 1
                fi
            fi
        fi
    else
        print_warning "Backup script not found: $backup_script"
        print_info "Skipping backup step"
    fi
}

# Function to get service status
get_service_status() {
    local service="$1"
    
    local status_output
    status_output=$($DOCKER_COMPOSE_CMD -f "$COMPOSE_FILE" ps "$service" 2>/dev/null || echo "")
    
    if echo "$status_output" | grep -q "Up"; then
        echo "running"
    elif echo "$status_output" | grep -q "Exit"; then
        echo "stopped"
    else
        echo "unknown"
    fi
}

# Function to get all services
get_all_services() {
    $DOCKER_COMPOSE_CMD -f "$COMPOSE_FILE" config --services 2>/dev/null || echo ""
}

# Function to stop all services gracefully
stop_all_services() {
    print_status "Stopping all services gracefully..."
    
    local services
    services=$(get_all_services)
    
    if [[ -z "$services" ]]; then
        print_error "Could not get services from compose file"
        return 1
    fi
    
    print_info "Services to stop: $(echo "$services" | tr '\n' ' ')"
    
    # Stop services in reverse dependency order (application first, databases last)
    local stop_order=(
        "multimodal-librarian"
        "attu"
        "pgadmin"
        "redis-commander"
        "log-viewer"
        "milvus"
        "redis"
        "neo4j"
        "postgres"
        "minio"
        "etcd"
    )
    
    for service in "${stop_order[@]}"; do
        if echo "$services" | grep -q "^$service$"; then
            local status
            status=$(get_service_status "$service")
            
            if [[ "$status" == "running" ]]; then
                print_debug "Stopping $service..."
                
                if $DOCKER_COMPOSE_CMD -f "$COMPOSE_FILE" stop -t 30 "$service" >/dev/null 2>&1; then
                    print_debug "$service stopped successfully"
                else
                    print_warning "Failed to stop $service gracefully"
                    
                    if [[ "$FORCE" == "true" ]]; then
                        print_debug "Force killing $service..."
                        $DOCKER_COMPOSE_CMD -f "$COMPOSE_FILE" kill "$service" >/dev/null 2>&1 || true
                    fi
                fi
            else
                print_debug "$service is not running"
            fi
        fi
    done
    
    # Wait a moment for services to fully stop
    print_debug "Waiting for services to fully stop..."
    sleep 3
    
    print_success "All services stopped"
}

# Function to start all services
start_all_services() {
    print_status "Starting all services..."
    
    # Start services in dependency order
    local start_order=(
        "etcd"
        "minio"
        "postgres"
        "neo4j"
        "redis"
        "milvus"
        "multimodal-librarian"
        "pgadmin"
        "attu"
        "redis-commander"
        "log-viewer"
    )
    
    for service in "${start_order[@]}"; do
        local services
        services=$(get_all_services)
        
        if echo "$services" | grep -q "^$service$"; then
            print_debug "Starting $service..."
            
            if $DOCKER_COMPOSE_CMD -f "$COMPOSE_FILE" up -d "$service" >/dev/null 2>&1; then
                print_debug "$service started successfully"
                
                # Wait a moment between critical services
                case "$service" in
                    postgres|neo4j|milvus|multimodal-librarian)
                        print_debug "Waiting for $service to initialize..."
                        sleep 5
                        ;;
                esac
            else
                print_error "Failed to start $service"
                
                if [[ "$FORCE" != "true" ]]; then
                    return 1
                fi
            fi
        fi
    done
    
    print_success "All services started"
}

# Function to wait for services to be healthy
wait_for_services() {
    print_status "Waiting for services to become healthy..."
    
    local wait_script="$SCRIPT_DIR/wait-for-services.sh"
    
    if [[ -f "$wait_script" ]]; then
        print_info "Using wait-for-services script..."
        
        local wait_args=("--timeout" "$TIMEOUT")
        
        if [[ "$VERBOSE" == "true" ]]; then
            wait_args+=("--verbose")
        fi
        
        if "$wait_script" "${wait_args[@]}"; then
            print_success "All services are healthy"
            return 0
        else
            print_error "Some services failed to become healthy"
            return 1
        fi
    else
        print_warning "Wait script not found, using basic health check..."
        
        # Basic health check
        local max_attempts=30
        local attempt=0
        
        while [[ $attempt -lt $max_attempts ]]; do
            attempt=$((attempt + 1))
            
            print_debug "Health check attempt $attempt/$max_attempts"
            
            # Check if main application is responding
            if curl -f -s http://localhost:8000/health/simple >/dev/null 2>&1; then
                print_success "Application is responding"
                return 0
            fi
            
            if [[ $attempt -lt $max_attempts ]]; then
                sleep 10
            fi
        done
        
        print_error "Application failed to respond within timeout"
        return 1
    fi
}

# Function to verify restart success
verify_restart() {
    print_status "Verifying restart success..."
    
    local health_script="$SCRIPT_DIR/health-check-all-services.py"
    
    if [[ -f "$health_script" ]]; then
        print_info "Running comprehensive health check..."
        
        if python3 "$health_script" --include-docker >/dev/null 2>&1; then
            print_success "All services passed health checks"
            return 0
        else
            print_warning "Some services failed health checks"
            
            if [[ "$VERBOSE" == "true" ]]; then
                print_info "Running health check with details..."
                python3 "$health_script" --include-docker
            fi
            
            return 1
        fi
    else
        print_warning "Health check script not found, using basic verification..."
        
        # Basic verification - check if services are running
        local services
        services=$(get_all_services)
        local failed_services=()
        
        for service in $services; do
            local status
            status=$(get_service_status "$service")
            
            if [[ "$status" != "running" ]]; then
                failed_services+=("$service")
            fi
        done
        
        if [[ ${#failed_services[@]} -eq 0 ]]; then
            print_success "All services are running"
            return 0
        else
            print_error "Failed services: ${failed_services[*]}"
            return 1
        fi
    fi
}

# Function to show final status
show_final_status() {
    print_status "Final service status:"
    echo
    
    $DOCKER_COMPOSE_CMD -f "$COMPOSE_FILE" ps
    
    echo
    print_info "Access URLs:"
    print_info "  Application:     http://localhost:8000"
    print_info "  Neo4j Browser:   http://localhost:7474"
    print_info "  pgAdmin:         http://localhost:5050"
    print_info "  Milvus Admin:    http://localhost:3000"
    print_info "  Redis Commander: http://localhost:8081"
    print_info "  Log Viewer:      http://localhost:8080"
}

# Function to handle cleanup on exit
cleanup() {
    local exit_code=$?
    
    if [[ $exit_code -ne 0 ]]; then
        print_error "Restart process failed"
        print_info "Check service logs with: make logs"
        print_info "Or use: docker-compose -f $COMPOSE_FILE logs"
    fi
    
    exit $exit_code
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --compose-file)
            COMPOSE_FILE="$2"
            shift 2
            ;;
        --timeout)
            TIMEOUT="$2"
            shift 2
            ;;
        --force)
            FORCE=true
            shift
            ;;
        --backup)
            BACKUP=true
            shift
            ;;
        --verbose)
            VERBOSE=true
            shift
            ;;
        --help)
            show_help
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Set up cleanup trap
trap cleanup EXIT

# Main execution
main() {
    print_status "🔄 Restart All Services - Local Development"
    echo
    
    # Pre-flight checks
    check_docker_compose
    check_compose_file
    
    # Create backup if requested
    create_backup
    
    # Perform restart
    print_status "Starting restart process..."
    
    if stop_all_services; then
        print_success "Services stopped successfully"
    else
        if [[ "$FORCE" != "true" ]]; then
            print_error "Failed to stop services"
            exit 1
        else
            print_warning "Some services failed to stop, continuing due to --force"
        fi
    fi
    
    if start_all_services; then
        print_success "Services started successfully"
    else
        if [[ "$FORCE" != "true" ]]; then
            print_error "Failed to start services"
            exit 1
        else
            print_warning "Some services failed to start, continuing due to --force"
        fi
    fi
    
    # Wait for services to be ready
    if wait_for_services; then
        print_success "Services are ready"
    else
        if [[ "$FORCE" != "true" ]]; then
            print_error "Services failed to become ready"
            exit 1
        else
            print_warning "Some services may not be ready, continuing due to --force"
        fi
    fi
    
    # Verify restart success
    if verify_restart; then
        print_success "Restart verification passed"
    else
        print_warning "Restart verification had issues"
    fi
    
    # Show final status
    show_final_status
    
    echo
    print_success "🎉 All services restarted successfully!"
    print_info "Total restart time: ${SECONDS}s"
}

# Change to project root directory
cd "$PROJECT_ROOT"

# Run main function
main "$@"