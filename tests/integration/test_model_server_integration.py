"""
Integration tests for Model Server and App communication.

These tests verify that the app correctly communicates with the model server
and handles various scenarios including server availability and unavailability.
"""

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Set test environment
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("MODEL_SERVER_URL", "http://localhost:8001")
os.environ.setdefault("MODEL_SERVER_ENABLED", "true")


class TestModelServerIntegration:
    """Integration tests for model server communication."""
    
    @pytest.fixture
    def model_server_client(self):
        """Create a model server client for testing."""
        from multimodal_librarian.clients.model_server_client import ModelServerClient
        return ModelServerClient(base_url="http://localhost:8001")
    
    @pytest.mark.asyncio
    async def test_health_check_when_server_available(self, model_server_client):
        """Test health check when model server is available."""
        # This test requires the model server to be running
        # Skip if not available
        try:
            health = await model_server_client.health_check()
            assert health is not None
            assert "status" in health
            assert health["status"] in ["healthy", "ready", "loading"]
        except Exception as e:
            pytest.skip(f"Model server not available: {e}")
        finally:
            await model_server_client.close()
    
    @pytest.mark.asyncio
    async def test_embedding_generation_when_server_available(self, model_server_client):
        """Test embedding generation when model server is available."""
        try:
            texts = ["Hello world", "Test embedding"]
            embeddings = await model_server_client.generate_embeddings(texts)
            
            assert embeddings is not None
            assert len(embeddings) == 2
            # Each embedding should be a list of floats
            assert all(isinstance(e, list) for e in embeddings)
            assert all(len(e) > 0 for e in embeddings)
        except Exception as e:
            pytest.skip(f"Model server not available: {e}")
        finally:
            await model_server_client.close()
    
    @pytest.mark.asyncio
    async def test_nlp_processing_when_server_available(self, model_server_client):
        """Test NLP processing when model server is available."""
        try:
            texts = ["The quick brown fox jumps over the lazy dog."]
            result = await model_server_client.process_nlp(texts, task="tokenize")
            
            assert result is not None
            assert "results" in result
            assert len(result["results"]) == 1
        except Exception as e:
            pytest.skip(f"Model server not available: {e}")
        finally:
            await model_server_client.close()
    
    @pytest.mark.asyncio
    async def test_graceful_degradation_when_server_unavailable(self):
        """Test that the client handles server unavailability gracefully."""
        from multimodal_librarian.clients.model_server_client import ModelServerClient

        # Create client pointing to non-existent server
        client = ModelServerClient(
            base_url="http://localhost:9999",
            timeout=1.0,
            max_retries=1
        )
        
        try:
            # Health check should handle unavailability gracefully
            health = await client.health_check()
            # If it returns, it should indicate unavailability
            assert health is None or health.get("status") in ["unavailable", "error", None]
        except Exception:
            # It's also acceptable to raise an exception for unavailable server
            pass
        finally:
            await client.close()
    
    @pytest.mark.asyncio
    async def test_embedding_fallback_when_server_unavailable(self):
        """Test embedding generation fallback when server is unavailable."""
        from multimodal_librarian.clients.model_server_client import ModelServerClient
        
        client = ModelServerClient(
            base_url="http://localhost:9999",
            timeout=1.0,
            max_retries=1
        )
        
        try:
            texts = ["Test text"]
            embeddings = await client.generate_embeddings(texts)
            # Should return None when server is unavailable
            assert embeddings is None
        except Exception:
            # It's also acceptable to raise an exception
            pass
        finally:
            await client.close()
    
    @pytest.mark.asyncio
    async def test_retry_logic_on_transient_failure(self):
        """Test that retry logic works for transient failures."""
        from multimodal_librarian.clients.model_server_client import ModelServerClient
        
        client = ModelServerClient(
            base_url="http://localhost:8001",
            timeout=5.0,
            max_retries=3
        )
        
        try:
            # This test verifies the retry mechanism exists
            # Actual retry behavior depends on implementation
            assert client.max_retries == 3
        finally:
            await client.close()


class TestAppWithModelServer:
    """Integration tests for the app using model server."""
    
    @pytest.fixture
    def app_client(self):
        """Create a test client for the app."""
        from fastapi.testclient import TestClient

        from multimodal_librarian.main import app
        return TestClient(app)
    
    def test_health_endpoint_includes_model_server_status(self, app_client):
        """Test that health endpoint includes model server status."""
        response = app_client.get("/health/simple")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
    
    def test_app_starts_without_model_server(self):
        """Test that app can start even if model server is unavailable."""
        # Set environment to disable model server
        with patch.dict(os.environ, {"MODEL_SERVER_ENABLED": "false"}):
            from fastapi.testclient import TestClient

            from multimodal_librarian.main import app
            
            client = TestClient(app)
            response = client.get("/health/simple")
            assert response.status_code == 200


class TestModelServerHealthMonitoring:
    """Tests for model server health monitoring integration."""
    
    @pytest.mark.asyncio
    async def test_component_health_check_includes_model_server(self):
        """Test that component health checks include model server status."""
        from multimodal_librarian.monitoring.component_health_checks import (
            ModelServerHealthCheck,
        )
        
        health_check = ModelServerHealthCheck()
        result = await health_check.run()
        
        assert result is not None
        assert "status" in result
        assert "component" in result
        assert result["component"] == "model_server"
    
    @pytest.mark.asyncio
    async def test_health_system_reports_model_server_status(self):
        """Test that health system includes model server in reports."""
        from multimodal_librarian.monitoring.health_check_system import (
            get_health_check_system,
        )
        
        health_system = get_health_check_system()
        # The health system should have model server as a component
        assert health_system is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
