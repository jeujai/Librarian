#!/bin/bash

# =============================================================================
# Multimodal Librarian - Local Development Environment Setup
# =============================================================================
# This script helps set up the local development environment

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to check Docker and Docker Compose
check_docker() {
    print_status "Checking Docker installation..."
    
    if ! command_exists docker; then
        print_error "Docker is not installed. Please install Docker first."
        echo "Visit: https://docs.docker.com/get-docker/"
        exit 1
    fi
    
    if ! command_exists docker-compose; then
        print_error "Docker Compose is not installed. Please install Docker Compose first."
        echo "Visit: https://docs.docker.com/compose/install/"
        exit 1
    fi
    
    # Check if Docker daemon is running
    if ! docker info >/dev/null 2>&1; then
        print_error "Docker daemon is not running. Please start Docker first."
        exit 1
    fi
    
    print_success "Docker and Docker Compose are available"
}

# Function to check system resources
check_resources() {
    print_status "Checking system resources..."
    
    # Check available memory (Linux/macOS)
    if command_exists free; then
        # Linux
        available_mem=$(free -m | awk 'NR==2{printf "%.0f", $7}')
    elif command_exists vm_stat; then
        # macOS
        available_mem=$(vm_stat | grep "Pages free" | awk '{print $3}' | sed 's/\.//' | awk '{print $1 * 4096 / 1024 / 1024}')
    else
        available_mem=8192  # Assume 8GB if we can't detect
        print_warning "Could not detect available memory. Assuming 8GB available."
    fi
    
    if [ "$available_mem" -lt 6144 ]; then  # Less than 6GB
        print_warning "Available memory is ${available_mem}MB. Recommended minimum is 6GB."
        print_warning "You may experience performance issues or out-of-memory errors."
    else
        print_success "Available memory: ${available_mem}MB (sufficient)"
    fi
    
    # Check available disk space
    available_disk=$(df -h . | awk 'NR==2 {print $4}' | sed 's/G//')
    if [ "${available_disk%.*}" -lt 10 ]; then  # Less than 10GB
        print_warning "Available disk space is ${available_disk}GB. Recommended minimum is 10GB."
    else
        print_success "Available disk space: ${available_disk}GB (sufficient)"
    fi
}

# Function to create .env.local file
setup_env_file() {
    print_status "Setting up environment configuration..."
    
    if [ -f ".env.local" ]; then
        print_warning ".env.local already exists. Backing up to .env.local.backup"
        cp .env.local .env.local.backup
    fi
    
    if [ ! -f ".env.local.example" ]; then
        print_error ".env.local.example not found. Please ensure you're in the project root directory."
        exit 1
    fi
    
    cp .env.local.example .env.local
    print_success "Created .env.local from template"
    
    # Prompt for API keys
    echo ""
    print_status "API Key Configuration (Optional but recommended for full functionality)"
    echo "You can skip these now and add them later to .env.local"
    echo ""
    
    read -p "Enter your OpenAI API key (or press Enter to skip): " openai_key
    if [ ! -z "$openai_key" ]; then
        sed -i.bak "s/OPENAI_API_KEY=your-openai-api-key-here/OPENAI_API_KEY=$openai_key/" .env.local
        rm .env.local.bak
        print_success "OpenAI API key configured"
    fi
    
    read -p "Enter your Google API key (or press Enter to skip): " google_key
    if [ ! -z "$google_key" ]; then
        sed -i.bak "s/GOOGLE_API_KEY=your-google-api-key-here/GOOGLE_API_KEY=$google_key/" .env.local
        rm .env.local.bak
        print_success "Google API key configured"
    fi
    
    read -p "Enter your Anthropic API key (or press Enter to skip): " anthropic_key
    if [ ! -z "$anthropic_key" ]; then
        sed -i.bak "s/ANTHROPIC_API_KEY=your-anthropic-api-key-here/ANTHROPIC_API_KEY=$anthropic_key/" .env.local
        rm .env.local.bak
        print_success "Anthropic API key configured"
    fi
}

# Function to create data directories
create_directories() {
    print_status "Creating data directories..."
    
    directories=(
        "data/postgres"
        "data/postgres-config"
        "data/neo4j"
        "data/neo4j-logs"
        "data/neo4j-import"
        "data/neo4j-plugins"
        "data/milvus"
        "data/etcd"
        "data/minio"
        "data/redis"
        "data/pgadmin"
        "uploads"
        "media"
        "exports"
        "logs"
        "audit_logs"
        "backups/postgresql"
        "backups/neo4j"
        "test_uploads"
        "test_media"
        "test_exports"
    )
    
    for dir in "${directories[@]}"; do
        if [ ! -d "$dir" ]; then
            mkdir -p "$dir"
            print_success "Created directory: $dir"
        fi
    done
    
    # Set appropriate permissions
    chmod 755 data/
    chmod -R 755 data/*/
    chmod -R 755 uploads/ media/ exports/ logs/ audit_logs/ backups/
    
    print_success "All data directories created with proper permissions"
}

# Function to pull Docker images
pull_images() {
    print_status "Pulling Docker images (this may take a while)..."
    
    if docker-compose -f docker-compose.local.yml pull; then
        print_success "All Docker images pulled successfully"
    else
        print_error "Failed to pull some Docker images. Check your internet connection."
        exit 1
    fi
}

# Function to validate configuration
validate_config() {
    print_status "Validating Docker Compose configuration..."
    
    if docker-compose -f docker-compose.local.yml config >/dev/null 2>&1; then
        print_success "Docker Compose configuration is valid"
    else
        print_error "Docker Compose configuration has errors:"
        docker-compose -f docker-compose.local.yml config
        exit 1
    fi
}

# Function to start services
start_services() {
    print_status "Starting local development services..."
    
    # Start services in background
    if docker-compose -f docker-compose.local.yml up -d; then
        print_success "Services started successfully"
        
        print_status "Waiting for services to be ready..."
        sleep 10
        
        # Check service health
        print_status "Checking service health..."
        docker-compose -f docker-compose.local.yml ps
        
        echo ""
        print_success "Local development environment is ready!"
        echo ""
        echo "Access points:"
        echo "  • Application:        http://localhost:8000"
        echo "  • API Documentation:  http://localhost:8000/docs"
        echo "  • Neo4j Browser:      http://localhost:7474 (neo4j/ml_password)"
        echo "  • pgAdmin:            http://localhost:5050 (admin@multimodal-librarian.local/admin)"
        echo "  • Milvus Admin:       http://localhost:3000"
        echo "  • Redis Commander:    http://localhost:8081"
        echo "  • MinIO Console:      http://localhost:9001 (minioadmin/minioadmin)"
        echo "  • Log Viewer:         http://localhost:8080"
        echo ""
        echo "To view logs: docker-compose -f docker-compose.local.yml logs -f"
        echo "To stop:      docker-compose -f docker-compose.local.yml down"
        echo ""
    else
        print_error "Failed to start services. Check the logs:"
        docker-compose -f docker-compose.local.yml logs
        exit 1
    fi
}

# Function to show help
show_help() {
    echo "Multimodal Librarian - Local Development Setup"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --help, -h          Show this help message"
    echo "  --check-only        Only check prerequisites, don't set up"
    echo "  --no-start          Set up but don't start services"
    echo "  --pull-only         Only pull Docker images"
    echo "  --reset             Reset environment (remove all data)"
    echo ""
    echo "Examples:"
    echo "  $0                  Full setup and start"
    echo "  $0 --check-only     Check if system is ready"
    echo "  $0 --no-start       Set up but don't start services"
    echo "  $0 --reset          Reset and recreate environment"
}

# Function to reset environment
reset_environment() {
    print_warning "This will remove all local data and containers!"
    read -p "Are you sure? (y/N): " confirm
    
    if [ "$confirm" = "y" ] || [ "$confirm" = "Y" ]; then
        print_status "Stopping and removing containers..."
        docker-compose -f docker-compose.local.yml down -v --remove-orphans
        
        print_status "Removing data directories..."
        rm -rf data/
        
        print_status "Removing environment file..."
        rm -f .env.local
        
        print_success "Environment reset complete"
    else
        print_status "Reset cancelled"
        exit 0
    fi
}

# Main execution
main() {
    echo "============================================================================="
    echo "Multimodal Librarian - Local Development Environment Setup"
    echo "============================================================================="
    echo ""
    
    # Parse command line arguments
    case "${1:-}" in
        --help|-h)
            show_help
            exit 0
            ;;
        --check-only)
            check_docker
            check_resources
            print_success "System check complete - ready for setup"
            exit 0
            ;;
        --pull-only)
            check_docker
            pull_images
            exit 0
            ;;
        --reset)
            reset_environment
            ;;
        --no-start)
            NO_START=true
            ;;
    esac
    
    # Run setup steps
    check_docker
    check_resources
    setup_env_file
    create_directories
    pull_images
    validate_config
    
    if [ "${NO_START:-}" != "true" ]; then
        start_services
    else
        print_success "Setup complete. Run 'docker-compose -f docker-compose.local.yml up -d' to start services."
    fi
}

# Run main function with all arguments
main "$@"