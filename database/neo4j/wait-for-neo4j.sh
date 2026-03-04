#!/bin/bash
# Wait for Neo4j to be ready and run initialization scripts

set -e

NEO4J_HOST=${NEO4J_HOST:-neo4j}
NEO4J_PORT=${NEO4J_PORT:-7687}
NEO4J_USER=${NEO4J_USER:-neo4j}
NEO4J_PASSWORD=${NEO4J_PASSWORD:-ml_password}
MAX_WAIT=${MAX_WAIT:-300}  # 5 minutes

echo "Waiting for Neo4j to be ready at $NEO4J_HOST:$NEO4J_PORT..."

# Function to check if Neo4j is ready
check_neo4j() {
    cypher-shell -a "bolt://$NEO4J_HOST:$NEO4J_PORT" -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" "RETURN 1" > /dev/null 2>&1
}

# Wait for Neo4j to be ready
WAIT_TIME=0
while ! check_neo4j; do
    if [ $WAIT_TIME -ge $MAX_WAIT ]; then
        echo "ERROR: Neo4j did not become ready within $MAX_WAIT seconds"
        exit 1
    fi
    
    echo "Neo4j not ready yet, waiting... ($WAIT_TIME/$MAX_WAIT seconds)"
    sleep 5
    WAIT_TIME=$((WAIT_TIME + 5))
done

echo "Neo4j is ready! Running initialization scripts..."

# Directory containing initialization scripts
INIT_DIR="/var/lib/neo4j/init"

# Check if initialization scripts exist
if [ ! -d "$INIT_DIR" ]; then
    echo "No initialization directory found at $INIT_DIR"
    exit 0
fi

# Run initialization scripts in order
for script in "$INIT_DIR"/*.cypher; do
    if [ -f "$script" ]; then
        echo "Running initialization script: $(basename "$script")"
        cypher-shell -a "bolt://$NEO4J_HOST:$NEO4J_PORT" -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" -f "$script"
        
        if [ $? -eq 0 ]; then
            echo "Successfully executed: $(basename "$script")"
        else
            echo "ERROR: Failed to execute: $(basename "$script")"
            exit 1
        fi
    fi
done

echo "All Neo4j initialization scripts completed successfully!"

# Run health check
echo "Running health check..."
cypher-shell -a "bolt://$NEO4J_HOST:$NEO4J_PORT" -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" -f "/var/lib/neo4j/health_check.cypher"

echo "Neo4j initialization and health check completed!"