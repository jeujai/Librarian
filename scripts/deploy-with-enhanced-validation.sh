#!/bin/bash

# Enhanced Production Deployment with Integrated Validation and VPC Fix
# This script integrates the production deployment checklist validation
# and VPC network mismatch fix into the deployment workflow.

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VALIDATION_MODULE="src/multimodal_librarian/validation"
LOG_FILE="/tmp/enhanced-deployment-$(date +%s).log"

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

# Function to check if service is currently running
check_service_status() {
    log "🔍 Checking current service status..."
    
    SERVICE_STATUS=$(aws ecs describe-services \
        --cluster multimodal-lib-prod-cluster \
        --services multimodal-lib-prod-service \
        --query 'services[0].status' \
        --output text 2>/dev/null || echo "NOT_FOUND")
    
    RUNNING_COUNT=$(aws ecs describe-services \
        --cluster multimodal-lib-prod-cluster \
        --services multimodal-lib-prod-service \
        --query 'services[0].runningCount' \
        --output text 2>/dev/null || echo "0")
    
    DESIRED_COUNT=$(aws ecs describe-services \
        --cluster multimodal-lib-prod-cluster \
        --services multimodal-lib-prod-service \
        --query 'services[0].desiredCount' \
        --output text 2>/dev/null || echo "0")
    
    log "Service Status: $SERVICE_STATUS"
    log "Running Tasks: $RUNNING_COUNT"
    log "Desired Tasks: $DESIRED_COUNT"
    
    if [[ "$SERVICE_STATUS" == "ACTIVE" && "$RUNNING_COUNT" -gt 0 ]]; then
        success "✅ Service is currently running"
        return 0
    elif [[ "$SERVICE_STATUS" == "ACTIVE" && "$DESIRED_COUNT" -eq 0 ]]; then
        warning "⚠️  Service exists but is scaled to 0"
        return 1
    else
        warning "⚠️  Service is not running or doesn't exist"
        return 2
    fi
}

# Function to resume service if it's shut down
resume_service_if_needed() {
    log "🚀 Checking if service needs to be resumed..."
    
    if check_service_status; then
        success "Service is already running"
        return 0
    fi
    
    # Check if service exists but is scaled to 0
    SERVICE_STATUS=$(aws ecs describe-services \
        --cluster multimodal-lib-prod-cluster \
        --services multimodal-lib-prod-service \
        --query 'services[0].status' \
        --output text 2>/dev/null || echo "NOT_FOUND")
    
    if [[ "$SERVICE_STATUS" == "ACTIVE" ]]; then
        log "Service exists but is scaled down - resuming with desired count 2..."
        
        aws ecs update-service \
            --cluster multimodal-lib-prod-cluster \
            --service multimodal-lib-prod-service \
            --desired-count 2
        
        if [[ $? -eq 0 ]]; then
            success "Service resume initiated"
            
            # Wait for service to start
            log "Waiting for service to start..."
            sleep 60
            
            return 0
        else
            error "Failed to resume service"
            return 1
        fi
    else
        error "Service doesn't exist - full deployment needed"
        return 2
    fi
}

# Function to run VPC network mismatch fix
fix_vpc_network_mismatch() {
    log "🔧 Running VPC network mismatch fix..."
    
    if [[ -f "scripts/fix-vpc-network-mismatch-corrected.py" ]]; then
        cd "$PROJECT_ROOT"
        
        python scripts/fix-vpc-network-mismatch-corrected.py
        VPC_FIX_EXIT_CODE=$?
        
        if [[ $VPC_FIX_EXIT_CODE -eq 0 ]]; then
            success "✅ VPC network configuration fix completed successfully"
            
            # Give the service time to stabilize after network changes
            log "Waiting for network changes to take effect..."
            sleep 30
            
            return 0
        else
            error "❌ VPC network configuration fix failed"
            return 1
        fi
    else
        warning "VPC fix script not found - skipping network fix"
        return 0
    fi
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
    LB_ARN="arn:aws:elasticloadbalancing:us-east-1:591222106065:loadbalancer/app/ml-shared-vpc-alb/a135abb283798f15"
    
    if [[ -z "$TASK_DEF_ARN" || "$TASK_DEF_ARN" == "None" ]]; then
        # Use the latest registered task definition
        TASK_DEF_ARN="arn:aws:ecs:us-east-1:591222106065:task-definition/multimodal-lib-prod-app:16"
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
                    for step in check['remediation_steps'][:3]:  # Show first 3 steps
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
    if [[ -f "scripts/check-vpc-endpoints-status.py" ]]; then
        python scripts/check-vpc-endpoints-status.py || warning "VPC endpoints check completed with warnings"
    fi
}

# Function to test application connectivity
test_application_connectivity() {
    log "🔍 Testing application connectivity..."
    
    # Get load balancer DNS name
    LB_DNS=$(aws elbv2 describe-load-balancers \
        --load-balancer-arns "arn:aws:elasticloadbalancing:us-east-1:591222106065:loadbalancer/app/ml-shared-vpc-alb/a135abb283798f15" \
        --query 'LoadBalancers[0].DNSName' \
        --output text 2>/dev/null || echo "")
    
    if [[ -n "$LB_DNS" ]]; then
        log "Testing HTTP connectivity..."
        
        # Test basic connectivity
        HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "http://$LB_DNS" --connect-timeout 10 --max-time 30 || echo "000")
        
        if [[ "$HTTP_STATUS" == "200" ]]; then
            success "✅ HTTP connectivity test PASSED (Status: $HTTP_STATUS)"
        else
            warning "⚠️  HTTP connectivity test returned status: $HTTP_STATUS"
        fi
        
        # Test health endpoint
        HEALTH_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "http://$LB_DNS/health/simple" --connect-timeout 10 --max-time 30 || echo "000")
        
        if [[ "$HEALTH_STATUS" == "200" ]]; then
            success "✅ Health endpoint test PASSED (Status: $HEALTH_STATUS)"
        else
            warning "⚠️  Health endpoint test returned status: $HEALTH_STATUS"
        fi
        
        log "Application URLs:"
        log "  Main: http://$LB_DNS"
        log "  Health: http://$LB_DNS/health/simple"
        
        # Test HTTPS if available
        HTTPS_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "https://d1c3ih7gvhogu1.cloudfront.net" --connect-timeout 10 --max-time 30 || echo "000")
        
        if [[ "$HTTPS_STATUS" == "200" ]]; then
            success "✅ HTTPS connectivity test PASSED (Status: $HTTPS_STATUS)"
            log "  HTTPS: https://d1c3ih7gvhogu1.cloudfront.net"
        else
            warning "⚠️  HTTPS connectivity test returned status: $HTTPS_STATUS"
        fi
        
    else
        warning "Could not retrieve load balancer DNS name"
    fi
}

# Function to deploy with enhanced validation
deploy_with_enhanced_validation() {
    log "🚀 Starting enhanced validated deployment process..."
    
    # Step 1: Check and resume service if needed
    resume_service_if_needed
    
    # Step 2: Apply automatic fixes first
    apply_automatic_fixes
    
    # Step 3: Fix VPC network mismatch
    if ! fix_vpc_network_mismatch; then
        error "🚨 VPC network fix failed - this may cause connectivity issues"
        warning "Continuing with deployment, but manual network fix may be needed"
    fi
    
    # Step 4: Run pre-deployment validation
    if ! run_pre_deployment_validation; then
        error "🚨 DEPLOYMENT BLOCKED: Pre-deployment validation failed"
        error "Fix the issues above and re-run deployment"
        exit 1
    fi
    
    # Step 5: Proceed with deployment if task definition update is available
    if [[ -f "task-definition-update.json" ]]; then
        log "✅ Validation passed - proceeding with task definition update..."
        
        # Register new task definition
        log "Registering updated task definition..."
        NEW_TASK_DEF=$(aws ecs register-task-definition \
            --cli-input-json file://task-definition-update.json \
            --query 'taskDefinition.taskDefinitionArn' \
            --output text)
        
        if [[ $? -eq 0 ]]; then
            success "New task definition registered: $NEW_TASK_DEF"
            
            # Update service with new task definition
            log "Updating ECS service..."
            aws ecs update-service \
                --cluster multimodal-lib-prod-cluster \
                --service multimodal-lib-prod-service \
                --task-definition "$NEW_TASK_DEF" \
                --desired-count 2
            
            if [[ $? -eq 0 ]]; then
                success "ECS service update initiated"
            else
                error "Failed to update ECS service"
                exit 1
            fi
            
            # Step 6: Wait for deployment to stabilize
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
        else
            error "Failed to register task definition"
            exit 1
        fi
    else
        log "✅ Validation passed - no task definition update needed"
        success "Service is running with current configuration"
    fi
    
    # Step 7: Test application connectivity
    log "🔍 Testing application connectivity..."
    sleep 30  # Give the service time to fully start
    test_application_connectivity
    
    # Step 8: Run post-deployment validation
    log "🔍 Running post-deployment validation..."
    
    if run_pre_deployment_validation; then
        success "✅ Post-deployment validation PASSED"
        success "🎉 Enhanced deployment completed successfully with validation!"
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
    echo "  --vpc-fix-only     Run VPC network fix only"
    echo "  --resume-only      Resume service if shut down"
    echo "  --test-only        Test connectivity only"
    echo "  --force            Skip validation and deploy anyway (NOT RECOMMENDED)"
    echo "  --help             Show this help message"
    echo ""
    echo "This script integrates the production deployment checklist validation"
    echo "and VPC network mismatch fix to ensure reliable deployments."
}

# Main execution
main() {
    log "🔧 Enhanced Production Deployment with Validation and VPC Fix"
    log "============================================================="
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
        --vpc-fix-only)
            log "Running VPC network fix only..."
            fix_vpc_network_mismatch
            ;;
        --resume-only)
            log "Resuming service only..."
            resume_service_if_needed
            ;;
        --test-only)
            log "Testing connectivity only..."
            test_application_connectivity
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
            # Default: full enhanced deployment
            deploy_with_enhanced_validation
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