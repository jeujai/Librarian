#!/bin/bash
#
# Fast Startup Script
#
# This script implements the fastest possible startup sequence
# using all cold start optimizations.
#

set -e

print_info() {
    echo -e "\033[0;36m[$(date '+%H:%M:%S')]\033[0m 💡 $1"
}

print_success() {
    echo -e "\033[0;32m[$(date '+%H:%M:%S')]\033[0m ✅ $1"
}

print_status() {
    echo -e "\033[0;34m[$(date '+%H:%M:%S')]\033[0m $1"
}

COMPOSE_FILE="docker-compose.cold-start-optimized.yml"

# Fast startup with optimized sequence
fast_startup() {
    local start_time=$(date +%s)
    
    print_status "🚀 Starting fast cold start sequence..."
    
    # Start essential services first (in parallel)
    print_info "Starting essential services..."
    docker compose -f "$COMPOSE_FILE" up -d redis postgres &
    
    # Start Milvus dependencies
    print_info "Starting Milvus dependencies..."
    docker compose -f "$COMPOSE_FILE" up -d etcd minio &
    
    # Wait for essential services
    wait
    
    # Start remaining services
    print_info "Starting remaining services..."
    docker compose -f "$COMPOSE_FILE" up -d neo4j milvus &
    
    # Start application (don't wait for all services to be fully ready)
    print_info "Starting application..."
    docker compose -f "$COMPOSE_FILE" up -d multimodal-librarian &
    
    wait
    
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    print_success "🎉 Fast startup completed in ${duration}s"
    print_info "Application should be available at: http://localhost:8000"
    print_info "Health check: http://localhost:8000/health/simple"
}

# Monitor startup progress
monitor_startup() {
    print_status "Monitoring startup progress..."
    
    local max_wait=60
    local wait_time=0
    
    while [[ $wait_time -lt $max_wait ]]; do
        if curl -f http://localhost:8000/health/simple >/dev/null 2>&1; then
            print_success "Application is ready! (${wait_time}s)"
            return 0
        fi
        
        sleep 2
        ((wait_time += 2))
        print_info "Waiting for application... (${wait_time}s)"
    done
    
    print_info "Application may still be starting up. Check logs with: make logs"
}

# Main function
main() {
    if [[ ! -f "$COMPOSE_FILE" ]]; then
        echo "Error: $COMPOSE_FILE not found. Run optimization first."
        exit 1
    fi
    
    fast_startup
    monitor_startup
}

main "$@"
