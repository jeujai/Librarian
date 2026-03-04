"""
Processing Status Service - Real-time document processing status tracking and WebSocket notifications.

This service tracks document processing progress and sends WebSocket updates to clients.
It follows the dependency injection pattern for ConnectionManager access.

Requirements: 3.1, 3.2, 3.3, 3.4, 6.1, 6.2, 6.4
"""

import logging
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ProcessingStatus(str, Enum):
    """Processing status values as defined in Requirements 6.2."""
    QUEUED = "queued"
    EXTRACTING = "extracting"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    KG_EXTRACTION = "kg_extraction"
    COMPLETED = "completed"
    FAILED = "failed"


class DocumentProcessingSummary(BaseModel):
    """Summary of completed document processing."""
    title: str
    page_count: int
    chunk_count: int
    concept_count: int
    processing_time_ms: int


class ProcessingStatusMessage(BaseModel):
    """
    WebSocket message for document processing status updates.
    
    Validates: Requirements 6.1, 6.2
    - Contains document_id, status, progress_percentage, current_stage fields
    - Status is one of: queued, extracting, chunking, embedding, kg_extraction, completed, failed
    """
    type: str = Field(default="document_processing_status")
    document_id: str
    filename: str
    status: ProcessingStatus
    progress_percentage: int = Field(ge=0, le=100)
    current_stage: str
    estimated_time_remaining: Optional[int] = None  # seconds
    error_message: Optional[str] = None
    retry_available: Optional[bool] = None
    summary: Optional[DocumentProcessingSummary] = None


class ProcessingStatusTracker(BaseModel):
    """Internal tracking for document processing status."""
    document_id: str
    connection_id: str
    filename: str
    status: ProcessingStatus
    progress_percentage: int
    current_stage: str
    started_at: datetime
    last_updated: datetime
    error_message: Optional[str] = None


class ProcessingStatusService:
    """
    Tracks document processing progress and sends WebSocket updates.
    
    This service is instantiated lazily via dependency injection, not at module import time.
    It uses the ConnectionManager to send WebSocket messages to specific connections.
    
    Requirements: 3.1, 3.2, 3.3, 3.4, 6.1, 6.2, 6.4
    """
    
    def __init__(self):
        """
        Initialize the ProcessingStatusService.
        
        ConnectionManager is injected separately via set_connection_manager(),
        following the DI pattern where services don't call other services in __init__.
        """
        # Mapping of document_id -> ProcessingStatusTracker
        self._tracking: Dict[str, ProcessingStatusTracker] = {}
        
        # ConnectionManager is injected separately, not in __init__
        self._connection_manager = None
        
        # Queue for status updates when connection is lost
        self._pending_updates: Dict[str, list] = {}  # connection_id -> [messages]
        
        logger.info("ProcessingStatusService initialized (lazy, no connections)")
    
    def set_connection_manager(self, connection_manager) -> None:
        """
        Set the ConnectionManager after DI resolution.
        
        This allows the ConnectionManager to be injected after the service
        is created, supporting the DI pattern.
        
        Args:
            connection_manager: WebSocket connection manager for sending updates
        """
        self._connection_manager = connection_manager
        logger.debug("ProcessingStatusService connection manager set")
    
    @property
    def connection_manager(self):
        """Get the connection manager if available."""
        return self._connection_manager
    
    async def register_upload(
        self,
        document_id: UUID,
        connection_id: str,
        filename: str
    ) -> None:
        """
        Register a document upload for status tracking.
        
        Args:
            document_id: Unique document identifier
            connection_id: WebSocket connection that initiated upload
            filename: Original filename for display
            
        Validates: Requirements 3.1, 6.4
        """
        doc_id_str = str(document_id)
        now = datetime.utcnow()
        
        tracker = ProcessingStatusTracker(
            document_id=doc_id_str,
            connection_id=connection_id,
            filename=filename,
            status=ProcessingStatus.QUEUED,
            progress_percentage=0,
            current_stage="Queued for processing",
            started_at=now,
            last_updated=now
        )
        
        self._tracking[doc_id_str] = tracker
        
        logger.info(f"Registered upload for document {doc_id_str} from connection {connection_id}")
        
        # Send initial status message
        await self._send_status_message(tracker)

    async def update_status(
        self,
        document_id: UUID,
        status: ProcessingStatus,
        progress_percentage: int,
        current_stage: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Update processing status and send WebSocket message.
        
        Args:
            document_id: Document being processed
            status: Current processing status
            progress_percentage: Progress (0-100)
            current_stage: Human-readable stage name
            metadata: Optional additional metadata
            
        Validates: Requirements 3.2, 6.1, 6.2
        """
        doc_id_str = str(document_id)
        
        if doc_id_str not in self._tracking:
            logger.warning(f"No tracking found for document {doc_id_str}, creating new tracker")
            # Create a minimal tracker if one doesn't exist
            self._tracking[doc_id_str] = ProcessingStatusTracker(
                document_id=doc_id_str,
                connection_id="unknown",
                filename="unknown",
                status=status,
                progress_percentage=progress_percentage,
                current_stage=current_stage,
                started_at=datetime.utcnow(),
                last_updated=datetime.utcnow()
            )
        
        tracker = self._tracking[doc_id_str]
        tracker.status = status
        tracker.progress_percentage = progress_percentage
        tracker.current_stage = current_stage
        tracker.last_updated = datetime.utcnow()
        
        logger.debug(f"Updated status for document {doc_id_str}: {status.value} ({progress_percentage}%)")
        
        # Send status message
        await self._send_status_message(tracker, metadata)
    
    async def notify_completion(
        self,
        document_id: UUID,
        summary: DocumentProcessingSummary
    ) -> None:
        """
        Notify that processing completed successfully.
        
        Args:
            document_id: Completed document
            summary: Processing summary with chunk count, etc.
            
        Validates: Requirements 3.3
        """
        doc_id_str = str(document_id)
        
        if doc_id_str not in self._tracking:
            logger.warning(f"No tracking found for completed document {doc_id_str}")
            return
        
        tracker = self._tracking[doc_id_str]
        tracker.status = ProcessingStatus.COMPLETED
        tracker.progress_percentage = 100
        tracker.current_stage = "Processing complete"
        tracker.last_updated = datetime.utcnow()
        
        logger.info(f"Document {doc_id_str} processing completed: {summary.chunk_count} chunks")
        
        # Send completion message with summary
        await self._send_status_message(tracker, summary=summary)
        
        # Clean up tracking after completion
        del self._tracking[doc_id_str]
    
    async def notify_failure(
        self,
        document_id: UUID,
        error: str,
        retry_available: bool = True
    ) -> None:
        """
        Notify that processing failed.
        
        Args:
            document_id: Failed document
            error: Error message
            retry_available: Whether retry is possible
            
        Validates: Requirements 3.4
        """
        doc_id_str = str(document_id)
        
        if doc_id_str not in self._tracking:
            logger.warning(f"No tracking found for failed document {doc_id_str}")
            return
        
        tracker = self._tracking[doc_id_str]
        tracker.status = ProcessingStatus.FAILED
        tracker.current_stage = "Processing failed"
        tracker.error_message = error
        tracker.last_updated = datetime.utcnow()
        
        logger.error(f"Document {doc_id_str} processing failed: {error}")
        
        # Send failure message
        await self._send_status_message(
            tracker,
            error_message=error,
            retry_available=retry_available
        )
    
    async def _send_status_message(
        self,
        tracker: ProcessingStatusTracker,
        metadata: Optional[Dict[str, Any]] = None,
        summary: Optional[DocumentProcessingSummary] = None,
        error_message: Optional[str] = None,
        retry_available: Optional[bool] = None
    ) -> None:
        """
        Send status message to the originating connection.
        
        Messages are only sent to the connection that initiated the upload,
        as required by Requirement 6.4.
        
        Args:
            tracker: Processing status tracker
            metadata: Optional additional metadata
            summary: Optional completion summary
            error_message: Optional error message
            retry_available: Optional retry availability flag
        """
        if self._connection_manager is None:
            logger.warning("ConnectionManager not set, queueing status message")
            self._queue_pending_update(tracker.connection_id, tracker, summary, error_message, retry_available)
            return
        
        # Calculate estimated time remaining if in progress
        estimated_time = None
        if tracker.status not in [ProcessingStatus.COMPLETED, ProcessingStatus.FAILED, ProcessingStatus.QUEUED]:
            elapsed = (tracker.last_updated - tracker.started_at).total_seconds()
            if tracker.progress_percentage > 0:
                total_estimated = elapsed / (tracker.progress_percentage / 100)
                estimated_time = int(total_estimated - elapsed)
        
        message = ProcessingStatusMessage(
            document_id=tracker.document_id,
            filename=tracker.filename,
            status=tracker.status,
            progress_percentage=tracker.progress_percentage,
            current_stage=tracker.current_stage,
            estimated_time_remaining=estimated_time,
            error_message=error_message or tracker.error_message,
            retry_available=retry_available,
            summary=summary
        )
        
        # Send only to the originating connection (Requirement 6.4)
        try:
            await self._connection_manager.send_personal_message(
                message.model_dump(),
                tracker.connection_id
            )
            logger.debug(f"Sent status message to connection {tracker.connection_id}")
        except Exception as e:
            logger.error(f"Failed to send status message to {tracker.connection_id}: {e}")
            # Queue for later delivery
            self._queue_pending_update(tracker.connection_id, tracker, summary, error_message, retry_available)
    
    def _queue_pending_update(
        self,
        connection_id: str,
        tracker: ProcessingStatusTracker,
        summary: Optional[DocumentProcessingSummary] = None,
        error_message: Optional[str] = None,
        retry_available: Optional[bool] = None
    ) -> None:
        """Queue a status update for later delivery when connection is restored."""
        if connection_id not in self._pending_updates:
            self._pending_updates[connection_id] = []
        
        message = ProcessingStatusMessage(
            document_id=tracker.document_id,
            filename=tracker.filename,
            status=tracker.status,
            progress_percentage=tracker.progress_percentage,
            current_stage=tracker.current_stage,
            error_message=error_message or tracker.error_message,
            retry_available=retry_available,
            summary=summary
        )
        
        self._pending_updates[connection_id].append(message.model_dump())
        logger.debug(f"Queued status update for connection {connection_id}")
    
    async def deliver_pending_updates(self, connection_id: str) -> int:
        """
        Deliver any pending status updates to a reconnected connection.
        
        Args:
            connection_id: The reconnected connection ID
            
        Returns:
            Number of messages delivered
            
        Validates: Requirements 6.5 (reconnection handling)
        """
        if connection_id not in self._pending_updates:
            return 0
        
        if self._connection_manager is None:
            logger.warning("ConnectionManager not set, cannot deliver pending updates")
            return 0
        
        messages = self._pending_updates.pop(connection_id)
        delivered = 0
        
        for message in messages:
            try:
                await self._connection_manager.send_personal_message(message, connection_id)
                delivered += 1
            except Exception as e:
                logger.error(f"Failed to deliver pending message to {connection_id}: {e}")
        
        logger.info(f"Delivered {delivered}/{len(messages)} pending updates to {connection_id}")
        return delivered
    
    def get_tracking_info(self, document_id: UUID) -> Optional[ProcessingStatusTracker]:
        """
        Get current tracking information for a document.
        
        Args:
            document_id: Document to look up
            
        Returns:
            ProcessingStatusTracker or None if not found
        """
        return self._tracking.get(str(document_id))
    
    def get_active_uploads_for_connection(self, connection_id: str) -> list:
        """
        Get all active uploads for a specific connection.
        
        Args:
            connection_id: Connection to look up
            
        Returns:
            List of ProcessingStatusTracker objects
        """
        return [
            tracker for tracker in self._tracking.values()
            if tracker.connection_id == connection_id
        ]
    
    def cleanup_connection(self, connection_id: str) -> None:
        """
        Clean up tracking data for a disconnected connection.
        
        Args:
            connection_id: Connection that disconnected
        """
        # Remove pending updates
        if connection_id in self._pending_updates:
            del self._pending_updates[connection_id]
        
        # Note: We don't remove active tracking entries as processing
        # may still be in progress. The user can reconnect and resume.
        logger.debug(f"Cleaned up pending updates for connection {connection_id}")
