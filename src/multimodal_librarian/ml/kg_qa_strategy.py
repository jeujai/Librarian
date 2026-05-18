"""
KG-Driven Q&A Pair Generation Strategy.

Generates medical Q&A instruction-tuning pairs from the knowledge graph's
Concept→EXTRACTED_FROM→Chunk relationships. For each concept with UMLS
metadata (CUI, semantic type, synonyms), the strategy retrieves linked
chunk content and produces a question/answer pair grounded in the
Librarian's curated medical knowledge.

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from .models import InstructionTuningPair, PairMetadata
from .rag_qa_strategy import DEFAULT_QUESTION_TEMPLATES, TEMPLATES_BY_SEMANTIC_TYPE

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cypher query for concept selection
# ---------------------------------------------------------------------------

_CONCEPT_QUERY = """\
MATCH (c:Concept)-[:SAME_AS]->(u:UMLSConcept)-[:HAS_SEMANTIC_TYPE]->(st:UMLSSemanticType)
MATCH (c)-[e:EXTRACTED_FROM]->(ch:Chunk)
WHERE size(c.name) > 3
WITH c, u, st,
     collect(DISTINCT ch.chunk_id) AS chunk_ids,
     count(DISTINCT e) AS edge_count
WHERE edge_count >= 2
  AND edge_count <= 5000
RETURN c.name AS name,
       u.cui AS cui,
       st.type_name AS semantic_type,
       u.synonyms AS synonyms,
       chunk_ids
ORDER BY rand()
LIMIT $limit
"""


def _count_tokens(text: str) -> int:
    """Approximate token count by splitting on whitespace."""
    return len(text.split())


def _generate_question(
    concept_name: str,
    semantic_type: str,
    synonyms: Optional[List[str]] = None,
    template_index: int = 0,
) -> str:
    """Generate a clinically relevant question for a concept.

    The question always contains the concept name (case-preserved) so that
    Property 2 (concept name appears in question) is satisfied.

    Args:
        concept_name: The concept's display name.
        semantic_type: UMLS semantic type string.
        synonyms: Optional list of synonyms for the concept.
        template_index: Which template to pick from the list (cycled).

    Returns:
        A question string containing the concept name.
    """
    templates = TEMPLATES_BY_SEMANTIC_TYPE.get(
        semantic_type, DEFAULT_QUESTION_TEMPLATES
    )
    template = templates[template_index % len(templates)]
    return template.format(concept_name=concept_name)


def _generate_answer(
    concept_name: str,
    semantic_type: str,
    chunk_content: str,
    source_document: str,
    chunk_id: str,
    synonyms: Optional[List[str]] = None,
) -> str:
    """Generate an answer from chunk content with source attribution.

    The answer always includes the source document title and chunk ID
    so that Property 3 (source attribution preserved) is satisfied.

    Args:
        concept_name: The concept's display name.
        semantic_type: UMLS semantic type string.
        chunk_content: The text content of the linked chunk.
        source_document: Title of the source document.
        chunk_id: Unique identifier of the chunk.
        synonyms: Optional list of synonyms.

    Returns:
        An answer string with source attribution.
    """
    synonym_note = ""
    if synonyms:
        # Filter out empty strings and the concept name itself
        unique_synonyms = [
            s for s in synonyms
            if s and s.lower() != concept_name.lower()
        ]
        if unique_synonyms:
            synonym_note = (
                f" {concept_name} is also known as "
                f"{', '.join(unique_synonyms[:3])}."
            )

    answer = (
        f"{chunk_content.strip()}"
        f"{synonym_note}"
        f"\n\n[Source: {source_document}, Chunk ID: {chunk_id}]"
    )
    return answer


# ---------------------------------------------------------------------------
# KGQAStrategy
# ---------------------------------------------------------------------------


class KGQAStrategy:
    """Generate Q&A pairs from knowledge graph concept-chunk links.

    This strategy queries Neo4j for Concept nodes that have
    ``EXTRACTED_FROM`` edges to Chunk nodes and possess UMLS metadata
    (CUI, semantic type, synonyms). For each concept it retrieves the
    linked chunk content from the vector store, generates a clinically
    relevant question from the concept metadata, and extracts an answer
    from the chunk content preserving source attribution.

    Chunks with fewer than ``min_chunk_tokens`` tokens are skipped.
    """

    def __init__(
        self,
        neo4j_client: Any,
        vector_client: Any,
    ) -> None:
        """Initialise the strategy.

        Args:
            neo4j_client: A Neo4j client with an async ``execute_query``
                method (e.g. ``Neo4jClient``).
            vector_client: A vector-store client with an async
                ``get_chunk_by_id`` method (e.g. ``MilvusClient``).
        """
        self._neo4j = neo4j_client
        self._vector = vector_client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate(
        self,
        target_count: int,
        min_chunk_tokens: int = 50,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> List[InstructionTuningPair]:
        """Generate KG-driven Q&A instruction-tuning pairs.

        Args:
            target_count: Desired number of pairs to produce. The
                strategy fetches more concepts than needed to account
                for filtering.
            min_chunk_tokens: Minimum token count for a chunk to be
                considered. Chunks below this threshold are skipped
                (Requirement 1.5).
            progress_callback: Optional ``(generated, target)`` callback
                invoked after each pair is produced.

        Returns:
            A list of ``InstructionTuningPair`` objects with
            ``metadata.strategy == "kg"``.
        """
        # Fetch more concepts than target to account for filtering
        fetch_limit = target_count * 3

        concepts = await self._fetch_concepts(fetch_limit)
        if not concepts:
            logger.warning("KG Q&A: No concepts returned from Neo4j")
            return []

        logger.info(
            "KG Q&A: Retrieved %d concepts, targeting %d pairs",
            len(concepts),
            target_count,
        )

        pairs: List[InstructionTuningPair] = []
        template_counter = 0

        for concept in concepts:
            if len(pairs) >= target_count:
                break

            concept_name: str = concept.get("name", "")
            cui: str = concept.get("cui", "")
            semantic_type: str = concept.get("semantic_type", "")
            synonyms_raw = concept.get("synonyms")
            chunk_ids: List[str] = concept.get("chunk_ids", [])

            # Parse synonyms — may be a list or a comma-separated string
            synonyms = self._parse_synonyms(synonyms_raw)

            if not concept_name or not semantic_type:
                continue

            for chunk_id in chunk_ids:
                if len(pairs) >= target_count:
                    break

                chunk_data = await self._fetch_chunk(chunk_id)
                if chunk_data is None:
                    continue

                content = self._extract_content(chunk_data)
                if _count_tokens(content) < min_chunk_tokens:
                    logger.debug(
                        "KG Q&A: Skipping chunk %s for concept '%s' — "
                        "only %d tokens (min %d)",
                        chunk_id,
                        concept_name,
                        _count_tokens(content),
                        min_chunk_tokens,
                    )
                    continue

                source_document = self._extract_document_title(chunk_data)

                question = _generate_question(
                    concept_name=concept_name,
                    semantic_type=semantic_type,
                    synonyms=synonyms,
                    template_index=template_counter,
                )
                template_counter += 1

                answer = _generate_answer(
                    concept_name=concept_name,
                    semantic_type=semantic_type,
                    chunk_content=content,
                    source_document=source_document,
                    chunk_id=chunk_id,
                    synonyms=synonyms,
                )

                pair = InstructionTuningPair(
                    instruction=question,
                    context=content,
                    response=answer,
                    metadata=PairMetadata(
                        strategy="kg",
                        source_concepts=[cui] if cui else [concept_name],
                        confidence_score=self._compute_confidence(
                            content, min_chunk_tokens
                        ),
                        source_document=source_document,
                        chunk_ids=[chunk_id],
                    ),
                )
                pairs.append(pair)

                if progress_callback is not None:
                    progress_callback(len(pairs), target_count)

        logger.info("KG Q&A: Generated %d pairs", len(pairs))
        return pairs

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _fetch_concepts(
        self, limit: int
    ) -> List[Dict[str, Any]]:
        """Query Neo4j for concepts with EXTRACTED_FROM edges.

        Handles Neo4j connection failures gracefully by logging
        and returning an empty list (Requirement 1.1).
        """
        try:
            results = await self._neo4j.execute_query(
                _CONCEPT_QUERY, {"limit": limit}
            )
            return results if results else []
        except Exception as exc:
            logger.error(
                "KG Q&A: Neo4j query failed — skipping KG strategy: %s",
                exc,
            )
            return []

    async def _fetch_chunk(
        self, chunk_id: str
    ) -> Optional[Dict[str, Any]]:
        """Retrieve a single chunk from the vector store.

        Handles Milvus/OpenSearch connection failures gracefully by
        logging and returning ``None`` so the affected pair is skipped.
        """
        try:
            result: Optional[Dict[str, Any]] = (
                await self._vector.get_chunk_by_id(chunk_id)
            )
            return result
        except Exception as exc:
            logger.warning(
                "KG Q&A: Failed to retrieve chunk %s — skipping: %s",
                chunk_id,
                exc,
            )
            return None

    @staticmethod
    def _extract_content(chunk_data: Dict[str, Any]) -> str:
        """Extract text content from a chunk data dict.

        Supports both OpenSearch format (top-level ``content``) and
        Milvus format (``metadata.content``).
        """
        content = chunk_data.get("content", "")
        if not content:
            metadata = chunk_data.get("metadata", {})
            if isinstance(metadata, dict):
                content = metadata.get("content", "")
        return content or ""

    @staticmethod
    def _extract_document_title(chunk_data: Dict[str, Any]) -> str:
        """Extract the source document title from a chunk data dict.

        Supports both OpenSearch format (top-level ``document_title``)
        and Milvus format (``metadata.title``).
        """
        title: str = chunk_data.get("document_title", "") or ""
        if not title:
            metadata = chunk_data.get("metadata", {})
            if isinstance(metadata, dict):
                title = metadata.get("title", "") or ""
        if not title:
            title = chunk_data.get("section", "") or ""
        if not title:
            title = (
                chunk_data.get("source_id", "Unknown Source")
                or "Unknown Source"
            )
        return title

    @staticmethod
    def _parse_synonyms(raw: Any) -> List[str]:
        """Normalise synonyms from Neo4j into a list of strings.

        Neo4j may return synonyms as a list, a comma-separated string,
        or ``None``.
        """
        if raw is None:
            return []
        if isinstance(raw, list):
            return [str(s) for s in raw if s]
        if isinstance(raw, str):
            return [s.strip() for s in raw.split(",") if s.strip()]
        return []

    @staticmethod
    def _compute_confidence(content: str, min_tokens: int) -> float:
        """Compute a confidence score for a KG-generated pair.

        Longer chunks relative to the minimum threshold yield higher
        confidence. The score is clamped to [0.0, 1.0].
        """
        token_count = _count_tokens(content)
        if token_count <= 0:
            return 0.0
        # Scale: chunks at min_tokens → 0.5, chunks at 5× min → 1.0
        ratio = token_count / max(min_tokens, 1)
        score = min(0.5 + (ratio - 1.0) * 0.125, 1.0)
        return max(round(score, 4), 0.0)
