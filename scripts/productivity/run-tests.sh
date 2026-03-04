#!/bin/bash
#
# Optimized Test Runner
#
# This script runs tests with optimizations for development workflow.
#

set -e

# Configuration
TEST_TYPE="all"
PARALLEL_WORKERS=4
COVERAGE_ENABLED=false
PERFORMANCE_TESTS=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --type)
            TEST_TYPE="$2"
            shift 2
            ;;
        --parallel)
            PARALLEL_WORKERS="$2"
            shift 2
            ;;
        --coverage)
            COVERAGE_ENABLED=true
            shift
            ;;
        --performance)
            PERFORMANCE_TESTS=true
            shift
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo "Options:"
            echo "  --type TYPE          Test type: unit, integration, performance, all"
            echo "  --parallel WORKERS   Number of parallel workers (default: 4)"
            echo "  --coverage           Enable coverage reporting"
            echo "  --performance        Include performance tests"
            echo "  --help               Show this help"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

echo "🧪 Running optimized tests..."
echo "   Type: $TEST_TYPE"
echo "   Parallel workers: $PARALLEL_WORKERS"
echo "   Coverage: $COVERAGE_ENABLED"
echo "   Performance tests: $PERFORMANCE_TESTS"

# Set up test environment
export ML_ENVIRONMENT=local
export DATABASE_TYPE=local
export TEST_MODE=true
export PYTEST_WORKERS=$PARALLEL_WORKERS

# Build pytest command
PYTEST_CMD="pytest"

# Add parallel execution
if [[ $PARALLEL_WORKERS -gt 1 ]]; then
    PYTEST_CMD="$PYTEST_CMD -n $PARALLEL_WORKERS"
fi

# Add coverage
if [[ "$COVERAGE_ENABLED" == "true" ]]; then
    PYTEST_CMD="$PYTEST_CMD --cov=multimodal_librarian --cov-report=html --cov-report=term"
fi

# Add test type filter
case $TEST_TYPE in
    unit)
        PYTEST_CMD="$PYTEST_CMD -m unit"
        ;;
    integration)
        PYTEST_CMD="$PYTEST_CMD -m integration"
        ;;
    performance)
        PYTEST_CMD="$PYTEST_CMD -m performance"
        ;;
    all)
        if [[ "$PERFORMANCE_TESTS" == "false" ]]; then
            PYTEST_CMD="$PYTEST_CMD -m 'not performance'"
        fi
        ;;
esac

# Run tests
echo "🚀 Executing: $PYTEST_CMD"
$PYTEST_CMD tests/

echo "✅ Tests completed successfully!"

# Show coverage report location if enabled
if [[ "$COVERAGE_ENABLED" == "true" ]]; then
    echo "📊 Coverage report available at: htmlcov/index.html"
fi
