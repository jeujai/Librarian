"""
Tests for ConceptNet API Client.

This module tests the local ConceptNet client for knowledge graph enrichment:
- ConceptNetClient queries ConceptNet data from local Neo4j

Note: WikidataClient was removed in favor of YAGO local data (YagoLocalClient).
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.multimodal_librarian.clients.conceptnet_client import ConceptNetClient
from src.multimodal_librarian.models.enrichment import ConceptNetRelation

# =============================================================================
# Test ConceptNetClient
# =============================================================================


class TestConceptNetClient:
    """Test ConceptNetClient functionality."""

    @pytest.fixture
    def mock_neo4j(self):
        """Create a mock Neo4j client."""
        client = MagicMock()
        client.execute_query = AsyncMock(return_value=[])
        client.connect = AsyncMock()
        return client

    @pytest.fixture
    def client(self, mock_neo4j):
        """Create a ConceptNetClient with mock Neo4j."""
        return ConceptNetClient(neo4j_client=mock_neo4j)

    def test_client_initialization(self, client):
        """Test client initialization."""
        assert client._neo4j is not None
        assert client._neo4j_initialized is True

    def test_client_initialization_without_neo4j(self):
        """Test client initialization without Neo4j client."""
        client = ConceptNetClient()
        assert client._neo4j is None
        assert client._neo4j_initialized is False

    def test_supported_relations(self, client):
        """Test supported relation types."""
        expected = [
            "IsA", "PartOf", "UsedFor", "CapableOf", "HasProperty",
            "AtLocation", "Causes", "HasPrerequisite", "MotivatedByGoal",
            "RelatedTo", "Synonym", "Antonym", "DerivedFrom", "DefinedAs"
        ]
        for rel in expected:
            assert rel in client.SUPPORTED_RELATIONS

    @pytest.mark.asyncio
    async def test_get_relationships_returns_relations(self, client, mock_neo4j):
        """Test get_relationships returns parsed relations."""
        mock_neo4j.execute_query = AsyncMock(return_value=[
            {
                "subject": "writer",
                "relation": "IsA",
                "object": "person",
                "weight": 0.8,
                "source_uri": "/a/test",
            }
        ])

        result = await client.get_relationships("writer")

        assert len(result) == 1
        assert result[0].relation == "IsA"
        assert result[0].subject == "writer"
        assert result[0].object == "person"
        assert result[0].weight == 0.8

    @pytest.mark.asyncio
    async def test_get_relationships_empty_when_no_neo4j(self):
        """Test get_relationships returns empty when Neo4j unavailable."""
        client = ConceptNetClient(neo4j_client=None)
        # Patch lazy init to also fail
        client._neo4j_initialized = True

        result = await client.get_relationships("test")
        assert result == []

    @pytest.mark.asyncio
    async def test_get_relationships_handles_errors(self, client, mock_neo4j):
        """Test get_relationships handles query errors gracefully."""
        mock_neo4j.execute_query = AsyncMock(side_effect=Exception("DB error"))

        result = await client.get_relationships("test")
        assert result == []

    @pytest.mark.asyncio
    async def test_get_relationship_by_type_unsupported(self, client):
        """Test get_relationship_by_type with unsupported type."""
        result = await client.get_relationship_by_type("test", "UnsupportedType")
        assert result == []

    @pytest.mark.asyncio
    async def test_get_relationship_by_type_supported(self, client, mock_neo4j):
        """Test get_relationship_by_type with supported type."""
        mock_neo4j.execute_query = AsyncMock(return_value=[
            {
                "subject": "writer",
                "relation": "IsA",
                "object": "person",
                "weight": 0.9,
                "source_uri": "/a/test",
            }
        ])

        result = await client.get_relationship_by_type("writer", "IsA")

        assert len(result) == 1
        assert result[0].relation == "IsA"

    @pytest.mark.asyncio
    async def test_batch_get_relationships(self, client, mock_neo4j):
        """Test batch_get_relationships for multiple concepts."""
        mock_neo4j.execute_query = AsyncMock(return_value=[
            {
                "subject": "writer",
                "relation": "IsA",
                "object": "person",
                "weight": 0.8,
                "source_uri": "/a/test1",
            },
            {
                "subject": "dog",
                "relation": "IsA",
                "object": "animal",
                "weight": 0.9,
                "source_uri": "/a/test2",
            },
        ])

        result = await client.batch_get_relationships(["writer", "dog"])

        assert "writer" in result
        assert "dog" in result

    @pytest.mark.asyncio
    async def test_batch_get_relationships_empty_input(self, client):
        """Test batch_get_relationships with empty list."""
        result = await client.batch_get_relationships([])
        assert result == {}

    @pytest.mark.asyncio
    async def test_batch_get_relationships_handles_errors(self, client, mock_neo4j):
        """Test batch_get_relationships handles errors gracefully."""
        mock_neo4j.execute_query = AsyncMock(side_effect=Exception("DB error"))

        result = await client.batch_get_relationships(["writer"])
        assert result == {"writer": []}


# =============================================================================
# Test Client Integration
# =============================================================================


class TestClientIntegration:
    """Integration tests for API clients."""

    @pytest.fixture
    def conceptnet_client(self):
        """Create ConceptNetClient."""
        return ConceptNetClient()

    def test_conceptnet_client_lazy_init(self, conceptnet_client):
        """Test ConceptNetClient supports lazy initialization."""
        assert conceptnet_client._neo4j is None
        assert conceptnet_client._neo4j_initialized is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
