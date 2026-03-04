"""
ConceptNet Client for Knowledge Graph Enrichment.

Queries local ConceptNet data stored in Neo4j (:ConceptNetConcept nodes
and :ConceptNetRelation edges) instead of the external api.conceptnet.io.
"""

import logging
from typing import Any, Dict, List, Optional

from ..models.enrichment import ConceptNetRelation

logger = logging.getLogger(__name__)


class ConceptNetClient:
    """
    Client for local ConceptNet data in Neo4j.

    Queries :ConceptNetConcept nodes connected by :ConceptNetRelation edges
    that were bulk-loaded into Neo4j. This replaces the previous external
    API client (api.conceptnet.io) which is unreliable.
    """

    # Relation types we care about for enrichment
    SUPPORTED_RELATIONS = [
        "IsA",
        "PartOf",
        "UsedFor",
        "CapableOf",
        "HasProperty",
        "AtLocation",
        "Causes",
        "HasPrerequisite",
        "MotivatedByGoal",
        "RelatedTo",
        "Synonym",
        "Antonym",
        "DerivedFrom",
        "DefinedAs",
    ]

    def __init__(self, neo4j_client: Optional[Any] = None):
        """
        Initialize the ConceptNet client.

        Args:
            neo4j_client: Neo4j graph client with execute_query method.
                          If None, will be lazily obtained from database factory.
        """
        self._neo4j = neo4j_client
        self._neo4j_initialized = neo4j_client is not None
        logger.info("ConceptNetClient initialized (local Neo4j mode)")

    async def _get_neo4j(self) -> Any:
        """Lazily obtain Neo4j client from database factory."""
        if not self._neo4j_initialized:
            try:
                from ..clients.database_factory import get_database_factory
                factory = get_database_factory()
                self._neo4j = factory.get_graph_client()
                await self._neo4j.connect()
                self._neo4j_initialized = True
            except Exception as e:
                logger.warning(f"Failed to get Neo4j client: {e}")
                return None
        return self._neo4j

    async def get_relationships(
        self,
        concept_name: str,
        limit: int = 20,
        language: str = "en",
    ) -> List[ConceptNetRelation]:
        """
        Get ConceptNet relationships for a concept from local Neo4j.

        Args:
            concept_name: Concept to query
            limit: Maximum relationships to return
            language: Language code (default: English)

        Returns:
            List of ConceptNet relationships
        """
        neo4j = await self._get_neo4j()
        if neo4j is None:
            return []

        normalized = concept_name.lower().strip()

        try:
            query = (
                "MATCH (a:ConceptNetConcept {name: $name})"
                "-[r:ConceptNetRelation]->"
                "(b:ConceptNetConcept) "
                "WHERE r.relation_type IN $rel_types "
                "AND b.language = $lang "
                "RETURN a.name AS subject, "
                "r.relation_type AS relation, "
                "b.name AS object, "
                "r.weight AS weight, "
                "r.source_uri AS source_uri "
                "ORDER BY r.weight DESC "
                "LIMIT $limit"
            )
            records = await neo4j.execute_query(query, {
                "name": normalized,
                "rel_types": self.SUPPORTED_RELATIONS,
                "lang": language,
                "limit": limit,
            })

            relations = []
            for rec in records:
                relations.append(ConceptNetRelation(
                    subject=rec.get("subject", normalized),
                    relation=rec.get("relation", "RelatedTo"),
                    object=rec.get("object", ""),
                    weight=float(rec.get("weight", 0.0)),
                    source_uri=rec.get("source_uri", ""),
                ))

            if relations:
                logger.debug(
                    f"Found {len(relations)} local ConceptNet relations "
                    f"for '{concept_name}'"
                )
            return relations

        except Exception as e:
            logger.warning(
                f"Local ConceptNet lookup failed for '{concept_name}': {e}"
            )
            return []

    async def get_relationship_by_type(
        self,
        concept_name: str,
        relation_type: str,
        limit: int = 10,
        language: str = "en",
    ) -> List[ConceptNetRelation]:
        """
        Get specific relationship type for a concept.

        Args:
            concept_name: Concept to query
            relation_type: Relationship type (e.g., "IsA", "PartOf")
            limit: Maximum relationships to return
            language: Language code

        Returns:
            List of ConceptNet relationships of the specified type
        """
        if relation_type not in self.SUPPORTED_RELATIONS:
            logger.warning(f"Unsupported relation type: {relation_type}")
            return []

        neo4j = await self._get_neo4j()
        if neo4j is None:
            return []

        normalized = concept_name.lower().strip()

        try:
            query = (
                "MATCH (a:ConceptNetConcept {name: $name})"
                "-[r:ConceptNetRelation {relation_type: $rel_type}]->"
                "(b:ConceptNetConcept) "
                "WHERE b.language = $lang "
                "RETURN a.name AS subject, "
                "r.relation_type AS relation, "
                "b.name AS object, "
                "r.weight AS weight, "
                "r.source_uri AS source_uri "
                "ORDER BY r.weight DESC "
                "LIMIT $limit"
            )
            records = await neo4j.execute_query(query, {
                "name": normalized,
                "rel_type": relation_type,
                "lang": language,
                "limit": limit,
            })

            return [
                ConceptNetRelation(
                    subject=rec.get("subject", normalized),
                    relation=rec.get("relation", relation_type),
                    object=rec.get("object", ""),
                    weight=float(rec.get("weight", 0.0)),
                    source_uri=rec.get("source_uri", ""),
                )
                for rec in records
            ]

        except Exception as e:
            logger.warning(
                f"Local ConceptNet lookup failed for "
                f"'{concept_name}' ({relation_type}): {e}"
            )
            return []

    async def batch_get_relationships(
        self,
        concept_names: List[str],
        limit_per_concept: int = 10,
        language: str = "en",
    ) -> Dict[str, List[ConceptNetRelation]]:
        """
        Batch get relationships for multiple concepts in a single query.

        Args:
            concept_names: List of concept names to query
            limit_per_concept: Max relationships per concept
            language: Language code

        Returns:
            Dict mapping concept names to their relationships
        """
        if not concept_names:
            return {}

        neo4j = await self._get_neo4j()
        if neo4j is None:
            return {name: [] for name in concept_names}

        lower_names = [n.lower().strip() for n in concept_names]
        name_map = {n.lower().strip(): n for n in concept_names}

        try:
            # Single batch query for all concepts
            query = (
                "MATCH (a:ConceptNetConcept)"
                "-[r:ConceptNetRelation]->"
                "(b:ConceptNetConcept) "
                "WHERE a.name IN $names "
                "AND r.relation_type IN $rel_types "
                "AND b.language = $lang "
                "RETURN a.name AS subject, "
                "r.relation_type AS relation, "
                "b.name AS object, "
                "r.weight AS weight, "
                "r.source_uri AS source_uri "
                "ORDER BY a.name, r.weight DESC"
            )
            records = await neo4j.execute_query(query, {
                "names": lower_names,
                "rel_types": self.SUPPORTED_RELATIONS,
                "lang": language,
            })

            # Group by concept, respecting limit_per_concept
            results: Dict[str, List[ConceptNetRelation]] = {
                name: [] for name in concept_names
            }
            counts: Dict[str, int] = {n: 0 for n in lower_names}

            for rec in records:
                subj = rec.get("subject", "")
                if counts.get(subj, 0) >= limit_per_concept:
                    continue
                counts[subj] = counts.get(subj, 0) + 1

                original_name = name_map.get(subj, subj)
                results.setdefault(original_name, []).append(
                    ConceptNetRelation(
                        subject=subj,
                        relation=rec.get("relation", "RelatedTo"),
                        object=rec.get("object", ""),
                        weight=float(rec.get("weight", 0.0)),
                        source_uri=rec.get("source_uri", ""),
                    )
                )

            found = sum(1 for v in results.values() if v)
            if found:
                logger.debug(
                    f"Batch ConceptNet lookup: {found}/{len(concept_names)} "
                    f"concepts had relations"
                )
            return results

        except Exception as e:
            logger.warning(f"Batch local ConceptNet lookup failed: {e}")
            return {name: [] for name in concept_names}
