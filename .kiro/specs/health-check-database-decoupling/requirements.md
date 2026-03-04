# Requirements Document: Database Restoration with Async Initialization

## Introduction

This specification addresses the need to restore OpenSearch and Neptune databases in the `multimodal-lib-prod-service-alb` service. The databases were previously disabled due to health check timeout issues. The solution implements asynchronous database initialization that decouples health checks from database connectivity, allowing the application to pass ALB health checks while databases initialize in the background.

## Current State

**Service**: multimodal-lib-prod-service-alb  
**Cluster**: multimodal-lib-prod-cluster  
**Status**: Running but unstable (tasks failing health checks intermittently)  
**Task Definition**: Revision 65 (has database endpoints but no async init code)

### Problem

Task definition revision 65 was deployed with:
- OpenSearch endpoint configured
- Neptune endpoint configured  
- NO `SKIP_OPENSEARCH_INIT` or `SKIP_NEPTUNE_INIT` variables
- NO async initialization code in the Docker image

This causes:
1. Application starts and tries to initialize OpenSearch synchronously
2. OpenSearch connection times out (60s default)
3. Health check endpoint blocks waiting for OpenSearch
4. ALB health check times out after 10s
5. Task marked unhealthy and stopped
6. Cycle repeats

### Solution Status

✅ **Code implemented** - Async database initialization manager created  
✅ **Deployment scripts created** - Ready to deploy  
❌ **Not deployed yet** - Need to build and deploy Docker image with fix  
❌ **Databases not restored** - Need to deploy fix first, then restore databases

## Glossary

- **ALB**: Application Load Balancer - AWS service that distributes incoming application traffic
- **Health_Check_Endpoint**: API endpoint called by ALB to determine if a target is healthy (`/health/simple`)
- **OpenSearch**: AWS OpenSearch service used for vector search and document indexing
- **Neptune**: AWS Neptune graph database used for knowledge graph storage
- **Async_Initialization**: Background initialization of databases that doesn't block application startup
- **Synchronous_Blocking**: Traditional initialization that waits for database connections before proceeding
- **Target_Health**: The status (healthy/unhealthy) of an ECS task as determined by ALB health checks
- **Task_Definition**: ECS configuration that specifies container image, environment variables, and resources

## Requirements

### Requirement 1: Asynchronous Database Initialization

**User Story:** As a DevOps engineer, I want databases to initialize asynchronously in the background, so that health checks pass immediately and tasks remain stable.

#### Acceptance Criteria

1.1 WHEN the application starts, THE System SHALL begin database initialization in a background task without blocking the main application startup

1.2 WHEN OpenSearch initialization is in progress, THE Health_Check_Endpoint SHALL respond with HTTP 200 status immediately

1.3 WHEN Neptune initialization is in progress, THE Health_Check_Endpoint SHALL respond with HTTP 200 status immediately

1.4 WHEN database initialization times out, THE Application SHALL continue running and mark the database as unavailable

1.5 WHEN database initialization fails, THE Application SHALL log the error and continue running without crashing

### Requirement 2: Health Check Independence

**User Story:** As a system operator, I want health check endpoints to be completely independent of database connectivity, so that ALB can determine application health reliably.

#### Acceptance Criteria

2.1 WHEN `/health/simple` is called, THE Endpoint SHALL respond within 1 second without checking database connectivity

2.2 WHEN `/health/simple` is called and databases are unavailable, THE Endpoint SHALL still return HTTP 200 status

2.3 WHEN `/health/simple` is called and databases are initializing, THE Endpoint SHALL still return HTTP 200 status

2.4 WHEN `/health/simple` is called, THE Endpoint SHALL NOT import or call any database client code

2.5 WHEN `/health/simple` is called, THE Response SHALL indicate only that the HTTP server is running and responsive

### Requirement 3: Database Status Monitoring

**User Story:** As a developer, I want to monitor database initialization status separately from health checks, so that I can diagnose connectivity issues without affecting ALB health.

#### Acceptance Criteria

3.1 THE System SHALL provide a `/api/health/databases` endpoint that reports database initialization status

3.2 WHEN `/api/health/databases` is called, THE Response SHALL include OpenSearch initialization status (not_started, in_progress, completed, failed, skipped)

3.3 WHEN `/api/health/databases` is called, THE Response SHALL include Neptune initialization status (not_started, in_progress, completed, failed, skipped)

3.4 WHEN `/api/health/databases` is called, THE Response SHALL include initialization duration in seconds

3.5 WHEN database initialization fails, THE `/api/health/databases` endpoint SHALL include error messages

### Requirement 4: Environment Variable Control

**User Story:** As a DevOps engineer, I want to control database initialization through environment variables, so that I can disable databases for testing or troubleshooting.

#### Acceptance Criteria

4.1 WHEN `SKIP_OPENSEARCH_INIT=true` is set, THE System SHALL skip OpenSearch initialization and mark it as skipped

4.2 WHEN `SKIP_NEPTUNE_INIT=true` is set, THE System SHALL skip Neptune initialization and mark it as skipped

4.3 WHEN `ENABLE_VECTOR_SEARCH=false` is set, THE System SHALL skip OpenSearch initialization

4.4 WHEN `OPENSEARCH_TIMEOUT` is set, THE System SHALL use that value (in seconds) as the OpenSearch connection timeout

4.5 WHEN `NEPTUNE_TIMEOUT` is set, THE System SHALL use that value (in seconds) as the Neptune connection timeout

### Requirement 5: Configurable Timeouts

**User Story:** As a system architect, I want configurable database connection timeouts, so that initialization doesn't block indefinitely.

#### Acceptance Criteria

5.1 THE System SHALL default to 10 seconds for OpenSearch connection timeout (down from 60s)

5.2 THE System SHALL default to 10 seconds for Neptune connection timeout

5.3 WHEN a database connection timeout is reached, THE System SHALL mark that database as failed and continue

5.4 WHEN a database connection timeout is reached, THE System SHALL log the timeout error with details

5.5 THE System SHALL allow timeout configuration through environment variables

### Requirement 6: Graceful Degradation

**User Story:** As a product owner, I want the application to remain functional even when databases are unavailable, so that users can still access basic features.

#### Acceptance Criteria

6.1 WHEN OpenSearch is unavailable, THE Application SHALL continue running and disable vector search features

6.2 WHEN Neptune is unavailable, THE Application SHALL continue running and disable knowledge graph features

6.3 WHEN both databases are unavailable, THE Application SHALL continue running with basic chat functionality

6.4 WHEN a database becomes available after startup, THE System SHALL allow reconnection without restart

6.5 THE System SHALL provide clear error messages to users when database-dependent features are unavailable

### Requirement 7: Deployment Process

**User Story:** As a DevOps engineer, I want a clear deployment process for the async database fix, so that I can restore databases safely.

#### Acceptance Criteria

7.1 THE Deployment SHALL first deploy the async initialization code without enabling databases

7.2 WHEN the async initialization code is deployed, THE Tasks SHALL remain stable for at least 5 minutes

7.3 WHEN tasks are stable, THE Deployment SHALL enable database endpoints in a second deployment

7.4 THE Deployment SHALL provide rollback scripts in case of issues

7.5 THE Deployment SHALL include verification steps to confirm database connectivity

### Requirement 8: Monitoring and Logging

**User Story:** As an operations engineer, I want comprehensive logging of database initialization, so that I can diagnose issues quickly.

#### Acceptance Criteria

8.1 WHEN database initialization starts, THE System SHALL log "ASYNC DATABASE INITIALIZATION STARTING"

8.2 WHEN each database initializes, THE System SHALL log the initialization status (success/failure)

8.3 WHEN database initialization completes, THE System SHALL log total duration

8.4 WHEN database initialization fails, THE System SHALL log detailed error messages

8.5 THE System SHALL log which databases are skipped based on environment variables
