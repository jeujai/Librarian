"""
Integration utilities for comprehensive metrics collection.

This module provides decorators and utilities to easily integrate comprehensive
metrics collection into existing services and functions.
"""

import time
import functools
from typing import Callable, Any, Optional, Dict
from datetime import datetime
import asyncio
import inspect

from .comprehensive_metrics_collector import ComprehensiveMetricsCollector
from ..logging_config import get_logger

logger = get_logger("metrics_integration")

# Global metrics collector instance
_metrics_collector: Optional[ComprehensiveMetricsCollector] = None


def initialize_metrics_integration(metrics_collector: ComprehensiveMetricsCollector) -> None:
    """Initialize the global metrics collector for integration utilities."""
    global _metrics_collector
    _metrics_collector = metrics_collector
    logger.info("Metrics integration initialized")


def get_metrics_collector() -> ComprehensiveMetricsCollector:
    """Get the global metrics collector instance."""
    if _metrics_collector is None:
        raise RuntimeError("Metrics integration not initialized. Call initialize_metrics_integration() first.")
    return _metrics_collector


def track_response_time(endpoint: str, method: str = "FUNCTION"):
    """
    Decorator to track response time for functions.
    
    Args:
        endpoint: Endpoint or function name to track
        method: HTTP method or operation type
    
    Usage:
        @track_response_time("/api/search", "POST")
        async def search_documents(query: str):
            # Function implementation
            pass
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            start_time = time.time()
            status_code = 200
            
            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                status_code = 500
                logger.error(f"Error in {endpoint}: {e}")
                raise
            finally:
                response_time_ms = (time.time() - start_time) * 1000
                
                try:
                    collector = get_metrics_collector()
                    collector.record_response_time(
                        endpoint=endpoint,
                        method=method,
                        response_time_ms=response_time_ms,
                        status_code=status_code
                    )
                except Exception as e:
                    logger.warning(f"Failed to record response time metric: {e}")
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs) -> Any:
            start_time = time.time()
            status_code = 200
            
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                status_code = 500
                logger.error(f"Error in {endpoint}: {e}")
                raise
            finally:
                response_time_ms = (time.time() - start_time) * 1000
                
                try:
                    collector = get_metrics_collector()
                    collector.record_response_time(
                        endpoint=endpoint,
                        method=method,
                        response_time_ms=response_time_ms,
                        status_code=status_code
                    )
                except Exception as e:
                    logger.warning(f"Failed to record response time metric: {e}")
        
        # Return appropriate wrapper based on function type
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


def track_search_performance(search_type: str = "unknown"):
    """
    Decorator to track search performance metrics.
    
    Args:
        search_type: Type of search (vector, hybrid, simple)
    
    Usage:
        @track_search_performance("vector")
        async def vector_search(query: str) -> SearchResults:
            # Search implementation
            pass
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            start_time = time.time()
            query_text = ""
            results_count = 0
            cache_hit = False
            
            try:
                # Try to extract query from arguments
                if args:
                    # Assume first argument might be query
                    if isinstance(args[0], str):
                        query_text = args[0][:100]  # Truncate for privacy
                
                # Check kwargs for query
                if "query" in kwargs:
                    query_text = str(kwargs["query"])[:100]
                elif "query_text" in kwargs:
                    query_text = str(kwargs["query_text"])[:100]
                
                result = await func(*args, **kwargs)
                
                # Try to extract results information
                if hasattr(result, 'results') and hasattr(result.results, '__len__'):
                    results_count = len(result.results)
                elif isinstance(result, dict):
                    if 'results' in result:
                        results_count = len(result['results']) if hasattr(result['results'], '__len__') else 0
                    if 'cache_hit' in result:
                        cache_hit = bool(result['cache_hit'])
                elif hasattr(result, '__len__') and not isinstance(result, str):
                    results_count = len(result)
                
                return result
                
            except Exception as e:
                logger.error(f"Error in search function: {e}")
                raise
            finally:
                response_time_ms = (time.time() - start_time) * 1000
                
                try:
                    collector = get_metrics_collector()
                    collector.record_search_performance(
                        query_text=query_text,
                        search_type=search_type,
                        response_time_ms=response_time_ms,
                        results_count=results_count,
                        cache_hit=cache_hit
                    )
                except Exception as e:
                    logger.warning(f"Failed to record search performance metric: {e}")
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs) -> Any:
            start_time = time.time()
            query_text = ""
            results_count = 0
            cache_hit = False
            
            try:
                # Try to extract query from arguments
                if args:
                    if isinstance(args[0], str):
                        query_text = args[0][:100]
                
                if "query" in kwargs:
                    query_text = str(kwargs["query"])[:100]
                elif "query_text" in kwargs:
                    query_text = str(kwargs["query_text"])[:100]
                
                result = func(*args, **kwargs)
                
                # Try to extract results information
                if hasattr(result, 'results') and hasattr(result.results, '__len__'):
                    results_count = len(result.results)
                elif isinstance(result, dict):
                    if 'results' in result:
                        results_count = len(result['results']) if hasattr(result['results'], '__len__') else 0
                    if 'cache_hit' in result:
                        cache_hit = bool(result['cache_hit'])
                elif hasattr(result, '__len__') and not isinstance(result, str):
                    results_count = len(result)
                
                return result
                
            except Exception as e:
                logger.error(f"Error in search function: {e}")
                raise
            finally:
                response_time_ms = (time.time() - start_time) * 1000
                
                try:
                    collector = get_metrics_collector()
                    collector.record_search_performance(
                        query_text=query_text,
                        search_type=search_type,
                        response_time_ms=response_time_ms,
                        results_count=results_count,
                        cache_hit=cache_hit
                    )
                except Exception as e:
                    logger.warning(f"Failed to record search performance metric: {e}")
        
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


def track_document_processing(processing_stage: str):
    """
    Decorator to track document processing metrics.
    
    Args:
        processing_stage: Stage of processing (upload, extract, chunk, embed, index)
    
    Usage:
        @track_document_processing("extract")
        async def extract_text(document_id: str) -> str:
            # Processing implementation
            pass
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            start_time = time.time()
            document_id = "unknown"
            document_size_mb = 0.0
            success = True
            error_message = None
            
            try:
                # Try to extract document ID from arguments
                if args:
                    if isinstance(args[0], str):
                        document_id = args[0]
                    # Check if second argument is document size
                    if len(args) > 1 and isinstance(args[1], (int, float)):
                        document_size_mb = float(args[1])
                
                if "document_id" in kwargs:
                    document_id = str(kwargs["document_id"])
                elif "doc_id" in kwargs:
                    document_id = str(kwargs["doc_id"])
                
                # Try to extract document size
                if "document_size_mb" in kwargs:
                    document_size_mb = float(kwargs["document_size_mb"])
                elif "size_mb" in kwargs:
                    document_size_mb = float(kwargs["size_mb"])
                
                result = await func(*args, **kwargs)
                return result
                
            except Exception as e:
                success = False
                error_message = str(e)
                logger.error(f"Error in document processing {processing_stage}: {e}")
                raise
            finally:
                processing_time_ms = (time.time() - start_time) * 1000
                
                try:
                    collector = get_metrics_collector()
                    collector.record_document_processing(
                        document_id=document_id,
                        document_size_mb=document_size_mb,
                        processing_time_ms=processing_time_ms,
                        processing_stage=processing_stage,
                        success=success,
                        error_message=error_message
                    )
                except Exception as e:
                    logger.warning(f"Failed to record document processing metric: {e}")
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs) -> Any:
            start_time = time.time()
            document_id = "unknown"
            document_size_mb = 0.0
            success = True
            error_message = None
            
            try:
                # Try to extract document ID from arguments
                if args:
                    if isinstance(args[0], str):
                        document_id = args[0]
                    # Check if second argument is document size
                    if len(args) > 1 and isinstance(args[1], (int, float)):
                        document_size_mb = float(args[1])
                
                if "document_id" in kwargs:
                    document_id = str(kwargs["document_id"])
                elif "doc_id" in kwargs:
                    document_id = str(kwargs["doc_id"])
                
                # Try to extract document size
                if "document_size_mb" in kwargs:
                    document_size_mb = float(kwargs["document_size_mb"])
                elif "size_mb" in kwargs:
                    document_size_mb = float(kwargs["size_mb"])
                
                result = func(*args, **kwargs)
                return result
                
            except Exception as e:
                success = False
                error_message = str(e)
                logger.error(f"Error in document processing {processing_stage}: {e}")
                raise
            finally:
                processing_time_ms = (time.time() - start_time) * 1000
                
                try:
                    collector = get_metrics_collector()
                    collector.record_document_processing(
                        document_id=document_id,
                        document_size_mb=document_size_mb,
                        processing_time_ms=processing_time_ms,
                        processing_stage=processing_stage,
                        success=success,
                        error_message=error_message
                    )
                except Exception as e:
                    logger.warning(f"Failed to record document processing metric: {e}")
        
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


class MetricsContext:
    """
    Context manager for manual metrics collection.
    
    Usage:
        async with MetricsContext("custom_operation") as ctx:
            # Perform operation
            result = await some_operation()
            ctx.set_result_info(count=len(result))
    """
    
    def __init__(self, operation_name: str, operation_type: str = "custom"):
        self.operation_name = operation_name
        self.operation_type = operation_type
        self.start_time = None
        self.result_info = {}
    
    async def __aenter__(self):
        self.start_time = time.time()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.start_time is None:
            return
        
        response_time_ms = (time.time() - self.start_time) * 1000
        status_code = 500 if exc_type else 200
        
        try:
            collector = get_metrics_collector()
            collector.record_response_time(
                endpoint=self.operation_name,
                method=self.operation_type,
                response_time_ms=response_time_ms,
                status_code=status_code
            )
        except Exception as e:
            logger.warning(f"Failed to record metrics in context: {e}")
    
    def set_result_info(self, **kwargs):
        """Set additional result information for metrics."""
        self.result_info.update(kwargs)


def record_cache_hit():
    """Record a cache hit event."""
    try:
        collector = get_metrics_collector()
        collector.record_cache_event("hit")
    except Exception as e:
        logger.warning(f"Failed to record cache hit: {e}")


def record_cache_miss():
    """Record a cache miss event."""
    try:
        collector = get_metrics_collector()
        collector.record_cache_event("miss")
    except Exception as e:
        logger.warning(f"Failed to record cache miss: {e}")


def record_cache_eviction():
    """Record a cache eviction event."""
    try:
        collector = get_metrics_collector()
        collector.record_cache_event("eviction")
    except Exception as e:
        logger.warning(f"Failed to record cache eviction: {e}")


def update_cache_size(size_bytes: int):
    """Update cache size metrics."""
    try:
        collector = get_metrics_collector()
        collector.record_cache_event("size_update", size_bytes)
    except Exception as e:
        logger.warning(f"Failed to update cache size: {e}")


class SearchMetricsHelper:
    """Helper class for manual search metrics collection."""
    
    @staticmethod
    def record_search(query: str, search_type: str, response_time_ms: float,
                     results_count: int, cache_hit: bool = False,
                     user_id: Optional[str] = None) -> None:
        """
        Manually record search performance metrics.
        
        Args:
            query: Search query text
            search_type: Type of search performed
            response_time_ms: Response time in milliseconds
            results_count: Number of results returned
            cache_hit: Whether result was from cache
            user_id: Optional user identifier
        """
        try:
            collector = get_metrics_collector()
            collector.record_search_performance(
                query_text=query,
                search_type=search_type,
                response_time_ms=response_time_ms,
                results_count=results_count,
                cache_hit=cache_hit,
                user_id=user_id
            )
        except Exception as e:
            logger.warning(f"Failed to record search metrics: {e}")


class DocumentMetricsHelper:
    """Helper class for manual document processing metrics collection."""
    
    @staticmethod
    def record_processing(document_id: str, document_size_mb: float,
                         processing_time_ms: float, processing_stage: str,
                         success: bool, error_message: Optional[str] = None) -> None:
        """
        Manually record document processing metrics.
        
        Args:
            document_id: Unique document identifier
            document_size_mb: Document size in megabytes
            processing_time_ms: Processing time in milliseconds
            processing_stage: Stage of processing
            success: Whether processing was successful
            error_message: Optional error message
        """
        try:
            collector = get_metrics_collector()
            collector.record_document_processing(
                document_id=document_id,
                document_size_mb=document_size_mb,
                processing_time_ms=processing_time_ms,
                processing_stage=processing_stage,
                success=success,
                error_message=error_message
            )
        except Exception as e:
            logger.warning(f"Failed to record document processing metrics: {e}")


# Convenience functions for common operations
def get_real_time_metrics() -> Dict[str, Any]:
    """Get real-time metrics from the collector."""
    try:
        collector = get_metrics_collector()
        return collector.get_real_time_metrics()
    except Exception as e:
        logger.error(f"Failed to get real-time metrics: {e}")
        return {"error": str(e)}


def get_performance_trends(hours: int = 24) -> Dict[str, Any]:
    """Get performance trends from the collector."""
    try:
        collector = get_metrics_collector()
        return collector.get_performance_trends(hours)
    except Exception as e:
        logger.error(f"Failed to get performance trends: {e}")
        return {"error": str(e)}


def get_user_session_analytics() -> Dict[str, Any]:
    """Get user session analytics from the collector."""
    try:
        collector = get_metrics_collector()
        return collector.get_user_session_analytics()
    except Exception as e:
        logger.error(f"Failed to get user session analytics: {e}")
        return {"error": str(e)}