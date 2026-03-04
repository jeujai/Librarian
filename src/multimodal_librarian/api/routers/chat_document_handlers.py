"""
Chat Document WebSocket Message Handlers.

This module provides WebSocket message handlers for document operations
within the chat interface, including upload, list, delete, and retry.

Requirements: 1.1, 7.2, 8.3, 8.4
"""

import base64
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Optional
from uuid import UUID, uuid4

from ..models.chat_document_models import (
    ChatUploadMessage,
    DocumentDeletedMessage,
    DocumentDeleteRequest,
    DocumentInfo,
    DocumentListMessage,
    DocumentListRequest,
    DocumentRetryRequest,
    DocumentRetryStartedMessage,
    DocumentUploadErrorCodes,
    DocumentUploadErrorMessage,
    DocumentUploadStartedMessage,
)

if TYPE_CHECKING:
    from ...components.document_manager.document_manager import DocumentManager
    from ...services.processing_status_service import ProcessingStatusService
    from ..dependencies.services import ConnectionManager

logger = logging.getLogger(__name__)

# Constants for validation
MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024  # 100MB
SUPPORTED_MIME_TYPES = ["application/pdf"]


async def handle_chat_document_upload(
    message_data: dict,
    connection_id: str,
    manager: "ConnectionManager",
    document_manager: "DocumentManager",
    processing_status_service: Optional["ProcessingStatusService"] = None
) -> None:
    """
    Handle document upload initiated from chat interface.
    
    This handler validates the uploaded file, decodes the base64 content,
    and initiates document processing through the DocumentManager.
    Status updates are sent via the ProcessingStatusService.
    
    Args:
        message_data: Upload message with file data
        connection_id: WebSocket connection ID
        manager: Connection manager for sending responses
        document_manager: Document manager for processing
        processing_status_service: Optional status service for progress updates
        
    Requirements: 1.1, 1.4, 1.5, 7.2
    """
    try:
        # Parse and validate the upload message
        try:
            upload_msg = ChatUploadMessage(**message_data)
        except Exception as e:
            logger.error(f"Invalid upload message format: {e}")
            await _send_upload_error(
                manager, connection_id,
                filename=message_data.get('filename', 'unknown'),
                error_code=DocumentUploadErrorCodes.UNKNOWN_ERROR,
                error_message=f"Invalid message format: {str(e)}"
            )
            return
        
        # Validate file type (Requirement 1.4)
        if upload_msg.content_type not in SUPPORTED_MIME_TYPES:
            logger.warning(f"Rejected non-PDF file: {upload_msg.filename} ({upload_msg.content_type})")
            await _send_upload_error(
                manager, connection_id,
                filename=upload_msg.filename,
                error_code=DocumentUploadErrorCodes.INVALID_FILE_TYPE,
                error_message="Only PDF files are supported for document cataloging"
            )
            return
        
        # Validate file size (Requirement 1.5)
        if upload_msg.file_size > MAX_FILE_SIZE_BYTES:
            logger.warning(f"Rejected oversized file: {upload_msg.filename} ({upload_msg.file_size} bytes)")
            await _send_upload_error(
                manager, connection_id,
                filename=upload_msg.filename,
                error_code=DocumentUploadErrorCodes.FILE_TOO_LARGE,
                error_message=f"File exceeds 100MB limit. Please upload a smaller file."
            )
            return
        
        # Decode base64 file data
        try:
            file_data = base64.b64decode(upload_msg.file_data)
        except Exception as e:
            logger.error(f"Failed to decode base64 file data: {e}")
            await _send_upload_error(
                manager, connection_id,
                filename=upload_msg.filename,
                error_code=DocumentUploadErrorCodes.INVALID_BASE64,
                error_message="Failed to decode file data"
            )
            return
        
        # Verify decoded size matches declared size
        if len(file_data) != upload_msg.file_size:
            logger.warning(f"File size mismatch: declared {upload_msg.file_size}, actual {len(file_data)}")
            # Allow some tolerance for encoding differences
            if abs(len(file_data) - upload_msg.file_size) > 1024:  # 1KB tolerance
                await _send_upload_error(
                    manager, connection_id,
                    filename=upload_msg.filename,
                    error_code=DocumentUploadErrorCodes.UNKNOWN_ERROR,
                    error_message="File size mismatch after decoding"
                )
                return
        
        # Generate document ID
        document_id = uuid4()
        
        # Start document processing first to check for duplicates
        # before creating any UI elements
        try:
            result = await document_manager.upload_and_process_document(
                file_data=file_data,
                filename=upload_msg.filename,
                title=upload_msg.title,
                description=upload_msg.description
            )
            
            # Use the actual document_id from the database (not the
            # locally generated one) so the tracker matches what
            # Celery workers report progress against.
            actual_document_id = result.get('document_id', document_id)
            
            # Only register and send started message after we know
            # it's not a duplicate
            if processing_status_service:
                await processing_status_service.register_upload(
                    document_id=actual_document_id,
                    connection_id=connection_id,
                    filename=upload_msg.filename
                )
            
            # Send upload started message
            started_msg = DocumentUploadStartedMessage(
                document_id=str(actual_document_id),
                filename=upload_msg.filename,
                file_size=len(file_data)
            )
            await manager.send_personal_message(
                started_msg.model_dump(mode='json'), connection_id
            )
            
            logger.info(f"Document upload initiated: {result.get('document_id')}")
            
        except Exception as e:
            error_str = str(e)
            logger.error(f"Document processing failed: {error_str}")
            
            # Determine error code based on error type
            error_code = DocumentUploadErrorCodes.PROCESSING_FAILED
            error_message = f"Failed to process document: {error_str}"
            retry_available = True
            
            # Check for duplicate document error
            if "already exists" in error_str.lower() or "duplicate" in error_str.lower():
                error_code = DocumentUploadErrorCodes.DUPLICATE_DOCUMENT
                # Extract the cleaner message
                if "Document already exists:" in error_str:
                    error_message = error_str.split("Document already exists:")[-1].strip().strip("'\"")
                    error_message = f"Document already exists: {error_message}"
                else:
                    error_message = "A document with the same content already exists"
                retry_available = False
            
            # Send error via upload error message only (not processing status)
            # to avoid duplicate error messages in the UI
            await _send_upload_error(
                manager, connection_id,
                filename=upload_msg.filename,
                error_code=error_code,
                error_message=error_message
            )
            
    except Exception as e:
        logger.error(f"Unexpected error in chat document upload: {e}")
        await _send_upload_error(
            manager, connection_id,
            filename=message_data.get('filename', 'unknown'),
            error_code=DocumentUploadErrorCodes.UNKNOWN_ERROR,
            error_message="An unexpected error occurred during upload"
        )


async def handle_document_list_request(
    message_data: dict,
    connection_id: str,
    manager: "ConnectionManager",
    document_manager: "DocumentManager"
) -> None:
    """
    Handle request to list user's documents.
    
    Args:
        message_data: Request message with optional filters
        connection_id: WebSocket connection ID
        manager: Connection manager for sending responses
        document_manager: Document manager for retrieving documents
        
    Requirements: 8.2
    """
    try:
        # Parse request
        try:
            list_request = DocumentListRequest(**message_data)
        except Exception as e:
            logger.error(f"Invalid document list request: {e}")
            await manager.send_personal_message({
                'type': 'error',
                'message': f"Invalid request format: {str(e)}"
            }, connection_id)
            return
        
        # Map status filter string to DocumentStatus enum if provided
        status_filter = None
        if list_request.status_filter:
            from ...models.documents import DocumentStatus
            status_map = {
                'uploaded': DocumentStatus.UPLOADED,
                'processing': DocumentStatus.PROCESSING,
                'completed': DocumentStatus.COMPLETED,
                'failed': DocumentStatus.FAILED
            }
            status_filter = status_map.get(list_request.status_filter.lower())
        
        # Get documents from document manager
        # Convert page/page_size to limit/offset for the document manager
        limit = list_request.page_size
        offset = (list_request.page - 1) * list_request.page_size
        
        documents_result = await document_manager.list_documents_with_status(
            status_filter=status_filter,
            limit=limit,
            offset=offset
        )
        
        # Convert to DocumentInfo models
        document_infos = []
        for doc in documents_result.get('documents', []):
            # Map DocumentStatus to string status
            status_str = _map_status_to_string(doc.get('status'))
            
            doc_info = DocumentInfo(
                document_id=str(doc.get('document_id', '')),
                title=doc.get('title', 'Untitled'),
                filename=doc.get('filename', 'unknown'),
                status=status_str,
                upload_timestamp=doc.get('upload_timestamp', datetime.utcnow()),
                file_size=doc.get('file_size', 0),
                chunk_count=doc.get('chunk_count'),
                error_message=doc.get('processing_error')
            )
            document_infos.append(doc_info)
        
        # Send response
        response = DocumentListMessage(
            documents=document_infos,
            total_count=documents_result.get('total_count', len(document_infos)),
            page=list_request.page,
            page_size=list_request.page_size
        )
        
        await manager.send_personal_message(response.model_dump(mode='json'), connection_id)
        
        logger.debug(f"Sent document list to {connection_id}: {len(document_infos)} documents")
        
    except Exception as e:
        logger.error(f"Error handling document list request: {e}")
        await manager.send_personal_message({
            'type': 'error',
            'message': 'Failed to retrieve document list'
        }, connection_id)


async def handle_document_delete_request(
    message_data: dict,
    connection_id: str,
    manager: "ConnectionManager",
    document_manager: "DocumentManager"
) -> None:
    """
    Handle request to delete a document.

    This handler removes the document from all storage locations:
    S3, OpenSearch, Neptune, and PostgreSQL.

    Args:
        message_data: Delete request with document_id
        connection_id: WebSocket connection ID
        manager: Connection manager for sending responses
        document_manager: Document manager for deletion

    Requirements: 8.3
    """
    try:
        # Parse request
        try:
            delete_request = DocumentDeleteRequest(**message_data)
        except Exception as e:
            logger.error(f"Invalid document delete request: {e}")
            await manager.send_personal_message({
                'type': 'error',
                'message': f"Invalid request format: {str(e)}"
            }, connection_id)
            return

        # Parse document ID
        try:
            document_id = UUID(delete_request.document_id)
        except ValueError:
            await manager.send_personal_message({
                'type': 'error',
                'message': 'Invalid document ID format'
            }, connection_id)
            return

        logger.info(f"Deleting document {document_id} for connection {connection_id}")

        # Delete document completely from all stores
        deletion_results = await document_manager.delete_document_completely(document_id)

        # Extract success status from results
        success = deletion_results.get('success', False)

        # Build detailed message
        if success:
            details = []
            if deletion_results.get('milvus_deleted', 0) > 0:
                details.append(f"{deletion_results['milvus_deleted']} vectors from Milvus")
            if deletion_results.get('neo4j_deleted', 0) > 0:
                details.append(f"{deletion_results['neo4j_deleted']} nodes from Neo4j")

            message = "Document deleted successfully"
            if details:
                message += f" (removed {', '.join(details)})"
        else:
            errors = deletion_results.get('errors', [])
            message = "Failed to delete document"
            if errors:
                message += f": {'; '.join(errors)}"

        # Send response
        response = DocumentDeletedMessage(
            document_id=str(document_id),
            success=success,
            message=message
        )

        await manager.send_personal_message(response.model_dump(mode='json'), connection_id)

        if success:
            logger.info(
                f"Document {document_id} deleted successfully "
                f"(Milvus: {deletion_results.get('milvus_deleted', 0)}, "
                f"Neo4j: {deletion_results.get('neo4j_deleted', 0)})"
            )
        else:
            logger.warning(f"Failed to delete document {document_id}: {deletion_results.get('errors', [])}")

    except Exception as e:
        logger.error(f"Error handling document delete request: {e}")
        await manager.send_personal_message({
            'type': 'error',
            'message': 'Failed to delete document'
        }, connection_id)


async def handle_document_retry_request(
    message_data: dict,
    connection_id: str,
    manager: "ConnectionManager",
    document_manager: "DocumentManager",
    processing_status_service: Optional["ProcessingStatusService"] = None
) -> None:
    """
    Handle request to retry failed document processing.
    
    This handler restarts processing from the failed stage.
    
    Args:
        message_data: Retry request with document_id
        connection_id: WebSocket connection ID
        manager: Connection manager for sending responses
        document_manager: Document manager for retry
        processing_status_service: Optional status service for progress updates
        
    Requirements: 8.4
    """
    try:
        # Parse request
        try:
            retry_request = DocumentRetryRequest(**message_data)
        except Exception as e:
            logger.error(f"Invalid document retry request: {e}")
            await manager.send_personal_message({
                'type': 'error',
                'message': f"Invalid request format: {str(e)}"
            }, connection_id)
            return
        
        # Parse document ID
        try:
            document_id = UUID(retry_request.document_id)
        except ValueError:
            await manager.send_personal_message({
                'type': 'error',
                'message': 'Invalid document ID format'
            }, connection_id)
            return
        
        logger.info(f"Retrying document processing for {document_id}")
        
        # Register retry with processing status service
        if processing_status_service:
            # Get document info for filename
            try:
                doc_status = await document_manager.get_document_status(document_id)
                filename = doc_status.get('filename', 'unknown')
            except Exception:
                filename = 'unknown'
            
            await processing_status_service.register_upload(
                document_id=document_id,
                connection_id=connection_id,
                filename=filename
            )
        
        # Retry document processing
        success = await document_manager.retry_document_processing(document_id)
        
        if success:
            # Send retry started message
            response = DocumentRetryStartedMessage(
                document_id=str(document_id),
                message="Document processing retry initiated"
            )
            await manager.send_personal_message(response.model_dump(mode='json'), connection_id)
            logger.info(f"Document {document_id} retry initiated successfully")
        else:
            await manager.send_personal_message({
                'type': 'error',
                'message': 'Failed to retry document processing. Document may not be in a failed state.'
            }, connection_id)
            logger.warning(f"Failed to retry document {document_id}")
        
    except Exception as e:
        logger.error(f"Error handling document retry request: {e}")
        await manager.send_personal_message({
            'type': 'error',
            'message': 'Failed to retry document processing'
        }, connection_id)


# =============================================================================
# Helper Functions
# =============================================================================

async def _send_upload_error(
    manager: "ConnectionManager",
    connection_id: str,
    filename: str,
    error_code: str,
    error_message: str
) -> None:
    """Send an upload error message to the client."""
    error_msg = DocumentUploadErrorMessage(
        filename=filename,
        error_code=error_code,
        error_message=error_message
    )
    await manager.send_personal_message(error_msg.model_dump(mode='json'), connection_id)


def _map_status_to_string(status) -> str:
    """Map DocumentStatus enum to string for API response."""
    if status is None:
        return "uploaded"
    
    # Handle both enum and string values
    status_str = status.value if hasattr(status, 'value') else str(status)
    
    status_map = {
        'uploaded': 'uploaded',
        'processing': 'processing',
        'completed': 'completed',
        'failed': 'failed',
        'pending': 'uploaded',
        'error': 'failed'
    }
    
    return status_map.get(status_str.lower(), 'uploaded')
