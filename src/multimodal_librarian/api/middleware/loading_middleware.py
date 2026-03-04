"""
Loading State Management Middleware

This middleware intercepts API requests and adds loading state information
to responses. It provides real-time capability advertising and manages
user expectations during system startup.

Key Features:
- Automatic capability checking for requests
- Loading state injection into responses
- Progress tracking and ETA calculations
- Request queuing for unavailable capabilities
"""

import json
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from ...logging_config import get_logger
from ...services.capability_service import CapabilityLevel, get_capability_service
from ...startup.minimal_server import get_minimal_server

logger = get_logger("loading_middleware")


class LoadingStateMiddleware(BaseHTTPMiddleware):
    """Middleware for managing loading states and capability advertising."""
    
    def __init__(self, app):
        super().__init__(app)
        self.capability_service = get_capability_service()
        self.request_capability_map = self._define_request_capabilities()
    
    def _define_request_capabilities(self) -> Dict[str, List[str]]:
        """Define which capabilities are required for different request types."""
        return {
            # Health and status endpoints (always available)
            "/api/health": [],
            "/health": [],
            "/status": [],
            
            # Basic chat endpoints
            "/api/chat/simple": ["simple_text"],
            "/api/chat/basic": ["basic_chat"],
            "/api/chat": ["advanced_chat"],
            
            # Search endpoints
            "/api/search/simple": ["simple_search"],
            "/api/search": ["semantic_search"],
            
            # Document endpoints
            "/api/documents/upload": ["document_upload"],
            "/api/documents/analyze": ["document_analysis"],
            "/api/documents/process": ["document_analysis"],
            
            # Advanced features
            "/api/reasoning": ["complex_reasoning"],
            "/api/multimodal": ["multimodal_processing"],
            
            # Default for unknown endpoints
            "default": ["basic_chat"]
        }
    
    async def dispatch(self, request: Request, call_next):
        """Process request and add loading state information."""
        # Skip WebSocket connections - BaseHTTPMiddleware doesn't handle them properly
        if request.headers.get("upgrade", "").lower() == "websocket":
            return await call_next(request)
        
        start_time = time.time()
        
        try:
            # Skip middleware for static files and certain paths
            if self._should_skip_middleware(request):
                return await call_next(request)
            
            # Get required capabilities for this request
            required_capabilities = self._get_required_capabilities(request)
            
            # Check if we can handle this request
            capability_check = self.capability_service.can_handle_request(
                request_type=str(request.url.path),
                required_capabilities=required_capabilities
            )
            
            # Add loading state to request for downstream handlers
            request.state.loading_info = {
                "capability_check": capability_check,
                "required_capabilities": required_capabilities,
                "request_start_time": start_time
            }
            
            # Process the request
            response = await call_next(request)
            
            # Add loading state information to response
            response = await self._enhance_response_with_loading_state(
                request, response, capability_check, start_time
            )
            
            return response
            
        except Exception as e:
            logger.error(f"Loading middleware error: {e}")
            # Return error response with loading state
            return await self._create_error_response_with_loading_state(request, str(e))
    
    def _should_skip_middleware(self, request: Request) -> bool:
        """Determine if middleware should be skipped for this request."""
        skip_paths = [
            "/static/",
            "/favicon.ico",
            "/robots.txt",
            "/docs",
            "/openapi.json"
        ]
        
        path = str(request.url.path)
        return any(path.startswith(skip_path) for skip_path in skip_paths)
    
    def _get_required_capabilities(self, request: Request) -> List[str]:
        """Get required capabilities for the request."""
        path = str(request.url.path)
        
        # Check for exact matches first
        if path in self.request_capability_map:
            return self.request_capability_map[path]
        
        # Check for prefix matches
        for pattern, capabilities in self.request_capability_map.items():
            if path.startswith(pattern):
                return capabilities
        
        # Return default capabilities
        return self.request_capability_map.get("default", ["basic_chat"])
    
    async def _enhance_response_with_loading_state(
        self, 
        request: Request, 
        response: Response, 
        capability_check: Dict[str, Any],
        start_time: float
    ) -> Response:
        """Add loading state information to the response."""
        try:
            # Only enhance JSON responses
            if not self._is_json_response(response):
                return response
            
            # Get current loading state
            loading_state = self._get_current_loading_state()
            
            # Calculate response time
            response_time_ms = (time.time() - start_time) * 1000
            
            # Parse existing response body
            response_body = await self._get_response_body(response)
            
            if isinstance(response_body, dict):
                # Add loading state to existing JSON response
                response_body["loading_state"] = {
                    "capability_check": capability_check,
                    "current_capabilities": loading_state["capabilities"],
                    "loading_progress": loading_state["progress"],
                    "system_status": loading_state["system_status"],
                    "response_time_ms": response_time_ms,
                    "timestamp": datetime.now().isoformat()
                }
                
                # Add quality indicator to response
                response_body["response_quality"] = {
                    "level": capability_check["quality_level"],
                    "indicator": capability_check["quality_indicator"],
                    "description": self._get_quality_description(capability_check["quality_level"])
                }
                
                # Create new response with enhanced body
                return JSONResponse(
                    content=response_body,
                    status_code=response.status_code,
                    headers=dict(response.headers)
                )
            
            return response
            
        except Exception as e:
            logger.error(f"Error enhancing response with loading state: {e}")
            return response
    
    def _is_json_response(self, response: Response) -> bool:
        """Check if response is JSON."""
        content_type = response.headers.get("content-type", "")
        return "application/json" in content_type
    
    async def _get_response_body(self, response: Response) -> Any:
        """Get response body as parsed JSON."""
        try:
            if hasattr(response, 'body'):
                body_bytes = response.body
            else:
                # For streaming responses, we can't easily modify them
                return None
            
            if body_bytes:
                body_str = body_bytes.decode('utf-8')
                return json.loads(body_str)
            
            return {}
            
        except Exception as e:
            logger.error(f"Error parsing response body: {e}")
            return {}
    
    def _get_current_loading_state(self) -> Dict[str, Any]:
        """Get current system loading state."""
        try:
            capabilities = self.capability_service.get_capability_summary()
            progress = self.capability_service.get_loading_progress()
            
            # Get server status
            server = get_minimal_server()
            server_status = server.get_status()
            
            return {
                "capabilities": capabilities,
                "progress": progress,
                "system_status": {
                    "phase": server_status.status.value,
                    "uptime_seconds": server_status.uptime_seconds,
                    "health_check_ready": server_status.health_check_ready
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting loading state: {e}")
            return {
                "capabilities": {},
                "progress": {},
                "system_status": {"phase": "unknown", "uptime_seconds": 0}
            }
    
    def _get_quality_description(self, quality_level: str) -> str:
        """Get description for quality level."""
        descriptions = {
            "basic": "Quick response mode - Basic text processing only",
            "enhanced": "Partial AI mode - Some advanced features available",
            "full": "Full AI mode - All capabilities ready"
        }
        return descriptions.get(quality_level, "Unknown quality level")
    
    async def _create_error_response_with_loading_state(
        self, 
        request: Request, 
        error_message: str
    ) -> JSONResponse:
        """Create error response with loading state information."""
        try:
            loading_state = self._get_current_loading_state()
            
            error_response = {
                "error": error_message,
                "status": "error",
                "loading_state": {
                    "current_capabilities": loading_state["capabilities"],
                    "loading_progress": loading_state["progress"],
                    "system_status": loading_state["system_status"],
                    "timestamp": datetime.now().isoformat()
                },
                "response_quality": {
                    "level": "basic",
                    "indicator": "⚡",
                    "description": "Error response - basic information only"
                }
            }
            
            return JSONResponse(content=error_response, status_code=500)
            
        except Exception as e:
            logger.error(f"Error creating error response with loading state: {e}")
            return JSONResponse(
                content={"error": error_message, "status": "error"},
                status_code=500
            )


class LoadingStateInjector:
    """Helper class for manually injecting loading state into responses."""
    
    def __init__(self):
        self.capability_service = get_capability_service()
    
    def inject_loading_state(
        self, 
        response_data: Dict[str, Any], 
        request_type: str = "default",
        required_capabilities: List[str] = None
    ) -> Dict[str, Any]:
        """Manually inject loading state into response data."""
        try:
            if required_capabilities is None:
                required_capabilities = ["basic_chat"]
            
            # Check capabilities
            capability_check = self.capability_service.can_handle_request(
                request_type=request_type,
                required_capabilities=required_capabilities
            )
            
            # Get current state
            capabilities = self.capability_service.get_capability_summary()
            progress = self.capability_service.get_loading_progress()
            
            # Add loading state to response
            response_data["loading_state"] = {
                "capability_check": capability_check,
                "current_capabilities": capabilities,
                "loading_progress": progress,
                "timestamp": datetime.now().isoformat()
            }
            
            # Add quality indicator
            response_data["response_quality"] = {
                "level": capability_check["quality_level"],
                "indicator": capability_check["quality_indicator"],
                "description": self._get_quality_description(capability_check["quality_level"])
            }
            
            return response_data
            
        except Exception as e:
            logger.error(f"Error injecting loading state: {e}")
            return response_data
    
    def _get_quality_description(self, quality_level: str) -> str:
        """Get description for quality level."""
        descriptions = {
            "basic": "Quick response mode - Basic text processing only",
            "enhanced": "Partial AI mode - Some advanced features available", 
            "full": "Full AI mode - All capabilities ready"
        }
        return descriptions.get(quality_level, "Unknown quality level")


# Global loading state injector
_loading_state_injector = None

def get_loading_state_injector() -> LoadingStateInjector:
    """Get the global loading state injector instance."""
    global _loading_state_injector
    if _loading_state_injector is None:
        _loading_state_injector = LoadingStateInjector()
    return _loading_state_injector