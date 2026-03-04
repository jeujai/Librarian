#!/bin/bash

# Wait for all database services to be ready
# This script waits for PostgreSQL, Neo4j, Milvus, and Redis to be operational

set -e

# Configuration
MAX_WAIT_TIME=${MAX_WAIT_TIME:-300}  # 5 minutes total
CHECK_INTERVAL=${CHECK_INTERVAL:-5}  # Check every 5 seconds

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if a service is ready using docker-compose health check
check_service_health() {
    local service_name=$1
    local compose_file=${2:-docker-compose.local.yml}
    
    # Get the health status from docker-compose
    local health_status=$(docker-compose -f "$compose_file" ps -q "$service_name" | xargs docker inspect --format='{{.State.Health.Status}}' 2>/dev/null || echo "unknown")
    
    if [ "$health_status" = "healthy" ]; then
        return 0
    else
        return 1
    fi
}

# Wait for a specific service
wait_for_service() {
    local service_name=$1
    local display_name=${2:-$service_name}
    local compose_file=${3:-docker-compose.local.yml}
    
    log_info "Waiting for $display_name..."
    
    local elapsed=0
    while [ $elapsed -lt $MAX_WAIT_TIME ]; do
        if check_service_health "$service_name" "$compose_file"; then
            log_success "$display_name is ready!"
            return 0
        fi
        
        log_info "$display_name not ready yet... (${elapsed}s/${MAX_WAIT_TIME}s)"
        sleep $CHECK_INTERVAL
        elapsed=$((elapsed + CHECK_INTERVAL))
    done
    
    log_error "$display_name failed to become ready within ${MAX_WAIT_TIME}s"
    return 1
}

# Check if docker-compose is available
check_docker_compose() {
    if ! command -v docker-compose &> /dev/null; then
        log_error "docker-compose is not installed or not in PATH"
        exit 1
    fi
}

# Main function
main() {
    local compose_file="docker-compose.local.yml"
    local failed_services=()
    
    # Parse command line arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            -f|--file)
                compose_file="$2"
                shift 2
                ;;
            -t|--timeout)
                MAX_WAIT_TIME="$2"
                shift 2
                ;;
            -i|--interval)
                CHECK_INTERVAL="$2"
                shift 2
                ;;
            -h|--help)
                echo "Usage: $0 [OPTIONS]"
                echo ""
                echo "Options:"
                echo "  -f, --file FILE       Docker compose file (default: docker-compose.local.yml)"
                echo "  -t, --timeout SECONDS Maximum wait time (default: 300)"
                echo "  -i, --interval SECONDS Check interval (default: 5)"
                echo "  -h, --help            Show this help message"
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                exit 1
                ;;
        esac
    done
    
    check_docker_compose
    
    log_info "Waiting for all database services to be ready..."
    log_info "Compose file: $compose_file"
    log_info "Max wait time: ${MAX_WAIT_TIME}s"
    log_info "Check interval: ${CHECK_INTERVAL}s"
    echo
    
    # Check if services are running first
    log_info "Checking if services are running..."
    if ! docker-compose -f "$compose_file" ps postgres neo4j milvus redis etcd minio | grep -q "Up"; then
        log_error "Some database services are not running. Please start them first:"
        log_error "  docker-compose -f $compose_file up -d postgres neo4j milvus redis"
        exit 1
    fi
    
    # Wait for each service in dependency order
    local start_time=$(date +%s)
    
    # First, wait for basic dependencies
    if ! wait_for_service "etcd" "etcd (Milvus dependency)" "$compose_file"; then
        failed_services+=("etcd")
    fi
    
    if ! wait_for_service "minio" "MinIO (Milvus dependency)" "$compose_file"; then
        failed_services+=("minio")
    fi
    
    # Then wait for main databases
    if ! wait_for_service "postgres" "PostgreSQL" "$compose_file"; then
        failed_services+=("postgres")
    fi
    
    if ! wait_for_service "redis" "Redis" "$compose_file"; then
        failed_services+=("redis")
    fi
    
    if ! wait_for_service "neo4j" "Neo4j" "$compose_file"; then
        failed_services+=("neo4j")
    fi
    
    if ! wait_for_service "milvus" "Milvus" "$compose_file"; then
        failed_services+=("milvus")
    fi
    
    local end_time=$(date +%s)
    local total_time=$((end_time - start_time))
    
    echo
    log_info "Health check completed in ${total_time}s"
    
    if [ ${#failed_services[@]} -eq 0 ]; then
        log_success "All database services are ready!"
        
        # Run comprehensive health check if available
        if [ -f "scripts/check-all-database-health.py" ]; then
            log_info "Running comprehensive health check..."
            python3 scripts/check-all-database-health.py --quiet
        fi
        
        echo
        log_success "Database services are ready for development!"
        log_info "You can now start the main application:"
        log_info "  docker-compose -f $compose_file up multimodal-librarian"
        log_info ""
        log_info "Or access admin interfaces:"
        log_info "  PostgreSQL (pgAdmin): http://localhost:5050"
        log_info "  Neo4j Browser: http://localhost:7474"
        log_info "  Milvus (Attu): http://localhost:3000"
        log_info "  Redis Commander: http://localhost:8081"
        log_info "  MinIO Console: http://localhost:9001"
        
        exit 0
    else
        log_error "The following services failed to become ready:"
        for service in "${failed_services[@]}"; do
            log_error "  - $service"
        done
        
        echo
        log_error "Troubleshooting steps:"
        log_error "1. Check service logs: docker-compose -f $compose_file logs [service_name]"
        log_error "2. Check service status: docker-compose -f $compose_file ps"
        log_error "3. Restart failed services: docker-compose -f $compose_file restart [service_name]"
        log_error "4. Check available resources (memory, disk space)"
        
        exit 1
    fi
}

# Run main function with all arguments
main "$@"