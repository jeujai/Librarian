"""
Query Performance Monitoring Decorators

This module provides decorators and integration utilities to automatically
track query performance in database clients without modifying their core logic.

The decorators integrate with the QueryPerformanceMonitor to provide seamless
performance tracking across all database operations.

Example Usage:
    ```python
    from multimodal_librarian.monitoring.query_performance_decorators import track_query_performance
    
    class MyDatabaseClient:
        @track_query_performance("postgresql")
        async def execute_query(self, query: str, parameters=None):
            # Original method implementation
            return await self._execute_raw_query(query, parameters)
    ```

Integration with Database Clients:
    The decorators automatically detect query types, track execution times,
    monitor resource usage, and integrate with the global performance monitor.
"""

import asyncio
import functools
import logging
from typing import Any, Callable, Optional, Dict, Union, TypeVar, ParamSpec
from datetime import datetime

from .query_performance_monitor import (
    QueryPerformanceMonitor, get_global_monitor, DatabaseType, QueryType
)

logger = logging.getLogger(__name__)

# Type variables for generic decorator support
P = ParamSpec('P')
T = TypeVar('T')


def track_query_performance(
    database_type: str,
    query_param: str = "query",
    parameters_param: str = "parameters",
    client_id_param: Optional[str] = None,
    extract_query_type: bool = True,
    monitor: Optional[QueryPerformanceMonitor] = None
):
    """
    Decorator to automatically track query performance.
    
    This decorator wraps database client methods to automatically track
    query execution performance using the QueryPerformanceMonitor.
    
    Args:
        database_type: Type of database (postgresql, neo4j, milvus)
        query_param: Name of the query parameter in the method signature
        parameters_param: Name of the parameters parameter in the method signature
        client_id_param: Name of the client ID parameter (optional)
        extract_query_type: Whether to automatically extract query type from query text
        monitor: Specific monitor instance to use (uses global if None)
    
    Returns:
        Decorated function that tracks query performance
    
    Example:
        ```python
        class PostgreSQLClient:
            @track_query_performance("postgresql")
            async def execute_query(self, query: str, parameters=None):
                # Method implementation
                pass
            
            @track_query_performance("postgresql", query_param="command")
            async def execute_command(self, command: str, parameters=None):
                # Method implementation
                pass
        ```
    """
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(func)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            # Get the monitor instance
            perf_monitor = monitor or get_global_monitor()
            if not perf_monitor or not perf_monitor.is_monitoring:
                # No monitoring active, call original function
                return await func(*args, **kwargs)
            
            # Extract query information from arguments
            query_info = _extract_query_info(
                func, args, kwargs,
                query_param, parameters_param, client_id_param
            )
            
            if not query_info["query"]:
                # No query found, call original function without tracking
                return await func(*args, **kwargs)
            
            # Determine query type
            query_type = None
            if extract_query_type:
                query_type = _extract_query_type_from_text(query_info["query"])
            
            # Track the query performance
            async with perf_monitor.track_query(
                database_type=database_type,
                query_text=query_info["query"],
                query_type=query_type,
                client_id=query_info.get("client_id"),
                session_id=_get_session_id_from_context()
            ) as tracker:
                try:
                    # Execute the original function
                    result = await func(*args, **kwargs)
                    
                    # Try to extract result count if possible
                    result_count = _extract_result_count(result)
                    if result_count is not None:
                        tracker.set_result_count(result_count)
                    
                    # Try to extract additional metadata
                    _extract_query_metadata(tracker, query_info["query"], result)
                    
                    return result
                    
                except Exception as e:
                    # Exception will be recorded by the tracker
                    raise
        
        @functools.wraps(func)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            # For synchronous functions, we can't use async tracking
            # Just call the original function
            logger.debug(f"Sync function {func.__name__} called - performance tracking not available")
            return func(*args, **kwargs)
        
        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


def track_vector_operation(
    operation_type: str = "vector_search",
    collection_param: str = "collection_name",
    query_param: str = "query_vector",
    monitor: Optional[QueryPerformanceMonitor] = None
):
    """
    Decorator specifically for vector database operations.
    
    This decorator is optimized for tracking vector database operations
    like similarity search, vector insertion, and collection management.
    
    Args:
        operation_type: Type of vector operation (vector_search, vector_insert, etc.)
        collection_param: Name of the collection parameter
        query_param: Name of the query/vector parameter
        monitor: Specific monitor instance to use (uses global if None)
    
    Returns:
        Decorated function that tracks vector operation performance
    
    Example:
        ```python
        class MilvusClient:
            @track_vector_operation("vector_search")
            async def search_vectors(self, collection_name: str, query_vector: list, k: int = 10):
                # Method implementation
                pass
            
            @track_vector_operation("vector_insert", query_param="vectors")
            async def insert_vectors(self, collection_name: str, vectors: list):
                # Method implementation
                pass
        ```
    """
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(func)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            # Get the monitor instance
            perf_monitor = monitor or get_global_monitor()
            if not perf_monitor or not perf_monitor.is_monitoring:
                # No monitoring active, call original function
                return await func(*args, **kwargs)
            
            # Extract operation information
            operation_info = _extract_vector_operation_info(
                func, args, kwargs,
                collection_param, query_param
            )
            
            # Create query text for tracking
            query_text = f"{operation_type.upper()}"
            if operation_info.get("collection"):
                query_text += f" ON {operation_info['collection']}"
            
            # Track the vector operation
            async with perf_monitor.track_query(
                database_type="milvus",
                query_text=query_text,
                query_type="VECTOR_SEARCH" if "search" in operation_type else "INSERT",
                session_id=_get_session_id_from_context()
            ) as tracker:
                try:
                    # Set operation-specific metadata
                    tracker.add_metadata("operation_type", operation_type)
                    if operation_info.get("collection"):
                        tracker.add_metadata("collection_name", operation_info["collection"])
                    
                    # Execute the original function
                    result = await func(*args, **kwargs)
                    
                    # Extract result information
                    if isinstance(result, list):
                        tracker.set_result_count(len(result))
                    elif isinstance(result, dict) and "results" in result:
                        tracker.set_result_count(len(result["results"]))
                    
                    # Set complexity based on operation
                    if "search" in operation_type:
                        tracker.set_query_complexity("medium")
                    elif "insert" in operation_type and isinstance(result, list) and len(result) > 100:
                        tracker.set_query_complexity("complex")
                    
                    return result
                    
                except Exception as e:
                    # Exception will be recorded by the tracker
                    raise
        
        # Return wrapper (vector operations are typically async)
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            # Fallback for sync functions
            return func
    
    return decorator


def track_graph_operation(
    query_param: str = "query",
    parameters_param: str = "parameters",
    monitor: Optional[QueryPerformanceMonitor] = None
):
    """
    Decorator specifically for graph database operations.
    
    This decorator is optimized for tracking Neo4j/graph database operations
    with Cypher queries and graph-specific metadata.
    
    Args:
        query_param: Name of the Cypher query parameter
        parameters_param: Name of the query parameters parameter
        monitor: Specific monitor instance to use (uses global if None)
    
    Returns:
        Decorated function that tracks graph operation performance
    
    Example:
        ```python
        class Neo4jClient:
            @track_graph_operation()
            async def execute_query(self, query: str, parameters=None):
                # Method implementation
                pass
            
            @track_graph_operation(query_param="cypher_query")
            async def run_cypher(self, cypher_query: str, params=None):
                # Method implementation
                pass
        ```
    """
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(func)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            # Get the monitor instance
            perf_monitor = monitor or get_global_monitor()
            if not perf_monitor or not perf_monitor.is_monitoring:
                # No monitoring active, call original function
                return await func(*args, **kwargs)
            
            # Extract query information
            query_info = _extract_query_info(
                func, args, kwargs,
                query_param, parameters_param, None
            )
            
            if not query_info["query"]:
                # No query found, call original function without tracking
                return await func(*args, **kwargs)
            
            # Track the graph query
            async with perf_monitor.track_query(
                database_type="neo4j",
                query_text=query_info["query"],
                query_type="GRAPH_QUERY",
                session_id=_get_session_id_from_context()
            ) as tracker:
                try:
                    # Analyze Cypher query for metadata
                    _analyze_cypher_query(tracker, query_info["query"])
                    
                    # Execute the original function
                    result = await func(*args, **kwargs)
                    
                    # Extract result information
                    result_count = _extract_result_count(result)
                    if result_count is not None:
                        tracker.set_result_count(result_count)
                    
                    return result
                    
                except Exception as e:
                    # Exception will be recorded by the tracker
                    raise
        
        # Return wrapper
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return func
    
    return decorator


def _extract_query_info(
    func: Callable,
    args: tuple,
    kwargs: dict,
    query_param: str,
    parameters_param: str,
    client_id_param: Optional[str]
) -> Dict[str, Any]:
    """Extract query information from function arguments."""
    import inspect
    
    # Get function signature
    sig = inspect.signature(func)
    bound_args = sig.bind(*args, **kwargs)
    bound_args.apply_defaults()
    
    query_info = {}
    
    # Extract query
    if query_param in bound_args.arguments:
        query_info["query"] = bound_args.arguments[query_param]
    else:
        query_info["query"] = None
    
    # Extract parameters
    if parameters_param in bound_args.arguments:
        query_info["parameters"] = bound_args.arguments[parameters_param]
    else:
        query_info["parameters"] = None
    
    # Extract client ID if specified
    if client_id_param and client_id_param in bound_args.arguments:
        query_info["client_id"] = bound_args.arguments[client_id_param]
    
    return query_info


def _extract_vector_operation_info(
    func: Callable,
    args: tuple,
    kwargs: dict,
    collection_param: str,
    query_param: str
) -> Dict[str, Any]:
    """Extract vector operation information from function arguments."""
    import inspect
    
    # Get function signature
    sig = inspect.signature(func)
    bound_args = sig.bind(*args, **kwargs)
    bound_args.apply_defaults()
    
    operation_info = {}
    
    # Extract collection name
    if collection_param in bound_args.arguments:
        operation_info["collection"] = bound_args.arguments[collection_param]
    
    # Extract query/vector information
    if query_param in bound_args.arguments:
        query_data = bound_args.arguments[query_param]
        if isinstance(query_data, list):
            operation_info["vector_count"] = len(query_data)
        operation_info["query_data"] = query_data
    
    return operation_info


def _extract_query_type_from_text(query_text: str) -> Optional[str]:
    """Extract query type from query text."""
    if not query_text:
        return None
    
    query_upper = query_text.strip().upper()
    
    if query_upper.startswith('SELECT'):
        return "SELECT"
    elif query_upper.startswith('INSERT'):
        return "INSERT"
    elif query_upper.startswith('UPDATE'):
        return "UPDATE"
    elif query_upper.startswith('DELETE'):
        return "DELETE"
    elif query_upper.startswith('CREATE'):
        return "CREATE"
    elif query_upper.startswith('DROP'):
        return "DROP"
    elif query_upper.startswith('ALTER'):
        return "ALTER"
    elif 'MATCH' in query_upper or 'RETURN' in query_upper:
        return "GRAPH_QUERY"
    elif 'search' in query_upper.lower() or 'vector' in query_upper.lower():
        return "VECTOR_SEARCH"
    
    return None


def _extract_result_count(result: Any) -> Optional[int]:
    """Extract result count from query result."""
    if result is None:
        return 0
    elif isinstance(result, list):
        return len(result)
    elif isinstance(result, dict):
        if "results" in result and isinstance(result["results"], list):
            return len(result["results"])
        elif "data" in result and isinstance(result["data"], list):
            return len(result["data"])
        elif "rows" in result and isinstance(result["rows"], list):
            return len(result["rows"])
    elif isinstance(result, int):
        # Probably an affected row count
        return result
    
    return None


def _extract_query_metadata(tracker, query_text: str, result: Any) -> None:
    """Extract additional metadata from query and result."""
    if not query_text:
        return
    
    query_upper = query_text.upper()
    
    # Analyze query complexity
    complexity = "simple"
    if any(keyword in query_upper for keyword in ["JOIN", "SUBQUERY", "UNION", "GROUP BY", "ORDER BY"]):
        complexity = "medium"
    if any(keyword in query_upper for keyword in ["RECURSIVE", "WINDOW", "CTE", "PARTITION"]):
        complexity = "complex"
    
    tracker.set_query_complexity(complexity)
    
    # Check for potential index usage
    if "WHERE" in query_upper:
        tracker.set_uses_index(True)  # Assume indexed if WHERE clause present
    
    # Count potential table scans
    table_scan_indicators = query_upper.count("SELECT") + query_upper.count("FROM")
    tracker.set_table_scans(max(1, table_scan_indicators))


def _analyze_cypher_query(tracker, query_text: str) -> None:
    """Analyze Cypher query for graph-specific metadata."""
    if not query_text:
        return
    
    query_upper = query_text.upper()
    
    # Analyze query complexity for Cypher
    complexity = "simple"
    if any(keyword in query_upper for keyword in ["OPTIONAL MATCH", "WITH", "UNWIND", "COLLECT"]):
        complexity = "medium"
    if any(keyword in query_upper for keyword in ["CALL", "FOREACH", "CASE", "REDUCE"]):
        complexity = "complex"
    
    tracker.set_query_complexity(complexity)
    
    # Check for index usage (WHERE clauses on properties)
    if "WHERE" in query_upper and ("." in query_text):
        tracker.set_uses_index(True)
    
    # Count MATCH clauses as "table scans"
    match_count = query_upper.count("MATCH")
    tracker.set_table_scans(match_count)
    
    # Add Cypher-specific metadata
    tracker.add_metadata("cypher_query", True)
    tracker.add_metadata("match_clauses", match_count)
    
    if "CREATE" in query_upper:
        tracker.add_metadata("creates_nodes", True)
    if "DELETE" in query_upper:
        tracker.add_metadata("deletes_nodes", True)
    if "SET" in query_upper:
        tracker.add_metadata("updates_properties", True)


def _get_session_id_from_context() -> Optional[str]:
    """Get session ID from current context (if available)."""
    try:
        # Try to get from asyncio context
        import contextvars
        
        # This would need to be set up in the application context
        # For now, return None
        return None
    except:
        return None


class QueryPerformanceIntegration:
    """
    Integration helper for adding query performance monitoring to existing clients.
    
    This class provides utilities to integrate performance monitoring into
    existing database clients without modifying their source code.
    """
    
    def __init__(self, monitor: Optional[QueryPerformanceMonitor] = None):
        """
        Initialize the integration helper.
        
        Args:
            monitor: Specific monitor instance to use (uses global if None)
        """
        self.monitor = monitor or get_global_monitor()
    
    def wrap_client_methods(
        self,
        client_instance: Any,
        database_type: str,
        method_mappings: Optional[Dict[str, Dict[str, str]]] = None
    ) -> Any:
        """
        Wrap database client methods with performance monitoring.
        
        This method dynamically wraps methods of an existing client instance
        to add performance monitoring without modifying the original class.
        
        Args:
            client_instance: The database client instance to wrap
            database_type: Type of database (postgresql, neo4j, milvus)
            method_mappings: Optional mapping of method names to parameter names
                           Format: {"method_name": {"query_param": "query", "parameters_param": "params"}}
        
        Returns:
            The wrapped client instance
        
        Example:
            ```python
            integration = QueryPerformanceIntegration()
            wrapped_client = integration.wrap_client_methods(
                my_postgres_client,
                "postgresql",
                {
                    "execute_query": {"query_param": "query", "parameters_param": "parameters"},
                    "execute_command": {"query_param": "command", "parameters_param": "params"}
                }
            )
            ```
        """
        if not self.monitor or not self.monitor.is_monitoring:
            logger.warning("No active performance monitor - returning unwrapped client")
            return client_instance
        
        # Default method mappings
        default_mappings = {
            "execute_query": {"query_param": "query", "parameters_param": "parameters"},
            "execute_command": {"query_param": "command", "parameters_param": "parameters"},
            "search_vectors": {"query_param": "query_vector", "parameters_param": None},
            "insert_vectors": {"query_param": "vectors", "parameters_param": None},
            "semantic_search": {"query_param": "query", "parameters_param": "filters"}
        }
        
        # Use provided mappings or defaults
        mappings = method_mappings or default_mappings
        
        # Wrap each specified method
        for method_name, params in mappings.items():
            if hasattr(client_instance, method_name):
                original_method = getattr(client_instance, method_name)
                
                # Create appropriate decorator
                if database_type.lower() == "milvus" and "vector" in method_name:
                    decorator = track_vector_operation(
                        operation_type=method_name,
                        collection_param="collection_name",
                        query_param=params.get("query_param", "query_vector"),
                        monitor=self.monitor
                    )
                elif database_type.lower() == "neo4j":
                    decorator = track_graph_operation(
                        query_param=params.get("query_param", "query"),
                        parameters_param=params.get("parameters_param", "parameters"),
                        monitor=self.monitor
                    )
                else:
                    decorator = track_query_performance(
                        database_type=database_type,
                        query_param=params.get("query_param", "query"),
                        parameters_param=params.get("parameters_param", "parameters"),
                        monitor=self.monitor
                    )
                
                # Apply decorator and replace method
                wrapped_method = decorator(original_method)
                setattr(client_instance, method_name, wrapped_method)
                
                logger.debug(f"Wrapped method {method_name} for {database_type} client")
        
        return client_instance
    
    def create_monitoring_middleware(self, database_type: str):
        """
        Create middleware function for query monitoring.
        
        This creates a middleware function that can be used in frameworks
        or custom client implementations to add monitoring.
        
        Args:
            database_type: Type of database (postgresql, neo4j, milvus)
        
        Returns:
            Middleware function for query monitoring
        
        Example:
            ```python
            integration = QueryPerformanceIntegration()
            middleware = integration.create_monitoring_middleware("postgresql")
            
            async def my_query_executor(query, params):
                async with middleware(query, params) as tracker:
                    result = await execute_raw_query(query, params)
                    tracker.set_result_count(len(result))
                    return result
            ```
        """
        if not self.monitor or not self.monitor.is_monitoring:
            # Return no-op middleware
            @asyncio.contextmanager
            async def noop_middleware(query, params=None):
                yield None
            return noop_middleware
        
        @asyncio.contextmanager
        async def monitoring_middleware(query: str, params=None, **kwargs):
            query_type = _extract_query_type_from_text(query)
            
            async with self.monitor.track_query(
                database_type=database_type,
                query_text=query,
                query_type=query_type,
                **kwargs
            ) as tracker:
                yield tracker
        
        return monitoring_middleware


# Convenience functions for common use cases

def enable_postgresql_monitoring(client_instance, monitor: Optional[QueryPerformanceMonitor] = None):
    """Enable performance monitoring for a PostgreSQL client."""
    integration = QueryPerformanceIntegration(monitor)
    return integration.wrap_client_methods(client_instance, "postgresql")


def enable_neo4j_monitoring(client_instance, monitor: Optional[QueryPerformanceMonitor] = None):
    """Enable performance monitoring for a Neo4j client."""
    integration = QueryPerformanceIntegration(monitor)
    return integration.wrap_client_methods(client_instance, "neo4j")


def enable_milvus_monitoring(client_instance, monitor: Optional[QueryPerformanceMonitor] = None):
    """Enable performance monitoring for a Milvus client."""
    integration = QueryPerformanceIntegration(monitor)
    return integration.wrap_client_methods(client_instance, "milvus")