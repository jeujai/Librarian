# Task Instability Root Cause Analysis

**Date**: 2026-01-17  
**Status**: CRITICAL - Tasks continuously failing  
**Service**: multimodal-lib-prod-service-alb  
**Cluster**: multimodal-lib-prod-cluster

## Executive Summary

The application is **NOT stable**. Tasks are continuously being stopped and restarted due to health check timeouts. The root cause is that **OpenSearch initialization is blocking the health check endpoint**, causing ALB to mark targets as unhealthy and ECS to stop tasks.

## Current Situation

### Service Status
- **Desired Count**: 1
- **Running Count**: 0 (tasks keep getting stopped)
- **Pending Count**: 1 (new task starting)
- **Health Status**: UNHEALTHY

### Failure Pattern
```
1. Task starts
2. Application begins OpenSearch initialization
3. OpenSearch connection times out after 60 seconds
4. Health check endpoint (/health/simple) is blocked waiting for OpenSearch
5. ALB health check times out after 10 seconds
6. ALB marks target as unhealthy
7. ECS stops the task
8. New task starts
9. CYCLE REPEATS
```

## Root Causes

### 1. OpenSearch Connection Timeout (PRIMARY)
**Error**: `Connection to vpc-multimodal-lib-prod-search-...us-east-1.es.amazonaws.com timed out (connect timeout=60)`

**Impact**: Blocks application startup for 60 seconds

**Why it's blocking health checks**:
- The health endpoint calls `get_minimal_server()`
- `get_minimal_server()` initializes components including OpenSearch client
- OpenSearch client tries to connect during initialization
- Connection times out after 60 seconds
- Health check times out after 10 seconds
- ALB marks target unhealthy before OpenSearch timeout completes

### 2. SearchService Import Error (SECONDARY)
**Error**: `cannot import name 'SearchService' from 'multimodal_librarian.components.vector_store.search_service'`

**Impact**: Causes health check system to fail

**Status**: Fixed in code but not deployed yet (task keeps getting stopped before new code runs)

### 3. Environment Variables Not Respected
**Issue**: Set environment variables to disable OpenSearch:
- `ENABLE_VECTOR_SEARCH=false`
- `SKIP_OPENSEARCH_INIT=true`
- `OPENSEARCH_TIMEOUT=5`

**Problem**: Application code is not checking these variables before initializing OpenSearch

## Why Previous Fixes Didn't Work

### Fix Attempt 1: Added SearchService Alias
**Status**: Code fixed but not deployed
**Reason**: Tasks keep getting stopped before new code can run

### Fix Attempt 2: Set Environment Variables
**Status**: Variables set in task definition
**Reason**: Application code doesn't check these variables before initializing OpenSearch

### Fix Attempt 3: Reduced OpenSearch Timeout
**Status**: Set OPENSEARCH_TIMEOUT=5
**Reason**: Application code doesn't use this variable

## The Real Problem

The application code has a **synchronous initialization pattern** where:
1. Health check endpoint depends on `get_minimal_server()`
2. `get_minimal_server()` initializes all components synchronously
3. OpenSearch client initialization is synchronous and blocking
4. No timeout or async handling for OpenSearch connection
5. Health check waits for everything to initialize before responding

This means the health check **cannot respond** until OpenSearch initialization completes or times out.

## Required Fixes

### Immediate Fix (Code Changes Required)
1. **Make OpenSearch initialization asynchronous and non-blocking**
   - Move OpenSearch initialization to background task
   - Don't wait for OpenSearch in health check path
   - Allow health check to respond immediately

2. **Respect SKIP_OPENSEARCH_INIT environment variable**
   - Check variable before initializing OpenSearch
   - Skip OpenSearch initialization if variable is true

3. **Add timeout handling to OpenSearch client**
   - Use OPENSEARCH_TIMEOUT environment variable
   - Default to 5 seconds instead of 60 seconds
   - Fail gracefully if timeout occurs

### Code Locations to Fix

#### 1. Health Check Endpoint
**File**: `src/multimodal_librarian/api/routers/health.py`
**Line**: ~700 (simple_health_check function)

**Current Code**:
```python
@router.get("/simple")
async def simple_health_check():
    server = get_minimal_server()  # BLOCKS HERE
    status = server.get_status()
    ...
```

**Required Fix**:
```python
@router.get("/simple")
async def simple_health_check():
    # Don't wait for minimal server - just check if HTTP server is running
    return JSONResponse(
        content={"status": "ok", "timestamp": datetime.now().isoformat()},
        status_code=200
    )
```

#### 2. Minimal Server Initialization
**File**: `src/multimodal_librarian/startup/minimal_server.py`

**Required Fix**:
- Check `SKIP_OPENSEARCH_INIT` before initializing OpenSearch
- Make OpenSearch initialization async
- Don't block on OpenSearch connection

#### 3. OpenSearch Client
**File**: `src/multimodal_librarian/clients/opensearch_client.py`

**Required Fix**:
- Use `OPENSEARCH_TIMEOUT` environment variable
- Default to 5 seconds
- Handle connection failures gracefully

## Deployment Strategy

### Phase 1: Emergency Fix (Immediate)
1. **Completely decouple health check from OpenSearch**
   - Make `/health/simple` return immediately without checking anything
   - Just verify HTTP server is responding

2. **Deploy emergency fix**
   - Build new image with fix
   - Update task definition
   - Force new deployment

### Phase 2: Proper Fix (After Stability)
1. **Implement async OpenSearch initialization**
2. **Add proper timeout handling**
3. **Respect environment variables**
4. **Add graceful degradation**

### Phase 3: Fix OpenSearch Connectivity (Long-term)
1. **Diagnose why OpenSearch is unreachable**
   - Check security groups
   - Check VPC configuration
   - Check network ACLs
2. **Fix network connectivity**
3. **Re-enable OpenSearch**

## Immediate Action Required

**STOP trying to fix with environment variables or configuration changes.**

**START fixing the application code:**
1. Decouple health check from OpenSearch
2. Make OpenSearch initialization non-blocking
3. Add proper error handling

The application will **never stabilize** until the code is fixed to handle OpenSearch initialization failures gracefully.

## Success Criteria

The deployment is successful when:
- [ ] Health check responds in <1 second
- [ ] Health check doesn't depend on OpenSearch
- [ ] Tasks remain running for >5 minutes
- [ ] ALB targets marked as healthy
- [ ] No task restarts in 10 minutes

## Current Status: BLOCKED

**Cannot proceed** until application code is fixed to:
1. Decouple health check from OpenSearch
2. Handle OpenSearch initialization failures gracefully
3. Respond to health checks immediately

**Estimated Time to Fix**: 30-60 minutes of code changes + rebuild + redeploy

## Recommendation

**Create a minimal health check endpoint that doesn't depend on ANY initialization:**

```python
@router.get("/health/simple")
async def simple_health_check():
    """Ultra-minimal health check for ALB - no dependencies."""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}
```

This will allow tasks to pass health checks while we fix the OpenSearch initialization issue properly.
