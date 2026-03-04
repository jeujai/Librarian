"""
Amazon Neptune Client for Multimodal Librarian

This module provides a Neptune client with Gremlin support, maintaining
compatibility with the Neo4j client interface while using AWS Neptune.
"""

import json
import logging
import time
import asyncio
from typing import Dict, List, Optional, Any, Union
from contextlib import asynccontextmanager

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from gremlin_python.driver import client, serializer
from gremlin_python.driver.driver_remote_connection import DriverRemoteConnection
from gremlin_python.process.anonymous_traversal import traversal
from gremlin_python.process.graph_traversal import __
from gremlin_python.process.traversal import T, P
import websockets
import asyncio

logger = logging.getLogger(__name__)


class NeptuneConnectionError(Exception):
    """Raised when Neptune connection fails."""
    pass


class NeptuneClient:
    """
    Neptune client with Gremlin support and Neo4j-compatible interface.
    """
    
    def __init__(self, secret_name: str = "multimodal-librarian/aws-native/neptune", region: str = "us-east-1"):
        """
        Initialize Neptune client.
        
        Args:
            secret_name: AWS Secrets Manager secret name for Neptune configuration
            region: AWS region for Neptune and Secrets Manager
        """
        self.secret_name = secret_name
        self.region = region
        self.client: Optional[client.Client] = None
        self.connection: Optional[DriverRemoteConnection] = None
        self.g = None  # Graph traversal source
        self._credentials: Optional[Dict[str, Any]] = None
        self._last_health_check = 0
        self._health_check_interval = 30  # seconds
        self._is_healthy = False
        
    def _get_credentials(self) -> Dict[str, Any]:
        """Get Neptune configuration from AWS Secrets Manager."""
        if self._credentials is None:
            try:
                secrets_client = boto3.client('secretsmanager', region_name=self.region)
                response = secrets_client.get_secret_value(SecretId=self.secret_name)
                self._credentials = json.loads(response['SecretString'])
                logger.info(f"Retrieved Neptune configuration from {self.secret_name}")
            except Exception as e:
                logger.error(f"Failed to get Neptune configuration: {e}")
                raise NeptuneConnectionError(f"Failed to retrieve configuration: {e}")
        
        return self._credentials
    
    def _create_connection(self) -> DriverRemoteConnection:
        """Create Neptune Gremlin connection with IAM authentication."""
        credentials = self._get_credentials()
        
        # Extract endpoint and port
        cluster_endpoint = credentials['cluster_endpoint']
        port = credentials.get('port', 8182)
        
        # Build WebSocket URL for Gremlin
        ws_url = f"wss://{cluster_endpoint}:{port}/gremlin"
        
        try:
            # Create connection with IAM authentication
            connection = DriverRemoteConnection(
                ws_url,
                'g',
                pool_size=10,
                max_workers=4,
                message_serializer=serializer.GraphSONSerializersV3d0(),
                headers={
                    'Authorization': self._get_iam_auth_header(cluster_endpoint, port)
                }
            )
            
            logger.info(f"Successfully connected to Neptune at {ws_url}")
            return connection
            
        except Exception as e:
            logger.error(f"Failed to connect to Neptune: {e}")
            raise NeptuneConnectionError(f"Connection failed: {e}")
    
    def _get_iam_auth_header(self, host: str, port: int) -> str:
        """Generate IAM authentication header for Neptune."""
        try:
            session = boto3.Session()
            credentials = session.get_credentials()
            
            # Create AWS request for signing
            request = AWSRequest(
                method='GET',
                url=f"https://{host}:{port}/gremlin",
                headers={'Host': f"{host}:{port}"}
            )
            
            # Sign the request
            SigV4Auth(credentials, 'neptune-db', self.region).add_auth(request)
            
            # Return the Authorization header
            return request.headers.get('Authorization', '')
            
        except Exception as e:
            logger.error(f"Failed to generate IAM auth header: {e}")
            raise NeptuneConnectionError(f"IAM authentication failed: {e}")
    
    def connect(self) -> None:
        """Establish connection to Neptune."""
        if self.connection is None:
            self.connection = self._create_connection()
            self.g = traversal().withRemote(self.connection)
            self._is_healthy = True
    
    def disconnect(self) -> None:
        """Close Neptune connection."""
        if self.connection:
            self.connection.close()
            self.connection = None
            self.g = None
            self._is_healthy = False
            logger.info("Disconnected from Neptune")
    
    def is_connected(self) -> bool:
        """Check if client is connected to Neptune."""
        return self.connection is not None and self._is_healthy
    
    def health_check(self, force: bool = False) -> Dict[str, Any]:
        """
        Perform health check on Neptune connection.
        
        Args:
            force: Force health check even if recently performed
            
        Returns:
            Dict with health status information
        """
        current_time = time.time()
        
        # Use cached result if recent and not forced
        if not force and (current_time - self._last_health_check) < self._health_check_interval:
            return {
                "status": "healthy" if self._is_healthy else "unhealthy",
                "cached": True,
                "last_check": self._last_health_check
            }
        
        try:
            if not self.connection:
                self.connect()
            
            # Test with a simple Gremlin query
            result = self.g.inject(1).next()
            if result == 1:
                self._is_healthy = True
                self._last_health_check = current_time
                
                # Get vertex and edge counts
                vertex_count = self.g.V().count().next()
                edge_count = self.g.E().count().next()
                
                return {
                    "status": "healthy",
                    "cached": False,
                    "last_check": current_time,
                    "vertex_count": vertex_count,
                    "edge_count": edge_count,
                    "engine": "neptune-gremlin"
                }
            else:
                raise NeptuneConnectionError("Health check query returned unexpected result")
                
        except Exception as e:
            self._is_healthy = False
            self._last_health_check = current_time
            logger.error(f"Neptune health check failed: {e}")
            
            return {
                "status": "unhealthy",
                "cached": False,
                "last_check": current_time,
                "error": str(e)
            }
    
    def execute_gremlin(self, query: str, bindings: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Execute a Gremlin query and return results.
        
        Args:
            query: Gremlin query string
            bindings: Query bindings/parameters
            
        Returns:
            List of result records
        """
        try:
            if not self.is_connected():
                self.connect()
            
            # Execute the query
            if bindings:
                result = self.connection.submit(query, bindings)
            else:
                result = self.connection.submit(query)
            
            # Convert results to list of dictionaries
            results = []
            for item in result:
                if hasattr(item, '__dict__'):
                    results.append(item.__dict__)
                elif isinstance(item, dict):
                    results.append(item)
                else:
                    results.append({"value": item})
            
            return results
            
        except Exception as e:
            logger.error(f"Gremlin query execution failed: {e}")
            raise NeptuneConnectionError(f"Query execution error: {e}")
    
    # Neo4j-compatible interface methods
    
    def execute_query(self, query: str, parameters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Execute a query (Neo4j-compatible interface).
        Converts Cypher-like operations to Gremlin.
        
        Args:
            query: Query string (will be converted from Cypher-like to Gremlin)
            parameters: Query parameters
            
        Returns:
            List of result records as dictionaries
        """
        # For now, assume the query is already in Gremlin format
        # In a full implementation, you'd convert Cypher to Gremlin
        return self.execute_gremlin(query, parameters)
    
    def execute_write_query(self, query: str, parameters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Execute a write query (Neo4j-compatible interface).
        
        Args:
            query: Query string
            parameters: Query parameters
            
        Returns:
            List of result records as dictionaries
        """
        return self.execute_query(query, parameters)
    
    def create_vertex(self, label: str, properties: Dict[str, Any]) -> str:
        """
        Create a vertex with given label and properties.
        
        Args:
            label: Vertex label
            properties: Vertex properties
            
        Returns:
            Created vertex ID
        """
        try:
            if not self.is_connected():
                self.connect()
            
            # Build Gremlin query to create vertex
            traversal_obj = self.g.addV(label)
            
            # Add properties
            for key, value in properties.items():
                traversal_obj = traversal_obj.property(key, value)
            
            # Execute and get the vertex
            vertex = traversal_obj.next()
            
            # Return the vertex ID
            return str(vertex.id)
            
        except Exception as e:
            logger.error(f"Failed to create vertex: {e}")
            raise NeptuneConnectionError(f"Vertex creation failed: {e}")
    
    def create_edge(self, from_id: str, to_id: str, label: str, properties: Optional[Dict[str, Any]] = None) -> str:
        """
        Create an edge between two vertices.
        
        Args:
            from_id: Source vertex ID
            to_id: Target vertex ID
            label: Edge label
            properties: Edge properties
            
        Returns:
            Created edge ID
        """
        try:
            if not self.is_connected():
                self.connect()
            
            # Build Gremlin query to create edge
            traversal_obj = self.g.V(from_id).addE(label).to(__.V(to_id))
            
            # Add properties if provided
            if properties:
                for key, value in properties.items():
                    traversal_obj = traversal_obj.property(key, value)
            
            # Execute and get the edge
            edge = traversal_obj.next()
            
            # Return the edge ID
            return str(edge.id)
            
        except Exception as e:
            logger.error(f"Failed to create edge: {e}")
            raise NeptuneConnectionError(f"Edge creation failed: {e}")
    
    def create_node(self, label: str, properties: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a node (Neo4j-compatible interface).
        
        Args:
            label: Node label
            properties: Node properties
            
        Returns:
            Created node information
        """
        vertex_id = self.create_vertex(label, properties)
        return {
            "id": vertex_id,
            "label": label,
            "properties": properties
        }
    
    def get_node(self, label: str, properties: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Get a node by label and properties (Neo4j-compatible interface).
        
        Args:
            label: Node label
            properties: Properties to match
            
        Returns:
            Node information if found, None otherwise
        """
        try:
            if not self.is_connected():
                self.connect()
            
            # Build Gremlin query to find vertex
            traversal_obj = self.g.V().hasLabel(label)
            
            # Add property filters
            for key, value in properties.items():
                traversal_obj = traversal_obj.has(key, value)
            
            # Get the first matching vertex
            vertices = traversal_obj.limit(1).toList()
            
            if vertices:
                vertex = vertices[0]
                return {
                    "id": str(vertex.id),
                    "label": vertex.label,
                    "properties": dict(vertex.properties) if hasattr(vertex, 'properties') else {}
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get node: {e}")
            return None
    
    def create_relationship(self, from_node_id: Union[int, str], to_node_id: Union[int, str], 
                          relationship_type: str, properties: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Create a relationship between two nodes (Neo4j-compatible interface).
        
        Args:
            from_node_id: Source node ID
            to_node_id: Target node ID
            relationship_type: Type of relationship
            properties: Relationship properties
            
        Returns:
            Created relationship information
        """
        edge_id = self.create_edge(str(from_node_id), str(to_node_id), relationship_type, properties)
        return {
            "id": edge_id,
            "type": relationship_type,
            "from": str(from_node_id),
            "to": str(to_node_id),
            "properties": properties or {}
        }
    
    def get_database_info(self) -> Dict[str, Any]:
        """Get Neptune database information."""
        try:
            if not self.is_connected():
                self.connect()
            
            # Get vertex count
            vertex_count = self.g.V().count().next()
            
            # Get edge count
            edge_count = self.g.E().count().next()
            
            # Get vertex labels
            vertex_labels = self.g.V().label().dedup().toList()
            
            # Get edge labels
            edge_labels = self.g.E().label().dedup().toList()
            
            return {
                "engine": "neptune",
                "vertex_count": vertex_count,
                "edge_count": edge_count,
                "vertex_labels": vertex_labels,
                "edge_labels": edge_labels,
                "status": "connected"
            }
        except Exception as e:
            logger.error(f"Failed to get database info: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()


# Global client instance
_neptune_client: Optional[NeptuneClient] = None


def get_neptune_client() -> NeptuneClient:
    """Get or create global Neptune client instance."""
    global _neptune_client
    
    if _neptune_client is None:
        _neptune_client = NeptuneClient()
    
    return _neptune_client


def close_neptune_client() -> None:
    """Close global Neptune client instance."""
    global _neptune_client
    
    if _neptune_client:
        _neptune_client.disconnect()
        _neptune_client = None