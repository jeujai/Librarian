"""
Database client exceptions for the Multimodal Librarian.

This module defines a hierarchy of exceptions used by database clients
to provide consistent error handling across different database implementations.

The exception hierarchy follows a pattern where specific errors inherit from
more general ones, allowing for both specific and general exception handling.

Exception Hierarchy:
    DatabaseClientError (base)
    ├── ConnectionError
    ├── QueryError
    ├── ValidationError
    ├── TransactionError
    ├── SchemaError
    ├── TimeoutError
    └── ResourceError

Example Usage:
    ```python
    from multimodal_librarian.clients.exceptions import (
        DatabaseClientError, ConnectionError, QueryError
    )
    
    try:
        await client.execute_query("SELECT * FROM users")
    except QueryError as e:
        logger.error(f"Query failed: {e}")
        # Handle query-specific error
    except ConnectionError as e:
        logger.error(f"Connection failed: {e}")
        # Handle connection-specific error
    except DatabaseClientError as e:
        logger.error(f"Database error: {e}")
        # Handle any database error
    ```
"""

from typing import Optional, Dict, Any


class DatabaseClientError(Exception):
    """
    Base exception for all database client errors.
    
    This is the root exception class that all other database client exceptions
    inherit from. It provides common functionality for error context and
    database-specific information.
    
    Attributes:
        message: Human-readable error message
        database_type: Type of database (postgresql, neo4j, milvus, etc.)
        host: Database host (if applicable)
        port: Database port (if applicable)
        context: Additional error context
    """
    
    def __init__(
        self,
        message: str,
        database_type: Optional[str] = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize database client error.
        
        Args:
            message: Human-readable error message
            database_type: Type of database (postgresql, neo4j, milvus, etc.)
            host: Database host
            port: Database port
            context: Additional error context
        """
        super().__init__(message)
        self.message = message
        self.database_type = database_type
        self.host = host
        self.port = port
        self.context = context or {}
    
    def __str__(self) -> str:
        """Return string representation of the error."""
        parts = [self.message]
        
        if self.database_type:
            parts.append(f"Database: {self.database_type}")
        
        if self.host and self.port:
            parts.append(f"Host: {self.host}:{self.port}")
        elif self.host:
            parts.append(f"Host: {self.host}")
        
        if self.context:
            context_str = ", ".join(f"{k}={v}" for k, v in self.context.items())
            parts.append(f"Context: {context_str}")
        
        return " | ".join(parts)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary representation."""
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "database_type": self.database_type,
            "host": self.host,
            "port": self.port,
            "context": self.context
        }


class ConnectionError(DatabaseClientError):
    """
    Raised when database connection operations fail.
    
    This exception is raised for connection-related errors such as:
    - Failed to establish connection
    - Connection timeout
    - Authentication failures
    - Network connectivity issues
    - Connection pool exhaustion
    
    Example:
        ```python
        try:
            await client.connect()
        except ConnectionError as e:
            logger.error(f"Failed to connect to database: {e}")
            # Implement retry logic or fallback
        ```
    """
    pass


class QueryError(DatabaseClientError):
    """
    Raised when database query execution fails.
    
    This exception is raised for query-related errors such as:
    - SQL syntax errors
    - Invalid query parameters
    - Query timeout
    - Constraint violations
    - Permission denied
    
    Additional Attributes:
        query: The query that failed (if available)
        parameters: Query parameters (if available)
    
    Example:
        ```python
        try:
            results = await client.execute_query("SELECT * FROM users WHERE id = :id", {"id": 123})
        except QueryError as e:
            logger.error(f"Query failed: {e}")
            if hasattr(e, 'query'):
                logger.debug(f"Failed query: {e.query}")
        ```
    """
    
    def __init__(
        self,
        message: str,
        query: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
        **kwargs
    ):
        """
        Initialize query error.
        
        Args:
            message: Human-readable error message
            query: The query that failed
            parameters: Query parameters
            **kwargs: Additional arguments passed to parent class
        """
        super().__init__(message, **kwargs)
        self.query = query
        self.parameters = parameters
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary representation."""
        result = super().to_dict()
        result.update({
            "query": self.query,
            "parameters": self.parameters
        })
        return result


class ValidationError(DatabaseClientError):
    """
    Raised when input validation fails.
    
    This exception is raised for validation-related errors such as:
    - Empty or invalid parameters
    - Invalid data types
    - Missing required fields
    - Data format errors
    - Business rule violations
    
    Additional Attributes:
        field: The field that failed validation (if applicable)
        value: The invalid value (if applicable)
        expected: Expected value or format (if applicable)
    
    Example:
        ```python
        try:
            await client.execute_query("")  # Empty query
        except ValidationError as e:
            logger.error(f"Validation failed: {e}")
            # Handle validation error
        ```
    """
    
    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        value: Optional[Any] = None,
        expected: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize validation error.
        
        Args:
            message: Human-readable error message
            field: The field that failed validation
            value: The invalid value
            expected: Expected value or format
            **kwargs: Additional arguments passed to parent class
        """
        super().__init__(message, **kwargs)
        self.field = field
        self.value = value
        self.expected = expected
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary representation."""
        result = super().to_dict()
        result.update({
            "field": self.field,
            "value": self.value,
            "expected": self.expected
        })
        return result


class TransactionError(DatabaseClientError):
    """
    Raised when database transaction operations fail.
    
    This exception is raised for transaction-related errors such as:
    - Transaction rollback failures
    - Deadlock detection
    - Isolation level violations
    - Transaction timeout
    - Concurrent modification conflicts
    
    Additional Attributes:
        transaction_id: Transaction identifier (if available)
        operation: The operation that failed (if applicable)
    
    Example:
        ```python
        try:
            async with client.transaction() as session:
                # Perform operations
                pass
        except TransactionError as e:
            logger.error(f"Transaction failed: {e}")
            # Handle transaction error
        ```
    """
    
    def __init__(
        self,
        message: str,
        transaction_id: Optional[str] = None,
        operation: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize transaction error.
        
        Args:
            message: Human-readable error message
            transaction_id: Transaction identifier
            operation: The operation that failed
            **kwargs: Additional arguments passed to parent class
        """
        super().__init__(message, **kwargs)
        self.transaction_id = transaction_id
        self.operation = operation
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary representation."""
        result = super().to_dict()
        result.update({
            "transaction_id": self.transaction_id,
            "operation": self.operation
        })
        return result


class SchemaError(DatabaseClientError):
    """
    Raised when database schema operations fail.
    
    This exception is raised for schema-related errors such as:
    - Table creation failures
    - Index creation failures
    - Migration errors
    - Constraint violations
    - Schema validation errors
    
    Additional Attributes:
        schema_object: The schema object that failed (table, index, etc.)
        operation: The schema operation that failed
    
    Example:
        ```python
        try:
            await client.create_tables()
        except SchemaError as e:
            logger.error(f"Schema operation failed: {e}")
            # Handle schema error
        ```
    """
    
    def __init__(
        self,
        message: str,
        schema_object: Optional[str] = None,
        operation: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize schema error.
        
        Args:
            message: Human-readable error message
            schema_object: The schema object that failed
            operation: The schema operation that failed
            **kwargs: Additional arguments passed to parent class
        """
        super().__init__(message, **kwargs)
        self.schema_object = schema_object
        self.operation = operation
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary representation."""
        result = super().to_dict()
        result.update({
            "schema_object": self.schema_object,
            "operation": self.operation
        })
        return result


class TimeoutError(DatabaseClientError):
    """
    Raised when database operations timeout.
    
    This exception is raised for timeout-related errors such as:
    - Query execution timeout
    - Connection timeout
    - Transaction timeout
    - Lock wait timeout
    - Network timeout
    
    Additional Attributes:
        timeout_duration: The timeout duration in seconds
        operation: The operation that timed out
    
    Example:
        ```python
        try:
            results = await client.execute_query("SELECT * FROM large_table")
        except TimeoutError as e:
            logger.error(f"Query timed out: {e}")
            # Handle timeout error
        ```
    """
    
    def __init__(
        self,
        message: str,
        timeout_duration: Optional[float] = None,
        operation: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize timeout error.
        
        Args:
            message: Human-readable error message
            timeout_duration: The timeout duration in seconds
            operation: The operation that timed out
            **kwargs: Additional arguments passed to parent class
        """
        super().__init__(message, **kwargs)
        self.timeout_duration = timeout_duration
        self.operation = operation
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary representation."""
        result = super().to_dict()
        result.update({
            "timeout_duration": self.timeout_duration,
            "operation": self.operation
        })
        return result


class ResourceError(DatabaseClientError):
    """
    Raised when database resource operations fail.
    
    This exception is raised for resource-related errors such as:
    - Out of memory
    - Disk space exhausted
    - Connection pool exhausted
    - Resource quota exceeded
    - Resource not available
    
    Additional Attributes:
        resource_type: The type of resource (memory, disk, connections, etc.)
        current_usage: Current resource usage (if available)
        limit: Resource limit (if available)
    
    Example:
        ```python
        try:
            await client.execute_query("SELECT * FROM huge_table")
        except ResourceError as e:
            logger.error(f"Resource error: {e}")
            # Handle resource error
        ```
    """
    
    def __init__(
        self,
        message: str,
        resource_type: Optional[str] = None,
        current_usage: Optional[Any] = None,
        limit: Optional[Any] = None,
        **kwargs
    ):
        """
        Initialize resource error.
        
        Args:
            message: Human-readable error message
            resource_type: The type of resource
            current_usage: Current resource usage
            limit: Resource limit
            **kwargs: Additional arguments passed to parent class
        """
        super().__init__(message, **kwargs)
        self.resource_type = resource_type
        self.current_usage = current_usage
        self.limit = limit
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary representation."""
        result = super().to_dict()
        result.update({
            "resource_type": self.resource_type,
            "current_usage": self.current_usage,
            "limit": self.limit
        })
        return result


# Legacy exception aliases for backward compatibility
class ConfigurationError(ValidationError):
    """Legacy alias for ValidationError with configuration context."""
    pass


class NeptuneConnectionError(ConnectionError):
    """Neptune-specific connection error."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(message, database_type="neptune", **kwargs)


class OpenSearchConnectionError(ConnectionError):
    """OpenSearch-specific connection error."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(message, database_type="opensearch", **kwargs)


class MilvusConnectionError(ConnectionError):
    """Milvus-specific connection error."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(message, database_type="milvus", **kwargs)


class Neo4jConnectionError(ConnectionError):
    """Neo4j-specific connection error."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(message, database_type="neo4j", **kwargs)


class PostgreSQLConnectionError(ConnectionError):
    """PostgreSQL-specific connection error."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(message, database_type="postgresql", **kwargs)


# Convenience function for creating database-specific errors
def create_database_error(
    error_class: type,
    message: str,
    database_type: str,
    **kwargs
) -> DatabaseClientError:
    """
    Create a database-specific error instance.
    
    Args:
        error_class: The error class to instantiate
        message: Error message
        database_type: Type of database
        **kwargs: Additional error context
        
    Returns:
        Database error instance
        
    Example:
        ```python
        error = create_database_error(
            QueryError,
            "Invalid SQL syntax",
            "postgresql",
            query="SELECT * FROM",
            host="localhost"
        )
        ```
    """
    return error_class(message, database_type=database_type, **kwargs)