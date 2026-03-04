#!/bin/bash

# WebSocket Connection Diagnosis Script
# This script implements Task 1 from the functional chat fix specification

set -e

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

echo "🔍 WebSocket Connection Diagnosis"
echo "================================="
echo ""

# Check AWS CLI
log_info "Checking AWS CLI configuration..."
if ! aws sts get-caller-identity > /dev/null 2>&1; then
    log_error "AWS CLI not configured or credentials invalid"
    exit 1
fi
log_success "AWS CLI configured"
echo ""

# Check ECS Service Status
log_info "Checking ECS Service Status..."
echo "Cluster: $CLUSTER_NAME"
echo "Service: $SERVICE_NAME"
echo ""

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
PENDING_COUNT=$(echo "$SERVICE_INFO" | jq -r '.pendingCount')
TASK_DEFINITION=$(echo "$SERVICE_INFO" | jq -r '.taskDefinition')
SERVICE_STATUS=$(echo "$SERVICE_INFO" | jq -r '.status')

echo "Service Status: $SERVICE_STATUS"
echo "Running Tasks: $RUNNING_COUNT"
echo "Desired Tasks: $DESIRED_COUNT"
echo "Pending Tasks: $PENDING_COUNT"
echo "Task Definition: $TASK_DEFINITION"

if [ "$RUNNING_COUNT" -eq 0 ]; then
    log_error "❌ No running tasks - service is failing!"
else
    log_success "✅ Service has running tasks"
fi

# Get deployment information
echo ""
log_info "Deployment Information:"
aws ecs describe-services \
    --cluster "$CLUSTER_NAME" \
    --services "$SERVICE_NAME" \
    --region "$REGION" \
    --query 'services[0].deployments[*].[status,taskDefinition,runningCount,pendingCount,failedTasks,createdAt]' \
    --output table

# Check task failures
echo ""
log_info "Checking for failed tasks..."
FAILED_TASKS=$(aws ecs list-tasks \
    --cluster "$CLUSTER_NAME" \
    --service-name "$SERVICE_NAME" \
    --desired-status STOPPED \
    --region "$REGION" \
    --query 'taskArns' \
    --output text)

if [ -n "$FAILED_TASKS" ] && [ "$FAILED_TASKS" != "None" ]; then
    log_warning "Found failed tasks, checking details..."
    
    # Get details of the most recent failed task
    LATEST_FAILED_TASK=$(echo "$FAILED_TASKS" | tr '\t' '\n' | head -1)
    
    if [ -n "$LATEST_FAILED_TASK" ]; then
        echo ""
        log_info "Latest failed task details:"
        aws ecs describe-tasks \
            --cluster "$CLUSTER_NAME" \
            --tasks "$LATEST_FAILED_TASK" \
            --region "$REGION" \
            --query 'tasks[0].[taskArn,lastStatus,stopCode,stoppedReason,containers[0].exitCode]' \
            --output table
    fi
else
    log_success "No failed tasks found"
fi

# Check ALB Configuration
echo ""
log_info "Checking ALB Configuration..."

ALB_ARN=$(aws elbv2 describe-load-balancers \
    --names "${PROJECT_NAME}-${ENVIRONMENT}" \
    --region "$REGION" \
    --query 'LoadBalancers[0].LoadBalancerArn' \
    --output text 2>/dev/null || echo "None")

if [ "$ALB_ARN" = "None" ]; then
    log_error "ALB ${PROJECT_NAME}-${ENVIRONMENT} not found"
else
    log_success "Found ALB: $ALB_ARN"
    
    # Get ALB DNS name
    ALB_DNS=$(aws elbv2 describe-load-balancers \
        --names "${PROJECT_NAME}-${ENVIRONMENT}" \
        --region "$REGION" \
        --query 'LoadBalancers[0].DNSName' \
        --output text)
    
    echo "ALB DNS: $ALB_DNS"
    
    # Check target group
    TARGET_GROUP_ARN=$(aws elbv2 describe-target-groups \
        --names "${PROJECT_NAME}-${ENVIRONMENT}" \
        --region "$REGION" \
        --query 'TargetGroups[0].TargetGroupArn' \
        --output text 2>/dev/null || echo "None")
    
    if [ "$TARGET_GROUP_ARN" = "None" ]; then
        log_error "Target group ${PROJECT_NAME}-${ENVIRONMENT} not found"
    else
        log_success "Found Target Group: $TARGET_GROUP_ARN"
        
        # Check target health
        echo ""
        log_info "Target Health Status:"
        aws elbv2 describe-target-health \
            --target-group-arn "$TARGET_GROUP_ARN" \
            --region "$REGION" \
            --query 'TargetHealthDescriptions[*].[Target.Id,TargetHealth.State,TargetHealth.Description]' \
            --output table
        
        # Check target group attributes for WebSocket support
        echo ""
        log_info "Target Group Attributes (WebSocket relevant):"
        aws elbv2 describe-target-group-attributes \
            --target-group-arn "$TARGET_GROUP_ARN" \
            --region "$REGION" \
            --query 'Attributes[?Key==`stickiness.enabled` || Key==`stickiness.type` || Key==`stickiness.lb_cookie.duration_seconds`].[Key,Value]' \
            --output table
    fi
    
    # Check listener rules
    echo ""
    log_info "Checking ALB Listener Rules..."
    LISTENER_ARN=$(aws elbv2 describe-listeners \
        --load-balancer-arn "$ALB_ARN" \
        --region "$REGION" \
        --query 'Listeners[0].ListenerArn' \
        --output text)
    
    if [ "$LISTENER_ARN" != "None" ]; then
        aws elbv2 describe-rules \
            --listener-arn "$LISTENER_ARN" \
            --region "$REGION" \
            --query 'Rules[*].[Priority,Conditions[0].Field,Conditions[0].Values[0],Actions[0].Type]' \
            --output table
    fi
fi

# Check CloudWatch Logs
echo ""
log_info "Checking CloudWatch Logs for Errors..."
LOG_GROUP="/ecs/${PROJECT_NAME}-${ENVIRONMENT}"

# Get recent log events (last 10 minutes)
SINCE_TIME=$(date -v-10M -u +%s)000

echo "Searching logs since $(date -v-10M)"
echo "Log Group: $LOG_GROUP"

# Check if log group exists
if aws logs describe-log-groups --log-group-name-prefix "$LOG_GROUP" --region "$REGION" --query 'logGroups[0].logGroupName' --output text | grep -q "$LOG_GROUP"; then
    log_success "Log group exists"
    
    # Get recent errors
    echo ""
    log_info "Recent ERROR logs:"
    aws logs filter-log-events \
        --log-group-name "$LOG_GROUP" \
        --start-time "$SINCE_TIME" \
        --filter-pattern "ERROR" \
        --region "$REGION" \
        --query 'events[*].[logStreamName,message]' \
        --output table \
        --max-items 5 || log_warning "No ERROR logs found or unable to retrieve"
    
    # Get recent WebSocket related logs
    echo ""
    log_info "Recent WebSocket logs:"
    aws logs filter-log-events \
        --log-group-name "$LOG_GROUP" \
        --start-time "$SINCE_TIME" \
        --filter-pattern "WebSocket" \
        --region "$REGION" \
        --query 'events[*].[logStreamName,message]' \
        --output table \
        --max-items 5 || log_warning "No WebSocket logs found"
    
else
    log_warning "Log group $LOG_GROUP not found"
fi

# Test HTTP Endpoints
if [ "$ALB_DNS" != "None" ] && [ -n "$ALB_DNS" ]; then
    echo ""
    log_info "Testing HTTP Endpoints..."
    
    # Test health endpoint
    echo "Testing: http://$ALB_DNS/health"
    if curl -s -f -m 10 "http://$ALB_DNS/health" > /dev/null; then
        log_success "✅ Health endpoint responding"
    else
        log_error "❌ Health endpoint not responding"
    fi
    
    # Test simple health endpoint
    echo "Testing: http://$ALB_DNS/health/simple"
    if curl -s -f -m 10 "http://$ALB_DNS/health/simple" > /dev/null; then
        log_success "✅ Simple health endpoint responding"
    else
        log_error "❌ Simple health endpoint not responding"
    fi
    
    # Test chat status
    echo "Testing: http://$ALB_DNS/chat/status"
    CHAT_STATUS=$(curl -s -m 10 "http://$ALB_DNS/chat/status" 2>/dev/null || echo "failed")
    if [ "$CHAT_STATUS" != "failed" ]; then
        log_success "✅ Chat status endpoint responding"
        echo "$CHAT_STATUS" | jq '.' 2>/dev/null || echo "$CHAT_STATUS"
    else
        log_error "❌ Chat status endpoint not responding"
    fi
fi

# Summary and Recommendations
echo ""
echo "🔍 DIAGNOSIS SUMMARY"
echo "==================="

# Determine main issues
ISSUES=()
RECOMMENDATIONS=()

if [ "$RUNNING_COUNT" -eq 0 ]; then
    ISSUES+=("No running ECS tasks")
    RECOMMENDATIONS+=("Check task definition and container logs")
    RECOMMENDATIONS+=("Verify container image and startup command")
fi

if [ "$ALB_ARN" = "None" ]; then
    ISSUES+=("ALB not found")
    RECOMMENDATIONS+=("Deploy ALB infrastructure")
fi

if [ "$TARGET_GROUP_ARN" = "None" ]; then
    ISSUES+=("Target group not found")
    RECOMMENDATIONS+=("Deploy target group configuration")
fi

# Check if we can test WebSocket
if [ "$ALB_DNS" != "None" ] && [ -n "$ALB_DNS" ] && [ "$RUNNING_COUNT" -gt 0 ]; then
    echo ""
    log_info "🧪 WebSocket Test Available:"
    echo "You can test WebSocket connection with:"
    echo "  python3 scripts/test-websocket-connection.py http://$ALB_DNS"
    echo ""
    echo "🌐 Access URLs:"
    echo "  Chat Interface: http://$ALB_DNS/chat"
    echo "  Health Check: http://$ALB_DNS/health"
    echo "  WebSocket: ws://$ALB_DNS/ws/chat"
fi

if [ ${#ISSUES[@]} -eq 0 ]; then
    log_success "✅ No critical issues detected"
    echo ""
    echo "🚀 Next Steps:"
    echo "1. Test WebSocket connection using the test script"
    echo "2. Monitor CloudWatch logs for any connection issues"
    echo "3. Check browser developer tools for WebSocket errors"
else
    log_error "❌ Issues detected:"
    for issue in "${ISSUES[@]}"; do
        echo "   - $issue"
    done
    
    echo ""
    log_info "💡 Recommendations:"
    for rec in "${RECOMMENDATIONS[@]}"; do
        echo "   - $rec"
    done
    
    echo ""
    echo "🔧 To fix these issues, run:"
    echo "   ./scripts/deploy-websocket-fix.sh"
fi

echo ""
echo "📋 For detailed deployment, run:"
echo "   ./scripts/deploy-websocket-fix.sh --help"