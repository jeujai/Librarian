#!/bin/bash
"""
Milvus Schema Initialization Script

This script provides a convenient way to initialize Milvus collection schemas
for the Multimodal Librarian application. It handles environment setup and
provides common initialization patterns.

Usage:
    # Initialize all default collections
    ./database/milvus/init_schemas.sh
    
    # Initialize with force recreation
    ./database/milvus/init_schemas.sh --force
    
    # Validate existing schemas
    ./database/milvus/init_schemas.sh --validate
    
    # Initialize specific collections
    ./database/milvus/init_schemas.sh --collections knowledge_chunks document_embeddings
    
    # Initialize with optional collections
    ./database/milvus/init_schemas.sh --include-optional
    
    # Use custom Milvus connection
    ./database/milvus/init_schemas.sh --host milvus.example.com --port 19530
"""

set -e  # Exit on any error

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Default values
MILVUS_HOST="${MILVUS_HOST:-localhost}"
MILVUS_PORT="${MILVUS_PORT:-19530}"
FORCE=false
VALIDATE_ONLY=false
INCLUDE_OPTIONAL=false
VERBOSE=false
COLLECTIONS=""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
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

# Help function
show_help() {
    cat << EOF
Milvus Schema Initialization Script

USAGE:
    $0 [OPTIONS]

OPTIONS:
    --host HOST             Milvus host (default: localhost)
    --port PORT             Milvus port (default: 19530)
    --collections LIST      Space-separated list of collections to initialize
    --force                 Force recreation of existing collections
    --validate              Only validate existing schemas, don't create
    --include-optional      Include optional collections in initialization
    --verbose               Enable verbose logging
    --help                  Show this help message

EXAMPLES:
    # Initialize all default collections
    $0
    
    # Force recreation of all collections
    $0 --force
    
    # Validate existing schemas
    $0 --validate
    
    # Initialize specific collections
    $0 --collections knowledge_chunks document_embeddings
    
    # Initialize with optional collections
    $0 --include-optional
    
    # Connect to remote Milvus
    $0 --host milvus.example.com --port 19530

ENVIRONMENT VARIABLES:
    MILVUS_HOST            Default Milvus host
    MILVUS_PORT            Default Milvus port
    PYTHONPATH             Python path (automatically set)

COLLECTIONS:
    Default Collections:
    - knowledge_chunks      Document text chunks with embeddings
    - document_embeddings   Document-level embeddings
    - conversation_embeddings  Chat message embeddings
    
    Optional Collections:
    - multimedia_embeddings  Multimodal content embeddings

EOF
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --host)
            MILVUS_HOST="$2"
            shift 2
            ;;
        --port)
            MILVUS_PORT="$2"
            shift 2
            ;;
        --collections)
            shift
            COLLECTIONS=""
            while [[ $# -gt 0 && ! "$1" =~ ^-- ]]; do
                COLLECTIONS="$COLLECTIONS $1"
                shift
            done
            ;;
        --force)
            FORCE=true
            shift
            ;;
        --validate)
            VALIDATE_ONLY=true
            shift
            ;;
        --include-optional)
            INCLUDE_OPTIONAL=true
            shift
            ;;
        --verbose)
            VERBOSE=true
            shift
            ;;
        --help)
            show_help
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Function to check if Milvus is accessible
check_milvus_connection() {
    log_info "Checking Milvus connection at $MILVUS_HOST:$MILVUS_PORT..."
    
    # Try to connect using curl to health endpoint
    if command -v curl >/dev/null 2>&1; then
        if curl -f -s "http://$MILVUS_HOST:9091/healthz" >/dev/null 2>&1; then
            log_success "Milvus health check passed"
            return 0
        fi
    fi
    
    # Try using netcat to check port
    if command -v nc >/dev/null 2>&1; then
        if nc -z "$MILVUS_HOST" "$MILVUS_PORT" 2>/dev/null; then
            log_success "Milvus port is accessible"
            return 0
        fi
    fi
    
    log_warning "Could not verify Milvus connection (this may be normal)"
    log_info "Proceeding with initialization attempt..."
    return 0
}

# Function to check Python dependencies
check_python_dependencies() {
    log_info "Checking Python dependencies..."
    
    # Check if Python is available
    if ! command -v python3 >/dev/null 2>&1; then
        log_error "Python 3 is not installed or not in PATH"
        exit 1
    fi
    
    # Check if pymilvus is available
    if ! python3 -c "import pymilvus" 2>/dev/null; then
        log_error "pymilvus is not installed"
        log_info "Install with: pip install pymilvus"
        exit 1
    fi
    
    log_success "Python dependencies are available"
}

# Function to set up environment
setup_environment() {
    log_info "Setting up environment..."
    
    # Set PYTHONPATH to include project root
    export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"
    
    # Change to project root directory
    cd "$PROJECT_ROOT"
    
    log_success "Environment setup complete"
}

# Function to wait for Milvus to be ready
wait_for_milvus() {
    log_info "Waiting for Milvus to be ready..."
    
    local max_attempts=30
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        if python3 -c "
from pymilvus import connections, utility
try:
    connections.connect('test', host='$MILVUS_HOST', port='$MILVUS_PORT', timeout=5)
    utility.list_collections(using='test')
    connections.disconnect('test')
    exit(0)
except:
    exit(1)
" 2>/dev/null; then
            log_success "Milvus is ready"
            return 0
        fi
        
        log_info "Attempt $attempt/$max_attempts: Milvus not ready, waiting..."
        sleep 2
        ((attempt++))
    done
    
    log_error "Milvus did not become ready within timeout"
    return 1
}

# Function to run schema initialization
run_initialization() {
    log_info "Starting Milvus schema initialization..."
    
    # Build Python command
    local python_cmd="python3 database/milvus/init_schemas.py"
    python_cmd="$python_cmd --host $MILVUS_HOST --port $MILVUS_PORT"
    
    if [ "$FORCE" = true ]; then
        python_cmd="$python_cmd --force"
    fi
    
    if [ "$VALIDATE_ONLY" = true ]; then
        python_cmd="$python_cmd --validate-only"
    fi
    
    if [ "$INCLUDE_OPTIONAL" = true ]; then
        python_cmd="$python_cmd --include-optional"
    fi
    
    if [ "$VERBOSE" = true ]; then
        python_cmd="$python_cmd --verbose"
    fi
    
    if [ -n "$COLLECTIONS" ]; then
        python_cmd="$python_cmd --collections$COLLECTIONS"
    fi
    
    log_info "Running: $python_cmd"
    
    # Execute the Python script
    if eval "$python_cmd"; then
        log_success "Schema initialization completed successfully"
        return 0
    else
        log_error "Schema initialization failed"
        return 1
    fi
}

# Function to show post-initialization info
show_post_init_info() {
    cat << EOF

${GREEN}Schema initialization completed!${NC}

${BLUE}Next steps:${NC}
1. Verify collections in Attu web interface: http://localhost:3000
2. Test the connection with your application
3. Start inserting data using the MilvusClient

${BLUE}Useful commands:${NC}
# List collections
python3 -c "from pymilvus import connections, utility; connections.connect('default', host='$MILVUS_HOST', port='$MILVUS_PORT'); print(utility.list_collections())"

# Validate schemas
$0 --validate

# Check collection stats
python3 database/milvus/validate_setup.py --host $MILVUS_HOST --port $MILVUS_PORT

${BLUE}Troubleshooting:${NC}
- Check Milvus logs: docker-compose -f docker-compose.local.yml logs milvus
- Verify dependencies: docker-compose -f docker-compose.local.yml ps etcd minio
- Test connection: curl http://$MILVUS_HOST:9091/healthz

EOF
}

# Main execution
main() {
    log_info "Milvus Schema Initialization"
    log_info "============================"
    
    # Pre-flight checks
    check_python_dependencies
    setup_environment
    check_milvus_connection
    
    # Wait for Milvus to be ready (unless validating only)
    if [ "$VALIDATE_ONLY" != true ]; then
        wait_for_milvus
    fi
    
    # Run the initialization
    if run_initialization; then
        if [ "$VALIDATE_ONLY" != true ]; then
            show_post_init_info
        fi
        exit 0
    else
        log_error "Initialization failed. Check the logs above for details."
        exit 1
    fi
}

# Handle script interruption
trap 'log_warning "Script interrupted by user"; exit 1' INT TERM

# Run main function
main "$@"