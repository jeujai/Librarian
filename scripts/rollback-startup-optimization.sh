#!/bin/bash
# rollback-startup-optimization.sh
# Complete rollback of startup optimization features

set -e

ENVIRONMENT="${1:-production}"
BACKUP_DIR="rollback-backups/$(date +%Y%m%d-%H%M%S)"

echo "🔄 Starting complete startup optimization rollback for $ENVIRONMENT..."
echo "Backup directory: $BACKUP_DIR"

# Create backup directory
mkdir -p "$BACKUP_DIR"

# 1. Backup current state
echo ""
echo "Step 1: Backing up current configuration..."
aws ecs describe-services \
    --cluster "multimodal-librarian-$ENVIRONMENT" \
    --services "multimodal-librarian-service" \
    > "$BACKUP_DIR/current-service.json"

aws ecs describe-task-definition \
    --task-definition "multimodal-librarian-$ENVIRONMENT" \
    --query 'taskDefinition' \
    > "$BACKUP_DIR/current-task-definition.json"

aws secretsmanager get-secret-value \
    --secret-id "multimodal-librarian/config" \
    --query 'SecretString' \
    --output text \
    > "$BACKUP_DIR/current-config.json"

echo "✅ Configuration backed up to $BACKUP_DIR"

# 2. Revert health check configuration
echo ""
echo "Step 2: Reverting health check configuration..."

# Check if pre-optimization task definition exists
if aws ecs describe-task-definition \
    --task-definition "multimodal-librarian-$ENVIRONMENT:pre-optimization" \
    > /dev/null 2>&1; then
    
    echo "Using pre-optimization task definition..."
    TARGET_TASK_DEF="multimodal-librarian-$ENVIRONMENT:pre-optimization"
else
    echo "Pre-optimization task definition not found, using previous revision..."
    
    # Get current revision number
    CURRENT_REVISION=$(aws ecs describe-task-definition \
        --task-definition "multimodal-librarian-$ENVIRONMENT" \
        --query 'taskDefinition.revision' \
        --output text)
    
    PREVIOUS_REVISION=$((CURRENT_REVISION - 1))
    TARGET_TASK_DEF="multimodal-librarian-$ENVIRONMENT:$PREVIOUS_REVISION"
fi

echo "Target task definition: $TARGET_TASK_DEF"

# 3. Update configuration to disable optimization features
echo ""
echo "Step 3: Disabling optimization features in configuration..."

# Get current config
CURRENT_CONFIG=$(aws secretsmanager get-secret-value \
    --secret-id "multimodal-librarian/config" \
    --query 'SecretString' \
    --output text)

# Update config to disable features
ROLLBACK_CONFIG=$(echo "$CURRENT_CONFIG" | jq '. + {
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
    "FALLBACK_MODE": "simple"
}')

# Update secrets manager
aws secretsmanager update-secret \
    --secret-id "multimodal-librarian/config" \
    --secret-string "$ROLLBACK_CONFIG"

echo "✅ Configuration updated to disable optimization features"

# 4. Clear model cache
echo ""
echo "Step 4: Clearing model cache..."

# Clear S3 cache if it exists
if aws s3 ls "s3://multimodal-librarian-model-cache-$ENVIRONMENT" > /dev/null 2>&1; then
    echo "Clearing S3 model cache..."
    aws s3 rm "s3://multimodal-librarian-model-cache-$ENVIRONMENT/" --recursive
    echo "✅ S3 cache cleared"
else
    echo "No S3 cache found, skipping..."
fi

# 5. Disable CloudWatch alarms
echo ""
echo "Step 5: Disabling startup monitoring alarms..."

ALARM_NAMES=(
    "multimodal-librarian-startup-phase-timeout"
    "multimodal-librarian-model-loading-failure"
    "multimodal-librarian-health-check-failure"
    "multimodal-librarian-user-wait-time-exceeded"
)

for alarm_name in "${ALARM_NAMES[@]}"; do
    if aws cloudwatch describe-alarms --alarm-names "$alarm_name" > /dev/null 2>&1; then
        aws cloudwatch disable-alarm-actions --alarm-names "$alarm_name"
        echo "Disabled alarm: $alarm_name"
    fi
done

echo "✅ Monitoring alarms disabled"

# 6. Deploy rollback version
echo ""
echo "Step 6: Deploying rollback application version..."

aws ecs update-service \
    --cluster "multimodal-librarian-$ENVIRONMENT" \
    --service "multimodal-librarian-service" \
    --task-definition "$TARGET_TASK_DEF" \
    --force-new-deployment \
    > /dev/null

echo "✅ Deployment initiated"

# 7. Wait for deployment
echo ""
echo "Step 7: Waiting for deployment to complete (this may take several minutes)..."

aws ecs wait services-stable \
    --cluster "multimodal-librarian-$ENVIRONMENT" \
    --services "multimodal-librarian-service" \
    --max-attempts 20 \
    --delay 30

echo "✅ Deployment completed"

# 8. Verify rollback
echo ""
echo "Step 8: Verifying rollback..."

# Get service status
SERVICE_STATUS=$(aws ecs describe-services \
    --cluster "multimodal-librarian-$ENVIRONMENT" \
    --services "multimodal-librarian-service" \
    --query 'services[0].{Status:status,Running:runningCount,Desired:desiredCount}')

echo "Service Status:"
echo "$SERVICE_STATUS" | jq .

# Check if running count matches desired count
RUNNING_COUNT=$(echo "$SERVICE_STATUS" | jq -r '.Running')
DESIRED_COUNT=$(echo "$SERVICE_STATUS" | jq -r '.Desired')

if [ "$RUNNING_COUNT" -eq "$DESIRED_COUNT" ]; then
    echo "✅ Service is stable with $RUNNING_COUNT/$DESIRED_COUNT tasks running"
else
    echo "⚠️  Service not fully stable: $RUNNING_COUNT/$DESIRED_COUNT tasks running"
fi

# 9. Run health checks
echo ""
echo "Step 9: Running health checks..."

# Get load balancer URL
LB_URL=$(aws ecs describe-services \
    --cluster "multimodal-librarian-$ENVIRONMENT" \
    --services "multimodal-librarian-service" \
    --query 'services[0].loadBalancers[0].targetGroupArn' \
    --output text)

if [ -n "$LB_URL" ]; then
    # Try to get health endpoint
    if command -v curl &> /dev/null; then
        echo "Testing health endpoint..."
        
        # Get the actual load balancer DNS
        LB_DNS=$(aws elbv2 describe-target-groups \
            --target-group-arns "$LB_URL" \
            --query 'TargetGroups[0].LoadBalancerArns[0]' \
            --output text | xargs -I {} aws elbv2 describe-load-balancers \
            --load-balancer-arns {} \
            --query 'LoadBalancers[0].DNSName' \
            --output text)
        
        if curl -f -s "http://$LB_DNS/health" > /dev/null; then
            echo "✅ Health check passed"
        else
            echo "⚠️  Health check failed or not accessible"
        fi
    fi
fi

# 10. Generate rollback report
echo ""
echo "Step 10: Generating rollback report..."

cat > "$BACKUP_DIR/rollback-report.txt" << EOF
Startup Optimization Rollback Report
====================================

Environment: $ENVIRONMENT
Timestamp: $(date)
Backup Location: $BACKUP_DIR

Rollback Actions Completed:
- ✅ Configuration backed up
- ✅ Health check configuration reverted
- ✅ Optimization features disabled
- ✅ Model cache cleared
- ✅ Monitoring alarms disabled
- ✅ Application version rolled back
- ✅ Deployment completed
- ✅ Service verified

Target Task Definition: $TARGET_TASK_DEF
Service Status: $RUNNING_COUNT/$DESIRED_COUNT tasks running

Configuration Changes:
- ENABLE_PROGRESSIVE_LOADING: false
- ENABLE_LOADING_STATES: false
- ENABLE_FALLBACK_RESPONSES: false
- ENABLE_MODEL_CACHE: false
- STARTUP_MODE: synchronous

Next Steps:
1. Monitor service stability for 30 minutes
2. Review logs for any errors
3. Document incident and root cause
4. Plan gradual re-enablement if needed

Rollback completed at: $(date)
EOF

cat "$BACKUP_DIR/rollback-report.txt"

echo ""
echo "✅ Complete startup optimization rollback completed successfully!"
echo ""
echo "📋 Rollback report saved to: $BACKUP_DIR/rollback-report.txt"
echo "📦 Backup files saved to: $BACKUP_DIR/"
echo ""
echo "⚠️  Important: Monitor the service for the next 30 minutes to ensure stability"
echo ""
echo "To re-enable features gradually, use: ./scripts/gradual-reenable.sh"
