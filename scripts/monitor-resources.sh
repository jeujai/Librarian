#!/bin/bash

# =============================================================================
# Resource Monitoring Script for Local Development
# =============================================================================
# This script monitors system and container resource usage

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
COMPOSE_FILE="docker-compose.local.yml"
REFRESH_INTERVAL=5
WATCH_MODE=false
OUTPUT_FILE=""

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

# Function to format bytes to human readable
bytes_to_human() {
    local bytes="$1"
    if [ "$bytes" -lt 1024 ]; then
        echo "${bytes}B"
    elif [ "$bytes" -lt $((1024 * 1024)) ]; then
        echo "$((bytes / 1024))KB"
    elif [ "$bytes" -lt $((1024 * 1024 * 1024)) ]; then
        echo "$((bytes / 1024 / 1024))MB"
    else
        echo "$((bytes / 1024 / 1024 / 1024))GB"
    fi
}

# Function to get container resource usage
get_container_stats() {
    local format="table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}\t{{.NetIO}}\t{{.BlockIO}}"
    
    # Get stats for our containers only
    local container_ids=$(docker-compose -f "$COMPOSE_FILE" ps -q 2>/dev/null | tr '\n' ' ')
    
    if [ -n "$container_ids" ]; then
        docker stats --no-stream --format "$format" $container_ids 2>/dev/null | grep -v "^NAME"
    else
        echo "No containers running"
    fi
}

# Function to get system resource usage
get_system_stats() {
    echo "System Resources:"
    echo "=================="
    
    # CPU usage (if available)
    if command -v top >/dev/null 2>&1; then
        local cpu_usage=$(top -l 1 -n 0 | grep "CPU usage" | awk '{print $3}' | sed 's/%//' 2>/dev/null || echo "N/A")
        if [ "$cpu_usage" != "N/A" ]; then
            printf "%-15s %s\n" "CPU Usage:" "${cpu_usage}%"
        fi
    fi
    
    # Memory usage
    if command -v free >/dev/null 2>&1; then
        # Linux
        local mem_info=$(free -h | grep "Mem:")
        local mem_total=$(echo "$mem_info" | awk '{print $2}')
        local mem_used=$(echo "$mem_info" | awk '{print $3}')
        local mem_percent=$(free | grep Mem | awk '{printf "%.1f", $3/$2 * 100.0}')
        
        printf "%-15s %s / %s (%s%%)\n" "Memory:" "$mem_used" "$mem_total" "$mem_percent"
    elif command -v vm_stat >/dev/null 2>&1; then
        # macOS
        local page_size=4096
        local pages_free=$(vm_stat | grep "Pages free" | awk '{print $3}' | sed 's/\.//')
        local pages_active=$(vm_stat | grep "Pages active" | awk '{print $3}' | sed 's/\.//')
        local pages_inactive=$(vm_stat | grep "Pages inactive" | awk '{print $3}' | sed 's/\.//')
        local pages_wired=$(vm_stat | grep "Pages wired down" | awk '{print $4}' | sed 's/\.//')
        
        local mem_free=$((pages_free * page_size))
        local mem_used=$(((pages_active + pages_inactive + pages_wired) * page_size))
        local mem_total=$((mem_free + mem_used))
        local mem_percent=$(echo "scale=1; $mem_used * 100 / $mem_total" | bc -l 2>/dev/null || echo "0")
        
        printf "%-15s %s / %s (%s%%)\n" "Memory:" "$(bytes_to_human $mem_used)" "$(bytes_to_human $mem_total)" "$mem_percent"
    fi
    
    # Disk usage
    local disk_info=$(df -h . | tail -1)
    local disk_used=$(echo "$disk_info" | awk '{print $3}')
    local disk_total=$(echo "$disk_info" | awk '{print $2}')
    local disk_percent=$(echo "$disk_info" | awk '{print $5}')
    
    printf "%-15s %s / %s (%s)\n" "Disk Usage:" "$disk_used" "$disk_total" "$disk_percent"
    
    # Load average (if available)
    if command -v uptime >/dev/null 2>&1; then
        local load_avg=$(uptime | awk -F'load average:' '{print $2}' | sed 's/^ *//')
        printf "%-15s %s\n" "Load Average:" "$load_avg"
    fi
}

# Function to get Docker system info
get_docker_stats() {
    echo ""
    echo "Docker System:"
    echo "=============="
    
    # Docker system info
    if docker system df >/dev/null 2>&1; then
        docker system df
    else
        print_warning "Docker system df not available"
    fi
    
    echo ""
    
    # Container count
    local running_containers=$(docker ps -q | wc -l)
    local total_containers=$(docker ps -a -q | wc -l)
    printf "%-20s %d running, %d total\n" "Containers:" "$running_containers" "$total_containers"
    
    # Image count
    local image_count=$(docker images -q | wc -l)
    printf "%-20s %d\n" "Images:" "$image_count"
    
    # Volume count
    local volume_count=$(docker volume ls -q | wc -l)
    printf "%-20s %d\n" "Volumes:" "$volume_count"
}

# Function to get service-specific stats
get_service_stats() {
    echo ""
    echo "Service Details:"
    echo "================"
    
    # Application service
    if docker-compose -f "$COMPOSE_FILE" ps multimodal-librarian | grep -q "Up"; then
        echo ""
        echo "Application Service:"
        echo "-------------------"
        
        # Get container ID
        local app_container=$(docker-compose -f "$COMPOSE_FILE" ps -q multimodal-librarian)
        
        if [ -n "$app_container" ]; then
            # Get detailed stats
            local stats=$(docker stats --no-stream --format "{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}\t{{.BlockIO}}" "$app_container")
            local cpu=$(echo "$stats" | cut -f1)
            local mem=$(echo "$stats" | cut -f2)
            local net=$(echo "$stats" | cut -f3)
            local block=$(echo "$stats" | cut -f4)
            
            printf "  %-15s %s\n" "CPU:" "$cpu"
            printf "  %-15s %s\n" "Memory:" "$mem"
            printf "  %-15s %s\n" "Network I/O:" "$net"
            printf "  %-15s %s\n" "Block I/O:" "$block"
            
            # Check if health endpoint is accessible
            if curl -s -f "http://localhost:8000/health/simple" >/dev/null 2>&1; then
                printf "  %-15s %s\n" "Health:" "✓ Healthy"
            else
                printf "  %-15s %s\n" "Health:" "✗ Unhealthy"
            fi
        fi
    else
        echo "Application service is not running"
    fi
    
    # Database services
    echo ""
    echo "Database Services:"
    echo "-----------------"
    
    for service in postgres neo4j milvus redis; do
        if docker-compose -f "$COMPOSE_FILE" ps "$service" | grep -q "Up"; then
            local container=$(docker-compose -f "$COMPOSE_FILE" ps -q "$service")
            if [ -n "$container" ]; then
                local stats=$(docker stats --no-stream --format "{{.CPUPerc}}\t{{.MemUsage}}" "$container")
                local cpu=$(echo "$stats" | cut -f1)
                local mem=$(echo "$stats" | cut -f2)
                
                printf "  %-10s CPU: %s, Memory: %s\n" "$service" "$cpu" "$mem"
            fi
        else
            printf "  %-10s %s\n" "$service" "Not running"
        fi
    done
}

# Function to check resource alerts
check_resource_alerts() {
    echo ""
    echo "Resource Alerts:"
    echo "==============="
    
    local alerts=0
    
    # Check disk usage
    local disk_usage=$(df . | tail -1 | awk '{print $5}' | sed 's/%//')
    if [ "$disk_usage" -gt 90 ]; then
        print_error "Disk usage is at ${disk_usage}% (critical)"
        alerts=$((alerts + 1))
    elif [ "$disk_usage" -gt 80 ]; then
        print_warning "Disk usage is at ${disk_usage}% (warning)"
        alerts=$((alerts + 1))
    fi
    
    # Check memory usage (if available)
    if command -v free >/dev/null 2>&1; then
        local mem_usage=$(free | grep Mem | awk '{printf "%.0f", $3/$2 * 100.0}')
        if [ "$mem_usage" -gt 90 ]; then
            print_error "Memory usage is at ${mem_usage}% (critical)"
            alerts=$((alerts + 1))
        elif [ "$mem_usage" -gt 80 ]; then
            print_warning "Memory usage is at ${mem_usage}% (warning)"
            alerts=$((alerts + 1))
        fi
    fi
    
    # Check for failed containers
    local failed_containers=$(docker-compose -f "$COMPOSE_FILE" ps | grep -c "Exit\|Restarting" || echo "0")
    if [ "$failed_containers" -gt 0 ]; then
        print_error "$failed_containers containers are not running properly"
        alerts=$((alerts + 1))
    fi
    
    # Check Docker daemon
    if ! docker info >/dev/null 2>&1; then
        print_error "Docker daemon is not accessible"
        alerts=$((alerts + 1))
    fi
    
    if [ "$alerts" -eq 0 ]; then
        print_success "No resource alerts"
    else
        print_warning "Found $alerts resource alerts"
    fi
    
    return $alerts
}

# Function to display monitoring dashboard
show_dashboard() {
    # Clear screen if in watch mode
    if [ "$WATCH_MODE" = true ]; then
        clear
    fi
    
    echo "============================================================================="
    echo "MULTIMODAL LIBRARIAN - RESOURCE MONITORING"
    echo "============================================================================="
    echo "Timestamp: $(date)"
    if [ "$WATCH_MODE" = true ]; then
        echo "Refresh: ${REFRESH_INTERVAL}s (Press Ctrl+C to exit)"
    fi
    echo ""
    
    # System stats
    get_system_stats
    
    # Container stats
    echo ""
    echo "Container Resources:"
    echo "==================="
    get_container_stats
    
    # Service-specific stats
    get_service_stats
    
    # Docker system stats
    get_docker_stats
    
    # Resource alerts
    check_resource_alerts
    
    echo ""
    echo "============================================================================="
    
    # Save to file if specified
    if [ -n "$OUTPUT_FILE" ]; then
        {
            echo "Timestamp: $(date)"
            echo ""
            get_system_stats
            echo ""
            echo "Container Resources:"
            get_container_stats
            echo ""
            check_resource_alerts
        } >> "$OUTPUT_FILE"
    fi
}

# Function to show help
show_help() {
    echo "Resource Monitoring Script for Local Development"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --watch, -w         Watch mode - refresh every N seconds"
    echo "  --interval SECONDS  Refresh interval for watch mode (default: 5)"
    echo "  --output FILE       Save monitoring data to file"
    echo "  --containers        Show only container stats"
    echo "  --system            Show only system stats"
    echo "  --alerts            Show only resource alerts"
    echo "  --help, -h          Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0                          # Show current resource usage"
    echo "  $0 --watch                  # Watch mode with 5s refresh"
    echo "  $0 --watch --interval 10    # Watch mode with 10s refresh"
    echo "  $0 --output monitor.log     # Save data to file"
    echo "  $0 --containers             # Show only container stats"
    echo "  $0 --alerts                 # Check resource alerts only"
    echo ""
    echo "Watch mode controls:"
    echo "  Ctrl+C              Exit watch mode"
    echo "  q                   Quit (in some terminals)"
}

# Main execution
main() {
    local mode="dashboard"
    
    # Parse command line arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --watch|-w)
                WATCH_MODE=true
                shift
                ;;
            --interval)
                REFRESH_INTERVAL="$2"
                shift 2
                ;;
            --output)
                OUTPUT_FILE="$2"
                shift 2
                ;;
            --containers)
                mode="containers"
                shift
                ;;
            --system)
                mode="system"
                shift
                ;;
            --alerts)
                mode="alerts"
                shift
                ;;
            --help|-h)
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
    
    # Validate refresh interval
    if ! [[ "$REFRESH_INTERVAL" =~ ^[0-9]+$ ]] || [ "$REFRESH_INTERVAL" -lt 1 ]; then
        print_error "Invalid refresh interval: $REFRESH_INTERVAL"
        exit 1
    fi
    
    # Create output file if specified
    if [ -n "$OUTPUT_FILE" ]; then
        touch "$OUTPUT_FILE" || {
            print_error "Cannot create output file: $OUTPUT_FILE"
            exit 1
        }
        print_info "Saving monitoring data to: $OUTPUT_FILE"
    fi
    
    # Run monitoring based on mode
    if [ "$WATCH_MODE" = true ]; then
        # Watch mode - continuous monitoring
        trap 'echo ""; print_info "Monitoring stopped"; exit 0' INT TERM
        
        while true; do
            case "$mode" in
                "dashboard")
                    show_dashboard
                    ;;
                "containers")
                    clear
                    echo "Container Resources ($(date)):"
                    echo "=============================="
                    get_container_stats
                    ;;
                "system")
                    clear
                    echo "System Resources ($(date)):"
                    echo "=========================="
                    get_system_stats
                    ;;
                "alerts")
                    clear
                    echo "Resource Alerts ($(date)):"
                    echo "========================"
                    check_resource_alerts
                    ;;
            esac
            
            sleep "$REFRESH_INTERVAL"
        done
    else
        # Single run mode
        case "$mode" in
            "dashboard")
                show_dashboard
                ;;
            "containers")
                echo "Container Resources:"
                echo "==================="
                get_container_stats
                ;;
            "system")
                get_system_stats
                ;;
            "alerts")
                check_resource_alerts
                exit $?
                ;;
        esac
    fi
}

# Run main function with all arguments
main "$@"