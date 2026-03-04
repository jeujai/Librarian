# Module-Level Database Initialization Fix

## Problem Summary

The application was failing health checks and timing out during startup because **synchronous database initialization was happening at module import time**, blocking the application before async initialization could run.

### Root Cause

Three router files had module-level code that created `VectorStore()` instances:

1. `src/multimodal_librarian/api/routers/chat.py` (lines 138-139)
2. `src/multimodal_librarian/api/routers/query.py` (lines 35-38)  
3. `src/multimodal_librarian/api/routers/ml_training.py` (lines 42-45)

### The Broken Flow

```
1. Python imports main.py
2. main.py imports routers (chat.py, query.py, ml_training.py)
3. Routers have module-level code: vector_store = VectorStore()
4. VectorStore.__init__() calls OpenSearchClient
5. OpenSearch tries to connect synchronously (60s timeout)
6. Container fails health checks (app takes too long to start)
7. THEN (too late!) async database initialization runs in background
```

### Why Async Init Was Useless

The async database initialization in `src/multimodal_librarian/startup/async_database_init.py` was correctly implemented, but it was being called **AFTER** the routers were imported. By that time, the synchronous OpenSearch connection had already blocked startup for 60+ seconds.

## Solution: Lazy Initialization

Replaced module-level database initialization with **lazy initialization** that only connects when the components are actually used.

### Changes Made

#### 1. chat.py
- **Before**: Module-level `vector_store = VectorStore()` that blocked on import
- **After**: `_get_legacy_components()` function that initializes on first use
- Added thread-safe lazy loading with lock
- Components only connect when actually needed by a route handler

#### 2. query.py
- **Before**: Module-level `vector_store = VectorStore()` that blocked on import
- **After**: `_get_query_components()` function that initializes on first use
- Added thread-safe lazy loading with lock
- Updated all route handlers to call lazy loader

#### 3. ml_training.py
- **Before**: Module-level `vector_store = VectorStore()` that blocked on import
- **After**: `_get_ml_components()` function that initializes on first use
- Added thread-safe lazy loading with lock
- Updated all route handlers to call lazy loader

### Key Implementation Details

```python
# OLD (BLOCKING):
vector_store = VectorStore()  # Connects immediately at import time
search_service = SemanticSearchService(vector_store)

# NEW (LAZY):
def _get_query_components():
    global query_processor, search_service, _components_initialized, _components_lock
    
    if _components_initialized:
        return query_processor, search_service, multimedia_generator
    
    with _components_lock:
        if _components_initialized:
            return query_processor, search_service, multimedia_generator
        
        vector_store = VectorStore()
        vector_store.connect()  # Only connects when first needed
        search_service = SemanticSearchService(vector_store)
        # ... rest of initialization
        
        _components_initialized = True
        return query_processor, search_service, multimedia_generator
```

## Benefits

1. **Fast Startup**: Application starts immediately without waiting for database connections
2. **Health Check Success**: `/health/simple` endpoint responds quickly, passing ALB health checks
3. **Async Init Works**: Background database initialization can now run properly
4. **Graceful Degradation**: Routes return 503 if databases aren't ready yet
5. **Thread-Safe**: Double-checked locking pattern prevents race conditions

## Testing

To verify the fix:

```bash
# 1. Build and deploy
python scripts/rebuild-and-redeploy.py

# 2. Check startup time
python scripts/check-alb-health-status.py

# 3. Monitor container logs
aws logs tail /ecs/multimodal-lib-prod-app --follow

# Expected: Container should be healthy within 60 seconds
```

## Files Modified

- `src/multimodal_librarian/api/routers/chat.py`
- `src/multimodal_librarian/api/routers/query.py`
- `src/multimodal_librarian/api/routers/ml_training.py`

## Related Issues

- Task failure: `efd8904de1a042948bb7c2ea7a417a18` (OpenSearch timeout)
- ALB health check failures (Target.Timeout)
- Container startup taking 60+ seconds

## Next Steps

1. Deploy the fix
2. Monitor ALB target health
3. Verify containers pass health checks within 60 seconds
4. Confirm async database initialization completes in background
5. Test that routes work correctly after databases initialize
