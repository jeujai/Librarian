#!/bin/bash

# Neo4j Backup Script for Multimodal Librarian Local Development
# This script creates backups of the Neo4j graph database

set -e

# Configuration
NEO4J_HOST="${NEO4J_HOST:-localhost}"
NEO4J_PORT="${NEO4J_PORT:-7687}"
NEO4J_HTTP_PORT="${NEO4J_HTTP_PORT:-7474}"
NEO4J_USER="${NEO4J_USER:-neo4j}"
NEO4J_PASSWORD="${NEO4J_PASSWORD:-ml_password}"
BACKUP_DIR="${BACKUP_DIR:-./backups/neo4j}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

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

# Create backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR"

# Check if Neo4j is accessible
check_connectivity() {
    log "Checking Neo4j connectivity..."
    
    # Check Bolt connection
    if ! cypher-shell -a "bolt://$NEO4J_HOST:$NEO4J_PORT" -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" "RETURN 1" >/dev/null 2>&1; then
        error "Cannot connect to Neo4j via Bolt protocol"
        return 1
    fi
    
    # Check HTTP connection
    if ! curl -s -f "http://$NEO4J_HOST:$NEO4J_HTTP_PORT" >/dev/null 2>&1; then
        warning "Neo4j HTTP interface not accessible (this is okay for backups)"
    fi
    
    success "Neo4j is accessible"
    return 0
}

# Function to create Cypher export backup
create_cypher_backup() {
    local backup_file="$BACKUP_DIR/cypher_export_${TIMESTAMP}.cypher"
    log "Creating Cypher export backup: $backup_file"
    
    # Use APOC export procedures
    local cypher_query="
    CALL apoc.export.cypher.all('$backup_file', {
        format: 'cypher-shell',
        useOptimizations: {type: 'UNWIND_BATCH', unwindBatchSize: 20},
        awaitForIndexes: 300
    })
    YIELD file, source, format, nodes, relationships, properties, time, rows, batchSize, batches, done, data
    RETURN file, source, format, nodes, relationships, properties, time, rows, batchSize, batches, done
    "
    
    if cypher-shell -a "bolt://$NEO4J_HOST:$NEO4J_PORT" -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" "$cypher_query" >/dev/null 2>&1; then
        success "Cypher export backup created successfully"
        echo "Cypher backup: $backup_file"
    else
        error "Failed to create Cypher export backup"
        return 1
    fi
}

# Function to create JSON export backup
create_json_backup() {
    local backup_file="$BACKUP_DIR/json_export_${TIMESTAMP}.json"
    log "Creating JSON export backup: $backup_file"
    
    # Use APOC export procedures for JSON
    local cypher_query="
    CALL apoc.export.json.all('$backup_file', {
        useTypes: true,
        writeNodeProperties: true,
        writeRelationshipProperties: true
    })
    YIELD file, source, format, nodes, relationships, properties, time, rows, batchSize, batches, done, data
    RETURN file, source, format, nodes, relationships, properties, time, rows, batchSize, batches, done
    "
    
    if cypher-shell -a "bolt://$NEO4J_HOST:$NEO4J_PORT" -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" "$cypher_query" >/dev/null 2>&1; then
        success "JSON export backup created successfully"
        echo "JSON backup: $backup_file"
    else
        error "Failed to create JSON export backup"
        return 1
    fi
}

# Function to create GraphML export backup
create_graphml_backup() {
    local backup_file="$BACKUP_DIR/graphml_export_${TIMESTAMP}.graphml"
    log "Creating GraphML export backup: $backup_file"
    
    # Use APOC export procedures for GraphML
    local cypher_query="
    CALL apoc.export.graphml.all('$backup_file', {
        useTypes: true,
        caption: ['name', 'title', 'label']
    })
    YIELD file, source, format, nodes, relationships, properties, time, rows, batchSize, batches, done, data
    RETURN file, source, format, nodes, relationships, properties, time, rows, batchSize, batches, done
    "
    
    if cypher-shell -a "bolt://$NEO4J_HOST:$NEO4J_PORT" -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" "$cypher_query" >/dev/null 2>&1; then
        success "GraphML export backup created successfully"
        echo "GraphML backup: $backup_file"
    else
        error "Failed to create GraphML export backup"
        return 1
    fi
}

# Function to create schema-only backup
create_schema_backup() {
    local backup_file="$BACKUP_DIR/schema_${TIMESTAMP}.cypher"
    log "Creating schema backup: $backup_file"
    
    # Export schema information
    local cypher_query="
    // Export constraints
    CALL db.constraints() YIELD description
    WITH 'CREATE ' + description + ';' AS constraint_statement
    
    UNION ALL
    
    // Export indexes
    CALL db.indexes() YIELD name, labelsOrTypes, properties, type
    WHERE type <> 'LOOKUP'
    WITH 'CREATE INDEX ' + name + ' FOR (n:' + labelsOrTypes[0] + ') ON (' + 
         reduce(s = '', prop IN properties | s + 'n.' + prop + ', ') + ');' AS index_statement
    
    RETURN constraint_statement AS statement
    "
    
    if cypher-shell -a "bolt://$NEO4J_HOST:$NEO4J_PORT" -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" "$cypher_query" > "$backup_file" 2>/dev/null; then
        success "Schema backup created successfully"
        echo "Schema backup: $backup_file"
    else
        error "Failed to create schema backup"
        return 1
    fi
}

# Function to create database statistics backup
create_stats_backup() {
    local backup_file="$BACKUP_DIR/statistics_${TIMESTAMP}.json"
    log "Creating database statistics backup: $backup_file"
    
    # Collect comprehensive database statistics
    local cypher_query="
    CALL {
        // Node counts by label
        CALL db.labels() YIELD label
        CALL apoc.cypher.run('MATCH (n:' + label + ') RETURN count(n) as count', {}) YIELD value
        RETURN {type: 'node_count', label: label, count: value.count} AS stat
        
        UNION ALL
        
        // Relationship counts by type
        CALL db.relationshipTypes() YIELD relationshipType
        CALL apoc.cypher.run('MATCH ()-[r:' + relationshipType + ']->() RETURN count(r) as count', {}) YIELD value
        RETURN {type: 'relationship_count', relationshipType: relationshipType, count: value.count} AS stat
        
        UNION ALL
        
        // Database info
        CALL dbms.components() YIELD name, versions, edition
        RETURN {type: 'database_info', name: name, versions: versions, edition: edition} AS stat
        
        UNION ALL
        
        // Store file sizes
        CALL dbms.queryJmx('org.neo4j:instance=kernel#0,name=Store file sizes') YIELD attributes
        RETURN {type: 'store_sizes', attributes: attributes} AS stat
    }
    RETURN collect(stat) AS statistics
    "
    
    if cypher-shell -a "bolt://$NEO4J_HOST:$NEO4J_PORT" -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" --format plain "$cypher_query" > "$backup_file" 2>/dev/null; then
        success "Statistics backup created successfully"
        echo "Statistics backup: $backup_file"
    else
        error "Failed to create statistics backup"
        return 1
    fi
}

# Function to create admin backup (using neo4j-admin)
create_admin_backup() {
    local backup_file="$BACKUP_DIR/admin_backup_${TIMESTAMP}"
    log "Creating admin backup: $backup_file"
    
    # Check if running in Docker
    if command -v docker-compose >/dev/null 2>&1; then
        # Use docker-compose to run neo4j-admin backup
        if docker-compose -f docker-compose.local.yml exec -T neo4j neo4j-admin database backup neo4j --to-path="/backups/admin_backup_${TIMESTAMP}" >/dev/null 2>&1; then
            success "Admin backup created successfully"
            echo "Admin backup: $backup_file"
        else
            error "Failed to create admin backup"
            return 1
        fi
    else
        warning "Docker not available, skipping admin backup"
        return 1
    fi
}

# Function to clean up old backups (keep last 7 days)
cleanup_old_backups() {
    log "Cleaning up old backups (keeping last 7 days)..."
    
    local files_deleted=0
    
    # Clean up different backup types
    for pattern in "*.cypher" "*.json" "*.graphml" "admin_backup_*"; do
        if find "$BACKUP_DIR" -name "$pattern" -type f -mtime +7 -delete 2>/dev/null; then
            files_deleted=$((files_deleted + 1))
        fi
    done
    
    if [[ $files_deleted -gt 0 ]]; then
        success "Cleaned up $files_deleted old backup files"
    else
        log "No old backup files to clean up"
    fi
}

# Function to show backup statistics
show_backup_stats() {
    log "Neo4j backup statistics:"
    echo "Backup directory: $BACKUP_DIR"
    
    if [[ ! -d "$BACKUP_DIR" ]]; then
        warning "Backup directory does not exist"
        return 1
    fi
    
    echo "Total backups: $(find "$BACKUP_DIR" -type f \( -name "*.cypher" -o -name "*.json" -o -name "*.graphml" \) | wc -l)"
    echo "Total size: $(du -sh "$BACKUP_DIR" 2>/dev/null | cut -f1 || echo "Unknown")"
    echo ""
    
    echo "Recent backups:"
    find "$BACKUP_DIR" -type f \( -name "*.cypher" -o -name "*.json" -o -name "*.graphml" \) -mtime -1 -exec ls -lh {} \; | head -10
    
    echo ""
    echo "Admin backups:"
    find "$BACKUP_DIR" -type d -name "admin_backup_*" -mtime -1 -exec ls -ld {} \; | head -5
}

# Function to verify backup integrity
verify_backup() {
    local backup_file="$1"
    
    if [[ ! -f "$backup_file" ]]; then
        error "Backup file not found: $backup_file"
        return 1
    fi
    
    log "Verifying backup: $backup_file"
    
    case "$backup_file" in
        *.cypher)
            # Check if Cypher file has valid syntax
            if grep -q "CREATE\|MERGE\|MATCH" "$backup_file"; then
                success "Cypher backup appears valid"
            else
                warning "Cypher backup may be incomplete"
                return 1
            fi
            ;;
        *.json)
            # Check if JSON file is valid
            if python3 -m json.tool "$backup_file" >/dev/null 2>&1; then
                success "JSON backup is valid"
            else
                error "JSON backup is invalid"
                return 1
            fi
            ;;
        *.graphml)
            # Check if GraphML file has valid XML structure
            if grep -q "<graphml\|<graph\|<node\|<edge" "$backup_file"; then
                success "GraphML backup appears valid"
            else
                warning "GraphML backup may be incomplete"
                return 1
            fi
            ;;
        *)
            warning "Unknown backup format, skipping verification"
            ;;
    esac
}

# Main execution
main() {
    case "${1:-cypher}" in
        "help"|"--help"|"-h")
            echo "Usage: $0 [cypher|json|graphml|schema|stats|admin|all|cleanup|verify <file>|stats-only]"
            echo ""
            echo "Options:"
            echo "  cypher     - Create Cypher export backup (default)"
            echo "  json       - Create JSON export backup"
            echo "  graphml    - Create GraphML export backup"
            echo "  schema     - Create schema-only backup"
            echo "  stats      - Create database statistics backup"
            echo "  admin      - Create admin backup (requires Docker)"
            echo "  all        - Create all types of backups"
            echo "  cleanup    - Remove backups older than 7 days"
            echo "  verify     - Verify backup file integrity"
            echo "  stats-only - Show backup statistics only"
            echo ""
            echo "Environment variables:"
            echo "  NEO4J_HOST     - Neo4j host (default: localhost)"
            echo "  NEO4J_PORT     - Neo4j Bolt port (default: 7687)"
            echo "  NEO4J_USER     - Neo4j username (default: neo4j)"
            echo "  NEO4J_PASSWORD - Neo4j password (default: ml_password)"
            echo "  BACKUP_DIR     - Backup directory (default: ./backups/neo4j)"
            exit 0
            ;;
        "stats-only")
            show_backup_stats
            exit 0
            ;;
        "cleanup")
            cleanup_old_backups
            exit 0
            ;;
        "verify")
            if [[ -z "$2" ]]; then
                error "Please specify backup file to verify"
                echo "Usage: $0 verify <backup_file_path>"
                exit 1
            fi
            verify_backup "$2"
            exit 0
            ;;
    esac
    
    log "Starting Neo4j backup"
    
    # Check connectivity for operations that need it
    if ! check_connectivity; then
        error "Cannot connect to Neo4j, aborting backup"
        exit 1
    fi
    
    case "${1:-cypher}" in
        "cypher")
            create_cypher_backup
            ;;
        "json")
            create_json_backup
            ;;
        "graphml")
            create_graphml_backup
            ;;
        "schema")
            create_schema_backup
            ;;
        "stats")
            create_stats_backup
            ;;
        "admin")
            create_admin_backup
            ;;
        "all")
            create_cypher_backup
            create_json_backup
            create_schema_backup
            create_stats_backup
            create_admin_backup
            ;;
        "cleanup")
            cleanup_old_backups
            ;;
        "verify")
            if [[ -z "$2" ]]; then
                error "Please specify backup file to verify"
                echo "Usage: $0 verify <backup_file_path>"
                exit 1
            fi
            verify_backup "$2"
            ;;
        "stats-only")
            show_backup_stats
            ;;
        *)
            echo "Usage: $0 [cypher|json|graphml|schema|stats|admin|all|cleanup|verify <file>|stats-only|help]"
            echo ""
            echo "Options:"
            echo "  cypher     - Create Cypher export backup (default)"
            echo "  json       - Create JSON export backup"
            echo "  graphml    - Create GraphML export backup"
            echo "  schema     - Create schema-only backup"
            echo "  stats      - Create database statistics backup"
            echo "  admin      - Create admin backup (requires Docker)"
            echo "  all        - Create all types of backups"
            echo "  cleanup    - Remove backups older than 7 days"
            echo "  verify     - Verify backup file integrity"
            echo "  stats-only - Show backup statistics only"
            echo "  help       - Show this help message"
            echo ""
            echo "Environment variables:"
            echo "  NEO4J_HOST     - Neo4j host (default: localhost)"
            echo "  NEO4J_PORT     - Neo4j Bolt port (default: 7687)"
            echo "  NEO4J_USER     - Neo4j username (default: neo4j)"
            echo "  NEO4J_PASSWORD - Neo4j password (default: ml_password)"
            echo "  BACKUP_DIR     - Backup directory (default: ./backups/neo4j)"
            exit 1
            ;;
    esac
    
    # Always show stats after backup operations (except for stats-only and cleanup)
    if [[ "$1" != "stats-only" && "$1" != "cleanup" && "$1" != "verify" ]]; then
        echo ""
        show_backup_stats
    fi
    
    success "Neo4j backup operation completed"
}

# Run main function with all arguments
main "$@"