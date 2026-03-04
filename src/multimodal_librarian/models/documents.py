"""
Document models for PDF upload functionality.

This module contains Pydantic models for document management,
including upload requests, responses, and data validation.
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum
from pydantic import BaseModel, Field, validator
import uuid


class DocumentStatus(str, Enum):
    """Document processing status enumeration."""
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ChunkType(str, Enum):
    """Document chunk type enumeration."""
    TEXT = "text"
    IMAGE = "image"
    TABLE = "table"
    CHART = "chart"


class Document(BaseModel):
    """Document model for PDF upload functionality."""
    
    id: str = Field(..., description="Unique document identifier")
    user_id: str = Field(..., description="Owner user ID")
    title: str = Field(..., description="Document title", max_length=255)
    description: Optional[str] = Field(None, description="Document description")
    filename: str = Field(..., description="Original filename", max_length=255)
    file_size: int = Field(..., description="File size in bytes", gt=0)
    mime_type: str = Field(..., description="MIME type", max_length=100)
    s3_key: str = Field(..., description="S3 storage key", max_length=500)
    status: DocumentStatus = Field(..., description="Processing status")
    processing_error: Optional[str] = Field(None, description="Error message if failed")
    upload_timestamp: datetime = Field(..., description="Upload time")
    processing_started_at: Optional[datetime] = Field(None, description="Processing start time")
    processing_completed_at: Optional[datetime] = Field(None, description="Processing completion time")
    page_count: Optional[int] = Field(None, description="Number of pages", gt=0)
    chunk_count: Optional[int] = Field(None, description="Number of chunks generated", ge=0)
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    @validator('file_size')
    def validate_file_size(cls, v):
        """Validate file size is within limits."""
        max_size = 100 * 1024 * 1024  # 100MB
        if v > max_size:
            raise ValueError(f"File size {v} exceeds maximum limit of {max_size} bytes")
        return v

    @validator('mime_type')
    def validate_mime_type(cls, v):
        """Validate MIME type is PDF."""
        allowed_types = ['application/pdf']
        if v not in allowed_types:
            raise ValueError(f"MIME type {v} not allowed. Must be one of: {allowed_types}")
        return v

    class Config:
        """Pydantic configuration."""
        use_enum_values = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class DocumentChunk(BaseModel):
    """Document chunk model for processed content."""
    
    id: str = Field(..., description="Unique chunk identifier")
    document_id: str = Field(..., description="Parent document ID")
    chunk_index: int = Field(..., description="Chunk order index", ge=0)
    content: str = Field(..., description="Chunk content")
    page_number: Optional[int] = Field(None, description="Source page number", gt=0)
    section_title: Optional[str] = Field(None, description="Section title", max_length=255)
    chunk_type: ChunkType = Field(..., description="Type of chunk")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Chunk metadata")
    created_at: datetime = Field(..., description="Creation timestamp")

    class Config:
        """Pydantic configuration."""
        use_enum_values = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class DocumentUploadRequest(BaseModel):
    """Request model for document upload."""
    
    title: Optional[str] = Field(None, description="Document title", max_length=255)
    description: Optional[str] = Field(None, description="Document description")

    @validator('title')
    def validate_title(cls, v):
        """Validate title if provided."""
        if v is not None and len(v.strip()) == 0:
            raise ValueError("Title cannot be empty if provided")
        return v.strip() if v else v


class DocumentUploadResponse(BaseModel):
    """Response model for document upload."""
    
    document_id: str = Field(..., description="Created document ID")
    title: str = Field(..., description="Document title")
    status: DocumentStatus = Field(..., description="Current status")
    file_size: int = Field(..., description="File size in bytes")
    upload_timestamp: datetime = Field(..., description="Upload timestamp")

    class Config:
        """Pydantic configuration."""
        use_enum_values = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class DocumentListResponse(BaseModel):
    """Response model for document list."""
    
    documents: List[Document] = Field(..., description="List of documents")
    total_count: int = Field(..., description="Total number of documents")
    page: int = Field(..., description="Current page number", ge=1)
    page_size: int = Field(..., description="Number of items per page", ge=1, le=100)
    has_next: bool = Field(..., description="Whether there are more pages")


class ProcessingStatus(BaseModel):
    """Processing status model for document processing."""
    
    document_id: str = Field(..., description="Document ID")
    status: DocumentStatus = Field(..., description="Current status")
    progress_percentage: float = Field(..., description="Processing progress (0-100)", ge=0, le=100)
    current_step: str = Field(..., description="Current processing step")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    estimated_completion: Optional[datetime] = Field(None, description="Estimated completion time")

    class Config:
        """Pydantic configuration."""
        use_enum_values = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class DocumentSearchRequest(BaseModel):
    """Request model for document search."""
    
    query: Optional[str] = Field(None, description="Search query")
    status: Optional[DocumentStatus] = Field(None, description="Filter by status")
    page: int = Field(1, description="Page number", ge=1)
    page_size: int = Field(50, description="Items per page", ge=1, le=100)
    sort_by: str = Field("upload_timestamp", description="Sort field")
    sort_order: str = Field("desc", description="Sort order (asc/desc)")

    @validator('sort_by')
    def validate_sort_by(cls, v):
        """Validate sort field."""
        allowed_fields = ['upload_timestamp', 'title', 'file_size', 'status']
        if v not in allowed_fields:
            raise ValueError(f"Sort field {v} not allowed. Must be one of: {allowed_fields}")
        return v

    @validator('sort_order')
    def validate_sort_order(cls, v):
        """Validate sort order."""
        if v.lower() not in ['asc', 'desc']:
            raise ValueError("Sort order must be 'asc' or 'desc'")
        return v.lower()


class DocumentMetadata(BaseModel):
    """Document metadata model."""
    
    title: str = Field(..., description="Document title")
    filename: str = Field(..., description="Original filename")
    file_size: int = Field(..., description="File size in bytes")
    mime_type: str = Field(..., description="MIME type")
    user_id: str = Field(..., description="Owner user ID")
    s3_key: str = Field(..., description="S3 storage key")
    upload_timestamp: datetime = Field(default_factory=datetime.utcnow, description="Upload timestamp")
    description: Optional[str] = Field(None, description="Document description")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class DocumentError(BaseModel):
    """Document error model."""
    
    error_code: str = Field(..., description="Error code")
    error_message: str = Field(..., description="Error message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Error timestamp")

    class Config:
        """Pydantic configuration."""
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


# Utility functions for model conversion

def generate_document_id() -> str:
    """Generate a unique document ID."""
    return str(uuid.uuid4())


def generate_chunk_id() -> str:
    """Generate a unique chunk ID."""
    return str(uuid.uuid4())


def create_document_from_upload(
    upload_request: DocumentUploadRequest,
    filename: str,
    file_size: int,
    mime_type: str,
    user_id: str,
    s3_key: str
) -> Document:
    """Create a Document instance from upload request."""
    document_id = generate_document_id()
    title = upload_request.title or filename
    
    return Document(
        id=document_id,
        user_id=user_id,
        title=title,
        description=upload_request.description,
        filename=filename,
        file_size=file_size,
        mime_type=mime_type,
        s3_key=s3_key,
        status=DocumentStatus.UPLOADED,
        upload_timestamp=datetime.utcnow(),
        metadata={}
    )


def create_upload_response(document: Document) -> DocumentUploadResponse:
    """Create upload response from document."""
    return DocumentUploadResponse(
        document_id=document.id,
        title=document.title,
        status=document.status,
        file_size=document.file_size,
        upload_timestamp=document.upload_timestamp
    )