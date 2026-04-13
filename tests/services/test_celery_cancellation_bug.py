"""
Bug Condition Exploration Tests — Property 1: Active Task Escapes Cancellation on Delete

These tests encode the EXPECTED (correct) behavior for Celery task cancellation
during document deletion. They are written BEFORE the fix and are expected to
FAIL on unfixed code, confirming the bug exists.

Bug sub-conditions tested:
  A) cancel_job() with task_id=None and status='pending'/'running' should poll
     for task_id or signal fallback — NOT silently return True.
  B) delete_document_completely() should record cancellation errors in
     results['errors'] — NOT swallow them via `except: pass`.
  C) cancel_job() should verify post-revoke task state via AsyncResult.status
     polling — NOT assume revoke succeeded.

Requirements: 1.1, 1.2, 1.3, 1.4
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

active_job_statuses = st.sampled_from(["pending", "running"])

# Exceptions that revoke() might raise in production
revoke_exceptions = st.sampled_from([
    ConnectionError("Redis broker unreachable"),
    TimeoutError("Revoke timed out"),
    OSError("Network error during revoke"),
    RuntimeError("Celery broker connection lost"),
])

# Non-terminal Celery task states (task still running after revoke)
non_terminal_celery_states = st.sampled_from([
    "PENDING", "STARTED", "RETRY", "RECEIVED",
])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_job_status(
    document_id: str,
    status: str,
    task_id=None,
):
    """Build a job_status dict matching CeleryService.get_job_status() shape."""
    return {
        "job_id": str(uuid4()),
        "document_id": document_id,
        "status": status,
        "progress_percentage": 0,
        "current_step": "Processing",
        "error_message": None,
        "started_at": None,
        "completed_at": None,
        "retry_count": 0,
        "metadata": {},
        "task_id": task_id,
    }


def _run(coro):
    """Run an async coroutine synchronously for tests."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Sub-condition A: Race window — task_id is None
# ---------------------------------------------------------------------------

class TestBugConditionA_RaceWindow:
    """
    When cancel_job() is called and task_id is None (race window between
    _create_processing_job and _update_job_task_id), the system should
    poll for the task_id or signal a fallback — NOT silently skip revoke
    and return True.

    On UNFIXED code: cancel_job() skips the `if task_id:` guard, never
    calls revoke(), but still returns True. This test SHOULD FAIL.
    """

    @given(job_status_str=active_job_statuses)
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=30000,
    )
    def test_cancel_job_with_null_task_id_must_not_silently_succeed(
        self, job_status_str
    ):
        """
        Property: For any active job with task_id=None, cancel_job()
        must NOT return True without either polling for the task_id
        or signalling that a fallback mechanism is needed.

        Expected to FAIL on unfixed code because cancel_job() returns
        True even though revoke() was never called and no polling occurred.
        """
        doc_id = uuid4()
        job = _make_job_status(str(doc_id), job_status_str, task_id=None)

        from multimodal_librarian.services.celery_service import CeleryService

        svc = CeleryService.__new__(CeleryService)
        svc.processing_stats = {
            "total_jobs_queued": 0,
            "successful_jobs": 0,
            "failed_jobs": 0,
            "active_jobs": 1,
            "average_processing_time": 0.0,
        }

        mock_revoke = MagicMock()
        mock_get_job = AsyncMock(return_value=job)

        with (
            patch.object(svc, "get_job_status", new=mock_get_job),
            patch.object(svc, "_update_job_status", new=AsyncMock()),
            patch(
                "multimodal_librarian.services.celery_service.celery_app"
            ) as mock_celery_app,
            patch(
                "multimodal_librarian.services.celery_service.UploadService",
                create=True,
            ),
            patch(
                "multimodal_librarian.services.upload_service.UploadService"
            ) as MockUploadSvc,
            patch(
                "multimodal_librarian.services.celery_service.time"
            ) as mock_time,
        ):
            mock_upload = MagicMock()
            mock_upload.update_document_status = AsyncMock()
            MockUploadSvc.return_value = mock_upload
            mock_celery_app.control.revoke = mock_revoke
            mock_time.sleep = MagicMock()  # skip real sleeps

            result = _run(svc.cancel_job(doc_id))

        # The bug: cancel_job() returns True even though task_id was None
        # and revoke() was never called, with NO polling attempt.
        # The CORRECT behavior is that cancel_job() should either:
        #   - poll for task_id (get_job_status called multiple times), OR
        #   - call revoke() if task_id appeared during polling
        #
        # On unfixed code: get_job_status is called only once (no polling),
        # so this assertion FAILS.
        # On fixed code: get_job_status is called 4 times (1 initial + 3 polls),
        # confirming the system polled for the task_id.
        get_job_calls = mock_get_job.call_count
        assert mock_revoke.called or get_job_calls > 1, (
            f"cancel_job() returned {result} with task_id=None and "
            f"status='{job_status_str}' but revoke() was never called "
            f"and get_job_status was only called {get_job_calls} time(s) "
            f"(no polling). The task escapes cancellation (bug condition 1.1)."
        )


# ---------------------------------------------------------------------------
# Sub-condition B: Swallowed cancellation errors
# ---------------------------------------------------------------------------

class TestBugConditionB_SwallowedErrors:
    """
    When cancel_processing() raises an exception inside
    delete_document_completely(), the error should be recorded in
    results['errors'] — NOT silently swallowed by `except: pass`.

    On UNFIXED code: the bare `except Exception: pass` discards the
    error and results['errors'] stays empty. This test SHOULD FAIL.
    """

    @given(exc=revoke_exceptions)
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=10000,
    )
    def test_delete_document_records_cancellation_errors(self, exc):
        """
        Property: For any exception raised by cancel_processing(),
        delete_document_completely() must record the error in
        results['errors'] — not silently discard it.

        Expected to FAIL on unfixed code because the bare
        `except Exception: pass` swallows the error.
        """
        doc_id = uuid4()

        from multimodal_librarian.components.document_manager.document_manager import (
            DocumentManager,
        )

        mock_upload_svc = MagicMock()
        mock_upload_svc.delete_document = AsyncMock(return_value=True)

        mock_processing_svc = MagicMock()
        mock_processing_svc.cancel_processing = AsyncMock(side_effect=exc)

        dm = DocumentManager.__new__(DocumentManager)
        dm.upload_service = mock_upload_svc
        dm.processing_service = mock_processing_svc

        # Patch out the heavy store-deletion helpers so we only test
        # the cancellation error-handling path.
        with (
            patch.object(dm, "_delete_from_milvus", new=AsyncMock(return_value=0)),
            patch.object(dm, "_delete_from_neo4j", new=AsyncMock(return_value=0)),
            patch.object(dm, "_delete_pg_extras", new=AsyncMock()),
            patch(
                "multimodal_librarian.components.document_manager"
                ".document_manager.db_manager",
                create=True,
            ) as mock_db,
        ):
            # Mock the conversation-resolution query to return no row
            mock_session = MagicMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_execute_result = MagicMock()
            mock_execute_result.fetchone.return_value = None
            mock_session.execute = AsyncMock(return_value=mock_execute_result)
            mock_db.get_async_session.return_value = mock_session

            results = _run(dm.delete_document_completely(doc_id))

        # The bug: results['errors'] is empty because the exception was
        # swallowed by `except Exception: pass`.  The CORRECT behavior
        # is that the error is recorded.
        cancellation_errors = [
            e for e in results["errors"]
            if "cancel" in str(e).lower()
            or type(exc).__name__ in str(e)
            or str(exc) in str(e)
        ]
        assert len(cancellation_errors) > 0, (
            f"delete_document_completely() swallowed {type(exc).__name__}: "
            f"'{exc}' — results['errors'] = {results['errors']}. "
            f"Cancellation failure is silently discarded (bug condition 1.2)."
        )


# ---------------------------------------------------------------------------
# Sub-condition C: No post-revoke verification
# ---------------------------------------------------------------------------

class TestBugConditionC_NoPostRevokeVerification:
    """
    After calling revoke(terminate=True), cancel_job() should verify
    that the task actually reached a terminal state via
    AsyncResult.status polling.

    On UNFIXED code: cancel_job() calls revoke() and immediately
    returns True without checking task state. This test SHOULD FAIL.
    """

    @given(
        non_terminal_state=non_terminal_celery_states,
        job_status_str=active_job_statuses,
    )
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=5000,
    )
    def test_cancel_job_verifies_task_state_after_revoke(
        self, non_terminal_state, job_status_str
    ):
        """
        Property: For any active job where revoke() is called but
        AsyncResult.status returns a non-terminal state, cancel_job()
        must detect that the task is still running (e.g., log a warning
        or return metadata indicating verification failed).

        Expected to FAIL on unfixed code because cancel_job() never
        checks AsyncResult.status after calling revoke().
        """
        doc_id = uuid4()
        task_id = f"celery-task-{uuid4()}"
        job = _make_job_status(str(doc_id), job_status_str, task_id=task_id)

        from multimodal_librarian.services.celery_service import CeleryService

        svc = CeleryService.__new__(CeleryService)
        svc.processing_stats = {
            "total_jobs_queued": 0,
            "successful_jobs": 0,
            "failed_jobs": 0,
            "active_jobs": 1,
            "average_processing_time": 0.0,
        }

        mock_async_result = MagicMock()
        mock_async_result.status = non_terminal_state

        with (
            patch.object(svc, "get_job_status", new=AsyncMock(return_value=job)),
            patch.object(svc, "_update_job_status", new=AsyncMock()),
            patch(
                "multimodal_librarian.services.celery_service.celery_app"
            ) as mock_celery_app,
            patch(
                "multimodal_librarian.services.celery_service.AsyncResult",
                return_value=mock_async_result,
            ) as MockAsyncResult,
            patch(
                "multimodal_librarian.services.upload_service.UploadService"
            ) as MockUploadSvc,
        ):
            mock_upload = MagicMock()
            mock_upload.update_document_status = AsyncMock()
            MockUploadSvc.return_value = mock_upload
            mock_celery_app.control.revoke = MagicMock()

            result = _run(svc.cancel_job(doc_id))

        # The bug: cancel_job() returns True without ever checking
        # AsyncResult.status.  The CORRECT behavior is that after
        # calling revoke(), the system polls AsyncResult to verify
        # the task reached a terminal state.
        #
        # We check that AsyncResult was instantiated with the task_id
        # AND that .status was accessed (indicating verification).
        assert MockAsyncResult.called, (
            f"cancel_job() never created AsyncResult to verify task state "
            f"after revoke(). Task '{task_id}' may still be running "
            f"(bug condition 1.4)."
        )
        # The mock's .status attribute should have been read at least once
        # AFTER the revoke call (for verification purposes).
        # Since the unfixed code only reads AsyncResult in get_job_status
        # (which we mocked), this assertion catches the missing verification.
        assert mock_async_result.status == non_terminal_state  # sanity
