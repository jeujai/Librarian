"""Unit tests for UMLSLoader Semantic Network loading."""

import os
import tempfile
from unittest.mock import AsyncMock, MagicMock

import pytest

from multimodal_librarian.components.knowledge_graph.umls_loader import (
    DryRunResult,
    LoadResult,
    UMLSLoader,
    UMLSStats,
)


@pytest.fixture
def mock_neo4j():
    """Create a mock Neo4j client."""
    mock = MagicMock()
    mock.execute_query = AsyncMock(return_value=[])
    mock.execute_write_query = AsyncMock(
        return_value=[{"count": 0}]
    )
    return mock


@pytest.fixture
def loader(mock_neo4j):
    """Create a UMLSLoader with mock Neo4j client."""
    return UMLSLoader(mock_neo4j)


class TestLoadSemanticNetwork:
    """Tests for load_semantic_network method."""

    @pytest.mark.asyncio
    async def test_file_not_found(self, loader):
        """FileNotFoundError raised for missing SRDEF."""
        with pytest.raises(FileNotFoundError):
            await loader.load_semantic_network(
                "/nonexistent/SRDEF"
            )

    @pytest.mark.asyncio
    async def test_empty_file(self, loader, mock_neo4j):
        """Empty SRDEF returns zero counts."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False
        ) as f:
            f.write("")
            path = f.name

        try:
            result = await loader.load_semantic_network(path)
            assert isinstance(result, LoadResult)
            assert result.nodes_created == 0
            assert result.relationships_created == 0
            assert result.batches_completed == 1
            assert result.batches_failed == 0
            assert result.elapsed_seconds >= 0
            assert mock_neo4j.execute_write_query.called
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_sty_records_create_nodes(
        self, loader, mock_neo4j
    ):
        """STY records create UMLSSemanticType nodes."""
        mock_neo4j.execute_write_query = AsyncMock(
            return_value=[{"count": 2}]
        )
        lines = [
            "STY|T001|Event|A|A happening.",
            "STY|T002|Entity|B|A thing.",
        ]
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False
        ) as f:
            for line in lines:
                f.write(line + "\n")
            path = f.name

        try:
            result = await loader.load_semantic_network(path)
            assert result.nodes_created == 2
            call_args = (
                mock_neo4j.execute_write_query.call_args_list
            )
            first_call = call_args[0]
            query = first_call[0][0]
            assert "UMLSSemanticType" in query
            assert "MERGE" in query
            params = first_call[0][1]
            types = params["types"]
            assert len(types) == 2
            assert types[0]["type_id"] == "T001"
            assert types[0]["type_name"] == "Event"
            assert types[0]["tree_number"] == "A"
            assert types[0]["definition"] == "A happening."
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_hierarchy_edges_from_tree_numbers(
        self, loader, mock_neo4j
    ):
        """Tree numbers derive parent-child edges."""
        mock_neo4j.execute_write_query = AsyncMock(
            return_value=[{"count": 3}]
        )
        lines = [
            "STY|T001|Event|A|Root type.",
            "STY|T002|Activity|A.1|An activity.",
            "STY|T003|Behavior|A.1.1|A behavior.",
        ]
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False
        ) as f:
            for line in lines:
                f.write(line + "\n")
            path = f.name

        try:
            await loader.load_semantic_network(path)
            calls = (
                mock_neo4j.execute_write_query.call_args_list
            )
            # Second call should be hierarchy edges
            hierarchy_call = calls[1]
            params = hierarchy_call[0][1]
            edges = params["edges"]
            assert len(edges) == 2
            # A.1 -> A (parent)
            assert edges[0]["child_type_id"] == "T002"
            assert edges[0]["parent_type_id"] == "T001"
            assert edges[0]["relation_name"] == "isa"
            assert edges[0]["relation_inverse"] == "inverse_isa"
            # A.1.1 -> A.1 (parent)
            assert edges[1]["child_type_id"] == "T003"
            assert edges[1]["parent_type_id"] == "T002"
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_rl_records_create_relationship_defs(
        self, loader, mock_neo4j
    ):
        """RL records create UMLSRelationshipDef nodes."""
        mock_neo4j.execute_write_query = AsyncMock(
            return_value=[{"count": 1}]
        )
        lines = [
            (
                "RL|T186|treats|A1.4.1|"
                "Therapeutic treatment.|"
                "ex|un|nh|trt|treated_by"
            ),
        ]
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False
        ) as f:
            for line in lines:
                f.write(line + "\n")
            path = f.name

        try:
            await loader.load_semantic_network(path)
            calls = (
                mock_neo4j.execute_write_query.call_args_list
            )
            rel_call = calls[0]
            params = rel_call[0][1]
            rels = params["rels"]
            assert len(rels) == 1
            assert rels[0]["rel_id"] == "T186"
            assert rels[0]["relation_name"] == "treats"
            assert rels[0]["relation_inverse"] == "treated_by"
            assert "Therapeutic" in rels[0]["definition"]
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_metadata_node_created(
        self, loader, mock_neo4j
    ):
        """UMLSMetadata singleton created with lite tier."""
        mock_neo4j.execute_write_query = AsyncMock(
            return_value=[{"count": 0}]
        )
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False
        ) as f:
            f.write("")
            path = f.name

        try:
            await loader.load_semantic_network(path)
            calls = (
                mock_neo4j.execute_write_query.call_args_list
            )
            metadata_call = calls[-1]
            query = metadata_call[0][0]
            assert "UMLSMetadata" in query
            assert "MERGE" in query
            params = metadata_call[0][1]
            assert params["loaded_tier"] == "lite"
            assert "load_timestamp" in params
            assert params["umls_version"] == "2024AA"
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_malformed_rows_skipped(
        self, loader, mock_neo4j
    ):
        """Rows with fewer than 5 fields are skipped."""
        mock_neo4j.execute_write_query = AsyncMock(
            return_value=[{"count": 1}]
        )
        lines = [
            "BAD|ROW",
            "STY|T001|Event|A|Valid row.",
            "SHORT",
        ]
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False
        ) as f:
            for line in lines:
                f.write(line + "\n")
            path = f.name

        try:
            await loader.load_semantic_network(path)
            calls = (
                mock_neo4j.execute_write_query.call_args_list
            )
            types_call = calls[0]
            params = types_call[0][1]
            types = params["types"]
            assert len(types) == 1
            assert types[0]["type_id"] == "T001"
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_no_hierarchy_for_root_nodes(
        self, loader, mock_neo4j
    ):
        """Root nodes (no dot in tree_number) get no edges."""
        mock_neo4j.execute_write_query = AsyncMock(
            return_value=[{"count": 2}]
        )
        lines = [
            "STY|T001|Event|A|Root one.",
            "STY|T002|Entity|B|Root two.",
        ]
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False
        ) as f:
            for line in lines:
                f.write(line + "\n")
            path = f.name

        try:
            await loader.load_semantic_network(path)
            calls = (
                mock_neo4j.execute_write_query.call_args_list
            )
            # types creation + metadata only, no hierarchy
            for call in calls:
                if "edges" in str(call):
                    pytest.fail(
                        "Hierarchy edges created for roots"
                    )
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_load_result_timing(
        self, loader, mock_neo4j
    ):
        """LoadResult includes positive elapsed time."""
        mock_neo4j.execute_write_query = AsyncMock(
            return_value=[{"count": 0}]
        )
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False
        ) as f:
            f.write("")
            path = f.name

        try:
            result = await loader.load_semantic_network(path)
            assert result.elapsed_seconds >= 0
            assert result.batches_completed == 1
            assert result.batches_failed == 0
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_mixed_sty_and_rl_records(
        self, loader, mock_neo4j
    ):
        """Both STY and RL records are parsed correctly."""
        mock_neo4j.execute_write_query = AsyncMock(
            return_value=[{"count": 2}]
        )
        lines = [
            "STY|T001|Event|A|A happening.",
            "STY|T002|Activity|A.1|An activity.",
            (
                "RL|T186|treats|A1.4.1|"
                "Treatment.|ex|un|nh|trt|treated_by"
            ),
        ]
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False
        ) as f:
            for line in lines:
                f.write(line + "\n")
            path = f.name

        try:
            await loader.load_semantic_network(path)
            calls = (
                mock_neo4j.execute_write_query.call_args_list
            )
            # types, hierarchy, rel defs, metadata
            assert len(calls) == 4
        finally:
            os.unlink(path)


class TestLoadConcepts:
    """Tests for load_concepts method."""

    @pytest.mark.asyncio
    async def test_mrconso_file_not_found(self, loader):
        """FileNotFoundError raised for missing MRCONSO."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False
        ) as f:
            f.write("")
            mrsty_path = f.name
        try:
            with pytest.raises(FileNotFoundError, match="MRCONSO"):
                await loader.load_concepts(
                    "/nonexistent/MRCONSO.csv", mrsty_path
                )
        finally:
            os.unlink(mrsty_path)

    @pytest.mark.asyncio
    async def test_mrsty_file_not_found(self, loader):
        """FileNotFoundError raised for missing MRSTY."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False
        ) as f:
            f.write("")
            mrconso_path = f.name
        try:
            with pytest.raises(FileNotFoundError, match="MRSTY"):
                await loader.load_concepts(
                    mrconso_path, "/nonexistent/MRSTY"
                )
        finally:
            os.unlink(mrconso_path)

    @pytest.mark.asyncio
    async def test_english_only_filter(self, loader, mock_neo4j):
        """Only English (LAT=ENG) entries are loaded."""
        mock_neo4j.execute_write_query = AsyncMock(
            return_value=[{"count": 1}]
        )
        # CUI|LAT|TS|LUI|STT|SUI|ISPREF|AUI|SAUI|SCUI|SDUI|SAB|TTY|CODE|STR|SRL|SUPPRESS|CVF
        mrconso_lines = [
            "C0000001|ENG|P|L001|PF|S001|Y|A001||SC1||MSH|PT|D001|Aspirin|0|N|",
            "C0000002|SPA|P|L002|PF|S002|Y|A002||SC2||MSH|PT|D002|Aspirina|0|N|",
            "C0000003|FRE|P|L003|PF|S003|Y|A003||SC3||MSH|PT|D003|Aspirine|0|N|",
        ]
        mrsty_lines = []

        mrconso_path, mrsty_path = _create_temp_files(
            mrconso_lines, mrsty_lines
        )
        try:
            result = await loader.load_concepts(
                mrconso_path, mrsty_path
            )
            # Only 1 English concept should be in the batch
            calls = mock_neo4j.execute_write_query.call_args_list
            # Find the concept creation call (has "concepts" param)
            concept_call = _find_call_with_param(calls, "concepts")
            assert concept_call is not None
            concepts = concept_call[0][1]["concepts"]
            assert len(concepts) == 1
            assert concepts[0]["cui"] == "C0000001"
        finally:
            os.unlink(mrconso_path)
            os.unlink(mrsty_path)

    @pytest.mark.asyncio
    async def test_source_vocab_filter(self, loader, mock_neo4j):
        """Only specified source vocabularies are loaded."""
        mock_neo4j.execute_write_query = AsyncMock(
            return_value=[{"count": 2}]
        )
        mrconso_lines = [
            "C0000001|ENG|P|L001|PF|S001|Y|A001||SC1||SNOMEDCT_US|PT|D001|Aspirin|0|N|",
            "C0000002|ENG|P|L002|PF|S002|Y|A002||SC2||MSH|PT|D002|Headache|0|N|",
            "C0000003|ENG|P|L003|PF|S003|Y|A003||SC3||RXNORM|PT|D003|Ibuprofen|0|N|",
            "C0000004|ENG|P|L004|PF|S004|Y|A004||SC4||ICD10|PT|D004|Fever|0|N|",
        ]
        mrsty_lines = []

        mrconso_path, mrsty_path = _create_temp_files(
            mrconso_lines, mrsty_lines
        )
        try:
            result = await loader.load_concepts(
                mrconso_path,
                mrsty_path,
                source_vocabs=["SNOMEDCT_US", "MSH"],
            )
            calls = mock_neo4j.execute_write_query.call_args_list
            concept_call = _find_call_with_param(calls, "concepts")
            concepts = concept_call[0][1]["concepts"]
            assert len(concepts) == 2
            cuis = {c["cui"] for c in concepts}
            assert cuis == {"C0000001", "C0000002"}
        finally:
            os.unlink(mrconso_path)
            os.unlink(mrsty_path)

    @pytest.mark.asyncio
    async def test_preferred_name_selection(
        self, loader, mock_neo4j
    ):
        """Preferred name is from TS=P, STT=PF row."""
        mock_neo4j.execute_write_query = AsyncMock(
            return_value=[{"count": 1}]
        )
        mrconso_lines = [
            "C0000001|ENG|S|L001|VO|S001|Y|A001||SC1||MSH|SY|D001|acetylsalicylic acid|0|N|",
            "C0000001|ENG|P|L002|PF|S002|Y|A002||SC1||MSH|PT|D001|Aspirin|0|N|",
            "C0000001|ENG|S|L003|VO|S003|Y|A003||SC1||MSH|SY|D001|ASA|0|N|",
        ]
        mrsty_lines = []

        mrconso_path, mrsty_path = _create_temp_files(
            mrconso_lines, mrsty_lines
        )
        try:
            await loader.load_concepts(mrconso_path, mrsty_path)
            calls = mock_neo4j.execute_write_query.call_args_list
            concept_call = _find_call_with_param(calls, "concepts")
            concepts = concept_call[0][1]["concepts"]
            assert len(concepts) == 1
            c = concepts[0]
            assert c["preferred_name"] == "Aspirin"
            assert "acetylsalicylic acid" in c["synonyms"]
            assert "ASA" in c["synonyms"]
            assert "Aspirin" not in c["synonyms"]
        finally:
            os.unlink(mrconso_path)
            os.unlink(mrsty_path)

    @pytest.mark.asyncio
    async def test_synonym_aggregation(self, loader, mock_neo4j):
        """Multiple names for same CUI are aggregated."""
        mock_neo4j.execute_write_query = AsyncMock(
            return_value=[{"count": 1}]
        )
        mrconso_lines = [
            "C0000001|ENG|P|L001|PF|S001|Y|A001||SC1||MSH|PT|D001|Aspirin|0|N|",
            "C0000001|ENG|S|L002|VO|S002|Y|A002||SC1||MSH|SY|D001|ASA|0|N|",
            "C0000001|ENG|S|L003|VO|S003|Y|A003||SC1||SNOMEDCT_US|SY|D001|Acetylsalicylic acid|0|N|",
        ]
        mrsty_lines = []

        mrconso_path, mrsty_path = _create_temp_files(
            mrconso_lines, mrsty_lines
        )
        try:
            await loader.load_concepts(mrconso_path, mrsty_path)
            calls = mock_neo4j.execute_write_query.call_args_list
            concept_call = _find_call_with_param(calls, "concepts")
            concepts = concept_call[0][1]["concepts"]
            c = concepts[0]
            assert c["preferred_name"] == "Aspirin"
            assert len(c["synonyms"]) == 2
            assert "ASA" in c["synonyms"]
            assert "Acetylsalicylic acid" in c["synonyms"]
        finally:
            os.unlink(mrconso_path)
            os.unlink(mrsty_path)

    @pytest.mark.asyncio
    async def test_suppressed_flag(self, loader, mock_neo4j):
        """Suppressed flag is True when SUPPRESS != N."""
        mock_neo4j.execute_write_query = AsyncMock(
            return_value=[{"count": 2}]
        )
        mrconso_lines = [
            "C0000001|ENG|P|L001|PF|S001|Y|A001||SC1||MSH|PT|D001|Aspirin|0|N|",
            "C0000002|ENG|P|L002|PF|S002|Y|A002||SC2||MSH|PT|D002|OldDrug|0|O|",
        ]
        mrsty_lines = []

        mrconso_path, mrsty_path = _create_temp_files(
            mrconso_lines, mrsty_lines
        )
        try:
            await loader.load_concepts(mrconso_path, mrsty_path)
            calls = mock_neo4j.execute_write_query.call_args_list
            concept_call = _find_call_with_param(calls, "concepts")
            concepts = concept_call[0][1]["concepts"]
            by_cui = {c["cui"]: c for c in concepts}
            assert by_cui["C0000001"]["suppressed"] is False
            assert by_cui["C0000002"]["suppressed"] is True
        finally:
            os.unlink(mrconso_path)
            os.unlink(mrsty_path)

    @pytest.mark.asyncio
    async def test_mrsty_creates_has_semantic_type_edges(
        self, loader, mock_neo4j
    ):
        """MRSTY entries create HAS_SEMANTIC_TYPE edges."""
        mock_neo4j.execute_write_query = AsyncMock(
            return_value=[{"count": 1}]
        )
        mrconso_lines = [
            "C0000001|ENG|P|L001|PF|S001|Y|A001||SC1||MSH|PT|D001|Aspirin|0|N|",
        ]
        mrsty_lines = [
            "C0000001|T121|A1.4.1.1.1|Pharmacologic Substance|AT123|",
            "C0000001|T109|A1.4.1.2.1|Organic Chemical|AT124|",
            "C9999999|T047|A2.2.2|Disease or Syndrome|AT125|",
        ]

        mrconso_path, mrsty_path = _create_temp_files(
            mrconso_lines, mrsty_lines
        )
        try:
            await loader.load_concepts(mrconso_path, mrsty_path)
            calls = mock_neo4j.execute_write_query.call_args_list
            edge_call = _find_call_with_param(calls, "edges")
            assert edge_call is not None
            edges = edge_call[0][1]["edges"]
            # Only C0000001 edges, not C9999999 (not in loaded set)
            assert len(edges) == 2
            tuis = {e["tui"] for e in edges}
            assert tuis == {"T121", "T109"}
            assert all(e["cui"] == "C0000001" for e in edges)
        finally:
            os.unlink(mrconso_path)
            os.unlink(mrsty_path)

    @pytest.mark.asyncio
    async def test_batch_size_respected(self, loader, mock_neo4j):
        """Concepts are batched according to batch_size."""
        mock_neo4j.execute_write_query = AsyncMock(
            return_value=[{"count": 1}]
        )
        # Create 5 concepts, batch_size=2 -> 3 concept batches
        mrconso_lines = [
            f"C000000{i}|ENG|P|L00{i}|PF|S00{i}|Y|A00{i}||SC{i}||MSH|PT|D00{i}|Drug{i}|0|N|"
            for i in range(1, 6)
        ]
        mrsty_lines = []

        mrconso_path, mrsty_path = _create_temp_files(
            mrconso_lines, mrsty_lines
        )
        try:
            result = await loader.load_concepts(
                mrconso_path, mrsty_path, batch_size=2
            )
            calls = mock_neo4j.execute_write_query.call_args_list
            concept_calls = [
                c
                for c in calls
                if "concepts" in str(c)
                and "UMLSConcept" in str(c)
            ]
            # 5 concepts / batch_size 2 = 3 batches
            assert len(concept_calls) == 3
        finally:
            os.unlink(mrconso_path)
            os.unlink(mrsty_path)

    @pytest.mark.asyncio
    async def test_metadata_updated_to_full(
        self, loader, mock_neo4j
    ):
        """UMLSMetadata updated with loaded_tier=full."""
        mock_neo4j.execute_write_query = AsyncMock(
            return_value=[{"count": 0}]
        )
        mrconso_lines = []
        mrsty_lines = []

        mrconso_path, mrsty_path = _create_temp_files(
            mrconso_lines, mrsty_lines
        )
        try:
            await loader.load_concepts(mrconso_path, mrsty_path)
            calls = mock_neo4j.execute_write_query.call_args_list
            # Last call should be metadata update
            metadata_call = calls[-1]
            query = metadata_call[0][0]
            assert "loaded_tier" in query
            assert "full" in query
            assert "complete" in query
        finally:
            os.unlink(mrconso_path)
            os.unlink(mrsty_path)

    @pytest.mark.asyncio
    async def test_import_status_set_to_in_progress(
        self, loader, mock_neo4j
    ):
        """Import status is set to in_progress at start."""
        mock_neo4j.execute_write_query = AsyncMock(
            return_value=[{"count": 0}]
        )
        mrconso_lines = [
            "C0000001|ENG|P|L001|PF|S001|Y|A001||SC1||MSH|PT|D001|Aspirin|0|N|",
        ]
        mrsty_lines = []

        mrconso_path, mrsty_path = _create_temp_files(
            mrconso_lines, mrsty_lines
        )
        try:
            await loader.load_concepts(mrconso_path, mrsty_path)
            calls = mock_neo4j.execute_write_query.call_args_list
            # First call should set import_status to in_progress
            first_call = calls[0]
            query = first_call[0][0]
            assert "in_progress" in query
        finally:
            os.unlink(mrconso_path)
            os.unlink(mrsty_path)

    @pytest.mark.asyncio
    async def test_load_result_structure(self, loader, mock_neo4j):
        """LoadResult has correct structure and values."""
        mock_neo4j.execute_write_query = AsyncMock(
            return_value=[{"count": 2}]
        )
        mrconso_lines = [
            "C0000001|ENG|P|L001|PF|S001|Y|A001||SC1||MSH|PT|D001|Aspirin|0|N|",
            "C0000002|ENG|P|L002|PF|S002|Y|A002||SC2||MSH|PT|D002|Ibuprofen|0|N|",
        ]
        mrsty_lines = [
            "C0000001|T121|A1|Pharmacologic Substance|AT1|",
        ]

        mrconso_path, mrsty_path = _create_temp_files(
            mrconso_lines, mrsty_lines
        )
        try:
            result = await loader.load_concepts(
                mrconso_path, mrsty_path
            )
            assert isinstance(result, LoadResult)
            assert result.nodes_created >= 0
            assert result.relationships_created >= 0
            assert result.batches_completed >= 0
            assert result.elapsed_seconds >= 0
        finally:
            os.unlink(mrconso_path)
            os.unlink(mrsty_path)

    @pytest.mark.asyncio
    async def test_no_preferred_name_fallback(
        self, loader, mock_neo4j
    ):
        """CUI with no TS=P/STT=PF row uses first synonym."""
        mock_neo4j.execute_write_query = AsyncMock(
            return_value=[{"count": 1}]
        )
        mrconso_lines = [
            "C0000001|ENG|S|L001|VO|S001|Y|A001||SC1||MSH|SY|D001|Name A|0|N|",
            "C0000001|ENG|S|L002|VO|S002|Y|A002||SC1||MSH|SY|D001|Name B|0|N|",
        ]
        mrsty_lines = []

        mrconso_path, mrsty_path = _create_temp_files(
            mrconso_lines, mrsty_lines
        )
        try:
            await loader.load_concepts(mrconso_path, mrsty_path)
            calls = mock_neo4j.execute_write_query.call_args_list
            concept_call = _find_call_with_param(calls, "concepts")
            concepts = concept_call[0][1]["concepts"]
            c = concepts[0]
            # First synonym becomes preferred_name
            assert c["preferred_name"] == "Name A"
            assert "Name B" in c["synonyms"]
            assert "Name A" not in c["synonyms"]
        finally:
            os.unlink(mrconso_path)
            os.unlink(mrsty_path)

    @pytest.mark.asyncio
    async def test_empty_mrconso_produces_zero_nodes(
        self, loader, mock_neo4j
    ):
        """Empty MRCONSO file produces zero concept nodes."""
        mock_neo4j.execute_write_query = AsyncMock(
            return_value=[{"count": 0}]
        )
        mrconso_lines = []
        mrsty_lines = []

        mrconso_path, mrsty_path = _create_temp_files(
            mrconso_lines, mrsty_lines
        )
        try:
            result = await loader.load_concepts(
                mrconso_path, mrsty_path
            )
            assert result.nodes_created == 0
            assert result.relationships_created == 0
        finally:
            os.unlink(mrconso_path)
            os.unlink(mrsty_path)

    @pytest.mark.asyncio
    async def test_non_english_only_produces_zero_nodes(
        self, loader, mock_neo4j
    ):
        """MRCONSO with only non-English rows produces zero nodes."""
        mock_neo4j.execute_write_query = AsyncMock(
            return_value=[{"count": 0}]
        )
        mrconso_lines = [
            "C0000001|SPA|P|L001|PF|S001|Y|A001||SC1||MSH|PT|D001|Aspirina|0|N|",
            "C0000002|FRE|P|L002|PF|S002|Y|A002||SC2||MSH|PT|D002|Aspirine|0|N|",
        ]
        mrsty_lines = []

        mrconso_path, mrsty_path = _create_temp_files(
            mrconso_lines, mrsty_lines
        )
        try:
            result = await loader.load_concepts(
                mrconso_path, mrsty_path
            )
            assert result.nodes_created == 0
        finally:
            os.unlink(mrconso_path)
            os.unlink(mrsty_path)

    @pytest.mark.asyncio
    async def test_duplicate_synonym_not_added(
        self, loader, mock_neo4j
    ):
        """Duplicate names for same CUI are not duplicated."""
        mock_neo4j.execute_write_query = AsyncMock(
            return_value=[{"count": 1}]
        )
        mrconso_lines = [
            "C0000001|ENG|P|L001|PF|S001|Y|A001||SC1||MSH|PT|D001|Aspirin|0|N|",
            "C0000001|ENG|S|L002|VO|S002|Y|A002||SC1||SNOMEDCT_US|SY|D001|Aspirin|0|N|",
            "C0000001|ENG|S|L003|VO|S003|Y|A003||SC1||MSH|SY|D001|ASA|0|N|",
        ]
        mrsty_lines = []

        mrconso_path, mrsty_path = _create_temp_files(
            mrconso_lines, mrsty_lines
        )
        try:
            await loader.load_concepts(mrconso_path, mrsty_path)
            calls = mock_neo4j.execute_write_query.call_args_list
            concept_call = _find_call_with_param(calls, "concepts")
            concepts = concept_call[0][1]["concepts"]
            c = concepts[0]
            # "Aspirin" should not appear in synonyms
            assert c["preferred_name"] == "Aspirin"
            assert c["synonyms"].count("Aspirin") == 0
            assert c["synonyms"].count("ASA") == 1
        finally:
            os.unlink(mrconso_path)
            os.unlink(mrsty_path)


class TestLoadRelationships:
    """Tests for load_relationships method."""

    @pytest.mark.asyncio
    async def test_mrrel_file_not_found(self, loader):
        """FileNotFoundError raised for missing MRREL file."""
        with pytest.raises(FileNotFoundError, match="MRREL"):
            await loader.load_relationships(
                "/nonexistent/MRREL.csv"
            )

    @pytest.mark.asyncio
    async def test_empty_mrrel_no_concepts(
        self, loader, mock_neo4j
    ):
        """Empty loaded concept set produces zero relationships."""
        mock_neo4j.execute_query = AsyncMock(return_value=[])
        mock_neo4j.execute_write_query = AsyncMock(
            return_value=[{"count": 0}]
        )

        mrrel_path = _create_temp_mrrel([])
        try:
            result = await loader.load_relationships(mrrel_path)
            assert result.relationships_created == 0
            assert result.batches_completed == 0
            assert result.nodes_created == 0
        finally:
            os.unlink(mrrel_path)

    @pytest.mark.asyncio
    async def test_basic_relationship_creation(
        self, loader, mock_neo4j
    ):
        """Valid MRREL rows create UMLS_REL edges."""
        mock_neo4j.execute_query = AsyncMock(
            return_value=[
                {"cui": "C0000001"},
                {"cui": "C0000002"},
            ]
        )
        mock_neo4j.execute_write_query = AsyncMock(
            return_value=[{"count": 2}]
        )

        mrrel_lines = [
            "C0000001|A001|AUI|RO|C0000002|A002|AUI|treats|R001||MSH|MSH|0|Y|N|",
            "C0000002|A002|AUI|RB|C0000001|A001|AUI|causes|R002||MSH|MSH|0|Y|N|",
        ]
        mrrel_path = _create_temp_mrrel(mrrel_lines)
        try:
            result = await loader.load_relationships(mrrel_path)
            assert result.relationships_created == 2
            assert result.batches_completed == 1

            calls = mock_neo4j.execute_write_query.call_args_list
            rel_call = _find_call_with_param(calls, "rels")
            assert rel_call is not None
            rels = rel_call[0][1]["rels"]
            assert len(rels) == 2
            assert rels[0]["cui1"] == "C0000001"
            assert rels[0]["cui2"] == "C0000002"
            assert rels[0]["rel_type"] == "RO"
            assert rels[0]["rela_type"] == "treats"
            assert rels[0]["source_vocabulary"] == "MSH"
            assert rels[0]["cui_pair"] == "C0000001-C0000002"
        finally:
            os.unlink(mrrel_path)

    @pytest.mark.asyncio
    async def test_edge_type_uses_rela_when_present(
        self, loader, mock_neo4j
    ):
        """Edge type is UMLS_{RELA} when RELA is non-empty."""
        mock_neo4j.execute_query = AsyncMock(
            return_value=[
                {"cui": "C0000001"},
                {"cui": "C0000002"},
            ]
        )
        mock_neo4j.execute_write_query = AsyncMock(
            return_value=[{"count": 1}]
        )

        mrrel_lines = [
            "C0000001|A001|AUI|RO|C0000002|A002|AUI|treats|R001||MSH|MSH|0|Y|N|",
        ]
        mrrel_path = _create_temp_mrrel(mrrel_lines)
        try:
            await loader.load_relationships(mrrel_path)
            calls = mock_neo4j.execute_write_query.call_args_list
            rel_call = _find_call_with_param(calls, "rels")
            rels = rel_call[0][1]["rels"]
            assert rels[0]["edge_type"] == "UMLS_treats"
        finally:
            os.unlink(mrrel_path)

    @pytest.mark.asyncio
    async def test_edge_type_uses_rel_when_rela_empty(
        self, loader, mock_neo4j
    ):
        """Edge type is UMLS_{REL} when RELA is empty."""
        mock_neo4j.execute_query = AsyncMock(
            return_value=[
                {"cui": "C0000001"},
                {"cui": "C0000002"},
            ]
        )
        mock_neo4j.execute_write_query = AsyncMock(
            return_value=[{"count": 1}]
        )

        mrrel_lines = [
            "C0000001|A001|AUI|RO|C0000002|A002|AUI||R001||MSH|MSH|0|Y|N|",
        ]
        mrrel_path = _create_temp_mrrel(mrrel_lines)
        try:
            await loader.load_relationships(mrrel_path)
            calls = mock_neo4j.execute_write_query.call_args_list
            rel_call = _find_call_with_param(calls, "rels")
            rels = rel_call[0][1]["rels"]
            assert rels[0]["edge_type"] == "UMLS_RO"
        finally:
            os.unlink(mrrel_path)

    @pytest.mark.asyncio
    async def test_source_vocab_filter(
        self, loader, mock_neo4j
    ):
        """Only relationships from specified vocabs are kept."""
        mock_neo4j.execute_query = AsyncMock(
            return_value=[
                {"cui": "C0000001"},
                {"cui": "C0000002"},
            ]
        )
        mock_neo4j.execute_write_query = AsyncMock(
            return_value=[{"count": 1}]
        )

        mrrel_lines = [
            "C0000001|A001|AUI|RO|C0000002|A002|AUI|treats|R001||MSH|MSH|0|Y|N|",
            "C0000001|A001|AUI|RO|C0000002|A002|AUI|causes|R002||RXNORM|RXNORM|0|Y|N|",
        ]
        mrrel_path = _create_temp_mrrel(mrrel_lines)
        try:
            await loader.load_relationships(
                mrrel_path, source_vocabs=["MSH"]
            )
            calls = mock_neo4j.execute_write_query.call_args_list
            rel_call = _find_call_with_param(calls, "rels")
            rels = rel_call[0][1]["rels"]
            assert len(rels) == 1
            assert rels[0]["source_vocabulary"] == "MSH"
        finally:
            os.unlink(mrrel_path)

    @pytest.mark.asyncio
    async def test_dangling_cuis_skipped(
        self, loader, mock_neo4j
    ):
        """Relationships where either CUI is absent are skipped."""
        mock_neo4j.execute_query = AsyncMock(
            return_value=[{"cui": "C0000001"}]
        )
        mock_neo4j.execute_write_query = AsyncMock(
            return_value=[{"count": 0}]
        )

        mrrel_lines = [
            "C0000001|A001|AUI|RO|C0000002|A002|AUI|treats|R001||MSH|MSH|0|Y|N|",
            "C0000003|A003|AUI|RO|C0000001|A001|AUI|causes|R002||MSH|MSH|0|Y|N|",
            "C0000003|A003|AUI|RO|C0000004|A004|AUI|isa|R003||MSH|MSH|0|Y|N|",
        ]
        mrrel_path = _create_temp_mrrel(mrrel_lines)
        try:
            result = await loader.load_relationships(mrrel_path)
            calls = mock_neo4j.execute_write_query.call_args_list
            rel_call = _find_call_with_param(calls, "rels")
            assert rel_call is None
            assert result.relationships_created == 0
        finally:
            os.unlink(mrrel_path)

    @pytest.mark.asyncio
    async def test_malformed_rows_skipped(
        self, loader, mock_neo4j
    ):
        """Rows with fewer than 11 fields are skipped."""
        mock_neo4j.execute_query = AsyncMock(
            return_value=[
                {"cui": "C0000001"},
                {"cui": "C0000002"},
            ]
        )
        mock_neo4j.execute_write_query = AsyncMock(
            return_value=[{"count": 1}]
        )

        mrrel_lines = [
            "C0000001|A001|AUI|RO|C0000002|A002|AUI|treats|R001||MSH|MSH|0|Y|N|",
            "MALFORMED|ROW|ONLY|THREE",
        ]
        mrrel_path = _create_temp_mrrel(mrrel_lines)
        try:
            await loader.load_relationships(mrrel_path)
            calls = mock_neo4j.execute_write_query.call_args_list
            rel_call = _find_call_with_param(calls, "rels")
            rels = rel_call[0][1]["rels"]
            assert len(rels) == 1
        finally:
            os.unlink(mrrel_path)

    @pytest.mark.asyncio
    async def test_batch_size_respected(
        self, loader, mock_neo4j
    ):
        """Relationships are batched according to batch_size."""
        mock_neo4j.execute_query = AsyncMock(
            return_value=[
                {"cui": "C0000001"},
                {"cui": "C0000002"},
            ]
        )
        mock_neo4j.execute_write_query = AsyncMock(
            return_value=[{"count": 1}]
        )

        mrrel_lines = [
            "C0000001|A001|AUI|RO|C0000002|A002|AUI|treats|R001||MSH|MSH|0|Y|N|",
            "C0000002|A002|AUI|RB|C0000001|A001|AUI|causes|R002||MSH|MSH|0|Y|N|",
            "C0000001|A001|AUI|RN|C0000002|A002|AUI||R003||MSH|MSH|0|Y|N|",
        ]
        mrrel_path = _create_temp_mrrel(mrrel_lines)
        try:
            result = await loader.load_relationships(
                mrrel_path, batch_size=2
            )
            assert result.batches_completed == 2
        finally:
            os.unlink(mrrel_path)

    @pytest.mark.asyncio
    async def test_batch_failure_continues(
        self, loader, mock_neo4j
    ):
        """Failed batches are counted and processing continues."""
        mock_neo4j.execute_query = AsyncMock(
            return_value=[
                {"cui": "C0000001"},
                {"cui": "C0000002"},
            ]
        )
        # First batch: fails initial + 3 retries = 4 failures
        # Second batch: succeeds
        # Metadata update: succeeds
        mock_neo4j.execute_write_query = AsyncMock(
            side_effect=[
                Exception("Neo4j timeout"),
                Exception("Neo4j timeout"),
                Exception("Neo4j timeout"),
                Exception("Neo4j timeout"),
                [{"count": 1}],
                [{"count": 0}],  # metadata update
            ]
        )

        mrrel_lines = [
            "C0000001|A001|AUI|RO|C0000002|A002|AUI|treats|R001||MSH|MSH|0|Y|N|",
            "C0000002|A002|AUI|RB|C0000001|A001|AUI|causes|R002||MSH|MSH|0|Y|N|",
        ]
        mrrel_path = _create_temp_mrrel(mrrel_lines)
        try:
            result = await loader.load_relationships(
                mrrel_path, batch_size=1
            )
            assert result.batches_failed == 1
            assert result.batches_completed == 1
            assert result.relationships_created == 1
        finally:
            os.unlink(mrrel_path)

    @pytest.mark.asyncio
    async def test_metadata_updated(self, loader, mock_neo4j):
        """UMLSMetadata is updated with relationship count."""
        mock_neo4j.execute_query = AsyncMock(
            return_value=[
                {"cui": "C0000001"},
                {"cui": "C0000002"},
            ]
        )
        mock_neo4j.execute_write_query = AsyncMock(
            return_value=[{"count": 1}]
        )

        mrrel_lines = [
            "C0000001|A001|AUI|RO|C0000002|A002|AUI|treats|R001||MSH|MSH|0|Y|N|",
        ]
        mrrel_path = _create_temp_mrrel(mrrel_lines)
        try:
            await loader.load_relationships(mrrel_path)
            calls = mock_neo4j.execute_write_query.call_args_list
            metadata_call = None
            for call in calls:
                query = call[0][0]
                if (
                    "UMLSMetadata" in query
                    and "rel_count" in str(call)
                ):
                    metadata_call = call
                    break
            assert metadata_call is not None
            params = metadata_call[0][1]
            assert params["rel_count"] == 1
        finally:
            os.unlink(mrrel_path)

    @pytest.mark.asyncio
    async def test_load_result_structure(
        self, loader, mock_neo4j
    ):
        """LoadResult has correct structure and timing."""
        mock_neo4j.execute_query = AsyncMock(
            return_value=[{"cui": "C0000001"}]
        )
        mock_neo4j.execute_write_query = AsyncMock(
            return_value=[{"count": 0}]
        )

        mrrel_path = _create_temp_mrrel([])
        try:
            result = await loader.load_relationships(mrrel_path)
            assert isinstance(result, LoadResult)
            assert result.nodes_created == 0
            assert result.elapsed_seconds >= 0
            assert result.batches_failed == 0
        finally:
            os.unlink(mrrel_path)

    @pytest.mark.asyncio
    async def test_all_dangling_produces_zero_edges(
        self, loader, mock_neo4j
    ):
        """MRREL with all dangling CUIs produces zero edges."""
        mock_neo4j.execute_query = AsyncMock(
            return_value=[{"cui": "C9999999"}]
        )
        mock_neo4j.execute_write_query = AsyncMock(
            return_value=[{"count": 0}]
        )

        mrrel_lines = [
            "C0000001|A001|AUI|RO|C0000002|A002|AUI|treats|R001||MSH|MSH|0|Y|N|",
            "C0000003|A003|AUI|RB|C0000004|A004|AUI|causes|R002||MSH|MSH|0|Y|N|",
        ]
        mrrel_path = _create_temp_mrrel(mrrel_lines)
        try:
            result = await loader.load_relationships(mrrel_path)
            assert result.relationships_created == 0
            assert result.batches_completed == 0
        finally:
            os.unlink(mrrel_path)

    @pytest.mark.asyncio
    async def test_edge_properties_stored(
        self, loader, mock_neo4j
    ):
        """All required edge properties are passed to Neo4j."""
        mock_neo4j.execute_query = AsyncMock(
            return_value=[
                {"cui": "C0000001"},
                {"cui": "C0000002"},
            ]
        )
        mock_neo4j.execute_write_query = AsyncMock(
            return_value=[{"count": 1}]
        )

        mrrel_lines = [
            "C0000001|A001|AUI|RO|C0000002|A002|AUI|may_prevent|R001||SNOMEDCT_US|SNOMEDCT_US|0|Y|N|",
        ]
        mrrel_path = _create_temp_mrrel(mrrel_lines)
        try:
            await loader.load_relationships(mrrel_path)
            calls = mock_neo4j.execute_write_query.call_args_list
            rel_call = _find_call_with_param(calls, "rels")
            rel = rel_call[0][1]["rels"][0]
            assert rel["rel_type"] == "RO"
            assert rel["rela_type"] == "may_prevent"
            assert rel["source_vocabulary"] == "SNOMEDCT_US"
            assert rel["cui_pair"] == "C0000001-C0000002"
            assert rel["edge_type"] == "UMLS_may_prevent"
        finally:
            os.unlink(mrrel_path)


def _create_temp_mrrel(mrrel_lines):
    """Helper to create a temporary MRREL file."""
    mrrel_file = tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False
    )
    for line in mrrel_lines:
        mrrel_file.write(line + "\n")
    mrrel_file.close()
    return mrrel_file.name


def _create_temp_mrconso(mrconso_lines):
    """Helper to create a temporary MRCONSO file."""
    mrconso_file = tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False
    )
    for line in mrconso_lines:
        mrconso_file.write(line + "\n")
    mrconso_file.close()
    return mrconso_file.name


def _create_temp_files(mrconso_lines, mrsty_lines):
    """Helper to create temporary MRCONSO and MRSTY files."""
    mrconso_file = tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False
    )
    for line in mrconso_lines:
        mrconso_file.write(line + "\n")
    mrconso_file.close()

    mrsty_file = tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False
    )
    for line in mrsty_lines:
        mrsty_file.write(line + "\n")
    mrsty_file.close()

    return mrconso_file.name, mrsty_file.name


def _find_call_with_param(calls, param_name):
    """Find a mock call that has the given parameter name."""
    for call in calls:
        args = call[0]
        if len(args) > 1 and isinstance(args[1], dict):
            if param_name in args[1]:
                return call
    return None


class TestDryRun:
    """Tests for dry_run method."""

    @pytest.mark.asyncio
    async def test_mrconso_file_not_found(self, loader):
        """Raises FileNotFoundError for missing MRCONSO."""
        with pytest.raises(FileNotFoundError, match="MRCONSO"):
            await loader.dry_run(
                "/nonexistent/MRCONSO.csv",
                "/nonexistent/MRREL.csv",
            )

    @pytest.mark.asyncio
    async def test_mrrel_file_not_found(self, loader):
        """Raises FileNotFoundError for missing MRREL."""
        mrconso_lines = [
            "C0000001|ENG|P|L0000001|PF|S0000001|Y|A0000001|0|Aspirin|SNOMEDCT_US|PT|12345|Aspirin|0|N|256|",
        ]
        mrconso_path = _create_temp_mrconso(mrconso_lines)
        try:
            with pytest.raises(FileNotFoundError, match="MRREL"):
                await loader.dry_run(
                    mrconso_path,
                    "/nonexistent/MRREL.csv",
                )
        finally:
            os.unlink(mrconso_path)

    @pytest.mark.asyncio
    async def test_estimates_non_negative(self, loader):
        """Dry run returns non-negative estimates."""
        mrconso_lines = [
            "C0000001|ENG|P|L0000001|PF|S0000001|Y|A0000001|0|Aspirin|0|SNOMEDCT_US|PT|12345|Aspirin|0|N|256|",
            "C0000002|ENG|P|L0000002|PF|S0000002|Y|A0000002|0|Ibuprofen|0|MSH|PT|67890|Ibuprofen|0|N|256|",
        ]
        mrrel_lines = [
            "C0000001|A001|AUI|RO|C0000002|A002|AUI|may_treat|R001||SNOMEDCT_US|SNOMEDCT_US|0|Y|N|",
        ]
        mrconso_path = _create_temp_mrconso(mrconso_lines)
        mrrel_path = _create_temp_mrrel(mrrel_lines)
        try:
            result = await loader.dry_run(mrconso_path, mrrel_path)
            assert isinstance(result, DryRunResult)
            assert result.estimated_nodes >= 0
            assert result.estimated_relationships >= 0
            assert result.estimated_memory_mb >= 0
        finally:
            os.unlink(mrconso_path)
            os.unlink(mrrel_path)

    @pytest.mark.asyncio
    async def test_counts_unique_cuis(self, loader):
        """Dry run counts unique CUIs correctly."""
        mrconso_lines = [
            "C0000001|ENG|P|L0000001|PF|S0000001|Y|A0000001|0|Aspirin|0|SNOMEDCT_US|PT|12345|Aspirin|0|N|256|",
            "C0000001|ENG|S|L0000001|VO|S0000002|Y|A0000003|0|ASA|0|SNOMEDCT_US|SY|12346|ASA|0|N|256|",
            "C0000002|ENG|P|L0000002|PF|S0000002|Y|A0000002|0|Ibuprofen|0|MSH|PT|67890|Ibuprofen|0|N|256|",
        ]
        mrrel_lines = []
        mrconso_path = _create_temp_mrconso(mrconso_lines)
        mrrel_path = _create_temp_mrrel(mrrel_lines)
        try:
            result = await loader.dry_run(mrconso_path, mrrel_path)
            assert result.estimated_nodes == 2
        finally:
            os.unlink(mrconso_path)
            os.unlink(mrrel_path)

    @pytest.mark.asyncio
    async def test_filters_non_english(self, loader):
        """Dry run filters out non-English entries."""
        mrconso_lines = [
            "C0000001|ENG|P|L0000001|PF|S0000001|Y|A0000001|0|Aspirin|0|SNOMEDCT_US|PT|12345|Aspirin|0|N|256|",
            "C0000002|FRE|P|L0000002|PF|S0000002|Y|A0000002|0|Aspirine|0|MSH|PT|67890|Aspirine|0|N|256|",
        ]
        mrrel_lines = []
        mrconso_path = _create_temp_mrconso(mrconso_lines)
        mrrel_path = _create_temp_mrrel(mrrel_lines)
        try:
            result = await loader.dry_run(mrconso_path, mrrel_path)
            assert result.estimated_nodes == 1
        finally:
            os.unlink(mrconso_path)
            os.unlink(mrrel_path)

    @pytest.mark.asyncio
    async def test_source_vocab_filter(self, loader):
        """Dry run respects source vocabulary filter."""
        mrconso_lines = [
            "C0000001|ENG|P|L0000001|PF|S0000001|Y|A0000001|0|Aspirin|0|SNOMEDCT_US|PT|12345|Aspirin|0|N|256|",
            "C0000002|ENG|P|L0000002|PF|S0000002|Y|A0000002|0|Ibuprofen|0|MSH|PT|67890|Ibuprofen|0|N|256|",
        ]
        mrrel_lines = []
        mrconso_path = _create_temp_mrconso(mrconso_lines)
        mrrel_path = _create_temp_mrrel(mrrel_lines)
        try:
            result = await loader.dry_run(
                mrconso_path,
                mrrel_path,
                source_vocabs=["SNOMEDCT_US"],
            )
            assert result.estimated_nodes == 1
        finally:
            os.unlink(mrconso_path)
            os.unlink(mrrel_path)

    @pytest.mark.asyncio
    async def test_fits_in_budget_true(self, loader):
        """Small data fits in default budget."""
        mrconso_lines = [
            "C0000001|ENG|P|L0000001|PF|S0000001|Y|A0000001|0|Aspirin|0|SNOMEDCT_US|PT|12345|Aspirin|0|N|256|",
        ]
        mrrel_lines = []
        mrconso_path = _create_temp_mrconso(mrconso_lines)
        mrrel_path = _create_temp_mrrel(mrrel_lines)
        try:
            result = await loader.dry_run(mrconso_path, mrrel_path)
            assert result.fits_in_budget is True
            assert result.recommended_vocabs is None
        finally:
            os.unlink(mrconso_path)
            os.unlink(mrrel_path)

    @pytest.mark.asyncio
    async def test_fits_in_budget_false_recommends_vocabs(self, loader):
        """When over budget, fits_in_budget=False and vocabs recommended."""
        mrconso_lines = [
            "C0000001|ENG|P|L0000001|PF|S0000001|Y|A0000001|0|Aspirin|0|SNOMEDCT_US|PT|12345|Aspirin|0|N|256|",
        ]
        mrrel_lines = []
        mrconso_path = _create_temp_mrconso(mrconso_lines)
        mrrel_path = _create_temp_mrrel(mrrel_lines)
        try:
            # Use a tiny budget to force over-budget
            result = await loader.dry_run(
                mrconso_path,
                mrrel_path,
                memory_budget_mb=0,
            )
            assert result.fits_in_budget is False
            assert result.recommended_vocabs is not None
            assert "SNOMEDCT_US" in result.recommended_vocabs
            assert "MSH" in result.recommended_vocabs
            assert "RXNORM" in result.recommended_vocabs
        finally:
            os.unlink(mrconso_path)
            os.unlink(mrrel_path)

    @pytest.mark.asyncio
    async def test_relationship_count(self, loader):
        """Dry run counts relationships where both CUIs exist."""
        mrconso_lines = [
            "C0000001|ENG|P|L0000001|PF|S0000001|Y|A0000001|0|Aspirin|0|SNOMEDCT_US|PT|12345|Aspirin|0|N|256|",
            "C0000002|ENG|P|L0000002|PF|S0000002|Y|A0000002|0|Ibuprofen|0|SNOMEDCT_US|PT|67890|Ibuprofen|0|N|256|",
        ]
        mrrel_lines = [
            "C0000001|A001|AUI|RO|C0000002|A002|AUI|may_treat|R001||SNOMEDCT_US|SNOMEDCT_US|0|Y|N|",
            "C0000001|A001|AUI|RO|C9999999|A003|AUI|causes|R002||SNOMEDCT_US|SNOMEDCT_US|0|Y|N|",
        ]
        mrconso_path = _create_temp_mrconso(mrconso_lines)
        mrrel_path = _create_temp_mrrel(mrrel_lines)
        try:
            result = await loader.dry_run(mrconso_path, mrrel_path)
            # Only 1 relationship where both CUIs exist
            assert result.estimated_relationships == 1
        finally:
            os.unlink(mrconso_path)
            os.unlink(mrrel_path)


class TestRemoveAllUmlsData:
    """Tests for remove_all_umls_data method."""

    @pytest.mark.asyncio
    async def test_executes_all_delete_queries(
        self, loader, mock_neo4j
    ):
        """All 9 delete queries are executed (includes HAS_SYNONYM + UMLSSynonym)."""
        await loader.remove_all_umls_data()
        calls = mock_neo4j.execute_write_query.call_args_list
        assert len(calls) == 9

    @pytest.mark.asyncio
    async def test_deletes_relationships_before_nodes(
        self, loader, mock_neo4j
    ):
        """Relationships are deleted before nodes."""
        await loader.remove_all_umls_data()
        calls = mock_neo4j.execute_write_query.call_args_list
        queries = [call[0][0] for call in calls]
        # First 4 should be relationship deletions
        assert "UMLS_REL" in queries[0]
        assert "UMLS_SEMANTIC_REL" in queries[1]
        assert "HAS_SEMANTIC_TYPE" in queries[2]
        assert "HAS_SYNONYM" in queries[3]
        # Then node deletions
        assert "UMLSSynonym" in queries[4]
        assert "UMLSConcept" in queries[5]
        assert "UMLSSemanticType" in queries[6]
        assert "UMLSRelationshipDef" in queries[7]
        assert "UMLSMetadata" in queries[8]

    @pytest.mark.asyncio
    async def test_uses_detach_delete_for_nodes(
        self, loader, mock_neo4j
    ):
        """Node deletions use DETACH DELETE."""
        await loader.remove_all_umls_data()
        calls = mock_neo4j.execute_write_query.call_args_list
        queries = [call[0][0] for call in calls]
        # First 4 are relationship deletions (plain DELETE),
        # remaining 5 are node deletions (DETACH DELETE)
        for q in queries[4:]:
            assert "DETACH DELETE" in q


class TestGetUmlsStats:
    """Tests for get_umls_stats method."""

    @pytest.mark.asyncio
    async def test_returns_umls_stats(self, loader, mock_neo4j):
        """Returns UMLSStats with correct structure."""
        mock_neo4j.execute_query = AsyncMock(
            side_effect=[
                [{"count": 100}],  # concept count
                [{"count": 50}],   # semantic type count
                [{"count": 200}],  # relationship count
                [{"count": 15}],   # same_as count
                [{"count": 75}],   # has_semantic_type count
                [{                 # metadata
                    "loaded_tier": "full",
                    "umls_version": "2024AA",
                    "load_timestamp": "2024-01-01T00:00:00",
                }],
            ]
        )
        result = await loader.get_umls_stats()
        assert isinstance(result, UMLSStats)
        assert result.concept_count == 100
        assert result.semantic_type_count == 50
        assert result.relationship_count == 200
        assert result.same_as_count == 15
        assert result.has_semantic_type_count == 75
        assert result.loaded_tier == "full"
        assert result.umls_version == "2024AA"
        assert result.load_timestamp == "2024-01-01T00:00:00"

    @pytest.mark.asyncio
    async def test_no_metadata_returns_none_tier(
        self, loader, mock_neo4j
    ):
        """When no metadata exists, loaded_tier is 'none'."""
        mock_neo4j.execute_query = AsyncMock(
            side_effect=[
                [{"count": 0}],  # concept count
                [{"count": 0}],  # semantic type count
                [{"count": 0}],  # relationship count
                [{"count": 0}],  # same_as count
                [{"count": 0}],  # has_semantic_type count
                [],              # no metadata
            ]
        )
        result = await loader.get_umls_stats()
        assert result.loaded_tier == "none"
        assert result.umls_version is None
        assert result.load_timestamp is None

    @pytest.mark.asyncio
    async def test_empty_db_returns_zero_counts(
        self, loader, mock_neo4j
    ):
        """Empty database returns zero counts."""
        mock_neo4j.execute_query = AsyncMock(
            return_value=[]
        )
        result = await loader.get_umls_stats()
        assert result.concept_count == 0
        assert result.semantic_type_count == 0
        assert result.relationship_count == 0
        assert result.same_as_count == 0


class TestResumeImport:
    """Tests for resume_import method."""

    @pytest.mark.asyncio
    async def test_mrconso_file_not_found(self, loader):
        """Raises FileNotFoundError for missing MRCONSO."""
        with pytest.raises(FileNotFoundError, match="MRCONSO"):
            await loader.resume_import(
                "/nonexistent/MRCONSO.csv",
                mrsty_path="/nonexistent/MRSTY.txt",
            )

    @pytest.mark.asyncio
    async def test_no_previous_batch_starts_fresh(
        self, loader, mock_neo4j
    ):
        """When no previous batch, delegates to load_concepts."""
        mock_neo4j.execute_query = AsyncMock(
            return_value=[{"last_batch_number": 0}]
        )
        mock_neo4j.execute_write_query = AsyncMock(
            return_value=[{"count": 0}]
        )
        mrconso_lines = [
            "C0000001|ENG|P|L0000001|PF|S0000001|Y|A0000001|0|Aspirin|0|SNOMEDCT_US|PT|12345|Aspirin|0|N|256|",
        ]
        mrsty_lines = ["C0000001|T121|"]
        mrconso_path, mrsty_path = _create_temp_files(
            mrconso_lines, mrsty_lines
        )
        try:
            result = await loader.resume_import(
                mrconso_path, mrsty_path=mrsty_path
            )
            assert isinstance(result, LoadResult)
            # resumed_from_batch should be None (fresh start)
            assert result.resumed_from_batch is None
        finally:
            os.unlink(mrconso_path)
            os.unlink(mrsty_path)

    @pytest.mark.asyncio
    async def test_resumes_from_last_batch(
        self, loader, mock_neo4j
    ):
        """Resumes from last_batch_number stored in metadata."""
        mock_neo4j.execute_query = AsyncMock(
            return_value=[{"last_batch_number": 2}]
        )
        mock_neo4j.execute_write_query = AsyncMock(
            return_value=[{"count": 1}]
        )
        # Create enough concepts for 3 batches with batch_size=1
        mrconso_lines = [
            "C0000001|ENG|P|L0000001|PF|S0000001|Y|A0000001|0|Aspirin|0|SNOMEDCT_US|PT|12345|Aspirin|0|N|256|",
            "C0000002|ENG|P|L0000002|PF|S0000002|Y|A0000002|0|Ibuprofen|0|SNOMEDCT_US|PT|67890|Ibuprofen|0|N|256|",
            "C0000003|ENG|P|L0000003|PF|S0000003|Y|A0000003|0|Tylenol|0|SNOMEDCT_US|PT|11111|Tylenol|0|N|256|",
        ]
        mrsty_lines = ["C0000003|T121|"]
        mrconso_path, mrsty_path = _create_temp_files(
            mrconso_lines, mrsty_lines
        )
        try:
            result = await loader.resume_import(
                mrconso_path,
                mrsty_path=mrsty_path,
                batch_size=1,
            )
            assert isinstance(result, LoadResult)
            assert result.resumed_from_batch == 2
        finally:
            os.unlink(mrconso_path)
            os.unlink(mrsty_path)


class TestBatchRetry:
    """Tests for _execute_batch_with_retry method."""

    @pytest.mark.asyncio
    async def test_succeeds_on_first_try(self, loader, mock_neo4j):
        """Returns result when first attempt succeeds."""
        mock_neo4j.execute_write_query = AsyncMock(
            return_value=[{"count": 5}]
        )
        result = await loader._execute_batch_with_retry(
            "RETURN 1", {}
        )
        assert result == [{"count": 5}]
        assert mock_neo4j.execute_write_query.call_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_failure(self, loader, mock_neo4j):
        """Retries after failure and succeeds."""
        mock_neo4j.execute_write_query = AsyncMock(
            side_effect=[
                Exception("Connection lost"),
                [{"count": 5}],
            ]
        )
        result = await loader._execute_batch_with_retry(
            "RETURN 1", {}, max_retries=3
        )
        assert result == [{"count": 5}]
        assert mock_neo4j.execute_write_query.call_count == 2

    @pytest.mark.asyncio
    async def test_raises_after_all_retries_exhausted(
        self, loader, mock_neo4j
    ):
        """Raises exception after all retries exhausted."""
        mock_neo4j.execute_write_query = AsyncMock(
            side_effect=Exception("Persistent failure")
        )
        with pytest.raises(Exception, match="Persistent failure"):
            await loader._execute_batch_with_retry(
                "RETURN 1", {}, max_retries=3
            )
        # 1 initial + 3 retries = 4 total attempts
        assert mock_neo4j.execute_write_query.call_count == 4

    @pytest.mark.asyncio
    async def test_succeeds_on_last_retry(
        self, loader, mock_neo4j
    ):
        """Succeeds on the final retry attempt."""
        mock_neo4j.execute_write_query = AsyncMock(
            side_effect=[
                Exception("Fail 1"),
                Exception("Fail 2"),
                Exception("Fail 3"),
                [{"count": 1}],
            ]
        )
        result = await loader._execute_batch_with_retry(
            "RETURN 1", {}, max_retries=3
        )
        assert result == [{"count": 1}]
        assert mock_neo4j.execute_write_query.call_count == 4


class TestVersionReplacement:
    """Tests for version replacement in load_concepts."""

    @pytest.mark.asyncio
    async def test_removes_previous_data_before_import(
        self, loader, mock_neo4j
    ):
        """When previous UMLS data exists, it is removed first."""
        # First call returns metadata (version check),
        # subsequent calls return default
        call_count = 0

        async def side_effect_query(query, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            if "UMLSMetadata" in query and "loaded_tier" in query:
                return [{
                    "loaded_tier": "full",
                    "umls_version": "2023AB",
                }]
            return []

        mock_neo4j.execute_query = AsyncMock(
            side_effect=side_effect_query
        )
        mock_neo4j.execute_write_query = AsyncMock(
            return_value=[{"count": 0}]
        )

        mrconso_lines = [
            "C0000001|ENG|P|L0000001|PF|S0000001|Y|A0000001|0|Aspirin|0|SNOMEDCT_US|PT|12345|Aspirin|0|N|256|",
        ]
        mrsty_lines = ["C0000001|T121|"]
        mrconso_path, mrsty_path = _create_temp_files(
            mrconso_lines, mrsty_lines
        )
        try:
            await loader.load_concepts(mrconso_path, mrsty_path)
            # Verify _remove_concept_data was called (4 targeted
            # delete queries — preserves semantic types/rel defs)
            write_calls = mock_neo4j.execute_write_query.call_args_list
            delete_queries = [
                c for c in write_calls
                if "DELETE" in c[0][0]
            ]
            assert len(delete_queries) >= 4
        finally:
            os.unlink(mrconso_path)
            os.unlink(mrsty_path)
