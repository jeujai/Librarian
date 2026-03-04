"""
Upload service for handling document upload business logic.

This service coordinates file validation, storage, database operations,
and processing queue management for PDF document uploads.
"""

import hashlib
import logging
from datetime import datetime
from typing import Any, Dict, Optional, Tuple
from uuid import UUID, uuid4

from sqlalchemy import text

from ..database.connection import db_manager
from ..models.documents import (
    Document,
    DocumentListResponse,
    DocumentStatus,
    DocumentUploadRequest,
    DocumentUploadResponse,
)
from .storage_service import StorageError, StorageService

logger = logging.getLogger(__name__)


class UploadError(Exception):
    """Base exception for upload operations."""
    pass


class ValidationError(UploadError):
    """Exception for file validation errors."""
    pass


class DuplicateDocumentError(UploadError):
    """Exception raised when a duplicate document is detected."""
    
    def __init__(self, message: str, existing_document_id: str, existing_title: str):
        super().__init__(message)
        self.existing_document_id = existing_document_id
        self.existing_title = existing_title


class UploadService:
    """
    Service for handling document uploads and management.
    
    Coordinates file validation, storage, database operations,
    and processing queue management.
    """
    
    def __init__(self, storage_service: Optional[StorageService] = None):
        """
        Initialize upload service.
        
        Args:
            storage_service: Storage service instance (creates new if None)
        """
        self.storage_service = storage_service or StorageService()
    
    def _compute_content_hash(self, file_data: bytes) -> str:
        """
        Compute SHA-256 hash of file content for duplicate detection.
        
        Args:
            file_data: File content as bytes
            
        Returns:
            str: 64-character hexadecimal hash string
        """
        return hashlib.sha256(file_data).hexdigest()
    
    async def _check_duplicate(self, content_hash: str) -> Optional[Tuple[str, str]]:
        """
        Check if a document with the same content hash already exists.
        
        Args:
            content_hash: SHA-256 hash of file content
            
        Returns:
            Tuple of (document_id, title) if duplicate exists, None otherwise
        """
        try:
            async with db_manager.get_async_session() as session:
                result = await session.execute(
                    text("""
                        SELECT id, title FROM multimodal_librarian.knowledge_sources 
                        WHERE metadata->>'content_hash' = :content_hash
                        LIMIT 1
                    """),
                    {"content_hash": content_hash}
                )
                row = result.fetchone()
                if row:
                    return (str(row.id), row.title)
                return None
        except Exception as e:
            logger.warning(f"Error checking for duplicate: {e}")
            return None
        
    async def upload_document(self, file_data: bytes, filename: str, 
                            upload_request: DocumentUploadRequest,
                            user_id: str = "default_user",
                            force_upload: bool = False) -> DocumentUploadResponse:
        """
        Upload and process a document.
        
        Args:
            file_data: File content as bytes
            filename: Original filename
            upload_request: Upload request with metadata
            user_id: User identifier
            force_upload: If True, upload even if duplicate exists
            
        Returns:
            DocumentUploadResponse: Upload result with document ID
            
        Raises:
            ValidationError: If file validation fails
            DuplicateDocumentError: If duplicate detected and force_upload is False
            UploadError: If upload process fails
        """
        try:
            # Compute content hash for duplicate detection
            content_hash = self._compute_content_hash(file_data)
            
            # Check for duplicate (unless force_upload is True)
            if not force_upload:
                duplicate = await self._check_duplicate(content_hash)
                if duplicate:
                    existing_id, existing_title = duplicate
                    raise DuplicateDocumentError(
                        f"Document already exists: '{existing_title}'",
                        existing_document_id=existing_id,
                        existing_title=existing_title
                    )
            
            # Generate document ID
            document_id = uuid4()
            
            # Validate file
            is_valid, error_message = self.storage_service.validate_file(file_data, filename)
            if not is_valid:
                raise ValidationError(error_message)
            
            # Upload to S3
            try:
                s3_key = self.storage_service.upload_file(
                    file_data=file_data,
                    document_id=document_id,
                    filename=filename,
                    content_type='application/pdf'
                )
            except StorageError as e:
                raise UploadError(f"Storage upload failed: {e}")
            
            # Create document record in database
            document = Document(
                id=str(document_id),
                user_id=user_id,
                title=upload_request.title or self._extract_title_from_filename(filename),
                description=upload_request.description,
                filename=filename,
                file_size=len(file_data),
                mime_type='application/pdf',
                s3_key=s3_key,
                status=DocumentStatus.UPLOADED,
                upload_timestamp=datetime.utcnow(),
                metadata={}
            )
            
            # Store in database with content hash
            await self._store_document_in_db(document, content_hash=content_hash)
            
            # Queue for processing (placeholder for now)
            await self._queue_for_processing(document_id)
            
            logger.info(f"Document uploaded successfully: {document_id}")
            
            return DocumentUploadResponse(
                document_id=str(document_id),
                title=document.title,
                status=document.status,
                file_size=document.file_size,
                upload_timestamp=document.upload_timestamp
            )
            
        except (ValidationError, UploadError):
            raise
        except Exception as e:
            logger.error(f"Unexpected error during upload: {e}")
            raise UploadError(f"Upload failed: {e}")
    
    async def get_document(self, document_id: UUID) -> Optional[Document]:
        """
        Get document by ID from unified schema.
        
        Args:
            document_id: Document identifier
            
        Returns:
            Document or None if not found
        """
        try:
            async with db_manager.get_async_session() as session:
                result = await session.execute(
                    text("""
                        SELECT id, user_id, title, file_path, file_size, 
                               processing_status, metadata, source_type,
                               created_at, updated_at
                        FROM multimodal_librarian.knowledge_sources 
                        WHERE id = :document_id
                    """),
                    {"document_id": str(document_id)}
                )
                row = result.fetchone()
                
                if not row:
                    return None
                
                # Extract additional fields from metadata
                metadata = row.metadata or {}
                
                # Map processing_status back to DocumentStatus
                status_mapping = {
                    'PENDING': DocumentStatus.UPLOADED,
                    'PROCESSING': DocumentStatus.PROCESSING,
                    'COMPLETED': DocumentStatus.COMPLETED,
                    'FAILED': DocumentStatus.FAILED
                }
                status = status_mapping.get(row.processing_status, DocumentStatus.UPLOADED)
                
                return Document(
                    id=str(row.id),
                    user_id=str(row.user_id),
                    title=row.title,
                    description=metadata.get('description'),
                    filename=row.file_path,
                    file_size=row.file_size,
                    mime_type=metadata.get('mime_type', 'application/pdf'),
                    s3_key=metadata.get('s3_key'),
                    status=status,
                    processing_error=metadata.get('processing_error'),
                    upload_timestamp=row.created_at,
                    processing_started_at=metadata.get('processing_started_at'),
                    processing_completed_at=metadata.get('processing_completed_at'),
                    page_count=metadata.get('page_count'),
                    chunk_count=metadata.get('chunk_count'),
                    metadata={k: v for k, v in metadata.items() 
                             if k not in ('description', 'mime_type', 's3_key', 
                                         'processing_error', 'processing_started_at',
                                         'processing_completed_at', 'page_count', 
                                         'chunk_count', 'content_hash')}
                )
                
        except Exception as e:
            logger.error(f"Error retrieving document {document_id}: {e}")
            return None
    
    async def list_documents(
        self,
        user_id: str = "default_user",
        search: Optional[str] = None,
        status: Optional[DocumentStatus] = None,
        page: int = 1,
        page_size: int = 20
    ) -> DocumentListResponse:
        """
        List documents with filtering and pagination from unified schema.
        
        Args:
            user_id: User identifier for filtering
            search: Search query for title/description
            status: Filter by document status
            page: Page number (1-based)
            page_size: Items per page
            
        Returns:
            DocumentListResponse: Paginated document list
        """
        try:
            async with db_manager.get_async_session() as session:
                # Build WHERE clause
                where_conditions = []
                params: Dict[str, Any] = {}
                
                # Only filter by user_id if it's a valid UUID
                # Skip filtering for placeholder values like "default_user"
                try:
                    import uuid as uuid_module
                    user_uuid = uuid_module.UUID(str(user_id))
                    where_conditions.append("user_id = :user_id")
                    params["user_id"] = str(user_uuid)
                except (ValueError, AttributeError):
                    # Not a valid UUID - don't filter by user_id
                    # This allows listing all documents for default/anonymous users
                    pass
                
                if status:
                    # Map DocumentStatus to processing_status
                    status_mapping = {
                        'uploaded': 'PENDING',
                        'processing': 'PROCESSING',
                        'completed': 'COMPLETED',
                        'failed': 'FAILED'
                    }
                    status_value = status if isinstance(status, str) else status.value
                    processing_status = status_mapping.get(status_value, 'PENDING')
                    where_conditions.append("processing_status = :status::multimodal_librarian.processing_status")
                    params["status"] = processing_status
                
                if search:
                    where_conditions.append(
                        "(title ILIKE :query OR metadata->>'description' ILIKE :query)"
                    )
                    params["query"] = f"%{search}%"
                
                # Build WHERE clause - use "1=1" if no conditions
                where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"
                
                # Get total count
                count_result = await session.execute(
                    text(f"SELECT COUNT(*) FROM multimodal_librarian.knowledge_sources WHERE {where_clause}"),
                    params
                )
                total_count = count_result.scalar() or 0
                
                # Get paginated results
                offset = (page - 1) * page_size
                params["limit"] = page_size
                params["offset"] = offset
                
                results = await session.execute(
                    text(f"""
                        SELECT id, user_id, title, file_path, file_size, 
                               processing_status, metadata, source_type,
                               created_at, updated_at
                        FROM multimodal_librarian.knowledge_sources 
                        WHERE {where_clause}
                        ORDER BY created_at DESC
                        LIMIT :limit OFFSET :offset
                    """),
                    params
                )
                
                # Map processing_status back to DocumentStatus
                status_reverse_mapping = {
                    'PENDING': DocumentStatus.UPLOADED,
                    'PROCESSING': DocumentStatus.PROCESSING,
                    'COMPLETED': DocumentStatus.COMPLETED,
                    'FAILED': DocumentStatus.FAILED
                }
                
                # Convert to Document objects
                documents = []
                for row in results.fetchall():
                    metadata = row.metadata or {}
                    doc_status = status_reverse_mapping.get(
                        row.processing_status, DocumentStatus.UPLOADED
                    )
                    
                    document = Document(
                        id=str(row.id),
                        user_id=str(row.user_id),
                        title=row.title,
                        description=metadata.get('description'),
                        filename=row.file_path,
                        file_size=row.file_size,
                        mime_type=metadata.get('mime_type', 'application/pdf'),
                        s3_key=metadata.get('s3_key'),
                        status=doc_status,
                        processing_error=metadata.get('processing_error'),
                        upload_timestamp=row.created_at,
                        processing_started_at=metadata.get('processing_started_at'),
                        processing_completed_at=metadata.get('processing_completed_at'),
                        page_count=metadata.get('page_count'),
                        chunk_count=metadata.get('chunk_count'),
                        metadata={k: v for k, v in metadata.items() 
                                 if k not in ('description', 'mime_type', 's3_key', 
                                             'processing_error', 'processing_started_at',
                                             'processing_completed_at', 'page_count', 
                                             'chunk_count', 'content_hash')}
                    )
                    documents.append(document)
                
                has_next = offset + page_size < total_count
                
                return DocumentListResponse(
                    documents=documents,
                    total_count=total_count,
                    page=page,
                    page_size=page_size,
                    has_next=has_next
                )
                
        except Exception as e:
            logger.error(f"Error listing documents: {e}")
            raise UploadError(f"Failed to list documents: {e}")
    
    async def delete_document(self, document_id: UUID) -> bool:
        """
        Delete document and associated files from unified schema.
        
        Deletes from multimodal_librarian.knowledge_sources which cascades
        to delete associated knowledge_chunks.
        
        Args:
            document_id: Document identifier
            
        Returns:
            bool: True if deletion successful
            
        Raises:
            UploadError: If deletion fails
        """
        try:
            document = await self.get_document(document_id)
            if not document:
                return False
            
            # Delete from storage
            if document.s3_key:
                try:
                    self.storage_service.delete_file(document.s3_key)
                except StorageError as e:
                    logger.warning(f"Failed to delete storage file {document.s3_key}: {e}")
                    # Continue with database deletion even if storage deletion fails
            
            # Delete from unified schema (cascades to knowledge_chunks)
            async with db_manager.get_async_session() as session:
                await session.execute(
                    text("DELETE FROM multimodal_librarian.knowledge_sources WHERE id = :document_id"),
                    {"document_id": str(document_id)}
                )
            
            logger.info(f"Document deleted successfully: {document_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting document {document_id}: {e}")
            raise UploadError(f"Deletion failed: {e}")
    
    async def get_document_content(self, document_id: UUID) -> Optional[bytes]:
        """
        Get document file content.
        
        Args:
            document_id: Document identifier
            
        Returns:
            bytes: File content or None if not found
            
        Raises:
            UploadError: If content retrieval fails
        """
        try:
            document = await self.get_document(document_id)
            if not document:
                return None
            
            return self.storage_service.download_file(document.s3_key)
            
        except StorageError as e:
            raise UploadError(f"Failed to retrieve document content: {e}")
        except Exception as e:
            logger.error(f"Error retrieving document content {document_id}: {e}")
            raise UploadError(f"Content retrieval failed: {e}")
    
    async def update_document_status(
        self,
        document_id: UUID,
        status: DocumentStatus, 
        error_message: Optional[str] = None
    ) -> bool:
        """
        Update document processing status in unified schema.
        
        Args:
            document_id: Document identifier
            status: New status
            error_message: Error message if status is FAILED
            
        Returns:
            bool: True if update successful
        """
        try:
            # Map DocumentStatus to processing_status enum
            status_mapping = {
                'uploaded': 'PENDING',
                'processing': 'PROCESSING',
                'completed': 'COMPLETED',
                'failed': 'FAILED'
            }
            status_value = status if isinstance(status, str) else status.value
            processing_status = status_mapping.get(status_value, 'PENDING')
            
            async with db_manager.get_async_session() as session:
                # First get current metadata to update it
                result = await session.execute(
                    text("""
                        SELECT metadata FROM multimodal_librarian.knowledge_sources 
                        WHERE id = :document_id
                    """),
                    {"document_id": str(document_id)}
                )
                row = result.fetchone()
                if not row:
                    return False
                
                import json
                from datetime import datetime
                
                metadata = row.metadata or {}
                
                # Update metadata with processing info
                if error_message:
                    metadata['processing_error'] = error_message
                
                if status == DocumentStatus.PROCESSING:
                    metadata['processing_started_at'] = datetime.utcnow().isoformat()
                elif status in [DocumentStatus.COMPLETED, DocumentStatus.FAILED]:
                    metadata['processing_completed_at'] = datetime.utcnow().isoformat()
                
                metadata_json = json.dumps(metadata)
                
                # Update the record
                update_result = await session.execute(
                    text("""
                        UPDATE multimodal_librarian.knowledge_sources 
                        SET processing_status = :status::multimodal_librarian.processing_status,
                            metadata = :metadata::jsonb,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = :document_id
                    """),
                    {
                        "document_id": str(document_id),
                        "status": processing_status,
                        "metadata": metadata_json
                    }
                )
                
                success = update_result.rowcount > 0
                
                if success:
                    logger.info(f"Document status updated: {document_id} -> {status}")
                
                return success
                
        except Exception as e:
            logger.error(f"Error updating document status {document_id}: {e}")
            return False
    
    async def _store_document_in_db(self, document: Document, content_hash: Optional[str] = None) -> None:
        """
        Store document record in unified schema (multimodal_librarian.knowledge_sources).
        
        Args:
            document: Document to store
            content_hash: SHA-256 hash of file content for duplicate detection
            
        Note:
            - Inserts into multimodal_librarian.knowledge_sources instead of public.documents
            - Sets source_type to 'UPLOAD' for uploaded documents
            - Maps fields according to unified schema structure
        """
        import json
        
        try:
            # Build metadata with content_hash included for duplicate detection
            metadata = document.metadata.copy() if document.metadata else {}
            if content_hash:
                metadata['content_hash'] = content_hash
            # Store additional document fields in metadata
            if document.description:
                metadata['description'] = document.description
            if document.mime_type:
                metadata['mime_type'] = document.mime_type
            if document.s3_key:
                metadata['s3_key'] = document.s3_key
            
            metadata_json = json.dumps(metadata)
            
            # Map document status to processing_status enum
            status_mapping = {
                'uploaded': 'PENDING',
                'processing': 'PROCESSING',
                'completed': 'COMPLETED',
                'failed': 'FAILED'
            }
            status_value = document.status if isinstance(document.status, str) else document.status.value
            processing_status = status_mapping.get(status_value, 'PENDING')
            
            # Use raw asyncpg connection for proper enum casting
            import uuid as uuid_module

            from ..database.connection import get_async_connection
            
            conn = await get_async_connection()
            try:
                # Resolve user_id to UUID - handle string user_ids like 'default_user'
                user_id = document.user_id
                try:
                    # Try to parse as UUID first
                    user_uuid = uuid_module.UUID(str(user_id))
                except (ValueError, AttributeError):
                    # Not a valid UUID, look up or create a default user
                    user_uuid = await self._get_or_create_default_user(conn)
                
                await conn.execute("""
                    INSERT INTO multimodal_librarian.knowledge_sources (
                        id, user_id, title, file_path, file_size,
                        processing_status, metadata, source_type, 
                        created_at, updated_at
                    ) VALUES (
                        $1::uuid, $2::uuid, $3, $4, $5,
                        $6::multimodal_librarian.processing_status, $7::jsonb, 
                        'UPLOAD'::multimodal_librarian.source_type, $8, $9
                    )
                """, 
                    document.id,
                    user_uuid,
                    document.title,
                    document.filename,
                    document.file_size,
                    processing_status,
                    metadata_json,
                    document.upload_timestamp,
                    document.upload_timestamp
                )
            finally:
                await conn.close()
                
        except Exception as e:
            logger.error(f"Error storing document in database: {e}")
            raise UploadError(f"Database storage failed: {e}")
    
    async def _get_or_create_default_user(self, conn) -> UUID:
        """
        Get or create a default user for document uploads.
        
        When user_id is a string like 'default_user' instead of a UUID,
        we need to resolve it to an actual user UUID from the users table.
        
        Args:
            conn: Database connection
            
        Returns:
            UUID of the default/admin user
        """
        # First, try to find an existing admin user
        result = await conn.fetchrow("""
            SELECT id FROM multimodal_librarian.users 
            WHERE username = 'admin' OR email LIKE '%admin%'
            LIMIT 1
        """)
        
        if result:
            return UUID(str(result['id']))
        
        # If no admin user, get any existing user
        result = await conn.fetchrow("""
            SELECT id FROM multimodal_librarian.users LIMIT 1
        """)
        
        if result:
            return UUID(str(result['id']))
        
        # No users exist - create a default upload user
        default_user_id = uuid4()
        await conn.execute("""
            INSERT INTO multimodal_librarian.users (id, username, email, password_hash)
            VALUES ($1, 'upload_user', 'upload@multimodal-librarian.local', 'not_for_login')
            ON CONFLICT (username) DO NOTHING
        """, default_user_id)
        
        # Fetch the user (in case of conflict, get the existing one)
        result = await conn.fetchrow("""
            SELECT id FROM multimodal_librarian.users WHERE username = 'upload_user'
        """)
        
        return UUID(str(result['id'])) if result else default_user_id
    
    def _extract_title_from_filename(self, filename: str) -> str:
        """
        Extract a readable title from filename.
        
        Args:
            filename: Original filename
            
        Returns:
            str: Extracted title
        """
        # Remove extension and replace underscores/hyphens with spaces
        title = filename.rsplit('.', 1)[0]
        title = title.replace('_', ' ').replace('-', ' ')
        
        # Capitalize words
        title = ' '.join(word.capitalize() for word in title.split())
        
        return title or "Untitled Document"
    
    async def _queue_for_processing(self, document_id: UUID):
        """
        Queue document for background processing using Celery.
        
        Args:
            document_id: Document identifier
        """
        try:
            # Import here to avoid circular imports
            from .processing_service import ProcessingService
            
            processing_service = ProcessingService(self)
            result = await processing_service.process_document(document_id)
            
            logger.info(f"Document queued for processing: {document_id} -> {result['task_id']}")
            
        except Exception as e:
            logger.error(f"Failed to queue document for processing: {e}")
            # Update document status to failed
            await self.update_document_status(
                document_id, DocumentStatus.FAILED, f"Failed to queue for processing: {e}"
            )
    
    async def get_upload_statistics(self) -> Dict[str, Any]:
        """
        Get upload statistics and metrics from unified schema.
        
        Returns:
            Dict[str, Any]: Statistics information
        """
        try:
            async with db_manager.get_async_session() as session:
                # Get status counts from unified schema
                status_results = await session.execute(
                    text("""
                        SELECT processing_status, COUNT(*) as count
                        FROM multimodal_librarian.knowledge_sources
                        WHERE source_type = 'UPLOAD'
                        GROUP BY processing_status
                    """)
                )
                
                # Map processing_status back to document status for compatibility
                status_reverse_mapping = {
                    'PENDING': 'uploaded',
                    'PROCESSING': 'processing',
                    'COMPLETED': 'completed',
                    'FAILED': 'failed'
                }
                
                status_counts = {
                    status_reverse_mapping.get(row.processing_status, row.processing_status): row.count 
                    for row in status_results.fetchall()
                }
                
                # Get total documents and size
                totals = await session.execute(
                    text("""
                        SELECT COUNT(*) as total_documents, 
                               COALESCE(SUM(file_size), 0) as total_size
                        FROM multimodal_librarian.knowledge_sources
                        WHERE source_type = 'UPLOAD'
                    """)
                )
                totals_row = totals.fetchone()
                
                total_docs = totals_row.total_documents if totals_row else 0
                total_size = totals_row.total_size if totals_row else 0
                
                return {
                    'total_documents': total_docs,
                    'status_counts': status_counts,
                    'total_size_bytes': total_size,
                    'total_size_mb': round(total_size / (1024 * 1024), 2),
                    'storage_service_status': self.storage_service.health_check()
                }
                
        except Exception as e:
            logger.error(f"Error getting upload statistics: {e}")
            return {
                'total_documents': 0,
                'status_counts': {},
                'total_size_bytes': 0,
                'total_size_mb': 0,
                'storage_service_status': {'status': 'error', 'error': str(e)}
            }
