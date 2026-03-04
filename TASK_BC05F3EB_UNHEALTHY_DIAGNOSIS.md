# Task bc05f3eb9ebb465a9ab1f472b1a4d287 Unhealthy Diagnosis

**Date**: January 18, 2026, 21:03 PST  
**Cluster**: multimodal-lib-prod-cluster  
**Service**: multimodal-lib-prod-service-alb  
**Task ID**: bc05f3eb9ebb465a9ab1f472b1a4d287

## Summary

Task bc05f3eb9ebb465a9ab1f472b1a4d287 went unhealthy and was stopped by ECS due to **ALB health check timeouts**. The task failed to respond to health checks on port 8000 at the `/health/simple` endpoint within the 20-second timeout window.

## Key Findings

### 1. Task Status
- **Last Status**: STOPPED
- **Health Status**: UNHEALTHY
- **Stopped At**: 2026-01-18T21:03:04 PST
- **Stop Reason**: Task failed ELB health checks in target group
- **Stop Code**: ServiceSchedulerInitiated
- **Container Exit Code**: 137 (SIGKILL - forcefully terminated)

### 2. Health Check Failure Details
```
(task bc05f3eb9ebb465a9ab1f472b1a4d287) (port 8000) is unhealthy in 
(target-group multimodal-lib-prod-tg-v2) due to (reason Request timed out)
```

### 3. ALB Target Group Configuration
- **Health Check Path**: `/health/simple`
- **Health Check Interval**: 30 seconds
- **Health Check Timeout**: 20 seconds
- **Healthy Threshold**: 2 consecutive successes
- **Unhealthy Threshold**: 3 consecutive failures
- **Expected Response**: HTTP 200

### 4. Container Health Check Configuration (Task Definition 71)
- **Command**: `curl -f http://localhost:8000/api/health/simple || exit 1`
- **Interval**: 30 seconds
- **Timeout**: 15 seconds
- **Retries**: 5
- **Start Period**: 300 seconds (5 minutes)

### 5. Current Service State
The service is experiencing **continuous health check failures**:
- Multiple tasks are being replaced due to unhealthy status
- Current running tasks (8c081c7d891d42c4a2244e1be7c5826a, 975c1586be434fffb9ba6d23a35330f4) are also showing UNHEALTHY status
- Pattern: Tasks start, fail health checks after ~1-2 minutes, get replaced

## Root Cause Analysis

### Primary Issue: Health Check Endpoint Timeout

The `/health/simple` endpoint is timing out, which suggests one of the following:

1. **Application Not Starting Properly**
   - The FastAPI application may not be binding to port 8000
   - Startup errors preventing the server from listening
   - Database initialization blocking the health check endpoint

2. **Database Connectivity Issues**
   - OpenSearch connection timeout (configured with 5-second timeout)
   - Neptune connection issues
   - PostgreSQL connection problems
   - Health check may be waiting for database connections that never complete

3. **Resource Constraints**
   - Memory: 8GB allocated
   - CPU: 4096 units (4 vCPU)
   - Application may be consuming all resources during startup

4. **Health Check Path Mismatch**
   - Container health check uses: `/api/health/simple`
   - ALB health check uses: `/health/simple`
   - **This is a critical discrepancy!**

## Critical Discovery: Health Check Path Mismatch

The container health check and ALB health check are using **different paths**:
- **Container**: `http://localhost:8000/api/health/simple`
- **ALB**: `http://<target>:8000/health/simple`

This means:
- The container health check might be passing (checking `/api/health/simple`)
- The ALB health check is failing (checking `/health/simple`)
- The application may not have a route handler for `/health/simple` (without `/api` prefix)

## Recommended Actions

### Immediate Fix (Option 1): Update ALB Health Check Path
```bash
aws elbv2 modify-target-group \
  --target-group-arn arn:aws:elasticloadbalancing:us-east-1:591222106065:targetgroup/multimodal-lib-prod-tg-v2/7b63a6337a5c7a34 \
  --health-check-path /api/health/simple \
  --region us-east-1
```

### Immediate Fix (Option 2): Add Route Handler
Add a route handler in the FastAPI application for `/health/simple` (without `/api` prefix) that mirrors the `/api/health/simple` endpoint.

### Investigation Steps

1. **Check Application Logs**
   ```bash
   aws logs tail /ecs/multimodal-lib-prod --since 2h --region us-east-1 --follow
   ```

2. **Verify Route Configuration**
   - Check `src/multimodal_librarian/api/routers/health.py`
   - Verify the health endpoint is registered at both `/health/simple` and `/api/health/simple`

3. **Test Health Endpoint Locally**
   ```bash
   curl http://localhost:8000/health/simple
   curl http://localhost:8000/api/health/simple
   ```

4. **Check Database Connectivity**
   - Verify OpenSearch endpoint is accessible from ECS tasks
   - Verify Neptune endpoint is accessible from ECS tasks
   - Check security group rules

## Related Issues

This is likely related to the ongoing health check issues documented in:
- `.kiro/specs/health-check-database-decoupling/`
- Previous health check fixes in task definitions 68-71
- ALB connectivity issues documented in `.kiro/specs/alb-connectivity-fix/`

## Next Steps

1. Fix the health check path mismatch (highest priority)
2. Review application startup logs to identify any blocking operations
3. Verify database connectivity from ECS tasks
4. Consider implementing the health check database decoupling spec
5. Add monitoring for health check response times
