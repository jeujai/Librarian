#!/bin/bash
"""
Enhanced Development Server with Hot Reload

This script provides an enhanced development experience with intelligent hot reload
functionality for the Multimodal Librarian application.

Features:
- Automatic server restart on file changes
- Configurable file watching patterns
- Graceful handling of configuration changes
- Development-optimized startup
- Real-time feedback on changes
"""

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
WATCH_DIRS="/app/src /app/pyproject.toml /app/.env.local"
RELOAD_DELAY=1
SERVER_HOST="0.0.0.0"
SERVER_PORT="8000"
LOG_LEVEL="DEBUG"

# Function to print colored output
print_status() {
    echo -e "${BLUE}[$(date '+%H:%M:%S')]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[$(date '+%H:%M:%S')]${NC} ✅ $1"
}

print_warning() {
    echo -e "${YELLOW}[$(date '+%H:%M:%S')]${NC} ⚠️  $1"
}

print_error() {
    echo -e "${RED}[$(date '+%H:%M:%S')]${NC} ❌ $1"
}

print_info() {
    echo -e "${CYAN}[$(date '+%H:%M:%S')]${NC} 💡 $1"
}

# Function to check if required tools are available
check_requirements() {
    print_status "Checking requirements..."
    
    # Check if we're in the right environment
    if [[ "$ML_ENVIRONMENT" != "local" ]]; then
        print_warning "ML_ENVIRONMENT is not set to 'local'"
        print_info "Setting ML_ENVIRONMENT=local for development"
        export ML_ENVIRONMENT=local
    fi
    
    # Check if source directory exists
    if [[ ! -d "/app/src" ]]; then
        print_error "Source directory /app/src not found"
        print_error "Make sure you're running this from the application container"
        exit 1
    fi
    
    # Check if Python is available
    if ! command -v python &> /dev/null; then
        print_error "Python not found"
        exit 1
    fi
    
    # Check if uvicorn is available
    if ! python -c "import uvicorn" &> /dev/null; then
        print_error "Uvicorn not available"
        print_info "Installing uvicorn..."
        pip install uvicorn[standard]
    fi
    
    print_success "Requirements check passed"
}

# Function to setup development environment
setup_dev_environment() {
    print_status "Setting up development environment..."
    
    # Set Python path
    export PYTHONPATH="/app/src:/app"
    
    # Set development environment variables
    export DEBUG=true
    export LOG_LEVEL=DEBUG
    export RELOAD_ENABLED=true
    export WATCHDOG_ENABLED=true
    
    # Create necessary directories
    mkdir -p /app/logs /app/uploads /app/media /app/exports
    
    print_success "Development environment setup complete"
}

# Function to start the development server with hot reload
start_dev_server() {
    print_status "Starting development server with hot reload..."
    
    # Build uvicorn command with hot reload options
    local cmd=(
        python -m uvicorn
        multimodal_librarian.main:app
        --host "$SERVER_HOST"
        --port "$SERVER_PORT"
        --reload
        --reload-dir /app/src
        --reload-include "*.py"
        --reload-include "*.yaml"
        --reload-include "*.yml"
        --reload-include "*.json"
        --reload-include "*.toml"
        --reload-exclude "__pycache__"
        --reload-exclude "*.pyc"
        --reload-exclude "*.pyo"
        --reload-exclude "*.pyd"
        --reload-exclude ".git"
        --log-level "$LOG_LEVEL"
        --access-log
        --use-colors
    )
    
    print_info "Server command: ${cmd[*]}"
    print_info "Watching directories: $WATCH_DIRS"
    print_info "Server will be available at: http://$SERVER_HOST:$SERVER_PORT"
    print_info "API documentation at: http://$SERVER_HOST:$SERVER_PORT/docs"
    
    echo
    print_success "🔥 Hot reload development server starting..."
    echo -e "${PURPLE}════════════════════════════════════════════════════════════════${NC}"
    echo -e "${PURPLE}🚀 Multimodal Librarian - Development Server with Hot Reload${NC}"
    echo -e "${PURPLE}════════════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}📝 Edit files in /app/src to trigger automatic reloads${NC}"
    echo -e "${GREEN}🛑 Press Ctrl+C to stop the server${NC}"
    echo -e "${PURPLE}════════════════════════════════════════════════════════════════${NC}"
    echo
    
    # Execute the server command
    exec "${cmd[@]}"
}

# Function to handle cleanup on exit
cleanup() {
    print_status "Cleaning up..."
    # Kill any background processes
    jobs -p | xargs -r kill
    print_success "Cleanup complete"
}

# Function to show help
show_help() {
    echo "Enhanced Development Server with Hot Reload"
    echo
    echo "Usage: $0 [OPTIONS]"
    echo
    echo "Options:"
    echo "  --host HOST        Server host (default: 0.0.0.0)"
    echo "  --port PORT        Server port (default: 8000)"
    echo "  --log-level LEVEL  Log level (default: DEBUG)"
    echo "  --help             Show this help message"
    echo
    echo "Environment Variables:"
    echo "  ML_ENVIRONMENT     Should be set to 'local' for development"
    echo "  DEBUG              Enable debug mode (default: true)"
    echo "  LOG_LEVEL          Set log level (default: DEBUG)"
    echo
    echo "Features:"
    echo "  • Automatic server restart on file changes"
    echo "  • Intelligent file watching (excludes cache files)"
    echo "  • Real-time feedback on changes"
    echo "  • Development-optimized configuration"
    echo "  • Graceful shutdown handling"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --host)
            SERVER_HOST="$2"
            shift 2
            ;;
        --port)
            SERVER_PORT="$2"
            shift 2
            ;;
        --log-level)
            LOG_LEVEL="$2"
            shift 2
            ;;
        --help)
            show_help
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Set up signal handlers for graceful shutdown
trap cleanup EXIT INT TERM

# Main execution
main() {
    print_status "🔥 Enhanced Development Server with Hot Reload"
    echo
    
    check_requirements
    setup_dev_environment
    start_dev_server
}

# Run main function
main "$@"