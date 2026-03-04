# Startup Optimization Rollback Procedures

This document provides specific rollback procedures for the Application Health and Startup Optimization features.

## Overview

The startup optimization system introduces several new components that may need to be rolled back:
- Multi-phase startup system
- Progressive model loading
- Smart user experience features
- Model caching infrastructure
- Enhanced health checks

## Quick Rollback Decision Matrix

| Issue | Severity | Rollback Action | Timeline |
|-------|----------|----------------|----------|
| Health checks failing | Critical | Revert health check config | 5 minutes |
| Models not loading | High | Disable progressive loading | 10 minutes |
| Startup timeout | High | Increase health check period | 5 minutes |
| Cache corruption | Medium | Clear model cache | 15 minutes |
| UI loading states broken | Low | Disable loading UI features | 10 minutes |
| Fallback responses incorrect | Medium | Disable fallback system | 10 minutes |

## Component-Specific Rollback Procedures

### 1. Health Check Configuration Rollback

#### Symptoms
- ECS tasks failing health checks
- Tasks being killed prematurely
- Service unable to reach stable state

#### Quick Rollback
```bash
#!/bin/bash
# rollback-health-checks.sh

set -e

echo "Rolling back health check configuration..."

# Revert to previous health check settings
aws ecs register-task-definition \
    --family multimodal-librarian-prod \
    --cli-input-json file://task-definition-pre-optimization.json

# Update service to use reverted task definition
aws ecs update-service \
    --cluster multimodal-librarian-prod \
    --service multimodal-librarian-service \
    --task-definition multimodal-librarian-prod:previous \
    --force-new-deployment

echo "Health check configuration rolled back"
```

#### Manual Rollback Steps
1. Open AWS ECS Console
2. Navigate to Task Definitions → multimodal-librarian-prod
3. Select previous revision (before optimization)
4. Click "Create new revision" → "Create"
5. Update service to use previous revision
6. Monitor service stability

#### Verification
```bash
# Verify health checks are passing
aws ecs describe-services \
    --cluster multimodal-librarian-prod \
    --services multimodal-librarian-service \
    --query 'services[0].deployments[0].rolloutState'

# Should return "COMPLETED" when stable
```

### 2. Progressive Model Loading Rollback

#### Symptoms
- Models not loading at all
- Application stuck in MINIMAL phase
- Model loading errors in logs
- Users unable to access AI features

#### Quick Rollback
```python
# scripts/disable-progressive-loading.py

import boto3
import json

def disable_progressive_loading():
    """Disable progressive loading and revert to synchronous loading."""
    
    secrets_client = boto3.client('secretsmanager')
    
    # Get current configuration
    response = secrets_client.get_secret_value(
        SecretId='multimodal-librarian/config'
    )
    
    config = json.loads(response['SecretString'])
    
    # Disable progressive loading
    config['ENABLE_PROGRESSIVE_LOADING'] = 'false'
    config['STARTUP_MODE'] = 'synchronous'
    config['LOAD_ALL_MODELS_ON_STARTUP'] = 'true'
    
    # Update configuration
    secrets_client.update_secret(
        SecretId='multimodal-librarian/config',
        SecretString=json.dumps(config)
    )
    
    print("Progressive loading disabled")
    
    # Force service restart
    ecs_client = boto3.client('ecs')
    ecs_client.update_service(
        cluster='multimodal-librarian-prod',
        service='multimodal-librarian-service',
        forceNewDeployment=True
    )
    
    print("Service restarting with synchronous model loading")

if __name__ == "__main__":
    disable_progressive_loading()
```

#### Environment Variable Rollback
```bash
# Disable progressive loading via environment variables
aws ecs register-task-definition \
    --family multimodal-librarian-prod \
    --container-definitions '[
        {
            "name": "multimodal-librarian",
            "environment": [
                {"name": "ENABLE_PROGRESSIVE_LOADING", "value": "false"},
                {"name": "STARTUP_MODE", "value": "synchronous"},
                {"name": "LOAD_ALL_MODELS_ON_STARTUP", "value": "true"}
            ]
        }
    ]'
```

#### Verification
```bash
# Check model loading status
curl http://internal-lb/api/health/models

# Should show all models loaded synchronously
```

### 3. Model Cache Rollback

#### Symptoms
- Corrupted model files
- Cache loading failures
- Increased startup times
- Model loading errors

#### Quick Cache Clear
```bash
#!/bin/bash
# clear-model-cache.sh

set -e

echo "Clearing model cache..."

# Option 1: Clear EFS cache
if [ -d "/mnt/efs/model-cache" ]; then
    echo "Clearing EFS model cache..."
    rm -rf /mnt/efs/model-cache/*
    echo "EFS cache cleared"
fi

# Option 2: Clear S3 cache
echo "Clearing S3 model cache..."
aws s3 rm s3://multimodal-librarian-model-cache/ --recursive

# Disable cache temporarily
aws secretsmanager update-secret \
    --secret-id multimodal-librarian/config \
    --secret-string '{"ENABLE_MODEL_CACHE": "false"}'

# Restart service to reload models from source
aws ecs update-service \
    --cluster multimodal-librarian-prod \
    --service multimodal-librarian-service \
    --force-new-deployment

echo "Model cache cleared and disabled"
```

#### Selective Cache Invalidation
```python
# scripts/invalidate-cache-selective.py

import boto3
import os

def invalidate_specific_models(model_names: list):
    """Invalidate cache for specific models only."""
    
    s3_client = boto3.client('s3')
    bucket = 'multimodal-librarian-model-cache'
    
    for model_name in model_names:
        # Delete model from S3 cache
        prefix = f"models/{model_name}/"
        
        response = s3_client.list_objects_v2(
            Bucket=bucket,
            Prefix=prefix
        )
        
        if 'Contents' in response:
            for obj in response['Contents']:
                s3_client.delete_object(
                    Bucket=bucket,
                    Key=obj['Key']
                )
                print(f"Deleted cached file: {obj['Key']}")
        
        print(f"Cache invalidated for model: {model_name}")

# Usage
invalidate_specific_models([
    'text-embedding-model',
    'chat-model-large'
])
```

### 4. Smart User Experience Rollback

#### Symptoms
- Incorrect loading states
- Misleading progress indicators
- Fallback responses not working
- UI showing wrong capabilities

#### Disable Loading States
```python
# scripts/disable-loading-states.py

import boto3
import json

def disable_loading_states():
    """Disable smart loading state features."""
    
    secrets_client = boto3.client('secretsmanager')
    
    response = secrets_client.get_secret_value(
        SecretId='multimodal-librarian/config'
    )
    
    config = json.loads(response['SecretString'])
    
    # Disable loading state features
    config['ENABLE_LOADING_STATES'] = 'false'
    config['ENABLE_CAPABILITY_ADVERTISING'] = 'false'
    config['ENABLE_PROGRESS_INDICATORS'] = 'false'
    config['SHOW_SIMPLE_LOADING_ONLY'] = 'true'
    
    secrets_client.update_secret(
        SecretId='multimodal-librarian/config',
        SecretString=json.dumps(config)
    )
    
    print("Loading state features disabled")

if __name__ == "__main__":
    disable_loading_states()
```

#### Disable Fallback Responses
```python
# scripts/disable-fallback-responses.py

import boto3
import json

def disable_fallback_responses():
    """Disable context-aware fallback response system."""
    
    secrets_client = boto3.client('secretsmanager')
    
    response = secrets_client.get_secret_value(
        SecretId='multimodal-librarian/config'
    )
    
    config = json.loads(response['SecretString'])
    
    # Disable fallback system
    config['ENABLE_FALLBACK_RESPONSES'] = 'false'
    config['ENABLE_CONTEXT_AWARE_FALLBACK'] = 'false'
    config['FALLBACK_MODE'] = 'simple'
    
    secrets_client.update_secret(
        SecretId='multimodal-librarian/config',
        SecretString=json.dumps(config)
    )
    
    print("Fallback response system disabled")
    
    # Restart service
    ecs_client = boto3.client('ecs')
    ecs_client.update_service(
        cluster='multimodal-librarian-prod',
        service='multimodal-librarian-service',
        forceNewDeployment=True
    )

if __name__ == "__main__":
    disable_fallback_responses()
```

### 5. Startup Phase Manager Rollback

#### Symptoms
- Application stuck in wrong phase
- Phase transitions not working
- Incorrect phase reporting

#### Reset Phase Manager
```python
# scripts/reset-phase-manager.py

import boto3
import json

def reset_phase_manager():
    """Reset startup phase manager to default state."""
    
    secrets_client = boto3.client('secretsmanager')
    
    response = secrets_client.get_secret_value(
        SecretId='multimodal-librarian/config'
    )
    
    config = json.loads(response['SecretString'])
    
    # Disable phase management
    config['ENABLE_PHASE_MANAGEMENT'] = 'false'
    config['FORCE_FULL_STARTUP'] = 'true'
    config['SKIP_PHASE_TRANSITIONS'] = 'true'
    
    secrets_client.update_secret(
        SecretId='multimodal-librarian/config',
        SecretString=json.dumps(config)
    )
    
    print("Phase manager reset to default state")

if __name__ == "__main__":
    reset_phase_manager()
```

### 6. Monitoring and Alerting Rollback

#### Disable Startup Monitoring
```python
# scripts/disable-startup-monitoring.py

import boto3

def disable_startup_monitoring():
    """Disable startup-specific monitoring and alerting."""
    
    cloudwatch = boto3.client('cloudwatch')
    
    # Disable startup metric alarms
    alarm_names = [
        'startup-phase-timeout',
        'model-loading-failure',
        'health-check-failure',
        'user-wait-time-exceeded'
    ]
    
    for alarm_name in alarm_names:
        try:
            cloudwatch.disable_alarm_actions(
                AlarmNames=[f'multimodal-librarian-{alarm_name}']
            )
            print(f"Disabled alarm: {alarm_name}")
        except Exception as e:
            print(f"Failed to disable alarm {alarm_name}: {e}")
    
    print("Startup monitoring alarms disabled")

if __name__ == "__main__":
    disable_startup_monitoring()
```

## Complete System Rollback

### Full Startup Optimization Rollback Script
```bash
#!/bin/bash
# rollback-startup-optimization.sh

set -e

echo "🔄 Starting complete startup optimization rollback..."

# 1. Backup current state
echo "Step 1: Backing up current configuration..."
./scripts/backup-current-config.sh

# 2. Revert health check configuration
echo "Step 2: Reverting health check configuration..."
./scripts/rollback-health-checks.sh

# 3. Disable progressive loading
echo "Step 3: Disabling progressive loading..."
python scripts/disable-progressive-loading.py

# 4. Clear model cache
echo "Step 4: Clearing model cache..."
./scripts/clear-model-cache.sh

# 5. Disable smart UX features
echo "Step 5: Disabling smart UX features..."
python scripts/disable-loading-states.py
python scripts/disable-fallback-responses.py

# 6. Reset phase manager
echo "Step 6: Resetting phase manager..."
python scripts/reset-phase-manager.py

# 7. Disable startup monitoring
echo "Step 7: Disabling startup monitoring..."
python scripts/disable-startup-monitoring.py

# 8. Deploy pre-optimization version
echo "Step 8: Deploying pre-optimization application version..."
aws ecs update-service \
    --cluster multimodal-librarian-prod \
    --service multimodal-librarian-service \
    --task-definition multimodal-librarian-prod:pre-optimization \
    --force-new-deployment

# 9. Wait for deployment
echo "Step 9: Waiting for deployment to complete..."
aws ecs wait services-stable \
    --cluster multimodal-librarian-prod \
    --services multimodal-librarian-service \
    --max-attempts 20 \
    --delay 30

# 10. Verify rollback
echo "Step 10: Verifying rollback..."
./scripts/verify-startup-rollback.sh

echo "✅ Complete startup optimization rollback completed"
```

### Rollback Verification Script
```python
# scripts/verify-startup-rollback.py

import asyncio
import aiohttp
import logging

async def verify_startup_rollback():
    """Verify that startup optimization rollback was successful."""
    
    base_url = "http://internal-load-balancer"
    
    verification_results = {
        "health_check": False,
        "synchronous_loading": False,
        "no_progressive_features": False,
        "cache_disabled": False
    }
    
    async with aiohttp.ClientSession() as session:
        # 1. Verify health endpoint works
        try:
            async with session.get(f"{base_url}/health") as response:
                if response.status == 200:
                    verification_results["health_check"] = True
                    logging.info("✅ Health check passed")
        except Exception as e:
            logging.error(f"❌ Health check failed: {e}")
        
        # 2. Verify synchronous loading
        try:
            async with session.get(f"{base_url}/api/health/models") as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("loading_mode") == "synchronous":
                        verification_results["synchronous_loading"] = True
                        logging.info("✅ Synchronous loading verified")
        except Exception as e:
            logging.error(f"❌ Synchronous loading verification failed: {e}")
        
        # 3. Verify progressive features disabled
        try:
            async with session.get(f"{base_url}/api/capabilities") as response:
                if response.status == 200:
                    data = await response.json()
                    if not data.get("progressive_loading_enabled"):
                        verification_results["no_progressive_features"] = True
                        logging.info("✅ Progressive features disabled")
        except Exception as e:
            logging.error(f"❌ Progressive features check failed: {e}")
        
        # 4. Verify cache disabled
        try:
            async with session.get(f"{base_url}/api/cache/status") as response:
                if response.status == 200:
                    data = await response.json()
                    if not data.get("cache_enabled"):
                        verification_results["cache_disabled"] = True
                        logging.info("✅ Cache disabled")
        except Exception as e:
            logging.error(f"❌ Cache status check failed: {e}")
    
    # Overall verification
    all_passed = all(verification_results.values())
    
    if all_passed:
        logging.info("✅ All rollback verifications passed")
        return True
    else:
        logging.error("❌ Some rollback verifications failed")
        logging.error(f"Results: {verification_results}")
        return False

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = asyncio.run(verify_startup_rollback())
    exit(0 if result else 1)
```

## Partial Rollback Scenarios

### Scenario 1: Keep Health Checks, Rollback Everything Else
```bash
# Keep optimized health checks but disable other features
python scripts/disable-progressive-loading.py
python scripts/disable-loading-states.py
python scripts/disable-fallback-responses.py
# Do NOT run rollback-health-checks.sh
```

### Scenario 2: Keep Model Cache, Rollback Loading Strategy
```bash
# Keep cache but disable progressive loading
python scripts/disable-progressive-loading.py
python scripts/reset-phase-manager.py
# Do NOT run clear-model-cache.sh
```

### Scenario 3: Keep Backend, Rollback Frontend Only
```bash
# Disable only UI features
python scripts/disable-loading-states.py
# Keep backend progressive loading and health checks
```

## Emergency Procedures

### Emergency Startup Rollback (< 5 minutes)
```bash
#!/bin/bash
# emergency-startup-rollback.sh

set -e

echo "🚨 EMERGENCY STARTUP ROLLBACK 🚨"

# Immediate rollback to last known stable version
aws ecs update-service \
    --cluster multimodal-librarian-prod \
    --service multimodal-librarian-service \
    --task-definition multimodal-librarian-prod:stable \
    --force-new-deployment

# Clear any corrupted cache
aws s3 rm s3://multimodal-librarian-model-cache/ --recursive

# Disable all optimization features
aws secretsmanager update-secret \
    --secret-id multimodal-librarian/config \
    --secret-string '{
        "ENABLE_PROGRESSIVE_LOADING": "false",
        "ENABLE_LOADING_STATES": "false",
        "ENABLE_FALLBACK_RESPONSES": "false",
        "ENABLE_MODEL_CACHE": "false",
        "STARTUP_MODE": "synchronous"
    }'

echo "Emergency rollback initiated - monitoring for stability"
```

## Post-Rollback Actions

### 1. Incident Documentation
```markdown
# Startup Optimization Rollback Incident Report

## Incident Details
- Date/Time: [TIMESTAMP]
- Duration: [DURATION]
- Severity: [Low/Medium/High/Critical]
- Initiated By: [NAME]

## Issue Description
[Detailed description of the issue that triggered rollback]

## Rollback Actions Taken
- [ ] Health check configuration reverted
- [ ] Progressive loading disabled
- [ ] Model cache cleared
- [ ] Smart UX features disabled
- [ ] Phase manager reset
- [ ] Monitoring disabled
- [ ] Application version reverted

## Verification Results
- Health Checks: [✅/❌]
- API Functionality: [✅/❌]
- Model Loading: [✅/❌]
- User Experience: [✅/❌]

## Root Cause Analysis
[Analysis of what went wrong]

## Prevention Measures
[Steps to prevent similar issues]

## Timeline for Re-deployment
[When optimization features will be re-enabled]
```

### 2. Monitoring After Rollback
```bash
# Monitor system stability after rollback
watch -n 30 'aws ecs describe-services \
    --cluster multimodal-librarian-prod \
    --services multimodal-librarian-service \
    --query "services[0].{Status:status,Running:runningCount,Desired:desiredCount,Health:healthCheckGracePeriodSeconds}"'
```

### 3. Re-enable Features Gradually
```bash
# Gradual re-enablement script
#!/bin/bash
# gradual-reenable.sh

# Day 1: Enable health check optimization only
python scripts/enable-health-check-optimization.py

# Day 2: Enable model cache
python scripts/enable-model-cache.py

# Day 3: Enable progressive loading
python scripts/enable-progressive-loading.py

# Day 4: Enable smart UX features
python scripts/enable-loading-states.py
python scripts/enable-fallback-responses.py

# Day 5: Enable full monitoring
python scripts/enable-startup-monitoring.py
```

## Rollback Testing

### Pre-Production Rollback Test
```bash
# Test rollback procedures in staging
./scripts/rollback-startup-optimization.sh --environment staging
./scripts/verify-startup-rollback.sh --environment staging
```

### Rollback Drill Schedule
- Monthly: Practice partial rollbacks
- Quarterly: Practice full system rollback
- Annually: Practice emergency rollback procedures

## Contact Information

### Escalation Path
1. On-call Engineer: [Contact]
2. Team Lead: [Contact]
3. Engineering Manager: [Contact]
4. VP Engineering: [Contact]

### Support Resources
- Runbook: [Link]
- Monitoring Dashboard: [Link]
- Incident Channel: #incidents-prod
- Documentation: [Link]

---

**Last Updated**: [DATE]
**Document Owner**: DevOps Team
**Review Frequency**: Monthly
