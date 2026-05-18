# Dependency Injection Architecture

This document describes the dependency injection (DI) patterns used in the Multimodal Librarian application. All services and components use FastAPI's native dependency injection system for clean separation of concerns, testability, and non-blocking startup.

## Core Principles

1. **No Import-Time Connections**: Module imports must not establish database connections or make network requests
2. **Lazy Initialization**: Services are created on first use, not at module import time
3. **Graceful Degradation**: Endpoints can function with reduced capabilities when services are unavailable
4. **Singleton Caching**: Service instances are cached for performance (one instance per application)
5. **Proper Cleanup**: All connections are properly closed during application shutdown

## Dependency Provider Location

All dependencies are defined in:
```
src/multimodal_librarian/api/dependencies/services.py
```

Import dependencies from the package:
```python
from multimodal_librarian.api.dependencies import (
    get_opensearch_client,
    get_ai_service,
    get_rag_service,
    get_connection_manager,
)
```

## Available Dependencies

### Service-Level Dependencies

| Dependency | Description | Optional Variant |
|------------|-------------|------------------|
| `get_opensearch_client()` | OpenSearch vector database client | `get_opensearch_client_optional()` |
| `get_ai_service()` | AI/LLM service for text generation | `get_ai_service_optional()` |
| `get_cached_ai_service_di()` | Cached AI service with performance optimizations | `get_cached_ai_service_optional()` |
| `get_rag_service()` | RAG service (requires OpenSearch + AI) | Returns `None` if unavailable |
| `get_cached_rag_service()` | Cached RAG service | Returns `None` if unavailable |
| `get_connection_manager()` | WebSocket connection manager | - |
| `get_connection_manager_with_services()` | Connection manager with RAG/AI injected | - |

### Component-Level Dependencies

| Dependency | Description | Optional Variant |
|------------|-------------|------------------|
| `get_vector_store()` | Vector storage for knowledge chunks | `get_vector_store_optional()` |
| `get_search_service()` | Semantic search over vector store | `get_search_service_optional()` |
| `get_conversation_manager()` | Conversation state management | `get_conversation_manager_optional()` |
| `get_query_processor()` | Unified query processing | `get_query_processor_optional()` |
| `get_multimedia_generator()` | Multimedia content generation | Returns `None` if unavailable |
| `get_export_engine()` | Document export capabilities | Returns `None` if unavailable |

## Usage Patterns

### Basic Dependency Injection

```python
from fastapi import APIRouter, Depends
from multimodal_librarian.api.dependencies import get_ai_service

router = APIRouter()

@router.post("/generate")
async def generate_text(
    prompt: str,
    ai_service = Depends(get_ai_service)
):
    """Endpoint with injected AI service."""
    return await ai_service.generate(prompt)
```

### Optional Dependencies for Graceful Degradation

```python
from fastapi import APIRouter, Depends
from multimodal_librarian.api.dependencies import (
    get_rag_service,
    get_ai_service_optional,
)

router = APIRouter()

@router.post("/chat")
async def chat(
    message: str,
    rag_service = Depends(get_rag_service),
    ai_service = Depends(get_ai_service_optional)
):
    """Chat endpoint that degrades gracefully."""
    if rag_service is None:
        # RAG unavailable - use basic AI response
        if ai_service:
            return {"response": await ai_service.generate(message), "mode": "basic"}
        return {"response": "Service temporarily unavailable", "mode": "fallback"}
    
    # Full RAG-enhanced response
    return {"response": await rag_service.query(message), "mode": "rag"}
```

### WebSocket with Dependency Injection

```python
from fastapi import APIRouter, WebSocket, Depends
from multimodal_librarian.api.dependencies import (
    get_connection_manager_with_services,
)

router = APIRouter()

@router.websocket("/ws/chat")
async def websocket_chat(
    websocket: WebSocket,
    manager = Depends(get_connection_manager_with_services)
):
    """WebSocket endpoint with injected services."""
    connection_id = str(uuid4())
    await manager.connect(websocket, connection_id)
    
    try:
        while True:
            data = await websocket.receive_text()
            # Use manager.rag_service or manager.ai_service
            if manager.rag_available:
                response = await manager.rag_service.query(data)
            else:
                response = "RAG service unavailable"
            await manager.send_personal_message({"response": response}, connection_id)
    except WebSocketDisconnect:
        manager.disconnect(connection_id)
```

### Chained Dependencies

```python
from fastapi import Depends
from multimodal_librarian.api.dependencies import (
    get_opensearch_client_optional,
    get_ai_service,
)

async def get_rag_service(
    opensearch = Depends(get_opensearch_client_optional),
    ai_service = Depends(get_ai_service)
):
    """RAG service depends on OpenSearch and AI service."""
    if opensearch is None:
        return None  # Graceful degradation
    
    # Create RAG service with injected dependencies
    return RAGService(opensearch_client=opensearch, ai_service=ai_service)
```

## Testing with Dependency Overrides

### Mocking Dependencies in Tests

```python
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock

from multimodal_librarian.main import app
from multimodal_librarian.api.dependencies import (
    get_ai_service,
    get_opensearch_client,
)

@pytest.fixture
def mock_ai_service():
    """Create a mock AI service."""
    mock = MagicMock()
    mock.generate = AsyncMock(return_value="Mock response")
    return mock

@pytest.fixture
def client_with_mocks(mock_ai_service):
    """Test client with mocked dependencies."""
    app.dependency_overrides[get_ai_service] = lambda: mock_ai_service
    
    with TestClient(app) as client:
        yield client
    
    # Clean up overrides after test
    app.dependency_overrides.clear()

def test_generate_endpoint(client_with_mocks, mock_ai_service):
    """Test endpoint with mocked AI service."""
    response = client_with_mocks.post("/generate", json={"prompt": "Hello"})
    assert response.status_code == 200
    mock_ai_service.generate.assert_called_once()
```

### Testing Graceful Degradation

```python
@pytest.fixture
def client_without_opensearch():
    """Test client with OpenSearch unavailable."""
    # Override to return None (simulating unavailable service)
    app.dependency_overrides[get_opensearch_client_optional] = lambda: None
    
    with TestClient(app) as client:
        yield client
    
    app.dependency_overrides.clear()

def test_chat_without_rag(client_without_opensearch):
    """Test that chat works without RAG service."""
    response = client_without_opensearch.post("/chat", json={"message": "Hello"})
    assert response.status_code == 200
    assert response.json()["mode"] in ["basic", "fallback"]
```

## Application Lifecycle

### Lifespan Context Manager

The application uses FastAPI's lifespan context manager for proper startup/shutdown:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    # STARTUP: No blocking initialization
    # Background tasks for non-critical initialization
    app.state.background_init_task = asyncio.create_task(
        _background_initialization(app)
    )
    
    yield  # Application runs here
    
    # SHUTDOWN: Clean up all DI-managed services
    from multimodal_librarian.api.dependencies import cleanup_services
    await cleanup_services()

app = FastAPI(lifespan=lifespan)
```

### Cleanup Functions

```python
from multimodal_librarian.api.dependencies import (
    clear_all_caches,      # Clear all cached instances
    cleanup_services,       # Async cleanup with proper disconnection
    cleanup_all_dependencies,  # Full cleanup of all dependencies
)
```

## Anti-Patterns to Avoid

### ❌ Module-Level Instantiation

```python
# BAD: Creates instance at import time
from myapp.services import AIService
ai_service = AIService()  # Blocks during import!

@router.post("/generate")
async def generate(prompt: str):
    return await ai_service.generate(prompt)
```

### ❌ Global Singleton Functions

```python
# BAD: Global state that's hard to test
_cached_service = None

def get_service():
    global _cached_service
    if _cached_service is None:
        _cached_service = MyService()  # May block
    return _cached_service
```

### ❌ Calling Services in __init__

```python
# BAD: ConnectionManager calls services during construction
class ConnectionManager:
    def __init__(self):
        self.rag_service = get_cached_rag_service()  # Blocks!
```

### ✅ Correct Pattern

```python
# GOOD: Use FastAPI Depends for lazy initialization
from fastapi import Depends
from multimodal_librarian.api.dependencies import get_ai_service

@router.post("/generate")
async def generate(
    prompt: str,
    ai_service = Depends(get_ai_service)  # Lazy, testable
):
    return await ai_service.generate(prompt)
```

## Adding New Services

See the example in `docs/architecture/adding-new-services-with-di.md` for a complete guide on adding new services to the DI system.

## Related Documentation

- Design Document: `.kiro/specs/dependency-injection-architecture/design.md`
- Requirements: `.kiro/specs/dependency-injection-architecture/requirements.md`
- Tasks: `.kiro/specs/dependency-injection-architecture/tasks.md`
