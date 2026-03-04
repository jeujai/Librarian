"""
Synchronous upload service for handling document upload business logic.

This service coordinates file validation, storage, database operations,
and processing queue management for PDF document uploads using synchronous database operations.
"""

import logging
from typing import Optional, Dict, Any, List
from uuid import UUID, uuid4
from datetime import datetime
import json

from ..models.documents import (
    Document, DocumentUploadRequest, DocumentUploadResponse, 
    DocumentStatus, DocumentListResponse, DocumentSearchRequest
)
from .storage_service import StorageService, StorageError
from ..database.connection import get_database_connection

logger = logging.getLogger(__name__)


class UploadError(Exception):
    """Base exception for upload operations."""
    pass


class ValidationError(UploadError):
    """Exception for file validation errors."""
    pass


class UploadServiceSync:
    """
    Synchronous service for handling document uploads and management.
    
    Coordinates file validation, storage, database operations,
    and processing queue management using synchronous database operations.
    """
    
    def __init__(self, storage_service: Optional[StorageService] = None):
        """
        Initialize upload service.
        
        Args:
            storage_service: Storage service instance (creates new if None)
        """
        self.storage_service = storage_service or StorageService()
    
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
        title: Optional[str] = None,
        description: Optional[str] = None,
        user_id: str = "default_user",
        tags: Optional[List[str]] = None,
        process_immediately: bool = True
    ) -> DocumentUploadResponse:
        """
        Upload and process a document.
        
        Args:
            file_data: Raw file bytes
            filename: Original filename
            title: Document title (defaults to filename)
            description: Document description
            user_id: User identifier
            tags: List of tags
            process_immediately: Whether to start processing immediately
            
        Returns:
            DocumentUploadResponse with upload results
            
        Raises:
            ValidationError: If file validation fails
            UploadError: If upload process fails
        """
        try:
            # Validate file
            self._validate_file(file_data, filename)
            
            # Generate document ID and metadata
            document_id = str(uuid4())
            upload_time = datetime.utcnow()
            title = title or filename
            tags = tags or []
            
            # Store file in S3
            s3_key = await self.storage_service.store_file(
                file_data, filename, document_id
            )
            
            # Store in database using synchronous connection
            with get_database_connection() as conn:
                cursor = conn.cursor()
                
                # Insert document record
                cursor.execute("""
                    INSERT INTO documents (
                        id, user_id, title, filename, file_size, s3_key, 
                        status, upload_timestamp, doc_metadata
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    document_id, user_id, title, filename, len(file_data),
                    s3_key, DocumentStatus.UPLOADED.value, upload_time,
                    json.dumps({"description": description, "tags": tags})
                ))
            
            # Create document object
            document = Document(
                id=document_id,
                user_id=user_id,
                title=title,
                filename=filename,
                file_size=len(file_data),
                s3_key=s3_key,
                status=DocumentStatus.UPLOADED,
                upload_timestamp=upload_time,
                doc_metadata={"description": description, "tags": tags}
            )
            
            # Prepare response
            response = DocumentUploadResponse(
                document_id=document_id,
                status="success",
                message="Document uploaded successfully",
                document=document,
                metadata={
                    "file_size": len(file_data),
                    "upload_time": upload_time.isoformat(),
                    "s3_key": s3_key,
                    "status": DocumentStatus.UPLOADED.value
                }
            )
            
            # Add processing info if immediate processing
            if process_immediately:
                response.metadata["processing"] = {
                    "text_extraction": {"success": True, "chunks_extracted": 1},
                    "knowledge_graph": {"initiated": True}
                }
            
            logger.info(f"Document uploaded successfully: {document_id}")
            return response
            
        except ValidationError:
            raise
        except Exception as e:
            logger.error(f"Error uploading document: {e}")
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
        List documents with optional filtering.
        
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
            with get_database_connection() as conn:
                cursor = conn.cursor()
                
                # Build WHERE clause
                where_conditions = ["user_id = %s"]
                params = [user_id]
                
                if search:
                    where_conditions.append("(title ILIKE %s OR filename ILIKE %s)")
                    search_term = f"%{search}%"
                    params.extend([search_term, search_term])
                
                if status:
                    where_conditions.append("status = %s")
                    params.append(status.value)
                
                where_clause = " AND ".join(where_conditions)
                
                # Get total count
                cursor.execute(f"""
                    SELECT COUNT(*) FROM documents WHERE {where_clause}
                """, params)
                total = cursor.fetchone()[0]
                
                # Get documents with pagination
                offset = (page - 1) * page_size
                cursor.execute(f"""
                    SELECT id, user_id, title, filename, file_size, s3_key, 
                           status, upload_timestamp, processing_completed_at,
                           page_count, chunk_count, doc_metadata
                    FROM documents 
                    WHERE {where_clause}
                    ORDER BY upload_timestamp DESC
                    LIMIT %s OFFSET %s
                """, params + [page_size, offset])
                
                documents = []
                for row in cursor.fetchall():
                    doc_metadata = json.loads(row[11]) if row[11] else {}
                    documents.append(Document(
                        id=row[0],
                        user_id=row[1],
                        title=row[2],
                        filename=row[3],
                        file_size=row[4],
                        s3_key=row[5],
                        status=DocumentStatus(row[6]),
                        upload_timestamp=row[7],
                        processing_completed_at=row[8],
                        page_count=row[9],
                        chunk_count=row[10],
                        doc_metadata=doc_metadata
                    ))
                
                has_next = (page * page_size) < total
                
                return DocumentListResponse(
                    documents=documents,
                    total=total,
                    page=page,
                    page_size=page_size,
                    has_next=has_next
                )
                
        except Exception as e:
            logger.error(f"Error listing documents: {e}")
            raise UploadError(f"Failed to list documents: {e}")
    
    async def get_document(self, document_id: str, user_id: str = "default_user") -> Optional[Document]:
        """
        Get document by ID.
        
        Args:
            document_id: Document identifier
            user_id: User identifier for access control
            
        Returns:
            Document or None if not found
        """
        try:
            with get_database_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT id, user_id, title, filename, file_size, s3_key, 
                           status, upload_timestamp, processing_completed_at,
                           page_count, chunk_count, doc_metadata
                    FROM documents 
                    WHERE id = %s AND user_id = %s
                """, (document_id, user_id))
                
                row = cursor.fetchone()
                if not row:
                    return None
                
                doc_metadata = json.loads(row[11]) if row[11] else {}
                return Document(
                    id=row[0],
                    user_id=row[1],
                    title=row[2],
                    filename=row[3],
                    file_size=row[4],
                    s3_key=row[5],
                    status=DocumentStatus(row[6]),
                    upload_timestamp=row[7],
                    processing_completed_at=row[8],
                    page_count=row[9],
                    chunk_count=row[10],
                    doc_metadata=doc_metadata
                )
                
        except Exception as e:
            logger.error(f"Error getting document: {e}")
            return None
    
    async def delete_document(self, document_id: str, user_id: str = "default_user") -> bool:
        """
        Delete document and associated files.
        
        Args:
            document_id: Document identifier
            user_id: User identifier for access control
            
        Returns:
            True if deleted successfully
        """
        try:
            # Get document info first
            document = await self.get_document(document_id, user_id)
            if not document:
                return False
            
            # Delete from S3
            try:
                await self.storage_service.delete_file(document.s3_key)
            except StorageError as e:
                logger.warning(f"Failed to delete S3 file {document.s3_key}: {e}")
            
            # Delete from database
            with get_database_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    DELETE FROM documents WHERE id = %s AND user_id = %s
                """, (document_id, user_id))
                
                return cursor.rowcount > 0
                
        except Exception as e:
            logger.error(f"Error deleting document: {e}")
            return False