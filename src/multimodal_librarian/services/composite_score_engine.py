"""
Composite Score Engine for cross-document relationship scoring.

Computes per-edge scores from three signals (relationship type weight,
embedding cosine similarity, ConceptNet edge weight) and aggregates them
into document-pair scores stored as RELATED_DOCS edges in Neo4j.
"""

import logging
import math
import re
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
    }

    # Default type weight for unknown relationship types
    DEFAULT_TYPE_WEIGHT: float = 0.3

    # Scoring formula weights (Requirement 2.1)
    W_TYPE: float = 0.4
    W_EMBEDDING: float = 0.45
    W_CN: float = 0.15

    # Minimum per-edge score to include in aggregation.
    # Edges below this threshold are noise (e.g. RelatedTo with
    # no embedding similarity) and are discarded before
    # document-pair scoring.
    MIN_EDGE_SCORE: float = 0.35

    # Minimum embedding similarity for an edge to qualify.
    # Concept pairs with near-zero cosine similarity are
    # coincidental matches via ConceptNet, not genuine
    # semantic relationships.
    MIN_EMBEDDING_SIMILARITY: float = 0.4

    # Aggregation weights (Requirement 3.1)
    # Edge quality dominates; density is a minor signal to avoid
    # inflated scores from many low-quality generic-concept edges.
    W_AVG_EDGE: float = 0.85
    W_DENSITY: float = 0.15

    # Minimum number of qualifying edges for a document pair
    # to be considered related at all.
    MIN_EDGES_FOR_PAIR: int = 5

    # Qualifying relationship types for edge discovery.
    # Only SAME_AS (YAGO-bridged exact entity matches) is used.
    # All ConceptNet types (RelatedTo, SimilarTo, Synonym, IsA,
    # PartOf, UsedFor, etc.) are too noisy for single-word
    # concepts — e.g. "research" UsedFor "book", "only" IsA
    # "single", "clinical" SimilarTo "Objective".
    QUALIFYING_REL_TYPES = [
        "SAME_AS",
    ]

    # Minimum token count for concept names in cross-doc edges.
    # Single-word SAME_AS matches often have bad YAGO
    # disambiguation (e.g. "Ali" → "Ali the rapper",
    # "Appendix" → "Appendix the band").  Multi-token names
    # like "machine learning", "neural network" are reliable.
    MIN_CONCEPT_TOKENS: int = 2

    # Concept types considered generic (not proper nouns).
    # Edges where BOTH concepts are generic are filtered out to
    # avoid noise from broad ConceptNet relationships like
    # "large" → "Big" or "down" → "Deep".
    #
    # Approach: whitelist types that are genuinely domain-specific.
    # spaCy NER often misclassifies common words (e.g. "Deep" as
    # NORP, "START" as PRODUCT), so we can't trust NER tags alone.
    # Only UMLS semantic types and select NER types with multi-token
    # names are considered proper nouns.
    DOMAIN_CONCEPT_TYPES: frozenset = frozenset({
        # UMLS semantic types (always domain-specific)
        "Disease or Syndrome",
        "Bacterium",
        "Virus",
        "Eukaryote",
        "Organic Chemical",
        "ORGANISM",
        "TREATMENT",
        # NER types that are reliable when multi-token
        "ORG",
        "PERSON",
        "GPE",
        "LOC",
        "FAC",
        "LAW",
        "WORK_OF_ART",
        "EVENT",
        "LANGUAGE",
        # Topic-level concepts from extraction
        "TOPIC",
    })

    # Known generic filler phrases that are never domain-specific.
    GARBAGE_PHRASES: frozenset = frozenset({
        "less than", "more than", "more than two",
        "information about", "such as", "as well",
        "due to", "based on", "according to",
        "in order", "at least", "up to",
        "each of", "one of",
    })

    # Pre-compiled regex patterns for garbage concept names.
    _GARBAGE_PATTERNS = [
        # PDF artifact characters
        re.compile(r'[?+=]'),
        # Hyphenation breaks
        re.compile(r'\w+- \w+'),
        # Table/figure references
        re.compile(
            r'^(table|figure|fig)\s+\d', re.IGNORECASE,
        ),
        # Time expressions
        re.compile(
            r'^\d+\s+(years?|days?|months?'
            r'|weeks?|hours?|minutes?)$',
            re.IGNORECASE,
        ),
        # Stage/phase labels
        re.compile(
            r'^(stage|phase|step|grade|level|type)\s+\d',
            re.IGNORECASE,
        ),
        # Citations
        re.compile(r'\bet\s+al\.?$', re.IGNORECASE),
    ]

    @staticmethod
    def _is_garbage_concept_name(name: str) -> bool:
        """Return True if *name* matches any garbage concept pattern.

        Checks exact-match against ``GARBAGE_PHRASES`` (case-insensitive)
        and regex-match against ``_GARBAGE_PATTERNS``.
        """
        if not name:
            return False
        lower = name.strip().lower()
        if lower in CompositeScoreEngine.GARBAGE_PHRASES:
            return True
        for pat in CompositeScoreEngine._GARBAGE_PATTERNS:
            if pat.search(name):
                return True
        return False

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
    MAX_EDGES_PER_TARGET_DOC: int = 200

    async def _discover_cross_doc_edges(
        self, document_id: str
    ) -> List[dict]:
        """Discover cross-document edges via shared concept name overlap.

        Uses a single bulk Cypher query to find concepts that share the
        same normalised name (lower-case) across documents.  Only
        multi-token concept names are considered (MIN_CONCEPT_TOKENS)
        to filter out generic single-word matches like "data", "model".

        Conversation documents are excluded from both source and target.
        Per-target-doc results are capped at MAX_EDGES_PER_TARGET_DOC.
        """
        edge_cap = self.MAX_EDGES_PER_TARGET_DOC

        # --- Exclude conversation documents ---
        conversation_doc_ids: set = set()
        try:
            from ..database.connection import get_async_connection
            conn = await get_async_connection()
            try:
                row = await conn.fetchrow(
                    "SELECT source_type::text "
                    "FROM multimodal_librarian.knowledge_sources "
                    "WHERE id::text = $1",
                    document_id,
                )
                if row and (
                    row["source_type"] or ""
                ).upper() == "CONVERSATION":
                    logger.info(
                        "Skipping composite scoring for "
                        f"conversation document {document_id}"
                    )
                    return []

                conv_rows = await conn.fetch(
                    "SELECT id::text AS doc_id "
                    "FROM multimodal_librarian.knowledge_sources "
                    "WHERE source_type::text = 'CONVERSATION'"
                )
                conversation_doc_ids = {
                    r["doc_id"] for r in conv_rows
                }
            finally:
                await conn.close()
        except Exception as e:
            logger.warning(
                f"Failed to check conversation status: {e}"
            )

        # --- Bulk concept-name overlap query ---
        # Finds concepts in the source document that share the
        # same normalised name with concepts in other documents.
        # Only multi-token names are matched (the WHERE clause
        # requires a space in the name).  Results are grouped
        # by target document and capped.
        t_start = time.time()
        overlap_query = """
        MATCH (ch1:Chunk {source_id: $doc_id})
              <-[:EXTRACTED_FROM]-(c1:Concept)
        WHERE c1.name CONTAINS ' '
        WITH c1, c1.name_lower AS norm_name
        MATCH (c2:Concept {name_lower: norm_name})
        WHERE c2.concept_id <> c1.concept_id
        WITH c1, c2
        MATCH (c2)-[:EXTRACTED_FROM]->(ch2:Chunk)
        WHERE ch2.source_id <> $doc_id
          AND ch2.source_id <> 'conceptnet'
        WITH DISTINCT
             c1.concept_id AS src_id,
             c2.concept_id AS tgt_id,
             c1.name AS src_name,
             c2.name AS tgt_name,
             c1.concept_type AS src_type,
             c2.concept_type AS tgt_type,
             ch2.source_id AS tgt_doc
        RETURN src_id, tgt_id, src_name, tgt_name,
               src_type, tgt_type,
               tgt_doc,
               $doc_id AS src_doc,
               'SAME_AS' AS rel_type
        LIMIT $total_cap
        """

        total_cap = edge_cap * 40  # generous cap for bulk
        try:
            results = await self._kg.execute_query(
                overlap_query,
                {
                    "doc_id": document_id,
                    "total_cap": total_cap,
                },
            )
        except Exception as e:
            logger.warning(
                f"Concept overlap query failed for "
                f"{document_id}: {e}"
            )
            return []

        elapsed_phase1 = time.time() - t_start

        # --- Deduplicate and cap per target doc ---
        seen: set = set()
        per_doc_count: Dict[str, int] = {}
        candidates: list = []

        for record in (results or []):
            tgt_doc = record["tgt_doc"]

            # Skip conversation documents
            if tgt_doc in conversation_doc_ids:
                continue

            # --- Garbage concept filtering ---
            src_name = record.get("src_name", "")
            tgt_name = record.get("tgt_name", "")

            # Layer 1: garbage name patterns
            if (self._is_garbage_concept_name(src_name)
                    or self._is_garbage_concept_name(
                        tgt_name)):
                continue

            # Layer 2: concept_type gate — require at
            # least one concept with a domain-specific type
            src_type = record.get("src_type")
            tgt_type = record.get("tgt_type")
            src_is_domain = (
                src_type in self.DOMAIN_CONCEPT_TYPES
            )
            tgt_is_domain = (
                tgt_type in self.DOMAIN_CONCEPT_TYPES
            )
            if not src_is_domain and not tgt_is_domain:
                continue

            # Per-target-doc cap
            doc_cnt = per_doc_count.get(tgt_doc, 0)
            if doc_cnt >= edge_cap:
                continue

            key = (record["src_id"], record["tgt_id"])
            if key in seen:
                continue
            seen.add(key)

            per_doc_count[tgt_doc] = doc_cnt + 1
            candidates.append({
                "src_id": record["src_id"],
                "src_doc": record.get(
                    "src_doc", document_id
                ),
                "tgt_id": record["tgt_id"],
                "tgt_doc": tgt_doc,
                "rel_type": "SAME_AS",
                "cn_weight": None,
                "embedding_similarity": 0.0,
            })

        if not candidates:
            logger.info(
                f"No concept overlap found for "
                f"{document_id} ({elapsed_phase1:.2f}s)"
            )
            return candidates

        # --- Phase 2: cosine similarity for candidates ---
        phase2_query = """
        UNWIND $pairs AS pair
        MATCH (c1:Concept {concept_id: pair.src_id})
        MATCH (c2:Concept {concept_id: pair.tgt_id})
        RETURN pair.src_id AS src_id,
               pair.tgt_id AS tgt_id,
               CASE
                 WHEN c1.embedding IS NOT NULL
                      AND c2.embedding IS NOT NULL
                      AND size(c1.embedding) > 0
                      AND size(c2.embedding) > 0
                 THEN gds.similarity.cosine(
                          c1.embedding, c2.embedding)
                 ELSE 0.0
               END AS embedding_similarity
        """

        for batch_start in range(
            0, len(candidates), edge_cap
        ):
            batch = candidates[
                batch_start:batch_start + edge_cap
            ]
            pairs = [
                {
                    "src_id": c["src_id"],
                    "tgt_id": c["tgt_id"],
                }
                for c in batch
            ]
            try:
                phase2_results = (
                    await self._kg.execute_query(
                        phase2_query, {"pairs": pairs}
                    )
                )
                sim_lookup: Dict[
                    Tuple[str, str], float
                ] = {}
                for rec in (phase2_results or []):
                    sim_lookup[
                        (rec["src_id"], rec["tgt_id"])
                    ] = float(
                        rec.get(
                            "embedding_similarity", 0.0
                        )
                    )
                for c in batch:
                    pk = (c["src_id"], c["tgt_id"])
                    if pk in sim_lookup:
                        c["embedding_similarity"] = (
                            sim_lookup[pk]
                        )
            except Exception as e2:
                logger.warning(
                    f"Phase 2 cosine batch failed: {e2}"
                )

        elapsed_total = time.time() - t_start
        target_count = len(per_doc_count)
        logger.info(
            f"Discovered {len(candidates)} cross-document "
            f"edges for document {document_id} "
            f"({target_count} target docs, "
            f"{elapsed_total:.2f}s)"
        )
        return candidates

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

    # NER types that require multi-token names to be trusted.
    # Single-word NER tags are often spaCy misclassifications
    # (e.g. "Deep" as NORP, "START" as PRODUCT).
    _NER_TYPES_NEED_MULTI_TOKEN: frozenset = frozenset({
        "GPE", "LOC", "FAC",
        "LAW", "WORK_OF_ART", "EVENT", "NORP",
        "PRODUCT", "LANGUAGE", "TOPIC",
    })

    # NER types trusted even for single-token names.
    # ORG and PERSON are rarely misclassified by spaCy
    # and are strong signals for cross-doc relatedness
    # (e.g. "Google", "OpenAI", "Python").
    _NER_TYPES_ALWAYS_TRUSTED: frozenset = frozenset({
        "ORG", "PERSON",
    })

    # UMLS semantic types are always domain-specific regardless
    # of token count (e.g. single-word disease names are valid).
    _UMLS_TYPES: frozenset = frozenset({
        "Disease or Syndrome", "Bacterium", "Virus",
        "Eukaryote", "Organic Chemical", "ORGANISM",
        "TREATMENT",
    })

    @classmethod
    def _is_domain_concept(
        cls, concept_type: str, concept_name: str
    ) -> bool:
        """Check if a concept is domain-specific enough for
        cross-document edge discovery.

        UMLS types are always accepted.  ORG/PERSON NER types
        are accepted even for single tokens.  Other NER types
        and multi-word CODE_TERMs are accepted only if the
        concept name has multiple tokens (to filter out
        single-word noise like "print", "Big", "Deep").
        """
        if concept_type in cls._UMLS_TYPES:
            return True
        if concept_type in cls._NER_TYPES_ALWAYS_TRUSTED:
            return True
        # Multi-token names are accepted for any type —
        # compound terms like "neural networks", "machine
        # learning", "the United States" are domain-specific
        # regardless of their NER/CODE_TERM classification.
        if " " in (concept_name or "").strip():
            return True
        return False

    def _compute_edge_score(self, edge: dict) -> EdgeScore:
        """Compute per-edge score using the three-signal formula.

        Formula: edge_score = clamp(type_weight * 0.4 + embedding_similarity * 0.45 + cn_weight * 0.15, 0.0, 1.0)

        Embedding similarity is pre-computed in the Cypher query
        (via gds.similarity.cosine) to avoid transferring large
        embedding vectors over the wire.
        """
        rel_type = edge["rel_type"]
        type_weight = self.TYPE_WEIGHTS.get(rel_type, self.DEFAULT_TYPE_WEIGHT)

        # Cosine similarity pre-computed in Cypher query
        embedding_similarity = float(
            edge.get("embedding_similarity", 0.0) or 0.0
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

        Formula: doc_score = clamp(avg_edge_score * 0.85 + neighborhood_density * 0.15, 0.0, 1.0)
        neighborhood_density = min(edge_count / sqrt(concept_count_a * concept_count_b), 1.0)

        Edges are filtered before aggregation:
        - edge_score must be >= MIN_EDGE_SCORE
        - embedding_similarity must be >= MIN_EMBEDDING_SIMILARITY
        Pairs with fewer than MIN_EDGES_FOR_PAIR qualifying edges are dropped.
        """
        # Filter edges: discard low-quality / low-similarity edges
        qualified = [
            es for es in edge_scores
            if es.edge_score >= self.MIN_EDGE_SCORE
            and es.embedding_similarity >= self.MIN_EMBEDDING_SIMILARITY
        ]

        # Group by sorted document pair to avoid (A,B) vs (B,A) duplicates
        pair_edges: Dict[Tuple[str, str], List[EdgeScore]] = defaultdict(list)
        for es in qualified:
            sorted_ids = sorted([es.source_document_id, es.target_document_id])
            pair_key: Tuple[str, str] = (sorted_ids[0], sorted_ids[1])
            pair_edges[pair_key].append(es)

        now = datetime.now(timezone.utc).isoformat()
        pair_scores: List[DocumentPairScore] = []

        for (doc_a, doc_b), edges in pair_edges.items():
            edge_count = len(edges)

            # Require minimum number of qualifying edges
            if edge_count < self.MIN_EDGES_FOR_PAIR:
                continue

            avg_edge_score = sum(e.edge_score for e in edges) / edge_count

            count_a = concept_counts.get(doc_a, 0)
            count_b = concept_counts.get(doc_b, 0)
            # Geometric mean: sqrt(a * b) — fairer than min() when
            # document sizes differ significantly
            geo_mean = math.sqrt(max(count_a, 1) * max(count_b, 1))
            neighborhood_density = min(edge_count / geo_mean, 1.0)

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
                "src_doc_id": ps.doc_id_a,
                "tgt_doc_id": ps.doc_id_b,
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
                "src_doc_id": ps.doc_id_b,
                "tgt_doc_id": ps.doc_id_a,
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
            r.computed_at = row.computed_at,
            r.source_doc_id = row.src_doc_id,
            r.target_doc_id = row.tgt_doc_id
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
