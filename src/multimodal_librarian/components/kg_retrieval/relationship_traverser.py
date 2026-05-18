"""
Relationship Traverser Component for Knowledge Graph-Guided Retrieval.

This component executes bounded Cypher queries that traverse inter-concept
relationships (CAUSES, PRESENTS_WITH, TREATED_BY, etc.) to find chunks at
the intersection of connected query concepts. It is used by the
KGRetrievalService to boost chunks that sit at the intersection of
clinically connected concepts in multi-concept queries.

The traverser is purely read-only — it never creates, modifies, or deletes
any nodes or edges in the Neo4j knowledge graph.

Requirements: 2.5, 9.1, 9.2
"""

import asyncio
import logging
import time
from itertools import combinations
from typing import Any, Dict, List, Optional, Set, Tuple

from ...models.kg_retrieval import TraversalResult

logger = logging.getLogger(__name__)


class RelationshipTraverser:
    """Traverses inter-concept relationships to find intersection chunks.

    Given a set of matched query concepts, this component generates all
    C(n,2) concept pairs, executes bounded Cypher queries for each pair
    to find relationship paths, and collects chunk IDs from concepts
    along those paths via EXTRACTED_FROM edges.

    The result is a TraversalResult mapping chunk IDs to the set of
    query concepts that reach them, enabling the KGRetrievalService
    to identify and boost intersection chunks.

    Follows FastAPI DI patterns — no connections at construction time.

    Requirements: 2.5, 9.1, 9.2
    """

    CLINICALLY_RELEVANT_RELATIONSHIPS: List[str] = [
        "CAUSES",
        "PRESENTS_WITH",
        "TREATED_BY",
        "TREATS",
        "IS_A",
        "PART_OF",
        "RELATED_TO",
        "SIMILAR_TO",
        "IsA",
        "PartOf",
        "RelatedTo",
        "Causes",
        "SimilarTo",
        "HasProperty",
        "UsedFor",
        "HasA",
        "HasPrerequisite",
        "Entails",
        "MadeOf",
    ]

    # UMLS_REL rela_type values that carry clinically meaningful semantics.
    # Excludes: empty string, qualifier metadata (QB edges), drug composition,
    # tradenames, administrative mappings, and measurement properties.
    CLINICALLY_MEANINGFUL_UMLS_RELA: List[str] = [
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
    ]

    def __init__(
        self,
        neo4j_client: Optional[Any] = None,
        hop_limit: int = 2,
        timeout_seconds: float = 3.0,
        max_paths_per_pair: int = 50,
    ):
        """Initialize RelationshipTraverser.

        Args:
            neo4j_client: Neo4j client for executing Cypher queries.
                Injected via DI. If None, traversal returns empty.
            hop_limit: Maximum number of relationship edges to
                traverse between any two query concepts (1–2).
            timeout_seconds: Timeout in seconds for the entire
                traversal operation across all concept pairs.
            max_paths_per_pair: Maximum number of paths explored
                per concept pair to bound query cost.
        """
        self._neo4j_client = neo4j_client
        self._hop_limit = hop_limit
        self._timeout_seconds = timeout_seconds
        self._max_paths_per_pair = max_paths_per_pair
        logger.debug(
            "RelationshipTraverser initialized "
            "(hop_limit=%d, timeout=%.1fs, max_paths=%d)",
            hop_limit,
            timeout_seconds,
            max_paths_per_pair,
        )

    def _build_pair_cypher(
        self,
        concept_id_a: str,
        concept_id_b: str,
    ) -> Tuple[str, Dict[str, Any]]:
        """Build a Cypher query finding paths between two concepts.

        Generates a read-only Cypher MATCH query using a
        variable-length path constrained to only
        CLINICALLY_RELEVANT_RELATIONSHIPS and bounded by hop_limit.
        Collects chunk IDs via EXTRACTED_FROM from all path nodes.

        Args:
            concept_id_a: ID of the first concept node.
            concept_id_b: ID of the second concept node.

        Returns:
            Tuple of (cypher_string, parameters_dict).

        Requirements: 2.1, 2.2, 2.3, 2.5, 6.3, 9.1, 9.2
        """
        rel_types = "|".join(self.CLINICALLY_RELEVANT_RELATIONSHIPS)

        cypher = (
            f"MATCH path = (a:Concept {{concept_id: $concept_id_a}})"
            f"-[:{rel_types}"
            f"*1..{self._hop_limit}]"
            f"-(b:Concept {{concept_id: $concept_id_b}}) "
            f"WITH path, nodes(path) AS path_nodes "
            f"LIMIT $max_paths "
            f"UNWIND path_nodes AS n "
            f"OPTIONAL MATCH (n)-[:EXTRACTED_FROM]->(ch:Chunk) "
            f"RETURN DISTINCT ch.chunk_id AS chunk_id, "
            f"n.concept_id AS via_concept_id, "
            f"$concept_id_a AS source_concept_a, "
            f"$concept_id_b AS source_concept_b"
        )

        parameters = {
            "concept_id_a": concept_id_a,
            "concept_id_b": concept_id_b,
            "max_paths": self._max_paths_per_pair,
        }

        return cypher, parameters

    def _build_umls_pair_cypher(
        self,
        concept_id_a: str,
        concept_id_b: str,
    ) -> Tuple[str, Dict[str, Any]]:
        """Build a Cypher query that walks through the UMLS relationship graph.

        Leverages the EXTRACTED_FROM → SAME_AS → UMLS_REL architecture:
        1. Concept → SAME_AS → UMLSConcept (bridge to UMLS namespace)
        2. UMLSConcept → UMLS_REL → UMLSConcept (clinical relationships)
        3. UMLSConcept ← SAME_AS ← Concept (bridge back to document concepts)

        Only includes UMLS_REL edges with clinically meaningful rela_type values
        (isa, may_treat, cause_of, due_to, has_manifestation, etc.) and
        excludes qualifier metadata (QB edges), drug composition, and
        administrative mappings.

        Args:
            concept_id_a: ID of the first concept node.
            concept_id_b: ID of the second concept node.

        Returns:
            Tuple of (cypher_string, parameters_dict).
        """
        clinical_rela = self.CLINICALLY_MEANINGFUL_UMLS_RELA

        cypher = (
            "MATCH (a:Concept {concept_id: $concept_id_a})-[:SAME_AS]->"
            "(ua:UMLSConcept) "
            "MATCH (b:Concept {concept_id: $concept_id_b})-[:SAME_AS]->"
            "(ub:UMLSConcept) "
            "MATCH (ua)-[r:UMLS_REL]-(ub) "
            "WHERE r.rela_type IN $clinical_rela "
            "WITH a, b, ua, r, ub "
            "LIMIT $max_paths "
            "OPTIONAL MATCH (a)-[:EXTRACTED_FROM]->(ch:Chunk) "
            "RETURN DISTINCT ch.chunk_id AS chunk_id, "
            "a.concept_id AS via_concept_id, "
            "$concept_id_a AS source_concept_a, "
            "$concept_id_b AS source_concept_b, "
            "ua.preferred_name AS umls_source_name, "
            "r.rela_type AS umls_relationship, "
            "ub.preferred_name AS umls_target_name, "
            "'umls_1hop' AS path_type"
        )

        parameters = {
            "concept_id_a": concept_id_a,
            "concept_id_b": concept_id_b,
            "max_paths": self._max_paths_per_pair,
            "clinical_rela": clinical_rela,
        }

        return cypher, parameters

    def _build_umls_2hop_cypher(
        self,
        concept_id_a: str,
        concept_id_b: str,
    ) -> Tuple[str, Dict[str, Any]]:
        """Build a 2-hop UMLS path walker Cypher query.

        Extends the 1-hop UMLS traversal to two UMLS_REL hops, enabling
        paths like: metformin → may_be_treated_by → Type 2 Diabetes →
        isa → Diabetes Mellitus.

        Handles both arrow-direction patterns through the intermediate node:
        - Forward-forward: (ua)-[r1]->(umid)-[r2]->(ub)
        - Forward-reverse: (ua)-[r1]->(umid)<-[r2]-(ub)
          (e.g., metformin→T2D←DM where DM-[isa]->T2D)

        Both UMLS_REL hops must use clinically meaningful rela_type values.

        Args:
            concept_id_a: ID of the first concept node.
            concept_id_b: ID of the second concept node.

        Returns:
            Tuple of (cypher_string, parameters_dict).
        """
        clinical_rela = self.CLINICALLY_MEANINGFUL_UMLS_RELA

        # Use two MATCH patterns (UNION-like via OR in path) to cover both
        # arrow-direction patterns through the intermediate UMLSConcept.
        cypher = (
            "MATCH (a:Concept {concept_id: $concept_id_a})-[:SAME_AS]->"
            "(ua:UMLSConcept) "
            "MATCH (b:Concept {concept_id: $concept_id_b})-[:SAME_AS]->"
            "(ub:UMLSConcept) "
            "MATCH (ua)-[r1:UMLS_REL]-(umid:UMLSConcept)"
            "-[r2:UMLS_REL]-(ub) "
            "WHERE r1.rela_type IN $clinical_rela "
            "  AND r2.rela_type IN $clinical_rela "
            "  AND umid <> ua AND umid <> ub "
            "WITH a, b, ua, r1, umid, r2, ub "
            "LIMIT $max_paths "
            "OPTIONAL MATCH (a)-[:EXTRACTED_FROM]->(ch:Chunk) "
            "RETURN DISTINCT ch.chunk_id AS chunk_id, "
            "a.concept_id AS via_concept_id, "
            "$concept_id_a AS source_concept_a, "
            "$concept_id_b AS source_concept_b, "
            "ua.preferred_name AS umls_source_name, "
            "r1.rela_type + '→' + r2.rela_type AS umls_relationship, "
            "umid.preferred_name + '→' + ub.preferred_name "
            "  AS umls_target_name, "
            "'umls_2hop' AS path_type"
        )

        parameters = {
            "concept_id_a": concept_id_a,
            "concept_id_b": concept_id_b,
            "max_paths": self._max_paths_per_pair,
            "clinical_rela": clinical_rela,
        }

        return cypher, parameters

    def _build_shared_chunk_cypher(
        self,
        concept_id_a: str,
        concept_id_b: str,
    ) -> Tuple[str, Dict[str, Any]]:
        """Build a Cypher query finding chunks shared by two concepts.

        Directly finds Chunk nodes that both concepts point to via
        EXTRACTED_FROM edges — the co-occurrence path. This captures
        concepts that appear together in the same document passage
        even when no explicit inter-concept relationship edge exists.

        Args:
            concept_id_a: ID of the first concept node.
            concept_id_b: ID of the second concept node.

        Returns:
            Tuple of (cypher_string, parameters_dict).
        """
        cypher = (
            "MATCH (a:Concept {concept_id: $concept_id_a})"
            "-[:EXTRACTED_FROM]->(ch:Chunk)"
            "<-[:EXTRACTED_FROM]"
            "-(b:Concept {concept_id: $concept_id_b}) "
            "RETURN DISTINCT ch.chunk_id AS chunk_id, "
            "a.concept_id AS via_concept_id, "
            "$concept_id_a AS source_concept_a, "
            "$concept_id_b AS source_concept_b, "
            "a.name AS concept_a_name, "
            "b.name AS concept_b_name, "
            "'shared_chunk' AS path_type "
            "LIMIT $max_paths"
        )

        parameters = {
            "concept_id_a": concept_id_a,
            "concept_id_b": concept_id_b,
            "max_paths": self._max_paths_per_pair,
        }

        return cypher, parameters

    async def _check_umls_bridges(
        self,
        concept_ids: List[str],
    ) -> bool:
        """Check whether any of the given concepts have UMLS SAME_AS bridges.

        Runs a single cheap Neo4j query to determine if UMLS strategies
        should be included. When no concepts map to UMLS (e.g., non-medical
        queries), UMLS strategies are skipped entirely, preserving timeout
        budget for document-edge and shared-chunk strategies.

        Args:
            concept_ids: List of concept IDs to check.

        Returns:
            True if at least one concept has a SAME_AS edge to a
            UMLSConcept node.
        """
        if not self._neo4j_client or not concept_ids:
            return False

        try:
            async with self._neo4j_client.session() as session:
                result = await session.run(
                    "MATCH (c:Concept)-[:SAME_AS]->(:UMLSConcept) "
                    "WHERE c.concept_id IN $concept_ids "
                    "RETURN count(c) > 0 AS has_bridge "
                    "LIMIT 1",
                    concept_ids=concept_ids,
                )
                record = await result.single()
                if record:
                    return bool(record.get("has_bridge", False))
        except Exception as e:
            logger.debug(
                "UMLS bridge pre-check failed, including UMLS "
                "strategies as fallback: %s",
                e,
            )

        return True  # Include UMLS strategies on error (fail open)

    async def traverse(
        self,
        concept_matches: List[Dict[str, Any]],
    ) -> TraversalResult:
        """Find paths between all pairs of matched concepts.

        Uses up to 4 strategies per pair, in order of clinical specificity:

        1. **UMLS 1-hop** — Direct UMLS clinical relationships via
           SAME_AS → UMLS_REL → SAME_AS bridge (e.g., hyperglycemia
           --[isa]--> Diabetes Mellitus).

        2. **UMLS 2-hop** — Two-hop UMLS clinical paths (e.g.,
           metformin --[may_be_treated_by]--> Type 2 Diabetes
           --[isa]--> Diabetes Mellitus).

        3. **Direct inter-concept edges** — Existing document-extracted
           relationships between Concept nodes.

        4. **Shared EXTRACTED_FROM chunks** — Concepts that co-occur
           in the same document passages, capturing implicit
           relationships that explicit edges miss.

        Generates C(n,2) concept pairs from the matched concepts,
        executes bounded Cypher queries for each pair and strategy,
        and collects chunk IDs from concepts along discovered paths.

        On timeout or exception the traverser logs a WARNING and
        returns TraversalResult.empty() so the pipeline falls back
        to the existing retrieval path.

        Args:
            concept_matches: List of concept match dicts, each
                containing at least a ``concept_id`` key.

        Returns:
            TraversalResult with chunk-to-concept-set mapping and
            optional path annotations.

        Requirements: 2.1, 2.3, 2.4, 6.1, 6.2, 8.2, 8.3
        """
        if not self._neo4j_client:
            logger.warning(
                "No Neo4j client available for relationship traversal"
            )
            return TraversalResult.empty()

        concept_ids = [
            m.get("concept_id", "")
            for m in concept_matches
            if m.get("concept_id")
        ]

        if len(concept_ids) < 2:
            logger.debug(
                "Fewer than 2 concepts (%d); skipping traversal",
                len(concept_ids),
            )
            return TraversalResult.empty()

        # Cap concept count to avoid combinatorial explosion.
        _MAX_CONCEPTS_FOR_TRAVERSAL = 5
        if len(concept_ids) > _MAX_CONCEPTS_FOR_TRAVERSAL:
            logger.debug(
                "Too many concepts (%d > %d); using top %d by "
                "match score for traversal",
                len(concept_ids),
                _MAX_CONCEPTS_FOR_TRAVERSAL,
                _MAX_CONCEPTS_FOR_TRAVERSAL,
            )
            scored = [
                (
                    float(
                        m.get("match_score", 0)
                        or m.get("similarity_score", 0)
                        or 0
                    ),
                    m.get("concept_id", ""),
                )
                for m in concept_matches
                if m.get("concept_id")
            ]
            scored.sort(key=lambda x: x[0], reverse=True)
            concept_ids = [
                cid
                for _, cid in scored[:_MAX_CONCEPTS_FOR_TRAVERSAL]
            ]

        start_time = time.monotonic()
        chunk_concept_connections: Dict[str, Set[str]] = {}
        total_paths_found = 0
        # Collect path annotations for downstream chain synthesis.
        path_annotations: List[Dict[str, Any]] = []

        # Pre-check: determine whether any matched concepts have UMLS
        # bridges. When none do (e.g., non-medical queries), skip UMLS
        # strategies entirely to avoid wasting timeout budget on Neo4j
        # queries that are guaranteed to return empty.
        has_umls_bridges = await self._check_umls_bridges(concept_ids)

        # Strategy execution order: UMLS clinical paths first (most
        # specific), then document edges, then shared chunks (broadest).
        # 2-hop is conditionally skipped for pairs that 1-hop already
        # resolved (short-circuit optimization).
        # UMLS strategies are only included when at least one concept
        # has a SAME_AS bridge to a UMLSConcept.
        strategies: List[Tuple[str, Any]] = []
        if has_umls_bridges:
            strategies.append(("umls_1hop", self._build_umls_pair_cypher))
            strategies.append(("umls_2hop", self._build_umls_2hop_cypher))
        strategies.append(("direct", self._build_pair_cypher))
        strategies.append(("shared_chunk", self._build_shared_chunk_cypher))

        total_timeout_reached = False

        try:
            pairs = list(combinations(concept_ids, 2))
            logger.debug(
                "Traversing %d concept pairs from %d concepts "
                "with %d strategies (timeout=%.1fs)",
                len(pairs),
                len(concept_ids),
                len(strategies),
                self._timeout_seconds,
            )

            # Track pairs that already have 1-hop UMLS results so we
            # can skip the more expensive 2-hop traversal for them.
            pairs_with_umls_1hop: Set[Tuple[str, str]] = set()

            for cid_a, cid_b in pairs:
                if total_timeout_reached:
                    break
                pair_key = (cid_a, cid_b)

                for strategy_name, cypher_builder in strategies:
                    # --- Total timeout check ---
                    elapsed = time.monotonic() - start_time
                    if elapsed >= self._timeout_seconds:
                        logger.debug(
                            "Traversal total timeout reached (%.1fs); "
                            "returning partial results",
                            elapsed,
                        )
                        total_timeout_reached = True
                        break

                    # --- Short-circuit: skip 2-hop when 1-hop found paths ---
                    if strategy_name == "umls_2hop" and pair_key in pairs_with_umls_1hop:
                        logger.debug(
                            "Pair (%s, %s): skipping 2-hop — "
                            "1-hop UMLS already found paths",
                            cid_a,
                            cid_b,
                        )
                        continue

                    # --- Per-query timeout from remaining budget ---
                    # Allocate 50% of remaining time to this query (leave
                    # budget for subsequent queries), with a 0.3s floor.
                    _PER_QUERY_FLOOR = 0.3
                    remaining = self._timeout_seconds - elapsed
                    query_timeout = max(_PER_QUERY_FLOOR, remaining * 0.5)

                    cypher, params = cypher_builder(cid_a, cid_b)

                    try:
                        records = await asyncio.wait_for(
                            self._execute_cypher(cypher, params),
                            timeout=query_timeout,
                        )
                    except asyncio.TimeoutError:
                        logger.debug(
                            "Strategy '%s' timed out for pair "
                            "(%s, %s) after %.1fs",
                            strategy_name,
                            cid_a,
                            cid_b,
                            query_timeout,
                        )
                        continue

                    if not records:
                        continue

                    pair_paths = 0
                    for record in records:
                        chunk_id = record.get("chunk_id")
                        if not chunk_id:
                            # UMLS paths may return rows without chunks
                            # (e.g., when a UMLSConcept has no Concept
                            # bridge back). Still record the annotation.
                            umls_rel = record.get("umls_relationship")
                            if umls_rel:
                                path_annotations.append({
                                    "source_concept_a": record.get(
                                        "source_concept_a"
                                    ),
                                    "source_concept_b": record.get(
                                        "source_concept_b"
                                    ),
                                    "umls_source": record.get(
                                        "umls_source_name"
                                    ),
                                    "relationship": umls_rel,
                                    "umls_target": record.get(
                                        "umls_target_name"
                                    ),
                                    "path_type": record.get(
                                        "path_type", strategy_name
                                    ),
                                })
                            continue

                        pair_paths += 1
                        if chunk_id not in chunk_concept_connections:
                            chunk_concept_connections[chunk_id] = set()

                        chunk_concept_connections[chunk_id].add(cid_a)
                        chunk_concept_connections[chunk_id].add(cid_b)

                        # Annotate UMLS paths for downstream synthesis.
                        umls_rel = record.get("umls_relationship")
                        if umls_rel:
                            path_annotations.append({
                                "source_concept_a": record.get(
                                    "source_concept_a"
                                ),
                                "source_concept_b": record.get(
                                    "source_concept_b"
                                ),
                                "umls_source": record.get(
                                    "umls_source_name"
                                ),
                                "relationship": umls_rel,
                                "umls_target": record.get(
                                    "umls_target_name"
                                ),
                                "path_type": record.get(
                                    "path_type", strategy_name
                                ),
                                "chunk_id": chunk_id,
                            })

                    total_paths_found += pair_paths
                    logger.debug(
                        "Pair (%s, %s) strategy '%s': %d links",
                        cid_a,
                        cid_b,
                        strategy_name,
                        pair_paths,
                    )

                    # Mark this pair as resolved if 1-hop UMLS found
                    # chunk-carrying paths.
                    if strategy_name == "umls_1hop" and pair_paths > 0:
                        pairs_with_umls_1hop.add(pair_key)

        except Exception as exc:
            elapsed_ms = int(
                (time.monotonic() - start_time) * 1000
            )
            logger.warning(
                "Relationship traversal failed after %dms: %s",
                elapsed_ms,
                exc,
            )
            return TraversalResult.empty()

        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        result = TraversalResult(
            chunk_concept_connections=chunk_concept_connections,
            total_paths_found=total_paths_found,
            traversal_duration_ms=elapsed_ms,
            completed=not total_timeout_reached,
        )

        # Attach path annotations for downstream chain synthesis.
        if path_annotations:
            result.path_annotations = path_annotations
            # Deduplicate annotations: keep the best path_type per
            # concept pair (umls_1hop > umls_2hop > direct >
            # shared_chunk).
            _PATH_TYPE_RANK = {
                "umls_1hop": 0,
                "umls_2hop": 1,
                "direct": 2,
                "shared_chunk": 3,
            }
            seen_pairs: Set[Tuple[str, str]] = set()
            deduped: List[Dict[str, Any]] = []
            # Sort by path_type rank ascending (best first).
            sorted_annotations = sorted(
                path_annotations,
                key=lambda a: _PATH_TYPE_RANK.get(
                    a.get("path_type", "shared_chunk"), 99
                ),
            )
            for ann in sorted_annotations:
                pair_key = (
                    ann.get("source_concept_a", ""),
                    ann.get("source_concept_b", ""),
                )
                if pair_key not in seen_pairs:
                    seen_pairs.add(pair_key)
                    deduped.append(ann)
            result.path_annotations = deduped

        logger.debug(
            "Relationship traversal completed in %dms: "
            "%d paths, %d intersection chunks, %d UMLS annotations",
            elapsed_ms,
            total_paths_found,
            len(result.intersection_chunk_ids),
            len(path_annotations),
        )
        return result

    async def _execute_cypher(
        self,
        cypher: str,
        params: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Execute a Cypher query against Neo4j.

        Wraps the Neo4j client call to handle both async and sync
        client interfaces.

        Args:
            cypher: Cypher query string.
            params: Query parameters.

        Returns:
            List of record dicts from the query result.
        """
        client = self._neo4j_client
        if client is None:
            return []

        if hasattr(client, "execute_query"):
            method = client.execute_query
            if asyncio.iscoroutinefunction(method):
                result: List[Dict[str, Any]] = await method(
                    cypher, params
                )
                return result
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, method, cypher, params
            )
            return result

        if hasattr(client, "run_query"):
            method = client.run_query
            if asyncio.iscoroutinefunction(method):
                result = await method(cypher, params)
                return result
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, method, cypher, params
            )
            return result

        logger.warning(
            "Neo4j client has no execute_query or run_query method"
        )
        return []

    def set_neo4j_client(self, client: Any) -> None:
        """Set the Neo4j client after initialization.

        Useful for lazy initialization or testing.

        Args:
            client: Neo4j client instance.
        """
        self._neo4j_client = client
        logger.debug("Neo4j client set on RelationshipTraverser")

    @property
    def has_neo4j_client(self) -> bool:
        """Check if Neo4j client is available."""
        return self._neo4j_client is not None
