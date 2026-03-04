# Adding New Services with Dependency Injection

This guide shows how to add new services to the Multimodal Librarian application using the FastAPI dependency injection pattern.

## Overview

When adding a new service, follow these steps:
1. Create the service class
2. Add a dependency provider function
3. Export the dependency
4. Use the dependency in routers

## Step-by-Step Example: Adding a Translation Service

### Step 1: Create the Service Class

Create your service in `src/multimodal_librarian/services/translation_service.py`:

```python
"""
Translation Service

Provides text translation capabilities using external APIs.
"""

import logging
from typing import Optional, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class TranslationResult:
    """Result of a translation operation."""
    original_text: str
    translated_text: str
    source_language: str
    target_language: str
    confidence: float


class TranslationService:
    """
    Service for translating text between languages.
    
    This service is designed for dependency injection:
    - Constructor does NOT establish connections
    - Connections are established lazily on first use
    - Service can be mocked for testing
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the translation service.
        
        IMPORTANT: Do NOT establish connections here.
        This constructor should be fast and non-blocking.
        
        Args:
            api_key: Optional API key for translation service
        """
        self._api_key = api_key
        self._client = None  # Lazy initialization
        self._connected = False
        logger.info("TranslationService initialized (lazy, no connections)")
    
    def _ensure_connected(self):
        """Lazily establish connection on first use."""
        if not self._connected:
            # Initialize client here (e.g., connect to translation API)
            logger.info("TranslationService establishing connection...")
            self._client = self._create_client()
            self._connected = True
            logger.info("TranslationService connected successfully")
    
    def _create_client(self):
        """Create the translation API client."""
        # In a real implementation, this would create the API client
        # For example: return TranslationAPIClient(api_key=self._api_key)
        return {"mock": True}  # Placeholder
    
    async def translate(
        self,
        text: str,
        target_language: str,
        source_language: Optional[str] = None
    ) -> TranslationResult:
        """
        Translate text to the target language.
        
        Args:
            text: Text to translate
            target_language: Target language code (e.g., 'es', 'fr')
            source_language: Source language code (auto-detect if None)
        
        Returns:
            TranslationResult with translated text
        """
        self._ensure_connected()
        
        # Perform translation (placeholder implementation)
        detected_source = source_language or "en"
        translated = f"[Translated to {target_language}]: {text}"
        
        return TranslationResult(
            original_text=text,
            translated_text=translated,
            source_language=detected_source,
            target_language=target_language,
            confidence=0.95
        )
    
    def disconnect(self):
        """Clean up resources."""
        if self._connected:
            logger.info("TranslationService disconnecting...")
            self._client = None
            self._connected = False
            logger.info("TranslationService disconnected")
```

### Step 2: Add Dependency Provider

Add the dependency provider to `src/multimodal_librarian/api/dependencies/services.py`:

```python
# Add to the cached instances section at the top of the file
_translation_service: Optional["TranslationService"] = None


async def get_translation_service() -> "TranslationService":
    """
    FastAPI dependency for TranslationService.
    
    Lazily creates and caches the translation service on first use.
    
    Returns:
        TranslationService instance
    
    Raises:
        HTTPException: If service initialization fails (503 Service Unavailable)
    """
    global _translation_service
    
    if _translation_service is None:
        # Import here to avoid import-time side effects
        from ...services.translation_service import TranslationService
        
        try:
            logger.info("Initializing TranslationService via DI (lazy)")
            _translation_service = TranslationService()
            logger.info("TranslationService initialized successfully via DI")
        except Exception as e:
            logger.error(f"TranslationService initialization failed: {e}")
            raise HTTPException(
                status_code=503,
                detail="Translation service unavailable"
            )
    
    return _translation_service


async def get_translation_service_optional() -> Optional["TranslationService"]:
    """
    Optional TranslationService dependency - returns None if unavailable.
    
    Use this for endpoints that can function without translation.
    
    Returns:
        TranslationService instance or None if unavailable
    """
    try:
        return await get_translation_service()
    except HTTPException:
        logger.warning("TranslationService unavailable, returning None")
        return None
    except Exception as e:
        logger.warning(f"TranslationService error, returning None: {e}")
        return None
```

Also update the `clear_all_caches()` function to include the new service:

```python
def clear_all_caches():
    """Clear all cached service and component instances."""
    global _translation_service  # Add this
    # ... existing globals ...
    
    # Disconnect translation service if connected
    if _translation_service is not None:
        try:
            _translation_service.disconnect()
        except Exception as e:
            logger.warning(f"Error disconnecting TranslationService: {e}")
    
    # ... existing cleanup code ...
    
    _translation_service = None  # Add this
```

### Step 3: Export the Dependency

Add exports to `src/multimodal_librarian/api/dependencies/__init__.py`:

```python
from .services import (
    # ... existing imports ...
    get_translation_service,
    get_translation_service_optional,
)

__all__ = [
    # ... existing exports ...
    "get_translation_service",
    "get_translation_service_optional",
]
```

### Step 4: Use in Router

Create a router that uses the new service in `src/multimodal_librarian/api/routers/translation.py`:

```python
"""
Translation router for text translation endpoints.

Uses dependency injection for the TranslationService.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from ..dependencies import (
    get_translation_service,
    get_translation_service_optional,
)

router = APIRouter(prefix="/translation", tags=["translation"])


class TranslateRequest(BaseModel):
    """Request model for translation."""
    text: str
    target_language: str
    source_language: Optional[str] = None


class TranslateResponse(BaseModel):
    """Response model for translation."""
    original_text: str
    translated_text: str
    source_language: str
    target_language: str
    confidence: float


@router.post("/translate", response_model=TranslateResponse)
async def translate_text(
    request: TranslateRequest,
    translation_service = Depends(get_translation_service)
):
    """
    Translate text to the target language.
    
    Uses dependency injection for the TranslationService.
    The service is lazily initialized on first request.
    
    Args:
        request: Translation request with text and target language
        translation_service: Injected TranslationService
    
    Returns:
        TranslateResponse with translated text
    """
    result = await translation_service.translate(
        text=request.text,
        target_language=request.target_language,
        source_language=request.source_language
    )
    
    return TranslateResponse(
        original_text=result.original_text,
        translated_text=result.translated_text,
        source_language=result.source_language,
        target_language=result.target_language,
        confidence=result.confidence
    )


@router.get("/status")
async def translation_status(
    translation_service = Depends(get_translation_service_optional)
):
    """
    Check translation service status.
    
    Uses optional dependency injection - returns status even if
    service is unavailable (graceful degradation).
    """
    if translation_service is None:
        return {
            "status": "unavailable",
            "message": "Translation service is not available"
        }
    
    return {
        "status": "available",
        "message": "Translation service is ready"
    }
```

### Step 5: Register the Router

Add the router to `src/multimodal_librarian/main.py`:

```python
# Import the router
from .api.routers import translation

# Register the router
app.include_router(translation.router)
```

## Testing the New Service

### Unit Test with Mocked Dependency

```python
"""Tests for translation router with mocked service."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock
from dataclasses import dataclass

from multimodal_librarian.main import app
from multimodal_librarian.api.dependencies import get_translation_service


@dataclass
class MockTranslationResult:
    original_text: str = "Hello"
    translated_text: str = "Hola"
    source_language: str = "en"
    target_language: str = "es"
    confidence: float = 0.99


@pytest.fixture
def mock_translation_service():
    """Create a mock translation service."""
    mock = MagicMock()
    mock.translate = AsyncMock(return_value=MockTranslationResult())
    return mock


@pytest.fixture
def client_with_mock(mock_translation_service):
    """Test client with mocked translation service."""
    app.dependency_overrides[get_translation_service] = lambda: mock_translation_service
    
    with TestClient(app) as client:
        yield client
    
    app.dependency_overrides.clear()


def test_translate_endpoint(client_with_mock, mock_translation_service):
    """Test translation endpoint with mocked service."""
    response = client_with_mock.post(
        "/translation/translate",
        json={
            "text": "Hello",
            "target_language": "es"
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["translated_text"] == "Hola"
    assert data["target_language"] == "es"
    mock_translation_service.translate.assert_called_once()


def test_status_when_unavailable(client_with_mock):
    """Test status endpoint when service unavailable."""
    # Override to return None (simulating unavailable service)
    from multimodal_librarian.api.dependencies import get_translation_service_optional
    app.dependency_overrides[get_translation_service_optional] = lambda: None
    
    response = client_with_mock.get("/translation/status")
    
    assert response.status_code == 200
    assert response.json()["status"] == "unavailable"
```

## Checklist for Adding New Services

- [ ] Service class created with lazy initialization
- [ ] Constructor does NOT establish connections
- [ ] `disconnect()` method implemented for cleanup
- [ ] Dependency provider function added to `services.py`
- [ ] Optional variant added for graceful degradation
- [ ] Dependencies exported in `__init__.py`
- [ ] Router created using `Depends()`
- [ ] Router registered in `main.py`
- [ ] `clear_all_caches()` updated to include new service
- [ ] Unit tests written with mocked dependencies
- [ ] Integration tests verify real service behavior

## Common Patterns

### Service with External Dependencies

```python
async def get_my_service(
    ai_service = Depends(get_ai_service),
    opensearch = Depends(get_opensearch_client_optional)
) -> "MyService":
    """Service that depends on other services."""
    global _my_service
    
    if _my_service is None:
        from ...services.my_service import MyService
        _my_service = MyService(
            ai_service=ai_service,
            opensearch_client=opensearch
        )
    
    return _my_service
```

### Service with Configuration

```python
async def get_configured_service() -> "ConfiguredService":
    """Service that uses configuration."""
    global _configured_service
    
    if _configured_service is None:
        from ...services.configured_service import ConfiguredService
        from ...config import get_settings
        
        settings = get_settings()
        _configured_service = ConfiguredService(
            api_key=settings.service_api_key,
            timeout=settings.service_timeout
        )
    
    return _configured_service
```

## Related Documentation

- [Dependency Injection Steering](.kiro/steering/dependency-injection.md)
- [DI Architecture Design](.kiro/specs/dependency-injection-architecture/design.md)
- [FastAPI Dependencies Documentation](https://fastapi.tiangolo.com/tutorial/dependencies/)
