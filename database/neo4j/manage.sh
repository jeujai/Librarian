#!/bin/bash

# Neo4j Management Script for Local Development
# This script provides utilities for managing the local Neo4j instance

set -e

# Configuration
NEO4J_CONTAINER="local-development-conversion-neo4j-1"
NEO4J_USER="neo4j"
NEO4J_PASSWORD="ml_password"
NEO4J_URI="bolt://localhost:7687"
NEO4J_HTTP_URI="http://localhost:7474"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
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

# Check if Neo4j container is running
check_container() {
    if ! docker ps | grep -q "$NEO4J_CONTAINER"; then
        log_error "Neo4j container is not running. Please start it with 'docker-compose up neo4j'"
        exit 1
    fi
}

# Wait for Neo4j to be ready
wait_for_neo4j() {
    log_info "Waiting for Neo4j to be ready..."
    local max_attempts=30
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        if docker exec "$NEO4J_CONTAINER" cypher-shell -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" "RETURN 1" >/dev/null 2>&1; then
            log_success "Neo4j is ready!"
            return 0
        fi
        
        log_info "Attempt $attempt/$max_attempts - Neo4j not ready yet, waiting..."
        sleep 5
        ((attempt++))
    done
    
    log_error "Neo4j failed to become ready after $max_attempts attempts"
    return 1
}

# Verify plugins are loaded
verify_plugins() {
    log_info "Verifying Neo4j plugins..."
    
    # Check APOC
    if docker exec "$NEO4J_CONTAINER" cypher-shell -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" "CALL apoc.version() YIELD version RETURN version" >/dev/null 2>&1; then
        local apoc_version=$(docker exec "$NEO4J_CONTAINER" cypher-shell -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" "CALL apoc.version() YIELD version RETURN version" 2>/dev/null | tail -n +2 | head -n 1 | tr -d '"')
        log_success "APOC plugin loaded successfully (version: $apoc_version)"
    else
        log_error "APOC plugin not loaded or not working"
        return 1
    fi
    
    # Check GDS
    if docker exec "$NEO4J_CONTAINER" cypher-shell -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" "CALL gds.version() YIELD gdsVersion RETURN gdsVersion" >/dev/null 2>&1; then
        local gds_version=$(docker exec "$NEO4J_CONTAINER" cypher-shell -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" "CALL gds.version() YIELD gdsVersion RETURN gdsVersion" 2>/dev/null | tail -n +2 | head -n 1 | tr -d '"')
        log_success "GDS plugin loaded successfully (version: $gds_version)"
    else
        log_error "GDS plugin not loaded or not working"
        return 1
    fi
    
    log_success "All plugins verified successfully!"
}

# Run initialization script
run_init_script() {
    log_info "Running Neo4j initialization script..."
    
    if [ -f "database/neo4j/init/01_verify_plugins.cypher" ]; then
        docker exec -i "$NEO4J_CONTAINER" cypher-shell -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" < database/neo4j/init/01_verify_plugins.cypher
        log_success "Initialization script completed"
    else
        log_warning "Initialization script not found at database/neo4j/init/01_verify_plugins.cypher"
    fi
}

# Show Neo4j status
show_status() {
    log_info "Neo4j Status Information"
    echo "=========================="
    
    # Container status
    if docker ps | grep -q "$NEO4J_CONTAINER"; then
        log_success "Container: Running"
    else
        log_error "Container: Not running"
        return 1
    fi
    
    # Service health
    if docker exec "$NEO4J_CONTAINER" cypher-shell -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" "RETURN 1" >/dev/null 2>&1; then
        log_success "Service: Healthy"
    else
        log_error "Service: Unhealthy"
    fi
    
    # Plugin status
    verify_plugins
    
    # Connection info
    echo ""
    log_info "Connection Information:"
    echo "  HTTP UI: $NEO4J_HTTP_URI"
    echo "  Bolt URI: $NEO4J_URI"
    echo "  Username: $NEO4J_USER"
    echo "  Password: $NEO4J_PASSWORD"
}

# Backup database
backup_database() {
    local backup_name="neo4j_backup_$(date +%Y%m%d_%H%M%S)"
    local backup_dir="./backups/neo4j"
    
    log_info "Creating backup: $backup_name"
    
    # Create backup directory if it doesn't exist
    mkdir -p "$backup_dir"
    
    # Use neo4j-admin dump command
    docker exec "$NEO4J_CONTAINER" neo4j-admin database dump --to-path=/backups neo4j
    
    # Copy from container to host
    docker cp "$NEO4J_CONTAINER:/backups/neo4j.dump" "$backup_dir/$backup_name.dump"
    
    log_success "Backup created: $backup_dir/$backup_name.dump"
}

# Restore database
restore_database() {
    local backup_file="$1"
    
    if [ -z "$backup_file" ]; then
        log_error "Please specify backup file path"
        echo "Usage: $0 restore <backup_file>"
        exit 1
    fi
    
    if [ ! -f "$backup_file" ]; then
        log_error "Backup file not found: $backup_file"
        exit 1
    fi
    
    log_warning "This will replace all data in the Neo4j database!"
    read -p "Are you sure you want to continue? (y/N): " -n 1 -r
    echo
    
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "Restore cancelled"
        exit 0
    fi
    
    log_info "Restoring from backup: $backup_file"
    
    # Copy backup to container
    docker cp "$backup_file" "$NEO4J_CONTAINER:/backups/restore.dump"
    
    # Stop database, restore, and start
    docker exec "$NEO4J_CONTAINER" neo4j-admin database load --from-path=/backups --overwrite-destination=true neo4j
    
    log_success "Database restored successfully"
}

# Execute cypher query
execute_query() {
    local query="$1"
    
    if [ -z "$query" ]; then
        log_error "Please specify a Cypher query"
        echo "Usage: $0 query \"MATCH (n) RETURN count(n)\""
        exit 1
    fi
    
    log_info "Executing query: $query"
    docker exec "$NEO4J_CONTAINER" cypher-shell -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" "$query"
}

# Show help
show_help() {
    echo "Neo4j Management Script"
    echo "======================="
    echo ""
    echo "Usage: $0 <command> [arguments]"
    echo ""
    echo "Commands:"
    echo "  status              Show Neo4j status and connection info"
    echo "  wait                Wait for Neo4j to be ready"
    echo "  verify              Verify plugins are loaded correctly"
    echo "  init                Run initialization script"
    echo "  backup              Create a database backup"
    echo "  restore <file>      Restore database from backup file"
    echo "  query \"<cypher>\"    Execute a Cypher query"
    echo "  help                Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 status"
    echo "  $0 query \"MATCH (n) RETURN count(n)\""
    echo "  $0 backup"
    echo "  $0 restore ./backups/neo4j/backup_20240101_120000.dump"
}

# Main script logic
case "${1:-help}" in
    "status")
        check_container
        show_status
        ;;
    "wait")
        check_container
        wait_for_neo4j
        ;;
    "verify")
        check_container
        wait_for_neo4j
        verify_plugins
        ;;
    "init")
        check_container
        wait_for_neo4j
        run_init_script
        ;;
    "backup")
        check_container
        backup_database
        ;;
    "restore")
        check_container
        restore_database "$2"
        ;;
    "query")
        check_container
        execute_query "$2"
        ;;
    "help"|*)
        show_help
        ;;
esac