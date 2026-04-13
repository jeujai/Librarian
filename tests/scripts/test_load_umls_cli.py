"""Unit tests for the UMLS Knowledge Graph Loader CLI (scripts/load_umls.py).

Covers argument parsing, subcommand routing, default values,
execution order, and flag-triggered behaviour.
"""

import argparse
import os
import sys
import tempfile
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

# The CLI lives outside the package tree, so we import its helpers directly.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
from load_umls import (  # noqa: E402
    TARGETED_VOCABULARY_SET,
    _resolve_neo4j_args,
    build_parser,
    cmd_bridge,
    cmd_clean,
    cmd_dry_run,
    cmd_load,
    cmd_stats,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def parser():
    """Return a fresh argparse parser."""
    return build_parser()


@pytest.fixture
def tmp_rrf_dir():
    """Create a temp directory with the two required RRF files."""
    with tempfile.TemporaryDirectory() as d:
        for name in ("MRCONSO.RRF", "MRREL.RRF"):
            open(os.path.join(d, name), "w").close()
        yield d


# ---------------------------------------------------------------------------
# Subcommand acceptance
# ---------------------------------------------------------------------------


class TestSubcommandAcceptance:
    """Verify argparse accepts all five subcommands."""

    @pytest.mark.parametrize("cmd", ["dry-run", "load", "bridge", "stats", "clean"])
    def test_subcommand_recognised(self, parser, cmd, tmp_rrf_dir):
        """Each subcommand should parse without error."""
        extra = [tmp_rrf_dir] if cmd in ("dry-run", "load") else []
        args = parser.parse_args([cmd] + extra)
        assert args.command == cmd

    def test_no_subcommand_sets_none(self, parser):
        """No subcommand should leave command as None."""
        args = parser.parse_args([])
        assert args.command is None


# ---------------------------------------------------------------------------
# Load subcommand arguments
# ---------------------------------------------------------------------------


class TestLoadArguments:
    """Verify the load subcommand accepts all documented arguments."""

    def test_defaults(self, parser, tmp_rrf_dir):
        args = parser.parse_args(["load", tmp_rrf_dir])
        assert args.rrf_dir == tmp_rrf_dir
        assert args.vocabs == TARGETED_VOCABULARY_SET
        assert args.batch_size == 5000
        assert args.rel_batch_size == 10000
        assert args.memory_limit is None
        assert args.resume is False
        assert args.bridge is False
        assert args.check_config is False

    def test_custom_vocabs(self, parser, tmp_rrf_dir):
        args = parser.parse_args(["load", tmp_rrf_dir, "--vocabs", "MSH", "HPO"])
        assert args.vocabs == ["MSH", "HPO"]

    def test_batch_sizes(self, parser, tmp_rrf_dir):
        args = parser.parse_args([
            "load", tmp_rrf_dir,
            "--batch-size", "2000",
            "--rel-batch-size", "5000",
        ])
        assert args.batch_size == 2000
        assert args.rel_batch_size == 5000

    def test_memory_limit(self, parser, tmp_rrf_dir):
        args = parser.parse_args(["load", tmp_rrf_dir, "--memory-limit", "4096"])
        assert args.memory_limit == 4096

    def test_resume_flag(self, parser, tmp_rrf_dir):
        args = parser.parse_args(["load", tmp_rrf_dir, "--resume"])
        assert args.resume is True

    def test_bridge_flag(self, parser, tmp_rrf_dir):
        args = parser.parse_args(["load", tmp_rrf_dir, "--bridge"])
        assert args.bridge is True

    def test_check_config_flag(self, parser, tmp_rrf_dir):
        args = parser.parse_args(["load", tmp_rrf_dir, "--check-config"])
        assert args.check_config is True


# ---------------------------------------------------------------------------
# Default vocabulary set
# ---------------------------------------------------------------------------


class TestDefaultVocabularySet:
    """Verify the default vocabulary set is the Targeted_Vocabulary_Set."""

    def test_targeted_set_contents(self):
        assert set(TARGETED_VOCABULARY_SET) == {
            "SNOMEDCT_US", "MSH", "ICD10CM", "RXNORM", "LNC", "HPO",
            "MED-RT", "ICD10PCS", "ATC",
        }

    def test_load_defaults_to_targeted_set(self, parser, tmp_rrf_dir):
        args = parser.parse_args(["load", tmp_rrf_dir])
        assert args.vocabs == TARGETED_VOCABULARY_SET

    def test_dry_run_defaults_to_targeted_set(self, parser, tmp_rrf_dir):
        args = parser.parse_args(["dry-run", tmp_rrf_dir])
        assert args.vocabs == TARGETED_VOCABULARY_SET


# ---------------------------------------------------------------------------
# Neo4j argument resolution
# ---------------------------------------------------------------------------


class TestNeo4jArgResolution:
    """Verify --neo4j-* args override environment variables."""

    def test_cli_args_override_env(self, parser, tmp_rrf_dir):
        args = parser.parse_args([
            "load", tmp_rrf_dir,
            "--neo4j-uri", "bolt://custom:7687",
            "--neo4j-user", "admin",
            "--neo4j-password", "secret",
        ])
        conn = _resolve_neo4j_args(args)
        assert conn["uri"] == "bolt://custom:7687"
        assert conn["user"] == "admin"
        assert conn["password"] == "secret"

    def test_env_vars_used_when_no_cli_args(self, parser, tmp_rrf_dir):
        args = parser.parse_args(["load", tmp_rrf_dir])
        with patch.dict(os.environ, {
            "NEO4J_URI": "bolt://env:7687",
            "NEO4J_USER": "envuser",
            "NEO4J_PASSWORD": "envpass",
        }):
            conn = _resolve_neo4j_args(args)
        assert conn["uri"] == "bolt://env:7687"
        assert conn["user"] == "envuser"
        assert conn["password"] == "envpass"

    def test_fallback_defaults(self, parser, tmp_rrf_dir):
        args = parser.parse_args(["load", tmp_rrf_dir])
        with patch.dict(os.environ, {}, clear=True):
            # Remove any existing NEO4J_* vars
            for key in ("NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD"):
                os.environ.pop(key, None)
            conn = _resolve_neo4j_args(args)
        assert conn["uri"] == "bolt://localhost:7687"
        assert conn["user"] == "neo4j"
        assert conn["password"] == "password"


# ---------------------------------------------------------------------------
# Clean subcommand --confirm flag
# ---------------------------------------------------------------------------


class TestCleanConfirm:
    """Verify clean prompts without --confirm and skips prompt with it."""

    def test_confirm_flag_parsed(self, parser):
        args = parser.parse_args(["clean", "--confirm"])
        assert args.confirm is True

    def test_no_confirm_defaults_false(self, parser):
        args = parser.parse_args(["clean"])
        assert args.confirm is False

    @pytest.mark.asyncio
    async def test_clean_without_confirm_prompts_user(self, parser):
        """Without --confirm, cmd_clean should call input() for confirmation."""
        args = parser.parse_args(["clean"])
        with patch("load_umls.input", return_value="n") as mock_input:
            await cmd_clean(args)
            mock_input.assert_called_once()

    @pytest.mark.asyncio
    async def test_clean_with_confirm_skips_prompt(self, parser):
        """With --confirm, cmd_clean should NOT call input()."""
        args = parser.parse_args(["clean", "--confirm"])

        mock_client = MagicMock()
        mock_client.connect = AsyncMock()
        mock_client.close = AsyncMock()

        mock_loader = MagicMock()
        mock_loader.remove_all_umls_data_with_counts = AsyncMock(return_value={})

        with (
            patch("load_umls._create_neo4j_client", new_callable=AsyncMock, return_value=mock_client),
            patch("load_umls.input", side_effect=AssertionError("should not prompt")) as mock_input,
            patch("multimodal_librarian.components.knowledge_graph.umls_loader.UMLSLoader", return_value=mock_loader),
        ):
            await cmd_clean(args)
            mock_input.assert_not_called()


# ---------------------------------------------------------------------------
# Check-config output format
# ---------------------------------------------------------------------------


class TestCheckConfig:
    """Verify --check-config output format from cmd_load."""

    @pytest.mark.asyncio
    async def test_check_config_runs_before_load(self, parser, tmp_rrf_dir):
        """--check-config should call check_neo4j_config before loading."""
        args = parser.parse_args(["load", tmp_rrf_dir, "--check-config"])

        mock_client = MagicMock()
        mock_client.connect = AsyncMock()
        mock_client.close = AsyncMock()

        mock_loader = MagicMock()
        mock_loader.check_neo4j_config = AsyncMock(return_value={
            "current": {"heap_size": "4g", "page_cache_size": "2g"},
            "sufficient": False,
            "issues": ["Heap below 5 GB"],
            "docker_compose_recommendations": {
                "NEO4J_server_memory_heap_max__size": "6g",
            },
        })
        mock_loader.create_indexes = AsyncMock()
        mock_loader.load_semantic_network = AsyncMock(return_value=LoadResult(
            nodes_created=0, relationships_created=0,
            batches_completed=0, batches_failed=0, elapsed_seconds=0.0,
        ))
        mock_loader.load_concepts = AsyncMock(return_value=LoadResult(
            nodes_created=10, relationships_created=5,
            batches_completed=1, batches_failed=0, elapsed_seconds=1.0,
        ))
        mock_loader.load_definitions = AsyncMock(return_value=LoadResult(
            nodes_created=3, relationships_created=0,
            batches_completed=1, batches_failed=0, elapsed_seconds=0.5,
        ))
        mock_loader.load_relationships = AsyncMock(return_value=LoadResult(
            nodes_created=0, relationships_created=20,
            batches_completed=1, batches_failed=0, elapsed_seconds=1.0,
        ))

        with (
            patch("load_umls._create_neo4j_client", new_callable=AsyncMock, return_value=mock_client),
            patch("multimodal_librarian.components.knowledge_graph.umls_loader.UMLSLoader", return_value=mock_loader),
        ):
            await cmd_load(args)

        mock_loader.check_neo4j_config.assert_awaited_once()


# ---------------------------------------------------------------------------
# Load execution order
# ---------------------------------------------------------------------------


from multimodal_librarian.components.knowledge_graph.umls_loader import LoadResult


class TestLoadExecutionOrder:
    """Verify cmd_load calls steps in the correct order."""

    @pytest.mark.asyncio
    async def test_execution_order(self, parser, tmp_rrf_dir):
        """Load should execute: indexes → SRDEF → concepts → defs → rels."""
        # Add optional files so all steps run
        for name in ("MRSTY.RRF", "MRDEF.RRF", "SRDEF"):
            open(os.path.join(tmp_rrf_dir, name), "w").close()

        args = parser.parse_args(["load", tmp_rrf_dir])

        mock_client = MagicMock()
        mock_client.connect = AsyncMock()
        mock_client.close = AsyncMock()

        call_order = []
        _lr = LoadResult(
            nodes_created=0, relationships_created=0,
            batches_completed=0, batches_failed=0, elapsed_seconds=0.0,
        )

        def _track(name):
            """Return a side_effect function that records the call and returns a LoadResult."""
            def _side_effect(*a, **kw):
                call_order.append(name)
                return _lr
            return _side_effect

        mock_loader = MagicMock()
        mock_loader.create_indexes = AsyncMock(side_effect=lambda: call_order.append("create_indexes"))
        mock_loader.load_semantic_network = AsyncMock(side_effect=_track("load_semantic_network"))
        mock_loader.load_concepts = AsyncMock(side_effect=_track("load_concepts"))
        mock_loader.load_definitions = AsyncMock(side_effect=_track("load_definitions"))
        mock_loader.load_relationships = AsyncMock(side_effect=_track("load_relationships"))

        with (
            patch("load_umls._create_neo4j_client", new_callable=AsyncMock, return_value=mock_client),
            patch("multimodal_librarian.components.knowledge_graph.umls_loader.UMLSLoader", return_value=mock_loader),
        ):
            await cmd_load(args)

        assert call_order == [
            "create_indexes",
            "load_semantic_network",
            "load_concepts",
            "load_definitions",
            "load_relationships",
        ]

    @pytest.mark.asyncio
    async def test_bridge_flag_triggers_bridging_after_load(self, parser, tmp_rrf_dir):
        """--bridge should run UMLSBridger.create_same_as_edges after load."""
        args = parser.parse_args(["load", tmp_rrf_dir, "--bridge"])

        mock_client = MagicMock()
        mock_client.connect = AsyncMock()
        mock_client.close = AsyncMock()

        _lr = LoadResult(
            nodes_created=0, relationships_created=0,
            batches_completed=0, batches_failed=0, elapsed_seconds=0.0,
        )
        mock_loader = MagicMock()
        mock_loader.create_indexes = AsyncMock()
        mock_loader.load_concepts = AsyncMock(return_value=_lr)
        mock_loader.load_relationships = AsyncMock(return_value=_lr)

        from multimodal_librarian.components.knowledge_graph.umls_bridger import (
            BridgeResult,
        )

        mock_bridger = MagicMock()
        mock_bridger.create_same_as_edges = AsyncMock(return_value=BridgeResult(
            concepts_matched=5, same_as_edges_created=5,
            unmatched_concepts=0, elapsed_seconds=0.1,
        ))

        with (
            patch("load_umls._create_neo4j_client", new_callable=AsyncMock, return_value=mock_client),
            patch("multimodal_librarian.components.knowledge_graph.umls_loader.UMLSLoader", return_value=mock_loader),
            patch("multimodal_librarian.components.knowledge_graph.umls_bridger.UMLSBridger", return_value=mock_bridger),
        ):
            await cmd_load(args)

        mock_bridger.create_same_as_edges.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_bridge_flag_skips_bridging(self, parser, tmp_rrf_dir):
        """Without --bridge, bridging should not run."""
        args = parser.parse_args(["load", tmp_rrf_dir])

        mock_client = MagicMock()
        mock_client.connect = AsyncMock()
        mock_client.close = AsyncMock()

        _lr = LoadResult(
            nodes_created=0, relationships_created=0,
            batches_completed=0, batches_failed=0, elapsed_seconds=0.0,
        )
        mock_loader = MagicMock()
        mock_loader.create_indexes = AsyncMock()
        mock_loader.load_concepts = AsyncMock(return_value=_lr)
        mock_loader.load_relationships = AsyncMock(return_value=_lr)

        with (
            patch("load_umls._create_neo4j_client", new_callable=AsyncMock, return_value=mock_client),
            patch("multimodal_librarian.components.knowledge_graph.umls_loader.UMLSLoader", return_value=mock_loader),
            patch("multimodal_librarian.components.knowledge_graph.umls_bridger.UMLSBridger") as mock_bridger_cls,
        ):
            await cmd_load(args)

        mock_bridger_cls.assert_not_called()


# ---------------------------------------------------------------------------
# Stats subcommand
# ---------------------------------------------------------------------------


class TestStatsSubcommand:
    """Verify cmd_stats calls get_umls_stats and displays results."""

    @pytest.mark.asyncio
    async def test_stats_calls_get_umls_stats(self, parser):
        args = parser.parse_args(["stats"])

        mock_client = MagicMock()
        mock_client.connect = AsyncMock()
        mock_client.close = AsyncMock()

        from multimodal_librarian.components.knowledge_graph.umls_loader import (
            UMLSStats,
        )

        mock_loader = MagicMock()
        mock_loader.get_umls_stats = AsyncMock(return_value=UMLSStats(
            concept_count=100,
            semantic_type_count=10,
            relationship_count=200,
            same_as_count=50,
            loaded_tier="full",
            umls_version="2024AA",
            load_timestamp="2024-01-01T00:00:00",
        ))

        with (
            patch("load_umls._create_neo4j_client", new_callable=AsyncMock, return_value=mock_client),
            patch("multimodal_librarian.components.knowledge_graph.umls_loader.UMLSLoader", return_value=mock_loader),
        ):
            await cmd_stats(args)

        mock_loader.get_umls_stats.assert_awaited_once()


# ---------------------------------------------------------------------------
# Bridge subcommand
# ---------------------------------------------------------------------------


class TestBridgeSubcommand:
    """Verify cmd_bridge calls create_same_as_edges."""

    @pytest.mark.asyncio
    async def test_bridge_calls_create_same_as_edges(self, parser):
        args = parser.parse_args(["bridge"])

        mock_client = MagicMock()
        mock_client.connect = AsyncMock()
        mock_client.close = AsyncMock()

        from multimodal_librarian.components.knowledge_graph.umls_bridger import (
            BridgeResult,
        )

        mock_bridger = MagicMock()
        mock_bridger.create_same_as_edges = AsyncMock(return_value=BridgeResult(
            concepts_matched=3, same_as_edges_created=3,
            unmatched_concepts=1, elapsed_seconds=0.5,
        ))

        with (
            patch("load_umls._create_neo4j_client", new_callable=AsyncMock, return_value=mock_client),
            patch("multimodal_librarian.components.knowledge_graph.umls_bridger.UMLSBridger", return_value=mock_bridger),
        ):
            await cmd_bridge(args)

        mock_bridger.create_same_as_edges.assert_awaited_once()


# ---------------------------------------------------------------------------
# Dry-run subcommand
# ---------------------------------------------------------------------------


class TestDryRunSubcommand:
    """Verify cmd_dry_run validates directory and calls dry_run."""

    @pytest.mark.asyncio
    async def test_dry_run_calls_loader_dry_run(self, parser, tmp_rrf_dir):
        args = parser.parse_args(["dry-run", tmp_rrf_dir])

        mock_client = MagicMock()
        mock_client.connect = AsyncMock()
        mock_client.close = AsyncMock()

        from multimodal_librarian.components.knowledge_graph.umls_loader import (
            DryRunResult,
        )

        mock_loader = MagicMock()
        mock_loader.dry_run = AsyncMock(return_value=DryRunResult(
            estimated_nodes=1000,
            estimated_relationships=5000,
            estimated_memory_mb=512.0,
            fits_in_budget=True,
        ))

        with (
            patch("load_umls._create_neo4j_client", new_callable=AsyncMock, return_value=mock_client),
            patch("multimodal_librarian.components.knowledge_graph.umls_loader.UMLSLoader", return_value=mock_loader),
        ):
            await cmd_dry_run(args)

        mock_loader.dry_run.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_dry_run_exits_on_missing_required_files(self, parser):
        """dry-run should sys.exit(1) if required RRF files are missing."""
        with tempfile.TemporaryDirectory() as empty_dir:
            args = parser.parse_args(["dry-run", empty_dir])
            with pytest.raises(SystemExit) as exc_info:
                await cmd_dry_run(args)
            assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# SRDEF missing is non-fatal
# ---------------------------------------------------------------------------


class TestSRDEFMissing:
    """Verify load continues when SRDEF is absent."""

    @pytest.mark.asyncio
    async def test_load_skips_srdef_gracefully(self, parser, tmp_rrf_dir):
        """Load should skip SRDEF step without error when file is missing."""
        args = parser.parse_args(["load", tmp_rrf_dir])

        mock_client = MagicMock()
        mock_client.connect = AsyncMock()
        mock_client.close = AsyncMock()

        _lr = LoadResult(
            nodes_created=0, relationships_created=0,
            batches_completed=0, batches_failed=0, elapsed_seconds=0.0,
        )
        mock_loader = MagicMock()
        mock_loader.create_indexes = AsyncMock()
        mock_loader.load_semantic_network = AsyncMock(return_value=_lr)
        mock_loader.load_concepts = AsyncMock(return_value=_lr)
        mock_loader.load_relationships = AsyncMock(return_value=_lr)

        with (
            patch("load_umls._create_neo4j_client", new_callable=AsyncMock, return_value=mock_client),
            patch("multimodal_librarian.components.knowledge_graph.umls_loader.UMLSLoader", return_value=mock_loader),
        ):
            # Should not raise
            await cmd_load(args)

        # load_semantic_network should NOT have been called (no SRDEF)
        mock_loader.load_semantic_network.assert_not_awaited()
