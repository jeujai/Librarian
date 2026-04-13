"""
Bug Condition Exploration Tests — Property 1

These tests encode the EXPECTED (correct) behavior for page progress display
and completion signaling. They are written BEFORE the fix and are expected to
FAIL on unfixed code, confirming the bugs exist.

Bug 1 — Page Overflow: _store_embeddings_in_vector_db() and
    _store_chunks_in_database() produce progress metadata where
    current_page > total_pages when chunk page numbers exceed the
    physical page count (e.g., journal-style numbering 195–236 with
    total_pages=89).

Bug 2 — Completion Race: finalize_processing_task() sends both a 100%
    status_update AND a processing_complete notification, causing the UI
    to inconsistently show "100%" or the completion summary.

Requirements: 1.1, 1.2, 1.3

**Validates: Requirements 1.1, 1.2**
"""

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

def _chunk_strategy(min_page: int, max_page: int):
    """
    Generate a single chunk dict with a page_number drawn from [min_page, max_page].
    """
    return st.fixed_dictionaries({
        "id": st.uuids().map(str),
        "content": st.text(min_size=1, max_size=50),
        "chunk_type": st.just("text"),
        "metadata": st.fixed_dictionaries({
            "page_number": st.integers(min_value=min_page, max_value=max_page),
            "chunk_index": st.integers(min_value=0, max_value=500),
            "content_type": st.just("text"),
        }),
    })


def _chunks_with_overflow():
    """
    Strategy that produces (chunks, total_pages) where at least one chunk
    has page_number > total_pages — the bug condition.
    """
    return (
        st.integers(min_value=1, max_value=100)  # total_pages
        .flatmap(lambda tp: st.tuples(
            # chunks whose page_number can exceed total_pages
            st.lists(
                _chunk_strategy(min_page=tp + 1, max_page=tp + 200),
                min_size=1,
                max_size=10,
            ),
            st.just(tp),
        ))
    )


# ---------------------------------------------------------------------------
# Helpers — extract metadata from mocked _update_job_status_sync calls
# ---------------------------------------------------------------------------

def _collect_metadata_from_calls(mock_update):
    """
    Return a list of metadata dicts that were passed to
    _update_job_status_sync via the `metadata=` keyword argument.
    """
    results = []
    for call in mock_update.call_args_list:
        meta = call.kwargs.get("metadata") if call.kwargs else None
        if meta is None and len(call.args) > 4:
            # positional fallback — unlikely but defensive
            pass
        if meta and isinstance(meta, dict):
            results.append(meta)
    return results


# ---------------------------------------------------------------------------
# Bug 1 — Page Overflow in _store_embeddings_in_vector_db
# ---------------------------------------------------------------------------

class TestEmbeddingPageOverflow:
    """
    Assert that _store_embeddings_in_vector_db() never produces
    progress metadata where current_page > total_pages.

    On UNFIXED code this FAILS because max_page is not clamped.
    """

    @given(data=_chunks_with_overflow())
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_property_embedding_progress_page_never_exceeds_total(self, data):
        """
        **Validates: Requirements 1.1**

        Property: For ALL chunk lists where page_number > total_pages,
        the progress metadata must satisfy current_page <= total_pages.

        On UNFIXED code this FAILS: max_page is used directly without
        clamping against total_pages.
        """
        chunks, total_pages = data

        mock_update = AsyncMock()
        mock_vector_client = AsyncMock()
        mock_vector_client.store_embeddings = AsyncMock()

        mock_model_client = MagicMock()
        mock_model_client.enabled = True

        document_id = str(uuid.uuid4())

        with (
            patch(
                "multimodal_librarian.services.celery_service._update_job_status_sync",
                mock_update,
            ),
            patch(
                "multimodal_librarian.services.celery_service._is_document_deleted",
                AsyncMock(return_value=False),
            ),
            patch(
                "multimodal_librarian.clients.database_factory.DatabaseClientFactory"
            ) as MockFactory,
            patch(
                "multimodal_librarian.config.config_factory.get_database_config",
                return_value=MagicMock(),
            ),
            patch(
                "multimodal_librarian.clients.model_server_client.initialize_model_client",
                AsyncMock(return_value=mock_model_client),
            ),
        ):
            factory_instance = MockFactory.return_value
            factory_instance.get_vector_client.return_value = mock_vector_client

            from multimodal_librarian.services.celery_service import (
                _store_embeddings_in_vector_db,
            )

            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(
                    _store_embeddings_in_vector_db(document_id, chunks, total_pages)
                )
            finally:
                loop.close()

        metas = _collect_metadata_from_calls(mock_update)
        for meta in metas:
            if "current_page" in meta and "total_pages" in meta:
                assert meta["current_page"] <= meta["total_pages"], (
                    f"COUNTEREXAMPLE: current_page={meta['current_page']}, "
                    f"total_pages={meta['total_pages']} — page progress "
                    f"exceeds total pages during embedding storage"
                )


# ---------------------------------------------------------------------------
# Bug 1 — Page Overflow in _store_chunks_in_database
# ---------------------------------------------------------------------------

class TestChunkStoragePageOverflow:
    """
    Assert that _store_chunks_in_database() never produces
    progress metadata where current_page > total_pages.

    On UNFIXED code this FAILS because max_page_seen is not clamped.
    """

    @given(data=_chunks_with_overflow())
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_property_chunk_storage_page_never_exceeds_total(self, data):
        """
        **Validates: Requirements 1.2**

        Property: For ALL chunk lists where page_number > total_pages,
        the progress metadata must satisfy current_page <= total_pages.

        On UNFIXED code this FAILS: max_page_seen is used directly
        without clamping against total_pages.
        """
        chunks, total_pages = data

        # Add required fields for _store_chunks_in_database
        for i, chunk in enumerate(chunks):
            chunk.setdefault("page_number", chunk.get("metadata", {}).get("page_number"))
            chunk.setdefault("section_title", None)

        mock_update = AsyncMock()
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_conn.close = AsyncMock()

        # Mock the transaction context manager
        mock_transaction = AsyncMock()
        mock_transaction.__aenter__ = AsyncMock(return_value=mock_transaction)
        mock_transaction.__aexit__ = AsyncMock(return_value=False)
        mock_conn.transaction = MagicMock(return_value=mock_transaction)

        document_id = str(uuid.uuid4())

        # Force the time-based progress update to fire by making
        # time.monotonic() advance past UPDATE_INTERVAL on every call.
        call_count = 0
        def fake_monotonic():
            nonlocal call_count
            call_count += 1
            # Return values that are always > UPDATE_INTERVAL apart
            return call_count * 10.0

        with (
            patch(
                "multimodal_librarian.services.celery_service._update_job_status_sync",
                mock_update,
            ),
            patch(
                "multimodal_librarian.services.celery_service._is_document_deleted",
                AsyncMock(return_value=False),
            ),
            patch(
                "multimodal_librarian.database.connection.get_async_connection",
                AsyncMock(return_value=mock_conn),
            ),
            patch(
                "time.monotonic",
                side_effect=fake_monotonic,
            ),
        ):
            from multimodal_librarian.services.celery_service import (
                _store_chunks_in_database,
            )

            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(
                    _store_chunks_in_database(document_id, chunks, total_pages)
                )
            finally:
                loop.close()

        metas = _collect_metadata_from_calls(mock_update)
        for meta in metas:
            if "current_page" in meta and "total_pages" in meta:
                assert meta["current_page"] <= meta["total_pages"], (
                    f"COUNTEREXAMPLE: current_page={meta['current_page']}, "
                    f"total_pages={meta['total_pages']} — page progress "
                    f"exceeds total pages during chunk storage"
                )


# ---------------------------------------------------------------------------
# Bug 2 — Completion Race in finalize_processing_task
# ---------------------------------------------------------------------------

class TestCompletionRaceCondition:
    """
    Assert that finalize_processing_task() does NOT send both a 100%
    status_update AND a completion notification.

    On UNFIXED code this FAILS because both messages are sent.
    """

    def test_no_dual_completion_messages(self):
        """
        **Validates: Requirements 1.3**

        Bug Condition: finalize_processing_task() sends
        _update_job_status_sync(..., 'completed', 100.0, ...) which
        triggers a WebSocket status_update, AND then calls
        notify_processing_completion_sync() which sends a separate
        completion WebSocket message.

        Expected behavior: Only ONE terminal WebSocket message should
        be sent (the completion notification with summary data).

        On UNFIXED code this FAILS: both messages are sent.
        """
        document_id = str(uuid.uuid4())

        # Track all calls to _update_job_status_sync
        update_calls = []
        original_update = AsyncMock()

        async def capture_update(doc_id, status, progress, step, *args, **kwargs):
            update_calls.append({
                "document_id": doc_id,
                "status": status,
                "progress": progress,
                "step": step,
            })

        original_update.side_effect = capture_update

        # Track calls to notify_processing_completion_sync
        completion_calls = []

        def capture_completion(**kwargs):
            completion_calls.append(kwargs)

        # Valid parallel_results that pass validation
        parallel_results = [
            {
                "status": "completed",
                "chunk_count": 100,
                "concept_count": 42,
                "page_count": 89,
                "title": "Test Document",
                "kg_failures": {"ner_failures": 0, "llm_failures": 0, "total_chunks": 100},
                "bridge_failures": {"failed_bridges": 0, "total_bridges": 50},
            },
            {
                "status": "completed",
                "chunk_count": 0,
                "concept_count": 0,
                "page_count": 0,
            },
        ]

        # Mock quality gate to pass
        mock_qg_result = MagicMock()
        mock_qg_result.passed = True
        mock_qg_result.content_type = "GENERAL"
        mock_qg_result.threshold = 0.5
        mock_qg_result.composite_rate = 0.0
        mock_qg_result.to_dict.return_value = {"passed": True}

        with (
            patch(
                "multimodal_librarian.services.celery_service._update_job_status_sync",
                original_update,
            ),
            patch(
                "multimodal_librarian.services.celery_service._update_document_status_sync",
                AsyncMock(),
            ),
            patch(
                "multimodal_librarian.services.celery_service._compute_composite_scores",
                AsyncMock(),
            ),
            patch(
                "multimodal_librarian.services.celery_service._check_document_deleted",
            ),
            patch(
                "multimodal_librarian.services.celery_service._cleanup_parallel_progress",
            ),
            patch(
                "multimodal_librarian.services.celery_service._record_stage_timing",
                AsyncMock(),
            ),
            patch(
                "multimodal_librarian.services.celery_service._retrieve_processing_payload",
                AsyncMock(return_value={}),
            ),
            patch(
                "multimodal_librarian.services.celery_service._delete_processing_payload",
                AsyncMock(),
            ),
            patch(
                "multimodal_librarian.services.celery_service._persist_quality_gate_data",
                AsyncMock(),
            ),
            patch(
                "multimodal_librarian.services.celery_service._validate_parallel_results",
                return_value=(True, None),
            ),
            patch(
                "multimodal_librarian.services.quality_gate.compute_quality_gate",
                return_value=mock_qg_result,
            ),
            patch(
                "multimodal_librarian.services.processing_status_integration.notify_processing_completion_sync",
                side_effect=capture_completion,
            ) as mock_notify,
        ):
            from multimodal_librarian.services.celery_service import (
                finalize_processing_task,
            )

            result = finalize_processing_task(parallel_results, document_id)

        assert result["status"] == "completed", (
            f"Expected completed status, got {result['status']}"
        )

        # Check: did the function send a 100% status_update?
        completed_100_updates = [
            c for c in update_calls
            if c["status"] == "completed" and c["progress"] == 100.0
        ]

        # Check: did the function also send a completion notification?
        has_completion_notification = len(completion_calls) > 0

        # The bug: BOTH are sent. Expected behavior: only the completion
        # notification should be sent (not the 100% status_update).
        assert not (completed_100_updates and has_completion_notification), (
            f"COUNTEREXAMPLE: finalize_processing_task() sends BOTH a "
            f"status_update with status='completed'/progress=100.0 AND a "
            f"processing_complete notification. This causes the UI to "
            f"inconsistently show '100%' or the completion summary. "
            f"Found {len(completed_100_updates)} completed-100% update(s) "
            f"and {len(completion_calls)} completion notification(s)."
        )
