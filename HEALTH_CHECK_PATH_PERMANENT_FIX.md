# Health Check Path - Permanent Fix Applied ✅

## Summary

The deployment scripts have been updated to use the correct health check path permanently, preventing regression on future rebuilds.

## Root Cause

The application has TWO health check endpoints:

1. **`/health/minimal`** - Defined in `src/multimodal_librarian/startup/minimal_server.py` (line 423)
   - Direct app route: `@app.get("/health/minimal")`
   - This is the PRIMARY endpoint used by the minimal server
   
2. **`/api/health/minimal`** - Defined in `src/multimodal_librarian/api/routers/health.py` (line 43)
   - Router with prefix `/api/health` and endpoint `/minimal`
   - This is a SECONDARY endpoint in the health router

## The Issue

The deployment scripts were configured to use `/api/health/minimal`, but the ALB health checks were timing out because:
- The minimal server initializes first and registers `/health/minimal`
- The `/api/health/minimal` endpoint may not be available during early startup
- The ALB needs to check the endpoint that's available earliest

## The Fix

Updated both deployment scripts to use the correct path:

### Files Updated:
1. **`scripts/rebuild-and-redeploy.py`** (line 20)
   - Changed: `HEALTH_CHECK_PATH = "/health/minimal"`
   - Comment added: `# Correct path (no /api prefix) - matches minimal_server.py`

2. **`scripts/deploy-with-startup-optimization.py`** (line 24)
   - Changed: `HEALTH_CHECK_PATH = "/health/minimal"`
   - Comment added: `# Correct path (no /api prefix) - matches minimal_server.py`

## Verification

The fix was already applied to the ALB target group and confirmed working:
- File: `health-check-path-fix-1768534905.json`
- Old path: `/api/health/minimal`
- New path: `/health/minimal`
- Result: Health checks passing, tasks stabilized

## Why This Matters

When you rebuild and redeploy:
1. The deployment scripts will now use `/health/minimal` for:
   - ECS task definition health checks
   - ALB target group health checks
2. This matches the actual endpoint that's available during startup
3. No manual fixes needed after deployment

## Technical Details

The `/health/minimal` endpoint is registered by the minimal server during app initialization:

```python
# src/multimodal_librarian/startup/minimal_server.py (line 423)
@app.get("/health/minimal")
async def minimal_health_check():
    """Minimal health check - basic server readiness."""
    # Returns basic health status
```

This endpoint is available immediately when the app starts, making it ideal for health checks during the startup period.

## Next Steps

No action required! The fix is permanent and will be used on all future deployments.

---

**Status**: ✅ Permanently Fixed
**Date**: 2026-01-16
**Files Modified**: 2 deployment scripts
**Prevents**: Health check failures on rebuild/redeploy
