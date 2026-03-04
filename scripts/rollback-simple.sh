#!/bin/bash

# Simple Rollback Script for Learning CI/CD
# This script provides simplified rollback capabilities for learning purposes

set -e

# Configuration
PROJECT_NAME="multimodal-librarian"
ENVIRONMENT="${ENVIRONMENT:-learning}"
REGION="${AWS_REGION:-us-east-1}"
STACK_NAME="MultimodalLibrarianStack"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log() {
    echo -e "${GREEN}[$(date +'%H:%M:%S')] $1${NC}"
}

warn() {
    echo -e "${YELLOW}[$(date +'%H:%M:%S')] WARNING: $1${NC}"
}

error() {
    echo -e "${RED}[$(date +'%H:%M:%S')] ERROR: $1${NC}"
    exit 1
}

info() {
    echo -e "${BLUE}[$(date +'%H:%M:%S')] INFO: $1${NC}"
}

# Show usage
show_usage() {
    echo "Simple Rollback Script for Learning CI/CD"
    echo ""
    echo "Usage: $0 [OPTIONS] COMMAND"
    echo ""
    echo "Commands:"
    echo "  app         Rollback application to previous version"
    echo "  database    Rollback database from snapshot"
    echo "  infra       Rollback infrastructure changes"
    echo "  config      Rollback configuration changes"
    echo "  list        List available rollback options"
    echo "  emergency   Emergency stop all services"
    echo ""
    echo "Options:"
    echo "  -e, --env ENV       Environment (default: learning)"
    echo "  -r, --region REGION AWS region (default: us-east-1)"
    echo "  -y, --yes           Skip confirmation prompts"
    echo "  -h, --help          Show this help"
    echo ""
    echo "Examples:"
    echo "  $0 app                      # Rollback application"
    echo "  $0 database                 # Rollback database"
    echo "  $0 list                     # Show rollback options"
    echo "  $0 -y emergency             # Emergency stop (no confirmation)"
    echo ""
}

# Check prerequisites
check_prerequisites() {
    log "Checking prerequisites..."
    
    # Check AWS CLI
    if ! command -v aws &> /dev/null; then
        error "AWS CLI is not installed"
    fi
    
    # Check AWS credentials
    if ! aws sts get-caller-identity &> /dev/null; then
        error "AWS credentials not configured"
    fi
    
    # Get AWS account info
    ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
    info "AWS Account: $ACCOUNT_ID"
    info "AWS Region: $REGION"
    info "Environment: $ENVIRONMENT"
    
    log "Prerequisites check passed"
}

# Confirm action with user
confirm_action() {
    local action="$1"
    local warning="$2"
    
    if [ "$SKIP_CONFIRMATION" = "true" ]; then
        return 0
    fi
    
    warn "$warning"
    echo ""
    read -p "Are you sure you want to $action? (type 'yes' to confirm): " CONFIRM
    
    if [ "$CONFIRM" != "yes" ]; then
        log "Action cancelled by user"
        exit 0
    fi
}

# List available rollback options
list_rollback_options() {
    log "Available Rollback Options for $PROJECT_NAME-$ENVIRONMENT"
    echo ""
    
    # Application rollback options
    echo "🚀 Application Rollback:"
    CLUSTER_NAME="$PROJECT_NAME-$ENVIRONMENT"
    
    if aws ecs describe-clusters --clusters "$CLUSTER_NAME" --region "$REGION" &> /dev/null; then
        SERVICES=$(aws ecs list-services \
            --cluster "$CLUSTER_NAME" \
            --region "$REGION" \
            --query 'serviceArns[*]' \
            --output text)
        
        if [ -n "$SERVICES" ]; then
            for SERVICE_ARN in $SERVICES; do
                SERVICE_NAME=$(basename "$SERVICE_ARN")
                
                # Get current task definition
                CURRENT_TASK_DEF=$(aws ecs describe-services \
                    --cluster "$CLUSTER_NAME" \
                    --services "$SERVICE_NAME" \
                    --region "$REGION" \
                    --query 'services[0].taskDefinition' \
                    --output text)
                
                TASK_FAMILY=$(echo "$CURRENT_TASK_DEF" | cut -d':' -f6 | cut -d'/' -f2)
                CURRENT_REVISION=$(echo "$CURRENT_TASK_DEF" | cut -d':' -f7)
                
                echo "   Service: $SERVICE_NAME"
                echo "     Current: $TASK_FAMILY:$CURRENT_REVISION"
                
                if [ "$CURRENT_REVISION" -gt 1 ]; then
                    PREVIOUS_REVISION=$((CURRENT_REVISION - 1))
                    echo "     Can rollback to: $TASK_FAMILY:$PREVIOUS_REVISION"
                else
                    echo "     Cannot rollback (already at revision 1)"
                fi
                echo ""
            done
        else
            echo "   No ECS services found"
        fi
    else
        echo "   ECS cluster not found"
    fi
    
    # Database rollback options
    echo "🗄️  Database Rollback:"
    DB_IDENTIFIER="$PROJECT_NAME-$ENVIRONMENT-db"
    
    if aws rds describe-db-instances --db-instance-identifier "$DB_IDENTIFIER" --region "$REGION" &> /dev/null; then
        echo "   Database: $DB_IDENTIFIER (exists)"
        
        # List recent snapshots
        SNAPSHOTS=$(aws rds describe-db-snapshots \
            --db-instance-identifier "$DB_IDENTIFIER" \
            --snapshot-type manual \
            --region "$REGION" \
            --query 'DBSnapshots[?SnapshotCreateTime>=`2024-01-01`].[DBSnapshotIdentifier,SnapshotCreateTime]' \
            --output text | head -5)
        
        if [ -n "$SNAPSHOTS" ]; then
            echo "   Recent snapshots available:"
            echo "$SNAPSHOTS" | while read -r snapshot_id create_time; do
                echo "     - $snapshot_id ($create_time)"
            done
        else
            echo "   No recent snapshots found"
        fi
    else
        echo "   Database not found"
    fi
    
    echo ""
    
    # Infrastructure rollback options
    echo "🏗️  Infrastructure Rollback:"
    STACK_STATUS=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --region "$REGION" \
        --query 'Stacks[0].StackStatus' \
        --output text 2>/dev/null || echo "NOT_FOUND")
    
    echo "   Stack: $STACK_NAME"
    echo "   Status: $STACK_STATUS"
    
    if [[ "$STACK_STATUS" == *"FAILED"* ]]; then
        echo "   Rollback available: Yes (stack in failed state)"
    elif [ "$STACK_STATUS" = "UPDATE_COMPLETE" ]; then
        echo "   Rollback available: Yes (can rollback to previous version)"
    else
        echo "   Rollback available: No"
    fi
    
    echo ""
}

# Rollback application to previous version
rollback_application() {
    log "Rolling back application to previous version..."
    
    CLUSTER_NAME="$PROJECT_NAME-$ENVIRONMENT"
    
    # Check if cluster exists
    if ! aws ecs describe-clusters --clusters "$CLUSTER_NAME" --region "$REGION" &> /dev/null; then
        error "ECS cluster $CLUSTER_NAME not found"
    fi
    
    # Get services
    SERVICES=$(aws ecs list-services \
        --cluster "$CLUSTER_NAME" \
        --region "$REGION" \
        --query 'serviceArns[*]' \
        --output text)
    
    if [ -z "$SERVICES" ]; then
        error "No ECS services found in cluster $CLUSTER_NAME"
    fi
    
    confirm_action "rollback the application" "This will rollback all ECS services to their previous task definition versions."
    
    # Rollback each service
    for SERVICE_ARN in $SERVICES; do
        SERVICE_NAME=$(basename "$SERVICE_ARN")
        log "Rolling back service: $SERVICE_NAME"
        
        # Get current task definition
        CURRENT_TASK_DEF=$(aws ecs describe-services \
            --cluster "$CLUSTER_NAME" \
            --services "$SERVICE_NAME" \
            --region "$REGION" \
            --query 'services[0].taskDefinition' \
            --output text)
        
        # Extract task definition family and revision
        TASK_FAMILY=$(echo "$CURRENT_TASK_DEF" | cut -d':' -f6 | cut -d'/' -f2)
        CURRENT_REVISION=$(echo "$CURRENT_TASK_DEF" | cut -d':' -f7)
        
        if [ "$CURRENT_REVISION" -le 1 ]; then
            warn "Service $SERVICE_NAME is already at revision 1, cannot rollback further"
            continue
        fi
        
        PREVIOUS_REVISION=$((CURRENT_REVISION - 1))
        PREVIOUS_TASK_DEF="$TASK_FAMILY:$PREVIOUS_REVISION"
        
        info "Rolling back from $CURRENT_TASK_DEF to $PREVIOUS_TASK_DEF"
        
        # Update service to previous task definition
        aws ecs update-service \
            --cluster "$CLUSTER_NAME" \
            --service "$SERVICE_NAME" \
            --task-definition "$PREVIOUS_TASK_DEF" \
            --region "$REGION" > /dev/null
        
        # Wait for rollback to complete
        log "Waiting for rollback to complete..."
        aws ecs wait services-stable \
            --cluster "$CLUSTER_NAME" \
            --services "$SERVICE_NAME" \
            --region "$REGION"
        
        log "Service $SERVICE_NAME rolled back successfully"
    done
    
    log "Application rollback completed"
}

# Rollback database from snapshot
rollback_database() {
    log "Rolling back database from snapshot..."
    
    DB_IDENTIFIER="$PROJECT_NAME-$ENVIRONMENT-db"
    
    # Check if database exists
    if ! aws rds describe-db-instances --db-instance-identifier "$DB_IDENTIFIER" --region "$REGION" &> /dev/null; then
        error "Database $DB_IDENTIFIER not found"
    fi
    
    # List available snapshots
    log "Available database snapshots:"
    SNAPSHOTS=$(aws rds describe-db-snapshots \
        --db-instance-identifier "$DB_IDENTIFIER" \
        --snapshot-type manual \
        --region "$REGION" \
        --query 'DBSnapshots[*].[DBSnapshotIdentifier,SnapshotCreateTime]' \
        --output table)
    
    if [ -z "$SNAPSHOTS" ]; then
        error "No manual snapshots found for database $DB_IDENTIFIER"
    fi
    
    echo "$SNAPSHOTS"
    echo ""
    
    # Get snapshot to restore from
    read -p "Enter snapshot identifier to restore from: " SNAPSHOT_ID
    
    if [ -z "$SNAPSHOT_ID" ]; then
        error "No snapshot identifier provided"
    fi
    
    # Verify snapshot exists
    if ! aws rds describe-db-snapshots \
        --db-snapshot-identifier "$SNAPSHOT_ID" \
        --region "$REGION" &> /dev/null; then
        error "Snapshot $SNAPSHOT_ID not found"
    fi
    
    confirm_action "restore database from snapshot" "This will REPLACE the current database with snapshot data. All data created after the snapshot will be LOST."
    
    # Create a backup of current database before rollback
    BACKUP_SNAPSHOT="$DB_IDENTIFIER-pre-rollback-$(date +%Y%m%d-%H%M%S)"
    log "Creating backup snapshot before rollback: $BACKUP_SNAPSHOT"
    
    aws rds create-db-snapshot \
        --db-instance-identifier "$DB_IDENTIFIER" \
        --db-snapshot-identifier "$BACKUP_SNAPSHOT" \
        --region "$REGION"
    
    # Wait for backup to complete
    log "Waiting for backup to complete..."
    aws rds wait db-snapshot-completed \
        --db-snapshot-identifier "$BACKUP_SNAPSHOT" \
        --region "$REGION"
    
    # Delete current database instance
    log "Deleting current database instance..."
    aws rds delete-db-instance \
        --db-instance-identifier "$DB_IDENTIFIER" \
        --skip-final-snapshot \
        --region "$REGION"
    
    # Wait for deletion
    log "Waiting for database deletion..."
    aws rds wait db-instance-deleted \
        --db-instance-identifier "$DB_IDENTIFIER" \
        --region "$REGION"
    
    # Restore from snapshot
    log "Restoring database from snapshot $SNAPSHOT_ID..."
    aws rds restore-db-instance-from-db-snapshot \
        --db-instance-identifier "$DB_IDENTIFIER" \
        --db-snapshot-identifier "$SNAPSHOT_ID" \
        --region "$REGION"
    
    # Wait for restore to complete
    log "Waiting for database restore to complete..."
    aws rds wait db-instance-available \
        --db-instance-identifier "$DB_IDENTIFIER" \
        --region "$REGION"
    
    log "Database rollback completed successfully"
    info "Backup of previous state saved as: $BACKUP_SNAPSHOT"
}

# Rollback infrastructure changes
rollback_infrastructure() {
    log "Rolling back infrastructure changes..."
    
    # Check if stack exists
    if ! aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --region "$REGION" &> /dev/null; then
        error "Stack $STACK_NAME not found"
    fi
    
    # Get stack status
    STACK_STATUS=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --region "$REGION" \
        --query 'Stacks[0].StackStatus' \
        --output text)
    
    info "Current stack status: $STACK_STATUS"
    
    # Check if rollback is possible
    case "$STACK_STATUS" in
        "UPDATE_FAILED"|"UPDATE_ROLLBACK_FAILED")
            log "Stack is in failed state, rollback is available"
            ;;
        "UPDATE_COMPLETE")
            warn "Stack is in UPDATE_COMPLETE state"
            confirm_action "rollback infrastructure" "This will rollback the CloudFormation stack to the previous successful version."
            ;;
        *)
            error "Cannot rollback stack in state: $STACK_STATUS"
            ;;
    esac
    
    # Initiate rollback
    log "Initiating CloudFormation stack rollback..."
    aws cloudformation cancel-update-stack \
        --stack-name "$STACK_NAME" \
        --region "$REGION" 2>/dev/null || true
    
    # Wait for rollback to complete
    log "Waiting for rollback to complete..."
    aws cloudformation wait stack-update-complete \
        --stack-name "$STACK_NAME" \
        --region "$REGION" || true
    
    # Check final status
    FINAL_STATUS=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --region "$REGION" \
        --query 'Stacks[0].StackStatus' \
        --output text)
    
    info "Final stack status: $FINAL_STATUS"
    
    if [[ "$FINAL_STATUS" == *"ROLLBACK_COMPLETE"* ]] || [[ "$FINAL_STATUS" == *"UPDATE_COMPLETE"* ]]; then
        log "Infrastructure rollback completed successfully"
    else
        error "Infrastructure rollback failed with status: $FINAL_STATUS"
    fi
}

# Rollback configuration changes
rollback_configuration() {
    log "Rolling back configuration changes..."
    
    warn "Configuration rollback requires manual intervention"
    warn "This script provides guidance for common configuration rollback scenarios"
    
    echo ""
    echo "🔧 Configuration Rollback Options:"
    echo ""
    
    # Check secrets
    SECRET_NAME="$PROJECT_NAME/$ENVIRONMENT/api-keys"
    if aws secretsmanager describe-secret \
        --secret-id "$SECRET_NAME" \
        --region "$REGION" &> /dev/null; then
        
        echo "1. API Keys Secret: $SECRET_NAME"
        echo "   - Go to AWS Console -> Secrets Manager"
        echo "   - Select the secret and view version history"
        echo "   - Restore to a previous version if needed"
        echo ""
    fi
    
    # Check parameter store
    echo "2. Parameter Store Configuration:"
    PARAMS=$(aws ssm describe-parameters \
        --parameter-filters "Key=Name,Option=BeginsWith,Values=/$PROJECT_NAME/$ENVIRONMENT/" \
        --region "$REGION" \
        --query 'Parameters[*].Name' \
        --output text 2>/dev/null || echo "")
    
    if [ -n "$PARAMS" ]; then
        echo "   Found parameters:"
        for PARAM in $PARAMS; do
            echo "     - $PARAM"
        done
        echo "   - Use AWS Console or CLI to update parameter values"
    else
        echo "   - No parameters found"
    fi
    
    echo ""
    echo "3. Environment Variables:"
    echo "   - Update task definitions with previous environment variables"
    echo "   - Redeploy services to pick up changes"
    echo ""
    
    echo "4. Application Configuration:"
    echo "   - Check application config files in the repository"
    echo "   - Revert to previous commit if needed"
    echo "   - Rebuild and redeploy application"
    echo ""
    
    info "Configuration rollback guidance provided"
    info "Manual intervention required based on specific changes"
}

# Emergency stop all services
emergency_stop() {
    log "Initiating emergency stop of all services..."
    
    confirm_action "emergency stop all services" "This will stop ALL services immediately. The application will be offline until services are restarted."
    
    CLUSTER_NAME="$PROJECT_NAME-$ENVIRONMENT"
    
    # Stop all ECS services
    if aws ecs describe-clusters --clusters "$CLUSTER_NAME" --region "$REGION" &> /dev/null; then
        SERVICES=$(aws ecs list-services \
            --cluster "$CLUSTER_NAME" \
            --region "$REGION" \
            --query 'serviceArns[*]' \
            --output text)
        
        if [ -n "$SERVICES" ]; then
            for SERVICE_ARN in $SERVICES; do
                SERVICE_NAME=$(basename "$SERVICE_ARN")
                log "Stopping service: $SERVICE_NAME"
                
                aws ecs update-service \
                    --cluster "$CLUSTER_NAME" \
                    --service "$SERVICE_NAME" \
                    --desired-count 0 \
                    --region "$REGION" > /dev/null
            done
            
            log "All ECS services stopped"
        else
            warn "No ECS services found"
        fi
    else
        warn "ECS cluster not found"
    fi
    
    warn "Emergency stop completed - all services are now offline"
    warn "Use the deploy script or AWS Console to restart services"
}

# Parse command line arguments
SKIP_CONFIRMATION=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -e|--env)
            ENVIRONMENT="$2"
            shift 2
            ;;
        -r|--region)
            REGION="$2"
            shift 2
            ;;
        -y|--yes)
            SKIP_CONFIRMATION=true
            shift
            ;;
        -h|--help)
            show_usage
            exit 0
            ;;
        app|database|infra|config|list|emergency)
            COMMAND="$1"
            shift
            ;;
        *)
            error "Unknown option: $1"
            ;;
    esac
done

# Check if command was provided
if [ -z "${COMMAND:-}" ]; then
    show_usage
    exit 1
fi

# Update derived variables
STACK_NAME="MultimodalLibrarianStack"

# Execute command
case "$COMMAND" in
    app)
        check_prerequisites
        rollback_application
        ;;
    database)
        check_prerequisites
        rollback_database
        ;;
    infra)
        check_prerequisites
        rollback_infrastructure
        ;;
    config)
        check_prerequisites
        rollback_configuration
        ;;
    list)
        check_prerequisites
        list_rollback_options
        ;;
    emergency)
        check_prerequisites
        emergency_stop
        ;;
    *)
        error "Unknown command: $COMMAND"
        ;;
esac

log "Command '$COMMAND' completed successfully"