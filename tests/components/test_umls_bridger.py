"""Unit tests for UMLSBridger SAME_AS edge creation."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from multimodal_librarian.components.knowledge_graph.umls_bridger import (
    BridgeResult,
    UMLSBridger,
)


@pytest.fixture
def mock_neo4j():
    """Create a mock Neo4j client."""
    mock = MagicMock()
    mock.execute_query = AsyncMock(return_value=[])
    mock.execute_write_query = AsyncMock(return_value=[{"cnt": 0}])
    return mock


@pytest.fixture
def bridger(mock_neo4j):
    """Create a UMLSBridger with mock Neo4j client."""
    return UMLSBridger(mock_neo4j)


class TestCaseInsensitiveMatching:
    """Tests for case-insensitive name matching."""

    @pytest.mark.asyncio
    async def test_preferred_name_case_insensitive(
        self, bridger, mock_neo4j
    ):
        """'Diabetes' concept matches 'diabetes' UMLSConcept preferred_name."""
        mock_neo4j.execute_query = AsyncMock(
            side_effect=[
                # _fetch_concept_names: Concept nodes
                [{"name": "Diabetes"}],
                # _match_concepts_batch: preferred_name query
                [{"name": "diabetes", "cui": "C0011849"}],
                # _match_concepts_batch: synonym query
                [],
            ]
        )
        mock_neo4j.execute_write_query = AsyncMock(
            return_value=[{"cnt": 1}]
        )

        result = await bridger.create_same_as_edges()

        assert result.concepts_matched == 1
        assert result.same_as_edges_created == 1
        assert result.unmatched_concepts == 0

        # Verify the MERGE query was called with correct match data
        write_calls = mock_neo4j.execute_write_query.call_args_list
        assert len(write_calls) == 1
        items = write_calls[0][0][1]["items"]
        assert len(items) == 1
        assert items[0]["concept_name"] == "Diabetes"
        assert items[0]["cui"] == "C0011849"
        assert items[0]["match_type"] == "preferred_name"


class TestSynonymMatching:
    """Tests for synonym matching."""

    @pytest.mark.asyncio
    async def test_concept_matches_synonym_entry(
        self, bridger, mock_neo4j
    ):
        """Concept name matching a synonym entry creates SAME_AS edge."""
        mock_neo4j.execute_query = AsyncMock(
            side_effect=[
                # _fetch_concept_names
                [{"name": "Heart Attack"}],
                # preferred_name query — no match
                [],
                # synonym query — match
                [{"name": "heart attack", "cui": "C0027051"}],
            ]
        )
        mock_neo4j.execute_write_query = AsyncMock(
            return_value=[{"cnt": 1}]
        )

        result = await bridger.create_same_as_edges()

        assert result.concepts_matched == 1
        write_calls = mock_neo4j.execute_write_query.call_args_list
        items = write_calls[0][0][1]["items"]
        assert len(items) == 1
        assert items[0]["match_type"] == "synonym"
        assert items[0]["cui"] == "C0027051"

    @pytest.mark.asyncio
    async def test_preferred_name_takes_priority_over_synonym(
        self, bridger, mock_neo4j
    ):
        """When concept matches both preferred and synonym for same CUI,
        only one edge is created (deduplicated by concept_name+cui pair)."""
        mock_neo4j.execute_query = AsyncMock(
            side_effect=[
                # _fetch_concept_names
                [{"name": "diabetes"}],
                # preferred_name query — match
                [{"name": "diabetes", "cui": "C0011849"}],
                # synonym query — also match same CUI
                [{"name": "diabetes", "cui": "C0011849"}],
            ]
        )
        mock_neo4j.execute_write_query = AsyncMock(
            return_value=[{"cnt": 1}]
        )

        result = await bridger.create_same_as_edges()

        write_calls = mock_neo4j.execute_write_query.call_args_list
        items = write_calls[0][0][1]["items"]
        # Should be deduplicated to one edge per (concept_name, cui) pair
        assert len(items) == 1
        # preferred_name match should come first
        assert items[0]["match_type"] == "preferred_name"


class TestBridgeResultCounts:
    """Tests for BridgeResult accuracy."""

    @pytest.mark.asyncio
    async def test_result_contains_correct_counts(
        self, bridger, mock_neo4j
    ):
        """BridgeResult has correct matched, unmatched, and edge counts."""
        mock_neo4j.execute_query = AsyncMock(
            side_effect=[
                # 3 Concept nodes
                [
                    {"name": "Diabetes"},
                    {"name": "Hypertension"},
                    {"name": "Unknown Disease"},
                ],
                # preferred_name query — 2 matches
                [
                    {"name": "diabetes", "cui": "C0011849"},
                    {"name": "hypertension", "cui": "C0020538"},
                ],
                # synonym query — no additional matches
                [],
            ]
        )
        mock_neo4j.execute_write_query = AsyncMock(
            return_value=[{"cnt": 2}]
        )

        result = await bridger.create_same_as_edges()

        assert isinstance(result, BridgeResult)
        assert result.concepts_matched == 2
        assert result.same_as_edges_created == 2
        assert result.unmatched_concepts == 1
        assert result.elapsed_seconds >= 0

    @pytest.mark.asyncio
    async def test_result_dataclass_fields(self, bridger, mock_neo4j):
        """BridgeResult has all expected fields."""
        result = await bridger.create_same_as_edges()
        assert hasattr(result, "concepts_matched")
        assert hasattr(result, "same_as_edges_created")
        assert hasattr(result, "unmatched_concepts")
        assert hasattr(result, "elapsed_seconds")


class TestNoConceptNodes:
    """Tests for empty graph scenarios."""

    @pytest.mark.asyncio
    async def test_no_concept_nodes_produces_zero_edges(
        self, bridger, mock_neo4j
    ):
        """No Concept nodes in graph produces zero SAME_AS edges."""
        mock_neo4j.execute_query = AsyncMock(return_value=[])

        result = await bridger.create_same_as_edges()

        assert result.concepts_matched == 0
        assert result.same_as_edges_created == 0
        assert result.unmatched_concepts == 0
        mock_neo4j.execute_write_query.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_umls_concept_nodes_produces_zero_edges(
        self, bridger, mock_neo4j
    ):
        """No UMLSConcept matches produces zero SAME_AS edges."""
        mock_neo4j.execute_query = AsyncMock(
            side_effect=[
                # _fetch_concept_names
                [{"name": "Diabetes"}],
                # preferred_name query — no match
                [],
                # synonym query — no match
                [],
            ]
        )

        result = await bridger.create_same_as_edges()

        assert result.concepts_matched == 0
        assert result.same_as_edges_created == 0
        assert result.unmatched_concepts == 1
        mock_neo4j.execute_write_query.assert_not_called()


class TestIdempotence:
    """Tests for SAME_AS bridging idempotence."""

    @pytest.mark.asyncio
    async def test_merge_query_used_for_idempotence(
        self, bridger, mock_neo4j
    ):
        """MERGE is used in the Cypher query to prevent duplicate edges."""
        mock_neo4j.execute_query = AsyncMock(
            side_effect=[
                [{"name": "Diabetes"}],
                [{"name": "diabetes", "cui": "C0011849"}],
                [],
            ]
        )
        mock_neo4j.execute_write_query = AsyncMock(
            return_value=[{"cnt": 1}]
        )

        await bridger.create_same_as_edges()

        write_calls = mock_neo4j.execute_write_query.call_args_list
        query = write_calls[0][0][0]
        assert "MERGE" in query
        assert "SAME_AS" in query


class TestEdgeProperties:
    """Tests for SAME_AS edge properties."""

    @pytest.mark.asyncio
    async def test_match_type_and_created_at_set(
        self, bridger, mock_neo4j
    ):
        """SAME_AS edges include match_type and created_at properties."""
        mock_neo4j.execute_query = AsyncMock(
            side_effect=[
                [{"name": "Diabetes"}],
                [{"name": "diabetes", "cui": "C0011849"}],
                [],
            ]
        )
        mock_neo4j.execute_write_query = AsyncMock(
            return_value=[{"cnt": 1}]
        )

        await bridger.create_same_as_edges()

        write_calls = mock_neo4j.execute_write_query.call_args_list
        query = write_calls[0][0][0]
        assert "match_type" in query
        assert "created_at" in query

        items = write_calls[0][0][1]["items"]
        assert items[0]["match_type"] in ("preferred_name", "synonym")
        assert items[0]["created_at"] is not None


class TestBatchProcessing:
    """Tests for batch UNWIND processing."""

    @pytest.mark.asyncio
    async def test_batching_with_small_batch_size(
        self, bridger, mock_neo4j
    ):
        """Multiple batches are created when matches exceed batch_size."""
        mock_neo4j.execute_query = AsyncMock(
            side_effect=[
                # _fetch_concept_names
                [
                    {"name": "Diabetes"},
                    {"name": "Hypertension"},
                    {"name": "Asthma"},
                ],
                # preferred_name query — all 3 match
                [
                    {"name": "diabetes", "cui": "C0011849"},
                    {"name": "hypertension", "cui": "C0020538"},
                    {"name": "asthma", "cui": "C0004096"},
                ],
                # synonym query
                [],
            ]
        )
        mock_neo4j.execute_write_query = AsyncMock(
            return_value=[{"cnt": 2}]
        )

        # batch_size=2 should produce 2 write batches for 3 matches
        result = await bridger.create_same_as_edges(batch_size=2)

        assert mock_neo4j.execute_write_query.call_count == 2
        first_batch = mock_neo4j.execute_write_query.call_args_list[0][0][1]["items"]
        second_batch = mock_neo4j.execute_write_query.call_args_list[1][0][1]["items"]
        assert len(first_batch) == 2
        assert len(second_batch) == 1


class TestMatchConceptsBatch:
    """Tests for the _match_concepts_batch query-based matching."""

    @pytest.mark.asyncio
    async def test_preferred_name_query_uses_lower_name(
        self, bridger, mock_neo4j
    ):
        """Preferred name query uses u.lower_name for indexed lookup."""
        mock_neo4j.execute_query = AsyncMock(return_value=[])

        await bridger._match_concepts_batch(["Diabetes"])

        # First call is preferred_name, second is synonym
        pn_call = mock_neo4j.execute_query.call_args_list[0]
        query = pn_call[0][0]
        assert "lower_name" in query
        params = pn_call[0][1]
        assert params["names"] == ["diabetes"]

    @pytest.mark.asyncio
    async def test_synonym_query_uses_umls_synonym_nodes(
        self, bridger, mock_neo4j
    ):
        """Synonym query uses indexed UMLSSynonym nodes via HAS_SYNONYM."""
        mock_neo4j.execute_query = AsyncMock(return_value=[])

        await bridger._match_concepts_batch(["Heart Attack"])

        syn_call = mock_neo4j.execute_query.call_args_list[1]
        query = syn_call[0][0]
        assert "UMLSSynonym" in query
        assert "HAS_SYNONYM" in query

    @pytest.mark.asyncio
    async def test_empty_names_returns_empty(self, bridger, mock_neo4j):
        """Empty names list returns empty matches without querying."""
        result = await bridger._match_concepts_batch([])
        assert result == []
        mock_neo4j.execute_query.assert_not_called()

    @pytest.mark.asyncio
    async def test_deduplication_by_concept_cui_pair(
        self, bridger, mock_neo4j
    ):
        """Matches are deduplicated by (concept_name, cui) pair."""
        mock_neo4j.execute_query = AsyncMock(
            side_effect=[
                # preferred_name match
                [{"name": "diabetes", "cui": "C001"}],
                # synonym match — same pair
                [{"name": "diabetes", "cui": "C001"}],
            ]
        )

        result = await bridger._match_concepts_batch(["Diabetes"])
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_multiple_cuis_same_name(self, bridger, mock_neo4j):
        """A name matching multiple CUIs returns all matches."""
        mock_neo4j.execute_query = AsyncMock(
            side_effect=[
                # preferred_name matches two CUIs
                [
                    {"name": "cold", "cui": "C001"},
                    {"name": "cold", "cui": "C002"},
                ],
                # synonym query
                [],
            ]
        )

        result = await bridger._match_concepts_batch(["Cold"])
        assert len(result) == 2
        cuis = {m["cui"] for m in result}
        assert cuis == {"C001", "C002"}
