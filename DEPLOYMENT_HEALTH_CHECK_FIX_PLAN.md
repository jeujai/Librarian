# Deployment Health Check Fix Plan

## Current Situation

The application is failing health checks in production with this pattern:
1. Container starts
2. Models load successfully (we see these logs)
3. **Complete silence** - no more logs
4. Health check times out after 60 seconds
5. ECS kills the container and restarts

## The Problem

We implemented comprehensive logging from the application-health-startup-optimization spec, but it only logged **inside** components (model loading, database connections, etc.). We completely missed logging at the **orchestration layer** where these components are initialized in `main.py`.

When the startup event hangs, we have zero visibility into which initialization step is the problem.

## The Fix

Added comprehensive orchestration-level logging to `main.py` with:

1. **10 numbered steps** - Each initialization step is clearly numbered and logged
2. **Timeout protection** - Every async call has a timeout (10-120 seconds depending on expected duration)
3. **Visual markers** - ✓ for success, ✗ for failure, ⚠ for warnings
4. **Clear error messages** - Timeout messages explicitly state which component hung
5. **Final confirmation** - Explicit log when startup completes successfully

## Deployment Plan

### Phase 1: Deploy the Fix (Immediate)

```bash
# Deploy the logging fix
python scripts/deploy-startup-logging-fix.py
```

This will:
- Build a new Docker image with comprehensive logging
- Push to ECR
- Update ECS service
- Monitor deployment

### Phase 2: Identify the Problem (5-10 minutes)

```bash
# Check the logs to see which step is hanging
python scripts/check-startup-logs.py
```

This will analyze the logs and tell you exactly which component is hanging.

Expected outcomes:
- **Best case**: Startup completes successfully (problem was transient)
- **Likely case**: We see exactly which step times out
- **Worst case**: We see which step the logs stop at (hanging without timeout)

### Phase 3: Fix the Root Cause (TBD)

Once we identify which component is hanging, we can:

1. **If it's the progressive loader (STEP 4)**:
   - Model loading is taking too long
   - May need to increase timeout or optimize model loading
   - Check if models are downloading vs loading from cache

2. **If it's the cache service (STEP 6)**:
   - Redis connection is failing or slow
   - Check Redis endpoint and connectivity
   - May need to increase timeout or fix Redis configuration

3. **If it's health monitoring (STEP 8)**:
   - Health check system is hanging
   - May be trying to check components that aren't ready
   - Need to fix health check initialization order

4. **If it's startup alerts (STEP 9)**:
   - Alert system is hanging
   - May be trying to evaluate alerts before components are ready
   - Need to defer alert evaluation until after startup

### Phase 4: Validate the Fix (5-10 minutes)

After fixing the root cause:

```bash
# Deploy the fix
python scripts/rebuild-and-deploy-working-image.py

# Check logs again
python scripts/check-startup-logs.py
```

Confirm we see:
```
✓ APPLICATION STARTUP COMPLETED SUCCESSFULLY
```

## Timeline

- **T+0**: Deploy logging fix (10 minutes)
- **T+10**: Check logs and identify problem (5 minutes)
- **T+15**: Implement root cause fix (30-60 minutes depending on issue)
- **T+75**: Deploy root cause fix (10 minutes)
- **T+85**: Validate fix works (5 minutes)

**Total estimated time**: 90 minutes

## Success Criteria

1. ✓ Logging fix deployed successfully
2. ✓ Can see all 10 startup steps in logs
3. ✓ Can identify which step is hanging
4. ✓ Root cause identified and fixed
5. ✓ Health checks passing consistently
6. ✓ Application accessible and functional

## Rollback Plan

If the logging fix causes issues:

```bash
# Rollback to previous task definition
aws ecs update-service \
  --cluster multimodal-librarian-prod \
  --service multimodal-librarian-service \
  --task-definition <previous-task-def-arn> \
  --region us-east-1
```

The logging fix is purely additive (only adds logging), so it should not cause any functional issues.

## Monitoring

During and after deployment, monitor:

1. **CloudWatch Logs**: `/ecs/multimodal-librarian-prod`
   - Look for the 10 numbered steps
   - Check for timeout messages
   - Verify "APPLICATION STARTUP COMPLETED SUCCESSFULLY"

2. **ECS Service**: `multimodal-librarian-service`
   - Check deployment status
   - Monitor running task count
   - Check health check status

3. **Application Health**: `https://<alb-dns>/health/simple`
   - Should return 200 OK
   - Should respond within 1-2 seconds

## Communication

### Status Updates

**After Phase 1 (Logging Fix Deployed)**:
"Deployed comprehensive startup logging. Monitoring logs to identify which component is hanging."

**After Phase 2 (Problem Identified)**:
"Identified that [component] is hanging during startup. Working on fix."

**After Phase 3 (Root Cause Fixed)**:
"Fixed [component] issue. Deploying fix and validating."

**After Phase 4 (Validated)**:
"Health checks passing. Application is stable and accessible."

## Files Reference

- `src/multimodal_librarian/main.py` - Main application with logging fix
- `STARTUP_LOGGING_FIX_IMPLEMENTATION.md` - Detailed implementation docs
- `STARTUP_LOGGING_FIX_SUMMARY.md` - Quick reference summary
- `scripts/deploy-startup-logging-fix.py` - Deployment script
- `scripts/check-startup-logs.py` - Log analysis script
- `MISSING_STARTUP_LOGGING_ANALYSIS.md` - Original problem analysis

## Next Actions

1. **Review this plan** - Make sure everyone understands the approach
2. **Deploy Phase 1** - Run the logging fix deployment
3. **Monitor logs** - Watch for the startup steps
4. **Identify problem** - Run the log analysis script
5. **Fix root cause** - Implement the appropriate fix
6. **Validate** - Confirm health checks pass

## Questions?

If you have questions about:
- **The fix**: See `STARTUP_LOGGING_FIX_IMPLEMENTATION.md`
- **Deployment**: See `STARTUP_LOGGING_FIX_SUMMARY.md`
- **The problem**: See `MISSING_STARTUP_LOGGING_ANALYSIS.md`
- **The spec**: See `.kiro/specs/application-health-startup-optimization/`

## Conclusion

This fix gives us the visibility we need to identify and fix the actual problem. Once deployed, we'll know exactly which component is hanging, and we can fix it quickly. The comprehensive logging will also help with future debugging and monitoring.

Let's deploy this fix and get the application healthy!
