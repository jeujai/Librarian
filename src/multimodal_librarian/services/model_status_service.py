"""
Model Status Service

Unified service for querying model availability from the model server.
This service is the single source of truth for model status across
the application, replacing the fragmented status tracking in MinimalServer
and ModelManager.

The service queries the actual model server container's health endpoint
and provides consistent model status information to all consumers.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class ModelServerStatus(Enum):
    """Status of the model server connection."""
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    UNKNOWN = "unknown"


@dataclass
class ModelInfo:
    """Information about a single model from the model server."""
    name: str
    status: str  # "loaded", "loading", "error", "not_loaded"
    model_type: Optional[str] = None
    load_time_seconds: Optional[float] = None
    memory_mb: Optional[float] = None
    device: Optional[str] = None
    error_message: Optional[str] = None


@dataclass
class ModelStatusSnapshot:
    """Snapshot of model server status at a point in time."""
    server_status: ModelServerStatus
    server_ready: bool
    models: Dict[str, ModelInfo] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    capabilities: Set[str] = field(default_factory=set)
    error_message: Optional[str] = None


class ModelStatusService:
    """
    Unified service for querying model availability from the model server.
    
    This service is the single source of truth for model status across
    the application. It queries the model server's health endpoint and
    caches results to avoid excessive requests.
    
    Key features:
    - Queries actual model server for real status
    - Caches status with configurable TTL
    - Maps model server models to application capabilities
    - Provides both sync and async interfaces
    - Handles connection failures gracefully
    """
    
    # Mapping from model server models to application capabilities
    MODEL_TO_CAPABILITIES: Dict[str, List[str]] = {
        "embedding": [
            "document_analysis",
            "simple_search",
            "semantic_search",
            "document_upload",
            "advanced_chat",
            "multimodal_processing",  # Multimodal content via embeddings
            "complex_reasoning",      # Complex reasoning requires embeddings
        ],
        "nlp": [
            "basic_chat",
            "document_upload",
            "text_processing",
            "advanced_chat",
            "complex_reasoning",      # Complex reasoning requires NLP
        ],
    }
    
    # Reverse mapping: capability -> required models
    CAPABILITY_TO_MODELS: Dict[str, List[str]] = {
        "document_analysis": ["embedding"],
        "simple_search": ["embedding"],
        "semantic_search": ["embedding"],
        "document_upload": ["embedding"],
        "basic_chat": ["nlp"],
        "text_processing": ["nlp"],
        "advanced_chat": ["embedding", "nlp"],
        "multimodal_processing": ["embedding"],        # Multimodal via embeddings
        "complex_reasoning": ["embedding", "nlp"],     # Requires both models
    }
    
    def __init__(
        self,
        model_client: Optional[Any] = None,
        cache_ttl_seconds: float = 5.0,
        retry_delay_seconds: float = 1.0,
        max_retries: int = 3,
    ):
        """
        Initialize the Model Status Service.
        
        Args:
            model_client: The model server client (injected via DI)
            cache_ttl_seconds: How long to cache status before refreshing
            retry_delay_seconds: Base delay between retries on failure
            max_retries: Maximum retry attempts for health checks
        """
        self._model_client = model_client
        self._cache_ttl = cache_ttl_seconds
        self._retry_delay = retry_delay_seconds
        self._max_retries = max_retries
        
        # Cached status
        self._cached_status: Optional[ModelStatusSnapshot] = None
        self._cache_lock = asyncio.Lock()
        
        # Background refresh task
        self._refresh_task: Optional[asyncio.Task] = None
        self._running = False
        
        logger.info(
            f"ModelStatusService initialized (cache_ttl={cache_ttl_seconds}s, "
            f"max_retries={max_retries})"
        )
    
    def set_model_client(self, client: Any) -> None:
        """Set the model client (for late initialization)."""
        self._model_client = client
    
    async def start_background_refresh(self, interval_seconds: float = 10.0) -> None:
        """Start background task to periodically refresh status."""
        if self._running:
            return
        
        self._running = True
        self._refresh_task = asyncio.create_task(
            self._background_refresh_loop(interval_seconds)
        )
        logger.info(f"Model status background refresh started (interval={interval_seconds}s)")
    
    async def stop_background_refresh(self) -> None:
        """Stop the background refresh task."""
        self._running = False
        if self._refresh_task:
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass
            self._refresh_task = None
        logger.info("Model status background refresh stopped")
    
    async def _background_refresh_loop(self, interval: float) -> None:
        """Background loop to refresh status periodically."""
        while self._running:
            try:
                await self.refresh_status()
            except Exception as e:
                logger.warning(f"Background status refresh failed: {e}")
            await asyncio.sleep(interval)
    
    async def get_status(self, force_refresh: bool = False) -> ModelStatusSnapshot:
        """
        Get current model status, using cache if valid.
        
        Args:
            force_refresh: If True, bypass cache and query model server
            
        Returns:
            ModelStatusSnapshot with current status
        """
        async with self._cache_lock:
            # Check if cache is valid
            if not force_refresh and self._cached_status:
                age = time.time() - self._cached_status.timestamp
                if age < self._cache_ttl:
                    return self._cached_status
            
            # Refresh status
            return await self._fetch_status()
    
    async def refresh_status(self) -> ModelStatusSnapshot:
        """Force refresh the cached status."""
        return await self.get_status(force_refresh=True)
    
    async def _fetch_status(self) -> ModelStatusSnapshot:
        """Fetch status from model server with retry logic."""
        if not self._model_client:
            status = self._create_unavailable_status("Model client not initialized")
            self._cached_status = status
            return status
        
        last_error = None
        for attempt in range(self._max_retries):
            try:
                health_data = await self._model_client.health_check()
                status = self._parse_health_response(health_data)
                self._cached_status = status
                return status
            except Exception as e:
                last_error = e
                logger.warning(
                    f"Model server health check failed "
                    f"(attempt {attempt + 1}/{self._max_retries}): {e}"
                )
                if attempt < self._max_retries - 1:
                    # Exponential backoff
                    delay = self._retry_delay * (2 ** attempt)
                    await asyncio.sleep(delay)
        
        # All retries failed
        logger.error(
            f"Model server unavailable after {self._max_retries} attempts: {last_error}"
        )
        status = self._create_unavailable_status(str(last_error))
        self._cached_status = status
        return status
    
    def _parse_health_response(self, health_data: Dict) -> ModelStatusSnapshot:
        """Parse model server health response into ModelStatusSnapshot."""
        models = {}
        available_capabilities: Set[str] = set()
        
        # Parse models from health response
        models_data = health_data.get("models", {})
        for model_name, model_info in models_data.items():
            models[model_name] = ModelInfo(
                name=model_name,
                status=model_info.get("status", "unknown"),
                model_type=model_info.get("name"),
                load_time_seconds=model_info.get("load_time_seconds"),
                memory_mb=model_info.get("memory_mb"),
                device=model_info.get("device"),
                error_message=model_info.get("error"),
            )
            
            # If model is loaded, add its capabilities
            if model_info.get("status") == "loaded":
                caps = self.MODEL_TO_CAPABILITIES.get(model_name, [])
                available_capabilities.update(caps)
        
        return ModelStatusSnapshot(
            server_status=ModelServerStatus.CONNECTED,
            server_ready=health_data.get("ready", False),
            models=models,
            timestamp=time.time(),
            capabilities=available_capabilities,
        )
    
    def _create_unavailable_status(self, error_message: str) -> ModelStatusSnapshot:
        """Create a status snapshot indicating server is unavailable."""
        return ModelStatusSnapshot(
            server_status=ModelServerStatus.DISCONNECTED,
            server_ready=False,
            models={},
            timestamp=time.time(),
            capabilities=set(),
            error_message=error_message,
        )
    
    # Synchronous convenience methods
    
    def get_status_sync(self) -> ModelStatusSnapshot:
        """
        Get cached status synchronously (does not refresh).
        
        Returns cached status or unavailable status if no cache exists.
        """
        if self._cached_status:
            return self._cached_status
        return self._create_unavailable_status("No cached status available")
    
    def is_capability_available(self, capability: str) -> bool:
        """Check if a capability is currently available (sync, uses cache)."""
        status = self.get_status_sync()
        return capability in status.capabilities
    
    def is_model_loaded(self, model_name: str) -> bool:
        """Check if a specific model is loaded (sync, uses cache)."""
        status = self.get_status_sync()
        model = status.models.get(model_name)
        return model is not None and model.status == "loaded"
    
    def get_available_capabilities(self) -> Set[str]:
        """Get set of currently available capabilities (sync, uses cache)."""
        return self.get_status_sync().capabilities
    
    def get_required_models(self, capability: str) -> List[str]:
        """Get list of models required for a capability."""
        return self.CAPABILITY_TO_MODELS.get(capability, [])
    
    def get_capability_status(self, capability: str) -> Dict[str, Any]:
        """
        Get detailed status for a capability.
        
        Returns dict compatible with existing ModelManager interface.
        """
        status = self.get_status_sync()
        required_models = self.get_required_models(capability)
        
        available_models = []
        loading_models = []
        failed_models = []
        
        for model_name in required_models:
            model = status.models.get(model_name)
            if model:
                if model.status == "loaded":
                    available_models.append(model_name)
                elif model.status == "loading":
                    loading_models.append(model_name)
                elif model.status in ("error", "failed"):
                    failed_models.append(model_name)
        
        # Capability is available if all required models are loaded
        all_loaded = len(available_models) == len(required_models) and len(required_models) > 0
        
        return {
            "capability": capability,
            "available": all_loaded or capability in status.capabilities,
            "required_models": required_models,
            "available_models": available_models,
            "loading_models": loading_models,
            "failed_models": failed_models,
            "server_connected": status.server_status == ModelServerStatus.CONNECTED,
        }
    
    def get_model_statuses_dict(self) -> Dict[str, str]:
        """
        Get model statuses as a simple dict.
        
        Returns dict compatible with MinimalServer.model_statuses format.
        """
        status = self.get_status_sync()
        return {
            model_name: model_info.status
            for model_name, model_info in status.models.items()
        }
    
    def get_all_capabilities_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status for all known capabilities."""
        return {
            capability: self.get_capability_status(capability)
            for capability in self.CAPABILITY_TO_MODELS.keys()
        }


# Global service instance
_model_status_service: Optional[ModelStatusService] = None


def get_model_status_service() -> Optional[ModelStatusService]:
    """Get the global Model Status Service instance (may be None)."""
    return _model_status_service


async def get_model_status_service_async() -> ModelStatusService:
    """
    Get or create the Model Status Service instance.
    
    Creates the service if it doesn't exist, initializing with the model client.
    """
    global _model_status_service
    
    if _model_status_service is None:
        from ..clients.model_server_client import get_model_client
        model_client = get_model_client()
        _model_status_service = ModelStatusService(model_client=model_client)
    
    return _model_status_service


async def initialize_model_status_service(
    model_client: Optional[Any] = None,
    cache_ttl_seconds: float = 5.0,
    start_background_refresh: bool = True,
    refresh_interval: float = 10.0,
) -> ModelStatusService:
    """
    Initialize the global Model Status Service.
    
    Args:
        model_client: Model server client (uses global if None)
        cache_ttl_seconds: Cache TTL in seconds
        start_background_refresh: Whether to start background refresh
        refresh_interval: Background refresh interval in seconds
        
    Returns:
        Initialized ModelStatusService
    """
    global _model_status_service
    
    if model_client is None:
        from ..clients.model_server_client import get_model_client
        model_client = get_model_client()
    
    _model_status_service = ModelStatusService(
        model_client=model_client,
        cache_ttl_seconds=cache_ttl_seconds,
    )
    
    # Do initial status fetch
    try:
        await _model_status_service.get_status(force_refresh=True)
        logger.info("Initial model status fetch completed")
    except Exception as e:
        logger.warning(f"Initial model status fetch failed: {e}")
    
    # Start background refresh if requested
    if start_background_refresh:
        await _model_status_service.start_background_refresh(refresh_interval)
    
    return _model_status_service


async def cleanup_model_status_service() -> None:
    """Clean up the global Model Status Service."""
    global _model_status_service
    
    if _model_status_service:
        await _model_status_service.stop_background_refresh()
        _model_status_service = None
        logger.info("Model status service cleaned up")
