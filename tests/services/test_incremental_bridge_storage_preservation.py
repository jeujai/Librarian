"""
Preservation Property Tests — Incremental Bridge Storage

Property 2: Preservation - Non-Failure Behavior Unchanged

These tests verify that for all inputs where the bug condition does NOT hold,
the fixed function produces the same result as the original function.

Following observation-first methodology:
- Documents with `bridge_needed: false` return early with `bridges_generated: 0`
- Successful storage produces `{'status': 'completed'}` with accurate counts
- Bridge generation failures (LLM errors) return `{'status': 'failed'}`
- Document deletion during processing is detected and aborts gracefully

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6**
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import HealthCheck, Phase, assume, given, settings
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Test Data Structures
# ---------------------------------------------------------------------------

@dataclass
class PreservationTestContext:
    """Context for preservation tests tracking expected vs actual behavior."""
    document_id: str
    bridge_needed: bool
    num_bridges: int
    storage_should_succeed: bool
    generation_should_succeed: bool
    document_deleted: bool
    expected_status: str
    expected_bridges_generated: int


def create_mock_bridge_generation_data(
    num_bridges: int,
    bridge_needed: bool = True
) -> Dict[str, Any]:
    """Create mock bridge generation data for testing."""
    if not bridge_needed or num_bridges == 0:
        return {
            'bridge_needed': [],
            'content_type': 'general',
            'domain_config_dict': {
                'domain_name': 'test',
                'bridge_thresholds': {},
                'preservation_patterns': [],
            },
            'all_unresolved_bisections': {},
        }
    
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
# Test Class: Preservation Property 1 - No Bridges Needed
# ---------------------------------------------------------------------------

class TestPreservationNoBridgesNeeded:
    """
    Preservation Property: Documents with bridge_needed: false return early
    with bridges_generated: 0.
    
    **Validates: Requirement 3.1**
    
    WHEN a document requires no bridges (bridge_generation_data indicates
    `bridge_needed: false`), THEN the system SHALL CONTINUE TO return early
    with `bridges_generated: 0` without attempting storage.
    """

    def _run_generate_bridges_task_with_mocks(
        self,
        document_id: str,
        bridge_generation_data: Dict[str, Any],
        storage_tracker: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Run generate_bridges_task with mocked dependencies."""
        from multimodal_librarian.components.chunking_framework.bridge_generator import (
            BatchGenerationStats,
            BridgeChunk,
        )
        
        if storage_tracker is None:
            storage_tracker = {'postgres_calls': [], 'milvus_calls': []}
        
        async def mock_store_postgres(doc_id, bridges):
            storage_tracker['postgres_calls'].append((doc_id, len(bridges)))
        
        async def mock_store_milvus(doc_id, bridges, document_title=None):
            storage_tracker['milvus_calls'].append((doc_id, len(bridges)))
        
        mock_db_manager = MagicMock()
        mock_db_manager.AsyncSessionLocal = MagicMock()
        mock_db_manager.initialize = MagicMock()
        
        from multimodal_librarian.services.celery_service import generate_bridges_task
        func = generate_bridges_task
        while hasattr(func, '__wrapped__'):
            func = func.__wrapped__
        
        with patch.multiple(
            'multimodal_librarian.services.celery_service',
            _check_document_deleted=MagicMock(),
            _retrieve_processing_payload=AsyncMock(return_value={
                'bridge_generation_data': bridge_generation_data,
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
        ):
            result = func({}, document_id)
        
        return result, storage_tracker

    def test_no_bridges_needed_returns_completed_with_zero_bridges(self):
        """
        PRESERVATION — When bridge_needed is empty, return completed with 0 bridges.
        
        Observed behavior on UNFIXED code:
        - Documents with empty bridge_needed list return early
        - Status is 'completed'
        - bridges_generated is 0
        - No storage calls are made
        
        This test verifies this behavior is preserved.
        """
        document_id = str(uuid.uuid4())
        bridge_generation_data = create_mock_bridge_generation_data(
            num_bridges=0, bridge_needed=False
        )
        
        result, storage_tracker = self._run_generate_bridges_task_with_mocks(
            document_id, bridge_generation_data
        )
        
        # Verify preserved behavior
        assert result['status'] == 'completed', (
            f"Expected status 'completed' for no bridges needed, got '{result['status']}'"
        )
        assert result['bridges_generated'] == 0, (
            f"Expected bridges_generated=0, got {result['bridges_generated']}"
        )
        assert result['document_id'] == document_id, (
            f"Expected document_id={document_id}, got {result['document_id']}"
        )
        
        # Verify no storage calls were made
        assert len(storage_tracker['postgres_calls']) == 0, (
            f"Expected no PostgreSQL storage calls, got {len(storage_tracker['postgres_calls'])}"
        )
        assert len(storage_tracker['milvus_calls']) == 0, (
            f"Expected no Milvus storage calls, got {len(storage_tracker['milvus_calls'])}"
        )

    @given(
        document_id=st.uuids().map(str),
    )
    @settings(
        max_examples=10,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        phases=[Phase.generate],
        deadline=None,
    )
    def test_property_no_bridges_needed_always_returns_zero(self, document_id: str):
        """
        Property: For ALL documents where bridge_needed is empty/false,
        the result equals {'status': 'completed', 'bridges_generated': 0}.
        
        **Validates: Requirement 3.1**
        """
        bridge_generation_data = create_mock_bridge_generation_data(
            num_bridges=0, bridge_needed=False
        )
        
        result, storage_tracker = self._run_generate_bridges_task_with_mocks(
            document_id, bridge_generation_data
        )
        
        # Property assertion
        assert result['status'] == 'completed', (
            f"Property violation: Expected status='completed' for no bridges needed, "
            f"got status='{result['status']}' for document {document_id}"
        )
        assert result['bridges_generated'] == 0, (
            f"Property violation: Expected bridges_generated=0 for no bridges needed, "
            f"got bridges_generated={result['bridges_generated']} for document {document_id}"
        )


# ---------------------------------------------------------------------------
# Test Class: Preservation Property 2 - Successful Storage
# ---------------------------------------------------------------------------

class TestPreservationSuccessfulStorage:
    """
    Preservation Property: Successful storage produces {'status': 'completed'}
    with accurate bridge counts.
    
    **Validates: Requirements 3.2, 3.5, 3.6**
    
    WHEN all bridges are generated and stored successfully, THEN the system
    SHALL CONTINUE TO return `{'status': 'completed'}` with accurate bridge counts.
    """

    def _run_generate_bridges_task_with_mocks(
        self,
        document_id: str,
        num_bridges: int,
        storage_tracker: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Run generate_bridges_task with successful storage mocks."""
        from multimodal_librarian.components.chunking_framework.bridge_generator import (
            BatchGenerationStats,
            BridgeChunk,
        )
        
        if storage_tracker is None:
            storage_tracker = {'postgres_calls': [], 'milvus_calls': []}
        
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
        
        async def mock_store_postgres(doc_id, bridges):
            storage_tracker['postgres_calls'].append((doc_id, len(bridges)))
        
        async def mock_store_milvus(doc_id, bridges, document_title=None):
            storage_tracker['milvus_calls'].append((doc_id, len(bridges)))
        
        mock_db_manager = MagicMock()
        mock_db_manager.AsyncSessionLocal = MagicMock()
        mock_db_manager.initialize = MagicMock()
        
        from multimodal_librarian.services.celery_service import generate_bridges_task
        func = generate_bridges_task
        while hasattr(func, '__wrapped__'):
            func = func.__wrapped__
        
        bridge_generation_data = create_mock_bridge_generation_data(num_bridges)
        
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
                'bridge_generation_data': bridge_generation_data,
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
        
        return result, storage_tracker

    def test_successful_storage_returns_completed_with_accurate_counts(self):
        """
        PRESERVATION — Successful storage returns completed with accurate counts.
        
        Observed behavior on UNFIXED code:
        - When all bridges are generated and stored successfully
        - Status is 'completed'
        - bridges_generated equals the number of bridges created
        
        This test verifies this behavior is preserved.
        """
        document_id = str(uuid.uuid4())
        num_bridges = 10
        
        result, storage_tracker = self._run_generate_bridges_task_with_mocks(
            document_id, num_bridges
        )
        
        # Verify preserved behavior
        assert result['status'] == 'completed', (
            f"Expected status 'completed' for successful storage, got '{result['status']}'"
        )
        assert result['bridges_generated'] == num_bridges, (
            f"Expected bridges_generated={num_bridges}, got {result['bridges_generated']}"
        )
        assert result['document_id'] == document_id, (
            f"Expected document_id={document_id}, got {result['document_id']}"
        )
        
        # Verify storage was called (Requirement 3.5)
        assert len(storage_tracker['postgres_calls']) == 1, (
            f"Expected 1 PostgreSQL storage call, got {len(storage_tracker['postgres_calls'])}"
        )
        assert len(storage_tracker['milvus_calls']) == 1, (
            f"Expected 1 Milvus storage call, got {len(storage_tracker['milvus_calls'])}"
        )

    @given(
        num_bridges=st.integers(min_value=1, max_value=100),
    )
    @settings(
        max_examples=10,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        phases=[Phase.generate],
        deadline=None,
    )
    def test_property_successful_storage_status_completed_and_count_matches(
        self, num_bridges: int
    ):
        """
        Property: For ALL successful storage operations, result status equals
        'completed' AND bridges_generated equals bridges_stored.
        
        **Validates: Requirements 3.2, 3.5**
        """
        document_id = str(uuid.uuid4())
        
        result, storage_tracker = self._run_generate_bridges_task_with_mocks(
            document_id, num_bridges
        )
        
        # Property assertions
        assert result['status'] == 'completed', (
            f"Property violation: Expected status='completed' for successful storage, "
            f"got status='{result['status']}' with {num_bridges} bridges"
        )
        assert result['bridges_generated'] == num_bridges, (
            f"Property violation: Expected bridges_generated={num_bridges}, "
            f"got bridges_generated={result['bridges_generated']}"
        )
        
        # Verify storage counts match
        total_stored_postgres = sum(c[1] for c in storage_tracker['postgres_calls'])
        total_stored_milvus = sum(c[1] for c in storage_tracker['milvus_calls'])
        
        assert total_stored_postgres == num_bridges, (
            f"Property violation: PostgreSQL stored {total_stored_postgres} bridges, "
            f"expected {num_bridges}"
        )
        assert total_stored_milvus == num_bridges, (
            f"Property violation: Milvus stored {total_stored_milvus} bridges, "
            f"expected {num_bridges}"
        )


# ---------------------------------------------------------------------------
# Test Class: Preservation Property 3 - Generation Failures
# ---------------------------------------------------------------------------

class TestPreservationGenerationFailures:
    """
    Preservation Property: Bridge generation failures (LLM errors) return
    {'status': 'failed'} with error details.
    
    **Validates: Requirement 3.4**
    
    WHEN bridge generation fails (not storage), THEN the system SHALL
    CONTINUE TO return `{'status': 'failed'}` with the error details.
    """

    def _run_generate_bridges_task_with_generation_failure(
        self,
        document_id: str,
        error_message: str,
    ) -> Dict[str, Any]:
        """Run generate_bridges_task with generation failure."""
        mock_db_manager = MagicMock()
        mock_db_manager.AsyncSessionLocal = MagicMock()
        mock_db_manager.initialize = MagicMock()
        
        from multimodal_librarian.services.celery_service import generate_bridges_task
        func = generate_bridges_task
        while hasattr(func, '__wrapped__'):
            func = func.__wrapped__
        
        bridge_generation_data = create_mock_bridge_generation_data(num_bridges=10)
        
        with patch.multiple(
            'multimodal_librarian.services.celery_service',
            _check_document_deleted=MagicMock(),
            _retrieve_processing_payload=AsyncMock(return_value={
                'bridge_generation_data': bridge_generation_data,
                'chunks': [{'metadata': {'title': 'Test Document'}}],
            }),
            _update_job_status_sync=AsyncMock(),
            _set_parallel_progress=MagicMock(return_value=50),
            _get_parallel_step_label=MagicMock(return_value="Generating bridges"),
            _store_bridge_chunks_in_database=AsyncMock(),
            _store_bridge_embeddings_in_vector_db=AsyncMock(),
            _record_stage_timing=AsyncMock(),
        ), patch(
            'multimodal_librarian.database.connection.db_manager',
            mock_db_manager
        ), patch(
            'multimodal_librarian.components.chunking_framework.framework.'
            'GenericMultiLevelChunkingFramework.generate_bridges_for_document',
            side_effect=Exception(error_message)
        ):
            result = func({}, document_id)
        
        return result

    def test_generation_failure_returns_failed_with_error(self):
        """
        PRESERVATION — Generation failures return failed status with error.
        
        Observed behavior on UNFIXED code:
        - When bridge generation fails (LLM error, etc.)
        - Status is 'failed'
        - Error details are included in the result
        
        This test verifies this behavior is preserved.
        """
        document_id = str(uuid.uuid4())
        error_message = "LLM API rate limit exceeded"
        
        result = self._run_generate_bridges_task_with_generation_failure(
            document_id, error_message
        )
        
        # Verify preserved behavior
        assert result['status'] == 'failed', (
            f"Expected status 'failed' for generation failure, got '{result['status']}'"
        )
        assert 'error' in result, (
            "Expected 'error' key in result for generation failure"
        )
        assert error_message in result['error'], (
            f"Expected error message '{error_message}' in result, got '{result['error']}'"
        )
        assert result['bridges_generated'] == 0, (
            f"Expected bridges_generated=0 for failed generation, got {result['bridges_generated']}"
        )

    @given(
        error_message=st.text(min_size=1, max_size=100).filter(lambda x: x.strip()),
    )
    @settings(
        max_examples=10,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        phases=[Phase.generate],
        deadline=None,
    )
    def test_property_generation_failures_always_return_failed_status(
        self, error_message: str
    ):
        """
        Property: For ALL generation failures (not storage), result status
        equals 'failed' with error details.
        
        **Validates: Requirement 3.4**
        """
        document_id = str(uuid.uuid4())
        
        result = self._run_generate_bridges_task_with_generation_failure(
            document_id, error_message
        )
        
        # Property assertions
        assert result['status'] == 'failed', (
            f"Property violation: Expected status='failed' for generation failure, "
            f"got status='{result['status']}' with error '{error_message}'"
        )
        assert 'error' in result, (
            f"Property violation: Expected 'error' key in result for generation failure "
            f"with error '{error_message}'"
        )


# ---------------------------------------------------------------------------
# Test Class: Preservation Property 4 - Document Deletion Detection
# ---------------------------------------------------------------------------

class TestPreservationDocumentDeletion:
    """
    Preservation Property: Document deletion during processing is detected
    and aborts gracefully.
    
    **Validates: Requirement 3.3**
    
    WHEN the document is deleted during bridge generation, THEN the system
    SHALL CONTINUE TO detect this via `_check_document_deleted()` and abort
    gracefully.
    """

    def _run_generate_bridges_task_with_document_deleted(
        self,
        document_id: str,
    ) -> Dict[str, Any]:
        """Run generate_bridges_task with document deletion during processing."""
        from multimodal_librarian.services.celery_service import DocumentDeletedError
        
        mock_db_manager = MagicMock()
        mock_db_manager.AsyncSessionLocal = MagicMock()
        mock_db_manager.initialize = MagicMock()
        
        from multimodal_librarian.services.celery_service import generate_bridges_task
        func = generate_bridges_task
        while hasattr(func, '__wrapped__'):
            func = func.__wrapped__
        
        bridge_generation_data = create_mock_bridge_generation_data(num_bridges=10)
        
        # Mock _check_document_deleted to raise DocumentDeletedError
        def mock_check_deleted(doc_id, stage=""):
            raise DocumentDeletedError(f"Document {doc_id} was deleted during processing")
        
        with patch.multiple(
            'multimodal_librarian.services.celery_service',
            _check_document_deleted=mock_check_deleted,
            _retrieve_processing_payload=AsyncMock(return_value={
                'bridge_generation_data': bridge_generation_data,
                'chunks': [{'metadata': {'title': 'Test Document'}}],
            }),
            _update_job_status_sync=AsyncMock(),
            _set_parallel_progress=MagicMock(return_value=50),
            _get_parallel_step_label=MagicMock(return_value="Generating bridges"),
            _store_bridge_chunks_in_database=AsyncMock(),
            _store_bridge_embeddings_in_vector_db=AsyncMock(),
            _record_stage_timing=AsyncMock(),
        ), patch(
            'multimodal_librarian.database.connection.db_manager',
            mock_db_manager
        ):
            result = func({}, document_id)
        
        return result

    def test_document_deletion_returns_aborted_status(self):
        """
        PRESERVATION — Document deletion during processing returns aborted.
        
        Observed behavior on UNFIXED code:
        - When document is deleted during bridge generation
        - _check_document_deleted() raises DocumentDeletedError
        - Status is 'aborted'
        - Processing stops gracefully
        
        This test verifies this behavior is preserved.
        """
        document_id = str(uuid.uuid4())
        
        result = self._run_generate_bridges_task_with_document_deleted(document_id)
        
        # Verify preserved behavior
        assert result['status'] == 'aborted', (
            f"Expected status 'aborted' for deleted document, got '{result['status']}'"
        )
        assert result['bridges_generated'] == 0, (
            f"Expected bridges_generated=0 for aborted processing, got {result['bridges_generated']}"
        )
        assert result['document_id'] == document_id, (
            f"Expected document_id={document_id}, got {result['document_id']}"
        )

    @given(
        document_id=st.uuids().map(str),
    )
    @settings(
        max_examples=10,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        phases=[Phase.generate],
        deadline=None,
    )
    def test_property_document_deletion_always_aborts_gracefully(
        self, document_id: str
    ):
        """
        Property: For ALL document deletions during processing, the system
        detects this and aborts gracefully with status 'aborted'.
        
        **Validates: Requirement 3.3**
        """
        result = self._run_generate_bridges_task_with_document_deleted(document_id)
        
        # Property assertions
        assert result['status'] == 'aborted', (
            f"Property violation: Expected status='aborted' for deleted document, "
            f"got status='{result['status']}' for document {document_id}"
        )
        assert result['bridges_generated'] == 0, (
            f"Property violation: Expected bridges_generated=0 for aborted processing, "
            f"got bridges_generated={result['bridges_generated']} for document {document_id}"
        )


# ---------------------------------------------------------------------------
# Test Class: Combined Preservation Properties
# ---------------------------------------------------------------------------

class TestPreservationCombinedProperties:
    """
    Combined property tests that verify preservation across multiple scenarios.
    
    These tests use property-based testing to generate diverse inputs and
    verify that non-bug-condition inputs produce consistent results.
    """

    @given(
        bridge_needed=st.booleans(),
        num_bridges=st.integers(min_value=0, max_value=50),
    )
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        phases=[Phase.generate],
        deadline=None,
    )
    def test_property_non_failure_scenarios_produce_expected_results(
        self, bridge_needed: bool, num_bridges: int
    ):
        """
        Property: For ALL inputs where NOT isBugCondition(input), the function
        produces the expected result based on input characteristics.
        
        This is the main preservation property that ensures non-failure
        scenarios continue to work correctly after the fix.
        
        **Validates: Requirements 3.1, 3.2, 3.5, 3.6**
        """
        from multimodal_librarian.components.chunking_framework.bridge_generator import (
            BatchGenerationStats,
            BridgeChunk,
        )
        
        document_id = str(uuid.uuid4())
        
        # Determine expected behavior based on inputs
        if not bridge_needed or num_bridges == 0:
            expected_status = 'completed'
            expected_bridges = 0
        else:
            expected_status = 'completed'
            expected_bridges = num_bridges
        
        # Create mock bridges
        mock_bridges = []
        for i in range(num_bridges if bridge_needed else 0):
            bridge = MagicMock(spec=BridgeChunk)
            bridge.id = str(uuid.uuid4())
            bridge.content = f"Bridge content {i}"
            bridge.source_chunks = [str(uuid.uuid4()), str(uuid.uuid4())]
            bridge.generation_method = "gemini_25_flash"
            bridge.confidence_score = 0.85
            mock_bridges.append(bridge)
        
        mock_stats = BatchGenerationStats(
            total_requests=num_bridges if bridge_needed else 0,
            successful_generations=num_bridges if bridge_needed else 0,
            failed_generations=0,
            total_tokens_used=1000,
            total_cost_estimate=0.01,
            average_generation_time=0.5,
            batch_processing_time=60.0,
        )
        
        storage_tracker = {'postgres_calls': [], 'milvus_calls': []}
        
        async def mock_store_postgres(doc_id, bridges):
            storage_tracker['postgres_calls'].append((doc_id, len(bridges)))
        
        async def mock_store_milvus(doc_id, bridges, document_title=None):
            storage_tracker['milvus_calls'].append((doc_id, len(bridges)))
        
        mock_db_manager = MagicMock()
        mock_db_manager.AsyncSessionLocal = MagicMock()
        mock_db_manager.initialize = MagicMock()
        
        from multimodal_librarian.services.celery_service import generate_bridges_task
        func = generate_bridges_task
        while hasattr(func, '__wrapped__'):
            func = func.__wrapped__
        
        bridge_generation_data = create_mock_bridge_generation_data(
            num_bridges=num_bridges if bridge_needed else 0,
            bridge_needed=bridge_needed
        )
        
        with patch.multiple(
            'multimodal_librarian.services.celery_service',
            _check_document_deleted=MagicMock(),
            _retrieve_processing_payload=AsyncMock(return_value={
                'bridge_generation_data': bridge_generation_data,
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
            return_value=(mock_bridges, mock_stats)
        ):
            result = func({}, document_id)
        
        # Property assertions
        assert result['status'] == expected_status, (
            f"Property violation: Expected status='{expected_status}', "
            f"got status='{result['status']}' with bridge_needed={bridge_needed}, "
            f"num_bridges={num_bridges}"
        )
        assert result['bridges_generated'] == expected_bridges, (
            f"Property violation: Expected bridges_generated={expected_bridges}, "
            f"got bridges_generated={result['bridges_generated']} with "
            f"bridge_needed={bridge_needed}, num_bridges={num_bridges}"
        )
