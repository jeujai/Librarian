#!/bin/bash
# =============================================================================
# Neo4j Schema Initialization Script
# =============================================================================
# This script initializes the Neo4j database with the complete schema,
# constraints, indexes, and sample data for local development.
#
# Usage:
#   ./init_schema.sh [--skip-sample-data] [--verify-only]
#
# Options:
#   --skip-sample-data    Skip loading sample data (production mode)
#   --verify-only         Only verify the schema, don't create anything
#   --help               Show this help message
# =============================================================================

set -e

# Configuration
NEO4J_HOST=${NEO4J_HOST:-localhost}
NEO4J_PORT=${NEO4J_PORT:-7687}
NEO4J_USER=${NEO4J_USER:-neo4j}
NEO4J_PASSWORD=${NEO4J_PASSWORD:-ml_password}
NEO4J_DATABASE=${NEO4J_DATABASE:-neo4j}

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INIT_DIR="$SCRIPT_DIR/init"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Flags
SKIP_SAMPLE_DATA=false
VERIFY_ONLY=false

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-sample-data)
            SKIP_SAMPLE_DATA=true
            shift
            ;;
        --verify-only)
            VERIFY_ONLY=true
            shift
            ;;
        --help)
            echo "Usage: $0 [--skip-sample-data] [--verify-only] [--help]"
            echo ""
            echo "Options:"
            echo "  --skip-sample-data    Skip loading sample data (production mode)"
            echo "  --verify-only         Only verify the schema, don't create anything"
            echo "  --help               Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Function to print colored output
print_status() {
    local color=$1
    local message=$2
    echo -e "${color}${message}${NC}"
}

# Function to execute Cypher script
execute_cypher_script() {
    local script_file=$1
    local description=$2
    
    if [[ ! -f "$script_file" ]]; then
        print_status $RED "ERROR: Script file not found: $script_file"
        return 1
    fi
    
    print_status $BLUE "Executing: $description"
    print_status $YELLOW "  Script: $(basename "$script_file")"
    
    if [[ "$VERIFY_ONLY" == "true" ]]; then
        print_status $YELLOW "  [VERIFY MODE] Would execute: $script_file"
        return 0
    fi
    
    # Check if running in Docker or local
    if command -v docker-compose &> /dev/null && docker-compose -f docker-compose.local.yml ps neo4j | grep -q "Up"; then
        # Running in Docker Compose
        docker-compose -f docker-compose.local.yml exec -T neo4j cypher-shell \
            -u "$NEO4J_USER" \
            -p "$NEO4J_PASSWORD" \
            -d "$NEO4J_DATABASE" \
            --file /dev/stdin < "$script_file"
    elif command -v cypher-shell &> /dev/null; then
        # Running locally
        cypher-shell \
            -a "bolt://$NEO4J_HOST:$NEO4J_PORT" \
            -u "$NEO4J_USER" \
            -p "$NEO4J_PASSWORD" \
            -d "$NEO4J_DATABASE" \
            --file "$script_file"
    else
        print_status $RED "ERROR: Neither docker-compose nor cypher-shell found"
        print_status $YELLOW "Please ensure Neo4j is running and cypher-shell is available"
        return 1
    fi
    
    if [[ $? -eq 0 ]]; then
        print_status $GREEN "  ✓ Completed successfully"
    else
        print_status $RED "  ✗ Failed to execute script"
        return 1
    fi
}

# Function to wait for Neo4j to be ready
wait_for_neo4j() {
    print_status $BLUE "Waiting for Neo4j to be ready..."
    
    local max_attempts=30
    local attempt=1
    
    while [[ $attempt -le $max_attempts ]]; do
        if [[ "$VERIFY_ONLY" == "true" ]]; then
            print_status $YELLOW "  [VERIFY MODE] Would check Neo4j connectivity"
            return 0
        fi
        
        # Try to connect to Neo4j
        if command -v docker-compose &> /dev/null && docker-compose -f docker-compose.local.yml ps neo4j | grep -q "Up"; then
            # Check Docker Compose Neo4j
            if docker-compose -f docker-compose.local.yml exec -T neo4j cypher-shell \
                -u "$NEO4J_USER" \
                -p "$NEO4J_PASSWORD" \
                -d "$NEO4J_DATABASE" \
                "RETURN 1 as test" &> /dev/null; then
                print_status $GREEN "  ✓ Neo4j is ready"
                return 0
            fi
        elif command -v cypher-shell &> /dev/null; then
            # Check local Neo4j
            if cypher-shell \
                -a "bolt://$NEO4J_HOST:$NEO4J_PORT" \
                -u "$NEO4J_USER" \
                -p "$NEO4J_PASSWORD" \
                -d "$NEO4J_DATABASE" \
                "RETURN 1 as test" &> /dev/null; then
                print_status $GREEN "  ✓ Neo4j is ready"
                return 0
            fi
        fi
        
        print_status $YELLOW "  Attempt $attempt/$max_attempts - Neo4j not ready yet, waiting..."
        sleep 2
        ((attempt++))
    done
    
    print_status $RED "ERROR: Neo4j did not become ready within $max_attempts attempts"
    return 1
}

# Function to verify schema
verify_schema() {
    print_status $BLUE "Verifying schema installation..."
    
    if [[ "$VERIFY_ONLY" == "true" ]]; then
        print_status $YELLOW "  [VERIFY MODE] Would verify schema"
        return 0
    fi
    
    # Create verification script
    local verify_script="/tmp/neo4j_verify_schema.cypher"
    cat > "$verify_script" << 'EOF'
// Verify constraints
CALL db.constraints() YIELD name, type
WITH count(*) as constraint_count
WHERE constraint_count >= 8  // Minimum expected constraints

// Verify indexes
CALL db.indexes() YIELD name, state
WITH count(*) as index_count
WHERE index_count >= 15 AND all(idx IN collect(state) WHERE idx = "ONLINE")

// Verify schema documentation
MATCH (s:SchemaDoc)
WITH count(s) as schema_doc_count
WHERE schema_doc_count >= 1

RETURN "Schema verification completed successfully" as status,
       datetime() as verified_at;
EOF
    
    execute_cypher_script "$verify_script" "Schema Verification"
    local result=$?
    
    # Clean up
    rm -f "$verify_script"
    
    return $result
}

# Main execution
main() {
    print_status $GREEN "==================================================================="
    print_status $GREEN "Neo4j Schema Initialization for Multimodal Librarian"
    print_status $GREEN "==================================================================="
    
    print_status $BLUE "Configuration:"
    print_status $YELLOW "  Neo4j Host: $NEO4J_HOST:$NEO4J_PORT"
    print_status $YELLOW "  Database: $NEO4J_DATABASE"
    print_status $YELLOW "  User: $NEO4J_USER"
    print_status $YELLOW "  Skip Sample Data: $SKIP_SAMPLE_DATA"
    print_status $YELLOW "  Verify Only: $VERIFY_ONLY"
    echo ""
    
    # Wait for Neo4j to be ready
    if ! wait_for_neo4j; then
        print_status $RED "Failed to connect to Neo4j. Please check your configuration."
        exit 1
    fi
    
    echo ""
    print_status $GREEN "Starting schema initialization..."
    echo ""
    
    # Step 1: Schema Initialization (constraints, indexes, documentation)
    if ! execute_cypher_script "$INIT_DIR/00_schema_initialization.cypher" "Complete Schema Setup"; then
        print_status $RED "Failed to initialize schema"
        exit 1
    fi
    
    echo ""
    
    # Step 2: Plugin Verification
    if ! execute_cypher_script "$INIT_DIR/01_verify_plugins.cypher" "Plugin Verification"; then
        print_status $YELLOW "Warning: Plugin verification failed, but continuing..."
    fi
    
    echo ""
    
    # Step 3: Additional Constraints (if any)
    if [[ -f "$INIT_DIR/02_create_constraints.cypher" ]]; then
        if ! execute_cypher_script "$INIT_DIR/02_create_constraints.cypher" "Additional Constraints"; then
            print_status $YELLOW "Warning: Additional constraints failed, but continuing..."
        fi
        echo ""
    fi
    
    # Step 4: Sample Data (optional)
    if [[ "$SKIP_SAMPLE_DATA" == "false" ]] && [[ -f "$INIT_DIR/03_sample_data.cypher" ]]; then
        if ! execute_cypher_script "$INIT_DIR/03_sample_data.cypher" "Sample Data Loading"; then
            print_status $YELLOW "Warning: Sample data loading failed, but continuing..."
        fi
        echo ""
    elif [[ "$SKIP_SAMPLE_DATA" == "true" ]]; then
        print_status $YELLOW "Skipping sample data loading (--skip-sample-data flag)"
        echo ""
    fi
    
    # Step 5: Verify Installation
    if ! verify_schema; then
        print_status $RED "Schema verification failed"
        exit 1
    fi
    
    echo ""
    print_status $GREEN "==================================================================="
    print_status $GREEN "Schema initialization completed successfully!"
    print_status $GREEN "==================================================================="
    
    if [[ "$VERIFY_ONLY" == "false" ]]; then
        print_status $BLUE "Next steps:"
        print_status $YELLOW "  1. Access Neo4j Browser at http://localhost:7474"
        print_status $YELLOW "  2. Login with username: $NEO4J_USER, password: $NEO4J_PASSWORD"
        print_status $YELLOW "  3. Run 'CALL db.schema.visualization()' to see the schema"
        print_status $YELLOW "  4. Start the application to begin using the knowledge graph"
    fi
    
    echo ""
}

# Run main function
main "$@"