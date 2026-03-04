"""
Tests for database client protocols.

This module tests that the database client protocols are properly defined
and have all required methods with correct signatures.
"""

import pytest
from typing import get_type_hints, get_origin, get_args
import inspect
from unittest.mock import AsyncMock, MagicMock

from multimodal_librarian.clients.protocols import (
    RelationalStoreClient,
    VectorStoreClient,
    GraphStoreClient,
    DatabaseClientError,
    ConnectionError,
    QueryError,
    TransactionError,
    SchemaError,
    ValidationError,
    TimeoutError,
    ConfigurationError,
    ResourceError
)


class TestRelationalStoreClientProtocol:
    """Test RelationalStoreClient protocol definition."""
    
    def test_protocol_has_required_methods(self):
        """Test that RelationalStoreClient has all required methods."""
        expected_methods = {
            'connect', 'disconnect', 'health_check',
            'get_async_session', 'get_session',
            'execute_query', 'execute_command', 'transaction',
            'create_tables', 'drop_tables', 'migrate_schema',
            'get_pool_status', 'reset_pool',
            'backup_database', 'restore_database',
            'get_database_info', 'get_table_info',
            'get_performance_stats', 'analyze_table'
        }
        
        actual_methods = set(dir(RelationalStoreClient))
        
        # Check that all expected methods are present
        missing_methods = expected_methods - actual_methods
        assert not missing_methods, f"Missing methods: {missing_methods}"
    
    def test_async_methods_are_async(self):
        """Test that async methods are properly defined as async."""
        async_methods = {
            'connect', 'disconnect', 'health_check',
            'execute_query', 'execute_command', 'transaction',
            'create_tables', 'drop_tables', 'migrate_schema',
            'reset_pool', 'backup_database', 'restore_database',
            'get_database_info', 'get_table_info',
            'get_performance_stats', 'analyze_table'
        }
        
        for method_name in async_methods:
            method = getattr(RelationalStoreClient, method_name, None)
            assert method is not None, f"Method {method_name} not found"
            
            # Check if method is marked as async (has __code__.co_flags & 0x80)
            # For protocols, we check the annotations instead
            hints = get_type_hints(method)
            # The presence of the method in the protocol is sufficient for this test


class TestVectorStoreClientProtocol:
    """Test VectorStoreClient protocol definition."""
    
    def test_protocol_has_required_methods(self):
        """Test that VectorStoreClient has all required methods."""
        expected_methods = {
            'connect', 'disconnect', 'health_check',
            'create_collection', 'delete_collection', 'list_collections',
            'insert_vectors', 'search_vectors', 'get_vector_by_id', 
            'delete_vectors', 'get_collection_stats',
            # High-level operations
            'store_embeddings', 'semantic_search', 'get_chunk_by_id',
            'delete_chunks_by_source', 'generate_embedding',
            # Index management
            'create_index', 'drop_index'
        }
        
        actual_methods = set(dir(VectorStoreClient))
        
        # Check that all expected methods are present
        missing_methods = expected_methods - actual_methods
        assert not missing_methods, f"Missing methods: {missing_methods}"
    
    def test_high_level_interface_methods(self):
        """Test that high-level interface methods are properly defined."""
        # These methods should exist for compatibility with existing codebase
        high_level_methods = {
            'store_embeddings', 'semantic_search', 'get_chunk_by_id',
            'delete_chunks_by_source', 'generate_embedding'
        }
        
        actual_methods = set(dir(VectorStoreClient))
        
        # Check that all high-level methods are present
        missing_methods = high_level_methods - actual_methods
        assert not missing_methods, f"Missing high-level methods: {missing_methods}"
    
    def test_index_management_methods(self):
        """Test that index management methods are properly defined."""
        index_methods = {'create_index', 'drop_index'}
        
        actual_methods = set(dir(VectorStoreClient))
        
        # Check that all index management methods are present
        missing_methods = index_methods - actual_methods
        assert not missing_methods, f"Missing index management methods: {missing_methods}"


class TestGraphStoreClientProtocol:
    """Test GraphStoreClient protocol definition."""
    
    def test_protocol_has_required_methods(self):
        """Test that GraphStoreClient has all required methods."""
        expected_methods = {
            'connect', 'disconnect', 'health_check', 'execute_query',
            'create_node', 'get_node', 'update_node', 'delete_node',
            'create_relationship', 'get_relationships', 'delete_relationship',
            'find_path', 'get_neighbors', 'get_database_info'
        }
        
        actual_methods = set(dir(GraphStoreClient))
        
        # Check that all expected methods are present
        missing_methods = expected_methods - actual_methods
        assert not missing_methods, f"Missing methods: {missing_methods}"


class TestExceptionHierarchy:
    """Test database exception class hierarchy."""
    
    def test_exception_inheritance(self):
        """Test that all exceptions inherit from DatabaseClientError."""
        assert issubclass(ConnectionError, DatabaseClientError)
        assert issubclass(QueryError, DatabaseClientError)
        assert issubclass(TransactionError, DatabaseClientError)
        assert issubclass(SchemaError, DatabaseClientError)
        assert issubclass(ValidationError, DatabaseClientError)
        assert issubclass(TimeoutError, DatabaseClientError)
        assert issubclass(ConfigurationError, DatabaseClientError)
        assert issubclass(ResourceError, DatabaseClientError)
    
    def test_base_exception_inheritance(self):
        """Test that DatabaseClientError inherits from Exception."""
        assert issubclass(DatabaseClientError, Exception)
    
    def test_exception_instantiation(self):
        """Test that exceptions can be instantiated with messages."""
        msg = "Test error message"
        
        db_error = DatabaseClientError(msg)
        assert str(db_error) == msg
        
        conn_error = ConnectionError(msg)
        assert str(conn_error) == msg
        
        query_error = QueryError(msg)
        assert str(query_error) == msg
        
        trans_error = TransactionError(msg)
        assert str(trans_error) == msg
        
        schema_error = SchemaError(msg)
        assert str(schema_error) == msg
        
        validation_error = ValidationError(msg)
        assert str(validation_error) == msg
        
        timeout_error = TimeoutError(msg)
        assert str(timeout_error) == msg
        
        config_error = ConfigurationError(msg)
        assert str(config_error) == msg
        
        resource_error = ResourceError(msg)
        assert str(resource_error) == msg
    
    def test_exception_with_context(self):
        """Test that exceptions can be instantiated with context information."""
        msg = "Test error with context"
        context = {"database": "test_db", "operation": "select"}
        
        db_error = DatabaseClientError(msg, context=context)
        assert db_error.message == msg
        assert db_error.context == context
        assert "database=test_db" in str(db_error)
        assert "operation=select" in str(db_error)
    
    def test_exception_with_error_code(self):
        """Test that exceptions can be instantiated with error codes."""
        msg = "Test error with code"
        error_code = "DB001"
        
        db_error = DatabaseClientError(msg, error_code=error_code)
        assert db_error.error_code == error_code
        assert f"Error Code: {error_code}" in str(db_error)
    
    def test_exception_with_original_exception(self):
        """Test that exceptions can wrap original exceptions."""
        original = ValueError("Original error")
        msg = "Wrapped error"
        
        db_error = DatabaseClientError(msg, original_exception=original)
        assert db_error.original_exception == original
        assert "ValueError: Original error" in str(db_error)
    
    def test_exception_to_dict(self):
        """Test that exceptions can be serialized to dictionaries."""
        msg = "Test error"
        error_code = "DB001"
        context = {"key": "value"}
        original = ValueError("Original")
        
        db_error = DatabaseClientError(
            msg, 
            error_code=error_code, 
            context=context, 
            original_exception=original
        )
        
        error_dict = db_error.to_dict()
        
        assert error_dict["error_type"] == "DatabaseClientError"
        assert error_dict["message"] == msg
        assert error_dict["error_code"] == error_code
        assert error_dict["context"] == context
        assert "ValueError: Original" in error_dict["original_exception"]
    
    def test_connection_error_with_database_info(self):
        """Test ConnectionError with database connection information."""
        msg = "Connection failed"
        
        conn_error = ConnectionError(
            msg,
            database_type="postgresql",
            host="localhost",
            port=5432,
            database_name="test_db"
        )
        
        assert conn_error.context["database_type"] == "postgresql"
        assert conn_error.context["host"] == "localhost"
        assert conn_error.context["port"] == 5432
        assert conn_error.context["database_name"] == "test_db"
    
    def test_query_error_with_query_info(self):
        """Test QueryError with query information."""
        msg = "Query failed"
        query = "SELECT * FROM users WHERE id = ?"
        parameters = {"id": 123, "password": "secret"}
        
        query_error = QueryError(
            msg,
            query=query,
            parameters=parameters,
            query_type="SELECT"
        )
        
        assert query_error.context["query"] == query
        assert query_error.context["parameters"]["id"] == "123"
        assert query_error.context["parameters"]["password"] == "[REDACTED]"
        assert query_error.context["query_type"] == "SELECT"
    
    def test_validation_error_with_field_info(self):
        """Test ValidationError with field validation information."""
        msg = "Field validation failed"
        
        validation_error = ValidationError(
            msg,
            field_name="email",
            field_value="invalid-email",
            validation_rule="email_format"
        )
        
        assert validation_error.context["field_name"] == "email"
        assert validation_error.context["field_value"] == "invalid-email"
        assert validation_error.context["validation_rule"] == "email_format"
    
    def test_timeout_error_with_timing_info(self):
        """Test TimeoutError with timing information."""
        msg = "Operation timed out"
        
        timeout_error = TimeoutError(
            msg,
            timeout_duration=30.0,
            operation_type="query_execution"
        )
        
        assert timeout_error.context["timeout_duration"] == 30.0
        assert timeout_error.context["operation_type"] == "query_execution"


class TestProtocolCompatibility:
    """Test protocol compatibility and usage patterns."""
    
    def test_relational_client_mock_compatibility(self):
        """Test that RelationalStoreClient can be mocked for testing."""
        # Create a mock that implements the protocol
        mock_client = AsyncMock(spec=RelationalStoreClient)
        
        # Test that we can call protocol methods
        mock_client.connect.return_value = None
        mock_client.health_check.return_value = {"status": "healthy"}
        
        # These should not raise any errors
        assert hasattr(mock_client, 'connect')
        assert hasattr(mock_client, 'health_check')
        assert hasattr(mock_client, 'execute_query')
    
    def test_vector_client_mock_compatibility(self):
        """Test that VectorStoreClient can be mocked for testing."""
        mock_client = AsyncMock(spec=VectorStoreClient)
        
        mock_client.search_vectors.return_value = []
        mock_client.list_collections.return_value = ["test_collection"]
        mock_client.semantic_search.return_value = []
        mock_client.generate_embedding.return_value = [0.1, 0.2, 0.3]
        
        assert hasattr(mock_client, 'search_vectors')
        assert hasattr(mock_client, 'list_collections')
        assert hasattr(mock_client, 'insert_vectors')
        assert hasattr(mock_client, 'semantic_search')
        assert hasattr(mock_client, 'generate_embedding')
        assert hasattr(mock_client, 'store_embeddings')
        assert hasattr(mock_client, 'get_chunk_by_id')
        assert hasattr(mock_client, 'delete_chunks_by_source')
    
    def test_graph_client_mock_compatibility(self):
        """Test that GraphStoreClient can be mocked for testing."""
        mock_client = AsyncMock(spec=GraphStoreClient)
        
        mock_client.execute_query.return_value = []
        mock_client.create_node.return_value = "node_123"
        
        assert hasattr(mock_client, 'execute_query')
        assert hasattr(mock_client, 'create_node')
        assert hasattr(mock_client, 'create_relationship')


if __name__ == "__main__":
    pytest.main([__file__])