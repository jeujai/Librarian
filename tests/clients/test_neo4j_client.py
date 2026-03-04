"""
Tests for Neo4j Client

This module contains tests for the Neo4j client implementation,
including connection management, query execution, and protocol compliance.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any

from src.multimodal_librarian.clients.neo4j_client import Neo4jClient, create_neo4j_client
from src.multimodal_librarian.clients.protocols import (
    ConnectionError,
    QueryError,
    ValidationError,
    TransactionError
)


class TestNeo4jClient:
    """Test cases for Neo4jClient."""
    
    @pytest.fixture
    def client_config(self):
        """Default client configuration for tests."""
        return {
            "uri": "bolt://localhost:7687",
            "user": "neo4j",
            "password": "test_password",
            "database": "neo4j"
        }
    
    @pytest.fixture
    def neo4j_client(self, client_config):
        """Create a Neo4j client for testing."""
        return Neo4jClient(**client_config)
    
    def test_client_initialization(self, neo4j_client):
        """Test client initialization with default parameters."""
        assert neo4j_client.uri == "bolt://localhost:7687"
        assert neo4j_client.user == "neo4j"
        assert neo4j_client.password == "test_password"
        assert neo4j_client.database == "neo4j"
        assert neo4j_client.driver is None
        assert not neo4j_client._is_connected
    
    def test_factory_function(self):
        """Test the factory function creates a client correctly."""
        client = create_neo4j_client(
            uri="bolt://test:7687",
            user="test_user",
            password="test_pass"
        )
        
        assert isinstance(client, Neo4jClient)
        assert client.uri == "bolt://test:7687"
        assert client.user == "test_user"
        assert client.password == "test_pass"
    
    @pytest.mark.asyncio
    async def test_connection_validation(self, neo4j_client):
        """Test connection validation raises appropriate errors."""
        with pytest.raises(ConnectionError, match="Neo4j client not connected"):
            neo4j_client._validate_connection()
    
    def test_parameter_sanitization(self, neo4j_client):
        """Test query parameter sanitization."""
        # Valid parameters
        params = {"name": "Alice", "age": 30, "active": True}
        sanitized = neo4j_client._sanitize_parameters(params)
        assert sanitized == params
        
        # None parameters
        assert neo4j_client._sanitize_parameters(None) == {}
        
        # Invalid parameter key
        with pytest.raises(ValidationError, match="Invalid parameter key"):
            neo4j_client._sanitize_parameters({"invalid-key": "value"})
        
        # Non-dict parameters
        with pytest.raises(ValidationError, match="must be a dictionary"):
            neo4j_client._sanitize_parameters("invalid")
    
    def test_cypher_query_formatting(self, neo4j_client):
        """Test Cypher query template formatting."""
        template = "MATCH (n:{label}) WHERE n.name = $name RETURN n"
        
        # Valid formatting
        formatted = neo4j_client._format_cypher_query(template, label="User")
        assert formatted == "MATCH (n:User) WHERE n.name = $name RETURN n"
        
        # Invalid template parameter
        with pytest.raises(ValidationError, match="Invalid template parameter"):
            neo4j_client._format_cypher_query(template, **{"invalid-param": "value"})
        
        # Missing template parameter
        with pytest.raises(ValidationError, match="Missing template parameter"):
            neo4j_client._format_cypher_query("MATCH (n:{missing}) RETURN n")
    
    @pytest.mark.asyncio
    async def test_connection_state_management(self, neo4j_client):
        """Test connection state management without actual Neo4j connection."""
        # Initially not connected
        assert not neo4j_client._is_connected
        assert neo4j_client.driver is None
        
        # Mock successful connection
        with patch.object(neo4j_client, '_create_connection_and_verify') as mock_connect:
            mock_driver = AsyncMock()
            mock_connect.return_value = mock_driver
            
            await neo4j_client.connect()
            
            assert neo4j_client._is_connected
            assert neo4j_client.driver == mock_driver
        
        # Test disconnect
        await neo4j_client.disconnect()
        assert not neo4j_client._is_connected
        assert neo4j_client.driver is None
    
    @pytest.mark.asyncio
    @patch('src.multimodal_librarian.clients.neo4j_client.GraphDatabase')
    async def test_connection_failure(self, mock_graph_database, neo4j_client):
        """Test connection failure handling."""
        from neo4j.exceptions import ServiceUnavailable
        
        mock_graph_database.async_driver.side_effect = ServiceUnavailable("Connection failed")
        
        with pytest.raises(ConnectionError, match="Failed to connect to Neo4j"):
            await neo4j_client.connect()
        
        assert not neo4j_client._is_connected
        assert neo4j_client.driver is None
    
    @pytest.mark.asyncio
    async def test_query_validation(self, neo4j_client):
        """Test query validation."""
        # Test validation before connection check
        with patch.object(neo4j_client, '_validate_connection'):
            # Empty query
            with pytest.raises(ValidationError, match="Query must be a non-empty string"):
                await neo4j_client.execute_query("")
            
            # Non-string query
            with pytest.raises(ValidationError, match="Query must be a non-empty string"):
                await neo4j_client.execute_query(123)
    
    @pytest.mark.asyncio
    async def test_node_operations_validation(self, neo4j_client):
        """Test node operations input validation."""
        # Invalid labels for create_node
        with pytest.raises(ValidationError, match="Labels must be a non-empty list"):
            await neo4j_client.create_node([], {"name": "test"})
        
        with pytest.raises(ValidationError, match="Labels must be a non-empty list"):
            await neo4j_client.create_node("invalid", {"name": "test"})
        
        # Invalid properties for create_node
        with pytest.raises(ValidationError, match="Properties must be a non-empty dictionary"):
            await neo4j_client.create_node(["User"], None)
        
        # Invalid node ID for get_node
        with pytest.raises(ValidationError, match="Node ID must be a non-empty string"):
            await neo4j_client.get_node("")
        
        with pytest.raises(ValidationError, match="Invalid node ID format"):
            await neo4j_client.get_node("invalid_id")
    
    @pytest.mark.asyncio
    async def test_relationship_operations_validation(self, neo4j_client):
        """Test relationship operations input validation."""
        # Invalid node IDs
        with pytest.raises(ValidationError, match="From node ID must be a non-empty string"):
            await neo4j_client.create_relationship("", "2", "FOLLOWS")
        
        with pytest.raises(ValidationError, match="To node ID must be a non-empty string"):
            await neo4j_client.create_relationship("1", "", "FOLLOWS")
        
        # Invalid relationship type
        with pytest.raises(ValidationError, match="Relationship type must be a non-empty string"):
            await neo4j_client.create_relationship("1", "2", "")
        
        with pytest.raises(ValidationError, match="Invalid relationship type"):
            await neo4j_client.create_relationship("1", "2", "INVALID-TYPE!")
        
        # Invalid node ID format
        with pytest.raises(ValidationError, match="Invalid node ID format"):
            await neo4j_client.create_relationship("invalid", "2", "FOLLOWS")
    
    @pytest.mark.asyncio
    async def test_get_relationships_validation(self, neo4j_client):
        """Test get_relationships input validation."""
        # Invalid direction
        with pytest.raises(ValidationError, match="Invalid direction"):
            await neo4j_client.get_relationships("1", "invalid_direction")
        
        # Test that validation happens before connection check
        with patch.object(neo4j_client, '_validate_connection'):
            # Valid directions should pass validation
            for direction in ["in", "out", "both"]:
                # Mock the execute_query to avoid actual execution
                with patch.object(neo4j_client, 'execute_query', return_value=[]):
                    result = await neo4j_client.get_relationships("1", direction)
                    assert result == []
    
    @pytest.mark.asyncio
    async def test_path_finding_validation(self, neo4j_client):
        """Test path finding input validation."""
        # Invalid max_depth
        with pytest.raises(ValidationError, match="Max depth must be a positive integer"):
            await neo4j_client.find_path("1", "2", max_depth=0)
        
        with pytest.raises(ValidationError, match="Max depth must be a positive integer"):
            await neo4j_client.find_path("1", "2", max_depth="invalid")
    
    @pytest.mark.asyncio
    async def test_neighbors_validation(self, neo4j_client):
        """Test get_neighbors input validation."""
        # Invalid depth
        with pytest.raises(ValidationError, match="Depth must be a positive integer"):
            await neo4j_client.get_neighbors("1", depth=0)
        
        with pytest.raises(ValidationError, match="Depth must be a positive integer"):
            await neo4j_client.get_neighbors("1", depth="invalid")
    
    @pytest.mark.asyncio
    async def test_transaction_queries_validation(self, neo4j_client):
        """Test execute_in_transaction input validation."""
        # Empty queries list
        with pytest.raises(ValidationError, match="Queries must be a non-empty list"):
            await neo4j_client.execute_in_transaction([])
        
        # Non-list queries
        with pytest.raises(ValidationError, match="Queries must be a non-empty list"):
            await neo4j_client.execute_in_transaction("invalid")
        
        # Invalid query format
        with pytest.raises(ValidationError, match="must be a dictionary with 'query' key"):
            await neo4j_client.execute_in_transaction([{"invalid": "format"}])
    
    def test_gremlin_compatibility_layer(self, neo4j_client):
        """Test Gremlin compatibility layer initialization."""
        gremlin_layer = neo4j_client.get_gremlin_compatibility()
        
        assert isinstance(gremlin_layer, Neo4jClient.GremlinCompatibilityLayer)
        assert gremlin_layer.client == neo4j_client
    
    @pytest.mark.asyncio
    async def test_context_manager(self, neo4j_client):
        """Test async context manager functionality."""
        with patch.object(neo4j_client, 'connect') as mock_connect:
            with patch.object(neo4j_client, 'disconnect') as mock_disconnect:
                async with neo4j_client:
                    pass
                
                mock_connect.assert_called_once()
                mock_disconnect.assert_called_once()


class TestGremlinCompatibilityLayer:
    """Test cases for Gremlin compatibility layer."""
    
    @pytest.fixture
    def neo4j_client(self):
        """Create a Neo4j client for testing."""
        return Neo4jClient()
    
    @pytest.fixture
    def gremlin_layer(self, neo4j_client):
        """Create a Gremlin compatibility layer for testing."""
        return neo4j_client.get_gremlin_compatibility()
    
    @pytest.mark.asyncio
    async def test_add_vertex(self, gremlin_layer):
        """Test add_vertex method."""
        with patch.object(gremlin_layer.client, 'create_node') as mock_create:
            mock_create.return_value = "123"
            
            result = await gremlin_layer.add_vertex("User", {"name": "Alice"})
            
            assert result == "123"
            mock_create.assert_called_once_with(["User"], {"name": "Alice"})
    
    @pytest.mark.asyncio
    async def test_add_edge(self, gremlin_layer):
        """Test add_edge method."""
        with patch.object(gremlin_layer.client, 'create_relationship') as mock_create:
            mock_create.return_value = "456"
            
            result = await gremlin_layer.add_edge("1", "2", "FOLLOWS", {"since": "2023"})
            
            assert result == "456"
            mock_create.assert_called_once_with("1", "2", "FOLLOWS", {"since": "2023"})
    
    @pytest.mark.asyncio
    async def test_get_vertex(self, gremlin_layer):
        """Test get_vertex method."""
        with patch.object(gremlin_layer.client, 'get_node') as mock_get:
            mock_get.return_value = {"id": "123", "labels": ["User"], "properties": {"name": "Alice"}}
            
            result = await gremlin_layer.get_vertex("123")
            
            assert result["id"] == "123"
            mock_get.assert_called_once_with("123")
    
    @pytest.mark.asyncio
    async def test_has_label_validation(self, gremlin_layer):
        """Test has_label input validation."""
        with patch.object(gremlin_layer.client, 'execute_query') as mock_execute:
            mock_execute.return_value = []
            
            await gremlin_layer.has_label("User")
            
            # Verify the query was constructed correctly
            call_args = mock_execute.call_args
            assert "MATCH (n:User)" in call_args[0][0]
    
    @pytest.mark.asyncio
    async def test_out_edges_validation(self, gremlin_layer):
        """Test out_edges input validation."""
        # Invalid vertex ID format
        with pytest.raises(ValidationError, match="Invalid vertex ID format"):
            await gremlin_layer.out_edges("invalid_id")


if __name__ == "__main__":
    pytest.main([__file__])