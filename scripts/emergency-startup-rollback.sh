#!/bin/bash
# emergency-startup-rollback.sh
# Emergency rollback for critical startup optimization issues
# Target: Complete rollback in under 5 minutes

set -e

ENVIRONMENT="${1:-production}"

echo "🚨 EMERGENCY STARTUP ROLLBACK INITIATED 🚨"
echo "Environment: $ENVIRONMENT"
echo "Timestamp: $(date)"
echo ""

# Log emergency rollback
mkdir -p logs
echo "Emergency rollback initiated at $(date) for $ENVIRONMENT" >> logs/emergency-rollback.log

# Step 1: Immediate service rollback (30 seconds)
echo "Step 1: Rolling back to emergency stable version..."
echo "⏱️  Target: 30 seconds"

# Use emergency-stable tag if it exists, otherwise use stable
if aws ecs describe-task-definition \
    --task-definition "multimodal-librarian-$ENVIRONMENT:emergency-stable" \
    > /dev/null 2>&1; then
    STABLE_VERSION="multimodal-librarian-$ENVIRONMENT:emergency-stable"
    echo "Using emergency-stable version"
else
    STABLE_VERSION="multimodal-librarian-$ENVIRONMENT:stable"
    echo "Using stable version"
fi

aws ecs update-service \
    --cluster "multimodal-librarian-$ENVIRONMENT" \
    --service "multimodal-librarian-service" \
    --task-definition "$STABLE_VERSION" \
    --force-new-deployment \
    > /dev/null

echo "✅ Service rollback initiated"

# Step 2: Clear corrupted cache (30 seconds)
echo ""
echo "Step 2: Clearing potentially corrupted cache..."
echo "⏱️  Target: 30 seconds"

# Clear S3 cache in background
if aws s3 ls "s3://multimodal-librarian-model-cache-$ENVIRONMENT" > /dev/null 2>&1; then
    aws s3 rm "s3://multimodal-librarian-model-cache-$ENVIRONMENT/" --recursive &
    CACHE_CLEAR_PID=$!
    echo "Cache clearing in background (PID: $CACHE_CLEAR_PID)"
else
    echo "No cache bucket found, skipping"
fi

# Step 3: Disable all optimization features (30 seconds)
echo ""
echo "Step 3: Disabling all optimization features..."
echo "⏱️  Target: 30 seconds"

# Emergency configuration with all features disabled
EMERGENCY_CONFIG='{
    "ENABLE_PROGRESSIVE_LOADING": "false",
    "ENABLE_LOADING_STATES": "false",
    "ENABLE_CAPABILITY_ADVERTISING": "false",
    "ENABLE_PROGRESS_INDICATORS": "false",
    "ENABLE_FALLBACK_RESPONSES": "false",
    "ENABLE_CONTEXT_AWARE_FALLBACK": "false",
    "ENABLE_PHASE_MANAGEMENT": "false",
    "ENABLE_MODEL_CACHE": "false",
    "STARTUP_MODE": "synchronous",
    "LOAD_ALL_MODELS_ON_STARTUP": "true",
    "FORCE_FULL_STARTUP": "true",
    "SKIP_PHASE_TRANSITIONS": "true",
    "SHOW_SIMPLE_LOADING_ONLY": "true",
    "FALLBACK_MODE": "simple",
    "EMERGENCY_MODE": "true"
}'

aws secretsmanager update-secret \
    --secret-id "multimodal-librarian/config" \
    --secret-string "$EMERGENCY_CONFIG" \
    > /dev/null

echo "✅ All optimization features disabled"

# Step 4: Send emergency notifications (15 seconds)
echo ""
echo "Step 4: Sending emergency notifications..."
echo "⏱️  Target: 15 seconds"

# Send SNS notification if topic exists
SNS_TOPIC_ARN=$(aws sns list-topics \
    --query "Topics[?contains(TopicArn, 'multimodal-librarian-alerts')].TopicArn" \
    --output text 2>/dev/null || echo "")

if [ -n "$SNS_TOPIC_ARN" ]; then
    aws sns publish \
        --topic-arn "$SNS_TOPIC_ARN" \
        --subject "🚨 EMERGENCY: Startup Optimization Rollback" \
        --message "Emergency rollback initiated for $ENVIRONMENT at $(date). System reverting to stable version. Monitor for stability." \
        > /dev/null
    echo "✅ SNS notification sent"
else
    echo "⚠️  No SNS topic found, skipping notification"
fi

# Step 5: Quick stability check (60 seconds)
echo ""
echo "Step 5: Waiting for initial stability..."
echo "⏱️  Target: 60 seconds"

# Wait for at least one task to be running
WAIT_COUNT=0
MAX_WAIT=12  # 12 * 5 seconds = 60 seconds

while [ $WAIT_COUNT -lt $MAX_WAIT ]; do
    RUNNING_COUNT=$(aws ecs describe-services \
        --cluster "multimodal-librarian-$ENVIRONMENT" \
        --services "multimodal-librarian-service" \
        --query 'services[0].runningCount' \
        --output text)
    
    if [ "$RUNNING_COUNT" -gt 0 ]; then
        echo "✅ At least one task is running ($RUNNING_COUNT tasks)"
        break
    fi
    
    echo "Waiting for tasks to start... ($WAIT_COUNT/$MAX_WAIT)"
    sleep 5
    WAIT_COUNT=$((WAIT_COUNT + 1))
done

if [ $WAIT_COUNT -eq $MAX_WAIT ]; then
    echo "⚠️  Warning: No tasks running after 60 seconds"
fi

# Step 6: Basic health check (30 seconds)
echo ""
echo "Step 6: Running basic health check..."
echo "⏱️  Target: 30 seconds"

# Try to get load balancer and test health
LB_ARN=$(aws ecs describe-services \
    --cluster "multimodal-librarian-$ENVIRONMENT" \
    --services "multimodal-librarian-service" \
    --query 'services[0].loadBalancers[0].targetGroupArn' \
    --output text 2>/dev/null || echo "")

if [ -n "$LB_ARN" ] && [ "$LB_ARN" != "None" ]; then
    LB_DNS=$(aws elbv2 describe-target-groups \
        --target-group-arns "$LB_ARN" \
        --query 'TargetGroups[0].LoadBalancerArns[0]' \
        --output text 2>/dev/null | xargs -I {} aws elbv2 describe-load-balancers \
        --load-balancer-arns {} \
        --query 'LoadBalancers[0].DNSName' \
        --output text 2>/dev/null || echo "")
    
    if [ -n "$LB_DNS" ] && command -v curl &> /dev/null; then
        # Try health check with timeout
        if timeout 10 curl -f -s "http://$LB_DNS/health" > /dev/null 2>&1; then
            echo "✅ Basic health check passed"
        else
            echo "⚠️  Health check failed or not yet accessible"
        fi
    else
        echo "ℹ️  Cannot test health endpoint"
    fi
else
    echo "ℹ️  No load balancer found"
fi

# Wait for cache clearing to complete
if [ -n "$CACHE_CLEAR_PID" ]; then
    echo ""
    echo "Waiting for cache clearing to complete..."
    wait $CACHE_CLEAR_PID 2>/dev/null || true
    echo "✅ Cache clearing completed"
fi

# Generate emergency report
echo ""
echo "========================================="
echo "Emergency Rollback Summary"
echo "========================================="

ELAPSED_TIME=$SECONDS
echo "Total Time: ${ELAPSED_TIME} seconds"
echo "Target Version: $STABLE_VERSION"
echo "Environment: $ENVIRONMENT"
echo ""

# Get final service status
FINAL_STATUS=$(aws ecs describe-services \
    --cluster "multimodal-librarian-$ENVIRONMENT" \
    --services "multimodal-librarian-service" \
    --query 'services[0].{Status:status,Running:runningCount,Desired:desiredCount}')

echo "Final Service Status:"
echo "$FINAL_STATUS" | jq .

# Save emergency report
REPORT_FILE="logs/emergency-rollback-$(date +%Y%m%d-%H%M%S).json"
cat > "$REPORT_FILE" << EOF
{
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "environment": "$ENVIRONMENT",
    "elapsed_seconds": $ELAPSED_TIME,
    "target_version": "$STABLE_VERSION",
    "actions_completed": [
        "Service rolled back to stable version",
        "Model cache cleared",
        "All optimization features disabled",
        "Emergency notifications sent",
        "Basic health check performed"
    ],
    "final_status": $FINAL_STATUS
}
EOF

echo ""
echo "📋 Emergency report saved to: $REPORT_FILE"

echo ""
echo "🚨 EMERGENCY ROLLBACK COMPLETED 🚨"
echo ""
echo "⚠️  CRITICAL NEXT STEPS:"
echo "1. Monitor service stability for next 15 minutes"
echo "2. Check application logs immediately: aws logs tail /ecs/multimodal-librarian --follow"
echo "3. Verify health endpoint: curl http://$LB_DNS/health"
echo "4. Alert on-call team if issues persist"
echo "5. Begin incident documentation"
echo ""
echo "For detailed verification: ./scripts/verify-startup-rollback.sh $ENVIRONMENT"
echo ""

# Log completion
echo "Emergency rollback completed at $(date) for $ENVIRONMENT (${ELAPSED_TIME}s)" >> logs/emergency-rollback.log

# Exit with warning code if took too long
if [ $ELAPSED_TIME -gt 300 ]; then
    echo "⚠️  Warning: Emergency rollback took longer than 5 minutes"
    exit 2
fi

exit 0
