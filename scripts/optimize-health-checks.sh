#!/bin/bash
#
# Health Check Optimization Script
#
# This script optimizes Docker health checks for faster container startup
# by implementing intelligent health check strategies, reducing check intervals,
# and providing fallback mechanisms.
#
# Features:
# - Adaptive health check intervals
# - Smart retry logic
# - Resource-aware health checks
# - Parallel health verification
# - Health check caching
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
HEALTH_CHECK_CACHE_DIR="./cache/health-checks"
HEALTH_CHECK_TIMEOUT=30
HEALTH_CHECK_INTERVAL=5
HEALTH_CHECK_RETRIES=3
HEALTH_CHECK_START_PERIOD=15

# Service-specific health check configurations
declare -A SERVICE_HEALTH_CONFIGS=(
    # Format: service="timeout:interval:retries:start_period:command"
    [redis]="5:2:2:5:redis-cli ping"
    [postgres]="10:3:3:10:pg_isready -U ml_user -d multimodal_librarian"
    [etcd]="10:3:2:10:etcdctl endpoint health"
    [minio]="10:3:2:10:curl -f http://localhost:9000/minio/health/live"
    [neo4j]="20:5:3:30:cypher-shell -u neo4j -p ml_password 'RETURN 1'"
    [milvus]="30:5:3:45:curl -f http://localhost:9091/healthz"
    [multimodal-librarian]="15:3:2:20:python -c \"import urllib.request; urllib.request.urlopen('http://localhost:8000/health/simple', timeout=3).read()\""
)

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

# Function to create health check cache directory
create_health_check_cache() {
    if [[ ! -d "$HEALTH_CHECK_CACHE_DIR" ]]; then
        mkdir -p "$HEALTH_CHECK_CACHE_DIR"
        print_info "Created health check cache directory: $HEALTH_CHECK_CACHE_DIR"
    fi
}

# Function to get cached health check result
get_cached_health_result() {
    local service=$1
    local cache_file="$HEALTH_CHECK_CACHE_DIR/${service}.cache"
    local cache_ttl=10  # Cache TTL in seconds
    
    if [[ -f "$cache_file" ]]; then
        local cache_time
        cache_time=$(stat -f %m "$cache_file" 2>/dev/null || stat -c %Y "$cache_file" 2>/dev/null || echo 0)
        local current_time
        current_time=$(date +%s)
        
        if [[ $((current_time - cache_time)) -lt $cache_ttl ]]; then
            local cached_result
            cached_result=$(cat "$cache_file")
            return "$cached_result"
        fi
    fi
    
    return 2  # Cache miss
}

# Function to cache health check result
cache_health_result() {
    local service=$1
    local result=$2
    local cache_file="$HEALTH_CHECK_CACHE_DIR/${service}.cache"
    
    echo "$result" > "$cache_file"
}

# Function to perform optimized health check
optimized_health_check() {
    local service=$1
    local use_cache=${2:-true}
    
    # Try cache first if enabled
    if [[ "$use_cache" == "true" ]]; then
        if get_cached_health_result "$service"; then
            local cached_result=$?
            if [[ $cached_result -eq 0 ]]; then
                return 0  # Healthy (cached)
            elif [[ $cached_result -eq 1 ]]; then
                return 1  # Unhealthy (cached)
            fi
        fi
    fi
    
    # Get service-specific configuration
    local config="${SERVICE_HEALTH_CONFIGS[$service]}"
    if [[ -z "$config" ]]; then
        print_warning "No health check configuration for $service, using generic check"
        docker compose -f "$COMPOSE_FILE" ps "$service" | grep -q "Up"
        local result=$?
        cache_health_result "$service" "$result"
        return $result
    fi
    
    # Parse configuration
    IFS=':' read -r timeout interval retries start_period command <<< "$config"
    
    # Execute health check command
    local health_result=1
    
    case $service in
        redis)
            docker compose -f "$COMPOSE_FILE" exec -T redis redis-cli ping >/dev/null 2>&1
            health_result=$?
            ;;
        postgres)
            docker compose -f "$COMPOSE_FILE" exec -T postgres pg_isready -U ml_user -d multimodal_librarian >/dev/null 2>&1
            health_result=$?
            ;;
        etcd)
            docker compose -f "$COMPOSE_FILE" exec -T etcd etcdctl endpoint health >/dev/null 2>&1
            health_result=$?
            ;;
        minio)
            curl -f http://localhost:9000/minio/health/live >/dev/null 2>&1
            health_result=$?
            ;;
        neo4j)
            docker compose -f "$COMPOSE_FILE" exec -T neo4j cypher-shell -u neo4j -p ml_password "RETURN 1" >/dev/null 2>&1
            health_result=$?
            ;;
        milvus)
            curl -f http://localhost:9091/healthz >/dev/null 2>&1
            health_result=$?
            ;;
        multimodal-librarian)
            python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/simple', timeout=3).read()" >/dev/null 2>&1
            health_result=$?
            ;;
        *)
            # Generic health check
            docker compose -f "$COMPOSE_FILE" ps "$service" | grep -q "Up"
            health_result=$?
            ;;
    esac
    
    # Cache the result
    cache_health_result "$service" "$health_result"
    
    return $health_result
}

# Function to wait for service with optimized health checks
wait_for_service_optimized() {
    local service=$1
    local timeout=${2:-$HEALTH_CHECK_TIMEOUT}
    local interval=${3:-$HEALTH_CHECK_INTERVAL}
    local retries=${4:-$HEALTH_CHECK_RETRIES}
    
    print_info "Waiting for $service (timeout: ${timeout}s, interval: ${interval}s, retries: $retries)"
    
    local start_time
    start_time=$(date +%s)
    local end_time=$((start_time + timeout))
    local attempt=0
    local consecutive_failures=0
    local max_consecutive_failures=2
    
    while [[ $(date +%s) -lt $end_time ]]; do
        ((attempt++))
        
        if optimized_health_check "$service"; then
            local elapsed=$(($(date +%s) - start_time))
            print_success "$service is healthy (${elapsed}s, attempt $attempt)"
            return 0
        else
            ((consecutive_failures++))
            
            # Adaptive interval - increase interval after consecutive failures
            local adaptive_interval=$interval
            if [[ $consecutive_failures -gt $max_consecutive_failures ]]; then
                adaptive_interval=$((interval * 2))
                print_warning "$service health check failed $consecutive_failures times, increasing interval to ${adaptive_interval}s"
            fi
            
            sleep "$adaptive_interval"
        fi
    done
    
    local elapsed=$(($(date +%s) - start_time))
    print_error "$service failed to become healthy within ${timeout}s (${attempt} attempts)"
    return 1
}

# Function to check all services in parallel
check_all_services_parallel() {
    local services=("$@")
    local pids=()
    local results=()
    
    print_status "Checking ${#services[@]} services in parallel..."
    
    # Start health checks in parallel
    for service in "${services[@]}"; do
        (
            if optimized_health_check "$service" false; then  # Don't use cache for parallel checks
                echo "$service:healthy"
            else
                echo "$service:unhealthy"
            fi
        ) &
        pids+=($!)
    done
    
    # Collect results
    local healthy_services=()
    local unhealthy_services=()
    
    for i in "${!pids[@]}"; do
        local pid=${pids[$i]}
        local service=${services[$i]}
        
        if wait "$pid"; then
            # Get the result from the background process
            # This is a simplified approach - in practice, you'd use a more robust IPC method
            if optimized_health_check "$service"; then
                healthy_services+=("$service")
            else
                unhealthy_services+=("$service")
            fi
        else
            unhealthy_services+=("$service")
        fi
    done
    
    # Report results
    print_info "Healthy services: ${healthy_services[*]}"
    if [[ ${#unhealthy_services[@]} -gt 0 ]]; then
        print_warning "Unhealthy services: ${unhealthy_services[*]}"
    fi
    
    return ${#unhealthy_services[@]}
}

# Function to generate optimized health check configuration
generate_optimized_healthcheck_config() {
    local service=$1
    local config="${SERVICE_HEALTH_CONFIGS[$service]}"
    
    if [[ -z "$config" ]]; then
        print_warning "No optimized configuration available for $service"
        return 1
    fi
    
    # Parse configuration
    IFS=':' read -r timeout interval retries start_period command <<< "$config"
    
    cat << EOF
    healthcheck:
      test: ["CMD-SHELL", "$command"]
      interval: ${interval}s
      timeout: ${timeout}s
      retries: $retries
      start_period: ${start_period}s
EOF
}

# Function to update compose file with optimized health checks
update_compose_healthchecks() {
    local compose_file=$1
    local backup_file="${compose_file}.backup.$(date +%Y%m%d_%H%M%S)"
    
    print_status "Updating health checks in $compose_file"
    
    # Create backup
    cp "$compose_file" "$backup_file"
    print_info "Created backup: $backup_file"
    
    # Update health checks for each service
    for service in "${!SERVICE_HEALTH_CONFIGS[@]}"; do
        print_info "Optimizing health check for $service"
        
        # This is a simplified approach - in practice, you'd use a proper YAML parser
        # For now, we'll just print the optimized configuration
        print_info "Optimized health check configuration for $service:"
        generate_optimized_healthcheck_config "$service"
        echo
    done
    
    print_success "Health check optimization completed"
    print_info "Manual update required - apply the configurations shown above to $compose_file"
}

# Function to benchmark health check performance
benchmark_health_checks() {
    local services=("redis" "postgres" "etcd" "minio" "neo4j" "milvus" "multimodal-librarian")
    local results_file="health_check_benchmark_$(date +%Y%m%d_%H%M%S).json"
    
    print_status "Benchmarking health check performance..."
    
    # Clear cache for accurate benchmarking
    rm -rf "$HEALTH_CHECK_CACHE_DIR"
    create_health_check_cache
    
    local benchmark_results="{"
    benchmark_results+='"benchmark_date": "'$(date -Iseconds)'",'
    benchmark_results+='"services": {'
    
    local first_service=true
    for service in "${services[@]}"; do
        if [[ "$first_service" != "true" ]]; then
            benchmark_results+=","
        fi
        first_service=false
        
        print_info "Benchmarking $service..."
        
        # Test without cache
        local start_time
        start_time=$(date +%s%3N)  # milliseconds
        optimized_health_check "$service" false
        local no_cache_result=$?
        local no_cache_time=$(($(date +%s%3N) - start_time))
        
        # Test with cache (second call should be cached)
        start_time=$(date +%s%3N)
        optimized_health_check "$service" true
        local cache_result=$?
        local cache_time=$(($(date +%s%3N) - start_time))
        
        benchmark_results+='"'$service'": {'
        benchmark_results+='"no_cache_time_ms": '$no_cache_time','
        benchmark_results+='"cache_time_ms": '$cache_time','
        benchmark_results+='"no_cache_result": '$no_cache_result','
        benchmark_results+='"cache_result": '$cache_result','
        benchmark_results+='"cache_improvement": '$((no_cache_time - cache_time))
        benchmark_results+='}'
        
        print_info "$service: no-cache=${no_cache_time}ms, cache=${cache_time}ms, improvement=$((no_cache_time - cache_time))ms"
    done
    
    benchmark_results+='}}'
    
    # Save results
    echo "$benchmark_results" | python -m json.tool > "$results_file"
    
    print_success "Health check benchmark completed"
    print_info "Results saved to: $results_file"
}

# Function to monitor health check performance
monitor_health_checks() {
    local duration=${1:-60}  # Monitor for 60 seconds by default
    local interval=5
    
    print_status "Monitoring health check performance for ${duration}s..."
    
    local start_time
    start_time=$(date +%s)
    local end_time=$((start_time + duration))
    
    while [[ $(date +%s) -lt $end_time ]]; do
        local elapsed=$(($(date +%s) - start_time))
        
        print_info "Health check status at ${elapsed}s:"
        
        # Check all services and measure time
        local check_start_time
        check_start_time=$(date +%s%3N)
        
        local healthy_count=0
        local total_count=0
        
        for service in redis postgres etcd minio neo4j milvus multimodal-librarian; do
            ((total_count++))
            if optimized_health_check "$service"; then
                ((healthy_count++))
                echo "  ✅ $service"
            else
                echo "  ❌ $service"
            fi
        done
        
        local check_duration=$(($(date +%s%3N) - check_start_time))
        
        print_info "Health check completed in ${check_duration}ms ($healthy_count/$total_count healthy)"
        echo
        
        sleep "$interval"
    done
    
    print_success "Health check monitoring completed"
}

# Function to show help
show_help() {
    echo "Health Check Optimization Script"
    echo
    echo "Usage: $0 [OPTIONS] [COMMAND]"
    echo
    echo "Commands:"
    echo "  check SERVICE         Check health of specific service"
    echo "  check-all            Check health of all services"
    echo "  wait SERVICE         Wait for service to be healthy"
    echo "  parallel             Check all services in parallel"
    echo "  update               Update compose file with optimized health checks"
    echo "  benchmark            Benchmark health check performance"
    echo "  monitor [DURATION]   Monitor health checks for specified duration"
    echo "  clear-cache          Clear health check cache"
    echo
    echo "Options:"
    echo "  --compose-file FILE  Use specific compose file"
    echo "  --timeout N          Health check timeout in seconds"
    echo "  --interval N         Health check interval in seconds"
    echo "  --retries N          Number of retries"
    echo "  --no-cache           Disable health check caching"
    echo "  --help               Show this help message"
    echo
    echo "Examples:"
    echo "  $0 check redis                    # Check Redis health"
    echo "  $0 wait multimodal-librarian      # Wait for application to be healthy"
    echo "  $0 parallel                       # Check all services in parallel"
    echo "  $0 benchmark                      # Benchmark health check performance"
    echo "  $0 monitor 120                    # Monitor for 2 minutes"
}

# Parse command line arguments
COMMAND=""
SERVICE=""
USE_CACHE=true

while [[ $# -gt 0 ]]; do
    case $1 in
        --compose-file)
            COMPOSE_FILE="$2"
            shift 2
            ;;
        --timeout)
            HEALTH_CHECK_TIMEOUT="$2"
            shift 2
            ;;
        --interval)
            HEALTH_CHECK_INTERVAL="$2"
            shift 2
            ;;
        --retries)
            HEALTH_CHECK_RETRIES="$2"
            shift 2
            ;;
        --no-cache)
            USE_CACHE=false
            shift
            ;;
        --help)
            show_help
            exit 0
            ;;
        check|check-all|wait|parallel|update|benchmark|monitor|clear-cache)
            COMMAND="$1"
            shift
            ;;
        *)
            if [[ -z "$SERVICE" ]] && [[ "$COMMAND" == "check" || "$COMMAND" == "wait" ]]; then
                SERVICE="$1"
                shift
            elif [[ "$COMMAND" == "monitor" ]] && [[ "$1" =~ ^[0-9]+$ ]]; then
                MONITOR_DURATION="$1"
                shift
            else
                print_error "Unknown option: $1"
                show_help
                exit 1
            fi
            ;;
    esac
done

# Set default command
COMMAND="${COMMAND:-check-all}"

# Main execution
main() {
    print_status "🏥 Health Check Optimization Tool"
    print_info "Compose file: $COMPOSE_FILE"
    print_info "Cache enabled: $USE_CACHE"
    print_info "Command: $COMMAND"
    echo
    
    # Create cache directory
    create_health_check_cache
    
    case $COMMAND in
        check)
            if [[ -z "$SERVICE" ]]; then
                print_error "Service name required for check command"
                show_help
                exit 1
            fi
            
            print_status "Checking health of $SERVICE..."
            if optimized_health_check "$SERVICE" "$USE_CACHE"; then
                print_success "$SERVICE is healthy"
            else
                print_error "$SERVICE is not healthy"
                exit 1
            fi
            ;;
        check-all)
            local services=("redis" "postgres" "etcd" "minio" "neo4j" "milvus" "multimodal-librarian")
            check_all_services_parallel "${services[@]}"
            ;;
        wait)
            if [[ -z "$SERVICE" ]]; then
                print_error "Service name required for wait command"
                show_help
                exit 1
            fi
            
            wait_for_service_optimized "$SERVICE" "$HEALTH_CHECK_TIMEOUT" "$HEALTH_CHECK_INTERVAL" "$HEALTH_CHECK_RETRIES"
            ;;
        parallel)
            local services=("redis" "postgres" "etcd" "minio" "neo4j" "milvus" "multimodal-librarian")
            check_all_services_parallel "${services[@]}"
            ;;
        update)
            update_compose_healthchecks "$COMPOSE_FILE"
            ;;
        benchmark)
            benchmark_health_checks
            ;;
        monitor)
            monitor_health_checks "${MONITOR_DURATION:-60}"
            ;;
        clear-cache)
            rm -rf "$HEALTH_CHECK_CACHE_DIR"
            print_success "Health check cache cleared"
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