## Purpose

Refactor the application to use a consistent dependency injection pattern throughout, eliminating the current mix of lazy initialization singletons and FastAPI dependency injection. This will ensure clean separation of concerns, testability, and prevent blocking initialization during application startup.


### Problem Statement
The current codebase uses two conflicting patterns for service initialization:
1. **Lazy initialization singletons** - Module-level `get_*_service()` functions that create instances on first call
2. **FastAPI dependency injection** - `Depends()` pattern in `api/dependencies/database.py`

This inconsistency causes:
- Blocking initialization during module import (e.g., `ConnectionManager` calling `get_cached_rag_service()` at import time)
- OpenSearch connection attempts during startup that block health checks
- Difficulty testing components in isolation
- Unclear ownership of service lifecycle

## Requirements

### Requirement: Application Startup

The system SHALL implement application startup as described in the requirements.

#### Scenario: Application Startup

- **THEN** The system SHALL implement application startup as described in the requirements.

### Requirement: Service Dependency Management

The system SHALL implement service dependency management as described in the requirements.

#### Scenario: Service Dependency Management

- **THEN** The system SHALL implement service dependency management as described in the requirements.

### Requirement: Connection Lifecycle Management

The system SHALL implement connection lifecycle management as described in the requirements.

#### Scenario: Connection Lifecycle Management

- **THEN** The system SHALL implement connection lifecycle management as described in the requirements.

### Requirement: WebSocket Connection Management

The system SHALL implement websocket connection management as described in the requirements.

#### Scenario: WebSocket Connection Management

- **THEN** The system SHALL implement websocket connection management as described in the requirements.

### Requirement: Testing Support

The system SHALL implement testing support as described in the requirements.

#### Scenario: Testing Support

- **THEN** The system SHALL implement testing support as described in the requirements.
