"""
UMLS Bridger Component.

Creates SAME_AS edges between document-extracted Concept nodes and
UMLSConcept nodes by case-insensitive exact matching on preferred
names and synonyms. Uses MERGE for idempotent edge creation.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class BridgeResult:
    """Result of a SAME_AS bridging operation."""

    concepts_matched: int
    same_as_edges_created: int
    unmatched_concepts: int
    elapsed_seconds: float


class UMLSBridger:
    """Creates SAME_AS edges between Concept and UMLSConcept nodes.

    Queries all document-extracted Concept nodes and all UMLSConcept
    nodes, performs case-insensitive exact matching on preferred_name
    and synonyms, and batch-MERGEs SAME_AS relationships.

    Idempotent: re-running produces no duplicate edges.
    """

    def __init__(self, neo4j_client: Any) -> None:
        self._neo4j = neo4j_client
        logger.info("umls_bridger_initialized")

    async def _fetch_concept_names(self) -> List[str]:
        """Fetch all document-extracted Concept node names."""
        query = (
            "MATCH (c:Concept) "
            "RETURN DISTINCT c.name AS name"
        )
        results = await self._neo4j.execute_query(query)
        return [
            r["name"]
            for r in results if r.get("name")
        ]

    async def _match_concepts_batch(
        self,
        names: List[str],
    ) -> List[Dict[str, str]]:
        """Match concept names against UMLSConcept.

        Uses the pre-computed lower_name and lower_synonyms
        properties on UMLSConcept nodes for fast
        case-insensitive matching.
        """
        if not names:
            return []

        lower_names = [n.lower() for n in names]
        # Map lower -> original for result reconstruction
        lower_to_orig: Dict[str, str] = {}
        for n in names:
            low = n.lower()
            if low not in lower_to_orig:
                lower_to_orig[low] = n

        timestamp = datetime.now(timezone.utc).isoformat()
        matches: List[Dict[str, str]] = []

        # Match on preferred_name (indexed via lower_name)
        try:
            pn_results = await self._neo4j.execute_query(
                "UNWIND $names AS name "
                "MATCH (u:UMLSConcept) WHERE u.lower_name = name "
                "RETURN name, u.cui AS cui",
                {"names": lower_names},
            )
            if pn_results:
                for r in pn_results:
                    orig = lower_to_orig.get(r["name"], r["name"])
                    matches.append({
                        "concept_name": orig,
                        "lower_name": r["name"],
                        "cui": r["cui"],
                        "match_type": "preferred_name",
                        "created_at": timestamp,
                    })
        except Exception as e:
            logger.warning(f"UMLS bridger preferred_name match failed: {e}")

        # Match on synonyms (via indexed UMLSSynonym nodes)
        try:
            syn_results = await self._neo4j.execute_query(
                "UNWIND $names AS name "
                "MATCH (s:UMLSSynonym {name: name})<-[:HAS_SYNONYM]-(u:UMLSConcept) "
                "RETURN name, u.cui AS cui",
                {"names": lower_names},
            )
            if syn_results:
                for r in syn_results:
                    orig = lower_to_orig.get(r["name"], r["name"])
                    matches.append({
                        "concept_name": orig,
                        "lower_name": r["name"],
                        "cui": r["cui"],
                        "match_type": "synonym",
                        "created_at": timestamp,
                    })
        except Exception as e:
            logger.warning(f"UMLS bridger synonym match failed: {e}")

        # Deduplicate by (concept_name, cui)
        seen_pairs: set = set()
        deduped: List[Dict[str, str]] = []
        for m in matches:
            pair = (m["concept_name"], m["cui"])
            if pair not in seen_pairs:
                seen_pairs.add(pair)
                deduped.append(m)

        return deduped

    async def _merge_same_as_batch(
        self,
        matches: List[Dict[str, str]],
    ) -> int:
        """MERGE a batch of SAME_AS edges. Returns edges created."""
        if not matches:
            return 0
        query = (
            "UNWIND $items AS item "
            "MATCH (c:Concept) WHERE c.name_lower = item.lower_name "
            "MATCH (u:UMLSConcept {cui: item.cui}) "
            "MERGE (c)-[r:SAME_AS]->(u) "
            "ON CREATE SET r.match_type = item.match_type, "
            "r.created_at = item.created_at "
            "RETURN count(r) AS cnt"
        )
        results = await self._neo4j.execute_write_query(
            query, {"items": matches}
        )
        if results and len(results) > 0:
            return results[0].get("cnt", 0)
        return 0

    async def bridge_concepts(
        self, concept_names: List[str], batch_size: int = 500
    ) -> BridgeResult:
        """Bridge only the provided concept names to UMLSConcept nodes.

        Unlike ``create_same_as_edges`` which fetches ALL Concept nodes
        from the graph, this method accepts a pre-built list of concept
        names (typically from the current document) and performs matching
        + SAME_AS edge creation only for those names.

        Args:
            concept_names: Concept names to bridge (from current document).
            batch_size: Number of matches per MERGE sub-batch.

        Returns:
            BridgeResult with counts and elapsed time.
        """
        import time

        start = time.monotonic()

        if not concept_names:
            return BridgeResult(
                concepts_matched=0,
                same_as_edges_created=0,
                unmatched_concepts=0,
                elapsed_seconds=0.0,
            )

        logger.info(
            "bridge_concepts_incremental",
            count=len(concept_names),
        )

        # Match in sub-batches against UMLS using indexed properties
        MATCH_BATCH = 200
        all_matches: List[Dict[str, str]] = []
        matched_concept_names: set = set()

        for sb_start in range(0, len(concept_names), MATCH_BATCH):
            sb_names = concept_names[sb_start:sb_start + MATCH_BATCH]
            batch_matches = await self._match_concepts_batch(sb_names)
            for m in batch_matches:
                matched_concept_names.add(m["concept_name"])
            all_matches.extend(batch_matches)

        logger.info(
            "bridge_incremental_matching_complete",
            total_concepts=len(concept_names),
            matched=len(matched_concept_names),
            total_match_pairs=len(all_matches),
        )

        # Batch MERGE SAME_AS edges
        total_edges = 0
        for i in range(0, len(all_matches), batch_size):
            batch = all_matches[i:i + batch_size]
            edges = await self._merge_same_as_batch(batch)
            total_edges += edges

        elapsed = time.monotonic() - start
        unmatched = len(concept_names) - len(matched_concept_names)

        result = BridgeResult(
            concepts_matched=len(matched_concept_names),
            same_as_edges_created=total_edges,
            unmatched_concepts=unmatched,
            elapsed_seconds=round(elapsed, 2),
        )

        logger.info(
            "bridge_incremental_complete",
            concepts_matched=result.concepts_matched,
            same_as_edges_created=result.same_as_edges_created,
            unmatched_concepts=result.unmatched_concepts,
            elapsed_seconds=result.elapsed_seconds,
        )

        return result

    async def create_same_as_edges(
        self, batch_size: int = 500
    ) -> BridgeResult:
        """Create SAME_AS edges between Concept and UMLSConcept nodes.

        Uses indexed lower_name and lower_synonyms properties on
        UMLSConcept for fast matching. Processes concept names in
        sub-batches to avoid Neo4j transaction timeouts.

        Args:
            batch_size: Number of concept names per matching sub-batch.

        Returns:
            BridgeResult with counts and elapsed time.
        """
        import time

        start = time.monotonic()

        logger.info("bridge_fetching_concepts")
        concept_names = await self._fetch_concept_names()
        logger.info("bridge_concepts_fetched", count=len(concept_names))

        # Match in sub-batches against UMLS using indexed properties
        MATCH_BATCH = 200
        all_matches: List[Dict[str, str]] = []
        matched_concept_names: set = set()

        for sb_start in range(0, len(concept_names), MATCH_BATCH):
            sb_names = concept_names[sb_start:sb_start + MATCH_BATCH]
            batch_matches = await self._match_concepts_batch(sb_names)
            for m in batch_matches:
                matched_concept_names.add(m["concept_name"])
            all_matches.extend(batch_matches)

        logger.info(
            "bridge_matching_complete",
            total_concepts=len(concept_names),
            matched=len(matched_concept_names),
            total_match_pairs=len(all_matches),
        )

        # Batch MERGE SAME_AS edges
        total_edges = 0
        for i in range(0, len(all_matches), batch_size):
            batch = all_matches[i:i + batch_size]
            edges = await self._merge_same_as_batch(batch)
            total_edges += edges
            logger.info(
                "bridge_batch_complete",
                batch_number=i // batch_size + 1,
                edges_in_batch=edges,
                total_edges=total_edges,
            )

        elapsed = time.monotonic() - start
        unmatched = len(concept_names) - len(matched_concept_names)

        result = BridgeResult(
            concepts_matched=len(matched_concept_names),
            same_as_edges_created=total_edges,
            unmatched_concepts=unmatched,
            elapsed_seconds=round(elapsed, 2),
        )

        logger.info(
            "bridge_complete",
            concepts_matched=result.concepts_matched,
            same_as_edges_created=result.same_as_edges_created,
            unmatched_concepts=result.unmatched_concepts,
            elapsed_seconds=result.elapsed_seconds,
        )

        return result
