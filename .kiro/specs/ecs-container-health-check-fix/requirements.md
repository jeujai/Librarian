# ECS Container Health Check Fix

## Problem Statement

The ECS container health check is failing during startup, causing containers to be killed with SIGKILL (exit code 137). The root cause is a mismatch between the container health check endpoint (`/health/minimal`) and the ALB health check endpoint (`/health/simple`).

### Current Behavior
- **ECS Container Health Check**: Uses `curl -f http://localhost:8000/health/minimal || exit 1`
- **ALB Health Check**: Uses `/health/simple` which always returns HTTP 200
- **Problem**: `/health/minimal` returns HTTP 503 when `MinimalServer.health_check_ready` is `False` during startup
- **Result**: ECS kills the container before it has time to fully initialize

### Root Cause Analysis (from Amazon Q)
- Container health check failure leading to SIGKILL (exit code 137)
- Health check command: `curl -f http://localhost:8000/health/minimal || exit 1`
- Stop reason: "Task failed container health checks"
- ECS service scheduler detected unhealthy container and initiated stop

## User Stories

### 1. Container Startup Reliability
As a DevOps engineer, I want the ECS container health check to be consistent with the ALB health check so that containers are not killed during normal startup.

**Acceptance Criteria:**
- 1.1 Container health check uses the same endpoint as ALB (`/health/simple`)
- 1.2 Container health check always passes once the HTTP server is listening
- 1.3 Container is not killed during normal startup (up to 5 minutes)
- 1.4 Health check configuration is documented

### 2. Graceful Startup Period
As a system administrator, I want the container to have sufficient time to initialize before health checks start failing.

**Acceptance Criteria:**
- 2.1 Health check `startPeriod` is sufficient for model loading (at least 300 seconds)
- 2.2 Health check `interval` and `retries` allow for transient failures
- 2.3 Health check `timeout` is appropriate for the endpoint response time

### 3. Health Check Consistency
As a developer, I want all health check endpoints to follow the dependency injection principles so that they don't block on database or model initialization.

**Acceptance Criteria:**
- 3.1 `/health/simple` endpoint does NOT depend on any service initialization
- 3.2 `/health/minimal` endpoint behavior is documented
- 3.3 Health check endpoints follow the steering rules for dependency injection

## Technical Requirements

### Task Definition Update
- Change container health check command from `/health/minimal` to `/health/simple`
- Verify health check parameters:
  - `interval`: 30 seconds
  - `timeout`: 15 seconds
  - `retries`: 5
  - `startPeriod`: 300 seconds (5 minutes)

### Code Verification
- Ensure `/health/simple` endpoint:
  - Does NOT call `get_minimal_server()`
  - Does NOT depend on database connections
  - Does NOT depend on model loading
  - Always returns HTTP 200 with `{"status": "ok"}`

## Out of Scope
- Changing ALB health check configuration (already working correctly)
- Modifying model loading behavior
- Changing startup phase management
