#!/bin/bash

# =============================================================================
# Milvus Management Script for Local Development
# =============================================================================
# This script provides common Milvus management operations

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
COMPOSE_FILE="docker-compose.local.yml"
MILVUS_HOST="localhost"
MILVUS_PORT="19530"
ATTU_PORT="3000"

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

# Function to check if Milvus is running
check_milvus_running() {
    if docker-compose -f "$COMPOSE_FILE" ps milvus | grep -q "Up"; then
        return 0
    else
        return 1
    fi
}

# Function to wait for Milvus to be ready
wait_for_milvus() {
    print_info "Waiting for Milvus to be ready..."
    local max_attempts=30
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        if curl -s -f "http://${MILVUS_HOST}:9091/healthz" >/dev/null 2>&1; then
            print_success "Milvus is ready!"
            return 0
        fi
        
        echo -n "."
        sleep 2
        attempt=$((attempt + 1))
    done
    
    print_error "Milvus failed to become ready after $((max_attempts * 2)) seconds"
    return 1
}

# Function to start Milvus and dependencies
start_milvus() {
    print_info "Starting Milvus and dependencies..."
    
    # Start etcd and minio first
    docker-compose -f "$COMPOSE_FILE" up -d etcd minio
    
    # Wait a bit for dependencies
    sleep 5
    
    # Start Milvus
    docker-compose -f "$COMPOSE_FILE" up -d milvus
    
    # Wait for Milvus to be ready
    if wait_for_milvus; then
        print_success "Milvus started successfully"
        print_info "Milvus gRPC: http://${MILVUS_HOST}:${MILVUS_PORT}"
        print_info "Milvus Web UI: http://${MILVUS_HOST}:9091"
    else
        print_error "Failed to start Milvus"
        return 1
    fi
}

# Function to start Attu admin interface
start_attu() {
    print_info "Starting Attu admin interface..."
    
    if ! check_milvus_running; then
        print_warning "Milvus is not running. Starting Milvus first..."
        start_milvus
    fi
    
    docker-compose -f "$COMPOSE_FILE" --profile admin-tools up -d attu
    
    # Wait for Attu to be ready
    sleep 5
    
    if curl -s -f "http://localhost:${ATTU_PORT}" >/dev/null 2>&1; then
        print_success "Attu started successfully"
        print_info "Attu Admin UI: http://localhost:${ATTU_PORT}"
        print_info "Connect to Milvus using: Host=milvus, Port=19530"
    else
        print_error "Failed to start Attu"
        return 1
    fi
}

# Function to stop Milvus
stop_milvus() {
    print_info "Stopping Milvus and dependencies..."
    docker-compose -f "$COMPOSE_FILE" stop milvus etcd minio attu
    print_success "Milvus stopped"
}

# Function to restart Milvus
restart_milvus() {
    print_info "Restarting Milvus..."
    stop_milvus
    sleep 2
    start_milvus
}

# Function to show Milvus status
show_status() {
    print_info "Milvus Service Status:"
    docker-compose -f "$COMPOSE_FILE" ps milvus etcd minio attu
    
    echo ""
    print_info "Health Checks:"
    
    # Check Milvus health
    if curl -s -f "http://${MILVUS_HOST}:9091/healthz" >/dev/null 2>&1; then
        print_success "Milvus: Healthy"
    else
        print_error "Milvus: Unhealthy or not accessible"
    fi
    
    # Check etcd health
    if docker-compose -f "$COMPOSE_FILE" exec -T etcd etcdctl endpoint health >/dev/null 2>&1; then
        print_success "etcd: Healthy"
    else
        print_error "etcd: Unhealthy"
    fi
    
    # Check MinIO health
    if curl -s -f "http://localhost:9000/minio/health/live" >/dev/null 2>&1; then
        print_success "MinIO: Healthy"
    else
        print_error "MinIO: Unhealthy or not accessible"
    fi
    
    # Check Attu
    if curl -s -f "http://localhost:${ATTU_PORT}" >/dev/null 2>&1; then
        print_success "Attu: Accessible"
    else
        print_warning "Attu: Not accessible (may not be started)"
    fi
}

# Function to show logs
show_logs() {
    local service="${1:-milvus}"
    print_info "Showing logs for $service..."
    docker-compose -f "$COMPOSE_FILE" logs -f "$service"
}

# Function to validate setup
validate_setup() {
    print_info "Validating Milvus setup..."
    
    if ! check_milvus_running; then
        print_error "Milvus is not running. Start it first with: $0 start"
        return 1
    fi
    
    # Run validation script
    if [ -f "database/milvus/validate_setup.py" ]; then
        python database/milvus/validate_setup.py --host "$MILVUS_HOST" --port "$MILVUS_PORT"
    else
        print_warning "Validation script not found. Performing basic checks..."
        
        # Basic connectivity test
        if curl -s -f "http://${MILVUS_HOST}:9091/healthz" >/dev/null 2>&1; then
            print_success "Basic connectivity test passed"
        else
            print_error "Basic connectivity test failed"
            return 1
        fi
    fi
}

# Function to backup data
backup_data() {
    local backup_dir="./backups/milvus/$(date +%Y%m%d_%H%M%S)"
    print_info "Creating backup in $backup_dir..."
    
    mkdir -p "$backup_dir"
    
    # Backup MinIO data (where Milvus stores vectors)
    docker-compose -f "$COMPOSE_FILE" exec -T minio mc mirror /data "$backup_dir/minio" >/dev/null 2>&1 || {
        print_warning "MinIO backup failed, trying alternative method..."
        docker cp "$(docker-compose -f "$COMPOSE_FILE" ps -q minio):/data" "$backup_dir/minio"
    }
    
    # Backup etcd data (metadata)
    docker cp "$(docker-compose -f "$COMPOSE_FILE" ps -q etcd):/etcd" "$backup_dir/etcd"
    
    print_success "Backup created in $backup_dir"
}

# Function to restore data
restore_data() {
    local backup_dir="$1"
    
    if [ -z "$backup_dir" ] || [ ! -d "$backup_dir" ]; then
        print_error "Please specify a valid backup directory"
        print_info "Usage: $0 restore /path/to/backup"
        return 1
    fi
    
    print_warning "This will stop Milvus and restore data from $backup_dir"
    read -p "Are you sure? (y/N): " confirm
    
    if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
        print_info "Restore cancelled"
        return 0
    fi
    
    print_info "Stopping Milvus..."
    stop_milvus
    
    print_info "Restoring data..."
    
    # Restore MinIO data
    if [ -d "$backup_dir/minio" ]; then
        docker cp "$backup_dir/minio/." "$(docker-compose -f "$COMPOSE_FILE" ps -q minio):/data/"
    fi
    
    # Restore etcd data
    if [ -d "$backup_dir/etcd" ]; then
        docker cp "$backup_dir/etcd/." "$(docker-compose -f "$COMPOSE_FILE" ps -q etcd):/etcd/"
    fi
    
    print_info "Starting Milvus..."
    start_milvus
    
    print_success "Data restored successfully"
}

# Function to reset data
reset_data() {
    print_warning "This will delete ALL Milvus data and cannot be undone!"
    read -p "Are you sure? (y/N): " confirm
    
    if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
        print_info "Reset cancelled"
        return 0
    fi
    
    print_info "Stopping Milvus..."
    docker-compose -f "$COMPOSE_FILE" down milvus etcd minio
    
    print_info "Removing data volumes..."
    docker volume rm -f multimodal-librarian-local_milvus_data || true
    docker volume rm -f multimodal-librarian-local_etcd_data || true
    docker volume rm -f multimodal-librarian-local_minio_data || true
    
    # Also remove local data directories
    rm -rf data/milvus data/etcd data/minio
    
    print_success "All Milvus data has been reset"
    print_info "Run '$0 start' to start fresh"
}

# Function to show help
show_help() {
    echo "Milvus Management Script"
    echo ""
    echo "Usage: $0 [COMMAND] [OPTIONS]"
    echo ""
    echo "Commands:"
    echo "  start           Start Milvus and dependencies"
    echo "  stop            Stop Milvus and dependencies"
    echo "  restart         Restart Milvus"
    echo "  status          Show service status and health"
    echo "  logs [SERVICE]  Show logs (default: milvus)"
    echo "  attu            Start Attu admin interface"
    echo "  validate        Validate Milvus setup"
    echo "  backup          Create data backup"
    echo "  restore DIR     Restore data from backup directory"
    echo "  reset           Reset all data (destructive!)"
    echo "  help            Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 start                    # Start Milvus"
    echo "  $0 logs milvus             # Show Milvus logs"
    echo "  $0 backup                  # Create backup"
    echo "  $0 restore ./backups/...   # Restore from backup"
    echo ""
    echo "Access Points:"
    echo "  Milvus gRPC:    http://localhost:19530"
    echo "  Milvus Web UI:  http://localhost:9091"
    echo "  Attu Admin:     http://localhost:3000"
    echo "  MinIO Console:  http://localhost:9001"
}

# Main execution
main() {
    case "${1:-help}" in
        start)
            start_milvus
            ;;
        stop)
            stop_milvus
            ;;
        restart)
            restart_milvus
            ;;
        status)
            show_status
            ;;
        logs)
            show_logs "$2"
            ;;
        attu)
            start_attu
            ;;
        validate)
            validate_setup
            ;;
        backup)
            backup_data
            ;;
        restore)
            restore_data "$2"
            ;;
        reset)
            reset_data
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            print_error "Unknown command: $1"
            echo ""
            show_help
            exit 1
            ;;
    esac
}

# Run main function with all arguments
main "$@"