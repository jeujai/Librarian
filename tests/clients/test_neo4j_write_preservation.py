"""
Preservation Property Tests — Neo4j Write Timeout Bugfix (Property 2)

These tests capture the CURRENT (unfixed) behavior that MUST be preserved
after the fix is applied.  They are written using observation-first
methodology: each test encodes behavior observed on the unfixed code and
must PASS both before and after the fix.

Preservation properties tested:
  2a. Read-path TransientError retry (3 retries, exponential backoff)
  2b. Successful first-attempt writes return immediately
  2c. TCP transport closed -> reconnect and retry exactly once
  2d. UMLS bridging skipped when umls_linker is None
  2e. Document deletion mid-processing aborts gracefully
"""

import inspect
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from neo4j.exceptions import TransientError

from src.multimodal_librarian.clients.neo4j_client import Neo4jClient
from src.multimodal_librarian.clients.protocols import QueryError

# -------------------------------------------------------------------
# Fixtures
# -------------------------------------------------------------------

@pytest.fixture
def neo4j_client():
    """Neo4jClient with a mocked driver for unit testing."""
    client = Neo4jClient(
        uri="bolt://localhost:7687",
        user="neo4j",
        password="test",
        database="neo4j",
    )
    client.driver = MagicMock()
    client._is_connected = True
    return client


# -------------------------------------------------------------------
# Test 2a -- Read-path TransientError retry preserved
# -------------------------------------------------------------------

class TestReadPathRetryPreservation:
    """Preservation: _run_query_session retries TransientError
    up to 3 times with exponential backoff."""

    @pytest.mark.asyncio
    @settings(
        max_examples=20,
        suppress_health_check=[
            HealthCheck.function_scoped_fixture,
        ],
        deadline=15000,
    )
    @given(
        fail_on_attempt=st.integers(min_value=1, max_value=2),
    )
    async def test_2a_read_retries_transient_and_succeeds(
        self, neo4j_client, fail_on_attempt
    ):
        """For read queries that raise TransientError on attempt N
        (N in {1,2}), _run_query_session retries and eventually
        succeeds.  Retry count and backoff timing must match the
        unfixed code: sleep = 0.1 * 2^retry_count (0.2s, 0.4s).
        """
        call_count = 0

        async def mock_run(query, params):
            nonlocal call_count
            call_count += 1
            if call_count <= fail_on_attempt:
                raise TransientError("transient read error")

            mock_record = MagicMock()
            mock_record.keys.return_value = ["val"]
            mock_record.__getitem__ = lambda s, k: 42

            class _AsyncIter:
                def __init__(self):
                    self._items = [mock_record]
                    self._idx = 0

                def __aiter__(self):
                    return self

                async def __anext__(self):
                    if self._idx >= len(self._items):
                        raise StopAsyncIteration
                    item = self._items[self._idx]
                    self._idx += 1
                    return item

            return _AsyncIter()

        mock_session = AsyncMock()
        mock_session.run = mock_run
        mock_session.__aenter__ = AsyncMock(
            return_value=mock_session
        )
        mock_session.__aexit__ = AsyncMock(return_value=False)
        neo4j_client.driver.session.return_value = mock_session

        t0 = time.monotonic()
        result = await neo4j_client._run_query_session(
            "MATCH (n) RETURN n.val AS val", {}
        )
        elapsed = time.monotonic() - t0

        assert len(result) == 1
        assert result[0]["val"] == 42
        assert call_count == fail_on_attempt + 1

        # Backoff: sum of 0.1*2^i for i in 1..fail_on_attempt
        min_backoff = sum(
            0.1 * (2 ** i) for i in range(1, fail_on_attempt + 1)
        )
        assert elapsed >= min_backoff * 0.8, (
            f"Expected >= {min_backoff * 0.8:.2f}s backoff, "
            f"got {elapsed:.2f}s"
        )

    @pytest.mark.asyncio
    async def test_2a_read_exhausts_retries_raises_query_error(
        self, neo4j_client
    ):
        """After 3 consecutive TransientErrors, _run_query_session
        raises QueryError -- not the raw TransientError."""
        call_count = 0

        async def mock_run(query, params):
            nonlocal call_count
            call_count += 1
            raise TransientError("always fails")

        mock_session = AsyncMock()
        mock_session.run = mock_run
        mock_session.__aenter__ = AsyncMock(
            return_value=mock_session
        )
        mock_session.__aexit__ = AsyncMock(return_value=False)
        neo4j_client.driver.session.return_value = mock_session

        with pytest.raises(QueryError, match="retries"):
            await neo4j_client._run_query_session(
                "MATCH (n) RETURN n", {}
            )

        assert call_count == 3

    @pytest.mark.asyncio
    async def test_2a_read_non_transient_not_retried(
        self, neo4j_client
    ):
        """Non-transient errors propagate immediately."""
        call_count = 0

        async def mock_run(query, params):
            nonlocal call_count
            call_count += 1
            raise RuntimeError("non-transient")

        mock_session = AsyncMock()
        mock_session.run = mock_run
        mock_session.__aenter__ = AsyncMock(
            return_value=mock_session
        )
        mock_session.__aexit__ = AsyncMock(return_value=False)
        neo4j_client.driver.session.return_value = mock_session

        with pytest.raises(RuntimeError, match="non-transient"):
            await neo4j_client._run_query_session(
                "MATCH (n) RETURN n", {}
            )

        assert call_count == 1



# -------------------------------------------------------------------
# Test 2b -- Successful first-attempt writes return immediately
# -------------------------------------------------------------------

class TestSuccessfulWritePreservation:
    """Preservation: writes that succeed on the first attempt
    return identical results with no added delay."""

    @pytest.mark.asyncio
    @settings(
        max_examples=30,
        suppress_health_check=[
            HealthCheck.function_scoped_fixture,
        ],
        deadline=10000,
    )
    @given(
        record_count=st.integers(min_value=0, max_value=10),
    )
    async def test_2b_successful_write_returns_immediately(
        self, neo4j_client, record_count
    ):
        """When session.execute_write succeeds on the first call,
        _run_write_session returns the records with no retry
        overhead."""
        expected = [{"id": i} for i in range(record_count)]

        async def mock_execute_write(write_fn):
            return expected

        mock_session = AsyncMock()
        mock_session.execute_write = mock_execute_write
        mock_session.__aenter__ = AsyncMock(
            return_value=mock_session
        )
        mock_session.__aexit__ = AsyncMock(return_value=False)
        neo4j_client.driver.session.return_value = mock_session

        t0 = time.monotonic()
        result = await neo4j_client._run_write_session(
            "CREATE (n:Test) RETURN n", {}
        )
        elapsed = time.monotonic() - t0

        assert result == expected
        # No artificial delay
        assert elapsed < 0.5, (
            f"Successful write took {elapsed:.3f}s -- "
            f"unexpected delay"
        )

    @pytest.mark.asyncio
    @settings(
        max_examples=20,
        suppress_health_check=[
            HealthCheck.function_scoped_fixture,
        ],
        deadline=10000,
    )
    @given(
        key=st.text(
            alphabet=st.characters(whitelist_categories=("L",)),
            min_size=1,
            max_size=10,
        ),
        value=st.one_of(
            st.integers(),
            st.text(min_size=0, max_size=50),
            st.floats(allow_nan=False, allow_infinity=False),
        ),
    )
    async def test_2b_write_result_fidelity(
        self, neo4j_client, key, value
    ):
        """Records returned by _run_write_session are exactly
        what session.execute_write produced -- no transformation."""
        expected = [{key: value}]

        async def mock_execute_write(write_fn):
            return expected

        mock_session = AsyncMock()
        mock_session.execute_write = mock_execute_write
        mock_session.__aenter__ = AsyncMock(
            return_value=mock_session
        )
        mock_session.__aexit__ = AsyncMock(return_value=False)
        neo4j_client.driver.session.return_value = mock_session

        result = await neo4j_client._run_write_session(
            "MERGE (n:T {k: $v}) RETURN n", {"v": value}
        )
        assert result == expected


# -------------------------------------------------------------------
# Test 2c -- TCP transport closed -> reconnect + retry once
# -------------------------------------------------------------------

class TestTCPReconnectPreservation:
    """Preservation: _execute_write_with_reconnect reconnects
    and retries exactly once on TCP transport closed errors."""

    @pytest.mark.asyncio
    @settings(
        max_examples=10,
        suppress_health_check=[
            HealthCheck.function_scoped_fixture,
        ],
        deadline=15000,
    )
    @given(
        error_msg=st.sampled_from([
            "tcptransport closed",
            "handler is closed",
            "connection has been closed",
            "session has been closed",
        ]),
    )
    async def test_2c_reconnects_on_transport_closed(
        self, neo4j_client, error_msg
    ):
        """When _run_write_session raises an error whose message
        matches a closed-transport pattern, the client reconnects
        and retries the write exactly once."""
        call_count = 0
        expected = [{"ok": True}]

        async def mock_run_write(query, params):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception(error_msg)
            return expected

        neo4j_client._run_write_session = mock_run_write
        neo4j_client._stop_keepalive = MagicMock()
        neo4j_client.connect = AsyncMock()

        # The reconnect path does:
        #   if self.driver: await self.driver.close()
        #   self.driver = None
        # We need driver to be a mock with an async close.
        mock_driver = MagicMock()
        mock_driver.close = AsyncMock()
        neo4j_client.driver = mock_driver

        result = await neo4j_client._execute_write_with_reconnect(
            "MERGE (n:T) RETURN n", {}
        )

        assert result == expected
        assert call_count == 2, (
            f"Expected exactly 2 calls (1 fail + 1 retry), "
            f"got {call_count}"
        )
        neo4j_client.connect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_2c_non_transport_error_not_retried(
        self, neo4j_client
    ):
        """Errors that are NOT transport-closed propagate
        immediately without reconnect."""
        call_count = 0

        async def mock_run_write(query, params):
            nonlocal call_count
            call_count += 1
            raise ValueError("some other error")

        neo4j_client._run_write_session = mock_run_write
        neo4j_client.connect = AsyncMock()

        with pytest.raises(ValueError, match="some other error"):
            await neo4j_client._execute_write_with_reconnect(
                "MERGE (n:T) RETURN n", {}
            )

        assert call_count == 1
        neo4j_client.connect.assert_not_awaited()


# -------------------------------------------------------------------
# Test 2d -- UMLS bridging skipped when umls_linker is None
# -------------------------------------------------------------------

class TestUMLSBridgingSkipPreservation:
    """Preservation: when umls_linker is None, no UMLS bridging
    is attempted in _update_knowledge_graph."""

    def test_2d_umls_bridge_guarded_by_linker_check(self):
        """The UMLS bridging block in _update_knowledge_graph is
        guarded by ``if umls_linker is not None``.  When the linker
        is None (unavailable), UMLSBridger is never instantiated
        and create_same_as_edges is never called.

        We verify this structurally: the source code must contain
        the guard before any UMLSBridger usage.
        """
        import src.multimodal_librarian.services.celery_service as cs

        source = inspect.getsource(cs._update_knowledge_graph)

        # The bridging block must be guarded
        assert "if umls_linker is not None" in source, (
            "_update_knowledge_graph does not guard UMLS bridging "
            "with 'if umls_linker is not None'"
        )

        # UMLSBridger instantiation must appear INSIDE the guard
        bridger_idx = source.index("UMLSBridger(")
        guard_idx = source.index("if umls_linker is not None")
        assert bridger_idx > guard_idx, (
            "UMLSBridger is instantiated before the "
            "umls_linker guard check"
        )

    @pytest.mark.asyncio
    async def test_2d_umls_linker_none_skips_bridging_runtime(
        self,
    ):
        """When UMLS is unavailable, _update_knowledge_graph must
        not call UMLSBridger at all.  We verify by patching the
        lazy imports and confirming UMLSBridger is never called."""
        mock_kg_client = AsyncMock()
        mock_kg_client.connect = AsyncMock()
        mock_kg_client.disconnect = AsyncMock()
        mock_kg_client.execute_query = AsyncMock(return_value=[])

        mock_kg_service_instance = MagicMock()
        mock_kg_service_instance.client = mock_kg_client

        mock_extraction = MagicMock()
        mock_extraction.extracted_concepts = []
        mock_extraction.extracted_relationships = []

        mock_builder = MagicMock()
        mock_builder.process_knowledge_chunk_extract_only = (
            AsyncMock(return_value=mock_extraction)
        )
        mock_builder.validate_batch_concepts = AsyncMock(
            return_value=([], [], {})
        )

        mock_umls_client = AsyncMock()
        mock_umls_client.initialize = AsyncMock()
        mock_umls_client.is_available = AsyncMock(
            return_value=False
        )

        bridger_cls = MagicMock()

        # Patch KnowledgeGraphService as a callable that returns
        # our mock instance — bypasses __init__ entirely, avoiding
        # the real get_database_factory → Neo4j connection chain.
        mock_kg_service_cls = MagicMock(
            return_value=mock_kg_service_instance
        )

        targets = [
            (
                "src.multimodal_librarian.services.celery_service"
                "._is_document_deleted",
                AsyncMock(return_value=False),
            ),
            (
                "src.multimodal_librarian.services.celery_service"
                "._update_job_status_sync",
                AsyncMock(),
            ),
            (
                "src.multimodal_librarian.services.celery_service"
                "._set_parallel_progress",
                MagicMock(return_value=50),
            ),
            (
                "src.multimodal_librarian.services.celery_service"
                "._create_enrichment_status",
                AsyncMock(),
            ),
            (
                "src.multimodal_librarian.services"
                ".knowledge_graph_service"
                ".KnowledgeGraphService",
                mock_kg_service_cls,
            ),
            (
                "src.multimodal_librarian.components"
                ".knowledge_graph"
                ".kg_builder.KnowledgeGraphBuilder",
                MagicMock(return_value=mock_builder),
            ),
            (
                "src.multimodal_librarian.components"
                ".knowledge_graph"
                ".umls_client.UMLSClient",
                MagicMock(return_value=mock_umls_client),
            ),
            (
                "src.multimodal_librarian.components"
                ".knowledge_graph"
                ".umls_linker.UMLSLinker",
                MagicMock(),
            ),
            (
                "src.multimodal_librarian.components"
                ".knowledge_graph"
                ".umls_bridger.UMLSBridger",
                bridger_cls,
            ),
            (
                "src.multimodal_librarian.clients"
                ".model_server_client"
                ".initialize_model_client",
                AsyncMock(return_value=None),
            ),
        ]

        stack = [patch(t, m) for t, m in targets]
        for p in stack:
            p.start()

        try:
            from src.multimodal_librarian.services.celery_service import (
                _update_knowledge_graph,
            )

            chunks = [
                {
                    "id": "chunk-1",
                    "content": "Test",
                    "chunk_type": "general",
                    "chunk_index": 0,
                    "metadata": {},
                }
            ]
            await _update_knowledge_graph(
                "00000000-0000-0000-0000-000000000123", chunks
            )

            # UMLSBridger should never have been instantiated
            bridger_cls.assert_not_called()
        finally:
            for p in reversed(stack):
                p.stop()


# -------------------------------------------------------------------
# Test 2e -- Document deletion mid-processing aborts gracefully
# -------------------------------------------------------------------

class TestDocumentDeletionAbortPreservation:
    """Preservation: when _is_document_deleted returns True,
    _update_knowledge_graph aborts without persisting further."""

    def test_2e_deletion_check_exists_in_batch_loop(self):
        """_update_knowledge_graph checks _is_document_deleted at
        the start of each batch iteration and returns early if
        the document was deleted."""
        import src.multimodal_librarian.services.celery_service as cs

        source = inspect.getsource(cs._update_knowledge_graph)

        assert "_is_document_deleted" in source, (
            "_update_knowledge_graph does not call "
            "_is_document_deleted"
        )

        # The deletion check must be inside the batch loop
        loop_idx = source.index("for batch_start in range")
        deletion_idx = source.index(
            "_is_document_deleted", loop_idx
        )
        assert deletion_idx > loop_idx, (
            "_is_document_deleted is not called inside the "
            "batch processing loop"
        )

        # It must trigger a return (abort)
        return_idx = source.index("return", deletion_idx)
        # The return should be close to the deletion check
        # (within ~500 chars -- the log message + return)
        assert return_idx - deletion_idx < 500, (
            "No early return found near _is_document_deleted "
            "check -- deletion may not abort processing"
        )

    @pytest.mark.asyncio
    async def test_2e_aborts_on_document_deletion_runtime(self):
        """If the document is deleted between batches,
        _update_knowledge_graph returns early."""
        deletion_check_count = 0

        async def mock_is_deleted(doc_id):
            nonlocal deletion_check_count
            deletion_check_count += 1
            # First batch: not deleted; second batch: deleted
            return deletion_check_count >= 2

        mock_kg_client = AsyncMock()
        mock_kg_client.connect = AsyncMock()
        mock_kg_client.disconnect = AsyncMock()
        mock_kg_client.execute_query = AsyncMock(
            return_value=[]
        )

        mock_kg_service_instance = MagicMock()
        mock_kg_service_instance.client = mock_kg_client

        mock_extraction = MagicMock()
        mock_extraction.extracted_concepts = []
        mock_extraction.extracted_relationships = []

        mock_builder = MagicMock()
        mock_builder.process_knowledge_chunk_extract_only = (
            AsyncMock(return_value=mock_extraction)
        )
        mock_builder.validate_batch_concepts = AsyncMock(
            return_value=([], [], {})
        )

        mock_umls_client = AsyncMock()
        mock_umls_client.initialize = AsyncMock()
        mock_umls_client.is_available = AsyncMock(
            return_value=False
        )

        # Patch KnowledgeGraphService as a callable returning
        # our mock — avoids real __init__ and Neo4j connection.
        mock_kg_service_cls = MagicMock(
            return_value=mock_kg_service_instance
        )

        targets = [
            (
                "src.multimodal_librarian.services.celery_service"
                "._is_document_deleted",
                mock_is_deleted,
            ),
            (
                "src.multimodal_librarian.services.celery_service"
                "._update_job_status_sync",
                AsyncMock(),
            ),
            (
                "src.multimodal_librarian.services.celery_service"
                "._set_parallel_progress",
                MagicMock(return_value=50),
            ),
            (
                "src.multimodal_librarian.services.celery_service"
                "._create_enrichment_status",
                AsyncMock(),
            ),
            (
                "src.multimodal_librarian.services"
                ".knowledge_graph_service"
                ".KnowledgeGraphService",
                mock_kg_service_cls,
            ),
            (
                "src.multimodal_librarian.components"
                ".knowledge_graph"
                ".kg_builder.KnowledgeGraphBuilder",
                MagicMock(return_value=mock_builder),
            ),
            (
                "src.multimodal_librarian.components"
                ".knowledge_graph"
                ".umls_client.UMLSClient",
                MagicMock(return_value=mock_umls_client),
            ),
            (
                "src.multimodal_librarian.components"
                ".knowledge_graph"
                ".umls_linker.UMLSLinker",
                MagicMock(),
            ),
            (
                "src.multimodal_librarian.clients"
                ".model_server_client"
                ".initialize_model_client",
                AsyncMock(return_value=None),
            ),
        ]

        stack = [patch(t, m) for t, m in targets]
        for p in stack:
            p.start()

        try:
            from src.multimodal_librarian.services.celery_service import (
                _update_knowledge_graph,
            )

            # 150 chunks -> 2 batches (BATCH_SIZE=100 for scale=1)
            # Batch 1: not deleted -> processes
            # Batch 2: deleted -> aborts
            chunks = [
                {
                    "id": f"chunk-{i}",
                    "content": f"Content {i}",
                    "chunk_type": "general",
                    "chunk_index": i,
                    "metadata": {},
                }
                for i in range(150)
            ]

            await _update_knowledge_graph(
                "00000000-0000-0000-0000-00000000de1e", chunks
            )

            # Deletion was checked at least twice
            assert deletion_check_count >= 2, (
                f"Expected >= 2 deletion checks, "
                f"got {deletion_check_count}"
            )
        finally:
            for p in reversed(stack):
                p.stop()
