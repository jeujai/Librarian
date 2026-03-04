"""
Tests for Model Server Client.

Tests the async HTTP client for communicating with the model server,
including retry logic, timeout handling, and error handling.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from multimodal_librarian.clients.model_server_client import (
    ModelServerClient,
    ModelServerError,
    ModelServerUnavailable,
    cleanup_model_client,
    get_model_client,
    initialize_model_client,
)


class TestModelServerClient:
    """Tests for ModelServerClient class."""

    def test_init_default_values(self):
        """Test client initialization with default values."""
        client = ModelServerClient()
        
        assert client.base_url == "http://model-server:8001"
        assert client.timeout == 30.0
        assert client.max_retries == 3
        assert client.retry_delay == 1.0
        assert client.enabled is True
        assert client._session is None
        assert client._healthy is False

    def test_init_custom_values(self):
        """Test client initialization with custom values."""
        client = ModelServerClient(
            base_url="http://localhost:9000",
            timeout=60.0,
            max_retries=5,
            retry_delay=2.0,
            enabled=False
        )
        
        assert client.base_url == "http://localhost:9000"
        assert client.timeout == 60.0
        assert client.max_retries == 5
        assert client.retry_delay == 2.0
        assert client.enabled is False

    def test_base_url_trailing_slash_removed(self):
        """Test that trailing slash is removed from base URL."""
        client = ModelServerClient(base_url="http://localhost:8001/")
        assert client.base_url == "http://localhost:8001"

    def test_get_status(self):
        """Test get_status returns correct information."""
        client = ModelServerClient(
            base_url="http://test:8001",
            timeout=15.0,
            max_retries=2,
            enabled=True
        )
        
        status = client.get_status()
        
        assert status["base_url"] == "http://test:8001"
        assert status["enabled"] is True
        assert status["healthy"] is False
        assert status["timeout"] == 15.0
        assert status["max_retries"] == 2


class TestModelServerClientDisabled:
    """Tests for disabled model server client."""

    @pytest.mark.asyncio
    async def test_request_when_disabled_raises_error(self):
        """Test that requests fail when client is disabled."""
        client = ModelServerClient(enabled=False)
        
        with pytest.raises(ModelServerUnavailable) as exc_info:
            await client._request("GET", "/health")
        
        assert "disabled" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_generate_embeddings_when_disabled(self):
        """Test embedding generation fails when disabled."""
        client = ModelServerClient(enabled=False)
        
        with pytest.raises(ModelServerUnavailable):
            await client.generate_embeddings(["test text"])

    @pytest.mark.asyncio
    async def test_process_nlp_when_disabled(self):
        """Test NLP processing fails when disabled."""
        client = ModelServerClient(enabled=False)
        
        with pytest.raises(ModelServerUnavailable):
            await client.process_nlp(["test text"])


class TestModelServerClientRequests:
    """Tests for model server client HTTP requests."""

    @pytest.mark.asyncio
    async def test_generate_embeddings_empty_list(self):
        """Test that empty list returns empty result."""
        client = ModelServerClient()
        result = await client.generate_embeddings([])
        assert result == []

    @pytest.mark.asyncio
    async def test_process_nlp_empty_list(self):
        """Test that empty list returns empty result."""
        client = ModelServerClient()
        result = await client.process_nlp([])
        assert result == []

    @pytest.mark.asyncio
    async def test_tokenize_empty_list(self):
        """Test tokenize with empty list."""
        client = ModelServerClient()
        result = await client.tokenize([])
        assert result == []

    @pytest.mark.asyncio
    async def test_get_entities_empty_list(self):
        """Test get_entities with empty list."""
        client = ModelServerClient()
        result = await client.get_entities([])
        assert result == []


class TestModelServerClientMocked:
    """Tests with mocked HTTP responses."""

    @pytest.mark.asyncio
    async def test_health_check_success(self):
        """Test successful health check."""
        client = ModelServerClient()
        
        mock_response = {
            "status": "healthy",
            "ready": True,
            "models": {
                "embedding": {"status": "loaded", "name": "all-MiniLM-L6-v2"},
                "nlp": {"status": "loaded", "name": "en_core_web_sm"}
            }
        }
        
        with patch.object(client, '_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            
            result = await client.health_check()
            
            assert result["status"] == "healthy"
            assert result["ready"] is True
            assert client._healthy is True
            mock_request.assert_called_once_with("GET", "/health", retry=False)

    @pytest.mark.asyncio
    async def test_health_check_failure_sets_unhealthy(self):
        """Test that failed health check sets client as unhealthy."""
        client = ModelServerClient()
        client._healthy = True  # Start as healthy
        
        with patch.object(client, '_request', new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = ModelServerUnavailable("Connection failed")
            
            with pytest.raises(ModelServerError):
                await client.health_check()
            
            assert client._healthy is False

    @pytest.mark.asyncio
    async def test_is_ready_returns_true(self):
        """Test is_ready returns True when server is ready."""
        client = ModelServerClient()
        
        with patch.object(client, '_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"ready": True}
            
            result = await client.is_ready()
            
            assert result is True

    @pytest.mark.asyncio
    async def test_is_ready_returns_false_on_error(self):
        """Test is_ready returns False on error."""
        client = ModelServerClient()
        
        with patch.object(client, '_request', new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = ModelServerUnavailable("Connection failed")
            
            result = await client.is_ready()
            
            assert result is False

    @pytest.mark.asyncio
    async def test_generate_embeddings_success(self):
        """Test successful embedding generation."""
        client = ModelServerClient()
        
        mock_response = {
            "embeddings": [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]],
            "model": "all-MiniLM-L6-v2",
            "dimensions": 384
        }
        
        with patch.object(client, '_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            
            result = await client.generate_embeddings(["text1", "text2"])
            
            assert len(result) == 2
            assert result[0] == [0.1, 0.2, 0.3]
            mock_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_nlp_success(self):
        """Test successful NLP processing."""
        client = ModelServerClient()
        
        mock_response = {
            "results": [
                {
                    "text": "Hello world",
                    "tokens": ["Hello", "world"],
                    "entities": [],
                    "pos_tags": [{"token": "Hello", "pos": "INTJ"}]
                }
            ]
        }
        
        with patch.object(client, '_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            
            result = await client.process_nlp(["Hello world"])
            
            assert len(result) == 1
            assert result[0]["tokens"] == ["Hello", "world"]

    @pytest.mark.asyncio
    async def test_close_session(self):
        """Test closing the HTTP session."""
        client = ModelServerClient()
        
        # Create a mock session
        mock_session = MagicMock()
        mock_session.closed = False
        mock_session.close = AsyncMock()
        client._session = mock_session
        
        await client.close()
        
        mock_session.close.assert_called_once()
        assert client._session is None


class TestGlobalClientFunctions:
    """Tests for global client management functions."""

    @pytest.mark.asyncio
    async def test_initialize_and_get_client(self):
        """Test initializing and getting the global client."""
        # Clean up any existing client
        await cleanup_model_client()
        
        # Initialize new client
        client = await initialize_model_client(
            base_url="http://test:8001",
            timeout=10.0,
            enabled=True
        )
        
        assert client is not None
        assert client.base_url == "http://test:8001"
        
        # Get the same client
        retrieved = get_model_client()
        assert retrieved is client
        
        # Clean up
        await cleanup_model_client()
        assert get_model_client() is None

    @pytest.mark.asyncio
    async def test_cleanup_model_client(self):
        """Test cleanup closes session and clears global."""
        await initialize_model_client()
        
        client = get_model_client()
        assert client is not None
        
        await cleanup_model_client()
        
        assert get_model_client() is None
        assert get_model_client() is None
