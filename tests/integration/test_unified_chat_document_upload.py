"""
Integration Tests for Unified Chat Document Upload Feature.

This module tests the end-to-end flows for:
- Document upload via WebSocket (Task 12.1)
- Document management (list, delete) flow (Task 12.2)
- Search prioritization with Librarian documents (Task 12.3)

Requirements: 1.1, 2.1, 2.2, 2.3, 2.4, 3.1, 3.3, 5.1, 5.2, 5.6, 8.2, 8.3
"""

import asyncio
import base64
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

# Application imports
from multimodal_librarian.api.models.chat_document_models import (
    ChatUploadMessage,
    DocumentDeleteRequest,
    DocumentInfo,
    DocumentListMessage,
    DocumentListRequest,
    DocumentUploadErrorCodes,
    DocumentUploadStartedMessage,
)
from multimodal_librarian.api.routers.chat_document_handlers import (
    MAX_FILE_SIZE_BYTES,
    SUPPORTED_MIME_TYPES,
    handle_chat_document_upload,
    handle_document_delete_request,
    handle_document_list_request,
    handle_document_retry_request,
)
from multimodal_librarian.services.processing_status_service import (
    DocumentProcessingSummary,
    ProcessingStatus,
    ProcessingStatusMessage,
    ProcessingStatusService,
)
from multimodal_librarian.services.source_prioritization_engine import (
    PrioritizedSearchResult,
    PrioritizedSearchResults,
    SearchSourceType,
    SourcePrioritizationEngine,
)

# =============================================================================
# Test Fixtures
# =============================================================================

def create_test_pdf_content() -> bytes:
    """Create minimal valid PDF content for testing."""
    return b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Resources<<>>>>endobj
xref
0 4
0000000000 65535 f 
0000000009 00000 n 
0000000052 00000 n 
0000000101 00000 n 
trailer<</Size 4/Root 1 0 R>>
startxref
178
%%EOF"""


@pytest.fixture
def mock_connection_manager():
    """Create a mock ConnectionManager for testing."""
    manager = MagicMock()
    manager.send_personal_message = AsyncMock()
    manager.active_connections = {}
    return manager


@pytest.fixture
def mock_document_manager():
    """Create a mock DocumentManager for testing."""
    manager = MagicMock()
    manager.upload_and_process_document = AsyncMock(return_value={
        'document_id': str(uuid4()),
        'status': 'processing',
        'message': 'Document processing started'
    })
    manager.list_documents_with_status = AsyncMock(return_value={
        'documents': [],
        'total_count': 0
    })
    manager.delete_document_completely = AsyncMock(return_value={
        'success': True,
        'opensearch_deleted': 5,
        'neptune_deleted': 10,
        'errors': []
    })
    manager.retry_document_processing = AsyncMock(return_value=True)
    manager.get_document_status = AsyncMock(return_value={
        'filename': 'test.pdf',
        'status': 'failed'
    })
    return manager


@pytest.fixture
def processing_status_service(mock_connection_manager):
    """Create a ProcessingStatusService with mock connection manager."""
    service = ProcessingStatusService()
    service.set_connection_manager(mock_connection_manager)
    return service


@pytest.fixture
def mock_vector_client():
    """Create a mock vector client for testing."""
    client = MagicMock()
    client.is_connected = MagicMock(return_value=True)
    # Use semantic_search_async since the engine checks for it first
    client.semantic_search_async = AsyncMock(return_value=[])
    # Remove semantic_search attribute so hasattr returns False
    del client.semantic_search
    client.health_check = MagicMock(return_value=True)
    return client


# =============================================================================
# Task 12.1: End-to-End Upload Flow Integration Tests
# =============================================================================

class TestEndToEndUploadFlow:
    """
    Integration tests for the end-to-end document upload flow.
    
    Tests the complete flow: Upload PDF via WebSocket → Verify status messages
    → Verify document becomes searchable.
    
    Requirements: 1.1, 2.1, 2.2, 2.3, 2.4, 3.1, 3.3
    """
    
    @pytest.mark.asyncio
    async def test_upload_pdf_via_websocket_initiates_processing(
        self,
        mock_connection_manager,
        mock_document_manager,
        processing_status_service
    ):
        """
        Test that uploading a PDF via WebSocket initiates document processing.
        
        Validates: Requirements 1.1, 2.1, 3.1
        """
        # Arrange
        connection_id = "test-connection-123"
        pdf_content = create_test_pdf_content()
        
        message_data = {
            'type': 'chat_document_upload',
            'filename': 'test_document.pdf',
            'file_size': len(pdf_content),
            'content_type': 'application/pdf',
            'file_data': base64.b64encode(pdf_content).decode('utf-8'),
            'title': 'Test Document',
            'description': 'A test document for integration testing'
        }
        
        # Act
        await handle_chat_document_upload(
            message_data=message_data,
            connection_id=connection_id,
            manager=mock_connection_manager,
            document_manager=mock_document_manager,
            processing_status_service=processing_status_service
        )
        
        # Assert - Document manager was called to process
        mock_document_manager.upload_and_process_document.assert_called_once()
        call_args = mock_document_manager.upload_and_process_document.call_args
        assert call_args.kwargs['filename'] == 'test_document.pdf'
        assert call_args.kwargs['title'] == 'Test Document'
        
        # Assert - Upload started message was sent
        assert mock_connection_manager.send_personal_message.call_count >= 1
        first_call = mock_connection_manager.send_personal_message.call_args_list[0]
        message = first_call[0][0]
        assert message.get('type') in ['document_processing_status', 'document_upload_started']
    
    @pytest.mark.asyncio
    async def test_upload_sends_status_messages_to_client(
        self,
        mock_connection_manager,
        mock_document_manager,
        processing_status_service
    ):
        """
        Test that status messages are sent to the client during upload.
        
        Validates: Requirements 3.1, 3.3
        """
        # Arrange
        connection_id = "test-connection-456"
        pdf_content = create_test_pdf_content()
        
        message_data = {
            'type': 'chat_document_upload',
            'filename': 'status_test.pdf',
            'file_size': len(pdf_content),
            'content_type': 'application/pdf',
            'file_data': base64.b64encode(pdf_content).decode('utf-8')
        }
        
        # Act
        await handle_chat_document_upload(
            message_data=message_data,
            connection_id=connection_id,
            manager=mock_connection_manager,
            document_manager=mock_document_manager,
            processing_status_service=processing_status_service
        )
        
        # Assert - Messages were sent to the correct connection
        for call in mock_connection_manager.send_personal_message.call_args_list:
            sent_connection_id = call[0][1]
            assert sent_connection_id == connection_id
    
    @pytest.mark.asyncio
    async def test_upload_rejects_non_pdf_files(
        self,
        mock_connection_manager,
        mock_document_manager,
        processing_status_service
    ):
        """
        Test that non-PDF files are rejected with appropriate error.
        
        Validates: Requirements 1.4
        """
        # Arrange
        connection_id = "test-connection-789"
        
        message_data = {
            'type': 'chat_document_upload',
            'filename': 'document.docx',
            'file_size': 1000,
            'content_type': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'file_data': base64.b64encode(b'fake content').decode('utf-8')
        }
        
        # Act
        await handle_chat_document_upload(
            message_data=message_data,
            connection_id=connection_id,
            manager=mock_connection_manager,
            document_manager=mock_document_manager,
            processing_status_service=processing_status_service
        )
        
        # Assert - Error message was sent
        mock_connection_manager.send_personal_message.assert_called()
        error_message = mock_connection_manager.send_personal_message.call_args[0][0]
        assert error_message.get('type') == 'document_upload_error'
        assert error_message.get('error_code') == DocumentUploadErrorCodes.INVALID_FILE_TYPE
        
        # Assert - Document manager was NOT called
        mock_document_manager.upload_and_process_document.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_upload_rejects_oversized_files(
        self,
        mock_connection_manager,
        mock_document_manager,
        processing_status_service
    ):
        """
        Test that files exceeding size limit are rejected.
        
        Validates: Requirements 1.5
        """
        # Arrange
        connection_id = "test-connection-size"
        oversized_file_size = MAX_FILE_SIZE_BYTES + 1
        
        message_data = {
            'type': 'chat_document_upload',
            'filename': 'large_document.pdf',
            'file_size': oversized_file_size,
            'content_type': 'application/pdf',
            'file_data': base64.b64encode(b'x' * 100).decode('utf-8')  # Small actual data
        }
        
        # Act
        await handle_chat_document_upload(
            message_data=message_data,
            connection_id=connection_id,
            manager=mock_connection_manager,
            document_manager=mock_document_manager,
            processing_status_service=processing_status_service
        )
        
        # Assert - Error message was sent
        mock_connection_manager.send_personal_message.assert_called()
        error_message = mock_connection_manager.send_personal_message.call_args[0][0]
        assert error_message.get('type') == 'document_upload_error'
        assert error_message.get('error_code') == DocumentUploadErrorCodes.FILE_TOO_LARGE
        
        # Assert - Document manager was NOT called
        mock_document_manager.upload_and_process_document.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_processing_status_service_tracks_upload(
        self,
        mock_connection_manager,
        processing_status_service
    ):
        """
        Test that ProcessingStatusService correctly tracks document uploads.
        
        Validates: Requirements 3.1, 6.1, 6.2
        """
        # Arrange
        document_id = uuid4()
        connection_id = "test-connection-track"
        filename = "tracked_document.pdf"
        
        # Act - Register upload
        await processing_status_service.register_upload(
            document_id=document_id,
            connection_id=connection_id,
            filename=filename
        )
        
        # Assert - Tracking info exists
        tracker = processing_status_service.get_tracking_info(document_id)
        assert tracker is not None
        assert tracker.document_id == str(document_id)
        assert tracker.connection_id == connection_id
        assert tracker.filename == filename
        assert tracker.status == ProcessingStatus.QUEUED
        
        # Assert - Initial status message was sent
        mock_connection_manager.send_personal_message.assert_called()
        status_message = mock_connection_manager.send_personal_message.call_args[0][0]
        assert status_message.get('type') == 'document_processing_status'
        assert status_message.get('status') == 'queued'
    
    @pytest.mark.asyncio
    async def test_processing_status_updates_sent_correctly(
        self,
        mock_connection_manager,
        processing_status_service
    ):
        """
        Test that processing status updates are sent with correct format.
        
        Validates: Requirements 3.2, 6.1, 6.2
        """
        # Arrange
        document_id = uuid4()
        connection_id = "test-connection-updates"
        
        await processing_status_service.register_upload(
            document_id=document_id,
            connection_id=connection_id,
            filename="update_test.pdf"
        )
        mock_connection_manager.send_personal_message.reset_mock()
        
        # Act - Send status update
        await processing_status_service.update_status(
            document_id=document_id,
            status=ProcessingStatus.EXTRACTING,
            progress_percentage=25,
            current_stage="Extracting text from PDF"
        )
        
        # Assert - Status message format is correct
        mock_connection_manager.send_personal_message.assert_called()
        status_message = mock_connection_manager.send_personal_message.call_args[0][0]
        
        # Verify required fields (Requirement 6.1)
        assert 'document_id' in status_message
        assert 'status' in status_message
        assert 'progress_percentage' in status_message
        assert 'current_stage' in status_message
        
        # Verify status value (Requirement 6.2)
        assert status_message['status'] == 'extracting'
        assert status_message['progress_percentage'] == 25
    
    @pytest.mark.asyncio
    async def test_processing_completion_notification(
        self,
        mock_connection_manager,
        processing_status_service
    ):
        """
        Test that completion notification is sent with summary.
        
        Validates: Requirements 3.3
        """
        # Arrange
        document_id = uuid4()
        connection_id = "test-connection-complete"
        
        await processing_status_service.register_upload(
            document_id=document_id,
            connection_id=connection_id,
            filename="complete_test.pdf"
        )
        mock_connection_manager.send_personal_message.reset_mock()
        
        summary = DocumentProcessingSummary(
            title="Complete Test Document",
            page_count=10,
            chunk_count=25,
            concept_count=15,
            processing_time_ms=5000
        )
        
        # Act
        await processing_status_service.notify_completion(
            document_id=document_id,
            summary=summary
        )
        
        # Assert
        mock_connection_manager.send_personal_message.assert_called()
        completion_message = mock_connection_manager.send_personal_message.call_args[0][0]
        
        assert completion_message['status'] == 'completed'
        assert completion_message['progress_percentage'] == 100
        assert completion_message['summary'] is not None
        assert completion_message['summary']['chunk_count'] == 25




# =============================================================================
# Task 12.2: Document Management Flow Integration Tests
# =============================================================================

class TestDocumentManagementFlow:
    """
    Integration tests for document management operations.
    
    Tests the flow: Upload → List → Delete → Verify removal from all stores.
    
    Requirements: 8.2, 8.3
    """
    
    @pytest.mark.asyncio
    async def test_list_documents_returns_uploaded_documents(
        self,
        mock_connection_manager,
        mock_document_manager
    ):
        """
        Test that document list request returns uploaded documents.
        
        Validates: Requirements 8.2
        """
        # Arrange
        connection_id = "test-connection-list"
        test_documents = [
            {
                'document_id': str(uuid4()),
                'title': 'Document 1',
                'filename': 'doc1.pdf',
                'status': 'completed',
                'upload_timestamp': datetime.utcnow(),
                'file_size': 1000,
                'chunk_count': 10
            },
            {
                'document_id': str(uuid4()),
                'title': 'Document 2',
                'filename': 'doc2.pdf',
                'status': 'processing',
                'upload_timestamp': datetime.utcnow(),
                'file_size': 2000,
                'chunk_count': None
            }
        ]
        
        mock_document_manager.list_documents_with_status.return_value = {
            'documents': test_documents,
            'total_count': 2
        }
        
        message_data = {
            'type': 'document_list_request',
            'page': 1,
            'page_size': 20
        }
        
        # Act
        await handle_document_list_request(
            message_data=message_data,
            connection_id=connection_id,
            manager=mock_connection_manager,
            document_manager=mock_document_manager
        )
        
        # Assert
        mock_connection_manager.send_personal_message.assert_called()
        response = mock_connection_manager.send_personal_message.call_args[0][0]
        
        assert response['type'] == 'document_list'
        assert response['total_count'] == 2
        assert len(response['documents']) == 2
    
    @pytest.mark.asyncio
    async def test_list_documents_with_status_filter(
        self,
        mock_connection_manager,
        mock_document_manager
    ):
        """
        Test that document list can be filtered by status.
        
        Validates: Requirements 8.2
        """
        # Arrange
        connection_id = "test-connection-filter"
        
        message_data = {
            'type': 'document_list_request',
            'status_filter': 'completed',
            'page': 1,
            'page_size': 20
        }
        
        # Act
        await handle_document_list_request(
            message_data=message_data,
            connection_id=connection_id,
            manager=mock_connection_manager,
            document_manager=mock_document_manager
        )
        
        # Assert - Document manager was called with status filter
        mock_document_manager.list_documents_with_status.assert_called()
    
    @pytest.mark.asyncio
    async def test_delete_document_removes_from_all_stores(
        self,
        mock_connection_manager,
        mock_document_manager
    ):
        """
        Test that document deletion removes from all storage locations.
        
        Validates: Requirements 8.3
        """
        # Arrange
        connection_id = "test-connection-delete"
        document_id = str(uuid4())
        
        mock_document_manager.delete_document_completely.return_value = {
            'success': True,
            'opensearch_deleted': 15,
            'neptune_deleted': 25,
            's3_deleted': True,
            'postgres_deleted': True,
            'errors': []
        }
        
        message_data = {
            'type': 'document_delete_request',
            'document_id': document_id
        }
        
        # Act
        await handle_document_delete_request(
            message_data=message_data,
            connection_id=connection_id,
            manager=mock_connection_manager,
            document_manager=mock_document_manager
        )
        
        # Assert - Delete was called with correct document ID
        mock_document_manager.delete_document_completely.assert_called_once()
        call_args = mock_document_manager.delete_document_completely.call_args[0]
        assert str(call_args[0]) == document_id
        
        # Assert - Success message was sent
        mock_connection_manager.send_personal_message.assert_called()
        response = mock_connection_manager.send_personal_message.call_args[0][0]
        assert response['type'] == 'document_deleted'
        assert response['success'] is True
    
    @pytest.mark.asyncio
    async def test_delete_document_reports_partial_failure(
        self,
        mock_connection_manager,
        mock_document_manager
    ):
        """
        Test that partial deletion failures are reported correctly.
        
        Validates: Requirements 8.3
        """
        # Arrange
        connection_id = "test-connection-partial"
        document_id = str(uuid4())
        
        mock_document_manager.delete_document_completely.return_value = {
            'success': False,
            'opensearch_deleted': 0,
            'neptune_deleted': 0,
            'errors': ['Failed to connect to OpenSearch', 'Neptune timeout']
        }
        
        message_data = {
            'type': 'document_delete_request',
            'document_id': document_id
        }
        
        # Act
        await handle_document_delete_request(
            message_data=message_data,
            connection_id=connection_id,
            manager=mock_connection_manager,
            document_manager=mock_document_manager
        )
        
        # Assert - Failure message was sent
        mock_connection_manager.send_personal_message.assert_called()
        response = mock_connection_manager.send_personal_message.call_args[0][0]
        assert response['type'] == 'document_deleted'
        assert response['success'] is False
    
    @pytest.mark.asyncio
    async def test_retry_failed_document_processing(
        self,
        mock_connection_manager,
        mock_document_manager,
        processing_status_service
    ):
        """
        Test that failed documents can be retried.
        
        Validates: Requirements 8.4
        """
        # Arrange
        connection_id = "test-connection-retry"
        document_id = str(uuid4())
        
        message_data = {
            'type': 'document_retry_request',
            'document_id': document_id
        }
        
        # Act
        await handle_document_retry_request(
            message_data=message_data,
            connection_id=connection_id,
            manager=mock_connection_manager,
            document_manager=mock_document_manager,
            processing_status_service=processing_status_service
        )
        
        # Assert - Retry was called
        mock_document_manager.retry_document_processing.assert_called_once()
        
        # Assert - Success message was sent
        mock_connection_manager.send_personal_message.assert_called()
        response = mock_connection_manager.send_personal_message.call_args[0][0]
        assert response['type'] == 'document_retry_started'
    
    @pytest.mark.asyncio
    async def test_complete_upload_list_delete_flow(
        self,
        mock_connection_manager,
        mock_document_manager,
        processing_status_service
    ):
        """
        Integration test for complete document lifecycle: upload → list → delete.
        
        Validates: Requirements 1.1, 8.2, 8.3
        """
        connection_id = "test-connection-lifecycle"
        
        # Step 1: Upload document
        pdf_content = create_test_pdf_content()
        upload_message = {
            'type': 'chat_document_upload',
            'filename': 'lifecycle_test.pdf',
            'file_size': len(pdf_content),
            'content_type': 'application/pdf',
            'file_data': base64.b64encode(pdf_content).decode('utf-8')
        }
        
        await handle_chat_document_upload(
            message_data=upload_message,
            connection_id=connection_id,
            manager=mock_connection_manager,
            document_manager=mock_document_manager,
            processing_status_service=processing_status_service
        )
        
        # Verify upload was initiated
        assert mock_document_manager.upload_and_process_document.called
        
        # Step 2: List documents
        mock_connection_manager.send_personal_message.reset_mock()
        document_id = str(uuid4())
        mock_document_manager.list_documents_with_status.return_value = {
            'documents': [{
                'document_id': document_id,
                'title': 'lifecycle_test.pdf',
                'filename': 'lifecycle_test.pdf',
                'status': 'completed',
                'upload_timestamp': datetime.utcnow(),
                'file_size': len(pdf_content),
                'chunk_count': 5
            }],
            'total_count': 1
        }
        
        list_message = {'type': 'document_list_request', 'page': 1, 'page_size': 20}
        await handle_document_list_request(
            message_data=list_message,
            connection_id=connection_id,
            manager=mock_connection_manager,
            document_manager=mock_document_manager
        )
        
        # Verify document appears in list
        list_response = mock_connection_manager.send_personal_message.call_args[0][0]
        assert list_response['total_count'] == 1
        
        # Step 3: Delete document
        mock_connection_manager.send_personal_message.reset_mock()
        delete_message = {
            'type': 'document_delete_request',
            'document_id': document_id
        }
        
        await handle_document_delete_request(
            message_data=delete_message,
            connection_id=connection_id,
            manager=mock_connection_manager,
            document_manager=mock_document_manager
        )
        
        # Verify deletion was successful
        delete_response = mock_connection_manager.send_personal_message.call_args[0][0]
        assert delete_response['success'] is True



# =============================================================================
# Task 12.3: Search Prioritization Integration Tests
# =============================================================================

class TestSearchPrioritization:
    """
    Integration tests for search source prioritization.
    
    Tests that Librarian documents are prioritized over external sources
    and that the boost factor is correctly applied.
    
    Requirements: 5.1, 5.2, 5.6
    """
    
    @pytest.mark.asyncio
    async def test_librarian_documents_searched_first(
        self,
        mock_vector_client
    ):
        """
        Test that Librarian documents are searched first.
        
        Validates: Requirements 5.1
        """
        # Arrange
        mock_vector_client.semantic_search_async = AsyncMock(return_value=[
            {
                'chunk_id': 'chunk-1',
                'source_id': 'doc-1',
                'content': 'Machine learning is a subset of AI',
                'similarity_score': 0.85,
                'metadata': {'title': 'ML Guide'}
            }
        ])
        
        engine = SourcePrioritizationEngine(
            vector_client=mock_vector_client,
            librarian_boost_factor=1.5
        )
        
        # Act
        results = await engine.search_with_prioritization(
            query="What is machine learning?",
            user_id="test-user",
            max_results=10
        )
        
        # Assert - Vector client was called (Librarian search)
        mock_vector_client.semantic_search_async.assert_called()
        
        # Assert - Results are from Librarian source
        assert results.librarian_count > 0
        for result in results.results:
            assert result.source_type == SearchSourceType.LIBRARIAN
    
    @pytest.mark.asyncio
    async def test_librarian_boost_factor_applied(
        self,
        mock_vector_client
    ):
        """
        Test that Librarian results have boost factor applied.
        
        Validates: Requirements 5.6
        """
        # Arrange
        original_score = 0.6
        boost_factor = 1.5
        
        mock_vector_client.semantic_search_async = AsyncMock(return_value=[
            {
                'chunk_id': 'chunk-boost',
                'source_id': 'doc-boost',
                'content': 'Test content for boost verification',
                'similarity_score': original_score,
                'metadata': {'title': 'Boost Test'}
            }
        ])
        
        engine = SourcePrioritizationEngine(
            vector_client=mock_vector_client,
            librarian_boost_factor=boost_factor
        )
        
        # Act
        results = await engine.search_with_prioritization(
            query="test query",
            user_id="test-user"
        )
        
        # Assert - Boost was applied
        assert len(results.results) > 0
        result = results.results[0]
        
        # Original score should be preserved
        assert result.original_score == original_score
        
        # Final score should be boosted
        expected_boosted_score = min(1.0, original_score * boost_factor)
        assert result.score == expected_boosted_score
        
        # Metadata should indicate boost was applied
        assert result.metadata.get('librarian_boost_applied') is True
    
    @pytest.mark.asyncio
    async def test_boosted_score_capped_at_one(
        self,
        mock_vector_client
    ):
        """
        Test that boosted scores are capped at 1.0.
        
        Validates: Requirements 5.6
        """
        # Arrange - High original score that would exceed 1.0 after boost
        original_score = 0.8
        boost_factor = 1.5  # 0.8 * 1.5 = 1.2, should be capped to 1.0
        
        mock_vector_client.semantic_search_async = AsyncMock(return_value=[
            {
                'chunk_id': 'chunk-cap',
                'source_id': 'doc-cap',
                'content': 'High score content',
                'similarity_score': original_score,
                'metadata': {}
            }
        ])
        
        engine = SourcePrioritizationEngine(
            vector_client=mock_vector_client,
            librarian_boost_factor=boost_factor
        )
        
        # Act
        results = await engine.search_with_prioritization(
            query="test",
            user_id="test-user"
        )
        
        # Assert - Score is capped at 1.0
        assert len(results.results) > 0
        assert results.results[0].score == 1.0
        assert results.results[0].original_score == original_score
    
    @pytest.mark.asyncio
    async def test_results_below_threshold_filtered(
        self,
        mock_vector_client
    ):
        """
        Test that results below confidence threshold are filtered out.
        
        Validates: Requirements 5.2
        """
        # Arrange
        threshold = 0.35
        
        mock_vector_client.semantic_search_async = AsyncMock(return_value=[
            {
                'chunk_id': 'chunk-high',
                'source_id': 'doc-high',
                'content': 'High relevance content',
                'similarity_score': 0.8,
                'metadata': {}
            },
            {
                'chunk_id': 'chunk-low',
                'source_id': 'doc-low',
                'content': 'Low relevance content',
                'similarity_score': 0.2,  # Below threshold
                'metadata': {}
            }
        ])
        
        engine = SourcePrioritizationEngine(
            vector_client=mock_vector_client,
            min_confidence_threshold=threshold
        )
        
        # Act
        results = await engine.search_with_prioritization(
            query="test",
            user_id="test-user"
        )
        
        # Assert - Only high-score result is returned
        assert len(results.results) == 1
        assert results.results[0].chunk_id == 'chunk-high'
    
    @pytest.mark.asyncio
    async def test_source_type_labeling(
        self,
        mock_vector_client
    ):
        """
        Test that all results have source_type field.
        
        Validates: Requirements 5.5
        """
        # Arrange
        mock_vector_client.semantic_search_async = AsyncMock(return_value=[
            {
                'chunk_id': f'chunk-{i}',
                'source_id': f'doc-{i}',
                'content': f'Content {i}',
                'similarity_score': 0.7 - (i * 0.1),
                'metadata': {}
            }
            for i in range(3)
        ])
        
        engine = SourcePrioritizationEngine(
            vector_client=mock_vector_client,
            min_confidence_threshold=0.3
        )
        
        # Act
        results = await engine.search_with_prioritization(
            query="test",
            user_id="test-user"
        )
        
        # Assert - All results have source_type
        for result in results.results:
            assert result.source_type is not None
            assert isinstance(result.source_type, SearchSourceType)
    
    @pytest.mark.asyncio
    async def test_search_results_sorted_by_score(
        self,
        mock_vector_client
    ):
        """
        Test that search results are sorted by score (descending).
        
        Validates: Requirements 5.1
        """
        # Arrange
        mock_vector_client.semantic_search_async = AsyncMock(return_value=[
            {'chunk_id': 'low', 'source_id': 'doc-1', 'content': 'Low', 'similarity_score': 0.5, 'metadata': {}},
            {'chunk_id': 'high', 'source_id': 'doc-2', 'content': 'High', 'similarity_score': 0.9, 'metadata': {}},
            {'chunk_id': 'mid', 'source_id': 'doc-3', 'content': 'Mid', 'similarity_score': 0.7, 'metadata': {}},
        ])
        
        engine = SourcePrioritizationEngine(
            vector_client=mock_vector_client,
            librarian_boost_factor=1.0  # No boost for easier verification
        )
        
        # Act
        results = await engine.search_with_prioritization(
            query="test",
            user_id="test-user"
        )
        
        # Assert - Results are sorted by score descending
        scores = [r.score for r in results.results]
        assert scores == sorted(scores, reverse=True)
    
    @pytest.mark.asyncio
    async def test_engine_handles_empty_results(
        self,
        mock_vector_client
    ):
        """
        Test that engine handles empty search results gracefully.
        """
        # Arrange
        mock_vector_client.semantic_search_async = AsyncMock(return_value=[])
        
        engine = SourcePrioritizationEngine(
            vector_client=mock_vector_client
        )
        
        # Act
        results = await engine.search_with_prioritization(
            query="nonexistent topic",
            user_id="test-user"
        )
        
        # Assert
        assert results.total_count == 0
        assert results.librarian_count == 0
        assert len(results.results) == 0
    
    @pytest.mark.asyncio
    async def test_engine_handles_search_errors(
        self,
        mock_vector_client
    ):
        """
        Test that engine handles search errors gracefully.
        """
        # Arrange
        mock_vector_client.semantic_search_async = AsyncMock(
            side_effect=Exception("Connection failed")
        )
        
        engine = SourcePrioritizationEngine(
            vector_client=mock_vector_client
        )
        
        # Act
        results = await engine.search_with_prioritization(
            query="test",
            user_id="test-user"
        )
        
        # Assert - Returns empty results, doesn't raise
        assert results.total_count == 0
        assert len(results.results) == 0
    
    @pytest.mark.asyncio
    async def test_prioritized_search_result_model(self):
        """
        Test PrioritizedSearchResult model validation.
        
        Validates: Requirements 5.5
        """
        # Arrange & Act
        result = PrioritizedSearchResult(
            chunk_id="test-chunk",
            document_id="test-doc",
            document_title="Test Document",
            content="Test content",
            score=0.9,
            original_score=0.6,
            source_type=SearchSourceType.LIBRARIAN,
            page_number=5,
            section_title="Introduction",
            metadata={"key": "value"}
        )
        
        # Assert
        assert result.chunk_id == "test-chunk"
        assert result.source_type == SearchSourceType.LIBRARIAN
        assert result.score == 0.9
        assert result.original_score == 0.6
    
    @pytest.mark.asyncio
    async def test_engine_status_reporting(
        self,
        mock_vector_client
    ):
        """
        Test that engine reports its configuration status.
        """
        # Arrange
        engine = SourcePrioritizationEngine(
            vector_client=mock_vector_client,
            librarian_boost_factor=1.5,
            min_confidence_threshold=0.4
        )
        
        # Act
        status = engine.get_engine_status()
        
        # Assert
        assert status['librarian_boost_factor'] == 1.5
        assert status['min_confidence_threshold'] == 0.4
        assert 'vector_client_type' in status


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
