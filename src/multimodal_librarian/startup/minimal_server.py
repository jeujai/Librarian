"""
Minimal HTTP Server for Fast Startup

This module implements a minimal HTTP server that can start in under 30 seconds,
providing basic health endpoints and request queuing while models load in the background.

Key Features:
- Starts in <30 seconds
- Basic health endpoints
- Model status reporting (delegated to ModelStatusService)
- Request queuing for pending operations
- Graceful degradation during startup

Note: Model status tracking has been deprecated in favor of ModelStatusService.
This server now delegates all model status queries to the unified service.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse

if TYPE_CHECKING:
    from ..services.model_status_service import ModelStatusService

logger = logging.getLogger(__name__)


class ServerStatus(Enum):
    """Server status states."""
    STARTING = "starting"
    MINIMAL = "minimal"
    READY = "ready"
    ERROR = "error"


@dataclass
class QueuedRequest:
    """Represents a queued request waiting for processing."""
    request_id: str
    endpoint: str
    method: str
    timestamp: datetime
    user_message: Optional[str] = None
    priority: str = "normal"  # "high", "normal", "low"
    estimated_wait_time: Optional[float] = None


@dataclass
class MinimalServerStatus:
    """Status information for the minimal server."""
    status: ServerStatus
    start_time: datetime
    uptime_seconds: float
    health_check_ready: bool
    request_queue_size: int
    processed_requests: int
    failed_requests: int
    capabilities: Dict[str, bool] = field(default_factory=dict)
    model_statuses: Dict[str, str] = field(default_factory=dict)
    estimated_ready_times: Dict[str, float] = field(default_factory=dict)


class MinimalServer:
    """
    Minimal HTTP server that provides status information based on actual service availability.
    
    This server delegates model status queries to the unified ModelStatusService,
    which queries the actual model server container for real status information.
    
    The server maintains only basic operational metrics (uptime, request counts)
    and delegates all model/capability status to ModelStatusService.
    """
    
    def __init__(self):
        """Initialize the minimal server."""
        self.start_time = datetime.now()
        self.status = ServerStatus.MINIMAL  # Start as minimal, upgrade when AI is available
        self.request_queue: List[QueuedRequest] = []
        self.processed_requests = 0
        self.failed_requests = 0
        
        # Reference to ModelStatusService (injected later)
        self._model_status_service: Optional["ModelStatusService"] = None
        
        # Basic capabilities available immediately (server-level, not model-dependent)
        self._basic_capabilities = {
            "health_endpoints": True,
            "basic_api": True,
            "status_reporting": True,
            "request_queuing": True,
            "fallback_responses": True
        }
        
        # Estimated ready times (minimal since we use external APIs)
        self.estimated_ready_times: Dict[str, float] = {}
        
        logger.info("MinimalServer initialized")
    
    def set_model_status_service(self, service: "ModelStatusService") -> None:
        """
        Inject the ModelStatusService for model status delegation.
        
        Args:
            service: The ModelStatusService instance to use
        """
        self._model_status_service = service
        logger.info("ModelStatusService injected into MinimalServer")
    
    @property
    def capabilities(self) -> Dict[str, bool]:
        """
        Get current capabilities, combining basic server capabilities with model-based capabilities.
        
        Model-based capabilities are delegated to ModelStatusService.
        """
        # Start with basic server capabilities
        caps = self._basic_capabilities.copy()
        
        # Add model-based capabilities from ModelStatusService
        if self._model_status_service:
            available_caps = self._model_status_service.get_available_capabilities()
            for cap in available_caps:
                caps[cap] = True
            
            # Also check if we have full capabilities
            if "basic_chat" in available_caps and "simple_search" in available_caps:
                caps["full_capabilities"] = True
            if "advanced_chat" in available_caps:
                caps["advanced_ai"] = True
        
        return caps
    
    @property
    def model_statuses(self) -> Dict[str, str]:
        """
        Get model statuses from ModelStatusService.
        
        This property is deprecated - use ModelStatusService directly.
        Maintained for backward compatibility.
        """
        if self._model_status_service:
            return self._model_status_service.get_model_statuses_dict()
        
        # Return empty dict if service not available
        return {}
    
    async def start(self) -> None:
        """Start the minimal server."""
        logger.info("Starting minimal server...")
        
        # Mark as minimal - will upgrade to READY when ModelStatusService reports models loaded
        self.status = ServerStatus.MINIMAL
        logger.info(f"MinimalServer status set to: {self.status.value}")
        
        # Start background task to check model availability via ModelStatusService
        asyncio.create_task(self._check_ai_availability())
        
        logger.info("Minimal server started successfully")
    
    async def _check_ai_availability(self) -> None:
        """
        Check model availability via ModelStatusService and update server status.
        
        This method delegates to ModelStatusService instead of directly checking
        AI providers. The ModelStatusService queries the actual model server
        for real model status.
        """
        try:
            while True:
                try:
                    # Check if ModelStatusService is available
                    if self._model_status_service:
                        # Get status from the unified service
                        status = await self._model_status_service.get_status()
                        
                        if status.server_ready:
                            # Model server is ready - mark as fully ready
                            self.status = ServerStatus.READY
                            logger.info(
                                f"Model server ready with capabilities: {status.capabilities} "
                                f"- server fully ready"
                            )
                            break
                        elif status.capabilities:
                            # Some capabilities available
                            logger.debug(
                                f"Model server partially ready: {status.capabilities}"
                            )
                    else:
                        # Fallback: check AI service directly if ModelStatusService not injected
                        try:
                            from ..services.ai_service import AIService
                            ai_service = AIService()
                            available_providers = ai_service.get_available_providers()
                            
                            if available_providers:
                                self.status = ServerStatus.READY
                                logger.info(
                                    f"AI providers available (fallback check): {available_providers} "
                                    f"- server fully ready"
                                )
                                break
                        except Exception as e:
                            logger.debug(f"AI service fallback check: {e}")
                    
                except Exception as e:
                    logger.debug(f"Model availability check: {e}")
                
                await asyncio.sleep(2)  # Check every 2 seconds
                
        except asyncio.CancelledError:
            logger.info("AI availability check cancelled")
        except Exception as e:
            logger.error(f"Error checking AI availability: {e}")
    
    async def _process_request_queue(self) -> None:
        """Process queued requests as capabilities become available."""
        try:
            while True:
                if self.request_queue:
                    # Process requests that can now be handled
                    processed_requests = []
                    
                    for request in self.request_queue:
                        if await self._can_process_request(request):
                            # Simulate processing
                            await asyncio.sleep(0.1)
                            processed_requests.append(request)
                            self.processed_requests += 1
                            logger.debug(f"Processed queued request {request.request_id}")
                    
                    # Remove processed requests from queue
                    for request in processed_requests:
                        self.request_queue.remove(request)
                
                await asyncio.sleep(5)  # Check every 5 seconds
                
        except asyncio.CancelledError:
            logger.info("Request queue processing cancelled")
        except Exception as e:
            logger.error(f"Error processing request queue: {e}")
    
    async def _can_process_request(self, request: QueuedRequest) -> bool:
        """Check if a request can now be processed based on available capabilities."""
        caps = self.capabilities
        
        # Simple logic - can process if required capabilities are available
        if request.endpoint.startswith("/api/chat"):
            return caps.get("basic_chat", False)
        elif request.endpoint.startswith("/api/search"):
            return caps.get("simple_search", False)
        elif request.endpoint.startswith("/api/documents"):
            return caps.get("document_analysis", False)
        else:
            return True  # Basic endpoints can always be processed
    
    def get_status(self) -> MinimalServerStatus:
        """Get current server status."""
        uptime = (datetime.now() - self.start_time).total_seconds()
        
        return MinimalServerStatus(
            status=self.status,
            start_time=self.start_time,
            uptime_seconds=uptime,
            health_check_ready=self.status != ServerStatus.STARTING,
            request_queue_size=len(self.request_queue),
            processed_requests=self.processed_requests,
            failed_requests=self.failed_requests,
            capabilities=self.capabilities.copy(),
            model_statuses=self.model_statuses.copy(),
            estimated_ready_times=self.estimated_ready_times.copy()
        )
    
    def queue_request(self, request_id: str, endpoint: str, method: str, 
                     user_message: Optional[str] = None, priority: str = "normal") -> QueuedRequest:
        """Queue a request for later processing."""
        caps = self.capabilities
        
        # Estimate wait time based on required capability
        estimated_wait = 0.0
        if endpoint.startswith("/api/chat") and not caps.get("basic_chat"):
            estimated_wait = self.estimated_ready_times.get("basic_chat", 60.0)
        elif endpoint.startswith("/api/search") and not caps.get("simple_search"):
            estimated_wait = self.estimated_ready_times.get("simple_search", 90.0)
        elif endpoint.startswith("/api/documents") and not caps.get("document_analysis"):
            estimated_wait = self.estimated_ready_times.get("document_analysis", 180.0)
        
        queued_request = QueuedRequest(
            request_id=request_id,
            endpoint=endpoint,
            method=method,
            timestamp=datetime.now(),
            user_message=user_message,
            priority=priority,
            estimated_wait_time=estimated_wait
        )
        
        # Insert based on priority
        if priority == "high":
            self.request_queue.insert(0, queued_request)
        else:
            self.request_queue.append(queued_request)
        
        logger.info(f"Queued request {request_id} for {endpoint} (estimated wait: {estimated_wait}s)")
        return queued_request
    
    def get_fallback_response(self, endpoint: str, user_message: Optional[str] = None) -> Dict[str, Any]:
        """Generate a fallback response for requests that can't be processed yet."""
        caps = self.capabilities
        
        base_response = {
            "status": "loading",
            "server_status": self.status.value,
            "timestamp": datetime.now().isoformat(),
            "capabilities": caps,
            "estimated_ready_times": self.estimated_ready_times
        }
        
        if endpoint.startswith("/api/chat"):
            if not caps.get("basic_chat"):
                base_response.update({
                    "message": "AI chat models are starting up. Basic responses will be available shortly.",
                    "fallback_response": self._generate_contextual_fallback(user_message),
                    "response_quality": "basic",
                    "estimated_ready_time": self.estimated_ready_times.get("basic_chat", 60.0),
                    "upgrade_message": f"Full AI capabilities will be ready in {self.estimated_ready_times.get('advanced_ai', 300.0)} seconds"
                })
            else:
                base_response.update({
                    "message": "Basic AI chat is ready. Advanced features are still loading.",
                    "response_quality": "enhanced",
                    "available_features": ["basic_chat", "simple_responses"],
                    "loading_features": ["advanced_reasoning", "document_analysis"]
                })
        
        elif endpoint.startswith("/api/search"):
            if not caps.get("simple_search"):
                base_response.update({
                    "message": "Search functionality is initializing. Please wait a moment.",
                    "fallback_response": "I can provide basic information now, but search capabilities will be available shortly.",
                    "estimated_ready_time": self.estimated_ready_times.get("simple_search", 90.0)
                })
            else:
                base_response.update({
                    "message": "Basic search is ready. Advanced semantic search is still loading.",
                    "available_features": ["simple_search", "keyword_matching"],
                    "loading_features": ["semantic_search", "advanced_ranking"]
                })
        
        elif endpoint.startswith("/api/documents"):
            if not caps.get("document_analysis"):
                base_response.update({
                    "message": "Document processing capabilities are loading. Please wait.",
                    "fallback_response": "I can discuss documents in general, but analysis features will be ready soon.",
                    "estimated_ready_time": self.estimated_ready_times.get("document_analysis", 180.0)
                })
            else:
                base_response.update({
                    "message": "Document processing is ready.",
                    "available_features": ["document_upload", "basic_processing"],
                    "loading_features": ["advanced_analysis", "multimodal_processing"]
                })
        
        else:
            base_response.update({
                "message": "System is starting up. Basic functionality is available.",
                "available_now": list(caps.keys())
            })
        
        return base_response
    
    def _generate_contextual_fallback(self, user_message: Optional[str]) -> str:
        """Generate a contextual fallback response based on user message."""
        if not user_message:
            return "I'm currently starting up my AI models. Please wait 30-60 seconds for full capabilities."
        
        message_lower = user_message.lower().strip()
        
        # Analyze user intent and provide appropriate fallback
        if any(word in message_lower for word in ['complex', 'analyze', 'detailed', 'explain']):
            return ("I'm starting up my advanced AI models for complex analysis. "
                   "Right now I can provide basic information, but detailed analysis "
                   "will be available in about 2-3 minutes.")
        
        elif any(word in message_lower for word in ['search', 'find', 'lookup']):
            return ("My search capabilities are initializing. I can discuss general topics now, "
                   "but advanced search and document lookup will be ready in about 90 seconds.")
        
        elif any(word in message_lower for word in ['document', 'file', 'pdf', 'upload']):
            return ("Document processing features are loading. I can provide general information "
                   "about documents now, but analysis and processing will be available in about 3 minutes.")
        
        elif any(word in message_lower for word in ['hello', 'hi', 'hey']):
            return ("Hello! I'm starting up my AI capabilities. Basic conversation is available now, "
                   "and full AI features will be ready shortly. How can I help you?")
        
        else:
            return ("I'm currently loading my AI models. I can provide basic responses now, "
                   "but my full capabilities (advanced reasoning, document analysis, complex queries) "
                   "will be ready in 1-2 minutes. What would you like to know?")
    
    def is_capability_available(self, capability: str) -> bool:
        """
        Check if a specific capability is available.
        
        Delegates to ModelStatusService if available, otherwise falls back
        to checking the capabilities property.
        """
        if self._model_status_service:
            return self._model_status_service.is_capability_available(capability)
        
        # Fallback to capabilities property
        return self.capabilities.get(capability, False)
    
    def get_model_status(self, model_name: str) -> str:
        """
        Get the status of a specific model.
        
        Delegates to ModelStatusService if available.
        """
        if self._model_status_service:
            if self._model_status_service.is_model_loaded(model_name):
                return "loaded"
            
            # Check if model exists in status
            status = self._model_status_service.get_status_sync()
            model = status.models.get(model_name)
            if model:
                return model.status
            
            return "unknown"
        
        # Fallback to model_statuses property
        return self.model_statuses.get(model_name, "unknown")
    
    def get_queue_status(self) -> Dict[str, Any]:
        """Get current request queue status."""
        return {
            "queue_size": len(self.request_queue),
            "processed_requests": self.processed_requests,
            "failed_requests": self.failed_requests,
            "queued_requests": [
                {
                    "request_id": req.request_id,
                    "endpoint": req.endpoint,
                    "method": req.method,
                    "priority": req.priority,
                    "estimated_wait_time": req.estimated_wait_time,
                    "queued_at": req.timestamp.isoformat()
                }
                for req in self.request_queue
            ]
        }


# Global minimal server instance
_minimal_server: Optional[MinimalServer] = None


def get_minimal_server() -> MinimalServer:
    """Get the global minimal server instance."""
    global _minimal_server
    if _minimal_server is None:
        _minimal_server = MinimalServer()
    return _minimal_server


async def initialize_minimal_server() -> MinimalServer:
    """Initialize and start the minimal server."""
    server = get_minimal_server()
    await server.start()
    return server


def create_minimal_health_endpoints(app: FastAPI) -> None:
    """Add minimal health endpoints to a FastAPI app."""
    
    @app.get("/health/minimal")
    async def minimal_health_check():
        """Minimal health check - basic server readiness."""
        server = get_minimal_server()
        status = server.get_status()
        
        return {
            "status": "healthy" if status.health_check_ready else "starting",
            "server_status": status.status.value,
            "uptime_seconds": status.uptime_seconds,
            "ready": status.health_check_ready,
            "capabilities": status.capabilities,
            "timestamp": datetime.now().isoformat()
        }
    
    @app.get("/health/ready")
    async def readiness_health_check():
        """Readiness health check - essential models loaded."""
        server = get_minimal_server()
        status = server.get_status()
        
        essential_ready = (
            status.capabilities.get("basic_chat", False) and
            status.capabilities.get("simple_search", False)
        )
        
        return {
            "status": "ready" if essential_ready else "not_ready",
            "server_status": status.status.value,
            "essential_models_ready": essential_ready,
            "capabilities": status.capabilities,
            "model_statuses": status.model_statuses,
            "estimated_ready_times": status.estimated_ready_times,
            "timestamp": datetime.now().isoformat()
        }
    
    @app.get("/health/full")
    async def full_health_check():
        """Full health check - all models loaded."""
        server = get_minimal_server()
        status = server.get_status()
        
        all_ready = status.status == ServerStatus.READY
        
        return {
            "status": "ready" if all_ready else "not_ready",
            "server_status": status.status.value,
            "all_models_ready": all_ready,
            "capabilities": status.capabilities,
            "model_statuses": status.model_statuses,
            "queue_status": server.get_queue_status(),
            "timestamp": datetime.now().isoformat()
        }
    
    @app.get("/startup/minimal/status")
    async def get_minimal_server_status():
        """Get detailed minimal server status."""
        server = get_minimal_server()
        status = server.get_status()
        
        return {
            "server_status": status.status.value,
            "uptime_seconds": status.uptime_seconds,
            "health_check_ready": status.health_check_ready,
            "capabilities": status.capabilities,
            "model_statuses": status.model_statuses,
            "estimated_ready_times": status.estimated_ready_times,
            "queue_status": server.get_queue_status(),
            "start_time": status.start_time.isoformat(),
            "timestamp": datetime.now().isoformat()
        }
    
    @app.get("/startup/minimal/queue")
    async def get_request_queue_status():
        """Get current request queue status."""
        server = get_minimal_server()
        return server.get_queue_status()
    
    logger.info("Minimal health endpoints added to FastAPI app")