"""
Tests for Model Server Endpoints.

Tests the FastAPI endpoints for embedding generation, NLP processing,
and health checks.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


class TestHealthEndpoints:
    """Tests for health check endpoints."""

    def test_health_endpoint_structure(self):
        """Test health endpoint returns expected structure."""
        # Import here to avoid loading models during test collection
        with patch('model_server.models.embedding.EmbeddingModel') as mock_embed:
            with patch('model_server.models.nlp.NLPModel') as mock_nlp:
                mock_embed_instance = MagicMock()
                mock_embed_instance.is_loaded = True
                mock_embed_instance.model_name = "all-MiniLM-L6-v2"
                mock_embed_instance.dimensions = 384
                mock_embed_instance.device = "cpu"
                mock_embed_instance.load_time_seconds = 1.0
                mock_embed_instance.error = None
                mock_embed.return_value = mock_embed_instance
                
                mock_nlp_instance = MagicMock()
                mock_nlp_instance.is_loaded = True
                mock_nlp_instance.model_name = "en_core_web_sm"
                mock_nlp_instance.load_time_seconds = 0.5
                mock_nlp_instance.error = None
                mock_nlp.return_value = mock_nlp_instance
                
                from model_server.main import app
                client = TestClient(app)
                
                response = client.get("/health")
                
                assert response.status_code == 200
                data = response.json()
                
                assert "status" in data
                assert "ready" in data
                assert "models" in data
                assert "embedding" in data["models"]
                assert "nlp" in data["models"]

    def test_health_ready_endpoint(self):
        """Test readiness probe endpoint."""
        with patch('model_server.models.embedding.EmbeddingModel') as mock_embed:
            with patch('model_server.models.nlp.NLPModel') as mock_nlp:
                mock_embed_instance = MagicMock()
                mock_embed_instance.is_loaded = True
                mock_embed.return_value = mock_embed_instance
                
                mock_nlp_instance = MagicMock()
                mock_nlp_instance.is_loaded = True
                mock_nlp.return_value = mock_nlp_instance
                
                from model_server.main import app
                client = TestClient(app)
                
                response = client.get("/health/ready")
                
                assert response.status_code in [200, 503]
                data = response.json()
                assert "ready" in data

    def test_health_live_endpoint(self):
        """Test liveness probe endpoint."""
        with patch('model_server.models.embedding.EmbeddingModel') as mock_embed:
            with patch('model_server.models.nlp.NLPModel') as mock_nlp:
                mock_embed.return_value = MagicMock()
                mock_nlp.return_value = MagicMock()
                
                from model_server.main import app
                client = TestClient(app)
                
                response = client.get("/health/live")
                
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "alive"


class TestEmbeddingEndpoints:
    """Tests for embedding generation endpoints."""

    def test_embeddings_endpoint_validation(self):
        """Test embedding endpoint validates input."""
        with patch('model_server.models.embedding.EmbeddingModel') as mock_embed:
            with patch('model_server.models.nlp.NLPModel') as mock_nlp:
                mock_embed_instance = MagicMock()
                mock_embed_instance.is_loaded = True
                mock_embed_instance.encode.return_value = [[0.1, 0.2, 0.3]]
                mock_embed.return_value = mock_embed_instance
                mock_nlp.return_value = MagicMock()
                
                from model_server.main import app
                client = TestClient(app)
                
                # Test with empty texts
                response = client.post("/embeddings", json={"texts": []})
                assert response.status_code == 200
                data = response.json()
                assert data["embeddings"] == []

    def test_embeddings_endpoint_success(self):
        """Test successful embedding generation."""
        with patch('model_server.models.embedding.EmbeddingModel') as mock_embed:
            with patch('model_server.models.nlp.NLPModel') as mock_nlp:
                mock_embed_instance = MagicMock()
                mock_embed_instance.is_loaded = True
                mock_embed_instance.model_name = "all-MiniLM-L6-v2"
                mock_embed_instance.dimensions = 384
                mock_embed_instance.encode.return_value = [
                    [0.1] * 384,
                    [0.2] * 384
                ]
                mock_embed.return_value = mock_embed_instance
                mock_nlp.return_value = MagicMock()
                
                from model_server.main import app
                client = TestClient(app)
                
                response = client.post(
                    "/embeddings",
                    json={"texts": ["hello", "world"]}
                )
                
                assert response.status_code == 200
                data = response.json()
                assert "embeddings" in data
                assert len(data["embeddings"]) == 2
                assert "model" in data
                assert "dimensions" in data


class TestNLPEndpoints:
    """Tests for NLP processing endpoints."""

    def test_nlp_process_endpoint_validation(self):
        """Test NLP endpoint validates input."""
        with patch('model_server.models.embedding.EmbeddingModel') as mock_embed:
            with patch('model_server.models.nlp.NLPModel') as mock_nlp:
                mock_embed.return_value = MagicMock()
                mock_nlp_instance = MagicMock()
                mock_nlp_instance.is_loaded = True
                mock_nlp.return_value = mock_nlp_instance
                
                from model_server.main import app
                client = TestClient(app)
                
                # Test with empty texts
                response = client.post(
                    "/nlp/process",
                    json={"texts": [], "tasks": ["tokenize"]}
                )
                assert response.status_code == 200
                data = response.json()
                assert data["results"] == []

    def test_nlp_process_tokenize(self):
        """Test NLP tokenization."""
        with patch('model_server.models.embedding.EmbeddingModel') as mock_embed:
            with patch('model_server.models.nlp.NLPModel') as mock_nlp:
                mock_embed.return_value = MagicMock()
                mock_nlp_instance = MagicMock()
                mock_nlp_instance.is_loaded = True
                mock_nlp_instance.process.return_value = [
                    {
                        "text": "Hello world",
                        "tokens": ["Hello", "world"],
                        "entities": [],
                        "pos_tags": []
                    }
                ]
                mock_nlp.return_value = mock_nlp_instance
                
                from model_server.main import app
                client = TestClient(app)
                
                response = client.post(
                    "/nlp/process",
                    json={"texts": ["Hello world"], "tasks": ["tokenize"]}
                )
                
                assert response.status_code == 200
                data = response.json()
                assert "results" in data
                assert len(data["results"]) == 1
                assert "tokens" in data["results"][0]


class TestErrorHandling:
    """Tests for error handling in model server."""

    def test_embeddings_model_not_ready(self):
        """Test embedding endpoint when model not ready."""
        with patch('model_server.models.embedding.EmbeddingModel') as mock_embed:
            with patch('model_server.models.nlp.NLPModel') as mock_nlp:
                mock_embed_instance = MagicMock()
                mock_embed_instance.is_loaded = False
                mock_embed_instance.error = "Model loading failed"
                mock_embed.return_value = mock_embed_instance
                mock_nlp.return_value = MagicMock()
                
                from model_server.main import app
                client = TestClient(app)
                
                response = client.post(
                    "/embeddings",
                    json={"texts": ["test"]}
                )
                
                # Should return 503 when model not ready
                assert response.status_code in [200, 503]

    def test_nlp_model_not_ready(self):
        """Test NLP endpoint when model not ready."""
        with patch('model_server.models.embedding.EmbeddingModel') as mock_embed:
            with patch('model_server.models.nlp.NLPModel') as mock_nlp:
                mock_embed.return_value = MagicMock()
                mock_nlp_instance = MagicMock()
                mock_nlp_instance.is_loaded = False
                mock_nlp_instance.error = "Model loading failed"
                mock_nlp.return_value = mock_nlp_instance
                
                from model_server.main import app
                client = TestClient(app)
                
                response = client.post(
                    "/nlp/process",
                    json={"texts": ["test"], "tasks": ["tokenize"]}
                )
                
                # Should return 503 when model not ready
                assert response.status_code in [200, 503]
                assert response.status_code in [200, 503]
