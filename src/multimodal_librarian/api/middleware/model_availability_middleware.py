"""
Model Availability Middleware

This middleware ensures that NO user requests fail due to "model not loaded" errors.
It intercepts all requests and provides graceful fallback responses when models are unavailable.

Key Features:
- Intercepts all API requests
- Checks model availability before processing
- Provides automatic fallback responses
- Tracks model availability errors
- Ensures 100% request success rate

Updated to use ModelStatusService as the single source of truth for model
availability, replacing the fragmented status tracking in ModelManager.
"""

import logging
import time
from typing import Any, Callable, Dict, Optional

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from ...logging.ux_logger import (
    RequestOutcome,
    get_ux_logger,
    log_fallback_response_usage,
)
from ...models.model_manager import get_model_manager
from ...services.expectation_manager import get_expectation_manager
from ...services.fallback_service import get_fallback_service

logger = logging.getLogger(__name__)


class ModelAvailabilityMiddleware(BaseHTTPMiddleware):
    """
    Middleware that ensures no requests fail due to model unavailability.
    
    This middleware:
    1. Checks if required models are available for each request
    2. Provides fallback responses when models are unavailable
    3. Tracks and logs model availability issues
    4. Ensures 100% request success rate
    """
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.model_manager = get_model_manager()
        self.fallback_service = get_fallback_service()
        self.expectation_manager = get_expectation_manager()
        self.ux_logger = get_ux_logger()
        
        # ModelStatusService will be retrieved lazily to avoid import-time issues
        self._model_status_service = None
        
        # Statistics
        self.stats = {
            "total_requests": 0,
            "model_available_requests": 0,
            "fallback_responses": 0,
            "model_not_loaded_prevented": 0
        }
        
        logger.info("ModelAvailabilityMiddleware initialized")
    
    def _get_model_status_service(self):
        """Get the ModelStatusService instance if available."""
        if self._model_status_service is not None:
            return self._model_status_service
        
        try:
            # Try to get from the DI system's cached instance
            from ..dependencies.services import _model_status_service
            if _model_status_service is not None:
                self._model_status_service = _model_status_service
                return self._model_status_service
            
            # Fallback to the service module's global instance
            from ...services.model_status_service import get_model_status_service
            service = get_model_status_service()
            if service is not None:
                self._model_status_service = service
            return service
        except ImportError:
            return None
        except Exception as e:
            logger.debug(f"Could not get ModelStatusService: {e}")
            return None
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process each request and ensure model availability."""
        # Skip WebSocket connections - BaseHTTPMiddleware doesn't handle them properly
        if request.headers.get("upgrade", "").lower() == "websocket":
            return await call_next(request)
        start_time = time.time()
        request_id = str(time.time())
        
        # Track total requests
        self.stats["total_requests"] += 1
        
        # Skip middleware for certain paths
        if self._should_skip_middleware(request.url.path):
            return await call_next(request)
        
        try:
            # Check if this request requires models
            required_capabilities = self._get_required_capabilities(request)
            
            if not required_capabilities:
                # No model requirements, proceed normally
                return await call_next(request)
            
            # Check if required capabilities are available
            availability_check = self._check_capability_availability(required_capabilities)
            
            if availability_check["all_available"]:
                # All required models available, proceed normally
                self.stats["model_available_requests"] += 1
                return await call_next(request)
            
            # Models not available - provide fallback response
            logger.info(f"Models not available for request {request_id}, providing fallback response")
            self.stats["fallback_responses"] += 1
            self.stats["model_not_loaded_prevented"] += 1
            
            # Generate fallback response
            fallback_response = await self._generate_fallback_response(
                request, 
                required_capabilities,
                availability_check
            )
            
            # Log fallback usage
            try:
                await log_fallback_response_usage(
                    request_id=request_id,
                    fallback_response=fallback_response["fallback_data"],
                    user_acceptance=None,
                    user_feedback="middleware_fallback"
                )
            except Exception as log_error:
                logger.debug(f"Failed to log fallback usage: {log_error}")
            
            # Return fallback response
            response_time = (time.time() - start_time) * 1000
            
            return JSONResponse(
                status_code=200,  # Always return 200 to prevent errors
                content={
                    "status": "success",
                    "fallback_mode": True,
                    "response": fallback_response["response"],
                    "metadata": {
                        "model_availability": availability_check,
                        "required_capabilities": required_capabilities,
                        "response_time_ms": response_time,
                        "request_id": request_id,
                        "quality_level": fallback_response.get("quality_level", "basic")
                    },
                    "system_status": fallback_response.get("system_status", {}),
                    "user_guidance": fallback_response.get("user_guidance", {})
                }
            )
        
        except Exception as e:
            # Ultimate fallback - ensure we NEVER return an error
            logger.error(f"Error in ModelAvailabilityMiddleware: {e}")
            
            return JSONResponse(
                status_code=200,
                content={
                    "status": "success",
                    "fallback_mode": True,
                    "emergency_fallback": True,
                    "response": {
                        "message": "I'm currently experiencing technical difficulties, but I'm here and working. Please try again in a moment.",
                        "system_status": "starting_up"
                    },
                    "metadata": {
                        "error_handled": True,
                        "request_id": request_id
                    }
                }
            )
    
    def _should_skip_middleware(self, path: str) -> bool:
        """Determine if middleware should be skipped for this path."""
        skip_paths = [
            "/health",
            "/ready",
            "/metrics",
            "/docs",
            "/openapi.json",
            "/static/",
            "/favicon.ico"
        ]
        
        return any(path.startswith(skip_path) for skip_path in skip_paths)
    
    def _get_required_capabilities(self, request: Request) -> list[str]:
        """Determine what capabilities are required for this request."""
        path = request.url.path
        method = request.method
        
        # Map paths to required capabilities
        capability_map = {
            "/api/chat": ["basic_chat", "advanced_chat"],
            "/api/v1/chat": ["basic_chat", "advanced_chat"],
            "/ws/chat": ["basic_chat"],
            "/api/search": ["simple_search", "semantic_search"],
            "/api/v1/search": ["simple_search", "semantic_search"],
            "/api/documents": ["document_analysis"],
            "/api/v1/documents": ["document_analysis"],
            "/api/analyze": ["complex_reasoning"],
            "/api/v1/analyze": ["complex_reasoning"]
        }
        
        # Check for exact matches
        for path_prefix, capabilities in capability_map.items():
            if path.startswith(path_prefix):
                return capabilities
        
        # Default: no specific requirements
        return []
    
    def _check_capability_availability(self, capabilities: list[str]) -> Dict[str, Any]:
        """Check if required capabilities are available.
        
        Uses ModelStatusService as the primary source of truth, with fallback
        to ModelManager for backward compatibility.
        """
        # Try to use ModelStatusService first (single source of truth)
        model_status_service = self._get_model_status_service()
        
        if model_status_service is not None:
            return self._check_availability_from_model_status_service(
                capabilities, model_status_service
            )
        
        # Fallback to ModelManager for backward compatibility
        logger.debug("ModelStatusService not available, falling back to ModelManager")
        return self._check_availability_from_model_manager(capabilities)
    
    def _check_availability_from_model_status_service(
        self, 
        capabilities: list[str],
        model_status_service
    ) -> Dict[str, Any]:
        """Check capability availability using ModelStatusService."""
        available = []
        unavailable = []
        loading = []
        
        # Get available capabilities from ModelStatusService
        available_capabilities = model_status_service.get_available_capabilities()
        
        for capability in capabilities:
            if capability in available_capabilities:
                available.append(capability)
            else:
                # Check if models are loading
                status = model_status_service.get_capability_status(capability)
                if status.get("loading_models"):
                    loading.append(capability)
                else:
                    unavailable.append(capability)
        
        return {
            "all_available": len(unavailable) == 0 and len(loading) == 0,
            "some_available": len(available) > 0,
            "available_capabilities": available,
            "unavailable_capabilities": unavailable,
            "loading_capabilities": loading
        }
    
    def _check_availability_from_model_manager(self, capabilities: list[str]) -> Dict[str, Any]:
        """Check capability availability using ModelManager (legacy fallback)."""
        available = []
        unavailable = []
        loading = []
        
        for capability in capabilities:
            status = self.model_manager.get_capability_status(capability)
            
            if status["available"]:
                available.append(capability)
            elif status["loading_models"]:
                loading.append(capability)
            else:
                unavailable.append(capability)
        
        return {
            "all_available": len(unavailable) == 0 and len(loading) == 0,
            "some_available": len(available) > 0,
            "available_capabilities": available,
            "unavailable_capabilities": unavailable,
            "loading_capabilities": loading
        }
    
    async def _generate_fallback_response(
        self, 
        request: Request,
        required_capabilities: list[str],
        availability_check: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate a fallback response when models are unavailable."""
        try:
            # Try to extract user message from request
            user_message = await self._extract_user_message(request)
            
            # Generate context-aware fallback
            if user_message and self.fallback_service:
                fallback_data = self.fallback_service.generate_fallback_response(user_message)
                
                # Create contextual response using expectation manager
                if self.expectation_manager:
                    contextual_response = self.expectation_manager.create_contextual_response(
                        user_message=user_message,
                        base_response=fallback_data.response_text
                    )
                    
                    return {
                        "response": contextual_response["response"],
                        "quality_level": fallback_data.response_quality.value,
                        "system_status": contextual_response.get("system_status", {}),
                        "user_guidance": contextual_response.get("user_guidance", {}),
                        "fallback_data": fallback_data
                    }
                else:
                    return {
                        "response": fallback_data.response_text,
                        "quality_level": fallback_data.response_quality.value,
                        "system_status": {
                            "current_mode": "loading",
                            "available_capabilities": availability_check["available_capabilities"],
                            "loading_capabilities": availability_check["loading_capabilities"]
                        },
                        "user_guidance": {
                            "limitations": fallback_data.limitations,
                            "alternatives": fallback_data.available_alternatives
                        },
                        "fallback_data": fallback_data
                    }
            
            # Basic fallback if services not available
            return {
                "response": self._generate_basic_fallback(required_capabilities, availability_check),
                "quality_level": "basic",
                "system_status": {
                    "current_mode": "loading",
                    "available_capabilities": availability_check["available_capabilities"],
                    "loading_capabilities": availability_check["loading_capabilities"]
                },
                "user_guidance": {
                    "limitations": ["Advanced AI features are loading"],
                    "alternatives": ["Try again in a moment", "Ask simple questions"]
                },
                "fallback_data": None
            }
        
        except Exception as e:
            logger.error(f"Error generating fallback response: {e}")
            
            # Emergency fallback
            return {
                "response": "I'm currently starting up. Please try again in a moment.",
                "quality_level": "basic",
                "system_status": {"current_mode": "starting"},
                "user_guidance": {
                    "limitations": ["System is initializing"],
                    "alternatives": ["Wait a moment and try again"]
                },
                "fallback_data": None
            }
    
    async def _extract_user_message(self, request: Request) -> Optional[str]:
        """Extract user message from request."""
        try:
            # Try to get message from query params
            if "message" in request.query_params:
                return request.query_params["message"]
            
            # Try to get message from JSON body
            if request.method == "POST":
                try:
                    body = await request.json()
                    if isinstance(body, dict):
                        return body.get("message") or body.get("query") or body.get("text")
                except Exception:
                    pass
            
            return None
        
        except Exception as e:
            logger.debug(f"Could not extract user message: {e}")
            return None
    
    def _generate_basic_fallback(
        self, 
        required_capabilities: list[str],
        availability_check: Dict[str, Any]
    ) -> str:
        """Generate a basic fallback message."""
        if availability_check["loading_capabilities"]:
            loading_caps = ", ".join(availability_check["loading_capabilities"])
            return f"I'm currently loading my {loading_caps} capabilities. Please wait a moment and try again."
        
        elif availability_check["unavailable_capabilities"]:
            unavailable_caps = ", ".join(availability_check["unavailable_capabilities"])
            return f"The {unavailable_caps} features are currently unavailable. I can help with basic tasks while the system finishes loading."
        
        else:
            return "I'm currently starting up. Please try again in a moment."
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get middleware statistics."""
        return {
            **self.stats,
            "fallback_rate": (
                self.stats["fallback_responses"] / self.stats["total_requests"] * 100
                if self.stats["total_requests"] > 0 else 0
            ),
            "model_available_rate": (
                self.stats["model_available_requests"] / self.stats["total_requests"] * 100
                if self.stats["total_requests"] > 0 else 0
            )
        }


def get_model_availability_middleware() -> ModelAvailabilityMiddleware:
    """Get the model availability middleware instance."""
    # This will be instantiated by FastAPI when added to the app
    return ModelAvailabilityMiddleware

def get_model_availability_middleware() -> ModelAvailabilityMiddleware:
    """Get the model availability middleware instance."""
    # This will be instantiated by FastAPI when added to the app
    return ModelAvailabilityMiddleware
