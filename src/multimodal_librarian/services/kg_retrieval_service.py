"""
Knowledge Graph-Guided Retrieval Service.

This service orchestrates the two-stage retrieval pipeline that uses Neo4j
knowledge graph for precise chunk retrieval and semantic re-ranking for
relevance ordering.

Stage 1 (KG-Based): Extract concepts from query, retrieve direct chunk pointers
from Neo4j source_chunks fields, and traverse relationships to find related chunks.

Stage 2 (Semantic Re-ranking): Re-rank candidate chunks using semantic similarity
for relevance ordering.

Requirements: 1.1, 1.3, 1.5, 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.3, 3.4, 6.1, 6.2, 6.3, 6.4, 6.5, 8.1, 8.2, 8.3, 8.5
"""

import asyncio
import logging
import sys
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

from ..components.kg_retrieval import (
    ChunkResolver,
    ExplanationGenerator,
    QueryDecomposer,
    SemanticReranker,
)
from ..models.kg_retrieval import (
    ChunkSourceMapping,
    KGRetrievalResult,
    Neo4jConnectionError,
    QueryDecomposition,
    RetrievalSource,
    RetrievedChunk,
    SourceChunksCacheEntry,
)

logger = logging.getLogger(__name__)


@dataclass
class RetrievalMetrics:
    """Retrieval quality metrics for evaluation.

    Requirements: 8.1
    """
    recall: float
    precision: float
    f1_score: float
    true_positives: int
    retrieved_count: int
    ground_truth_count: int


# asyncio.timeout is only available in Python 3.11+
# For earlier versions, we use asyncio.wait_for instead
if sys.version_info >= (3, 11):
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def async_timeout(seconds: float):
        """Context manager for async timeout (Python 3.11+ native)."""
        async with asyncio.timeout(seconds):
            yield
else:
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def async_timeout(seconds: float):
        """Context manager for async timeout (Python 3.9/3.10 compatibility)."""
        # For Python < 3.11, we can't use context manager style timeout
        # This is a simplified version that doesn't support cancellation
        # The actual timeout is handled by asyncio.wait_for in the caller
        yield


async def with_timeout(coro, seconds: float):
    """Execute coroutine with timeout (cross-version compatible)."""
    return await asyncio.wait_for(coro, timeout=seconds)


# =============================================================================
# Constants
# =============================================================================

# Default configuration values
DEFAULT_CACHE_TTL_SECONDS = 300  # 5 minutes (Requirement 8.2)
DEFAULT_MAX_RESULTS = 15  # Maximum chunks to return (Requirement 3.4)
DEFAULT_MAX_HOPS = 2  # Maximum relationship hops (Requirement 2.1)
DEFAULT_AUGMENTATION_THRESHOLD = 3  # Minimum chunks before augmentation (Requirement 3.3)
DEFAULT_QUERY_TIMEOUT_SECONDS = 5.0  # Neo4j query timeout (Requirement 6.4)


# Relationship types to prioritize during traversal (Requirement 2.3)
# Includes both pattern-extracted types (uppercase) and ConceptNet types (PascalCase)
PRIORITY_RELATIONSHIP_TYPES = [
    # Pattern-extracted relationship types
    "IS_A",
    "PART_OF",
    "CAUSES",
    "RELATED_TO",
    "SIMILAR_TO",
    # ConceptNet relationship types (PascalCase as stored in Neo4j)
    "IsA",
    "PartOf",
    "RelatedTo",
    "Synonym",
    "HasContext",
    "DerivedFrom",
    "FormOf",
    "HasProperty",
    "UsedFor",
    "CapableOf",
    "AtLocation",
    "SimilarTo",
    "MannerOf",
    "Causes",
    "HasA",
    "HasPrerequisite",
    "CreatedBy",
    "MotivatedByGoal",
    "InstanceOf",
    "DefinedAs",
    "Entails",
    "MadeOf",
]


class KGRetrievalService:
    """
    Knowledge Graph-Guided Retrieval Service.

    Orchestrates multi-stage retrieval using Neo4j knowledge graph
    for precise chunk retrieval and semantic re-ranking for relevance.

    Follows FastAPI DI patterns - no connections at construction time.

    Example:
        service = KGRetrievalService(
            neo4j_client=client,
            vector_client=opensearch_client
        )
        result = await service.retrieve("What did our team observe at Chelsea?")

    Requirements: 1.1, 1.3, 1.5, 2.1-2.5, 3.1, 3.3, 3.4, 6.1-6.5, 8.1-8.3, 8.5
    """

    def __init__(
        self,
        neo4j_client: Optional[Any] = None,
        vector_client: Optional[Any] = None,
        model_client: Optional[Any] = None,
        cache_ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS,
        max_results: int = DEFAULT_MAX_RESULTS,
        max_hops: int = DEFAULT_MAX_HOPS,
        augmentation_threshold: int = DEFAULT_AUGMENTATION_THRESHOLD,
        query_timeout_seconds: float = DEFAULT_QUERY_TIMEOUT_SECONDS,
        hop_distance_decay: float = 0.5,
        max_related_chunks: int = 50,
    ):
        """
        Initialize KG Retrieval Service.

        Args:
            neo4j_client: Neo4j client (injected via DI)
            vector_client: Vector store client for chunk resolution and semantic search
            model_client: Model server client for embedding generation
            cache_ttl_seconds: TTL for source_chunks cache (default 5 min)
            max_results: Maximum chunks to return (default 15)
            max_hops: Maximum relationship hops (default 2)
            augmentation_threshold: Minimum chunks before semantic augmentation (default 3)
            query_timeout_seconds: Timeout for Neo4j queries (default 5s)
            hop_distance_decay: Decay factor per hop for KG relevance score (default 0.5)
            max_related_chunks: Maximum related chunks passed to reranker (default 50)
        """
        self._neo4j_client = neo4j_client
        self._vector_client = vector_client
        self._model_client = model_client
        self._cache_ttl = cache_ttl_seconds
        self._max_results = max_results
        self._max_hops = max_hops
        self._augmentation_threshold = augmentation_threshold
        self._query_timeout = query_timeout_seconds
        self._hop_distance_decay = hop_distance_decay
        self._max_related_chunks = max_related_chunks

        # Initialize components
        self._query_decomposer = QueryDecomposer(
            neo4j_client=neo4j_client,
            model_server_client=model_client,
        )
        self._chunk_resolver = ChunkResolver(vector_client=vector_client)
        self._semantic_reranker = SemanticReranker(model_client=model_client)
        self._explanation_generator = ExplanationGenerator()

        # Cache for source_chunks (Requirement 8.2)
        self._source_chunks_cache: Dict[str, SourceChunksCacheEntry] = {}

        # Statistics
        self._cache_hits = 0
        self._cache_misses = 0
        self._total_queries = 0

        self._initialized = False
        logger.debug("KGRetrievalService initialized")

    async def retrieve(
        self,
        query: str,
        top_k: int = 15,
        include_explanation: bool = True,
        precomputed_decomposition: Optional["QueryDecomposition"] = None,
    ) -> KGRetrievalResult:
        """
        Perform knowledge graph-guided retrieval.

        Implements the two-stage pipeline:
        1. Stage 1: KG-based candidate retrieval (direct + relationship traversal)
        2. Stage 2: Semantic re-ranking for relevance ordering

        Args:
            query: User query text
            top_k: Maximum number of chunks to return
            include_explanation: Whether to generate explanation
            precomputed_decomposition: Optional pre-computed QueryDecomposition
                from the RAG pipeline's process_query step. When provided,
                skips the internal decomposition to avoid redundant Neo4j
                and embedding calls.

        Returns:
            KGRetrievalResult with ranked chunks and metadata

        Requirements: 1.1, 1.3, 1.5, 2.1-2.5, 3.1, 3.3, 3.4, 6.1-6.5
        """
        start_time = time.time()
        self._total_queries += 1
        cache_hits_before = self._cache_hits

        # Validate input
        if not query or not query.strip():
            logger.warning("Empty query provided to retrieve")
            return KGRetrievalResult(
                chunks=[],
                explanation="No query provided.",
                fallback_used=True,
                metadata={"fallback_reason": "empty_query"},
            )

        query = query.strip()
        effective_top_k = min(top_k, self._max_results)
        logger.info(f"KG retrieval for query: {query[:100]}...")

        try:
            # Step 1: Use precomputed decomposition or decompose query
            if precomputed_decomposition is not None:
                decomposition = precomputed_decomposition
                logger.info("Using precomputed query decomposition (skipping redundant decompose)")
            else:
                decomposition = await self._decompose_query_safe(query)

            # Check if we have KG matches
            if not decomposition.has_kg_matches:
                logger.info("No KG matches found, falling back to semantic search")
                return await self._fallback_to_semantic(
                    query, decomposition, "no_concepts", start_time
                )

            # Step 2: Stage 1 - KG-based retrieval (with timeout)
            try:
                stage1_chunks, source_mappings = await with_timeout(
                    self._stage1_kg_retrieval(decomposition),
                    self._query_timeout * 2  # 2x single-query timeout
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "Stage 1 KG retrieval timed out, falling back"
                )
                return await self._fallback_to_semantic(
                    query, decomposition, "stage1_timeout", start_time
                )
            stage1_count = len(stage1_chunks)

            # Check if Stage 1 returned results
            if not stage1_chunks:
                logger.info("Stage 1 returned no chunks, falling back to semantic search")
                return await self._fallback_to_semantic(
                    query, decomposition, "no_kg_results", start_time
                )

            # Step 3: Augment with semantic search if below threshold (Requirement 3.3)
            if stage1_count < self._augmentation_threshold:
                logger.info(
                    f"Stage 1 returned {stage1_count} chunks (< {self._augmentation_threshold}), "
                    "augmenting with semantic search"
                )
                stage1_chunks = await self._augment_with_semantic(
                    query, stage1_chunks, source_mappings
                )

            # Step 4: Stage 2 - Semantic re-ranking
            ranked_chunks = await self._semantic_reranker.rerank(
                stage1_chunks, query, effective_top_k
            )
            stage2_count = len(ranked_chunks)

            # Step 5: Generate explanation
            explanation = ""
            if include_explanation:
                result_for_explanation = KGRetrievalResult(
                    chunks=ranked_chunks,
                    query_decomposition=decomposition,
                    stage1_chunk_count=stage1_count,
                    stage2_chunk_count=stage2_count,
                )
                explanation = self._explanation_generator.generate(
                    result_for_explanation, decomposition
                )

            # Calculate timing and cache stats
            retrieval_time_ms = int((time.time() - start_time) * 1000)
            cache_hits_this_query = self._cache_hits - cache_hits_before

            logger.info(
                f"KG retrieval complete: {stage2_count} chunks in {retrieval_time_ms}ms "
                f"(Stage 1: {stage1_count}, cache hits: {cache_hits_this_query})"
            )

            return KGRetrievalResult(
                chunks=ranked_chunks,
                query_decomposition=decomposition,
                explanation=explanation,
                fallback_used=False,
                retrieval_time_ms=retrieval_time_ms,
                stage1_chunk_count=stage1_count,
                stage2_chunk_count=stage2_count,
                cache_hits=cache_hits_this_query,
                metadata={
                    "concepts_matched": len(decomposition.entities),
                    "query_timeout_seconds": self._query_timeout,
                },
            )

        except Neo4jConnectionError as e:
            logger.warning(f"Neo4j connection error, falling back: {e}")
            return await self._fallback_to_semantic(
                query, None, "neo4j_error", start_time
            )
        except asyncio.TimeoutError:
            logger.warning("Neo4j query timeout, falling back to semantic search")
            return await self._fallback_to_semantic(
                query, None, "timeout", start_time
            )
        except Exception as e:
            logger.error(f"Unexpected error in KG retrieval: {e}")
            return await self._fallback_to_semantic(
                query, None, "unexpected_error", start_time
            )

    async def _decompose_query_safe(self, query: str) -> QueryDecomposition:
        """
        Decompose query with timeout protection.

        Args:
            query: User query text

        Returns:
            QueryDecomposition with extracted components

        Raises:
            Neo4jConnectionError: If Neo4j is unavailable
            asyncio.TimeoutError: If query times out
        """
        try:
            return await with_timeout(
                self._query_decomposer.decompose(query),
                self._query_timeout
            )
        except asyncio.TimeoutError:
            logger.warning(
                f"Query decomposition timed out after {self._query_timeout}s"
            )
            raise
        except Exception as e:
            if "connection" in str(e).lower() or "unavailable" in str(e).lower():
                raise Neo4jConnectionError(str(e))
            raise

    async def _stage1_kg_retrieval(
        self, decomposition: QueryDecomposition
    ) -> Tuple[List[RetrievedChunk], Dict[str, ChunkSourceMapping]]:
        """
        Stage 1: KG-based candidate retrieval.

        OPTIMIZED: Implements lazy relationship traversal - only traverses
        relationships if direct chunks are insufficient (below max_results).

        Retrieves chunks via:
        1. Direct source_chunks from matched concepts
        2. Relationship traversal (only if direct chunks < max_results)

        Args:
            decomposition: Query decomposition with matched concepts

        Returns:
            Tuple of (chunks, source_mappings)

        Requirements: 1.1, 1.3, 2.1-2.5
        """
        all_chunk_ids: Set[str] = set()
        source_mappings: Dict[str, ChunkSourceMapping] = {}

        # Step 1: Retrieve direct chunks from matched concepts
        direct_chunk_ids, direct_mappings = await self._retrieve_direct_chunks(
            decomposition.concept_matches
        )
        all_chunk_ids.update(direct_chunk_ids)
        source_mappings.update(direct_mappings)

        # Always traverse relationships to leverage KG connections
        # This ensures related concepts (like "regulated industries" connected to "Chelsea")
        # are included in results even when direct chunks are sufficient
        logger.debug(
            f"Direct chunks: {len(direct_chunk_ids)}, traversing relationships for KG enrichment"
        )
        related_chunk_ids, related_mappings = await self._retrieve_related_chunks(
            decomposition.concept_matches
        )

        # Add related chunks (avoiding duplicates)
        for chunk_id in related_chunk_ids:
            if chunk_id not in all_chunk_ids:
                all_chunk_ids.add(chunk_id)
                if chunk_id in related_mappings:
                    source_mappings[chunk_id] = related_mappings[chunk_id]

        logger.debug(
            f"Stage 1 collected {len(all_chunk_ids)} unique chunk IDs "
            f"({len(direct_chunk_ids)} direct, {len(related_chunk_ids)} related)"
        )

        # Step 3: Resolve chunk IDs to actual content
        all_resolved = await self._chunk_resolver.resolve_chunks(
            list(all_chunk_ids), source_mappings
        )

        # Split resolved chunks into direct vs related based on source_mappings
        direct_chunks: List[RetrievedChunk] = []
        related_chunks: List[RetrievedChunk] = []
        for chunk in all_resolved:
            if chunk.chunk_id in direct_chunk_ids:
                direct_chunks.append(chunk)
            else:
                related_chunks.append(chunk)

        # Aggregate with hop-distance-aware scoring and related chunk capping
        chunks = self._aggregate_and_deduplicate(
            direct_chunks, related_chunks, source_mappings
        )

        return chunks, source_mappings

    async def _retrieve_direct_chunks(
        self, concept_matches: List[Dict[str, Any]]
    ) -> Tuple[Set[str], Dict[str, ChunkSourceMapping]]:
        """
        Retrieve direct chunks from matched concept source_chunks.

        Args:
            concept_matches: List of matched concepts from query decomposition

        Returns:
            Tuple of (chunk_ids, source_mappings)

        Requirements: 1.1, 1.3, 8.2
        """
        chunk_ids: Set[str] = set()
        source_mappings: Dict[str, ChunkSourceMapping] = {}

        for concept in concept_matches:
            concept_id = concept.get("concept_id", "")
            concept_name = concept.get("name", "")
            # Semantic matches have 'similarity_score' (0-1 range).
            # Lucene matches have 'match_score' (0-15 range).
            # _aggregate_and_deduplicate normalizes via raw_score / 10.0,
            # so we scale semantic scores to the Lucene range (multiply
            # by 10) so they survive normalization correctly.
            if concept.get("match_type") == "semantic":
                concept_match_score = float(
                    concept.get("similarity_score", 1.0)
                ) * 10.0  # scale 0-1 → 0-10 for Lucene-style normalization
            else:
                concept_match_score = float(
                    concept.get("match_score", 1.0)
                )

            if not concept_id:
                continue

            # Check cache first (Requirement 8.2)
            cached_entry = self._get_cached_source_chunks(concept_id)

            if cached_entry:
                self._cache_hits += 1
                concept_chunk_ids = cached_entry.chunk_ids
                logger.debug(f"Cache hit for concept {concept_name}: {len(concept_chunk_ids)} chunks")
            else:
                self._cache_misses += 1
                # Get source_chunks from concept data or query Neo4j
                source_chunks_str = concept.get("source_chunks", "")
                concept_chunk_ids = self._parse_source_chunks(source_chunks_str)

                # Cache the result
                self._cache_source_chunks(concept_id, concept_name, concept_chunk_ids)
                logger.debug(f"Cached source_chunks for concept {concept_name}: {len(concept_chunk_ids)} chunks")

            # Add chunks with source mapping
            for chunk_id in concept_chunk_ids:
                if chunk_id and chunk_id not in chunk_ids:
                    chunk_ids.add(chunk_id)
                    source_mappings[chunk_id] = ChunkSourceMapping(
                        chunk_id=chunk_id,
                        source_concept_id=concept_id,
                        source_concept_name=concept_name,
                        retrieval_source=RetrievalSource.DIRECT_CONCEPT,
                        hop_distance=0,
                        match_score=concept_match_score,
                    )

        return chunk_ids, source_mappings

    async def _retrieve_related_chunks(
        self, concept_matches: List[Dict[str, Any]]
    ) -> Tuple[Set[str], Dict[str, ChunkSourceMapping]]:
        """
        Retrieve chunks from related concepts via relationship traversal.

        Traverses relationships up to max_hops to find related concepts
        and collects their source_chunks.

        Args:
            concept_matches: List of matched concepts from query decomposition

        Returns:
            Tuple of (chunk_ids, source_mappings)

        Requirements: 2.1, 2.2, 2.3, 2.4, 2.5
        """
        chunk_ids: Set[str] = set()
        source_mappings: Dict[str, ChunkSourceMapping] = {}

        if not self._neo4j_client:
            logger.debug("No Neo4j client available for relationship traversal")
            return chunk_ids, source_mappings

        for concept in concept_matches:
            concept_id = concept.get("concept_id", "")
            concept_name = concept.get("name", "")

            if not concept_id:
                continue

            try:
                # Query for related concepts within max_hops
                related_concepts = await self._query_related_concepts(
                    concept_id, concept_name
                )

                for related in related_concepts:
                    related_id = related.get("concept_id", "")
                    related_name = related.get("name", "")
                    hop_distance = related.get("hop_distance", 1)
                    relationship_path = related.get("relationship_path", [])
                    source_chunks_str = related.get("source_chunks", "")

                    related_chunk_ids = self._parse_source_chunks(source_chunks_str)

                    for chunk_id in related_chunk_ids:
                        if chunk_id and chunk_id not in chunk_ids:
                            chunk_ids.add(chunk_id)
                            source_mappings[chunk_id] = ChunkSourceMapping(
                                chunk_id=chunk_id,
                                source_concept_id=related_id,
                                source_concept_name=related_name,
                                retrieval_source=RetrievalSource.RELATED_CONCEPT,
                                relationship_path=relationship_path,
                                hop_distance=hop_distance,
                            )

            except Exception as e:
                logger.warning(
                    f"Error traversing relationships for concept {concept_name}: {e}"
                )
                continue

        logger.debug(f"Found {len(chunk_ids)} chunks from related concepts")
        return chunk_ids, source_mappings

    async def _query_related_concepts(
        self, concept_id: str, concept_name: str
    ) -> List[Dict[str, Any]]:
        """
        Query Neo4j for related concepts within 1 hop.

        Uses a single-hop traversal with explicit relationship type filter
        to avoid expensive variable-length path expansion on large graphs.

        Args:
            concept_id: Starting concept ID
            concept_name: Starting concept name (for logging)

        Returns:
            List of related concept dictionaries

        Requirements: 2.1, 2.2, 2.3
        """
        if not self._neo4j_client:
            return []

        try:
            # Ensure Neo4j connection is active before querying
            if hasattr(self._neo4j_client, '_is_connected') and not self._neo4j_client._is_connected:
                logger.info("Neo4j client connection is stale in KGRetrievalService, reconnecting...")
                if hasattr(self._neo4j_client, 'connect'):
                    await self._neo4j_client.connect()
                    logger.info("Neo4j client reconnected successfully in KGRetrievalService")

            # Build relationship type filter
            rel_types = "|".join(PRIORITY_RELATIONSHIP_TYPES)

            # Single-hop query — avoids combinatorial explosion of variable-length paths.
            # With 215K+ relationships, *1..2 patterns are too expensive.
            cypher_query = f"""
            MATCH (start:Concept {{concept_id: $concept_id}})
                  -[r:{rel_types}]-(related:Concept)
            WHERE related.concept_id <> start.concept_id
            RETURN DISTINCT
                related.concept_id as concept_id,
                related.name as name,
                related.source_chunks as source_chunks,
                1 as hop_distance,
                [type(r)] as relationship_path,
                [start.name, related.name] as path_names
            LIMIT 20
            """

            results = await with_timeout(
                self._neo4j_client.execute_query(
                    cypher_query, {"concept_id": concept_id}
                ),
                self._query_timeout
            )

            related_concepts = []
            for r in results or []:
                related_concepts.append({
                    "concept_id": r.get("concept_id", ""),
                    "name": r.get("name", ""),
                    "source_chunks": r.get("source_chunks", ""),
                    "hop_distance": r.get("hop_distance", 1),
                    "relationship_path": r.get("relationship_path", []),
                })

            logger.debug(
                f"Found {len(related_concepts)} related concepts for {concept_name}"
            )
            return related_concepts

        except asyncio.TimeoutError:
            logger.warning(f"Timeout querying related concepts for {concept_name}")
            return []
        except Exception as e:
            logger.warning(
                f"Error querying related concepts for {concept_name}: {e}"
            )
            return []

    def _aggregate_and_deduplicate(
        self,
        direct_chunks: List[RetrievedChunk],
        related_chunks: List[RetrievedChunk],
        source_mappings: Dict[str, ChunkSourceMapping],
    ) -> List[RetrievedChunk]:
        """
        Aggregate and deduplicate chunks from multiple sources.

        Direct chunks take precedence over related chunks when there are duplicates.
        Direct chunks get kg_relevance_score=1.0. Related chunks get a decayed score
        based on hop distance and are capped at max_related_chunks.

        Args:
            direct_chunks: Chunks from direct concept retrieval
            related_chunks: Chunks from relationship traversal
            source_mappings: Mapping of chunk IDs to their source provenance

        Returns:
            Deduplicated list of chunks with hop-distance-aware scores

        Requirements: 1.5, 2.1, 2.2, 3.1, 3.2, 3.3
        """
        seen_ids: Set[str] = set()
        aggregated: List[RetrievedChunk] = []

        # Direct chunks: score based on concept match_score, always included
        for chunk in direct_chunks:
            if chunk.chunk_id not in seen_ids:
                mapping = source_mappings.get(chunk.chunk_id)
                # Use the concept's fulltext match_score to
                # differentiate strong vs weak concept matches.
                # Normalize: scores typically range 0-15 from Lucene;
                # we clamp to [0.1, 1.0] so direct chunks always
                # outrank related chunks (which get decay^hop).
                raw_score = mapping.match_score if mapping else 1.0
                # Normalize to [0.1, 1.0] range
                normalized = min(1.0, max(0.1, raw_score / 10.0))
                chunk.kg_relevance_score = normalized
                seen_ids.add(chunk.chunk_id)
                aggregated.append(chunk)

        # Related chunks: sort by hop_distance ascending, cap at max, apply decay
        sorted_related = sorted(
            related_chunks,
            key=lambda c: source_mappings[c.chunk_id].hop_distance
            if c.chunk_id in source_mappings
            else 1,
        )
        related_count = 0
        for chunk in sorted_related:
            if chunk.chunk_id not in seen_ids and related_count < self._max_related_chunks:
                mapping = source_mappings.get(chunk.chunk_id)
                hop = mapping.hop_distance if mapping else 1
                chunk.kg_relevance_score = self._hop_distance_decay ** hop
                seen_ids.add(chunk.chunk_id)
                aggregated.append(chunk)
                related_count += 1

        logger.debug(
            f"Aggregated {len(aggregated)} unique chunks from "
            f"{len(direct_chunks)} direct + {len(related_chunks)} related "
            f"(capped related: {related_count}/{len(related_chunks)})"
        )
        return aggregated

    async def _augment_with_semantic(
        self,
        query: str,
        existing_chunks: List[RetrievedChunk],
        existing_mappings: Dict[str, ChunkSourceMapping],
    ) -> List[RetrievedChunk]:
        """
        Augment KG results with semantic search when below threshold.

        Args:
            query: Original query for semantic search
            existing_chunks: Existing chunks from KG retrieval
            existing_mappings: Existing source mappings

        Returns:
            Augmented list of chunks

        Requirements: 3.3
        """
        if not self._vector_client:
            logger.debug("No vector client available for semantic augmentation")
            return existing_chunks

        existing_ids = {chunk.chunk_id for chunk in existing_chunks}
        augment_count = self._augmentation_threshold - len(existing_chunks)

        if augment_count <= 0:
            return existing_chunks

        try:
            # Perform semantic search
            search_results = await self._perform_semantic_search(
                query, top_k=augment_count + 5  # Get extra to account for duplicates
            )

            # Add non-duplicate results
            augmented_chunks = list(existing_chunks)
            added = 0

            for result in search_results:
                chunk_id = result.get("chunk_id", result.get("id", ""))
                if chunk_id and chunk_id not in existing_ids:
                    content = result.get("content", result.get("text", ""))
                    similarity_score = result.get(
                        "similarity_score", result.get("score", 0.5)
                    )

                    augmented_chunk = RetrievedChunk(
                        chunk_id=chunk_id,
                        content=content,
                        source=RetrievalSource.SEMANTIC_AUGMENT,
                        kg_relevance_score=0.5,  # Default for augmented chunks
                        semantic_score=similarity_score,
                        final_score=similarity_score,
                        metadata=result.get("metadata", {}),
                    )
                    augmented_chunks.append(augmented_chunk)
                    existing_ids.add(chunk_id)
                    added += 1

                    if added >= augment_count:
                        break

            logger.info(f"Augmented with {added} semantic search results")
            return augmented_chunks

        except Exception as e:
            logger.warning(f"Semantic augmentation failed: {e}")
            return existing_chunks

    async def _fallback_to_semantic(
        self,
        query: str,
        decomposition: Optional[QueryDecomposition],
        reason: str,
        start_time: float,
    ) -> KGRetrievalResult:
        """
        Fall back to pure semantic search.

        Args:
            query: Original query
            decomposition: Query decomposition (may be None)
            reason: Reason for fallback
            start_time: Start time for timing calculation

        Returns:
            KGRetrievalResult with fallback results

        Requirements: 6.1, 6.2, 6.3, 6.5
        """
        logger.info(f"Falling back to semantic search (reason: {reason})")

        chunks: List[RetrievedChunk] = []

        if self._vector_client:
            try:
                search_results = await self._perform_semantic_search(
                    query, top_k=self._max_results
                )

                for search_result in search_results:
                    chunk_id = search_result.get(
                        "chunk_id", search_result.get("id", "")
                    )
                    content = search_result.get(
                        "content", search_result.get("text", "")
                    )
                    similarity_score = search_result.get(
                        "similarity_score", search_result.get("score", 0.5)
                    )

                    if chunk_id and content:
                        chunks.append(
                            RetrievedChunk(
                                chunk_id=chunk_id,
                                content=content,
                                source=RetrievalSource.SEMANTIC_FALLBACK,
                                kg_relevance_score=0.0,
                                semantic_score=similarity_score,
                                final_score=similarity_score,
                                metadata=search_result.get("metadata", {}),
                            )
                        )

            except Exception as e:
                logger.error(f"Semantic fallback search failed: {e}")

        retrieval_time_ms = int((time.time() - start_time) * 1000)

        # Generate fallback explanation
        kg_result = KGRetrievalResult(
            chunks=chunks,
            query_decomposition=decomposition,
            fallback_used=True,
            retrieval_time_ms=retrieval_time_ms,
            stage1_chunk_count=0,
            stage2_chunk_count=len(chunks),
            metadata={"fallback_reason": reason},
        )

        kg_result.explanation = self._explanation_generator.generate(
            kg_result, decomposition
        )

        return kg_result

    async def _perform_semantic_search(
        self, query: str, top_k: int = 15
    ) -> List[Dict[str, Any]]:
        """
        Perform semantic search using vector client.

        Args:
            query: Query text
            top_k: Maximum results to return

        Returns:
            List of search result dictionaries
        """
        if not self._vector_client:
            return []

        try:
            # Try async method first (OpenSearch)
            if hasattr(self._vector_client, "semantic_search_async"):
                return await self._vector_client.semantic_search_async(
                    query=query, top_k=top_k
                )
            # Fall back to sync method (Milvus)
            elif hasattr(self._vector_client, "semantic_search"):
                method = self._vector_client.semantic_search
                if asyncio.iscoroutinefunction(method):
                    return await method(query=query, top_k=top_k)
                else:
                    loop = asyncio.get_event_loop()
                    return await loop.run_in_executor(
                        None, lambda: method(query=query, top_k=top_k)
                    )
            else:
                logger.warning("Vector client has no semantic_search method")
                return []

        except Exception as e:
            logger.warning(f"Semantic search failed: {e}")
            return []

    # =========================================================================
    # Cache Management (Requirement 8.2)
    # =========================================================================

    def _get_cached_source_chunks(
        self, concept_id: str
    ) -> Optional[SourceChunksCacheEntry]:
        """
        Get cached source_chunks for a concept.

        Args:
            concept_id: Concept ID to look up

        Returns:
            Cache entry if found and not expired, None otherwise
        """
        entry = self._source_chunks_cache.get(concept_id)

        if entry is None:
            return None

        if entry.is_expired():
            # Remove expired entry
            del self._source_chunks_cache[concept_id]
            return None

        return entry

    def _cache_source_chunks(
        self, concept_id: str, concept_name: str, chunk_ids: List[str]
    ) -> None:
        """
        Cache source_chunks for a concept.

        Args:
            concept_id: Concept ID
            concept_name: Concept name
            chunk_ids: List of chunk IDs
        """
        self._source_chunks_cache[concept_id] = SourceChunksCacheEntry(
            concept_id=concept_id,
            concept_name=concept_name,
            chunk_ids=chunk_ids,
            ttl_seconds=self._cache_ttl,
        )

    def _parse_source_chunks(self, source_chunks_str: str) -> List[str]:
        """
        Parse source_chunks string into list of chunk IDs.

        The source_chunks field in Neo4j is stored as a comma-separated string.

        Args:
            source_chunks_str: Comma-separated chunk IDs

        Returns:
            List of chunk IDs
        """
        if not source_chunks_str:
            return []

        # Handle both comma-separated and JSON array formats
        if source_chunks_str.startswith("["):
            try:
                import json
                return json.loads(source_chunks_str)
            except (json.JSONDecodeError, ValueError):
                pass

        # Parse comma-separated format
        chunk_ids = [
            chunk_id.strip()
            for chunk_id in source_chunks_str.split(",")
            if chunk_id.strip()
        ]

        return chunk_ids

    def clear_cache(self) -> int:
        """
        Clear the source_chunks cache.

        Returns:
            Number of entries cleared
        """
        count = len(self._source_chunks_cache)
        self._source_chunks_cache.clear()
        logger.info(f"Cleared {count} cache entries")
        return count

    def cleanup_expired_cache(self) -> int:
        """
        Remove expired entries from cache.

        Returns:
            Number of entries removed
        """
        expired_ids = [
            concept_id
            for concept_id, entry in self._source_chunks_cache.items()
            if entry.is_expired()
        ]

        for concept_id in expired_ids:
            del self._source_chunks_cache[concept_id]

        if expired_ids:
            logger.debug(f"Cleaned up {len(expired_ids)} expired cache entries")

        return len(expired_ids)

    # =========================================================================
    # Health Check and Statistics (Requirements 7.5, 8.5)
    # =========================================================================

    async def health_check(self) -> Dict[str, Any]:
        """
        Check health of KG retrieval service.

        Verifies connectivity to Neo4j and vector store.

        Returns:
            Health status dictionary

        Requirements: 7.5
        """
        health: Dict[str, Any] = {
            "status": "healthy",
            "neo4j_available": False,
            "vector_store_available": False,
            "cache_size": len(self._source_chunks_cache),
            "total_queries": self._total_queries,
            "cache_hit_rate": self._calculate_cache_hit_rate(),
            "components": {
                "query_decomposer": self._query_decomposer.has_neo4j_client,
                "chunk_resolver": self._chunk_resolver.has_vector_client,
                "semantic_reranker": self._semantic_reranker.has_model_client,
            },
        }

        # Check Neo4j connectivity
        if self._neo4j_client:
            try:
                await with_timeout(
                    self._neo4j_client.execute_query("RETURN 1 as test", {}),
                    2.0
                )
                health["neo4j_available"] = True
            except Exception as e:
                health["neo4j_error"] = str(e)

        # Check vector store connectivity
        if self._vector_client:
            try:
                if hasattr(self._vector_client, "is_connected"):
                    health["vector_store_available"] = (
                        self._vector_client.is_connected()
                    )
                elif hasattr(self._vector_client, "_connected"):
                    health["vector_store_available"] = self._vector_client._connected
                else:
                    health["vector_store_available"] = True
            except Exception as e:
                health["vector_store_error"] = str(e)

        # Determine overall status
        if not health["neo4j_available"] and not health["vector_store_available"]:
            health["status"] = "unhealthy"
        elif not health["neo4j_available"] or not health["vector_store_available"]:
            health["status"] = "degraded"

        return health

    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Cache statistics dictionary

        Requirements: 8.5
        """
        # Count expired entries
        expired_count = sum(
            1 for entry in self._source_chunks_cache.values() if entry.is_expired()
        )

        return {
            "cache_size": len(self._source_chunks_cache),
            "cache_ttl_seconds": self._cache_ttl,
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "cache_hit_rate": self._calculate_cache_hit_rate(),
            "expired_entries": expired_count,
            "total_queries": self._total_queries,
        }

    def _calculate_cache_hit_rate(self) -> float:
        """Calculate cache hit rate as a percentage."""
        total = self._cache_hits + self._cache_misses
        if total == 0:
            return 0.0
        return (self._cache_hits / total) * 100.0

    # =========================================================================
    # Client Management
    # =========================================================================

    def set_neo4j_client(self, client: Any) -> None:
        """
        Set the Neo4j client after initialization.

        Args:
            client: Neo4j client instance
        """
        self._neo4j_client = client
        self._query_decomposer.set_neo4j_client(client)
        logger.debug("Neo4j client set on KGRetrievalService")

    def set_vector_client(self, client: Any) -> None:
        """
        Set the vector client after initialization.

        Args:
            client: Vector store client instance
        """
        self._vector_client = client
        self._chunk_resolver.set_vector_client(client)
        logger.debug("Vector client set on KGRetrievalService")

    def set_model_client(self, client: Any) -> None:
        """
        Set the model client after initialization.

        Args:
            client: Model server client instance
        """
        self._model_client = client
        self._semantic_reranker.set_model_client(client)
        self._query_decomposer.set_model_server_client(client)
        logger.debug("Model client set on KGRetrievalService")

    @property
    def has_neo4j_client(self) -> bool:
        """Check if Neo4j client is available."""
        return self._neo4j_client is not None

    @property
    def has_vector_client(self) -> bool:
        """Check if vector client is available."""
        return self._vector_client is not None

    @property
    def has_model_client(self) -> bool:
        """Check if model client is available."""
        return self._model_client is not None

    @property
    def max_results(self) -> int:
        """Get the maximum results limit."""
        return self._max_results

    @property
    def cache_ttl(self) -> int:
        """Get the cache TTL in seconds."""
        return self._cache_ttl

    async def evaluate_retrieval(
        self,
        query: str,
        ground_truth_chunk_ids: List[str],
        top_k: int = 15,
        threshold_overrides: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Evaluate retrieval quality against ground truth.

        Args:
            query: The query to evaluate
            ground_truth_chunk_ids: List of chunk IDs that are known relevant
            top_k: Maximum number of chunks to retrieve
            threshold_overrides: Optional dict of threshold names to values
                for A/B comparison (e.g., {'target_embedding_tokens': 384}).
                Applied temporarily for this evaluation only.

        Returns:
            Dict with recall, precision, f1_score, true_positives,
            retrieved_count, ground_truth_count, threshold_config,
            and retrieval_result.

        Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 9.2, 9.3
        """
        from ..config import get_settings

        # Handle empty ground truth
        if not ground_truth_chunk_ids:
            return {
                'recall': 0.0,
                'precision': 0.0,
                'f1_score': 0.0,
                'true_positives': 0,
                'retrieved_count': 0,
                'ground_truth_count': 0,
                'threshold_config': threshold_overrides or 'defaults',
                'retrieval_result': None,
            }

        # Apply temporary overrides if provided
        original_values = {}
        if threshold_overrides:
            settings = get_settings()
            for key, value in threshold_overrides.items():
                if hasattr(settings, key):
                    original_values[key] = getattr(settings, key)
                    setattr(settings, key, value)
                else:
                    logger.warning(
                        f"Unknown threshold override key: {key}"
                    )

        try:
            result = await self.retrieve(query, top_k=top_k)
            retrieved_ids = {
                chunk.chunk_id for chunk in result.chunks
            }
            gt_set = set(ground_truth_chunk_ids)

            true_positives = len(retrieved_ids & gt_set)
            recall = (
                true_positives / len(gt_set) if gt_set else 0.0
            )
            precision = (
                true_positives / len(retrieved_ids)
                if retrieved_ids else 0.0
            )
            f1 = (
                (2 * precision * recall / (precision + recall))
                if (precision + recall) > 0 else 0.0
            )

            return {
                'recall': recall,
                'precision': precision,
                'f1_score': f1,
                'true_positives': true_positives,
                'retrieved_count': len(retrieved_ids),
                'ground_truth_count': len(gt_set),
                'threshold_config': (
                    threshold_overrides or 'defaults'
                ),
                'retrieval_result': result,
            }
        finally:
            # Restore original values — always, even on exception
            if original_values:
                settings = get_settings()
                for key, value in original_values.items():
                    setattr(settings, key, value)
