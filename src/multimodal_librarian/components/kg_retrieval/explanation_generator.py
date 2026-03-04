"""
Explanation Generator Component for Knowledge Graph-Guided Retrieval.

This component generates human-readable explanations for retrieval results,
describing how chunks were found and why they are relevant. It handles
explanations for direct concept retrieval, relationship-based retrieval,
and fallback scenarios.

Requirements: 5.1, 5.2, 5.3, 5.5
"""

import logging
from typing import Any, Dict, List, Optional

from ...models.kg_retrieval import (
    KGRetrievalResult,
    QueryDecomposition,
    RetrievalSource,
    RetrievedChunk,
)

logger = logging.getLogger(__name__)


class ExplanationGenerator:
    """
    Generates explanations for knowledge graph-guided retrieval.

    Produces human-readable descriptions of how chunks were found
    and why they are relevant. Supports explanations for:
    - Direct concept retrieval (source_chunks from matched concepts)
    - Relationship-based retrieval (traversing graph relationships)
    - Fallback scenarios (when KG retrieval was not applicable)

    Example:
        generator = ExplanationGenerator()
        explanation = generator.generate(result, decomposition)
        # "Found 3 relevant chunks via knowledge graph. The concept 'Chelsea AI Ventures'
        #  directly referenced 2 chunks. 1 additional chunk was found through the
        #  relationship: Chelsea AI Ventures -> RELATED_TO -> AI Research."
    """

    def __init__(self):
        """Initialize ExplanationGenerator."""
        logger.debug("ExplanationGenerator initialized")

    def generate(
        self,
        result: KGRetrievalResult,
        query_decomposition: Optional[QueryDecomposition] = None,
    ) -> str:
        """
        Generate explanation for retrieval result.

        Creates a human-readable explanation describing:
        - How many chunks were found
        - Which concepts provided the chunks
        - What relationship paths were traversed
        - Whether fallback was used and why

        Args:
            result: The KGRetrievalResult containing chunks and metadata
            query_decomposition: Optional QueryDecomposition with extracted entities

        Returns:
            Human-readable explanation string

        Validates: Requirements 5.1, 5.2, 5.3, 5.5
        """
        if not result:
            return "No retrieval result available."

        # Use decomposition from result if not provided separately
        decomposition = query_decomposition or result.query_decomposition

        # Handle fallback case first
        if result.fallback_used:
            return self._generate_fallback_explanation(result, decomposition)

        # Handle empty results
        if not result.chunks:
            return self._generate_empty_result_explanation(decomposition)

        # Generate explanation for KG-based retrieval
        return self._generate_kg_retrieval_explanation(result, decomposition)

    def _generate_kg_retrieval_explanation(
        self,
        result: KGRetrievalResult,
        decomposition: Optional[QueryDecomposition],
    ) -> str:
        """
        Generate explanation for successful KG-based retrieval.

        Args:
            result: The retrieval result with chunks
            decomposition: Query decomposition details

        Returns:
            Explanation string for KG retrieval
        """
        parts: List[str] = []

        # Count chunks by source
        source_counts = result.get_source_distribution()
        total_chunks = len(result.chunks)

        # Opening statement
        parts.append(f"Found {total_chunks} relevant chunk{'s' if total_chunks != 1 else ''} via knowledge graph.")

        # Explain direct concept retrievals
        direct_count = source_counts.get(RetrievalSource.DIRECT_CONCEPT.value, 0)
        if direct_count > 0:
            direct_explanation = self._explain_direct_retrievals(result.chunks, decomposition)
            if direct_explanation:
                parts.append(direct_explanation)

        # Explain relationship-based retrievals
        related_count = source_counts.get(RetrievalSource.RELATED_CONCEPT.value, 0)
        path_count = source_counts.get(RetrievalSource.REASONING_PATH.value, 0)
        relationship_count = related_count + path_count

        if relationship_count > 0:
            relationship_explanation = self._explain_relationship_retrievals(result.chunks)
            if relationship_explanation:
                parts.append(relationship_explanation)

        # Explain semantic augmentation if used
        augment_count = source_counts.get(RetrievalSource.SEMANTIC_AUGMENT.value, 0)
        if augment_count > 0:
            parts.append(
                f"{augment_count} additional chunk{'s were' if augment_count != 1 else ' was'} "
                "added via semantic search to supplement the knowledge graph results."
            )

        # Add timing info if available
        if result.retrieval_time_ms > 0:
            parts.append(f"Retrieval completed in {result.retrieval_time_ms}ms.")

        return " ".join(parts)

    def _explain_direct_retrievals(
        self,
        chunks: List[RetrievedChunk],
        decomposition: Optional[QueryDecomposition],
    ) -> str:
        """
        Explain chunks retrieved directly from concept source_chunks.

        Args:
            chunks: List of retrieved chunks
            decomposition: Query decomposition with matched concepts

        Returns:
            Explanation string for direct retrievals

        Validates: Requirement 5.3 - indicate which concept provided the chunk
        """
        direct_chunks = [
            c for c in chunks
            if c.source == RetrievalSource.DIRECT_CONCEPT
        ]

        if not direct_chunks:
            return ""

        # Group by concept name
        concept_chunks: Dict[str, int] = {}
        for chunk in direct_chunks:
            concept_name = chunk.concept_name or "unknown concept"
            concept_chunks[concept_name] = concept_chunks.get(concept_name, 0) + 1

        # Build explanation
        explanations: List[str] = []
        for concept_name, count in concept_chunks.items():
            chunk_word = "chunk" if count == 1 else "chunks"
            explanations.append(f"'{concept_name}' directly referenced {count} {chunk_word}")

        if len(explanations) == 1:
            return f"The concept {explanations[0]}."
        elif len(explanations) == 2:
            return f"The concepts {explanations[0]} and {explanations[1]}."
        else:
            # Join with commas and 'and' for the last item
            all_but_last = ", ".join(explanations[:-1])
            return f"The concepts {all_but_last}, and {explanations[-1]}."

    def _explain_relationship_retrievals(
        self,
        chunks: List[RetrievedChunk],
    ) -> str:
        """
        Explain chunks retrieved via relationship traversal.

        Args:
            chunks: List of retrieved chunks

        Returns:
            Explanation string for relationship-based retrievals

        Validates: Requirement 5.2 - include concept names and relationship types
        """
        relationship_chunks = [
            c for c in chunks
            if c.source in (RetrievalSource.RELATED_CONCEPT, RetrievalSource.REASONING_PATH)
        ]

        if not relationship_chunks:
            return ""

        # Collect unique relationship paths
        unique_paths: List[str] = []
        seen_paths: set = set()

        for chunk in relationship_chunks:
            if chunk.relationship_path:
                path_str = " -> ".join(chunk.relationship_path)
                if path_str not in seen_paths:
                    seen_paths.add(path_str)
                    unique_paths.append(path_str)

        count = len(relationship_chunks)
        chunk_word = "chunk was" if count == 1 else "chunks were"

        if unique_paths:
            # Show up to 3 paths
            paths_to_show = unique_paths[:3]
            path_descriptions = [f"'{p}'" for p in paths_to_show]

            if len(unique_paths) > 3:
                remaining = len(unique_paths) - 3
                path_descriptions.append(f"{remaining} more path{'s' if remaining != 1 else ''}")

            paths_text = ", ".join(path_descriptions)
            return f"{count} {chunk_word} found through relationship traversal: {paths_text}."
        else:
            return f"{count} additional {chunk_word} found through related concepts in the knowledge graph."

    def _generate_fallback_explanation(
        self,
        result: KGRetrievalResult,
        decomposition: Optional[QueryDecomposition],
    ) -> str:
        """
        Generate explanation when fallback to semantic search was used.

        Args:
            result: The retrieval result
            decomposition: Query decomposition details

        Returns:
            Explanation indicating fallback was used

        Validates: Requirement 5.5 - indicate when KG retrieval was not applicable
        """
        parts: List[str] = []

        # Determine reason for fallback
        fallback_reason = result.metadata.get("fallback_reason", "")

        if fallback_reason == "no_concepts":
            parts.append(
                "Knowledge graph retrieval was not applicable for this query "
                "(no matching concepts found)."
            )
        elif fallback_reason == "no_kg_results":
            parts.append(
                "Knowledge graph retrieval found no relevant chunks. "
            )
        elif fallback_reason == "neo4j_error":
            parts.append(
                "Knowledge graph was temporarily unavailable. "
            )
        elif fallback_reason == "timeout":
            parts.append(
                "Knowledge graph query timed out. "
            )
        else:
            parts.append(
                "Knowledge graph retrieval was not applicable. "
            )

        # Add info about fallback results
        chunk_count = len(result.chunks)
        if chunk_count > 0:
            parts.append(
                f"Retrieved {chunk_count} chunk{'s' if chunk_count != 1 else ''} "
                "using semantic search instead."
            )
        else:
            parts.append("No results found via semantic search fallback.")

        return " ".join(parts)

    def _generate_empty_result_explanation(
        self,
        decomposition: Optional[QueryDecomposition],
    ) -> str:
        """
        Generate explanation when no chunks were found.

        Args:
            decomposition: Query decomposition details

        Returns:
            Explanation for empty results
        """
        if decomposition and decomposition.entities:
            entities_str = ", ".join(f"'{e}'" for e in decomposition.entities[:3])
            return (
                f"No relevant chunks found for the identified concepts ({entities_str}). "
                "The knowledge graph concepts may not have associated document chunks."
            )
        else:
            return (
                "No relevant chunks found. The query did not match any concepts "
                "in the knowledge graph."
            )

    def _explain_direct_retrieval(self, chunk: RetrievedChunk) -> str:
        """
        Explain a single directly retrieved chunk.

        Args:
            chunk: The chunk to explain

        Returns:
            Explanation string for this chunk

        Validates: Requirement 5.3
        """
        if not chunk:
            return ""

        concept_name = chunk.concept_name or "an unknown concept"
        score_info = ""

        if chunk.final_score > 0:
            score_info = f" (relevance: {chunk.final_score:.2f})"

        return f"Retrieved from concept '{concept_name}'{score_info}."

    def _explain_relationship_retrieval(self, chunk: RetrievedChunk) -> str:
        """
        Explain a single chunk retrieved via relationships.

        Args:
            chunk: The chunk to explain

        Returns:
            Explanation string for this chunk

        Validates: Requirement 5.2
        """
        if not chunk:
            return ""

        if chunk.relationship_path:
            path_str = " -> ".join(chunk.relationship_path)
            score_info = ""

            if chunk.final_score > 0:
                score_info = f" (relevance: {chunk.final_score:.2f})"

            return f"Found via relationship path: {path_str}{score_info}."
        else:
            concept_name = chunk.concept_name or "a related concept"
            return f"Found through related concept '{concept_name}'."

    def generate_chunk_explanation(self, chunk: RetrievedChunk) -> str:
        """
        Generate explanation for a single chunk.

        Useful for providing per-chunk explanations in detailed views.

        Args:
            chunk: The chunk to explain

        Returns:
            Explanation string for this specific chunk
        """
        if not chunk:
            return "No chunk information available."

        if chunk.source == RetrievalSource.DIRECT_CONCEPT:
            return self._explain_direct_retrieval(chunk)
        elif chunk.source in (RetrievalSource.RELATED_CONCEPT, RetrievalSource.REASONING_PATH):
            return self._explain_relationship_retrieval(chunk)
        elif chunk.source == RetrievalSource.SEMANTIC_FALLBACK:
            return "Retrieved via semantic search fallback."
        elif chunk.source == RetrievalSource.SEMANTIC_AUGMENT:
            return "Added via semantic search to supplement knowledge graph results."
        else:
            return "Retrieved from an unknown source."

    def generate_summary(self, result: KGRetrievalResult) -> Dict[str, Any]:
        """
        Generate a structured summary of the retrieval result.

        Useful for programmatic access to explanation components.

        Args:
            result: The retrieval result

        Returns:
            Dictionary with structured explanation data
        """
        if not result:
            return {"error": "No result available"}

        source_distribution = result.get_source_distribution()

        # Collect unique concepts
        concepts_used: List[str] = []
        for chunk in result.chunks:
            if chunk.concept_name and chunk.concept_name not in concepts_used:
                concepts_used.append(chunk.concept_name)

        # Collect unique relationship paths
        paths_used: List[List[str]] = []
        for chunk in result.chunks:
            if chunk.relationship_path and chunk.relationship_path not in paths_used:
                paths_used.append(chunk.relationship_path)

        return {
            "total_chunks": len(result.chunks),
            "fallback_used": result.fallback_used,
            "source_distribution": source_distribution,
            "concepts_used": concepts_used,
            "relationship_paths": paths_used,
            "retrieval_time_ms": result.retrieval_time_ms,
            "cache_hits": result.cache_hits,
            "explanation": self.generate(result),
        }
