# ECS Container Health Check Fix - Design Document

## Overview

This design addresses the ECS container health check failures that cause containers to be killed during startup. The fix aligns the container health check with the ALB health check by using the `/health/simple` endpoint.

## Current Architecture

### Health Check Endpoints

| Endpoint | Purpose | Behavior | HTTP Status |
|----------|---------|----------|-------------|
| `/health/simple` | ALB health check | Always returns OK | 200 |
| `/health/minimal` | ECS container health check | Returns 503 if `health_check_ready=False` | 200/503 |
| `/api/health/minimal` | API health check | Same as `/health/minimal` | 200/503 |

### Current Task Definition Health Check
```json
{
  "healthCheck": {
    "command": ["CMD-SHELL", "curl -f http://localhost:8000/health/minimal || exit 1"],
    "interval": 30,
    "timeout": 15,
    "retries": 5,
    "startPeriod": 300
  }
}
```

### Problem Flow
1. Container starts
2. FastAPI server begins initialization
3. ECS health check runs after `startPeriod` (300s)
4. `/health/minimal` checks `MinimalServer.health_check_ready`
5. If `health_check_ready=False`, returns 503
6. After 5 retries (5 × 30s = 150s), ECS kills container with SIGKILL

## Proposed Solution

### Change 1: Update Task Definition Health Check

Update the ECS task definition to use `/health/simple` instead of `/health/minimal`:

```json
{
  "healthCheck": {
    "command": ["CMD-SHELL", "curl -f http://localhost:8000/health/simple || exit 1"],
    "interval": 30,
    "timeout": 15,
    "retries": 5,
    "startPeriod": 300
  }
}
```

### Rationale

1. **Consistency**: ALB already uses `/health/simple` successfully
2. **Simplicity**: `/health/simple` has no dependencies and always returns 200
3. **Reliability**: Container won't be killed during normal startup
4. **No Code Changes**: Only task definition update required

### Health Check Endpoint Responsibilities

After this change:

| Endpoint | Used By | Purpose |
|----------|---------|---------|
| `/health/simple` | ALB + ECS Container | Basic liveness check |
| `/health/minimal` | Internal monitoring | Startup progress tracking |
| `/api/health/ready` | Kubernetes-style readiness | Model loading status |
| `/api/health/full` | Full system health | All components ready |

## Implementation Plan

### Phase 1: Task Definition Update
1. Create new task definition revision with updated health check command
2. Deploy to ECS service
3. Monitor deployment for stability

### Phase 2: Verification
1. Verify container starts successfully
2. Verify ALB health checks pass
3. Verify no SIGKILL events in CloudWatch logs

## Deployment Script

The deployment will use a Python script that:
1. Gets current task definition
2. Updates health check command to use `/health/simple`
3. Registers new task definition revision
4. Updates ECS service with new task definition
5. Monitors deployment progress

## Rollback Plan

If issues occur:
1. Revert to previous task definition revision
2. Update ECS service with previous revision
3. Monitor for stability

## Correctness Properties

### Property 1: Health Check Endpoint Availability
- **Property**: `/health/simple` endpoint returns HTTP 200 within 5 seconds of server start
- **Test**: Start server, immediately call `/health/simple`, verify 200 response

### Property 2: No Dependency on Initialization
- **Property**: `/health/simple` does not call any initialization code
- **Test**: Code inspection - endpoint must not import or call `get_minimal_server()`

### Property 3: Container Survival
- **Property**: Container is not killed during normal startup (up to 5 minutes)
- **Test**: Deploy and verify no SIGKILL events in first 5 minutes

## Monitoring

After deployment, monitor:
1. ECS task health status
2. ALB target group health
3. CloudWatch logs for health check failures
4. Container restart count
