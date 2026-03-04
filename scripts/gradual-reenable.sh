#!/bin/bash
# gradual-reenable.sh
# Gradually re-enable startup optimization features after rollback

set -e

ENVIRONMENT="${1:-production}"
PHASE="${2:-1}"

echo "🔄 Gradual Re-enablement of Startup Optimization Features"
echo "Environment: $ENVIRONMENT"
echo "Phase: $PHASE"
echo ""

# Get current configuration
CURRENT_CONFIG=$(aws secretsmanager get-secret-value \
    --secret-id "multimodal-librarian/config" \
    --query 'SecretString' \
    --output text)

case $PHASE in
    1)
        echo "Phase 1: Enable Health Check Optimization Only"
        echo "========================================="
        echo ""
        echo "This phase enables optimized health check configuration"
        echo "without any other startup optimization features."
        echo ""
        
        # Update task definition with optimized health checks
        echo "Updating task definition with optimized health checks..."
        
        # Get current task definition
        CURRENT_TASK_DEF=$(aws ecs describe-services \
            --cluster "multimodal-librarian-$ENVIRONMENT" \
            --services "multimodal-librarian-service" \
            --query 'services[0].taskDefinition' \
            --output text)
        
        # Register new task definition with optimized health checks
        aws ecs describe-task-definition \
            --task-definition "$CURRENT_TASK_DEF" \
            --query 'taskDefinition' > /tmp/task-def.json
        
        # Update health check in task definition
        jq '.containerDefinitions[0].healthCheck = {
            "command": ["CMD-SHELL", "curl -f http://localhost:8000/health/minimal || exit 1"],
            "interval": 30,
            "timeout": 10,
            "retries": 3,
            "startPeriod": 60
        } | del(.taskDefinitionArn, .revision, .status, .requiresAttributes, .compatibilities, .registeredAt, .registeredBy)' \
            /tmp/task-def.json > /tmp/task-def-updated.json
        
        # Register new task definition
        NEW_TASK_DEF=$(aws ecs register-task-definition \
            --cli-input-json file:///tmp/task-def-updated.json \
            --query 'taskDefinition.taskDefinitionArn' \
            --output text)
        
        # Update service
        aws ecs update-service \
            --cluster "multimodal-librarian-$ENVIRONMENT" \
            --service "multimodal-librarian-service" \
            --task-definition "$NEW_TASK_DEF" \
            --force-new-deployment \
            > /dev/null
        
        echo "✅ Health check optimization enabled"
        echo ""
        echo "Monitor for 24 hours before proceeding to Phase 2"
        echo "Next: ./scripts/gradual-reenable.sh $ENVIRONMENT 2"
        ;;
        
    2)
        echo "Phase 2: Enable Model Cache"
        echo "========================================="
        echo ""
        echo "This phase enables model caching to improve startup times"
        echo "while keeping other features disabled."
        echo ""
        
        # Update configuration
        UPDATED_CONFIG=$(echo "$CURRENT_CONFIG" | jq '. + {
            "ENABLE_MODEL_CACHE": "true"
        }')
        
        aws secretsmanager update-secret \
            --secret-id "multimodal-librarian/config" \
            --secret-string "$UPDATED_CONFIG" \
            > /dev/null
        
        # Restart service to pick up new configuration
        aws ecs update-service \
            --cluster "multimodal-librarian-$ENVIRONMENT" \
            --service "multimodal-librarian-service" \
            --force-new-deployment \
            > /dev/null
        
        echo "✅ Model cache enabled"
        echo ""
        echo "Monitor cache performance for 24 hours before proceeding to Phase 3"
        echo "Check cache metrics: aws cloudwatch get-metric-statistics --namespace MultimodalLibrarian --metric-name CacheHitRate"
        echo "Next: ./scripts/gradual-reenable.sh $ENVIRONMENT 3"
        ;;
        
    3)
        echo "Phase 3: Enable Progressive Loading"
        echo "========================================="
        echo ""
        echo "This phase enables progressive model loading and phase management"
        echo "while keeping UI features disabled."
        echo ""
        
        # Update configuration
        UPDATED_CONFIG=$(echo "$CURRENT_CONFIG" | jq '. + {
            "ENABLE_PROGRESSIVE_LOADING": "true",
            "ENABLE_PHASE_MANAGEMENT": "true",
            "STARTUP_MODE": "progressive",
            "LOAD_ALL_MODELS_ON_STARTUP": "false",
            "FORCE_FULL_STARTUP": "false",
            "SKIP_PHASE_TRANSITIONS": "false"
        }')
        
        aws secretsmanager update-secret \
            --secret-id "multimodal-librarian/config" \
            --secret-string "$UPDATED_CONFIG" \
            > /dev/null
        
        # Restart service
        aws ecs update-service \
            --cluster "multimodal-librarian-$ENVIRONMENT" \
            --service "multimodal-librarian-service" \
            --force-new-deployment \
            > /dev/null
        
        echo "✅ Progressive loading enabled"
        echo ""
        echo "Monitor startup phases for 24 hours before proceeding to Phase 4"
        echo "Check phase metrics: aws cloudwatch get-metric-statistics --namespace MultimodalLibrarian --metric-name StartupPhaseTime"
        echo "Next: ./scripts/gradual-reenable.sh $ENVIRONMENT 4"
        ;;
        
    4)
        echo "Phase 4: Enable Smart UX Features"
        echo "========================================="
        echo ""
        echo "This phase enables loading states, capability advertising,"
        echo "and fallback responses."
        echo ""
        
        # Update configuration
        UPDATED_CONFIG=$(echo "$CURRENT_CONFIG" | jq '. + {
            "ENABLE_LOADING_STATES": "true",
            "ENABLE_CAPABILITY_ADVERTISING": "true",
            "ENABLE_PROGRESS_INDICATORS": "true",
            "ENABLE_FALLBACK_RESPONSES": "true",
            "ENABLE_CONTEXT_AWARE_FALLBACK": "true",
            "SHOW_SIMPLE_LOADING_ONLY": "false",
            "FALLBACK_MODE": "context_aware"
        }')
        
        aws secretsmanager update-secret \
            --secret-id "multimodal-librarian/config" \
            --secret-string "$UPDATED_CONFIG" \
            > /dev/null
        
        # Restart service
        aws ecs update-service \
            --cluster "multimodal-librarian-$ENVIRONMENT" \
            --service "multimodal-librarian-service" \
            --force-new-deployment \
            > /dev/null
        
        echo "✅ Smart UX features enabled"
        echo ""
        echo "Monitor user experience metrics for 24 hours before proceeding to Phase 5"
        echo "Check UX metrics: aws cloudwatch get-metric-statistics --namespace MultimodalLibrarian --metric-name UserWaitTime"
        echo "Next: ./scripts/gradual-reenable.sh $ENVIRONMENT 5"
        ;;
        
    5)
        echo "Phase 5: Enable Full Monitoring"
        echo "========================================="
        echo ""
        echo "This phase enables all startup monitoring and alerting."
        echo ""
        
        # Enable CloudWatch alarms
        ALARM_NAMES=(
            "multimodal-librarian-startup-phase-timeout"
            "multimodal-librarian-model-loading-failure"
            "multimodal-librarian-health-check-failure"
            "multimodal-librarian-user-wait-time-exceeded"
        )
        
        for alarm_name in "${ALARM_NAMES[@]}"; do
            if aws cloudwatch describe-alarms --alarm-names "$alarm_name" > /dev/null 2>&1; then
                aws cloudwatch enable-alarm-actions --alarm-names "$alarm_name"
                echo "Enabled alarm: $alarm_name"
            else
                echo "Alarm not found: $alarm_name (may need to be created)"
            fi
        done
        
        # Update configuration to remove emergency mode
        UPDATED_CONFIG=$(echo "$CURRENT_CONFIG" | jq 'del(.EMERGENCY_MODE)')
        
        aws secretsmanager update-secret \
            --secret-id "multimodal-librarian/config" \
            --secret-string "$UPDATED_CONFIG" \
            > /dev/null
        
        echo "✅ Full monitoring enabled"
        echo ""
        echo "🎉 All startup optimization features have been re-enabled!"
        echo ""
        echo "Continue monitoring for 7 days to ensure stability."
        echo "Review metrics dashboard: [Your CloudWatch Dashboard URL]"
        ;;
        
    *)
        echo "❌ Invalid phase: $PHASE"
        echo ""
        echo "Valid phases:"
        echo "  1 - Enable health check optimization"
        echo "  2 - Enable model cache"
        echo "  3 - Enable progressive loading"
        echo "  4 - Enable smart UX features"
        echo "  5 - Enable full monitoring"
        echo ""
        echo "Usage: ./scripts/gradual-reenable.sh <environment> <phase>"
        exit 1
        ;;
esac

# Wait for deployment to complete
echo ""
echo "Waiting for deployment to complete..."
aws ecs wait services-stable \
    --cluster "multimodal-librarian-$ENVIRONMENT" \
    --services "multimodal-librarian-service" \
    --max-attempts 20 \
    --delay 30

echo ""
echo "✅ Deployment completed successfully"
echo ""

# Get service status
SERVICE_STATUS=$(aws ecs describe-services \
    --cluster "multimodal-librarian-$ENVIRONMENT" \
    --services "multimodal-librarian-service" \
    --query 'services[0].{Status:status,Running:runningCount,Desired:desiredCount}')

echo "Service Status:"
echo "$SERVICE_STATUS" | jq .

# Log the re-enablement
mkdir -p logs
echo "Phase $PHASE re-enabled at $(date) for $ENVIRONMENT" >> logs/gradual-reenable.log

echo ""
echo "📋 Monitoring Checklist for Phase $PHASE:"
echo "  [ ] Check application logs for errors"
echo "  [ ] Monitor CloudWatch metrics"
echo "  [ ] Verify health endpoints"
echo "  [ ] Check user-facing functionality"
echo "  [ ] Review performance metrics"
echo "  [ ] Monitor for 24 hours before next phase"
echo ""
