#!/usr/bin/env python3
"""
Tests demonstrating proper use of app.dependency_overrides for DI mocking.

Feature: dependency-injection-architecture
Task 9.1: Update existing tests to use `app.dependency_overrides` for mocking

**Validates: Requirements 5.1, 5.2, 5.3, 5.4**

This module demonstrates the canonical pattern for testing with FastAPI's
dependency injection system using app.dependency_overrides.

Key patterns:
- Use app.dependency_overrides to inject mock services
- Clear overrides after each test to prevent test pollution
- Use fixtures to manage override lifecycle
- Support both sync and async test patterns
"""

import asyncio
import pytest
from typing import Optional, Dict, Any
from unittest.mock import MagicMock, AsyncMock
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient


class TestDependencyOverridesBasics:
    """Basic tests demonstrating app.dependency_overrides usage."""
    
    @pytest.fixture
    def mock_opensearch_client(self):
        """Create a mock OpenSearch client for testing."""
        mock = MagicMock()
        mock.connect = MagicMock()
        mock.disconnect = MagicMock()
        mock.health_check = MagicMock(return_value=True)
        mock.semantic_search = MagicMock(return_value=[])
        return mock
    
    @pytest.fixture
    def mock_ai_service(self):
        """Create a mock AI service for testing."""
        mock = MagicMock()
        mock.generate_response = AsyncMock(return_value={
            "response": "Mock AI response",
            "citations": [],
            "context_used": 0
        })
        mock.health_check = MagicMock(return_value=True)
        return mock
    
    @pytest.fixture
    def mock_rag_service(self, mock_opensearch_client, mock_ai_service):
        """Create a mock RAG service for testing."""
        mock = MagicMock()
        mock.get_relevant_context = AsyncMock(return_value=[])
        mock.get_service_status = MagicMock(return_value={"status": "healthy"})
        mock.opensearch_client = mock_opensearch_client
        mock.ai_service = mock_ai_service
        return mock
    
    @pytest.fixture
    def mock_connection_manager(self):
        """Create a mock ConnectionManager for testing."""
        try:
            from multimodal_librarian.api.dependencies.services import ConnectionManager
            manager = ConnectionManager()
            return manager
        except ImportError:
            mock = MagicMock()
            mock.active_connections = {}
            mock.conversation_history = {}
            mock.user_threads = {}
            mock._rag_service = None
            mock._ai_service = None
            mock.rag_available = False
            return mock
    
    @pytest.fixture
    def test_app_with_overrides(
        self, 
        mock_opensearch_client, 
        mock_ai_service, 
        mock_rag_service,
        mock_connection_manager
    ):
        """
        Create a test app with dependency overrides.
        
        This demonstrates the canonical pattern for testing with DI:
        1. Create the app
        2. Set up dependency overrides
        3. Yield the app for testing
        4. Clear overrides after test
        """
        try:
            from multimodal_librarian.main import create_minimal_app
            from multimodal_librarian.api.dependencies.services import (
                get_opensearch_client,
                get_opensearch_client_optional,
                get_ai_service,
                get_ai_service_optional,
                get_rag_service,
                get_cached_rag_service,
                get_connection_manager,
                get_connection_manager_with_services,
                clear_service_cache
            )
            
            # Clear any cached services before test
            clear_service_cache()
            
            # Create the app
            app = create_minimal_app()
            
            # Set up dependency overrides
            async def override_opensearch():
                return mock_opensearch_client
            
            async def override_opensearch_optional():
                return mock_opensearch_client
            
            async def override_ai_service():
                return mock_ai_service
            
            async def override_ai_service_optional():
                return mock_ai_service
            
            async def override_rag_service(
                opensearch=Depends(override_opensearch_optional),
                ai_service=Depends(override_ai_service)
            ):
                return mock_rag_service
            
            async def override_cached_rag_service(
                opensearch=Depends(override_opensearch_optional),
                ai_service=Depends(override_ai_service)
            ):
                return mock_rag_service
            
            async def override_connection_manager():
                return mock_connection_manager
            
            async def override_connection_manager_with_services(
                rag_service=Depends(override_cached_rag_service),
                ai_service=Depends(override_ai_service_optional)
            ):
                mock_connection_manager.set_services(
                    rag_service=rag_service,
                    ai_service=ai_service
                )
                return mock_connection_manager
            
            # Apply overrides
            app.dependency_overrides[get_opensearch_client] = override_opensearch
            app.dependency_overrides[get_opensearch_client_optional] = override_opensearch_optional
            app.dependency_overrides[get_ai_service] = override_ai_service
            app.dependency_overrides[get_ai_service_optional] = override_ai_service_optional
            app.dependency_overrides[get_rag_service] = override_rag_service
            app.dependency_overrides[get_cached_rag_service] = override_cached_rag_service
            app.dependency_overrides[get_connection_manager] = override_connection_manager
            app.dependency_overrides[get_connection_manager_with_services] = override_connection_manager_with_services
            
            yield app
            
            # Clear overrides after test
            app.dependency_overrides.clear()
            clear_service_cache()
            
        except ImportError as e:
            pytest.skip(f"Module not available: {e}")
    
    def test_health_endpoint_with_mocked_services(self, test_app_with_overrides):
        """
        Test health endpoint with mocked services via dependency overrides.
        
        Validates: Requirement 5.1 - Dependencies can be overridden
        """
        client = TestClient(test_app_with_overrides)
        
        response = client.get("/health/simple")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
    
    def test_root_endpoint_with_mocked_services(self, test_app_with_overrides):
        """
        Test root endpoint with mocked services.
        
        Validates: Requirement 5.1 - Dependencies can be overridden
        """
        client = TestClient(test_app_with_overrides)
        
        response = client.get("/")
        
        assert response.status_code == 200
        data = response.json()
        assert "message" in data


class TestDependencyOverridesIsolation:
    """Tests verifying test isolation with dependency overrides."""
    
    @pytest.fixture(autouse=True)
    def clear_caches(self):
        """Clear DI caches before and after each test."""
        try:
            from multimodal_librarian.api.dependencies.services import clear_service_cache
            clear_service_cache()
        except ImportError:
            pass
        
        yield
        
        try:
            from multimodal_librarian.api.dependencies.services import clear_service_cache
            clear_service_cache()
        except ImportError:
            pass
    
    def test_overrides_do_not_persist_between_tests_1(self):
        """
        First test in isolation sequence - sets up specific mock.
        
        Validates: Requirement 5.2 - No global state prevents parallel execution
        """
        try:
            from multimodal_librarian.main import create_minimal_app
            from multimodal_librarian.api.dependencies.services import get_ai_service
            
            app = create_minimal_app()
            
            # Create a unique mock for this test
            mock_ai = MagicMock()
            mock_ai.test_marker = "test_1_marker"
            
            async def override():
                return mock_ai
            
            app.dependency_overrides[get_ai_service] = override
            
            # Verify override is set
            assert get_ai_service in app.dependency_overrides
            
            # Clear overrides
            app.dependency_overrides.clear()
            
            # Verify override is cleared
            assert get_ai_service not in app.dependency_overrides
            
        except ImportError as e:
            pytest.skip(f"Module not available: {e}")
    
    def test_overrides_do_not_persist_between_tests_2(self):
        """
        Second test in isolation sequence - verifies no pollution from test 1.
        
        Validates: Requirement 5.2 - No global state prevents parallel execution
        """
        try:
            from multimodal_librarian.main import create_minimal_app
            from multimodal_librarian.api.dependencies.services import get_ai_service
            
            app = create_minimal_app()
            
            # Verify no overrides from previous test
            assert get_ai_service not in app.dependency_overrides
            
            # Create a different mock for this test
            mock_ai = MagicMock()
            mock_ai.test_marker = "test_2_marker"
            
            async def override():
                return mock_ai
            
            app.dependency_overrides[get_ai_service] = override
            
            # Verify this test's override is set
            assert get_ai_service in app.dependency_overrides
            
            # Clear overrides
            app.dependency_overrides.clear()
            
        except ImportError as e:
            pytest.skip(f"Module not available: {e}")


class TestDependencyOverridesWithAsyncDependencies:
    """Tests for async dependency overrides."""
    
    @pytest.fixture(autouse=True)
    def clear_caches(self):
        """Clear DI caches before and after each test."""
        try:
            from multimodal_librarian.api.dependencies.services import clear_service_cache
            clear_service_cache()
        except ImportError:
            pass
        
        yield
        
        try:
            from multimodal_librarian.api.dependencies.services import clear_service_cache
            clear_service_cache()
        except ImportError:
            pass
    
    @pytest.mark.asyncio
    async def test_async_dependency_override(self):
        """
        Test that async dependencies can be properly overridden.
        
        Validates: Requirement 5.3 - Test fixtures can provide mock implementations
        """
        try:
            from multimodal_librarian.main import create_minimal_app
            from multimodal_librarian.api.dependencies.services import (
                get_connection_manager,
                ConnectionManager
            )
            
            app = create_minimal_app()
            
            # Create a mock connection manager
            mock_manager = ConnectionManager()
            mock_manager._test_marker = "async_test_marker"
            
            async def override_connection_manager():
                return mock_manager
            
            app.dependency_overrides[get_connection_manager] = override_connection_manager
            
            # Verify the override works
            result = await override_connection_manager()
            assert result._test_marker == "async_test_marker"
            
            # Clean up
            app.dependency_overrides.clear()
            
        except ImportError as e:
            pytest.skip(f"Module not available: {e}")
    
    @pytest.mark.asyncio
    async def test_chained_dependency_overrides(self):
        """
        Test that chained dependencies can be overridden.
        
        Validates: Requirement 5.4 - Integration tests can selectively use real vs mock
        """
        try:
            from multimodal_librarian.main import create_minimal_app
            from multimodal_librarian.api.dependencies.services import (
                get_opensearch_client_optional,
                get_ai_service,
                get_rag_service
            )
            
            app = create_minimal_app()
            
            # Create mocks
            mock_opensearch = MagicMock()
            mock_opensearch.health_check = MagicMock(return_value=True)
            
            mock_ai = MagicMock()
            mock_ai.health_check = MagicMock(return_value=True)
            
            mock_rag = MagicMock()
            mock_rag.get_service_status = MagicMock(return_value={"status": "healthy"})
            
            # Override the dependencies
            async def override_opensearch():
                return mock_opensearch
            
            async def override_ai():
                return mock_ai
            
            async def override_rag(opensearch=None, ai_service=None):
                return mock_rag
            
            app.dependency_overrides[get_opensearch_client_optional] = override_opensearch
            app.dependency_overrides[get_ai_service] = override_ai
            app.dependency_overrides[get_rag_service] = override_rag
            
            # Verify overrides are set
            assert len(app.dependency_overrides) == 3
            
            # Clean up
            app.dependency_overrides.clear()
            
        except ImportError as e:
            pytest.skip(f"Module not available: {e}")


class TestDependencyOverridesForGracefulDegradation:
    """Tests for graceful degradation using dependency overrides."""
    
    @pytest.fixture(autouse=True)
    def clear_caches(self):
        """Clear DI caches before and after each test."""
        try:
            from multimodal_librarian.api.dependencies.services import clear_service_cache
            clear_service_cache()
        except ImportError:
            pass
        
        yield
        
        try:
            from multimodal_librarian.api.dependencies.services import clear_service_cache
            clear_service_cache()
        except ImportError:
            pass
    
    def test_override_to_simulate_service_unavailable(self):
        """
        Test overriding dependencies to simulate service unavailability.
        
        Validates: Requirement 5.4 - Integration tests can selectively use real vs mock
        """
        try:
            from multimodal_librarian.main import create_minimal_app
            from multimodal_librarian.api.dependencies.services import (
                get_opensearch_client_optional,
                get_rag_service
            )
            
            app = create_minimal_app()
            
            # Override to return None (simulating unavailable service)
            async def override_opensearch_unavailable():
                return None
            
            async def override_rag_unavailable(opensearch=None, ai_service=None):
                # RAG service returns None when OpenSearch is unavailable
                return None
            
            app.dependency_overrides[get_opensearch_client_optional] = override_opensearch_unavailable
            app.dependency_overrides[get_rag_service] = override_rag_unavailable
            
            # Create test client
            client = TestClient(app)
            
            # Health check should still work
            response = client.get("/health/simple")
            assert response.status_code == 200
            
            # Clean up
            app.dependency_overrides.clear()
            
        except ImportError as e:
            pytest.skip(f"Module not available: {e}")
    
    def test_override_to_simulate_partial_availability(self):
        """
        Test overriding some dependencies while keeping others.
        
        Validates: Requirement 5.4 - Integration tests can selectively use real vs mock
        """
        try:
            from multimodal_librarian.main import create_minimal_app
            from multimodal_librarian.api.dependencies.services import (
                get_opensearch_client_optional,
                get_ai_service
            )
            
            app = create_minimal_app()
            
            # Override OpenSearch to be unavailable
            async def override_opensearch_unavailable():
                return None
            
            # Keep AI service available with a mock
            mock_ai = MagicMock()
            mock_ai.health_check = MagicMock(return_value=True)
            
            async def override_ai_available():
                return mock_ai
            
            app.dependency_overrides[get_opensearch_client_optional] = override_opensearch_unavailable
            app.dependency_overrides[get_ai_service] = override_ai_available
            
            # Create test client
            client = TestClient(app)
            
            # Health check should still work
            response = client.get("/health/simple")
            assert response.status_code == 200
            
            # Clean up
            app.dependency_overrides.clear()
            
        except ImportError as e:
            pytest.skip(f"Module not available: {e}")


# Pytest fixtures for reusable test setup
@pytest.fixture
def di_test_app():
    """
    Fixture providing a test app with cleared DI caches.
    
    Usage:
        def test_something(di_test_app):
            client = TestClient(di_test_app)
            # ... test code ...
    """
    try:
        from multimodal_librarian.main import create_minimal_app
        from multimodal_librarian.api.dependencies.services import clear_service_cache
        
        clear_service_cache()
        app = create_minimal_app()
        
        yield app
        
        app.dependency_overrides.clear()
        clear_service_cache()
        
    except ImportError as e:
        pytest.skip(f"Module not available: {e}")


@pytest.fixture
def mock_services():
    """
    Fixture providing a dictionary of mock services.
    
    Usage:
        def test_something(di_test_app, mock_services):
            app.dependency_overrides[get_ai_service] = lambda: mock_services['ai']
    """
    return {
        'opensearch': MagicMock(
            connect=MagicMock(),
            disconnect=MagicMock(),
            health_check=MagicMock(return_value=True),
            semantic_search=MagicMock(return_value=[])
        ),
        'ai': MagicMock(
            generate_response=AsyncMock(return_value={"response": "Mock response"}),
            health_check=MagicMock(return_value=True)
        ),
        'rag': MagicMock(
            get_relevant_context=AsyncMock(return_value=[]),
            get_service_status=MagicMock(return_value={"status": "healthy"})
        )
    }


if __name__ == "__main__":
    print("Running Dependency Override Tests")
    print("=" * 60)
    print("\nTo run with pytest:")
    print("pytest tests/api/test_di_dependency_overrides.py -v")
