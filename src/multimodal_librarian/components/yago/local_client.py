"""Local YAGO client for querying YAGO data from Neo4j.

This client provides local Neo4j queries for YAGO data with graceful
degradation when the data is not available.
"""

import logging
from typing import TYPE_CHECKING, Dict, List, Optional

from .logger import YagoLoggerMixin, get_yago_logger
from .models import YagoEntityData, YagoSearchResult

if TYPE_CHECKING:
    from ...clients.protocols import GraphStoreClient

logger = logging.getLogger(__name__)


class YagoLocalClient(YagoLoggerMixin):
    """Local client for YAGO data stored in Neo4j.

    Queries local Neo4j data for entity lookups. Returns None when data
    is unavailable for graceful degradation.

    Example:
        client = YagoLocalClient(neo4j_client=graph_client)
        entity = await client.get_entity("Q42")
        if entity:
            print(f"Found: {entity.label}")
    """

    def __init__(self, neo4j_client: "GraphStoreClient"):
        """Initialize the local YAGO client.

        Args:
            neo4j_client: Graph database client for Neo4j operations.
                Should implement the GraphStoreClient protocol.
        """
        self._neo4j_client = neo4j_client
        self._logger = get_yago_logger(self.__class__.__name__)
        self._logger.info("YagoLocalClient initialized")

    async def get_entity(self, entity_id: str) -> Optional[YagoEntityData]:
        """Get a YAGO entity by its ID.

        Args:
            entity_id: The entity ID (e.g., "Q42").

        Returns:
            YagoEntityData if found, None if not found or Neo4j unavailable.

        Example:
            entity = await client.get_entity("Q42")
            if entity:
                print(f"Entity: {entity.label}")
        """
        try:
            query = """
            MATCH (e:YagoEntity {entity_id: $entity_id})
            RETURN e.entity_id as entity_id, e.label as label,
                   e.description as description, e.data as data
            """
            results = await self._neo4j_client.execute_query(
                query, {"entity_id": entity_id}
            )

            if not results:
                self._logger.debug(f"Entity not found: {entity_id}")
                return None

            record = results[0]
            data = record.get("data")

            # Parse stored data if it's a JSON string
            import json

            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except json.JSONDecodeError:
                    data = {}

            return YagoEntityData(
                entity_id=record["entity_id"],
                label=record["label"] or "",
                description=record.get("description"),
                instance_of=data.get("instance_of", []),
                subclass_of=data.get("subclass_of", []),
                aliases=data.get("aliases", []),
            )

        except Exception as e:
            self._logger.warning(f"Error getting entity {entity_id}: {e}")
            return None

    async def search_entities(
        self, query: str, limit: int = 10
    ) -> List[YagoSearchResult]:
        """Search for YAGO entities by English label.

        Uses CONTAINS for fuzzy matching on the English label.

        Args:
            query: Search query string.
            limit: Maximum number of results to return (default 10).

        Returns:
            List of YagoSearchResult objects.

        Example:
            results = await client.search_entities("Douglas Adams", limit=5)
            for r in results:
                print(f"{r.entity_id}: {r.label}")
        """
        try:
            cypher_query = """
            MATCH (e:YagoEntity)
            WHERE e.label CONTAINS $query
            RETURN e.entity_id as entity_id, e.label as label,
                   e.description as description
            ORDER BY e.label
            LIMIT $limit
            """
            results = await self._neo4j_client.execute_query(
                cypher_query, {"query": query, "limit": limit}
            )

            search_results = []
            for record in results:
                search_results.append(
                    YagoSearchResult(
                        entity_id=record["entity_id"],
                        label=record["label"] or "",
                        description=record.get("description"),
                    )
                )

            msg = (
                f"Search for '{query}' returned "
                f"{len(search_results)} results"
            )
            self._logger.debug(msg)
            return search_results

        except Exception as e:
            self._logger.warning(f"Error searching entities: {e}")
            return []

    async def batch_search_entities(
        self, names: List[str]
    ) -> Dict[str, Optional["YagoEntityData"]]:
        """Batch search for YAGO entities by label.

        Uses exact match against the RANGE index (fast), then
        retries unmatched names with title-case. Avoids toLower()
        which forces a full scan of 391K nodes.

        Args:
            names: List of concept names to look up.

        Returns:
            Dict mapping input name to YagoEntityData or None.
        """
        if not names:
            return {}

        import json

        results: Dict[str, Optional[YagoEntityData]] = {
            n: None for n in names
        }

        try:
            # Build candidate labels: original + title-cased
            # e.g. "machine learning" -> ["machine learning",
            #       "Machine Learning", "Machine learning"]
            candidate_map: Dict[str, str] = {}  # label -> orig name
            all_labels: List[str] = []
            for name in names:
                variants = {name}
                variants.add(name.title())
                variants.add(name.capitalize())
                for v in variants:
                    if v not in candidate_map:
                        candidate_map[v] = name
                        all_labels.append(v)

            # Single UNWIND with exact match (uses RANGE index)
            cypher_query = """
            UNWIND $labels AS lbl
            OPTIONAL MATCH (e:YagoEntity {label: lbl})
            WITH lbl,
                 collect({
                     entity_id: e.entity_id,
                     label: e.label,
                     description: e.description,
                     data: e.data
                 })[0] AS best
            WHERE best.entity_id IS NOT NULL
            RETURN lbl,
                   best.entity_id AS entity_id,
                   best.label AS label,
                   best.description AS description,
                   best.data AS data
            """
            records = await self._neo4j_client.execute_query(
                cypher_query, {"labels": all_labels}
            )

            for rec in (records or []):
                lbl = rec["lbl"]
                orig_name = candidate_map.get(lbl)
                if not orig_name or results[orig_name] is not None:
                    continue

                data = rec.get("data")
                if isinstance(data, str):
                    try:
                        data = json.loads(data)
                    except json.JSONDecodeError:
                        data = {}
                if not data:
                    data = {}

                entity = YagoEntityData(
                    entity_id=rec["entity_id"],
                    label=rec["label"] or "",
                    description=rec.get("description"),
                    instance_of=data.get(
                        "instance_of", []
                    ),
                    subclass_of=data.get(
                        "subclass_of", []
                    ),
                    aliases=data.get("aliases", []),
                )
                results[orig_name] = entity

            found = sum(
                1 for v in results.values()
                if v is not None
            )
            self._logger.debug(
                f"Batch YAGO search: "
                f"{found}/{len(names)} matched"
            )

        except Exception as e:
            self._logger.warning(
                f"Batch YAGO search failed: {e}"
            )

        return results

    async def get_instances_of(
        self, class_id: str, limit: int = 100
    ) -> List[str]:
        """Get all entities that are instances of a given class.

        Args:
            class_id: The class entity ID (e.g., "Q5" for human).
            limit: Maximum number of results to return (default 100).

        Returns:
            List of entity IDs that are instances of the class.

        Example:
            humans = await client.get_instances_of("Q5", limit=10)
            print(f"Found {len(humans)} humans")
        """
        try:
            query = """
            MATCH (e:YagoEntity)-[:INSTANCE_OF]->
                  (c:YagoEntity {entity_id: $class_id})
            RETURN e.entity_id as entity_id
            LIMIT $limit
            """
            results = await self._neo4j_client.execute_query(
                query, {"class_id": class_id, "limit": limit}
            )

            entity_ids = [r["entity_id"] for r in results]
            self._logger.debug(
                f"Found {len(entity_ids)} instances of {class_id}"
            )
            return entity_ids

        except Exception as e:
            self._logger.warning(f"Error getting instances of {class_id}: {e}")
            return []

    async def get_subclasses_of(
        self, class_id: str, limit: int = 100
    ) -> List[str]:
        """Get all subclasses of a given class.

        Args:
            class_id: The parent class entity ID (e.g., "Q729" for animal).
            limit: Maximum number of results to return (default 100).

        Returns:
            List of entity IDs that are subclasses of the class.

        Example:
            animals = await client.get_subclasses_of("Q729", limit=10)
            print(f"Found {len(animals)} animal subclasses")
        """
        try:
            query = """
            MATCH (e:YagoEntity)-[:SUBCLASS_OF]->
                  (c:YagoEntity {entity_id: $class_id})
            RETURN e.entity_id as entity_id
            LIMIT $limit
            """
            results = await self._neo4j_client.execute_query(
                query, {"class_id": class_id, "limit": limit}
            )

            entity_ids = [r["entity_id"] for r in results]
            self._logger.debug(
                f"Found {len(entity_ids)} subclasses of {class_id}"
            )
            return entity_ids

        except Exception as e:
            self._logger.warning(f"Error getting subclasses of {class_id}: {e}")
            return []

    async def get_related_entities(
        self, entity_id: str, relationship_type: str
    ) -> List[str]:
        """Get entities related by a specific relationship type.

        Args:
            entity_id: The source entity ID.
            relationship_type: Type of relationship (INSTANCE_OF, SUBCLASS_OF,
                              ALIAS_OF, SEE_ALSO).

        Returns:
            List of related entity IDs.

        Example:
            # Get what Q42 is an instance of
            instances = await client.get_related_entities("Q42", "INSTANCE_OF")
        """
        try:
            # Validate relationship type
            valid_types = {"INSTANCE_OF", "SUBCLASS_OF", "ALIAS_OF", "SEE_ALSO"}
            rel_type = relationship_type.upper()
            if rel_type not in valid_types:
                self._logger.warning(
                    f"Invalid relationship type: {relationship_type}"
                )
                return []

            query = f"""
            MATCH (e:YagoEntity {{entity_id: $entity_id}})
                  -[r:{rel_type}]->(related:YagoEntity)
            RETURN related.entity_id as entity_id
            """

            results = await self._neo4j_client.execute_query(
                query, {"entity_id": entity_id}
            )

            entity_ids = [r["entity_id"] for r in results]
            self._logger.debug(
                f"Found {len(entity_ids)} entities related via {relationship_type}"
            )
            return entity_ids

        except Exception as e:
            self._logger.warning(
                f"Error getting related entities for {entity_id}: {e}"
            )
            return []

    async def is_available(self) -> bool:
        """Check if YAGO data is loaded in Neo4j.

        Returns:
            True if YAGO data is available, False otherwise.

        Example:
            if await client.is_available():
                print("YAGO data is loaded")
        """
        try:
            query = """
            MATCH (e:YagoEntity)
            RETURN count(e) as count
            LIMIT 1
            """
            results = await self._neo4j_client.execute_query(query)

            if results:
                count = results[0].get("count", 0)
                is_available = count > 0
                self._logger.debug(
                    f"YAGO data available: {is_available} ({count} entities)"
                )
                return is_available

            return False

        except Exception as e:
            self._logger.warning(f"Error checking YAGO availability: {e}")
            return False