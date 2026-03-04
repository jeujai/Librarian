#!/bin/bash

# =============================================================================
# Log Analysis Script for Local Development
# =============================================================================
# This script analyzes logs from all services and provides insights

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
COMPOSE_FILE="docker-compose.local.yml"
TIME_RANGE="${1:-1h}"  # Default to last hour

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

# Function to print section header
print_section() {
    echo ""
    echo "============================================================================="
    echo "$1"
    echo "============================================================================="
}

# Function to analyze application logs
analyze_application_logs() {
    print_section "APPLICATION LOG ANALYSIS"
    
    print_info "Analyzing application logs for the last $TIME_RANGE..."
    
    # Check if application is running
    if ! docker-compose -f "$COMPOSE_FILE" ps multimodal-librarian | grep -q "Up"; then
        print_warning "Application container is not running"
        return
    fi
    
    # Get log count by level
    echo ""
    echo "Log Level Distribution:"
    echo "----------------------"
    
    local logs=$(docker-compose -f "$COMPOSE_FILE" logs --since="$TIME_RANGE" multimodal-librarian 2>/dev/null || echo "")
    
    if [ -z "$logs" ]; then
        print_warning "No application logs found for the specified time range"
        return
    fi
    
    # Count different log levels
    local debug_count=$(echo "$logs" | grep -c '"level":"DEBUG"' 2>/dev/null || echo "0")
    local info_count=$(echo "$logs" | grep -c '"level":"INFO"' 2>/dev/null || echo "0")
    local warning_count=$(echo "$logs" | grep -c '"level":"WARNING"' 2>/dev/null || echo "0")
    local error_count=$(echo "$logs" | grep -c '"level":"ERROR"' 2>/dev/null || echo "0")
    local critical_count=$(echo "$logs" | grep -c '"level":"CRITICAL"' 2>/dev/null || echo "0")
    
    printf "DEBUG:    %6d\n" "$debug_count"
    printf "INFO:     %6d\n" "$info_count"
    printf "WARNING:  %6d\n" "$warning_count"
    printf "ERROR:    %6d\n" "$error_count"
    printf "CRITICAL: %6d\n" "$critical_count"
    
    # Show recent errors if any
    if [ "$error_count" -gt 0 ] || [ "$critical_count" -gt 0 ]; then
        echo ""
        echo "Recent Errors:"
        echo "--------------"
        echo "$logs" | grep -E '"level":"(ERROR|CRITICAL)"' | tail -5 | while read -r line; do
            # Extract timestamp and message
            local timestamp=$(echo "$line" | grep -o '"timestamp":"[^"]*"' | cut -d'"' -f4)
            local level=$(echo "$line" | grep -o '"level":"[^"]*"' | cut -d'"' -f4)
            local message=$(echo "$line" | grep -o '"message":"[^"]*"' | cut -d'"' -f4)
            
            if [ "$level" = "ERROR" ]; then
                echo -e "${RED}[$timestamp] $level: $message${NC}"
            else
                echo -e "${RED}[$timestamp] $level: $message${NC}"
            fi
        done
    else
        print_success "No errors found in the specified time range"
    fi
    
    # API endpoint analysis
    echo ""
    echo "API Endpoint Activity:"
    echo "---------------------"
    
    local api_logs=$(echo "$logs" | grep -E '"endpoint":"[^"]*"' 2>/dev/null || echo "")
    if [ -n "$api_logs" ]; then
        echo "$api_logs" | grep -o '"endpoint":"[^"]*"' | sort | uniq -c | sort -nr | head -10 | while read -r count endpoint; do
            local clean_endpoint=$(echo "$endpoint" | cut -d'"' -f4)
            printf "%6d  %s\n" "$count" "$clean_endpoint"
        done
    else
        print_warning "No API endpoint logs found"
    fi
    
    # Performance analysis
    echo ""
    echo "Performance Metrics:"
    echo "-------------------"
    
    local slow_operations=$(echo "$logs" | grep '"duration_ms":[0-9]*' | grep -E '"duration_ms":[0-9]{4,}' | wc -l)
    printf "Slow operations (>1000ms): %d\n" "$slow_operations"
    
    if [ "$slow_operations" -gt 0 ]; then
        echo ""
        echo "Slowest Operations:"
        echo "$logs" | grep '"duration_ms":[0-9]*' | grep -o '"duration_ms":[0-9]*' | sort -t: -k2 -nr | head -5 | while read -r duration; do
            local ms=$(echo "$duration" | cut -d: -f2)
            printf "  %6d ms\n" "$ms"
        done
    fi
}

# Function to analyze database logs
analyze_database_logs() {
    print_section "DATABASE LOG ANALYSIS"
    
    # PostgreSQL analysis
    print_info "Analyzing PostgreSQL logs..."
    
    if docker-compose -f "$COMPOSE_FILE" ps postgres | grep -q "Up"; then
        local pg_logs=$(docker-compose -f "$COMPOSE_FILE" logs --since="$TIME_RANGE" postgres 2>/dev/null || echo "")
        
        local pg_errors=$(echo "$pg_logs" | grep -i -c "error\|fatal" 2>/dev/null || echo "0")
        local pg_connections=$(echo "$pg_logs" | grep -c "connection" 2>/dev/null || echo "0")
        
        printf "PostgreSQL errors:     %6d\n" "$pg_errors"
        printf "Connection events:     %6d\n" "$pg_connections"
        
        if [ "$pg_errors" -gt 0 ]; then
            echo ""
            echo "Recent PostgreSQL Errors:"
            echo "$pg_logs" | grep -i "error\|fatal" | tail -3
        fi
    else
        print_warning "PostgreSQL container is not running"
    fi
    
    echo ""
    
    # Neo4j analysis
    print_info "Analyzing Neo4j logs..."
    
    if docker-compose -f "$COMPOSE_FILE" ps neo4j | grep -q "Up"; then
        local neo4j_logs=$(docker-compose -f "$COMPOSE_FILE" logs --since="$TIME_RANGE" neo4j 2>/dev/null || echo "")
        
        local neo4j_errors=$(echo "$neo4j_logs" | grep -i -c "error\|exception" 2>/dev/null || echo "0")
        local neo4j_queries=$(echo "$neo4j_logs" | grep -c "query" 2>/dev/null || echo "0")
        
        printf "Neo4j errors:          %6d\n" "$neo4j_errors"
        printf "Query events:          %6d\n" "$neo4j_queries"
        
        if [ "$neo4j_errors" -gt 0 ]; then
            echo ""
            echo "Recent Neo4j Errors:"
            echo "$neo4j_logs" | grep -i "error\|exception" | tail -3
        fi
    else
        print_warning "Neo4j container is not running"
    fi
    
    echo ""
    
    # Milvus analysis
    print_info "Analyzing Milvus logs..."
    
    if docker-compose -f "$COMPOSE_FILE" ps milvus | grep -q "Up"; then
        local milvus_logs=$(docker-compose -f "$COMPOSE_FILE" logs --since="$TIME_RANGE" milvus 2>/dev/null || echo "")
        
        local milvus_errors=$(echo "$milvus_logs" | grep -i -c "error\|exception" 2>/dev/null || echo "0")
        local milvus_searches=$(echo "$milvus_logs" | grep -c "search" 2>/dev/null || echo "0")
        
        printf "Milvus errors:         %6d\n" "$milvus_errors"
        printf "Search events:         %6d\n" "$milvus_searches"
        
        if [ "$milvus_errors" -gt 0 ]; then
            echo ""
            echo "Recent Milvus Errors:"
            echo "$milvus_logs" | grep -i "error\|exception" | tail -3
        fi
    else
        print_warning "Milvus container is not running"
    fi
}

# Function to analyze system health
analyze_system_health() {
    print_section "SYSTEM HEALTH ANALYSIS"
    
    print_info "Checking service status..."
    
    # Check running services
    local services=("multimodal-librarian" "postgres" "neo4j" "milvus" "redis" "etcd" "minio")
    
    echo ""
    echo "Service Status:"
    echo "---------------"
    
    for service in "${services[@]}"; do
        if docker-compose -f "$COMPOSE_FILE" ps "$service" | grep -q "Up"; then
            printf "%-20s %s\n" "$service" "$(print_success "Running")"
        else
            printf "%-20s %s\n" "$service" "$(print_error "Stopped")"
        fi
    done
    
    # Check resource usage
    echo ""
    echo "Resource Usage:"
    echo "---------------"
    
    # Get container stats (if available)
    if command -v docker >/dev/null 2>&1; then
        local stats=$(docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" 2>/dev/null | grep -E "(multimodal|postgres|neo4j|milvus|redis)" || echo "")
        
        if [ -n "$stats" ]; then
            echo "$stats"
        else
            print_warning "Could not retrieve resource usage statistics"
        fi
    fi
}

# Function to generate summary
generate_summary() {
    print_section "SUMMARY AND RECOMMENDATIONS"
    
    # Count total errors across all services
    local total_errors=0
    
    # Application errors
    if docker-compose -f "$COMPOSE_FILE" ps multimodal-librarian | grep -q "Up"; then
        local app_errors=$(docker-compose -f "$COMPOSE_FILE" logs --since="$TIME_RANGE" multimodal-librarian 2>/dev/null | grep -c '"level":"ERROR"' 2>/dev/null || echo "0")
        total_errors=$((total_errors + app_errors))
    fi
    
    # Database errors
    for service in postgres neo4j milvus; do
        if docker-compose -f "$COMPOSE_FILE" ps "$service" | grep -q "Up"; then
            local db_errors=$(docker-compose -f "$COMPOSE_FILE" logs --since="$TIME_RANGE" "$service" 2>/dev/null | grep -i -c "error\|fatal\|exception" 2>/dev/null || echo "0")
            total_errors=$((total_errors + db_errors))
        fi
    done
    
    echo ""
    if [ "$total_errors" -eq 0 ]; then
        print_success "System appears healthy - no errors found in the last $TIME_RANGE"
    elif [ "$total_errors" -lt 5 ]; then
        print_warning "Found $total_errors errors in the last $TIME_RANGE - monitor closely"
    else
        print_error "Found $total_errors errors in the last $TIME_RANGE - investigation recommended"
    fi
    
    echo ""
    echo "Recommendations:"
    echo "----------------"
    
    # Check if any services are down
    local down_services=()
    for service in multimodal-librarian postgres neo4j milvus redis; do
        if ! docker-compose -f "$COMPOSE_FILE" ps "$service" | grep -q "Up"; then
            down_services+=("$service")
        fi
    done
    
    if [ ${#down_services[@]} -gt 0 ]; then
        echo "• Start missing services: docker-compose -f $COMPOSE_FILE up -d ${down_services[*]}"
    fi
    
    if [ "$total_errors" -gt 0 ]; then
        echo "• Review error logs: docker-compose -f $COMPOSE_FILE logs [service-name]"
        echo "• Check service health: scripts/health-check.sh"
    fi
    
    echo "• Monitor logs in real-time: docker-compose -f $COMPOSE_FILE logs -f"
    echo "• View logs in browser: http://localhost:8080 (start with --profile monitoring)"
}

# Function to show help
show_help() {
    echo "Log Analysis Script for Local Development"
    echo ""
    echo "Usage: $0 [TIME_RANGE]"
    echo ""
    echo "TIME_RANGE: Time range for log analysis (default: 1h)"
    echo "  Examples: 30m, 2h, 1d, 24h"
    echo ""
    echo "Examples:"
    echo "  $0           # Analyze logs from last hour"
    echo "  $0 30m       # Analyze logs from last 30 minutes"
    echo "  $0 1d        # Analyze logs from last day"
    echo ""
    echo "The script analyzes:"
    echo "  • Application logs (errors, performance, API usage)"
    echo "  • Database logs (PostgreSQL, Neo4j, Milvus)"
    echo "  • System health and resource usage"
    echo "  • Provides recommendations for issues found"
}

# Main execution
main() {
    case "${1:-}" in
        --help|-h|help)
            show_help
            exit 0
            ;;
    esac
    
    echo "============================================================================="
    echo "MULTIMODAL LIBRARIAN - LOG ANALYSIS REPORT"
    echo "============================================================================="
    echo "Time Range: $TIME_RANGE"
    echo "Generated: $(date)"
    
    analyze_application_logs
    analyze_database_logs
    analyze_system_health
    generate_summary
    
    echo ""
    echo "============================================================================="
    echo "ANALYSIS COMPLETE"
    echo "============================================================================="
}

# Run main function
main "$@"