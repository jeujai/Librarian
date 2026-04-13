"""
Model Server Client

Async HTTP client for communicating with the dedicated model server.
Provides embedding generation and NLP processing via the model server API.
"""

import asyncio
import logging
import os
from typing import Any, Dict, List, Optional

import aiohttp

logger = logging.getLogger(__name__)

# Global client instance
_model_client: Optional["ModelServerClient"] = None


class ModelServerError(Exception):
    """Exception raised for model server errors."""
    pass


class ModelServerUnavailable(ModelServerError):
    """Exception raised when model server is unavailable."""
    pass


class ModelServerClient:
    """
    Async HTTP client for the model server.
    
    Provides methods for embedding generation and NLP processing
    with retry logic and connection pooling.
    """
    
    def __init__(
        self,
        base_url: str = "http://model-server:8001",
        timeout: float = 30.0,
        max_retries: int = 5,
        retry_delay: float = 1.0,
        enabled: bool = True
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.enabled = enabled
        self._session: Optional[aiohttp.ClientSession] = None
        self._healthy = False
        self._last_health_check: Optional[float] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create the aiohttp session.
        
        Creates a new session if:
        - No session exists
        - Session is closed
        - Session is attached to a different event loop (Celery worker issue)
        """
        try:
            # Check if we need a new session
            need_new_session = (
                self._session is None or 
                self._session.closed
            )
            
            # Also check if the session's connector is attached to the current loop
            if not need_new_session and self._session._connector is not None:
                try:
                    current_loop = asyncio.get_running_loop()
                    # If connector's loop doesn't match current loop, we need a new session
                    if hasattr(self._session._connector, '_loop'):
                        connector_loop = self._session._connector._loop
                        if connector_loop is not None and connector_loop != current_loop:
                            logger.debug("Session attached to different event loop, creating new session")
                            need_new_session = True
                except RuntimeError:
                    # No running loop - shouldn't happen in async context
                    need_new_session = True
            
            if need_new_session:
                # Close old session if it exists and isn't already closed
                if self._session is not None and not self._session.closed:
                    try:
                        await self._session.close()
                    except Exception:
                        pass  # Ignore errors closing old session
                
                timeout = aiohttp.ClientTimeout(total=self.timeout)
                self._session = aiohttp.ClientSession(timeout=timeout)
                
            return self._session
        except Exception as e:
            # If anything goes wrong, create a fresh session
            logger.warning(f"Error checking session state, creating new session: {e}")
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self._session = aiohttp.ClientSession(timeout=timeout)
            return self._session
    
    async def close(self):
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
    
    async def _request(
        self,
        method: str,
        path: str,
        json: Optional[Dict] = None,
        retry: bool = True
    ) -> Dict[str, Any]:
        """
        Make an HTTP request with retry logic.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            path: API path
            json: JSON body for POST requests
            retry: Whether to retry on failure
            
        Returns:
            Response JSON
            
        Raises:
            ModelServerUnavailable: If server is unavailable after retries
            ModelServerError: For other errors
        """
        if not self.enabled:
            raise ModelServerUnavailable("Model server is disabled")
        
        url = f"{self.base_url}{path}"
        
        last_error = None
        attempts = self.max_retries if retry else 1
        
        for attempt in range(attempts):
            try:
                session = await self._get_session()
                async with session.request(method, url, json=json) as response:
                    if response.status == 503:
                        raise ModelServerUnavailable("Model server not ready")
                    
                    response.raise_for_status()
                    return await response.json()
                    
            except aiohttp.ClientConnectorError as e:
                last_error = e
                logger.warning(
                    f"Model server connection failed (attempt {attempt + 1}/{attempts}): {e}"
                )
            except aiohttp.ServerDisconnectedError as e:
                last_error = e
                # Force a fresh session on next attempt — the TCP connection died
                if self._session is not None and not self._session.closed:
                    try:
                        await self._session.close()
                    except Exception:
                        pass
                self._session = None
                logger.warning(
                    f"Model server disconnected (attempt {attempt + 1}/{attempts}): {e}"
                )
            except (aiohttp.ClientOSError, ConnectionResetError) as e:
                last_error = e
                if self._session is not None and not self._session.closed:
                    try:
                        await self._session.close()
                    except Exception:
                        pass
                self._session = None
                logger.warning(
                    f"Model server connection reset (attempt {attempt + 1}/{attempts}): {e}"
                )
            except aiohttp.ClientResponseError as e:
                last_error = e
                if e.status == 503:
                    logger.warning(
                        f"Model server not ready (attempt {attempt + 1}/{attempts})"
                    )
                else:
                    raise ModelServerError(f"Model server error: {e}")
            except asyncio.TimeoutError as e:
                last_error = e
                logger.warning(
                    f"Model server timeout (attempt {attempt + 1}/{attempts})"
                )
            except Exception as e:
                last_error = e
                err_str = str(e).lower()
                # Retry on connection-related errors instead of raising immediately
                if any(s in err_str for s in ("session is closed", "connector is closed", "connection closed")):
                    if self._session is not None and not self._session.closed:
                        try:
                            await self._session.close()
                        except Exception:
                            pass
                    self._session = None
                    logger.warning(
                        f"Model server session error (attempt {attempt + 1}/{attempts}): {e}"
                    )
                else:
                    logger.error(f"Unexpected error calling model server: {e}")
                    raise ModelServerError(f"Unexpected error: {e}")
            
            if attempt < attempts - 1:
                await asyncio.sleep(min(2 ** attempt, 16))
        
        raise ModelServerUnavailable(f"Model server unavailable after {attempts} attempts: {last_error}")
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Check model server health.
        
        Returns:
            Health status dictionary
        """
        try:
            result = await self._request("GET", "/health", retry=False)
            self._healthy = result.get("ready", False)
            return result
        except ModelServerError:
            self._healthy = False
            raise
    
    async def is_ready(self) -> bool:
        """Check if model server is ready to serve requests."""
        try:
            result = await self._request("GET", "/health/ready", retry=False)
            return result.get("ready", False)
        except ModelServerError:
            return False
    
    async def wait_for_ready(
        self,
        timeout: float = 120.0,
        poll_interval: float = 2.0
    ) -> bool:
        """
        Wait for model server to be ready.
        
        Args:
            timeout: Maximum time to wait in seconds
            poll_interval: Time between health checks
            
        Returns:
            True if server became ready, False if timeout
        """
        import time
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                if await self.is_ready():
                    logger.info("Model server is ready")
                    return True
            except ModelServerError:
                pass
            
            await asyncio.sleep(poll_interval)
        
        logger.warning(f"Model server not ready after {timeout}s")
        return False
    
    async def generate_embeddings(
        self,
        texts: List[str],
        model: Optional[str] = None,
        normalize: bool = True
    ) -> List[List[float]]:
        """
        Generate embeddings for texts via model server.
        
        Args:
            texts: List of texts to embed
            model: Model name (optional, uses server default)
            normalize: Whether to normalize embeddings
            
        Returns:
            List of embedding vectors
        """
        if not texts:
            return []
        
        request_data = {
            "texts": texts,
            "normalize": normalize
        }
        if model:
            request_data["model"] = model
        
        result = await self._request("POST", "/embeddings", json=request_data)
        return result.get("embeddings", [])
    
    async def rerank(self, query: str, documents: List[str]) -> List[float]:
        """
        Score query-document pairs via cross-encoder reranking.
        
        Args:
            query: Query text for cross-attention scoring
            documents: List of document texts to score against the query
            
        Returns:
            List of relevance scores in [0, 1], one per document
            
        Raises:
            ModelServerError: On server-side errors
            ModelServerUnavailable: On connection/timeout failures or 503
        """
        if not documents:
            return []
        
        result = await self._request(
            "POST", "/rerank", json={"query": query, "documents": documents}
        )
        return result.get("scores", [])
    
    async def process_nlp(
        self,
        texts: List[str],
        tasks: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Process texts with NLP tasks via model server.
        
        Args:
            texts: List of texts to process
            tasks: NLP tasks to perform (tokenize, ner, pos, lemma, sentences)
            
        Returns:
            List of processing results
        """
        if not texts:
            return []
        
        request_data = {
            "texts": texts,
            "tasks": tasks or ["tokenize", "ner", "pos"]
        }
        
        result = await self._request("POST", "/nlp/process", json=request_data)
        return result.get("results", [])
    
    async def tokenize(self, texts: List[str]) -> List[List[str]]:
        """Tokenize texts (convenience method)."""
        results = await self.process_nlp(texts, tasks=["tokenize"])
        return [r.get("tokens", []) for r in results]
    
    async def get_entities(self, texts: List[str]) -> List[List[Dict]]:
        """Extract named entities (convenience method)."""
        results = await self.process_nlp(texts, tasks=["ner"])
        return [r.get("entities", []) for r in results]
    
    def get_status(self) -> Dict[str, Any]:
        """Get client status information."""
        return {
            "base_url": self.base_url,
            "enabled": self.enabled,
            "healthy": self._healthy,
            "timeout": self.timeout,
            "max_retries": self.max_retries
        }


def get_model_client() -> Optional[ModelServerClient]:
    """Get the global model server client instance."""
    return _model_client


async def initialize_model_client(
    base_url: Optional[str] = None,
    timeout: Optional[float] = None,
    enabled: Optional[bool] = None
) -> ModelServerClient:
    """
    Initialize the global model server client.
    
    Reads configuration from Settings if not provided, falling back to
    environment variables.
    
    Note: In Celery worker context, this creates a fresh client each time
    to avoid event loop issues across multiple asyncio.run() calls.
    """
    global _model_client
    
    # Close existing client if any (important for Celery workers)
    if _model_client is not None:
        try:
            await _model_client.close()
        except Exception:
            pass  # Ignore errors closing old client
        _model_client = None
    
    # Try to get settings from config
    try:
        from ..config import get_settings
        settings = get_settings()
        
        if base_url is None:
            base_url = settings.model_server_url
        if timeout is None:
            timeout = settings.model_server_timeout
        if enabled is None:
            enabled = settings.model_server_enabled
    except Exception:
        # Fall back to environment variables if config not available
        if base_url is None:
            base_url = os.environ.get("MODEL_SERVER_URL", "http://model-server:8001")
        if timeout is None:
            timeout = float(os.environ.get("MODEL_SERVER_TIMEOUT", "30"))
        if enabled is None:
            enabled = os.environ.get("MODEL_SERVER_ENABLED", "true").lower() == "true"
    
    _model_client = ModelServerClient(
        base_url=base_url,
        timeout=timeout,
        enabled=enabled
    )
    
    logger.info(f"Model server client initialized: {base_url} (enabled={enabled})")
    
    return _model_client


async def cleanup_model_client():
    """Clean up the global model server client."""
    global _model_client
    
    if _model_client:
        await _model_client.close()
        _model_client = None
        logger.info("Model server client closed")
