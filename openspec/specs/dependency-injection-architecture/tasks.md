# Tasks: Dependency Injection Architecture Refactoring

## Phase 1: Create DI Infrastructure (Non-Breaking)

- [x] 1. Create centralized service dependency providers
  - [x] 1.1 Create `src/multimodal_librarian/api/dependencies/services.py` with async dependency providers
  - [x] 1.2 Implement `get_opensearch_client()` dependency with lazy connection
  - [x] 1.3 Implement `get_opensearch_client_optional()` for graceful degradation
  - [x] 1.4 Implement `get_ai_service()` dependency
  - [x] 1.5 Implement `get_rag_service()` dependency with optional OpenSearch
  - [x] 1.6 Implement `get_connection_manager()` dependency for WebSocket management
  - [x] 1.7 Create `src/multimodal_librarian/api/dependencies/__init__.py` to export all dependencies

- [x] 2. Refactor service constructors for dependency injection
  - [x] 2.1 Modify `OpenSearchClient` to separate construction from connection
  - [x] 2.2 Modify `RAGService.__init__()` to accept injected `opensearch_client` and `ai_service`
  - [x] 2.3 Modify `CachedRAGService.__init__()` to accept injected dependencies
  - [x] 2.4 Ensure backward compatibility with existing code during migration

- [x] 3. Write property-based tests for DI infrastructure
  - [x] 3.1 (PBT) Test: Import-time behavior - no module imports should establish connections or block > 100ms
  - [x] 3.2 (PBT) Test: Dependency resolution idempotence - same instance returned on multiple resolutions
  - [x] 3.3 Write unit tests for each dependency provider
  - [x] 3.4 Write tests for graceful degradation when services unavailable

## Phase 2: Migrate Routers to DI

- [x] 4. Migrate chat.py router (highest priority - fixes blocking issue)
  - [x] 4.1 Remove module-level `manager = ConnectionManager()` instantiation
  - [x] 4.2 Update `ConnectionManager` class to not call `get_cached_rag_service()` in `__init__`
  - [x] 4.3 Update `websocket_endpoint()` to use `Depends(get_connection_manager)`
  - [x] 4.4 Update `websocket_endpoint()` to inject RAG and AI services via `Depends()`
  - [x] 4.5 Update `_get_legacy_components()` to use DI instead of direct instantiation
  - [x] 4.6 Test WebSocket functionality with new DI pattern

- [x] 5. Migrate other routers using RAG/AI services
  - [x] 5.1 Identify all routers that use `get_cached_rag_service()` or similar patterns
  - [x] 5.2 Update each router to use `Depends()` for service injection
  - [x] 5.3 Test each migrated router

- [x] 6. Update main.py startup lifecycle
  - [x] 6.1 Replace `@app.on_event("startup")` with lifespan context manager
  - [x] 6.2 Move background initialization to non-blocking tasks
  - [x] 6.3 Implement proper shutdown cleanup for DI-managed services
  - [x] 6.4 Verify health check responds within 100ms of startup

## Phase 3: Remove Legacy Patterns

- [x] 7. Remove module-level singleton patterns
  - [x] 7.1 Remove `get_cached_rag_service()` global function from `rag_service_cached.py`
  - [x] 7.2 Remove `get_opensearch_client()` global function from `opensearch_client.py`
  - [x] 7.3 Remove `get_ai_service()` global function from `ai_service.py`
  - [x] 7.4 Remove any remaining `_cached_*` module-level variables
  - [x] 7.5 Update all imports to use DI dependencies instead

- [-] 8. Clean up database.py dependencies
  - [x] 8.1 Consolidate `api/dependencies/database.py` with new `services.py`
  - [x] 8.2 Remove duplicate dependency providers
  - [x] 8.3 Ensure consistent naming and patterns across all dependencies

## Phase 4: Testing and Documentation

- [x] 9. Update test suite for DI
  - [x] 9.1 Update existing tests to use `app.dependency_overrides` for mocking
  - [x] 9.2 Remove any tests that rely on module-level singleton state
  - [x] 9.3 Add integration tests for full request flow with DI
  - [x] 9.4 Verify tests can run in parallel without interference

- [x] 10. Write property-based tests for correctness properties
  - [x] 10.1 (PBT) Test: Graceful degradation - endpoints return valid responses when services unavailable
  - [x] 10.2 (PBT) Test: Test isolation - dependency overrides don't leak between tests

- [x] 11. Documentation and developer guidance
  - [x] 11.1 Document DI patterns in steering files
  - [x] 11.2 Add code comments explaining DI usage
  - [x] 11.3 Create example showing how to add new services with DI
  - [x] 11.4 Update README with DI architecture overview

## Validation

- [x] 12. End-to-end validation
  - [x] 12.1 Deploy to test environment and verify health check passes within 60 seconds
  - [x] 12.2 Verify WebSocket chat works with RAG service available
  - [x] 12.3 Verify WebSocket chat degrades gracefully when RAG unavailable
  - [x] 12.4 Verify no blocking during application startup
  - [x] 12.5 Run full test suite and verify all tests pass
