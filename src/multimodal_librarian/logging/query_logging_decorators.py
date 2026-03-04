"""
Query Logging Decorators and Middleware

This module provides decorators and middleware to automatically capture database
query logs from all database clients without modifying the client code directly.
It integrates with the DatabaseQueryLogger to provide seamless query monitoring.

Features:
- Automatic query logging for all database operations
- Performance metrics capture during query execution
- Error handling and logging
- Configurable logging levels per client
- Integration with existing database clients

Example Usage:
    ```python
    from multimodal_librarian.logging.query_logging_decorators import log_database_queries
    
    # Decorate database client methods
    @log_database_queries(database_type="postgresql")
    class PostgreSQLClient:
        async def execute_query(self, query: str, parameters=None):
            # Original method implementation
            pass
    
    # Or use as method decorator
    class Neo4jClient:
        @log_query_execution("neo4j")
        async def execute_query(self, query: str, parameters=None):
            # Original method implementation
            pass
    ```
"""

import asyncio
import functools
import inspect
import time
import psutil
from typing import Any, Callable, Dict, Optional, TypeVar, Union
from datetime import datetime

from .database_query_logger import get_database_query_logger, DatabaseQueryLogger
from ..logging_config import get_logger

logger = get_logger(__name__)

F = TypeVar('F', bound=Callable[..., Any])


class QueryExecutionContext:
    """Context for tracking query execution metrics."""
    
    def __init__(self, database_type: str, method_name: str):
        self.database_type = database_type
        self.method_name = method_name
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.start_cpu: Optional[float] = None
        self.end_cpu: Optional[float] = None
        self.start_memory: Optional[float] = None
        self.end_memory: Optional[float] = None
        self.query_logger = get_database_query_logger()
    
    async def __aenter__(self):
        """Start tracking query execution."""
        self.start_time = time.time()
        
        # Capture initial resource usage
        try:
            process = psutil.Process()
            self.start_cpu = process.cpu_percent()
            self.start_memory = process.memory_info().rss / 1024 / 1024  # MB
        except Exception as e:
            logger.debug(f"Failed to capture start resource usage: {e}")
        
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Finish tracking query execution."""
        self.end_time = time.time()
        
        # Capture final resource usage
        try:
            process = psutil.Process()
            self.end_cpu = process.cpu_percent()
            self.end_memory = process.memory_info().rss / 1024 / 1024  # MB
        except Exception as e:
            logger.debug(f"Failed to capture end resource usage: {e}")
    
    def get_execution_time_ms(self) -> float:
        """Get execution time in milliseconds."""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time) * 1000
        return 0.0
    
    def get_cpu_usage_delta(self) -> Optional[float]:
        """Get CPU usage delta during execution."""
        if self.start_cpu is not None and self.end_cpu is not None:
            return self.end_cpu - self.start_cpu
        return None
    
    def get_memory_usage_delta(self) -> Optional[float]:
        """Get memory usage delta during execution."""
        if self.start_memory is not None and self.end_memory is not None:
            return self.end_memory - self.start_memory
        return None


def log_query_execution(
    database_type: str,
    extract_query: Optional[Callable] = None,
    extract_parameters: Optional[Callable] = None,
    extract_result_count: Optional[Callable] = None,
    extract_affected_rows: Optional[Callable] = None,
    method_name_override: Optional[str] = None
) -> Callable[[F], F]:
    """
    Decorator to automatically log database query execution.
    
    Args:
        database_type: Type of database (postgresql, neo4j, milvus)
        extract_query: Function to extract query text from method arguments
        extract_parameters: Function to extract query parameters from method arguments
        extract_result_count: Function to extract result count from method result
        extract_affected_rows: Function to extract affected rows from method result
        method_name_override: Override for method name in logs
        
    Returns:
        Decorated function with automatic query logging
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            method_name = method_name_override or func.__name__
            
            # Extract query information
            query_text = ""
            parameters = {}
            
            if extract_query:
                try:
                    query_text = extract_query(*args, **kwargs)
                except Exception as e:
                    logger.debug(f"Failed to extract query text: {e}")
                    query_text = f"<{method_name}>"
            else:
                # Default extraction logic
                query_text = _default_extract_query(*args, **kwargs)
            
            if extract_parameters:
                try:
                    parameters = extract_parameters(*args, **kwargs)
                except Exception as e:
                    logger.debug(f"Failed to extract parameters: {e}")
            else:
                # Default parameter extraction
                parameters = _default_extract_parameters(*args, **kwargs)
            
            # Track execution
            async with QueryExecutionContext(database_type, method_name) as context:
                try:
                    # Execute the original method
                    result = await func(*args, **kwargs)
                    
                    # Extract result information
                    result_count = None
                    affected_rows = None
                    
                    if extract_result_count:
                        try:
                            result_count = extract_result_count(result)
                        except Exception as e:
                            logger.debug(f"Failed to extract result count: {e}")
                    else:
                        result_count = _default_extract_result_count(result)
                    
                    if extract_affected_rows:
                        try:
                            affected_rows = extract_affected_rows(result)
                        except Exception as e:
                            logger.debug(f"Failed to extract affected rows: {e}")
                    else:
                        affected_rows = _default_extract_affected_rows(result)
                    
                    # Log successful query
                    await context.query_logger.log_query(
                        database_type=database_type,
                        query=query_text,
                        execution_time_ms=context.get_execution_time_ms(),
                        parameters=parameters,
                        result_count=result_count,
                        affected_rows=affected_rows,
                        cpu_usage_percent=context.get_cpu_usage_delta(),
                        memory_usage_mb=context.get_memory_usage_delta(),
                        method_name=method_name
                    )
                    
                    return result
                    
                except Exception as e:
                    # Log failed query
                    await context.query_logger.log_query(
                        database_type=database_type,
                        query=query_text,
                        execution_time_ms=context.get_execution_time_ms(),
                        parameters=parameters,
                        error_message=str(e),
                        cpu_usage_percent=context.get_cpu_usage_delta(),
                        memory_usage_mb=context.get_memory_usage_delta(),
                        method_name=method_name
                    )
                    
                    # Re-raise the exception
                    raise
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            # For synchronous methods, we need to handle differently
            method_name = method_name_override or func.__name__
            
            # Extract query information
            query_text = ""
            parameters = {}
            
            if extract_query:
                try:
                    query_text = extract_query(*args, **kwargs)
                except Exception as e:
                    logger.debug(f"Failed to extract query text: {e}")
                    query_text = f"<{method_name}>"
            else:
                query_text = _default_extract_query(*args, **kwargs)
            
            if extract_parameters:
                try:
                    parameters = extract_parameters(*args, **kwargs)
                except Exception as e:
                    logger.debug(f"Failed to extract parameters: {e}")
            else:
                parameters = _default_extract_parameters(*args, **kwargs)
            
            # Track execution time
            start_time = time.time()
            start_cpu = None
            start_memory = None
            
            try:
                process = psutil.Process()
                start_cpu = process.cpu_percent()
                start_memory = process.memory_info().rss / 1024 / 1024  # MB
            except Exception:
                pass
            
            try:
                # Execute the original method
                result = func(*args, **kwargs)
                
                # Calculate execution time
                execution_time_ms = (time.time() - start_time) * 1000
                
                # Calculate resource usage
                cpu_delta = None
                memory_delta = None
                
                try:
                    process = psutil.Process()
                    if start_cpu is not None:
                        cpu_delta = process.cpu_percent() - start_cpu
                    if start_memory is not None:
                        memory_delta = (process.memory_info().rss / 1024 / 1024) - start_memory
                except Exception:
                    pass
                
                # Extract result information
                result_count = None
                affected_rows = None
                
                if extract_result_count:
                    try:
                        result_count = extract_result_count(result)
                    except Exception as e:
                        logger.debug(f"Failed to extract result count: {e}")
                else:
                    result_count = _default_extract_result_count(result)
                
                if extract_affected_rows:
                    try:
                        affected_rows = extract_affected_rows(result)
                    except Exception as e:
                        logger.debug(f"Failed to extract affected rows: {e}")
                else:
                    affected_rows = _default_extract_affected_rows(result)
                
                # Log successful query (async call in sync context)
                asyncio.create_task(
                    get_database_query_logger().log_query(
                        database_type=database_type,
                        query=query_text,
                        execution_time_ms=execution_time_ms,
                        parameters=parameters,
                        result_count=result_count,
                        affected_rows=affected_rows,
                        cpu_usage_percent=cpu_delta,
                        memory_usage_mb=memory_delta,
                        method_name=method_name
                    )
                )
                
                return result
                
            except Exception as e:
                # Calculate execution time
                execution_time_ms = (time.time() - start_time) * 1000
                
                # Calculate resource usage
                cpu_delta = None
                memory_delta = None
                
                try:
                    process = psutil.Process()
                    if start_cpu is not None:
                        cpu_delta = process.cpu_percent() - start_cpu
                    if start_memory is not None:
                        memory_delta = (process.memory_info().rss / 1024 / 1024) - start_memory
                except Exception:
                    pass
                
                # Log failed query (async call in sync context)
                asyncio.create_task(
                    get_database_query_logger().log_query(
                        database_type=database_type,
                        query=query_text,
                        execution_time_ms=execution_time_ms,
                        parameters=parameters,
                        error_message=str(e),
                        cpu_usage_percent=cpu_delta,
                        memory_usage_mb=memory_delta,
                        method_name=method_name
                    )
                )
                
                # Re-raise the exception
                raise
        
        # Return appropriate wrapper based on function type
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


def log_database_queries(
    database_type: str,
    methods_to_log: Optional[list] = None,
    exclude_methods: Optional[list] = None
) -> Callable[[type], type]:
    """
    Class decorator to automatically log all database query methods.
    
    Args:
        database_type: Type of database (postgresql, neo4j, milvus)
        methods_to_log: Specific methods to log (default: auto-detect query methods)
        exclude_methods: Methods to exclude from logging
        
    Returns:
        Decorated class with automatic query logging
    """
    def decorator(cls: type) -> type:
        # Default methods to log if not specified
        if methods_to_log is None:
            default_methods = [
                'execute_query', 'execute_command', 'execute_write_query',
                'search_vectors', 'insert_vectors', 'semantic_search',
                'create_node', 'create_relationship', 'get_vector_by_id',
                'store_embeddings', 'delete_chunks_by_source'
            ]
        else:
            default_methods = methods_to_log
        
        exclude_list = exclude_methods or []
        
        # Get all methods to decorate
        for method_name in default_methods:
            if method_name in exclude_list:
                continue
            
            if hasattr(cls, method_name):
                original_method = getattr(cls, method_name)
                
                # Create appropriate extractor functions based on method name and database type
                extract_query_func = _create_query_extractor(method_name, database_type)
                extract_params_func = _create_params_extractor(method_name, database_type)
                extract_result_func = _create_result_extractor(method_name, database_type)
                extract_affected_func = _create_affected_extractor(method_name, database_type)
                
                # Apply the decorator
                decorated_method = log_query_execution(
                    database_type=database_type,
                    extract_query=extract_query_func,
                    extract_parameters=extract_params_func,
                    extract_result_count=extract_result_func,
                    extract_affected_rows=extract_affected_func,
                    method_name_override=method_name
                )(original_method)
                
                # Replace the method
                setattr(cls, method_name, decorated_method)
        
        return cls
    
    return decorator


def _default_extract_query(*args, **kwargs) -> str:
    """Default query extraction logic."""
    # Look for common query parameter names
    query_params = ['query', 'command', 'statement', 'cypher', 'sql']
    
    # Check keyword arguments first
    for param in query_params:
        if param in kwargs:
            return str(kwargs[param])
    
    # Check positional arguments (skip self/cls)
    if len(args) > 1:
        # Assume first argument after self is the query
        return str(args[1])
    
    return "<unknown_query>"


def _default_extract_parameters(*args, **kwargs) -> Dict[str, Any]:
    """Default parameter extraction logic."""
    # Look for common parameter names
    param_names = ['parameters', 'params', 'values', 'data']
    
    for param in param_names:
        if param in kwargs and isinstance(kwargs[param], dict):
            return kwargs[param]
    
    # Check if second positional argument looks like parameters
    if len(args) > 2 and isinstance(args[2], dict):
        return args[2]
    
    return {}


def _default_extract_result_count(result: Any) -> Optional[int]:
    """Default result count extraction logic."""
    if result is None:
        return None
    
    # Handle list results
    if isinstance(result, list):
        return len(result)
    
    # Handle dict results with count field
    if isinstance(result, dict):
        count_fields = ['count', 'total', 'num_results', 'result_count']
        for field in count_fields:
            if field in result:
                return int(result[field])
    
    # Handle single result
    if hasattr(result, '__len__'):
        try:
            return len(result)
        except:
            pass
    
    return None


def _default_extract_affected_rows(result: Any) -> Optional[int]:
    """Default affected rows extraction logic."""
    if result is None:
        return None
    
    # Handle integer results (common for INSERT/UPDATE/DELETE)
    if isinstance(result, int):
        return result
    
    # Handle dict results with affected rows field
    if isinstance(result, dict):
        affected_fields = ['affected_rows', 'rowcount', 'rows_affected', 'modified_count']
        for field in affected_fields:
            if field in result:
                return int(result[field])
    
    return None


def _create_query_extractor(method_name: str, database_type: str) -> Optional[Callable]:
    """Create query extractor function based on method name and database type."""
    if database_type == "postgresql":
        if method_name in ['execute_query', 'execute_command']:
            return lambda *args, **kwargs: args[1] if len(args) > 1 else kwargs.get('query', kwargs.get('command', '<unknown>'))
    
    elif database_type == "neo4j":
        if method_name in ['execute_query', 'execute_write_query']:
            return lambda *args, **kwargs: args[1] if len(args) > 1 else kwargs.get('query', '<unknown>')
    
    elif database_type == "milvus":
        if method_name == 'search_vectors':
            return lambda *args, **kwargs: f"SEARCH VECTORS IN {args[1] if len(args) > 1 else kwargs.get('collection_name', 'unknown')}"
        elif method_name == 'insert_vectors':
            return lambda *args, **kwargs: f"INSERT VECTORS INTO {args[1] if len(args) > 1 else kwargs.get('collection_name', 'unknown')}"
        elif method_name == 'semantic_search':
            return lambda *args, **kwargs: f"SEMANTIC SEARCH: {args[1] if len(args) > 1 else kwargs.get('query', 'unknown')}"
    
    return None


def _create_params_extractor(method_name: str, database_type: str) -> Optional[Callable]:
    """Create parameters extractor function based on method name and database type."""
    if database_type in ["postgresql", "neo4j"]:
        if method_name in ['execute_query', 'execute_command', 'execute_write_query']:
            return lambda *args, **kwargs: args[2] if len(args) > 2 else kwargs.get('parameters', {})
    
    elif database_type == "milvus":
        if method_name == 'search_vectors':
            return lambda *args, **kwargs: {
                'top_k': args[3] if len(args) > 3 else kwargs.get('k', kwargs.get('top_k', 10)),
                'filters': kwargs.get('filters', {})
            }
        elif method_name == 'semantic_search':
            return lambda *args, **kwargs: {
                'top_k': args[2] if len(args) > 2 else kwargs.get('top_k', 10),
                'filters': kwargs.get('filters', {})
            }
    
    return None


def _create_result_extractor(method_name: str, database_type: str) -> Optional[Callable]:
    """Create result count extractor function based on method name and database type."""
    if method_name in ['execute_query', 'search_vectors', 'semantic_search']:
        return lambda result: len(result) if isinstance(result, list) else None
    
    return None


def _create_affected_extractor(method_name: str, database_type: str) -> Optional[Callable]:
    """Create affected rows extractor function based on method name and database type."""
    if method_name in ['execute_command', 'execute_write_query', 'insert_vectors']:
        return lambda result: result if isinstance(result, int) else None
    
    return None


# Convenience decorators for specific database types

def log_postgresql_queries(
    methods_to_log: Optional[list] = None,
    exclude_methods: Optional[list] = None
):
    """Decorator for PostgreSQL client classes."""
    return log_database_queries("postgresql", methods_to_log, exclude_methods)


def log_neo4j_queries(
    methods_to_log: Optional[list] = None,
    exclude_methods: Optional[list] = None
):
    """Decorator for Neo4j client classes."""
    return log_database_queries("neo4j", methods_to_log, exclude_methods)


def log_milvus_queries(
    methods_to_log: Optional[list] = None,
    exclude_methods: Optional[list] = None
):
    """Decorator for Milvus client classes."""
    return log_database_queries("milvus", methods_to_log, exclude_methods)


# Method-level decorators for convenience

def log_postgresql_query(
    extract_query: Optional[Callable] = None,
    extract_parameters: Optional[Callable] = None,
    extract_result_count: Optional[Callable] = None,
    extract_affected_rows: Optional[Callable] = None
):
    """Method decorator for PostgreSQL queries."""
    return log_query_execution(
        "postgresql", extract_query, extract_parameters, 
        extract_result_count, extract_affected_rows
    )


def log_neo4j_query(
    extract_query: Optional[Callable] = None,
    extract_parameters: Optional[Callable] = None,
    extract_result_count: Optional[Callable] = None,
    extract_affected_rows: Optional[Callable] = None
):
    """Method decorator for Neo4j queries."""
    return log_query_execution(
        "neo4j", extract_query, extract_parameters, 
        extract_result_count, extract_affected_rows
    )


def log_milvus_query(
    extract_query: Optional[Callable] = None,
    extract_parameters: Optional[Callable] = None,
    extract_result_count: Optional[Callable] = None,
    extract_affected_rows: Optional[Callable] = None
):
    """Method decorator for Milvus queries."""
    return log_query_execution(
        "milvus", extract_query, extract_parameters, 
        extract_result_count, extract_affected_rows
    )