#!/bin/bash
# Deploy with Startup Optimization
# This script deploys the application with optimized health check configuration
# for multi-phase startup with progressive model loading

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
CLUSTER_NAME="${CLUSTER_NAME:-multimodal-lib-prod-cluster}"
SERVICE_NAME="${SERVICE_NAME:-multimodal-lib-prod-service}"
TASK_FAMILY="${TASK_FAMILY:-multimodal-lib-prod-app}"
AWS_REGION="${AWS_REGION:-us-east-1}"
ECR_REPOSITORY="${ECR_REPOSITORY:-multimodal-librarian}"

# Health check configuration for startup optimization
HEALTH_CHECK_PATH="/api/health/minimal"
HEALTH_CHECK_INTERVAL=30
HEALTH_CHECK_TIMEOUT=15
HEALTH_CHECK_RETRIES=5
HEALTH_CHECK_START_PERIOD=300  # 5 minutes for AI model loading

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Deployment with Startup Optimization${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "${YELLOW}Configuration:${NC}"
echo -e "  Cluster: ${CLUSTER_NAME}"
echo -e "  Service: ${SERVICE_NAME}"
echo -e "  Task Family: ${TASK_FAMILY}"
echo -e "  Region: ${AWS_REGION}"
echo -e "  Health Check Path: ${HEALTH_CHECK_PATH}"
echo -e "  Health Check Start Period: ${HEALTH_CHECK_START_PERIOD}s"
echo ""

# Function to print status messages
print_status() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

# Function to check if AWS CLI is installed
check_aws_cli() {
    if ! command -v aws &> /dev/null; then
        print_error "AWS CLI is not installed. Please install it first."
        exit 1
    fi
    print_status "AWS CLI is installed"
}

# Function to check if Docker is installed
check_docker() {
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed. Please install it first."
        exit 1
    fi
    print_status "Docker is installed"
}

# Function to get ECR repository URI
get_ecr_repository_uri() {
    print_info "Getting ECR repository URI..."
    
    REPO_URI=$(aws ecr describe-repositories \
        --repository-names "${ECR_REPOSITORY}" \
        --region "${AWS_REGION}" \
        --query 'repositories[0].repositoryUri' \
        --output text 2>/dev/null)
    
    if [ -z "$REPO_URI" ] || [ "$REPO_URI" == "None" ]; then
        print_error "ECR repository '${ECR_REPOSITORY}' not found"
        exit 1
    fi
    
    print_status "ECR repository found: ${REPO_URI}"
    echo "$REPO_URI"
}

# Function to build and push Docker image
build_and_push_image() {
    local repo_uri=$1
    
    print_info "Building Docker image..."
    
    # Get ECR login token
    aws ecr get-login-password --region "${AWS_REGION}" | \
        docker login --username AWS --password-stdin "${repo_uri%/*}" || {
        print_error "Failed to login to ECR"
        exit 1
    }
    print_status "Logged into ECR"
    
    # Build image
    docker build -t "${repo_uri}:latest" . || {
        print_error "Failed to build Docker image"
        exit 1
    }
    print_status "Docker image built successfully"
    
    # Tag with timestamp
    TIMESTAMP=$(date +%Y%m%d-%H%M%S)
    docker tag "${repo_uri}:latest" "${repo_uri}:${TIMESTAMP}"
    print_status "Image tagged with timestamp: ${TIMESTAMP}"
    
    # Push images
    print_info "Pushing Docker images to ECR..."
    docker push "${repo_uri}:latest" || {
        print_error "Failed to push latest image"
        exit 1
    }
    print_status "Pushed latest image"
    
    docker push "${repo_uri}:${TIMESTAMP}" || {
        print_warning "Failed to push timestamped image (non-critical)"
    }
    print_status "Pushed timestamped image"
}

# Function to update task definition with optimized health checks
update_task_definition() {
    local repo_uri=$1
    
    print_info "Updating task definition with optimized health checks..."
    
    # Get current task definition
    CURRENT_TASK_DEF=$(aws ecs describe-task-definition \
        --task-definition "${TASK_FAMILY}" \
        --region "${AWS_REGION}" \
        --query 'taskDefinition' 2>/dev/null)
    
    if [ -z "$CURRENT_TASK_DEF" ] || [ "$CURRENT_TASK_DEF" == "null" ]; then
        print_error "Task definition '${TASK_FAMILY}' not found"
        exit 1
    fi
    
    # Extract necessary fields and update with new health check configuration
    NEW_TASK_DEF=$(echo "$CURRENT_TASK_DEF" | jq --arg image "${repo_uri}:latest" \
        --arg health_path "$HEALTH_CHECK_PATH" \
        --argjson interval "$HEALTH_CHECK_INTERVAL" \
        --argjson timeout "$HEALTH_CHECK_TIMEOUT" \
        --argjson retries "$HEALTH_CHECK_RETRIES" \
        --argjson start_period "$HEALTH_CHECK_START_PERIOD" '
        {
            family: .family,
            taskRoleArn: .taskRoleArn,
            executionRoleArn: .executionRoleArn,
            networkMode: .networkMode,
            requiresCompatibilities: .requiresCompatibilities,
            cpu: .cpu,
            memory: .memory,
            ephemeralStorage: .ephemeralStorage,
            containerDefinitions: [
                .containerDefinitions[0] | 
                .image = $image |
                .healthCheck = {
                    command: ["CMD-SHELL", "curl -f http://localhost:8000\($health_path) || exit 1"],
                    interval: $interval,
                    timeout: $timeout,
                    retries: $retries,
                    startPeriod: $start_period
                }
            ]
        }
    ')
    
    # Register new task definition
    NEW_TASK_DEF_ARN=$(echo "$NEW_TASK_DEF" | \
        aws ecs register-task-definition \
            --cli-input-json file:///dev/stdin \
            --region "${AWS_REGION}" \
            --query 'taskDefinition.taskDefinitionArn' \
            --output text)
    
    if [ -z "$NEW_TASK_DEF_ARN" ]; then
        print_error "Failed to register new task definition"
        exit 1
    fi
    
    print_status "New task definition registered: ${NEW_TASK_DEF_ARN}"
    echo "$NEW_TASK_DEF_ARN"
}

# Function to update ALB target group health check
update_alb_health_check() {
    print_info "Updating ALB target group health check..."
    
    # Find target group for the service
    TARGET_GROUP_ARN=$(aws elbv2 describe-target-groups \
        --region "${AWS_REGION}" \
        --query "TargetGroups[?contains(TargetGroupName, 'multimodal-lib-prod')].TargetGroupArn" \
        --output text 2>/dev/null | head -n1)
    
    if [ -z "$TARGET_GROUP_ARN" ] || [ "$TARGET_GROUP_ARN" == "None" ]; then
        print_warning "Target group not found, skipping ALB health check update"
        return 0
    fi
    
    # Update target group health check
    aws elbv2 modify-target-group \
        --target-group-arn "${TARGET_GROUP_ARN}" \
        --health-check-path "${HEALTH_CHECK_PATH}" \
        --health-check-interval-seconds "${HEALTH_CHECK_INTERVAL}" \
        --health-check-timeout-seconds "${HEALTH_CHECK_TIMEOUT}" \
        --healthy-threshold-count 2 \
        --unhealthy-threshold-count 5 \
        --region "${AWS_REGION}" > /dev/null || {
        print_warning "Failed to update ALB health check (non-critical)"
        return 0
    }
    
    print_status "ALB target group health check updated"
}

# Function to update ECS service
update_ecs_service() {
    local task_def_arn=$1
    
    print_info "Updating ECS service..."
    
    aws ecs update-service \
        --cluster "${CLUSTER_NAME}" \
        --service "${SERVICE_NAME}" \
        --task-definition "${task_def_arn}" \
        --force-new-deployment \
        --region "${AWS_REGION}" > /dev/null || {
        print_error "Failed to update ECS service"
        exit 1
    }
    
    print_status "ECS service update initiated"
}

# Function to wait for deployment to complete
wait_for_deployment() {
    print_info "Waiting for deployment to complete..."
    print_info "This may take 5-10 minutes due to startup optimization..."
    
    # Wait for service to stabilize
    aws ecs wait services-stable \
        --cluster "${CLUSTER_NAME}" \
        --services "${SERVICE_NAME}" \
        --region "${AWS_REGION}" || {
        print_warning "Service stabilization wait timed out"
        print_info "Checking service status manually..."
    }
    
    # Get service status
    SERVICE_STATUS=$(aws ecs describe-services \
        --cluster "${CLUSTER_NAME}" \
        --services "${SERVICE_NAME}" \
        --region "${AWS_REGION}" \
        --query 'services[0]' 2>/dev/null)
    
    RUNNING_COUNT=$(echo "$SERVICE_STATUS" | jq -r '.runningCount')
    DESIRED_COUNT=$(echo "$SERVICE_STATUS" | jq -r '.desiredCount')
    
    echo ""
    print_info "Service Status:"
    echo "  Running tasks: ${RUNNING_COUNT}"
    echo "  Desired tasks: ${DESIRED_COUNT}"
    
    if [ "$RUNNING_COUNT" == "$DESIRED_COUNT" ]; then
        print_status "Deployment completed successfully"
        return 0
    else
        print_warning "Service not fully healthy yet (${RUNNING_COUNT}/${DESIRED_COUNT} tasks)"
        print_info "Tasks may still be starting up. Check CloudWatch logs for details."
        return 1
    fi
}

# Function to verify health endpoints
verify_health_endpoints() {
    print_info "Verifying health endpoints..."
    
    # Get ALB DNS name
    ALB_DNS=$(aws elbv2 describe-load-balancers \
        --region "${AWS_REGION}" \
        --query "LoadBalancers[?contains(LoadBalancerName, 'multimodal-lib-prod')].DNSName" \
        --output text 2>/dev/null | head -n1)
    
    if [ -z "$ALB_DNS" ] || [ "$ALB_DNS" == "None" ]; then
        print_warning "Could not find ALB DNS name"
        return 0
    fi
    
    print_info "Testing health endpoints via ALB: ${ALB_DNS}"
    
    # Test minimal health endpoint
    if curl -f -s "http://${ALB_DNS}${HEALTH_CHECK_PATH}" > /dev/null 2>&1; then
        print_status "Minimal health endpoint responding"
    else
        print_warning "Minimal health endpoint not responding yet"
    fi
    
    # Test ready endpoint
    if curl -f -s "http://${ALB_DNS}/api/health/ready" > /dev/null 2>&1; then
        print_status "Ready health endpoint responding"
    else
        print_info "Ready endpoint not responding (models may still be loading)"
    fi
    
    # Test full endpoint
    if curl -f -s "http://${ALB_DNS}/api/health/full" > /dev/null 2>&1; then
        print_status "Full health endpoint responding"
    else
        print_info "Full endpoint not responding (all models may not be loaded yet)"
    fi
}

# Main deployment flow
main() {
    echo -e "${BLUE}Starting deployment process...${NC}"
    echo ""
    
    # Pre-flight checks
    check_aws_cli
    check_docker
    echo ""
    
    # Get ECR repository
    REPO_URI=$(get_ecr_repository_uri)
    echo ""
    
    # Build and push image
    build_and_push_image "$REPO_URI"
    echo ""
    
    # Update task definition
    TASK_DEF_ARN=$(update_task_definition "$REPO_URI")
    echo ""
    
    # Update ALB health check
    update_alb_health_check
    echo ""
    
    # Update ECS service
    update_ecs_service "$TASK_DEF_ARN"
    echo ""
    
    # Wait for deployment
    wait_for_deployment
    echo ""
    
    # Verify health endpoints
    verify_health_endpoints
    echo ""
    
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}Deployment Complete!${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo -e "${YELLOW}Next Steps:${NC}"
    echo "1. Monitor CloudWatch logs for startup progress"
    echo "2. Check health endpoints:"
    echo "   - /api/health/minimal (basic server ready)"
    echo "   - /api/health/ready (essential models loaded)"
    echo "   - /api/health/full (all models loaded)"
    echo "3. Monitor startup metrics in CloudWatch"
    echo ""
    echo -e "${BLUE}Startup Timeline:${NC}"
    echo "  0-30s:   Minimal startup (basic API ready)"
    echo "  30s-2m:  Essential models loading"
    echo "  2m-5m:   Full capability loading"
    echo ""
}

# Run main function
main
