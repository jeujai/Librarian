#!/bin/bash

# Neo4j Restore Script for Multimodal Librarian Local Development
# This script restores Neo4j graph database from backups

set -e

# Configuration
NEO4J_HOST="${NEO4J_HOST:-localhost}"
NEO4J_PORT="${NEO4J_PORT:-7687}"
NEO4J_HTTP_PORT="${NEO4J_HTTP_PORT:-7474}"
NEO4J_USER="${NEO4J_USER:-neo4j}"
NEO4J_PASSWORD="${NEO4J_PASSWORD:-ml_password}"
BACKUP_DIR="${BACKUP_DIR:-./backups/neo4j}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Check if Neo4j is accessible
check_connectivity() {
    log "Checking Neo4j connectivity..."
    
    # Check Bolt connection
    if ! cypher-shell -a "bolt://$NEO4J_HOST:$NEO4J_PORT" -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" "RETURN 1" >/dev/null 2>&1; then
        error "Cannot connect to Neo4j via Bolt protocol"
        return 1
    fi
    
    success "Neo4j is accessible"
    return 0
}

# Function to list available backups
list_backups() {
    log "Available Neo4j backups in $BACKUP_DIR:"
    echo ""
    
    if [[ ! -d "$BACKUP_DIR" ]]; then
        warning "Backup directory does not exist: $BACKUP_DIR"
        return 1
    fi
    
    local backups_found=false
    
    echo "Cypher Backups:"
    if find "$BACKUP_DIR" -name "*.cypher" -type f | head -1 >/dev/null 2>&1; then
        find "$BACKUP_DIR" -name "*.cypher" -type f -exec ls -lh {} \; | sort -k9
        backups_found=true
    else
        echo "  No Cypher backups found"
    fi
    
    echo ""
    echo "JSON Backups:"
    if find "$BACKUP_DIR" -name "*.json" -type f | head -1 >/dev/null 2>&1; then
        find "$BACKUP_DIR" -name "*.json" -type f -exec ls -lh {} \; | sort -k9
        backups_found=true
    else
        echo "  No JSON backups found"
    fi
    
    echo ""
    echo "GraphML Backups:"
    if find "$BACKUP_DIR" -name "*.graphml" -type f | head -1 >/dev/null 2>&1; then
        find "$BACKUP_DIR" -name "*.graphml" -type f -exec ls -lh {} \; | sort -k9
        backups_found=true
    else
        echo "  No GraphML backups found"
    fi
    
    echo ""
    echo "Admin Backups:"
    if find "$BACKUP_DIR" -name "admin_backup_*" -type d | head -1 >/dev/null 2>&1; then
        find "$BACKUP_DIR" -name "admin_backup_*" -type d -exec ls -ld {} \; | sort -k9
        backups_found=true
    else
        echo "  No admin backups found"
    fi
    
    if [[ "$backups_found" == false ]]; then
        warning "No backups found in $BACKUP_DIR"
        return 1
    fi
}

# Function to get latest backup
get_latest_backup() {
    local backup_type="$1"
    local pattern
    
    case "$backup_type" in
        "cypher")
            pattern="cypher_export_*.cypher"
            ;;
        "json")
            pattern="json_export_*.json"
            ;;
        "graphml")
            pattern="graphml_export_*.graphml"
            ;;
        "schema")
            pattern="schema_*.cypher"
            ;;
        "stats")
            pattern="statistics_*.json"
            ;;
        *)
            # Default to cypher export
            pattern="cypher_export_*.cypher"
            ;;
    esac
    
    find "$BACKUP_DIR" -name "$pattern" -type f -printf '%T@ %p\n' 2>/dev/null | \
    sort -n | tail -1 | cut -d' ' -f2-
}

# Function to clear database
clear_database() {
    log "Clearing existing Neo4j database..."
    
    # Ask for confirmation
    echo -n "This will delete all existing data in Neo4j. Continue? (y/N): "
    read -r confirmation
    if [[ "$confirmation" != "y" && "$confirmation" != "Y" ]]; then
        log "Database clear cancelled by user"
        return 1
    fi
    
    # Delete all nodes and relationships
    local clear_query="MATCH (n) DETACH DELETE n"
    
    if cypher-shell -a "bolt://$NEO4J_HOST:$NEO4J_PORT" -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" "$clear_query" >/dev/null 2>&1; then
        success "Database cleared successfully"
    else
        error "Failed to clear database"
        return 1
    fi
}

# Function to restore from Cypher backup
restore_cypher_backup() {
    local backup_file="$1"
    
    if [[ ! -f "$backup_file" ]]; then
        error "Backup file not found: $backup_file"
        return 1
    fi
    
    log "Restoring from Cypher backup: $backup_file"
    
    # Clear database first
    if ! clear_database; then
        return 1
    fi
    
    # Execute Cypher file
    if cypher-shell -a "bolt://$NEO4J_HOST:$NEO4J_PORT" -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" -f "$backup_file"; then
        success "Database restored successfully from Cypher backup"
    else
        error "Failed to restore from Cypher backup"
        return 1
    fi
}

# Function to restore from JSON backup using APOC
restore_json_backup() {
    local backup_file="$1"
    
    if [[ ! -f "$backup_file" ]]; then
        error "Backup file not found: $backup_file"
        return 1
    fi
    
    log "Restoring from JSON backup: $backup_file"
    
    # Clear database first
    if ! clear_database; then
        return 1
    fi
    
    # Copy file to Neo4j import directory (if using Docker)
    local import_file="/var/lib/neo4j/import/$(basename "$backup_file")"
    
    if command -v docker-compose >/dev/null 2>&1; then
        # Copy file to container
        if docker-compose -f docker-compose.local.yml cp "$backup_file" "neo4j:$import_file" >/dev/null 2>&1; then
            log "Backup file copied to Neo4j container"
        else
            error "Failed to copy backup file to Neo4j container"
            return 1
        fi
    else
        # Assume file is accessible directly
        import_file="$backup_file"
    fi
    
    # Use APOC to import JSON
    local import_query="
    CALL apoc.import.json('$(basename "$backup_file")', {
        readLabels: true,
        readTypes: true
    })
    YIELD file, source, format, nodes, relationships, properties, time, rows, batchSize, batches, done, data
    RETURN file, source, format, nodes, relationships, properties, time, rows, batchSize, batches, done
    "
    
    if cypher-shell -a "bolt://$NEO4J_HOST:$NEO4J_PORT" -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" "$import_query" >/dev/null 2>&1; then
        success "Database restored successfully from JSON backup"
    else
        error "Failed to restore from JSON backup"
        return 1
    fi
}

# Function to restore from GraphML backup using APOC
restore_graphml_backup() {
    local backup_file="$1"
    
    if [[ ! -f "$backup_file" ]]; then
        error "Backup file not found: $backup_file"
        return 1
    fi
    
    log "Restoring from GraphML backup: $backup_file"
    
    # Clear database first
    if ! clear_database; then
        return 1
    fi
    
    # Copy file to Neo4j import directory (if using Docker)
    local import_file="/var/lib/neo4j/import/$(basename "$backup_file")"
    
    if command -v docker-compose >/dev/null 2>&1; then
        # Copy file to container
        if docker-compose -f docker-compose.local.yml cp "$backup_file" "neo4j:$import_file" >/dev/null 2>&1; then
            log "Backup file copied to Neo4j container"
        else
            error "Failed to copy backup file to Neo4j container"
            return 1
        fi
    else
        # Assume file is accessible directly
        import_file="$backup_file"
    fi
    
    # Use APOC to import GraphML
    local import_query="
    CALL apoc.import.graphml('$(basename "$backup_file")', {
        readLabels: true,
        storeNodeIds: false
    })
    YIELD file, source, format, nodes, relationships, properties, time, rows, batchSize, batches, done, data
    RETURN file, source, format, nodes, relationships, properties, time, rows, batchSize, batches, done
    "
    
    if cypher-shell -a "bolt://$NEO4J_HOST:$NEO4J_PORT" -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" "$import_query" >/dev/null 2>&1; then
        success "Database restored successfully from GraphML backup"
    else
        error "Failed to restore from GraphML backup"
        return 1
    fi
}

# Function to restore schema only
restore_schema_only() {
    local backup_file="$1"
    
    if [[ ! -f "$backup_file" ]]; then
        error "Schema backup file not found: $backup_file"
        return 1
    fi
    
    log "Restoring schema from: $backup_file"
    
    # Execute schema file (constraints and indexes)
    if cypher-shell -a "bolt://$NEO4J_HOST:$NEO4J_PORT" -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" -f "$backup_file"; then
        success "Schema restored successfully"
    else
        error "Failed to restore schema"
        return 1
    fi
}

# Function to restore from admin backup
restore_admin_backup() {
    local backup_dir="$1"
    
    if [[ ! -d "$backup_dir" ]]; then
        error "Admin backup directory not found: $backup_dir"
        return 1
    fi
    
    log "Restoring from admin backup: $backup_dir"
    
    # This requires stopping Neo4j, restoring files, and restarting
    warning "Admin backup restore requires Neo4j service restart"
    
    if command -v docker-compose >/dev/null 2>&1; then
        # Stop Neo4j service
        log "Stopping Neo4j service..."
        if docker-compose -f docker-compose.local.yml stop neo4j; then
            success "Neo4j service stopped"
        else
            error "Failed to stop Neo4j service"
            return 1
        fi
        
        # Restore backup using neo4j-admin
        log "Restoring backup using neo4j-admin..."
        if docker-compose -f docker-compose.local.yml run --rm neo4j neo4j-admin database restore neo4j --from-path="$(basename "$backup_dir")" --overwrite-destination=true >/dev/null 2>&1; then
            success "Admin backup restored"
        else
            error "Failed to restore admin backup"
            return 1
        fi
        
        # Start Neo4j service
        log "Starting Neo4j service..."
        if docker-compose -f docker-compose.local.yml start neo4j; then
            success "Neo4j service started"
            
            # Wait for service to be ready
            log "Waiting for Neo4j to be ready..."
            local retry_count=0
            while ! cypher-shell -a "bolt://$NEO4J_HOST:$NEO4J_PORT" -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" "RETURN 1" >/dev/null 2>&1; do
                sleep 2
                retry_count=$((retry_count + 1))
                if [[ $retry_count -gt 30 ]]; then
                    error "Neo4j did not start within expected time"
                    return 1
                fi
            done
            success "Neo4j is ready"
        else
            error "Failed to start Neo4j service"
            return 1
        fi
    else
        error "Docker not available, cannot perform admin backup restore"
        return 1
    fi
}

# Function to verify restore
verify_restore() {
    log "Verifying Neo4j restore..."
    
    # Check connectivity
    if ! check_connectivity; then
        return 1
    fi
    
    # Get basic statistics
    local node_count=$(cypher-shell -a "bolt://$NEO4J_HOST:$NEO4J_PORT" -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" "MATCH (n) RETURN count(n)" --format plain 2>/dev/null | tail -1 | xargs || echo "0")
    local rel_count=$(cypher-shell -a "bolt://$NEO4J_HOST:$NEO4J_PORT" -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" "MATCH ()-[r]->() RETURN count(r)" --format plain 2>/dev/null | tail -1 | xargs || echo "0")
    
    success "Restore verification completed"
    echo "  Nodes: $node_count"
    echo "  Relationships: $rel_count"
    
    # Check for labels
    local labels=$(cypher-shell -a "bolt://$NEO4J_HOST:$NEO4J_PORT" -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" "CALL db.labels()" --format plain 2>/dev/null | wc -l || echo "0")
    echo "  Labels: $labels"
    
    # Check for relationship types
    local rel_types=$(cypher-shell -a "bolt://$NEO4J_HOST:$NEO4J_PORT" -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" "CALL db.relationshipTypes()" --format plain 2>/dev/null | wc -l || echo "0")
    echo "  Relationship types: $rel_types"
}

# Main execution
main() {
    case "${1:-list}" in
        "list")
            list_backups
            ;;
        "latest")
            check_connectivity
            local latest_backup
            latest_backup=$(get_latest_backup "cypher")
            if [[ -n "$latest_backup" ]]; then
                log "Latest backup found: $latest_backup"
                restore_cypher_backup "$latest_backup"
                verify_restore
            else
                error "No Cypher backups found"
                exit 1
            fi
            ;;
        "latest-json")
            check_connectivity
            local latest_json
            latest_json=$(get_latest_backup "json")
            if [[ -n "$latest_json" ]]; then
                log "Latest JSON backup found: $latest_json"
                restore_json_backup "$latest_json"
                verify_restore
            else
                error "No JSON backups found"
                exit 1
            fi
            ;;
        "schema")
            check_connectivity
            local latest_schema
            latest_schema=$(get_latest_backup "schema")
            if [[ -n "$latest_schema" ]]; then
                log "Latest schema backup found: $latest_schema"
                restore_schema_only "$latest_schema"
                verify_restore
            else
                error "No schema backups found"
                exit 1
            fi
            ;;
        "file")
            if [[ -z "$2" ]]; then
                error "Please specify backup file path"
                echo "Usage: $0 file <backup_file_path>"
                exit 1
            fi
            check_connectivity
            
            case "$2" in
                *.cypher)
                    restore_cypher_backup "$2"
                    ;;
                *.json)
                    restore_json_backup "$2"
                    ;;
                *.graphml)
                    restore_graphml_backup "$2"
                    ;;
                *)
                    error "Unsupported backup file format: $2"
                    echo "Supported formats: .cypher, .json, .graphml"
                    exit 1
                    ;;
            esac
            verify_restore
            ;;
        "admin")
            if [[ -z "$2" ]]; then
                # Find latest admin backup
                local latest_admin
                latest_admin=$(find "$BACKUP_DIR" -name "admin_backup_*" -type d -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -1 | cut -d' ' -f2-)
                if [[ -n "$latest_admin" ]]; then
                    log "Latest admin backup found: $latest_admin"
                    restore_admin_backup "$latest_admin"
                else
                    error "No admin backups found"
                    exit 1
                fi
            else
                restore_admin_backup "$2"
            fi
            verify_restore
            ;;
        "verify")
            verify_restore
            ;;
        "help"|"--help"|"-h")
            echo "Usage: $0 [list|latest|latest-json|schema|file <path>|admin [path]|verify|help]"
            echo ""
            echo "Options:"
            echo "  list           - List available backups (default)"
            echo "  latest         - Restore from latest Cypher backup"
            echo "  latest-json    - Restore from latest JSON backup"
            echo "  schema         - Restore schema from latest schema backup"
            echo "  file <path>    - Restore from specific backup file"
            echo "  admin [path]   - Restore from admin backup (latest if no path)"
            echo "  verify         - Verify current database state"
            echo "  help           - Show this help message"
            echo ""
            echo "Environment variables:"
            echo "  NEO4J_HOST     - Neo4j host (default: localhost)"
            echo "  NEO4J_PORT     - Neo4j Bolt port (default: 7687)"
            echo "  NEO4J_USER     - Neo4j username (default: neo4j)"
            echo "  NEO4J_PASSWORD - Neo4j password (default: ml_password)"
            echo "  BACKUP_DIR     - Backup directory (default: ./backups/neo4j)"
            echo ""
            echo "Examples:"
            echo "  $0 latest                           # Restore from latest Cypher backup"
            echo "  $0 file /path/to/backup.cypher      # Restore from specific file"
            echo "  $0 schema                           # Restore schema only"
            echo "  $0 admin                            # Restore from latest admin backup"
            exit 0
            ;;
        *)
            error "Unknown action: $1"
            echo "Use '$0 help' for usage information"
            exit 1
            ;;
    esac
    
    success "Neo4j restore operation completed"
}

# Run main function with all arguments
main "$@"