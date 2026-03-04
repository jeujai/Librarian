# Minimal Health Check Fix - Implementation Summary

## Date: 2026-01-18

## Problem Statement

The ALB health checks were timing out even though the application was returning 200 OK responses. The root cause was **middleware interference** with the `/health/simple` endpoint.

### Symptoms
- Application logs showed successful 200 OK responses
- ALB reported `Target.Timeout` errors
- Session middleware errors: "SessionMiddleware must be installed to access request.session"
- Request tracking middleware adding overhead to health checks

### Root Cause Analysis
The `/health/simple` endpoint was registered as a normal route, which meant it went through ALL middleware:
1. **Logging Middleware** - Request/response logging
2. **Authentication Middleware** - Session checks
3. **User Wait Tracking Middleware** - Request tracking
4. **Model Availability Middleware** - Model status checks
5. **Concurrent Request Handler** - Request queuing

Each middleware layer added latency and potential failure points, causing the health check to exceed the ALB timeout threshold.

## Solution Implemented

### Code Changes

**File: `src/multimodal_librarian/main.py`**

Added a minimal health check endpoint **BEFORE** any middleware is registered:

```python
# ============================================================================
# CRITICAL: Add minimal health check endpoint BEFORE any middleware
# This endpoint MUST bypass all middleware to respond immediately for ALB
# ============================================================================
from fastapi import Response

@app.get("/health/simple", include_in_schema=False)
async def alb_health_check():
    """
    Ultra-minimal health check for ALB that bypasses ALL middleware.
    
    CRITICAL REQUIREMENTS:
    - Must be registered BEFORE any middleware
    - Must NOT call get_minimal_server() or any initialization code
    - Must NOT access database, models, or any external services
    - Must return immediately (< 100ms)
    
    This endpoint is specifically designed for AWS ALB health checks
    which require fast, reliable responses without any dependencies.
    """
    return Response(
        content='{"status":"ok","timestamp":"' + datetime.now().isoformat() + '"}',
        media_type="application/json",
        status_code=200
    )
```

### Key Design Decisions

1. **Registered BEFORE Middleware**: The endpoint is registered immediately after the FastAPI app is created, before any `app.add_middleware()` calls

2. **No Dependencies**: The endpoint does NOT:
   - Call `get_minimal_server()`
   - Access any database (OpenSearch, Neptune, PostgreSQL)
   - Check model loading status
   - Use any external services
   - Wait for any initialization

3. **Immediate Response**: Returns a simple JSON response with:
   - Status: "ok"
   - Timestamp: Current ISO timestamp
   - HTTP 200 status code

4. **Excluded from Schema**: `include_in_schema=False` keeps it out of API documentation since it's infrastructure-only

## Deployment Process

### Deployment Script

Created `scripts/deploy-minimal-health-check-fix.py` which:

1. **Rebuilds Docker image** with the fix
2. **Pushes to ECR** (multimodal-librarian-prod repository)
3. **Forces new ECS deployment** with updated image
4. **Waits for deployment** to complete (up to 10 minutes)
5. **Verifies health check** by testing the endpoint 5 times

### Running the Deployment

```bash
python scripts/deploy-minimal-health-check-fix.py
```

## Expected Results

### Before Fix
- ALB health checks: **FAILING** (Target.Timeout)
- Response time: **> 20 seconds** (timeout)
- Middleware errors in logs
- Targets marked as unhealthy

### After Fix
- ALB health checks: **PASSING** (200 OK)
- Response time: **< 100ms** (immediate)
- No middleware errors
- Targets marked as healthy

## Verification Steps

1. **Check Target Health**:
   ```bash
   aws elbv2 describe-target-health \
     --target-group-arn arn:aws:elasticloadbalancing:us-east-1:591222106065:targetgroup/multimodal-lib-prod-tg-v2/7b63a6337a5c7a34 \
     --region us-east-1
   ```

2. **Test Health Endpoint**:
   ```bash
   curl http://multimodal-lib-prod-alb-v2-<id>.us-east-1.elb.amazonaws.com/health/simple
   ```

3. **Check Application Logs**:
   ```bash
   aws logs tail /ecs/multimodal-librarian-prod --follow --region us-east-1
   ```

## Alternative Solutions Considered

### Option 1: Fix Middleware Issues ❌
- **Rejected**: Would require fixing multiple middleware components
- Too complex and risky for immediate fix

### Option 2: Align Both Health Checks to `/api/health/simple` ❌
- **Rejected**: The `/api/health/simple` endpoint still goes through middleware
- Would not solve the underlying timeout issue

### Option 3: Bypass Endpoint (SELECTED) ✅
- **Chosen**: Simplest and most reliable solution
- Minimal code changes
- No risk to existing functionality
- Follows AWS best practices for health checks

## Technical Details

### FastAPI Middleware Order

In FastAPI, middleware is applied in **reverse order** of registration:
1. Last middleware added = First to process request
2. First middleware added = Last to process request

By registering the health check endpoint **before** any middleware, it bypasses the entire middleware stack.

### Why This Works

When a request comes to `/health/simple`:
1. FastAPI router matches the endpoint
2. Endpoint handler executes immediately
3. Response is returned
4. **Middleware is never invoked** for this route

This is different from middleware exclusion patterns, which still invoke middleware but skip processing.

## Monitoring and Alerts

### Metrics to Watch

1. **Target Health Status**: Should be "healthy"
2. **Health Check Response Time**: Should be < 100ms
3. **Health Check Success Rate**: Should be 100%
4. **Application Errors**: Should not see session middleware errors

### CloudWatch Alarms

Consider setting up alarms for:
- Target health check failures
- Health check response time > 1 second
- Unhealthy target count > 0

## Rollback Plan

If the fix doesn't work:

1. **Immediate Rollback**:
   ```bash
   aws ecs update-service \
     --cluster multimodal-librarian-prod-cluster \
     --service multimodal-librarian-prod-service \
     --task-definition <previous-task-definition> \
     --region us-east-1
   ```

2. **Alternative Fix**: Update ALB to use `/api/health/minimal` which has fewer dependencies

## Related Documentation

- **Root Cause Analysis**: `ALB_HEALTH_CHECK_FINAL_DIAGNOSIS.md`
- **Network Diagnosis**: `ALB_CONNECTIVITY_DIAGNOSIS_COMPLETE.md`
- **Health Check Router**: `src/multimodal_librarian/api/routers/health.py`

## Lessons Learned

1. **Health checks must be simple**: No dependencies, no middleware, no external services
2. **Middleware can add significant latency**: Even "lightweight" middleware adds up
3. **ALB timeouts are strict**: 20 seconds is generous, but middleware can exceed it
4. **Test health checks independently**: Don't assume they work because the app works

## Future Improvements

1. **Add health check metrics**: Track response times and success rates
2. **Create dedicated health check router**: Separate from main application routing
3. **Document health check requirements**: Clear guidelines for all health endpoints
4. **Add health check tests**: Automated tests to verify bypass behavior

## Success Criteria

✅ ALB targets show "healthy" status
✅ Health check response time < 100ms
✅ No middleware errors in logs
✅ Application remains accessible via ALB
✅ No impact on existing functionality

## Conclusion

This fix implements a truly minimal health check endpoint that bypasses all middleware, ensuring fast and reliable responses for ALB health checks. The solution is simple, focused, and follows AWS best practices for health check endpoints.
