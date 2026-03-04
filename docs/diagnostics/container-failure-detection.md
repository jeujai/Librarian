# Container-Level Failure Detection

## Overview

Container-level failures (OOM kills, segfaults, etc.) happen at the **kernel level**, below the application logging layer. These failures **never appear in application logs** because the kernel terminates the process before it can log anything.

## Why This Matters

When we reduced Uvicorn workers from 4 to 1, the OOM problem became obvious because the entire container was killed. With 4 workers, individual workers were being OOM killed while the parent process stayed alive, masking the problem in the logs.

## Diagnostic Script

### Location
```bash
scripts/diagnose-container-failures.py
```

### Usage
```bash
# Check default production service
python scripts/diagnose-container-failures.py

# Check specific cluster/service
python scripts/diagnose-container-failures.py --cluster my-cluster --service my-service
```

### What It Detects

The script checks ECS task exit codes and stop reasons to detect:

1. **OOM Kills (Exit Code 137)**
   - Container exceeded memory limits
   - Linux kernel sent SIGKILL
   - Most common infrastructure failure

2. **Segmentation Faults (Exit Code 139)**
   - Invalid memory access
   - Usually from native libraries (PyTorch, NumPy)
   - Indicates memory corruption

3. **Orchestrator Termination (Exit Code 143)**
   - ECS sent SIGTERM to stop task
   - Usually intentional (deployment, scaling down)

4. **Resource Exhaustion**
   - Detected from stop reasons
   - May not have specific exit code

## When to Use Each Diagnostic Tool

### 1. Container Failures (Infrastructure Level)
**Use:** `scripts/diagnose-container-failures.py`

**When:**
- Tasks are stopping unexpectedly
- Service keeps restarting
- No error logs in CloudWatch
- Suspected memory/resource issues

**What it finds:**
- OOM kills
- Segmentation faults
- Resource exhaustion
- Exit codes and stop reasons

### 2. Startup Issues (Application Level)
**Use:** `scripts/check-startup-logs.py`

**When:**
- Application starts but hangs
- Startup takes too long
- Need to see which step is failing

**What it finds:**
- Which startup step completed last
- Timeouts during initialization
- Application-level errors

### 3. Health Check Failures
**Use:** `scripts/diagnose-health-check-failure.py`

**When:**
- Tasks start successfully but fail health checks
- Load balancer marks targets unhealthy
- Service events show health check failures

**What it finds:**
- Health check configuration
- Target health status
- Recent service events

### 4. Deployment Progress
**Use:** `scripts/monitor-deployment-progress.py`

**When:**
- Deploying new version
- Want real-time status updates
- Need to track deployment completion

**What it finds:**
- Task status changes
- Health check progression
- Deployment events

## Diagnostic Sequence

When investigating issues, follow this order:

```
1. Check container failures FIRST
   └─> scripts/diagnose-container-failures.py
       ├─> If OOM kills found: Increase memory or reduce workers
       ├─> If segfaults found: Check native libraries
       └─> If no infrastructure failures: Continue to step 2

2. Check startup logs
   └─> scripts/check-startup-logs.py
       ├─> If hanging: Identify which component
       ├─> If errors: Check application logs
       └─> If startup completes: Continue to step 3

3. Check health checks
   └─> scripts/diagnose-health-check-failure.py
       ├─> If failing: Check endpoint response
       ├─> If timing out: Adjust health check parameters
       └─> If passing: Issue is elsewhere

4. Monitor deployment
   └─> scripts/monitor-deployment-progress.py
       └─> Real-time tracking of deployment status
```

## Why Container Failures Don't Appear in Logs

### The Problem
When the Linux kernel OOM killer terminates a process:
1. Kernel detects memory limit exceeded
2. Kernel sends SIGKILL (signal 9) to process
3. Process is terminated **immediately**
4. No cleanup, no logging, no graceful shutdown

### What You See
- **In CloudWatch Logs:** Nothing (or logs stop abruptly)
- **In ECS Task Status:** Exit code 137, stop reason "OutOfMemory"
- **In Service Events:** "Task stopped" messages

### The Multi-Worker Masking Effect

With `--workers 4`:
```
Parent Process (PID 1)
├─> Worker 1 (loads models) → OOM killed → restarted
├─> Worker 2 (loads models) → OOM killed → restarted
├─> Worker 3 (loads models) → OOM killed → restarted
└─> Worker 4 (loads models) → OOM killed → restarted

Parent stays alive, accepts health checks
Logs show repeated model loading (workers restarting)
Task status: RUNNING (parent alive)
Health status: UNKNOWN (workers keep dying)
```

With `--workers 1`:
```
Single Process (PID 1)
└─> Loads models → OOM killed

Entire container dies
Task status: STOPPED
Exit code: 137
Problem is obvious
```

## Common Exit Codes Reference

| Exit Code | Meaning | Cause | Solution |
|-----------|---------|-------|----------|
| 0 | Success | Normal termination | None needed |
| 1 | General error | Application error | Check logs |
| 137 | OOM Kill | Memory limit exceeded | Increase memory or reduce usage |
| 139 | Segmentation fault | Invalid memory access | Check native libraries |
| 143 | SIGTERM | Orchestrator stopped task | Usually intentional |

## Memory Optimization Strategies

If OOM kills are detected:

### 1. Immediate Fix
```bash
# Reduce workers in Dockerfile
CMD ["uvicorn", "src.multimodal_librarian.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
```

### 2. Increase Memory
```terraform
# In task definition
memory = "4096"  # Increase from 2048
```

### 3. Progressive Loading
```python
# Load models gradually instead of all at once
# Already implemented in startup optimization
```

### 4. Model Caching
```python
# Use EFS to cache models and reduce memory pressure
# Already implemented in model cache system
```

## Running the Script

### Prerequisites
- AWS CLI configured with appropriate credentials
- Python 3.8+
- boto3 installed

### Example Output
```
================================================================================
CONTAINER-LEVEL FAILURE DIAGNOSIS
================================================================================
Cluster: multimodal-lib-prod-cluster
Service: multimodal-lib-prod-service

1. RETRIEVING STOPPED TASKS
--------------------------------------------------------------------------------
Found 5 stopped tasks

2. ANALYZING TASK FAILURES
--------------------------------------------------------------------------------
Failure Summary:
  OOM Kill: 3
  Health Check Failure: 2

3. INFRASTRUCTURE-LEVEL FAILURES DETECTED
--------------------------------------------------------------------------------

Task: abc123def456
  Failure Type: OOM Kill
  Exit Code: 137 (OOM Kill - SIGKILL)
  Stop Reason: OutOfMemoryError: Container killed due to memory usage
  Runtime: 127.3 seconds
  Stopped At: 2026-01-14 10:23:45

4. RESOURCE LIMIT ANALYSIS
--------------------------------------------------------------------------------
Task Definition: multimodal-lib-prod-task:42
Task Memory Limit: 2048 MB
Task CPU: 1024

Container Resources:
  app:
    Hard Limit: 2048 MB
    Soft Limit: 1536 MB
    CPU: 1024

5. RECOMMENDATIONS
--------------------------------------------------------------------------------
⚠ 3 OOM Kill(s) detected

OOM kills happen when containers exceed memory limits.
The Linux kernel terminates the process with SIGKILL (exit 137).

Solutions:
  1. Increase container memory limits in task definition
  2. Reduce number of Uvicorn workers (--workers flag)
  3. Optimize application memory usage
  4. Use progressive model loading to spread memory usage
```

## Integration with CI/CD

You can integrate this script into your deployment pipeline:

```yaml
# .github/workflows/deploy.yml
- name: Check for container failures
  run: |
    python scripts/diagnose-container-failures.py
    if [ $? -ne 0 ]; then
      echo "Container failures detected - investigate before deploying"
      exit 1
    fi
```

## Related Documentation

- [Startup Optimization](../startup/phase-management.md)
- [Health Check Configuration](../startup/health-check-parameter-adjustments.md)
- [Memory Management](../startup/model-loading-optimization.md)
- [Troubleshooting Guide](../startup/troubleshooting.md)
