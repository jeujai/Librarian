#!/bin/bash
#
# Container Pre-warming Script
#
# This script pre-warms containers by building and caching images,
# pre-loading dependencies, and preparing the environment for
# instant startup.
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

# Pre-warm Docker images
prewarm_images() {
    print_status "Pre-warming Docker images..."
    
    # Build with cache
    export DOCKER_BUILDKIT=1
    export COMPOSE_DOCKER_CLI_BUILD=1
    
    # Build dependency cache stage
    docker build --target dependency-cache \
        --cache-from multimodal-librarian:dependency-cache \
        -t multimodal-librarian:dependency-cache \
        -f Dockerfile.cold-start-optimized .
    
    # Build runtime base stage
    docker build --target runtime-base \
        --cache-from multimodal-librarian:dependency-cache \
        --cache-from multimodal-librarian:runtime-base \
        -t multimodal-librarian:runtime-base \
        -f Dockerfile.cold-start-optimized .
    
    # Build development stage
    docker build --target development \
        --cache-from multimodal-librarian:dependency-cache \
        --cache-from multimodal-librarian:runtime-base \
        --cache-from multimodal-librarian:development \
        -t multimodal-librarian:development \
        -f Dockerfile.cold-start-optimized .
    
    print_success "Docker images pre-warmed successfully"
}

# Pre-create data directories
prewarm_directories() {
    print_status "Pre-creating data directories..."
    
    local dirs=(
        "./data/postgres"
        "./data/neo4j"
        "./data/neo4j-logs"
        "./data/milvus"
        "./data/etcd"
        "./data/minio"
        "./data/redis"
        "./cache/models"
        "./cache/pip"
        "./uploads"
        "./media"
        "./exports"
        "./logs"
    )
    
    for dir in "${dirs[@]}"; do
        if [[ ! -d "$dir" ]]; then
            mkdir -p "$dir"
            print_info "Created directory: $dir"
        fi
    done
    
    print_success "Data directories pre-created"
}

# Pre-pull base images
prewarm_base_images() {
    print_status "Pre-pulling base images..."
    
    local images=(
        "python:3.11-slim"
        "postgres:15-alpine"
        "neo4j:5.15-community"
        "milvusdb/milvus:v2.3.4"
        "quay.io/coreos/etcd:v3.5.5"
        "minio/minio:RELEASE.2023-03-20T20-16-18Z"
        "redis:7-alpine"
    )
    
    for image in "${images[@]}"; do
        print_info "Pulling $image..."
        docker pull "$image" &
    done
    
    wait
    print_success "Base images pre-pulled"
}

# Main pre-warming function
main() {
    print_status "🔥 Starting container pre-warming process..."
    
    prewarm_base_images
    prewarm_directories
    prewarm_images
    
    print_success "🎉 Container pre-warming completed!"
    print_info "Containers are now ready for instant cold start"
}

main "$@"
