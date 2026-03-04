#!/bin/bash
# verify-startup-rollback.sh
# Verify that startup optimization rollback was successful

set -e

ENVIRONMENT="${1:-production}"
REPORT_FILE="rollback-verification-$(date +%Y%m%d-%H%M%S).json"

echo "🔍 Verifying startup optimization rollback for $ENVIRONMENT..."
echo ""

# Initialize results
RESULTS='{"timestamp":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'","environment":"'$ENVIRONMENT'","tests":{}}'

# Test 1: Service Health
echo "Test 1: Verifying service health..."
SERVICE_INFO=$(aws ecs describe-services \
    --cluster "multimodal-librarian-$ENVIRONMENT" \
    --services "multimodal-librarian-service" \
    --query 'services[0]')

RUNNING_COUNT=$(echo "$SERVICE_INFO" | jq -r '.runningCount')
DESIRED_COUNT=$(echo "$SERVICE_INFO" | jq -r '.desiredCount')
SERVICE_STATUS=$(echo "$SERVICE_INFO" | jq -r '.status')

if [ "$RUNNING_COUNT" -eq "$DESIRED_COUNT" ] && [ "$SERVICE_STATUS" = "ACTIVE" ]; then
    echo "✅ Service health: PASSED ($RUNNING_COUNT/$DESIRED_COUNT tasks running)"
    RESULTS=$(echo "$RESULTS" | jq '.tests.service_health = {"passed": true, "running": '$RUNNING_COUNT', "desired": '$DESIRED_COUNT'}')
else
    echo "❌ Service health: FAILED ($RUNNING_COUNT/$DESIRED_COUNT tasks running, status: $SERVICE_STATUS)"
    RESULTS=$(echo "$RESULTS" | jq '.tests.service_health = {"passed": false, "running": '$RUNNING_COUNT', "desired": '$DESIRED_COUNT', "status": "'$SERVICE_STATUS'"}')
fi

# Test 2: Configuration Verification
echo ""
echo "Test 2: Verifying configuration rollback..."
CONFIG=$(aws secretsmanager get-secret-value \
    --secret-id "multimodal-librarian/config" \
    --query 'SecretString' \
    --output text)

PROGRESSIVE_LOADING=$(echo "$CONFIG" | jq -r '.ENABLE_PROGRESSIVE_LOADING // "not_set"')
LOADING_STATES=$(echo "$CONFIG" | jq -r '.ENABLE_LOADING_STATES // "not_set"')
FALLBACK_RESPONSES=$(echo "$CONFIG" | jq -r '.ENABLE_FALLBACK_RESPONSES // "not_set"')
MODEL_CACHE=$(echo "$CONFIG" | jq -r '.ENABLE_MODEL_CACHE // "not_set"')
STARTUP_MODE=$(echo "$CONFIG" | jq -r '.STARTUP_MODE // "not_set"')

CONFIG_PASSED=true

if [ "$PROGRESSIVE_LOADING" != "false" ]; then
    echo "❌ Progressive loading not disabled: $PROGRESSIVE_LOADING"
    CONFIG_PASSED=false
else
    echo "✅ Progressive loading disabled"
fi

if [ "$LOADING_STATES" != "false" ]; then
    echo "❌ Loading states not disabled: $LOADING_STATES"
    CONFIG_PASSED=false
else
    echo "✅ Loading states disabled"
fi

if [ "$FALLBACK_RESPONSES" != "false" ]; then
    echo "❌ Fallback responses not disabled: $FALLBACK_RESPONSES"
    CONFIG_PASSED=false
else
    echo "✅ Fallback responses disabled"
fi

if [ "$MODEL_CACHE" != "false" ]; then
    echo "❌ Model cache not disabled: $MODEL_CACHE"
    CONFIG_PASSED=false
else
    echo "✅ Model cache disabled"
fi

if [ "$STARTUP_MODE" != "synchronous" ]; then
    echo "❌ Startup mode not synchronous: $STARTUP_MODE"
    CONFIG_PASSED=false
else
    echo "✅ Startup mode is synchronous"
fi

if [ "$CONFIG_PASSED" = true ]; then
    echo "✅ Configuration verification: PASSED"
    RESULTS=$(echo "$RESULTS" | jq '.tests.configuration = {"passed": true}')
else
    echo "❌ Configuration verification: FAILED"
    RESULTS=$(echo "$RESULTS" | jq '.tests.configuration = {"passed": false}')
fi

# Test 3: Task Definition Verification
echo ""
echo "Test 3: Verifying task definition rollback..."
CURRENT_TASK_DEF=$(echo "$SERVICE_INFO" | jq -r '.taskDefinition')
TASK_DEF_INFO=$(aws ecs describe-task-definition \
    --task-definition "$CURRENT_TASK_DEF" \
    --query 'taskDefinition')

# Check health check configuration
HEALTH_CHECK=$(echo "$TASK_DEF_INFO" | jq -r '.containerDefinitions[0].healthCheck // empty')

if [ -n "$HEALTH_CHECK" ]; then
    START_PERIOD=$(echo "$HEALTH_CHECK" | jq -r '.startPeriod // 0')
    INTERVAL=$(echo "$HEALTH_CHECK" | jq -r '.interval // 0')
    TIMEOUT=$(echo "$HEALTH_CHECK" | jq -r '.timeout // 0')
    
    echo "Health check configuration:"
    echo "  Start period: $START_PERIOD seconds"
    echo "  Interval: $INTERVAL seconds"
    echo "  Timeout: $TIMEOUT seconds"
    
    # Verify it's not the optimized configuration (which would have longer start period)
    if [ "$START_PERIOD" -lt 60 ]; then
        echo "✅ Task definition verification: PASSED (pre-optimization health checks)"
        RESULTS=$(echo "$RESULTS" | jq '.tests.task_definition = {"passed": true, "start_period": '$START_PERIOD'}')
    else
        echo "⚠️  Task definition may still have optimized health checks (start period: $START_PERIOD)"
        RESULTS=$(echo "$RESULTS" | jq '.tests.task_definition = {"passed": false, "start_period": '$START_PERIOD', "note": "Still using optimized health checks"}')
    fi
else
    echo "⚠️  No health check configuration found"
    RESULTS=$(echo "$RESULTS" | jq '.tests.task_definition = {"passed": false, "note": "No health check found"}')
fi

# Test 4: Alarm Status
echo ""
echo "Test 4: Verifying monitoring alarms disabled..."
ALARM_NAMES=(
    "multimodal-librarian-startup-phase-timeout"
    "multimodal-librarian-model-loading-failure"
    "multimodal-librarian-health-check-failure"
    "multimodal-librarian-user-wait-time-exceeded"
)

ALARMS_DISABLED=true
for alarm_name in "${ALARM_NAMES[@]}"; do
    if aws cloudwatch describe-alarms --alarm-names "$alarm_name" > /dev/null 2>&1; then
        ACTIONS_ENABLED=$(aws cloudwatch describe-alarms \
            --alarm-names "$alarm_name" \
            --query 'MetricAlarms[0].ActionsEnabled' \
            --output text)
        
        if [ "$ACTIONS_ENABLED" = "False" ]; then
            echo "✅ Alarm disabled: $alarm_name"
        else
            echo "❌ Alarm still enabled: $alarm_name"
            ALARMS_DISABLED=false
        fi
    else
        echo "ℹ️  Alarm not found: $alarm_name (may not have been created)"
    fi
done

if [ "$ALARMS_DISABLED" = true ]; then
    echo "✅ Alarm verification: PASSED"
    RESULTS=$(echo "$RESULTS" | jq '.tests.alarms = {"passed": true}')
else
    echo "❌ Alarm verification: FAILED"
    RESULTS=$(echo "$RESULTS" | jq '.tests.alarms = {"passed": false}')
fi

# Test 5: Cache Status
echo ""
echo "Test 5: Verifying model cache cleared..."
if aws s3 ls "s3://multimodal-librarian-model-cache-$ENVIRONMENT" > /dev/null 2>&1; then
    CACHE_OBJECTS=$(aws s3 ls "s3://multimodal-librarian-model-cache-$ENVIRONMENT/" --recursive | wc -l)
    
    if [ "$CACHE_OBJECTS" -eq 0 ]; then
        echo "✅ Cache verification: PASSED (cache is empty)"
        RESULTS=$(echo "$RESULTS" | jq '.tests.cache = {"passed": true, "objects": 0}')
    else
        echo "⚠️  Cache verification: WARNING ($CACHE_OBJECTS objects still in cache)"
        RESULTS=$(echo "$RESULTS" | jq '.tests.cache = {"passed": false, "objects": '$CACHE_OBJECTS'}')
    fi
else
    echo "ℹ️  Cache bucket not found (may not have been created)"
    RESULTS=$(echo "$RESULTS" | jq '.tests.cache = {"passed": true, "note": "Cache bucket not found"}')
fi

# Test 6: Application Health Endpoint
echo ""
echo "Test 6: Testing application health endpoint..."

# Get load balancer DNS
LB_ARN=$(echo "$SERVICE_INFO" | jq -r '.loadBalancers[0].targetGroupArn // empty')

if [ -n "$LB_ARN" ]; then
    LB_DNS=$(aws elbv2 describe-target-groups \
        --target-group-arns "$LB_ARN" \
        --query 'TargetGroups[0].LoadBalancerArns[0]' \
        --output text 2>/dev/null | xargs -I {} aws elbv2 describe-load-balancers \
        --load-balancer-arns {} \
        --query 'LoadBalancers[0].DNSName' \
        --output text 2>/dev/null)
    
    if [ -n "$LB_DNS" ] && command -v curl &> /dev/null; then
        echo "Testing health endpoint at: http://$LB_DNS/health"
        
        if HEALTH_RESPONSE=$(curl -f -s -m 10 "http://$LB_DNS/health" 2>/dev/null); then
            echo "✅ Health endpoint: PASSED"
            echo "Response: $HEALTH_RESPONSE"
            RESULTS=$(echo "$RESULTS" | jq '.tests.health_endpoint = {"passed": true, "response": "'"$HEALTH_RESPONSE"'"}')
        else
            echo "❌ Health endpoint: FAILED (not accessible or returned error)"
            RESULTS=$(echo "$RESULTS" | jq '.tests.health_endpoint = {"passed": false, "note": "Endpoint not accessible"}')
        fi
    else
        echo "ℹ️  Cannot test health endpoint (curl not available or DNS not found)"
        RESULTS=$(echo "$RESULTS" | jq '.tests.health_endpoint = {"passed": null, "note": "Cannot test"}')
    fi
else
    echo "ℹ️  No load balancer found for service"
    RESULTS=$(echo "$RESULTS" | jq '.tests.health_endpoint = {"passed": null, "note": "No load balancer"}')
fi

# Calculate overall result
echo ""
echo "========================================="
echo "Verification Summary"
echo "========================================="

OVERALL_PASSED=$(echo "$RESULTS" | jq '[.tests[] | select(.passed == true)] | length')
OVERALL_FAILED=$(echo "$RESULTS" | jq '[.tests[] | select(.passed == false)] | length')
OVERALL_TOTAL=$(echo "$RESULTS" | jq '.tests | length')

echo "Tests Passed: $OVERALL_PASSED"
echo "Tests Failed: $OVERALL_FAILED"
echo "Total Tests: $OVERALL_TOTAL"

if [ "$OVERALL_FAILED" -eq 0 ]; then
    echo ""
    echo "✅ Overall Verification: PASSED"
    RESULTS=$(echo "$RESULTS" | jq '.overall_result = "PASSED"')
    EXIT_CODE=0
else
    echo ""
    echo "❌ Overall Verification: FAILED"
    RESULTS=$(echo "$RESULTS" | jq '.overall_result = "FAILED"')
    EXIT_CODE=1
fi

# Save results
echo "$RESULTS" | jq . > "$REPORT_FILE"
echo ""
echo "📋 Verification report saved to: $REPORT_FILE"

# Display recommendations
echo ""
echo "========================================="
echo "Recommendations"
echo "========================================="

if [ "$EXIT_CODE" -eq 0 ]; then
    echo "✅ Rollback verification successful!"
    echo ""
    echo "Next steps:"
    echo "1. Monitor service for 30 minutes to ensure stability"
    echo "2. Review application logs for any errors"
    echo "3. Document the incident and root cause"
    echo "4. Plan gradual re-enablement if needed"
else
    echo "⚠️  Rollback verification found issues!"
    echo ""
    echo "Recommended actions:"
    echo "1. Review failed tests above"
    echo "2. Check application logs for errors"
    echo "3. Verify ECS service status in AWS Console"
    echo "4. Consider running emergency rollback if critical"
    echo ""
    echo "For emergency rollback: ./scripts/emergency-startup-rollback.sh"
fi

echo ""
exit $EXIT_CODE
