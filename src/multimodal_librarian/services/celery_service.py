"""
Celery service for background document processing.

This service provides Celery-based job queue functionality for processing
documents asynchronously with Redis as the message broker.
"""

import asyncio
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

import redis
from celery import Celery
from celery.result import AsyncResult
from celery.signals import (
    task_failure,
    task_postrun,
    task_prerun,
    worker_ready,
    worker_shutdown,
)

from .redis_task_lock import redis_task_lock

logger = logging.getLogger(__name__)

# Celery configuration - use environment variables for Docker compatibility
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://redis:6379/0")
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "redis://redis:6379/0")

# Task time limits (seconds).  Every pipeline task shares these.
# Change here to adjust all tasks + progress-key TTLs in one place.
TASK_HARD_TIME_LIMIT = 501 * 60 * 60   # 501 hours
TASK_SOFT_TIME_LIMIT = 500 * 60 * 60   # 500 hours
PROGRESS_KEY_TTL = TASK_HARD_TIME_LIMIT  # progress keys live as long as the task can

# --- Shared parallel-progress helpers (bridges + KG) ---
# Each parallel task writes its own fraction (0.0–1.0) to Redis.
# The progress reporter reads both and computes: 30 + avg(bridge, kg) * 60
_progress_redis = None

def _get_progress_redis():
    global _progress_redis
    if _progress_redis is None:
        _progress_redis = redis.Redis.from_url(CELERY_BROKER_URL, decode_responses=True)
    return _progress_redis

def _set_parallel_progress(document_id: str, task_name: str, fraction: float):
    """Write this task's fraction (0.0–1.0) and return averaged overall %.

    Monotonic: the stored fraction never decreases.  This prevents the
    progress bar from jumping backwards when a duplicate task delivery
    (acks_late + broker hiccup) restarts from zero.
    """
    r = _get_progress_redis()
    key = f"docprog:{document_id}:{task_name}"
    new_val = min(fraction, 1.0)
    # Only increase — never decrease
    old_raw = r.get(key)
    if old_raw is not None:
        old_val = float(old_raw)
        if new_val < old_val:
            new_val = old_val
    r.set(key, str(new_val), ex=PROGRESS_KEY_TTL)
    # Read both fractions
    bridge_val = r.get(f"docprog:{document_id}:bridges")
    kg_val = r.get(f"docprog:{document_id}:kg")
    b = float(bridge_val) if bridge_val else 0.0
    k = float(kg_val) if kg_val else 0.0
    avg = (b + k) / 2.0
    return int(30 + avg * 60)  # 30–90%


def _get_parallel_step_label(document_id: str) -> str:
    """Return a progress label reflecting which parallel tasks are still running."""
    r = _get_progress_redis()
    bridge_val = r.get(f"docprog:{document_id}:bridges")
    kg_val = r.get(f"docprog:{document_id}:kg")
    b = float(bridge_val) if bridge_val else 0.0
    k = float(kg_val) if kg_val else 0.0
    bridges_done = b >= 1.0
    kg_done = k >= 1.0
    if bridges_done and not kg_done:
        return 'Updating knowledge graph'
    if kg_done and not bridges_done:
        return 'Generating bridges'
    if not bridges_done and not kg_done:
        return 'Generating bridges & knowledge graph'
    return 'Finalizing'


def _get_parallel_substage_pcts(document_id: str) -> Optional[str]:
    """Return a formatted substage breakdown string, or None if not in parallel phase."""
    r = _get_progress_redis()
    bridge_val = r.get(f"docprog:{document_id}:bridges")
    kg_val = r.get(f"docprog:{document_id}:kg")
    if bridge_val is None and kg_val is None:
        return None
    b = float(bridge_val) if bridge_val else 0.0
    k = float(kg_val) if kg_val else 0.0
    if b >= 1.0 and k >= 1.0:
        return None
    b_pct = min(int(b * 100), 100)
    k_pct = min(int(k * 100), 100)
    parts = []
    if b < 1.0:
        parts.append(f"Bridges: {b_pct}%")
    if k < 1.0:
        parts.append(f"KG: {k_pct}%")
    return "  ·  ".join(parts)

def _cleanup_parallel_progress(document_id: str):
    """Remove Redis keys after finalization."""
    r = _get_progress_redis()
    r.delete(f"docprog:{document_id}:bridges", f"docprog:{document_id}:kg")


class DocumentDeletedError(Exception):
    """Raised when a pipeline task detects the document has been deleted."""
    pass


class CancellationError(Exception):
    """Raised when a Celery task revocation fails (broker unreachable, timeout, etc.)."""
    pass


async def _is_document_deleted(document_id: str) -> bool:
    """Check if a document has been deleted from PostgreSQL.

    Returns True if the knowledge_sources row no longer exists, meaning
    the user deleted the document while processing was in progress.
    """
    try:
        from ..database.connection import get_async_connection

        conn = await get_async_connection()
        try:
            row = await conn.fetchrow(
                "SELECT 1 FROM multimodal_librarian.knowledge_sources WHERE id = $1",
                document_id,
            )
            return row is None
        finally:
            await conn.close()
    except Exception as e:
        logger.warning(f"Could not check document existence for {document_id}: {e}")
        return False  # Assume not deleted on error to avoid false aborts


def _check_document_deleted(document_id: str, stage: str = ""):
    """Synchronous wrapper for Celery tasks — raises DocumentDeletedError."""
    deleted = asyncio.run(_is_document_deleted(document_id))
    if deleted:
        msg = f"Document {document_id} was deleted during processing"
        if stage:
            msg += f" (detected at {stage})"
        logger.warning(msg)
        raise DocumentDeletedError(msg)

# Create Celery app
celery_app = Celery(
    'document_processing',
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
    include=['src.multimodal_librarian.services.celery_service']
)

# Celery configuration
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=60 * 60,  # 60 minutes
    task_soft_time_limit=55 * 60,  # 55 minutes
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    worker_disable_rate_limits=False,
    task_default_retry_delay=60,  # 1 minute
    task_max_retries=3,
    task_routes={
        'process_document_task': {'queue': 'document_processing'},
        'extract_pdf_content_task': {'queue': 'pdf_processing'},
        'generate_chunks_task': {'queue': 'chunking'},
        'generate_bridges_task': {'queue': 'chunking'},
        'update_knowledge_graph_task': {'queue': 'knowledge_graph'},
        'finalize_processing_task': {'queue': 'document_processing'},
        'enrich_concepts_task': {'queue': 'enrichment'}
    }
)


def _get_valid_document_title(title: Optional[str], filename: Optional[str]) -> str:
    """
    Get a valid document title, falling back to filename or default if needed.
    
    This helper validates the title and provides fallbacks to ensure chunks
    always have a valid, non-empty title in their metadata.
    
    Bug Condition: isBugCondition(document_row) where title IS NULL OR 
    title = '' OR title.strip() = ''
    
    Expected Behavior: Return valid non-empty title string, preferring:
    1. User-provided title (if valid non-empty string)
    2. Filename without extension (if title is invalid)
    3. "Untitled Document" (if both title and filename are invalid)
    
    Preservation: Valid non-empty titles are returned unchanged.
    
    Args:
        title: The title value from the database row (may be None, empty, or whitespace)
        filename: The filename from the database row (used as fallback)
        
    Returns:
        A valid non-empty title string
        
    Requirements: 2.1, 2.2, 2.3, 3.1
    """
    # Check if title is valid (non-None, non-empty, non-whitespace)
    if title is not None and title.strip():
        return title
    
    # Title is invalid - log and fall back to filename
    if title is None:
        logger.debug(f"Document title is None, falling back to filename: {filename}")
    elif title == '':
        logger.debug(f"Document title is empty string, falling back to filename: {filename}")
    else:
        logger.debug(f"Document title is whitespace-only ('{repr(title)}'), falling back to filename: {filename}")
    
    # Try to derive title from filename
    if filename and filename.strip():
        # Remove extension - handle multiple dots by splitting on last dot
        name = filename.rsplit('.', 1)[0] if '.' in filename else filename
        name = name.strip()
        
        if name:
            logger.info(f"Using filename-derived title: '{name}' (original filename: '{filename}')")
            return name
    
    # Both title and filename are invalid - use default
    logger.warning(
        f"Both title ('{repr(title)}') and filename ('{repr(filename)}') are invalid, "
        f"using default 'Untitled Document'"
    )
    return "Untitled Document"


class CeleryService:
    """
    Service for managing Celery-based background processing.
    
    Provides job queue functionality with Redis as message broker
    and comprehensive status tracking.
    """
    
    def __init__(self):
        """Initialize Celery service."""

        self.redis_client = redis.Redis.from_url(CELERY_BROKER_URL)
        
        # Processing statistics
        self.processing_stats = {
            'total_jobs_queued': 0,
            'successful_jobs': 0,
            'failed_jobs': 0,
            'active_jobs': 0,
            'average_processing_time': 0.0
        }
        
        logger.info("Celery service initialized")
    
    async def queue_document_processing(self, document_id: UUID) -> str:
        """
        Queue document for background processing.
        
        Args:
            document_id: Document to process
            
        Returns:
            str: Celery task ID
        """
        try:
            # Create processing job record
            await self._create_processing_job(document_id)
            
            # Queue Celery task
            task = process_document_task.delay(str(document_id))
            
            # Update job with task ID
            await self._update_job_task_id(document_id, task.id)
            
            self.processing_stats['total_jobs_queued'] += 1
            self.processing_stats['active_jobs'] += 1
            
            logger.info(f"Document {document_id} queued for processing with task ID {task.id}")
            return task.id
            
        except Exception as e:
            logger.error(f"Failed to queue document processing: {e}")
            raise
    
    async def get_job_status(self, document_id: UUID) -> Optional[Dict[str, Any]]:
        """
        Get processing job status.
        
        Args:
            document_id: Document identifier
            
        Returns:
            Dict with job status information
        """
        try:
            # Import here to avoid circular imports
            from sqlalchemy import text

            from ..database.connection import db_manager

            # Ensure database is initialized
            if not db_manager.AsyncSessionLocal:
                db_manager.initialize()
            
            async with db_manager.get_async_session() as session:
                result = await session.execute(
                    text("""
                        SELECT pj.id, pj.source_id, pj.status, pj.progress_percentage, pj.current_step,
                               pj.error_message, pj.started_at, pj.completed_at, pj.retry_count,
                               pj.job_metadata, pj.task_id
                        FROM multimodal_librarian.processing_jobs pj
                        WHERE pj.source_id = :source_id
                        ORDER BY pj.started_at DESC
                        LIMIT 1
                    """),
                    {"source_id": str(document_id)}
                )
                row = result.fetchone()
                
                if not row:
                    return None
                
                job_status = {
                    'job_id': str(row.id),
                    'document_id': str(row.source_id),
                    'status': row.status,
                    'progress_percentage': row.progress_percentage,
                    'current_step': row.current_step,
                    'error_message': row.error_message,
                    'started_at': row.started_at.isoformat() if row.started_at else None,
                    'completed_at': row.completed_at.isoformat() if row.completed_at else None,
                    'retry_count': row.retry_count,
                    'metadata': row.job_metadata or {},
                    'task_id': row.task_id
                }
                
                # Get Celery task status if available
                if row.task_id:
                    celery_result = AsyncResult(row.task_id, app=celery_app)
                    job_status['celery_status'] = celery_result.status
                    job_status['celery_info'] = celery_result.info
                
                return job_status
                
        except Exception as e:
            logger.error(f"Error getting job status: {e}")
            return None
    
    async def cancel_job(self, document_id: UUID) -> bool:
        """
        Cancel a processing job.

        Handles NULL task_id (race window) by polling, propagates
        revocation errors as CancellationError, and verifies post-revoke
        task state via AsyncResult.status polling.

        Args:
            document_id: Document identifier

        Returns:
            bool: True if job was cancelled or fallback is in effect

        Raises:
            CancellationError: If revoke() fails (broker unreachable, etc.)
        """
        job_status = await self.get_job_status(document_id)
        if not job_status:
            return False

        task_id = job_status.get('task_id')
        status = job_status.get('status')

        # --- 3.1: Handle NULL task_id with polling for active jobs ---
        if not task_id and status in ('pending', 'running'):
            for attempt in range(3):
                time.sleep(1)
                job_status = await self.get_job_status(document_id)
                if not job_status:
                    return False
                task_id = job_status.get('task_id')
                if task_id:
                    logger.info(
                        f"task_id appeared after {attempt + 1} poll(s) "
                        f"for document {document_id}"
                    )
                    break

            if not task_id:
                logger.warning(
                    f"task_id still NULL after 3 polls for document "
                    f"{document_id} (status={status}). Relying on "
                    f"_check_document_deleted() fallback."
                )
                # Mark job as failed so it doesn't linger
                await self._update_job_status(
                    document_id, 'failed', 0,
                    'Cancelled by user',
                    'Job cancelled — task_id unavailable, '
                    'fallback to _check_document_deleted()'
                )
                from ..models.documents import DocumentStatus
                from .upload_service import UploadService
                upload_service = UploadService()
                await upload_service.update_document_status(
                    document_id, DocumentStatus.FAILED,
                    "Processing cancelled by user"
                )
                self.processing_stats['active_jobs'] = max(
                    0, self.processing_stats['active_jobs'] - 1
                )
                self.processing_stats['failed_jobs'] += 1
                return True

        # --- 3.2: Revoke with error propagation ---
        if task_id:
            try:
                celery_app.control.revoke(
                    task_id, terminate=True
                )
            except Exception as e:
                logger.error(
                    f"Failed to revoke task {task_id} for document "
                    f"{document_id}: {e}"
                )
                raise CancellationError(
                    f"Failed to revoke task {task_id}: {e}"
                ) from e

            # --- 3.3: Post-revoke verification ---
            terminal_states = {'REVOKED', 'FAILURE', 'SUCCESS'}
            task_stopped = False
            for _ in range(5):
                result = AsyncResult(task_id, app=celery_app)
                if result.status in terminal_states:
                    task_stopped = True
                    logger.info(
                        f"Task {task_id} reached terminal state "
                        f"'{result.status}' for document {document_id}"
                    )
                    break
                time.sleep(1)

            if not task_stopped:
                logger.warning(
                    f"Task {task_id} still in non-terminal state after "
                    f"revoke for document {document_id}. Relying on "
                    f"_check_document_deleted() fallback."
                )

        # Update job status in database
        await self._update_job_status(
            document_id, 'failed', 0,
            'Cancelled by user', 'Job cancelled by user'
        )

        # Update document status
        from ..models.documents import DocumentStatus
        from .upload_service import UploadService

        upload_service = UploadService()
        await upload_service.update_document_status(
            document_id, DocumentStatus.FAILED,
            "Processing cancelled by user"
        )

        self.processing_stats['active_jobs'] = max(
            0, self.processing_stats['active_jobs'] - 1
        )
        self.processing_stats['failed_jobs'] += 1

        logger.info(
            f"Processing job cancelled for document {document_id}"
        )
        return True
    
    async def get_active_jobs(self) -> List[Dict[str, Any]]:
        """
        Get all active processing jobs.
        
        Returns:
            List of active job information
        """
        try:
            from sqlalchemy import text

            from ..database.connection import db_manager

            # Ensure database is initialized
            if not db_manager.AsyncSessionLocal:
                db_manager.initialize()
            
            async with db_manager.get_async_session() as session:
                result = await session.execute(
                    text("""
                        SELECT pj.id, pj.source_id, pj.status, pj.progress_percentage, pj.current_step,
                               pj.started_at, pj.retry_count, pj.task_id
                        FROM multimodal_librarian.processing_jobs pj
                        WHERE pj.status IN ('pending', 'running')
                        ORDER BY pj.started_at DESC
                    """)
                )
                rows = result.fetchall()
                
                active_jobs = []
                for row in rows:
                    job_info = {
                        'job_id': str(row.id),
                        'document_id': str(row.source_id),
                        'status': row.status,
                        'progress_percentage': row.progress_percentage,
                        'current_step': row.current_step,
                        'started_at': row.started_at.isoformat() if row.started_at else None,
                        'retry_count': row.retry_count,
                        'task_id': row.task_id
                    }
                    
                    # Add Celery status
                    if row.task_id:
                        celery_result = AsyncResult(row.task_id, app=celery_app)
                        job_info['celery_status'] = celery_result.status
                    
                    active_jobs.append(job_info)
                
                return active_jobs
                
        except Exception as e:
            logger.error(f"Error getting active jobs: {e}")
            return []
    
    async def get_failed_stage(self, document_id: UUID) -> Optional[str]:
        """
        Get the failed stage for a document from job_metadata.
        
        This is used to determine where to restart processing during retry.
        
        Args:
            document_id: Document identifier
            
        Returns:
            Stage name where processing failed, or None if not found
            
        Requirements: 8.4 - Track failed stage in processing metadata
        """
        try:
            job_status = await self.get_job_status(document_id)
            if not job_status:
                return None
            
            metadata = job_status.get('metadata', {})
            return metadata.get('failed_stage')
            
        except Exception as e:
            logger.error(f"Error getting failed stage for document {document_id}: {e}")
            return None
    
    async def retry_from_stage(self, document_id: UUID, start_stage: Optional[str] = None) -> str:
        """
        Retry document processing from a specific stage.
        
        If start_stage is not provided, it will be read from job_metadata.
        If no failed_stage is found, processing starts from the beginning.
        
        Args:
            document_id: Document identifier
            start_stage: Optional stage to start from. If None, reads from job_metadata.
            
        Returns:
            str: Celery task ID
            
        Requirements: 8.4 - Restart processing from appropriate stage
        """
        try:
            # Get the failed stage if not provided
            if start_stage is None:
                start_stage = await self.get_failed_stage(document_id)
            
            logger.info(f"Retrying document {document_id} from stage: {start_stage or 'beginning'}")
            
            # Reset job status for retry
            await self._reset_job_for_retry(document_id)
            
            # Increment retry count
            await self._increment_retry_count(document_id)
            
            # Queue the appropriate task based on start_stage
            task = await self._queue_retry_task(document_id, start_stage)
            
            # Update job with task ID
            await self._update_job_task_id(document_id, task.id)
            
            self.processing_stats['total_jobs_queued'] += 1
            self.processing_stats['active_jobs'] += 1
            
            logger.info(f"Document {document_id} retry queued with task ID {task.id} from stage {start_stage or 'beginning'}")
            return task.id
            
        except Exception as e:
            logger.error(f"Failed to retry document processing from stage: {e}")
            raise
    
    async def _reset_job_for_retry(self, document_id: UUID):
        """Reset job status for retry."""
        try:
            from sqlalchemy import text

            from ..database.connection import db_manager

            # Ensure database is initialized
            if not db_manager.AsyncSessionLocal:
                db_manager.initialize()
            
            async with db_manager.get_async_session() as session:
                await session.execute(
                    text("""
                        UPDATE multimodal_librarian.processing_jobs 
                        SET status = 'pending',
                            progress_percentage = 0,
                            current_step = 'Queued for retry',
                            error_message = NULL,
                            started_at = NULL,
                            completed_at = NULL
                        WHERE source_id = :source_id
                    """),
                    {"source_id": str(document_id)}
                )
                
        except Exception as e:
            logger.error(f"Error resetting job for retry: {e}")
            raise
    
    async def _increment_retry_count(self, document_id: UUID):
        """Increment retry count for a job."""
        try:
            from sqlalchemy import text

            from ..database.connection import db_manager

            # Ensure database is initialized
            if not db_manager.AsyncSessionLocal:
                db_manager.initialize()
            
            async with db_manager.get_async_session() as session:
                await session.execute(
                    text("""
                        UPDATE multimodal_librarian.processing_jobs 
                        SET retry_count = COALESCE(retry_count, 0) + 1
                        WHERE source_id = :source_id
                    """),
                    {"source_id": str(document_id)}
                )
                
        except Exception as e:
            logger.error(f"Error incrementing retry count: {e}")
            raise
    
    async def _queue_retry_task(self, document_id: UUID, start_stage: Optional[str]):
        """
        Queue the appropriate Celery task based on the start stage.
        
        Args:
            document_id: Document identifier
            start_stage: Stage to start from
            
        Returns:
            Celery AsyncResult
            
        Requirements: 8.4 - Restart processing from appropriate stage
        """
        document_id_str = str(document_id)
        
        # Define stage order for determining where to start
        STAGE_ORDER = [
            'process_document',
            'extract_pdf_content',
            'generate_chunks',
            'store_embeddings',
            'update_knowledge_graph',
            'finalize_processing'
        ]
        
        # If no start_stage or unknown stage, start from beginning
        if not start_stage or start_stage not in STAGE_ORDER:
            logger.info(f"Starting from beginning for document {document_id}")
            return process_document_task.delay(document_id_str)
        
        # For stages that are part of the chain, we need to restart from the beginning
        # because each stage depends on the output of the previous stage
        # However, we can skip stages that have already completed successfully
        
        stage_index = STAGE_ORDER.index(start_stage)
        
        if stage_index <= 1:  # process_document or extract_pdf_content
            # Start from the beginning
            logger.info(f"Restarting from beginning (failed at {start_stage})")
            return process_document_task.delay(document_id_str)
        
        elif stage_index == 2:  # generate_chunks
            # Need to re-extract PDF content first, then continue
            logger.info(f"Restarting from PDF extraction (failed at {start_stage})")
            return process_document_task.delay(document_id_str)
        
        elif stage_index == 3:  # store_embeddings
            # Need chunks from previous stage, restart from beginning
            logger.info(f"Restarting from beginning (failed at {start_stage})")
            return process_document_task.delay(document_id_str)
        
        elif stage_index == 4:  # update_knowledge_graph
            # KG update can be retried independently if chunks exist
            # But for simplicity, restart from beginning
            logger.info(f"Restarting from beginning (failed at {start_stage})")
            return process_document_task.delay(document_id_str)
        
        elif stage_index == 5:  # finalize_processing
            # Finalization can be retried directly
            logger.info(f"Retrying finalization directly for document {document_id}")
            return finalize_processing_task.delay({}, document_id_str)
        
        # Default: start from beginning
        return process_document_task.delay(document_id_str)
    
    async def _create_processing_job(self, document_id: UUID):
        """Create processing job record in database."""
        try:
            from sqlalchemy import text

            from ..database.connection import db_manager

            # Ensure database is initialized
            if not db_manager.AsyncSessionLocal:
                db_manager.initialize()
            
            async with db_manager.get_async_session() as session:
                await session.execute(
                    text("""
                        INSERT INTO multimodal_librarian.processing_jobs (
                            source_id, status, progress_percentage, current_step
                        ) VALUES (
                            :source_id, 'pending', 0, 'Queued for processing'
                        )
                    """),
                    {"source_id": str(document_id)}
                )
                
        except Exception as e:
            logger.error(f"Error creating processing job: {e}")
            raise
    
    async def _update_job_task_id(self, document_id: UUID, task_id: str):
        """Update job with Celery task ID."""
        try:
            from sqlalchemy import text

            from ..database.connection import db_manager

            # Ensure database is initialized
            if not db_manager.AsyncSessionLocal:
                db_manager.initialize()
            
            async with db_manager.get_async_session() as session:
                await session.execute(
                    text("""
                        UPDATE multimodal_librarian.processing_jobs 
                        SET task_id = :task_id
                        WHERE source_id = :source_id
                        AND status = 'pending'
                    """),
                    {"source_id": str(document_id), "task_id": task_id}
                )
                
        except Exception as e:
            logger.error(f"Error updating job task ID: {e}")
    
    async def _update_job_status(self, document_id: UUID, status: str, 
                               progress: float, step: str, error_message: str = None):
        """Update job status in database."""
        try:
            from sqlalchemy import text

            from ..database.connection import db_manager

            # Ensure database is initialized
            if not db_manager.AsyncSessionLocal:
                db_manager.initialize()
            
            update_fields = [
                "status = :status",
                "progress_percentage = :progress",
                "current_step = :step"
            ]
            params = {
                "source_id": str(document_id),
                "status": status,
                "progress": progress,
                "step": step
            }
            
            if error_message:
                update_fields.append("error_message = :error_message")
                params["error_message"] = error_message
            
            if status == 'running':
                update_fields.append("started_at = COALESCE(started_at, NOW())")
            elif status in ['completed', 'failed']:
                update_fields.append("completed_at = NOW()")
            
            update_clause = ", ".join(update_fields)
            
            # Guard: don't let a 'running' update overwrite a terminal status
            status_guard = ""
            if status == 'running':
                status_guard = " AND status NOT IN ('completed', 'failed')"
            
            async with db_manager.get_async_session() as session:
                await session.execute(
                    text(f"""
                        UPDATE multimodal_librarian.processing_jobs 
                        SET {update_clause}
                        WHERE source_id = :source_id{status_guard}
                    """),
                    params
                )
                
        except Exception as e:
            logger.error(f"Error updating job status: {e}")
    
    def health_check(self) -> Dict[str, Any]:
        """
        Check Celery service health.
        
        Returns:
            Dict with health status
        """
        try:
            # Check Redis connection
            redis_healthy = self.redis_client.ping()
            
            # Check Celery workers
            inspect = celery_app.control.inspect()
            active_workers = inspect.active()
            worker_count = len(active_workers) if active_workers else 0
            
            # Get queue lengths
            queue_lengths = {}
            for queue in ['document_processing', 'pdf_processing', 'chunking', 'vector_storage', 'knowledge_graph']:
                try:
                    length = self.redis_client.llen(f"celery:{queue}")
                    queue_lengths[queue] = length
                except:
                    queue_lengths[queue] = -1
            
            return {
                'status': 'healthy' if redis_healthy and worker_count > 0 else 'degraded',
                'redis_connection': 'healthy' if redis_healthy else 'unhealthy',
                'worker_count': worker_count,
                'queue_lengths': queue_lengths,
                'processing_stats': self.processing_stats
            }
            
        except Exception as e:
            return {
                'status': 'unhealthy',
                'error': str(e),
                'processing_stats': self.processing_stats
            }



# Celery task definitions
@celery_app.task(bind=True, name='process_document_task')
def process_document_task(self, document_id: str):
    """
    Main document processing task - orchestrates the processing pipeline.
    Uses Celery chain to avoid blocking .get() calls.
    
    Args:
        document_id: Document identifier
    """
    from uuid import UUID

    from celery import chain, chord, group

    from ..models.documents import DocumentStatus
    
    try:
        logger.info(f"Starting document processing for {document_id}")
        
        # Update job status
        asyncio.run(_update_job_status_sync(
            UUID(document_id), 'running', 2.0, 'Starting document processing'
        ))
        
        # Update document status
        asyncio.run(_update_document_status_sync(
            UUID(document_id), DocumentStatus.PROCESSING
        ))
        
        # Pipeline: extract → chunks (+ inline embeddings) → [bridges, KG] in parallel → finalize
        # Embeddings are inlined into generate_chunks_task to avoid
        # serializing 655+ chunks through Redis. Bridges and KG run
        # concurrently after chunks+embeddings are stored.
        processing_pipeline = chain(
            extract_pdf_content_task.s(document_id),
            generate_chunks_task.s(document_id),
            # chord runs the group in parallel, then calls finalize
            chord(
                group(
                    generate_bridges_task.s(document_id),
                    update_knowledge_graph_task.s(document_id),
                ),
                finalize_processing_task.s(document_id)
            )
        )
        
        # Execute the pipeline asynchronously
        processing_pipeline.apply_async()
        
        logger.info(f"Document processing pipeline started for {document_id}")
        return {'status': 'processing', 'document_id': document_id}
        
    except Exception as e:
        error_message = str(e)
        logger.error(f"Document processing failed for {document_id}: {error_message}")
        
        # Update job and document status with failed_stage for retry support
        # Requirements: 8.4 - Track failed stage in processing metadata
        asyncio.run(_update_job_status_sync(
            UUID(document_id), 'failed', 0, 'Processing failed', error_message,
            failed_stage='process_document'
        ))
        asyncio.run(_update_document_status_sync(
            UUID(document_id), DocumentStatus.FAILED, error_message
        ))
        
        # Send failure notification via WebSocket
        # Requirements: 3.4
        try:
            from .processing_status_integration import notify_processing_failure_sync
            notify_processing_failure_sync(
                document_id=UUID(document_id),
                error=error_message,
                retry_available=True
            )
        except Exception as ws_error:
            logger.debug(f"WebSocket failure notification failed (non-critical): {ws_error}")
        
        raise


def _validate_parallel_results(parallel_results):
    """
    Validate that parallel_results from the chord contain real completion data.

    Returns (is_valid, error_message).  Defence-in-depth: even if
    ``Ignore()`` prevents ``skipped_duplicate`` from reaching here, this
    guard catches any edge case where incomplete results slip through.

    Requirements: 1.2, 1.3, 2.2, 2.3
    """
    if not isinstance(parallel_results, list):
        return False, (
            f"parallel_results is not a list (got {type(parallel_results).__name__}): "
            "incomplete parallel processing"
        )

    if len(parallel_results) < 2:
        return False, (
            f"Expected at least 2 parallel results, got {len(parallel_results)}: "
            "incomplete parallel processing"
        )

    has_kg = False
    has_bridge = False

    for result in parallel_results:
        if not isinstance(result, dict):
            continue

        if result.get('status') == 'skipped_duplicate':
            return False, (
                f"parallel_results contains a skipped_duplicate entry "
                f"(document_id={result.get('document_id', 'unknown')}): "
                "chord fired before real task completed"
            )

        if 'kg_failures' in result:
            has_kg = True
        if 'bridge_failures' in result:
            has_bridge = True

    # Aborted results won't contain kg_failures/bridge_failures, and that's
    # fine — the abort handler downstream deals with them.  But if *no*
    # result carries the expected keys and none is aborted, something is wrong.
    has_abort = any(
        isinstance(r, dict) and r.get('status') == 'aborted'
        for r in parallel_results
    )

    if not has_kg and not has_abort:
        return False, (
            "No parallel result contains 'kg_failures': "
            "KG task result missing — incomplete parallel processing"
        )

    if not has_bridge and not has_abort:
        return False, (
            "No parallel result contains 'bridge_failures': "
            "bridge task result missing — incomplete parallel processing"
        )

    return True, ''


@celery_app.task(name='finalize_processing_task')
def finalize_processing_task(parallel_results, document_id: str):
    """
    Finalize document processing - mark as completed.
    
    Called as the callback of a chord, so parallel_results is a list
    of results from [generate_bridges_task, update_knowledge_graph_task].
    Embeddings are stored inline by generate_chunks_task.
    
    Args:
        parallel_results: List of results from parallel tasks
        document_id: Document identifier
    """
    import time as _time
    from uuid import UUID

    from ..models.documents import DocumentStatus
    _t0 = _time.monotonic()
    try:
        logger.info(f"Finalizing document processing for {document_id}")

        # Validate parallel_results before proceeding (defense-in-depth).
        # Requirements: 1.2, 1.3, 2.2, 2.3
        is_valid, validation_error = _validate_parallel_results(parallel_results)
        if not is_valid:
            logger.error(
                f"Invalid parallel_results for {document_id}: {validation_error}"
            )
            asyncio.run(_update_job_status_sync(
                UUID(document_id), 'failed', 0,
                'Incomplete parallel processing', validation_error,
                failed_stage='finalize_processing'
            ))
            asyncio.run(_update_document_status_sync(
                UUID(document_id), DocumentStatus.FAILED, validation_error
            ))
            try:
                from .processing_status_integration import (
                    notify_processing_failure_sync,
                )
                notify_processing_failure_sync(
                    document_id=UUID(document_id),
                    error=validation_error,
                    retry_available=True
                )
            except Exception as ws_error:
                logger.debug(f"WebSocket failure notification failed (non-critical): {ws_error}")
            try:
                asyncio.run(_delete_processing_payload(document_id))
            except Exception:
                pass
            return {'status': 'failed', 'document_id': document_id, 'error': validation_error}
        
        # If the document was deleted during processing, skip finalization
        # NOTE: _cleanup_parallel_progress is called AFTER job completion to ensure
        # the Active Jobs report can read substage progress until the job is done.
        try:
            _check_document_deleted(document_id, "finalize_processing")
        except DocumentDeletedError:
            logger.info(f"Skipping finalization for deleted document {document_id}")
            _cleanup_parallel_progress(document_id)
            return {'status': 'aborted', 'document_id': document_id}
        
        # --- Quality gate evaluation ---
        # Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 5.1, 5.2, 5.3, 7.5
        from ..models.core import ContentType
        from .quality_gate import compute_quality_gate

        # Extract kg_failures and bridge_failures from parallel task results
        kg_failures = {'ner_failures': 0, 'llm_failures': 0, 'total_chunks': 0}
        bridge_failures = {'failed_bridges': 0, 'total_bridges': 0}
        if isinstance(parallel_results, list):
            for result in parallel_results:
                if isinstance(result, dict):
                    if 'kg_failures' in result:
                        kg_failures = result['kg_failures']
                    if 'bridge_failures' in result:
                        bridge_failures = result['bridge_failures']

        # Determine document content_type from the processing payload
        content_type = ContentType.GENERAL
        try:
            payload = asyncio.run(_retrieve_processing_payload(document_id))
            ct_value = (payload.get('content_profile') or {}).get('content_type', '')
            if ct_value:
                content_type = ContentType(ct_value)
            logger.info(
                f"Quality gate: resolved content_type={content_type.value} "
                f"for {document_id}"
            )
        except Exception as ct_err:
            logger.warning(f"Could not determine content_type for {document_id}, using GENERAL: {ct_err}")

        qg_result = compute_quality_gate(kg_failures, bridge_failures, content_type)
        logger.info(
            f"Quality gate result for {document_id}: "
            f"content_type={qg_result.content_type}, "
            f"threshold={qg_result.threshold}, "
            f"composite={qg_result.composite_rate:.4f}, "
            f"passed={qg_result.passed}"
        )

        # Persist quality gate data for both passing and failing documents
        # Requirements: 7.5
        try:
            asyncio.run(_persist_quality_gate_data(document_id, qg_result.to_dict()))
        except Exception as qg_persist_err:
            logger.warning(f"Failed to persist quality gate data for {document_id}: {qg_persist_err}")

        if not qg_result.passed:
            # Quality gate FAILED — mark document as FAILED
            # Requirements: 4.1, 4.2, 4.3, 4.4, 4.5
            error_message = qg_result.error_message()
            logger.warning(f"Quality gate failed for {document_id}: {error_message}")

            asyncio.run(_update_job_status_sync(
                UUID(document_id), 'failed', 0, 'Quality gate failed', error_message,
                failed_stage='update_knowledge_graph'
            ))
            asyncio.run(_update_document_status_sync(
                UUID(document_id), DocumentStatus.FAILED, error_message
            ))

            # Send failure notification via WebSocket
            # Requirements: 5.1, 5.2, 5.3
            try:
                from .processing_status_integration import (
                    notify_processing_failure_sync,
                )
                notify_processing_failure_sync(
                    document_id=UUID(document_id),
                    error=error_message,
                    retry_available=True
                )
            except Exception as ws_error:
                logger.debug(f"WebSocket failure notification failed (non-critical): {ws_error}")

            asyncio.run(_record_stage_timing(document_id, "finalize", _time.monotonic() - _t0))

            # Clean up parallel progress Redis keys
            _cleanup_parallel_progress(document_id)

            # Clean up the processing payload from PostgreSQL
            try:
                asyncio.run(_delete_processing_payload(document_id))
            except Exception as cleanup_err:
                logger.debug(f"Processing payload cleanup failed (non-critical): {cleanup_err}")

            return {'status': 'failed', 'document_id': document_id, 'quality_gate': qg_result.to_dict()}

        # --- Quality gate PASSED — proceed with normal completion flow ---
        # Update job and document status
        asyncio.run(_update_job_status_sync(
            UUID(document_id), 'running', 90.0, 'Computing related documents'
        ))
        
        # Compute composite scores to create RELATED_DOCS edges
        try:
            asyncio.run(_compute_composite_scores(document_id))
        except Exception as score_err:
            logger.warning(
                f"Composite score computation failed for {document_id} "
                f"(non-fatal): {score_err}"
            )
        
        asyncio.run(_update_job_status_sync(
            UUID(document_id), 'running', 95.0, 'Finalizing'
        ))
        asyncio.run(_update_job_status_sync(
            UUID(document_id), 'running', 99.0, 'Finalizing'
        ))
        asyncio.run(_update_document_status_sync(
            UUID(document_id), DocumentStatus.COMPLETED
        ))
        
        # Send detailed completion notification via WebSocket
        # Requirements: 3.3
        try:
            from .processing_status_integration import notify_processing_completion_sync

            # Extract processing summary from parallel_results
            chunk_count = 0
            concept_count = 0
            page_count = 0
            title = "Document"
            
            # parallel_results is a list of dicts from the 3 parallel tasks
            if isinstance(parallel_results, list):
                for result in parallel_results:
                    if isinstance(result, dict):
                        chunk_count = max(chunk_count, result.get('chunk_count', 0))
                        concept_count = max(concept_count, result.get('concept_count', 0))
                        page_count = max(page_count, result.get('page_count', 0))
                        if result.get('title'):
                            title = result['title']
            
            notify_processing_completion_sync(
                document_id=UUID(document_id),
                title=title,
                page_count=page_count,
                chunk_count=chunk_count,
                concept_count=concept_count,
                processing_time_ms=0  # Could be calculated from job timestamps
            )
        except Exception as ws_error:
            # Don't fail the job if WebSocket notification fails
            logger.debug(f"WebSocket completion notification failed (non-critical): {ws_error}")
        
        logger.info(f"Document processing completed successfully for {document_id}")
        
        # Clean up parallel progress Redis keys now that job is complete
        _cleanup_parallel_progress(document_id)
        
        asyncio.run(_record_stage_timing(document_id, "finalize", _time.monotonic() - _t0))
        
        # Clean up the processing payload from PostgreSQL
        try:
            asyncio.run(_delete_processing_payload(document_id))
        except Exception as cleanup_err:
            logger.debug(f"Processing payload cleanup failed (non-critical): {cleanup_err}")
        
        return {'status': 'completed', 'document_id': document_id}
        
    except Exception as e:
        error_message = str(e)
        logger.error(f"Failed to finalize processing for {document_id}: {error_message}")
        
        # Clean up parallel progress Redis keys
        _cleanup_parallel_progress(document_id)
        
        # Clean up the processing payload even on failure
        try:
            asyncio.run(_delete_processing_payload(document_id))
        except Exception:
            pass
        
        # Update job and document status with failed_stage for retry support
        # Requirements: 8.4 - Track failed stage in processing metadata
        asyncio.run(_update_job_status_sync(
            UUID(document_id), 'failed', 0, 'Finalization failed', error_message,
            failed_stage='finalize_processing'
        ))
        asyncio.run(_update_document_status_sync(
            UUID(document_id), DocumentStatus.FAILED, error_message
        ))
        
        # Send failure notification via WebSocket
        # Requirements: 3.4
        try:
            from .processing_status_integration import notify_processing_failure_sync
            notify_processing_failure_sync(
                document_id=UUID(document_id),
                error=error_message,
                retry_available=True
            )
        except Exception as ws_error:
            logger.debug(f"WebSocket failure notification failed (non-critical): {ws_error}")
        
        raise


@celery_app.task(name='extract_pdf_content_task', time_limit=TASK_HARD_TIME_LIMIT, soft_time_limit=TASK_SOFT_TIME_LIMIT)
@redis_task_lock("extract_lock:{document_id}")
def extract_pdf_content_task(document_id: str):
    """
    Extract content from PDF document.
    
    Uses a single asyncio.run() call to avoid the stale-event-loop problem.
    """
    try:
        import time as _time
        _t0 = _time.monotonic()
        _check_document_deleted(document_id, "extract_pdf_content start")
        logger.info(f"Extracting PDF content for document {document_id}")
        result = asyncio.run(_extract_pdf_content_async(document_id))
        asyncio.run(_record_stage_timing(document_id, "extract_pdf", _time.monotonic() - _t0))
        return result
    except Exception as e:
        logger.error(f"PDF content extraction failed for document {document_id}: {e}")
        raise


async def _extract_pdf_content_async(document_id: str) -> Dict[str, Any]:
    """All async work for PDF extraction in a single coroutine.
    
    This avoids multiple asyncio.run() calls which poison the SQLAlchemy
    async engine's connection pool across event loop boundaries.
    """
    import json
    from uuid import UUID

    from ..components.pdf_processor.pdf_processor import PDFProcessor
    from ..database.connection import get_async_connection
    from .storage_service import StorageService

    # Step 1: Update job progress
    await _update_job_status_sync(
        UUID(document_id), 'running', 5.0, 'Extracting PDF content'
    )

    # Step 2: Fetch document s3_key and title using direct asyncpg (NOT db_manager)
    conn = await get_async_connection()
    try:
        row = await conn.fetchrow("""
            SELECT metadata, title FROM multimodal_librarian.knowledge_sources
            WHERE id = $1::uuid
        """, document_id)
    finally:
        await conn.close()

    if not row:
        raise Exception(f"Document {document_id} not found in knowledge_sources")

    metadata = row['metadata']
    if isinstance(metadata, str):
        metadata = json.loads(metadata)

    s3_key = metadata.get('s3_key') if metadata else None
    if not s3_key:
        raise Exception(f"Document {document_id} has no s3_key in metadata")
    
    # Extract filename from s3_key (e.g., "documents/uuid/20260304_040636_myfile.pdf" -> "myfile.pdf")
    # The s3_key format is: documents/{doc_id}/{timestamp}_{original_filename}
    s3_filename = s3_key.rsplit('/', 1)[-1] if s3_key else None
    # Strip the timestamp prefix (format: YYYYMMDD_HHMMSS_)
    if s3_filename and len(s3_filename) > 16 and s3_filename[8] == '_' and s3_filename[15] == '_':
        s3_filename = s3_filename[16:]
    
    # Get user-provided document title from knowledge_sources, with validation
    user_document_title = _get_valid_document_title(row['title'], s3_filename)

    # Step 3: Download file content (sync call — StorageService uses boto3)
    storage_service = StorageService()
    document_content = storage_service.download_file(s3_key)

    if not document_content:
        raise Exception("Document content not found")

    # Step 4: Process PDF (sync — CPU-bound)
    pdf_processor = PDFProcessor()
    pdf_processor.enable_graceful_degradation_mode(True)
    pdf_content = pdf_processor.extract_content(document_content)

    # Step 5: Serialize for passing to next task in chain
    serialized_content = {
        'text': pdf_content.text,
        'images': [
            {
                'element_id': img.element_id,
                'element_type': img.element_type,
                'caption': img.caption,
                'alt_text': img.alt_text,
                'metadata': img.metadata
            } for img in pdf_content.images
        ],
        'tables': [
            {
                'element_id': table.element_id,
                'element_type': table.element_type,
                'caption': table.caption,
                'alt_text': table.alt_text,
                'metadata': table.metadata
            } for table in pdf_content.tables
        ],
        'charts': [
            {
                'element_id': chart.element_id,
                'element_type': chart.element_type,
                'caption': chart.caption,
                'alt_text': chart.alt_text,
                'metadata': chart.metadata
            } for chart in pdf_content.charts
        ],
        'metadata': {
            'title': user_document_title,  # Use user-provided title from knowledge_sources
            'author': pdf_content.metadata.author if pdf_content.metadata else None,
            'page_count': pdf_content.metadata.page_count if pdf_content.metadata else 0,
            'file_size': pdf_content.metadata.file_size if pdf_content.metadata else 0
        }
    }

    logger.info(f"PDF content extracted successfully for document {document_id}")

    # Send extraction stats via WebSocket
    page_count = pdf_content.metadata.page_count if pdf_content.metadata else 0
    await _update_job_status_sync(
        UUID(document_id), 'running', 10.0, 'Extracting PDF content',
        metadata={
            'pages_extracted': page_count,
            'images': len(pdf_content.images),
            'tables': len(pdf_content.tables),
            'charts': len(pdf_content.charts),
            'text_length': len(pdf_content.text),
        }
    )

    return serialized_content


@celery_app.task(name='generate_chunks_task', time_limit=TASK_HARD_TIME_LIMIT, soft_time_limit=TASK_SOFT_TIME_LIMIT)
@redis_task_lock("chunks_lock:{document_id}")
def generate_chunks_task(pdf_content: Dict[str, Any], document_id: str):
    """
    Generate chunks from PDF content.
    
    Args:
        pdf_content: Serialized PDF content (from previous task in chain)
        document_id: Document identifier
        
    Returns:
        Serialized processed document
    """
    import re

    def _extract_page_number_from_content(content: str) -> Optional[int]:
        """Extract the first page number from [Page N] markers embedded in chunk content.
        
        The PDF processor embeds markers like [Page 302] in the extracted text.
        This function finds the first such marker and returns the page number as int.
        Returns None if no marker is found or the value is not numeric.
        """
        match = re.search(r'\[Page\s+(\d+)', content)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                return None
        return None

    try:
        # Import here to avoid circular imports
        import time as _time
        _t0 = _time.monotonic()
        from uuid import UUID

        from ..components.chunking_framework.framework import (
            GenericMultiLevelChunkingFramework,
        )
        from ..database.connection import db_manager
        from ..models.core import DocumentContent, DocumentMetadata
        
        logger.info(f"Generating chunks for document {document_id}")
        
        _check_document_deleted(document_id, "generate_chunks start")
        
        # Initialize database if needed
        if not db_manager.AsyncSessionLocal:
            db_manager.initialize()
        
        # Update progress
        asyncio.run(_update_job_status_sync(
            UUID(document_id), 'running', 15.0, 'Generating chunks'
        ))
        
        # Reconstruct DocumentContent from serialized data
        metadata = DocumentMetadata(
            title=pdf_content['metadata']['title'],
            author=pdf_content['metadata']['author'],
            page_count=pdf_content['metadata']['page_count'],
            file_size=pdf_content['metadata']['file_size']
        )
        
        doc_content = DocumentContent(
            text=pdf_content['text'],
            images=[],  # Simplified for now
            tables=[],  # Simplified for now
            charts=[],  # Simplified for now
            metadata=metadata
        )
        
        # Process through chunking framework (chunks only, no bridges)
        # Bridges are generated in parallel by generate_bridges_task
        chunking_framework = GenericMultiLevelChunkingFramework()
        processed_document = chunking_framework.process_document_chunks_only(doc_content, document_id)
        
        # Serialize processed document
        # Include document title in each chunk's metadata for citation display
        document_title = pdf_content['metadata']['title']
        
        serialized_chunks = []
        last_seen_page = None
        for chunk in processed_document.chunks:
            # Extract page number from [Page N] markers in chunk content
            page_number = _extract_page_number_from_content(chunk.content)
            if page_number is not None:
                last_seen_page = page_number
            elif last_seen_page is not None:
                # Propagate last-seen page to chunks without a marker
                page_number = last_seen_page
            
            serialized_chunk = {
                'id': chunk.id,
                'content': chunk.content,
                'start_position': chunk.start_position,
                'end_position': chunk.end_position,
                'chunk_type': chunk.chunk_type,
                'page_number': page_number,
                'metadata': {
                    **(chunk.metadata or {}),
                    'title': document_title,
                    'document_title': document_title,
                    'page_number': page_number,
                }
            }
            serialized_chunks.append(serialized_chunk)
        
        serialized_processed = {
            'document_id': processed_document.document_id,
            'chunks': serialized_chunks,
            'bridges': [],  # Bridges generated in parallel by generate_bridges_task
            'bridge_generation_data': processed_document.processing_stats.get('bridge_generation_data', {}),
            'content_profile': {
                'content_type': processed_document.content_profile.content_type.value,
                'complexity_score': processed_document.content_profile.complexity_score,
                'domain_categories': processed_document.content_profile.domain_categories
            },
            'processing_stats': processed_document.processing_stats
        }
        
        logger.info(f"Generated {len(processed_document.chunks)} chunks for document {document_id}")
        
        # --- Inline embedding storage (was store_embeddings_task) ---
        # Storing embeddings here avoids serializing 655+ chunks through
        # Redis and eliminates one Celery task dispatch overhead.
        logger.info(f"Storing embeddings inline for document {document_id}")
        
        # Delete existing chunks before storing new ones (supports reprocessing)
        try:
            deleted_count = asyncio.run(_delete_document_chunks(document_id))
            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} existing chunks for document {document_id}")
        except Exception as e:
            logger.warning(f"Cleanup warning for document {document_id}: {e}")
        
        asyncio.run(_update_job_status_sync(
            UUID(document_id), 'running', 15.0, 'Storing chunks and embeddings',
            metadata={'chunks_generated': len(serialized_chunks),
                      'total_chunks': len(serialized_chunks),
                      'pages': pdf_content['metadata']['page_count']}
        ))
        
        total_pages = pdf_content['metadata']['page_count']
        
        # Store chunks in PostgreSQL (with incremental progress updates)
        asyncio.run(_store_chunks_in_database(document_id, serialized_chunks,
                                              total_pages=total_pages))
        
        # Store chunk embeddings in vector database (with incremental progress updates)
        asyncio.run(_store_embeddings_in_vector_db(document_id, serialized_chunks,
                                                   total_pages=total_pages))
        
        logger.info(f"Stored {len(serialized_chunks)} chunks + embeddings for document {document_id}")
        # --- End inline embedding storage ---
        
        # Send progress update with chunk/embedding stats
        asyncio.run(_update_job_status_sync(
            UUID(document_id), 'running', 25.0, 'Chunks and embeddings stored',
            metadata={'chunks_stored': len(serialized_chunks),
                      'embeddings_stored': len(serialized_chunks),
                      'total_chunks': len(serialized_chunks),
                      'pages': pdf_content['metadata']['page_count']}
        ))
        
        # Store processed document payload in PostgreSQL instead of passing
        # through the Celery message broker. Large payloads (68MB+) cause
        # JSON serialization timeouts and chord dispatch failures.
        asyncio.run(_store_processing_payload(document_id, serialized_processed))
        
        # Return only the document_id — downstream tasks retrieve the
        # payload from PostgreSQL via _retrieve_processing_payload().
        asyncio.run(_record_stage_timing(document_id, "generate_chunks", _time.monotonic() - _t0))
        return {'document_id': document_id}
        
    except DocumentDeletedError:
        logger.info(f"Chunk generation aborted — document {document_id} was deleted")
        return {'status': 'aborted', 'document_id': document_id}
    except Exception as e:
        logger.error(f"Chunk generation failed for document {document_id}: {e}")
        raise


@celery_app.task(name='generate_bridges_task', time_limit=TASK_HARD_TIME_LIMIT, soft_time_limit=TASK_SOFT_TIME_LIMIT)
@redis_task_lock("bridge_lock:{document_id}")
def generate_bridges_task(upstream_result: Dict[str, Any], document_id: str):
    """
    Generate bridge chunks between adjacent content chunks.
    
    This task runs in PARALLEL with store_embeddings_task and
    update_knowledge_graph_task. It uses the bridge_generation_data
    stashed by generate_chunks_task to produce bridges without
    re-running chunking or gap analysis.
    
    Bridges are stored INCREMENTALLY in PostgreSQL and the vector DB
    as each batch is generated. This ensures that if Milvus storage fails,
    previously-stored bridges are preserved and not lost.
    
    Args:
        processed_document: Serialized processed document (from generate_chunks_task)
        document_id: Document identifier
        
    Returns:
        Dict with bridge generation results including bridges_stored count
    """
    # Use a single persistent event loop for all async calls in this task.
    # asyncio.run() creates and DESTROYS a loop each time, which on Python
    # 3.11 sets the thread-local event loop to None.  The bridge generator's
    # _process_batch also manipulates event loops.  Using one shared loop
    # with run_until_complete() avoids the "no current event loop" crash.
    _task_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_task_loop)
    
    # Track bridges stored incrementally (separate from bridges_generated)
    bridges_stored_counter = [0]  # mutable for closure
    storage_error = [None]  # Track storage errors for partial failure handling
    total_bridges_expected = [0]  # Track total bridges expected for error reporting
    
    try:
        import time as _time
        from uuid import UUID

        from ..components.chunking_framework.framework import (
            GenericMultiLevelChunkingFramework,
        )
        from ..database.connection import db_manager
        _t0 = _time.monotonic()
        logger.info(f"Generating bridges for document {document_id}")
        
        _check_document_deleted(document_id, "generate_bridges start")
        
        if not db_manager.AsyncSessionLocal:
            db_manager.initialize()
        
        # Retrieve processed document from PostgreSQL (no longer passed via broker)
        processed_document = _task_loop.run_until_complete(
            _retrieve_processing_payload(document_id)
        )
        
        # Get document title from chunk metadata for bridge title propagation
        document_title = None
        chunks = processed_document.get('chunks', [])
        if chunks:
            document_title = chunks[0].get('metadata', {}).get('title')
        
        # Update progress — bridges run in parallel with KG
        pct = _set_parallel_progress(document_id, 'bridges', 0.0)
        _task_loop.run_until_complete(_update_job_status_sync(
            UUID(document_id), 'running', pct, _get_parallel_step_label(document_id)
        ))
        
        bridge_generation_data = processed_document.get('bridge_generation_data', {})
        if not bridge_generation_data or not bridge_generation_data.get('bridge_needed'):
            logger.info(f"No bridges needed for document {document_id}")
            pct = _set_parallel_progress(document_id, 'bridges', 1.0)
            _task_loop.run_until_complete(_update_job_status_sync(
                UUID(document_id), 'running', pct, _get_parallel_step_label(document_id),
                metadata={'bridges_generated': 0, 'bridges_stored': 0, 'bridges_needed': False}
            ))
            return {
                'status': 'completed',
                'document_id': document_id,
                'bridges_generated': 0,
                'bridges_stored': 0,
                'bridge_failures': {
                    'failed_bridges': 0,
                    'total_bridges': 0,
                }
            }
        
        # Generate bridges using the deferred method with progress reporting
        import time as _time
        _last_progress_time = [0.0]  # mutable for closure

        def _bridge_progress(bridges_so_far, total_bridges, failed):
            now = _time.time()
            # Throttle updates to every 5 seconds to avoid flooding WebSocket
            if now - _last_progress_time[0] < 5.0:
                return
            _last_progress_time[0] = now

            # Check if document was deleted during generation — abort early
            # to avoid wasting Ollama/GPU resources on orphaned work
            try:
                _check_document_deleted(document_id, "bridge_progress")
            except DocumentDeletedError:
                raise  # Propagates up through batch_generate_bridges

            fraction = bridges_so_far / max(total_bridges, 1)
            pct = _set_parallel_progress(document_id, 'bridges', fraction)
            # Re-set the event loop — _process_batch may have replaced it
            asyncio.set_event_loop(_task_loop)
            _task_loop.run_until_complete(_update_job_status_sync(
                UUID(document_id), 'running', pct,
                _get_parallel_step_label(document_id),
                metadata={
                    'bridges_generated': bridges_so_far,
                    'bridges_stored': bridges_stored_counter[0],
                    'total_bridges': total_bridges,
                    'bridges_failed': failed,
                }
            ))

        async def _incremental_storage_async(batch_bridges):
            """Async implementation of incremental bridge storage."""
            nonlocal bridges_stored_counter, storage_error
            
            if not batch_bridges:
                return
            
            serialized_batch = [
                {
                    'id': bridge.id,
                    'content': bridge.content,
                    'source_chunks': bridge.source_chunks,
                    'generation_method': bridge.generation_method,
                    'confidence_score': bridge.confidence_score
                }
                for bridge in batch_bridges
            ]
            
            batch_size = len(serialized_batch)
            
            try:
                await _store_bridge_chunks_in_database(document_id, serialized_batch)
                logger.info(f"Stored {batch_size} bridges in PostgreSQL for document {document_id} (total: {bridges_stored_counter[0] + batch_size})")
                
                await _store_bridge_embeddings_in_vector_db(document_id, serialized_batch, document_title=document_title)
                logger.info(f"Stored {batch_size} bridge embeddings in Milvus for document {document_id}")
                
                bridges_stored_counter[0] += batch_size
                
            except Exception as e:
                logger.error(
                    f"Incremental storage failed for batch of {batch_size} bridges "
                    f"(document {document_id}, stored so far: {bridges_stored_counter[0]}): {e}"
                )
                storage_error[0] = str(e)
                raise

        def _incremental_storage_callback(batch_bridges):
            """
            Synchronous wrapper that runs incremental storage on the task event loop.
            
            Called by batch_generate_bridges after each batch completes.
            Uses _task_loop.run_until_complete to properly await the async storage.
            """
            # Re-set the event loop — _process_batch may have replaced it
            asyncio.set_event_loop(_task_loop)
            _task_loop.run_until_complete(_incremental_storage_async(batch_bridges))

        chunking_framework = GenericMultiLevelChunkingFramework()
        # Track total expected bridges before generation starts
        total_bridges_expected[0] = len(bridge_generation_data.get('bridge_needed', []))
        bridges, batch_stats = chunking_framework.generate_bridges_for_document(
            bridge_generation_data, 
            progress_callback=_bridge_progress,
            storage_callback=_incremental_storage_callback
        )
        
        # Restore our task loop after _process_batch may have replaced it
        asyncio.set_event_loop(_task_loop)
        
        # Note: With incremental storage, bridges are already stored by the callback.
        # We no longer need to store all bridges at the end.
        
        logger.info(f"Bridge generation completed for document {document_id}: {len(bridges)} bridges generated, {bridges_stored_counter[0]} stored")
        pct = _set_parallel_progress(document_id, 'bridges', 1.0)
        _task_loop.run_until_complete(_update_job_status_sync(
            UUID(document_id), 'running', pct, _get_parallel_step_label(document_id),
            metadata={'bridges_generated': len(bridges), 'bridges_stored': bridges_stored_counter[0]}
        ))
        _task_loop.run_until_complete(_record_stage_timing(document_id, "generate_bridges", _time.monotonic() - _t0))
        
        # Check for partial success (some bridges stored before failure)
        if storage_error[0] and bridges_stored_counter[0] > 0:
            return {
                'status': 'partial',
                'document_id': document_id,
                'bridges_generated': len(bridges),
                'bridges_stored': bridges_stored_counter[0],
                'bridge_failures': {
                    'failed_bridges': batch_stats.failed_generations,
                    'total_bridges': batch_stats.total_requests,
                },
                'storage_error': storage_error[0]
            }
        
        return {
            'status': 'completed',
            'document_id': document_id,
            'bridges_generated': len(bridges),
            'bridges_stored': bridges_stored_counter[0],
            'bridge_failures': {
                'failed_bridges': batch_stats.failed_generations,
                'total_bridges': batch_stats.total_requests,
            }
        }
        
    except DocumentDeletedError:
        logger.info(f"Bridge generation aborted — document {document_id} was deleted")
        _task_loop.run_until_complete(_record_stage_timing(document_id, "generate_bridges", _time.monotonic() - _t0))
        return {
            'status': 'aborted',
            'document_id': document_id,
            'bridges_generated': 0,
            'bridges_stored': bridges_stored_counter[0],
            'bridge_failures': {
                'failed_bridges': 0,
                'total_bridges': 0,
            }
        }
    except Exception as e:
        logger.error(f"Bridge generation failed for document {document_id}: {e}")
        # Don't fail the entire pipeline for bridge errors
        # Log partial success if some bridges were stored before failure
        if bridges_stored_counter[0] > 0:
            logger.info(f"Partial success: {bridges_stored_counter[0]} bridges stored before failure")
        logger.warning(f"Continuing without remaining bridges for document {document_id}")
        return {
            'status': 'failed' if bridges_stored_counter[0] == 0 else 'partial',
            'document_id': document_id,
            'bridges_generated': bridges_stored_counter[0],
            'bridges_stored': bridges_stored_counter[0],
            'bridge_failures': {
                'failed_bridges': total_bridges_expected[0] - bridges_stored_counter[0],
                'total_bridges': total_bridges_expected[0],
            },
            'error': str(e)
        }
    finally:
        _task_loop.close()
        asyncio.set_event_loop(None)


@celery_app.task(name='store_embeddings_task', time_limit=TASK_HARD_TIME_LIMIT, soft_time_limit=TASK_SOFT_TIME_LIMIT)
@redis_task_lock("embeddings_lock:{document_id}")
def store_embeddings_task(processed_document: Dict[str, Any], document_id: str):
    """
    Store embeddings in vector database.
    
    This task supports document reprocessing by first deleting any existing
    chunks for the document before storing new ones. This ensures clean
    reprocessing without duplicate or orphaned chunks.
    
    Args:
        processed_document: Serialized processed document (from previous task in chain)
        document_id: Document identifier
    """
    try:
        from uuid import UUID

        from ..database.connection import db_manager
        
        logger.info(f"Storing embeddings for document {document_id}")
        
        # Initialize database if needed
        if not db_manager.AsyncSessionLocal:
            db_manager.initialize()
        
        # Update progress
        asyncio.run(_update_job_status_sync(
            UUID(document_id), 'running', 20.0, 'Cleaning up existing chunks'
        ))
        
        # Delete existing chunks before storing new ones (supports reprocessing)
        # This ensures clean reprocessing without duplicate or orphaned chunks
        try:
            deleted_count = asyncio.run(_delete_document_chunks(document_id))
            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} existing chunks for document {document_id}")
        except Exception as e:
            # Log warning but continue - this might be a new document with no existing chunks
            logger.warning(f"Cleanup warning for document {document_id}: {e}")
        
        # Update progress
        asyncio.run(_update_job_status_sync(
            UUID(document_id), 'running', 22.0, 'Storing embeddings'
        ))
        
        chunks = processed_document['chunks']
        
        # Store chunks in relational database (PostgreSQL)
        asyncio.run(_store_chunks_in_database(document_id, chunks))
        
        # Store chunk embeddings in vector database (Milvus for local, OpenSearch for AWS)
        asyncio.run(_store_embeddings_in_vector_db(document_id, chunks))
        
        # NOTE: Bridge storage is handled by generate_bridges_task (runs in parallel)
        
        logger.info(f"Stored {len(chunks)} chunks for document {document_id}")
        
        # Return processed_document for next task in chain
        return processed_document
        
    except Exception as e:
        logger.error(f"Embedding storage failed for document {document_id}: {e}")
        raise


async def _store_embeddings_in_vector_db(document_id: str, chunks: List[Dict[str, Any]],
                                        total_pages: int = 0):
    """Store chunk embeddings in vector database (Milvus or OpenSearch).
    
    The chunk ID must be a valid UUID that was generated by the chunking framework.
    This ensures consistency between PostgreSQL and Milvus storage.
    
    Splits chunks into sub-batches and sends incremental progress updates
    via WebSocket every ~5 seconds.
    """
    try:
        import time
        import uuid as uuid_module

        from ..clients.database_factory import DatabaseClientFactory
        from ..clients.model_server_client import initialize_model_client
        from ..config.config_factory import get_database_config

        # Get database configuration (auto-detects local vs AWS)
        config = get_database_config()
        factory = DatabaseClientFactory(config)
        
        # Get vector client (Milvus for local, OpenSearch for AWS)
        vector_client = factory.get_vector_client()
        
        # Connect to vector database
        await vector_client.connect()
        
        # Initialize model server client for embedding generation
        # This is required in Celery worker context where the client isn't pre-initialized
        model_client = await initialize_model_client()
        if model_client and model_client.enabled:
            vector_client._model_server_client = model_client
            vector_client._embedding_dimension = 768  # Default for bge-base-en-v1.5
            logger.info("Model server client initialized for Celery worker")
        
        # Prepare all chunks for vector storage
        total_chunks = len(chunks)
        all_vector_chunks = []
        for i, chunk in enumerate(chunks):
            # Validate that chunk ID is a valid UUID - fail fast if invalid
            chunk_id = chunk.get('id')
            if not chunk_id:
                raise ValueError(f"Chunk at index {i} missing required 'id' field")
            try:
                uuid_module.UUID(chunk_id)
            except (ValueError, TypeError):
                raise ValueError(f"Chunk ID must be a valid UUID, got: {chunk_id}")
            
            vector_chunk = {
                'id': chunk_id,  # Use existing UUID unchanged
                'content': chunk['content'],
                'metadata': {
                    'source_id': document_id,
                    'chunk_index': chunk.get('metadata', {}).get('chunk_index', i),
                    'chunk_type': chunk.get('chunk_type', 'text'),
                    'content_type': chunk.get('metadata', {}).get('content_type', 'text'),
                    **chunk.get('metadata', {})
                }
            }
            all_vector_chunks.append(vector_chunk)
        
        # Store embeddings in sub-batches with progress reporting
        EMBED_BATCH_SIZE = 200  # Sub-batch size for incremental progress
        last_update_time = time.monotonic()
        UPDATE_INTERVAL = 5.0  # seconds between progress updates
        stored_so_far = 0

        for batch_start in range(0, total_chunks, EMBED_BATCH_SIZE):
            # Check for deletion between batches so we abort promptly
            if await _is_document_deleted(document_id):
                logger.info(
                    f"Document {document_id} deleted during embedding storage "
                    f"(batch {batch_start}/{total_chunks}), aborting."
                )
                raise DocumentDeletedError(
                    f"Document {document_id} was deleted during embedding storage"
                )

            batch_end = min(batch_start + EMBED_BATCH_SIZE, total_chunks)
            batch = all_vector_chunks[batch_start:batch_end]
            
            await vector_client.store_embeddings(batch)
            stored_so_far = batch_end
            
            # Send incremental progress every ~5 seconds (or on last batch)
            now = time.monotonic()
            is_last_batch = batch_end >= total_chunks
            if now - last_update_time >= UPDATE_INTERVAL or is_last_batch:
                last_update_time = now
                # Embeddings phase: 20-25% progress range
                progress_pct = 20.0 + (stored_so_far / total_chunks) * 5.0
                # Extract max page from this batch for page tracking
                max_page = 0
                for vc in all_vector_chunks[:stored_so_far]:
                    pn = vc.get('metadata', {}).get('page_number')
                    if pn is not None:
                        try:
                            max_page = max(max_page, int(pn))
                        except (ValueError, TypeError):
                            pass
                if total_pages > 0:
                    max_page = min(max_page, total_pages)
                meta = {
                    'embeddings_stored_so_far': stored_so_far,
                    'total_chunks': total_chunks,
                }
                if max_page > 0:
                    meta['current_page'] = max_page
                if total_pages > 0:
                    meta['total_pages'] = total_pages
                await _update_job_status_sync(
                    uuid_module.UUID(document_id), 'running', min(progress_pct, 25.0),
                    'Storing embeddings',
                    metadata=meta
                )
        
        logger.info(f"Stored {total_chunks} embeddings in vector database for document {document_id}")
        
    except Exception as e:
        logger.error(f"Error storing embeddings in vector database: {e}")
        raise


async def _store_bridge_embeddings_in_vector_db(document_id: str, bridges: List[Dict[str, Any]], document_title: Optional[str] = None):
    """Store bridge chunk embeddings in vector database (Milvus or OpenSearch).
    
    Bridge chunks are stored with special metadata to distinguish them from regular chunks,
    enabling bridge-specific search and retrieval for context continuity.
    
    The bridge ID must be a valid UUID that was generated by the chunking framework.
    This ensures consistency between PostgreSQL and Milvus storage.
    """
    try:
        import uuid as uuid_module

        from ..clients.database_factory import DatabaseClientFactory
        from ..clients.model_server_client import initialize_model_client
        from ..config.config_factory import get_database_config

        # Get database configuration (auto-detects local vs AWS)
        config = get_database_config()
        factory = DatabaseClientFactory(config)
        
        # Get vector client (Milvus for local, OpenSearch for AWS)
        vector_client = factory.get_vector_client()
        
        # Connect to vector database
        await vector_client.connect()
        
        # Initialize model server client for embedding generation
        # This is required in Celery worker context where the client isn't pre-initialized
        model_client = await initialize_model_client()
        if model_client and model_client.enabled:
            vector_client._model_server_client = model_client
            vector_client._embedding_dimension = 768  # Default for bge-base-en-v1.5
            logger.info("Model server client initialized for bridge embeddings in Celery worker")
        
        # Prepare bridge chunks for vector storage
        vector_bridges = []
        for i, bridge in enumerate(bridges):
            # Use existing bridge UUID if available, otherwise generate one
            bridge_id = bridge.get('id')
            if bridge_id:
                # Validate that bridge ID is a valid UUID
                try:
                    uuid_module.UUID(bridge_id)
                except (ValueError, TypeError):
                    raise ValueError(f"Bridge ID must be a valid UUID, got: {bridge_id}")
            else:
                # Generate UUID for backward compatibility with bridges that don't have IDs
                bridge_id = str(uuid_module.uuid4())
                logger.warning(f"Bridge at index {i} missing 'id' field, generated UUID: {bridge_id}")
            
            vector_bridge = {
                'id': bridge_id,
                'content': bridge['content'],
                'metadata': {
                    'source_id': document_id,
                    'chunk_type': 'bridge',
                    'is_bridge': True,
                    'bridge_index': i,
                    'source_chunks': ','.join(bridge.get('source_chunks', [])),
                    'generation_method': bridge.get('generation_method', 'unknown'),
                    'confidence_score': bridge.get('confidence_score', 0.0),
                    'section': f"BRIDGE_{i}",  # Special prefix for bridge identification
                    'title': document_title or 'Untitled Document',
                    'document_title': document_title or 'Untitled Document',
                }
            }
            vector_bridges.append(vector_bridge)
        
        # Store bridge embeddings (vector client handles embedding generation)
        await vector_client.store_embeddings(vector_bridges)
        
        logger.info(f"Stored {len(vector_bridges)} bridge embeddings in vector database for document {document_id}")
        
    except Exception as e:
        logger.error(f"Error storing bridge embeddings in vector database: {e}")
        raise


@celery_app.task(name='update_knowledge_graph_task', time_limit=TASK_HARD_TIME_LIMIT, soft_time_limit=TASK_SOFT_TIME_LIMIT, acks_late=False)
@redis_task_lock("kg_lock:{document_id}")
def update_knowledge_graph_task(upstream_result: Dict[str, Any], document_id: str):
    """
    Update knowledge graph with document concepts.
    
    Args:
        upstream_result: Minimal result from previous task (contains document_id only)
        document_id: Document identifier
    """
    try:
        import time as _time
        _t0 = _time.monotonic()
        from uuid import UUID

        from ..database.connection import db_manager
        
        logger.info(f"Updating knowledge graph for document {document_id}")
        
        _check_document_deleted(document_id, "update_knowledge_graph start")
        
        # Initialize database if needed
        if not db_manager.AsyncSessionLocal:
            db_manager.initialize()
        
        # Retrieve processed document from PostgreSQL (no longer passed via broker)
        processed_document = asyncio.run(
            _retrieve_processing_payload(document_id)
        )
        
        # Update progress — KG runs in parallel with bridges
        pct = _set_parallel_progress(document_id, 'kg', 0.0)
        asyncio.run(_update_job_status_sync(
            UUID(document_id), 'running', pct, _get_parallel_step_label(document_id)
        ))
        
        # Process chunks through knowledge graph builder
        kg_failures = asyncio.run(_update_knowledge_graph(document_id, processed_document['chunks']))
        
        logger.info(f"Knowledge graph updated for document {document_id}")
        
        asyncio.run(_record_stage_timing(document_id, "update_knowledge_graph", _time.monotonic() - _t0))
        return {'status': 'completed', 'document_id': document_id, 'kg_failures': kg_failures}
        
    except DocumentDeletedError:
        logger.info(f"KG update aborted — document {document_id} was deleted")
        return {'status': 'aborted', 'document_id': document_id}
    except Exception as e:
        logger.error(f"Knowledge graph update failed for document {document_id}: {e}")
        # KG failure is fatal — re-raise to fail the entire processing pipeline
        raise


async def _execute_with_retry(client, query, params, max_retries=3):
    """Execute a Neo4j query with exponential backoff retry on failure.

    After exhausting retries, logs a warning and returns None (matching
    the existing behaviour of bare try/except blocks around MERGE ops).
    """
    for attempt in range(1, max_retries + 1):
        try:
            return await client.execute_query(query, params)
        except Exception as e:
            if attempt >= max_retries:
                logger.warning(
                    f"Query failed after {max_retries} retries: {e}"
                )
                return None
            backoff = 2 ** (attempt - 1)  # 1s, 2s, 4s
            logger.warning(
                f"Query attempt {attempt}/{max_retries} failed, "
                f"retrying in {backoff}s: {e}"
            )
            await asyncio.sleep(backoff)


async def _update_knowledge_graph(document_id: str, chunks: List[Dict[str, Any]]):
    """Update knowledge graph with concepts and relationships from chunks.

    Processes chunks in batches of 50 with concurrent extraction and
    **incremental persistence** — each batch's concepts and relationships
    are persisted to Neo4j immediately so that progress is not lost if the
    Celery task hits the soft time limit.

    BUG FIX: ConceptNet relationships returned by the validator use concept
    *names* (e.g. "machine learning") as subject/object, while pattern-based
    relationships use concept *IDs* (e.g. "multi_word_machine_learning").
    We now maintain a ``concept_name_to_id`` reverse map so both kinds of
    relationship endpoints can be resolved to Neo4j node IDs.
    """
    kg_service = None  # Defined early so the finally block can always reference it
    try:
        from ..components.knowledge_graph.kg_builder import KnowledgeGraphBuilder
        from ..models.core import ContentType, KnowledgeChunk, SourceType
        from ..services.knowledge_graph_service import KnowledgeGraphService

        # Initialize knowledge graph service and connect
        kg_service = KnowledgeGraphService()
        await kg_service.client.connect()

        # Pass the Neo4j client to KnowledgeGraphBuilder for ConceptNet
        # validation. If ConceptNet data hasn't been imported, the
        # validator will simply find no matches and concepts pass through
        # the NER/pattern tiers instead.
        neo4j_client = None
        try:
            neo4j_client = kg_service.client
            # Quick probe: check if ConceptNet index exists
            probe = await neo4j_client.execute_query(
                "MATCH (c:ConceptNetConcept) RETURN c LIMIT 1", {}
            )
            if not probe:
                logger.warning(
                    "No ConceptNet data found in Neo4j; "
                    "validation gate will rely on NER/pattern tiers only"
                )
        except Exception as e:
            logger.warning(
                f"ConceptNet data unavailable, skipping validation: {e}"
            )
            neo4j_client = None

        kg_builder = KnowledgeGraphBuilder(neo4j_client=neo4j_client)

        # Initialize UMLS linker for concept-to-CUI annotation.
        # Degrades gracefully: if UMLS data isn't loaded, link_concepts()
        # is a fast no-op that returns concepts unchanged.
        umls_linker = None
        try:
            from ..components.knowledge_graph.umls_client import UMLSClient
            from ..components.knowledge_graph.umls_linker import UMLSLinker

            umls_client = UMLSClient(neo4j_client=kg_service.client)
            await umls_client.initialize()
            if await umls_client.is_available():
                umls_linker = UMLSLinker(umls_client=umls_client)
                logger.info("UMLS linker initialized for KG extraction")
            else:
                logger.info("UMLS data not loaded; skipping UMLS linking")
        except Exception as e:
            logger.warning(f"UMLS linker initialization failed, skipping: {e}")

        # Obtain model server client for embedding generation.
        # IMPORTANT: Always call initialize_model_client() here instead of
        # get_model_client().  Earlier asyncio.run() calls in this Celery
        # task (e.g. _store_embeddings_in_vector_db) leave a stale global
        # _model_client whose aiohttp session is bound to a now-dead event
        # loop.  get_model_client() would return that zombie client, which
        # silently fails on subsequent batches.  initialize_model_client()
        # closes the old client and creates a fresh one on the current loop.
        model_client = None
        try:
            from ..clients.model_server_client import initialize_model_client

            model_client = await initialize_model_client()
            if model_client and not model_client.enabled:
                model_client = None
            if model_client:
                logger.info(
                    f"Model server client ready for KG embeddings: "
                    f"{model_client.base_url} (enabled={model_client.enabled})"
                )
        except Exception as e:
            logger.warning(f"Model server client unavailable: {e}")

        # Batch processing configuration — scale down for large documents
        # to avoid Neo4j OOM from oversized UNWIND transactions.
        # Scale factor: every 1000 chunks doubles the divisor.
        # E.g. 3333 chunks → scale=3 → BATCH_SIZE=33, CONCEPT/REL=166
        # NOTE: MAX_CONCURRENT is no longer used for semaphore-based throttling.
        # Concurrency is now managed by the shared Ollama pool (ollama_pool_manager).

        # Persistent maps across batches — concepts may be referenced by
        # relationships in later batches.
        concept_id_map = {}       # concept_id  -> Neo4j node id
        concept_name_to_id = {}   # lowered concept_name -> concept_id
        all_concept_ids = []      # for enrichment at the end
        total_concepts_persisted = 0
        total_relationships_persisted = 0

        # Convert all chunks to KnowledgeChunk objects first
        knowledge_chunks = []
        for chunk in chunks:
            chunk_type = chunk.get('chunk_type', 'general')
            try:
                content_type = ContentType(chunk_type)
            except ValueError:
                content_type = ContentType.GENERAL

            knowledge_chunk = KnowledgeChunk(
                id=chunk['id'],
                content=chunk['content'],
                source_type=SourceType.BOOK,
                source_id=document_id,
                location_reference=str(chunk.get('chunk_index', 0)),
                section=chunk.get('metadata', {}).get('section', ''),
                content_type=content_type
            )
            knowledge_chunks.append(knowledge_chunk)

        total_chunks = len(knowledge_chunks)

        # Quality gate failure counters
        ner_failure_count = 0
        llm_failure_count = 0

        # Dynamic batch scaling: scale_factor grows with document size.
        # Extraction and Neo4j persistence are DECOUPLED:
        #
        # EXTRACT_BATCH_SIZE — how many chunks to extract concurrently
        #   per iteration.  Extraction is pure Ollama/spaCy (no Neo4j),
        #   so larger batches are fine — concurrency is managed by the
        #   shared Ollama pool.  Scales gently: for very large documents
        #   we still avoid accumulating too many
        #   concepts in memory before persisting.
        #
        # _NEO4J_SUB_BATCH — how many concepts/relationships per
        #   UNWIND transaction.  Scales down aggressively with
        #   document size to prevent Neo4j OOM.
        _scale_factor = max(1, total_chunks // 1000)

        # Extraction batch: start at 100, scale down slowly
        # (÷ sqrt of scale_factor so it stays large)
        import math as _math
        EXTRACT_BATCH_SIZE = max(
            20,
            int(100 / _math.sqrt(_scale_factor))
        )

        # Neo4j sub-batch: scale down aggressively (original formula)
        _NEO4J_SUB_BATCH = max(25, 100 // _scale_factor)

        total_batches = (
            (total_chunks + EXTRACT_BATCH_SIZE - 1)
            // EXTRACT_BATCH_SIZE
        )
        logger.info(
            f"Processing {total_chunks} chunks in "
            f"{total_batches} batches "
            f"(extract_batch={EXTRACT_BATCH_SIZE}, "
            f"neo4j_sub_batch={_NEO4J_SUB_BATCH}, "
            f"scale_factor={_scale_factor}) for KG extraction"
        )

        for batch_start in range(0, total_chunks, EXTRACT_BATCH_SIZE):
            batch_end = min(
                batch_start + EXTRACT_BATCH_SIZE, total_chunks
            )
            batch = knowledge_chunks[batch_start:batch_end]
            batch_num = (
                batch_start // EXTRACT_BATCH_SIZE + 1
            )

            # Check if document was deleted mid-processing
            if await _is_document_deleted(document_id):
                logger.warning(
                    f"Document {document_id} deleted during KG processing "
                    f"(detected at batch {batch_num}/{total_batches}). Aborting."
                )
                return {
                    'ner_failures': ner_failure_count,
                    'llm_failures': llm_failure_count,
                    'total_chunks': total_chunks,
                }

            # --- Extract concepts & relationships concurrently (NO per-chunk ConceptNet) ---
            # Use asyncio.Semaphore for overall chunk concurrency.  The actual
            # Ollama call inside each chunk's extraction is submitted through
            # the shared pool (task_type="kg") for fair share with bridging.
            # NER, regex, and model-server calls stay on this event loop.
            import os as _os
            _kg_concurrency = int(_os.environ.get('OLLAMA_NUM_PARALLEL', '16'))
            _kg_semaphore = asyncio.Semaphore(_kg_concurrency)

            async def process_chunk_with_semaphore(chunk: KnowledgeChunk):
                """Process chunk with semaphore-limited concurrency."""
                async with _kg_semaphore:
                    return await kg_builder.process_knowledge_chunk_extract_only(chunk)

            tasks = [process_chunk_with_semaphore(chunk) for chunk in batch]
            extractions = await asyncio.gather(*tasks, return_exceptions=True)

            batch_concepts = []
            batch_relationships = []
            for i, extraction in enumerate(extractions):
                if isinstance(extraction, BaseException):
                    logger.warning(
                        f"KG extraction failed for chunk "
                        f"{batch_start + i}: "
                        f"{type(extraction).__name__}: {extraction}"
                    )
                    # Only count as model failures if it's a
                    # connection/timeout error.  Generic exceptions
                    # (CancelledError, ValueError, etc.) are not
                    # model-server outages.
                    exc_name = type(extraction).__name__
                    if any(kw in exc_name.lower() for kw in (
                        'connection', 'timeout', 'unavailable',
                    )):
                        ner_failure_count += 1
                        llm_failure_count += 1
                    continue
                # Unpack (ConceptExtraction, ner_failed, llm_failed) tuple
                concept_extraction, ner_failed, llm_failed = extraction
                if ner_failed:
                    ner_failure_count += 1
                if llm_failed:
                    llm_failure_count += 1
                batch_concepts.extend(concept_extraction.extracted_concepts)
                batch_relationships.extend(concept_extraction.extracted_relationships)

            # --- Batch-level ConceptNet validation (2 Neo4j queries per batch) ---
            validated_concepts, conceptnet_rels, _val_stats = \
                await kg_builder.validate_batch_concepts(batch_concepts)
            batch_concepts = validated_concepts
            batch_relationships.extend(conceptnet_rels)

            # --- UMLS concept linking (annotate with CUI + semantic type) ---
            if umls_linker is not None:
                try:
                    batch_concepts = await umls_linker.link_concepts(batch_concepts)
                except Exception as e:
                    logger.warning(f"UMLS linking failed for batch {batch_num}: {e}")

            # --- Generate embeddings for this batch's concepts ---
            # The model server accepts max 1000 texts per request, but KG
            # batches can produce 2000+ concepts.  Sub-batch into groups of
            # 500 to stay well within the limit.
            # Retry with exponential backoff to handle transient model
            # server disconnects that previously caused 818 missing embeddings.
            EMBED_BATCH = 500
            EMBED_MAX_RETRIES = 3
            concept_embeddings = {}
            if batch_concepts and model_client:
                names = [c.concept_name for c in batch_concepts]
                for eb_start in range(0, len(names), EMBED_BATCH):
                    eb_end = min(eb_start + EMBED_BATCH, len(names))
                    sub_names = names[eb_start:eb_end]
                    for attempt in range(1, EMBED_MAX_RETRIES + 1):
                        try:
                            embeddings = await model_client.generate_embeddings(sub_names)
                            if embeddings and len(embeddings) == len(sub_names):
                                for concept, emb in zip(
                                    batch_concepts[eb_start:eb_end], embeddings
                                ):
                                    concept_embeddings[concept.concept_id] = emb
                                break  # success
                            else:
                                logger.warning(
                                    f"Embedding count mismatch (attempt {attempt}/{EMBED_MAX_RETRIES}): "
                                    f"got {len(embeddings) if embeddings else 0} "
                                    f"for {len(sub_names)} concepts"
                                )
                        except Exception as e:
                            logger.warning(
                                f"Failed to generate concept embeddings "
                                f"(sub-batch {eb_start}-{eb_end}, "
                                f"attempt {attempt}/{EMBED_MAX_RETRIES}): {e}"
                            )
                        if attempt < EMBED_MAX_RETRIES:
                            backoff = 2 ** (attempt - 1)  # 1s, 2s
                            logger.info(f"Retrying embedding sub-batch in {backoff}s...")
                            await asyncio.sleep(backoff)
                        else:
                            logger.error(
                                f"Exhausted {EMBED_MAX_RETRIES} retries for embedding "
                                f"sub-batch {eb_start}-{eb_end} "
                                f"({len(sub_names)} concepts will lack embeddings)"
                            )

            # --- Persist concepts incrementally (batched UNWIND) ---
            now_ts = datetime.utcnow().isoformat()

            # --- Step 1: MERGE Chunk nodes for this batch ---
            # Collect unique (chunk_id, source_id) pairs from the batch's KnowledgeChunk objects
            chunk_rows = []
            seen_chunk_ids = set()
            for kc in batch:
                if kc.id not in seen_chunk_ids:
                    seen_chunk_ids.add(kc.id)
                    chunk_rows.append({
                        'chunk_id': kc.id,
                        'source_id': kc.source_id,
                        'created_at': now_ts,
                    })

            if chunk_rows:
                for sub_start in range(0, len(chunk_rows), _NEO4J_SUB_BATCH):
                    sub_batch = chunk_rows[sub_start:sub_start + _NEO4J_SUB_BATCH]
                    await _execute_with_retry(
                        kg_service.client,
                        """
                        UNWIND $rows AS row
                        MERGE (ch:Chunk {chunk_id: row.chunk_id})
                        ON CREATE SET ch.source_id = row.source_id,
                                      ch.created_at = row.created_at
                        RETURN ch.chunk_id AS chunk_id
                        """,
                        {'rows': sub_batch}
                    )

            # --- Step 2: MERGE Concept nodes (no source_chunks/source_document) ---
            new_concept_rows = []
            for concept in batch_concepts:
                if concept.concept_id in concept_id_map:
                    continue
                row = {
                    'concept_id': concept.concept_id,
                    'name': concept.concept_name,
                    'type': concept.concept_type,
                    'confidence': concept.confidence,
                    'created_at': now_ts,
                    'updated_at': now_ts,
                }
                embedding = concept_embeddings.get(concept.concept_id)
                if embedding is not None:
                    row['embedding'] = embedding
                new_concept_rows.append(row)

            # Batch MERGE new concepts (dynamically scaled sub-batches)
            CONCEPT_BATCH_SIZE = _NEO4J_SUB_BATCH
            for sub_start in range(0, len(new_concept_rows), CONCEPT_BATCH_SIZE):
                sub_batch = new_concept_rows[sub_start:sub_start + CONCEPT_BATCH_SIZE]
                # Separate rows with/without embeddings (different SET clauses)
                rows_with_emb = [r for r in sub_batch if 'embedding' in r]
                rows_no_emb = [r for r in sub_batch if 'embedding' not in r]

                if rows_no_emb:
                    result = await _execute_with_retry(
                        kg_service.client,
                        """
                        UNWIND $rows AS row
                        MERGE (c:Concept {concept_id: row.concept_id})
                        ON CREATE SET c.name = row.name, c.type = row.type,
                                      c.concept_type = row.type,
                                      c.confidence = row.confidence,
                                      c.name_lower = toLower(row.name),
                                      c.created_at = row.created_at,
                                      c.updated_at = row.updated_at
                        ON MATCH SET c.updated_at = row.updated_at,
                                     c.concept_type = CASE WHEN c.concept_type IS NULL
                                                      THEN row.type
                                                      ELSE c.concept_type END,
                                     c.name_lower = CASE WHEN c.name_lower IS NULL
                                                    THEN toLower(row.name)
                                                    ELSE c.name_lower END
                        RETURN c.concept_id AS concept_id, elementId(c) AS node_id
                        """,
                        {'rows': rows_no_emb}
                    )
                    for rec in (result or []):
                        cid = rec['concept_id']
                        nid = rec['node_id']
                        concept_id_map[cid] = nid
                        total_concepts_persisted += 1

                if rows_with_emb:
                    result = await _execute_with_retry(
                        kg_service.client,
                        """
                        UNWIND $rows AS row
                        MERGE (c:Concept {concept_id: row.concept_id})
                        ON CREATE SET c.name = row.name, c.type = row.type,
                                      c.concept_type = row.type,
                                      c.confidence = row.confidence,
                                      c.embedding = row.embedding,
                                      c.name_lower = toLower(row.name),
                                      c.created_at = row.created_at,
                                      c.updated_at = row.updated_at
                        ON MATCH SET c.updated_at = row.updated_at,
                                     c.concept_type = CASE WHEN c.concept_type IS NULL
                                                      THEN row.type
                                                      ELSE c.concept_type END,
                                     c.name_lower = CASE WHEN c.name_lower IS NULL
                                                    THEN toLower(row.name)
                                                    ELSE c.name_lower END
                        RETURN c.concept_id AS concept_id, elementId(c) AS node_id
                        """,
                        {'rows': rows_with_emb}
                    )
                    for rec in (result or []):
                        cid = rec['concept_id']
                        nid = rec['node_id']
                        concept_id_map[cid] = nid
                        total_concepts_persisted += 1

            # Update reverse name map for all new concepts
            for concept in batch_concepts:
                if concept.concept_id in concept_id_map and concept.concept_id not in all_concept_ids:
                    concept_name_to_id[concept.concept_name.lower()] = concept.concept_id
                    all_concept_ids.append(concept.concept_id)

            # --- Step 3: MERGE EXTRACTED_FROM relationships (Concept -> Chunk) ---
            ef_rows = []
            for concept in batch_concepts:
                if concept.concept_id not in concept_id_map:
                    continue
                for chunk_id in (concept.source_chunks or []):
                    if chunk_id:
                        ef_rows.append({
                            'concept_id': concept.concept_id,
                            'chunk_id': chunk_id,
                            'created_at': now_ts,
                        })

            EF_BATCH_SIZE = _NEO4J_SUB_BATCH
            for sub_start in range(0, len(ef_rows), EF_BATCH_SIZE):
                sub_batch = ef_rows[sub_start:sub_start + EF_BATCH_SIZE]
                await _execute_with_retry(
                    kg_service.client,
                    """
                    UNWIND $rows AS row
                    MATCH (c:Concept {concept_id: row.concept_id})
                    MATCH (ch:Chunk {chunk_id: row.chunk_id})
                    MERGE (c)-[r:EXTRACTED_FROM]->(ch)
                    ON CREATE SET r.created_at = row.created_at
                    RETURN count(r) AS cnt
                    """,
                    {'rows': sub_batch}
                )

            # --- Persist relationships incrementally (batched UNWIND) ---
            # Group relationships by type (Neo4j requires static rel types in queries)
            import re as _re
            rels_by_type: Dict[str, list] = {}
            for relationship in batch_relationships:
                from_node_id = concept_id_map.get(relationship.subject_concept)
                if from_node_id is None:
                    resolved_id = concept_name_to_id.get(relationship.subject_concept.lower())
                    if resolved_id:
                        from_node_id = concept_id_map.get(resolved_id)

                to_node_id = concept_id_map.get(relationship.object_concept)
                if to_node_id is None:
                    resolved_id = concept_name_to_id.get(relationship.object_concept.lower())
                    if resolved_id:
                        to_node_id = concept_id_map.get(resolved_id)

                if from_node_id and to_node_id:
                    sanitized = _re.sub(r'[^A-Za-z0-9_]', '_', relationship.predicate)
                    rels_by_type.setdefault(sanitized, []).append({
                        'from_id': str(from_node_id),
                        'to_id': str(to_node_id),
                        'confidence': relationship.confidence,
                        'evidence_chunks': ','.join(relationship.evidence_chunks) if relationship.evidence_chunks else '',
                        'source_document': document_id,
                        'created_at': now_ts,
                    })

            REL_BATCH_SIZE = _NEO4J_SUB_BATCH
            for rel_type, rel_rows in rels_by_type.items():
                for sub_start in range(0, len(rel_rows), REL_BATCH_SIZE):
                    sub_batch = rel_rows[sub_start:sub_start + REL_BATCH_SIZE]
                    result = await _execute_with_retry(
                        kg_service.client,
                        f"""
                        UNWIND $rows AS row
                        MATCH (a) WHERE elementId(a) = row.from_id
                        MATCH (b) WHERE elementId(b) = row.to_id
                        MERGE (a)-[r:{rel_type}]->(b)
                        ON CREATE SET r.confidence = row.confidence,
                                      r.evidence_chunks = row.evidence_chunks,
                                      r.source_document = row.source_document,
                                      r.created_at = row.created_at
                        ON MATCH SET r.confidence = row.confidence
                        RETURN count(r) AS cnt
                        """,
                        {'rows': sub_batch}
                    )
                    if result:
                        cnt = result[0]['cnt'] if result else 0
                        total_relationships_persisted += cnt

            logger.info(
                f"KG batch {batch_num}/{total_batches}: "
                f"{len(batch)} chunks → {len(batch_concepts)} concepts, "
                f"{len(batch_relationships)} relationships (persisted)"
            )

            # Send live stats via WebSocket after each batch
            # Keep progress at 70% during parallel phase — metadata tells the real story
            fraction = batch_num / total_batches
            pct = _set_parallel_progress(document_id, 'kg', fraction)
            await _update_job_status_sync(
                UUID(document_id), 'running', pct,
                _get_parallel_step_label(document_id),
                metadata={
                    'kg_batch': batch_num,
                    'kg_total_batches': total_batches,
                    'concepts': total_concepts_persisted,
                    'relationships': total_relationships_persisted,
                    'chunks_processed': batch_end,
                    'total_chunks': total_chunks,
                }
            )

        logger.info(
            f"KG complete: persisted {total_concepts_persisted} concepts and "
            f"{total_relationships_persisted} relationships for document {document_id}"
        )

        # --- Create SAME_AS edges between Concept and UMLSConcept nodes ---
        if umls_linker is not None:
            try:
                from ..components.knowledge_graph.umls_bridger import UMLSBridger

                umls_bridger = UMLSBridger(neo4j_client=kg_service.client)
                # Incremental bridging: only bridge concepts from this document
                doc_concept_names = list(concept_name_to_id.keys())
                bridge_result = await umls_bridger.bridge_concepts(doc_concept_names)
                logger.info(
                    f"UMLS bridging complete for document {document_id}: "
                    f"{bridge_result.concepts_matched} matched, "
                    f"{bridge_result.same_as_edges_created} SAME_AS edges, "
                    f"{bridge_result.unmatched_concepts} unmatched, "
                    f"{bridge_result.elapsed_seconds}s"
                )
            except Exception as e:
                logger.warning(f"UMLS bridging failed for document {document_id}: {e}")

        # Queue background enrichment task
        if all_concept_ids:
            await _create_enrichment_status(document_id, len(all_concept_ids))

            enrich_concepts_task.apply_async(
                args=[document_id, all_concept_ids],
                kwargs={'checkpoint': None},
            )

            logger.info(
                f"Queued background enrichment for document {document_id} "
                f"with {len(all_concept_ids)} concepts"
            )
        else:
            logger.info(f"No concepts to enrich for document {document_id}")

        return {
            'ner_failures': ner_failure_count,
            'llm_failures': llm_failure_count,
            'total_chunks': total_chunks,
        }

    except Exception as e:
        logger.error(f"Error updating knowledge graph: {e}")
        raise
    finally:
        # CRITICAL: Disconnect Neo4j before asyncio.run() tears down the
        # event loop.  If we don't, the driver's internal tasks get
        # cancelled mid-flight and the next asyncio.run() in the same
        # worker thread inherits a poisoned loop state, causing
        # "RuntimeError: Event loop is closed" in the enrichment task.
        if kg_service is not None:
            try:
                await kg_service.client.disconnect()
                logger.debug("Neo4j client disconnected after KG update")
            except Exception:
                pass


async def _enrich_concepts_with_external_knowledge(
    concepts: List[Any],
    document_id: str,
    kg_service: Any
):
    """
    Enrich concepts with YAGO and ConceptNet data.
    
    This function calls the EnrichmentService to:
    - Look up YAGO Q-numbers for concepts
    - Create INSTANCE_OF relationships to external entity classes
    - Store ConceptNet relationships (IsA, PartOf, UsedFor, etc.)
    - Create SAME_AS links for cross-document concept matching
    
    Args:
        concepts: List of ConceptNode objects extracted from document
        document_id: Source document identifier
        kg_service: KnowledgeGraphService instance for Neo4j operations
    """
    if not concepts:
        logger.info(f"No concepts to enrich for document {document_id}")
        return
    
    try:
        from ..services.enrichment_service import EnrichmentService

        # Create enrichment service with KG service injected
        enrichment_service = EnrichmentService(kg_service=kg_service)
        
        # Enrich all concepts
        result = await enrichment_service.enrich_concepts(concepts, document_id)
        
        # Log enrichment statistics
        logger.info(
            f"External enrichment complete for document {document_id}: "
            f"{result.concepts_enriched}/{result.concepts_processed} enriched, "
            f"YAGO: {result.yago_hits}, ConceptNet: {result.conceptnet_hits}, "
            f"Cache hits: {result.cache_hits}, Errors: {len(result.errors)}, "
            f"Duration: {result.duration_ms:.1f}ms"
        )
        
        # Log any errors (but don't fail the pipeline)
        for error in result.errors[:5]:  # Log first 5 errors
            logger.warning(f"Enrichment error: {error}")
        
        if len(result.errors) > 5:
            logger.warning(f"... and {len(result.errors) - 5} more enrichment errors")
            
    except ImportError as e:
        logger.warning(f"EnrichmentService not available: {e}")
    except Exception as e:
        # Don't fail document processing for enrichment errors
        logger.warning(
            f"External enrichment failed for document {document_id}: {e}. "
            "Document processing will continue without enrichment."
        )


@celery_app.task(
    bind=True,
    name='enrich_concepts_task',
    max_retries=3,
    default_retry_delay=60,
    soft_time_limit=3600,  # 60 minutes
    time_limit=3900,  # 65 minutes
    acks_late=True,
    reject_on_worker_lost=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
)
def enrich_concepts_task(
    self,
    document_id: str,
    concept_ids: List[str],
    checkpoint: Optional[Dict] = None
):
    """
    Background task for concept enrichment with external knowledge sources.
    
    This task runs independently from document processing, allowing documents
    to be marked as COMPLETED before enrichment finishes. It supports:
    - Checkpoint-based resumption for failed tasks
    - Rate limiting for YAGO/ConceptNet APIs
    - Batch processing with configurable batch size
    - Circuit breaker deferral when APIs are unavailable
    
    Args:
        document_id: Document being enriched
        concept_ids: List of concept IDs to enrich
        checkpoint: Resume checkpoint from previous attempt (optional)
    
    Returns:
        dict with enrichment results
    """
    from uuid import UUID

    from ..config import get_settings
    from ..models.enrichment_status import EnrichmentResult, EnrichmentState
    from ..services.circuit_breaker import get_circuit_breaker
    
    settings = get_settings()
    
    # Check circuit breaker state before starting
    # If circuit breaker is open, defer the task without counting as a retry
    yago_breaker = get_circuit_breaker("yago")
    if yago_breaker.is_open():
        recovery_time = yago_breaker.get_recovery_time()
        delay = yago_breaker.recovery_timeout
        
        logger.warning(
            f"Circuit breaker is OPEN for document {document_id}. "
            f"Deferring enrichment task for {delay} seconds. "
            f"Recovery expected at: {recovery_time}"
        )
        
        # Requeue the task with delay, but don't count as a retry
        # Use apply_async with countdown to defer
        enrich_concepts_task.apply_async(
            args=[document_id, concept_ids],
            kwargs={'checkpoint': checkpoint},
            countdown=delay,
        )
        
        return {
            "status": "deferred",
            "reason": "circuit_breaker_open",
            "retry_after_seconds": delay,
        }
    
    logger.info(
        f"Starting background enrichment for document {document_id} "
        f"with {len(concept_ids)} concepts"
    )
    
    try:
        # Ensure a clean event loop.  Previous asyncio.run() calls in the
        # same worker thread (e.g. update_knowledge_graph_task) close the
        # thread-local loop.  The Neo4j async driver can cache a reference
        # to that dead loop, so we explicitly install a fresh one before
        # calling asyncio.run().
        try:
            old_loop = asyncio.get_event_loop()
            if old_loop.is_closed():
                asyncio.set_event_loop(asyncio.new_event_loop())
        except RuntimeError:
            # No current event loop — asyncio.run() will create one
            pass

        # Run the async enrichment logic
        result = asyncio.run(_run_background_enrichment(
            document_id=document_id,
            concept_ids=concept_ids,
            checkpoint=checkpoint,
            batch_size=settings.enrichment_batch_size,
            checkpoint_interval=settings.enrichment_checkpoint_interval,
            retry_count=self.request.retries,
        ))
        
        # Self-chain: if the enrichment bailed out before the time limit,
        # re-queue with the checkpoint so it continues in a fresh task
        # invocation.  This does NOT count as a retry.
        if result.get('status') == 'continuation_needed':
            continuation_checkpoint = result['checkpoint']
            remaining = result.get('concepts_remaining', '?')
            logger.info(
                f"Enrichment self-chaining for document {document_id}: "
                f"{remaining} concepts remaining, re-queuing with checkpoint"
            )
            enrich_concepts_task.apply_async(
                args=[document_id, concept_ids],
                kwargs={'checkpoint': continuation_checkpoint},
            )
            return result

        logger.info(
            f"Background enrichment completed for document {document_id}: "
            f"{result.get('concepts_enriched', 0)} enriched"
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Background enrichment failed for document {document_id}: {e}")
        
        # Update enrichment status to failed if max retries exceeded
        if self.request.retries >= self.max_retries:
            asyncio.run(_mark_enrichment_failed(
                document_id=document_id,
                error_message=str(e),
                retry_count=self.request.retries,
            ))
        
        raise


async def _run_background_enrichment(
    document_id: str,
    concept_ids: List[str],
    checkpoint: Optional[Dict],
    batch_size: int,
    checkpoint_interval: int,
    retry_count: int,
    time_limit_seconds: int = 3300,
) -> Dict[str, Any]:
    """
    Run background enrichment with batch processing, checkpointing, and
    self-chaining to avoid hitting the Celery soft time limit.
    
    When elapsed time approaches time_limit_seconds (default 55 min, well
    under the 60-min soft limit), the function saves a checkpoint and
    returns a special {"status": "continuation_needed"} result.  The
    calling Celery task detects this and re-queues itself with the
    checkpoint, allowing enrichment to resume in a fresh task invocation
    without counting as a retry.
    
    Args:
        document_id: Document being enriched
        concept_ids: List of concept IDs to enrich
        checkpoint: Resume checkpoint from previous attempt
        batch_size: Number of concepts per batch
        checkpoint_interval: Save checkpoint every N concepts
        retry_count: Current retry count
        time_limit_seconds: Bail-out threshold in seconds (default 3300 = 55 min)
        
    Returns:
        dict with enrichment results, or {"status": "continuation_needed", ...}
    """
    import time
    from uuid import UUID

    from ..models.enrichment_status import EnrichmentResult, EnrichmentState
    from ..services.knowledge_graph_service import KnowledgeGraphService
    
    start_time = time.time()
    
    # Initialize services
    kg_service = KnowledgeGraphService()
    
    # Health probe with exponential backoff before attempting connection.
    # After a heavy KG write phase, Neo4j may need time to flush transactions
    # and recover. This probe waits for Neo4j to be ready with up to 10 attempts
    # and exponential backoff (1s, 2s, 4s, 8s, 16s, 32s, 64s, 128s, 256s = 511s total ~ 8.5 min).
    # Combined with the 300s (5 min) initial countdown, this gives up to ~13.5 minutes total.
    # This prevents the "connect call failed" errors that occurred when the
    # enrichment task started immediately after KG extraction completed.
    logger.info("Waiting for Neo4j to be ready...")
    max_health_attempts = 10
    for attempt in range(1, max_health_attempts + 1):
        try:
            # Ensure the driver is created before probing
            await kg_service.client.connect()
            # Try a simple query to verify Neo4j is ready
            async with kg_service.client.driver.session(database=kg_service.client.database) as session:
                result = await session.run("RETURN 1 AS test")
                record = await result.single()
                if record and record["test"] == 1:
                    logger.info("Neo4j health check passed")
                    break
        except Exception as e:
            if attempt < max_health_attempts:
                backoff = 2 ** (attempt - 1)
                logger.warning(
                    f"Neo4j health check failed (attempt {attempt}/{max_health_attempts}): {e}. "
                    f"Retrying in {backoff}s..."
                )
                await asyncio.sleep(backoff)
            else:
                logger.error(
                    f"Neo4j health check failed after {max_health_attempts} attempts: {e}"
                )
                raise RuntimeError(
                    f"Neo4j not ready after {max_health_attempts} health check attempts: {e}"
                )
    
    # Connection is already established from the health probe above
    
    # Determine starting point from checkpoint
    start_index = 0
    partial_stats = {
        'yago_hits': 0,
        'conceptnet_hits': 0,
        'cache_hits': 0,
        'errors': 0,
        'concepts_enriched': 0,
    }
    
    if checkpoint:
        start_index = checkpoint.get('last_concept_index', 0) + 1
        partial_stats = checkpoint.get('partial_stats', partial_stats)
        logger.info(f"Resuming enrichment from checkpoint at index {start_index}")
    
    # Update enrichment status to in-progress
    await _update_enrichment_status_in_progress(document_id)
    
    # Get concepts from knowledge graph
    concepts_to_enrich = await _get_concepts_by_ids(kg_service, concept_ids[start_index:])
    
    if not concepts_to_enrich:
        logger.info(f"No concepts to enrich for document {document_id}")
        result = EnrichmentResult(
            concepts_enriched=partial_stats['concepts_enriched'],
            yago_hits=partial_stats['yago_hits'],
            conceptnet_hits=partial_stats['conceptnet_hits'],
            cache_hits=partial_stats['cache_hits'],
            errors=partial_stats['errors'],
            duration_ms=(time.time() - start_time) * 1000,
        )
        await _mark_enrichment_completed(document_id, result)
        return result.to_dict()
    
    # Process concepts in batches
    total_concepts = len(concepts_to_enrich)
    processed_count = 0
    
    try:
        # Initialize model server client for embedding generation on
        # newly created Concept nodes (e.g. ConceptNet relationship targets).
        # Uses initialize_model_client() to get a fresh client on the
        # current event loop, same pattern as _update_knowledge_graph.
        model_client = None
        try:
            from ..clients.model_server_client import initialize_model_client
            model_client = await initialize_model_client()
            if model_client and not model_client.enabled:
                model_client = None
            if model_client:
                logger.info(
                    f"Model server client ready for enrichment embeddings: "
                    f"{model_client.base_url}"
                )
        except Exception as e:
            logger.warning(f"Model server client unavailable for enrichment: {e}")

        from ..services.enrichment_service import EnrichmentService

        # Create YAGO client for enrichment (reuses the same Neo4j connection)
        yago_client = None
        try:
            from ..components.yago.local_client import YagoLocalClient
            yago_client = YagoLocalClient(neo4j_client=kg_service.client)
            if await yago_client.is_available():
                logger.info("YAGO client ready for enrichment")
            else:
                logger.info("YAGO data not available, skipping YAGO enrichment")
                yago_client = None
        except Exception as e:
            logger.warning(f"YAGO client unavailable for enrichment: {e}")

        enrichment_service = EnrichmentService(
            kg_service=kg_service,
            model_client=model_client,
            yago_client=yago_client,
        )
        
        for batch_start in range(0, total_concepts, batch_size):
            # --- Time-limit check: bail out before Celery kills us ---
            elapsed = time.time() - start_time
            if elapsed >= time_limit_seconds:
                logger.warning(
                    f"Enrichment approaching time limit ({elapsed:.0f}s >= "
                    f"{time_limit_seconds}s). Saving checkpoint and requesting "
                    f"continuation. Processed {processed_count}/{total_concepts} "
                    f"concepts this invocation."
                )
                checkpoint_index = start_index + batch_start - 1
                await _save_enrichment_checkpoint(
                    document_id=document_id,
                    last_concept_index=checkpoint_index,
                    concepts_processed=concept_ids[:checkpoint_index + 1],
                    partial_stats=partial_stats,
                )
                return {
                    'status': 'continuation_needed',
                    'checkpoint': {
                        'last_concept_index': checkpoint_index,
                        'partial_stats': partial_stats,
                    },
                    'concepts_remaining': total_concepts - batch_start,
                }

            batch_end = min(batch_start + batch_size, total_concepts)
            batch = concepts_to_enrich[batch_start:batch_end]
            
            # Enrich batch
            batch_result = await enrichment_service.enrich_concepts(batch, document_id)
            
            # Update stats
            partial_stats['yago_hits'] += batch_result.yago_hits
            partial_stats['conceptnet_hits'] += batch_result.conceptnet_hits
            partial_stats['cache_hits'] += batch_result.cache_hits
            partial_stats['errors'] += len(batch_result.errors)
            partial_stats['concepts_enriched'] += batch_result.concepts_enriched
            
            processed_count += len(batch)
            
            # Update progress
            await _update_enrichment_progress(
                document_id=document_id,
                concepts_enriched=partial_stats['concepts_enriched'],
                yago_hits=partial_stats['yago_hits'],
                conceptnet_hits=partial_stats['conceptnet_hits'],
                cache_hits=partial_stats['cache_hits'],
                errors=partial_stats['errors'],
            )
            
            # Save checkpoint at intervals
            if processed_count % checkpoint_interval == 0:
                await _save_enrichment_checkpoint(
                    document_id=document_id,
                    last_concept_index=start_index + batch_end - 1,
                    concepts_processed=concept_ids[:start_index + batch_end],
                    partial_stats=partial_stats,
                )
            
            logger.info(
                f"Enrichment batch {batch_start//batch_size + 1}: "
                f"processed {len(batch)} concepts for document {document_id}"
            )
        
        # Mark enrichment as completed
        duration_ms = (time.time() - start_time) * 1000
        result = EnrichmentResult(
            concepts_enriched=partial_stats['concepts_enriched'],
            yago_hits=partial_stats['yago_hits'],
            conceptnet_hits=partial_stats['conceptnet_hits'],
            cache_hits=partial_stats['cache_hits'],
            errors=partial_stats['errors'],
            duration_ms=duration_ms,
        )
        
        await _mark_enrichment_completed(document_id, result)
        
        return result.to_dict()
        
    except Exception as e:
        # Save checkpoint before failing
        await _save_enrichment_checkpoint(
            document_id=document_id,
            last_concept_index=start_index + processed_count - 1,
            concepts_processed=concept_ids[:start_index + processed_count],
            partial_stats=partial_stats,
        )
        raise
    finally:
        # Disconnect Neo4j so the driver doesn't leave dangling tasks
        # on the event loop that asyncio.run() is about to tear down.
        try:
            await kg_service.client.disconnect()
            logger.debug("Neo4j client disconnected after enrichment")
        except Exception:
            pass


async def _get_concepts_by_ids(kg_service, concept_ids: List[str]) -> List[Any]:
    """Get concept nodes from knowledge graph by IDs using a batch Cypher query."""
    from ..models.knowledge_graph import ConceptNode

    if not concept_ids:
        return []

    try:
        results = await kg_service.client.execute_query(
            "MATCH (c:Concept) WHERE c.concept_id IN $ids "
            "RETURN c.concept_id AS concept_id, c.name AS name, "
            "c.type AS type, c.confidence AS confidence, "
            "c.source_chunks AS source_chunks, c.source_document AS source_document",
            {"ids": concept_ids},
        )

        concepts = []
        for row in results:
            concepts.append(ConceptNode(
                concept_id=row.get("concept_id", ""),
                concept_name=row.get("name", ""),
                concept_type=row.get("type", "ENTITY"),
                confidence=row.get("confidence", 0.0),
                source_chunks=row.get("source_chunks", []) or [],
                source_document=row.get("source_document"),
            ))

        logger.info(f"Batch fetched {len(concepts)} concepts from {len(concept_ids)} IDs")
        return concepts

    except Exception as e:
        logger.error(f"Failed to batch fetch concepts: {e}")
        return []


async def _create_enrichment_status(document_id: str, total_concepts: int) -> None:
    """Create initial enrichment status record for a document."""
    try:
        from ..database.connection import get_async_connection

        # Determine initial state
        state = 'pending' if total_concepts > 0 else 'skipped'
        
        conn = await get_async_connection()
        try:
            await conn.execute("""
                INSERT INTO multimodal_librarian.enrichment_status (
                    document_id, state, total_concepts
                ) VALUES (
                    $1, $2, $3
                )
                ON CONFLICT (document_id) DO UPDATE SET
                    state = $2,
                    total_concepts = $3,
                    concepts_enriched = 0,
                    yago_hits = 0,
                    conceptnet_hits = 0,
                    cache_hits = 0,
                    error_count = 0,
                    retry_count = 0,
                    started_at = NULL,
                    completed_at = NULL,
                    duration_ms = NULL,
                    last_error = NULL,
                    checkpoint_index = NULL,
                    checkpoint_data = NULL
            """, document_id, state, total_concepts)
        finally:
            await conn.close()
        
        logger.info(
            f"Created enrichment status for document {document_id} "
            f"with {total_concepts} concepts, state={state}"
        )
    except Exception as e:
        logger.warning(f"Failed to create enrichment status: {e}")


async def _update_enrichment_status_in_progress(document_id: str) -> None:
    """Update enrichment status to in-progress."""
    try:
        from ..database.connection import get_async_connection
        
        conn = await get_async_connection()
        try:
            await conn.execute("""
                UPDATE multimodal_librarian.enrichment_status
                SET state = 'enriching', started_at = NOW()
                WHERE document_id = $1
            """, document_id)
        finally:
            await conn.close()
    except Exception as e:
        logger.warning(f"Failed to update enrichment status to in-progress: {e}")


async def _update_enrichment_progress(
    document_id: str,
    concepts_enriched: int,
    yago_hits: int,
    conceptnet_hits: int,
    cache_hits: int,
    errors: int,
) -> None:
    """Update enrichment progress in database."""
    try:
        from ..database.connection import get_async_connection
        
        conn = await get_async_connection()
        try:
            await conn.execute("""
                UPDATE multimodal_librarian.enrichment_status
                SET concepts_enriched = $1,
                    yago_hits = $2,
                    conceptnet_hits = $3,
                    cache_hits = $4,
                    error_count = $5
                WHERE document_id = $6
            """, concepts_enriched, yago_hits, conceptnet_hits,
                cache_hits, errors, document_id)
        finally:
            await conn.close()
    except Exception as e:
        logger.warning(f"Failed to update enrichment progress: {e}")


async def _save_enrichment_checkpoint(
    document_id: str,
    last_concept_index: int,
    concepts_processed: List[str],
    partial_stats: Dict[str, int],
) -> None:
    """Save enrichment checkpoint for resumption."""
    import json
    try:
        from ..database.connection import get_async_connection
        
        checkpoint_data = {
            "concepts_processed": concepts_processed,
            "partial_stats": partial_stats,
            "created_at": datetime.utcnow().isoformat(),
        }
        
        conn = await get_async_connection()
        try:
            await conn.execute("""
                UPDATE multimodal_librarian.enrichment_status
                SET checkpoint_index = $1,
                    checkpoint_data = $2::jsonb
                WHERE document_id = $3
            """, last_concept_index, json.dumps(checkpoint_data), document_id)
        finally:
            await conn.close()
        
        logger.debug(f"Saved enrichment checkpoint at index {last_concept_index}")
    except Exception as e:
        logger.warning(f"Failed to save enrichment checkpoint: {e}")


async def _mark_enrichment_completed(document_id: str, result) -> None:
    """Mark enrichment as completed with final stats."""
    try:
        from ..database.connection import get_async_connection

        state = 'completed'
        
        conn = await get_async_connection()
        try:
            await conn.execute("""
                UPDATE multimodal_librarian.enrichment_status
                SET state = $1,
                    concepts_enriched = $2,
                    yago_hits = $3,
                    conceptnet_hits = $4,
                    cache_hits = $5,
                    error_count = $6,
                    duration_ms = $7,
                    completed_at = NOW()
                WHERE document_id = $8
            """, state, result.concepts_enriched, result.yago_hits,
                result.conceptnet_hits, result.cache_hits, result.errors,
                result.duration_ms, document_id)
        finally:
            await conn.close()
        
        logger.info(f"Marked enrichment as {state} for document {document_id}")
    except Exception as e:
        logger.warning(f"Failed to mark enrichment as completed: {e}")


async def _mark_enrichment_failed(
    document_id: str,
    error_message: str,
    retry_count: int,
) -> None:
    """Mark enrichment as failed."""
    try:
        from ..database.connection import get_async_connection
        
        conn = await get_async_connection()
        try:
            await conn.execute("""
                UPDATE multimodal_librarian.enrichment_status
                SET state = 'failed',
                    last_error = $1,
                    retry_count = $2,
                    completed_at = NOW()
                WHERE document_id = $3
            """, error_message, retry_count, document_id)
        finally:
            await conn.close()
        
        logger.error(f"Marked enrichment as failed for document {document_id}: {error_message}")
    except Exception as e:
        logger.warning(f"Failed to mark enrichment as failed: {e}")


# Helper functions for async operations in sync tasks


async def _store_processing_payload(document_id: str, payload: Dict[str, Any]) -> None:
    """Store processed document payload in PostgreSQL instead of passing through Celery broker."""
    import json
    from uuid import UUID as _UUID

    from ..database.connection import get_async_connection
    conn = await get_async_connection()
    try:
        doc_uuid = _UUID(document_id) if isinstance(document_id, str) else document_id
        await conn.execute(
            """
            INSERT INTO multimodal_librarian.processing_payloads (document_id, payload)
            VALUES ($1, $2::jsonb)
            ON CONFLICT (document_id) DO UPDATE SET payload = $2::jsonb, created_at = CURRENT_TIMESTAMP
            """,
            doc_uuid, json.dumps(payload)
        )
        logger.info(f"Stored processing payload for document {document_id}")
    finally:
        await conn.close()


async def _retrieve_processing_payload(document_id: str) -> Dict[str, Any]:
    """Retrieve processed document payload from PostgreSQL."""
    import json
    from uuid import UUID as _UUID

    from ..database.connection import get_async_connection
    conn = await get_async_connection()
    try:
        doc_uuid = _UUID(document_id) if isinstance(document_id, str) else document_id
        row = await conn.fetchrow(
            "SELECT payload FROM multimodal_librarian.processing_payloads WHERE document_id = $1",
            doc_uuid
        )
        if row is None:
            raise ValueError(f"No processing payload found for document {document_id}")
        payload = row['payload']
        # asyncpg returns JSONB as a string or dict depending on version
        if isinstance(payload, str):
            return json.loads(payload)
        return payload
    finally:
        await conn.close()


async def _delete_processing_payload(document_id: str) -> None:
    """Clean up processing payload after processing completes."""
    from uuid import UUID as _UUID

    from ..database.connection import get_async_connection
    conn = await get_async_connection()
    try:
        doc_uuid = _UUID(document_id) if isinstance(document_id, str) else document_id
        await conn.execute(
            "DELETE FROM multimodal_librarian.processing_payloads WHERE document_id = $1",
            doc_uuid
        )
        logger.debug(f"Cleaned up processing payload for document {document_id}")
    finally:
        await conn.close()


async def _compute_composite_scores(document_id: str) -> None:
    """Compute composite scores and create RELATED_DOCS edges for a document."""
    from ..clients.database_factory import get_database_factory
    from ..services.composite_score_engine import CompositeScoreEngine

    factory = get_database_factory()
    client = factory.get_graph_client()
    if not getattr(client, '_is_connected', False):
        await client.connect()

    engine = CompositeScoreEngine(client)
    result = await engine.compute_composite_scores(document_id)
    logger.info(
        f"Composite scores for {document_id}: "
        f"{result.edges_discovered} edges, "
        f"{result.document_pairs} pairs, "
        f"{result.related_docs_created} RELATED_DOCS, "
        f"{result.duration_ms:.0f}ms"
    )


async def _record_stage_timing(document_id, stage: str, duration_seconds: float):
    """Record a pipeline stage's duration in job_metadata.stage_timings."""
    try:
        import json

        from ..database.connection import get_async_connection
        conn = await get_async_connection()
        try:
            await conn.execute("""
                UPDATE multimodal_librarian.processing_jobs
                SET job_metadata = jsonb_set(
                    jsonb_set(
                        COALESCE(job_metadata, '{}'::jsonb),
                        '{stage_timings}',
                        COALESCE(job_metadata->'stage_timings', '{}'::jsonb)
                    ),
                    ARRAY['stage_timings', $1],
                    $2::jsonb
                )
                WHERE source_id = $3::uuid
            """, stage, json.dumps(round(duration_seconds, 2)), str(document_id))
        finally:
            await conn.close()
    except Exception as e:
        logger.warning(f"Failed to record stage timing for {stage}: {e}")


async def _persist_quality_gate_data(document_id, quality_gate_dict: Dict[str, Any]):
    """Persist quality gate evaluation result to job_metadata.quality_gate."""
    try:
        import json

        from ..database.connection import get_async_connection
        conn = await get_async_connection()
        try:
            await conn.execute("""
                UPDATE multimodal_librarian.processing_jobs
                SET job_metadata = jsonb_set(
                    COALESCE(job_metadata, '{}'::jsonb),
                    '{quality_gate}',
                    $1::jsonb
                )
                WHERE source_id = $2::uuid
            """, json.dumps(quality_gate_dict), str(document_id))
        finally:
            await conn.close()
    except Exception as e:
        logger.warning(f"Failed to persist quality gate data for {document_id}: {e}")


async def _update_job_status_sync(document_id, status: str, progress: float,
                                  step: str, error_message: str = None,
                                  failed_stage: str = None,
                                  metadata: Dict[str, Any] = None):
    """Update job status using asyncpg connection for high performance.
    
    Also sends WebSocket notifications via ProcessingStatusService.
    
    Args:
        document_id: Document identifier
        status: Job status (pending, running, completed, failed)
        progress: Progress percentage (0-100)
        step: Human-readable step description
        error_message: Optional error message for failures
        failed_stage: Optional stage name where processing failed (for retry support)
    """
    try:
        import json

        from ..database.connection import get_async_connection

        conn = await get_async_connection()
        try:
            update_fields = [
                "status = $1",
                "progress_percentage = $2",
                "current_step = $3"
            ]
            params = [status, progress, step]
            param_idx = 4

            if error_message:
                update_fields.append(f"error_message = ${param_idx}")
                params.append(error_message)
                param_idx += 1

            if status == 'running':
                update_fields.append("started_at = COALESCE(started_at, NOW())")
            elif status in ['completed', 'failed']:
                update_fields.append("completed_at = NOW()")
            
            # Store failed stage in job_metadata for retry support
            # Requirements: 8.4 - Track failed stage in processing metadata
            if status == 'failed' and failed_stage:
                update_fields.append(f"job_metadata = jsonb_set(COALESCE(job_metadata, '{{}}'::jsonb), '{{failed_stage}}', ${param_idx}::jsonb)")
                params.append(json.dumps(failed_stage))
                param_idx += 1

            update_clause = ", ".join(update_fields)
            params.append(str(document_id))

            # Guard: don't let a 'running' update overwrite a terminal
            # status ('completed' or 'failed').  This prevents a parallel
            # subtask's progress update from clobbering the failure status
            # set by another subtask's error handler.
            status_guard = ""
            if status == 'running':
                status_guard = " AND status NOT IN ('completed', 'failed')"

            await conn.execute(f"""
                UPDATE multimodal_librarian.processing_jobs
                SET {update_clause}
                WHERE source_id = ${param_idx}{status_guard}
            """, *params)
        finally:
            await conn.close()
        
        # Send WebSocket notification via ProcessingStatusService
        # Requirements: 3.1, 3.2, 3.3, 3.4
        try:
            from .processing_status_integration import notify_processing_status_update
            await notify_processing_status_update(
                document_id=document_id,
                status=status,
                progress_percentage=progress,
                current_step=step,
                error_message=error_message,
                metadata=metadata
            )
        except Exception as ws_error:
            # Don't fail the job if WebSocket notification fails
            logger.debug(f"WebSocket notification failed (non-critical): {ws_error}")

    except Exception as e:
        logger.error(f"Error updating job status: {e}")


async def _update_document_status_sync(document_id, status, 
                                     error_message: str = None):
    """Update document status using direct asyncpg connection.
    
    Uses get_async_connection() which creates a fresh connection each time,
    avoiding event loop issues when called from multiple asyncio.run() calls
    in Celery tasks.
    
    Updates multimodal_librarian.knowledge_sources instead of public.documents.
    """
    try:
        from ..database.connection import get_async_connection

        conn = await get_async_connection()
        try:
            # Get status value (handle both enum and string)
            status_value = status.value if hasattr(status, 'value') else str(status)
            
            # Map status to processing_status enum values
            status_mapping = {
                'uploaded': 'PENDING',
                'processing': 'PROCESSING',
                'completed': 'COMPLETED',
                'failed': 'FAILED',
                'pending': 'PENDING'
            }
            processing_status = status_mapping.get(status_value.lower(), status_value.upper())
            
            # Build update query for knowledge_sources
            if error_message:
                # Store error in metadata JSON
                await conn.execute("""
                    UPDATE multimodal_librarian.knowledge_sources 
                    SET processing_status = $1::multimodal_librarian.processing_status, 
                        metadata = jsonb_set(COALESCE(metadata, '{}'::jsonb), '{processing_error}', to_jsonb($2::text)),
                        updated_at = NOW()
                    WHERE id = $3::uuid
                """, processing_status, error_message, str(document_id))
            else:
                await conn.execute("""
                    UPDATE multimodal_librarian.knowledge_sources 
                    SET processing_status = $1::multimodal_librarian.processing_status,
                        updated_at = NOW()
                    WHERE id = $2::uuid
                """, processing_status, str(document_id))
            
            logger.info(f"Document status updated: {document_id} -> {processing_status}")
        finally:
            await conn.close()
            
    except Exception as e:
        logger.error(f"Error updating document status {document_id}: {e}")


async def _delete_document_chunks(document_id: str) -> int:
    """Delete existing chunks for a document from both PostgreSQL and vector database.

    This function is used for document reprocessing support. It removes all
    existing chunks before new ones are stored, ensuring clean reprocessing
    without duplicate or orphaned chunks.

    Deletes from multimodal_librarian.knowledge_chunks using source_id.

    Args:
        document_id: The document ID (source_id) to delete chunks for

    Returns:
        Total number of chunks deleted (PostgreSQL + vector database)

    Raises:
        Exception: If deletion fails in either storage system
    """
    total_deleted = 0

    try:
        logger.info(f"Deleting existing chunks for document {document_id}")

        # Step 1: Delete from PostgreSQL (unified schema)
        from ..database.connection import get_async_connection

        conn = await get_async_connection()
        try:
            # Delete chunks from knowledge_chunks table using source_id
            result = await conn.execute("""
                DELETE FROM multimodal_librarian.knowledge_chunks
                WHERE source_id = $1::uuid
            """, document_id)

            # Parse the result to get deleted count (format: "DELETE N")
            pg_deleted = 0
            if result:
                parts = result.split()
                if len(parts) >= 2 and parts[0] == 'DELETE':
                    try:
                        pg_deleted = int(parts[1])
                    except ValueError:
                        pass

            total_deleted += pg_deleted
            logger.info(f"Deleted {pg_deleted} chunks from PostgreSQL for document {document_id}")
        finally:
            await conn.close()

        # Step 2: Delete from vector database (Milvus or OpenSearch)
        from ..clients.database_factory import DatabaseClientFactory
        from ..config.config_factory import get_database_config

        config = get_database_config()
        factory = DatabaseClientFactory(config)
        vector_client = factory.get_vector_client()

        await vector_client.connect()

        try:
            # Use the delete_chunks_by_source method which filters by source_id
            vector_deleted = await vector_client.delete_chunks_by_source(document_id)
            total_deleted += vector_deleted
            logger.info(f"Deleted {vector_deleted} chunks from vector database for document {document_id}")
        except Exception as e:
            # Log but don't fail if vector deletion fails (collection might not exist)
            logger.warning(f"Vector database deletion warning for document {document_id}: {e}")

        logger.info(f"Total deleted: {total_deleted} chunks for document {document_id}")
        return total_deleted

    except Exception as e:
        logger.error(f"Error deleting chunks for document {document_id}: {e}")
        raise


async def _store_chunks_in_database(document_id: str, chunks: List[Dict[str, Any]],
                                    total_pages: int = 0):
    """Store chunks in unified schema using the chunk's existing UUID.

    The chunk ID must be a valid UUID that was generated by the chunking framework.
    This ensures consistency between PostgreSQL and vector database storage.

    Stores chunks in multimodal_librarian.knowledge_chunks with:
    - source_type set to 'BOOK' for PDF-derived chunks
    - content_hash computed as SHA-256 of content
    - Fields mapped according to unified schema structure
    
    Sends incremental progress updates via WebSocket every ~5 seconds.
    """
    try:
        import hashlib
        import json
        import time
        import uuid
        from uuid import UUID

        from ..database.connection import get_async_connection

        def compute_content_hash(content: str) -> str:
            """Compute SHA-256 hash of content for deduplication."""
            return hashlib.sha256(content.encode('utf-8')).hexdigest()

        def map_chunk_type_to_content_type(chunk_type: str) -> str:
            """Map chunk_type to content_type enum."""
            mapping = {
                'text': 'GENERAL',
                'image': 'TECHNICAL',
                'table': 'TECHNICAL',
                'chart': 'TECHNICAL'
            }
            return mapping.get(chunk_type, 'GENERAL')

        total_chunks = len(chunks)
        last_update_time = time.monotonic()
        UPDATE_INTERVAL = 5.0  # seconds between progress updates
        max_page_seen = 0

        conn = await get_async_connection()
        try:
            # Use a transaction for batch insert
            async with conn.transaction():
                DELETION_CHECK_INTERVAL = 200  # Check every 200 chunks
                for i, chunk in enumerate(chunks):
                    # Periodically check if document was deleted mid-storage
                    if i > 0 and i % DELETION_CHECK_INTERVAL == 0:
                        if await _is_document_deleted(document_id):
                            logger.info(
                                f"Document {document_id} deleted during chunk storage "
                                f"(chunk {i}/{total_chunks}), aborting."
                            )
                            raise DocumentDeletedError(
                                f"Document {document_id} was deleted during chunk storage"
                            )

                    # Serialize metadata to JSON string if it's a dict
                    metadata = chunk.get('metadata', {})
                    if isinstance(metadata, dict):
                        metadata = json.dumps(metadata)

                    # Map chunk_type to valid content_type values
                    chunk_type = chunk.get('chunk_type', 'text')
                    if chunk_type not in ('text', 'image', 'table', 'chart'):
                        chunk_type = 'text'
                    content_type = map_chunk_type_to_content_type(chunk_type)

                    # Validate that chunk ID is a valid UUID - fail fast if invalid
                    chunk_id = chunk.get('id', '')
                    try:
                        uuid.UUID(chunk_id)
                    except (ValueError, TypeError):
                        raise ValueError(f"Chunk ID must be a valid UUID, got: {chunk_id}")

                    # Get content and compute hash
                    content = chunk['content']
                    content_hash = compute_content_hash(content)

                    # Map page_number to location_reference (string conversion)
                    page_number = chunk.get('page_number')
                    location_reference = str(page_number) if page_number is not None else None

                    # Track max page seen for progress reporting
                    if page_number is not None:
                        try:
                            max_page_seen = max(max_page_seen, int(page_number))
                        except (ValueError, TypeError):
                            pass

                    # Map section_title to section
                    section = chunk.get('section_title')

                    await conn.execute("""
                        INSERT INTO multimodal_librarian.knowledge_chunks (
                            id, source_id, source_type, chunk_index, content,
                            content_hash, content_type, location_reference, section, metadata
                        ) VALUES ($1::uuid, $2::uuid, 'BOOK', $3, $4, $5, $6, $7, $8, $9::jsonb)
                        ON CONFLICT (id) DO UPDATE SET
                            content = EXCLUDED.content,
                            content_type = EXCLUDED.content_type,
                            location_reference = EXCLUDED.location_reference,
                            section = EXCLUDED.section,
                            metadata = EXCLUDED.metadata,
                            chunk_index = EXCLUDED.chunk_index,
                            updated_at = CURRENT_TIMESTAMP
                    """,
                        chunk_id,
                        document_id,
                        i,
                        content,
                        content_hash,
                        content_type,
                        location_reference,
                        section,
                        metadata
                    )

                    # Send incremental progress every ~5 seconds
                    now = time.monotonic()
                    if now - last_update_time >= UPDATE_INTERVAL:
                        last_update_time = now
                        stored_so_far = i + 1
                        progress_pct = 15.0 + (stored_so_far / total_chunks) * 5.0  # 15-20%
                        meta = {
                            'chunks_stored_so_far': stored_so_far,
                            'total_chunks': total_chunks,
                        }
                        if max_page_seen > 0:
                            clamped_page = min(max_page_seen, total_pages) if total_pages > 0 else max_page_seen
                            meta['current_page'] = clamped_page
                        if total_pages > 0:
                            meta['total_pages'] = total_pages
                        await _update_job_status_sync(
                            UUID(document_id), 'running', min(progress_pct, 20.0),
                            'Storing chunks',
                            metadata=meta
                        )

                # Update document chunk count in knowledge_sources
                await conn.execute("""
                    UPDATE multimodal_librarian.knowledge_sources
                    SET updated_at = CURRENT_TIMESTAMP
                    WHERE id = $1::uuid
                """, document_id)
        finally:
            await conn.close()

    except Exception as e:
        logger.error(f"Error storing chunks in database: {e}")
        raise


async def _store_bridge_chunks_in_database(document_id: str, bridges: List[Dict[str, Any]]):
    """Store bridge chunks in PostgreSQL for verification and relationship tracking.
    
    Bridge chunks connect two knowledge chunks and are stored with:
    - source_chunk_id: FK to the source knowledge chunk
    - target_chunk_id: Reference to the target chunk (by chunk_id string)
    - gap_analysis: JSON containing the gap analysis that triggered bridge generation
    - validation_result: JSON containing validation scores
    - confidence_score: Overall confidence in the bridge quality
    """
    try:
        import json
        import uuid

        from ..database.connection import get_async_connection

        conn = await get_async_connection()
        try:
            async with conn.transaction():
                for bridge in bridges:
                    bridge_id = bridge.get('id', str(uuid.uuid4()))
                    content = bridge.get('content', '')
                    source_chunks = bridge.get('source_chunks', [])
                    generation_method = bridge.get('generation_method', 'gemini_25_flash')
                    confidence_score = bridge.get('confidence_score', 0.0)
                    
                    # source_chunks is a list like ["chunk_id_1", "chunk_id_2"]
                    # The bridge connects chunk1 -> chunk2, so source is first, target is second
                    source_chunk_id = source_chunks[0] if len(source_chunks) > 0 else None
                    target_chunk_id = source_chunks[1] if len(source_chunks) > 1 else None
                    
                    if not source_chunk_id:
                        logger.warning(f"Bridge {bridge_id} has no source chunk, skipping")
                        continue
                    
                    # Validate source_chunk_id is a valid UUID and use it
                    try:
                        source_uuid = uuid.UUID(source_chunk_id)
                    except (ValueError, TypeError):
                        logger.warning(f"Bridge {bridge_id} has invalid source_chunk_id: {source_chunk_id}")
                        continue
                    
                    # Serialize gap_analysis and validation_result if present
                    gap_analysis = bridge.get('gap_analysis')
                    if gap_analysis and isinstance(gap_analysis, dict):
                        gap_analysis = json.dumps(gap_analysis)
                    
                    validation_result = bridge.get('validation_result')
                    if validation_result and isinstance(validation_result, dict):
                        validation_result = json.dumps(validation_result)
                    
                    await conn.execute("""
                        INSERT INTO multimodal_librarian.bridge_chunks (
                            id, bridge_id, content, source_chunk_id, target_chunk_id,
                            generation_method, gap_analysis, validation_result, confidence_score
                        ) VALUES (
                            gen_random_uuid(), $1, $2, $3::uuid, $4, $5, $6::jsonb, $7::jsonb, $8
                        )
                        ON CONFLICT (bridge_id) DO UPDATE SET
                            content = EXCLUDED.content,
                            source_chunk_id = EXCLUDED.source_chunk_id,
                            target_chunk_id = EXCLUDED.target_chunk_id,
                            generation_method = EXCLUDED.generation_method,
                            gap_analysis = EXCLUDED.gap_analysis,
                            validation_result = EXCLUDED.validation_result,
                            confidence_score = EXCLUDED.confidence_score,
                            created_at = CURRENT_TIMESTAMP
                    """,
                        bridge_id,
                        content,
                        str(source_uuid),
                        target_chunk_id,
                        generation_method,
                        gap_analysis,
                        validation_result,
                        confidence_score
                    )
                    
            logger.info(f"Stored {len(bridges)} bridge chunks in PostgreSQL")
        finally:
            await conn.close()

    except Exception as e:
        logger.error(f"Error storing bridge chunks in database: {e}")
        raise


def _mark_document_failed_sync(document_id: str, error_message: str, failed_stage: str = None):
    """
    Mark document as failed using synchronous database connection.
    
    This function is designed to be called from Celery signal handlers
    which run in the main process and cannot use asyncio.run() safely.
    Uses psycopg2 directly for synchronous database access.
    
    Args:
        document_id: Document identifier
        error_message: Error message describing the failure
        failed_stage: Optional stage name where processing failed (for retry support)
                     Requirements: 8.4 - Track failed stage in processing metadata
    """
    try:
        import json

        import psycopg2

        # Get database connection parameters from environment
        db_host = os.environ.get('POSTGRES_HOST', 'postgres')
        db_port = os.environ.get('POSTGRES_PORT', '5432')
        db_name = os.environ.get('POSTGRES_DB', 'multimodal_librarian')
        db_user = os.environ.get('POSTGRES_USER', 'postgres')
        db_password = os.environ.get('POSTGRES_PASSWORD', 'postgres')
        
        # Connect and update
        conn = psycopg2.connect(
            host=db_host,
            port=db_port,
            dbname=db_name,
            user=db_user,
            password=db_password
        )
        
        try:
            with conn.cursor() as cur:
                # Update document status to failed in unified schema
                cur.execute("""
                    UPDATE multimodal_librarian.knowledge_sources 
                    SET processing_status = 'FAILED'::multimodal_librarian.processing_status, 
                        metadata = jsonb_set(COALESCE(metadata, '{}'::jsonb), '{processing_error}', to_jsonb(%s::text)),
                        updated_at = NOW()
                    WHERE id = %s::uuid
                """, (error_message[:1000] if error_message else 'Unknown error', document_id))
                
                # Update processing job status to failed with failed_stage in job_metadata
                # Requirements: 8.4 - Track failed stage in processing metadata
                if failed_stage:
                    cur.execute("""
                        UPDATE multimodal_librarian.processing_jobs 
                        SET status = 'failed', 
                            error_message = %s,
                            job_metadata = jsonb_set(COALESCE(job_metadata, '{}'::jsonb), '{failed_stage}', %s::jsonb),
                            completed_at = NOW()
                        WHERE source_id = %s::uuid
                    """, (error_message[:1000] if error_message else 'Unknown error', 
                          json.dumps(failed_stage), document_id))
                else:
                    cur.execute("""
                        UPDATE multimodal_librarian.processing_jobs 
                        SET status = 'failed', 
                            error_message = %s,
                            completed_at = NOW()
                        WHERE source_id = %s::uuid
                    """, (error_message[:1000] if error_message else 'Unknown error', document_id))
                
                conn.commit()
                logger.info(f"Successfully marked document {document_id} as failed (stage: {failed_stage})")
        finally:
            conn.close()
            
    except Exception as e:
        logger.error(f"Failed to mark document as failed in database: {e}")


# Celery signal handlers
@task_prerun.connect
def task_prerun_handler(sender=None, task_id=None, task=None, args=None, kwargs=None, **kwds):
    """Handle task prerun signal."""
    logger.info(f"Task {task.name} [{task_id}] starting")


@task_postrun.connect
def task_postrun_handler(sender=None, task_id=None, task=None, args=None, kwargs=None, 
                        retval=None, state=None, **kwds):
    """Handle task postrun signal."""
    logger.info(f"Task {task.name} [{task_id}] completed with state: {state}")


@task_failure.connect
def task_failure_handler(sender=None, task_id=None, exception=None,
                         args=None, kwargs=None, traceback=None, einfo=None, **kwds):
    """
    Handle task failure signal - runs in main process so survives worker crashes.
    
    This is critical for handling OOM kills and other worker crashes where the
    task itself cannot update the document status before dying.
    
    Requirements: 8.4 - Track failed stage in processing metadata for retry support
    """
    task_name = sender.name if sender else 'unknown'
    logger.error(f"Task {task_name} [{task_id}] failed: {exception}")
    
    # Map task names to stage names for retry support
    # Requirements: 8.4 - Track failed stage in processing metadata
    TASK_TO_STAGE_MAP = {
        'process_document_task': 'process_document',
        'extract_pdf_content_task': 'extract_pdf_content',
        'generate_chunks_task': 'generate_chunks',
        'store_embeddings_task': 'store_embeddings',
        'update_knowledge_graph_task': 'update_knowledge_graph',
        'finalize_processing_task': 'finalize_processing',
        'enrich_concepts_task': 'enrich_concepts'
    }
    
    # Extract failed_stage from task name
    failed_stage = TASK_TO_STAGE_MAP.get(task_name)
    
    # Extract document_id from task arguments
    document_id = None
    if args:
        # First positional arg is usually document_id (or previous_result for chained tasks)
        if len(args) >= 1:
            first_arg = args[0]
            # For chained tasks, document_id is the second arg
            if len(args) >= 2 and isinstance(args[1], str):
                document_id = args[1]
            # For initial tasks, document_id is the first arg
            elif isinstance(first_arg, str) and len(first_arg) == 36:  # UUID length
                document_id = first_arg
    
    if document_id:
        try:
            # Update document and job status to failed with failed_stage
            # Use sync database connection since we're in a signal handler
            _mark_document_failed_sync(document_id, str(exception), failed_stage)
            logger.info(f"Marked document {document_id} as failed due to task failure at stage: {failed_stage}")
        except Exception as e:
            logger.error(f"Failed to mark document {document_id} as failed: {e}")
    else:
        logger.warning(f"Could not extract document_id from failed task args: {args}")


@worker_ready.connect
def worker_ready_handler(**kwargs):
    """Clean up stale Redis task locks when the worker starts.

    On a single-worker deployment, any existing locks are orphaned
    from a previous worker instance.  On multi-worker deployments,
    this is still safe because worker_shutdown_handler clears locks
    when a worker stops — so any locks present at startup of a NEW
    worker are from a crashed (not gracefully stopped) predecessor.

    We only clear locks that have no heartbeat renewal (i.e., the
    TTL is decaying, meaning no live task is extending it).  We do
    this by checking if the lock's remaining TTL is less than half
    the original TTL (600s), indicating the heartbeat stopped.
    """
    try:
        import redis as _redis
        broker_url = os.environ.get("CELERY_BROKER_URL", "redis://redis:6379/0")
        rc = _redis.Redis.from_url(broker_url)
        cleaned = 0
        for pattern in ("bridge_lock:*", "kg_lock:*"):
            for key in rc.scan_iter(match=pattern):
                ttl = rc.ttl(key)
                # If TTL < 300s (half of 600s default), the heartbeat
                # is dead — this lock is orphaned.  If TTL is -1 (no
                # expiry) or -2 (key gone), also clean up.
                if ttl < 300:
                    rc.delete(key)
                    cleaned += 1
                    logger.info(
                        f"Cleaned up stale lock on startup: {key} "
                        f"(remaining TTL: {ttl}s)"
                    )
        rc.close()
        if cleaned:
            logger.info(
                f"Cleaned {cleaned} stale Redis task lock(s) "
                f"on worker startup"
            )
    except Exception as e:
        logger.warning(f"Redis lock cleanup on startup failed: {e}")


@worker_shutdown.connect
def worker_shutdown_handler(**kwargs):
    """Gracefully shutdown the shared Ollama pool when the Celery worker stops.

    Requirements: 7.3 - Pool resources properly managed across worker lifecycle.
    """
    from ..services.ollama_pool_manager import shutdown_pool

    logger.info("Celery worker shutting down — closing shared Ollama pool")
    shutdown_pool(wait=True)

    # Clean up all Redis task locks held by this worker.
    # When the worker shuts down, any in-flight tasks are killed and their
    # locks become stale.  Clearing them here prevents the next worker
    # from being blocked by orphaned locks.
    try:
        import redis as _redis
        broker_url = os.environ.get("CELERY_BROKER_URL", "redis://redis:6379/0")
        rc = _redis.Redis.from_url(broker_url)
        for pattern in ("bridge_lock:*", "kg_lock:*"):
            for key in rc.scan_iter(match=pattern):
                rc.delete(key)
                logger.info(f"Cleaned up stale lock on shutdown: {key}")
        rc.close()
    except Exception as e:
        logger.warning(f"Redis lock cleanup on shutdown failed: {e}")

    logger.info("Shared Ollama pool shutdown complete")
