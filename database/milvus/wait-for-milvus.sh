#!/bin/bash

# Wait for Milvus to be ready
# This script waits for Milvus to be fully operational before proceeding

set -e

# Configuration
MILVUS_HOST="${MILVUS_HOST:-localhost}"
MILVUS_PORT="${MILVUS_PORT:-19530}"
MILVUS_HTTP_PORT="${MILVUS_HTTP_PORT:-9091}"
MAX_ATTEMPTS="${MAX_ATTEMPTS:-60}"
SLEEP_INTERVAL="${SLEEP_INTERVAL:-5}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

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

# Check if required tools are available
check_dependencies() {
    if ! command -v curl &> /dev/null; then
        log_error "curl is required but not installed"
        exit 1
    fi
}

# Test HTTP health endpoint
test_http_health() {
    curl -f -s "http://$MILVUS_HOST:$MILVUS_HTTP_PORT/healthz" > /dev/null 2>&1
}

# Test gRPC connectivity (basic)
test_grpc_connectivity() {
    # Simple TCP connection test
    timeout 5 bash -c "</dev/tcp/$MILVUS_HOST/$MILVUS_PORT" 2>/dev/null
}

# Test with Python client if available
test_python_client() {
    python3 -c "
import sys
try:
    from pymilvus import connections, utility
    connections.connect(host='$MILVUS_HOST', port=$MILVUS_PORT, timeout=5)
    version = utility.get_server_version()
    connections.disconnect('default')
    print(f'Milvus version: {version}')
    sys.exit(0)
except Exception as e:
    print(f'Python client test failed: {e}')
    sys.exit(1)
" 2>/dev/null
}

# Main waiting loop
wait_for_milvus() {
    log_info "Waiting for Milvus at $MILVUS_HOST:$MILVUS_PORT (HTTP: $MILVUS_HTTP_PORT)"
    log_info "Max attempts: $MAX_ATTEMPTS, Sleep interval: ${SLEEP_INTERVAL}s"
    
    local attempt=1
    
    while [ $attempt -le $MAX_ATTEMPTS ]; do
        log_info "Attempt $attempt/$MAX_ATTEMPTS: Testing Milvus connectivity..."
        
        # Test HTTP health endpoint first (fastest)
        if test_http_health; then
            log_info "HTTP health endpoint responding"
            
            # Test gRPC connectivity
            if test_grpc_connectivity; then
                log_info "gRPC port accessible"
                
                # Test with Python client if available
                if command -v python3 &> /dev/null && python3 -c "import pymilvus" 2>/dev/null; then
                    if test_python_client; then
                        log_success "Milvus is fully ready! (HTTP + gRPC + Python client verified)"
                        return 0
                    else
                        log_warning "Python client test failed, but basic connectivity works"
                    fi
                else
                    log_info "Python client not available, skipping advanced test"
                fi
                
                log_success "Milvus is ready! (HTTP + gRPC verified)"
                return 0
            else
                log_warning "HTTP endpoint responding but gRPC port not accessible"
            fi
        else
            log_info "Milvus not ready yet..."
        fi
        
        if [ $attempt -lt $MAX_ATTEMPTS ]; then
            log_info "Waiting ${SLEEP_INTERVAL}s before next attempt..."
            sleep $SLEEP_INTERVAL
        fi
        
        ((attempt++))
    done
    
    log_error "Milvus failed to become ready after $MAX_ATTEMPTS attempts"
    log_error "Please check:"
    log_error "  1. Milvus container is running: docker ps | grep milvus"
    log_error "  2. Milvus logs: docker logs <milvus-container>"
    log_error "  3. Network connectivity to $MILVUS_HOST:$MILVUS_PORT"
    log_error "  4. Dependencies (etcd, minio) are running"
    
    return 1
}

# Show help
show_help() {
    echo "Wait for Milvus Script"
    echo
    echo "Usage: $0 [OPTIONS]"
    echo
    echo "Options:"
    echo "  -h, --help              Show this help message"
    echo "  --host HOST             Milvus host (default: localhost)"
    echo "  --port PORT             Milvus gRPC port (default: 19530)"
    echo "  --http-port PORT        Milvus HTTP port (default: 9091)"
    echo "  --max-attempts N        Maximum attempts (default: 60)"
    echo "  --sleep-interval N      Sleep interval in seconds (default: 5)"
    echo
    echo "Environment Variables:"
    echo "  MILVUS_HOST            Milvus host"
    echo "  MILVUS_PORT            Milvus gRPC port"
    echo "  MILVUS_HTTP_PORT       Milvus HTTP port"
    echo "  MAX_ATTEMPTS           Maximum attempts"
    echo "  SLEEP_INTERVAL         Sleep interval in seconds"
    echo
    echo "Examples:"
    echo "  $0                                    # Wait with defaults"
    echo "  $0 --host milvus --port 19530         # Custom host/port"
    echo "  $0 --max-attempts 30 --sleep-interval 10  # Custom timing"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        --host)
            MILVUS_HOST="$2"
            shift 2
            ;;
        --port)
            MILVUS_PORT="$2"
            shift 2
            ;;
        --http-port)
            MILVUS_HTTP_PORT="$2"
            shift 2
            ;;
        --max-attempts)
            MAX_ATTEMPTS="$2"
            shift 2
            ;;
        --sleep-interval)
            SLEEP_INTERVAL="$2"
            shift 2
            ;;
        *)
            log_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Main execution
check_dependencies
wait_for_milvus