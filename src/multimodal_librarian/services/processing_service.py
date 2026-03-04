"""
Processing service for handling document processing workflows.

This service orchestrates the background processing of uploaded documents,
coordinating PDF processing, chunking, vector storage, and knowledge graph updates.
Now integrated with Celery for robust background job processing.
"""

import logging
from typing import Optional, Dict, Any, List
from uuid import UUID

logger = logging.getLogger(__name__)


class ProcessingError(Exception):
    """Base exception for processing operations."""
    pass


class ProcessingService:
    """
    Service for orchestrating document processing workflows.
    
    Manages the complete pipeline from PDF processing through vector storage
    and knowledge graph integration using Celery for background processing.
    """
    
    def __init__(self, upload_service: Optional = None):
        """
        Initialize processing service.
        
        Args:
            upload_service: Upload service instance
        """
        # Use lazy imports to avoid circular dependencies
        self._upload_service = upload_service
        self._celery_service = None
        
        # Processing statistics
        self.processing_stats = {
            'total_jobs': 0,
            'successful_jobs': 0,
            'failed_jobs': 0,
            'average_processing_time': 0.0,
            'total_documents_processed': 0,
            'total_chunks_created': 0,
            'total_concepts_extracted': 0,
            'total_relationships_extracted': 0
        }
        
        logger.info("Processing service initialized with Celery integration")
    
    @property
    def upload_service(self):
        """Lazy load upload service."""
        if self._upload_service is None:
            from .upload_service import UploadService
            self._upload_service = UploadService()
        return self._upload_service
    
    @property
    def celery_service(self):
        """Lazy load celery service."""
        if self._celery_service is None:
            from .celery_service import CeleryService
            self._celery_service = CeleryService()
        return self._celery_service
    
    async def process_document(self, document_id: UUID) -> Dict[str, Any]:
        """
        Process a document through the complete pipeline using Celery.
        
        Args:
            document_id: Document to process
            
        Returns:
            Dict with job information
            
        Raises:
            ProcessingError: If processing setup fails
        """
        try:
            # Queue document for processing with Celery
            task_id = await self.celery_service.queue_document_processing(document_id)
            
            self.processing_stats['total_jobs'] += 1
            
            logger.info(f"Document {document_id} queued for processing with task {task_id}")
            
            return {
                'document_id': str(document_id),
                'task_id': task_id,
                'status': 'queued',
                'message': 'Document queued for background processing'
            }
            
        except Exception as e:
            logger.error(f"Failed to start processing for document {document_id}: {e}")
            raise ProcessingError(f"Failed to start processing: {e}")
    
    async def get_processing_status(self, document_id: UUID) -> Optional[Dict[str, Any]]:
        """
        Get processing status for a document.
        
        Args:
            document_id: Document identifier
            
        Returns:
            Dict with processing status or None if not found
        """
        return await self.celery_service.get_job_status(document_id)
    
    async def cancel_processing(self, document_id: UUID) -> bool:
        """
        Cancel document processing.
        
        Args:
            document_id: Document identifier
            
        Returns:
            bool: True if cancellation successful
        """
        return await self.celery_service.cancel_job(document_id)
    
    async def get_active_jobs(self) -> List[Dict[str, Any]]:
        """
        Get all active processing jobs.
        
        Returns:
            List of active job information
        """
        return await self.celery_service.get_active_jobs()
    
    async def retry_failed_processing(self, document_id: UUID) -> Dict[str, Any]:
        """
        Retry failed document processing.
        
        Args:
            document_id: Document identifier
            
        Returns:
            Dict with retry job information
        """
        try:
            # Check current status
            current_status = await self.get_processing_status(document_id)
            if not current_status or current_status['status'] != 'failed':
                raise ProcessingError("Document is not in failed state")
            
            # Reset document status
            from ..models.documents import DocumentStatus
            await self.upload_service.update_document_status(
                document_id, DocumentStatus.UPLOADED
            )
            
            # Queue for processing again
            return await self.process_document(document_id)
            
        except Exception as e:
            logger.error(f"Failed to retry processing for document {document_id}: {e}")
            raise ProcessingError(f"Retry failed: {e}")
    
    
    def health_check(self) -> Dict[str, Any]:
        """
        Perform health check on processing service.
        
        Returns:
            Health status information
        """
        try:
            # Check Celery service health
            celery_health = self.celery_service.health_check()
            
            return {
                'status': celery_health.get('status', 'unknown'),
                'celery_service': celery_health,
                'processing_stats': self.processing_stats
            }
            
        except Exception as e:
            return {
                'status': 'unhealthy',
                'error': str(e),
                'processing_stats': self.processing_stats
            }
    
    def get_processing_statistics(self) -> Dict[str, Any]:
        """
        Get processing service statistics.
        
        Returns:
            Dictionary with processing statistics
        """
        stats = self.processing_stats.copy()
        
        # Add Celery service stats
        try:
            celery_health = self.celery_service.health_check()
            stats['celery_stats'] = celery_health.get('processing_stats', {})
        except:
            stats['celery_stats'] = {}
        
        return stats