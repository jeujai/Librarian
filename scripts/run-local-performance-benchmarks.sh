#!/bin/bash
"""
Local Development Performance Benchmark Runner Script

This script provides a convenient way to run performance benchmarks for the
local development conversion with various options and configurations.

Usage:
    ./scripts/run-local-performance-benchmarks.sh [options]
    
Options:
    --quick         Run in quick mode (abbreviated test suite)
    --skip-resource Skip resource-intensive tests
    --ci            Run in CI/CD mode
    --help          Show this help message

Examples:
    # Run full benchmark suite
    ./scripts/run-local-performance-benchmarks.sh
    
    # Run quick benchmarks for development
    ./scripts/run-local-performance-benchmarks.sh --quick
    
    # Run in CI/CD pipeline
    ./scripts/run-local-performance-benchmarks.sh --ci --quick
"""

set -e  # Exit on any error

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Default options
QUICK_MODE=false
SKIP_RESOURCE_TESTS=false
CI_MODE=false
GENERATE_HTML=true
OUTPUT_DIR="$PROJECT_ROOT/tests/performance/benchmark_reports"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_info() {
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

# Function to show help
show_help() {
    echo "Local Development Performance Benchmark Runner"
    echo ""
    echo "Usage: $0 [options]"
    echo ""
    echo "Options:"
    echo "  --quick         Run in quick mode (abbreviated test suite)"
    echo "  --skip-resource Skip resource-intensive tests"
    echo "  --ci            Run in CI/CD mode"
    echo "  --no-html       Don't generate HTML reports"
    echo "  --output-dir    Specify output directory"
    echo "  --help          Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0                                    # Run full benchmark suite"
    echo "  $0 --quick                           # Run quick benchmarks"
    echo "  $0 --ci --quick --no-html            # Run in CI/CD mode"
    echo "  $0 --output-dir ./my-results         # Custom output directory"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --quick)
            QUICK_MODE=true
            shift
            ;;
        --skip-resource)
            SKIP_RESOURCE_TESTS=true
            shift
            ;;
        --ci)
            CI_MODE=true
            GENERATE_HTML=false
            shift
            ;;
        --no-html)
            GENERATE_HTML=false
            shift
            ;;
        --output-dir)
            OUTPUT_DIR="$2"
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

# Function to check prerequisites
check_prerequisites() {
    print_info "Checking prerequisites..."
    
    # Check if Python is available
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 is required but not installed"
        exit 1
    fi
    
    # Check if we're in the project root
    if [[ ! -f "$PROJECT_ROOT/pyproject.toml" ]]; then
        print_error "Script must be run from project root or scripts directory"
        exit 1
    fi
    
    # Check if benchmark files exist
    if [[ ! -f "$PROJECT_ROOT/tests/performance/test_local_development_benchmarks.py" ]]; then
        print_error "Benchmark test file not found"
        exit 1
    fi
    
    if [[ ! -f "$PROJECT_ROOT/tests/performance/run_local_development_benchmarks.py" ]]; then
        print_error "Benchmark runner not found"
        exit 1
    fi
    
    print_success "Prerequisites check passed"
}

# Function to check local services
check_local_services() {
    print_info "Checking local database services..."
    
    # Check if Docker is running
    if ! docker info &> /dev/null; then
        print_warning "Docker is not running - some tests may fail"
        return 1
    fi
    
    # Check if docker-compose.local.yml exists
    if [[ ! -f "$PROJECT_ROOT/docker-compose.local.yml" ]]; then
        print_warning "docker-compose.local.yml not found - local services may not be available"
        return 1
    fi
    
    # Check if services are running
    cd "$PROJECT_ROOT"
    if docker-compose -f docker-compose.local.yml ps | grep -q "Up"; then
        print_success "Local database services are running"
        return 0
    else
        print_warning "Local database services don't appear to be running"
        print_info "You may want to start them with: docker-compose -f docker-compose.local.yml up -d"
        return 1
    fi
}

# Function to create output directory
setup_output_directory() {
    print_info "Setting up output directory: $OUTPUT_DIR"
    
    mkdir -p "$OUTPUT_DIR"
    
    if [[ ! -w "$OUTPUT_DIR" ]]; then
        print_error "Output directory is not writable: $OUTPUT_DIR"
        exit 1
    fi
    
    print_success "Output directory ready"
}

# Function to run benchmarks
run_benchmarks() {
    print_info "Starting performance benchmarks..."
    
    # Build command
    local cmd=(
        "python3"
        "$PROJECT_ROOT/tests/performance/run_local_development_benchmarks.py"
        "--output-dir" "$OUTPUT_DIR"
    )
    
    # Add options based on flags
    if [[ "$QUICK_MODE" == "true" ]]; then
        cmd+=(--quick-mode)
        print_info "Running in quick mode"
    fi
    
    if [[ "$SKIP_RESOURCE_TESTS" == "true" ]]; then
        cmd+=(--skip-resource-tests)
        print_info "Skipping resource-intensive tests"
    fi
    
    if [[ "$CI_MODE" == "true" ]]; then
        cmd+=(--ci-mode)
        print_info "Running in CI/CD mode"
    fi
    
    if [[ "$GENERATE_HTML" == "false" ]]; then
        cmd+=(--no-html)
        print_info "HTML report generation disabled"
    fi
    
    # Add configuration file if it exists
    local config_file="$PROJECT_ROOT/tests/performance/benchmark_config.json"
    if [[ -f "$config_file" ]]; then
        cmd+=(--config-file "$config_file")
        print_info "Using configuration file: $config_file"
    fi
    
    print_info "Running command: ${cmd[*]}"
    echo ""
    
    # Change to project root and run
    cd "$PROJECT_ROOT"
    
    # Run the benchmark command
    if "${cmd[@]}"; then
        print_success "Benchmarks completed successfully"
        return 0
    else
        local exit_code=$?
        case $exit_code in
            1)
                print_warning "Benchmarks completed with warnings"
                return 1
                ;;
            2)
                print_error "Benchmarks failed - performance issues detected"
                return 2
                ;;
            3)
                print_error "Benchmark execution error"
                return 3
                ;;
            *)
                print_error "Benchmarks failed with exit code: $exit_code"
                return $exit_code
                ;;
        esac
    fi
}

# Function to show results
show_results() {
    print_info "Benchmark results:"
    
    # Find the most recent results file
    local latest_json=$(find "$OUTPUT_DIR" -name "local_development_benchmarks_*.json" -type f -printf '%T@ %p\n' | sort -n | tail -1 | cut -d' ' -f2-)
    local latest_html=$(find "$OUTPUT_DIR" -name "local_development_benchmark_report_*.html" -type f -printf '%T@ %p\n' | sort -n | tail -1 | cut -d' ' -f2-)
    
    if [[ -n "$latest_json" ]]; then
        print_success "JSON report: $latest_json"
        
        # Try to extract summary information
        if command -v jq &> /dev/null; then
            local summary=$(jq -r '.summary // empty' "$latest_json" 2>/dev/null)
            if [[ -n "$summary" ]]; then
                local grade=$(echo "$summary" | jq -r '.performance_grade // "N/A"')
                local success_rate=$(echo "$summary" | jq -r '.overall_success_rate // 0')
                print_info "Performance Grade: $grade"
                print_info "Success Rate: $(echo "$success_rate * 100" | bc -l 2>/dev/null || echo "$success_rate")%"
            fi
        fi
    fi
    
    if [[ -n "$latest_html" && "$GENERATE_HTML" == "true" ]]; then
        print_success "HTML report: $latest_html"
        
        # Try to open HTML report in browser (if not in CI mode)
        if [[ "$CI_MODE" == "false" ]] && command -v xdg-open &> /dev/null; then
            print_info "Opening HTML report in browser..."
            xdg-open "$latest_html" &> /dev/null &
        elif [[ "$CI_MODE" == "false" ]] && command -v open &> /dev/null; then
            print_info "Opening HTML report in browser..."
            open "$latest_html" &> /dev/null &
        fi
    fi
    
    print_info "All results saved to: $OUTPUT_DIR"
}

# Main execution
main() {
    echo "🚀 Local Development Performance Benchmark Runner"
    echo "=================================================="
    echo ""
    
    # Run checks
    check_prerequisites
    check_local_services
    setup_output_directory
    
    echo ""
    print_info "Configuration:"
    print_info "  Quick Mode: $QUICK_MODE"
    print_info "  Skip Resource Tests: $SKIP_RESOURCE_TESTS"
    print_info "  CI Mode: $CI_MODE"
    print_info "  Generate HTML: $GENERATE_HTML"
    print_info "  Output Directory: $OUTPUT_DIR"
    echo ""
    
    # Run benchmarks
    local start_time=$(date +%s)
    
    if run_benchmarks; then
        local end_time=$(date +%s)
        local duration=$((end_time - start_time))
        
        echo ""
        print_success "Benchmark execution completed in ${duration} seconds"
        show_results
        
        if [[ "$CI_MODE" == "true" ]]; then
            exit 0
        fi
    else
        local exit_code=$?
        local end_time=$(date +%s)
        local duration=$((end_time - start_time))
        
        echo ""
        print_error "Benchmark execution failed after ${duration} seconds"
        
        if [[ "$CI_MODE" == "true" ]]; then
            exit $exit_code
        else
            print_info "Check the output above for error details"
            exit $exit_code
        fi
    fi
}

# Run main function
main "$@"