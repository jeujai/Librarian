#!/bin/bash

# Local Development Testing Script
# This script runs tests for the local development environment
# It can be used both locally and in CI/CD pipelines

set -e  # Exit on any error

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$PROJECT_ROOT/docker-compose.local.yml"
ENV_FILE="$PROJECT_ROOT/.env.test"

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
Local Development Testing Script

Usage: $0 [OPTIONS] [TEST_TYPE]

TEST_TYPE:
    unit                Run unit tests only
    integration         Run integration tests only
    local               Run local-specific tests only
    clients             Run database client tests only
    config              Run configuration tests only
    docker              Run Docker Compose tests only
    performance         Run performance tests only
    all                 Run all tests (default)

OPTIONS:
    -h, --help          Show this help message
    -v, --verbose       Verbose output
    -c, --coverage      Generate coverage report
    -f, --fast          Skip slow tests
    -s, --services      Start services only (don't run tests)
    -k, --keep          Keep services running after tests
    -n, --no-services   Run tests without starting services (assume they're running)
    --parallel          Run tests in parallel
    --docker-compose    Use Docker Compose for all services
    --github-services   Use GitHub Actions services (CI mode)
    --cleanup           Clean up all test resources and exit

Examples:
    $0                          # Run all tests with local services
    $0 unit -c                  # Run unit tests with coverage
    $0 integration --docker-compose  # Run integration tests with Docker Compose
    $0 -s                       # Start services only
    $0 --cleanup                # Clean up test resources

Environment Variables:
    TEST_POSTGRES_HOST          PostgreSQL host (default: localhost)
    TEST_POSTGRES_PORT          PostgreSQL port (default: 5432)
    TEST_NEO4J_HOST            Neo4j host (default: localhost)
    TEST_NEO4J_PORT            Neo4j port (default: 7687)
    TEST_MILVUS_HOST           Milvus host (default: localhost)
    TEST_MILVUS_PORT           Milvus port (default: 19530)
    TEST_REDIS_HOST            Redis host (default: localhost)
    TEST_REDIS_PORT            Redis port (default: 6379)
    SKIP_SERVICE_WAIT          Skip waiting for services to be ready
    MAX_WAIT_TIME              Maximum time to wait for services (default: 300s)

EOF
}

# Default values
TEST_TYPE="all"
VERBOSE=false
COVERAGE=false
FAST=false
SERVICES_ONLY=false
KEEP_SERVICES=false
NO_SERVICES=false
PARALLEL=false
USE_DOCKER_COMPOSE=false
GITHUB_SERVICES=false
CLEANUP_ONLY=false

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        -c|--coverage)
            COVERAGE=true
            shift
            ;;
        -f|--fast)
            FAST=true
            shift
            ;;
        -s|--services)
            SERVICES_ONLY=true
            shift
            ;;
        -k|--keep)
            KEEP_SERVICES=true
            shift
            ;;
        -n|--no-services)
            NO_SERVICES=true
            shift
            ;;
        --parallel)
            PARALLEL=true
            shift
            ;;
        --docker-compose)
            USE_DOCKER_COMPOSE=true
            shift
            ;;
        --github-services)
            GITHUB_SERVICES=true
            shift
            ;;
        --cleanup)
            CLEANUP_ONLY=true
            shift
            ;;
        unit|integration|local|clients|config|docker|performance|all)
            TEST_TYPE="$1"
            shift
            ;;
        *)
            log_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Change to project root
cd "$PROJECT_ROOT"

# Cleanup function
cleanup_resources() {
    log_info "Cleaning up test resources..."
    
    # Stop Docker Compose services
    if [ -f "$COMPOSE_FILE" ]; then
        docker-compose -f "$COMPOSE_FILE" down -v 2>/dev/null || true
    fi
    
    # Stop standalone Milvus if running
    if [ -f "standalone_embed.sh" ]; then
        bash standalone_embed.sh stop 2>/dev/null || true
    fi
    
    # Clean up Docker resources
    docker system prune -f 2>/dev/null || true
    
    # Remove test files
    rm -f .env.test
    rm -f standalone_embed.sh
    rm -rf htmlcov/
    rm -f .coverage
    rm -f coverage.xml
    rm -f test-results-*.xml
    rm -f integration-results-*.xml
    rm -f client-results-*.xml
    rm -f benchmark-results.json
    
    log_success "Cleanup completed"
}

# Handle cleanup-only mode
if [ "$CLEANUP_ONLY" = true ]; then
    cleanup_resources
    exit 0
fi

# Trap to cleanup on exit
if [ "$KEEP_SERVICES" = false ]; then
    trap cleanup_resources EXIT
fi

# Check dependencies
check_dependencies() {
    log_info "Checking dependencies..."
    
    # Check Python
    if ! command -v python3 &> /dev/null; then
        log_error "Python 3 is required but not installed"
        exit 1
    fi
    
    # Check pip
    if ! command -v pip &> /dev/null && ! command -v pip3 &> /dev/null; then
        log_error "pip is required but not installed"
        exit 1
    fi
    
    # Check Docker if needed
    if [ "$USE_DOCKER_COMPOSE" = true ] && ! command -v docker &> /dev/null; then
        log_error "Docker is required for Docker Compose mode but not installed"
        exit 1
    fi
    
    # Check Docker Compose if needed
    if [ "$USE_DOCKER_COMPOSE" = true ] && ! command -v docker-compose &> /dev/null; then
        log_error "Docker Compose is required but not installed"
        exit 1
    fi
    
    log_success "Dependencies check passed"
}

# Install Python dependencies
install_dependencies() {
    log_info "Installing Python dependencies..."
    
    # Upgrade pip
    python3 -m pip install --upgrade pip
    
    # Install requirements
    if [ -f "requirements.txt" ]; then
        pip install -r requirements.txt
    fi
    
    if [ -f "requirements-dev.txt" ]; then
        pip install -r requirements-dev.txt
    fi
    
    # Install test dependencies
    pip install pytest pytest-cov pytest-asyncio pytest-xdist pytest-timeout pytest-benchmark
    
    log_success "Python dependencies installed"
}

# Set up test environment
setup_test_environment() {
    log_info "Setting up test environment..."
    
    # Create test environment file
    cat > "$ENV_FILE" << EOF
# Local Development Test Environment
ML_ENVIRONMENT=test
ML_DATABASE_TYPE=local
DATABASE_TYPE=local
DEBUG=true
LOG_LEVEL=DEBUG

# Service Configuration
POSTGRES_HOST=${TEST_POSTGRES_HOST:-localhost}
POSTGRES_PORT=${TEST_POSTGRES_PORT:-5432}
POSTGRES_DB=multimodal_librarian_test
POSTGRES_USER=ml_user
POSTGRES_PASSWORD=ml_password

NEO4J_HOST=${TEST_NEO4J_HOST:-localhost}
NEO4J_PORT=${TEST_NEO4J_PORT:-7687}
NEO4J_USER=neo4j
NEO4J_PASSWORD=ml_password
NEO4J_URI=bolt://${TEST_NEO4J_HOST:-localhost}:${TEST_NEO4J_PORT:-7687}

MILVUS_HOST=${TEST_MILVUS_HOST:-localhost}
MILVUS_PORT=${TEST_MILVUS_PORT:-19530}
MILVUS_COLLECTION_NAME=test_knowledge_chunks

REDIS_HOST=${TEST_REDIS_HOST:-localhost}
REDIS_PORT=${TEST_REDIS_PORT:-6379}
REDIS_DB=1

# Connection Settings
CONNECTION_TIMEOUT=15
QUERY_TIMEOUT=10
MAX_RETRIES=2
POOL_SIZE=5

# Test Optimizations
ENABLE_HEALTH_CHECKS=false
VALIDATE_CONFIG_ON_STARTUP=false
STRICT_CONFIG_VALIDATION=false
ENABLE_QUERY_LOGGING=false

# Disable External Services
OPENAI_API_KEY=test-key-disabled
GOOGLE_API_KEY=test-key-disabled
ANTHROPIC_API_KEY=test-key-disabled

# Test-specific Settings
TEST_MODE=true
PYTEST_CURRENT_TEST=true
EOF
    
    # Export environment variables
    export ML_ENVIRONMENT=test
    export ML_DATABASE_TYPE=local
    export DATABASE_TYPE=local
    
    log_success "Test environment configured"
}

# Wait for service to be ready
wait_for_service() {
    local service_name="$1"
    local host="$2"
    local port="$3"
    local max_wait="${MAX_WAIT_TIME:-300}"
    local wait_time=0
    
    log_info "Waiting for $service_name to be ready..."
    
    while [ $wait_time -lt $max_wait ]; do
        if nc -z "$host" "$port" 2>/dev/null; then
            log_success "$service_name is ready"
            return 0
        fi
        
        sleep 2
        wait_time=$((wait_time + 2))
        
        if [ $((wait_time % 30)) -eq 0 ]; then
            log_info "Still waiting for $service_name... (${wait_time}s/${max_wait}s)"
        fi
    done
    
    log_error "$service_name failed to start within ${max_wait}s"
    return 1
}

# Start services with Docker Compose
start_docker_compose_services() {
    log_info "Starting services with Docker Compose..."
    
    # Copy environment file
    cp .env.local.example .env.local
    
    # Update for testing
    cat >> .env.local << EOF

# Test overrides
POSTGRES_DB=multimodal_librarian_test
MILVUS_COLLECTION_NAME=test_knowledge_chunks
REDIS_DB=1
DEBUG=true
LOG_LEVEL=DEBUG
EOF
    
    # Start services
    docker-compose -f "$COMPOSE_FILE" up -d
    
    # Wait for services
    if [ "$SKIP_SERVICE_WAIT" != "true" ]; then
        wait_for_service "PostgreSQL" "localhost" "5432"
        wait_for_service "Neo4j" "localhost" "7687"
        wait_for_service "Redis" "localhost" "6379"
        wait_for_service "Milvus" "localhost" "19530"
    fi
    
    log_success "Docker Compose services started"
}

# Start standalone services (for GitHub Actions or local development)
start_standalone_services() {
    log_info "Starting standalone services..."
    
    # Start Milvus standalone
    if [ "$GITHUB_SERVICES" = false ]; then
        log_info "Starting Milvus standalone..."
        
        # Download Milvus standalone script
        curl -sfL https://raw.githubusercontent.com/milvus-io/milvus/master/scripts/standalone_embed.sh -o standalone_embed.sh
        chmod +x standalone_embed.sh
        
        # Start Milvus
        bash standalone_embed.sh start
        
        # Wait for Milvus
        if [ "$SKIP_SERVICE_WAIT" != "true" ]; then
            wait_for_service "Milvus" "localhost" "19530"
        fi
    fi
    
    log_success "Standalone services started"
}

# Verify service connectivity
verify_services() {
    log_info "Verifying service connectivity..."
    
    # PostgreSQL
    if command -v psql &> /dev/null; then
        PGPASSWORD=ml_password psql -h "${TEST_POSTGRES_HOST:-localhost}" -U ml_user -d multimodal_librarian_test -c "SELECT version();" >/dev/null 2>&1 || {
            log_warning "PostgreSQL connection test failed"
        }
    fi
    
    # Neo4j
    if command -v cypher-shell &> /dev/null; then
        echo 'RETURN "Hello Neo4j" as message' | cypher-shell -u neo4j -p ml_password >/dev/null 2>&1 || {
            log_warning "Neo4j connection test failed"
        }
    fi
    
    # Redis
    if command -v redis-cli &> /dev/null; then
        redis-cli -h "${TEST_REDIS_HOST:-localhost}" ping >/dev/null 2>&1 || {
            log_warning "Redis connection test failed"
        }
    fi
    
    # Milvus
    curl -f "http://${TEST_MILVUS_HOST:-localhost}:${TEST_MILVUS_PORT:-19530}/healthz" >/dev/null 2>&1 || {
        log_warning "Milvus health check failed"
    }
    
    log_success "Service connectivity verified"
}

# Initialize test databases
initialize_databases() {
    log_info "Initializing test databases..."
    
    # PostgreSQL
    if [ -f "database/postgresql/init_db.sql" ] && command -v psql &> /dev/null; then
        PGPASSWORD=ml_password psql -h "${TEST_POSTGRES_HOST:-localhost}" -U ml_user -d multimodal_librarian_test -f database/postgresql/init_db.sql >/dev/null 2>&1 || {
            log_warning "PostgreSQL initialization failed"
        }
    fi
    
    # Neo4j
    if [ -f "database/neo4j/init_schema.sh" ]; then
        bash database/neo4j/init_schema.sh >/dev/null 2>&1 || {
            log_warning "Neo4j initialization failed"
        }
    fi
    
    # Milvus (initialize via Python)
    python3 -c "
import sys
sys.path.append('src')
try:
    from multimodal_librarian.clients.milvus_client import MilvusClient
    import asyncio
    
    async def init_milvus():
        client = MilvusClient(host='${TEST_MILVUS_HOST:-localhost}', port=${TEST_MILVUS_PORT:-19530})
        await client.connect()
        try:
            await client.create_collection('test_knowledge_chunks', dimension=384)
        except Exception:
            pass  # Collection might already exist
        await client.disconnect()
    
    asyncio.run(init_milvus())
except Exception as e:
    print(f'Milvus initialization: {e}')
" 2>/dev/null || {
        log_warning "Milvus initialization failed"
    }
    
    log_success "Test databases initialized"
}

# Build pytest command
build_pytest_command() {
    local cmd="pytest"
    
    # Add verbosity
    if [ "$VERBOSE" = true ]; then
        cmd="$cmd -v"
    fi
    
    # Add coverage
    if [ "$COVERAGE" = true ]; then
        cmd="$cmd --cov=src/multimodal_librarian --cov-report=xml --cov-report=html --cov-report=term-missing"
    fi
    
    # Add parallel execution
    if [ "$PARALLEL" = true ]; then
        cmd="$cmd -n auto"
    fi
    
    # Add timeout
    cmd="$cmd --timeout=60"
    
    # Add test selection based on type
    case "$TEST_TYPE" in
        unit)
            cmd="$cmd tests/ -k 'not integration and not docker'"
            if [ "$FAST" = true ]; then
                cmd="$cmd -m 'not slow'"
            fi
            ;;
        integration)
            cmd="$cmd tests/integration/"
            ;;
        local)
            cmd="$cmd tests/ -k 'local'"
            ;;
        clients)
            cmd="$cmd tests/clients/"
            ;;
        config)
            cmd="$cmd tests/config/"
            ;;
        docker)
            cmd="$cmd tests/integration/test_local_docker_integration.py"
            ;;
        performance)
            cmd="$cmd tests/performance/ --benchmark-only"
            ;;
        all)
            cmd="$cmd tests/"
            if [ "$FAST" = true ]; then
                cmd="$cmd -m 'not slow'"
            fi
            ;;
    esac
    
    # Add JUnit XML output
    cmd="$cmd --junit-xml=test-results-${TEST_TYPE}.xml"
    
    echo "$cmd"
}

# Run tests
run_tests() {
    log_info "Running $TEST_TYPE tests..."
    
    # Build pytest command
    local pytest_cmd
    pytest_cmd=$(build_pytest_command)
    
    log_info "Executing: $pytest_cmd"
    
    # Run tests
    if eval "$pytest_cmd"; then
        log_success "$TEST_TYPE tests passed"
        return 0
    else
        log_error "$TEST_TYPE tests failed"
        return 1
    fi
}

# Main execution
main() {
    log_info "Starting local development testing..."
    log_info "Test type: $TEST_TYPE"
    log_info "Options: verbose=$VERBOSE, coverage=$COVERAGE, fast=$FAST"
    
    # Check dependencies
    check_dependencies
    
    # Install Python dependencies
    install_dependencies
    
    # Set up test environment
    setup_test_environment
    
    # Start services if needed
    if [ "$NO_SERVICES" = false ]; then
        if [ "$USE_DOCKER_COMPOSE" = true ]; then
            start_docker_compose_services
        else
            start_standalone_services
        fi
        
        # Verify services
        verify_services
        
        # Initialize databases
        initialize_databases
    fi
    
    # Exit if services-only mode
    if [ "$SERVICES_ONLY" = true ]; then
        log_success "Services started successfully"
        log_info "Services are running. Use --cleanup to stop them."
        exit 0
    fi
    
    # Run tests
    if run_tests; then
        log_success "All tests completed successfully"
        exit 0
    else
        log_error "Some tests failed"
        exit 1
    fi
}

# Run main function
main "$@"