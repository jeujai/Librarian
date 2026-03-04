# Implementation Plan: Unified Chat Document Upload

## Overview

This implementation plan integrates document upload into the chat interface, removes the separate Document Library panel, adds real-time processing status feedback via WebSocket, and implements source prioritization in RAG retrieval. The implementation follows the existing dependency injection architecture and builds on the current document processing pipeline.

## Tasks

- [x] 1. Create Processing Status Service
  - [x] 1.1 Create ProcessingStatusService class with DI support
    - Create `src/multimodal_librarian/services/processing_status_service.py`
    - Implement status tracking with connection_id mapping
    - Implement WebSocket message sending via ConnectionManager
    - Add methods: register_upload, update_status, notify_completion, notify_failure
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 6.1, 6.2, 6.4_
  
  - [x] 1.2 Add ProcessingStatusService to dependency injection
    - Add `get_processing_status_service()` to `api/dependencies/services.py`
    - Implement singleton caching pattern
    - Wire ConnectionManager dependency
    - _Requirements: 6.4_
  
  - [ ]* 1.3 Write property test for status message format
    - **Property 7: Processing Status Message Format**
    - Generate random status updates, verify all contain required fields
    - **Validates: Requirements 6.1, 6.2**

- [x] 2. Implement WebSocket Message Handlers for Chat Upload
  - [x] 2.1 Add WebSocket message types for document operations
    - Add message handlers to `api/routers/chat.py`
    - Implement `handle_chat_document_upload` for file uploads
    - Implement `handle_document_list_request` for listing documents
    - Implement `handle_document_delete_request` for deletion
    - Implement `handle_document_retry_request` for retry
    - Update `handle_websocket_message` to route new message types
    - _Requirements: 1.1, 7.2, 8.3, 8.4_
  
  - [x] 2.2 Integrate ProcessingStatusService with document processing
    - Hook into DocumentManager.upload_and_process_document
    - Send status updates at each processing stage
    - Handle processing completion and failure notifications
    - _Requirements: 3.1, 3.2, 3.3, 3.4_
  
  - [ ]* 1.4 Write property test for status message routing
    - **Property 8: Status Message Routing**
    - Verify messages only sent to originating connection
    - **Validates: Requirements 6.4**

- [x] 3. Checkpoint - Backend services complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Create Source Prioritization Engine
  - [x] 4.1 Create SourcePrioritizationEngine class
    - Create `src/multimodal_librarian/services/source_prioritization_engine.py`
    - Implement search_with_prioritization method
    - Implement _apply_librarian_boost for score boosting
    - Implement _merge_and_rank_results for result ordering
    - Add SourceType enum and PrioritizedSearchResult model
    - _Requirements: 5.1, 5.5, 5.6_
  
  - [x] 4.2 Integrate SourcePrioritizationEngine with RAGService
    - Modify RAGService._search_documents to use prioritization
    - Add source_type field to search results
    - Update citation generation to include source type
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_
  
  - [ ]* 4.3 Write property test for search prioritization
    - **Property 9: Search Source Prioritization**
    - Generate random queries and results, verify Librarian boost applied
    - **Validates: Requirements 5.1, 5.6**
  
  - [ ]* 4.4 Write property test for source labeling
    - **Property 10: Source Type Labeling**
    - Generate random results, verify all have source_type
    - **Validates: Requirements 5.5**

- [x] 5. Implement Frontend Chat Upload Handler
  - [x] 5.1 Create ChatUploadHandler class
    - Create `src/multimodal_librarian/static/js/chat-upload-handler.js`
    - Extend FileHandler with chat-specific behavior
    - Implement handleChatUpload for WebSocket upload
    - Implement file validation (PDF only, size limit)
    - Implement multi-file queuing
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_
  
  - [x] 5.2 Update chat.js to use ChatUploadHandler
    - Replace FileHandler with ChatUploadHandler in ChatApp
    - Update setupFileHandlers to use new handler
    - Wire WebSocket message sending for uploads
    - _Requirements: 1.1, 1.2, 1.3_
  
  - [ ]* 5.3 Write property test for PDF acceptance
    - **Property 1: PDF Acceptance**
    - Generate valid PDF metadata, verify acceptance
    - **Validates: Requirements 1.1, 1.2, 1.3**
  
  - [ ]* 5.4 Write property test for non-PDF rejection
    - **Property 2: Non-PDF Rejection**
    - Generate non-PDF file types, verify rejection
    - **Validates: Requirements 1.4**
  
  - [ ]* 5.5 Write property test for file size validation
    - **Property 3: File Size Validation**
    - Generate oversized files, verify rejection
    - **Validates: Requirements 1.5**

- [x] 6. Implement Processing Status UI
  - [x] 6.1 Add processing status indicator to chat UI
    - Create processing status card component in chat.js
    - Handle `document_processing_status` WebSocket messages
    - Display progress bar with stage name and percentage
    - Handle completion and failure states
    - _Requirements: 3.5, 3.6, 4.1, 4.2, 4.3, 4.4, 4.5_
  
  - [x] 6.2 Add CSS styles for processing status
    - Add styles to `static/css/chat.css` or new file
    - Style progress bar, status card, success/error states
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

- [x] 7. Checkpoint - Upload and status feedback complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Implement Document List Panel
  - [x] 8.1 Create DocumentListPanel class
    - Create `src/multimodal_librarian/static/js/document-list-panel.js`
    - Implement show/hide methods
    - Implement updateDocumentList for rendering
    - Implement handleDelete and handleRetry actions
    - Wire WebSocket messages for document operations
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_
  
  - [x] 8.2 Update upload button to show dropdown
    - Modify upload button in chat UI to show dropdown
    - Add "Upload PDF" and "View Documents" options
    - Wire dropdown to ChatUploadHandler and DocumentListPanel
    - _Requirements: 8.1, 8.2_
  
  - [x] 8.3 Add CSS styles for document list panel
    - Style dropdown menu and document list
    - Style document items with status badges
    - Style action buttons (delete, retry)
    - _Requirements: 8.2_

- [x] 9. Remove Document Library Panel
  - [x] 9.1 Remove Documents button from header
    - Remove documentsBtn from header in index.html or chat.js
    - Remove DocumentManager class instantiation
    - Remove document_upload.js script include (or keep for shared utilities)
    - _Requirements: 7.1_
  
  - [x] 9.2 Clean up unused Document Library code
    - Remove or deprecate document modal HTML
    - Remove unused event listeners
    - Update any references to old document management
    - _Requirements: 7.1_

- [x] 10. Implement Document Deletion Completeness
  - [x] 10.1 Enhance document deletion to remove from all stores
    - Update DocumentManager.delete_document_completely
    - Ensure removal from S3, OpenSearch, Neptune, PostgreSQL
    - Add verification of deletion success
    - _Requirements: 8.3_
  
  - [ ]* 10.2 Write property test for deletion completeness
    - **Property 11: Document Deletion Completeness**
    - Verify document removed from all storage locations
    - **Validates: Requirements 8.3**

- [x] 11. Implement Document Retry Functionality
  - [x] 11.1 Enhance retry to restart from failed stage
    - Update DocumentManager.retry_document_processing
    - Track failed stage in processing metadata
    - Restart processing from appropriate stage
    - _Requirements: 8.4_
  
  - [ ]* 11.2 Write property test for retry functionality
    - **Property 12: Failed Document Retry**
    - Verify failed documents can be retried and status transitions
    - **Validates: Requirements 8.4**

- [x] 12. Integration Testing
  - [x]* 12.1 Write integration test for end-to-end upload flow
    - Upload PDF via WebSocket
    - Verify status messages received
    - Verify document searchable
    - _Requirements: 1.1, 2.1, 2.2, 2.3, 2.4, 3.1, 3.3_
  
  - [x]* 12.2 Write integration test for document management flow
    - Upload, list, delete document
    - Verify removal from all stores
    - _Requirements: 8.2, 8.3_
  
  - [x]* 12.3 Write integration test for search prioritization
    - Upload Librarian document
    - Query with matching content
    - Verify Librarian result ranked first
    - _Requirements: 5.1, 5.2, 5.6_

- [x] 13. Final Checkpoint - All features complete
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties
- Unit tests validate specific examples and edge cases
- The implementation follows the existing dependency injection architecture
- WebSocket message handlers use FastAPI's Depends for service injection

## Bug Fixes Applied (Post-Implementation)

### BF-1: WebSocket DateTime Serialization (2026-02-09)
**Issue**: Document upload showed "Queued for processing... 0%" and never progressed. Document list panel showed "Loading documents..." indefinitely.

**Root Cause**: Pydantic models with `datetime` fields (e.g., `DocumentInfo.upload_timestamp`) were not JSON serializable when sent via WebSocket. The error "Object of type datetime is not JSON serializable" caused WebSocket connections to close before messages could be delivered.

**Fix**: Changed all `model_dump()` calls to `model_dump(mode='json')` in `chat_document_handlers.py` to ensure proper datetime serialization.

**Files Modified**:
- `src/multimodal_librarian/api/routers/chat_document_handlers.py`

### BF-2: Duplicate Document Error Display (2026-02-09)
**Issue**: When uploading a duplicate document, the error message wasn't displayed to the user - the upload just appeared stuck.

**Root Cause**: The duplicate detection was working correctly, but the error message wasn't reaching the frontend due to the datetime serialization issue (BF-1), and the frontend wasn't properly updating status cards on error.

**Fix**: 
1. Added specific error code detection for `DUPLICATE_DOCUMENT` errors
2. Improved error message extraction for duplicate document errors
3. Enhanced `handleUploadError()` in JavaScript to find and update status cards when errors occur
4. Added logic to show failure state on status cards and auto-remove after 10 seconds

**Files Modified**:
- `src/multimodal_librarian/api/routers/chat_document_handlers.py`
- `src/multimodal_librarian/static/js/chat-upload-handler.js`
