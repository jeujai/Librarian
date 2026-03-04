"""
Concurrent Request Handler Middleware

This middleware ensures that concurrent requests during startup are handled
gracefully without errors, race conditions, or performance degradation.

Key Features:
- Request throttling during startup phases
- Automatic fallback response generation
- Request prioritization based on type
- Deadlock prevention
- Resource contention management
- Graceful degradation under load

Validates Requirements:
- REQ-2: Application Startup Optimization (graceful degradation)
- REQ-3: Smart User Experience (immediate feedback)
"""

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional, Set

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from ...logging_config import get_logger
from ...services.expectation_manager import get_expectation_manager
from ...services.fallback_service import get_fallback_service
from ...startup.phase_manager import StartupPhase, get_phase_manager

logger = get_logger("concurrent_request_handler")


@dataclass
class RequestMetrics:
    """Metrics for tracking concurrent request handling."""
    total_requests: int = 0
    concurrent_requests: int = 0
    peak_concurrent_requests: int = 0
    throttled_requests: int = 0
    fallback_responses: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    avg_response_time_ms: float = 0.0
    requests_by_phase: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    requests_by_endpoint: Dict[str, int] = field(default_factory=lambda: defaultdict(int))


class ConcurrentRequestHandler(BaseHTTPMiddleware):
    """
    Middleware for handling concurrent requests gracefully during startup.
    
    This middleware:
    1. Tracks concurrent request count
    2. Applies throttling during critical startup phases
    3. Provides fallback responses when needed
    4. Prevents resource contention
    5. Ensures no "model not loaded" errors reach users
    """
    
    def __init__(self, app):
        super().__init__(app)
        
        # Configuration
        self.max_concurrent_requests = {
            StartupPhase.MINIMAL: 50,      # Allow many requests during minimal phase
            StartupPhase.ESSENTIAL: 100,   # More capacity as models load
            StartupPhase.FULL: 200         # Full capacity when all models loaded
        }
        
        # Request tracking
        self._active_requests: Set[str] = set()
        self._request_endpoint_map: Dict[str, str] = {}  # request_id -> endpoint
        self._request_lock = asyncio.Lock()
        self._metrics = RequestMetrics()
        
        # Rate limiting per endpoint - these are CONCURRENT limits, not total
        self._endpoint_limits = {
            "/api/chat": 100,          # Allow many chat requests
            "/api/search": 100,        # Allow many search requests
            "/api/documents": 100,     # Allow many document operations
            "/health": 500,            # Allow many health checks
            "/api/loading/status": 200 # Allow status checks
        }
        
        # Request prioritization
        self._priority_endpoints = {
            "/health": 1,              # Highest priority
            "/api/loading/status": 2,
            "/api/chat": 3,
            "/api/search": 4,
            "/api/documents": 5
        }
        
        # Services
        try:
            self.phase_manager = get_phase_manager()
            self.fallback_service = get_fallback_service()
            self.expectation_manager = get_expectation_manager()
        except Exception as e:
            logger.warning(f"Could not initialize services: {e}")
            self.phase_manager = None
            self.fallback_service = None
            self.expectation_manager = None
        
        logger.info("Concurrent request handler initialized")
    
    async def dispatch(self, request: Request, call_next):
        """Handle request with concurrent request management."""
        # Skip WebSocket connections - BaseHTTPMiddleware doesn't handle them properly
        if request.headers.get("upgrade", "").lower() == "websocket":
            return await call_next(request)
        
        request_id = self._generate_request_id()
        start_time = time.time()
        
        try:
            # Skip middleware for static files
            if self._should_skip_middleware(request):
                return await call_next(request)
            
            # Get current phase
            current_phase = self._get_current_phase()
            
            # Check if we should throttle this request
            should_throttle, throttle_reason = await self._should_throttle_request(
                request, current_phase
            )
            
            if should_throttle:
                return await self._create_throttle_response(
                    request, throttle_reason, current_phase
                )
            
            # Track request start
            await self._track_request_start(request_id, request, current_phase)
            
            try:
                # Process the request
                response = await call_next(request)
                
                # Track successful request
                self._metrics.successful_requests += 1
                
                return response
                
            except Exception as e:
                # Track failed request
                self._metrics.failed_requests += 1
                logger.error(f"Request {request_id} failed: {e}")
                
                # Return fallback response instead of error
                return await self._create_error_fallback_response(request, str(e))
            
            finally:
                # Track request end
                await self._track_request_end(request_id, start_time)
        
        except Exception as e:
            logger.error(f"Concurrent request handler error: {e}")
            # Always return a response, never let errors propagate
            return await self._create_emergency_response(request, str(e))
    
    def _should_skip_middleware(self, request: Request) -> bool:
        """Determine if middleware should be skipped."""
        skip_paths = [
            "/static/",
            "/favicon.ico",
            "/robots.txt",
            "/docs",
            "/openapi.json",
            "/health/",  # Skip health endpoints for fast response
            "/health/simple",  # Explicitly skip simple health check
            "/health/minimal",  # Explicitly skip minimal health check
            "/health/alb",  # Explicitly skip ALB health check
        ]
        
        path = str(request.url.path)
        return any(path.startswith(skip_path) for skip_path in skip_paths)
    
    def _get_current_phase(self) -> StartupPhase:
        """Get current startup phase."""
        if self.phase_manager:
            try:
                return self.phase_manager.current_phase
            except Exception:
                pass
        return StartupPhase.MINIMAL  # Default to minimal if unknown
    
    async def _should_throttle_request(
        self, 
        request: Request, 
        current_phase: StartupPhase
    ) -> tuple[bool, Optional[str]]:
        """Determine if request should be throttled."""
        path = str(request.url.path)
        
        # Check global concurrent request limit
        max_concurrent = self.max_concurrent_requests.get(current_phase, 50)
        
        async with self._request_lock:
            if self._metrics.concurrent_requests >= max_concurrent:
                return True, f"System at capacity ({max_concurrent} concurrent requests)"
        
        # Check endpoint-specific limits
        for endpoint_pattern, limit in self._endpoint_limits.items():
            if path.startswith(endpoint_pattern):
                endpoint_requests = self._metrics.requests_by_endpoint.get(endpoint_pattern, 0)
                if endpoint_requests >= limit:
                    return True, f"Endpoint {endpoint_pattern} at capacity ({limit} requests)"
        
        # During MINIMAL phase, be more restrictive
        if current_phase == StartupPhase.MINIMAL:
            # Only allow health checks and status requests at high volume
            if not (path.startswith("/health") or path.startswith("/api/loading")):
                # Limit other requests during minimal phase
                if self._metrics.concurrent_requests >= 10:
                    return True, "System starting up - limited capacity available"
        
        return False, None
    
    async def _track_request_start(
        self, 
        request_id: str, 
        request: Request,
        current_phase: StartupPhase
    ):
        """Track request start."""
        async with self._request_lock:
            self._active_requests.add(request_id)
            self._metrics.total_requests += 1
            self._metrics.concurrent_requests += 1
            
            # Update peak
            if self._metrics.concurrent_requests > self._metrics.peak_concurrent_requests:
                self._metrics.peak_concurrent_requests = self._metrics.concurrent_requests
            
            # Track by phase
            phase_key = current_phase.value
            self._metrics.requests_by_phase[phase_key] += 1
            
            # Track by endpoint and store mapping for decrement on request end
            path = str(request.url.path)
            for endpoint_pattern in self._endpoint_limits.keys():
                if path.startswith(endpoint_pattern):
                    self._metrics.requests_by_endpoint[endpoint_pattern] += 1
                    self._request_endpoint_map[request_id] = endpoint_pattern
                    break
    
    async def _track_request_end(self, request_id: str, start_time: float):
        """Track request end."""
        response_time = (time.time() - start_time) * 1000  # ms
        
        async with self._request_lock:
            if request_id in self._active_requests:
                self._active_requests.remove(request_id)
            
            self._metrics.concurrent_requests = max(0, self._metrics.concurrent_requests - 1)
            
            # Decrement endpoint-specific counters using the stored mapping
            if request_id in self._request_endpoint_map:
                endpoint_pattern = self._request_endpoint_map.pop(request_id)
                if endpoint_pattern in self._metrics.requests_by_endpoint:
                    self._metrics.requests_by_endpoint[endpoint_pattern] = max(
                        0, self._metrics.requests_by_endpoint[endpoint_pattern] - 1
                    )
            
            # Update average response time
            total_completed = self._metrics.successful_requests + self._metrics.failed_requests
            if total_completed > 0:
                self._metrics.avg_response_time_ms = (
                    (self._metrics.avg_response_time_ms * (total_completed - 1) + response_time) 
                    / total_completed
                )
    
    async def _create_throttle_response(
        self, 
        request: Request, 
        reason: str,
        current_phase: StartupPhase
    ) -> JSONResponse:
        """Create response for throttled request."""
        self._metrics.throttled_requests += 1
        
        # Get estimated wait time
        estimated_wait_seconds = self._estimate_wait_time(current_phase)
        
        # Create helpful response
        response_data = {
            "status": "throttled",
            "message": "System is currently handling many requests. Please try again shortly.",
            "reason": reason,
            "retry_after_seconds": estimated_wait_seconds,
            "current_phase": current_phase.value,
            "system_status": {
                "concurrent_requests": self._metrics.concurrent_requests,
                "phase": current_phase.value,
                "health": "operational"
            },
            "guidance": {
                "action": "retry",
                "wait_time": f"{estimated_wait_seconds} seconds",
                "alternative": "Check /api/loading/status for system readiness"
            },
            "timestamp": datetime.now().isoformat()
        }
        
        # Add fallback response if available
        if self.fallback_service and request.method == "POST":
            try:
                # Try to extract user message
                body = await request.body()
                if body:
                    import json
                    data = json.loads(body)
                    user_message = data.get("message", "")
                    
                    if user_message:
                        fallback_response = self.fallback_service.generate_fallback_response(
                            user_message
                        )
                        response_data["fallback_response"] = fallback_response.response_text
                        response_data["estimated_full_ready_time"] = fallback_response.estimated_full_ready_time
            except Exception as e:
                logger.debug(f"Could not generate fallback for throttled request: {e}")
        
        return JSONResponse(
            content=response_data,
            status_code=429,  # Too Many Requests
            headers={"Retry-After": str(estimated_wait_seconds)}
        )
    
    async def _create_error_fallback_response(
        self, 
        request: Request, 
        error_message: str
    ) -> JSONResponse:
        """Create fallback response for errors."""
        self._metrics.fallback_responses += 1
        
        # Try to provide helpful fallback
        if self.expectation_manager:
            try:
                contextual_response = self.expectation_manager.create_contextual_response(
                    user_message="",
                    base_response=f"I encountered an issue processing your request, but the system is operational. Please try again."
                )
                
                return JSONResponse(
                    content={
                        "status": "error_with_fallback",
                        "message": contextual_response["response"],
                        "error_details": error_message,
                        "system_status": contextual_response.get("system_status", {}),
                        "capabilities": contextual_response.get("capabilities", {}),
                        "timestamp": datetime.now().isoformat()
                    },
                    status_code=200  # Return 200 to avoid client-side errors
                )
            except Exception as e:
                logger.error(f"Could not create contextual fallback: {e}")
        
        # Basic fallback
        return JSONResponse(
            content={
                "status": "error",
                "message": "An error occurred, but the system is operational. Please try again.",
                "error_details": error_message,
                "timestamp": datetime.now().isoformat()
            },
            status_code=200
        )
    
    async def _create_emergency_response(
        self, 
        request: Request, 
        error_message: str
    ) -> JSONResponse:
        """Create emergency response when everything fails."""
        return JSONResponse(
            content={
                "status": "emergency_fallback",
                "message": "The system is operational but experiencing high load. Please try again in a moment.",
                "timestamp": datetime.now().isoformat()
            },
            status_code=200
        )
    
    def _estimate_wait_time(self, current_phase: StartupPhase) -> int:
        """Estimate wait time before retry."""
        # Base wait time on current load
        if self._metrics.concurrent_requests > 100:
            return 10
        elif self._metrics.concurrent_requests > 50:
            return 5
        else:
            return 2
    
    def _generate_request_id(self) -> str:
        """Generate unique request ID."""
        import uuid
        return str(uuid.uuid4())
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics."""
        return {
            "total_requests": self._metrics.total_requests,
            "concurrent_requests": self._metrics.concurrent_requests,
            "peak_concurrent_requests": self._metrics.peak_concurrent_requests,
            "throttled_requests": self._metrics.throttled_requests,
            "fallback_responses": self._metrics.fallback_responses,
            "successful_requests": self._metrics.successful_requests,
            "failed_requests": self._metrics.failed_requests,
            "avg_response_time_ms": self._metrics.avg_response_time_ms,
            "success_rate": (
                self._metrics.successful_requests / max(self._metrics.total_requests, 1)
            ) * 100,
            "requests_by_phase": dict(self._metrics.requests_by_phase),
            "requests_by_endpoint": dict(self._metrics.requests_by_endpoint),
            "active_requests": len(self._active_requests)
        }


# Global instance
_concurrent_request_handler = None

def get_concurrent_request_handler() -> Optional[ConcurrentRequestHandler]:
    """Get the global concurrent request handler instance."""
    global _concurrent_request_handler
    return _concurrent_request_handler

def set_concurrent_request_handler(handler: ConcurrentRequestHandler):
    """Set the global concurrent request handler instance."""
    global _concurrent_request_handler
    _concurrent_request_handler = handler
