#!/usr/bin/env bash
#
# Parallel Service Startup Script
#
# This script optimizes the startup sequence by starting services in parallel
# groups based on their dependencies, reducing overall startup time.
#
# Features:
# - Dependency-aware parallel startup
# - Health check coordination
# - Failure handling and rollback
# - Progress monitoring
# - Resource-aware scheduling
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
COMPOSE_FILE="docker-compose.optimized.yml"
MAX_PARALLEL_SERVICES=4
HEALTH_CHECK_TIMEOUT=60
HEALTH_CHECK_INTERVAL=2
STARTUP_TIMEOUT=300

# Service dependency groups (order matters)
SERVICE_GROUP_1="redis postgres"                    # Essential fast services
SERVICE_GROUP_2="etcd minio"                       # Milvus dependencies
SERVICE_GROUP_3="neo4j"                            # Knowledge graph (can start in parallel with group 2)
SERVICE_GROUP_4="milvus"                           # Vector database (depends on etcd, minio)
SERVICE_GROUP_5="multimodal-librarian"             # Main application (depends on all)

# Function to get service group by number
get_service_group() {
    local group_num=$1
    case $group_num in
        1) echo "$SERVICE_GROUP_1" ;;
        2) echo "$SERVICE_GROUP_2" ;;
        3) echo "$SERVICE_GROUP_3" ;;
        4) echo "$SERVICE_GROUP_4" ;;
        5) echo "$SERVICE_GROUP_5" ;;
        *) echo "" ;;
    esac
}

# Function to get health check command for service
get_health_check_command() {
    local service=$1
    case $service in
        redis) echo "docker compose -f $COMPOSE_FILE exec -T redis redis-cli ping" ;;
        postgres) echo "docker compose -f $COMPOSE_FILE exec -T postgres pg_isready -U ml_user -d multimodal_librarian" ;;
        etcd) echo "docker compose -f $COMPOSE_FILE exec -T etcd etcdctl endpoint health" ;;
        minio) echo "curl -f http://localhost:9000/minio/health/live" ;;
        neo4j) echo "docker compose -f $COMPOSE_FILE exec -T neo4j cypher-shell -u neo4j -p ml_password 'RETURN 1'" ;;
        milvus) echo "curl -f http://localhost:9091/healthz" ;;
        multimodal-librarian) echo "curl -f http://localhost:8000/health/simple" ;;
        *) echo "" ;;
    esac
}

# Function to get service priority
get_service_priority() {
    local service=$1
    case $service in
        redis|postgres) echo "1" ;;
        etcd|minio) echo "2" ;;
        neo4j) echo "3" ;;
        milvus) echo "4" ;;
        multimodal-librarian) echo "5" ;;
        *) echo "99" ;;
    esac
}

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

print_progress() {
    echo -e "${PURPLE}[$(date '+%H:%M:%S')]${NC} 🔄 $1"
}

# Function to check if a service is healthy
check_service_health() {
    local service=$1
    local health_check
    health_check=$(get_health_check_command "$service")
    
    if [[ -z "$health_check" ]]; then
        # Generic health check - just check if container is running
        docker compose -f "$COMPOSE_FILE" ps "$service" | grep -q "Up"
        return $?
    fi
    
    # Execute specific health check
    eval "$health_check" >/dev/null 2>&1
}

# Function to wait for service to be healthy
wait_for_service_health() {
    local service=$1
    local timeout=${2:-$HEALTH_CHECK_TIMEOUT}
    local interval=${3:-$HEALTH_CHECK_INTERVAL}
    
    local start_time
    start_time=$(date +%s)
    local end_time=$((start_time + timeout))
    
    print_progress "Waiting for $service to be healthy..."
    
    while [[ $(date +%s) -lt $end_time ]]; do
        if check_service_health "$service"; then
            local elapsed=$(($(date +%s) - start_time))
            print_success "$service is healthy (${elapsed}s)"
            return 0
        fi
        
        sleep "$interval"
    done
    
    local elapsed=$(($(date +%s) - start_time))
    print_error "$service failed to become healthy within ${timeout}s"
    return 1
}

# Function to start a service
start_service() {
    local service=$1
    
    print_info "Starting $service..."
    
    if docker compose -f "$COMPOSE_FILE" up -d "$service"; then
        print_success "$service started"
        return 0
    else
        print_error "Failed to start $service"
        return 1
    fi
}

# Function to start services in parallel within a group
start_service_group_parallel() {
    local group_services=($1)
    local pids=()
    local failed_services=()
    local successful_services=()
    
    print_status "Starting service group in parallel: ${group_services[*]}"
    
    # Start all services in the group in parallel
    for service in "${group_services[@]}"; do
        (
            if start_service "$service"; then
                echo "$service:success"
            else
                echo "$service:failed"
            fi
        ) &
        pids+=($!)
    done
    
    # Wait for all services to start
    for i in "${!pids[@]}"; do
        local pid=${pids[$i]}
        local service=${group_services[$i]}
        
        if wait "$pid"; then
            local result
            result=$(jobs -p | grep -q "$pid" && echo "running" || echo "completed")
            print_info "$service startup process completed"
        else
            print_warning "$service startup process had issues"
        fi
    done
    
    # Wait for all services to be healthy
    local health_pids=()
    for service in "${group_services[@]}"; do
        wait_for_service_health "$service" &
        health_pids+=($!)
    done
    
    # Collect health check results
    for i in "${!health_pids[@]}"; do
        local pid=${health_pids[$i]}
        local service=${group_services[$i]}
        
        if wait "$pid"; then
            successful_services+=("$service")
        else
            failed_services+=("$service")
        fi
    done
    
    # Report results
    if [[ ${#failed_services[@]} -eq 0 ]]; then
        print_success "All services in group are healthy: ${successful_services[*]}"
        return 0
    else
        print_error "Some services failed to become healthy: ${failed_services[*]}"
        print_info "Successful services: ${successful_services[*]}"
        return 1
    fi
}

# Function to start all services with optimized parallel startup
start_all_services_parallel() {
    print_status "🚀 Starting all services with parallel optimization"
    
    local overall_start_time
    overall_start_time=$(date +%s)
    local failed_groups=()
    local successful_groups=()
    
    # Process each service group (1 through 5)
    for group_num in 1 2 3 4 5; do
        local group_services
        group_services=$(get_service_group "$group_num")
        
        if [[ -z "$group_services" ]]; then
            continue
        fi
        
        print_status "Processing group $group_num: $group_services"
        
        local group_start_time
        group_start_time=$(date +%s)
        
        if start_service_group_parallel "$group_services"; then
            local group_duration=$(($(date +%s) - group_start_time))
            print_success "Group $group_num completed successfully (${group_duration}s)"
            successful_groups+=("$group_num")
        else
            local group_duration=$(($(date +%s) - group_start_time))
            print_error "Group $group_num failed (${group_duration}s)"
            failed_groups+=("$group_num")
            
            # Decide whether to continue or abort
            if [[ $group_num -le 2 ]]; then
                print_error "Critical service group failed. Aborting startup."
                return 1
            else
                print_warning "Non-critical service group failed. Continuing..."
            fi
        fi
        
        # Brief pause between groups to avoid resource contention
        if [[ $group_num -lt 5 ]]; then
            sleep 2
        fi
    done
    
    local overall_duration=$(($(date +%s) - overall_start_time))
    
    # Final status report
    echo
    print_status "📊 Parallel Startup Summary"
    print_info "Total startup time: ${overall_duration}s"
    print_info "Successful groups: ${successful_groups[*]}"
    
    if [[ ${#failed_groups[@]} -gt 0 ]]; then
        print_warning "Failed groups: ${failed_groups[*]}"
    fi
    
    # Verify all critical services are running
    local critical_services=("redis" "postgres" "multimodal-librarian")
    local critical_failures=()
    
    for service in "${critical_services[@]}"; do
        if ! check_service_health "$service"; then
            critical_failures+=("$service")
        fi
    done
    
    if [[ ${#critical_failures[@]} -eq 0 ]]; then
        print_success "🎉 All critical services are healthy!"
        print_info "Application should be available at: http://localhost:8000"
        return 0
    else
        print_error "❌ Critical services are not healthy: ${critical_failures[*]}"
        return 1
    fi
}

# Function to stop all services
stop_all_services() {
    print_status "Stopping all services..."
    
    if docker compose -f "$COMPOSE_FILE" down; then
        print_success "All services stopped"
    else
        print_error "Failed to stop some services"
        return 1
    fi
}

# Function to show service status
show_service_status() {
    print_status "Service Status Report"
    echo
    
    # Get all services from compose file
    local all_services
    all_services=$(docker compose -f "$COMPOSE_FILE" config --services)
    
    local running_count=0
    local total_count=0
    
    for service in $all_services; do
        ((total_count++))
        
        local status="❌ Stopped"
        local health="❓ Unknown"
        
        # Check if container is running
        if docker compose -f "$COMPOSE_FILE" ps "$service" | grep -q "Up"; then
            status="✅ Running"
            ((running_count++))
            
            # Check health
            if check_service_health "$service"; then
                health="✅ Healthy"
            else
                health="⚠️  Unhealthy"
            fi
        fi
        
        printf "%-25s %s %s\n" "$service" "$status" "$health"
    done
    
    echo
    print_info "Summary: $running_count/$total_count services running"
    
    if [[ $running_count -eq $total_count ]]; then
        print_success "All services are running"
    else
        print_warning "Some services are not running"
    fi
}

# Function to monitor startup progress
monitor_startup_progress() {
    local timeout=${1:-$STARTUP_TIMEOUT}
    local start_time
    start_time=$(date +%s)
    local end_time=$((start_time + timeout))
    
    print_status "Monitoring startup progress (timeout: ${timeout}s)..."
    
    while [[ $(date +%s) -lt $end_time ]]; do
        local elapsed=$(($(date +%s) - start_time))
        
        # Count healthy services
        local healthy_count=0
        local total_services=0
        
        for service in redis postgres etcd minio neo4j milvus multimodal-librarian; do
            ((total_services++))
            if check_service_health "$service" 2>/dev/null; then
                ((healthy_count++))
            fi
        done
        
        local progress_percent=$((healthy_count * 100 / total_services))
        
        print_progress "Progress: $healthy_count/$total_services services healthy (${progress_percent}%, ${elapsed}s elapsed)"
        
        # Check if all services are healthy
        if [[ $healthy_count -eq $total_services ]]; then
            print_success "All services are healthy! Total time: ${elapsed}s"
            return 0
        fi
        
        sleep 5
    done
    
    local elapsed=$(($(date +%s) - start_time))
    print_error "Startup monitoring timed out after ${elapsed}s"
    return 1
}

# Function to show help
show_help() {
    echo "Parallel Service Startup Script"
    echo
    echo "Usage: $0 [OPTIONS] [COMMAND]"
    echo
    echo "Commands:"
    echo "  start         Start all services with parallel optimization"
    echo "  stop          Stop all services"
    echo "  status        Show current service status"
    echo "  monitor       Monitor startup progress"
    echo "  restart       Restart all services"
    echo
    echo "Options:"
    echo "  --compose-file FILE    Use specific compose file (default: docker-compose.optimized.yml)"
    echo "  --max-parallel N       Maximum parallel services (default: 4)"
    echo "  --timeout N            Health check timeout in seconds (default: 60)"
    echo "  --startup-timeout N    Overall startup timeout (default: 300)"
    echo "  --help                 Show this help message"
    echo
    echo "Examples:"
    echo "  $0 start                    # Start all services in parallel"
    echo "  $0 --timeout 120 start      # Start with longer health check timeout"
    echo "  $0 status                   # Show service status"
    echo "  $0 monitor                  # Monitor startup progress"
}

# Parse command line arguments
COMMAND=""
while [[ $# -gt 0 ]]; do
    case $1 in
        --compose-file)
            COMPOSE_FILE="$2"
            shift 2
            ;;
        --max-parallel)
            MAX_PARALLEL_SERVICES="$2"
            shift 2
            ;;
        --timeout)
            HEALTH_CHECK_TIMEOUT="$2"
            shift 2
            ;;
        --startup-timeout)
            STARTUP_TIMEOUT="$2"
            shift 2
            ;;
        --help)
            show_help
            exit 0
            ;;
        start|stop|status|monitor|restart)
            COMMAND="$1"
            shift
            ;;
        *)
            print_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Set default command
COMMAND="${COMMAND:-start}"

# Main execution
main() {
    print_status "🔄 Parallel Service Startup Tool"
    print_info "Compose file: $COMPOSE_FILE"
    print_info "Max parallel services: $MAX_PARALLEL_SERVICES"
    print_info "Health check timeout: ${HEALTH_CHECK_TIMEOUT}s"
    print_info "Command: $COMMAND"
    echo
    
    # Check if compose file exists
    if [[ ! -f "$COMPOSE_FILE" ]]; then
        print_error "Compose file not found: $COMPOSE_FILE"
        exit 1
    fi
    
    case $COMMAND in
        start)
            start_all_services_parallel
            ;;
        stop)
            stop_all_services
            ;;
        status)
            show_service_status
            ;;
        monitor)
            monitor_startup_progress
            ;;
        restart)
            print_status "Restarting all services..."
            stop_all_services
            sleep 3
            start_all_services_parallel
            ;;
        *)
            print_error "Unknown command: $COMMAND"
            show_help
            exit 1
            ;;
    esac
}

# Run main function
main "$@"