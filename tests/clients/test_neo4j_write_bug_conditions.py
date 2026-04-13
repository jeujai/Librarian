"""
Bug Condition Exploration Tests — Neo4j Write Timeout (Property 1)

These tests encode the EXPECTED (fixed) behavior. They are designed to
FAIL on the current unfixed code, proving the bug exists. Once the fix
is applied, these same tests should PASS.

Bug conditions tested:
  1a. transient_failure — _run_write_session has no retry for TransientError
  1b. batch_too_large  — _CONCEPT_REL_SUB_BATCH defaults to 500 (should be ≤100)
  1c. silent_data_loss  — failed MERGE batches are not retried
  1d. full_scan_bridge  — create_same_as_edges scans ALL concepts, not doc-scoped
  1e. no_client_timeout — execute_write_query has no asyncio.wait_for wrapper
"""

import asyncio
import inspect
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from neo4j.exceptions import TransientError

from src.multimodal_librarian.clients.neo4j_client import Neo4jClient
from src.multimodal_librarian.clients.protocols import QueryError

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def neo4j_client():
    """Create a Neo4jClient with a mocked driver for unit testing."""
    client = Neo4jClient(
        uri="bolt://localhost:7687",
        user="neo4j",
        password="test",
        database="neo4j",
    )
    client.driver = MagicMock()
    client._is_connected = True
    return client


# ---------------------------------------------------------------------------
# Test 1a: transient_failure — _run_write_session should retry TransientError
# ---------------------------------------------------------------------------

class TestTransientFailureRetry:
    """Bug Condition: _run_write_session raises TransientError without retry."""

    @pytest.mark.asyncio
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=10000,
    )
    @given(
        fail_count=st.integers(min_value=1, max_value=2),
    )
    async def test_1a_write_session_retries_transient_error(
        self, neo4j_client, fail_count
    ):
        """_run_write_session should retry up to 3 times on TransientError.

        On unfixed code this FAILS because _run_write_session has no retry
        loop — the first TransientError propagates immediately.
        """
        call_count = 0
        expected_result = [{"id": 1}]

        async def mock_execute_write(write_fn):
            nonlocal call_count
            call_count += 1
            if call_count <= fail_count:
                raise TransientError("transaction timeout")
            # Simulate calling the write_fn and returning results
            return expected_result

        mock_session = AsyncMock()
        mock_session.execute_write = mock_execute_write
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        neo4j_client.driver.session.return_value = mock_session

        result = await neo4j_client._run_write_session(
            "MERGE (n:Test {id: $id}) RETURN n",
            {"id": 1},
        )

        # Expected: retried and eventually succeeded
        assert result == expected_result
        assert call_count == fail_count + 1, (
            f"Expected {fail_count + 1} attempts but got {call_count}"
        )


# ---------------------------------------------------------------------------
# Test 1b: batch_too_large — _CONCEPT_REL_SUB_BATCH should be ≤ 100
# ---------------------------------------------------------------------------

class TestBatchSizeTooLarge:
    """Bug Condition: _CONCEPT_REL_SUB_BATCH defaults to 500 for scale_factor=1."""

    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        total_chunks=st.integers(min_value=1, max_value=999),
    )
    def test_1b_concept_rel_sub_batch_within_limit(self, total_chunks):
        """For documents under 1000 chunks (scale_factor=1), sub-batch ≤ 100.

        On unfixed code this FAILS because the formula was
        max(50, 500 // 1) = 500. The fix changes it to max(25, 100 // 1) = 100.

        We read the actual formula from celery_service source to verify.
        """
        import re

        import src.multimodal_librarian.services.celery_service as cs

        source = inspect.getsource(cs._update_knowledge_graph)

        # Extract the _CONCEPT_REL_SUB_BATCH formula from source
        match = re.search(
            r"_CONCEPT_REL_SUB_BATCH\s*=\s*max\((\d+),\s*(\d+)\s*//\s*_scale_factor\)",
            source,
        )
        assert match is not None, (
            "_CONCEPT_REL_SUB_BATCH formula not found in _update_knowledge_graph"
        )

        floor_val = int(match.group(1))
        numerator = int(match.group(2))

        _scale_factor = max(1, total_chunks // 1000)
        _CONCEPT_REL_SUB_BATCH = max(floor_val, numerator // _scale_factor)

        assert _CONCEPT_REL_SUB_BATCH <= 100, (
            f"_CONCEPT_REL_SUB_BATCH={_CONCEPT_REL_SUB_BATCH} exceeds 100 "
            f"for {total_chunks} chunks (scale_factor={_scale_factor})"
        )


# ---------------------------------------------------------------------------
# Test 1c: silent_data_loss — failed MERGE batches should be retried
# ---------------------------------------------------------------------------

class TestSilentDataLoss:
    """Bug Condition: failed MERGE batches log warning with zero retries."""

    def test_1c_failed_merge_batch_is_retried(self):
        """A failed MERGE sub-batch should be retried before logging warning.

        On unfixed code this FAILS because the try/except blocks around
        MERGE operations in _update_knowledge_graph just log and continue
        with no retry attempt.
        """
        import src.multimodal_librarian.services.celery_service as cs

        source = inspect.getsource(cs._update_knowledge_graph)

        # The fix should introduce a dedicated retry helper that wraps
        # MERGE operations.
        has_retry_helper = "_execute_with_retry" in source

        if not has_retry_helper:
            # The unfixed code has bare try/except blocks with "MERGE failed"
            # warnings and no retry. Count them — if any exist, the bug is
            # present.
            bare_except_count = source.count("MERGE failed")
            assert bare_except_count == 0, (
                f"Found {bare_except_count} bare 'MERGE failed' warning(s) "
                f"with no retry mechanism — failed batches are silently lost"
            )


# ---------------------------------------------------------------------------
# Test 1d: full_scan_bridge — create_same_as_edges scans ALL concepts
# ---------------------------------------------------------------------------

class TestFullScanBridge:
    """Bug Condition: create_same_as_edges fetches ALL concepts, not doc-scoped."""

    @pytest.mark.asyncio
    async def test_1d_create_same_as_edges_fetches_all_concepts(self):
        """create_same_as_edges calls _fetch_concept_names which runs
        MATCH (c:Concept) RETURN DISTINCT c.concept_name — a full graph scan.

        On unfixed code this FAILS because there is no document-scoped
        bridging method; the celery service always calls create_same_as_edges.
        """
        from src.multimodal_librarian.components.knowledge_graph.umls_bridger import (
            UMLSBridger,
        )

        # Verify UMLSBridger has a document-scoped bridge_concepts method
        has_bridge_concepts = hasattr(UMLSBridger, "bridge_concepts")
        assert has_bridge_concepts, (
            "UMLSBridger has no bridge_concepts() method — only the full "
            "graph scan create_same_as_edges() is available"
        )

        # Verify the celery service calls bridge_concepts (incremental)
        # rather than create_same_as_edges (full scan)
        import src.multimodal_librarian.services.celery_service as cs
        kg_source = inspect.getsource(cs._update_knowledge_graph)

        has_incremental_bridge = "bridge_concepts" in kg_source

        assert has_incremental_bridge, (
            "celery_service calls create_same_as_edges() (full graph scan) "
            "instead of an incremental bridge_concepts() method"
        )


# ---------------------------------------------------------------------------
# Test 1e: no_client_timeout — execute_write_query has no asyncio.wait_for
# ---------------------------------------------------------------------------

class TestNoClientTimeout:
    """Bug Condition: execute_write_query has no client-side timeout."""

    def test_1e_execute_write_query_has_timeout_enforcement(self):
        """execute_write_query should wrap the write call with
        asyncio.wait_for to enforce a client-side timeout.

        On unfixed code this FAILS because there is no wait_for wrapper.
        """
        source = inspect.getsource(Neo4jClient.execute_write_query)

        has_wait_for = "wait_for" in source
        has_timeout_param = "write_timeout" in source

        assert has_wait_for and has_timeout_param, (
            "execute_write_query has no asyncio.wait_for timeout enforcement — "
            "writes can hang indefinitely"
        )

    def test_1e_init_has_write_timeout_parameter(self):
        """Neo4jClient.__init__ should accept a write_timeout parameter.

        On unfixed code this FAILS because no such parameter exists.
        """
        sig = inspect.signature(Neo4jClient.__init__)
        assert "write_timeout" in sig.parameters, (
            "Neo4jClient.__init__ does not have a write_timeout parameter"
        )
