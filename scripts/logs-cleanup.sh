#!/bin/bash

# =============================================================================
# Log Cleanup Script for Local Development
# =============================================================================
# This script manages log cleanup, rotation, and archival for the local
# development environment

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
COMPOSE_FILE="docker-compose.local.yml"
LOG_DIR="./logs"
RETENTION_DAYS="${LOG_RETENTION_DAYS:-30}"
COMPRESS_DAYS="${LOG_COMPRESS_DAYS:-7}"
ARCHIVE_DAYS="${LOG_ARCHIVE_DAYS:-90}"
MAX_LOG_SIZE="${MAX_LOG_SIZE:-100M}"

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
    echo "Log Cleanup Script for Local Development"
    echo ""
    echo "Usage: $0 [OPTIONS] [COMMAND]"
    echo ""
    echo "Commands:"
    echo "  cleanup     - Clean up old logs (default)"
    echo "  compress    - Compress old logs"
    echo "  archive     - Archive very old logs"
    echo "  rotate      - Rotate current logs"
    echo "  status      - Show log directory status"
    echo "  purge       - Remove all logs (dangerous!)"
    echo ""
    echo "Options:"
    echo "  --retention-days DAYS    - Keep logs for DAYS days (default: $RETENTION_DAYS)"
    echo "  --compress-days DAYS     - Compress logs older than DAYS (default: $COMPRESS_DAYS)"
    echo "  --archive-days DAYS      - Archive logs older than DAYS (default: $ARCHIVE_DAYS)"
    echo "  --max-size SIZE          - Maximum log file size before rotation (default: $MAX_LOG_SIZE)"
    echo "  --dry-run               - Show what would be done without doing it"
    echo "  --verbose               - Show detailed output"
    echo "  --help                  - Show this help"
    echo ""
    echo "Environment Variables:"
    echo "  LOG_RETENTION_DAYS      - Default retention period"
    echo "  LOG_COMPRESS_DAYS       - Default compression period"
    echo "  LOG_ARCHIVE_DAYS        - Default archive period"
    echo "  MAX_LOG_SIZE            - Default maximum log size"
    echo ""
    echo "Examples:"
    echo "  $0                      # Clean up logs with default settings"
    echo "  $0 --retention-days 14  # Keep logs for 14 days"
    echo "  $0 compress             # Compress old logs"
    echo "  $0 status               # Show log directory status"
    echo "  $0 --dry-run cleanup    # Preview cleanup without doing it"
}

# Function to get log directory status
get_log_status() {
    local total_size=0
    local file_count=0
    local compressed_count=0
    local old_count=0
    
    if [ -d "$LOG_DIR" ]; then
        # Count files and calculate sizes
        while IFS= read -r -d '' file; do
            if [ -f "$file" ]; then
                file_count=$((file_count + 1))
                size=$(stat -f%z "$file" 2>/dev/null || stat -c%s "$file" 2>/dev/null || echo 0)
                total_size=$((total_size + size))
                
                if [[ "$file" == *.gz ]]; then
                    compressed_count=$((compressed_count + 1))
                fi
                
                # Check if file is older than retention period
                if [ -n "$(find "$file" -mtime +$RETENTION_DAYS 2>/dev/null)" ]; then
                    old_count=$((old_count + 1))
                fi
            fi
        done < <(find "$LOG_DIR" -type f -print0 2>/dev/null)
    fi
    
    # Convert size to human readable
    local human_size
    if [ $total_size -gt 1073741824 ]; then
        human_size=$(echo "scale=1; $total_size / 1073741824" | bc)GB
    elif [ $total_size -gt 1048576 ]; then
        human_size=$(echo "scale=1; $total_size / 1048576" | bc)MB
    elif [ $total_size -gt 1024 ]; then
        human_size=$(echo "scale=1; $total_size / 1024" | bc)KB
    else
        human_size="${total_size}B"
    fi
    
    echo "total_size:$total_size"
    echo "human_size:$human_size"
    echo "file_count:$file_count"
    echo "compressed_count:$compressed_count"
    echo "old_count:$old_count"
}

# Function to show log directory status
show_status() {
    print_info "Log Directory Status"
    echo "===================="
    
    if [ ! -d "$LOG_DIR" ]; then
        print_warning "Log directory does not exist: $LOG_DIR"
        return
    fi
    
    local status_info
    status_info=$(get_log_status)
    
    local total_size=$(echo "$status_info" | grep "total_size:" | cut -d: -f2)
    local human_size=$(echo "$status_info" | grep "human_size:" | cut -d: -f2)
    local file_count=$(echo "$status_info" | grep "file_count:" | cut -d: -f2)
    local compressed_count=$(echo "$status_info" | grep "compressed_count:" | cut -d: -f2)
    local old_count=$(echo "$status_info" | grep "old_count:" | cut -d: -f2)
    
    echo "Directory: $LOG_DIR"
    echo "Total Size: $human_size"
    echo "Total Files: $file_count"
    echo "Compressed Files: $compressed_count"
    echo "Files older than $RETENTION_DAYS days: $old_count"
    echo ""
    
    # Show largest files
    echo "Largest Log Files:"
    echo "------------------"
    if command -v du >/dev/null 2>&1; then
        find "$LOG_DIR" -type f -name "*.log" -o -name "*.log.*" | \
        xargs du -h 2>/dev/null | \
        sort -hr | \
        head -10 | \
        while read -r size file; do
            echo "  $size  $file"
        done
    fi
    
    echo ""
    
    # Show recent activity
    echo "Recent Log Activity:"
    echo "-------------------"
    find "$LOG_DIR" -type f -mtime -1 2>/dev/null | \
    head -10 | \
    while read -r file; do
        if [ -f "$file" ]; then
            local mod_time
            mod_time=$(stat -f%Sm -t%Y-%m-%d\ %H:%M "$file" 2>/dev/null || stat -c%y "$file" 2>/dev/null | cut -d. -f1)
            echo "  $mod_time  $file"
        fi
    done
}

# Function to clean up old logs
cleanup_logs() {
    local dry_run=$1
    local verbose=$2
    
    print_info "Cleaning up logs older than $RETENTION_DAYS days..."
    
    if [ ! -d "$LOG_DIR" ]; then
        print_warning "Log directory does not exist: $LOG_DIR"
        return
    fi
    
    local files_to_delete
    files_to_delete=$(find "$LOG_DIR" -type f \( -name "*.log" -o -name "*.log.*" \) -mtime +$RETENTION_DAYS 2>/dev/null)
    
    if [ -z "$files_to_delete" ]; then
        print_success "No old log files found to clean up"
        return
    fi
    
    local file_count
    file_count=$(echo "$files_to_delete" | wc -l)
    
    if [ "$dry_run" = "true" ]; then
        print_info "DRY RUN: Would delete $file_count files:"
        echo "$files_to_delete" | while read -r file; do
            if [ -n "$file" ]; then
                local size
                size=$(stat -f%z "$file" 2>/dev/null || stat -c%s "$file" 2>/dev/null || echo 0)
                local human_size
                if [ $size -gt 1048576 ]; then
                    human_size=$(echo "scale=1; $size / 1048576" | bc)MB
                else
                    human_size=$(echo "scale=1; $size / 1024" | bc)KB
                fi
                echo "  $human_size  $file"
            fi
        done
    else
        print_info "Deleting $file_count old log files..."
        
        local deleted_count=0
        local total_size=0
        
        echo "$files_to_delete" | while read -r file; do
            if [ -n "$file" ] && [ -f "$file" ]; then
                local size
                size=$(stat -f%z "$file" 2>/dev/null || stat -c%s "$file" 2>/dev/null || echo 0)
                
                if rm "$file" 2>/dev/null; then
                    deleted_count=$((deleted_count + 1))
                    total_size=$((total_size + size))
                    
                    if [ "$verbose" = "true" ]; then
                        print_info "Deleted: $file"
                    fi
                else
                    print_error "Failed to delete: $file"
                fi
            fi
        done
        
        # Convert total size to human readable
        local human_total
        if [ $total_size -gt 1073741824 ]; then
            human_total=$(echo "scale=1; $total_size / 1073741824" | bc)GB
        elif [ $total_size -gt 1048576 ]; then
            human_total=$(echo "scale=1; $total_size / 1048576" | bc)MB
        else
            human_total=$(echo "scale=1; $total_size / 1024" | bc)KB
        fi
        
        print_success "Deleted $deleted_count files, freed $human_total"
    fi
}

# Function to compress old logs
compress_logs() {
    local dry_run=$1
    local verbose=$2
    
    print_info "Compressing logs older than $COMPRESS_DAYS days..."
    
    if [ ! -d "$LOG_DIR" ]; then
        print_warning "Log directory does not exist: $LOG_DIR"
        return
    fi
    
    local files_to_compress
    files_to_compress=$(find "$LOG_DIR" -type f -name "*.log" -mtime +$COMPRESS_DAYS ! -name "*.gz" 2>/dev/null)
    
    if [ -z "$files_to_compress" ]; then
        print_success "No log files found to compress"
        return
    fi
    
    local file_count
    file_count=$(echo "$files_to_compress" | wc -l)
    
    if [ "$dry_run" = "true" ]; then
        print_info "DRY RUN: Would compress $file_count files:"
        echo "$files_to_compress" | while read -r file; do
            if [ -n "$file" ]; then
                local size
                size=$(stat -f%z "$file" 2>/dev/null || stat -c%s "$file" 2>/dev/null || echo 0)
                local human_size
                if [ $size -gt 1048576 ]; then
                    human_size=$(echo "scale=1; $size / 1048576" | bc)MB
                else
                    human_size=$(echo "scale=1; $size / 1024" | bc)KB
                fi
                echo "  $human_size  $file"
            fi
        done
    else
        print_info "Compressing $file_count log files..."
        
        local compressed_count=0
        local total_saved=0
        
        echo "$files_to_compress" | while read -r file; do
            if [ -n "$file" ] && [ -f "$file" ]; then
                local original_size
                original_size=$(stat -f%z "$file" 2>/dev/null || stat -c%s "$file" 2>/dev/null || echo 0)
                
                if gzip "$file" 2>/dev/null; then
                    local compressed_size
                    compressed_size=$(stat -f%z "$file.gz" 2>/dev/null || stat -c%s "$file.gz" 2>/dev/null || echo 0)
                    local saved=$((original_size - compressed_size))
                    
                    compressed_count=$((compressed_count + 1))
                    total_saved=$((total_saved + saved))
                    
                    if [ "$verbose" = "true" ]; then
                        local saved_percent
                        if [ $original_size -gt 0 ]; then
                            saved_percent=$(echo "scale=1; $saved * 100 / $original_size" | bc)
                        else
                            saved_percent=0
                        fi
                        print_info "Compressed: $file (saved ${saved_percent}%)"
                    fi
                else
                    print_error "Failed to compress: $file"
                fi
            fi
        done
        
        # Convert total saved to human readable
        local human_saved
        if [ $total_saved -gt 1073741824 ]; then
            human_saved=$(echo "scale=1; $total_saved / 1073741824" | bc)GB
        elif [ $total_saved -gt 1048576 ]; then
            human_saved=$(echo "scale=1; $total_saved / 1048576" | bc)MB
        else
            human_saved=$(echo "scale=1; $total_saved / 1024" | bc)KB
        fi
        
        print_success "Compressed $compressed_count files, saved $human_saved"
    fi
}

# Function to archive very old logs
archive_logs() {
    local dry_run=$1
    local verbose=$2
    
    print_info "Archiving logs older than $ARCHIVE_DAYS days..."
    
    if [ ! -d "$LOG_DIR" ]; then
        print_warning "Log directory does not exist: $LOG_DIR"
        return
    fi
    
    # Create archive directory
    local archive_dir="$LOG_DIR/archive"
    local archive_date
    archive_date=$(date +%Y%m%d)
    local archive_file="$archive_dir/logs-archive-$archive_date.tar.gz"
    
    local files_to_archive
    files_to_archive=$(find "$LOG_DIR" -type f \( -name "*.log" -o -name "*.log.*" \) -mtime +$ARCHIVE_DAYS ! -path "$archive_dir/*" 2>/dev/null)
    
    if [ -z "$files_to_archive" ]; then
        print_success "No log files found to archive"
        return
    fi
    
    local file_count
    file_count=$(echo "$files_to_archive" | wc -l)
    
    if [ "$dry_run" = "true" ]; then
        print_info "DRY RUN: Would archive $file_count files to $archive_file"
        echo "$files_to_archive" | head -10 | while read -r file; do
            if [ -n "$file" ]; then
                echo "  $file"
            fi
        done
        if [ $file_count -gt 10 ]; then
            echo "  ... and $((file_count - 10)) more files"
        fi
    else
        print_info "Archiving $file_count files to $archive_file..."
        
        # Create archive directory if it doesn't exist
        mkdir -p "$archive_dir"
        
        # Create archive
        if echo "$files_to_archive" | tar -czf "$archive_file" -T - 2>/dev/null; then
            # Remove archived files
            local removed_count=0
            echo "$files_to_archive" | while read -r file; do
                if [ -n "$file" ] && [ -f "$file" ]; then
                    if rm "$file" 2>/dev/null; then
                        removed_count=$((removed_count + 1))
                        if [ "$verbose" = "true" ]; then
                            print_info "Archived and removed: $file"
                        fi
                    fi
                fi
            done
            
            local archive_size
            archive_size=$(stat -f%z "$archive_file" 2>/dev/null || stat -c%s "$archive_file" 2>/dev/null || echo 0)
            local human_archive_size
            if [ $archive_size -gt 1048576 ]; then
                human_archive_size=$(echo "scale=1; $archive_size / 1048576" | bc)MB
            else
                human_archive_size=$(echo "scale=1; $archive_size / 1024" | bc)KB
            fi
            
            print_success "Archived $file_count files to $archive_file ($human_archive_size)"
        else
            print_error "Failed to create archive: $archive_file"
        fi
    fi
}

# Function to rotate current logs
rotate_logs() {
    local dry_run=$1
    local verbose=$2
    
    print_info "Rotating large log files (larger than $MAX_LOG_SIZE)..."
    
    if [ ! -d "$LOG_DIR" ]; then
        print_warning "Log directory does not exist: $LOG_DIR"
        return
    fi
    
    # Convert MAX_LOG_SIZE to bytes for comparison
    local max_bytes
    case "$MAX_LOG_SIZE" in
        *G|*GB) max_bytes=$(echo "$MAX_LOG_SIZE" | sed 's/[^0-9]//g'); max_bytes=$((max_bytes * 1073741824)) ;;
        *M|*MB) max_bytes=$(echo "$MAX_LOG_SIZE" | sed 's/[^0-9]//g'); max_bytes=$((max_bytes * 1048576)) ;;
        *K|*KB) max_bytes=$(echo "$MAX_LOG_SIZE" | sed 's/[^0-9]//g'); max_bytes=$((max_bytes * 1024)) ;;
        *) max_bytes=$(echo "$MAX_LOG_SIZE" | sed 's/[^0-9]//g') ;;
    esac
    
    local files_to_rotate
    files_to_rotate=$(find "$LOG_DIR" -type f -name "*.log" ! -name "*.gz" 2>/dev/null)
    
    local rotated_count=0
    
    if [ -n "$files_to_rotate" ]; then
        echo "$files_to_rotate" | while read -r file; do
            if [ -n "$file" ] && [ -f "$file" ]; then
                local file_size
                file_size=$(stat -f%z "$file" 2>/dev/null || stat -c%s "$file" 2>/dev/null || echo 0)
                
                if [ $file_size -gt $max_bytes ]; then
                    local timestamp
                    timestamp=$(date +%Y%m%d_%H%M%S)
                    local rotated_file="${file}.${timestamp}"
                    
                    if [ "$dry_run" = "true" ]; then
                        local human_size
                        if [ $file_size -gt 1048576 ]; then
                            human_size=$(echo "scale=1; $file_size / 1048576" | bc)MB
                        else
                            human_size=$(echo "scale=1; $file_size / 1024" | bc)KB
                        fi
                        print_info "DRY RUN: Would rotate $file ($human_size) to $rotated_file"
                    else
                        if mv "$file" "$rotated_file" 2>/dev/null; then
                            # Create new empty log file
                            touch "$file"
                            
                            rotated_count=$((rotated_count + 1))
                            
                            if [ "$verbose" = "true" ]; then
                                local human_size
                                if [ $file_size -gt 1048576 ]; then
                                    human_size=$(echo "scale=1; $file_size / 1048576" | bc)MB
                                else
                                    human_size=$(echo "scale=1; $file_size / 1024" | bc)KB
                                fi
                                print_info "Rotated: $file ($human_size) to $rotated_file"
                            fi
                        else
                            print_error "Failed to rotate: $file"
                        fi
                    fi
                fi
            fi
        done
    fi
    
    if [ "$dry_run" != "true" ]; then
        if [ $rotated_count -eq 0 ]; then
            print_success "No log files needed rotation"
        else
            print_success "Rotated $rotated_count log files"
        fi
    fi
}

# Function to purge all logs
purge_logs() {
    local dry_run=$1
    local verbose=$2
    
    print_warning "PURGING ALL LOGS - This will delete all log files!"
    
    if [ "$dry_run" != "true" ]; then
        echo -n "Are you sure you want to delete ALL log files? (type 'yes' to confirm): "
        read -r confirmation
        
        if [ "$confirmation" != "yes" ]; then
            print_info "Purge cancelled"
            return
        fi
    fi
    
    if [ ! -d "$LOG_DIR" ]; then
        print_warning "Log directory does not exist: $LOG_DIR"
        return
    fi
    
    local all_log_files
    all_log_files=$(find "$LOG_DIR" -type f \( -name "*.log" -o -name "*.log.*" \) 2>/dev/null)
    
    if [ -z "$all_log_files" ]; then
        print_success "No log files found to purge"
        return
    fi
    
    local file_count
    file_count=$(echo "$all_log_files" | wc -l)
    
    if [ "$dry_run" = "true" ]; then
        print_info "DRY RUN: Would purge $file_count log files"
    else
        print_info "Purging $file_count log files..."
        
        local purged_count=0
        echo "$all_log_files" | while read -r file; do
            if [ -n "$file" ] && [ -f "$file" ]; then
                if rm "$file" 2>/dev/null; then
                    purged_count=$((purged_count + 1))
                    if [ "$verbose" = "true" ]; then
                        print_info "Purged: $file"
                    fi
                fi
            fi
        done
        
        print_success "Purged $purged_count log files"
    fi
}

# Main execution
main() {
    local command="cleanup"
    local dry_run="false"
    local verbose="false"
    
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --retention-days)
                RETENTION_DAYS="$2"
                shift 2
                ;;
            --compress-days)
                COMPRESS_DAYS="$2"
                shift 2
                ;;
            --archive-days)
                ARCHIVE_DAYS="$2"
                shift 2
                ;;
            --max-size)
                MAX_LOG_SIZE="$2"
                shift 2
                ;;
            --dry-run)
                dry_run="true"
                shift
                ;;
            --verbose)
                verbose="true"
                shift
                ;;
            --help|-h)
                show_help
                exit 0
                ;;
            cleanup|compress|archive|rotate|status|purge)
                command="$1"
                shift
                ;;
            *)
                print_error "Unknown option: $1"
                show_help
                exit 1
                ;;
        esac
    done
    
    # Validate numeric parameters
    if ! [[ "$RETENTION_DAYS" =~ ^[0-9]+$ ]]; then
        print_error "Invalid retention days: $RETENTION_DAYS"
        exit 1
    fi
    
    if ! [[ "$COMPRESS_DAYS" =~ ^[0-9]+$ ]]; then
        print_error "Invalid compress days: $COMPRESS_DAYS"
        exit 1
    fi
    
    if ! [[ "$ARCHIVE_DAYS" =~ ^[0-9]+$ ]]; then
        print_error "Invalid archive days: $ARCHIVE_DAYS"
        exit 1
    fi
    
    # Show configuration if verbose
    if [ "$verbose" = "true" ]; then
        print_info "Configuration:"
        echo "  Log Directory: $LOG_DIR"
        echo "  Retention Days: $RETENTION_DAYS"
        echo "  Compress Days: $COMPRESS_DAYS"
        echo "  Archive Days: $ARCHIVE_DAYS"
        echo "  Max Log Size: $MAX_LOG_SIZE"
        echo "  Dry Run: $dry_run"
        echo ""
    fi
    
    # Execute command
    case $command in
        cleanup)
            cleanup_logs "$dry_run" "$verbose"
            ;;
        compress)
            compress_logs "$dry_run" "$verbose"
            ;;
        archive)
            archive_logs "$dry_run" "$verbose"
            ;;
        rotate)
            rotate_logs "$dry_run" "$verbose"
            ;;
        status)
            show_status
            ;;
        purge)
            purge_logs "$dry_run" "$verbose"
            ;;
        *)
            print_error "Unknown command: $command"
            show_help
            exit 1
            ;;
    esac
}

# Check dependencies
if ! command -v find >/dev/null 2>&1; then
    print_error "Required command 'find' not found"
    exit 1
fi

if ! command -v bc >/dev/null 2>&1; then
    print_warning "Command 'bc' not found - size calculations may be less accurate"
fi

# Run main function
main "$@"