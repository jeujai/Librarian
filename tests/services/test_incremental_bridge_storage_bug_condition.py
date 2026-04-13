"""
Bug Condition Exploration Tests — Incremental Bridge Storage

Property 1: Bug Condition - Milvus Storage Failure After Full Bridge Generation

These tests encode the EXPECTED (correct) behavior for incremental bridge storage.
They are written BEFORE the fix and are expected to FAIL on unfixed code,
confirming the bug exists.

Bug Condition: When Milvus storage fails after generating N bridges (N > 0),
the system should have stored some bridges incrementally before the failure.
On unfixed code, bridges_stored_before_failure = 0 despite bridges being generated.

Expected Behavior: bridges_stored_before_failure > 0 for any failure after at
least one batch completes.

Requirements: 1.1, 1.2, 1.3, 1.4
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
from hypothesis import HealthCheck, Phase, given, settings
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Test Data Structures
# ---------------------------------------------------------------------------

@dataclass
class StorageTracker:
    """Tracks storage calls to verify incremental vs batch storage."""
    postgres_calls: List[Tuple[str, int]] = field(default_factory=list)
    milvus_calls: List[Tuple[str, int]] = field(default_factory=list)
    milvus_should_fail_after: int = 0  # Fail after N successful calls
    milvus_failure_exception: Optional[Exception] = None
    
    @property
    def total_bridges_stored_in_postgres(self) -> int:
        return sum(count for _, count in self.postgres_calls)
    
    @property
    def total_bridges_stored_in_milvus(self) -> int:
        return sum(count for _, count in self.milvus_calls)


def create_mock_bridge_generation_data(num_bridges: int) -> Dict[str, Any]:
    """Create mock bridge generation data for testing."""
    bridge_needed_data = []
    for i in range(num_bridges):
        bridge_needed_data.append({
            'chunk1_id': str(uuid.uuid4()),
            'chunk2_id': str(uuid.uuid4()),
            'chunk1_content': f'Content of chunk {i}. This is sample text for testing bridge generation.',
            'chunk2_content': f'Content of chunk {i + 1}. More sample text for the next chunk.',
            'gap_type': 'conceptual',
            'bridge_strategy': 'semantic_overlap',
            'necessity_score': 0.8,
            'semantic_distance': 0.3,
            'concept_overlap': 0.5,
            'boundary_index': i,
        })
    
    return {
        'bridge_needed': bridge_needed_data,
        'content_type': 'general',
        'domain_config_dict': {
            'domain_name': 'test',
            'bridge_thresholds': {},
            'preservation_patterns': [],
        },
        'all_unresolved_bisections': {},
    }


# ---------------------------------------------------------------------------
# Test Class: Bug Condition Exploration - Code Structure Analysis
# ---------------------------------------------------------------------------

class TestBugConditionCodeAnalysis:
    """
    Analyze the code structure to confirm the fix has been applied.
    
    These tests inspect the source code to verify:
    1. Storage callback parameter exists in batch_generate_bridges
    2. Incremental storage pattern in generate_bridges_task
    """

    def test_current_implementation_has_incremental_storage(self):
        """
        FIX VERIFICATION — Verify that the current implementation has
        incremental storage via storage callback.
        
        After the fix, generate_bridges_task should pass a storage_callback
        to generate_bridges_for_document.
        """
        import inspect

        from multimodal_librarian.services.celery_service import generate_bridges_task

        # Get the underlying function, not the Celery task wrapper
        func = generate_bridges_task
        while hasattr(func, '__wrapped__'):
            func = func.__wrapped__
        
        source = inspect.getsource(func)
        
        # The fix pattern: storage_callback is defined and passed
        has_storage_callback = 'storage_callback=' in source or '_incremental_storage_callback' in source
        
        # Verify storage callback is used
        assert has_storage_callback, (
            "Expected incremental storage callback in generate_bridges_task"
        )

    def test_batch_generate_bridges_has_storage_callback(self):
        """
        FIX VERIFICATION — Verify that batch_generate_bridges HAS
        a storage callback parameter (the fix has been applied).
        """
        import inspect

        from multimodal_librarian.components.chunking_framework.bridge_generator import (
            SmartBridgeGenerator,
        )
        
        sig = inspect.signature(SmartBridgeGenerator.batch_generate_bridges)
        param_names = list(sig.parameters.keys())
        
        # The fix: storage_callback parameter exists
        has_storage_callback = 'storage_callback' in param_names
        
        assert has_storage_callback, (
            "Expected batch_generate_bridges to have storage_callback parameter. "
            "The fix should add this parameter for incremental storage."
        )

    def test_generate_bridges_task_has_incremental_storage_pattern(self):
        """
        FIX VERIFICATION — Verify that generate_bridges_task uses
        incremental storage via callback, not batch-then-store.
        """
        import inspect

        from multimodal_librarian.services.celery_service import generate_bridges_task

        # Get the underlying function, not the Celery task wrapper
        func = generate_bridges_task
        while hasattr(func, '__wrapped__'):
            func = func.__wrapped__
        
        source = inspect.getsource(func)
        
        # The fix pattern: storage callback is defined and passed to generate_bridges_for_document
        has_incremental_storage = (
            '_incremental_storage_callback' in source
            and 'storage_callback=_incremental_storage_callback' in source
        )
        
        assert has_incremental_storage, (
            "Expected incremental storage callback pattern in generate_bridges_task. "
            "The fix should define _incremental_storage_callback and pass it to "
            "generate_bridges_for_document."
        )


# ---------------------------------------------------------------------------
# Test Class: Bug Condition Exploration - Runtime Behavior
# ---------------------------------------------------------------------------

class TestBugConditionRuntimeBehavior:
    """
    Test the actual runtime behavior to confirm the bug.
    
    These tests mock the dependencies and call the real generate_bridges_task
    to verify that when Milvus fails, no bridges have been stored incrementally.
    """

    @pytest.fixture
    def storage_tracker(self):
        """Create a storage tracker for monitoring calls."""
        return StorageTracker()

    def _run_generate_bridges_task_with_mocks(
        self, 
        storage_tracker: StorageTracker,
        document_id: str,
        num_bridges: int,
    ) -> Dict[str, Any]:
        """
        Run the generate_bridges_task with all external dependencies mocked.
        
        This bypasses Redis, Celery, and database connections to test the
        core logic of the task.
        """
        from multimodal_librarian.components.chunking_framework.bridge_generator import (
            BatchGenerationStats,
            BridgeChunk,
        )

        # Create mock bridges
        mock_bridges = []
        for i in range(num_bridges):
            bridge = MagicMock(spec=BridgeChunk)
            bridge.id = str(uuid.uuid4())
            bridge.content = f"Bridge content {i}"
            bridge.source_chunks = [str(uuid.uuid4()), str(uuid.uuid4())]
            bridge.generation_method = "gemini_25_flash"
            bridge.confidence_score = 0.85
            mock_bridges.append(bridge)
        
        mock_stats = BatchGenerationStats(
            total_requests=num_bridges,
            successful_generations=num_bridges,
            failed_generations=0,
            total_tokens_used=1000,
            total_cost_estimate=0.01,
            average_generation_time=0.5,
            batch_processing_time=60.0,
        )
        
        # Track storage calls
        async def mock_store_postgres(doc_id, bridges):
            storage_tracker.postgres_calls.append((doc_id, len(bridges)))
        
        async def mock_store_milvus(doc_id, bridges, document_title=None):
            # Record the call before failing
            storage_tracker.milvus_calls.append((doc_id, len(bridges)))
            raise Exception("gRPC connection timeout - Milvus unavailable")
        
        # Create mock db_manager
        mock_db_manager = MagicMock()
        mock_db_manager.AsyncSessionLocal = MagicMock()
        mock_db_manager.initialize = MagicMock()
        
        # Get the underlying function without decorators
        from multimodal_librarian.services.celery_service import generate_bridges_task
        func = generate_bridges_task
        while hasattr(func, '__wrapped__'):
            func = func.__wrapped__
        
        # Create a mock for generate_bridges_for_document that invokes the storage callback
        # This simulates the incremental storage behavior
        batch_size = 60
        def mock_generate_bridges_for_document(bridge_generation_data, progress_callback=None, storage_callback=None):
            # Invoke storage callback for each batch to simulate incremental storage
            if storage_callback:
                for i in range(0, num_bridges, batch_size):
                    batch_end = min(i + batch_size, num_bridges)
                    batch_bridges = mock_bridges[i:batch_end]
                    storage_callback(batch_bridges)
            return (mock_bridges, mock_stats)
        
        # Mock all dependencies
        with patch.multiple(
            'multimodal_librarian.services.celery_service',
            _check_document_deleted=MagicMock(),
            _retrieve_processing_payload=AsyncMock(return_value={
                'bridge_generation_data': create_mock_bridge_generation_data(num_bridges),
                'chunks': [{'metadata': {'title': 'Test Document'}}],
            }),
            _update_job_status_sync=AsyncMock(),
            _set_parallel_progress=MagicMock(return_value=50),
            _get_parallel_step_label=MagicMock(return_value="Generating bridges"),
            _store_bridge_chunks_in_database=mock_store_postgres,
            _store_bridge_embeddings_in_vector_db=mock_store_milvus,
            _record_stage_timing=AsyncMock(),
        ), patch(
            'multimodal_librarian.database.connection.db_manager',
            mock_db_manager
        ), patch(
            'multimodal_librarian.components.chunking_framework.framework.'
            'GenericMultiLevelChunkingFramework.generate_bridges_for_document',
            side_effect=mock_generate_bridges_for_document
        ):
            # Call the underlying function directly (bypassing Celery and Redis decorators)
            result = func({}, document_id)
        
        return result

    def test_milvus_failure_after_bridge_generation_loses_all_bridges(
        self, storage_tracker
    ):
        """
        BUG CONDITION TEST — After the fix, this test verifies that bridges
        ARE stored incrementally before Milvus failure.
        
        With incremental storage:
        - Storage callback is invoked per batch
        - First batch is stored successfully in PostgreSQL
        - Milvus fails on first batch, but PostgreSQL storage succeeded
        - bridges_stored_before_failure > 0
        
        EXPECTED OUTCOME: Test PASSES (confirms bug is fixed)
        """
        document_id = str(uuid.uuid4())
        num_bridges = 120  # 2 batches worth (batch_size=60)
        
        result = self._run_generate_bridges_task_with_mocks(
            storage_tracker, document_id, num_bridges
        )
        
        # With incremental storage, Milvus is called per batch (until failure)
        # The first batch should trigger a Milvus call that fails
        assert len(storage_tracker.milvus_calls) >= 1, (
            f"Expected at least 1 Milvus call with incremental storage, got {len(storage_tracker.milvus_calls)}"
        )
        
        # The task should have failed or be partial (due to Milvus error)
        assert result['status'] in ('failed', 'partial'), (
            f"Expected task to fail or be partial on Milvus error, got status: {result['status']}"
        )
        
        # FIX VERIFICATION — With incremental storage, PostgreSQL should have stored
        # at least the first batch before Milvus failed
        # Note: PostgreSQL storage happens before Milvus in the callback
        bridges_stored_in_postgres = storage_tracker.total_bridges_stored_in_postgres
        expected_min_stored = 60  # At least one batch should be stored in PostgreSQL
        
        assert bridges_stored_in_postgres >= expected_min_stored, (
            f"FIX VERIFICATION: {num_bridges} bridges generated, "
            f"Milvus storage failed, {bridges_stored_in_postgres} bridges "
            f"stored in PostgreSQL before failure. Expected at least {expected_min_stored} "
            f"bridges to be stored incrementally before the failure. "
            f"PostgreSQL storage was called {len(storage_tracker.postgres_calls)} time(s) "
            f"with {[c[1] for c in storage_tracker.postgres_calls]} bridges each."
        )

    @given(
        num_bridges=st.integers(min_value=61, max_value=200),
    )
    @settings(
        max_examples=5,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        phases=[Phase.generate],  # Skip shrinking for faster execution
        deadline=None,
    )
    def test_property_no_incremental_storage_on_any_bridge_count(
        self, num_bridges: int
    ):
        """
        Property: For ALL bridge counts > batch_size, when Milvus fails,
        the system SHOULD have stored some bridges incrementally in PostgreSQL.
        
        After the fix: bridges_stored_in_postgres >= batch_size (at least first batch stored)
        
        **Validates: Requirements 2.1, 2.2, 2.3**
        """
        storage_tracker = StorageTracker()
        document_id = str(uuid.uuid4())
        batch_size = 60
        
        result = self._run_generate_bridges_task_with_mocks(
            storage_tracker, document_id, num_bridges
        )
        
        # With incremental storage, PostgreSQL should have stored at least the first batch
        # before Milvus failed (PostgreSQL storage happens before Milvus in the callback)
        bridges_stored_in_postgres = storage_tracker.total_bridges_stored_in_postgres
        expected_min_stored = batch_size  # At least first batch should be stored
        
        assert bridges_stored_in_postgres >= expected_min_stored, (
            f"FIX VERIFICATION: {num_bridges} bridges generated, "
            f"Milvus failed, {bridges_stored_in_postgres} bridges stored in PostgreSQL. "
            f"Expected at least {expected_min_stored} with incremental storage. "
            f"PostgreSQL storage was called {len(storage_tracker.postgres_calls)} time(s) "
            f"with {[c[1] for c in storage_tracker.postgres_calls]} bridges each."
        )


# ---------------------------------------------------------------------------
# Test Class: Counterexample Documentation
# ---------------------------------------------------------------------------

class TestBugConditionCounterexamples:
    """
    Document specific counterexamples that demonstrate the bug.
    
    These tests serve as documentation of the bug's impact.
    """

    def _run_generate_bridges_task_with_mocks(
        self, 
        storage_tracker: StorageTracker,
        document_id: str,
        num_bridges: int,
    ) -> Dict[str, Any]:
        """Run the task with mocks - same as in TestBugConditionRuntimeBehavior."""
        from multimodal_librarian.components.chunking_framework.bridge_generator import (
            BatchGenerationStats,
            BridgeChunk,
        )
        
        mock_bridges = []
        for i in range(num_bridges):
            bridge = MagicMock(spec=BridgeChunk)
            bridge.id = str(uuid.uuid4())
            bridge.content = f"Bridge content {i}"
            bridge.source_chunks = [str(uuid.uuid4()), str(uuid.uuid4())]
            bridge.generation_method = "gemini_25_flash"
            bridge.confidence_score = 0.85
            mock_bridges.append(bridge)
        
        mock_stats = BatchGenerationStats(
            total_requests=num_bridges,
            successful_generations=num_bridges,
            failed_generations=0,
            total_tokens_used=1000,
            total_cost_estimate=0.01,
            average_generation_time=0.5,
            batch_processing_time=60.0,
        )
        
        async def mock_store_postgres(doc_id, bridges):
            storage_tracker.postgres_calls.append((doc_id, len(bridges)))
        
        async def mock_store_milvus(doc_id, bridges, document_title=None):
            storage_tracker.milvus_calls.append((doc_id, len(bridges)))
            raise Exception("gRPC timeout - Milvus unavailable")
        
        mock_db_manager = MagicMock()
        mock_db_manager.AsyncSessionLocal = MagicMock()
        mock_db_manager.initialize = MagicMock()
        
        from multimodal_librarian.services.celery_service import generate_bridges_task
        func = generate_bridges_task
        while hasattr(func, '__wrapped__'):
            func = func.__wrapped__
        
        # Create a mock for generate_bridges_for_document that invokes the storage callback
        batch_size = 60
        def mock_generate_bridges_for_document(bridge_generation_data, progress_callback=None, storage_callback=None):
            # Invoke storage callback for each batch to simulate incremental storage
            if storage_callback:
                for i in range(0, num_bridges, batch_size):
                    batch_end = min(i + batch_size, num_bridges)
                    batch_bridges = mock_bridges[i:batch_end]
                    storage_callback(batch_bridges)
            return (mock_bridges, mock_stats)
        
        with patch.multiple(
            'multimodal_librarian.services.celery_service',
            _check_document_deleted=MagicMock(),
            _retrieve_processing_payload=AsyncMock(return_value={
                'bridge_generation_data': create_mock_bridge_generation_data(num_bridges),
                'chunks': [{'metadata': {'title': 'Test Document'}}],
            }),
            _update_job_status_sync=AsyncMock(),
            _set_parallel_progress=MagicMock(return_value=50),
            _get_parallel_step_label=MagicMock(return_value="Generating bridges"),
            _store_bridge_chunks_in_database=mock_store_postgres,
            _store_bridge_embeddings_in_vector_db=mock_store_milvus,
            _record_stage_timing=AsyncMock(),
        ), patch(
            'multimodal_librarian.database.connection.db_manager',
            mock_db_manager
        ), patch(
            'multimodal_librarian.components.chunking_framework.framework.'
            'GenericMultiLevelChunkingFramework.generate_bridges_for_document',
            side_effect=mock_generate_bridges_for_document
        ):
            result = func({}, document_id)
        
        return result

    @pytest.mark.parametrize(
        "num_bridges,description",
        [
            (200, "Large document - preserves partial progress"),
            (120, "Two batches - first batch preserved"),
            (180, "Three batches - multiple batches preserved"),
        ],
    )
    def test_counterexample_all_work_lost_on_milvus_failure(
        self, num_bridges: int, description: str
    ):
        """
        FIX VERIFICATION — Document specific scenarios where partial progress is preserved.
        
        After the fix, these tests PASS because incremental storage preserves
        bridges in PostgreSQL before Milvus failure.
        
        **Validates: Requirements 2.3, 2.4**
        """
        storage_tracker = StorageTracker()
        document_id = str(uuid.uuid4())
        batch_size = 60
        
        result = self._run_generate_bridges_task_with_mocks(
            storage_tracker, document_id, num_bridges
        )
        
        # With incremental storage, PostgreSQL should have stored at least the first batch
        bridges_stored_in_postgres = storage_tracker.total_bridges_stored_in_postgres
        expected_min_stored = batch_size  # At least first batch should be stored
        
        assert bridges_stored_in_postgres >= expected_min_stored, (
            f"FIX VERIFICATION ({description}): "
            f"{num_bridges} bridges generated, "
            f"Milvus timeout on storage, "
            f"{bridges_stored_in_postgres} bridges preserved in PostgreSQL. "
            f"Expected at least {expected_min_stored} bridges with incremental storage. "
            f"PostgreSQL storage was called {len(storage_tracker.postgres_calls)} time(s) "
            f"with {[c[1] for c in storage_tracker.postgres_calls]} bridges each."
        )
