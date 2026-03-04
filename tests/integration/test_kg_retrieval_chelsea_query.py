"""
Integration Test for Knowledge Graph-Guided Retrieval - Chelsea Query Use Case.

This module tests the motivating use case for KG-guided retrieval:
"What did our team observe at Chelsea?"

The test verifies that:
1. The query is decomposed correctly (entities, actions, subjects extracted)
2. The "Chelsea" concept is found in the knowledge graph
3. Relevant chunks are retrieved via KG retrieval (not fallback)
4. The explanation correctly describes the retrieval path

Test File Location: tests/integration/test_kg_retrieval_chelsea_query.py

Validates:
- Requirement 1.1: Direct chunk retrieval via source_chunks
- Requirement 2.1: Graph-guided relationship retrieval
- Requirement 5.1: Explanation generation for retrieval path
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.multimodal_librarian.models.kg_retrieval import (
    KGRetrievalResult,
    QueryDecomposition,
    RetrievalSource,
    RetrievedChunk,
)
from src.multimodal_librarian.services.kg_retrieval_service import KGRetrievalService

logger = logging.getLogger(__name__)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def chelsea_concept_data():
    """
    Mock data representing the Chelsea concept in Neo4j.
    
    This simulates a concept node with source_chunks pointing to
    document chunks that mention Chelsea.
    """
    return {
        "concept_id": "concept-chelsea-001",
        "name": "Chelsea AI Ventures",
        "type": "ENTITY",
        "confidence": 0.95,
        "source_document": "doc-field-report-001",
        "source_chunks": "chunk-chelsea-001,chunk-chelsea-002,chunk-chelsea-003",
    }


@pytest.fixture
def chelsea_chunk_data():
    """
    Mock chunk data that would be stored in OpenSearch.
    
    These chunks contain content about observations at Chelsea.
    """
    return {
        "chunk-chelsea-001": {
            "chunk_id": "chunk-chelsea-001",
            "content": "Our team observed significant AI research progress at Chelsea AI Ventures. "
                      "The facility demonstrated advanced neural network architectures.",
            "source_id": "doc-field-report-001",
            "page_number": 5,
            "metadata": {"section": "Field Observations"}
        },
        "chunk-chelsea-002": {
            "chunk_id": "chunk-chelsea-002",
            "content": "At Chelsea, we noted innovative approaches to machine learning deployment. "
                      "The team there has developed novel optimization techniques.",
            "source_id": "doc-field-report-001",
            "page_number": 6,
            "metadata": {"section": "Technical Findings"}
        },
        "chunk-chelsea-003": {
            "chunk_id": "chunk-chelsea-003",
            "content": "Chelsea AI Ventures reported breakthrough results in natural language processing. "
                      "Our observations confirmed their claims about model performance.",
            "source_id": "doc-field-report-001",
            "page_number": 7,
            "metadata": {"section": "Results Summary"}
        },
    }


@pytest.fixture
def related_concept_data():
    """
    Mock data for concepts related to Chelsea via graph relationships.
    """
    return [
        {
            "concept_id": "concept-ai-research-001",
            "name": "AI Research",
            "type": "TOPIC",
            "source_chunks": "chunk-ai-001",
            "hop_distance": 1,
            "relationship_path": ["RELATED_TO"],
        },
        {
            "concept_id": "concept-ml-deployment-001",
            "name": "Machine Learning Deployment",
            "type": "TOPIC",
            "source_chunks": "chunk-ml-001",
            "hop_distance": 2,
            "relationship_path": ["RELATED_TO", "PART_OF"],
        },
    ]


@pytest.fixture
def mock_neo4j_client(chelsea_concept_data, related_concept_data):
    """
    Create a mock Neo4j client that returns Chelsea concept data.
    
    Handles the following query patterns from QueryDecomposer:
    1. Full-text index search (db.index.fulltext.queryNodes) with $search_terms
    2. CONTAINS fallback with $words list
    3. Vector similarity search (db.index.vector.queryNodes) with $embedding
    4. Related concepts traversal (MATCH path / *1..)
    """
    mock = MagicMock()
    
    async def execute_query(query: str, params: Dict[str, Any] = None):
        params = params or {}
        query_lower = query.lower()
        
        # Handle full-text index search (primary path in _find_entity_matches)
        if "fulltext.querynodes" in query_lower:
            search_terms = params.get("search_terms", "").lower()
            if "chelsea" in search_terms:
                return [{**chelsea_concept_data, "match_score": 2.5}]
            return []
        
        # Handle CONTAINS fallback (secondary path in _find_entity_matches)
        if "contains" in query_lower:
            words = params.get("words", [])
            if any("chelsea" in w.lower() for w in words):
                return [{**chelsea_concept_data, "matched_word": "chelsea", "name_length": len(chelsea_concept_data["name"])}]
            return []
        
        # Handle vector similarity search (_find_semantic_matches)
        if "vector.querynodes" in query_lower:
            return [{**chelsea_concept_data, "similarity_score": 0.85}]
        
        # Handle related concepts query
        if "match path" in query_lower or "*1.." in query_lower:
            concept_id = params.get("concept_id", "")
            if concept_id == chelsea_concept_data["concept_id"]:
                return related_concept_data
            return []
        
        # Default: return empty
        return []
    
    mock.execute_query = AsyncMock(side_effect=execute_query)
    return mock


@pytest.fixture
def mock_vector_client(chelsea_chunk_data):
    """
    Create a mock vector client that returns Chelsea chunk content.
    """
    mock = MagicMock()
    
    async def get_chunk_by_id(chunk_id: str):
        return chelsea_chunk_data.get(chunk_id)
    
    async def semantic_search_async(query: str, top_k: int = 10):
        # Return semantic search results (for fallback/augmentation)
        return [
            {
                "chunk_id": "chunk-semantic-001",
                "content": "General AI content from semantic search.",
                "score": 0.75,
            }
        ]
    
    mock.get_chunk_by_id = AsyncMock(side_effect=get_chunk_by_id)
    mock.semantic_search_async = AsyncMock(side_effect=semantic_search_async)
    mock.is_connected = MagicMock(return_value=True)
    # Prevent MagicMock from auto-creating get_chunks_by_ids, which would
    # cause ChunkResolver's batch path to silently return empty results
    del mock.get_chunks_by_ids
    
    return mock


@pytest.fixture
def mock_model_client():
    """
    Create a mock model client for embedding generation.
    """
    mock = MagicMock()
    
    async def generate_embeddings(texts: List[str]):
        # Return mock embeddings (384-dimensional)
        return [[0.1 + (i * 0.01)] * 384 for i in range(len(texts))]
    
    mock.generate_embeddings = AsyncMock(side_effect=generate_embeddings)
    return mock


@pytest.fixture
def kg_service(mock_neo4j_client, mock_vector_client, mock_model_client):
    """
    Create KGRetrievalService with mocked dependencies.
    """
    return KGRetrievalService(
        neo4j_client=mock_neo4j_client,
        vector_client=mock_vector_client,
        model_client=mock_model_client,
        cache_ttl_seconds=300,
        max_results=15,
        max_hops=2,
        augmentation_threshold=3,
    )


# =============================================================================
# Test: Chelsea Query Integration
# =============================================================================

class TestChelseaQueryIntegration:
    """
    Integration tests for the Chelsea query use case.
    
    Tests the complete flow from query to results for the motivating
    use case: "What did our team observe at Chelsea?"
    
    Validates: Requirements 1.1, 2.1, 5.1
    """
    
    @pytest.mark.asyncio
    async def test_chelsea_query_finds_relevant_chunks(
        self,
        kg_service,
        chelsea_chunk_data,
    ):
        """
        Test that the Chelsea query finds relevant chunks via KG retrieval.
        
        This is the primary motivating use case for KG-guided retrieval.
        The query "What did our team observe at Chelsea?" should:
        1. Recognize "Chelsea" as a named entity
        2. Find the Chelsea concept in Neo4j
        3. Retrieve chunks from the concept's source_chunks
        4. NOT use fallback (semantic search)
        
        Validates: Requirement 1.1 - Direct chunk retrieval via source_chunks
        """
        query = "What did our team observe at Chelsea?"
        
        result = await kg_service.retrieve(query)
        
        # Verify KG retrieval was used (not fallback)
        assert result.fallback_used is False, (
            f"Expected KG retrieval, but fallback was used. "
            f"Reason: {result.metadata.get('fallback_reason', 'unknown')}"
        )
        
        # Verify chunks were retrieved
        assert len(result.chunks) > 0, "Expected at least one chunk to be retrieved"
        
        # Verify at least one chunk is from direct concept retrieval
        direct_chunks = [
            c for c in result.chunks 
            if c.source == RetrievalSource.DIRECT_CONCEPT
        ]
        assert len(direct_chunks) > 0, (
            "Expected at least one chunk from direct concept retrieval. "
            f"Sources found: {[c.source.value for c in result.chunks]}"
        )
        
        # Verify chunk content mentions Chelsea
        chelsea_mentioned = any(
            "chelsea" in chunk.content.lower() 
            for chunk in result.chunks
        )
        assert chelsea_mentioned, (
            "Expected at least one chunk to mention Chelsea. "
            f"Chunk contents: {[c.content[:50] for c in result.chunks]}"
        )
        
        logger.info(
            f"Chelsea query retrieved {len(result.chunks)} chunks, "
            f"{len(direct_chunks)} from direct concept retrieval"
        )

    @pytest.mark.asyncio
    async def test_chelsea_query_decomposition(
        self,
        kg_service,
        chelsea_concept_data,
    ):
        """
        Test that the Chelsea query is decomposed correctly.
        
        The query "What did our team observe at Chelsea?" should extract:
        - Entities: ["Chelsea AI Ventures"] (from KG match)
        - Actions: ["observe"] or ["observed"]
        - Subjects: ["our team"]
        
        Validates: Requirements 4.1, 4.2, 4.3
        """
        query = "What did our team observe at Chelsea?"
        
        result = await kg_service.retrieve(query)
        
        # Verify query decomposition exists
        assert result.query_decomposition is not None, (
            "Expected query decomposition in result"
        )
        
        decomposition = result.query_decomposition
        
        # Verify original query is preserved
        assert decomposition.original_query == query
        
        # Verify entities were extracted (Chelsea should be found)
        assert decomposition.has_kg_matches is True, (
            "Expected KG matches for Chelsea concept"
        )
        assert len(decomposition.entities) > 0, (
            "Expected at least one entity to be extracted"
        )
        
        # Verify Chelsea-related entity was found
        chelsea_entity_found = any(
            "chelsea" in entity.lower() 
            for entity in decomposition.entities
        )
        assert chelsea_entity_found, (
            f"Expected Chelsea entity in decomposition. "
            f"Found entities: {decomposition.entities}"
        )
        
        # Verify actions were extracted
        assert len(decomposition.actions) > 0, (
            "Expected action words to be extracted"
        )
        action_found = any(
            action in ["observe", "observed"] 
            for action in decomposition.actions
        )
        assert action_found, (
            f"Expected 'observe' or 'observed' in actions. "
            f"Found actions: {decomposition.actions}"
        )
        
        # Verify subjects were extracted
        assert len(decomposition.subjects) > 0, (
            "Expected subject references to be extracted"
        )
        subject_found = "our team" in decomposition.subjects
        assert subject_found, (
            f"Expected 'our team' in subjects. "
            f"Found subjects: {decomposition.subjects}"
        )
        
        logger.info(
            f"Query decomposition: entities={decomposition.entities}, "
            f"actions={decomposition.actions}, subjects={decomposition.subjects}"
        )

    @pytest.mark.asyncio
    async def test_chelsea_query_explanation_generated(
        self,
        kg_service,
    ):
        """
        Test that an explanation is generated for the Chelsea query.
        
        The explanation should describe how chunks were retrieved,
        including the concept name that provided the chunks.
        
        Validates: Requirement 5.1 - Explanation generation
        """
        query = "What did our team observe at Chelsea?"
        
        result = await kg_service.retrieve(query, include_explanation=True)
        
        # Verify explanation was generated
        assert result.explanation, "Expected explanation to be generated"
        assert len(result.explanation) > 0, "Expected non-empty explanation"
        
        # Explanation should mention the retrieval method or concept
        explanation_lower = result.explanation.lower()
        
        # Should mention knowledge graph or concept-based retrieval
        kg_mentioned = any(
            term in explanation_lower 
            for term in ["knowledge graph", "concept", "chelsea", "direct"]
        )
        assert kg_mentioned, (
            f"Expected explanation to mention KG retrieval. "
            f"Explanation: {result.explanation}"
        )
        
        logger.info(f"Generated explanation: {result.explanation[:200]}...")

    @pytest.mark.asyncio
    async def test_chelsea_query_retrieval_metadata(
        self,
        kg_service,
    ):
        """
        Test that retrieval metadata is complete for the Chelsea query.
        
        The result should include:
        - Retrieval timing
        - Stage 1 and Stage 2 chunk counts
        - Cache statistics
        
        Validates: Requirements 3.5, 8.5
        """
        query = "What did our team observe at Chelsea?"
        
        result = await kg_service.retrieve(query)
        
        # Verify timing metadata
        assert result.retrieval_time_ms >= 0, (
            "Expected non-negative retrieval time"
        )
        
        # Verify stage counts
        assert result.stage1_chunk_count >= 0, (
            "Expected non-negative Stage 1 chunk count"
        )
        assert result.stage2_chunk_count >= 0, (
            "Expected non-negative Stage 2 chunk count"
        )
        
        # If not fallback, Stage 1 should have found chunks
        if not result.fallback_used:
            assert result.stage1_chunk_count > 0, (
                "Expected Stage 1 to find chunks when not using fallback"
            )
        
        # Verify all chunks have valid source metadata
        for chunk in result.chunks:
            assert chunk.source is not None, (
                f"Chunk {chunk.chunk_id} missing source metadata"
            )
            assert chunk.source in RetrievalSource, (
                f"Chunk {chunk.chunk_id} has invalid source: {chunk.source}"
            )
        
        logger.info(
            f"Retrieval metadata: time={result.retrieval_time_ms}ms, "
            f"stage1={result.stage1_chunk_count}, stage2={result.stage2_chunk_count}"
        )

    @pytest.mark.asyncio
    async def test_chelsea_query_no_fallback_when_concept_found(
        self,
        kg_service,
        mock_neo4j_client,
    ):
        """
        Test that fallback is NOT used when Chelsea concept is found.
        
        This verifies the core value proposition of KG-guided retrieval:
        when a named entity like "Chelsea" is recognized in the KG,
        we should use direct chunk pointers instead of semantic search.
        
        Validates: Requirements 1.1, 6.2
        """
        query = "What did our team observe at Chelsea?"
        
        result = await kg_service.retrieve(query)
        
        # Primary assertion: fallback should NOT be used
        assert result.fallback_used is False, (
            f"Fallback should NOT be used when Chelsea concept is found. "
            f"Fallback reason: {result.metadata.get('fallback_reason', 'N/A')}"
        )
        
        # Verify Neo4j was queried (concept lookup happened)
        assert mock_neo4j_client.execute_query.called, (
            "Expected Neo4j to be queried for concept lookup"
        )
        
        # Verify chunks came from KG, not semantic fallback
        fallback_chunks = [
            c for c in result.chunks 
            if c.source == RetrievalSource.SEMANTIC_FALLBACK
        ]
        assert len(fallback_chunks) == 0, (
            f"Expected no fallback chunks, but found {len(fallback_chunks)}"
        )
        
        logger.info("Verified: KG retrieval used, fallback NOT triggered")

    @pytest.mark.asyncio
    async def test_chelsea_query_kg_metadata_present(
        self,
        kg_service,
    ):
        """
        Test that KG metadata is present in the Chelsea query response.
        
        The response metadata should include:
        - concepts_matched: Number of concepts matched from the query
        - retrieval_source: Source of each chunk (DIRECT_CONCEPT, RELATED_CONCEPT, etc.)
        
        This test validates that KG-guided retrieval provides proper metadata
        for downstream consumers (RAG service, Chat Router) to use.
        
        Validates: Requirement 6.1 - KG retrieval returns relevant chunks with metadata
        """
        query = "What did our team observe at Chelsea?"
        
        result = await kg_service.retrieve(query)
        
        # Verify KG metadata is present in result.metadata
        assert result.metadata is not None, "Expected metadata in result"
        
        # Verify concepts_matched is present and valid
        assert "concepts_matched" in result.metadata, (
            f"Expected 'concepts_matched' in metadata. "
            f"Available keys: {list(result.metadata.keys())}"
        )
        concepts_matched = result.metadata["concepts_matched"]
        assert isinstance(concepts_matched, int), (
            f"Expected concepts_matched to be int, got {type(concepts_matched)}"
        )
        assert concepts_matched > 0, (
            "Expected at least one concept to be matched for Chelsea query"
        )
        
        # Verify each chunk has retrieval_source metadata
        for chunk in result.chunks:
            assert chunk.source is not None, (
                f"Chunk {chunk.chunk_id} missing retrieval source"
            )
            # Verify source is a valid RetrievalSource enum value
            assert isinstance(chunk.source, RetrievalSource), (
                f"Chunk {chunk.chunk_id} has invalid source type: {type(chunk.source)}"
            )
            # Verify source value is one of the expected types
            valid_sources = [
                RetrievalSource.DIRECT_CONCEPT,
                RetrievalSource.RELATED_CONCEPT,
                RetrievalSource.SEMANTIC_AUGMENT,
                RetrievalSource.SEMANTIC_FALLBACK,
            ]
            assert chunk.source in valid_sources, (
                f"Chunk {chunk.chunk_id} has unexpected source: {chunk.source}"
            )
        
        # For Chelsea query, we expect at least one DIRECT_CONCEPT chunk
        direct_concept_chunks = [
            c for c in result.chunks 
            if c.source == RetrievalSource.DIRECT_CONCEPT
        ]
        assert len(direct_concept_chunks) > 0, (
            "Expected at least one chunk with DIRECT_CONCEPT retrieval source. "
            f"Sources found: {[c.source.value for c in result.chunks]}"
        )
        
        logger.info(
            f"KG metadata verified: concepts_matched={concepts_matched}, "
            f"chunks with sources: {[(c.chunk_id, c.source.value) for c in result.chunks]}"
        )


# =============================================================================
# Test: Edge Cases
# =============================================================================

class TestChelseaQueryEdgeCases:
    """
    Edge case tests for the Chelsea query use case.
    """
    
    @pytest.mark.asyncio
    async def test_chelsea_query_case_insensitive(
        self,
        kg_service,
    ):
        """
        Test that Chelsea query works regardless of case.
        
        Queries like "chelsea", "CHELSEA", "Chelsea" should all work.
        """
        queries = [
            "What did our team observe at Chelsea?",
            "What did our team observe at chelsea?",
            "What did our team observe at CHELSEA?",
        ]
        
        for query in queries:
            result = await kg_service.retrieve(query)
            
            # Should find Chelsea concept regardless of case
            assert result.query_decomposition is not None
            assert result.query_decomposition.has_kg_matches is True, (
                f"Expected KG matches for query: {query}"
            )
        
        logger.info("Verified: Chelsea query is case-insensitive")

    @pytest.mark.asyncio
    async def test_chelsea_query_with_variations(
        self,
        kg_service,
    ):
        """
        Test Chelsea query with different phrasings.
        """
        queries = [
            "What did our team observe at Chelsea?",
            "Tell me about observations at Chelsea",
            "Chelsea findings from our team",
            "What was found at Chelsea AI Ventures?",
        ]
        
        for query in queries:
            result = await kg_service.retrieve(query)
            
            # All variations should find Chelsea-related content
            # (may use fallback for some variations if concept not matched)
            assert result is not None
            assert isinstance(result, KGRetrievalResult)
        
        logger.info("Verified: Chelsea query works with variations")


# =============================================================================
# Test: Performance
# =============================================================================

class TestChelseaQueryPerformance:
    """
    Performance tests for the Chelsea query use case.
    """
    
    @pytest.mark.asyncio
    async def test_chelsea_query_completes_within_timeout(
        self,
        kg_service,
    ):
        """
        Test that Chelsea query completes within reasonable time.
        
        Validates: Requirement 8.1 - Stage 1 within 500ms
        """
        query = "What did our team observe at Chelsea?"
        
        result = await kg_service.retrieve(query)
        
        # With mocked clients, should be very fast
        # In production, target is 500ms for Stage 1
        assert result.retrieval_time_ms < 5000, (
            f"Query took too long: {result.retrieval_time_ms}ms"
        )
        
        logger.info(f"Chelsea query completed in {result.retrieval_time_ms}ms")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
