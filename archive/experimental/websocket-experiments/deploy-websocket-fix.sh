#!/bin/bash

# Deploy WebSocket Connection Fix
# This script implements the critical path fixes from the functional chat specification

set -e

echo "🔧 Starting WebSocket Connection Fix Deployment"
echo "================================================"

# Configuration
PROJECT_NAME="multimodal-librarian"
ENVIRONMENT="learning"
REGION="us-east-1"
CLUSTER_NAME="${PROJECT_NAME}-${ENVIRONMENT}"
SERVICE_NAME="${PROJECT_NAME}-${ENVIRONMENT}-web"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if AWS CLI is configured
check_aws_cli() {
    log_info "Checking AWS CLI configuration..."
    if ! aws sts get-caller-identity > /dev/null 2>&1; then
        log_error "AWS CLI not configured or credentials invalid"
        exit 1
    fi
    log_success "AWS CLI configured"
}

# Function to get current ECS service status
check_ecs_service() {
    log_info "Checking current ECS service status..."
    
    SERVICE_INFO=$(aws ecs describe-services \
        --cluster "$CLUSTER_NAME" \
        --services "$SERVICE_NAME" \
        --region "$REGION" \
        --query 'services[0]' 2>/dev/null || echo "null")
    
    if [ "$SERVICE_INFO" = "null" ]; then
        log_error "ECS service $SERVICE_NAME not found in cluster $CLUSTER_NAME"
        exit 1
    fi
    
    RUNNING_COUNT=$(echo "$SERVICE_INFO" | jq -r '.runningCount')
    DESIRED_COUNT=$(echo "$SERVICE_INFO" | jq -r '.desiredCount')
    TASK_DEFINITION=$(echo "$SERVICE_INFO" | jq -r '.taskDefinition')
    
    log_info "Service Status:"
    log_info "  Running Tasks: $RUNNING_COUNT"
    log_info "  Desired Tasks: $DESIRED_COUNT"
    log_info "  Task Definition: $TASK_DEFINITION"
    
    if [ "$RUNNING_COUNT" -eq 0 ]; then
        log_warning "No running tasks found - service may be failing"
    fi
}

# Function to get ALB information
check_alb_config() {
    log_info "Checking ALB configuration..."
    
    # Find the load balancer
    ALB_ARN=$(aws elbv2 describe-load-balancers \
        --names "${PROJECT_NAME}-${ENVIRONMENT}" \
        --region "$REGION" \
        --query 'LoadBalancers[0].LoadBalancerArn' \
        --output text 2>/dev/null || echo "None")
    
    if [ "$ALB_ARN" = "None" ]; then
        log_error "ALB ${PROJECT_NAME}-${ENVIRONMENT} not found"
        exit 1
    fi
    
    log_success "Found ALB: $ALB_ARN"
    
    # Get target group information
    TARGET_GROUP_ARN=$(aws elbv2 describe-target-groups \
        --names "${PROJECT_NAME}-${ENVIRONMENT}" \
        --region "$REGION" \
        --query 'TargetGroups[0].TargetGroupArn' \
        --output text 2>/dev/null || echo "None")
    
    if [ "$TARGET_GROUP_ARN" = "None" ]; then
        log_error "Target group ${PROJECT_NAME}-${ENVIRONMENT} not found"
        exit 1
    fi
    
    log_success "Found Target Group: $TARGET_GROUP_ARN"
    
    # Check target health
    log_info "Checking target health..."
    aws elbv2 describe-target-health \
        --target-group-arn "$TARGET_GROUP_ARN" \
        --region "$REGION" \
        --query 'TargetHealthDescriptions[*].[Target.Id,TargetHealth.State,TargetHealth.Description]' \
        --output table
}

# Function to check CloudWatch logs for errors
check_logs() {
    log_info "Checking recent CloudWatch logs for errors..."
    
    LOG_GROUP="/ecs/${PROJECT_NAME}-${ENVIRONMENT}"
    
    # Get recent log events (last 10 minutes)
    SINCE_TIME=$(date -d '10 minutes ago' -u +%s)000
    
    log_info "Searching logs since $(date -d '10 minutes ago')"
    
    aws logs filter-log-events \
        --log-group-name "$LOG_GROUP" \
        --start-time "$SINCE_TIME" \
        --filter-pattern "ERROR" \
        --region "$REGION" \
        --query 'events[*].[logStreamName,message]' \
        --output table \
        --max-items 10 || log_warning "Could not retrieve logs (log group may not exist)"
}

# Function to test WebSocket endpoint
test_websocket() {
    log_info "Testing WebSocket endpoint..."
    
    # Get ALB DNS name
    ALB_DNS=$(aws elbv2 describe-load-balancers \
        --names "${PROJECT_NAME}-${ENVIRONMENT}" \
        --region "$REGION" \
        --query 'LoadBalancers[0].DNSName' \
        --output text)
    
    if [ "$ALB_DNS" != "None" ]; then
        log_info "Testing HTTP endpoint: http://$ALB_DNS/health"
        
        # Test HTTP health endpoint
        if curl -s -f "http://$ALB_DNS/health" > /dev/null; then
            log_success "HTTP health endpoint responding"
        else
            log_warning "HTTP health endpoint not responding"
        fi
        
        # Test chat status endpoint
        log_info "Testing chat status: http://$ALB_DNS/chat/status"
        CHAT_STATUS=$(curl -s "http://$ALB_DNS/chat/status" || echo "failed")
        
        if [ "$CHAT_STATUS" != "failed" ]; then
            log_success "Chat status endpoint responding"
            echo "$CHAT_STATUS" | jq '.' 2>/dev/null || echo "$CHAT_STATUS"
        else
            log_warning "Chat status endpoint not responding"
        fi
        
        log_info "WebSocket URL would be: ws://$ALB_DNS/ws/chat"
    fi
}

# Function to deploy infrastructure updates
deploy_infrastructure() {
    log_info "Deploying ALB WebSocket configuration updates..."
    
    cd infrastructure/learning
    
    # Install dependencies if needed
    if [ ! -d "node_modules" ]; then
        log_info "Installing CDK dependencies..."
        npm install
    fi
    
    # Deploy the stack with WebSocket fixes
    log_info "Deploying infrastructure stack..."
    npx cdk deploy --require-approval never
    
    if [ $? -eq 0 ]; then
        log_success "Infrastructure deployment completed"
    else
        log_error "Infrastructure deployment failed"
        exit 1
    fi
    
    cd ../..
}

# Function to build and deploy enhanced WebSocket image
deploy_enhanced_websocket() {
    log_info "Building enhanced WebSocket Docker image..."
    
    # Build the enhanced image
    docker build -f Dockerfile.enhanced-websocket -t multimodal-librarian-enhanced-websocket .
    
    if [ $? -ne 0 ]; then
        log_error "Docker build failed"
        exit 1
    fi
    
    # Get ECR repository URI
    ECR_URI=$(aws ecr describe-repositories \
        --repository-names "${PROJECT_NAME}-${ENVIRONMENT}" \
        --region "$REGION" \
        --query 'repositories[0].repositoryUri' \
        --output text 2>/dev/null || echo "None")
    
    if [ "$ECR_URI" = "None" ]; then
        log_error "ECR repository not found"
        exit 1
    fi
    
    # Tag and push image
    IMAGE_TAG="enhanced-websocket-$(date +%s)"
    FULL_IMAGE_URI="${ECR_URI}:${IMAGE_TAG}"
    
    log_info "Tagging image: $FULL_IMAGE_URI"
    docker tag multimodal-librarian-enhanced-websocket "$FULL_IMAGE_URI"
    
    log_info "Logging into ECR..."
    aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$ECR_URI"
    
    log_info "Pushing image to ECR..."
    docker push "$FULL_IMAGE_URI"
    
    if [ $? -eq 0 ]; then
        log_success "Image pushed successfully: $FULL_IMAGE_URI"
        echo "$FULL_IMAGE_URI" > .last-enhanced-image
    else
        log_error "Image push failed"
        exit 1
    fi
}

# Function to update ECS service with new image
update_ecs_service() {
    log_info "Updating ECS service with enhanced WebSocket image..."
    
    if [ ! -f ".last-enhanced-image" ]; then
        log_error "No enhanced image found. Run deploy_enhanced_websocket first."
        exit 1
    fi
    
    NEW_IMAGE=$(cat .last-enhanced-image)
    log_info "Using image: $NEW_IMAGE"
    
    # Get current task definition
    CURRENT_TASK_DEF=$(aws ecs describe-services \
        --cluster "$CLUSTER_NAME" \
        --services "$SERVICE_NAME" \
        --region "$REGION" \
        --query 'services[0].taskDefinition' \
        --output text)
    
    log_info "Current task definition: $CURRENT_TASK_DEF"
    
    # Create new task definition with updated image
    TASK_DEF_JSON=$(aws ecs describe-task-definition \
        --task-definition "$CURRENT_TASK_DEF" \
        --region "$REGION" \
        --query 'taskDefinition')
    
    # Update the image in the task definition
    NEW_TASK_DEF=$(echo "$TASK_DEF_JSON" | jq --arg image "$NEW_IMAGE" '
        .containerDefinitions[0].image = $image |
        del(.taskDefinitionArn, .revision, .status, .requiresAttributes, .placementConstraints, .compatibilities, .registeredAt, .registeredBy)
    ')
    
    # Register new task definition
    log_info "Registering new task definition..."
    NEW_TASK_DEF_ARN=$(echo "$NEW_TASK_DEF" | aws ecs register-task-definition \
        --region "$REGION" \
        --cli-input-json file:///dev/stdin \
        --query 'taskDefinition.taskDefinitionArn' \
        --output text)
    
    if [ $? -ne 0 ]; then
        log_error "Failed to register new task definition"
        exit 1
    fi
    
    log_success "New task definition registered: $NEW_TASK_DEF_ARN"
    
    # Update service
    log_info "Updating ECS service..."
    aws ecs update-service \
        --cluster "$CLUSTER_NAME" \
        --service "$SERVICE_NAME" \
        --task-definition "$NEW_TASK_DEF_ARN" \
        --region "$REGION" > /dev/null
    
    if [ $? -eq 0 ]; then
        log_success "ECS service update initiated"
    else
        log_error "ECS service update failed"
        exit 1
    fi
}

# Function to wait for deployment to complete
wait_for_deployment() {
    log_info "Waiting for deployment to complete..."
    
    local max_wait=600  # 10 minutes
    local wait_time=0
    local check_interval=30
    
    while [ $wait_time -lt $max_wait ]; do
        SERVICE_STATUS=$(aws ecs describe-services \
            --cluster "$CLUSTER_NAME" \
            --services "$SERVICE_NAME" \
            --region "$REGION" \
            --query 'services[0].deployments[?status==`PRIMARY`] | [0]')
        
        RUNNING_COUNT=$(echo "$SERVICE_STATUS" | jq -r '.runningCount // 0')
        DESIRED_COUNT=$(echo "$SERVICE_STATUS" | jq -r '.desiredCount // 0')
        
        log_info "Deployment status: $RUNNING_COUNT/$DESIRED_COUNT tasks running"
        
        if [ "$RUNNING_COUNT" -eq "$DESIRED_COUNT" ] && [ "$RUNNING_COUNT" -gt 0 ]; then
            log_success "Deployment completed successfully!"
            return 0
        fi
        
        sleep $check_interval
        wait_time=$((wait_time + check_interval))
    done
    
    log_warning "Deployment did not complete within $max_wait seconds"
    return 1
}

# Function to run post-deployment tests
run_post_deployment_tests() {
    log_info "Running post-deployment tests..."
    
    # Wait a bit for the service to stabilize
    sleep 30
    
    # Test the endpoints
    test_websocket
    
    # Check if enhanced features are available
    ALB_DNS=$(aws elbv2 describe-load-balancers \
        --names "${PROJECT_NAME}-${ENVIRONMENT}" \
        --region "$REGION" \
        --query 'LoadBalancers[0].DNSName' \
        --output text)
    
    if [ "$ALB_DNS" != "None" ]; then
        log_info "Testing enhanced WebSocket features..."
        
        # Test diagnostics endpoint
        DIAGNOSTICS=$(curl -s "http://$ALB_DNS/diagnostics" 2>/dev/null || echo "failed")
        if [ "$DIAGNOSTICS" != "failed" ]; then
            log_success "Enhanced diagnostics endpoint responding"
        else
            log_warning "Enhanced diagnostics endpoint not available"
        fi
    fi
}

# Main execution flow
main() {
    echo "🚀 WebSocket Connection Fix Deployment"
    echo "======================================"
    echo ""
    
    # Parse command line arguments
    SKIP_INFRA=false
    SKIP_IMAGE=false
    SKIP_DEPLOY=false
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --skip-infra)
                SKIP_INFRA=true
                shift
                ;;
            --skip-image)
                SKIP_IMAGE=true
                shift
                ;;
            --skip-deploy)
                SKIP_DEPLOY=true
                shift
                ;;
            --help)
                echo "Usage: $0 [options]"
                echo "Options:"
                echo "  --skip-infra   Skip infrastructure deployment"
                echo "  --skip-image   Skip Docker image build and push"
                echo "  --skip-deploy  Skip ECS service deployment"
                echo "  --help         Show this help message"
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                exit 1
                ;;
        esac
    done
    
    # Step 1: Pre-deployment checks
    log_info "Step 1: Pre-deployment diagnostics"
    check_aws_cli
    check_ecs_service
    check_alb_config
    check_logs
    echo ""
    
    # Step 2: Deploy infrastructure updates (ALB WebSocket config)
    if [ "$SKIP_INFRA" = false ]; then
        log_info "Step 2: Deploying ALB WebSocket configuration"
        deploy_infrastructure
        echo ""
    else
        log_warning "Skipping infrastructure deployment"
    fi
    
    # Step 3: Build and push enhanced WebSocket image
    if [ "$SKIP_IMAGE" = false ]; then
        log_info "Step 3: Building enhanced WebSocket image"
        deploy_enhanced_websocket
        echo ""
    else
        log_warning "Skipping image build"
    fi
    
    # Step 4: Update ECS service
    if [ "$SKIP_DEPLOY" = false ]; then
        log_info "Step 4: Updating ECS service"
        update_ecs_service
        echo ""
        
        # Step 5: Wait for deployment
        log_info "Step 5: Waiting for deployment completion"
        wait_for_deployment
        echo ""
    else
        log_warning "Skipping ECS service deployment"
    fi
    
    # Step 6: Post-deployment testing
    log_info "Step 6: Post-deployment testing"
    run_post_deployment_tests
    echo ""
    
    # Final status
    log_success "WebSocket connection fix deployment completed!"
    echo ""
    echo "🔗 Next steps:"
    echo "1. Test the WebSocket connection in your browser"
    echo "2. Monitor CloudWatch logs for any issues"
    echo "3. Check the diagnostics endpoint for system health"
    echo ""
    
    if [ "$ALB_DNS" != "None" ]; then
        echo "🌐 Access URLs:"
        echo "  Chat Interface: http://$ALB_DNS/chat"
        echo "  Health Check: http://$ALB_DNS/health"
        echo "  Diagnostics: http://$ALB_DNS/diagnostics"
        echo "  WebSocket: ws://$ALB_DNS/ws/chat"
    fi
}

# Create Dockerfile for enhanced WebSocket
create_enhanced_dockerfile() {
    log_info "Creating enhanced WebSocket Dockerfile..."
    
    cat > Dockerfile.enhanced-websocket << 'EOF'
# Enhanced WebSocket Dockerfile
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/
COPY config/ ./config/

# Set Python path
ENV PYTHONPATH=/app/src

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start command with enhanced WebSocket router
CMD ["python", "-m", "uvicorn", "multimodal_librarian.main_enhanced_websocket:app", "--host", "0.0.0.0", "--port", "8000"]
EOF

    log_success "Enhanced WebSocket Dockerfile created"
}

# Create enhanced main application file
create_enhanced_main() {
    log_info "Creating enhanced WebSocket main application..."
    
    mkdir -p src/multimodal_librarian
    
    cat > src/multimodal_librarian/main_enhanced_websocket.py << 'EOF'
"""
Enhanced WebSocket main application for Multimodal Librarian.

This version includes the enhanced WebSocket router with robust connection management.
"""

import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

# Import the enhanced chat router
from .api.routers import chat_enhanced

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Multimodal Librarian - Enhanced WebSocket",
    description="Enhanced WebSocket implementation with robust connection management",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include enhanced chat router
app.include_router(chat_enhanced.router, tags=["Enhanced Chat"])

# Health check endpoints
@app.get("/health")
async def health_check():
    """Simple health check."""
    return {"status": "healthy", "service": "enhanced_websocket"}

@app.get("/health/simple")
async def simple_health():
    """Simple health check for ALB."""
    return {"status": "ok"}

# Root redirect
@app.get("/")
async def root():
    """Redirect to chat interface."""
    return RedirectResponse(url="/chat")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
EOF

    log_success "Enhanced WebSocket main application created"
}

# Check if we need to create the enhanced files
if [ ! -f "Dockerfile.enhanced-websocket" ]; then
    create_enhanced_dockerfile
fi

if [ ! -f "src/multimodal_librarian/main_enhanced_websocket.py" ]; then
    create_enhanced_main
fi

# Run main function
main "$@"