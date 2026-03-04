"""Unit tests for YagoNeo4jLoader."""

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from multimodal_librarian.components.yago.loader import (
    DeadLetterQueue,
    ImportResult,
    YagoNeo4jLoader,
    YagoStats,
)
from multimodal_librarian.components.yago.models import FilteredEntity


class TestDeadLetterQueue:
    """Tests for DeadLetterQueue."""

    def test_append_and_get_all(self):
        """Test appending batches and retrieving them."""
        queue = DeadLetterQueue(max_size=100)

        batch1 = [
            FilteredEntity(
                entity_id="Q1",
                label="Test1",
                description="Desc1",
                instance_of=[],
                subclass_of=[],
                aliases=[],
                see_also=[],
            )
        ]
        batch2 = [
            FilteredEntity(
                entity_id="Q2",
                label="Test2",
                description="Desc2",
                instance_of=[],
                subclass_of=[],
                aliases=[],
                see_also=[],
            )
        ]

        queue.append(batch1)
        queue.append(batch2)

        all_items = queue.get_all()
        assert len(all_items) == 2
        assert all_items[0].entity_id == "Q1"
        assert all_items[1].entity_id == "Q2"
        assert queue.is_empty()

    def test_max_size_enforcement(self):
        """Test that max size is enforced."""
        queue = DeadLetterQueue(max_size=2)

        for i in range(5):
            batch = [
                FilteredEntity(
                    entity_id=f"Q{i}",
                    label=f"Test{i}",
                    description=f"Desc{i}",
                    instance_of=[],
                    subclass_of=[],
                    aliases=[],
                    see_also=[],
                )
            ]
            queue.append(batch)

        all_items = queue.get_all()
        assert len(all_items) == 2
        # Should have the last 2 items
        assert all_items[0].entity_id == "Q3"
        assert all_items[1].entity_id == "Q4"

    def test_length(self):
        """Test __len__ method."""
        queue = DeadLetterQueue()

        assert len(queue) == 0

        batch = [
            FilteredEntity(
                entity_id="Q1",
                label="Test",
                description="Desc",
                instance_of=[],
                subclass_of=[],
                aliases=[],
                see_also=[],
            )
        ]
        queue.append(batch)
        assert len(queue) == 1


class TestYagoNeo4jLoader:
    """Tests for YagoNeo4jLoader."""

    @pytest.fixture
    def mock_neo4j_client(self):
        """Create a mock Neo4j client."""
        client = MagicMock()
        client.execute_query = AsyncMock(return_value=[])
        client.execute_write_query = AsyncMock(return_value=[])
        client.transaction = MagicMock()
        return client

    @pytest.fixture
    def loader(self, mock_neo4j_client):
        """Create a loader with mock client."""
        return YagoNeo4jLoader(
            neo4j_client=mock_neo4j_client,
            batch_size=10,
            max_retries=2,
            retry_delay=1,
        )

    def test_initialization(self, loader):
        """Test loader initialization."""
        assert loader.batch_size == 10
        assert loader.max_retries == 2
        assert loader.retry_delay == 1
        assert loader.imported_count == 0
        assert loader.relationship_count == 0
        assert loader.failed_count == 0

    @pytest.mark.asyncio
    async def test_create_entity_node(self, loader, mock_neo4j_client):
        """Test creating a single entity node."""
        mock_neo4j_client.execute_write_query.return_value = [
            {"node_id": 123}
        ]

        entity = FilteredEntity(
            entity_id="Q42",
            label="Douglas Adams",
            description="English writer",
            instance_of=["Q5"],
            subclass_of=[],
            aliases=["Douglas Noël Adams"],
            see_also=[],
        )

        node_id = await loader.create_entity_node(entity)

        assert node_id == 123
        mock_neo4j_client.execute_write_query.assert_called_once()
        call_args = mock_neo4j_client.execute_write_query.call_args
        assert call_args[0][1]["entity_id"] == "Q42"
        assert call_args[0][1]["label"] == "Douglas Adams"

    @pytest.mark.asyncio
    async def test_create_relationships(self, loader, mock_neo4j_client):
        """Test creating relationships."""
        mock_neo4j_client.execute_write_query = AsyncMock(return_value=[])

        relationships = [
            {"target_id": "Q5", "type": "INSTANCE_OF"},
            {"target_id": "Q366", "type": "SUBCLASS_OF"},
        ]

        rel_count = await loader.create_relationships("Q42", relationships)

        assert rel_count == 2
        assert mock_neo4j_client.execute_write_query.call_count == 2

    @pytest.mark.asyncio
    async def test_create_alias_relationship(self, loader, mock_neo4j_client):
        """Test creating ALIAS_OF relationship."""
        mock_neo4j_client.execute_write_query = AsyncMock(return_value=[])

        relationships = [
            {"target_id": "", "type": "ALIAS_OF", "label": "Douglas Adams"},
        ]

        rel_count = await loader.create_relationships("Q42", relationships)

        # ALIAS_OF with empty target_id but with label should still create relationship
        assert rel_count == 1
        call_args = mock_neo4j_client.execute_write_query.call_args
        assert call_args[0][1]["alias"] == "Douglas Adams"

    @pytest.mark.asyncio
    async def test_get_stats(self, loader, mock_neo4j_client):
        """Test getting statistics."""
        mock_neo4j_client.execute_query = AsyncMock(
            side_effect=[
                [{"count": 100}],  # entities
                [{"count": 250}],  # relationships
                [{"count": 150}],  # INSTANCE_OF
                [{"count": 50}],   # SUBCLASS_OF
                [{"count": 30}],   # ALIAS_OF
                [{"count": 20}],   # SEE_ALSO
            ]
        )

        stats = await loader.get_stats()

        assert stats.entity_count == 100
        assert stats.relationship_count == 250
        assert stats.instance_of_count == 150
        assert stats.subclass_of_count == 50
        assert stats.alias_of_count == 30
        assert stats.see_also_count == 20
        assert stats.storage_bytes > 0

    @pytest.mark.asyncio
    async def test_clear_all(self, loader, mock_neo4j_client):
        """Test clearing all YAGO data."""
        mock_neo4j_client.execute_write_query = AsyncMock(return_value=[])

        await loader.clear_all()

        # Should call delete for entities and aliases
        assert mock_neo4j_client.execute_write_query.call_count == 2
        assert loader.imported_count == 0
        assert loader.relationship_count == 0

    def test_estimate_storage(self, loader):
        """Test storage estimation."""
        estimate = loader.estimate_storage(1000, avg_relationships=2.0)

        assert estimate["estimated_entities"] == 1000
        assert estimate["estimated_relationships"] == 2000
        assert estimate["estimated_total_mb"] > 0

    def test_get_progress_no_total(self, loader):
        """Test progress without total count."""
        loader._imported_count = 50
        loader._failed_count = 5

        progress = loader.get_progress()

        assert progress["imported"] == 50
        assert progress["failed"] == 5
        assert progress["total"] is None

    def test_get_progress_with_total(self, loader):
        """Test progress with total count."""
        loader._imported_count = 50
        loader._failed_count = 5
        loader._total_entities = 100

        progress = loader.get_progress()

        assert progress["imported"] == 50
        assert progress["failed"] == 5
        assert progress["total"] == 100
        assert progress["percentage"] == 55.0

    def test_checkpoint(self, loader):
        """Test checkpoint setting and retrieval."""
        loader._imported_count = 100

        loader.set_checkpoint("Q50")

        checkpoint = loader.get_checkpoint()
        assert checkpoint is not None
        assert checkpoint["entity_id"] == "Q50"
        assert checkpoint["imported_count"] == 100

    def test_get_checkpoint_none(self, loader):
        """Test getting checkpoint when none set."""
        checkpoint = loader.get_checkpoint()
        assert checkpoint is None

    @pytest.mark.asyncio
    async def test_import_entities_empty(self, loader):
        """Test importing empty entity stream."""
        async def empty_iterator():
            return
            yield  # Make it a generator

        result = await loader.import_entities(empty_iterator())

        assert result.imported == 0
        assert result.failed == 0

    @pytest.mark.asyncio
    async def test_import_entities_single_batch(self, loader, mock_neo4j_client):
        """Test importing entities in a single batch."""
        # Mock transaction context manager
        mock_tx = AsyncMock()
        mock_tx.run = AsyncMock()
        mock_neo4j_client.transaction.return_value.__aenter__ = AsyncMock(
            return_value=mock_tx
        )
        mock_neo4j_client.transaction.return_value.__aexit__ = AsyncMock(
            return_value=None
        )

        entities = [
            FilteredEntity(
                entity_id=f"Q{i}",
                label=f"Entity {i}",
                description=f"Description {i}",
                instance_of=[],
                subclass_of=[],
                aliases=[],
                see_also=[],
            )
            for i in range(5)
        ]

        async def entity_iterator():
            for entity in entities:
                yield entity

        result = await loader.import_entities(entity_iterator())

        assert result.imported == 5
        assert result.failed == 0

    @pytest.mark.asyncio
    async def test_import_entities_with_retry(self, loader, mock_neo4j_client):
        """Test retry logic on batch import failure."""
        # Mock transaction to fail twice then succeed
        call_count = 0
        mock_tx = AsyncMock()
        mock_result = AsyncMock()
        mock_result.single = AsyncMock(return_value={"node_id": 123})

        async def mock_run(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise Exception("Transient error")
            return mock_result

        mock_tx.run = mock_run
        mock_neo4j_client.transaction.return_value.__aenter__ = AsyncMock(
            return_value=mock_tx
        )
        mock_neo4j_client.transaction.return_value.__aexit__ = AsyncMock(
            return_value=None
        )

        entities = [
            FilteredEntity(
                entity_id="Q1",
                label="Test",
                description="Desc",
                instance_of=[],
                subclass_of=[],
                aliases=[],
                see_also=[],
            )
        ]

        async def entity_iterator():
            for entity in entities:
                yield entity

        result = await loader.import_entities(entity_iterator())

        # Should succeed after retries
        assert result.imported == 1
        assert result.failed == 0

    @pytest.mark.asyncio
    async def test_import_entities_all_fail(self, loader, mock_neo4j_client):
        """Test that failed batches go to dead letter queue."""
        mock_tx = AsyncMock()
        mock_tx.run = AsyncMock(side_effect=Exception("Permanent failure"))
        mock_neo4j_client.transaction.return_value.__aenter__ = AsyncMock(
            return_value=mock_tx
        )
        mock_neo4j_client.transaction.return_value.__aexit__ = AsyncMock(
            return_value=None
        )

        entities = [
            FilteredEntity(
                entity_id="Q1",
                label="Test",
                description="Desc",
                instance_of=[],
                subclass_of=[],
                aliases=[],
                see_also=[],
            )
        ]

        async def entity_iterator():
            for entity in entities:
                yield entity

        result = await loader.import_entities(entity_iterator())

        assert result.failed == 1
        assert len(loader.get_dead_letter_queue()) == 1

    @pytest.mark.asyncio
    async def test_retry_failed_batches(self, loader, mock_neo4j_client):
        """Test retrying failed batches from dead letter queue."""
        # First, add some failed entities
        failed_entity = FilteredEntity(
            entity_id="Q1",
            label="Failed",
            description="Desc",
            instance_of=[],
            subclass_of=[],
            aliases=[],
            see_also=[],
        )
        loader._dead_letter_queue.append([failed_entity])

        # Mock transaction for retry
        mock_tx = AsyncMock()
        mock_tx.run = AsyncMock()
        mock_neo4j_client.transaction.return_value.__aenter__ = AsyncMock(
            return_value=mock_tx
        )
        mock_neo4j_client.transaction.return_value.__aexit__ = AsyncMock(
            return_value=None
        )

        result = await loader.retry_failed_batches()

        assert result.imported == 1
        assert len(loader.get_dead_letter_queue()) == 0

    @pytest.mark.asyncio
    async def test_checkpoint_resume(self, loader, mock_neo4j_client):
        """Test resuming from checkpoint."""
        # Set checkpoint
        loader.set_checkpoint("Q5")

        # Mock transaction
        mock_tx = AsyncMock()
        mock_tx.run = AsyncMock()
        mock_neo4j_client.transaction.return_value.__aenter__ = AsyncMock(
            return_value=mock_tx
        )
        mock_neo4j_client.transaction.return_value.__aexit__ = AsyncMock(
            return_value=None
        )

        entities = [
            FilteredEntity(
                entity_id="Q1",
                label="Test1",
                description="Desc1",
                instance_of=[],
                subclass_of=[],
                aliases=[],
                see_also=[],
            ),
            FilteredEntity(
                entity_id="Q5",
                label="Test5",
                description="Desc5",
                instance_of=[],
                subclass_of=[],
                aliases=[],
                see_also=[],
            ),
            FilteredEntity(
                entity_id="Q10",
                label="Test10",
                description="Desc10",
                instance_of=[],
                subclass_of=[],
                aliases=[],
                see_also=[],
            ),
        ]

        async def entity_iterator():
            for entity in entities:
                yield entity

        result = await loader.import_entities(entity_iterator())

        # Should only import Q10 (after checkpoint Q5)
        assert result.imported == 1
        assert result.failed == 0


class TestImportResult:
    """Tests for ImportResult dataclass."""

    def test_default_values(self):
        """Test default values for ImportResult."""
        result = ImportResult()

        assert result.imported == 0
        assert result.failed == 0
        assert result.relationships_created == 0
        assert result.duration_seconds == 0.0
        assert result.failed_entity_ids == []

    def test_with_values(self):
        """Test ImportResult with values."""
        result = ImportResult(
            imported=100,
            failed=5,
            relationships_created=250,
            duration_seconds=10.5,
            failed_entity_ids=["Q1", "Q2"],
        )

        assert result.imported == 100
        assert result.failed == 5
        assert result.relationships_created == 250
        assert result.duration_seconds == 10.5
        assert result.failed_entity_ids == ["Q1", "Q2"]


class TestYagoStats:
    """Tests for YagoStats dataclass."""

    def test_creation(self):
        """Test creating YagoStats."""
        stats = YagoStats(
            entity_count=1000,
            relationship_count=2500,
            instance_of_count=1500,
            subclass_of_count=500,
            alias_of_count=300,
            see_also_count=200,
            storage_bytes=500000,
        )

        assert stats.entity_count == 1000
        assert stats.relationship_count == 2500
        assert stats.storage_bytes == 500000