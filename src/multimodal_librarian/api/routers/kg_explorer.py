"""
KG Explorer API Router

Provides endpoints for the Knowledge Graph Explorer frontend:
- Neighborhood queries (landing view + ego graph)
- Semantic concept search

Validates: Requirements 15.1, 15.2, 15.3, 15.4, 15.5
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..dependencies.services import (
    get_kg_query_engine_optional,
    get_model_server_client_optional,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/knowledge-graph",
    tags=["kg-explorer"],
)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class GraphNode(BaseModel):
    """A concept node in the knowledge graph neighborhood."""

    name: str
    source_document: Optional[str] = None
    source_title: Optional[str] = None
    source_type: str = "document"  # "document", "conversation", "citation", or "external"
    concept_type: Optional[str] = None
    degree: int = 0


class GraphEdge(BaseModel):
    """A directed relationship between two concept nodes."""

    source: str
    target: str
    relationship_type: str


class NeighborhoodResponse(BaseModel):
    """Response for the neighborhood endpoint."""

    focus_concept: Optional[str] = None
    nodes: List[GraphNode]
    edges: List[GraphEdge]
    is_landing: bool = False


class ConceptMatch(BaseModel):
    """A single concept search result."""

    name: str
    source_document: Optional[str] = None
    similarity_score: float
    degree: int = 0


class ConceptSearchResponse(BaseModel):
    """Response for the concept search endpoint."""

    query: str
    matches: List[ConceptMatch]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/search/concepts",
    response_model=ConceptSearchResponse,
)
async def search_concepts(
    query: str = Query(..., min_length=1),
    source_id: Optional[str] = Query(default=None),
    kg_query_engine=Depends(get_kg_query_engine_optional),
    model_server_client=Depends(get_model_server_client_optional),
) -> ConceptSearchResponse:
    """Search for concepts by semantic similarity.

    Embeds the *query* using the model server and compares against
    concept name embeddings stored in Neo4j.  Returns at most 10
    matches ranked by descending similarity.

    Returns 503 when the graph database or model server is unavailable.

    Validates: Requirements 15.2, 15.4, 15.5
    """
    if kg_query_engine is None:
        raise HTTPException(
            status_code=503,
            detail="Knowledge graph service unavailable",
        )
    if model_server_client is None:
        raise HTTPException(
            status_code=503,
            detail="Model server unavailable for embedding generation",
        )

    try:
        embeddings = await model_server_client.generate_embeddings([query])
        if not embeddings or len(embeddings) == 0:
            raise ValueError("Empty embedding returned")
        query_embedding = embeddings[0]
    except Exception as e:
        logger.error(f"Failed to generate query embedding: {e}")
        raise HTTPException(
            status_code=503,
            detail="Failed to generate query embedding",
        )

    results = await kg_query_engine.search_concepts_by_embedding(
        query_embedding=query_embedding,
        source_id=source_id,
        limit=10,
    )

    matches = [
        ConceptMatch(
            name=r["name"],
            source_document=r["source_document"],
            similarity_score=float(r["similarity_score"]),
            degree=int(r["degree"]),
        )
        for r in results
    ]

    return ConceptSearchResponse(query=query, matches=matches)


@router.get(
    "/{source_id}/neighborhood",
    response_model=NeighborhoodResponse,
)
async def get_neighborhood(
    source_id: str,
    focus_concept: Optional[str] = Query(default=None),
    max_nodes: int = Query(default=50, le=100, ge=1),
    kg_query_engine=Depends(get_kg_query_engine_optional),
) -> NeighborhoodResponse:
    """Return a bounded graph neighborhood for the KG Explorer.

    If *focus_concept* is omitted the endpoint returns a **landing view**
    with the top 10 concepts by degree for the given source.

    If *focus_concept* is provided the endpoint returns the **ego graph**
    around that concept, capped at *max_nodes*.

    Returns 503 when the graph database is unavailable.

    Validates: Requirements 15.1, 15.3
    """
    if kg_query_engine is None:
        raise HTTPException(
            status_code=503,
            detail="Knowledge graph service unavailable",
        )

    # Since the source_id fix, Neo4j concepts now store the UUID5
    # source_id directly as source_document (matching knowledge_sources.id).
    # No resolution needed — pass source_id straight through.

    data = await kg_query_engine.get_neighborhood(
        source_id=source_id,
        focus_concept=focus_concept,
        max_nodes=max_nodes,
    )

    # Resolve titles for source_document UUIDs so the frontend can
    # display human-readable names instead of raw IDs.
    source_ids = list({n["source_document"] for n in data.get("nodes", []) if n.get("source_document")})
    title_map = await _resolve_source_titles(source_ids)

    nodes = [
        GraphNode(
            name=n["name"],
            source_document=n["source_document"],
            source_title=title_map.get(n.get("source_document", "")),
            source_type=_infer_source_type(
                n.get("source_document", ""),
                concept_type=n.get("concept_type"),
            ),
            concept_type=n.get("concept_type"),
            degree=int(n.get("degree", 0)),
        )
        for n in data.get("nodes", [])
    ]
    edges = [
        GraphEdge(
            source=e["source"],
            target=e["target"],
            relationship_type=e["relationship_type"],
        )
        for e in data.get("edges", [])
    ]

    return NeighborhoodResponse(
        focus_concept=data.get("focus_concept"),
        nodes=nodes,
        edges=edges,
        is_landing=data.get("is_landing", False),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _infer_source_type(source_document: str, concept_type: Optional[str] = None) -> str:
    """Determine source type from the source_document identifier and concept type.

    Known external KBs (conceptnet, yago, …) map to "external".
    CITED_SOURCE concept types map to "citation".
    Everything else (UUIDs from knowledge_sources) maps to
    "document".

    The frontend uses source_type for color coding:
      document → blue (#4A90D9)
      external → green (#50C878)
      citation → orange (frontend-defined)
    """
    if concept_type and concept_type.upper() == "CITED_SOURCE":
        return "citation"

    if not source_document:
        return "document"

    external_sources = {
        "conceptnet", "yago", "umls",
        "wikidata", "dbpedia", "wordnet",
    }
    if source_document.lower() in external_sources:
        return "external"

    return "document"


async def _resolve_source_titles(source_ids: list) -> dict:
    """Batch-resolve source_document UUIDs to human-readable titles.

    Looks up knowledge_sources by both ``id`` (for regular docs) and
    ``metadata->>'source_thread_id'`` (for conversations where Neo4j
    stores the raw thread_id).  Returns a dict mapping each input
    source_id string to its title, or omits it if not found.
    """
    if not source_ids:
        return {}

    titles: dict = {}
    try:
        from ...database.connection import get_async_connection
        conn = await get_async_connection()
        try:
            # Direct ID match (regular documents)
            rows = await conn.fetch("""
                SELECT id::text AS sid, title
                FROM multimodal_librarian.knowledge_sources
                WHERE id = ANY($1::uuid[])
            """, source_ids)
            for r in rows:
                if r["title"]:
                    titles[r["sid"]] = r["title"]

            # Thread-id match (conversations stored under raw thread_id)
            missing = [s for s in source_ids if s not in titles]
            if missing:
                rows = await conn.fetch("""
                    SELECT metadata->>'source_thread_id' AS tid, title
                    FROM multimodal_librarian.knowledge_sources
                    WHERE source_type = 'CONVERSATION'::multimodal_librarian.source_type
                      AND metadata->>'source_thread_id' = ANY($1::text[])
                """, missing)
                for r in rows:
                    if r["tid"] and r["title"]:
                        titles[r["tid"]] = r["title"]
        finally:
            await conn.close()
    except Exception as e:
        logger.debug(f"Could not resolve source titles: {e}")

    return titles


async def _resolve_source_id(source_id: str) -> str:
    """Resolve a knowledge_sources.id to the actual Neo4j source_document key.

    For conversation documents, knowledge_sources.id is a UUID5 derived from
    the thread_id, but Neo4j concepts and vector store chunks use the raw
    thread_id as their source identifier.  This function looks up the
    source_thread_id from metadata and returns it when applicable.

    For regular (non-conversation) documents, returns source_id unchanged.
    """
    try:
        from ...database.connection import get_async_connection
        conn = await get_async_connection()
        try:
            row = await conn.fetchrow("""
                SELECT source_type::text AS stype,
                       metadata->>'source_thread_id' AS thread_id
                FROM multimodal_librarian.knowledge_sources
                WHERE id = $1::uuid
            """, source_id)
            if (row
                    and (row['stype'] or '').upper() == 'CONVERSATION'
                    and row['thread_id']):
                return row['thread_id']
        finally:
            await conn.close()
    except Exception as e:
        logger.debug(
            f"Could not resolve source_id {source_id}: {e}"
        )
    return source_id
