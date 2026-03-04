"""
Mock upload service for testing document upload API without database.

This service provides mock implementations for testing the document upload API
endpoints without requiring a running database.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from ..models.documents import (
    Document,
    DocumentListResponse,
    DocumentSearchRequest,
    DocumentStatus,
    DocumentUploadRequest,
    DocumentUploadResponse,
)

logger = logging.getLogger(__name__)


class UploadError(Exception):
    """Base exception for upload operations."""
    pass


class ValidationError(UploadError):
    """Exception for file validation errors."""
    pass


class UploadServiceMock:
    """
    Mock service for handling document uploads and management.
    
    Provides mock implementations for testing without database dependencies.
    """
    
    def __init__(self):
        """Initialize mock upload service."""
        # In-memory storage for testing
        self.documents = {}
    
    def _validate_file(self, file_data: bytes, filename: str) -> None:
        """
        Validate uploaded file.
        
        Args:
            file_data: File content as bytes
            filename: Original filename
            
        Raises:
            ValidationError: If validation fails
        """
        # Check file size (max 100MB)
        max_size = 100 * 1024 * 1024  # 100MB
        if len(file_data) > max_size:
            raise ValidationError(f"File too large: {len(file_data)} bytes (max: {max_size})")
        
        # Check file extension
        if not filename.lower().endswith(('.pdf', '.txt')):
            raise ValidationError(f"Unsupported file type: {filename}")
        
        # Check file content (basic validation)
        if len(file_data) == 0:
            raise ValidationError("File is empty")
    
    async def upload_document(
        self, 
        file_data: bytes, 
        filename: str, 
        upload_request: DocumentUploadRequest,
        user_id: str = "default_user"
    ) -> DocumentUploadResponse:
        """
        Mock upload and process a document.
        
        Args:
            file_data: Raw file bytes
            filename: Original filename
            upload_request: Upload request with metadata
            user_id: User identifier
            
        Returns:
            DocumentUploadResponse with upload results
        """
        try:
            # Validate file
            self._validate_file(file_data, filename)
            
            # Generate document ID and metadata
            document_id = str(uuid4())
            upload_time = datetime.utcnow()
            title = upload_request.title or filename
            description = upload_request.description
            
            # Mock S3 key
            s3_key = f"documents/{user_id}/{document_id}/{filename}"
            
            # Create document object
            document = Document(
                id=document_id,
                user_id=user_id,
                title=title,
                description=description,
                filename=filename,
                file_size=len(file_data),
                mime_type='application/pdf',
                s3_key=s3_key,
                status=DocumentStatus.UPLOADED,
                upload_timestamp=upload_time,
                metadata={"description": description}
            )
            
            # Store in mock storage
            self.documents[document_id] = document
            
            # Prepare response
            response = DocumentUploadResponse(
                document_id=document_id,
                title=document.title,
                status=document.status,
                file_size=document.file_size,
                upload_timestamp=document.upload_timestamp
            )
            
            logger.info(f"Document uploaded successfully (mock): {document_id}")
            return response
            
        except ValidationError:
            raise
        except Exception as e:
            logger.error(f"Error uploading document (mock): {e}")
            raise UploadError(f"Failed to upload document: {e}")
    
    async def list_documents(
        self,
        user_id: str = "default_user",
        search: Optional[str] = None,
        status: Optional[DocumentStatus] = None,
        page: int = 1,
        page_size: int = 20
    ) -> DocumentListResponse:
        """
        Mock list documents with optional filtering.
        
        Args:
            user_id: User identifier
            search: Search term for title/filename
            status: Filter by document status
            page: Page number (1-based)
            page_size: Items per page
            
        Returns:
            DocumentListResponse with documents and pagination
        """
        try:
            # Filter documents by user
            user_documents = [doc for doc in self.documents.values() if doc.user_id == user_id]
            
            # Apply search filter
            if search:
                search_lower = search.lower()
                user_documents = [
                    doc for doc in user_documents 
                    if search_lower in doc.title.lower() or search_lower in doc.filename.lower()
                ]
            
            # Apply status filter
            if status:
                user_documents = [doc for doc in user_documents if doc.status == status]
            
            # Sort by upload timestamp (newest first)
            user_documents.sort(key=lambda x: x.upload_timestamp, reverse=True)
            
            # Apply pagination
            total = len(user_documents)
            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size
            page_documents = user_documents[start_idx:end_idx]
            
            has_next = end_idx < total
            
            return DocumentListResponse(
                documents=page_documents,
                total_count=total,
                page=page,
                page_size=page_size,
                has_next=has_next
            )
            
        except Exception as e:
            logger.error(f"Error listing documents (mock): {e}")
            raise UploadError(f"Failed to list documents: {e}")
    
    async def get_document(self, document_id: str, user_id: str = "default_user") -> Optional[Document]:
        """
        Mock get document by ID.
        
        Args:
            document_id: Document identifier (string or UUID)
            user_id: User identifier for access control
            
        Returns:
            Document or None if not found
        """
        try:
            # Convert UUID to string if needed
            if hasattr(document_id, '__str__'):
                document_id = str(document_id)
            
            document = self.documents.get(document_id)
            if document and document.user_id == user_id:
                return document
            return None
                
        except Exception as e:
            logger.error(f"Error getting document (mock): {e}")
            return None
    
    async def delete_document(self, document_id: str, user_id: str = "default_user") -> bool:
        """
        Mock delete document and associated files.
        
        Args:
            document_id: Document identifier (string or UUID)
            user_id: User identifier for access control
            
        Returns:
            True if deleted successfully
        """
        try:
            # Convert UUID to string if needed
            if hasattr(document_id, '__str__'):
                document_id = str(document_id)
            
            document = self.documents.get(document_id)
            if document and document.user_id == user_id:
                del self.documents[document_id]
                logger.info(f"Document deleted successfully (mock): {document_id}")
                return True
            return False
                
        except Exception as e:
            logger.error(f"Error deleting document (mock): {e}")
            return False                
        except Exception as e:
            logger.error(f"Error deleting document (mock): {e}")
            return False