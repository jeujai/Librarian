# Root Cause Analysis: Application Not Listening on Port 8000

## Date: 2026-01-16

## Summary
The application container shows "Uvicorn running on http://0.0.0.0:8000" in logs, but **no traffic is actually reaching the application**. The NLB shows targets as healthy (TCP check passes), but HTTP requests timeout.

## Evidence

### 1. Uvicorn Logs Show It's Listening
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

### 2. No HTTP Requests in Logs
- Checked application logs for the last 30 minutes
- **ZERO HTTP requests logged** (no GET, POST, etc.)
- Only internal health check logs from monitoring services

### 3. NLB Connection Test
```bash
curl http://multimodal-lib-prod-nlb-9f03ee5dda51903f.elb.us-east-1.amazonaws.com/health/simple
# Result: Connection timeout after 10 seconds
# TCP handshake succeeds, but HTTP request times out
```

### 4. Target Health
- NLB target group shows target as **HEALTHY**
- Target: 10.0.2.58:8000
- Health check: TCP on port 8000 (passes)

### 5. Security Group Configuration
Container security group (sg-0135b368e20b7bd01):
- Port 8000: Allow from 10.0.0.0/16 (VPC CIDR) ✓
- Port 80: Allow from 0.0.0.0/0 ✓
- Port 443: Allow from 0.0.0.0/0 ✓

### 6. Network Configuration
- NLB is in public subnets with internet gateway ✓
- Container is in private subnet (10.0.2.58) ✓
- NLB can reach container (TCP health check passes) ✓

## Root Cause Hypothesis

The most likely causes are:

### **Hypothesis 1: Application Crashes After Startup (MOST LIKELY)**
- Uvicorn starts and logs "running on 0.0.0.0:8000"
- Application then crashes or hangs during initialization
- Container stays running (process 1 doesn't exit)
- TCP port 8000 appears open (socket in TIME_WAIT or similar state)
- But no process is actually listening and accepting connections

**Evidence:**
- Logs show startup sequence completes
- But then no HTTP request logs at all
- NLB TCP health check passes (port is "open")
- But HTTP requests timeout (no process handling them)

### **Hypothesis 2: Uvicorn Binding Issue**
- Uvicorn might be binding to 127.0.0.1 despite logs saying 0.0.0.0
- Or binding to IPv6 (::) instead of IPv4
- This would explain why localhost health check in Dockerfile fails

### **Hypothesis 3: Application Deadlock**
- Application starts but deadlocks during initialization
- Uvicorn is running but can't accept connections
- Background tasks are blocking the event loop

## Diagnostic Steps Needed

### 1. Check if Process is Actually Listening
```bash
# Need to exec into container (requires ECS Execute Command enabled)
netstat -tlnp | grep 8000
# Should show: tcp 0 0 0.0.0.0:8000 0.0.0.0:* LISTEN <pid>/python

# Or use ss
ss -tlnp | grep 8000
```

### 2. Test Connection from Within VPC
```bash
# From another container or EC2 instance in the same VPC
curl -v http://10.0.2.58:8000/health/simple
```

### 3. Check Application Logs for Crashes
```bash
# Look for Python tracebacks or errors after "Uvicorn running"
aws logs tail /ecs/multimodal-lib-prod-app --since 1h --format short | grep -A 20 "Uvicorn running"
```

### 4. Check Container Health Check
```bash
# The Dockerfile health check uses curl which isn't installed
# This might be causing the container to be marked unhealthy
HEALTHCHECK CMD curl -f http://localhost:8000/health/simple || exit 1
# But curl is NOT in the container (only wget is installed)
```

## Immediate Fixes to Try

### Fix 1: Update Dockerfile Health Check
The Dockerfile uses `curl` but only `wget` is installed:

```dockerfile
# Current (BROKEN):
HEALTHCHECK CMD curl -f http://localhost:8000/health/simple || exit 1

# Fix Option 1: Use wget
HEALTHCHECK CMD wget --spider --quiet http://localhost:8000/health/simple || exit 1

# Fix Option 2: Use Python
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/simple', timeout=5)" || exit 1

# Fix Option 3: Use the existing socket check (already in task definition)
# Remove HEALTHCHECK from Dockerfile, rely on ECS task definition health check
```

### Fix 2: Add Startup Logging
Add more verbose logging to see where the application might be failing:

```python
# In main.py, after "Uvicorn running" equivalent
logger.info("Application startup complete - ready to accept connections")
logger.info(f"Listening on 0.0.0.0:8000")

# Add a test request on startup
try:
    import urllib.request
    response = urllib.request.urlopen('http://localhost:8000/health/simple', timeout=2)
    logger.info(f"Self-test successful: {response.read()}")
except Exception as e:
    logger.error(f"Self-test FAILED: {e}")
```

### Fix 3: Simplify Startup
The application has complex startup with phase managers, background tasks, etc.
Try a minimal version:

```python
# Minimal test version
from fastapi import FastAPI
import uvicorn

app = FastAPI()

@app.get("/health/simple")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

## Next Steps

1. **Enable ECS Execute Command** on the service to exec into the container
2. **Check if port 8000 is actually listening** using netstat/ss
3. **Test connection from within VPC** using another container
4. **Fix the Dockerfile HEALTHCHECK** to use wget or Python instead of curl
5. **Add self-test on startup** to verify the application can handle requests
6. **Simplify startup** if the complex initialization is causing issues

## Files to Update

1. `Dockerfile` - Fix HEALTHCHECK command
2. `src/multimodal_librarian/main.py` - Add startup self-test
3. ECS Service - Enable Execute Command for debugging

## Conclusion

The application **appears** to start (Uvicorn logs say it's running), but **no traffic is reaching it**. This strongly suggests the application crashes, hangs, or deadlocks shortly after startup, leaving the port in a state where TCP connections succeed but HTTP requests fail.

The immediate priority is to:
1. Fix the broken HEALTHCHECK in the Dockerfile
2. Add diagnostic logging to see what happens after "Uvicorn running"
3. Enable ECS Execute Command to inspect the running container
