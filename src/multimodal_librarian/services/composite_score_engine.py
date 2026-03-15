"""
Composite Score Engine for cross-document relationship scoring.

Computes per-edge scores from three signals (relationship type weight,
embedding cosine similarity, ConceptNet edge weight) and aggregates them
into document-pair scores stored as RELATED_DOCS edges in Neo4j.
"""

import logging
import math
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class EdgeScore:
    """Score for a single cross-document concept pair."""
    source_concept_id: str
    target_concept_id: str
    source_document_id: str
    target_document_id: str
    relationship_type: str
    type_weight: float
    embedding_similarity: float
    cn_weight: float
    edge_score: float  # Clamped to [0.0, 1.0]


@dataclass
class DocumentPairScore:
    """Aggregate score for a pair of documents."""
    doc_id_a: str
    doc_id_b: str
    score: float           # Clamped to [0.0, 1.0]
    edge_count: int
    avg_edge_score: float
    neighborhood_density: float
    computed_at: str        # ISO 8601


@dataclass
class CompositeScoreResult:
    """Result of composite score computation for a single ingested document."""
    document_id: str
    edges_discovered: int
    edges_scored: int
    document_pairs: int
    related_docs_created: int
    duration_ms: float
    pair_scores: List[DocumentPairScore] = field(default_factory=list)


class CompositeScoreEngine:
    """Computes composite cross-document relationship scores.

    Discovers cross-document concept pairs, scores them using a three-signal
    formula, aggregates into document-pair scores, and persists RELATED_DOCS
    edges in Neo4j.
    """

    # Relationship type weights (Requirement 2.2)
    TYPE_WEIGHTS: Dict[str, float] = {
        "SAME_AS": 1.0,
        "Synonym": 0.80,
        "SimilarTo": 0.70,
        "IsA": 0.65,
        "PartOf": 0.60,
        "UsedFor": 0.55,
        "CapableOf": 0.55,
        "Causes": 0.55,
        "HasProperty": 0.50,
        "AtLocation": 0.50,
        "HasPrerequisite": 0.50,
        "MotivatedByGoal": 0.45,
        "RelatedTo": 0.40,
    }

    # Default type weight for unknown relationship types
    DEFAULT_TYPE_WEIGHT: float = 0.3

    # Scoring formula weights (Requirement 2.1)
    W_TYPE: float = 0.4
    W_EMBEDDING: float = 0.45
    W_CN: float = 0.15

    # Aggregation weights (Requirement 3.1)
    W_AVG_EDGE: float = 0.7
    W_DENSITY: float = 0.3

    # Qualifying relationship types for edge discovery
    QUALIFYING_REL_TYPES = [
        "SAME_AS", "IsA", "PartOf", "RelatedTo", "UsedFor", "CapableOf",
        "HasProperty", "AtLocation", "Causes", "HasPrerequisite",
        "MotivatedByGoal", "Synonym", "SimilarTo",
    ]

    def __init__(self, kg_client: Any) -> None:
        """
        Args:
            kg_client: Neo4j graph client (from get_database_factory().get_graph_client())
        """
        self._kg = kg_client

    async def compute_composite_scores(self, document_id: str) -> CompositeScoreResult:
        """Main entry point. Discovers edges, scores them, aggregates, and persists RELATED_DOCS.

        All exceptions propagate (KG failure is fatal per Requirement 5.3).
        """
        start = time.time()

        # Step 1: Discover cross-document edges
        raw_edges = await self._discover_cross_doc_edges(document_id)

        if not raw_edges:
            duration = (time.time() - start) * 1000
            return CompositeScoreResult(
                document_id=document_id,
                edges_discovered=0,
                edges_scored=0,
                document_pairs=0,
                related_docs_created=0,
                duration_ms=duration,
            )

        # Step 2: Compute per-edge scores
        edge_scores = [self._compute_edge_score(e) for e in raw_edges]

        # Step 3: Get concept counts for all involved documents
        doc_ids = set()
        for es in edge_scores:
            doc_ids.add(es.source_document_id)
            doc_ids.add(es.target_document_id)
        concept_counts = await self._get_concept_counts(list(doc_ids))

        # Step 4: Aggregate into document-pair scores
        pair_scores = self._aggregate_document_pairs(edge_scores, concept_counts)

        # Step 5: Persist RELATED_DOCS edges
        created = await self._persist_related_docs(pair_scores, edge_scores)

        duration = (time.time() - start) * 1000
        return CompositeScoreResult(
            document_id=document_id,
            edges_discovered=len(raw_edges),
            edges_scored=len(edge_scores),
            document_pairs=len(pair_scores),
            related_docs_created=created,
            duration_ms=duration,
            pair_scores=pair_scores,
        )

    # Maximum edges to sample per target document for scoring.
    # Keeps the query result set bounded while still producing
    # representative composite scores.
    MAX_EDGES_PER_TARGET_DOC: int = 500

    async def _discover_cross_doc_edges(self, document_id: str) -> List[dict]:
        """Query Neo4j for cross-document concept pairs involving document_id.

        Gets all other document source_ids from Chunk nodes, then for each
        target document fetches a capped sample of concept-pair edges.
        This avoids the expensive full-graph traversal that times out on
        large documents.

        Conversation documents (source_type='CONVERSATION') are excluded
        from both source and target to avoid spurious RELATED_DOCS edges
        caused by generic concept overlap.
        """
        rel_types = self.QUALIFYING_REL_TYPES
        edge_cap = self.MAX_EDGES_PER_TARGET_DOC

        # Check if the source document is a conversation — skip entirely
        conversation_doc_ids: set = set()
        try:
            from ..database.connection import get_async_connection
            conn = await get_async_connection()
            try:
                row = await conn.fetchrow(
                    "SELECT source_type::text FROM multimodal_librarian.knowledge_sources "
                    "WHERE id::text = $1",
                    document_id,
                )
                if row and (row["source_type"] or "").upper() == "CONVERSATION":
                    logger.info(
                        f"Skipping composite scoring for conversation document {document_id}"
                    )
                    return []

                # Also get all conversation source_ids to exclude as targets
                conv_rows = await conn.fetch(
                    "SELECT id::text AS doc_id FROM multimodal_librarian.knowledge_sources "
                    "WHERE source_type::text = 'CONVERSATION'"
                )
                conversation_doc_ids = {r["doc_id"] for r in conv_rows}
            finally:
                await conn.close()
        except Exception as e:
            logger.warning(f"Failed to check conversation status: {e}")

        # Get all other document IDs from Chunk nodes (fast indexed query)
        other_docs_query = """
        MATCH (ch:Chunk)
        WHERE ch.source_id <> $doc_id
          AND ch.source_id <> 'conceptnet'
        RETURN DISTINCT ch.source_id AS doc_id
        """
        other_results = await self._kg.execute_query(
            other_docs_query, {"doc_id": document_id}
        )
        target_doc_ids = [
            r["doc_id"] for r in (other_results or [])
            if r["doc_id"] not in conversation_doc_ids
        ]

        if not target_doc_ids:
            logger.info(
                f"No other documents found for cross-doc "
                f"scoring of {document_id}"
            )
            return []

        # For each target doc, fetch capped edges with embeddings
        per_doc_query = """
        MATCH (ch1:Chunk {source_id: $doc_id})
              <-[:EXTRACTED_FROM]-(c1:Concept)
              -[r]-(c2:Concept)
              -[:EXTRACTED_FROM]->(ch2:Chunk {source_id: $tgt_doc})
        WHERE type(r) IN $rel_types
        WITH DISTINCT c1, c2,
             type(r) AS rel_type, r.weight AS cn_weight
        LIMIT $edge_cap
        RETURN c1.concept_id AS src_id,
               $doc_id AS src_doc,
               c1.embedding AS src_emb,
               c2.concept_id AS tgt_id,
               $tgt_doc AS tgt_doc,
               c2.embedding AS tgt_emb,
               rel_type,
               cn_weight
        """

        seen: set = set()
        edges: list = []
        for tgt_doc in target_doc_ids:
            try:
                params = {
                    "doc_id": document_id,
                    "tgt_doc": tgt_doc,
                    "rel_types": rel_types,
                    "edge_cap": edge_cap,
                }
                results = await self._kg.execute_query(
                    per_doc_query, params
                )
                for record in (results or []):
                    key = (
                        record["src_id"],
                        record["tgt_id"],
                        record["rel_type"],
                    )
                    if key not in seen:
                        seen.add(key)
                        edges.append(record)
            except Exception as e:
                logger.warning(
                    f"Failed to fetch edges for "
                    f"target doc {tgt_doc}: {e}"
                )

        logger.info(
            f"Discovered {len(edges)} cross-document edges "
            f"for document {document_id} "
            f"({len(target_doc_ids)} target docs)"
        )
        return edges

    @staticmethod
    def _cosine_similarity(vec_a: Optional[List[float]], vec_b: Optional[List[float]]) -> float:
        """Compute cosine similarity between two vectors.

        Returns 0.0 if either vector is None, empty, or zero-magnitude.
        """
        if not vec_a or not vec_b:
            return 0.0

        dot = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = math.sqrt(sum(a * a for a in vec_a))
        norm_b = math.sqrt(sum(b * b for b in vec_b))

        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0

        return dot / (norm_a * norm_b)

    def _compute_edge_score(self, edge: dict) -> EdgeScore:
        """Compute per-edge score using the three-signal formula.

        Formula: edge_score = clamp(type_weight * 0.4 + embedding_similarity * 0.45 + cn_weight * 0.15, 0.0, 1.0)
        """
        rel_type = edge["rel_type"]
        type_weight = self.TYPE_WEIGHTS.get(rel_type, self.DEFAULT_TYPE_WEIGHT)

        # Cosine similarity (default 0.0 if embeddings missing)
        embedding_similarity = self._cosine_similarity(
            edge.get("src_emb"), edge.get("tgt_emb")
        )

        # CN weight normalization
        raw_cn = edge.get("cn_weight")
        if rel_type == "SAME_AS":
            cn_weight = 1.0
        elif raw_cn is None:
            cn_weight = 0.0
        else:
            cn_weight = max(0.0, min(float(raw_cn), 1.0))

        raw_score = (
            type_weight * self.W_TYPE
            + embedding_similarity * self.W_EMBEDDING
            + cn_weight * self.W_CN
        )
        edge_score = max(0.0, min(raw_score, 1.0))

        return EdgeScore(
            source_concept_id=edge["src_id"],
            target_concept_id=edge["tgt_id"],
            source_document_id=edge["src_doc"],
            target_document_id=edge["tgt_doc"],
            relationship_type=rel_type,
            type_weight=type_weight,
            embedding_similarity=embedding_similarity,
            cn_weight=cn_weight,
            edge_score=edge_score,
        )

    async def _get_concept_counts(self, document_ids: List[str]) -> Dict[str, int]:
        """Get concept count per document for neighborhood density calculation."""
        if not document_ids:
            return {}

        query = """
        UNWIND $doc_ids AS did
        MATCH (ch:Chunk {source_id: did})<-[:EXTRACTED_FROM]-(c:Concept)
        RETURN did AS doc_id, count(DISTINCT c) AS concept_count
        """
        results = await self._kg.execute_query(query, {"doc_ids": document_ids})

        counts: Dict[str, int] = {}
        for rec in (results or []):
            counts[rec["doc_id"]] = rec["concept_count"]
        return counts

    def _aggregate_document_pairs(
        self,
        edge_scores: List[EdgeScore],
        concept_counts: Dict[str, int],
    ) -> List[DocumentPairScore]:
        """Group edge scores by document pair and compute aggregate scores.

        Formula: doc_score = clamp(avg_edge_score * 0.7 + neighborhood_density * 0.3, 0.0, 1.0)
        neighborhood_density = min(edge_count / min(concept_count_a, concept_count_b), 1.0)
        Uses 1 as denominator if concept count is 0.
        """
        # Group by sorted document pair to avoid (A,B) vs (B,A) duplicates
        pair_edges: Dict[Tuple[str, str], List[EdgeScore]] = defaultdict(list)
        for es in edge_scores:
            sorted_ids = sorted([es.source_document_id, es.target_document_id])
            pair_key: Tuple[str, str] = (sorted_ids[0], sorted_ids[1])
            pair_edges[pair_key].append(es)

        now = datetime.now(timezone.utc).isoformat()
        pair_scores: List[DocumentPairScore] = []

        for (doc_a, doc_b), edges in pair_edges.items():
            edge_count = len(edges)
            avg_edge_score = sum(e.edge_score for e in edges) / edge_count

            count_a = concept_counts.get(doc_a, 0)
            count_b = concept_counts.get(doc_b, 0)
            min_concepts = min(count_a, count_b)
            denominator = max(min_concepts, 1)  # avoid division by zero
            neighborhood_density = min(edge_count / denominator, 1.0)

            raw_score = avg_edge_score * self.W_AVG_EDGE + neighborhood_density * self.W_DENSITY
            doc_score = max(0.0, min(raw_score, 1.0))

            pair_scores.append(DocumentPairScore(
                doc_id_a=doc_a,
                doc_id_b=doc_b,
                score=doc_score,
                edge_count=edge_count,
                avg_edge_score=avg_edge_score,
                neighborhood_density=neighborhood_density,
                computed_at=now,
            ))

        return pair_scores

    async def _persist_related_docs(
        self,
        pair_scores: List[DocumentPairScore],
        edge_scores: List[EdgeScore],
    ) -> int:
        """Upsert RELATED_DOCS edges bidirectionally in Neo4j.

        Selects a representative concept per document (highest individual edge score)
        and runs the upsert twice (once per direction).
        """
        if not pair_scores:
            return 0

        # Build representative concept map: for each (doc_pair), pick the concept
        # with the highest edge score per document
        pair_edges: Dict[Tuple[str, str], List[EdgeScore]] = defaultdict(list)
        for es in edge_scores:
            sorted_ids = sorted([es.source_document_id, es.target_document_id])
            pair_key: Tuple[str, str] = (sorted_ids[0], sorted_ids[1])
            pair_edges[pair_key].append(es)

        # For each pair, find best concept per document.
        # Ensure the two representative concepts are different
        # to avoid self-loop RELATED_DOCS edges on shared concepts.
        rows_forward = []
        rows_reverse = []
        for ps in pair_scores:
            sorted_ids = sorted([ps.doc_id_a, ps.doc_id_b])
            pair_key = (sorted_ids[0], sorted_ids[1])
            edges = pair_edges.get(pair_key, [])
            if not edges:
                continue

            # Best concept for doc_a
            best_a = self._best_concept_for_doc(
                edges, ps.doc_id_a
            )
            # Best concept for doc_b, excluding best_a
            best_b = self._best_concept_for_doc(
                edges, ps.doc_id_b, exclude={best_a}
            )

            # If best_b is None (all concepts shared),
            # try the other direction
            if not best_b:
                best_b = self._best_concept_for_doc(
                    edges, ps.doc_id_b
                )
                best_a = self._best_concept_for_doc(
                    edges, ps.doc_id_a, exclude={best_b}
                )

            if not best_a or not best_b or best_a == best_b:
                logger.debug(
                    f"Skipping pair {ps.doc_id_a}-{ps.doc_id_b}: "
                    f"no distinct representative concepts"
                )
                continue

            row = {
                "src_concept_id": best_a,
                "tgt_concept_id": best_b,
                "score": ps.score,
                "edge_count": ps.edge_count,
                "avg_edge_score": ps.avg_edge_score,
                "neighborhood_density": ps.neighborhood_density,
                "computed_at": ps.computed_at,
            }
            rows_forward.append(row)
            rows_reverse.append({
                "src_concept_id": best_b,
                "tgt_concept_id": best_a,
                "score": ps.score,
                "edge_count": ps.edge_count,
                "avg_edge_score": ps.avg_edge_score,
                "neighborhood_density": ps.neighborhood_density,
                "computed_at": ps.computed_at,
            })

        upsert_query = """
        UNWIND $rows AS row
        MATCH (c1:Concept {concept_id: row.src_concept_id})
        MATCH (c2:Concept {concept_id: row.tgt_concept_id})
        MERGE (c1)-[r:RELATED_DOCS]->(c2)
        SET r.score = row.score,
            r.edge_count = row.edge_count,
            r.avg_edge_score = row.avg_edge_score,
            r.neighborhood_density = row.neighborhood_density,
            r.computed_at = row.computed_at
        RETURN count(r) AS cnt
        """

        total = 0
        for rows in [rows_forward, rows_reverse]:
            if not rows:
                continue
            result = await self._kg.execute_query(upsert_query, {"rows": rows})
            if result:
                total += result[0].get("cnt", 0)

        logger.info(f"Persisted {total} RELATED_DOCS edges ({len(pair_scores)} pairs, bidirectional)")
        return total

    @staticmethod
    def _best_concept_for_doc(
        edges: List[EdgeScore],
        doc_id: str,
        exclude: Optional[set] = None,
    ) -> Optional[str]:
        """Find the concept with the highest edge score for a given document.

        Args:
            edges: List of scored edges to search.
            doc_id: Document ID to find the best concept for.
            exclude: Optional set of concept_ids to skip.
        """
        best_score = -1.0
        best_concept = None
        skip = exclude or set()
        for e in edges:
            if (e.source_document_id == doc_id
                    and e.source_concept_id not in skip
                    and e.edge_score > best_score):
                best_score = e.edge_score
                best_concept = e.source_concept_id
            if (e.target_document_id == doc_id
                    and e.target_concept_id not in skip
                    and e.edge_score > best_score):
                best_score = e.edge_score
                best_concept = e.target_concept_id
        return best_concept
