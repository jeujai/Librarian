#!/bin/bash

# Simple Deployment Script for Learning CI/CD
# This script provides a simplified deployment process for learning purposes

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
    echo "Simple Deployment Script for Learning CI/CD"
    echo ""
    echo "Usage: $0 [OPTIONS] COMMAND"
    echo ""
    echo "Commands:"
    echo "  build       Build and push Docker image"
    echo "  deploy      Deploy application to ECS"
    echo "  infra       Deploy infrastructure with CDK"
    echo "  validate    Validate current deployment"
    echo "  status      Show deployment status"
    echo "  logs        Show application logs"
    echo ""
    echo "Options:"
    echo "  -e, --env ENV       Environment (default: learning)"
    echo "  -r, --region REGION AWS region (default: us-east-1)"
    echo "  -h, --help          Show this help"
    echo ""
    echo "Examples:"
    echo "  $0 build                    # Build and push image"
    echo "  $0 deploy                   # Deploy to ECS"
    echo "  $0 infra                    # Deploy infrastructure"
    echo "  $0 -e dev deploy            # Deploy to dev environment"
    echo ""
}

# Check prerequisites
check_prerequisites() {
    log "Checking prerequisites..."
    
    # Check AWS CLI
    if ! command -v aws &> /dev/null; then
        error "AWS CLI is not installed"
    fi
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        error "Docker is not installed"
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

# Build and push Docker image
build_image() {
    log "Building and pushing Docker image..."
    
    # Login to ECR
    aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com"
    
    # Repository name
    REPO_NAME="$PROJECT_NAME-$ENVIRONMENT"
    ECR_URI="$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$REPO_NAME"
    
    # Generate image tag
    IMAGE_TAG="deploy-$(date +%Y%m%d-%H%M%S)"
    
    info "Building image: $ECR_URI:$IMAGE_TAG"
    
    # Build image
    if [ -f "Dockerfile.learning" ]; then
        docker build -f Dockerfile.learning -t "$ECR_URI:$IMAGE_TAG" .
    else
        docker build -t "$ECR_URI:$IMAGE_TAG" .
    fi
    
    # Tag as latest
    docker tag "$ECR_URI:$IMAGE_TAG" "$ECR_URI:latest"
    
    # Push images
    log "Pushing image to ECR..."
    docker push "$ECR_URI:$IMAGE_TAG"
    docker push "$ECR_URI:latest"
    
    log "Image pushed successfully: $ECR_URI:$IMAGE_TAG"
    
    # Store image info for other commands
    echo "$ECR_URI:$IMAGE_TAG" > .last-image-uri
    echo "$IMAGE_TAG" > .last-image-tag
}

# Deploy infrastructure
deploy_infrastructure() {
    log "Deploying infrastructure..."
    
    # Check if CDK is available
    if ! command -v cdk &> /dev/null; then
        error "AWS CDK is not installed"
    fi
    
    # Check if we're in the right directory
    if [ ! -f "infrastructure/learning/cdk.json" ]; then
        error "Must run from project root directory"
    fi
    
    # Change to CDK directory
    cd infrastructure/learning
    
    # Install dependencies if needed
    if [ ! -d "node_modules" ]; then
        log "Installing CDK dependencies..."
        npm install
    fi
    
    # Show what will change
    info "Previewing infrastructure changes..."
    cdk diff "$STACK_NAME" || warn "CDK diff failed, but continuing"
    
    # Deploy with confirmation
    log "Deploying CDK stack..."
    cdk deploy "$STACK_NAME" \
        --require-approval=any-change \
        --rollback=true \
        --region "$REGION"
    
    # Return to original directory
    cd - > /dev/null
    
    log "Infrastructure deployment completed"
}

# Deploy application to ECS
deploy_application() {
    log "Deploying application to ECS..."
    
    CLUSTER_NAME="$PROJECT_NAME-$ENVIRONMENT"
    
    # Check if cluster exists
    if ! aws ecs describe-clusters --clusters "$CLUSTER_NAME" --region "$REGION" &> /dev/null; then
        error "ECS cluster $CLUSTER_NAME not found. Deploy infrastructure first."
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
    
    # Update each service
    for SERVICE_ARN in $SERVICES; do
        SERVICE_NAME=$(basename "$SERVICE_ARN")
        log "Updating service: $SERVICE_NAME"
        
        # Get current task definition
        CURRENT_TASK_DEF=$(aws ecs describe-services \
            --cluster "$CLUSTER_NAME" \
            --services "$SERVICE_NAME" \
            --region "$REGION" \
            --query 'services[0].taskDefinition' \
            --output text)
        
        info "Current task definition: $CURRENT_TASK_DEF"
        
        # Force new deployment (pulls latest image)
        aws ecs update-service \
            --cluster "$CLUSTER_NAME" \
            --service "$SERVICE_NAME" \
            --force-new-deployment \
            --region "$REGION" > /dev/null
        
        log "Waiting for deployment to stabilize..."
        aws ecs wait services-stable \
            --cluster "$CLUSTER_NAME" \
            --services "$SERVICE_NAME" \
            --region "$REGION"
        
        log "Service $SERVICE_NAME updated successfully"
    done
    
    log "Application deployment completed"
}

# Validate deployment
validate_deployment() {
    log "Validating deployment..."
    
    # Check stack status
    STACK_STATUS=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --region "$REGION" \
        --query 'Stacks[0].StackStatus' \
        --output text 2>/dev/null || echo "NOT_FOUND")
    
    info "Stack status: $STACK_STATUS"
    
    if [ "$STACK_STATUS" = "NOT_FOUND" ]; then
        warn "CloudFormation stack not found"
        return 1
    fi
    
    # Get load balancer URL
    ALB_DNS=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --region "$REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`LoadBalancerDNS`].OutputValue' \
        --output text 2>/dev/null || echo "")
    
    if [ -n "$ALB_DNS" ]; then
        info "Application URL: http://$ALB_DNS"
        
        # Test health endpoint
        log "Testing health endpoint..."
        if curl -f -s "http://$ALB_DNS/health" > /dev/null; then
            log "Health check passed ✅"
        else
            warn "Health check failed ❌"
            warn "Application may still be starting up"
        fi
    else
        warn "No load balancer found"
    fi
    
    # Check ECS service health
    CLUSTER_NAME="$PROJECT_NAME-$ENVIRONMENT"
    if aws ecs describe-clusters --clusters "$CLUSTER_NAME" --region "$REGION" &> /dev/null; then
        RUNNING_TASKS=$(aws ecs list-tasks \
            --cluster "$CLUSTER_NAME" \
            --desired-status RUNNING \
            --region "$REGION" \
            --query 'length(taskArns)')
        
        info "Running ECS tasks: $RUNNING_TASKS"
        
        if [ "$RUNNING_TASKS" -gt 0 ]; then
            log "ECS services are running ✅"
        else
            warn "No running ECS tasks found ❌"
        fi
    else
        warn "ECS cluster not found"
    fi
    
    log "Validation completed"
}

# Show deployment status
show_status() {
    log "Deployment Status for $PROJECT_NAME-$ENVIRONMENT"
    echo ""
    
    # CloudFormation stack
    echo "📋 Infrastructure (CloudFormation):"
    STACK_STATUS=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --region "$REGION" \
        --query 'Stacks[0].StackStatus' \
        --output text 2>/dev/null || echo "NOT_FOUND")
    echo "   Status: $STACK_STATUS"
    
    if [ "$STACK_STATUS" != "NOT_FOUND" ]; then
        STACK_UPDATED=$(aws cloudformation describe-stacks \
            --stack-name "$STACK_NAME" \
            --region "$REGION" \
            --query 'Stacks[0].LastUpdatedTime' \
            --output text 2>/dev/null || echo "N/A")
        echo "   Last Updated: $STACK_UPDATED"
    fi
    
    echo ""
    
    # ECS cluster and services
    echo "🐳 Application (ECS):"
    CLUSTER_NAME="$PROJECT_NAME-$ENVIRONMENT"
    
    if aws ecs describe-clusters --clusters "$CLUSTER_NAME" --region "$REGION" &> /dev/null; then
        CLUSTER_STATUS=$(aws ecs describe-clusters \
            --clusters "$CLUSTER_NAME" \
            --region "$REGION" \
            --query 'clusters[0].status' \
            --output text)
        echo "   Cluster Status: $CLUSTER_STATUS"
        
        RUNNING_TASKS=$(aws ecs list-tasks \
            --cluster "$CLUSTER_NAME" \
            --desired-status RUNNING \
            --region "$REGION" \
            --query 'length(taskArns)')
        echo "   Running Tasks: $RUNNING_TASKS"
        
        # List services
        SERVICES=$(aws ecs list-services \
            --cluster "$CLUSTER_NAME" \
            --region "$REGION" \
            --query 'serviceArns[*]' \
            --output text)
        
        if [ -n "$SERVICES" ]; then
            echo "   Services:"
            for SERVICE_ARN in $SERVICES; do
                SERVICE_NAME=$(basename "$SERVICE_ARN")
                SERVICE_STATUS=$(aws ecs describe-services \
                    --cluster "$CLUSTER_NAME" \
                    --services "$SERVICE_NAME" \
                    --region "$REGION" \
                    --query 'services[0].status' \
                    --output text)
                echo "     - $SERVICE_NAME: $SERVICE_STATUS"
            done
        fi
    else
        echo "   Cluster: NOT_FOUND"
    fi
    
    echo ""
    
    # Load balancer
    echo "🌐 Load Balancer:"
    ALB_DNS=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --region "$REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`LoadBalancerDNS`].OutputValue' \
        --output text 2>/dev/null || echo "")
    
    if [ -n "$ALB_DNS" ]; then
        echo "   URL: http://$ALB_DNS"
        
        # Quick health check
        if curl -f -s "http://$ALB_DNS/health" > /dev/null; then
            echo "   Health: ✅ HEALTHY"
        else
            echo "   Health: ❌ UNHEALTHY"
        fi
    else
        echo "   URL: NOT_FOUND"
    fi
    
    echo ""
}

# Show application logs
show_logs() {
    log "Fetching application logs..."
    
    CLUSTER_NAME="$PROJECT_NAME-$ENVIRONMENT"
    LOG_GROUP="/ecs/$PROJECT_NAME-$ENVIRONMENT"
    
    # Check if log group exists
    if aws logs describe-log-groups \
        --log-group-name-prefix "$LOG_GROUP" \
        --region "$REGION" &> /dev/null; then
        
        info "Showing recent logs from $LOG_GROUP"
        echo ""
        
        # Get recent log events
        aws logs tail "$LOG_GROUP" \
            --since 1h \
            --region "$REGION" \
            --follow
    else
        warn "Log group $LOG_GROUP not found"
        info "Available log groups:"
        aws logs describe-log-groups \
            --region "$REGION" \
            --query 'logGroups[?contains(logGroupName, `ecs`)].logGroupName' \
            --output table
    fi
}

# Parse command line arguments
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
        -h|--help)
            show_usage
            exit 0
            ;;
        build|deploy|infra|validate|status|logs)
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
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "")

# Execute command
case "$COMMAND" in
    build)
        check_prerequisites
        build_image
        ;;
    deploy)
        check_prerequisites
        deploy_application
        validate_deployment
        ;;
    infra)
        check_prerequisites
        deploy_infrastructure
        ;;
    validate)
        check_prerequisites
        validate_deployment
        ;;
    status)
        show_status
        ;;
    logs)
        show_logs
        ;;
    *)
        error "Unknown command: $COMMAND"
        ;;
esac

log "Command '$COMMAND' completed successfully"