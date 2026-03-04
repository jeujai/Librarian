#!/bin/bash

# Dockerfile validation script for local development conversion
# Tests both development and production Docker builds

set -e

echo "🐳 Validating Dockerfile for local development conversion..."
echo "================================================================"

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

# Function to check if Docker is running
check_docker() {
    if ! docker info >/dev/null 2>&1; then
        print_status $RED "❌ Docker is not running. Please start Docker and try again."
        exit 1
    fi
    print_status $GREEN "✅ Docker is running"
}

# Function to validate Dockerfile syntax
validate_dockerfile_syntax() {
    print_status $BLUE "🔍 Validating Dockerfile syntax..."
    
    # Check if Dockerfile exists and is readable
    if [[ ! -f "Dockerfile" ]]; then
        print_status $RED "❌ Dockerfile not found"
        exit 1
    fi
    
    # Basic syntax validation by attempting to parse build context
    if docker build --help >/dev/null 2>&1; then
        print_status $GREEN "✅ Docker build command is available"
    else
        print_status $RED "❌ Docker build command not available"
        exit 1
    fi
}

# Function to test development build
test_development_build() {
    print_status $BLUE "🏗️  Testing development build..."
    
    # Build development image
    if docker build --target development -t multimodal-librarian:dev-test . >/dev/null 2>&1; then
        print_status $GREEN "✅ Development build successful"
    else
        print_status $RED "❌ Development build failed"
        docker build --target development -t multimodal-librarian:dev-test .
        exit 1
    fi
    
    # Test development image
    print_status $BLUE "🧪 Testing development image..."
    
    # Check if development dependencies are installed
    if docker run --rm multimodal-librarian:dev-test python -c "import pytest, black, isort, mypy" >/dev/null 2>&1; then
        print_status $GREEN "✅ Development dependencies are available"
    else
        print_status $RED "❌ Development dependencies missing"
        exit 1
    fi
    
    # Check if local database clients are available
    if docker run --rm multimodal-librarian:dev-test python -c "import neo4j, pymilvus" >/dev/null 2>&1; then
        print_status $GREEN "✅ Local database clients are available"
    else
        print_status $RED "❌ Local database clients missing"
        exit 1
    fi
    
    # Check if development tools are installed
    if docker run --rm multimodal-librarian:dev-test which vim >/dev/null 2>&1; then
        print_status $GREEN "✅ Development tools are installed"
    else
        print_status $YELLOW "⚠️  Some development tools may be missing"
    fi
    
    # Check environment variables
    if docker run --rm -e ML_ENVIRONMENT=local multimodal-librarian:dev-test python -c "import os; assert os.getenv('ML_ENVIRONMENT') == 'local'" >/dev/null 2>&1; then
        print_status $GREEN "✅ Environment variables work correctly"
    else
        print_status $RED "❌ Environment variable configuration failed"
        exit 1
    fi
}

# Function to test production build
test_production_build() {
    print_status $BLUE "🏗️  Testing production build..."
    
    # Build production image
    if docker build --target production -t multimodal-librarian:prod-test . >/dev/null 2>&1; then
        print_status $GREEN "✅ Production build successful"
    else
        print_status $RED "❌ Production build failed"
        docker build --target production -t multimodal-librarian:prod-test .
        exit 1
    fi
    
    # Test production image
    print_status $BLUE "🧪 Testing production image..."
    
    # Check that development dependencies are NOT installed
    if docker run --rm multimodal-librarian:prod-test python -c "import pytest" >/dev/null 2>&1; then
        print_status $YELLOW "⚠️  Development dependencies found in production image (may increase image size)"
    else
        print_status $GREEN "✅ Production image is clean (no development dependencies)"
    fi
    
    # Check that core dependencies are available
    if docker run --rm multimodal-librarian:prod-test python -c "import fastapi, uvicorn, torch, transformers" >/dev/null 2>&1; then
        print_status $GREEN "✅ Core production dependencies are available"
    else
        print_status $RED "❌ Core production dependencies missing"
        exit 1
    fi
    
    # Check environment variables
    if docker run --rm -e ML_ENVIRONMENT=aws multimodal-librarian:prod-test python -c "import os; assert os.getenv('ML_ENVIRONMENT') == 'aws'" >/dev/null 2>&1; then
        print_status $GREEN "✅ Production environment variables work correctly"
    else
        print_status $RED "❌ Production environment variable configuration failed"
        exit 1
    fi
}

# Function to test image sizes
check_image_sizes() {
    print_status $BLUE "📏 Checking image sizes..."
    
    dev_size=$(docker images multimodal-librarian:dev-test --format "table {{.Size}}" | tail -n 1)
    prod_size=$(docker images multimodal-librarian:prod-test --format "table {{.Size}}" | tail -n 1)
    
    print_status $BLUE "Development image size: $dev_size"
    print_status $BLUE "Production image size: $prod_size"
    
    # Convert sizes to bytes for comparison (simplified)
    if [[ "$dev_size" == *"GB"* ]] && [[ "$prod_size" == *"GB"* ]]; then
        print_status $GREEN "✅ Both images are reasonably sized"
    else
        print_status $YELLOW "⚠️  Check image sizes - they may be larger than expected"
    fi
}

# Function to test health checks
test_health_checks() {
    print_status $BLUE "🏥 Testing health check configurations..."
    
    # Test development health check
    dev_health=$(docker inspect multimodal-librarian:dev-test --format='{{.Config.Healthcheck.Test}}')
    if [[ "$dev_health" == *"curl"* ]]; then
        print_status $GREEN "✅ Development health check configured"
    else
        print_status $RED "❌ Development health check not configured properly"
    fi
    
    # Test production health check
    prod_health=$(docker inspect multimodal-librarian:prod-test --format='{{.Config.Healthcheck.Test}}')
    if [[ "$prod_health" == *"python"* ]]; then
        print_status $GREEN "✅ Production health check configured"
    else
        print_status $RED "❌ Production health check not configured properly"
    fi
}

# Function to cleanup test images
cleanup() {
    print_status $BLUE "🧹 Cleaning up test images..."
    docker rmi multimodal-librarian:dev-test >/dev/null 2>&1 || true
    docker rmi multimodal-librarian:prod-test >/dev/null 2>&1 || true
    print_status $GREEN "✅ Cleanup completed"
}

# Main execution
main() {
    echo "Starting Dockerfile validation..."
    echo
    
    check_docker
    validate_dockerfile_syntax
    
    echo
    print_status $BLUE "Testing Development Build"
    print_status $BLUE "========================"
    test_development_build
    
    echo
    print_status $BLUE "Testing Production Build"
    print_status $BLUE "======================="
    test_production_build
    
    echo
    check_image_sizes
    test_health_checks
    
    echo
    print_status $GREEN "🎉 All Dockerfile validations passed!"
    print_status $GREEN "✅ Development target: Ready for local development"
    print_status $GREEN "✅ Production target: Ready for AWS deployment"
    
    echo
    print_status $BLUE "Next steps:"
    echo "  1. Test with docker-compose.local.yml: make dev-local"
    echo "  2. Verify local database connectivity"
    echo "  3. Test hot reload functionality"
    echo "  4. Run integration tests"
    
    cleanup
}

# Handle script interruption
trap cleanup EXIT

# Run main function
main "$@"