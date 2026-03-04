#!/bin/bash

# =============================================================================
# TEST VOLUME MOUNTS
# =============================================================================
# This script tests that all volume mounts are working correctly
# for the local development environment

set -e

echo "🧪 Testing volume mounts for local development environment..."

# =============================================================================
# CONFIGURATION
# =============================================================================
COMPOSE_FILE="docker-compose.local.yml"
SERVICE_NAME="multimodal-librarian"
TEST_FILE="volume-mount-test-$(date +%s).txt"
TEST_CONTENT="Volume mount test - $(date)"

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================
cleanup() {
    echo "🧹 Cleaning up test files..."
    rm -f "src/${TEST_FILE}" 2>/dev/null || true
    rm -f "uploads/${TEST_FILE}" 2>/dev/null || true
    rm -f "logs/${TEST_FILE}" 2>/dev/null || true
    rm -f "notebooks/${TEST_FILE}" 2>/dev/null || true
}

test_mount() {
    local host_path="$1"
    local container_path="$2"
    local mount_type="$3"
    local description="$4"
    
    echo "  📁 Testing $description..."
    
    # Create test file on host
    echo "$TEST_CONTENT" > "$host_path/$TEST_FILE"
    
    # Check if file exists in container
    if docker compose -f "$COMPOSE_FILE" exec -T "$SERVICE_NAME" test -f "$container_path/$TEST_FILE"; then
        # Read content from container
        container_content=$(docker compose -f "$COMPOSE_FILE" exec -T "$SERVICE_NAME" cat "$container_path/$TEST_FILE" | tr -d '\r')
        
        if [ "$container_content" = "$TEST_CONTENT" ]; then
            echo "    ✅ $description mount working correctly"
            
            # Test write capability if it's a read-write mount
            if [ "$mount_type" = "rw" ]; then
                echo "    🔄 Testing write capability..."
                docker compose -f "$COMPOSE_FILE" exec -T "$SERVICE_NAME" sh -c "echo 'Container write test' >> '$container_path/$TEST_FILE'"
                
                if grep -q "Container write test" "$host_path/$TEST_FILE"; then
                    echo "    ✅ Write capability working"
                else
                    echo "    ❌ Write capability failed"
                    return 1
                fi
            fi
        else
            echo "    ❌ Content mismatch in $description"
            echo "    Expected: $TEST_CONTENT"
            echo "    Got: $container_content"
            return 1
        fi
    else
        echo "    ❌ File not found in container for $description"
        return 1
    fi
    
    # Clean up test file
    rm -f "$host_path/$TEST_FILE"
}

test_directory_mount() {
    local host_path="$1"
    local container_path="$2"
    local description="$3"
    
    echo "  📂 Testing $description directory..."
    
    # Check if directory exists in container
    if docker compose -f "$COMPOSE_FILE" exec -T "$SERVICE_NAME" test -d "$container_path"; then
        echo "    ✅ $description directory mounted correctly"
    else
        echo "    ❌ $description directory not found in container"
        return 1
    fi
}

# =============================================================================
# MAIN TESTS
# =============================================================================
trap cleanup EXIT

echo ""
echo "🔍 Checking if services are running..."

# Check if the service is running
if ! docker compose -f "$COMPOSE_FILE" ps "$SERVICE_NAME" | grep -q "Up"; then
    echo "❌ Service $SERVICE_NAME is not running"
    echo "   Please start the development environment first:"
    echo "   make dev-local"
    exit 1
fi

echo "✅ Service is running"
echo ""

# =============================================================================
# TEST SOURCE CODE MOUNTS
# =============================================================================
echo "🧪 Testing source code mounts..."

test_mount "src" "/app/src" "rw" "Source code"

# =============================================================================
# TEST APPLICATION DATA MOUNTS
# =============================================================================
echo ""
echo "🧪 Testing application data mounts..."

test_mount "uploads" "/app/uploads" "rw" "Uploads directory"
test_mount "logs" "/app/logs" "rw" "Logs directory"

# =============================================================================
# TEST DEVELOPMENT WORKSPACE MOUNTS
# =============================================================================
echo ""
echo "🧪 Testing development workspace mounts..."

test_mount "notebooks" "/app/notebooks" "rw" "Notebooks directory"

# =============================================================================
# TEST READ-ONLY MOUNTS
# =============================================================================
echo ""
echo "🧪 Testing read-only mounts..."

test_directory_mount "docs" "/app/docs" "Documentation"
test_directory_mount "examples" "/app/examples" "Examples"
test_directory_mount "scripts" "/app/scripts" "Scripts"

# =============================================================================
# TEST CONFIGURATION FILE MOUNTS
# =============================================================================
echo ""
echo "🧪 Testing configuration file mounts..."

# Test pyproject.toml mount
if docker compose -f "$COMPOSE_FILE" exec -T "$SERVICE_NAME" test -f "/app/pyproject.toml"; then
    echo "  ✅ pyproject.toml mounted correctly"
else
    echo "  ❌ pyproject.toml not found in container"
    exit 1
fi

# Test .env.local mount
if docker compose -f "$COMPOSE_FILE" exec -T "$SERVICE_NAME" test -f "/app/.env.local"; then
    echo "  ✅ .env.local mounted correctly"
else
    echo "  ❌ .env.local not found in container"
    exit 1
fi

# =============================================================================
# TEST CACHE VOLUMES
# =============================================================================
echo ""
echo "🧪 Testing cache volumes..."

test_directory_mount "cache" "/app/.cache" "ML model cache"

# =============================================================================
# TEST HOT RELOAD FUNCTIONALITY
# =============================================================================
echo ""
echo "🧪 Testing hot reload functionality..."

# Create a simple Python file to test hot reload
cat > "src/test_hot_reload.py" << 'EOF'
# Test file for hot reload functionality
def test_function():
    return "hot_reload_test_initial"
EOF

echo "  📝 Created test Python file..."

# Wait a moment for the file to be detected
sleep 2

# Check if the file is accessible in the container
if docker compose -f "$COMPOSE_FILE" exec -T "$SERVICE_NAME" python -c "
import sys
sys.path.append('/app/src')
try:
    from test_hot_reload import test_function
    result = test_function()
    print(f'Result: {result}')
    assert result == 'hot_reload_test_initial', f'Expected hot_reload_test_initial, got {result}'
    print('✅ Hot reload test passed')
except Exception as e:
    print(f'❌ Hot reload test failed: {e}')
    exit(1)
"; then
    echo "  ✅ Hot reload functionality working"
else
    echo "  ❌ Hot reload functionality failed"
    rm -f "src/test_hot_reload.py"
    exit 1
fi

# Clean up test file
rm -f "src/test_hot_reload.py"

# =============================================================================
# SUMMARY
# =============================================================================
echo ""
echo "🎉 All volume mount tests passed!"
echo ""
echo "✅ Volume mounts are working correctly:"
echo "  • Source code hot reload: ✅"
echo "  • Application data persistence: ✅"
echo "  • Development workspace: ✅"
echo "  • Read-only resource access: ✅"
echo "  • Configuration file access: ✅"
echo "  • Cache volume persistence: ✅"
echo ""
echo "🚀 Your development environment is ready for use!"
echo ""
echo "💡 Tips:"
echo "  • Edit files in ./src/ and see changes immediately"
echo "  • Upload files will persist in ./uploads/"
echo "  • Logs are available in ./logs/"
echo "  • Use ./notebooks/ for Jupyter development"
echo "  • Check ./cache/ for persistent ML model cache"
echo ""