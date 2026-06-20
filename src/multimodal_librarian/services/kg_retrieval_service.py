"""
Knowledge Graph-Guided Retrieval Service.

This service orchestrates the two-stage retrieval pipeline that uses Neo4j
knowledge graph for precise chunk retrieval and semantic re-ranking for
relevance ordering.

Stage 1 (KG-Based): Extract concepts from query, retrieve chunk IDs via
EXTRACTED_FROM graph traversal, and traverse relationships to find related chunks.

Stage 2 (Semantic Re-ranking): Re-rank candidate chunks using semantic similarity
for relevance ordering.

Requirements: 1.1, 1.3, 1.5, 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.3, 3.4, 6.1, 6.2, 6.3, 6.4, 6.5, 8.1, 8.2, 8.3, 8.5
"""

import asyncio
import heapq
import logging
import math
import re
import sys
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple

if TYPE_CHECKING:
    from ..components.kg_retrieval.relevance_detector import RelevanceDetector

from ..components.kg_retrieval import (
    ChunkResolver,
    ExplanationGenerator,
    QueryDecomposer,
    RelationshipTraverser,
    SemanticReranker,
)
from ..components.kg_retrieval.chain_synthesizer import ChainSynthesizer
from ..components.kg_retrieval.query_decomposer import is_generic_concept
from ..models.kg_retrieval import (
    ChunkSourceMapping,
    KGRetrievalResult,
    Neo4jConnectionError,
    QueryDecomposition,
    RetrievalSource,
    RetrievedChunk,
    SourceChunksCacheEntry,
    TraversalResult,
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


# Relationship types eligible for concept promotion to direct retrieval.
# UMLS-derived and clinically-meaningful ConceptNet types only — loose
# associations like RelatedTo or AtLocation are excluded to avoid
# promoting irrelevant concepts (e.g. "voice" RelatedTo "cough").
_PROMOTION_ELIGIBLE_RELATIONSHIPS = frozenset({
    # UMLS-derived clinical relationships (pattern-extracted, lowercase)
    "IS_A", "PART_OF", "CAUSES", "SIMILAR_TO",
    # ConceptNet clinically-meaningful relationships (PascalCase)
    "IsA", "PartOf", "Synonym", "FormOf", "HasContext",
    "DerivedFrom", "HasProperty", "UsedFor", "CapableOf",
    "HasA", "DefinedAs", "Entails", "Causes",
})

# UMLS_REL rela_type values eligible for concept promotion.
# These represent clinically validated edges between medical concepts
# (e.g., pneumonia → may_be_treated_by → doxycycline).
# Sourced from RelationshipTraverser.CLINICALLY_MEANINGFUL_UMLS_RELA —
# excludes qualifier metadata, drug composition, trade names, and
# administrative mappings.
_UMLS_PROMOTION_ELIGIBLE_RELA = frozenset({
    "isa", "inverse_isa",
    "may_treat", "may_be_treated_by",
    "may_be_prevented_by", "may_prevent",
    "cause_of", "due_to",
    "has_manifestation", "manifestation_of",
    "has_definitional_manifestation",
    "has_associated_finding", "associated_finding_of",
    "has_associated_etiologic_finding",
    "finding_site_of", "has_finding_site",
    "has_procedure_site", "procedure_site_of",
    "has_direct_procedure_site", "has_indirect_procedure_site",
    "has_focus", "focus_of",
    "has_component", "component_of",
    "occurs_after", "occurs_before",
    "has_clinical_course", "clinical_course_of",
    "has_severity", "severity_of",
    "has_stage", "stage_of",
    "has_associated_morphology", "associated_morphology_of",
    "has_pathological_process", "pathological_process_of",
    "has_specimen", "specimen_of",
    "has_interpretation", "interpretation_of",
    "has_method", "method_of",
    "has_direct_morphology", "has_indirect_morphology",
    "has_causative_agent",
    "has_pharmacokinetics",
    "has_physiologic_effect",
    "has_mechanism_of_action",
    "has_therapeutic_class",
    "may_diagnose", "may_be_diagnosed_by",
})


# Path-type-aware decay rates for hop-distance scoring.
# UMLS clinical paths are curated medical knowledge — they get minimal/no decay.
# Document-extracted edges and co-occurrence are noisier — they get full decay.
# Keys match path_type values from RelationshipTraverser path annotations.
_PATH_TYPE_DECAY = {
    "umls_1hop": 1.0,            # Clinically validated direct UMLS path — no decay
    "umls_2hop": 0.85,           # Clinically validated 2-hop UMLS — slight decay
    "umls_bridge": 1.0,          # UMLS bridge traversal (SAME_AS → UMLS_REL) — no decay
    "umls_bridge_2hop": 0.85,    # 2-hop UMLS bridge — slight decay
    "direct": 0.7,               # Document-extracted direct edge — moderate decay
    "shared_chunk": 0.5,         # Co-occurrence in shared chunk — full decay
}
_PATH_TYPE_RANK = {
    "umls_1hop": 0,
    "umls_2hop": 1,
    "umls_bridge": 0,
    "umls_bridge_2hop": 1,
    "direct": 2,
    "shared_chunk": 3,
}

# 2-hop traversal limits — keep fan-out bounded to avoid
# combinatorial explosion on densely-connected concept graphs.
_MAX_2HOP_INTERMEDIATE = 3        # max intermediates to expand from (per concept)
_MAX_2HOP_TARGETS_PER_INTERMEDIATE = 3  # max 2-hop targets per intermediate
_MAX_CONCEPTS_FOR_2HOP = 3        # only top-N concepts by match score get 2-hop
_MAX_CONCEPTS_FOR_1HOP = 10       # only top-N concepts by match score get 1-hop traversal
_MAX_CONCEPTS_FOR_UMLS_1HOP = 5  # narrower cap for UMLS bridge (13.9M UMLS_REL edges)

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
        relevance_detector: Optional["RelevanceDetector"] = None,
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
            relevance_detector: Optional RelevanceDetector for proper-noun chunk filtering
        """
        self._neo4j_client = neo4j_client
        self._vector_client = vector_client
        self._model_client = model_client
        self._relevance_detector = relevance_detector
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
        self._chain_synthesizer = ChainSynthesizer()

        # Initialize relationship traverser with config settings
        from ..config import get_settings
        _settings = get_settings()
        self._relationship_traverser = RelationshipTraverser(
            neo4j_client=neo4j_client,
            hop_limit=getattr(_settings, 'relationship_hop_limit', 2),
            timeout_seconds=getattr(_settings, 'relationship_traversal_timeout', 3.0),
            max_paths_per_pair=getattr(_settings, 'relationship_max_paths_per_pair', 50),
        )

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
                stage1_chunks, source_mappings, traversal_result = await with_timeout(
                    self._stage1_kg_retrieval(decomposition),
                    self._query_timeout * 3  # 3x single-query timeout for large graphs
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

            # Step 3.5: Pre-reranking proper-noun filter (Requirement 7)
            chunks_for_reranking = stage1_chunks
            if self._relevance_detector is not None:
                try:
                    # Compute adaptive threshold from entity count
                    from ..components.kg_retrieval.relevance_detector import (
                        compute_adaptive_threshold,
                    )
                    from ..config import get_settings

                    _settings = get_settings()
                    _proper_noun_count = len(decomposition.entities)
                    _adaptive_threshold = compute_adaptive_threshold(
                        proper_noun_count=_proper_noun_count,
                        domain=None,  # domain not available pre-reranking
                        base_threshold_floor=_settings.adaptive_threshold_floor,
                        medical_threshold=_settings.adaptive_medical_threshold,
                        legal_threshold=_settings.adaptive_legal_threshold,
                        small_query_noun_limit=_settings.adaptive_small_query_noun_limit,
                    )

                    filtered = await self._relevance_detector.filter_chunks_by_proper_nouns(
                        stage1_chunks, query, adaptive_threshold=_adaptive_threshold
                    )
                    if filtered is not None:
                        chunks_for_reranking = filtered
                except Exception as e:
                    logger.warning(f"Proper-noun chunk filter failed: {e}")
                    # Fall back to unfiltered candidates

            # Step 4: Stage 2 - Semantic re-ranking
            ranked_chunks = await self._semantic_reranker.rerank(
                chunks_for_reranking, query, effective_top_k,
                decomposition=decomposition,
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

            # Build result metadata
            result_metadata: Dict[str, Any] = {
                "concepts_matched": len(decomposition.entities),
                "query_timeout_seconds": self._query_timeout,
            }

            # Add relationship-aware metadata (Requirements: 1.4, 6.4, 8.1)
            is_multi_concept = len(decomposition.concept_matches) >= 2
            if is_multi_concept and traversal_result is not None:
                result_metadata["relationship_aware_activated"] = True
                result_metadata["intersection_chunks_found"] = len(
                    traversal_result.intersection_chunk_ids
                )
                result_metadata["relationship_paths_traversed"] = (
                    traversal_result.total_paths_found
                )
                result_metadata["relationship_traversal_duration_ms"] = (
                    traversal_result.traversal_duration_ms
                )
                logger.info(
                    f"Relationship traversal completed in "
                    f"{traversal_result.traversal_duration_ms}ms: "
                    f"{traversal_result.total_paths_found} paths, "
                    f"{len(traversal_result.intersection_chunk_ids)} intersection chunks"
                )

                # Synthesize clinical reasoning gloss from UMLS path annotations
                if traversal_result.path_annotations:
                    concept_id_to_name = {
                        m.get("concept_id", ""): m.get("concept_name", "")
                        for m in decomposition.concept_matches
                    }
                    gloss = self._chain_synthesizer.synthesize(
                        traversal_result.path_annotations,
                        concept_id_to_name,
                    )
                    if gloss:
                        result_metadata["kg_explanation"] = gloss
            else:
                result_metadata["relationship_aware_activated"] = False

            return KGRetrievalResult(
                chunks=ranked_chunks,
                query_decomposition=decomposition,
                explanation=explanation,
                fallback_used=False,
                retrieval_time_ms=retrieval_time_ms,
                stage1_chunk_count=stage1_count,
                stage2_chunk_count=stage2_count,
                cache_hits=cache_hits_this_query,
                metadata=result_metadata,
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
    ) -> Tuple[List[RetrievedChunk], Dict[str, ChunkSourceMapping], Optional[TraversalResult]]:
        """
        Stage 1: KG-based candidate retrieval.

        OPTIMIZED: Implements lazy relationship traversal - only traverses
        relationships if direct chunks are insufficient (below max_results).

        Retrieves chunks via:
        1. Direct chunk IDs from matched concepts via EXTRACTED_FROM traversal
        2. Relationship traversal (only if direct chunks < max_results)

        Args:
            decomposition: Query decomposition with matched concepts

        Returns:
            Tuple of (chunks, source_mappings, traversal_result)
            traversal_result is None when relationship traversal was not performed.

        Requirements: 1.1, 1.3, 2.1-2.5
        """
        all_chunk_ids: Set[str] = set()
        source_mappings: Dict[str, ChunkSourceMapping] = {}

        # Run direct chunk retrieval and relationship traversal concurrently.
        # Direct retrieval is the critical path — it must never be discarded
        # because the expensive UMLS/relationship traversal timed out.
        # return_exceptions=True ensures a TimeoutError in the related task
        # doesn't kill the direct results that completed in <2 seconds.
        direct_task = self._retrieve_direct_chunks(decomposition.concept_matches)
        related_task = self._retrieve_related_chunks(decomposition.concept_matches)
        gathered = await asyncio.gather(
            direct_task, related_task, return_exceptions=True
        )
        direct_result, related_result = gathered

        if isinstance(direct_result, Exception):
            logger.error(
                f"Direct chunk retrieval failed: {direct_result}"
            )
            raise direct_result

        direct_chunk_ids, direct_mappings, chunk_concept_hits = direct_result

        if isinstance(related_result, Exception):
            logger.warning(
                f"Related traversal failed, proceeding with direct chunks "
                f"({len(direct_chunk_ids)}): {related_result}"
            )
            related_chunk_ids_raw: Set[str] = set()
            related_mappings_raw: Dict[str, ChunkSourceMapping] = {}
            promoted_concepts = []
        else:
            related_chunk_ids_raw, related_mappings_raw, promoted_concepts = related_result

        # Concept expansion: promote related concepts reached via clinical
        # edges to direct retrieval status.  Chunks from promoted concepts
        # get full scoring weight (coverage bonus, doc boost, title boost)
        # instead of the hop-distance decay ceiling applied to related chunks.
        promoted_chunk_count = 0
        for pc in promoted_concepts:
            pc_id = pc["concept_id"]
            pc_name = pc["concept_name"]
            pc_score = pc["match_score"]
            for chunk_id in pc["chunk_ids"]:
                if chunk_id and chunk_id not in direct_chunk_ids:
                    direct_chunk_ids.add(chunk_id)
                    direct_mappings[chunk_id] = ChunkSourceMapping(
                        chunk_id=chunk_id,
                        source_concept_id=pc_id,
                        source_concept_name=pc_name,
                        retrieval_source=RetrievalSource.DIRECT_CONCEPT,
                        match_score=pc_score,
                        path_type="promoted",
                    )
                    # Register concept hit for coverage scoring
                    if chunk_id not in chunk_concept_hits:
                        chunk_concept_hits[chunk_id] = []
                    chunk_concept_hits[chunk_id].append({
                        "concept_id": pc_id,
                        "concept_name": pc_name,
                        "match_score": pc_score,
                        "match_type": "promoted",
                    })
                    promoted_chunk_count += 1
        if promoted_chunk_count:
            logger.info(
                f"Concept expansion: promoted {promoted_chunk_count} chunks "
                f"from {len(promoted_concepts)} related concepts to direct status"
            )

        all_chunk_ids.update(direct_chunk_ids)
        source_mappings.update(direct_mappings)

        # Merge related chunks (already retrieved concurrently above)
        related_chunk_ids = related_chunk_ids_raw
        related_mappings = related_mappings_raw

        # Add related chunks, capped to _max_related_chunks and prioritized
        # by the parent concept's similarity score. Without this cap, generic
        # concepts like "we saw" fan out to tens of thousands of related
        # chunks via relationship traversal, wasting Milvus resolution time.
        # Uses heapq.nlargest for O(n log k) instead of full sort O(n log n).
        new_related: list = []
        for chunk_id in related_chunk_ids:
            if chunk_id not in all_chunk_ids:
                mapping = related_mappings.get(chunk_id)
                score = mapping.match_score if mapping else 0.0
                new_related.append((score, chunk_id, mapping))
        top_related = heapq.nlargest(
            self._max_related_chunks, new_related, key=lambda x: x[0]
        )
        for _score, chunk_id, mapping in top_related:
            all_chunk_ids.add(chunk_id)
            if mapping:
                source_mappings[chunk_id] = mapping

        logger.debug(
            f"Stage 1 collected {len(all_chunk_ids)} unique chunk IDs "
            f"({len(direct_chunk_ids)} direct, {len(top_related)} related "
            f"[capped from {len(new_related)}])"
        )

        # --- determinism diagnostic: log sorted chunk IDs ---
        _sorted_direct = sorted(direct_chunk_ids)[:10]
        logger.info(
            f"DETERMINISM_DIAG direct_chunk_ids ({len(direct_chunk_ids)}): {_sorted_direct}"
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

        # Aggregate with concept-coverage scoring and related chunk capping
        matched_concept_names = [
            c["name"] for c in decomposition.concept_matches
            if c.get("name") and not is_generic_concept(c["name"])
        ]
        # Precompute rationale→query similarity per (concept, chunk).  Done
        # here (async) because _aggregate_and_deduplicate is synchronous and
        # cannot embed the query or query Neo4j for edge rationale embeddings.
        rationale_sim_by_pair = await self._compute_rationale_sims(
            [c.get("concept_id") for c in decomposition.concept_matches if c.get("concept_id")],
            direct_chunk_ids,
            decomposition.original_query,
        )
        chunks = self._aggregate_and_deduplicate(
            direct_chunks, related_chunks, source_mappings, chunk_concept_hits,
            query=decomposition.original_query,
            matched_concept_names=matched_concept_names,
            rationale_sim_by_pair=rationale_sim_by_pair,
        )

        # Apply relationship-aware boost for multi-concept queries
        # Requirements: 1.1, 1.2, 5.1, 5.2, 5.3
        traversal_result: Optional[TraversalResult] = None
        if len(decomposition.concept_matches) >= 2:
            traversal_result = await self._relationship_traverser.traverse(
                decomposition.concept_matches
            )
            if traversal_result.completed:
                # Apply intersection boost
                if traversal_result.intersection_chunk_ids:
                    from ..config import get_settings
                    _settings = get_settings()
                    chunks = self._apply_relationship_boost(
                        chunks, traversal_result,
                        getattr(_settings, 'relationship_boost', 1.0)
                    )
                    logger.debug(
                        f"Relationship-aware boost applied: "
                        f"{len(traversal_result.intersection_chunk_ids)} intersection chunks, "
                        f"{traversal_result.total_paths_found} paths found, "
                        f"{traversal_result.traversal_duration_ms}ms traversal time"
                    )

                # Merge UMLS-discovered chunks not already in the pipeline.
                # The relationship traverser finds chunks via UMLS clinical
                # paths that the generic 1-hop _query_related_concepts misses
                # (e.g., treatment chunks reachable only via UMLS-mediated
                # relationships like Diabetes -[may_be_treated_by]-> Metformin).
                existing_ids = {c.chunk_id for c in chunks}
                new_traversal_ids = (
                    set(traversal_result.chunk_concept_connections.keys())
                    - existing_ids
                )

                if new_traversal_ids:
                    # Build chunk_id → best path_type from annotations
                    pt_map: Dict[str, str] = {}
                    for ann in traversal_result.path_annotations:
                        cid = ann.get("chunk_id")
                        pt = ann.get("path_type", "shared_chunk")
                        if cid and cid in new_traversal_ids:
                            if (cid not in pt_map
                                    or _PATH_TYPE_RANK.get(pt, 99)
                                    < _PATH_TYPE_RANK.get(pt_map[cid], 99)):
                                pt_map[cid] = pt

                    # Build source mappings for new chunks
                    new_mappings: Dict[str, ChunkSourceMapping] = {}
                    for cid in new_traversal_ids:
                        pt = pt_map.get(cid)
                        hop = 2 if pt == "umls_2hop" else 1
                        new_mappings[cid] = ChunkSourceMapping(
                            chunk_id=cid,
                            source_concept_id="",
                            source_concept_name="",
                            retrieval_source=RetrievalSource.REASONING_PATH,
                            hop_distance=hop,
                            path_type=pt,
                        )

                    # Resolve and score new chunks
                    new_resolved = await self._chunk_resolver.resolve_chunks(
                        list(new_traversal_ids), new_mappings
                    )

                    for chunk in new_resolved:
                        mapping = new_mappings.get(chunk.chunk_id)
                        pt = mapping.path_type if mapping else None
                        decay = _PATH_TYPE_DECAY.get(
                            pt, self._hop_distance_decay
                        )
                        hop = mapping.hop_distance if mapping else 1
                        chunk.kg_relevance_score = decay ** hop
                        chunk.metadata["umls_discovered"] = True

                    chunks.extend(new_resolved)
                    logger.info(
                        f"Merged {len(new_resolved)} UMLS-discovered chunks "
                        f"not found by direct/related pipeline "
                        f"(path_types: {set(pt_map.values())})"
                    )
            else:
                logger.debug(
                    "Relationship traversal timed out or incomplete, "
                    "proceeding with existing pipeline results"
                )

        return chunks, source_mappings, traversal_result

    async def _retrieve_direct_chunks(
        self, concept_matches: List[Dict[str, Any]]
    ) -> Tuple[Set[str], Dict[str, ChunkSourceMapping], Dict[str, List[Dict[str, Any]]]]:
        """
        Retrieve direct chunks from matched concepts via EXTRACTED_FROM traversal.

        Queries Neo4j for chunk IDs linked to each concept via
        (Concept)-[:EXTRACTED_FROM]->(Chunk) relationships.

        Tracks ALL concept matches per chunk for concept-coverage scoring.

        Args:
            concept_matches: List of matched concepts from query decomposition

        Returns:
            Tuple of (chunk_ids, source_mappings, chunk_concept_hits)
            chunk_concept_hits maps chunk_id -> list of concept match dicts
            with keys: concept_id, concept_name, match_score

        Requirements: 1.1, 1.3, 8.2, 6.1
        """
        chunk_ids: Set[str] = set()
        source_mappings: Dict[str, ChunkSourceMapping] = {}
        # Track ALL concept matches per chunk for coverage scoring
        chunk_concept_hits: Dict[str, List[Dict[str, Any]]] = {}

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

            # Skip generic verb-derived concepts entirely for chunk
            # retrieval.  They fan out to many irrelevant chunks and
            # don't contribute to coverage_bonus (which only counts
            # specific concepts).  This dramatically reduces Neo4j
            # queries and prevents timeouts on verb-heavy queries.
            is_specific = not is_generic_concept(concept_name)
            if not is_specific and concept.get("match_type") == "semantic":
                logger.debug(
                    f"Skipping generic concept '{concept_name}' "
                    f"for chunk retrieval"
                )
                continue

            # Check cache first (Requirement 8.2)
            cached_entry = self._get_cached_source_chunks(concept_id)

            if cached_entry:
                self._cache_hits += 1
                concept_chunk_ids = cached_entry.chunk_ids
                logger.debug(f"Cache hit for concept {concept_name}: {len(concept_chunk_ids)} chunks")
            else:
                self._cache_misses += 1
                # Query Neo4j for chunk IDs via EXTRACTED_FROM traversal (Requirement 6.1)
                concept_chunk_ids = await self._query_chunk_ids_for_concept(concept_id)

                # Name expansion for SPECIFIC concepts only: also retrieve
                # chunks from sibling concepts with the same name but
                # different concept_ids (e.g., "Chelsea" as PERSON vs ORG
                # vs CODE_TERM all link to different chunks).
                if is_specific and concept_name and self._neo4j_client:
                    try:
                        sibling_chunks = await self._query_chunks_by_concept_name(
                            concept_name, exclude_concept_id=concept_id
                        )
                        if sibling_chunks:
                            before = len(concept_chunk_ids)
                            existing = set(concept_chunk_ids)
                            for cid in sibling_chunks:
                                if cid not in existing:
                                    concept_chunk_ids.append(cid)
                                    existing.add(cid)
                            if len(concept_chunk_ids) > before:
                                logger.info(
                                    f"Name expansion for '{concept_name}': "
                                    f"{before} → {len(concept_chunk_ids)} chunks"
                                )
                    except Exception as e:
                        logger.debug(f"Name expansion failed for '{concept_name}': {e}")

                # Cache the result (stores chunk ID lists directly from graph traversal)
                self._cache_source_chunks(concept_id, concept_name, concept_chunk_ids)
                logger.debug(f"Cached chunk IDs for concept {concept_name}: {len(concept_chunk_ids)} chunks")

            # Add chunks with source mapping and track concept hits
            hit_info = {
                "concept_id": concept_id,
                "concept_name": concept_name,
                "match_score": concept_match_score,
            }
            for chunk_id in concept_chunk_ids:
                if not chunk_id:
                    continue
                # Track every concept that links to this chunk
                chunk_concept_hits.setdefault(chunk_id, []).append(hit_info)
                # Source mapping stores the first (highest-scoring) concept
                if chunk_id not in chunk_ids:
                    chunk_ids.add(chunk_id)
                    source_mappings[chunk_id] = ChunkSourceMapping(
                        chunk_id=chunk_id,
                        source_concept_id=concept_id,
                        source_concept_name=concept_name,
                        retrieval_source=RetrievalSource.DIRECT_CONCEPT,
                        hop_distance=0,
                        match_score=concept_match_score,
                    )

        return chunk_ids, source_mappings, chunk_concept_hits

    async def _compute_rationale_sims(
        self,
        concept_ids: List[str],
        chunk_ids: Set[str],
        query: str,
    ) -> Dict[Tuple[str, str], float]:
        """Compute rationale→query cosine similarity per (concept_id, chunk_id).

        Fetches the LLM rationale embedding stored on each EXTRACTED_FROM edge
        for the matched concepts (bounded to the candidate chunks), embeds the
        query once, and returns a cosine-similarity map used to boost chunks
        whose concept rationale is semantically close to the query.  Degrades
        to an empty map when the model/Neo4j clients are unavailable.
        """
        if not concept_ids or not chunk_ids:
            return {}
        if not self._model_client or not self._neo4j_client:
            return {}
        if not query or not query.strip():
            return {}

        try:
            q_embs = await self._model_client.generate_embeddings([query])
        except Exception as e:
            logger.warning(f"Rationale boost: query embedding failed: {e}")
            return {}
        if not q_embs:
            return {}
        q_emb = q_embs[0]

        cypher = """
        MATCH (c:Concept)-[r:EXTRACTED_FROM]->(ch:Chunk)
        WHERE c.concept_id IN $concept_ids
          AND ch.chunk_id IN $chunk_ids
          AND r.rationale_embedding IS NOT NULL
        RETURN c.concept_id AS concept_id,
               ch.chunk_id AS chunk_id,
               r.rationale_embedding AS emb
        """
        try:
            rows = await with_timeout(
                self._neo4j_client.execute_query(
                    cypher,
                    {
                        "concept_ids": list(concept_ids),
                        "chunk_ids": list(chunk_ids),
                    },
                ),
                self._query_timeout,
            )
        except Exception as e:
            logger.debug(f"Rationale boost: edge query failed: {e}")
            return {}

        def _cos(a, b) -> float:
            dot = sum(x * y for x, y in zip(a, b))
            na = sum(x * x for x in a) ** 0.5
            nb = sum(x * x for x in b) ** 0.5
            return dot / (na * nb) if na and nb else 0.0

        sims: Dict[Tuple[str, str], float] = {}
        for row in (rows or []):
            emb = row.get("emb")
            if not emb:
                continue
            sims[(row["concept_id"], row["chunk_id"])] = _cos(q_emb, emb)
        if sims:
            logger.info(
                f"Rationale boost: computed {len(sims)} rationale→query "
                f"similarities (max={max(sims.values()):.3f})"
            )
        return sims

    async def _query_chunk_ids_for_concept(self, concept_id: str) -> List[str]:
        """
        Query Neo4j for chunk IDs linked to a concept via EXTRACTED_FROM traversal.

        Args:
            concept_id: The concept ID to look up

        Returns:
            List of chunk IDs

        Requirements: 6.1
        """
        if not self._neo4j_client:
            return []

        try:
            cypher_query = """
            MATCH (c:Concept {concept_id: $concept_id})-[:EXTRACTED_FROM]->(ch:Chunk)
            RETURN ch.chunk_id AS chunk_id
            """
            results = await with_timeout(
                self._neo4j_client.execute_query(
                    cypher_query, {"concept_id": concept_id}
                ),
                self._query_timeout,
            )
            return [
                r["chunk_id"]
                for r in (results or [])
                if r.get("chunk_id")
            ]
        except asyncio.TimeoutError:
            logger.warning(f"Timeout querying chunk IDs for concept {concept_id}")
            return []
        except Exception as e:
            logger.warning(f"Error querying chunk IDs for concept {concept_id}: {e}")
            return []

    async def _query_chunks_by_concept_name(
        self, concept_name: str, exclude_concept_id: str = ""
    ) -> List[str]:
        """Query Neo4j for chunk IDs from sibling concepts with the same name.

        When the KG has multiple concepts named "Chelsea" (PERSON, ORG,
        CODE_TERM), the semantic vector search returns only one.  This
        method finds chunks linked to the OTHER concepts with the same
        name so they are treated as direct chunks (not related).

        Args:
            concept_name: The concept name to look up.
            exclude_concept_id: Concept ID to exclude (already queried).

        Returns:
            List of chunk IDs from sibling concepts.
        """
        if not self._neo4j_client:
            return []

        try:
            cypher = """
            MATCH (c:Concept)-[:EXTRACTED_FROM]->(ch:Chunk)
            WHERE c.name = $name
              AND c.concept_id <> $exclude_id
              AND NOT c.type IN ['PERSON']
            RETURN DISTINCT ch.chunk_id AS chunk_id
            """
            results = await with_timeout(
                self._neo4j_client.execute_query(
                    cypher,
                    {"name": concept_name, "exclude_id": exclude_concept_id},
                ),
                self._query_timeout,
            )
            return [
                r["chunk_id"]
                for r in (results or [])
                if r.get("chunk_id")
            ]
        except Exception as e:
            logger.debug(
                f"Sibling concept query failed for '{concept_name}': {e}"
            )
            return []

    async def _retrieve_related_chunks(
        self, concept_matches: List[Dict[str, Any]]
    ) -> Tuple[Set[str], Dict[str, ChunkSourceMapping], List[Dict[str, Any]]]:
        """
        Retrieve chunks from related concepts via relationship traversal.

        Runs all concept traversals concurrently via asyncio.gather for
        performance — total time ≈ slowest single concept, not the sum.

        Also identifies 1-hop related concepts for promotion to direct
        retrieval: concepts discovered via traversal that have document
        chunks are candidates for full scoring weight instead of the
        hop-distance decay applied to related chunks.

        Args:
            concept_matches: List of matched concepts from query decomposition

        Returns:
            Tuple of (chunk_ids, source_mappings, promoted_concepts)
            promoted_concepts is a list of dicts with keys:
                concept_id, concept_name, chunk_ids, match_score

        Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 6.2
        """
        chunk_ids: Set[str] = set()
        source_mappings: Dict[str, ChunkSourceMapping] = {}
        promoted_concepts: List[Dict[str, Any]] = []

        if not self._neo4j_client:
            logger.debug("No Neo4j client available for relationship traversal")
            return chunk_ids, source_mappings, promoted_concepts

        # Build list of (concept_meta, coroutine) for concurrent execution.
        # 1-hop traversal is limited to top-N concepts to keep query count
        # manageable — each traversal is a separate Neo4j round-trip.
        tasks: list = []
        task_meta: list = []

        # Sort key: semantic matches first (higher quality for traversal),
        # then by score descending within each group.  Lexical Lucene scores
        # are inflated (exact phrase match) and produce garbage intermediates
        # like "woman presents" → "(see figure)" → "with".
        def _traversal_sort_key(c: Dict[str, Any]) -> Tuple[int, float]:
            is_sem = 1 if c.get("match_type") == "semantic" else 0
            score = float(c.get("similarity_score", c.get("match_score", 0)))
            return (is_sem, score)

        sorted_matches = sorted(
            concept_matches, key=_traversal_sort_key, reverse=True
        )

        for concept in sorted_matches[:_MAX_CONCEPTS_FOR_1HOP]:
            concept_id = concept.get("concept_id", "")
            concept_name = concept.get("name", "")
            if concept.get("match_type") == "semantic":
                parent_score = float(concept.get("similarity_score", 0.0))
            else:
                parent_score = float(concept.get("match_score", 0.0))

            if not concept_id:
                continue

            # Skip generic concepts for relationship traversal —
            # they fan out to thousands of related chunks via hops.
            if is_generic_concept(concept_name) and concept.get("match_type") == "semantic":
                continue

            tasks.append(self._query_related_concepts(concept_id, concept_name))
            task_meta.append((concept_id, concept_name, parent_score, "umls_1hop"))

        # UMLS-aware 1-hop traversal: Concept → SAME_AS → UMLSConcept
        # → UMLS_REL → UMLSConcept → SAME_AS → Concept.
        # Surfaces treatment/diagnostic concepts reachable via
        # validated clinical edges even when no direct Concept→Concept
        # edge exists.
        # Uses a narrower cap than plain 1-hop because each query walks
        # the 13.9M-edge UMLS_REL graph.
        for concept in sorted_matches[:_MAX_CONCEPTS_FOR_UMLS_1HOP]:
            concept_id = concept.get("concept_id", "")
            concept_name = concept.get("name", "")
            if concept.get("match_type") == "semantic":
                parent_score = float(concept.get("similarity_score", 0.0))
            else:
                parent_score = float(concept.get("match_score", 0.0))

            if not concept_id:
                continue
            if is_generic_concept(concept_name) and concept.get("match_type") == "semantic":
                continue

            tasks.append(
                self._query_umls_related_concepts(concept_id, concept_name)
            )
            task_meta.append(
                (concept_id, concept_name, parent_score, "umls_bridge")
            )

        # 2-hop traversal for top-N concepts only (Requirement 2.2).
        # Limits fan-out to keep query times reasonable.
        if self._max_hops >= 2:
            sorted_concepts = sorted(
                concept_matches, key=_traversal_sort_key, reverse=True
            )
            for concept in sorted_concepts[:_MAX_CONCEPTS_FOR_2HOP]:
                cid = concept.get("concept_id", "")
                cname = concept.get("name", "")
                if not cid:
                    continue
                if concept.get("match_type") == "semantic":
                    pscore = float(concept.get("similarity_score", 0.0))
                else:
                    pscore = float(concept.get("match_score", 0.0))
                tasks.append(
                    self._query_2hop_related_concepts(cid, cname)
                )
                task_meta.append((cid, cname, pscore, "umls_2hop"))

                # 2-hop UMLS bridge: reaches treatment concepts 2 clinical
                # hops away (e.g., pneumonia → isa → Bacterial Pneumonia
                # → may_treat → doxycycline).
                tasks.append(
                    self._query_umls_2hop_related_concepts(cid, cname)
                )
                task_meta.append(
                    (cid, cname, pscore, "umls_bridge_2hop")
                )

        if not tasks:
            return chunk_ids, source_mappings, promoted_concepts

        # Run all traversals concurrently; individual failures return []
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for (concept_id, concept_name, parent_score, path_type), result in zip(
            task_meta, results
        ):
            if isinstance(result, Exception):
                logger.warning(
                    f"Error traversing relationships for concept {concept_name}: {result}"
                )
                continue

            for related in result:
                related_id = related.get("concept_id", "")
                related_name = related.get("name", "")
                hop_distance = related.get("hop_distance", 1)
                relationship_path = related.get("relationship_path", [])
                related_chunk_ids = related.get("chunk_ids", [])

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
                            path_type=path_type,
                            match_score=parent_score,
                        )

                # Promote related concepts reached via clinical edges
                # to direct retrieval status.  Concept expansion:
                # symptom → diagnosis traversal (e.g. "productive cough"
                # IsA "cough" → HasContext "pneumonia") gets full scoring
                # weight instead of the hop-distance decay ceiling.
                #
                # 1-hop: promote when the single relationship type is
                # clinically meaningful (UMLS rela or ConceptNet edge).
                #
                # 2-hop UMLS bridge: promote when both hops use
                # clinically-meaningful UMLS rela types — the path
                # pneumonia → isa → Bacterial Pneumonia → may_treat →
                # doxycycline is clinically validated and deserves full
                # scoring weight.
                if related_chunk_ids:
                    promoted = False
                    if hop_distance == 1:
                        rel_type = relationship_path[0] if relationship_path else ""
                        if (rel_type in _PROMOTION_ELIGIBLE_RELATIONSHIPS
                                or rel_type in _UMLS_PROMOTION_ELIGIBLE_RELA):
                            promoted = True
                    elif hop_distance == 2 and path_type in ("umls_bridge_2hop",):
                        rela1 = relationship_path[0] if len(relationship_path) > 0 else ""
                        rela2 = relationship_path[1] if len(relationship_path) > 1 else ""
                        if (rela1 in _UMLS_PROMOTION_ELIGIBLE_RELA
                                and rela2 in _UMLS_PROMOTION_ELIGIBLE_RELA):
                            promoted = True
                    if promoted:
                        promoted_concepts.append({
                            "concept_id": related_id,
                            "concept_name": related_name,
                            "chunk_ids": list(related_chunk_ids),
                            "match_score": parent_score,
                        })

        logger.debug(f"Found {len(chunk_ids)} chunks from related concepts "
                     f"(+{len(promoted_concepts)} concepts promoted to direct)")
        return chunk_ids, source_mappings, promoted_concepts

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
            # Collects chunk IDs via EXTRACTED_FROM traversal (Requirement 6.2).
            # LIMIT is applied BEFORE OPTIONAL MATCH so only the top-N related
            # concepts get their chunk lists resolved.
            cypher_query = f"""
            MATCH (start:Concept {{concept_id: $concept_id}})
                  -[r:{rel_types}]-(related:Concept)
            WHERE related.concept_id <> start.concept_id
            WITH DISTINCT related, type(r) as rel_type, start
            ORDER BY related.concept_id
            LIMIT 20
            OPTIONAL MATCH (related)-[:EXTRACTED_FROM]->(ch:Chunk)
            RETURN DISTINCT
                related.concept_id as concept_id,
                related.name as name,
                collect(DISTINCT ch.chunk_id) as chunk_ids,
                1 as hop_distance,
                [rel_type] as relationship_path,
                [start.name, related.name] as path_names
            """

            results = await with_timeout(
                self._neo4j_client.execute_query(
                    cypher_query, {"concept_id": concept_id}
                ),
                self._query_timeout
            )

            related_concepts = []
            for r in results or []:
                # chunk_ids comes as a list directly from collect()
                raw_chunk_ids = r.get("chunk_ids", [])
                # Filter out None values that may come from OPTIONAL MATCH
                chunk_ids = [cid for cid in raw_chunk_ids if cid]
                related_concepts.append({
                    "concept_id": r.get("concept_id", ""),
                    "name": r.get("name", ""),
                    "chunk_ids": chunk_ids,
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

    async def _query_umls_related_concepts(
        self, concept_id: str, concept_name: str
    ) -> List[Dict[str, Any]]:
        """
        Query Neo4j for UMLS-related concepts via SAME_AS → UMLS_REL bridge.

        Walks: Concept → SAME_AS → UMLSConcept → UMLS_REL → UMLSConcept
        → SAME_AS → Concept, collecting EXTRACTED_FROM chunks from the
        far-side document Concepts. This surfaces treatment concepts
        (e.g., doxycycline) that are clinically related to a diagnosis
        concept (e.g., pneumonia) via validated UMLS edges, even when
        no direct Concept→Concept edge exists.

        Only traverses UMLS_REL edges with clinically meaningful
        rela_type values — excludes qualifier metadata, drug composition,
        trade names, and administrative mappings.

        Args:
            concept_id: Starting concept ID
            concept_name: Starting concept name (for logging)

        Returns:
            List of related concept dicts with keys:
            concept_id, name, chunk_ids, hop_distance=1,
            relationship_path=[rela_type], path_names
        """
        if not self._neo4j_client:
            return []

        try:
            if hasattr(self._neo4j_client, '_is_connected') and not self._neo4j_client._is_connected:
                logger.info("Neo4j client connection is stale, reconnecting...")
                if hasattr(self._neo4j_client, 'connect'):
                    await self._neo4j_client.connect()

            clinical_rela = RelationshipTraverser.CLINICALLY_MEANINGFUL_UMLS_RELA

            cypher = """
            MATCH (start:Concept {concept_id: $concept_id})
                  -[:SAME_AS]->(ua:UMLSConcept)
                  -[r:UMLS_REL]-(ub:UMLSConcept)
            WHERE r.rela_type IN $clinical_rela
              AND ub.preferred_name IS NOT NULL
            WITH DISTINCT ub, r.rela_type AS rela_type, start
            ORDER BY ub.cui
            LIMIT 20
            OPTIONAL MATCH (target:Concept)-[:SAME_AS]->(ub)
            WHERE target.concept_id <> start.concept_id
            OPTIONAL MATCH (target)-[:EXTRACTED_FROM]->(ch:Chunk)
            RETURN DISTINCT
                target.concept_id AS concept_id,
                target.name AS name,
                collect(DISTINCT ch.chunk_id) AS chunk_ids,
                1 AS hop_distance,
                [rela_type] AS relationship_path,
                [start.name, ub.preferred_name] AS path_names
            """

            results = await with_timeout(
                self._neo4j_client.execute_query(
                    cypher,
                    {
                        "concept_id": concept_id,
                        "clinical_rela": clinical_rela,
                    },
                ),
                self._query_timeout,
            )

            related_concepts = []
            for r in results or []:
                raw_chunk_ids = r.get("chunk_ids", [])
                chunk_ids = [cid for cid in raw_chunk_ids if cid]
                related_concepts.append({
                    "concept_id": r.get("concept_id", ""),
                    "name": r.get("name", ""),
                    "chunk_ids": chunk_ids,
                    "hop_distance": r.get("hop_distance", 1),
                    "relationship_path": r.get("relationship_path", []),
                })

            logger.debug(
                f"Found {len(related_concepts)} UMLS-related concepts for {concept_name}"
            )
            return related_concepts

        except asyncio.TimeoutError:
            logger.warning(
                f"Timeout querying UMLS-related concepts for {concept_name}"
            )
            return []
        except Exception as e:
            logger.warning(
                f"Error querying UMLS-related concepts for {concept_name}: {e}"
            )
            return []

    async def _query_umls_2hop_related_concepts(
        self, concept_id: str, concept_name: str,
    ) -> List[Dict[str, Any]]:
        """
        Query Neo4j for UMLS-related concepts within 2 UMLS_REL hops.

        Walks: Concept → SAME_AS → UMLSConcept → UMLS_REL →
        UMLSConcept → UMLS_REL → UMLSConcept → SAME_AS → Concept.

        This reaches treatment concepts that are 2 clinical hops away
        (e.g., pneumonia → isa → Bacterial Pneumonia → may_treat →
        doxycycline) which the 1-hop UMLS traversal misses.

        Bounded with LIMITs at each hop to prevent fan-out explosion.

        Args:
            concept_id: Starting concept ID
            concept_name: Starting concept name (for logging)

        Returns:
            List of related concept dicts with keys:
            concept_id, name, chunk_ids, hop_distance=2,
            relationship_path=[rela_type_1, rela_type_2], path_names
        """
        if not self._neo4j_client:
            return []

        try:
            if hasattr(self._neo4j_client, '_is_connected') and not self._neo4j_client._is_connected:
                logger.info("Neo4j client connection is stale, reconnecting...")
                if hasattr(self._neo4j_client, 'connect'):
                    await self._neo4j_client.connect()

            # Use a focused subset for 2-hop — the full clinical_rela
            # list (50+ types) produces 10K+ targets, pushing clinically
            # relevant concepts like doxycycline past the LIMIT.
            clinical_rela_focused = [
                "isa", "inverse_isa",
                "may_treat", "may_be_treated_by",
                "cause_of", "due_to",
                "has_manifestation", "manifestation_of",
            ]

            cypher = """
            MATCH (start:Concept {concept_id: $concept_id})
                  -[:SAME_AS]->(ua:UMLSConcept)
                  -[r1:UMLS_REL]-(umid:UMLSConcept)
            WHERE r1.rela_type IN $clinical_rela
              AND umid <> ua
            WITH DISTINCT umid, r1.rela_type AS rela1, start, ua
            ORDER BY umid.cui
            LIMIT 10
            MATCH (umid)-[r2:UMLS_REL]-(ub:UMLSConcept)
            WHERE r2.rela_type IN $clinical_rela
              AND ub <> umid
              AND ub <> ua
              AND ub.preferred_name IS NOT NULL
            // Aggregate paths per unique UMLS target to prevent
            // multi-path duplicates from inflating the effective
            // position of each target in the ordered set.
            WITH ub, rela1, r2.rela_type AS rela2, start, umid
            WITH ub,
                 collect({rela1: rela1, rela2: rela2,
                          umid_name: umid.preferred_name,
                          start_name: start.name}) AS paths,
                 start
            ORDER BY ub.cui
            LIMIT 50
            UNWIND paths AS path
            OPTIONAL MATCH (target:Concept)-[:SAME_AS]->(ub)
            WHERE target.concept_id <> start.concept_id
            OPTIONAL MATCH (target)-[:EXTRACTED_FROM]->(ch:Chunk)
            RETURN DISTINCT
                target.concept_id AS concept_id,
                target.name AS name,
                collect(DISTINCT ch.chunk_id) AS chunk_ids,
                2 AS hop_distance,
                [path.rela1, path.rela2] AS relationship_path,
                [path.start_name, path.umid_name, ub.preferred_name]
                    AS path_names
            """

            results = await with_timeout(
                self._neo4j_client.execute_query(
                    cypher,
                    {
                        "concept_id": concept_id,
                        "clinical_rela": clinical_rela_focused,
                    },
                ),
                self._query_timeout,
            )

            related_concepts = []
            for r in results or []:
                raw_chunk_ids = r.get("chunk_ids", [])
                chunk_ids = [cid for cid in raw_chunk_ids if cid]
                related_concepts.append({
                    "concept_id": r.get("concept_id", ""),
                    "name": r.get("name", ""),
                    "chunk_ids": chunk_ids,
                    "hop_distance": r.get("hop_distance", 2),
                    "relationship_path": r.get("relationship_path", []),
                })

            logger.debug(
                f"Found {len(related_concepts)} UMLS 2-hop concepts "
                f"for {concept_name}"
            )
            return related_concepts

        except asyncio.TimeoutError:
            logger.warning(
                f"Timeout querying UMLS 2-hop concepts for {concept_name}"
            )
            return []
        except Exception as e:
            logger.warning(
                f"Error querying UMLS 2-hop concepts for {concept_name}: {e}"
            )
            return []

    async def _query_2hop_related_concepts(
        self, concept_id: str, concept_name: str,
    ) -> List[Dict[str, Any]]:
        """
        Query Neo4j for related concepts within 2 hops.

        Uses a single bounded Cypher query: 1-hop to intermediates
        (LIMIT 5), then from each intermediate expands to 2-hop targets
        (LIMIT 5 per intermediate).  This avoids the *1..2 variable-length
        pattern while keeping to a single round-trip.

        Args:
            concept_id: Starting concept ID
            concept_name: Starting concept name (for logging)

        Returns:
            List of 2-hop related concept dictionaries with hop_distance=2
        """
        if not self._neo4j_client:
            return []

        rel_types = "|".join(PRIORITY_RELATIONSHIP_TYPES)

        try:
            # Single-query 2-hop: bound intermediates via LIMIT, then
            # unbind to targets.  Keeps fan-out predictable.
            # LIMIT is applied BEFORE OPTIONAL MATCH so only the top-N
            # targets get their chunk lists resolved.
            cypher = f"""
            MATCH (start:Concept {{concept_id: $concept_id}})
                  -[r1:{rel_types}]-(mid:Concept)
            WHERE mid.concept_id <> start.concept_id
            WITH mid, type(r1) as rel1, start.name as start_name
            ORDER BY mid.concept_id
            LIMIT $intermediate_limit
            MATCH (mid)-[r2:{rel_types}]-(target:Concept)
            WHERE target.concept_id <> $concept_id
              AND target.concept_id <> mid.concept_id
            WITH DISTINCT target, rel1, type(r2) as rel2, start_name, mid.name as mid_name
            ORDER BY target.concept_id
            LIMIT $target_limit
            OPTIONAL MATCH (target)-[:EXTRACTED_FROM]->(ch:Chunk)
            RETURN DISTINCT
                target.concept_id as concept_id,
                target.name as name,
                collect(DISTINCT ch.chunk_id) as chunk_ids,
                2 as hop_distance,
                [rel1, rel2] as relationship_path,
                [start_name, mid_name, target.name] as path_names
            """

            results = await with_timeout(
                self._neo4j_client.execute_query(
                    cypher, {
                        "concept_id": concept_id,
                        "intermediate_limit": _MAX_2HOP_INTERMEDIATE,
                        "target_limit": _MAX_2HOP_INTERMEDIATE * _MAX_2HOP_TARGETS_PER_INTERMEDIATE,
                    }
                ),
                self._query_timeout * 3,  # 2-hop walks more edges, keep ~15s
            )

            two_hop: List[Dict[str, Any]] = []
            for row in (results or []):
                raw_chunk_ids = row.get("chunk_ids", [])
                chunk_ids = [cid for cid in raw_chunk_ids if cid]
                if chunk_ids:
                    two_hop.append({
                        "concept_id": row.get("concept_id", ""),
                        "name": row.get("name", ""),
                        "chunk_ids": chunk_ids,
                        "hop_distance": 2,
                        "relationship_path": row.get("relationship_path", []),
                        "path_names": row.get("path_names", []),
                    })

            logger.info(
                f"2-hop traversal for '{concept_name}': "
                f"{len(two_hop)} targets with chunks"
            )
            return two_hop

        except asyncio.TimeoutError:
            logger.warning(f"Timeout in 2-hop traversal for {concept_name}")
            return []
        except Exception as e:
            logger.warning(f"Error in 2-hop traversal for {concept_name}: {e}")
            return []

    def _aggregate_and_deduplicate(
        self,
        direct_chunks: List[RetrievedChunk],
        related_chunks: List[RetrievedChunk],
        source_mappings: Dict[str, ChunkSourceMapping],
        chunk_concept_hits: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        query: str = "",
        matched_concept_names: Optional[List[str]] = None,
        rationale_sim_by_pair: Optional[Dict[Tuple[str, str], float]] = None,
    ) -> List[RetrievedChunk]:
        """
        Aggregate and deduplicate chunks from multiple sources.

        Uses concept-coverage scoring: chunks that match MORE query concepts
        get higher kg_relevance_scores. This rewards chunks that sit at the
        intersection of multiple query concepts over chunks that only match
        a single generic concept.

        Scoring formula for direct chunks:
            base_score = max(normalized concept match scores)
            coverage_bonus = log2(num_matched_concepts) * 0.1
            kg_relevance_score = min(1.0, base_score + coverage_bonus)

        Related chunks get hop-distance-decayed scores and are capped.

        Args:
            direct_chunks: Chunks from direct concept retrieval
            related_chunks: Chunks from relationship traversal
            source_mappings: Mapping of chunk IDs to their source provenance
            chunk_concept_hits: Mapping of chunk_id -> list of all concept
                matches for that chunk (from _retrieve_direct_chunks)

        Returns:
            Deduplicated list of chunks with concept-coverage-aware scores

        Requirements: 1.5, 2.1, 2.2, 3.1, 3.2, 3.3
        """

        seen_ids: Set[str] = set()
        aggregated: List[RetrievedChunk] = []
        concept_hits = chunk_concept_hits or {}

        # Document chunk-hit concentration: reward chunks from documents
        # where a higher proportion of concept-matched chunks originate.
        # Global concept nodes in Neo4j (source_document: NULL) cause
        # cross-document pollution — this soft boost counters that by
        # weighting document relevance into the KG score via the fraction
        # of concept-hit chunks that belong to each document.
        chunk_to_doc: Dict[str, str] = {}
        for chunk in direct_chunks + related_chunks:
            doc_id = (
                chunk.metadata.get('source_id')
                or chunk.metadata.get('document_id')
            )
            if doc_id:
                chunk_to_doc[chunk.chunk_id] = str(doc_id)

        # Count concept-hit chunks per document (concentration metric).
        # A document contributing 40/50 concept-hit chunks gets a larger
        # boost than one contributing only 5/50 — even when only a single
        # concept is matched by the query.
        doc_hit_counts: Dict[str, int] = {}
        total_chunks_with_hits = 0
        for cid in concept_hits:
            doc_id = chunk_to_doc.get(cid)
            if doc_id:
                doc_hit_counts[doc_id] = doc_hit_counts.get(doc_id, 0) + 1
                total_chunks_with_hits += 1

        # Concept IDF: rare concepts that appear in few documents get
        # higher weight in the coverage bonus. Common terms like
        # "diagnosis" that span many documents contribute less.
        concept_to_docs: Dict[str, Set[str]] = {}
        for cid, hits_list in concept_hits.items():
            doc_id = chunk_to_doc.get(cid)
            if doc_id:
                for h in hits_list:
                    name = re.sub(
                        r'[^a-z0-9\s]', '',
                        h["concept_name"].lower(),
                    ).strip()
                    if name not in concept_to_docs:
                        concept_to_docs[name] = set()
                    concept_to_docs[name].add(doc_id)
        num_docs = len(set(chunk_to_doc.values()))
        concept_idf: Dict[str, float] = {}
        for name, doc_set in concept_to_docs.items():
            df = len(doc_set)
            idf_raw = math.log(max(1, num_docs) / max(1, df))
            concept_idf[name] = min(2.0, max(0.5, idf_raw))

        # Document-title relevance: boost chunks from documents whose
        # titles overlap with query content words.  A query about
        # "community-acquired pneumonia" should give higher weight to
        # chunks from "Diagnosis and Treatment of Adults with
        # Community-Acquired Pneumonia" than from "Ferris Clinical
        # Advisor 2021", even when both match the same concepts.
        # Fetch document titles from PostgreSQL — Milvus chunk metadata
        # does not include title/document_title fields.
        doc_id_to_title: Dict[str, str] = {}
        if chunk_to_doc:
            try:
                from src.multimodal_librarian.database.connection import db_manager
                from sqlalchemy import text
                if not db_manager.SessionLocal:
                    db_manager.initialize()
                doc_ids = list({str(d) for d in chunk_to_doc.values()})
                with db_manager.get_session() as session:
                    result = session.execute(
                        text(
                            "SELECT id::text, title "
                            "FROM multimodal_librarian.knowledge_sources "
                            "WHERE id::text = ANY(:ids)"
                        ),
                        {"ids": doc_ids},
                    )
                    for row in result:
                        doc_id_to_title[row[0]] = str(row[1])
            except Exception as e:
                logger.warning(
                    f"Failed to fetch document titles from PostgreSQL: {e}"
                )

        _QUERY_TITLE_BOOST_WEIGHT = 0.15
        _CONCEPT_TITLE_BOOST_WEIGHT = 0.30
        _RATIONALE_WEIGHT = 0.25
        _rationale_sims = rationale_sim_by_pair or {}
        _QUERY_STOPWORDS = {
            'what', 'is', 'the', 'a', 'an', 'and', 'or', 'of', 'in', 'to',
            'for', 'with', 'on', 'at', 'by', 'from', 'about', 'are', 'was',
            'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does',
            'did', 'will', 'would', 'could', 'should', 'may', 'might', 'can',
            'shall', 'not', 'no', 'so', 'as', 'if', 'then', 'than', 'that',
            'this', 'these', 'those', 'it', 'its', 'they', 'them', 'their',
            'we', 'us', 'our', 'you', 'your', 'he', 'she', 'his', 'her',
            'who', 'whom', 'which', 'how', 'when', 'where', 'why', 'but',
            'also', 'very', 'just', 'still', 'already', 'only', 'even',
        }
        doc_title_boost: Dict[str, float] = {}
        if query and doc_id_to_title:
            # Split on whitespace AND hyphens so that both
            # "community-acquired pneumonia" and
            # "metlay-et-al-2019-diagnosis-and-treatment-of-adults-with-
            #  community-acquired-pneumonia-..." produce overlapping tokens.
            _word_split = re.compile(r'[-\s]+')
            query_words = {
                w.lower().strip('?.,!"\'();:[]{}')
                for w in _word_split.split(query)
                if len(w) > 2 and w.lower() not in _QUERY_STOPWORDS
            }
            for doc_id, title in doc_id_to_title.items():
                title_words = {
                    w.lower().strip('?.,!"\'();:[]{}')
                    for w in _word_split.split(title)
                    if len(w) > 2
                }
                if query_words and title_words:
                    overlap = query_words & title_words
                    overlap_ratio = len(overlap) / max(1, len(query_words))
                    doc_title_boost[doc_id] = 1.0 + overlap_ratio * _QUERY_TITLE_BOOST_WEIGHT
                    if overlap:
                        logger.info(
                            f"Title boost: doc={doc_id[:8]}... "
                            f"title='{title[:80]}...' "
                            f"overlap={overlap} ratio={overlap_ratio:.2f} "
                            f"boost={doc_title_boost[doc_id]:.3f}"
                        )
                else:
                    doc_title_boost[doc_id] = 1.0
        else:
            for doc_id in doc_id_to_title:
                doc_title_boost[doc_id] = 1.0

        # Concept→document title boost: when a concept like
        # "community-acquired pneumonia" is matched, chunks from
        # documents whose titles contain that phrase get a stronger
        # boost than the generic query-word overlap alone provides.
        # This surfaces treatment chunks from documents that are
        # specifically about the matched diagnosis, even when NER
        # only linked one chunk via EXTRACTED_FROM.
        #
        # Per-concept scoring: for each matched concept, compute what
        # fraction of its words appear in the document title.  Sum
        # contributions across concepts so that a document matching
        # several specific concepts (e.g. "community-acquired pneumonia"
        # AND "pneumococcal pneumonia") gets a stronger boost than one
        # matching only a generic concept ("diagnosis").
        concept_title_boost: Dict[str, float] = {}
        if matched_concept_names and doc_id_to_title:
            _word_split = re.compile(r'[-\s]+')
            # Pre-tokenize each concept name: list of content words
            _concept_tokens: List[Tuple[str, List[str]]] = []
            for cname in matched_concept_names:
                tokens = [
                    w.lower().strip('?.,!"\'();:[]{}')
                    for w in _word_split.split(cname)
                    if len(w) > 2 and w.lower() not in _QUERY_STOPWORDS
                ]
                if tokens:
                    _concept_tokens.append((cname, tokens))
            if _concept_tokens:
                for doc_id, title in doc_id_to_title.items():
                    title_words = {
                        w.lower().strip('?.,!"\'();:[]{}')
                        for w in _word_split.split(title)
                        if len(w) > 2
                    }
                    # Also strip file extensions (.pdf, .txt, etc.)
                    # from title words so "pneumonia.pdf" matches
                    # the concept token "pneumonia".
                    title_words = {
                        w.rsplit('.', 1)[0] if '.' in w and len(w.rsplit('.', 1)[1]) <= 5 else w
                        for w in title_words
                    }
                    total_boost = 0.0
                    matched_details: List[str] = []
                    for cname, ctokens in _concept_tokens:
                        # Per-concept overlap: what fraction of this
                        # concept's words appear in the title?
                        c_overlap = sum(1 for t in ctokens if t in title_words)
                        c_ratio = c_overlap / len(ctokens)
                        # Threshold by concept length to avoid weak
                        # matches inflating the boost.  "antibiotic
                        # treatment" (2 words) should only match titles
                        # that contain BOTH words, otherwise "treatment"
                        # alone would match 50% of medical titles.
                        if len(ctokens) == 1:
                            min_ratio = 1.0    # single-word: exact match
                        elif len(ctokens) == 2:
                            min_ratio = 1.0    # 2-word: both words required
                        else:
                            min_ratio = 0.67   # 3+ word: at least 2/3
                        if c_ratio >= min_ratio:
                            total_boost += c_ratio * _CONCEPT_TITLE_BOOST_WEIGHT
                            matched_details.append(
                                f"{cname}({c_ratio:.0%})"
                            )
                    concept_title_boost[doc_id] = 1.0 + total_boost
                    if matched_details:
                        logger.info(
                            f"Concept-title boost: doc={doc_id[:8]}... "
                            f"title='{title[:80]}...' "
                            f"matched_concepts={matched_details} "
                            f"boost={concept_title_boost[doc_id]:.3f}"
                        )
            for doc_id in doc_id_to_title:
                if doc_id not in concept_title_boost:
                    concept_title_boost[doc_id] = 1.0
        else:
            for doc_id in doc_id_to_title:
                concept_title_boost[doc_id] = 1.0

        # Direct chunks: concept-coverage-aware scoring
        for chunk in direct_chunks:
            if chunk.chunk_id not in seen_ids:
                hits = concept_hits.get(chunk.chunk_id, [])
                if hits:
                    # Normalize each concept's match_score to [0.1, 1.0]
                    normalized_scores = [
                        min(1.0, max(0.1, h["match_score"] / 10.0))
                        for h in hits
                    ]
                    # Base score: best single concept match
                    base_score = max(normalized_scores)
                    # Coverage bonus: reward chunks matching DISTINCT concepts.
                    # Deduplicate by normalized name (lowercase, stripped of
                    # punctuation) so that e.g. "Chelsea" and "chelsea()" count
                    # as one concept rather than inflating the bonus.
                    distinct_names = {
                        re.sub(r'[^a-z0-9\s]', '', h["concept_name"].lower()).strip()
                        for h in hits
                    }
                    # Only count specific (non-generic) concepts for the
                    # coverage bonus.  Generic verb-derived concepts like
                    # "we observe" or "we saw" should not inflate the bonus.
                    # Fallback: if ALL concepts are generic, treat as a
                    # single concept (bonus = 0) to avoid inflating scores.
                    specific_names = {
                        name for name in distinct_names
                        if not is_generic_concept(name)
                    }
                    # Similarity + distinctiveness weighted coverage.
                    # Each distinct concept beyond the best contributes
                    # proportionally to both its match similarity and its
                    # IDF (rarer concepts across the result set weight more
                    # heavily).  Capped/clamped to [0.5, 2.0] so a concept
                    # in 1/N docs gets at most 2× weighting.
                    specific_pairs = []  # (name, max_score)
                    for name in specific_names:
                        max_score = max(
                            h["match_score"] for h in hits
                            if re.sub(r'[^a-z0-9\s]', '', h["concept_name"].lower()).strip() == name
                        )
                        specific_pairs.append((name, max_score))
                    if specific_pairs:
                        specific_pairs.sort(key=lambda x: x[1], reverse=True)
                        additional_pairs = specific_pairs[1:]
                        coverage_bonus = sum(
                            score / 10.0 * 0.15 * concept_idf.get(name, 0.5)
                            for name, score in additional_pairs
                        )
                    else:
                        coverage_bonus = 0.0
                    doc_id = chunk_to_doc.get(chunk.chunk_id)
                    doc_hit_count = doc_hit_counts.get(doc_id, 0) if doc_id else 0
                    concentration = doc_hit_count / max(1, total_chunks_with_hits)
                    doc_boost = 1.0 + concentration * 0.2
                    title_boost = doc_title_boost.get(doc_id, 1.0) if doc_id else 1.0
                    ctitle_boost = concept_title_boost.get(doc_id, 1.0) if doc_id else 1.0
                    # Rationale boost: when a concept's persisted LLM rationale
                    # is semantically close to the query, lift the chunk.  Uses
                    # the best rationale→query similarity across this chunk's
                    # concept hits (clamped to non-negative).
                    best_rat = 0.0
                    for h in hits:
                        s = _rationale_sims.get((h["concept_id"], chunk.chunk_id), 0.0)
                        if s > best_rat:
                            best_rat = s
                    rationale_boost = 1.0 + best_rat * _RATIONALE_WEIGHT
                    chunk.kg_relevance_score = min(1.0, (base_score + coverage_bonus) * doc_boost * title_boost * ctitle_boost * rationale_boost)
                    chunk.final_score = chunk.kg_relevance_score
                    # Store matched concepts on the chunk for downstream use
                    chunk.matched_concepts = hits
                    # Update concept_name to reflect the best-matching concept
                    best_hit = max(hits, key=lambda h: h["match_score"])
                    chunk.concept_name = best_hit["concept_name"]
                else:
                    # Fallback: use source_mapping score
                    mapping = source_mappings.get(chunk.chunk_id)
                    raw_score = mapping.match_score if mapping else 1.0
                    doc_id = chunk_to_doc.get(chunk.chunk_id)
                    doc_hit_count = doc_hit_counts.get(doc_id, 0) if doc_id else 0
                    concentration = doc_hit_count / max(1, total_chunks_with_hits)
                    doc_boost = 1.0 + concentration * 0.2
                    title_boost = doc_title_boost.get(doc_id, 1.0) if doc_id else 1.0
                    ctitle_boost = concept_title_boost.get(doc_id, 1.0) if doc_id else 1.0
                    # When concept-title alignment is strong, treat the
                    # chunk as having a synthetic concept hit.  A 100%
                    # concept→title match (e.g. "community-acquired
                    # pneumonia" all in the title) adds 0.30 to the
                    # boost, which translates to a 0.60 score bonus —
                    # enough to compete with direct NER concept hits.
                    concept_bonus = max(0.0, ctitle_boost - 1.0)
                    base_score = max(0.1, raw_score / 10.0) + concept_bonus * 2.0
                    chunk.kg_relevance_score = min(1.0, base_score * doc_boost * title_boost)
                    chunk.final_score = chunk.kg_relevance_score

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
                # Path-type-aware decay: UMLS clinical paths get minimal decay,
                # document-extracted edges and co-occurrence get standard decay.
                pt = mapping.path_type if mapping else None
                decay = _PATH_TYPE_DECAY.get(pt, self._hop_distance_decay)
                chunk.kg_relevance_score = decay ** hop
                chunk.final_score = chunk.kg_relevance_score

                seen_ids.add(chunk.chunk_id)
                aggregated.append(chunk)
                related_count += 1

        # Enrich ALL aggregated chunks with document titles from PostgreSQL.
        # _convert_kg_results in the RAG service reads metadata['document_title']
        # and surfaces it as "[Source N: <title>]" in the LLM prompt.
        # Also store the concept-title boost so downstream filters (e.g.
        # co-occurrence drop) can protect concept-aligned chunks.
        enriched = 0
        for chunk in aggregated:
            doc_id = chunk_to_doc.get(chunk.chunk_id)
            if doc_id and doc_id in doc_id_to_title:
                chunk.metadata['document_title'] = doc_id_to_title[doc_id]
                cboost = concept_title_boost.get(doc_id, 1.0)
                chunk.metadata['concept_title_boost'] = cboost
                enriched += 1

        logger.debug(
            f"Aggregated {len(aggregated)} unique chunks from "
            f"{len(direct_chunks)} direct + {len(related_chunks)} related "
            f"(capped related: {related_count}/{len(related_chunks)})"
        )
        return aggregated

    def _apply_relationship_boost(
        self,
        chunks: List[RetrievedChunk],
        traversal_result: TraversalResult,
        boost_factor: float,
    ) -> List[RetrievedChunk]:
        """
        Apply relationship boost to intersection chunks.

        For each chunk reachable from >= 2 query concepts via relationship
        paths, multiply its kg_relevance_score by a scaled boost factor
        and cap at 1.0.

        Scaling formula:
            scaled_boost = boost_factor * (1 + 0.1 * (num_concepts - 2))
            - 2 concepts: boost_factor * 1.0
            - 3 concepts: boost_factor * 1.1
            - 4 concepts: boost_factor * 1.2

        When boost_factor is 1.0, scores remain unchanged (identity).

        Args:
            chunks: List of retrieved chunks from aggregation
            traversal_result: Result from RelationshipTraverser.traverse()
            boost_factor: Base boost multiplier for intersection chunks

        Returns:
            Modified chunk list with boosted scores on intersection chunks

        Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 8.4
        """
        intersection_ids = traversal_result.intersection_chunk_ids

        if not intersection_ids:
            return chunks

        boosted_count = 0
        for chunk in chunks:
            if chunk.chunk_id in intersection_ids:
                num_concepts = traversal_result.concept_count_for_chunk(chunk.chunk_id)
                scaled_boost = boost_factor * (1 + 0.1 * (num_concepts - 2))
                chunk.kg_relevance_score = min(1.0, chunk.kg_relevance_score * scaled_boost)
                chunk.metadata["relationship_boost_applied"] = scaled_boost
                chunk.metadata["connecting_concept_count"] = num_concepts
                boosted_count += 1

        logger.debug(
            f"Applied relationship boost to {boosted_count}/{len(chunks)} chunks "
            f"(boost_factor={boost_factor}, intersection_chunks={len(intersection_ids)})"
        )
        return chunks

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
                        kg_relevance_score=0.3,  # Low KG score for augmented chunks — they weren't found via KG
                        semantic_score=similarity_score,
                        final_score=similarity_score * 0.6,  # Discount augmented chunks so KG-found chunks rank higher
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
                    executor = getattr(self._vector_client, '_executor', None)
                    return await loop.run_in_executor(
                        executor, lambda: method(query=query, top_k=top_k)
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

    def evict_chunks(self, stale_chunk_ids: set) -> int:
        """Surgically remove specific chunk IDs from the source_chunks cache.

        Iterates every cached entry and removes any chunk_id that appears
        in *stale_chunk_ids*.  Entries that become empty are dropped
        entirely.

        Args:
            stale_chunk_ids: Set of chunk IDs to evict.

        Returns:
            Number of cache entries modified or dropped.
        """
        if not stale_chunk_ids:
            return 0

        affected = 0
        to_delete: list = []

        for concept_id, entry in self._source_chunks_cache.items():
            before = len(entry.chunk_ids)
            entry.chunk_ids = [
                cid for cid in entry.chunk_ids if cid not in stale_chunk_ids
            ]
            if len(entry.chunk_ids) < before:
                affected += 1
                if not entry.chunk_ids:
                    to_delete.append(concept_id)

        for concept_id in to_delete:
            del self._source_chunks_cache[concept_id]

        if affected:
            logger.info(
                f"Evicted chunks from {affected} cache entries "
                f"({len(to_delete)} entries dropped entirely)"
            )
        return affected

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
        self._relationship_traverser.set_neo4j_client(client)
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
