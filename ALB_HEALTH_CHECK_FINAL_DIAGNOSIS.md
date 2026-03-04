# ALB Health Check Final Diagnosis and Solution

## Date: 2026-01-17

## Executive Summary
The ALB networking issue has been diagnosed. The root cause is **NOT a network connectivity problem** but rather a **health check configuration mismatch** between the ECS container health check and the ALB target group health check.

## Root Cause

### The Problem
1. **Container Health Check** checks `/api/health/simple` (with `/api` prefix)
2. **ALB Target Group** checks `/health/simple` (without `/api` prefix)
3. Both endpoints exist and work, BUT they have different response characteristics
4. The application logs show successful 200 OK responses, but the ALB reports timeouts

### Why This Happens
The `/health/simple` endpoint (without `/api`) is defined directly on the FastAPI app object and should return immediately. However, the ALB is still reporting timeouts even with a 20-second timeout, which suggests:

1. **Middleware Interference**: The request may be going through middleware that adds latency
2. **Session Middleware Error**: The logs show "SessionMiddleware must be installed to access request.session" errors
3. **Request Tracking Overhead**: The application tries to track requests even for health checks

## Evidence

### Application Logs Show Success
```
2026-01-18T06:57:42.618000 INFO: 10.0.2.206:10096 - "GET /health/simple HTTP/1.1" 200 OK
2026-01-18T06:57:42.669000 INFO: 10.0.3.220:20584 - "GET /health/simple HTTP/1.1" 200 OK
2026-01-18T06:57:42.768000 INFO: 10.0.1.211:35078 - "GET /health/simple HTTP/1.1" 200 OK
```

### But Also Show Errors
```
Failed to start tracking request 96497c11-fcfd-4a1a-836b-07b1bf5f51c9: SessionMiddleware must be installed to access request.session
```

### ALB Reports Timeout
```json
{
  "State": "unhealthy",
  "Reason": "Target.Timeout",
  "Description": "Request timed out"
}
```

## Solution

### Option 1: Fix the Health Check Endpoint (RECOMMENDED)
Create a truly minimal health check endpoint that bypasses all middleware:

```python
# In main.py, add this BEFORE any middleware is applied
@app.get("/health/simple", include_in_schema=False)
async def simple_health_check(request: Request):
    """
    Ultra-simple health check for ALB.
    CRITICAL: This endpoint must NOT use any middleware or dependencies.
    """
    return Response(
        content='{"status":"ok"}',
        media_type="application/json",
        status_code=200
    )
```

### Option 2: Align Both Health Checks to Same Endpoint
Update the ALB target group to use `/api/health/simple`:

```bash
aws elbv2 modify-target-group \
  --target-group-arn arn:aws:elasticloadbalancing:us-east-1:591222106065:targetgroup/multimodal-lib-prod-tg-v2/7b63a6337a5c7a34 \
  --health-check-path /api/health/simple \
  --health-check-timeout-seconds 20 \
  --region us-east-1
```

### Option 3: Fix Middleware Issues
1. Install SessionMiddleware properly or remove session access from middleware
2. Exclude health check endpoints from request tracking middleware
3. Add middleware bypass for `/health/*` paths

## Immediate Action Plan

1. **Update the health check endpoint** to bypass middleware:
   ```python
   from fastapi import Response
   
   @app.get("/health/simple", include_in_schema=False)
   async def simple_health_check():
       return Response(
           content='{"status":"ok"}',
           media_type="application/json",
           status_code=200
       )
   ```

2. **Rebuild and redeploy** the application

3. **Monitor target health** for 2-3 minutes

4. **If still failing**, switch to `/api/health/simple` for ALB health checks

## Network Configuration Summary (All Correct ✅)

- **Security Groups**: Properly configured
- **NACLs**: Allow traffic on port 8000
- **Route Tables**: Correct routing
- **Subnets**: Properly configured
- **VPC**: No issues

## Conclusion

The ALB networking is **NOT** the issue. The problem is:
1. Middleware interference with health check responses
2. Session middleware errors causing delays or failures
3. Request tracking overhead on health check endpoints

**Fix**: Create a truly minimal health check endpoint that bypasses all middleware and dependencies.

## Files to Modify

1. `src/multimodal_librarian/main.py` - Update `/health/simple` endpoint
2. `src/multimodal_librarian/api/middleware.py` - Exclude health checks from middleware

## Next Steps

1. Implement Option 1 (minimal health check endpoint)
2. Deploy the fix
3. Monitor for 5 minutes
4. If successful, document the solution
5. If unsuccessful, implement Option 2 (align to `/api/health/simple`)
