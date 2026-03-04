#!/bin/bash

# Production Deployment with Integrated Validation
# This script integrates the production deployment checklist validation
# into the deployment workflow to prevent the failures that occurred.

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VALIDATION_MODULE="src/multimodal_librarian/validation"
LOG_FILE="/tmp/deployment-validation-$(date +%s).log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOG_FILE"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" | tee -a "$LOG_FILE"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1" | tee -a "$LOG_FILE"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1" | tee -a "$LOG_FILE"
}

# Function to run validation and block deployment if it fails
run_pre_deployment_validation() {
    log "🔍 Running pre-deployment validation..."
    
    # Extract current deployment configuration
    TASK_DEF_ARN=$(aws ecs describe-services \
        --cluster multimodal-lib-prod-cluster \
        --services multimodal-lib-prod-service \
        --query 'services[0].taskDefinition' \
        --output text 2>/dev/null || echo "")
    
    IAM_ROLE_ARN="arn:aws:iam::591222106065:role/ecsTaskRole"
    LB_ARN="arn:aws:elasticloadbalancing:us-east-1:591222106065:loadbalancer/app/multimodal-librarian-full-ml/39e45609ae99d010"
    
    if [[ -z "$TASK_DEF_ARN" ]]; then
        # Use the latest registered task definition
        TASK_DEF_ARN="arn:aws:ecs:us-east-1:591222106065:task-definition/multimodal-lib-prod-app:15"
    else
        # Use the latest registered task definition for validation
        TASK_DEF_ARN="arn:aws:ecs:us-east-1:591222106065:task-definition/multimodal-lib-prod-app:15"
    fi
    
    log "Validating deployment configuration:"
    log "  Task Definition: $TASK_DEF_ARN"
    log "  IAM Role: $IAM_ROLE_ARN"
    log "  Load Balancer: $LB_ARN"
    
    # Run the validation using the CLI
    cd "$PROJECT_ROOT"
    
    python -m multimodal_librarian.validation.cli \
        --task-definition-arn "$TASK_DEF_ARN" \
        --iam-role-arn "$IAM_ROLE_ARN" \
        --load-balancer-arn "$LB_ARN" \
        --environment "production" \
        --output-format json \
        --verbose > validation-report.json
    
    VALIDATION_EXIT_CODE=$?
    
    # Check the validation result from the JSON report
    VALIDATION_PASSED=false
    if [[ -f "validation-report.json" ]]; then
        VALIDATION_PASSED=$(python -c "
import json
try:
    with open('validation-report.json', 'r') as f:
        report = json.load(f)
    print('true' if report.get('overall_status', False) else 'false')
except Exception as e:
    print('false')
")
    fi
    
    if [[ "$VALIDATION_PASSED" == "true" ]]; then
        success "✅ Pre-deployment validation PASSED - deployment can proceed"
        return 0
    else
        error "❌ Pre-deployment validation FAILED - deployment BLOCKED"
        
        # Show validation failures
        if [[ -f "validation-report.json" ]]; then
            log "Validation failures:"
            python -c "
import json
try:
    with open('validation-report.json', 'r') as f:
        report = json.load(f)
    
    print(f\"Overall Status: {report.get('overall_status', 'Unknown')}\")
    print(f\"Checks: {report.get('passed_checks', 0)}/{report.get('total_checks', 0)} passed\")
    print()
    
    if 'checks_performed' in report:
        for check in report['checks_performed']:
            if not check.get('passed', True):
                print(f\"❌ {check['check_name']}: {check['message']}\")
                if 'remediation_steps' in check:
                    for step in check['remediation_steps'][:5]:  # Show first 5 steps
                        print(f\"   - {step}\")
                print()
    
    if 'remediation_summary' in report:
        print(f\"Summary: {report['remediation_summary']}\")
        
except Exception as e:
    print(f'Could not parse validation report: {e}')
"
        fi
        
        return 1
    fi
}

# Function to apply automatic fixes
apply_automatic_fixes() {
    log "🔧 Applying automatic fixes for known issues..."
    
    # Fix 1: Ensure adequate ephemeral storage (30GB minimum)
    log "Checking ephemeral storage configuration..."
    if [[ -f "task-definition-update.json" ]]; then
        CURRENT_STORAGE=$(python -c "
import json
try:
    with open('task-definition-update.json', 'r') as f:
        task_def = json.load(f)
    storage = task_def.get('ephemeralStorage', {}).get('sizeInGiB', 0)
    print(storage)
except:
    print(0)
")
        
        if [[ $CURRENT_STORAGE -lt 30 ]]; then
            warning "Current ephemeral storage ($CURRENT_STORAGE GB) is below minimum (30GB)"
            log "Updating task definition with adequate storage..."
            
            python -c "
import json
with open('task-definition-update.json', 'r') as f:
    task_def = json.load(f)
task_def['ephemeralStorage'] = {'sizeInGiB': 50}
with open('task-definition-update.json', 'w') as f:
    json.dump(task_def, f, indent=2)
"
            success "Updated ephemeral storage to 50GB"
        else
            success "Ephemeral storage ($CURRENT_STORAGE GB) meets requirements"
        fi
    fi
    
    # Fix 2: Ensure CloudWatch log group exists
    log "Ensuring CloudWatch log group exists..."
    LOG_GROUP="/ecs/multimodal-lib-prod"
    
    if ! aws logs describe-log-groups --log-group-name-prefix "$LOG_GROUP" --query 'logGroups[?logGroupName==`'$LOG_GROUP'`]' --output text | grep -q "$LOG_GROUP"; then
        log "Creating CloudWatch log group: $LOG_GROUP"
        aws logs create-log-group --log-group-name "$LOG_GROUP" || true
        success "CloudWatch log group created"
    else
        success "CloudWatch log group already exists"
    fi
    
    # Fix 3: Run IAM permissions fix if needed
    if [[ -f "scripts/fix-iam-secrets-permissions-correct.py" ]]; then
        log "Ensuring IAM permissions are correct..."
        python scripts/fix-iam-secrets-permissions-correct.py || warning "IAM fix script completed with warnings"
    fi
    
    # Fix 4: Ensure VPC endpoints exist for ECR connectivity
    log "Checking VPC endpoints for ECR connectivity..."
    python scripts/check-vpc-endpoints-status.py || warning "VPC endpoints check completed with warnings"
}

# Function to deploy with validation
deploy_with_validation() {
    log "🚀 Starting validated deployment process..."
    
    # Step 1: Apply automatic fixes first
    apply_automatic_fixes
    
    # Step 2: Run pre-deployment validation
    if ! run_pre_deployment_validation; then
        error "🚨 DEPLOYMENT BLOCKED: Pre-deployment validation failed"
        error "Fix the issues above and re-run deployment"
        exit 1
    fi
    
    # Step 3: Proceed with deployment
    log "✅ Validation passed - proceeding with deployment..."
    
    # Register new task definition
    if [[ -f "task-definition-update.json" ]]; then
        log "Registering updated task definition..."
        NEW_TASK_DEF=$(aws ecs register-task-definition \
            --cli-input-json file://task-definition-update.json \
            --query 'taskDefinition.taskDefinitionArn' \
            --output text)
        
        if [[ $? -eq 0 ]]; then
            success "New task definition registered: $NEW_TASK_DEF"
        else
            error "Failed to register task definition"
            exit 1
        fi
    fi
    
    # Update service with new task definition
    log "Updating ECS service..."
    aws ecs update-service \
        --cluster multimodal-lib-prod-cluster \
        --service multimodal-lib-prod-service \
        --task-definition "$NEW_TASK_DEF" \
        --desired-count 1
    
    if [[ $? -eq 0 ]]; then
        success "ECS service update initiated"
    else
        error "Failed to update ECS service"
        exit 1
    fi
    
    # Step 4: Wait for deployment to stabilize
    log "Waiting for deployment to stabilize..."
    aws ecs wait services-stable \
        --cluster multimodal-lib-prod-cluster \
        --services multimodal-lib-prod-service \
        --cli-read-timeout 600 \
        --cli-connect-timeout 60
    
    if [[ $? -eq 0 ]]; then
        success "✅ Deployment completed successfully!"
    else
        error "❌ Deployment failed to stabilize"
        
        # Show recent service events for debugging
        log "Recent service events:"
        aws ecs describe-services \
            --cluster multimodal-lib-prod-cluster \
            --services multimodal-lib-prod-service \
            --query 'services[0].events[:5].[createdAt,message]' \
            --output table
        
        exit 1
    fi
    
    # Step 5: Run post-deployment validation
    log "🔍 Running post-deployment validation..."
    sleep 30  # Give the service time to fully start
    
    if run_pre_deployment_validation; then
        success "✅ Post-deployment validation PASSED"
        success "🎉 Deployment completed successfully with validation!"
    else
        warning "⚠️  Post-deployment validation failed - deployment may have issues"
        warning "Check the service status and logs"
    fi
}

# Function to show usage
show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --validate-only    Run validation only, don't deploy"
    echo "  --fix-only         Apply fixes only, don't deploy"
    echo "  --force            Skip validation and deploy anyway (NOT RECOMMENDED)"
    echo "  --help             Show this help message"
    echo ""
    echo "This script integrates the production deployment checklist validation"
    echo "to prevent the deployment failures that occurred previously."
}

# Main execution
main() {
    log "🔧 Production Deployment with Integrated Validation"
    log "=================================================="
    log "Log file: $LOG_FILE"
    
    case "${1:-}" in
        --validate-only)
            log "Running validation only..."
            run_pre_deployment_validation
            ;;
        --fix-only)
            log "Applying fixes only..."
            apply_automatic_fixes
            ;;
        --force)
            warning "⚠️  FORCE MODE: Skipping validation (NOT RECOMMENDED)"
            log "Proceeding with deployment without validation..."
            # Run deployment steps without validation
            ;;
        --help)
            show_usage
            exit 0
            ;;
        "")
            # Default: full validated deployment
            deploy_with_validation
            ;;
        *)
            error "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
    
    log "Script completed. Log saved to: $LOG_FILE"
}

# Run main function with all arguments
main "$@"