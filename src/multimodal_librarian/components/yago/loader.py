"""YAGO Neo4j Loader for batch importing entities into Neo4j."""

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from ...clients.neo4j_client import Neo4jClient
from .logger import YagoLoggerMixin, log_import_metrics
from .models import FilteredEntity

logger = logging.getLogger(__name__)


@dataclass
class ImportResult:
    """Result of an import operation."""
    imported: int = 0
    failed: int = 0
    relationships_created: int = 0
    duration_seconds: float = 0.0
    failed_entity_ids: List[str] = None

    def __post_init__(self):
        if self.failed_entity_ids is None:
            self.failed_entity_ids = []


@dataclass
class YagoStats:
    """Statistics about YAGO data in Neo4j."""
    entity_count: int
    relationship_count: int
    instance_of_count: int
    subclass_of_count: int
    alias_of_count: int
    see_also_count: int
    storage_bytes: int


class DeadLetterQueue:
    """Queue for failed batches awaiting retry."""

    def __init__(self, max_size: int = 1000):
        self._queue: List[FilteredEntity] = []
        self._max_size = max_size

    def append(self, batch: List[FilteredEntity]) -> None:
        """Add failed batch to queue."""
        self._queue.extend(batch)
        if len(self._queue) > self._max_size:
            # Remove oldest entries
            self._queue = self._queue[-self._max_size:]

    def get_all(self) -> List[FilteredEntity]:
        """Get all failed entities for retry."""
        failed = self._queue.copy()
        self._queue.clear()
        return failed

    def __len__(self) -> int:
        return len(self._queue)

    def is_empty(self) -> bool:
        return len(self._queue) == 0


class YagoNeo4jLoader(YagoLoggerMixin):
    """
    Loader for importing YAGO entities into Neo4j.

    This component handles batch importing of filtered YAGO entities
    with retry logic, progress tracking, and dead letter queue support.

    Attributes:
        neo4j_client: Neo4j client for database operations
        batch_size: Number of entities per batch (default: 1000)
        max_retries: Maximum retry attempts for failed batches (default: 3)
        retry_delay: Base delay in seconds between retries (default: 5)
        namespace: YAGO namespace for isolation (default: "yago")

    Example:
        ```python
        loader = YagoNeo4jLoader(neo4j_client, batch_size=1000)
        async for entity in entities:
            await loader.create_entity_node(entity)
        stats = await loader.get_stats()
        ```
    """

    # Retry configuration
    MAX_RETRIES = 3
    RETRY_DELAY = 5  # seconds

    # Relationship types
    REL_INSTANCE_OF = "INSTANCE_OF"
    REL_SUBCLASS_OF = "SUBCLASS_OF"
    REL_ALIAS_OF = "ALIAS_OF"
    REL_SEE_ALSO = "SEE_ALSO"

    def __init__(
        self,
        neo4j_client: Neo4jClient,
        batch_size: int = 1000,
        max_retries: int = None,
        retry_delay: int = None,
    ):
        """
        Initialize the YAGO Neo4j loader.

        Args:
            neo4j_client: Neo4j client instance for database operations
            batch_size: Number of entities per batch (default: 1000)
            max_retries: Maximum retry attempts for failed batches (default: 3)
            retry_delay: Base delay in seconds between retries (default: 5)
        """
        self._neo4j_client = neo4j_client
        self.batch_size = batch_size
        self.max_retries = max_retries if max_retries is not None else self.MAX_RETRIES
        self.retry_delay = retry_delay if retry_delay is not None else self.RETRY_DELAY

        # Progress tracking
        self._imported_count = 0
        self._relationship_count = 0
        self._failed_count = 0
        self._last_entity_id: Optional[str] = None
        self._start_time: Optional[float] = None
        self._total_entities: Optional[int] = None

        # Dead letter queue for failed batches
        self._dead_letter_queue = DeadLetterQueue()

        # Checkpoint for resuming
        self._checkpoint_entity_id: Optional[str] = None
        self._checkpoint_imported_count: int = 0

        # Track failed entity IDs for reporting
        self._failed_entity_ids: List[str] = []

        self.logger.info(
            f"YagoNeo4jLoader initialized with batch_size={batch_size}, "
            f"max_retries={self.max_retries}"
        )

    @property
    def imported_count(self) -> int:
        """Get the number of successfully imported entities."""
        return self._imported_count

    @property
    def relationship_count(self) -> int:
        """Get the number of relationships created."""
        return self._relationship_count

    @property
    def failed_count(self) -> int:
        """Get the number of failed entities."""
        return self._failed_count

    @property
    def last_entity_id(self) -> Optional[str]:
        """Get the last successfully imported entity ID."""
        return self._last_entity_id

    async def import_entities(
        self,
        entities: any,
        total_entities: Optional[int] = None,
    ) -> ImportResult:
        """
        Import entities with batch transactions and retry logic.

        This method processes entities from an async iterator, batching them
        for efficient import. Each batch is imported atomically with retry
        logic for transient failures.

        Args:
            entities: Async iterator yielding FilteredEntity objects
            total_entities: Optional total count for progress tracking

        Returns:
            ImportResult with import statistics

        Raises:
            Exception: If import fails after all retries

        Validates: Requirements 11.1, 11.2, 11.3, 11.4
        """
        self._start_time = time.time()
        self._total_entities = total_entities
        self._imported_count = 0
        self._relationship_count = 0
        self._failed_count = 0
        self._failed_entity_ids: List[str] = []

        self.logger.info("Starting entity import", batch_size=self.batch_size)

        batch: List[FilteredEntity] = []
        async for entity in entities:
            # Skip entities before checkpoint if resuming
            if self._checkpoint_entity_id is not None:
                if entity.entity_id != self._checkpoint_entity_id:
                    continue
                # Found checkpoint, skip it and clear for subsequent entities
                self._checkpoint_entity_id = None
                continue

            batch.append(entity)

            if len(batch) >= self.batch_size:
                success = await self._import_batch(batch, is_incremental=False)
                if success:
                    self._imported_count += len(batch)
                    self._last_entity_id = batch[-1].entity_id
                else:
                    self._failed_count += len(batch)
                    self._failed_entity_ids.extend(e.entity_id for e in batch)
                    self._dead_letter_queue.append(batch)
                batch = []

        # Process remaining entities
        if batch:
            success = await self._import_batch(batch, is_incremental=False)
            if success:
                self._imported_count += len(batch)
                self._last_entity_id = batch[-1].entity_id
            else:
                self._failed_count += len(batch)
                self._failed_entity_ids.extend(e.entity_id for e in batch)
                self._dead_letter_queue.append(batch)

        duration = time.time() - self._start_time

        # Log final metrics
        metrics = log_import_metrics(
            entities_imported=self._imported_count,
            relationships_created=self._relationship_count,
            failed_batches=self._failed_count,
            duration_seconds=duration,
        )
        self.logger.info("Entity import completed", **metrics)

        return ImportResult(
            imported=self._imported_count,
            failed=self._failed_count,
            relationships_created=self._relationship_count,
            duration_seconds=duration,
            failed_entity_ids=self._failed_entity_ids,
        )

    async def _import_batch(
        self, batch: List[FilteredEntity], is_incremental: bool = False
    ) -> bool:
        """
        Import a batch of entities with retry logic.

        Args:
            batch: List of entities to import
            is_incremental: Whether this is an incremental import

        Returns:
            True if batch imported successfully, False otherwise
        """
        for attempt in range(self.max_retries + 1):
            try:
                await self._execute_batch_import(
                    batch, is_incremental=is_incremental
                )
                return True
            except Exception as e:
                delay = self.retry_delay * (2 ** attempt)
                self.logger.warning(
                    f"Batch import attempt {attempt + 1}/"
                    f"{self.max_retries + 1} failed: {e}",
                    attempt=attempt + 1,
                    max_retries=self.max_retries,
                    retry_delay=delay,
                )
                if attempt < self.max_retries:
                    await asyncio.sleep(delay)
                else:
                    self.logger.error(
                        f"Batch import failed after {self.max_retries + 1} "
                        f"attempts",
                        batch_size=len(batch),
                        first_entity_id=batch[0].entity_id if batch else None,
                    )
                    return False
        return False

    async def _execute_batch_import(
        self, batch: List[FilteredEntity], is_incremental: bool = False
    ) -> None:
        """
        Execute the actual batch import to Neo4j.

        Args:
            batch: List of entities to import
            is_incremental: Whether this is an incremental import
        """
        async with self._neo4j_client.transaction() as tx:
            for entity in batch:
                if is_incremental:
                    # For incremental: MERGE to update or create
                    await self._create_entity_node_tx(tx, entity)
                    # Clear and recreate relationships for updates
                    await self._clear_relationships_tx(tx, entity.entity_id)
                    rel_count = await self._create_relationships_tx(tx, entity)
                    self._relationship_count += rel_count
                else:
                    # For full import: standard behavior
                    await self._create_entity_node_tx(tx, entity)
                    rel_count = await self._create_relationships_tx(tx, entity)
                    self._relationship_count += rel_count

    async def _clear_relationships_tx(self, tx, entity_id: str) -> None:
        """
        Clear all relationships from an entity within a transaction.

        Args:
            tx: Transaction object
            entity_id: Entity ID to clear relationships for
        """
        query = """
        MATCH (e:YagoEntity {entity_id: $entity_id})-[r]->()
        DELETE r
        """
        await tx.run(query, {"entity_id": entity_id})

    async def _create_entity_node_tx(self, tx, entity: FilteredEntity) -> int:
        """
        Create a YagoEntity node within a transaction.

        Args:
            tx: Transaction object
            entity: FilteredEntity to create

        Returns:
            Node ID
        """
        # Use MERGE to prevent duplicates
        query = """
        MERGE (e:YagoEntity {entity_id: $entity_id})
        SET e.label = $label,
            e.description = $description,
            e.data = $data
        RETURN id(e) as node_id
        """

        data_json = json.dumps({
            "entity_id": entity.entity_id,
            "label": entity.label,
            "description": entity.description,
            "instance_of": entity.instance_of,
            "subclass_of": entity.subclass_of,
            "aliases": entity.aliases,
            "see_also": entity.see_also,
        })

        result = await tx.run(
            query,
            {
                "entity_id": entity.entity_id,
                "label": entity.label or "",
                "description": entity.description or "",
                "data": data_json,
            },
        )
        record = await result.single()
        return record["node_id"] if record else -1

    async def _create_relationships_tx(
        self, tx, entity: FilteredEntity
    ) -> int:
        """
        Create relationships for an entity within a transaction.

        Args:
            tx: Transaction object
            entity: FilteredEntity to create relationships for

        Returns:
            Number of relationships created
        """
        rel_count = 0

        # Create INSTANCE_OF relationships
        for target_id in entity.instance_of:
            if target_id:
                await self._create_relationship_tx(
                    tx, entity.entity_id, target_id, self.REL_INSTANCE_OF
                )
                rel_count += 1

        # Create SUBCLASS_OF relationships
        for target_id in entity.subclass_of:
            if target_id:
                await self._create_relationship_tx(
                    tx, entity.entity_id, target_id, self.REL_SUBCLASS_OF
                )
                rel_count += 1

        # Create ALIAS_OF relationships (for alias labels)
        for alias in entity.aliases:
            if alias:
                await self._create_alias_relationship_tx(
                    tx, entity.entity_id, alias
                )
                rel_count += 1

        # Create SEE_ALSO relationships
        for target_id in entity.see_also:
            if target_id:
                await self._create_relationship_tx(
                    tx, entity.entity_id, target_id, self.REL_SEE_ALSO
                )
                rel_count += 1

        return rel_count

    async def _create_relationship_tx(
        self, tx, entity_id: str, target_id: str, rel_type: str
    ) -> None:
        """
        Create a relationship between two YagoEntity nodes.

        Args:
            tx: Transaction object
            entity_id: Source entity ID
            target_id: Target entity ID
            rel_type: Relationship type (INSTANCE_OF, SUBCLASS_OF, SEE_ALSO)
        """
        query = """
        MATCH (e:YagoEntity {entity_id: $entity_id})
        MATCH (t:YagoEntity {entity_id: $target_id})
        MERGE (e)-[:INSTANCE_OF | SUBCLASS_OF | SEE_ALSO *0..1]->(t)
        """

        # Use dynamic relationship type
        if rel_type == self.REL_INSTANCE_OF:
            query = """
            MATCH (e:YagoEntity {entity_id: $entity_id})
            MATCH (t:YagoEntity {entity_id: $target_id})
            MERGE (e)-[:INSTANCE_OF]->(t)
            """
        elif rel_type == self.REL_SUBCLASS_OF:
            query = """
            MATCH (e:YagoEntity {entity_id: $entity_id})
            MATCH (t:YagoEntity {entity_id: $target_id})
            MERGE (e)-[:SUBCLASS_OF]->(t)
            """
        elif rel_type == self.REL_SEE_ALSO:
            query = """
            MATCH (e:YagoEntity {entity_id: $entity_id})
            MATCH (t:YagoEntity {entity_id: $target_id})
            MERGE (e)-[:SEE_ALSO]->(t)
            """

        await tx.run(query, {"entity_id": entity_id, "target_id": target_id})

    async def _create_alias_relationship_tx(
        self, tx, entity_id: str, alias: str
    ) -> None:
        """
        Create an ALIAS_OF relationship for an alias label.

        Args:
            tx: Transaction object
            entity_id: Source entity ID
            alias: Alias label
        """
        query = """
        MATCH (e:YagoEntity {entity_id: $entity_id})
        MERGE (a:Alias {label: $alias})
        MERGE (e)-[:ALIAS_OF]->(a)
        """
        await tx.run(query, {"entity_id": entity_id, "alias": alias})

    async def create_entity_node(self, entity: FilteredEntity) -> int:
        """
        Create a YagoEntity node for a single entity.

        Args:
            entity: FilteredEntity to create

        Returns:
            Node ID

        Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.1.1, 4.1.2, 4.1.3, 4.1.6, 4.1.7, 4.1.8
        """
        query = """
        MERGE (e:YagoEntity {entity_id: $entity_id})
        SET e.label = $label,
            e.description = $description,
            e.data = $data
        RETURN id(e) as node_id
        """

        data_json = json.dumps({
            "entity_id": entity.entity_id,
            "label": entity.label,
            "description": entity.description,
            "instance_of": entity.instance_of,
            "subclass_of": entity.subclass_of,
            "aliases": entity.aliases,
            "see_also": entity.see_also,
        })

        result = await self._neo4j_client.execute_write_query(
            query,
            {
                "entity_id": entity.entity_id,
                "label": entity.label or "",
                "description": entity.description or "",
                "data": data_json,
            },
        )

        if result and len(result) > 0:
            node_id = result[0]["node_id"]
            self.logger.debug(
                f"Created YagoEntity node",
                entity_id=entity.entity_id,
                node_id=node_id,
            )
            return node_id

        return -1

    async def create_relationships(
        self,
        entity_id: str,
        relationships: List[Dict[str, Any]],
    ) -> int:
        """
        Create relationships from an entity to target entities.

        Args:
            entity_id: Source entity ID
            relationships: List of relationship dicts with 'target_id' and 'type'

        Returns:
            Number of relationships created

        Validates: Requirements 4.3, 4.4, 4.1.4, 4.1.5
        """
        rel_count = 0

        for rel in relationships:
            target_id = rel.get("target_id")
            rel_type = rel.get("type", "INSTANCE_OF")

            # For ALIAS_OF, we need a label even if target_id is empty
            if rel_type == self.REL_ALIAS_OF:
                alias = rel.get("label", "")
                if alias:
                    await self._create_alias_relationship(
                        entity_id, alias
                    )
                    rel_count += 1
                continue

            if not target_id:
                continue

            # Map relationship type to Neo4j relationship type
            if rel_type == "INSTANCE_OF":
                neo4j_rel = self.REL_INSTANCE_OF
            elif rel_type == "SUBCLASS_OF":
                neo4j_rel = self.REL_SUBCLASS_OF
            elif rel_type == "SEE_ALSO":
                neo4j_rel = self.REL_SEE_ALSO
            else:
                neo4j_rel = rel_type

            await self._create_relationship(
                entity_id, target_id, neo4j_rel
            )
            rel_count += 1

        self.logger.debug(
            f"Created {rel_count} relationships",
            entity_id=entity_id,
            relationship_count=rel_count,
        )

        return rel_count

    async def _create_relationship(
        self, entity_id: str, target_id: str, rel_type: str
    ) -> None:
        """
        Create a single relationship between entities.

        Args:
            entity_id: Source entity ID
            target_id: Target entity ID
            rel_type: Relationship type
        """
        if rel_type == self.REL_INSTANCE_OF:
            query = """
            MATCH (e:YagoEntity {entity_id: $entity_id})
            MATCH (t:YagoEntity {entity_id: $target_id})
            MERGE (e)-[:INSTANCE_OF]->(t)
            """
        elif rel_type == self.REL_SUBCLASS_OF:
            query = """
            MATCH (e:YagoEntity {entity_id: $entity_id})
            MATCH (t:YagoEntity {entity_id: $target_id})
            MERGE (e)-[:SUBCLASS_OF]->(t)
            """
        elif rel_type == self.REL_SEE_ALSO:
            query = """
            MATCH (e:YagoEntity {entity_id: $entity_id})
            MATCH (t:YagoEntity {entity_id: $target_id})
            MERGE (e)-[:SEE_ALSO]->(t)
            """
        else:
            query = f"""
            MATCH (e:YagoEntity {{entity_id: $entity_id}})
            MATCH (t:YagoEntity {{entity_id: $target_id}})
            MERGE (e)-[:{rel_type}]->(t)
            """

        await self._neo4j_client.execute_write_query(
            query, {"entity_id": entity_id, "target_id": target_id}
        )

    async def _create_alias_relationship(
        self, entity_id: str, alias: str
    ) -> None:
        """
        Create an ALIAS_OF relationship for an alias label.

        Args:
            entity_id: Source entity ID
            alias: Alias label
        """
        query = """
        MATCH (e:YagoEntity {entity_id: $entity_id})
        MERGE (a:Alias {label: $alias})
        MERGE (e)-[:ALIAS_OF]->(a)
        """
        await self._neo4j_client.execute_write_query(
            query, {"entity_id": entity_id, "alias": alias}
        )

    def get_progress(self) -> Dict[str, Any]:
        """
        Get import progress as a percentage.

        Returns:
            Dictionary with progress information including:
            - percentage: Progress as a percentage (0-100)
            - imported: Number of imported entities
            - failed: Number of failed entities
            - total: Total entities (if known)
            - last_entity_id: Last successfully imported entity ID

        Validates: Requirements 11.3, 11.4, 11.5
        """
        percentage = 0.0

        if self._total_entities and self._total_entities > 0:
            total_processed = self._imported_count + self._failed_count
            percentage = round(
                total_processed / self._total_entities * 100, 2
            )
        elif self._start_time is not None:
            # Estimate based on time if total unknown
            elapsed = time.time() - self._start_time
            if elapsed > 0 and self._imported_count > 0:
                rate = self._imported_count / elapsed
                # Estimate remaining time if we have a rate
                percentage = None  # Cannot calculate without total

        return {
            "percentage": percentage,
            "imported": self._imported_count,
            "failed": self._failed_count,
            "total": self._total_entities,
            "last_entity_id": self._last_entity_id,
            "relationships_created": self._relationship_count,
        }

    def set_checkpoint(self, entity_id: str) -> None:
        """
        Set a checkpoint for resuming import.

        Args:
            entity_id: Entity ID to resume from (next entity after this will be processed)

        Validates: Requirements 11.4
        """
        self._checkpoint_entity_id = entity_id
        self._checkpoint_imported_count = self._imported_count
        self.logger.info(f"Checkpoint set at entity_id: {entity_id}")

    def get_checkpoint(self) -> Optional[Dict[str, Any]]:
        """
        Get the current checkpoint information.

        Returns:
            Checkpoint info or None if no checkpoint set
        """
        if self._checkpoint_entity_id is None:
            return None

        return {
            "entity_id": self._checkpoint_entity_id,
            "imported_count": self._checkpoint_imported_count,
        }

    async def get_stats(self) -> YagoStats:
        """
        Get statistics about YAGO data in Neo4j.

        Returns:
            YagoStats with entity and relationship counts

        Validates: Requirements 9.1, 9.4
        """
        # Count entities
        entity_query = "MATCH (e:YagoEntity) RETURN count(e) as count"
        entity_result = await self._neo4j_client.execute_query(entity_query)
        entity_count = entity_result[0]["count"] if entity_result else 0

        # Count relationships
        rel_query = "MATCH ()-[r:INSTANCE_OF | SUBCLASS_OF | ALIAS_OF | SEE_ALSO]->() RETURN count(r) as count"
        rel_result = await self._neo4j_client.execute_query(rel_query)
        relationship_count = rel_result[0]["count"] if rel_result else 0

        # Count by type
        instance_query = "MATCH ()-[r:INSTANCE_OF]->() RETURN count(r) as count"
        instance_result = await self._neo4j_client.execute_query(instance_query)
        instance_of_count = instance_result[0]["count"] if instance_result else 0

        subclass_query = "MATCH ()-[r:SUBCLASS_OF]->() RETURN count(r) as count"
        subclass_result = await self._neo4j_client.execute_query(subclass_query)
        subclass_of_count = subclass_result[0]["count"] if subclass_result else 0

        alias_query = "MATCH ()-[r:ALIAS_OF]->() RETURN count(r) as count"
        alias_result = await self._neo4j_client.execute_query(alias_query)
        alias_of_count = alias_result[0]["count"] if alias_result else 0

        see_also_query = "MATCH ()-[r:SEE_ALSO]->() RETURN count(r) as count"
        see_also_result = await self._neo4j_client.execute_query(see_also_query)
        see_also_count = see_also_result[0]["count"] if see_also_result else 0

        # Estimate storage (rough calculation)
        storage_bytes = (
            entity_count * 200  # ~200 bytes per node
            + relationship_count * 100  # ~100 bytes per relationship
        )

        return YagoStats(
            entity_count=entity_count,
            relationship_count=relationship_count,
            instance_of_count=instance_of_count,
            subclass_of_count=subclass_of_count,
            alias_of_count=alias_of_count,
            see_also_count=see_also_count,
            storage_bytes=storage_bytes,
        )

    async def clear_all(self) -> None:
        """
        Remove all YAGO data from Neo4j.

        This removes all YagoEntity nodes, Alias nodes, and relationships.

        Validates: Requirements 9.3
        """
        self.logger.warning("Clearing all YAGO data from Neo4j")

        # Delete all YagoEntity nodes and their relationships
        delete_query = """
        MATCH (e:YagoEntity)
        DETACH DELETE e
        """
        await self._neo4j_client.execute_write_query(delete_query)

        # Delete all Alias nodes (orphaned)
        delete_alias_query = """
        MATCH (a:Alias)
        WHERE NOT (a)<-[:ALIAS_OF]-()
        DELETE a
        """
        await self._neo4j_client.execute_write_query(delete_alias_query)

        # Reset stats
        self._imported_count = 0
        self._relationship_count = 0
        self._failed_count = 0
        self._last_entity_id = None

        self.logger.info("All YAGO data cleared from Neo4j")

    def estimate_storage(
        self, entity_count: int, avg_relationships: float = 2.5
    ) -> Dict[str, Any]:
        """
        Estimate storage requirements before import.

        Args:
            entity_count: Number of entities to import
            avg_relationships: Average relationships per entity

        Returns:
            Dictionary with storage estimates

        Validates: Requirements 9.1
        """
        relationship_count = int(entity_count * avg_relationships)

        # Estimate based on typical YAGO entity size
        node_bytes = entity_count * 200  # ~200 bytes per node
        rel_bytes = relationship_count * 100  # ~100 bytes per relationship
        property_bytes = entity_count * 500  # ~500 bytes for properties

        total_bytes = node_bytes + rel_bytes + property_bytes

        return {
            "estimated_entities": entity_count,
            "estimated_relationships": relationship_count,
            "estimated_node_bytes": node_bytes,
            "estimated_relationship_bytes": rel_bytes,
            "estimated_property_bytes": property_bytes,
            "estimated_total_bytes": total_bytes,
            "estimated_total_mb": round(total_bytes / (1024 * 1024), 2),
        }

    def get_dead_letter_queue(self) -> DeadLetterQueue:
        """
        Get the dead letter queue for failed batches.

        Returns:
            DeadLetterQueue instance
        """
        return self._dead_letter_queue

    async def retry_failed_batches(self) -> ImportResult:
        """
        Retry entities from the dead letter queue.

        Returns:
            ImportResult for the retry operation
        """
        failed_entities = self._dead_letter_queue.get_all()

        if not failed_entities:
            self.logger.info("No failed batches to retry")
            return ImportResult()

        self.logger.info(
            f"Retrying {len(failed_entities)} failed entities",
            failed_count=len(failed_entities),
        )

        # Create async iterator from list
        async def entity_iterator():
            for entity in failed_entities:
                yield entity

        return await self.import_entities(entity_iterator())

    async def ensure_indexes(self) -> None:
        """
        Ensure required indexes exist for YAGO data.

        Creates indexes on entity_id for fast lookups and label for search.
        """
        index_statements = [
            # Index on entity_id for fast lookups
            "CREATE INDEX yago_entity_id_index IF NOT EXISTS "
            "FOR (e:YagoEntity) ON (e.entity_id)",
            # Index on label for search
            "CREATE INDEX yago_entity_label_index IF NOT EXISTS "
            "FOR (e:YagoEntity) ON (e.label)",
            # Index on Alias label
            "CREATE INDEX alias_label_index IF NOT EXISTS "
            "FOR (a:Alias) ON (a.label)",
        ]

        try:
            async with self._neo4j_client.driver.session(
                database=self._neo4j_client.database
            ) as session:
                for statement in index_statements:
                    try:
                        await session.run(statement)
                    except Exception as e:
                        # Index may already exist - log warning but continue
                        self.logger.warning(f"Index creation warning: {e}")

            self.logger.info("YAGO indexes ensured")
        except Exception as e:
            self.logger.error(f"Failed to ensure indexes: {e}")

    # ========== Incremental Update Methods ==========

    async def update_entity(self, entity: FilteredEntity) -> bool:
        """
        Update an existing YagoEntity node.

        This method uses MERGE to update existing entities or create new ones
        if they don't exist. It updates all properties and relationships.

        Args:
            entity: FilteredEntity with updated data

        Returns:
            True if entity was updated/created successfully

        Validates: Requirement 8.2
        """
        try:
            # Update entity node
            await self.create_entity_node(entity)

            # Clear old relationships and recreate them
            await self._clear_entity_relationships(entity.entity_id)

            # Create new relationships
            await self.create_relationships(
                entity.entity_id,
                [
                    {"target_id": tid, "type": "INSTANCE_OF"}
                    for tid in entity.instance_of
                ],
            )
            await self.create_relationships(
                entity.entity_id,
                [
                    {"target_id": tid, "type": "SUBCLASS_OF"}
                    for tid in entity.subclass_of
                ],
            )
            await self.create_relationships(
                entity.entity_id,
                [
                    {"target_id": tid, "type": "SEE_ALSO"}
                    for tid in entity.see_also
                ],
            )
            await self.create_relationships(
                entity.entity_id,
                [
                    {"type": "ALIAS_OF", "label": alias}
                    for alias in entity.aliases
                ],
            )

            self.logger.debug(
                f"Updated YagoEntity",
                entity_id=entity.entity_id,
            )
            return True

        except Exception as e:
            self.logger.error(
                f"Failed to update entity: {e}",
                entity_id=entity.entity_id,
            )
            return False

    async def _clear_entity_relationships(self, entity_id: str) -> int:
        """
        Clear all relationships from an entity.

        Args:
            entity_id: Entity ID to clear relationships for

        Returns:
            Number of relationships deleted
        """
        query = """
        MATCH (e:YagoEntity {entity_id: $entity_id})-[r]->()
        DELETE r
        """
        result = await self._neo4j_client.execute_write_query(
            query, {"entity_id": entity_id}
        )
        # Count deleted relationships
        count = 0
        if result:
            for record in result:
                count += 1
        return count

    async def delete_entity(self, entity_id: str) -> bool:
        """
        Delete a YagoEntity node and all its relationships.

        Args:
            entity_id: Entity ID to delete

        Returns:
            True if entity was deleted successfully

        Validates: Requirement 8.3
        """
        try:
            query = """
            MATCH (e:YagoEntity {entity_id: $entity_id})
            DETACH DELETE e
            """
            await self._neo4j_client.execute_write_query(
                query, {"entity_id": entity_id}
            )

            self.logger.info(
                f"Deleted YagoEntity",
                entity_id=entity_id,
            )
            return True

        except Exception as e:
            self.logger.error(
                f"Failed to delete entity: {e}",
                entity_id=entity_id,
            )
            return False

    async def mark_entity_deleted(
        self, entity_id: str, deleted_timestamp: datetime | None = None
    ) -> bool:
        """
        Soft-delete an entity by marking it with a deleted flag.

        This preserves the entity node but marks it as deleted, allowing
        for audit trails and potential restoration.

        Args:
            entity_id: Entity ID to soft-delete
            deleted_timestamp: When the deletion occurred (defaults to now)

        Returns:
            True if entity was marked successfully
        """
        try:
            timestamp = deleted_timestamp or datetime.utcnow()

            query = """
            MATCH (e:YagoEntity {entity_id: $entity_id})
            SET e.is_deleted = true,
                e.deleted_at = $deleted_at
            """
            await self._neo4j_client.execute_write_query(
                query,
                {
                    "entity_id": entity_id,
                    "deleted_at": timestamp.isoformat(),
                },
            )

            self.logger.info(
                f"Soft-deleted YagoEntity",
                entity_id=entity_id,
                deleted_at=timestamp.isoformat(),
            )
            return True

        except Exception as e:
            self.logger.error(
                f"Failed to soft-delete entity: {e}",
                entity_id=entity_id,
            )
            return False

    async def get_all_entity_ids(self) -> Set[str]:
        """
        Get all entity IDs currently in the database.

        Returns:
            Set of all entity IDs
        """
        query = "MATCH (e:YagoEntity) RETURN e.entity_id as entity_id"
        result = await self._neo4j_client.execute_query(query)

        entity_ids: set[str] = set()
        if result:
            for record in result:
                entity_id = record.get("entity_id")
                if entity_id:
                    entity_ids.add(entity_id)

        return entity_ids

    async def delete_entities_not_in(
        self, valid_entity_ids: Set[str]
    ) -> int:
        """
        Delete entities that are not in the provided set.

        This is used during incremental updates to remove entities
        that no longer exist in the dump.

        Args:
            valid_entity_ids: Set of entity IDs that should remain

        Returns:
            Number of entities deleted

        Validates: Requirement 8.3
        """
        if not valid_entity_ids:
            # If no valid IDs provided, delete all non-deleted entities
            query = """
            MATCH (e:YagoEntity)
            WHERE e.is_deleted IS NULL OR e.is_deleted = false
            WITH e
            LIMIT 10000
            DETACH DELETE e
            RETURN count(e) as deleted_count
            """
            result = await self._neo4j_client.execute_write_query(query)
        else:
            # Delete entities not in the valid set
            query = """
            MATCH (e:YagoEntity)
            WHERE e.entity_id NOT IN $valid_ids
            AND (e.is_deleted IS NULL OR e.is_deleted = false)
            DETACH DELETE e
            RETURN count(e) as deleted_count
            """
            result = await self._neo4j_client.execute_write_query(
                query, {"valid_ids": list(valid_entity_ids)}
            )

        if result and result[0]:
            deleted_count = result[0].get("deleted_count", 0)
            self.logger.info(
                f"Deleted {deleted_count} entities not in incremental dump"
            )
            return deleted_count

        return 0

    async def import_incremental(
        self,
        entities: any,
        valid_entity_ids: Set[str],
        total_entities: int | None = None,
    ) -> ImportResult:
        """
        Import entities from an incremental dump with update and delete logic.

        This method:
        1. Updates or creates entities from the incremental dump
        2. Deletes entities not present in the incremental dump
        3. Tracks the last processed timestamp

        Args:
            entities: Async iterator yielding FilteredEntity objects
            valid_entity_ids: Set of entity IDs from the incremental dump
            total_entities: Optional total count for progress tracking

        Returns:
            ImportResult with import statistics

        Validates: Requirements 8.2, 8.3, 8.4
        """
        self._start_time = time.time()
        self._total_entities = total_entities
        self._imported_count = 0
        self._relationship_count = 0
        self._failed_count = 0
        self._entities_in_incremental = valid_entity_ids

        self.logger.info(
            "Starting incremental import",
            batch_size=self.batch_size,
            valid_entity_count=len(valid_entity_ids),
        )

        # Track entities being updated/created
        processed_entity_ids: set[str] = set()

        batch: List[FilteredEntity] = []
        async for entity in entities:
            batch.append(entity)
            processed_entity_ids.add(entity.entity_id)

            if len(batch) >= self.batch_size:
                success = await self._import_batch(batch, is_incremental=True)
                if success:
                    self._imported_count += len(batch)
                    self._last_entity_id = batch[-1].entity_id
                else:
                    self._failed_count += len(batch)
                    self._failed_entity_ids.extend(e.entity_id for e in batch)
                    self._dead_letter_queue.append(batch)
                batch = []

        # Process remaining entities
        if batch:
            success = await self._import_batch(batch, is_incremental=True)
            if success:
                self._imported_count += len(batch)
                self._last_entity_id = batch[-1].entity_id
            else:
                self._failed_count += len(batch)
                self._failed_entity_ids.extend(e.entity_id for e in batch)
                self._dead_letter_queue.append(batch)

        # Delete entities not in incremental dump
        deleted_count = await self.delete_entities_not_in(valid_entity_ids)

        # Update timestamp tracking
        self._last_processed_timestamp = datetime.utcnow()
        self._save_incremental_checkpoint()

        duration = time.time() - self._start_time

        # Log final metrics
        metrics = log_import_metrics(
            entities_imported=self._imported_count,
            relationships_created=self._relationship_count,
            failed_batches=self._failed_count,
            duration_seconds=duration,
        )
        self.logger.info(
            "Incremental import completed",
            **metrics,
            entities_deleted=deleted_count,
        )

        return ImportResult(
            imported=self._imported_count,
            failed=self._failed_count,
            relationships_created=self._relationship_count,
            duration_seconds=duration,
            failed_entity_ids=self._failed_entity_ids,
        )

    def _save_incremental_checkpoint(self) -> None:
        """Save checkpoint with timestamp for incremental updates."""
        checkpoint_data = {
            "last_entity_id": self._last_entity_id,
            "last_processed_timestamp": self._last_processed_timestamp.isoformat()
            if self._last_processed_timestamp
            else None,
            "processed_count": self._imported_count,
        }
        try:
            with open(self._checkpoint_file, "w") as f:
                json.dump(checkpoint_data, f, indent=2)
            self.logger.debug(
                "Incremental checkpoint saved",
                last_entity_id=self._last_entity_id,
            )
        except IOError as e:
            self.logger.warning(f"Failed to save checkpoint: {e}")

    def get_incremental_checkpoint(self) -> dict | None:
        """
        Get the current incremental checkpoint information.

        Returns:
            Checkpoint data dict or None if no checkpoint exists
        """
        if not self._checkpoint_file.exists():
            return None

        try:
            with open(self._checkpoint_file, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None

    @property
    def last_processed_timestamp(self) -> Optional[datetime]:
        """Get the last processed timestamp for incremental updates."""
        return self._last_processed_timestamp