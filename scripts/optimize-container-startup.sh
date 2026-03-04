#!/bin/bash
#
# Container Startup Optimization Script
#
# This script implements various optimizations to reduce container startup times
# for the local development environment.
#
# Features:
# - Parallel service startup optimization
# - Resource allocation tuning
# - Health check optimization
# - Image layer caching
# - Dependency chain optimization
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
ORIGINAL_COMPOSE_FILE="docker-compose.local.yml"
OPTIMIZATION_LEVEL="medium"
ENABLE_TMPFS=true
ENABLE_PARALLEL_BUILD=true
ENABLE_CACHE_OPTIMIZATION=true

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
    echo "Container Startup Optimization Script"
    echo
    echo "Usage: $0 [OPTIONS] [COMMAND]"
    echo
    echo "Commands:"
    echo "  optimize      Apply all optimizations and start services"
    echo "  build         Build optimized images with caching"
    echo "  start         Start services with optimizations"
    echo "  stop          Stop all services"
    echo "  clean         Clean up optimization artifacts"
    echo "  benchmark     Benchmark startup times"
    echo "  status        Show optimization status"
    echo
    echo "Options:"
    echo "  --level LEVEL         Optimization level: low, medium, high (default: medium)"
    echo "  --no-tmpfs           Disable tmpfs volumes"
    echo "  --no-parallel        Disable parallel building"
    echo "  --no-cache           Disable cache optimization"
    echo "  --compose-file FILE  Use specific compose file"
    echo "  --help               Show this help message"
    echo
    echo "Examples:"
    echo "  $0 optimize                    # Apply all optimizations"
    echo "  $0 --level high optimize       # High-level optimizations"
    echo "  $0 benchmark                   # Benchmark startup times"
    echo "  $0 build --no-cache           # Build without cache optimization"
}

# Function to check system requirements
check_system_requirements() {
    print_status "Checking system requirements for optimizations..."
    
    # Check Docker version
    if ! docker --version >/dev/null 2>&1; then
        print_error "Docker not found"
        return 1
    fi
    
    # Check Docker Compose version
    if ! docker compose version >/dev/null 2>&1; then
        print_error "Docker Compose not found"
        return 1
    fi
    
    # Check available memory
    local available_memory
    if command -v free >/dev/null 2>&1; then
        available_memory=$(free -m | awk 'NR==2{printf "%.0f", $7}')
        if [[ $available_memory -lt 4096 ]]; then
            print_warning "Available memory is ${available_memory}MB. Recommended: 4GB+"
        fi
    fi
    
    # Check available disk space
    local available_disk
    available_disk=$(df . | awk 'NR==2{print $4}')
    if [[ $available_disk -lt 10485760 ]]; then  # 10GB in KB
        print_warning "Available disk space is low. Recommended: 10GB+"
    fi
    
    # Check if tmpfs is supported
    if [[ "$ENABLE_TMPFS" == "true" ]]; then
        if ! mount | grep -q tmpfs; then
            print_warning "tmpfs not detected. Some optimizations may not work."
        fi
    fi
    
    print_success "System requirements check completed"
}

# Function to create cache directories
create_cache_directories() {
    print_status "Creating cache directories..."
    
    local cache_dirs=(
        "./cache/models"
        "./cache/pip"
        "./cache/pytest"
        "./data/postgres"
        "./data/neo4j"
        "./data/neo4j-logs"
        "./data/milvus"
        "./data/etcd"
        "./data/minio"
        "./data/redis"
    )
    
    for dir in "${cache_dirs[@]}"; do
        if [[ ! -d "$dir" ]]; then
            mkdir -p "$dir"
            print_info "Created cache directory: $dir"
        fi
    done
    
    print_success "Cache directories created"
}

# Function to optimize Docker daemon settings
optimize_docker_daemon() {
    print_status "Checking Docker daemon optimization..."
    
    # Check if Docker daemon has optimal settings
    local docker_info
    docker_info=$(docker info 2>/dev/null || echo "")
    
    if echo "$docker_info" | grep -q "Storage Driver: overlay2"; then
        print_success "Docker using overlay2 storage driver (optimal)"
    else
        print_warning "Docker not using overlay2 storage driver"
    fi
    
    # Check for BuildKit
    if [[ "${DOCKER_BUILDKIT:-}" == "1" ]] || echo "$docker_info" | grep -q "BuildKit"; then
        print_success "Docker BuildKit enabled (optimal for caching)"
    else
        print_info "Consider enabling Docker BuildKit: export DOCKER_BUILDKIT=1"
    fi
}

# Function to build optimized images
build_optimized_images() {
    print_status "Building optimized Docker images..."
    
    local build_args=()
    
    if [[ "$ENABLE_PARALLEL_BUILD" == "true" ]]; then
        build_args+=("--parallel")
    fi
    
    if [[ "$ENABLE_CACHE_OPTIMIZATION" == "true" ]]; then
        # Enable BuildKit for better caching
        export DOCKER_BUILDKIT=1
        export COMPOSE_DOCKER_CLI_BUILD=1
        
        # Build with cache mount
        build_args+=("--build-arg" "BUILDKIT_INLINE_CACHE=1")
    fi
    
    # Build the optimized images
    print_info "Building with args: ${build_args[*]}"
    
    if docker compose -f "$COMPOSE_FILE" build "${build_args[@]}" multimodal-librarian; then
        print_success "Optimized images built successfully"
    else
        print_error "Failed to build optimized images"
        return 1
    fi
}

# Function to start services with optimizations
start_optimized_services() {
    print_status "Starting services with optimizations..."
    
    # Start services in optimized order
    local service_groups=(
        "redis postgres"           # Fast-starting essential services
        "etcd minio"              # Milvus dependencies
        "neo4j"                   # Knowledge graph
        "milvus"                  # Vector database
        "multimodal-librarian"    # Main application
    )
    
    for group in "${service_groups[@]}"; do
        print_info "Starting service group: $group"
        
        # Start services in parallel within each group
        for service in $group; do
            docker compose -f "$COMPOSE_FILE" up -d "$service" &
        done
        
        # Wait for this group to be ready before starting next group
        wait
        
        # Quick health check for this group
        for service in $group; do
            print_info "Waiting for $service to be ready..."
            local retries=0
            local max_retries=30
            
            while [[ $retries -lt $max_retries ]]; do
                if docker compose -f "$COMPOSE_FILE" ps "$service" | grep -q "Up"; then
                    print_success "$service is ready"
                    break
                fi
                
                sleep 2
                ((retries++))
            done
            
            if [[ $retries -eq $max_retries ]]; then
                print_warning "$service took longer than expected to start"
            fi
        done
    done
    
    print_success "All services started with optimizations"
}

# Function to benchmark startup times
benchmark_startup_times() {
    print_status "Benchmarking container startup times..."
    
    local results_file="startup_benchmark_$(date +%Y%m%d_%H%M%S).json"
    
    # Test original compose file
    print_info "Testing original configuration..."
    local original_start_time
    original_start_time=$(date +%s)
    
    docker compose -f "$ORIGINAL_COMPOSE_FILE" down -v >/dev/null 2>&1 || true
    docker compose -f "$ORIGINAL_COMPOSE_FILE" up -d >/dev/null 2>&1
    
    # Wait for services to be ready
    ./scripts/wait-for-services.sh --file "$ORIGINAL_COMPOSE_FILE" --timeout 300 >/dev/null 2>&1
    
    local original_end_time
    original_end_time=$(date +%s)
    local original_duration=$((original_end_time - original_start_time))
    
    docker compose -f "$ORIGINAL_COMPOSE_FILE" down -v >/dev/null 2>&1
    
    # Test optimized compose file
    print_info "Testing optimized configuration..."
    local optimized_start_time
    optimized_start_time=$(date +%s)
    
    docker compose -f "$COMPOSE_FILE" down -v >/dev/null 2>&1 || true
    docker compose -f "$COMPOSE_FILE" up -d >/dev/null 2>&1
    
    # Wait for services to be ready
    ./scripts/wait-for-services.sh --file "$COMPOSE_FILE" --timeout 300 >/dev/null 2>&1
    
    local optimized_end_time
    optimized_end_time=$(date +%s)
    local optimized_duration=$((optimized_end_time - optimized_start_time))
    
    # Calculate improvement
    local improvement=$((original_duration - optimized_duration))
    local improvement_percent
    if [[ $original_duration -gt 0 ]]; then
        improvement_percent=$(( (improvement * 100) / original_duration ))
    else
        improvement_percent=0
    fi
    
    # Create benchmark results
    cat > "$results_file" << EOF
{
  "benchmark_date": "$(date -Iseconds)",
  "original_startup_time": ${original_duration},
  "optimized_startup_time": ${optimized_duration},
  "improvement_seconds": ${improvement},
  "improvement_percent": ${improvement_percent},
  "optimization_level": "${OPTIMIZATION_LEVEL}",
  "optimizations_enabled": {
    "tmpfs_volumes": ${ENABLE_TMPFS},
    "parallel_build": ${ENABLE_PARALLEL_BUILD},
    "cache_optimization": ${ENABLE_CACHE_OPTIMIZATION}
  }
}
EOF
    
    # Display results
    echo
    print_success "Benchmark Results:"
    print_info "Original startup time: ${original_duration}s"
    print_info "Optimized startup time: ${optimized_duration}s"
    
    if [[ $improvement -gt 0 ]]; then
        print_success "Improvement: ${improvement}s (${improvement_percent}% faster)"
    elif [[ $improvement -lt 0 ]]; then
        print_warning "Regression: $((improvement * -1))s (slower)"
    else
        print_info "No significant change in startup time"
    fi
    
    print_info "Detailed results saved to: $results_file"
}

# Function to show optimization status
show_optimization_status() {
    print_status "Container Startup Optimization Status"
    echo
    
    # Check if optimized files exist
    if [[ -f "$COMPOSE_FILE" ]]; then
        print_success "Optimized compose file: $COMPOSE_FILE"
    else
        print_warning "Optimized compose file not found"
    fi
    
    if [[ -f "Dockerfile.optimized" ]]; then
        print_success "Optimized Dockerfile: Dockerfile.optimized"
    else
        print_warning "Optimized Dockerfile not found"
    fi
    
    # Check cache directories
    local cache_dirs=("./cache/models" "./cache/pip" "./data")
    local cache_status=true
    
    for dir in "${cache_dirs[@]}"; do
        if [[ -d "$dir" ]]; then
            local size
            size=$(du -sh "$dir" 2>/dev/null | cut -f1 || echo "0")
            print_info "Cache directory $dir: $size"
        else
            print_warning "Cache directory $dir: not found"
            cache_status=false
        fi
    done
    
    # Check running services
    if docker compose -f "$COMPOSE_FILE" ps >/dev/null 2>&1; then
        local running_services
        running_services=$(docker compose -f "$COMPOSE_FILE" ps --services --filter "status=running" | wc -l)
        print_info "Running optimized services: $running_services"
    fi
    
    # Overall status
    echo
    if [[ -f "$COMPOSE_FILE" ]] && [[ -f "Dockerfile.optimized" ]] && [[ "$cache_status" == "true" ]]; then
        print_success "✅ Container startup optimizations are ready"
    else
        print_warning "⚠️  Some optimizations are missing or incomplete"
    fi
}

# Function to clean up optimization artifacts
cleanup_optimizations() {
    print_status "Cleaning up optimization artifacts..."
    
    # Stop services
    docker compose -f "$COMPOSE_FILE" down -v >/dev/null 2>&1 || true
    
    # Remove optimization files
    local files_to_remove=(
        "$COMPOSE_FILE"
        "Dockerfile.optimized"
        "startup_benchmark_*.json"
    )
    
    for file in "${files_to_remove[@]}"; do
        if [[ -f "$file" ]]; then
            rm -f "$file"
            print_info "Removed: $file"
        fi
    done
    
    # Clean cache directories (optional)
    read -p "Remove cache directories? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf ./cache ./data
        print_info "Removed cache directories"
    fi
    
    print_success "Cleanup completed"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --level)
            OPTIMIZATION_LEVEL="$2"
            shift 2
            ;;
        --no-tmpfs)
            ENABLE_TMPFS=false
            shift
            ;;
        --no-parallel)
            ENABLE_PARALLEL_BUILD=false
            shift
            ;;
        --no-cache)
            ENABLE_CACHE_OPTIMIZATION=false
            shift
            ;;
        --compose-file)
            COMPOSE_FILE="$2"
            shift 2
            ;;
        --help)
            show_help
            exit 0
            ;;
        optimize|build|start|stop|clean|benchmark|status)
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
COMMAND="${COMMAND:-optimize}"

# Main execution
main() {
    print_status "🚀 Container Startup Optimization Tool"
    print_info "Optimization level: $OPTIMIZATION_LEVEL"
    print_info "Command: $COMMAND"
    echo
    
    case $COMMAND in
        optimize)
            check_system_requirements
            create_cache_directories
            optimize_docker_daemon
            build_optimized_images
            start_optimized_services
            print_success "🎉 Container startup optimization completed!"
            ;;
        build)
            check_system_requirements
            create_cache_directories
            optimize_docker_daemon
            build_optimized_images
            ;;
        start)
            start_optimized_services
            ;;
        stop)
            print_status "Stopping optimized services..."
            docker compose -f "$COMPOSE_FILE" down
            print_success "Services stopped"
            ;;
        benchmark)
            benchmark_startup_times
            ;;
        status)
            show_optimization_status
            ;;
        clean)
            cleanup_optimizations
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