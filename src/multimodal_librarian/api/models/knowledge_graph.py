"""
Pydantic models for Knowledge Graph API endpoints.
"""

from typing import Dict, List, Optional, Any, Union
from pydantic import BaseModel, Field
from datetime import datetime


class NodeCreateRequest(BaseModel):
    """Request model for creating a node."""
    label: str = Field(..., description="Node label (e.g., 'Document', 'Entity')")
    properties: Dict[str, Any] = Field(..., description="Node properties")
    merge_on: Optional[List[str]] = Field(None, description="Properties to use for MERGE instead of CREATE")


class NodeUpdateRequest(BaseModel):
    """Request model for updating a node."""
    properties: Dict[str, Any] = Field(..., description="Properties to update")


class NodeResponse(BaseModel):
    """Response model for node operations."""
    id: int = Field(..., description="Node ID")
    labels: List[str] = Field(..., description="Node labels")
    properties: Dict[str, Any] = Field(..., description="Node properties")


class RelationshipCreateRequest(BaseModel):
    """Request model for creating a relationship."""
    from_node_id: int = Field(..., description="Source node ID")
    to_node_id: int = Field(..., description="Target node ID")
    relationship_type: str = Field(..., description="Relationship type (e.g., 'CONTAINS', 'RELATES_TO')")
    properties: Optional[Dict[str, Any]] = Field(None, description="Relationship properties")


class RelationshipResponse(BaseModel):
    """Response model for relationship operations."""
    id: int = Field(..., description="Relationship ID")
    type: str = Field(..., description="Relationship type")
    properties: Dict[str, Any] = Field(..., description="Relationship properties")
    from_node_id: Optional[int] = Field(None, description="Source node ID")
    to_node_id: Optional[int] = Field(None, description="Target node ID")


class CypherQueryRequest(BaseModel):
    """Request model for Cypher queries."""
    query: str = Field(..., description="Cypher query string")
    parameters: Optional[Dict[str, Any]] = Field(None, description="Query parameters")


class CypherQueryResponse(BaseModel):
    """Response model for Cypher queries."""
    results: List[Dict[str, Any]] = Field(..., description="Query results")
    execution_time_ms: Optional[float] = Field(None, description="Query execution time in milliseconds")


class SearchRequest(BaseModel):
    """Request model for node search."""
    search_term: str = Field(..., description="Term to search for")
    labels: Optional[List[str]] = Field(None, description="Node labels to search in")
    properties: Optional[List[str]] = Field(None, description="Properties to search in")
    limit: int = Field(50, description="Maximum number of results", ge=1, le=1000)


class SearchResponse(BaseModel):
    """Response model for search operations."""
    nodes: List[NodeResponse] = Field(..., description="Matching nodes")
    total_count: int = Field(..., description="Total number of matches")


class GraphStatsResponse(BaseModel):
    """Response model for graph statistics."""
    total_nodes: int = Field(..., description="Total number of nodes")
    total_relationships: int = Field(..., description="Total number of relationships")
    nodes_by_label: Dict[str, int] = Field(..., description="Node count by label")
    relationships_by_type: Dict[str, int] = Field(..., description="Relationship count by type")


class HealthCheckResponse(BaseModel):
    """Response model for Neo4j health check."""
    status: str = Field(..., description="Health status")
    message: str = Field(..., description="Status message")
    neo4j_available: bool = Field(..., description="Whether Neo4j is available")
    connection_status: Optional[str] = Field(None, description="Connection status")
    database_info: Optional[Dict[str, Any]] = Field(None, description="Database information")
    last_check: Optional[float] = Field(None, description="Last health check timestamp")


class ErrorResponse(BaseModel):
    """Response model for errors."""
    error: str = Field(..., description="Error message")
    detail: Optional[str] = Field(None, description="Error details")
    error_type: Optional[str] = Field(None, description="Error type")


class SuccessResponse(BaseModel):
    """Response model for successful operations."""
    success: bool = Field(True, description="Operation success")
    message: str = Field(..., description="Success message")
    data: Optional[Any] = Field(None, description="Response data")