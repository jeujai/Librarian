"""
Preservation Property Tests — Property 2: Normal Chord Completion
and Lock Behavior Unchanged

These tests capture the OBSERVED behavior of the UNFIXED code for
normal (non-bug-condition) inputs.  They must PASS on unfixed code,
confirming the baseline behavior that the fix must preserve.

Observations (on unfixed code):
  1) finalize_processing_task with two valid completed results
     (one with kg_failures, one with bridge_failures) returns
     {'status': 'completed', 'document_id': ...} and marks the
     document COMPLETED — provided the quality gate passes.
  2) finalize_processing_task with an aborted result (document
     deleted) returns {'status': 'aborted', 'document_id': ...}
     without updating document status.
  3) finalize_processing_task with a failed bridge result and a
     completed KG result still extracts bridge_failures data and
     runs the quality gate normally — bridge failure is non-fatal
     as long as the quality gate passes.
  4) redis_task_lock with no lock contention acquires the lock,
     executes the wrapped function, returns its result, and
     releases the lock.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**
"""

import asyncio
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Valid UUID strings (finalize_processing_task calls UUID(document_id))
document_ids = st.uuids().map(str)

# KG failure data — total_chunks >= 1 so quality gate doesn't fail on
# the kg_missing guard (total_chunks == 0 → gate fails).
kg_failure_data = st.fixed_dictionaries({
    "ner_failures": st.integers(min_value=0, max_value=5),
    "llm_failures": st.integers(min_value=0, max_value=5),
    "total_chunks": st.integers(min_value=1, max_value=100),
})

# Bridge failure data — keep failure rates low enough that the quality
# gate passes for "general" content type (threshold 0.20).
# composite = max(ner_rate, llm_rate) * 0.7 + bridge_rate * 0.3
# We constrain so that the composite stays ≤ 0.20.
bridge_failure_data = st.fixed_dictionaries({
    "failed_bridges": st.integers(min_value=0, max_value=5),
    "total_bridges": st.integers(min_value=10, max_value=100),
})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CELERY_SVC = "multimodal_librarian.services.celery_service"


@contextmanager
def _patch_finalize_dependencies():
    """Patch all external deps of finalize_processing_task for normal
    (non-abort) scenarios.  _check_document_deleted does NOT raise."""
    mock_update_doc = AsyncMock()
    mock_update_job = AsyncMock()
    mock_retrieve_payload = AsyncMock(return_value={
        "content_profile": {"content_type": "general"},
    })

    with (
        patch(f"{_CELERY_SVC}._cleanup_parallel_progress"),
        patch(f"{_CELERY_SVC}._check_document_deleted"),
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
        patch(f"{_CELERY_SVC}._record_stage_timing", new=AsyncMock()),
        patch(f"{_CELERY_SVC}._delete_processing_payload", new=AsyncMock()),
        patch(f"{_CELERY_SVC}._compute_composite_scores", new=AsyncMock()),
        patch(f"{_CELERY_SVC}._persist_quality_gate_data", new=AsyncMock()),
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


@contextmanager
def _patch_finalize_abort():
    """Patch for abort scenario — _check_document_deleted RAISES
    DocumentDeletedError so finalize returns early with 'aborted'."""
    from multimodal_librarian.services.celery_service import DocumentDeletedError

    mock_update_doc = AsyncMock()
    mock_update_job = AsyncMock()

    def _raise_deleted(*args, **kwargs):
        raise DocumentDeletedError("Document deleted")

    with (
        patch(f"{_CELERY_SVC}._cleanup_parallel_progress"),
        patch(
            f"{_CELERY_SVC}._check_document_deleted",
            side_effect=_raise_deleted,
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
            new=AsyncMock(return_value={
                "content_profile": {"content_type": "general"},
            }),
        ),
        patch(f"{_CELERY_SVC}._record_stage_timing", new=AsyncMock()),
        patch(f"{_CELERY_SVC}._delete_processing_payload", new=AsyncMock()),
        patch(f"{_CELERY_SVC}._compute_composite_scores", new=AsyncMock()),
        patch(f"{_CELERY_SVC}._persist_quality_gate_data", new=AsyncMock()),
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


def _make_completed_kg_result(document_id, kg_failures):
    """Build a completed KG task result."""
    return {
        "status": "completed",
        "document_id": document_id,
        "kg_failures": kg_failures,
        "concept_count": 5,
    }


def _make_completed_bridge_result(document_id, bridge_failures):
    """Build a completed bridge task result."""
    return {
        "status": "completed",
        "document_id": document_id,
        "bridge_failures": bridge_failures,
        "chunk_count": 10,
    }


def _quality_gate_would_pass(kg_failures, bridge_failures):
    """Return True if the quality gate would pass for 'general' content.

    Mirrors compute_quality_gate logic:
      ner_rate = ner_failures / total_chunks
      llm_rate = llm_failures / total_chunks
      bridge_rate = failed_bridges / total_bridges
      composite = max(ner_rate, llm_rate) * 0.7 + bridge_rate * 0.3
      threshold = 0.20 (general)
      passed = (total_chunks > 0) and (composite <= threshold)
    """
    tc = kg_failures["total_chunks"]
    if tc == 0:
        return False
    ner_rate = kg_failures["ner_failures"] / tc
    llm_rate = kg_failures["llm_failures"] / tc
    tb = bridge_failures["total_bridges"]
    bridge_rate = (
        bridge_failures["failed_bridges"] / tb if tb > 0 else 0.0
    )
    composite = max(ner_rate, llm_rate) * 0.7 + bridge_rate * 0.3
    return composite <= 0.20


# ---------------------------------------------------------------------------
# Test: Normal completion with two valid completed results
# ---------------------------------------------------------------------------

class TestPreservation_NormalCompletion:
    """
    For all parallel_results where both entries have status='completed'
    and contain the expected data keys (kg_failures, bridge_failures),
    finalize_processing_task produces the same behavior as observed on
    unfixed code: returns {'status': 'completed'} when the quality gate
    passes, or {'status': 'failed'} when it doesn't.

    **Validates: Requirements 3.1, 3.5**
    """

    @given(
        doc_id=document_ids,
        kg_failures=kg_failure_data,
        bridge_failures=bridge_failure_data,
    )
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=30000,
    )
    def test_normal_completion_preserves_behavior(
        self, doc_id, kg_failures, bridge_failures,
    ):
        """
        Property: For all valid completed parallel_results,
        finalize_processing_task returns 'completed' when the quality
        gate passes and 'failed' when it doesn't — matching observed
        unfixed-code behavior.

        **Validates: Requirements 3.1, 3.5**
        """
        from multimodal_librarian.services.celery_service import (
            finalize_processing_task,
        )

        parallel_results = [
            _make_completed_kg_result(doc_id, kg_failures),
            _make_completed_bridge_result(doc_id, bridge_failures),
        ]

        gate_passes = _quality_gate_would_pass(kg_failures, bridge_failures)

        with _patch_finalize_dependencies() as mocks:
            result = finalize_processing_task(parallel_results, doc_id)

        if gate_passes:
            assert result["status"] == "completed", (
                f"Expected status='completed' when quality gate passes, "
                f"got '{result['status']}'. "
                f"kg_failures={kg_failures}, bridge_failures={bridge_failures}"
            )
            assert result["document_id"] == doc_id
        else:
            assert result["status"] == "failed", (
                f"Expected status='failed' when quality gate fails, "
                f"got '{result['status']}'. "
                f"kg_failures={kg_failures}, bridge_failures={bridge_failures}"
            )
            assert result["document_id"] == doc_id


# ---------------------------------------------------------------------------
# Test: Abort handling (document deleted)
# ---------------------------------------------------------------------------

class TestPreservation_AbortHandling:
    """
    For all parallel_results where the document is deleted during
    processing (_check_document_deleted raises DocumentDeletedError),
    finalize_processing_task returns {'status': 'aborted'} without
    updating document status.

    **Validates: Requirements 3.2**
    """

    @given(
        doc_id=document_ids,
        kg_failures=kg_failure_data,
        bridge_failures=bridge_failure_data,
    )
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=30000,
    )
    def test_abort_preserves_behavior(
        self, doc_id, kg_failures, bridge_failures,
    ):
        """
        Property: For all inputs where the document is deleted,
        finalize_processing_task returns 'aborted' and does not
        update document status — matching observed unfixed-code
        behavior.

        **Validates: Requirements 3.2**
        """
        from multimodal_librarian.services.celery_service import (
            finalize_processing_task,
        )

        parallel_results = [
            _make_completed_kg_result(doc_id, kg_failures),
            _make_completed_bridge_result(doc_id, bridge_failures),
        ]

        with _patch_finalize_abort() as mocks:
            result = finalize_processing_task(parallel_results, doc_id)

        assert result["status"] == "aborted", (
            f"Expected status='aborted' when document is deleted, "
            f"got '{result['status']}'."
        )
        assert result["document_id"] == doc_id
        # Document status should NOT be updated on abort
        assert mocks["update_doc"].call_count == 0, (
            f"Document status should not be updated on abort, "
            f"but update_doc was called: {mocks['update_doc'].call_args_list}"
        )


# ---------------------------------------------------------------------------
# Test: Bridge failure with completed KG (non-fatal)
# ---------------------------------------------------------------------------

class TestPreservation_BridgeFailure:
    """
    For all parallel_results where the bridge task has status='failed'
    and the KG task completed normally, finalize_processing_task still
    extracts bridge_failures data and runs the quality gate. Bridge
    failure is non-fatal — the outcome depends on the quality gate.

    **Validates: Requirements 3.3**
    """

    @given(
        doc_id=document_ids,
        kg_failures=kg_failure_data,
        bridge_failures=bridge_failure_data,
    )
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=30000,
    )
    def test_bridge_failure_preserves_behavior(
        self, doc_id, kg_failures, bridge_failures,
    ):
        """
        Property: For all inputs where the bridge task failed but KG
        completed, finalize_processing_task still runs the quality
        gate and produces a result (completed or failed) — matching
        observed unfixed-code behavior. Bridge failure is non-fatal.

        **Validates: Requirements 3.3**
        """
        from multimodal_librarian.services.celery_service import (
            finalize_processing_task,
        )

        parallel_results = [
            _make_completed_kg_result(doc_id, kg_failures),
            {
                "status": "failed",
                "document_id": doc_id,
                "bridge_failures": bridge_failures,
            },
        ]

        gate_passes = _quality_gate_would_pass(kg_failures, bridge_failures)

        with _patch_finalize_dependencies() as mocks:
            result = finalize_processing_task(parallel_results, doc_id)

        if gate_passes:
            assert result["status"] == "completed", (
                f"Expected status='completed' when quality gate passes "
                f"despite bridge failure, got '{result['status']}'."
            )
        else:
            assert result["status"] == "failed", (
                f"Expected status='failed' when quality gate fails, "
                f"got '{result['status']}'."
            )
        assert result["document_id"] == doc_id


# ---------------------------------------------------------------------------
# Test: redis_task_lock with no contention
# ---------------------------------------------------------------------------

class TestPreservation_LockNoContention:
    """
    For all task invocations where redis_task_lock successfully acquires
    the lock (no contention), the decorator executes the wrapped function
    and returns its result normally.

    **Validates: Requirements 3.4**
    """

    @given(doc_id=document_ids)
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=30000,
    )
    def test_lock_no_contention_preserves_behavior(self, doc_id):
        """
        Property: For all task invocations where the lock is acquired
        successfully, redis_task_lock executes the wrapped function
        and returns its result unchanged.

        **Validates: Requirements 3.4**
        """
        from multimodal_librarian.services.redis_task_lock import redis_task_lock

        sentinel = {"status": "completed", "document_id": doc_id, "v": 42}

        @redis_task_lock("test_lock:{document_id}")
        def dummy_task(upstream_result, document_id):
            return sentinel

        mock_redis = MagicMock()
        mock_redis.set.return_value = True  # Lock acquired

        with patch(
            "multimodal_librarian.services.redis_task_lock._get_redis_client",
            return_value=mock_redis,
        ):
            result = dummy_task({}, document_id=doc_id)

        assert result is sentinel, (
            f"Expected the wrapped function's exact return value, "
            f"got {result}"
        )
        # Lock was acquired
        mock_redis.set.assert_called_once()
        # Lock was released (eval called with release Lua script)
        assert mock_redis.eval.called, "Lock should be released after execution"
