"""
Error handling decorators and utilities for comprehensive error logging.

This module provides decorators and utilities to automatically capture
and log errors with full context information across the application.
"""

import asyncio
import functools
import inspect
from typing import Any, Callable, Dict, Optional, TypeVar, Union
from datetime import datetime

from .error_logging_service import (
    get_error_logging_service, 
    ErrorSeverity, 
    ErrorCategory,
    error_context
)
from ..logging_config import get_logger

F = TypeVar('F', bound=Callable[..., Any])

logger = get_logger("error_handler")


def handle_errors(
    service: str,
    operation: Optional[str] = None,
    severity: Optional[ErrorSeverity] = None,
    category: Optional[ErrorCategory] = None,
    reraise: bool = True,
    fallback_return: Any = None,
    context_extractor: Optional[Callable] = None
):
    """
    Decorator for comprehensive error handling and logging.
    
    Args:
        service: Service name for error categorization
        operation: Operation name (defaults to function name)
        severity: Custom error severity
        category: Custom error category
        reraise: Whether to re-raise the exception after logging
        fallback_return: Value to return if error occurs and reraise=False
        context_extractor: Function to extract additional context from function args
    """
    def decorator(func: F) -> F:
        actual_operation = operation or func.__name__
        
        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                # Extract additional context
                additional_context = {}
                if context_extractor:
                    try:
                        additional_context = context_extractor(*args, **kwargs)
                    except Exception as e:
                        logger.warning(f"Context extraction failed: {e}")
                
                # Add function parameters to context
                sig = inspect.signature(func)
                bound_args = sig.bind(*args, **kwargs)
                bound_args.apply_defaults()
                
                additional_context['input_parameters'] = {
                    k: str(v)[:200] if isinstance(v, str) else str(type(v).__name__)
                    for k, v in bound_args.arguments.items()
                }
                
                try:
                    async with error_context(service, actual_operation, additional_context):
                        return await func(*args, **kwargs)
                except Exception as e:
                    if not reraise:
                        logger.info(f"Error handled, returning fallback value: {fallback_return}")
                        return fallback_return
                    raise
            
            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                # Extract additional context
                additional_context = {}
                if context_extractor:
                    try:
                        additional_context = context_extractor(*args, **kwargs)
                    except Exception as e:
                        logger.warning(f"Context extraction failed: {e}")
                
                # Add function parameters to context
                sig = inspect.signature(func)
                bound_args = sig.bind(*args, **kwargs)
                bound_args.apply_defaults()
                
                additional_context['input_parameters'] = {
                    k: str(v)[:200] if isinstance(v, str) else str(type(v).__name__)
                    for k, v in bound_args.arguments.items()
                }
                
                try:
                    error_logging_service = get_error_logging_service()
                    error_id = None
                    
                    try:
                        return func(*args, **kwargs)
                    except Exception as e:
                        error_id = error_logging_service.log_error(
                            e, service, actual_operation, 
                            additional_context, severity, category
                        )
                        if not reraise:
                            logger.info(f"Error handled, returning fallback value: {fallback_return}")
                            return fallback_return
                        raise
                        
                except Exception as e:
                    if hasattr(e, 'error_id'):
                        logger.error(f"Error {e.error_id} in {service}.{actual_operation}: {e}")
                    raise
            
            return sync_wrapper
    
    return decorator


def handle_service_errors(service: str, **kwargs):
    """Convenience decorator for service-level error handling."""
    return handle_errors(service=service, **kwargs)


def handle_api_errors(endpoint: str, **kwargs):
    """Convenience decorator for API endpoint error handling."""
    return handle_errors(service="api", operation=endpoint, **kwargs)


def handle_database_errors(operation: str, **kwargs):
    """Convenience decorator for database operation error handling."""
    return handle_errors(
        service="database", 
        operation=operation,
        category=ErrorCategory.DATABASE_ERROR,
        severity=ErrorSeverity.HIGH,
        **kwargs
    )


def handle_search_errors(operation: str, **kwargs):
    """Convenience decorator for search operation error handling."""
    return handle_errors(
        service="search", 
        operation=operation,
        category=ErrorCategory.SERVICE_FAILURE,
        severity=ErrorSeverity.MEDIUM,
        **kwargs
    )


def handle_ai_errors(operation: str, **kwargs):
    """Convenience decorator for AI service error handling."""
    return handle_errors(
        service="ai_service", 
        operation=operation,
        category=ErrorCategory.EXTERNAL_SERVICE_ERROR,
        severity=ErrorSeverity.MEDIUM,
        **kwargs
    )


class ErrorRecoveryManager:
    """Manager for automatic error recovery strategies."""
    
    def __init__(self):
        self.error_logging_service = get_error_logging_service()
        self.logger = get_logger("error_recovery_manager")
        
        # Recovery strategies
        self.recovery_strategies = {
            'retry_with_backoff': self._retry_with_backoff,
            'retry_with_fallback': self._retry_with_fallback,
            'reconnect_database': self._reconnect_database,
            'refresh_credentials': self._refresh_credentials,
            'free_memory_and_retry': self._free_memory_and_retry,
            'validate_and_retry': self._validate_and_retry,
            'use_default_value': self._use_default_value,
            'reload_configuration': self._reload_configuration
        }
    
    async def attempt_recovery(self, error_id: str, strategy: str, 
                             original_function: Callable, 
                             args: tuple, kwargs: dict) -> tuple[bool, Any]:
        """
        Attempt to recover from an error using the specified strategy.
        
        Returns:
            Tuple of (success, result)
        """
        if strategy not in self.recovery_strategies:
            self.logger.warning(f"Unknown recovery strategy: {strategy}")
            return False, None
        
        try:
            recovery_func = self.recovery_strategies[strategy]
            success, result = await recovery_func(error_id, original_function, args, kwargs)
            
            self.error_logging_service.log_recovery_attempt(
                error_id, strategy, success, 
                {'result_type': type(result).__name__ if result is not None else 'None'}
            )
            
            return success, result
            
        except Exception as e:
            self.logger.error(f"Recovery strategy {strategy} failed: {e}")
            self.error_logging_service.log_recovery_attempt(
                error_id, strategy, False, 
                {'recovery_error': str(e)}
            )
            return False, None
    
    async def _retry_with_backoff(self, error_id: str, func: Callable, 
                                args: tuple, kwargs: dict) -> tuple[bool, Any]:
        """Retry with exponential backoff."""
        import time
        
        max_retries = 3
        base_delay = 1.0
        
        for attempt in range(max_retries):
            try:
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)
                return True, result
                
            except Exception as e:
                if attempt == max_retries - 1:
                    return False, None
                
                delay = base_delay * (2 ** attempt)
                self.logger.info(f"Retry attempt {attempt + 1} failed, waiting {delay}s")
                await asyncio.sleep(delay)
        
        return False, None
    
    async def _retry_with_fallback(self, error_id: str, func: Callable, 
                                 args: tuple, kwargs: dict) -> tuple[bool, Any]:
        """Retry once, then use fallback if available."""
        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            return True, result
            
        except Exception:
            # Try to find a fallback function
            fallback_name = f"{func.__name__}_fallback"
            if hasattr(func, '__self__'):
                # Method call
                if hasattr(func.__self__, fallback_name):
                    fallback_func = getattr(func.__self__, fallback_name)
                    try:
                        if asyncio.iscoroutinefunction(fallback_func):
                            result = await fallback_func(*args, **kwargs)
                        else:
                            result = fallback_func(*args, **kwargs)
                        return True, result
                    except Exception:
                        pass
            
            return False, None
    
    async def _reconnect_database(self, error_id: str, func: Callable, 
                                args: tuple, kwargs: dict) -> tuple[bool, Any]:
        """Attempt to reconnect to database and retry."""
        try:
            # This would be implemented with actual database reconnection logic
            self.logger.info("Attempting database reconnection")
            await asyncio.sleep(1)  # Simulate reconnection delay
            
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            return True, result
            
        except Exception:
            return False, None
    
    async def _refresh_credentials(self, error_id: str, func: Callable, 
                                 args: tuple, kwargs: dict) -> tuple[bool, Any]:
        """Refresh authentication credentials and retry."""
        try:
            # This would be implemented with actual credential refresh logic
            self.logger.info("Attempting credential refresh")
            await asyncio.sleep(0.5)  # Simulate refresh delay
            
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            return True, result
            
        except Exception:
            return False, None
    
    async def _free_memory_and_retry(self, error_id: str, func: Callable, 
                                   args: tuple, kwargs: dict) -> tuple[bool, Any]:
        """Attempt to free memory and retry."""
        try:
            import gc
            gc.collect()  # Force garbage collection
            self.logger.info("Performed garbage collection")
            
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            return True, result
            
        except Exception:
            return False, None
    
    async def _validate_and_retry(self, error_id: str, func: Callable, 
                                args: tuple, kwargs: dict) -> tuple[bool, Any]:
        """Validate inputs and retry with corrected data."""
        try:
            # This would implement input validation and correction
            self.logger.info("Attempting input validation and correction")
            
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            return True, result
            
        except Exception:
            return False, None
    
    async def _use_default_value(self, error_id: str, func: Callable, 
                                args: tuple, kwargs: dict) -> tuple[bool, Any]:
        """Return a default value instead of retrying."""
        # This would determine appropriate default values based on function signature
        return True, None
    
    async def _reload_configuration(self, error_id: str, func: Callable, 
                                  args: tuple, kwargs: dict) -> tuple[bool, Any]:
        """Reload configuration and retry."""
        try:
            # This would implement configuration reloading
            self.logger.info("Attempting configuration reload")
            
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            return True, result
            
        except Exception:
            return False, None


# Global recovery manager instance
_recovery_manager = None


def get_recovery_manager() -> ErrorRecoveryManager:
    """Get the global error recovery manager instance."""
    global _recovery_manager
    if _recovery_manager is None:
        _recovery_manager = ErrorRecoveryManager()
    return _recovery_manager


def with_recovery(strategy: str):
    """
    Decorator to add automatic error recovery to functions.
    
    Args:
        strategy: Recovery strategy to use
    """
    def decorator(func: F) -> F:
        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    if hasattr(e, 'error_id'):
                        recovery_manager = get_recovery_manager()
                        success, result = await recovery_manager.attempt_recovery(
                            e.error_id, strategy, func, args, kwargs
                        )
                        if success:
                            return result
                    raise
            
            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if hasattr(e, 'error_id'):
                        recovery_manager = get_recovery_manager()
                        # For sync functions, we can't use async recovery
                        logger.info(f"Error recovery not available for sync function: {func.__name__}")
                    raise
            
            return sync_wrapper
    
    return decorator