#!/bin/bash

# =============================================================================
# Health Check Script for Local Development
# =============================================================================
# This script checks the health of all services in the local development environment

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
COMPOSE_FILE="docker-compose.local.yml"
TIMEOUT=10
VERBOSE=false
CI_MODE=false

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

# Function to check if a service is running
check_service_running() {
    local service="$1"
    docker-compose -f "$COMPOSE_FILE" ps "$service" | grep -q "Up"
}

# Function to check HTTP endpoint
check_http_endpoint() {
    local url="$1"
    local expected_status="${2:-200}"
    local timeout="${3:-$TIMEOUT}"
    
    local response=$(curl -s -w "%{http_code}" -m "$timeout" "$url" -o /dev/null 2>/dev/null || echo "000")
    
    if [ "$response" = "$expected_status" ]; then
        return 0
    else
        return 1
    fi
}

# Function to check TCP port
check_tcp_port() {
    local host="$1"
    local port="$2"
    local timeout="${3:-$TIMEOUT}"
    
    timeout "$timeout" bash -c "</dev/tcp/$host/$port" 2>/dev/null
}

# Function to check application health
check_application() {
    local service="multimodal-librarian"
    local status="UNKNOWN"
    local details=""
    
    if ! check_service_running "$service"; then
        status="DOWN"
        details="Container not running"
    elif check_http_endpoint "http://localhost:8000/health/simple" 200 5; then
        status="UP"
        details="Health endpoint responding"
        
        # Check detailed health if available
        if check_http_endpoint "http://localhost:8000/health/detailed" 200 5; then
            local health_response=$(curl -s -m 5 "http://localhost:8000/health/detailed" 2>/dev/null || echo "{}")
            if echo "$health_response" | grep -q '"overall":true'; then
                details="All health checks passing"
            else
                status="DEGRADED"
                details="Some health checks failing"
            fi
        fi
    else
        status="DOWN"
        details="Health endpoint not responding"
    fi
    
    printf "%-20s %s\n" "$service" "$(format_status "$status" "$details")"
    
    if [ "$VERBOSE" = true ] && [ "$status" != "UP" ]; then
        echo "  Logs (last 10 lines):"
        docker-compose -f "$COMPOSE_FILE" logs --tail=10 "$service" 2>/dev/null | sed 's/^/    /'
    fi
    
    [ "$status" = "UP" ]
}

# Function to check PostgreSQL health
check_postgres() {
    local service="postgres"
    local status="UNKNOWN"
    local details=""
    
    if ! check_service_running "$service"; then
        status="DOWN"
        details="Container not running"
    elif check_tcp_port "localhost" "5432" 3; then
        # Try to connect and run a simple query
        if docker-compose -f "$COMPOSE_FILE" exec -T "$service" pg_isready -U ml_user -d multimodal_librarian >/dev/null 2>&1; then
            status="UP"
            details="Database accepting connections"
            
            # Check if we can run queries
            if docker-compose -f "$COMPOSE_FILE" exec -T "$service" psql -U ml_user -d multimodal_librarian -c "SELECT 1;" >/dev/null 2>&1; then
                details="Database queries working"
            else
                status="DEGRADED"
                details="Connection OK but queries failing"
            fi
        else
            status="DOWN"
            details="Database not ready"
        fi
    else
        status="DOWN"
        details="Port 5432 not accessible"
    fi
    
    printf "%-20s %s\n" "$service" "$(format_status "$status" "$details")"
    
    if [ "$VERBOSE" = true ] && [ "$status" != "UP" ]; then
        echo "  Logs (last 5 lines):"
        docker-compose -f "$COMPOSE_FILE" logs --tail=5 "$service" 2>/dev/null | sed 's/^/    /'
    fi
    
    [ "$status" = "UP" ]
}

# Function to check Neo4j health
check_neo4j() {
    local service="neo4j"
    local status="UNKNOWN"
    local details=""
    
    if ! check_service_running "$service"; then
        status="DOWN"
        details="Container not running"
    elif check_http_endpoint "http://localhost:7474" 200 5; then
        # Try to connect via Cypher shell
        if docker-compose -f "$COMPOSE_FILE" exec -T "$service" cypher-shell -u neo4j -p ml_password "RETURN 1" >/dev/null 2>&1; then
            status="UP"
            details="Database queries working"
        else
            status="DEGRADED"
            details="HTTP OK but Cypher queries failing"
        fi
    elif check_tcp_port "localhost" "7687" 3; then
        status="DEGRADED"
        details="Bolt port accessible but HTTP not ready"
    else
        status="DOWN"
        details="Ports not accessible"
    fi
    
    printf "%-20s %s\n" "$service" "$(format_status "$status" "$details")"
    
    if [ "$VERBOSE" = true ] && [ "$status" != "UP" ]; then
        echo "  Logs (last 5 lines):"
        docker-compose -f "$COMPOSE_FILE" logs --tail=5 "$service" 2>/dev/null | sed 's/^/    /'
    fi
    
    [ "$status" = "UP" ]
}

# Function to check Milvus health
check_milvus() {
    local service="milvus"
    local status="UNKNOWN"
    local details=""
    
    if ! check_service_running "$service"; then
        status="DOWN"
        details="Container not running"
    elif check_http_endpoint "http://localhost:9091/healthz" 200 5; then
        status="UP"
        details="Health endpoint responding"
        
        # Check if gRPC port is accessible
        if check_tcp_port "localhost" "19530" 3; then
            details="HTTP and gRPC ports accessible"
        else
            status="DEGRADED"
            details="HTTP OK but gRPC port not accessible"
        fi
    else
        status="DOWN"
        details="Health endpoint not responding"
    fi
    
    printf "%-20s %s\n" "$service" "$(format_status "$status" "$details")"
    
    if [ "$VERBOSE" = true ] && [ "$status" != "UP" ]; then
        echo "  Logs (last 5 lines):"
        docker-compose -f "$COMPOSE_FILE" logs --tail=5 "$service" 2>/dev/null | sed 's/^/    /'
    fi
    
    [ "$status" = "UP" ]
}

# Function to check Redis health
check_redis() {
    local service="redis"
    local status="UNKNOWN"
    local details=""
    
    if ! check_service_running "$service"; then
        status="DOWN"
        details="Container not running"
    elif docker-compose -f "$COMPOSE_FILE" exec -T "$service" redis-cli ping | grep -q "PONG"; then
        status="UP"
        details="Redis responding to ping"
    else
        status="DOWN"
        details="Redis not responding"
    fi
    
    printf "%-20s %s\n" "$service" "$(format_status "$status" "$details")"
    
    if [ "$VERBOSE" = true ] && [ "$status" != "UP" ]; then
        echo "  Logs (last 5 lines):"
        docker-compose -f "$COMPOSE_FILE" logs --tail=5 "$service" 2>/dev/null | sed 's/^/    /'
    fi
    
    [ "$status" = "UP" ]
}

# Function to check etcd health
check_etcd() {
    local service="etcd"
    local status="UNKNOWN"
    local details=""
    
    if ! check_service_running "$service"; then
        status="DOWN"
        details="Container not running"
    elif docker-compose -f "$COMPOSE_FILE" exec -T "$service" etcdctl endpoint health >/dev/null 2>&1; then
        status="UP"
        details="etcd cluster healthy"
    else
        status="DOWN"
        details="etcd health check failed"
    fi
    
    printf "%-20s %s\n" "$service" "$(format_status "$status" "$details")"
    
    if [ "$VERBOSE" = true ] && [ "$status" != "UP" ]; then
        echo "  Logs (last 5 lines):"
        docker-compose -f "$COMPOSE_FILE" logs --tail=5 "$service" 2>/dev/null | sed 's/^/    /'
    fi
    
    [ "$status" = "UP" ]
}

# Function to check MinIO health
check_minio() {
    local service="minio"
    local status="UNKNOWN"
    local details=""
    
    if ! check_service_running "$service"; then
        status="DOWN"
        details="Container not running"
    elif check_http_endpoint "http://localhost:9000/minio/health/live" 200 5; then
        if check_http_endpoint "http://localhost:9000/minio/health/ready" 200 5; then
            status="UP"
            details="MinIO live and ready"
        else
            status="DEGRADED"
            details="MinIO live but not ready"
        fi
    else
        status="DOWN"
        details="Health endpoints not responding"
    fi
    
    printf "%-20s %s\n" "$service" "$(format_status "$status" "$details")"
    
    if [ "$VERBOSE" = true ] && [ "$status" != "UP" ]; then
        echo "  Logs (last 5 lines):"
        docker-compose -f "$COMPOSE_FILE" logs --tail=5 "$service" 2>/dev/null | sed 's/^/    /'
    fi
    
    [ "$status" = "UP" ]
}

# Function to format status output
format_status() {
    local status="$1"
    local details="$2"
    
    case "$status" in
        "UP")
            echo -e "${GREEN}✓ UP${NC} - $details"
            ;;
        "DOWN")
            echo -e "${RED}✗ DOWN${NC} - $details"
            ;;
        "DEGRADED")
            echo -e "${YELLOW}⚠ DEGRADED${NC} - $details"
            ;;
        *)
            echo -e "${BLUE}? UNKNOWN${NC} - $details"
            ;;
    esac
}

# Function to check system resources
check_system_resources() {
    echo ""
    echo "System Resources:"
    echo "=================="
    
    # Disk space
    local disk_usage=$(df . | tail -1 | awk '{print $5}' | sed 's/%//')
    local disk_status="OK"
    
    if [ "$disk_usage" -gt 90 ]; then
        disk_status="CRITICAL"
    elif [ "$disk_usage" -gt 80 ]; then
        disk_status="WARNING"
    fi
    
    printf "%-20s %s\n" "Disk Usage" "$(format_resource_status "$disk_status" "${disk_usage}% used")"
    
    # Memory usage (if available)
    if command -v free >/dev/null 2>&1; then
        local mem_usage=$(free | grep Mem | awk '{printf "%.0f", $3/$2 * 100.0}')
        local mem_status="OK"
        
        if [ "$mem_usage" -gt 90 ]; then
            mem_status="CRITICAL"
        elif [ "$mem_usage" -gt 80 ]; then
            mem_status="WARNING"
        fi
        
        printf "%-20s %s\n" "Memory Usage" "$(format_resource_status "$mem_status" "${mem_usage}% used")"
    fi
    
    # Docker daemon
    if docker info >/dev/null 2>&1; then
        printf "%-20s %s\n" "Docker Daemon" "$(format_resource_status "OK" "Running")"
    else
        printf "%-20s %s\n" "Docker Daemon" "$(format_resource_status "CRITICAL" "Not accessible")"
    fi
}

# Function to format resource status
format_resource_status() {
    local status="$1"
    local details="$2"
    
    case "$status" in
        "OK")
            echo -e "${GREEN}✓ OK${NC} - $details"
            ;;
        "WARNING")
            echo -e "${YELLOW}⚠ WARNING${NC} - $details"
            ;;
        "CRITICAL")
            echo -e "${RED}✗ CRITICAL${NC} - $details"
            ;;
        *)
            echo -e "${BLUE}? UNKNOWN${NC} - $details"
            ;;
    esac
}

# Function to show summary
show_summary() {
    local total_services="$1"
    local healthy_services="$2"
    local failed_services=$((total_services - healthy_services))
    
    echo ""
    echo "Summary:"
    echo "========"
    
    if [ "$failed_services" -eq 0 ]; then
        print_success "All $total_services services are healthy"
        return 0
    elif [ "$healthy_services" -gt 0 ]; then
        print_warning "$healthy_services/$total_services services are healthy ($failed_services failed)"
        return 1
    else
        print_error "All $total_services services are down"
        return 2
    fi
}

# Function to show help
show_help() {
    echo "Health Check Script for Local Development"
    echo ""
    echo "Usage: $0 [OPTIONS] [SERVICE]"
    echo ""
    echo "Options:"
    echo "  --verbose, -v       Show detailed output including logs"
    echo "  --timeout SECONDS   Set timeout for health checks (default: 10)"
    echo "  --ci                CI mode - machine readable output"
    echo "  --help, -h          Show this help message"
    echo ""
    echo "Services:"
    echo "  all                 Check all services (default)"
    echo "  app                 Check application only"
    echo "  postgres            Check PostgreSQL only"
    echo "  neo4j               Check Neo4j only"
    echo "  milvus              Check Milvus only"
    echo "  redis               Check Redis only"
    echo "  etcd                Check etcd only"
    echo "  minio               Check MinIO only"
    echo ""
    echo "Examples:"
    echo "  $0                  # Check all services"
    echo "  $0 --verbose        # Check all with detailed output"
    echo "  $0 postgres         # Check PostgreSQL only"
    echo "  $0 --ci             # CI mode output"
    echo ""
    echo "Exit codes:"
    echo "  0 - All services healthy"
    echo "  1 - Some services unhealthy"
    echo "  2 - All services down"
}

# Main execution
main() {
    local service_to_check="all"
    
    # Parse command line arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --verbose|-v)
                VERBOSE=true
                shift
                ;;
            --timeout)
                TIMEOUT="$2"
                shift 2
                ;;
            --ci)
                CI_MODE=true
                shift
                ;;
            --help|-h)
                show_help
                exit 0
                ;;
            all|app|postgres|neo4j|milvus|redis|etcd|minio)
                service_to_check="$1"
                shift
                ;;
            *)
                print_error "Unknown option: $1"
                show_help
                exit 1
                ;;
        esac
    done
    
    if [ "$CI_MODE" = false ]; then
        echo "============================================================================="
        echo "MULTIMODAL LIBRARIAN - HEALTH CHECK"
        echo "============================================================================="
        echo "Timestamp: $(date)"
        echo "Timeout: ${TIMEOUT}s"
        echo ""
        
        echo "Service Health:"
        echo "==============="
    fi
    
    local total_services=0
    local healthy_services=0
    
    # Check services based on selection
    case "$service_to_check" in
        "all")
            services=("app" "postgres" "neo4j" "milvus" "redis" "etcd" "minio")
            ;;
        "app")
            services=("app")
            ;;
        *)
            services=("$service_to_check")
            ;;
    esac
    
    # Run health checks
    for service in "${services[@]}"; do
        total_services=$((total_services + 1))
        
        case "$service" in
            "app")
                if check_application; then
                    healthy_services=$((healthy_services + 1))
                fi
                ;;
            "postgres")
                if check_postgres; then
                    healthy_services=$((healthy_services + 1))
                fi
                ;;
            "neo4j")
                if check_neo4j; then
                    healthy_services=$((healthy_services + 1))
                fi
                ;;
            "milvus")
                if check_milvus; then
                    healthy_services=$((healthy_services + 1))
                fi
                ;;
            "redis")
                if check_redis; then
                    healthy_services=$((healthy_services + 1))
                fi
                ;;
            "etcd")
                if check_etcd; then
                    healthy_services=$((healthy_services + 1))
                fi
                ;;
            "minio")
                if check_minio; then
                    healthy_services=$((healthy_services + 1))
                fi
                ;;
        esac
    done
    
    # Show system resources if checking all services
    if [ "$service_to_check" = "all" ] && [ "$CI_MODE" = false ]; then
        check_system_resources
    fi
    
    # Show summary
    if [ "$CI_MODE" = false ]; then
        show_summary "$total_services" "$healthy_services"
        exit_code=$?
        
        echo ""
        echo "============================================================================="
        
        exit $exit_code
    else
        # CI mode - simple output
        if [ "$healthy_services" -eq "$total_services" ]; then
            echo "HEALTHY: $healthy_services/$total_services"
            exit 0
        else
            echo "UNHEALTHY: $healthy_services/$total_services"
            exit 1
        fi
    fi
}

# Run main function with all arguments
main "$@"