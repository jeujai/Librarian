"""
Knowledge Graph API Router for Multimodal Librarian

This router provides REST API endpoints for managing knowledge graphs,
including CRUD operations for nodes and relationships.
"""

import logging
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.responses import JSONResponse

from src.multimodal_librarian.api.models.knowledge_graph import (
    CypherQueryRequest,
    CypherQueryResponse,
    ErrorResponse,
    GraphStatsResponse,
    HealthCheckResponse,
    NodeCreateRequest,
    NodeResponse,
    NodeUpdateRequest,
    RelationshipCreateRequest,
    RelationshipResponse,
    SearchRequest,
    SearchResponse,
    SuccessResponse,
)
from src.multimodal_librarian.clients.database_factory import DatabaseClientError
from src.multimodal_librarian.services.knowledge_graph_service import (
    get_knowledge_graph_service,
)

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/knowledge-graph", tags=["Knowledge Graph"])


def get_kg_service():
    """Dependency to get knowledge graph service."""
    try:
        return get_knowledge_graph_service()
    except Exception as e:
        logger.error(f"Failed to get knowledge graph service: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"Knowledge graph service unavailable: {str(e)}"
        )


@router.get("/health", response_model=HealthCheckResponse)
async def health_check():
    """Check Neptune health and connectivity."""
    try:
        from src.multimodal_librarian.clients.database_factory import (
            get_database_factory,
        )
        factory = get_database_factory()
        
        # Perform health check
        health_result = factory.health_check()
        
        if health_result["overall_status"] in ["healthy", "degraded"]:
            # Get graph database info
            graph_info = health_result["services"].get("graph_db", {})
            
            return HealthCheckResponse(
                status=health_result["overall_status"],
                message="Neptune connection successful",
                neo4j_available=True,  # Keep field name for API compatibility
                connection_status=graph_info.get("status", "unknown"),
                database_info=graph_info.get("database_info", {}),
                last_check=graph_info.get("last_check", 0)
            )
        else:
            return HealthCheckResponse(
                status="unhealthy",
                message=f"Neptune connection failed: {health_result.get('error', 'Unknown error')}",
                neo4j_available=False,
                connection_status="unhealthy",
                last_check=0
            )
            
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return HealthCheckResponse(
            status="error",
            message=f"Health check error: {str(e)}",
            neo4j_available=False
        )


# Node Operations

@router.post("/nodes", response_model=NodeResponse)
async def create_node(
    request: NodeCreateRequest,
    kg_service = Depends(get_kg_service)
):
    """Create a new node in the knowledge graph."""
    try:
        node = kg_service.create_node(
            label=request.label,
            properties=request.properties,
            merge_on=request.merge_on
        )
        
        return NodeResponse(
            id=node["id"],
            labels=[request.label],  # Primary label
            properties=node
        )
        
    except DatabaseClientError as e:
        logger.error(f"Database connection error creating node: {e}")
        raise HTTPException(status_code=503, detail=f"Database connection error: {str(e)}")
    except Exception as e:
        logger.error(f"Error creating node: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create node: {str(e)}")


@router.get("/nodes/{node_id}", response_model=NodeResponse)
async def get_node(
    node_id: int = Path(..., description="Node ID"),
    kg_service = Depends(get_kg_service)
):
    """Get a node by ID."""
    try:
        node = kg_service.get_node_by_id(node_id)
        
        if not node:
            raise HTTPException(status_code=404, detail=f"Node {node_id} not found")
        
        return NodeResponse(
            id=node["id"],
            labels=node.get("labels", []),
            properties=node
        )
        
    except HTTPException:
        raise
    except DatabaseClientError as e:
        logger.error(f"Database connection error getting node: {e}")
        raise HTTPException(status_code=503, detail=f"Database connection error: {str(e)}")
    except Exception as e:
        logger.error(f"Error getting node {node_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get node: {str(e)}")


@router.get("/nodes", response_model=List[NodeResponse])
async def get_nodes(
    label: str = Query(..., description="Node label to filter by"),
    limit: int = Query(100, description="Maximum number of nodes to return", ge=1, le=1000),
    kg_service = Depends(get_kg_service)
):
    """Get nodes by label."""
    try:
        nodes = kg_service.get_nodes_by_label(label=label, limit=limit)
        
        return [
            NodeResponse(
                id=node["id"],
                labels=node.get("labels", []),
                properties=node
            )
            for node in nodes
        ]
        
    except DatabaseClientError as e:
        logger.error(f"Database connection error getting nodes: {e}")
        raise HTTPException(status_code=503, detail=f"Database connection error: {str(e)}")
    except Exception as e:
        logger.error(f"Error getting nodes: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get nodes: {str(e)}")


@router.put("/nodes/{node_id}", response_model=NodeResponse)
async def update_node(
    node_id: int = Path(..., description="Node ID"),
    request: NodeUpdateRequest = ...,
    kg_service = Depends(get_kg_service)
):
    """Update a node's properties."""
    try:
        node = kg_service.update_node(node_id, request.properties)
        
        return NodeResponse(
            id=node["id"],
            labels=node.get("labels", []),
            properties=node
        )
        
    except DatabaseClientError as e:
        logger.error(f"Database connection error updating node: {e}")
        raise HTTPException(status_code=503, detail=f"Database connection error: {str(e)}")
    except Exception as e:
        logger.error(f"Error updating node {node_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update node: {str(e)}")


@router.delete("/nodes/{node_id}", response_model=SuccessResponse)
async def delete_node(
    node_id: int = Path(..., description="Node ID"),
    delete_relationships: bool = Query(True, description="Whether to delete connected relationships"),
    kg_service = Depends(get_kg_service)
):
    """Delete a node and optionally its relationships."""
    try:
        success = kg_service.delete_node(node_id, delete_relationships)
        
        if success:
            return SuccessResponse(
                success=True,
                message=f"Node {node_id} deleted successfully"
            )
        else:
            raise HTTPException(status_code=404, detail=f"Node {node_id} not found")
        
    except HTTPException:
        raise
    except DatabaseClientError as e:
        logger.error(f"Database connection error deleting node: {e}")
        raise HTTPException(status_code=503, detail=f"Database connection error: {str(e)}")
    except Exception as e:
        logger.error(f"Error deleting node {node_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete node: {str(e)}")


# Relationship Operations

@router.post("/relationships", response_model=RelationshipResponse)
async def create_relationship(
    request: RelationshipCreateRequest,
    kg_service = Depends(get_kg_service)
):
    """Create a relationship between two nodes."""
    try:
        relationship = kg_service.create_relationship(
            from_node_id=request.from_node_id,
            to_node_id=request.to_node_id,
            relationship_type=request.relationship_type,
            properties=request.properties
        )
        
        return RelationshipResponse(
            id=relationship["id"],
            type=relationship["type"],
            properties=relationship,
            from_node_id=request.from_node_id,
            to_node_id=request.to_node_id
        )
        
    except DatabaseClientError as e:
        logger.error(f"Database connection error creating relationship: {e}")
        raise HTTPException(status_code=503, detail=f"Database connection error: {str(e)}")
    except Exception as e:
        logger.error(f"Error creating relationship: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create relationship: {str(e)}")


@router.get("/nodes/{node_id}/relationships", response_model=List[RelationshipResponse])
async def get_node_relationships(
    node_id: int = Path(..., description="Node ID"),
    direction: str = Query("both", description="Relationship direction", regex="^(incoming|outgoing|both)$"),
    kg_service = Depends(get_kg_service)
):
    """Get relationships for a node."""
    try:
        relationships = kg_service.get_node_relationships(node_id, direction)
        
        return [
            RelationshipResponse(
                id=rel["id"],
                type=rel["type"],
                properties=rel
            )
            for rel in relationships
        ]
        
    except DatabaseClientError as e:
        logger.error(f"Database connection error getting relationships: {e}")
        raise HTTPException(status_code=503, detail=f"Database connection error: {str(e)}")
    except Exception as e:
        logger.error(f"Error getting relationships for node {node_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get relationships: {str(e)}")


@router.delete("/relationships/{relationship_id}", response_model=SuccessResponse)
async def delete_relationship(
    relationship_id: int = Path(..., description="Relationship ID"),
    kg_service = Depends(get_kg_service)
):
    """Delete a relationship."""
    try:
        success = kg_service.delete_relationship(relationship_id)
        
        if success:
            return SuccessResponse(
                success=True,
                message=f"Relationship {relationship_id} deleted successfully"
            )
        else:
            raise HTTPException(status_code=404, detail=f"Relationship {relationship_id} not found")
        
    except HTTPException:
        raise
    except DatabaseClientError as e:
        logger.error(f"Database connection error deleting relationship: {e}")
        raise HTTPException(status_code=503, detail=f"Database connection error: {str(e)}")
    except Exception as e:
        logger.error(f"Error deleting relationship {relationship_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete relationship: {str(e)}")


# Query Operations

@router.post("/query", response_model=CypherQueryResponse)
async def execute_cypher_query(
    request: CypherQueryRequest,
    kg_service = Depends(get_kg_service)
):
    """Execute a custom Cypher query."""
    try:
        start_time = time.time()
        results = kg_service.execute_cypher(request.query, request.parameters)
        execution_time = (time.time() - start_time) * 1000  # Convert to milliseconds
        
        return CypherQueryResponse(
            results=results,
            execution_time_ms=execution_time
        )
        
    except DatabaseClientError as e:
        logger.error(f"Database connection error executing query: {e}")
        raise HTTPException(status_code=503, detail=f"Database connection error: {str(e)}")
    except Exception as e:
        logger.error(f"Error executing Cypher query: {e}")
        raise HTTPException(status_code=400, detail=f"Query execution failed: {str(e)}")


@router.post("/search", response_model=SearchResponse)
async def search_nodes(
    request: SearchRequest,
    kg_service = Depends(get_kg_service)
):
    """Search for nodes containing a term."""
    try:
        nodes = kg_service.search_nodes(
            search_term=request.search_term,
            labels=request.labels,
            properties=request.properties,
            limit=request.limit
        )
        
        node_responses = [
            NodeResponse(
                id=node["id"],
                labels=node.get("labels", []),
                properties=node
            )
            for node in nodes
        ]
        
        return SearchResponse(
            nodes=node_responses,
            total_count=len(node_responses)
        )
        
    except DatabaseClientError as e:
        logger.error(f"Database connection error searching nodes: {e}")
        raise HTTPException(status_code=503, detail=f"Database connection error: {str(e)}")
    except Exception as e:
        logger.error(f"Error searching nodes: {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


# Statistics

@router.get("/stats", response_model=GraphStatsResponse)
async def get_graph_statistics(
    kg_service = Depends(get_kg_service)
):
    """Get knowledge graph statistics."""
    try:
        stats = kg_service.get_graph_stats()
        
        return GraphStatsResponse(
            total_nodes=stats["total_nodes"],
            total_relationships=stats["total_relationships"],
            nodes_by_label=stats["nodes_by_label"],
            relationships_by_type=stats["relationships_by_type"]
        )
        
    except DatabaseClientError as e:
        logger.error(f"Database connection error getting stats: {e}")
        raise HTTPException(status_code=503, detail=f"Database connection error: {str(e)}")
    except Exception as e:
        logger.error(f"Error getting graph statistics: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get statistics: {str(e)}")


# Note: Exception handlers should be registered on the FastAPI app, not on routers.
# The endpoints above already handle DatabaseClientError and other exceptions
# by catching them and raising appropriate HTTPExceptions.