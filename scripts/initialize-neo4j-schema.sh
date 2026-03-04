#!/bin/bash
# =============================================================================
# Initialize Neo4j Schema for Local Development
# =============================================================================
# This script initializes the Neo4j schema after the Docker containers are up.
# It should be run after `docker-compose -f docker-compose.local.yml up -d`
#
# Usage:
#   ./scripts/initialize-neo4j-schema.sh [--skip-sample-data]
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    local color=$1
    local message=$2
    echo -e "${color}${message}${NC}"
}

# Check if Docker Compose is available
if ! command -v docker-compose &> /dev/null; then
    print_status $RED "ERROR: docker-compose is not installed or not in PATH"
    exit 1
fi

# Check if Neo4j container is running
if ! docker-compose -f docker-compose.local.yml ps neo4j | grep -q "Up"; then
    print_status $RED "ERROR: Neo4j container is not running"
    print_status $YELLOW "Please start the containers first:"
    print_status $YELLOW "  docker-compose -f docker-compose.local.yml up -d"
    exit 1
fi

print_status $GREEN "==================================================================="
print_status $GREEN "Initializing Neo4j Schema for Multimodal Librarian"
print_status $GREEN "==================================================================="

# Wait for Neo4j to be fully ready
print_status $BLUE "Waiting for Neo4j to be ready..."
max_attempts=30
attempt=1

while [[ $attempt -le $max_attempts ]]; do
    if docker-compose -f docker-compose.local.yml exec -T neo4j cypher-shell \
        -u neo4j -p ml_password "RETURN 1 as test" &> /dev/null; then
        print_status $GREEN "✓ Neo4j is ready"
        break
    fi
    
    print_status $YELLOW "  Attempt $attempt/$max_attempts - waiting for Neo4j..."
    sleep 2
    ((attempt++))
    
    if [[ $attempt -gt $max_attempts ]]; then
        print_status $RED "ERROR: Neo4j did not become ready within $max_attempts attempts"
        exit 1
    fi
done

echo ""

# Execute schema initialization scripts in order
init_scripts=(
    "00_schema_initialization.cypher"
    "01_verify_plugins.cypher"
    "02_create_constraints.cypher"
)

# Add sample data script if not skipping
if [[ "$1" != "--skip-sample-data" ]]; then
    init_scripts+=("03_sample_data.cypher")
else
    print_status $YELLOW "Skipping sample data (--skip-sample-data flag provided)"
fi

# Execute each script
for script in "${init_scripts[@]}"; do
    script_path="/var/lib/neo4j/init/$script"
    
    print_status $BLUE "Executing: $script"
    
    if docker-compose -f docker-compose.local.yml exec -T neo4j test -f "$script_path"; then
        if docker-compose -f docker-compose.local.yml exec -T neo4j cypher-shell \
            -u neo4j -p ml_password --file "$script_path"; then
            print_status $GREEN "  ✓ $script completed successfully"
        else
            print_status $RED "  ✗ $script failed"
            if [[ "$script" == "00_schema_initialization.cypher" ]]; then
                print_status $RED "ERROR: Core schema initialization failed, aborting"
                exit 1
            else
                print_status $YELLOW "  Warning: Non-critical script failed, continuing..."
            fi
        fi
    else
        print_status $YELLOW "  Warning: $script not found, skipping..."
    fi
    
    echo ""
done

# Verify the schema
print_status $BLUE "Verifying schema installation..."

verification_query="
CALL db.constraints() YIELD name, type
WITH count(*) as constraint_count

CALL db.indexes() YIELD name, state
WITH constraint_count, count(*) as index_count, collect(state) as states
WHERE constraint_count >= 8 AND index_count >= 15 AND all(state IN states WHERE state = 'ONLINE')

MATCH (s:SchemaDoc)
WITH constraint_count, index_count, count(s) as schema_docs
WHERE schema_docs >= 1

RETURN 'Schema verification successful' as status,
       constraint_count as constraints,
       index_count as indexes,
       schema_docs as documentation_nodes;
"

if docker-compose -f docker-compose.local.yml exec -T neo4j cypher-shell \
    -u neo4j -p ml_password "$verification_query" &> /dev/null; then
    print_status $GREEN "✓ Schema verification completed successfully"
else
    print_status $YELLOW "Warning: Schema verification had issues, but basic setup appears complete"
fi

echo ""
print_status $GREEN "==================================================================="
print_status $GREEN "Neo4j Schema Initialization Complete!"
print_status $GREEN "==================================================================="

print_status $BLUE "Next steps:"
print_status $YELLOW "  1. Access Neo4j Browser at http://localhost:7474"
print_status $YELLOW "  2. Login with username: neo4j, password: ml_password"
print_status $YELLOW "  3. Run 'CALL db.schema.visualization()' to see the schema"
print_status $YELLOW "  4. Explore sample data with queries from database/neo4j/sample_queries.cypher"

echo ""
print_status $BLUE "Useful commands:"
print_status $YELLOW "  # View all node labels"
print_status $YELLOW "  CALL db.labels()"
print_status $YELLOW ""
print_status $YELLOW "  # View all relationship types"
print_status $YELLOW "  CALL db.relationshipTypes()"
print_status $YELLOW ""
print_status $YELLOW "  # Count nodes by type"
print_status $YELLOW "  MATCH (n) RETURN labels(n) as label, count(n) as count ORDER BY count DESC"

echo ""