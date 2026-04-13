"""
Preservation Property Tests — Property 2: Non-Active-Task Deletions Unchanged

These tests capture the EXISTING behavior of the unfixed code for non-buggy
inputs (where isBugCondition returns false).  They are written BEFORE the fix
and MUST PASS on unfixed code, establishing a baseline to detect regressions.

Preservation scope (from bugfix.md §3.1–3.5):
  - Documents with no processing job → all stores cleaned up, success=True
  - Documents with completed job → deletion succeeds, no revocation attempted
  - Documents with failed job → deletion succeeds, no revocation attempted
  - Conversation documents → thread archived, CASCADE delete succeeds
  - _check_document_deleted() for existing documents → does NOT raise

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Hypothesis strategies for non-bug-condition inputs
# ---------------------------------------------------------------------------

# Job statuses that are NOT active (bug condition requires 'pending'/'running')
non_active_job_statuses = st.sampled_from([None, "completed", "failed"])

# Document source types
source_types = st.sampled_from(["PDF", "CONVERSATION"])

# Milvus deletion counts (non-negative)
milvus_counts = st.integers(min_value=0, max_value=50)

# Neo4j deletion counts (non-negative)
neo4j_counts = st.integers(min_value=0, max_value=50)

DB_MANAGER_PATCH_TARGET = (
    "multimodal_librarian.database.connection.db_manager"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    """Run an async coroutine synchronously for tests."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _make_db_row(source_type: str, thread_id: str = None):
    """Build a mock DB row for the conversation-resolution query."""
    row = MagicMock()
    row.source_type = source_type
    row.file_path = f"conversation://{thread_id}" if thread_id else "/uploads/doc.pdf"
    row.metadata = {"source_thread_id": thread_id} if thread_id else {}
    return row


def _setup_db_mock(mock_db, db_row=None):
    """Configure a mock db_manager (from patch with create=True)."""
    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_execute_result = MagicMock()
    mock_execute_result.fetchone.return_value = db_row
    mock_session.execute = AsyncMock(return_value=mock_execute_result)
    mock_db.get_async_session.return_value = mock_session


def _build_document_manager(upload_delete_ok=True, cancel_side_effect=None):
    """
    Build a DocumentManager with mocked dependencies.
    Returns (dm, mock_upload_svc, mock_processing_svc).
    """
    from multimodal_librarian.components.document_manager.document_manager import (
        DocumentManager,
    )

    mock_upload_svc = MagicMock()
    mock_upload_svc.delete_document = AsyncMock(return_value=upload_delete_ok)

    mock_processing_svc = MagicMock()
    if cancel_side_effect:
        mock_processing_svc.cancel_processing = AsyncMock(
            side_effect=cancel_side_effect
        )
    else:
        mock_processing_svc.cancel_processing = AsyncMock(return_value=True)

    dm = DocumentManager.__new__(DocumentManager)
    dm.upload_service = mock_upload_svc
    dm.processing_service = mock_processing_svc

    return dm, mock_upload_svc, mock_processing_svc


# ---------------------------------------------------------------------------
# Property 2a: Non-active-task deletions produce success=True
# ---------------------------------------------------------------------------

class TestPreservation_DeleteSucceeds:
    """
    For all documents where isBugCondition is false (no active processing
    job), delete_document_completely() must produce success=True with all
    stores cleaned up.

    Requirement 3.1: No active job → all stores cleaned up, success=True
    Requirement 3.2: Completed job → deletion succeeds
    """

    @given(
        job_status=non_active_job_statuses,
        source_type=source_types,
        milvus_deleted=milvus_counts,
        neo4j_deleted=neo4j_counts,
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=10000,
    )
    def test_non_active_task_deletion_succeeds(
        self, job_status, source_type, milvus_deleted, neo4j_deleted
    ):
        """
        Property: For any document with no active processing job
        (job_status in {None, 'completed', 'failed'}) and any source_type,
        delete_document_completely() returns success=True and
        postgresql_deleted=True.
        """
        doc_id = uuid4()
        thread_id = str(uuid4()) if source_type == "CONVERSATION" else None
        db_row = _make_db_row(source_type, thread_id)

        dm, mock_upload, mock_proc = _build_document_manager(
            upload_delete_ok=True,
        )

        with (
            patch.object(
                dm, "_delete_from_milvus", new=AsyncMock(return_value=milvus_deleted)
            ),
            patch.object(
                dm, "_delete_from_neo4j", new=AsyncMock(return_value=neo4j_deleted)
            ),
            patch.object(dm, "_delete_pg_extras", new=AsyncMock()),
            patch(DB_MANAGER_PATCH_TARGET, create=True) as mock_db,
        ):
            _setup_db_mock(mock_db, db_row)
            results = _run(dm.delete_document_completely(doc_id))

        assert results["success"] is True, (
            f"delete_document_completely() returned success=False for "
            f"non-active-task document (job_status={job_status}, "
            f"source_type={source_type}). results={results}"
        )
        assert results["postgresql_deleted"] is True
        assert results["minio_deleted"] is True
        # For CONVERSATION docs, Milvus/Neo4j are called twice (doc_id + thread_id)
        # so the total is 2x the per-call return value
        if source_type == "CONVERSATION":
            assert results["milvus_deleted"] == milvus_deleted * 2
            assert results["neo4j_deleted"] == neo4j_deleted * 2
        else:
            assert results["milvus_deleted"] == milvus_deleted
            assert results["neo4j_deleted"] == neo4j_deleted


# ---------------------------------------------------------------------------
# Property 2b: No revocation attempted for non-active-task documents
# ---------------------------------------------------------------------------

class TestPreservation_NoRevocationAttempted:
    """
    For all documents where isBugCondition is false, cancel_processing()
    is called but does not block the deletion flow.

    Requirement 3.2: Completed job → no-op for cancellation
    Requirement 3.1: No job → cancel_processing returns False (no job found)
    """

    @given(
        job_status=non_active_job_statuses,
        source_type=source_types,
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=10000,
    )
    def test_cancel_processing_does_not_block_deletion(
        self, job_status, source_type
    ):
        """
        Property: For any non-active-task document, the cancel_processing()
        call inside delete_document_completely() does not prevent the
        deletion from succeeding.
        """
        doc_id = uuid4()
        thread_id = str(uuid4()) if source_type == "CONVERSATION" else None
        db_row = _make_db_row(source_type, thread_id)

        dm, mock_upload, mock_proc = _build_document_manager(
            upload_delete_ok=True,
        )

        with (
            patch.object(dm, "_delete_from_milvus", new=AsyncMock(return_value=0)),
            patch.object(dm, "_delete_from_neo4j", new=AsyncMock(return_value=0)),
            patch.object(dm, "_delete_pg_extras", new=AsyncMock()),
            patch(DB_MANAGER_PATCH_TARGET, create=True) as mock_db,
        ):
            _setup_db_mock(mock_db, db_row)
            results = _run(dm.delete_document_completely(doc_id))

        # cancel_processing was called (best-effort)
        mock_proc.cancel_processing.assert_called_once_with(doc_id)

        # Deletion still succeeded regardless of cancel outcome
        assert results["success"] is True, (
            f"Deletion failed for non-active-task document "
            f"(job_status={job_status}, source_type={source_type})"
        )

    @given(source_type=source_types)
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=10000,
    )
    def test_cancel_processing_exception_does_not_block_deletion(
        self, source_type
    ):
        """
        Property: Even when cancel_processing() raises an exception for
        a non-active-task document, delete_document_completely() still
        succeeds (the current except:pass swallows the error).

        This captures the EXISTING behavior — the fix will change error
        handling for active tasks, but non-active-task paths should still
        not be blocked by cancellation errors.
        """
        doc_id = uuid4()
        thread_id = str(uuid4()) if source_type == "CONVERSATION" else None
        db_row = _make_db_row(source_type, thread_id)

        dm, mock_upload, mock_proc = _build_document_manager(
            upload_delete_ok=True,
            cancel_side_effect=RuntimeError("No active job to cancel"),
        )

        with (
            patch.object(dm, "_delete_from_milvus", new=AsyncMock(return_value=0)),
            patch.object(dm, "_delete_from_neo4j", new=AsyncMock(return_value=0)),
            patch.object(dm, "_delete_pg_extras", new=AsyncMock()),
            patch(DB_MANAGER_PATCH_TARGET, create=True) as mock_db,
        ):
            _setup_db_mock(mock_db, db_row)
            results = _run(dm.delete_document_completely(doc_id))

        assert results["success"] is True, (
            f"Deletion blocked by cancel_processing() exception for "
            f"non-active-task document (source_type={source_type})"
        )


# ---------------------------------------------------------------------------
# Property 2c: Conversation document deletion archives thread
# ---------------------------------------------------------------------------

class TestPreservation_ConversationDeletion:
    """
    Conversation documents (source_type='CONVERSATION') must have their
    thread_id resolved and used for Milvus/Neo4j cleanup.

    Requirement 3.5: Conversation document deletion archives thread
    and CASCADE-deletes as today.
    """

    def test_conversation_document_resolves_thread_id(self):
        """
        Property: For a conversation document, delete_document_completely()
        resolves the thread_id from the DB row and uses it for Milvus/Neo4j
        cleanup (vector_id != doc_id → both IDs used).
        """
        doc_id = uuid4()
        thread_id = str(uuid4())
        db_row = _make_db_row("CONVERSATION", thread_id)

        dm, mock_upload, mock_proc = _build_document_manager(
            upload_delete_ok=True,
        )

        mock_milvus = AsyncMock(return_value=5)
        mock_neo4j = AsyncMock(return_value=3)

        with (
            patch.object(dm, "_delete_from_milvus", mock_milvus),
            patch.object(dm, "_delete_from_neo4j", mock_neo4j),
            patch.object(dm, "_delete_pg_extras", new=AsyncMock()),
            patch(DB_MANAGER_PATCH_TARGET, create=True) as mock_db,
        ):
            _setup_db_mock(mock_db, db_row)
            results = _run(dm.delete_document_completely(doc_id))

        assert results["success"] is True

        # Milvus and Neo4j should be called with BOTH doc_id and thread_id
        milvus_calls = [str(c[0][0]) for c in mock_milvus.call_args_list]
        neo4j_calls = [str(c[0][0]) for c in mock_neo4j.call_args_list]

        assert str(doc_id) in milvus_calls, (
            f"Milvus not called with doc_id={doc_id}"
        )
        assert thread_id in milvus_calls, (
            f"Milvus not called with thread_id={thread_id}"
        )
        assert str(doc_id) in neo4j_calls, (
            f"Neo4j not called with doc_id={doc_id}"
        )
        assert thread_id in neo4j_calls, (
            f"Neo4j not called with thread_id={thread_id}"
        )

    def test_pdf_document_does_not_resolve_thread_id(self):
        """
        Property: For a PDF document, delete_document_completely() does
        NOT call Milvus/Neo4j with a separate thread_id (only doc_id).
        """
        doc_id = uuid4()
        db_row = _make_db_row("PDF")

        dm, mock_upload, mock_proc = _build_document_manager(
            upload_delete_ok=True,
        )

        mock_milvus = AsyncMock(return_value=3)
        mock_neo4j = AsyncMock(return_value=2)

        with (
            patch.object(dm, "_delete_from_milvus", mock_milvus),
            patch.object(dm, "_delete_from_neo4j", mock_neo4j),
            patch.object(dm, "_delete_pg_extras", new=AsyncMock()),
            patch(DB_MANAGER_PATCH_TARGET, create=True) as mock_db,
        ):
            _setup_db_mock(mock_db, db_row)
            results = _run(dm.delete_document_completely(doc_id))

        assert results["success"] is True

        # Milvus and Neo4j should be called only once (with doc_id)
        assert mock_milvus.call_count == 1, (
            f"Milvus called {mock_milvus.call_count} times for PDF doc "
            f"(expected 1)"
        )
        assert mock_neo4j.call_count == 1, (
            f"Neo4j called {mock_neo4j.call_count} times for PDF doc "
            f"(expected 1)"
        )


# ---------------------------------------------------------------------------
# Property 2d: _check_document_deleted does NOT raise for existing docs
# ---------------------------------------------------------------------------

class TestPreservation_CheckDocumentDeleted:
    """
    _check_document_deleted() must NOT raise DocumentDeletedError when
    the document still exists in knowledge_sources.

    Requirement 3.4: Running tasks proceed normally when document exists.
    """

    def test_check_document_deleted_does_not_raise_for_existing_doc(self):
        """
        Property: _check_document_deleted(doc_id) does not raise
        DocumentDeletedError when the knowledge_sources row exists.
        """
        doc_id = str(uuid4())

        with patch(
            "multimodal_librarian.services.celery_service._is_document_deleted",
            new=AsyncMock(return_value=False),
        ):
            from multimodal_librarian.services.celery_service import (
                _check_document_deleted,
            )

            # Should NOT raise
            _check_document_deleted(doc_id, stage="test_stage")

    def test_check_document_deleted_raises_for_deleted_doc(self):
        """
        Sanity check: _check_document_deleted(doc_id) DOES raise
        DocumentDeletedError when the knowledge_sources row is gone.
        """
        doc_id = str(uuid4())

        with patch(
            "multimodal_librarian.services.celery_service._is_document_deleted",
            new=AsyncMock(return_value=True),
        ):
            import pytest

            from multimodal_librarian.services.celery_service import (
                DocumentDeletedError,
                _check_document_deleted,
            )

            with pytest.raises(DocumentDeletedError):
                _check_document_deleted(doc_id, stage="test_stage")

    @given(stage=st.text(min_size=0, max_size=50))
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=5000,
    )
    def test_check_document_deleted_safe_for_any_stage_name(self, stage):
        """
        Property: For any stage name string, _check_document_deleted()
        does not raise when the document exists.
        """
        doc_id = str(uuid4())

        with patch(
            "multimodal_librarian.services.celery_service._is_document_deleted",
            new=AsyncMock(return_value=False),
        ):
            from multimodal_librarian.services.celery_service import (
                _check_document_deleted,
            )

            # Should NOT raise for any stage name
            _check_document_deleted(doc_id, stage=stage)


# ---------------------------------------------------------------------------
# Property 2e: Store cleanup order is preserved
# ---------------------------------------------------------------------------

class TestPreservation_StoreCleanupOrder:
    """
    The deletion flow must clean up stores in the correct order:
    cancel → Milvus → Neo4j → MinIO/PostgreSQL → extras.

    This captures the existing ordering so the fix doesn't accidentally
    reorder non-cancellation steps.
    """

    def test_store_cleanup_order_is_preserved(self):
        """
        Property: For a non-active-task PDF document, the store cleanup
        order is: cancel_processing → _delete_from_milvus →
        _delete_from_neo4j → upload_service.delete_document →
        _delete_pg_extras.
        """
        doc_id = uuid4()
        db_row = _make_db_row("PDF")

        dm, mock_upload, mock_proc = _build_document_manager(
            upload_delete_ok=True,
        )

        call_order = []

        async def track_cancel(did):
            call_order.append("cancel_processing")
            return True

        async def track_milvus(did, results):
            call_order.append("milvus")
            return 0

        async def track_neo4j(did, results):
            call_order.append("neo4j")
            return 0

        async def track_upload_delete(did):
            call_order.append("upload_delete")
            return True

        async def track_pg_extras(did, results):
            call_order.append("pg_extras")

        mock_proc.cancel_processing = AsyncMock(side_effect=track_cancel)
        mock_upload.delete_document = AsyncMock(side_effect=track_upload_delete)

        with (
            patch.object(dm, "_delete_from_milvus", side_effect=track_milvus),
            patch.object(dm, "_delete_from_neo4j", side_effect=track_neo4j),
            patch.object(dm, "_delete_pg_extras", side_effect=track_pg_extras),
            patch(DB_MANAGER_PATCH_TARGET, create=True) as mock_db,
        ):
            _setup_db_mock(mock_db, db_row)
            results = _run(dm.delete_document_completely(doc_id))

        assert results["success"] is True

        expected_order = [
            "cancel_processing",
            "milvus",
            "neo4j",
            "upload_delete",
            "pg_extras",
        ]
        assert call_order == expected_order, (
            f"Store cleanup order changed. "
            f"Expected: {expected_order}, Got: {call_order}"
        )
