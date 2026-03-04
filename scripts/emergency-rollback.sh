#!/bin/bash
"""
Emergency Rollback Script for Configuration Cleanup

This script can quickly restore the system to the last known good state
in case anything goes wrong during the cleanup process.
"""

set -e

# Configuration
CLUSTER_NAME="multimodal-librarian-full-ml"
SERVICE_NAME="multimodal-librarian-service"
BACKUP_DIR="backup"
LOG_FILE="rollback-$(date +%Y%m%d-%H%M%S).log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOG_FILE"
}

error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1" | tee -a "$LOG_FILE"
}

warn() {
    echo -e "${YELLOW}[$(date '+%Y-%m-%d %H:%M:%S')] WARNING:${NC} $1" | tee -a "$LOG_FILE"
}

# Function to check if we're in emergency mode
check_emergency_mode() {
    if [ "$1" = "--emergency" ]; then
        warn "🚨 EMERGENCY ROLLBACK MODE ACTIVATED"
        warn "This will immediately restore the last known good configuration"
        read -p "Are you sure you want to proceed? (yes/no): " confirm
        if [ "$confirm" != "yes" ]; then
            error "Emergency rollback cancelled"
            exit 1
        fi
    fi
}

# Function to validate backup files exist
validate_backups() {
    log "🔍 Validating backup files..."
    
    required_files=(
        "$BACKUP_DIR/current-task-definition.json"
        "$BACKUP_DIR/current-docker-image-tag.txt"
        "$BACKUP_DIR/working-deployment-process.md"
    )
    
    for file in "${required_files[@]}"; do
        if [ ! -f "$file" ]; then
            error "Required backup file missing: $file"
            error "Cannot proceed with rollback without complete backup"
            exit 1
        fi
    done
    
    log "✅ All required backup files found"
}

# Function to get the last known good Docker image
get_backup_image() {
    if [ -f "$BACKUP_DIR/current-docker-image-tag.txt" ]; then
        cat "$BACKUP_DIR/current-docker-image-tag.txt"
    else
        error "Cannot find backup Docker image tag"
        exit 1
    fi
}

# Function to rollback ECS service
rollback_ecs_service() {
    log "🔄 Rolling back ECS service to last known good configuration..."
    
    # Get the backup task definition
    if [ ! -f "$BACKUP_DIR/current-task-definition.json" ]; then
        error "Backup task definition not found"
        exit 1
    fi
    
    # Register the backup task definition
    log "📝 Registering backup task definition..."
    aws ecs register-task-definition --cli-input-json file://$BACKUP_DIR/current-task-definition.json
    
    if [ $? -ne 0 ]; then
        error "Failed to register backup task definition"
        exit 1
    fi
    
    # Update the service to use the backup task definition
    log "🔄 Updating ECS service..."
    aws ecs update-service \
        --cluster "$CLUSTER_NAME" \
        --service "$SERVICE_NAME" \
        --task-definition multimodal-librarian
    
    if [ $? -ne 0 ]; then
        error "Failed to update ECS service"
        exit 1
    fi
    
    log "✅ ECS service rollback initiated"
}

# Function to wait for service to stabilize
wait_for_service_stable() {
    log "⏳ Waiting for service to stabilize..."
    
    aws ecs wait services-stable \
        --cluster "$CLUSTER_NAME" \
        --services "$SERVICE_NAME" \
        --cli-read-timeout 600 \
        --cli-connect-timeout 60
    
    if [ $? -eq 0 ]; then
        log "✅ Service is stable"
    else
        error "Service failed to stabilize within timeout"
        exit 1
    fi
}

# Function to validate rollback success
validate_rollback() {
    log "🔍 Validating rollback success..."
    
    # Run the comprehensive validation script
    if [ -f "scripts/comprehensive-safety-validation.py" ]; then
        log "Running comprehensive validation..."
        python3 scripts/comprehensive-safety-validation.py
        
        if [ $? -eq 0 ]; then
            log "✅ Rollback validation successful"
        else
            error "❌ Rollback validation failed"
            error "System may still have issues after rollback"
            exit 1
        fi
    else
        warn "Validation script not found, performing basic checks..."
        
        # Basic health check
        HEALTH_URL="http://multimodal-librarian-full-ml-249704554.us-east-1.elb.amazonaws.com/health"
        
        log "Checking health endpoint..."
        response=$(curl -s -o /dev/null -w "%{http_code}" "$HEALTH_URL" || echo "000")
        
        if [ "$response" = "200" ]; then
            log "✅ Health check passed"
        else
            error "❌ Health check failed (HTTP $response)"
            exit 1
        fi
    fi
}

# Function to restore secrets if needed
restore_secrets() {
    log "🔐 Checking if secrets need to be restored..."
    
    if [ -f "$BACKUP_DIR/current-secrets-structure.json" ]; then
        log "Secrets backup found, but automatic restoration not implemented"
        warn "If secrets were modified, manual restoration may be required"
        warn "Check $BACKUP_DIR/current-secrets-structure.json for reference"
    fi
}

# Function to create rollback report
create_rollback_report() {
    log "📊 Creating rollback report..."
    
    cat > "rollback-report-$(date +%Y%m%d-%H%M%S).md" << EOF
# Emergency Rollback Report

**Date:** $(date)
**Cluster:** $CLUSTER_NAME
**Service:** $SERVICE_NAME

## Actions Taken
1. Validated backup files
2. Rolled back ECS service to backup task definition
3. Waited for service stabilization
4. Validated system health

## Backup Files Used
- Task Definition: $BACKUP_DIR/current-task-definition.json
- Docker Image: $(get_backup_image)
- Process Documentation: $BACKUP_DIR/working-deployment-process.md

## Validation Results
$(if [ -f "scripts/comprehensive-safety-validation.py" ]; then echo "Comprehensive validation completed"; else echo "Basic health check completed"; fi)

## Next Steps
1. Investigate root cause of issue that triggered rollback
2. Review rollback log: $LOG_FILE
3. Verify all functionality is working as expected
4. Plan corrective actions before attempting changes again

## Log File
See $LOG_FILE for detailed rollback execution log.
EOF

    log "📄 Rollback report created: rollback-report-$(date +%Y%m%d-%H%M%S).md"
}

# Main rollback function
main() {
    log "🚨 Starting Emergency Rollback Process"
    log "Cluster: $CLUSTER_NAME"
    log "Service: $SERVICE_NAME"
    log "Backup Directory: $BACKUP_DIR"
    
    check_emergency_mode "$1"
    validate_backups
    rollback_ecs_service
    wait_for_service_stable
    restore_secrets
    validate_rollback
    create_rollback_report
    
    log "✅ Emergency rollback completed successfully"
    log "📄 Check the rollback report for details"
    log "🔍 Review log file: $LOG_FILE"
}

# Help function
show_help() {
    cat << EOF
Emergency Rollback Script

Usage: $0 [OPTIONS]

OPTIONS:
    --emergency     Run in emergency mode (skips confirmations)
    --help         Show this help message

DESCRIPTION:
    This script performs an emergency rollback of the multimodal-librarian
    system to the last known good configuration.

PREREQUISITES:
    - AWS CLI configured and authenticated
    - Backup files must exist in the backup/ directory
    - ECS cluster and service must be accessible

BACKUP FILES REQUIRED:
    - backup/current-task-definition.json
    - backup/current-docker-image-tag.txt
    - backup/working-deployment-process.md

EXAMPLES:
    # Interactive rollback
    $0

    # Emergency rollback (minimal prompts)
    $0 --emergency

EOF
}

# Parse command line arguments
case "$1" in
    --help|-h)
        show_help
        exit 0
        ;;
    --emergency)
        main "$1"
        ;;
    "")
        main
        ;;
    *)
        error "Unknown option: $1"
        show_help
        exit 1
        ;;
esac