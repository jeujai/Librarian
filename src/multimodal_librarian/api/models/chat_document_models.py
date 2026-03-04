"""
Chat Document WebSocket Message Models.

This module defines the Pydantic models for WebSocket messages related to
document operations within the chat interface.

Requirements: 1.1, 7.2, 8.3, 8.4
"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

# =============================================================================
# Client → Server Messages
# =============================================================================

class ChatUploadMessage(BaseModel):
    """
    WebSocket message for chat document upload.
    
    Sent by the client when uploading a document via the chat interface.
    
    Requirements: 1.1, 1.2, 1.3
    """
    type: Literal["chat_document_upload"] = "chat_document_upload"
    filename: str = Field(..., description="Original filename")
    file_size: int = Field(..., ge=0, description="File size in bytes")
    content_type: str = Field(..., description="MIME type of the file")
    file_data: str = Field(..., description="Base64 encoded file content")
    title: Optional[str] = Field(None, description="Optional document title")
    description: Optional[str] = Field(None, description="Optional document description")


class DocumentListRequest(BaseModel):
    """
    Request to list documents.
    
    Sent by the client to retrieve the list of uploaded documents.
    
    Requirements: 8.2
    """
    type: Literal["document_list_request"] = "document_list_request"
    status_filter: Optional[str] = Field(None, description="Filter by status: uploaded, processing, completed, failed")
    page: int = Field(1, ge=1, description="Page number for pagination")
    page_size: int = Field(20, ge=1, le=100, description="Number of documents per page")


class DocumentDeleteRequest(BaseModel):
    """
    Request to delete a document.
    
    Sent by the client to delete a document from all storage locations.
    
    Requirements: 8.3
    """
    type: Literal["document_delete_request"] = "document_delete_request"
    document_id: str = Field(..., description="Document ID to delete")


class DocumentRetryRequest(BaseModel):
    """
    Request to retry failed document processing.
    
    Sent by the client to retry processing a failed document.
    
    Requirements: 8.4
    """
    type: Literal["document_retry_request"] = "document_retry_request"
    document_id: str = Field(..., description="Document ID to retry")


# =============================================================================
# Server → Client Messages
# =============================================================================

class DocumentInfo(BaseModel):
    """
    Document information for list display.
    
    Requirements: 8.2
    """
    document_id: str
    title: str
    filename: str
    status: Literal["uploaded", "processing", "completed", "failed"]
    upload_timestamp: datetime
    file_size: int
    chunk_count: Optional[int] = None
    error_message: Optional[str] = None


class DocumentListMessage(BaseModel):
    """
    WebSocket message containing document list.
    
    Sent by the server in response to a document list request.
    
    Requirements: 8.2
    """
    type: Literal["document_list"] = "document_list"
    documents: List[DocumentInfo]
    total_count: int
    page: int
    page_size: int
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class DocumentUploadStartedMessage(BaseModel):
    """
    WebSocket message indicating upload has started.
    
    Sent by the server when a document upload is received and processing begins.
    
    Requirements: 3.1
    """
    type: Literal["document_upload_started"] = "document_upload_started"
    document_id: str
    filename: str
    file_size: int
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class DocumentUploadErrorMessage(BaseModel):
    """
    WebSocket message for upload errors.
    
    Sent by the server when a document upload fails validation or processing.
    
    Requirements: 1.4, 1.5, 2.6
    """
    type: Literal["document_upload_error"] = "document_upload_error"
    filename: str
    error_code: str
    error_message: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class DocumentDeletedMessage(BaseModel):
    """
    WebSocket message confirming document deletion.
    
    Sent by the server when a document has been successfully deleted.
    
    Requirements: 8.3
    """
    type: Literal["document_deleted"] = "document_deleted"
    document_id: str
    success: bool
    message: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class DocumentRetryStartedMessage(BaseModel):
    """
    WebSocket message confirming retry has started.
    
    Sent by the server when document processing retry has been initiated.
    
    Requirements: 8.4
    """
    type: Literal["document_retry_started"] = "document_retry_started"
    document_id: str
    message: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# =============================================================================
# Error Codes
# =============================================================================

class DocumentUploadErrorCodes:
    """Error codes for document upload failures."""
    INVALID_FILE_TYPE = "invalid_file_type"
    FILE_TOO_LARGE = "file_too_large"
    INVALID_BASE64 = "invalid_base64"
    PROCESSING_FAILED = "processing_failed"
    DUPLICATE_DOCUMENT = "duplicate_document"
    STORAGE_ERROR = "storage_error"
    UNKNOWN_ERROR = "unknown_error"
