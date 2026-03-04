# Startup Optimization Deployment Guide

This guide explains how to deploy the application with optimized health check configuration for multi-phase startup with progressive model loading.

## Overview

The startup optimization deployment ensures that:
- Health checks are configured for AI-heavy applications with long startup times
- The application uses a multi-phase startup approach (Minimal → Essential → Full)
- Users receive immediate feedback while models load in the background
- ECS tasks are not prematurely terminated during model loading

## Deployment Scripts

### 1. deploy-with-startup-optimization.sh (Bash)

**Location**: `scripts/deploy-with-startup-optimization.sh`

**Usage**:
```bash
./scripts/deploy-with-startup-optimization.sh
```

**Features**:
- Builds and pushes Docker image to ECR
- Updates task definition with optimized health checks
- Updates ALB target group health check configuration
- Deploys to ECS with force new deployment
- Waits for deployment to complete
- Verifies health endpoints

**Environment Variables** (optional):
```bash
export CLUSTER_NAME="multimodal-lib-prod-cluster"
export SERVICE_NAME="multimodal-lib-prod-service"
export TASK_FAMILY="multimodal-lib-prod-app"
export AWS_REGION="us-east-1"
export ECR_REPOSITORY="multimodal-librarian"
```

### 2. deploy-with-startup-optimization.py (Python)

**Location**: `scripts/deploy-with-startup-optimization.py`

**Usage**:
```bash
python scripts/deploy-with-startup-optimization.py
```

**Features**:
- Same functionality as bash script
- Better cross-platform compatibility
- More detailed error handling
- Colored output for better readability

**Requirements**:
- Python 3.7+
- boto3
- requests

### 3. rebuild-and-redeploy.py (Updated)

**Location**: `scripts/rebuild-and-redeploy.py`

**Usage**:
```bash
python scripts/rebuild-and-redeploy.py
```

**Updates**:
- Now includes optimized health check configuration
- Updates both task definition and ALB target group
- Provides startup timeline information

## Health Check Configuration

### Task Definition Health Check

```json
{
  "healthCheck": {
    "command": ["CMD-SHELL", "curl -f http://localhost:8000/api/health/minimal || exit 1"],
    "interval": 30,
    "timeout": 15,
    "retries": 5,
    "startPeriod": 300
  }
}
```

**Parameters**:
- **Path**: `/api/health/minimal` - Basic server readiness check
- **Interval**: 30 seconds - Time between health checks
- **Timeout**: 15 seconds - Maximum time to wait for response
- **Retries**: 5 - Number of consecutive failures before unhealthy
- **Start Period**: 300 seconds (5 minutes) - Grace period for startup

### ALB Target Group Health Check

```
Health Check Path: /api/health/minimal
Interval: 30 seconds
Timeout: 15 seconds
Healthy Threshold: 2
Unhealthy Threshold: 5
```

## Health Endpoints

The application provides three health endpoints for different startup phases:

### 1. /api/health/minimal
- **Purpose**: Basic server readiness
- **Response Time**: < 1 second
- **Available**: 0-30 seconds after startup
- **Indicates**: HTTP server is running and can accept requests

### 2. /api/health/ready
- **Purpose**: Essential models loaded
- **Response Time**: < 2 seconds
- **Available**: 30 seconds - 2 minutes after startup
- **Indicates**: Core functionality is available (80% of requests can be served)

### 3. /api/health/full
- **Purpose**: All models loaded
- **Response Time**: < 2 seconds
- **Available**: 2-5 minutes after startup
- **Indicates**: Full AI capabilities are available

## Startup Timeline

```
0-30 seconds:   Minimal Startup
                ├─ HTTP server starts
                ├─ Basic API endpoints available
                ├─ Health check passes
                └─ Request queuing active

30s-2 minutes:  Essential Models Loading
                ├─ Text embedding model (lightweight)
                ├─ Basic chat model
                ├─ Simple search functionality
                └─ 80% of requests can be served

2-5 minutes:    Full Capability Loading
                ├─ Large language models
                ├─ Multimodal models
                ├─ Complex analysis models
                └─ 100% functionality available
```

## Deployment Process

### Step-by-Step

1. **Pre-flight Checks**
   - Verify AWS CLI is installed
   - Verify Docker is installed
   - Check AWS credentials

2. **Build Docker Image**
   - Build image with latest code
   - Tag with `latest` and timestamp
   - Push to ECR

3. **Update Task Definition**
   - Get current task definition
   - Update container image
   - Update health check configuration
   - Register new task definition

4. **Update ALB Health Check**
   - Find target group
   - Update health check path
   - Update health check parameters

5. **Deploy to ECS**
   - Update service with new task definition
   - Force new deployment
   - Wait for service to stabilize

6. **Verify Deployment**
   - Check service status
   - Verify health endpoints
   - Monitor CloudWatch logs

## Monitoring

### CloudWatch Logs

Monitor startup progress in CloudWatch:
```
Log Group: /ecs/multimodal-lib-prod
```

**Key Log Messages**:
- `Starting minimal server...` - Phase 1 begins
- `Minimal server ready` - Phase 1 complete
- `Loading essential models...` - Phase 2 begins
- `Essential models loaded` - Phase 2 complete
- `Loading full models...` - Phase 3 begins
- `All models loaded` - Phase 3 complete

### CloudWatch Metrics

Monitor these metrics:
- `StartupPhaseCompletionTime` - Time to complete each phase
- `ModelLoadingTime` - Individual model loading times
- `UserWaitTime` - Actual user wait times
- `CacheHitRate` - Model cache effectiveness

### Health Check Status

Check health check status:
```bash
aws elbv2 describe-target-health \
  --target-group-arn <target-group-arn> \
  --region us-east-1
```

## Troubleshooting

### Health Checks Failing

**Symptom**: Tasks are being terminated during startup

**Solution**:
1. Check CloudWatch logs for startup errors
2. Verify health check start period is sufficient (300s)
3. Ensure `/api/health/minimal` endpoint is responding
4. Check container resource limits (CPU/Memory)

### Slow Startup

**Symptom**: Startup takes longer than 5 minutes

**Solution**:
1. Check model cache configuration
2. Verify EFS/S3 connectivity for model cache
3. Review model loading order (essential models first)
4. Check network connectivity to model repositories

### Models Not Loading

**Symptom**: `/api/health/ready` never returns 200

**Solution**:
1. Check CloudWatch logs for model loading errors
2. Verify model cache is accessible
3. Check memory limits (models may be too large)
4. Review model loading configuration

### Deployment Timeout

**Symptom**: Deployment waits indefinitely

**Solution**:
1. Check ECS service events for errors
2. Verify task definition is valid
3. Check security group and network configuration
4. Review CloudWatch logs for startup errors

## Rollback

If deployment fails, rollback to previous version:

```bash
# Get previous task definition
aws ecs describe-task-definition \
  --task-definition multimodal-lib-prod-app \
  --region us-east-1

# Update service to previous version
aws ecs update-service \
  --cluster multimodal-lib-prod-cluster \
  --service multimodal-lib-prod-service \
  --task-definition multimodal-lib-prod-app:<previous-revision> \
  --region us-east-1
```

## Best Practices

1. **Always test in staging first**
   - Deploy to staging environment
   - Verify health checks pass
   - Test all three startup phases

2. **Monitor during deployment**
   - Watch CloudWatch logs in real-time
   - Monitor health check status
   - Check service events

3. **Verify after deployment**
   - Test all health endpoints
   - Verify model loading progress
   - Check user-facing functionality

4. **Keep deployment history**
   - Tag images with timestamps
   - Save deployment results
   - Document any issues

## Configuration Files

### Task Definition Template

See `task-definition-update.json` for the complete task definition with optimized health checks.

### Terraform Configuration

See `infrastructure/aws-native/modules/application/main.tf` for infrastructure-as-code configuration.

## Related Documentation

- [Phase Management](../startup/phase-management.md)
- [Health Check Configuration](../startup/health-check-parameter-adjustments.md)
- [Troubleshooting Guide](../startup/troubleshooting.md)
- [Model Loading Optimization](../startup/model-loading-optimization.md)

## Support

For issues or questions:
1. Check CloudWatch logs
2. Review troubleshooting guide
3. Check ECS service events
4. Contact DevOps team
