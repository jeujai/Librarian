#!/bin/bash

# Redis Restore Script for Multimodal Librarian Local Development
# This script restores Redis database from backups

set -e

# Configuration
REDIS_HOST="${REDIS_HOST:-localhost}"
REDIS_PORT="${REDIS_PORT:-6379}"
BACKUP_DIR="${BACKUP_DIR:-./backups/redis}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Check if Redis is accessible
check_connectivity() {
    log "Checking Redis connectivity..."
    
    if ! redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" ping >/dev/null 2>&1; then
        error "Cannot connect to Redis server"
        return 1
    fi
    
    success "Redis is accessible"
    return 0
}

# Function to list available backups
list_backups() {
    log "Available Redis backups in $BACKUP_DIR:"
    echo ""
    
    if [[ ! -d "$BACKUP_DIR" ]]; then
        warning "Backup directory does not exist: $BACKUP_DIR"
        return 1
    fi
    
    local backups_found=false
    
    echo "RDB Backups:"
    if find "$BACKUP_DIR" -name "*.rdb" -type f | head -1 >/dev/null 2>&1; then
        find "$BACKUP_DIR" -name "*.rdb" -type f -exec ls -lh {} \; | sort -k9
        backups_found=true
    else
        echo "  No RDB backups found"
    fi
    
    echo ""
    echo "AOF Backups:"
    if find "$BACKUP_DIR" -name "*.aof" -type f | head -1 >/dev/null 2>&1; then
        find "$BACKUP_DIR" -name "*.aof" -type f -exec ls -lh {} \; | sort -k9
        backups_found=true
    else
        echo "  No AOF backups found"
    fi
    
    if [[ "$backups_found" == false ]]; then
        warning "No backups found in $BACKUP_DIR"
        return 1
    fi
}

# Function to get latest backup
get_latest_backup() {
    local backup_type="${1:-rdb}"
    local pattern
    
    case "$backup_type" in
        "rdb")
            pattern="*.rdb"
            ;;
        "aof")
            pattern="*.aof"
            ;;
        *)
            pattern="*.rdb"
            ;;
    esac
    
    find "$BACKUP_DIR" -name "$pattern" -type f -printf '%T@ %p\n' 2>/dev/null | \
    sort -n | tail -1 | cut -d' ' -f2-
}

# Function to flush current Redis data
flush_redis_data() {
    log "Flushing current Redis data..."
    
    # Ask for confirmation
    echo -n "This will delete all existing data in Redis. Continue? (y/N): "
    read -r confirmation
    if [[ "$confirmation" != "y" && "$confirmation" != "Y" ]]; then
        log "Redis flush cancelled by user"
        return 1
    fi
    
    # Flush all databases
    if redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" FLUSHALL >/dev/null 2>&1; then
        success "Redis data flushed successfully"
    else
        error "Failed to flush Redis data"
        return 1
    fi
}

# Function to restore from RDB backup
restore_rdb_backup() {
    local backup_file="$1"
    
    if [[ ! -f "$backup_file" ]]; then
        error "Backup file not found: $backup_file"
        return 1
    fi
    
    log "Restoring from RDB backup: $backup_file"
    
    # Flush current data first
    if ! flush_redis_data; then
        return 1
    fi
    
    # Method 1: Try using Docker if available
    if command -v docker-compose >/dev/null 2>&1; then
        log "Using Docker method for RDB restore..."
        
        # Stop Redis service temporarily
        log "Stopping Redis service..."
        if docker-compose -f docker-compose.local.yml stop redis; then
            success "Redis service stopped"
        else
            error "Failed to stop Redis service"
            return 1
        fi
        
        # Copy backup file to Redis data directory
        local redis_data_dir="./data/redis"
        mkdir -p "$redis_data_dir"
        
        if cp "$backup_file" "$redis_data_dir/dump.rdb"; then
            success "Backup file copied to Redis data directory"
        else
            error "Failed to copy backup file"
            return 1
        fi
        
        # Start Redis service
        log "Starting Redis service..."
        if docker-compose -f docker-compose.local.yml start redis; then
            success "Redis service started"
            
            # Wait for Redis to be ready
            log "Waiting for Redis to be ready..."
            local retry_count=0
            while ! redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" ping >/dev/null 2>&1; do
                sleep 1
                retry_count=$((retry_count + 1))
                if [[ $retry_count -gt 30 ]]; then
                    error "Redis did not start within expected time"
                    return 1
                fi
            done
            success "Redis is ready"
        else
            error "Failed to start Redis service"
            return 1
        fi
    else
        # Method 2: Use redis-cli with DEBUG RELOAD (if supported)
        warning "Docker not available, trying alternative method..."
        
        # This method requires Redis to support DEBUG RELOAD
        # Note: This may not work in all Redis configurations
        if redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" --rdb "$backup_file" >/dev/null 2>&1; then
            success "RDB backup restored using redis-cli"
        else
            error "Failed to restore RDB backup using redis-cli"
            error "Please manually copy $backup_file to Redis data directory and restart Redis"
            return 1
        fi
    fi
    
    success "RDB backup restored successfully"
}

# Function to restore from AOF backup
restore_aof_backup() {
    local backup_file="$1"
    
    if [[ ! -f "$backup_file" ]]; then
        error "Backup file not found: $backup_file"
        return 1
    fi
    
    log "Restoring from AOF backup: $backup_file"
    
    # Flush current data first
    if ! flush_redis_data; then
        return 1
    fi
    
    # Method 1: Try using Docker if available
    if command -v docker-compose >/dev/null 2>&1; then
        log "Using Docker method for AOF restore..."
        
        # Stop Redis service temporarily
        log "Stopping Redis service..."
        if docker-compose -f docker-compose.local.yml stop redis; then
            success "Redis service stopped"
        else
            error "Failed to stop Redis service"
            return 1
        fi
        
        # Copy backup file to Redis data directory
        local redis_data_dir="./data/redis"
        mkdir -p "$redis_data_dir"
        
        if cp "$backup_file" "$redis_data_dir/appendonly.aof"; then
            success "AOF backup file copied to Redis data directory"
        else
            error "Failed to copy AOF backup file"
            return 1
        fi
        
        # Start Redis service with AOF enabled
        log "Starting Redis service with AOF enabled..."
        if docker-compose -f docker-compose.local.yml start redis; then
            success "Redis service started"
            
            # Wait for Redis to be ready
            log "Waiting for Redis to be ready..."
            local retry_count=0
            while ! redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" ping >/dev/null 2>&1; do
                sleep 1
                retry_count=$((retry_count + 1))
                if [[ $retry_count -gt 30 ]]; then
                    error "Redis did not start within expected time"
                    return 1
                fi
            done
            success "Redis is ready"
        else
            error "Failed to start Redis service"
            return 1
        fi
    else
        # Method 2: Replay AOF commands manually
        warning "Docker not available, trying to replay AOF commands..."
        
        # Read AOF file and execute commands
        if redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" --pipe < "$backup_file" >/dev/null 2>&1; then
            success "AOF commands replayed successfully"
        else
            error "Failed to replay AOF commands"
            return 1
        fi
    fi
    
    success "AOF backup restored successfully"
}

# Function to restore from Redis commands file
restore_commands_backup() {
    local backup_file="$1"
    
    if [[ ! -f "$backup_file" ]]; then
        error "Backup file not found: $backup_file"
        return 1
    fi
    
    log "Restoring from Redis commands file: $backup_file"
    
    # Flush current data first
    if ! flush_redis_data; then
        return 1
    fi
    
    # Execute commands from file
    if redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" < "$backup_file" >/dev/null 2>&1; then
        success "Redis commands executed successfully"
    else
        error "Failed to execute Redis commands"
        return 1
    fi
}

# Function to verify restore
verify_restore() {
    log "Verifying Redis restore..."
    
    # Check connectivity
    if ! check_connectivity; then
        return 1
    fi
    
    # Get basic statistics
    local key_count=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" DBSIZE 2>/dev/null || echo "0")
    local memory_usage=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" INFO memory 2>/dev/null | grep "used_memory_human:" | cut -d: -f2 | tr -d '\r' || echo "Unknown")
    
    success "Restore verification completed"
    echo "  Keys: $key_count"
    echo "  Memory usage: $memory_usage"
    
    # Show some sample keys
    local sample_keys=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" KEYS "*" 2>/dev/null | head -5 || echo "")
    if [[ -n "$sample_keys" ]]; then
        echo "  Sample keys:"
        echo "$sample_keys" | while read -r key; do
            if [[ -n "$key" ]]; then
                echo "    $key"
            fi
        done
    fi
}

# Function to create Redis backup before restore (safety measure)
create_safety_backup() {
    log "Creating safety backup before restore..."
    
    local safety_backup_dir="$BACKUP_DIR/safety"
    mkdir -p "$safety_backup_dir"
    
    local timestamp=$(date +"%Y%m%d_%H%M%S")
    local safety_backup_file="$safety_backup_dir/safety_backup_${timestamp}.rdb"
    
    # Create backup using BGSAVE
    if redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" BGSAVE >/dev/null 2>&1; then
        # Wait for background save to complete
        while redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" LASTSAVE | grep -q "$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" LASTSAVE)"; do
            sleep 1
        done
        
        # Copy the dump file if using Docker
        if command -v docker-compose >/dev/null 2>&1; then
            if docker-compose -f docker-compose.local.yml exec -T redis cp /data/dump.rdb "/backups/safety_backup_${timestamp}.rdb" 2>/dev/null; then
                success "Safety backup created: $safety_backup_file"
            else
                warning "Could not create safety backup"
            fi
        else
            warning "Safety backup creation requires Docker setup"
        fi
    else
        warning "Failed to create safety backup"
    fi
}

# Main execution
main() {
    case "${1:-list}" in
        "list")
            list_backups
            ;;
        "latest")
            check_connectivity
            create_safety_backup
            
            local latest_backup
            latest_backup=$(get_latest_backup "rdb")
            if [[ -n "$latest_backup" ]]; then
                log "Latest RDB backup found: $latest_backup"
                restore_rdb_backup "$latest_backup"
                verify_restore
            else
                error "No RDB backups found"
                exit 1
            fi
            ;;
        "latest-aof")
            check_connectivity
            create_safety_backup
            
            local latest_aof
            latest_aof=$(get_latest_backup "aof")
            if [[ -n "$latest_aof" ]]; then
                log "Latest AOF backup found: $latest_aof"
                restore_aof_backup "$latest_aof"
                verify_restore
            else
                error "No AOF backups found"
                exit 1
            fi
            ;;
        "file")
            if [[ -z "$2" ]]; then
                error "Please specify backup file path"
                echo "Usage: $0 file <backup_file_path>"
                exit 1
            fi
            check_connectivity
            create_safety_backup
            
            case "$2" in
                *.rdb)
                    restore_rdb_backup "$2"
                    ;;
                *.aof)
                    restore_aof_backup "$2"
                    ;;
                *.redis|*.txt)
                    restore_commands_backup "$2"
                    ;;
                *)
                    error "Unsupported backup file format: $2"
                    echo "Supported formats: .rdb, .aof, .redis, .txt"
                    exit 1
                    ;;
            esac
            verify_restore
            ;;
        "verify")
            verify_restore
            ;;
        "help"|"--help"|"-h")
            echo "Usage: $0 [list|latest|latest-aof|file <path>|verify|help]"
            echo ""
            echo "Options:"
            echo "  list           - List available backups (default)"
            echo "  latest         - Restore from latest RDB backup"
            echo "  latest-aof     - Restore from latest AOF backup"
            echo "  file <path>    - Restore from specific backup file"
            echo "  verify         - Verify current Redis state"
            echo "  help           - Show this help message"
            echo ""
            echo "Environment variables:"
            echo "  REDIS_HOST     - Redis host (default: localhost)"
            echo "  REDIS_PORT     - Redis port (default: 6379)"
            echo "  BACKUP_DIR     - Backup directory (default: ./backups/redis)"
            echo ""
            echo "Examples:"
            echo "  $0 latest                           # Restore from latest RDB backup"
            echo "  $0 file /path/to/backup.rdb         # Restore from specific RDB file"
            echo "  $0 latest-aof                       # Restore from latest AOF backup"
            echo ""
            echo "Note: This script will create a safety backup before restore"
            exit 0
            ;;
        *)
            error "Unknown action: $1"
            echo "Use '$0 help' for usage information"
            exit 1
            ;;
    esac
    
    success "Redis restore operation completed"
}

# Run main function with all arguments
main "$@"