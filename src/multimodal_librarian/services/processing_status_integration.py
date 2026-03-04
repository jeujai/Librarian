"""
Processing Status Integration Module.

This module provides integration between the document processing pipeline
(Celery tasks) and the ProcessingStatusService for real-time WebSocket updates.

When running inside the FastAPI app process, updates go directly to the
ProcessingStatusService. When running inside a Celery worker (where the
service is unavailable), updates are published to a Redis pub/sub channel
so the app process can pick them up and forward to WebSocket clients.

Requirements: 3.1, 3.2, 3.3, 3.4
"""

import asyncio
import json
import logging
import os
from typing import Any, Dict, Optional
from uuid import UUID

from .processing_status_service import (
    DocumentProcessingSummary,
    ProcessingStatus,
    ProcessingStatusService,
)

logger = logging.getLogger(__name__)

# Redis pub/sub channel for cross-process progress notifications
PROGRESS_CHANNEL = "processing_progress"

# Global reference to the processing status service
# This is set by the application during startup or when needed
_processing_status_service: Optional[ProcessingStatusService] = None

# Lazy-initialized sync Redis client for Celery workers
_redis_client = None


def _get_redis_client():
    """Get or create a sync Redis client for publishing from Celery workers."""
    global _redis_client
    if _redis_client is None:
        import redis
        broker_url = os.environ.get("CELERY_BROKER_URL", "redis://redis:6379/0")
        _redis_client = redis.Redis.from_url(broker_url)
    return _redis_client


def _publish_to_redis(message: dict) -> None:
    """Publish a progress message to Redis pub/sub (sync, for Celery workers)."""
    try:
        client = _get_redis_client()
        client.publish(PROGRESS_CHANNEL, json.dumps(message, default=str))
    except Exception as e:
        logger.error(f"Failed to publish progress to Redis: {e}")


def set_processing_status_service(service: ProcessingStatusService) -> None:
    """
    Set the global ProcessingStatusService instance.
    
    This should be called during application startup or when the service
    is first needed.
    
    Args:
        service: ProcessingStatusService instance
    """
    global _processing_status_service
    _processing_status_service = service
    logger.info("ProcessingStatusService set for integration")


def get_processing_status_service() -> Optional[ProcessingStatusService]:
    """
    Get the global ProcessingStatusService instance.
    
    Returns:
        ProcessingStatusService instance or None if not set
    """
    return _processing_status_service


# Mapping from job status strings to ProcessingStatus enum
STATUS_MAPPING = {
    'queued': ProcessingStatus.QUEUED,
    'running': ProcessingStatus.EXTRACTING,  # Default for running
    'extracting': ProcessingStatus.EXTRACTING,
    'chunking': ProcessingStatus.CHUNKING,
    'embedding': ProcessingStatus.EMBEDDING,
    'kg_extraction': ProcessingStatus.KG_EXTRACTION,
    'completed': ProcessingStatus.COMPLETED,
    'failed': ProcessingStatus.FAILED,
}

# Mapping from current_step strings to ProcessingStatus enum
STEP_TO_STATUS_MAPPING = {
    'Starting document processing': ProcessingStatus.QUEUED,
    'Extracting PDF content': ProcessingStatus.EXTRACTING,
    'Generating chunks': ProcessingStatus.CHUNKING,
    'Storing chunks and embeddings': ProcessingStatus.EMBEDDING,
    'Storing embeddings': ProcessingStatus.EMBEDDING,
    'Cleaning up existing chunks': ProcessingStatus.EMBEDDING,
    'Generating bridges': ProcessingStatus.CHUNKING,
    'Updating knowledge graph': ProcessingStatus.KG_EXTRACTION,
    'Processing completed successfully': ProcessingStatus.COMPLETED,
    'Processing failed': ProcessingStatus.FAILED,
}


async def notify_processing_status_update(
    document_id: UUID,
    status: str,
    progress_percentage: float,
    current_step: str,
    error_message: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> None:
    """
    Send a processing status update via WebSocket.
    
    When called from the FastAPI app process, sends directly via
    ProcessingStatusService. When called from a Celery worker (service
    is None), publishes to Redis pub/sub for the app to pick up.
    
    Args:
        document_id: Document being processed
        status: Current status string (queued, running, completed, failed)
        progress_percentage: Progress (0-100)
        current_step: Human-readable step description
        error_message: Optional error message for failures
        metadata: Optional additional metadata
        
    Requirements: 3.2, 6.1, 6.2
    """
    service = get_processing_status_service()
    if service is None:
        # Running in Celery worker — publish to Redis for the app process
        _publish_to_redis({
            'type': 'status_update',
            'document_id': str(document_id),
            'status': status,
            'progress_percentage': progress_percentage,
            'current_step': current_step,
            'error_message': error_message,
            'metadata': metadata,
        })
        return
    
    try:
        # Map status string to ProcessingStatus enum
        processing_status = _map_status(status, current_step)
        
        # Send status update
        await service.update_status(
            document_id=document_id,
            status=processing_status,
            progress_percentage=int(progress_percentage),
            current_stage=current_step,
            metadata=metadata
        )
        
        logger.debug(f"Sent processing status update for {document_id}: {processing_status.value} ({progress_percentage}%)")
        
    except Exception as e:
        logger.error(f"Failed to send processing status update for {document_id}: {e}")


async def notify_processing_completion(
    document_id: UUID,
    title: str,
    page_count: int,
    chunk_count: int,
    concept_count: int,
    processing_time_ms: int
) -> None:
    """
    Send a processing completion notification via WebSocket.
    
    Args:
        document_id: Completed document
        title: Document title
        page_count: Number of pages processed
        chunk_count: Number of chunks created
        concept_count: Number of concepts extracted
        processing_time_ms: Total processing time in milliseconds
        
    Requirements: 3.3
    """
    service = get_processing_status_service()
    if service is None:
        _publish_to_redis({
            'type': 'completion',
            'document_id': str(document_id),
            'title': title,
            'page_count': page_count,
            'chunk_count': chunk_count,
            'concept_count': concept_count,
            'processing_time_ms': processing_time_ms,
        })
        return
    
    try:
        summary = DocumentProcessingSummary(
            title=title,
            page_count=page_count,
            chunk_count=chunk_count,
            concept_count=concept_count,
            processing_time_ms=processing_time_ms
        )
        
        await service.notify_completion(
            document_id=document_id,
            summary=summary
        )
        
        logger.info(f"Sent processing completion notification for {document_id}")
        
    except Exception as e:
        logger.error(f"Failed to send processing completion notification for {document_id}: {e}")


async def notify_processing_failure(
    document_id: UUID,
    error: str,
    retry_available: bool = True
) -> None:
    """
    Send a processing failure notification via WebSocket.
    
    Args:
        document_id: Failed document
        error: Error message
        retry_available: Whether retry is possible
        
    Requirements: 3.4
    """
    service = get_processing_status_service()
    if service is None:
        _publish_to_redis({
            'type': 'failure',
            'document_id': str(document_id),
            'error': error,
            'retry_available': retry_available,
        })
        return
    
    try:
        await service.notify_failure(
            document_id=document_id,
            error=error,
            retry_available=retry_available
        )
        
        logger.info(f"Sent processing failure notification for {document_id}")
        
    except Exception as e:
        logger.error(f"Failed to send processing failure notification for {document_id}: {e}")


def notify_processing_status_update_sync(
    document_id: UUID,
    status: str,
    progress_percentage: float,
    current_step: str,
    error_message: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> None:
    """
    Synchronous wrapper for notify_processing_status_update.
    
    This is used from Celery tasks which run in a synchronous context.
    
    Args:
        document_id: Document being processed
        status: Current status string
        progress_percentage: Progress (0-100)
        current_step: Human-readable step description
        error_message: Optional error message
        metadata: Optional additional metadata
    """
    try:
        asyncio.run(notify_processing_status_update(
            document_id=document_id,
            status=status,
            progress_percentage=progress_percentage,
            current_step=current_step,
            error_message=error_message,
            metadata=metadata
        ))
    except Exception as e:
        logger.error(f"Failed to send sync processing status update for {document_id}: {e}")


def notify_processing_completion_sync(
    document_id: UUID,
    title: str,
    page_count: int,
    chunk_count: int,
    concept_count: int,
    processing_time_ms: int
) -> None:
    """
    Synchronous wrapper for notify_processing_completion.
    
    This is used from Celery tasks which run in a synchronous context.
    """
    try:
        asyncio.run(notify_processing_completion(
            document_id=document_id,
            title=title,
            page_count=page_count,
            chunk_count=chunk_count,
            concept_count=concept_count,
            processing_time_ms=processing_time_ms
        ))
    except Exception as e:
        logger.error(f"Failed to send sync processing completion for {document_id}: {e}")


def notify_processing_failure_sync(
    document_id: UUID,
    error: str,
    retry_available: bool = True
) -> None:
    """
    Synchronous wrapper for notify_processing_failure.
    
    This is used from Celery tasks which run in a synchronous context.
    """
    try:
        asyncio.run(notify_processing_failure(
            document_id=document_id,
            error=error,
            retry_available=retry_available
        ))
    except Exception as e:
        logger.error(f"Failed to send sync processing failure for {document_id}: {e}")


def _map_status(status: str, current_step: str) -> ProcessingStatus:
    """
    Map status string and current step to ProcessingStatus enum.
    
    Args:
        status: Status string from job
        current_step: Current step description
        
    Returns:
        ProcessingStatus enum value
    """
    # First try to map from current_step (more specific)
    if current_step in STEP_TO_STATUS_MAPPING:
        return STEP_TO_STATUS_MAPPING[current_step]
    
    # Fall back to status mapping
    status_lower = status.lower()
    if status_lower in STATUS_MAPPING:
        return STATUS_MAPPING[status_lower]
    
    # Default to QUEUED for unknown statuses
    logger.warning(f"Unknown status '{status}' with step '{current_step}', defaulting to QUEUED")
    return ProcessingStatus.QUEUED
