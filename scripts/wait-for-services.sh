#!/bin/bash
#
# Wait for Services Script
#
# This script waits for all required services to be ready before proceeding.
# It's designed to work with the local development environment and supports
# both basic health checks and advanced service discovery.
#
# Features:
# - Configurable timeout and retry intervals
# - Support for multiple Docker Compose files
# - Detailed health check reporting
# - Graceful handling of service failures
# - Integration with hot reload development
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

# Default configuration
COMPOSE_FILE="docker-compose.local.yml"
TIMEOUT=300
RETRY_INTERVAL=5
VERBOSE=false
SERVICES=""

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

# Function to show help
show_help() {
    echo "Wait for Services Script"
    echo
    echo "Usage: $0 [OPTIONS]"
    echo
    echo "Options:"
    echo "  --file FILE        Docker Compose file (default: docker-compose.local.yml)"
    echo "  --timeout SECONDS  Maximum wait time (default: 300)"
    echo "  --interval SECONDS Retry interval (default: 5)"
    echo "  --services LIST    Comma-separated list of services to wait for"
    echo "  --verbose          Enable verbose output"
    echo "  --help             Show this help message"
    echo
    echo "Examples:"
    echo "  $0                                    # Wait for all services"
    echo "  $0 --timeout 600                     # Wait up to 10 minutes"
    echo "  $0 --services postgres,neo4j         # Wait for specific services"
    echo "  $0 --file docker-compose.yml         # Use different compose file"
}

# Function to check if a service is healthy
check_service_health() {
    local service=$1
    local compose_file=$2
    
    # Check if container is running
    if ! docker compose -f "$compose_file" ps "$service" | grep -q "Up"; then
        return 1
    fi
    
    # Service-specific health checks
    case $service in
        postgres)
            docker compose -f "$compose_file" exec -T postgres pg_isready -U ml_user -d multimodal_librarian >/dev/null 2>&1
            ;;
        neo4j)
            docker compose -f "$compose_file" exec -T neo4j cypher-shell -u neo4j -p ml_password "RETURN 1" >/dev/null 2>&1
            ;;
        milvus)
            curl -f http://localhost:19530/healthz >/dev/null 2>&1
            ;;
        redis)
            docker compose -f "$compose_file" exec -T redis redis-cli ping >/dev/null 2>&1
            ;;
        etcd)
            docker compose -f "$compose_file" exec -T etcd etcdctl endpoint health >/dev/null 2>&1
            ;;
        minio)
            curl -f http://localhost:9000/minio/health/live >/dev/null 2>&1
            ;;
        multimodal-librarian)
            # Wait a bit longer for the application to start
            sleep 2
            curl -f http://localhost:8000/health/simple >/dev/null 2>&1
            ;;
        *)
            # Generic health check - just check if container is running
            return 0
            ;;
    esac
}

# Function to get list of services from compose file
get_services_from_compose() {
    local compose_file=$1
    
    if [[ -f "$compose_file" ]]; then
        # Extract service names from docker-compose file
        docker compose -f "$compose_file" config --services 2>/dev/null || echo ""
    else
        echo ""
    fi
}

# Function to wait for services
wait_for_services() {
    local compose_file=$1
    local timeout=$2
    local retry_interval=$3
    local services_list=$4
    
    print_status "Waiting for services to be ready..."
    print_info "Compose file: $compose_file"
    print_info "Timeout: ${timeout}s, Retry interval: ${retry_interval}s"
    
    # Get list of services to wait for
    local services_to_check
    if [[ -n "$services_list" ]]; then
        IFS=',' read -ra services_to_check <<< "$services_list"
    else
        # Get all services from compose file
        local all_services
        all_services=$(get_services_from_compose "$compose_file")
        if [[ -z "$all_services" ]]; then
            print_error "Could not get services from compose file: $compose_file"
            return 1
        fi
        # Convert newline-separated services to array using while loop
        services_to_check=()
        while IFS= read -r service; do
            if [[ -n "$service" ]]; then
                services_to_check+=("$service")
            fi
        done <<< "$all_services"
    fi
    
    print_info "Services to check: ${services_to_check[*]}"
    echo
    
    local start_time
    start_time=$(date +%s)
    local ready_services=()
    local failed_services=()
    
    while true; do
        local current_time
        current_time=$(date +%s)
        local elapsed=$((current_time - start_time))
        
        if [[ $elapsed -ge $timeout ]]; then
            print_error "Timeout reached (${timeout}s)"
            print_error "Ready services: ${ready_services[*]}"
            print_error "Failed services: ${failed_services[*]}"
            return 1
        fi
        
        local all_ready=true
        ready_services=()
        failed_services=()
        
        for service in "${services_to_check[@]}"; do
            if check_service_health "$service" "$compose_file"; then
                ready_services+=("$service")
                if [[ "$VERBOSE" == "true" ]]; then
                    print_success "$service is ready"
                fi
            else
                failed_services+=("$service")
                all_ready=false
                if [[ "$VERBOSE" == "true" ]]; then
                    print_warning "$service is not ready yet"
                fi
            fi
        done
        
        if [[ "$all_ready" == "true" ]]; then
            print_success "All services are ready!"
            print_info "Ready services: ${ready_services[*]}"
            print_info "Total wait time: ${elapsed}s"
            return 0
        fi
        
        # Show progress
        local ready_count=${#ready_services[@]}
        local total_count=${#services_to_check[@]}
        print_status "Progress: $ready_count/$total_count services ready (${elapsed}s elapsed)"
        
        if [[ "$VERBOSE" == "true" ]]; then
            print_info "Ready: ${ready_services[*]}"
            print_warning "Waiting for: ${failed_services[*]}"
        fi
        
        sleep "$retry_interval"
    done
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --file)
            COMPOSE_FILE="$2"
            shift 2
            ;;
        --timeout)
            TIMEOUT="$2"
            shift 2
            ;;
        --interval)
            RETRY_INTERVAL="$2"
            shift 2
            ;;
        --services)
            SERVICES="$2"
            shift 2
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

# Main execution
main() {
    print_status "🕐 Wait for Services - Local Development"
    echo
    
    # Check if compose file exists
    if [[ ! -f "$COMPOSE_FILE" ]]; then
        print_error "Compose file not found: $COMPOSE_FILE"
        exit 1
    fi
    
    # Check if docker compose is available
    if ! command -v docker &> /dev/null; then
        print_error "docker not found"
        exit 1
    fi
    
    if ! docker compose version &> /dev/null; then
        print_error "docker compose not available"
        exit 1
    fi
    
    # Wait for services
    if wait_for_services "$COMPOSE_FILE" "$TIMEOUT" "$RETRY_INTERVAL" "$SERVICES"; then
        echo
        print_success "🎉 All services are ready for development!"
        print_info "You can now access the application at http://localhost:8000"
        exit 0
    else
        echo
        print_error "❌ Some services failed to start within the timeout period"
        print_info "Check service logs with: make logs"
        exit 1
    fi
}

# Run main function
main "$@"