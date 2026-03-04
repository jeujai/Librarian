"""
Relation Type Registry.

Discovers and caches the set of ConceptNet relation types present
in Neo4j at startup, enabling the system to self-adapt to whatever
ConceptNet data is loaded without code changes.
"""

import logging
from typing import Any, Set

logger = logging.getLogger(__name__)


class RelationTypeRegistry:
    """Discovers and caches ConceptNet relation types from Neo4j."""

    _DISCOVERY_QUERY = (
        "MATCH ()-[r:ConceptNetRelation]->()"
        " RETURN DISTINCT r.relation_type AS rel_type"
    )

    def __init__(self, neo4j_client: Any) -> None:
        self._neo4j = neo4j_client
        self._discovered_types: Set[str] = set()
        self._initialized: bool = False

    async def initialize(self) -> None:
        """Query Neo4j for distinct relation types.

        Safe to call multiple times. On failure, logs a warning
        and operates with an empty discovered set.
        """
        try:
            records = await self._neo4j.execute_query(
                self._DISCOVERY_QUERY, {},
            )
            self._discovered_types = {
                rec["rel_type"]
                for rec in records
                if rec.get("rel_type")
            }
            self._initialized = True
            logger.info(
                "RelationTypeRegistry initialized with %d types",
                len(self._discovered_types),
            )
        except Exception:
            logger.warning(
                "Failed to initialize RelationTypeRegistry, "
                "operating with empty discovered set",
                exc_info=True,
            )
            self._discovered_types = set()
            self._initialized = True

    async def refresh(self) -> None:
        """Re-query Neo4j and update the cached set.

        On failure, retains the previously cached set.
        """
        try:
            records = await self._neo4j.execute_query(
                self._DISCOVERY_QUERY, {},
            )
            self._discovered_types = {
                rec["rel_type"]
                for rec in records
                if rec.get("rel_type")
            }
            logger.info(
                "RelationTypeRegistry refreshed with %d types",
                len(self._discovered_types),
            )
        except Exception:
            logger.warning(
                "Failed to refresh RelationTypeRegistry, "
                "retaining previously cached set",
                exc_info=True,
            )

    def get_discovered_types(self) -> Set[str]:
        """Return the set of discovered relation type strings."""
        return set(self._discovered_types)

    def is_known_type(self, relation_type: str) -> bool:
        """Check if a relation type was discovered in Neo4j."""
        return relation_type in self._discovered_types
