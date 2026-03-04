"""
Model Request Wrapper

This module provides decorators and wrappers that ensure all model-dependent
operations have proper fallback handling, guaranteeing that no requests fail
due to "model not loaded" errors.

Key Features:
- Automatic model availability checking
- Graceful fallback when models unavailable
- Request queuing for pending model loads
- Comprehensive error handling
"""

import asyncio
import logging
import functools
from typing import Callable, Any, Optional, Dict, List
from datetime import datetime

from ..models.model_manager import get_model_manager
from ..services.fallback_service import get_fallback_service
from ..services.expectation_manager import get_expectation_manager

logger = logging.getLogger(__name__)


class ModelNotAvailableError(Exception):
    """Exception raised when a required model is not available."""
    pass


class ModelRequestWrapper:
    """
    Wrapper for model-dependent requests that ensures graceful fallback.
    """
    
    def __init__(self):
        self.model_manager = get_model_manager()
        self.fallback_service = get_fallback_service()
        self.expectation_manager = get_expectation_manager()
        
        # Request queue for pending model loads
        self.pending_requests: Dict[str, List[Dict[str, Any]]] = {}
        
        logger.info("ModelRequestWrapper initialized")
    
    def require_models(
        self, 
        required_models: List[str],
        fallback_models: Optional[List[str]] = None,
        allow_fallback_response: bool = True
    ):
        """
        Decorator that ensures required models are available before executing function.
        
        Args:
            required_models: List of model names that must be available
            fallback_models: Optional list of fallback models to try
            allow_fallback_response: If True, return fallback response instead of error
        """
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            async def wrapper(*args, **kwargs) -> Any:
                # Check if required models are available
                available_models = []
                unavailable_models = []
                
                for model_name in required_models:
                    if self.model_manager.is_model_available(model_name):
                        available_models.append(model_name)
                    else:
                        unavailable_models.append(model_name)
                
                # All required models available - proceed normally
                if not unavailable_models:
                    return await func(*args, **kwargs)
                
                # Try fallback models
                if fallback_models:
                    for fallback_model in fallback_models:
                        if self.model_manager.is_model_available(fallback_model):
                            logger.info(f"Using fallback model {fallback_model} for {func.__name__}")
                            # Update kwargs to use fallback model
                            kwargs["model_name"] = fallback_model
                            return await func(*args, **kwargs)
                
                # No models available - provide fallback response
                if allow_fallback_response:
                    logger.info(f"Providing fallback response for {func.__name__} (models unavailable: {unavailable_models})")
                    return await self._generate_fallback_for_function(
                        func, args, kwargs, unavailable_models
                    )
                else:
                    # Raise error if fallback not allowed
                    raise ModelNotAvailableError(
                        f"Required models not available: {unavailable_models}"
                    )
            
            return wrapper
        return decorator
    
    def require_capability(
        self,
        required_capability: str,
        allow_fallback_response: bool = True
    ):
        """
        Decorator that ensures a capability is available before executing function.
        
        Args:
            required_capability: Capability that must be available
            allow_fallback_response: If True, return fallback response instead of error
        """
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            async def wrapper(*args, **kwargs) -> Any:
                # Check if capability is available
                if self.model_manager.can_handle_capability(required_capability):
                    return await func(*args, **kwargs)
                
                # Capability not available
                if allow_fallback_response:
                    logger.info(f"Providing fallback response for {func.__name__} (capability unavailable: {required_capability})")
                    return await self._generate_fallback_for_capability(
                        func, args, kwargs, required_capability
                    )
                else:
                    raise ModelNotAvailableError(
                        f"Required capability not available: {required_capability}"
                    )
            
            return wrapper
        return decorator
    
    async def _generate_fallback_for_function(
        self,
        func: Callable,
        args: tuple,
        kwargs: dict,
        unavailable_models: List[str]
    ) -> Dict[str, Any]:
        """Generate a fallback response for a function call."""
        try:
            # Try to extract user message from args/kwargs
            user_message = self._extract_message_from_args(args, kwargs)
            
            if user_message and self.fallback_service:
                # Generate context-aware fallback
                fallback_response = self.fallback_service.generate_fallback_response(user_message)
                
                return {
                    "status": "success",
                    "fallback_mode": True,
                    "response": fallback_response.response_text,
                    "quality_level": fallback_response.response_quality.value,
                    "limitations": fallback_response.limitations,
                    "alternatives": fallback_response.available_alternatives,
                    "upgrade_message": fallback_response.upgrade_message,
                    "estimated_ready_time": fallback_response.estimated_full_ready_time,
                    "unavailable_models": unavailable_models
                }
            
            # Basic fallback
            return {
                "status": "success",
                "fallback_mode": True,
                "response": f"The requested functionality requires models that are currently loading: {', '.join(unavailable_models)}. Please try again in a moment.",
                "quality_level": "basic",
                "unavailable_models": unavailable_models
            }
        
        except Exception as e:
            logger.error(f"Error generating fallback for function: {e}")
            
            # Emergency fallback
            return {
                "status": "success",
                "fallback_mode": True,
                "emergency_fallback": True,
                "response": "I'm currently starting up. Please try again in a moment.",
                "quality_level": "basic"
            }
    
    async def _generate_fallback_for_capability(
        self,
        func: Callable,
        args: tuple,
        kwargs: dict,
        capability: str
    ) -> Dict[str, Any]:
        """Generate a fallback response for a capability requirement."""
        try:
            # Get capability status
            status = self.model_manager.get_capability_status(capability)
            
            # Try to extract user message
            user_message = self._extract_message_from_args(args, kwargs)
            
            if user_message and self.fallback_service:
                # Generate context-aware fallback
                fallback_response = self.fallback_service.generate_fallback_response(user_message)
                
                return {
                    "status": "success",
                    "fallback_mode": True,
                    "response": fallback_response.response_text,
                    "quality_level": fallback_response.response_quality.value,
                    "capability_status": status,
                    "limitations": fallback_response.limitations,
                    "alternatives": fallback_response.available_alternatives,
                    "upgrade_message": fallback_response.upgrade_message
                }
            
            # Basic fallback
            loading_models = status.get("loading_models", [])
            if loading_models:
                message = f"The {capability} capability is currently loading. Please try again in a moment."
            else:
                message = f"The {capability} capability is currently unavailable. I can help with basic tasks while the system finishes loading."
            
            return {
                "status": "success",
                "fallback_mode": True,
                "response": message,
                "quality_level": "basic",
                "capability_status": status
            }
        
        except Exception as e:
            logger.error(f"Error generating fallback for capability: {e}")
            
            # Emergency fallback
            return {
                "status": "success",
                "fallback_mode": True,
                "emergency_fallback": True,
                "response": "I'm currently starting up. Please try again in a moment.",
                "quality_level": "basic"
            }
    
    def _extract_message_from_args(self, args: tuple, kwargs: dict) -> Optional[str]:
        """Extract user message from function arguments."""
        # Check kwargs first
        for key in ["message", "query", "text", "user_message", "prompt"]:
            if key in kwargs:
                return str(kwargs[key])
        
        # Check args
        for arg in args:
            if isinstance(arg, str) and len(arg) > 0:
                return arg
            elif isinstance(arg, dict):
                for key in ["message", "query", "text", "user_message", "prompt"]:
                    if key in arg:
                        return str(arg[key])
        
        return None
    
    async def execute_with_fallback(
        self,
        func: Callable,
        *args,
        required_models: Optional[List[str]] = None,
        required_capability: Optional[str] = None,
        **kwargs
    ) -> Any:
        """
        Execute a function with automatic fallback handling.
        
        Args:
            func: Function to execute
            required_models: Optional list of required models
            required_capability: Optional required capability
            *args, **kwargs: Arguments to pass to function
        """
        try:
            # Check model availability if specified
            if required_models:
                unavailable = [
                    model for model in required_models
                    if not self.model_manager.is_model_available(model)
                ]
                
                if unavailable:
                    logger.info(f"Models unavailable for {func.__name__}: {unavailable}")
                    return await self._generate_fallback_for_function(
                        func, args, kwargs, unavailable
                    )
            
            # Check capability availability if specified
            if required_capability:
                if not self.model_manager.can_handle_capability(required_capability):
                    logger.info(f"Capability unavailable for {func.__name__}: {required_capability}")
                    return await self._generate_fallback_for_capability(
                        func, args, kwargs, required_capability
                    )
            
            # Execute function
            if asyncio.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            else:
                return func(*args, **kwargs)
        
        except ModelNotAvailableError as e:
            logger.warning(f"Model not available error in {func.__name__}: {e}")
            return await self._generate_fallback_for_function(
                func, args, kwargs, [str(e)]
            )
        
        except Exception as e:
            logger.error(f"Error executing {func.__name__}: {e}")
            
            # Emergency fallback
            return {
                "status": "error_handled",
                "fallback_mode": True,
                "emergency_fallback": True,
                "response": "An error occurred, but I'm still here. Please try again.",
                "error": str(e)
            }


# Global wrapper instance
_model_request_wrapper: Optional[ModelRequestWrapper] = None


def get_model_request_wrapper() -> ModelRequestWrapper:
    """Get the global model request wrapper instance."""
    global _model_request_wrapper
    if _model_request_wrapper is None:
        _model_request_wrapper = ModelRequestWrapper()
    return _model_request_wrapper


# Convenience decorators
def require_models(
    required_models: List[str],
    fallback_models: Optional[List[str]] = None,
    allow_fallback_response: bool = True
):
    """Decorator that ensures required models are available."""
    wrapper = get_model_request_wrapper()
    return wrapper.require_models(required_models, fallback_models, allow_fallback_response)


def require_capability(
    required_capability: str,
    allow_fallback_response: bool = True
):
    """Decorator that ensures a capability is available."""
    wrapper = get_model_request_wrapper()
    return wrapper.require_capability(required_capability, allow_fallback_response)
