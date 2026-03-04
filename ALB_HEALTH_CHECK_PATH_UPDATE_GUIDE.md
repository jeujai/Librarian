# ALB Health Check Path Update Guide

## Objective
Update the ALB target group health check path from `/api/health/simple` to `/health/simple`.

## Current Situation
- The ALB is currently configured to check `/api/health/simple`
- The application's actual health endpoint is at `/health/simple` (without the `/api` prefix)
- This mismatch is causing health check failures

## Solution

### Step 1: Check Current Configuration
Run the health status check script to see the current configuration:

```bash
python3 scripts/check-alb-health-status.py
```

This will show:
- Current health check path
- Target health status
- Health check configuration details

### Step 2: Update Health Check Path
Run the fix script to update the path:

```bash
python3 scripts/fix-alb-health-check-path.py
```

This script will:
1. Find all multimodal-related target groups
2. Check their current health check paths
3. Update any that are using `/api/health/simple` to `/health/simple`
4. Preserve other health check settings (interval, timeout, thresholds)

### Step 3: Verify the Update
After running the update script:

1. **Wait 30-60 seconds** for the new health checks to execute
2. **Check target health** again:
   ```bash
   python3 scripts/check-alb-health-status.py
   ```
3. **Verify the path** is now `/health/simple`
4. **Confirm targets are healthy**

## Expected Results

### Before Update
```
Health Check Configuration:
  Path: /api/health/simple
  Protocol: HTTP
  Port: traffic-port
  Interval: 30s
  Timeout: 29s
  
Target Status: unhealthy
Reason: Target.FailedHealthChecks
```

### After Update
```
Health Check Configuration:
  Path: /health/simple
  Protocol: HTTP
  Port: traffic-port
  Interval: 30s
  Timeout: 29s
  
Target Status: healthy
```

## Scripts Available

1. **check-alb-health-status.py** - Check current health status and configuration
2. **fix-alb-health-check-path.py** - Update health check path from `/api/health/simple` to `/health/simple`
3. **update-alb-health-check-path.py** - Alternative script for manual path updates

## Troubleshooting

If targets remain unhealthy after the update:

1. **Check application logs** to verify the `/health/simple` endpoint is responding
2. **Test the endpoint directly** from within the VPC:
   ```bash
   curl http://<container-ip>:8000/health/simple
   ```
3. **Verify security groups** allow traffic from ALB to containers on port 8000
4. **Check health check timeout** - ensure the application responds within 29 seconds

## Rollback

If you need to revert the change:

```bash
# Manually update back to /api/health/simple if needed
aws elbv2 modify-target-group \
  --target-group-arn <arn> \
  --health-check-path /api/health/simple
```

## Notes

- The health check path change takes effect immediately
- New health checks will start using the updated path within seconds
- It may take 30-60 seconds (one health check interval) to see status changes
- The script preserves all other health check settings
- Results are saved to timestamped JSON files for audit purposes
