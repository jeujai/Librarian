"""
ConceptNet Validation Gate.

Validates candidate concepts against local ConceptNet data
in Neo4j and retrieves real semantic relationships to replace
co-occurrence RELATED_TO.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ...models.knowledge_graph import ConceptNode, RelationshipEdge
from .relation_type_mapper import RelationTypeMapper

logger = logging.getLogger(__name__)

NER_ENTITY_LABELS = frozenset({
    "ORG", "PERSON", "GPE", "PRODUCT", "WORK_OF_ART",
    "EVENT", "LAW", "NORP", "FAC", "LOC",
})

KEPT_PATTERN_TYPES = frozenset({
    "CODE_TERM", "MULTI_WORD", "ACRONYM",
})


@dataclass
class ValidationResult:
    """Result of validating candidate concepts."""

    validated_concepts: List[ConceptNode] = field(
        default_factory=list,
    )
    conceptnet_relationships: List[RelationshipEdge] = field(
        default_factory=list,
    )
    discarded_count: int = 0
    kept_by_ner: int = 0
    kept_by_conceptnet: int = 0
    kept_by_umls: int = 0
    kept_by_pattern: int = 0


class ConceptNetValidator:
    """Validate concepts against local ConceptNet data.

    Four-tier filtering:
      Tier 1  - concept exists in ConceptNet -> keep + rels
      Tier 1b - concept exists in UMLS (when available) -> keep
      Tier 2  - spaCy NER entity type -> keep
      Tier 3  - CODE_TERM/MULTI_WORD/ACRONYM -> keep
      Otherwise - discard
    """

    def __init__(
        self,
        neo4j_client: Any,
        umls_client: Optional[Any] = None,
    ) -> None:
        self._neo4j = neo4j_client
        self._umls_client = umls_client

    async def lookup_concept(
        self, name: str,
    ) -> Optional[Dict[str, Any]]:
        """Single concept lookup (lowered)."""
        query = (
            "MATCH (c:ConceptNetConcept) "
            "WHERE c.name = $name "
            "RETURN c"
        )
        records = await self._neo4j.execute_query(
            query, {"name": name.lower()},
        )
        if records:
            node = records[0].get("c", {})
            if isinstance(node, dict):
                return node.get("properties", node)
            return node
        return None

    async def batch_lookup_concepts(
        self, names: List[str],
    ) -> set:
        """Batch lookup - single query instead of N.

        Returns a set of lowered names found in ConceptNet.
        """
        if not names:
            return set()
        lower_names = list({n.lower() for n in names})
        query = (
            "MATCH (c:ConceptNetConcept) "
            "WHERE c.name IN $names "
            "RETURN c.name AS name"
        )
        try:
            records = await self._neo4j.execute_query(
                query, {"names": lower_names},
            )
            return {
                rec["name"].lower()
                for rec in records
                if rec.get("name")
            }
        except Exception:
            logger.warning(
                "Batch ConceptNet lookup failed",
                exc_info=True,
            )
            return set()

    async def get_relationships_for_concepts(
        self, concept_names: List[str],
    ) -> List[RelationshipEdge]:
        """Batch-fetch ConceptNet rels between concepts."""
        if not concept_names:
            return []
        lower_names = [n.lower() for n in concept_names]
        query = (
            "MATCH (a:ConceptNetConcept)"
            "-[r:ConceptNetRelation]->"
            "(b:ConceptNetConcept) "
            "WHERE a.name IN $names "
            "AND b.name IN $names "
            "RETURN a.name AS source, "
            "r.relation_type AS rel_type, "
            "r.weight AS weight, "
            "b.name AS target"
        )
        records = await self._neo4j.execute_query(
            query, {"names": lower_names},
        )
        edges: List[RelationshipEdge] = []
        for rec in records:
            edges.append(RelationshipEdge(
                subject_concept=rec["source"],
                predicate=rec["rel_type"],
                object_concept=rec["target"],
                confidence=float(
                    rec.get("weight", 0.5),
                ),
                relationship_type=RelationTypeMapper.classify(rec["rel_type"]),
                raw_relation_type=rec["rel_type"],
            ))
        return edges

    async def validate_concepts(
        self, candidates: List[ConceptNode],
    ) -> ValidationResult:
        """Run four-tier validation on candidates.

        Uses batch query for Tier 1 (N -> 1 round-trips).
        Tier 1b checks unmatched concepts against UMLS when available.
        """
        result = ValidationResult()
        conceptnet_names: List[str] = []
        all_names = [c.concept_name for c in candidates]
        found = await self.batch_lookup_concepts(all_names)

        # Collect concepts not matched by ConceptNet for UMLS check
        unmatched: List[ConceptNode] = []

        for concept in candidates:
            low = concept.concept_name.lower()
            if low in found:
                result.validated_concepts.append(concept)
                result.kept_by_conceptnet += 1
                conceptnet_names.append(
                    concept.concept_name,
                )
            else:
                unmatched.append(concept)

        # Tier 1b: UMLS batch lookup for unmatched concepts
        umls_matched: set = set()
        if unmatched and self._umls_client is not None:
            try:
                umls_names = [c.concept_name for c in unmatched]
                umls_map = await self._umls_client.batch_search_by_names(
                    umls_names,
                )
                if umls_map:
                    umls_matched = {
                        name for name in umls_map
                    }
            except Exception:
                logger.warning(
                    "UMLS batch lookup failed",
                    exc_info=True,
                )

        # Classify unmatched concepts through remaining tiers
        for concept in unmatched:
            if concept.concept_name in umls_matched:
                result.validated_concepts.append(concept)
                result.kept_by_umls += 1
            elif concept.concept_type in NER_ENTITY_LABELS:
                result.validated_concepts.append(concept)
                result.kept_by_ner += 1
            elif concept.concept_type in KEPT_PATTERN_TYPES:
                result.validated_concepts.append(concept)
                result.kept_by_pattern += 1
            else:
                result.discarded_count += 1

        if conceptnet_names:
            try:
                rels = (
                    await self
                    .get_relationships_for_concepts(
                        conceptnet_names,
                    )
                )
                result.conceptnet_relationships = rels
            except Exception:
                logger.warning(
                    "Failed to fetch ConceptNet rels",
                    exc_info=True,
                )
        return result

    async def _classify(
        self, concept: ConceptNode,
    ) -> tuple:
        """Classify a single concept (legacy path)."""
        try:
            cn = await self.lookup_concept(
                concept.concept_name,
            )
            if cn is not None:
                return True, "conceptnet"
        except Exception:
            logger.warning(
                "ConceptNet lookup failed for %r",
                concept.concept_name,
                exc_info=True,
            )
        if concept.concept_type in NER_ENTITY_LABELS:
            return True, "ner"
        if concept.concept_type in KEPT_PATTERN_TYPES:
            return True, "pattern"
        return False, None
