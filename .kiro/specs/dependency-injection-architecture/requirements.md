# Requirements: Dependency Injection Architecture Refactoring

## Overview
Refactor the application to use a consistent dependency injection pattern throughout, eliminating the current mix of lazy initialization singletons and FastAPI dependency injection. This will ensure clean separation of concerns, testability, and prevent blocking initialization during application startup.

## Problem Statement
The current codebase uses two conflicting patterns for service initialization:
1. **Lazy initialization singletons** - Module-level `get_*_service()` functions that create instances on first call
2. **FastAPI dependency injection** - `Depends()` pattern in `api/dependencies/database.py`

This inconsistency causes:
- Blocking initialization during module import (e.g., `ConnectionManager` calling `get_cached_rag_service()` at import time)
- OpenSearch connection attempts during startup that block health checks
- Difficulty testing components in isolation
- Unclear ownership of service lifecycle

## User Stories

### 1. Application Startup
**As a** DevOps engineer deploying to AWS ECS  
**I want** the application to start and respond to health checks within 60 seconds  
**So that** the ALB doesn't mark the container as unhealthy and kill it

#### Acceptance Criteria
- 1.1 Health check endpoint `/health/simple` responds within 100ms of Uvicorn starting
- 1.2 No database connections are attempted during module import
- 1.3 No external service connections block the FastAPI app creation
- 1.4 All service initialization happens via FastAPI's dependency injection system
- 1.5 Background initialization tasks don't block the main startup event

### 2. Service Dependency Management
**As a** developer maintaining the codebase  
**I want** all services to be injected via FastAPI's `Depends()` mechanism  
**So that** I can easily understand and test service dependencies

#### Acceptance Criteria
- 2.1 All services (RAGService, AIService, OpenSearchClient, etc.) are available as FastAPI dependencies
- 2.2 No module-level singleton instantiation (no `manager = ConnectionManager()` at module level)
- 2.3 Service dependencies are explicitly declared in function signatures
- 2.4 Services can be mocked/replaced for testing without monkey-patching
- 2.5 Circular dependencies are eliminated through proper dependency ordering

### 3. Connection Lifecycle Management
**As a** developer  
**I want** database and external service connections to be managed by the DI container  
**So that** connections are established only when needed and properly cleaned up

#### Acceptance Criteria
- 3.1 OpenSearch connections are established on first use, not at import time
- 3.2 Neptune connections are established on first use, not at import time
- 3.3 PostgreSQL connections are established on first use, not at import time
- 3.4 All connections are properly closed during application shutdown
- 3.5 Connection failures don't crash the application, they return appropriate HTTP errors

### 4. WebSocket Connection Management
**As a** user of the chat interface  
**I want** WebSocket connections to work even if some backend services are unavailable  
**So that** I can still use basic chat functionality during partial outages

#### Acceptance Criteria
- 4.1 WebSocket endpoint accepts connections without requiring all services to be ready
- 4.2 ConnectionManager is instantiated per-request or lazily, not at module import
- 4.3 RAG service unavailability results in graceful fallback, not connection failure
- 4.4 Service status is communicated to clients via WebSocket messages
- 4.5 Chat functionality degrades gracefully based on available services

### 5. Testing Support
**As a** developer writing tests  
**I want** to easily inject mock services into endpoints  
**So that** I can test components in isolation without real database connections

#### Acceptance Criteria
- 5.1 All dependencies can be overridden using FastAPI's `app.dependency_overrides`
- 5.2 No global state prevents parallel test execution
- 5.3 Test fixtures can provide mock implementations of all services
- 5.4 Integration tests can selectively use real vs mock services
- 5.5 No import-time side effects that affect test isolation

## Technical Requirements

### Architecture Constraints
- Use FastAPI's native dependency injection system exclusively
- Eliminate all module-level service instantiation
- Use `async def` dependencies for services that require async initialization
- Implement proper dependency caching (singleton per app, not per request where appropriate)
- Support graceful degradation when optional services are unavailable

### Migration Strategy
- Phase 1: Create DI providers for all services
- Phase 2: Update routers to use DI instead of module-level imports
- Phase 3: Remove legacy singleton patterns
- Phase 4: Update tests to use DI overrides

## Out of Scope
- Changing the actual service implementations (only how they're instantiated)
- Adding new features to existing services
- Modifying the database schemas
- Changing the API contracts
