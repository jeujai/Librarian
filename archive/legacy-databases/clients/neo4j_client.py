"""
Neo4j Client for Multimodal Librarian

This module provides a robust Neo4j client with connection management,
health checks, and error handling for the knowledge graph functionality.
"""

import json
import logging
import time
from typing import Dict, List, Optional, Any, Union
from contextlib import contextmanager

import boto3
from neo4j import GraphDatabase, Driver, Session
from neo4j.exceptions import ServiceUnavailable, AuthError, Neo4jError

logger = logging.getLogger(__name__)


class Neo4jConnectionError(Exception):
    """Raised when Neo4j connection fails."""
    pass


class Neo4jClient:
    """
    Neo4j client with connection pooling, health checks, and error handling.
    """
    
    def __init__(self, secret_name: str = "multimodal-librarian/full-ml/neo4j", region: str = "us-east-1"):
        """
        Initialize Neo4j client.
        
        Args:
            secret_name: AWS Secrets Manager secret name for Neo4j credentials
            region: AWS region for Secrets Manager
        """
        self.secret_name = secret_name
        self.region = region
        self.driver: Optional[Driver] = None
        self._credentials: Optional[Dict[str, Any]] = None
        self._last_health_check = 0
        self._health_check_interval = 30  # seconds
        self._is_healthy = False
        
    def _get_credentials(self) -> Dict[str, Any]:
        """Get Neo4j credentials from AWS Secrets Manager."""
        if self._credentials is None:
            try:
                secrets_client = boto3.client('secretsmanager', region_name=self.region)
                response = secrets_client.get_secret_value(SecretId=self.secret_name)
                self._credentials = json.loads(response['SecretString'])
                logger.info(f"Retrieved Neo4j credentials from {self.secret_name}")
            except Exception as e:
                logger.error(f"Failed to get Neo4j credentials: {e}")
                raise Neo4jConnectionError(f"Failed to retrieve credentials: {e}")
        
        return self._credentials
    
    def _create_driver(self) -> Driver:
        """Create Neo4j driver with connection pooling."""
        credentials = self._get_credentials()
        
        uri = f"bolt://{credentials['host']}:{credentials['port']}"
        auth = (credentials['username'], credentials['password'])
        
        try:
            driver = GraphDatabase.driver(
                uri,
                auth=auth,
                max_connection_lifetime=3600,  # 1 hour
                max_connection_pool_size=50,
                connection_acquisition_timeout=60,  # 60 seconds
                encrypted=False,  # VPC internal communication
                trust=True
            )
            
            # Test the connection
            driver.verify_connectivity()
            logger.info(f"Successfully connected to Neo4j at {uri}")
            return driver
            
        except (ServiceUnavailable, AuthError) as e:
            logger.error(f"Failed to connect to Neo4j: {e}")
            raise Neo4jConnectionError(f"Connection failed: {e}")
        except Exception as e:
            logger.error(f"Unexpected error connecting to Neo4j: {e}")
            raise Neo4jConnectionError(f"Unexpected connection error: {e}")
    
    def connect(self) -> None:
        """Establish connection to Neo4j."""
        if self.driver is None:
            self.driver = self._create_driver()
            self._is_healthy = True
    
    def disconnect(self) -> None:
        """Close Neo4j connection."""
        if self.driver:
            self.driver.close()
            self.driver = None
            self._is_healthy = False
            logger.info("Disconnected from Neo4j")
    
    def is_connected(self) -> bool:
        """Check if client is connected to Neo4j."""
        return self.driver is not None and self._is_healthy
    
    def health_check(self, force: bool = False) -> Dict[str, Any]:
        """
        Perform health check on Neo4j connection.
        
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
            if not self.driver:
                self.connect()
            
            # Test with a simple query
            with self.driver.session() as session:
                result = session.run("RETURN 1 as test")
                record = result.single()
                if record and record["test"] == 1:
                    self._is_healthy = True
                    self._last_health_check = current_time
                    
                    # Get additional info
                    db_info = session.run("CALL dbms.components() YIELD name, versions, edition")
                    components = [dict(record) for record in db_info]
                    
                    return {
                        "status": "healthy",
                        "cached": False,
                        "last_check": current_time,
                        "components": components,
                        "connection_pool_size": len(self.driver._pool._connections) if hasattr(self.driver, '_pool') else 0
                    }
                else:
                    raise Neo4jConnectionError("Health check query returned unexpected result")
                    
        except Exception as e:
            self._is_healthy = False
            self._last_health_check = current_time
            logger.error(f"Neo4j health check failed: {e}")
            
            return {
                "status": "unhealthy",
                "cached": False,
                "last_check": current_time,
                "error": str(e)
            }
    
    @contextmanager
    def session(self, **kwargs):
        """
        Context manager for Neo4j sessions.
        
        Args:
            **kwargs: Additional arguments for session creation
            
        Yields:
            Neo4j session
        """
        if not self.is_connected():
            self.connect()
        
        session = None
        try:
            session = self.driver.session(**kwargs)
            yield session
        except Exception as e:
            logger.error(f"Session error: {e}")
            raise
        finally:
            if session:
                session.close()
    
    def execute_query(self, query: str, parameters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Execute a Cypher query and return results.
        
        Args:
            query: Cypher query string
            parameters: Query parameters
            
        Returns:
            List of result records as dictionaries
        """
        try:
            with self.session() as session:
                result = session.run(query, parameters or {})
                return [dict(record) for record in result]
        except Neo4jError as e:
            logger.error(f"Query execution failed: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error executing query: {e}")
            raise Neo4jConnectionError(f"Query execution error: {e}")
    
    def execute_write_query(self, query: str, parameters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Execute a write Cypher query and return results.
        
        Args:
            query: Cypher query string
            parameters: Query parameters
            
        Returns:
            List of result records as dictionaries
        """
        try:
            with self.session() as session:
                result = session.write_transaction(lambda tx: tx.run(query, parameters or {}))
                return [dict(record) for record in result]
        except Neo4jError as e:
            logger.error(f"Write query execution failed: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error executing write query: {e}")
            raise Neo4jConnectionError(f"Write query execution error: {e}")
    
    def create_node(self, label: str, properties: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a node with given label and properties.
        
        Args:
            label: Node label
            properties: Node properties
            
        Returns:
            Created node information
        """
        query = f"CREATE (n:{label} $props) RETURN n"
        result = self.execute_write_query(query, {"props": properties})
        
        if result:
            return dict(result[0]["n"])
        else:
            raise Neo4jConnectionError("Failed to create node")
    
    def get_node(self, label: str, properties: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Get a node by label and properties.
        
        Args:
            label: Node label
            properties: Properties to match
            
        Returns:
            Node information if found, None otherwise
        """
        where_clauses = [f"n.{key} = ${key}" for key in properties.keys()]
        where_clause = " AND ".join(where_clauses)
        
        query = f"MATCH (n:{label}) WHERE {where_clause} RETURN n LIMIT 1"
        result = self.execute_query(query, properties)
        
        if result:
            return dict(result[0]["n"])
        return None
    
    def create_relationship(self, from_node_id: Union[int, str], to_node_id: Union[int, str], 
                          relationship_type: str, properties: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Create a relationship between two nodes.
        
        Args:
            from_node_id: Source node ID
            to_node_id: Target node ID
            relationship_type: Type of relationship
            properties: Relationship properties
            
        Returns:
            Created relationship information
        """
        props_clause = ""
        params = {"from_id": from_node_id, "to_id": to_node_id}
        
        if properties:
            props_clause = " $props"
            params["props"] = properties
        
        query = f"""
        MATCH (a), (b)
        WHERE id(a) = $from_id AND id(b) = $to_id
        CREATE (a)-[r:{relationship_type}{props_clause}]->(b)
        RETURN r
        """
        
        result = self.execute_write_query(query, params)
        
        if result:
            return dict(result[0]["r"])
        else:
            raise Neo4jConnectionError("Failed to create relationship")
    
    def get_database_info(self) -> Dict[str, Any]:
        """Get Neo4j database information."""
        try:
            with self.session() as session:
                # Get database info
                db_info = session.run("CALL dbms.components() YIELD name, versions, edition")
                components = [dict(record) for record in db_info]
                
                # Get node count
                node_count_result = session.run("MATCH (n) RETURN count(n) as count")
                node_count = node_count_result.single()["count"]
                
                # Get relationship count
                rel_count_result = session.run("MATCH ()-[r]->() RETURN count(r) as count")
                rel_count = rel_count_result.single()["count"]
                
                return {
                    "components": components,
                    "node_count": node_count,
                    "relationship_count": rel_count,
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
_neo4j_client: Optional[Neo4jClient] = None


def get_neo4j_client() -> Neo4jClient:
    """Get or create global Neo4j client instance."""
    global _neo4j_client
    
    if _neo4j_client is None:
        _neo4j_client = Neo4jClient()
    
    return _neo4j_client


def close_neo4j_client() -> None:
    """Close global Neo4j client instance."""
    global _neo4j_client
    
    if _neo4j_client:
        _neo4j_client.disconnect()
        _neo4j_client = None