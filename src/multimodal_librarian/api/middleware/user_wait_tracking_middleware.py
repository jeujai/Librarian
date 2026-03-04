"""
User Wait Time Tracking Middleware

This middleware automatically tracks user wait times for all API requests during startup phases.
It integrates with the startup metrics system to provide comprehensive user experience monitoring.
"""

import logging
import time
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from ...logging.ux_logger import (
    RequestOutcome,
    log_user_request_completion,
    log_user_request_start,
)
from ...monitoring.startup_metrics import complete_user_request, track_user_request
from ...services.capability_service import CapabilityLevel

logger = logging.getLogger(__name__)


class UserWaitTrackingMiddleware(BaseHTTPMiddleware):
    """
    Middleware to automatically track user wait times during startup phases.
    
    This middleware:
    - Tracks the start of each user request
    - Records completion with success/failure status
    - Detects fallback responses based on response headers
    - Measures actual processing time vs wait time
    """
    
    def __init__(self, app, enabled: bool = True):
        """
        Initialize the user wait tracking middleware.
        
        Args:
            app: FastAPI application instance
            enabled: Whether to enable wait time tracking
        """
        super().__init__(app)
        self.enabled = enabled
        
        # Endpoint configuration for capability requirements
        self.endpoint_capabilities = {
            "/api/chat": ["chat-model-base"],
            "/api/search": ["search-model", "embedding-model"],
            "/api/document/analyze": ["document-processor", "multimodal-model"],
            "/api/document/upload": ["document-processor"],
            "/api/knowledge/query": ["knowledge-graph", "embedding-model"],
        }
        
        # Request type mapping
        self.endpoint_types = {
            "/api/chat": "chat",
            "/api/search": "search",
            "/api/document": "document",
            "/api/knowledge": "knowledge",
            "/api/health": "health",
        }
        
        logger.info(f"UserWaitTrackingMiddleware initialized (enabled: {enabled})")
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and track user wait times."""
        # Skip WebSocket connections - BaseHTTPMiddleware doesn't handle them properly
        if request.headers.get("upgrade", "").lower() == "websocket":
            return await call_next(request)
        
        if not self.enabled:
            return await call_next(request)
        
        # Skip health endpoints for fast response
        path = request.url.path
        if path.startswith("/health"):
            return await call_next(request)
        
        # Generate unique request ID
        request_id = str(uuid.uuid4())
        request.state.wait_tracking_id = request_id
        
        # Extract user information
        user_id = self._extract_user_id(request)
        endpoint = self._normalize_endpoint(request.url.path)
        request_type = self._get_request_type(endpoint)
        required_capabilities = self._get_required_capabilities(endpoint)
        
        # Start tracking the request
        start_time = time.time()
        try:
            await track_user_request(
                request_id=request_id,
                user_id=user_id,
                endpoint=endpoint,
                request_type=request_type,
                required_capabilities=required_capabilities
            )
            
            # Also log with UX logger for detailed pattern analysis
            await log_user_request_start(
                request_id=request_id,
                user_id=user_id,
                session_id=request.session.get("session_id") if hasattr(request, 'session') else None,
                endpoint=endpoint,
                request_type=request_type,
                user_message=None,  # Could extract from request body if needed
                required_capabilities=required_capabilities,
                user_agent=request.headers.get("user-agent"),
                ip_address=request.client.host if request.client else None,
                referrer=request.headers.get("referer")
            )
            
            logger.debug(f"Started tracking user request: {request_id} for {endpoint}")
            
        except Exception as e:
            logger.warning(f"Failed to start tracking request {request_id}: {e}")
        
        # Process the request
        try:
            response = await call_next(request)
            processing_time = time.time() - start_time
            
            # Analyze response for fallback usage
            fallback_info = self._analyze_response_for_fallback(response)
            
            # Record successful completion
            await self._record_completion(
                request_id=request_id,
                success=True,
                fallback_used=fallback_info["used"],
                fallback_quality=fallback_info["quality"],
                actual_processing_time_seconds=processing_time
            )
            
            # Also log with UX logger
            await self._log_ux_completion(
                request_id=request_id,
                success=True,
                processing_time=processing_time,
                fallback_info=fallback_info
            )
            
            # Add tracking headers to response
            response.headers["X-Wait-Tracking-ID"] = request_id
            if fallback_info["used"]:
                response.headers["X-Fallback-Used"] = "true"
                response.headers["X-Fallback-Quality"] = fallback_info["quality"]
            
            return response
            
        except Exception as e:
            processing_time = time.time() - start_time
            
            # Record failed completion
            await self._record_completion(
                request_id=request_id,
                success=False,
                error_message=str(e),
                actual_processing_time_seconds=processing_time
            )
            
            # Also log with UX logger
            await self._log_ux_completion(
                request_id=request_id,
                success=False,
                processing_time=processing_time,
                error_message=str(e)
            )
            
            logger.error(f"Request {request_id} failed: {e}")
            raise
    
    def _extract_user_id(self, request: Request) -> Optional[str]:
        """Extract user ID from request headers or authentication."""
        # Try various common user identification methods
        user_id = None
        
        # Check authorization header
        auth_header = request.headers.get("authorization")
        if auth_header:
            # This would typically decode a JWT or API key
            # For now, just use a hash of the auth header
            user_id = f"auth_{hash(auth_header) % 10000}"
        
        # Check custom user ID header
        user_id = user_id or request.headers.get("x-user-id")
        
        # Check session cookie
        session_id = request.cookies.get("session_id")
        if session_id:
            user_id = f"session_{session_id}"
        
        # Fallback to IP address
        if not user_id:
            client_ip = request.client.host if request.client else "unknown"
            user_id = f"ip_{client_ip}"
        
        return user_id
    
    def _normalize_endpoint(self, path: str) -> str:
        """Normalize endpoint path for consistent tracking."""
        # Remove query parameters
        if "?" in path:
            path = path.split("?")[0]
        
        # Remove trailing slash
        path = path.rstrip("/")
        
        # Group similar endpoints
        if path.startswith("/api/document/"):
            return "/api/document"
        elif path.startswith("/api/health/"):
            return "/api/health"
        elif path.startswith("/api/knowledge/"):
            return "/api/knowledge"
        
        return path
    
    def _get_request_type(self, endpoint: str) -> str:
        """Get request type based on endpoint."""
        for pattern, req_type in self.endpoint_types.items():
            if endpoint.startswith(pattern):
                return req_type
        return "unknown"
    
    def _get_required_capabilities(self, endpoint: str) -> List[str]:
        """Get required capabilities for an endpoint."""
        for pattern, capabilities in self.endpoint_capabilities.items():
            if endpoint.startswith(pattern):
                return capabilities
        return []
    
    def _analyze_response_for_fallback(self, response: Response) -> dict:
        """Analyze response to detect fallback usage."""
        fallback_info = {
            "used": False,
            "quality": None
        }
        
        # Check response headers for fallback indicators
        if response.headers.get("x-response-mode") == "fallback":
            fallback_info["used"] = True
            fallback_info["quality"] = response.headers.get("x-response-quality", "basic")
        
        # Check for loading state indicators
        if response.headers.get("x-loading-state") in ["loading", "partial"]:
            fallback_info["used"] = True
            fallback_info["quality"] = "basic"
        
        # Check response status for degraded service
        if response.status_code == 206:  # Partial Content
            fallback_info["used"] = True
            fallback_info["quality"] = "enhanced"
        
        return fallback_info
    
    async def _record_completion(self, request_id: str, success: bool = True,
                               error_message: Optional[str] = None,
                               fallback_used: bool = False,
                               fallback_quality: Optional[str] = None,
                               actual_processing_time_seconds: Optional[float] = None) -> None:
        """Record request completion."""
        try:
            await complete_user_request(
                request_id=request_id,
                success=success,
                error_message=error_message,
                fallback_used=fallback_used,
                fallback_quality=fallback_quality,
                actual_processing_time_seconds=actual_processing_time_seconds
            )
            
            logger.debug(f"Recorded completion for request: {request_id} "
                        f"(success: {success}, fallback: {fallback_used})")
            
        except Exception as e:
            logger.warning(f"Failed to record completion for request {request_id}: {e}")
    
    async def _log_ux_completion(self, request_id: str, success: bool = True,
                               processing_time: Optional[float] = None,
                               fallback_info: Optional[Dict[str, Any]] = None,
                               error_message: Optional[str] = None) -> None:
        """Log request completion with UX logger."""
        try:
            # Determine outcome
            if not success:
                outcome = RequestOutcome.ERROR
            elif fallback_info and fallback_info.get("used"):
                outcome = RequestOutcome.FALLBACK_USED
            else:
                outcome = RequestOutcome.SUCCESS
            
            # Map fallback quality
            fallback_quality = None
            if fallback_info and fallback_info.get("quality"):
                quality_str = fallback_info["quality"]
                if quality_str == "basic":
                    fallback_quality = CapabilityLevel.BASIC
                elif quality_str == "enhanced":
                    fallback_quality = CapabilityLevel.ENHANCED
                elif quality_str == "full":
                    fallback_quality = CapabilityLevel.FULL
            
            await log_user_request_completion(
                request_id=request_id,
                outcome=outcome,
                response_time_seconds=processing_time,
                fallback_used=fallback_info.get("used", False) if fallback_info else False,
                fallback_quality=fallback_quality,
                error_message=error_message
            )
            
        except Exception as e:
            logger.debug(f"Failed to log UX completion for request {request_id}: {e}")
    
    def configure_endpoint_capabilities(self, endpoint: str, capabilities: List[str]) -> None:
        """Configure required capabilities for a specific endpoint."""
        self.endpoint_capabilities[endpoint] = capabilities
        logger.info(f"Configured capabilities for {endpoint}: {capabilities}")
    
    def configure_endpoint_type(self, endpoint: str, request_type: str) -> None:
        """Configure request type for a specific endpoint."""
        self.endpoint_types[endpoint] = request_type
        logger.info(f"Configured request type for {endpoint}: {request_type}")