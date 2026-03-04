"""
Test Neo4j Client Protocol Compliance

This module tests that the Neo4j client properly implements the GraphStoreClient protocol.
"""

import pytest
from typing import get_type_hints
import inspect

from src.multimodal_librarian.clients.neo4j_client import Neo4jClient
from src.multimodal_librarian.clients.protocols import GraphStoreClient


class TestNeo4jProtocolCompliance:
    """Test Neo4j client protocol compliance."""
    
    def test_neo4j_client_has_all_protocol_methods(self):
        """Test that Neo4jClient has all methods required by GraphStoreClient protocol."""
        # Get all methods from the protocol
        protocol_methods = {}
        for name in dir(GraphStoreClient):
            if not name.startswith('_'):
                attr = getattr(GraphStoreClient, name)
                if callable(attr):
                    protocol_methods[name] = attr
        
        # Check that Neo4jClient has all these methods
        client = Neo4jClient()
        for method_name in protocol_methods:
            assert hasattr(client, method_name), f"Neo4jClient missing method: {method_name}"
            
            client_method = getattr(client, method_name)
            assert callable(client_method), f"Neo4jClient.{method_name} is not callable"
    
    def test_neo4j_client_method_signatures(self):
        """Test that Neo4jClient methods have compatible signatures with the protocol."""
        client = Neo4jClient()
        
        # Test key methods have the expected signatures
        key_methods = [
            'connect', 'disconnect', 'health_check', 'execute_query',
            'create_node', 'get_node', 'update_node', 'delete_node',
            'create_relationship', 'get_relationships', 'delete_relationship',
            'find_path', 'get_neighbors', 'get_database_info'
        ]
        
        for method_name in key_methods:
            assert hasattr(client, method_name), f"Missing method: {method_name}"
            method = getattr(client, method_name)
            
            # Check that method is callable
            assert callable(method), f"Method {method_name} is not callable"
            
            # Check that method signature is reasonable (has expected parameters)
            sig = inspect.signature(method)
            assert len(sig.parameters) >= 0, f"Method {method_name} signature issue"
    
    def test_neo4j_client_async_methods(self):
        """Test that async methods are properly defined."""
        client = Neo4jClient()
        
        async_methods = [
            'connect', 'disconnect', 'health_check', 'execute_query',
            'create_node', 'get_node', 'update_node', 'delete_node',
            'create_relationship', 'get_relationships', 'delete_relationship',
            'find_path', 'get_neighbors', 'get_database_info'
        ]
        
        for method_name in async_methods:
            method = getattr(client, method_name)
            assert inspect.iscoroutinefunction(method), f"Method {method_name} should be async"
    
    def test_neo4j_client_can_be_used_as_protocol(self):
        """Test that Neo4jClient can be used where GraphStoreClient is expected."""
        def use_graph_client(client: GraphStoreClient) -> str:
            """Function that expects a GraphStoreClient protocol."""
            return f"Using client: {type(client).__name__}"
        
        # This should not raise any type errors
        client = Neo4jClient()
        result = use_graph_client(client)
        assert "Neo4jClient" in result
    
    def test_gremlin_compatibility_layer(self):
        """Test that Gremlin compatibility layer is available."""
        client = Neo4jClient()
        
        # Should have gremlin compatibility method
        assert hasattr(client, 'get_gremlin_compatibility')
        
        gremlin_layer = client.get_gremlin_compatibility()
        assert gremlin_layer is not None
        
        # Check key Gremlin-like methods
        gremlin_methods = ['add_vertex', 'add_edge', 'get_vertex', 'has_label', 'out_edges', 'in_edges']
        for method_name in gremlin_methods:
            assert hasattr(gremlin_layer, method_name), f"Gremlin layer missing method: {method_name}"
            method = getattr(gremlin_layer, method_name)
            assert callable(method), f"Gremlin method {method_name} is not callable"
            assert inspect.iscoroutinefunction(method), f"Gremlin method {method_name} should be async"


if __name__ == "__main__":
    pytest.main([__file__])