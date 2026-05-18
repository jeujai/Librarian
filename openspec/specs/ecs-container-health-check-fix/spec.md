## Purpose

### Problem Statement
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

## Requirements

### Requirement: Container Startup Reliability

The system SHALL implement container startup reliability as described in the requirements.

#### Scenario: 1.1 Container health check uses the same endpoint as ALB (`/

- **THEN** 1.1 Container health check uses the same endpoint as ALB (`/health/simple`)

#### Scenario: 1.2 Container health check always passes once the HTTP serve

- **THEN** 1.2 Container health check always passes once the HTTP server is listening

#### Scenario: 1.3 Container is not killed during normal startup (up to 5 m

- **THEN** 1.3 Container is not killed during normal startup (up to 5 minutes)

#### Scenario: 1.4 Health check configuration is documented

- **THEN** 1.4 Health check configuration is documented

### Requirement: Graceful Startup Period

The system SHALL implement graceful startup period as described in the requirements.

#### Scenario: 2.1 Health check `startPeriod` is sufficient for model loadi

- **THEN** 2.1 Health check `startPeriod` is sufficient for model loading (at least 300 seconds)

#### Scenario: 2.2 Health check `interval` and `retries` allow for transien

- **THEN** 2.2 Health check `interval` and `retries` allow for transient failures

#### Scenario: 2.3 Health check `timeout` is appropriate for the endpoint r

- **THEN** 2.3 Health check `timeout` is appropriate for the endpoint response time

### Requirement: Health Check Consistency

The system SHALL implement health check consistency as described in the requirements.

#### Scenario: 3.1 `/health/simple` endpoint does NOT depend on any service

- **THEN** 3.1 `/health/simple` endpoint does NOT depend on any service initialization

#### Scenario: 3.2 `/health/minimal` endpoint behavior is documented

- **THEN** 3.2 `/health/minimal` endpoint behavior is documented

#### Scenario: 3.3 Health check endpoints follow the steering rules for dep

- **THEN** 3.3 Health check endpoints follow the steering rules for dependency injection
