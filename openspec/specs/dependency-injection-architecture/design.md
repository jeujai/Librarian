# Design: Dependency Injection Architecture Refactoring

## Overview
This design document describes the refactoring of the application to use FastAPI's dependency injection system consistently, eliminating the current mix of lazy initialization singletons and DI patterns that cause blocking startup issues.

## Architecture

### Current State (Problem)
```
Module Import Time:
  chat.py imports → ConnectionManager() instantiated at module level
    → get_cached_rag_service() called
      → CachedRAGService() created
        → RAGService.__init__() called
          → get_opensearch_client() called
            → OpenSearchClient.connect() BLOCKS for 60+ seconds
              → Health check times out → Container killed
```

### Target State (Solution)
```
Module Import Time:
  chat.py imports → No instantiation, only function/class definitions

Request Time (via FastAPI Depends):
  WebSocket request → get_connection_manager() dependency resolved
    → get_rag_service() dependency resolved (if needed)
      → get_opensearch_client() dependency resolved (if needed)
        → Connection established (or graceful failure)
```

## Component Design

### 1. Dependency Provider Module
Create a centralized dependency provider module that manages all service dependencies.

**File: `src/multimodal_librarian/api/dependencies/services.py`**

```python
from typing import Optional
from fastapi import Depends, HTTPException
import logging

logger = logging.getLogger(__name__)

# Cached instances (managed by DI, not module-level)
_opensearch_client: Optional["OpenSearchClient"] = None
_rag_service: Optional["RAGService"] = None
_ai_service: Optional["AIService"] = None

async def get_opensearch_client() -> "OpenSearchClient":
    """
    FastAPI dependency for OpenSearchClient.
    Lazily creates and caches the client on first use.
    """
    global _opensearch_client
    if _opensearch_client is None:
        from ...clients.opensearch_client import OpenSearchClient
        try:
            _opensearch_client = OpenSearchClient()
            _opensearch_client.connect()
            logger.info("OpenSearch client connected via DI")
        except Exception as e:
            logger.error(f"OpenSearch connection failed: {e}")
            raise HTTPException(status_code=503, detail="Vector search unavailable")
    return _opensearch_client

async def get_opensearch_client_optional() -> Optional["OpenSearchClient"]:
    """
    Optional OpenSearch client - returns None if unavailable.
    Use this for endpoints that can function without vector search.
    """
    try:
        return await get_opensearch_client()
    except HTTPException:
        return None

async def get_ai_service() -> "AIService":
    """FastAPI dependency for AIService."""
    global _ai_service
    if _ai_service is None:
        from ...services.ai_service import AIService
        _ai_service = AIService()
        logger.info("AI service initialized via DI")
    return _ai_service

async def get_rag_service(
    opensearch: Optional["OpenSearchClient"] = Depends(get_opensearch_client_optional),
    ai_service: "AIService" = Depends(get_ai_service)
) -> Optional["RAGService"]:
    """
    FastAPI dependency for RAGService.
    Returns None if OpenSearch is unavailable.
    """
    global _rag_service
    if opensearch is None:
        return None
    if _rag_service is None:
        from ...services.rag_service import RAGService
        _rag_service = RAGService(opensearch_client=opensearch, ai_service=ai_service)
        logger.info("RAG service initialized via DI")
    return _rag_service
```

### 2. Service Constructor Refactoring
Modify services to accept dependencies via constructor injection instead of calling global getters.

**RAGService Changes:**
```python
class RAGService:
    def __init__(
        self, 
        opensearch_client: OpenSearchClient,
        ai_service: AIService,
        kg_builder: Optional[KnowledgeGraphBuilder] = None
    ):
        # Accept injected dependencies instead of calling get_*()
        self.opensearch_client = opensearch_client
        self.ai_service = ai_service
        self.kg_builder = kg_builder or KnowledgeGraphBuilder()
        # ... rest of init without connection calls
```

### 3. WebSocket Connection Manager Refactoring
Remove module-level instantiation and use request-scoped or app-scoped management.

**File: `src/multimodal_librarian/api/routers/chat.py`**

```python
from fastapi import APIRouter, WebSocket, Depends
from ..dependencies.services import get_rag_service, get_ai_service

router = APIRouter()

# NO module-level instantiation
# manager = ConnectionManager()  # REMOVED

class ConnectionManager:
    """WebSocket connection manager - instantiated per app, not per module."""
    
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.conversation_history: Dict[str, List] = {}
        # NO service initialization here
        self._rag_service = None
        self._ai_service = None
    
    def set_services(self, rag_service, ai_service):
        """Set services after DI resolution."""
        self._rag_service = rag_service
        self._ai_service = ai_service

# App-scoped connection manager (set during startup)
_connection_manager: Optional[ConnectionManager] = None

async def get_connection_manager() -> ConnectionManager:
    """FastAPI dependency for ConnectionManager."""
    global _connection_manager
    if _connection_manager is None:
        _connection_manager = ConnectionManager()
    return _connection_manager

@router.websocket("/ws/chat")
async def websocket_endpoint(
    websocket: WebSocket,
    manager: ConnectionManager = Depends(get_connection_manager),
    rag_service = Depends(get_rag_service),
    ai_service = Depends(get_ai_service)
):
    """WebSocket endpoint with injected dependencies."""
    # Services are injected, not fetched at module level
    manager.set_services(rag_service, ai_service)
    # ... rest of handler
```

### 4. Startup/Shutdown Lifecycle
Use FastAPI's lifespan context manager for proper lifecycle management.

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize nothing blocking
    logger.info("Application starting - no blocking initialization")
    
    # Background task for optional pre-warming
    asyncio.create_task(background_service_warmup())
    
    yield
    
    # Shutdown: Clean up connections
    await cleanup_services()

app = FastAPI(lifespan=lifespan)
```

## Correctness Properties

### Property 1: No Import-Time Connections
**Validates: Requirements 1.2, 1.3, 2.2**

For any module in the application, importing that module must not:
- Establish database connections
- Make network requests
- Block for more than 100ms

```python
# Property: import_time_is_fast
# For all modules M in application:
#   time(import M) < 100ms AND
#   network_connections_during(import M) == 0
```

### Property 2: Dependency Resolution Idempotence
**Validates: Requirements 2.1, 2.3**

Resolving a dependency multiple times must return the same instance (singleton behavior) and must not cause side effects beyond the first resolution.

```python
# Property: dependency_resolution_idempotent
# For all dependencies D:
#   resolve(D) == resolve(D) AND
#   side_effects(resolve(D)) == side_effects(first_resolve(D))
```

### Property 3: Graceful Degradation
**Validates: Requirements 3.5, 4.3, 4.5**

When an optional service is unavailable, endpoints that depend on it must:
- Return a valid response (not crash)
- Indicate reduced functionality
- Not block indefinitely

```python
# Property: graceful_degradation
# For all optional services S and endpoints E that use S:
#   when S.unavailable:
#     E.response.status_code in [200, 503] AND
#     E.response_time < timeout AND
#     E.response.body.indicates_degraded_mode
```

### Property 4: Test Isolation
**Validates: Requirements 5.1, 5.2, 5.5**

Tests using dependency overrides must be isolated from each other and from the global state.

```python
# Property: test_isolation
# For all tests T1, T2 running in parallel:
#   state_after(T1) independent_of state_after(T2) AND
#   dependency_overrides(T1) not_visible_to T2
```

## File Changes

### Files to Modify
1. `src/multimodal_librarian/api/dependencies/database.py` - Extend with all service dependencies
2. `src/multimodal_librarian/api/routers/chat.py` - Remove module-level instantiation
3. `src/multimodal_librarian/services/rag_service.py` - Accept injected dependencies
4. `src/multimodal_librarian/services/rag_service_cached.py` - Accept injected dependencies
5. `src/multimodal_librarian/clients/opensearch_client.py` - Separate construction from connection
6. `src/multimodal_librarian/main.py` - Use lifespan context manager

### Files to Create
1. `src/multimodal_librarian/api/dependencies/services.py` - Centralized service dependencies
2. `src/multimodal_librarian/api/dependencies/__init__.py` - Export all dependencies

### Files to Remove/Deprecate
1. Module-level `get_*_service()` singleton functions (after migration)

## Testing Strategy

### Unit Tests
- Test each dependency provider in isolation
- Verify singleton behavior
- Verify graceful failure handling

### Integration Tests
- Test full request flow with DI
- Test dependency override mechanism
- Test startup/shutdown lifecycle

### Property-Based Tests
- Test import-time behavior across all modules
- Test dependency resolution idempotence
- Test graceful degradation under various failure scenarios

## Migration Plan

### Phase 1: Create DI Infrastructure (Non-Breaking)
1. Create `api/dependencies/services.py` with new dependency providers
2. Add constructor injection support to services (backward compatible)
3. Add tests for new DI providers

### Phase 2: Migrate Routers (Incremental)
1. Update `chat.py` to use DI (highest priority - fixes blocking issue)
2. Update other routers one at a time
3. Verify each migration with integration tests

### Phase 3: Remove Legacy Patterns
1. Remove module-level singleton instantiation
2. Remove `get_*_service()` global functions
3. Update all tests to use DI overrides

### Phase 4: Documentation and Cleanup
1. Document DI patterns for future development
2. Add linting rules to prevent module-level instantiation
3. Clean up any remaining legacy code

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Breaking existing functionality | High | Incremental migration with tests at each step |
| Performance regression from DI overhead | Low | FastAPI DI is highly optimized; benchmark before/after |
| Circular dependency issues | Medium | Careful dependency ordering; use Optional types |
| Test suite breakage | Medium | Update tests incrementally alongside code changes |
