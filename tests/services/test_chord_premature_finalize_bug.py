"""
Bug Condition Exploration Tests — Property 1: Skipped Duplicate Results
Cause Premature Finalization

These tests encode the EXPECTED (correct) behavior for chord finalization
when parallel_results contain skipped_duplicate entries. They are written
BEFORE the fix and are expected to FAIL on unfixed code, confirming the
bug exists.

Bug sub-conditions tested:
  1) finalize_processing_task with a skipped_duplicate bridge result and
     a completed KG result should mark the document FAILED — NOT COMPLETED.
  2) finalize_processing_task with a completed bridge result and a
     skipped_duplicate KG result should mark the document FAILED.
  3) finalize_processing_task with two skipped_duplicate results should
     mark the document FAILED.
  4) redis_task_lock decorator should raise Ignore() when the lock is
     already held — NOT return {'status': 'skipped_duplicate'}.

Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Generate document IDs
document_ids = st.uuids().map(str)

# KG failure data with realistic values
kg_failure_data = st.fixed_dictionaries({
    "ner_failures": st.integers(min_value=0, max_value=10),
    "llm_failures": st.integers(min_value=0, max_value=10),
    "total_chunks": st.integers(min_value=1, max_value=100),
})

# Bridge failure data with realistic values
bridge_failure_data = st.fixed_dictionaries({
    "failed_bridges": st.integers(min_value=0, max_value=10),
    "total_bridges": st.integers(min_value=1, max_value=100),
})


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


def _make_completed_kg_result(document_id, kg_failures=None):
    """Build a completed KG task result."""
    if kg_failures is None:
        kg_failures = {
            "ner_failures": 0,
            "llm_failures": 0,
            "total_chunks": 10,
        }
    return {
        "status": "completed",
        "document_id": document_id,
        "kg_failures": kg_failures,
        "concept_count": 5,
    }


def _make_completed_bridge_result(document_id, bridge_failures=None):
    """Build a completed bridge task result."""
    if bridge_failures is None:
        bridge_failures = {
            "failed_bridges": 0,
            "total_bridges": 10,
        }
    return {
        "status": "completed",
        "document_id": document_id,
        "bridge_failures": bridge_failures,
        "chunk_count": 10,
    }


def _make_skipped_duplicate_result(document_id):
    """Build a skipped_duplicate result from redis_task_lock."""
    return {
        "status": "skipped_duplicate",
        "document_id": document_id,
    }


# Common patch targets for finalize_processing_task
_CELERY_SVC = "multimodal_librarian.services.celery_service"


def _patch_finalize_dependencies():
    """Return a context manager that patches all external dependencies
    of finalize_processing_task so it can run in isolation."""
    from contextlib import contextmanager

    @contextmanager
    def _ctx():
        mock_update_doc = AsyncMock()
        mock_update_job = AsyncMock()
        mock_retrieve_payload = AsyncMock(return_value={
            "content_profile": {"content_type": "general"},
        })

        with (
            patch(
                f"{_CELERY_SVC}._cleanup_parallel_progress",
            ),
            patch(
                f"{_CELERY_SVC}._check_document_deleted",
            ),
            patch(
                f"{_CELERY_SVC}._update_document_status_sync",
                new=mock_update_doc,
            ),
            patch(
                f"{_CELERY_SVC}._update_job_status_sync",
                new=mock_update_job,
            ),
            patch(
                f"{_CELERY_SVC}._retrieve_processing_payload",
                new=mock_retrieve_payload,
            ),
            patch(
                f"{_CELERY_SVC}._record_stage_timing",
                new=AsyncMock(),
            ),
            patch(
                f"{_CELERY_SVC}._delete_processing_payload",
                new=AsyncMock(),
            ),
            patch(
                f"{_CELERY_SVC}._compute_composite_scores",
                new=AsyncMock(),
            ),
            patch(
                f"{_CELERY_SVC}._persist_quality_gate_data",
                new=AsyncMock(),
            ),
            patch(
                f"{_CELERY_SVC}.notify_processing_completion_sync",
                create=True,
            ),
            patch(
                f"{_CELERY_SVC}.notify_processing_failure_sync",
                create=True,
            ),
        ):
            yield {
                "update_doc": mock_update_doc,
                "update_job": mock_update_job,
            }

    return _ctx()


# ---------------------------------------------------------------------------
# Test Case 1: Duplicate bridge task + completed KG task
# ---------------------------------------------------------------------------

class TestBugCondition_SkippedDuplicateBridge:
    """
    When finalize_processing_task receives parallel_results containing
    a skipped_duplicate bridge result and a completed KG result, the
    document should be marked FAILED — NOT COMPLETED.

    On UNFIXED code: finalize logs a warning but proceeds to mark the
    document COMPLETED with missing bridge data. This test SHOULD FAIL.

    Counterexample (unfixed code): finalize_processing_task with
    parallel_results=[skipped_duplicate_bridge, completed_kg] logs
    WARNING "Subtask was skipped (duplicate lock)" but proceeds to
    mark document COMPLETED. bridge_failures defaults to
    {failed_bridges: 0, total_bridges: 0}, quality gate passes
    trivially (composite=0.0), and document is finalized with
    incomplete data.
    """

    @given(
        doc_id=document_ids,
        kg_failures=kg_failure_data,
    )
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=30000,
    )
    def test_skipped_duplicate_bridge_marks_document_failed(
        self, doc_id, kg_failures,
    ):
        """
        Property: For any parallel_results where the bridge task returned
        skipped_duplicate and the KG task completed normally,
        finalize_processing_task must mark the document as FAILED.

        Expected to FAIL on unfixed code because finalize proceeds
        with missing bridge data and marks the document COMPLETED.
        """
        from multimodal_librarian.models.documents import DocumentStatus
        from multimodal_librarian.services.celery_service import (
            finalize_processing_task,
        )

        parallel_results = [
            _make_skipped_duplicate_result(doc_id),
            _make_completed_kg_result(doc_id, kg_failures),
        ]

        with _patch_finalize_dependencies() as mocks:
            result = finalize_processing_task(parallel_results, doc_id)

        # The bug: finalize_processing_task logs a warning about
        # skipped_duplicate but continues, marking the document
        # COMPLETED with default zero bridge_failures.
        # The CORRECT behavior: document should be marked FAILED
        # because parallel_results contain a skipped_duplicate entry.
        assert result["status"] == "failed", (
            f"finalize_processing_task returned status='{result['status']}' "
            f"when parallel_results contained a skipped_duplicate bridge "
            f"result. Expected status='failed'. The document was finalized "
            f"with incomplete data (bug condition 1.2)."
        )

        # Verify document status was set to FAILED
        doc_status_calls = [
            call for call in mocks["update_doc"].call_args_list
            if len(call.args) >= 2
            and call.args[1] == DocumentStatus.FAILED
        ]
        assert len(doc_status_calls) > 0, (
            f"Document was never marked as FAILED. "
            f"update_document_status_sync calls: "
            f"{mocks['update_doc'].call_args_list}"
        )


# ---------------------------------------------------------------------------
# Test Case 2: Completed bridge task + duplicate KG task
# ---------------------------------------------------------------------------

class TestBugCondition_SkippedDuplicateKG:
    """
    When finalize_processing_task receives parallel_results containing
    a completed bridge result and a skipped_duplicate KG result, the
    document should be marked FAILED — NOT COMPLETED.

    On UNFIXED code: finalize logs a warning but proceeds with default
    zero kg_failures, which trivially passes the quality gate.
    This test SHOULD FAIL.
    """

    @given(
        doc_id=document_ids,
        bridge_failures=bridge_failure_data,
    )
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=30000,
    )
    def test_skipped_duplicate_kg_marks_document_failed(
        self, doc_id, bridge_failures,
    ):
        """
        Property: For any parallel_results where the KG task returned
        skipped_duplicate and the bridge task completed normally,
        finalize_processing_task must mark the document as FAILED.

        Expected to FAIL on unfixed code because finalize proceeds
        with default zero kg_failures (total_chunks=0) and the
        quality gate's kg_missing check may catch it — but the
        document should be rejected earlier at validation.
        """
        from multimodal_librarian.models.documents import DocumentStatus
        from multimodal_librarian.services.celery_service import (
            finalize_processing_task,
        )

        parallel_results = [
            _make_completed_bridge_result(doc_id, bridge_failures),
            _make_skipped_duplicate_result(doc_id),
        ]

        with _patch_finalize_dependencies() as mocks:
            result = finalize_processing_task(parallel_results, doc_id)

        # The bug: finalize_processing_task proceeds with default
        # kg_failures = {ner_failures: 0, llm_failures: 0, total_chunks: 0}.
        # The quality gate's kg_missing guard (total_chunks == 0) may
        # catch this, but the root cause is that finalize should reject
        # skipped_duplicate results BEFORE reaching the quality gate.
        # The CORRECT behavior: document should be marked FAILED
        # because parallel_results contain a skipped_duplicate entry.
        assert result["status"] == "failed", (
            f"finalize_processing_task returned status='{result['status']}' "
            f"when parallel_results contained a skipped_duplicate KG "
            f"result. Expected status='failed'. The document was finalized "
            f"with incomplete KG data (bug condition 1.3)."
        )

        # Verify document status was set to FAILED
        doc_status_calls = [
            call for call in mocks["update_doc"].call_args_list
            if len(call.args) >= 2
            and call.args[1] == DocumentStatus.FAILED
        ]
        assert len(doc_status_calls) > 0, (
            f"Document was never marked as FAILED. "
            f"update_document_status_sync calls: "
            f"{mocks['update_doc'].call_args_list}"
        )


# ---------------------------------------------------------------------------
# Test Case 3: Both tasks skipped_duplicate
# ---------------------------------------------------------------------------

class TestBugCondition_BothSkippedDuplicate:
    """
    When finalize_processing_task receives parallel_results where both
    tasks returned skipped_duplicate, the document should be marked
    FAILED — NOT COMPLETED.

    On UNFIXED code: finalize logs warnings but proceeds with all-zero
    defaults for both kg_failures and bridge_failures.
    This test SHOULD FAIL.
    """

    @given(doc_id=document_ids)
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=30000,
    )
    def test_both_skipped_duplicate_marks_document_failed(self, doc_id):
        """
        Property: For any parallel_results where both tasks returned
        skipped_duplicate, finalize_processing_task must mark the
        document as FAILED.

        Expected to FAIL on unfixed code because finalize proceeds
        with all-zero defaults and the quality gate may or may not
        catch it depending on the kg_missing guard.
        """
        from multimodal_librarian.models.documents import DocumentStatus
        from multimodal_librarian.services.celery_service import (
            finalize_processing_task,
        )

        parallel_results = [
            _make_skipped_duplicate_result(doc_id),
            _make_skipped_duplicate_result(doc_id),
        ]

        with _patch_finalize_dependencies() as mocks:
            result = finalize_processing_task(parallel_results, doc_id)

        # The bug: finalize_processing_task proceeds with all-zero
        # defaults. No real data from either task.
        # The CORRECT behavior: document should be marked FAILED.
        assert result["status"] == "failed", (
            f"finalize_processing_task returned status='{result['status']}' "
            f"when both parallel results were skipped_duplicate. "
            f"Expected status='failed'. No real data was available "
            f"(bug condition 1.2, 1.3)."
        )

        # Verify document status was set to FAILED
        doc_status_calls = [
            call for call in mocks["update_doc"].call_args_list
            if len(call.args) >= 2
            and call.args[1] == DocumentStatus.FAILED
        ]
        assert len(doc_status_calls) > 0, (
            f"Document was never marked as FAILED. "
            f"update_document_status_sync calls: "
            f"{mocks['update_doc'].call_args_list}"
        )


# ---------------------------------------------------------------------------
# Test Case 4: redis_task_lock returns dict instead of raising Ignore()
# ---------------------------------------------------------------------------

class TestBugCondition_RedisTaskLockReturnsDict:
    """
    When redis_task_lock detects the lock is already held, it should
    raise celery.exceptions.Ignore() — NOT return a dict with
    status='skipped_duplicate'.

    On UNFIXED code: the decorator returns a dict, which Celery stores
    in the result backend and the chord counts as a valid completion.
    This test SHOULD FAIL.

    Counterexample (unfixed code): redis_task_lock returns
    {'status': 'skipped_duplicate', 'document_id': '<id>'} instead of
    raising Ignore(). Celery stores this in the result backend and the
    chord counts it toward its completion threshold.
    """

    @given(doc_id=document_ids)
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=30000,
    )
    def test_redis_task_lock_raises_ignore_when_lock_held(self, doc_id):
        """
        Property: For any task invocation where redis_task_lock detects
        the lock is already held, the decorator must raise
        celery.exceptions.Ignore() — not return a result dict.

        Expected to FAIL on unfixed code because the decorator returns
        {'status': 'skipped_duplicate', 'document_id': ...}.
        """
        from celery.exceptions import Ignore

        from multimodal_librarian.services.redis_task_lock import redis_task_lock

        # Create a simple function decorated with redis_task_lock
        @redis_task_lock("test_lock:{document_id}")
        def dummy_task(upstream_result, document_id):
            return {"status": "completed", "document_id": document_id}

        # Mock Redis so the lock is already held (acquire returns False)
        mock_redis = MagicMock()
        mock_redis.set.return_value = False  # Lock NOT acquired

        with patch(
            "multimodal_librarian.services.redis_task_lock._get_redis_client",
            return_value=mock_redis,
        ):
            # The bug: dummy_task returns a dict instead of raising Ignore()
            # The CORRECT behavior: Ignore() is raised
            try:
                result = dummy_task({}, document_id=doc_id)
                # If we get here, the function returned instead of raising
                raise AssertionError(
                    f"redis_task_lock returned {result} instead of raising "
                    f"Ignore() when lock was already held. The chord will "
                    f"count this as a valid completion, causing premature "
                    f"finalization (bug condition 1.1, 1.4)."
                )
            except Ignore:
                # This is the CORRECT behavior — Ignore was raised
                pass
