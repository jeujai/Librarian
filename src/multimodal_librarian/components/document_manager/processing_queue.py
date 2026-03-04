"""
Processing Queue Component.

This component manages the job queue for document processing,
providing job scheduling, priority management, and monitoring capabilities.
"""

import logging
import asyncio
from typing import Dict, List, Optional, Callable, Any
from uuid import UUID
from datetime import datetime, timedelta
from enum import Enum
import heapq
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class JobPriority(int, Enum):
    """Job priority levels."""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4


class QueueStatus(str, Enum):
    """Queue status."""
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"


@dataclass
class QueuedJob:
    """Represents a job in the processing queue."""
    document_id: UUID
    job_type: str
    priority: JobPriority
    created_at: datetime
    scheduled_at: Optional[datetime] = None
    retry_count: int = 0
    max_retries: int = 3
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __lt__(self, other):
        """Compare jobs for priority queue ordering."""
        # Higher priority first, then earlier scheduled time
        if self.priority != other.priority:
            return self.priority.value > other.priority.value
        
        scheduled_self = self.scheduled_at or self.created_at
        scheduled_other = other.scheduled_at or other.created_at
        return scheduled_self < scheduled_other


class ProcessingQueue:
    """
    Job queue manager for document processing.
    
    Provides priority-based job scheduling, retry logic, and monitoring
    capabilities for document processing workflows.
    """
    
    def __init__(self, max_concurrent_jobs: int = 3, 
                 job_timeout: int = 3600):  # 1 hour default timeout
        """
        Initialize processing queue.
        
        Args:
            max_concurrent_jobs: Maximum number of concurrent processing jobs
            job_timeout: Job timeout in seconds
        """
        self.max_concurrent_jobs = max_concurrent_jobs
        self.job_timeout = job_timeout
        
        # Queue management
        self.job_queue: List[QueuedJob] = []
        self.running_jobs: Dict[str, QueuedJob] = {}
        self.completed_jobs: List[QueuedJob] = []
        self.failed_jobs: List[QueuedJob] = []
        
        # Queue state
        self.status = QueueStatus.STOPPED
        self.worker_task: Optional[asyncio.Task] = None
        
        # Job handlers
        self.job_handlers: Dict[str, Callable] = {}
        
        # Statistics
        self.queue_stats = {
            'total_jobs_queued': 0,
            'total_jobs_completed': 0,
            'total_jobs_failed': 0,
            'average_processing_time': 0.0,
            'queue_start_time': None
        }
        
        logger.info(f"Processing queue initialized with max {max_concurrent_jobs} concurrent jobs")
    
    def register_job_handler(self, job_type: str, handler: Callable):
        """
        Register a handler function for a specific job type.
        
        Args:
            job_type: Type of job to handle
            handler: Async function to handle the job
        """
        self.job_handlers[job_type] = handler
        logger.info(f"Registered handler for job type: {job_type}")
    
    async def enqueue_job(self, document_id: UUID, job_type: str = "pdf_processing",
                         priority: JobPriority = JobPriority.NORMAL,
                         scheduled_at: Optional[datetime] = None,
                         metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Add a job to the processing queue.
        
        Args:
            document_id: Document to process
            job_type: Type of processing job
            priority: Job priority level
            scheduled_at: When to process the job (None for immediate)
            metadata: Additional job metadata
            
        Returns:
            True if job was queued successfully
        """
        try:
            # Check if job already exists
            if self._job_exists(document_id, job_type):
                logger.warning(f"Job already exists for document {document_id} with type {job_type}")
                return False
            
            # Create queued job
            job = QueuedJob(
                document_id=document_id,
                job_type=job_type,
                priority=priority,
                created_at=datetime.utcnow(),
                scheduled_at=scheduled_at,
                metadata=metadata or {}
            )
            
            # Add to priority queue
            heapq.heappush(self.job_queue, job)
            self.queue_stats['total_jobs_queued'] += 1
            
            logger.info(f"Queued job for document {document_id} with priority {priority.name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to enqueue job for document {document_id}: {e}")
            return False
    
    async def start_queue(self):
        """Start the processing queue worker."""
        if self.status == QueueStatus.RUNNING:
            logger.warning("Queue is already running")
            return
        
        self.status = QueueStatus.RUNNING
        self.queue_stats['queue_start_time'] = datetime.utcnow()
        
        # Start worker task
        self.worker_task = asyncio.create_task(self._queue_worker())
        
        logger.info("Processing queue started")
    
    async def stop_queue(self):
        """Stop the processing queue worker."""
        if self.status == QueueStatus.STOPPED:
            return
        
        self.status = QueueStatus.STOPPED
        
        # Cancel worker task
        if self.worker_task:
            self.worker_task.cancel()
            try:
                await self.worker_task
            except asyncio.CancelledError:
                pass
            self.worker_task = None
        
        logger.info("Processing queue stopped")
    
    async def pause_queue(self):
        """Pause the processing queue (finish current jobs but don't start new ones)."""
        if self.status == QueueStatus.RUNNING:
            self.status = QueueStatus.PAUSED
            logger.info("Processing queue paused")
    
    async def resume_queue(self):
        """Resume the processing queue."""
        if self.status == QueueStatus.PAUSED:
            self.status = QueueStatus.RUNNING
            logger.info("Processing queue resumed")
    
    async def _queue_worker(self):
        """Main queue worker loop."""
        logger.info("Queue worker started")
        
        try:
            while self.status != QueueStatus.STOPPED:
                # Check if we should process jobs
                if self.status == QueueStatus.PAUSED:
                    await asyncio.sleep(1)
                    continue
                
                # Check if we can start new jobs
                if len(self.running_jobs) >= self.max_concurrent_jobs:
                    await asyncio.sleep(1)
                    continue
                
                # Get next job from queue
                job = await self._get_next_job()
                if not job:
                    await asyncio.sleep(1)
                    continue
                
                # Start processing the job
                await self._start_job_processing(job)
                
        except asyncio.CancelledError:
            logger.info("Queue worker cancelled")
        except Exception as e:
            logger.error(f"Queue worker error: {e}")
        finally:
            logger.info("Queue worker stopped")
    
    async def _get_next_job(self) -> Optional[QueuedJob]:
        """Get the next job to process from the queue."""
        if not self.job_queue:
            return None
        
        # Check if the highest priority job is ready to run
        job = self.job_queue[0]
        
        # Check if job is scheduled for the future
        if job.scheduled_at and job.scheduled_at > datetime.utcnow():
            return None
        
        # Remove job from queue
        return heapq.heappop(self.job_queue)
    
    async def _start_job_processing(self, job: QueuedJob):
        """Start processing a job."""
        try:
            # Add to running jobs
            job_key = f"{job.document_id}_{job.job_type}"
            self.running_jobs[job_key] = job
            
            # Get job handler
            handler = self.job_handlers.get(job.job_type)
            if not handler:
                raise Exception(f"No handler registered for job type: {job.job_type}")
            
            # Start job processing task
            task = asyncio.create_task(
                self._execute_job_with_timeout(job, handler)
            )
            
            # Don't await here - let it run in background
            task.add_done_callback(
                lambda t: asyncio.create_task(self._handle_job_completion(job, t))
            )
            
            logger.info(f"Started processing job for document {job.document_id}")
            
        except Exception as e:
            logger.error(f"Failed to start job processing: {e}")
            await self._handle_job_failure(job, str(e))
    
    async def _execute_job_with_timeout(self, job: QueuedJob, handler: Callable):
        """Execute job with timeout handling."""
        try:
            # Execute job with timeout
            await asyncio.wait_for(
                handler(job.document_id),
                timeout=self.job_timeout
            )
            
        except asyncio.TimeoutError:
            raise Exception(f"Job timed out after {self.job_timeout} seconds")
        except Exception as e:
            raise Exception(f"Job execution failed: {e}")
    
    async def _handle_job_completion(self, job: QueuedJob, task: asyncio.Task):
        """Handle job completion (success or failure)."""
        job_key = f"{job.document_id}_{job.job_type}"
        
        try:
            # Remove from running jobs
            if job_key in self.running_jobs:
                del self.running_jobs[job_key]
            
            # Check task result
            if task.exception():
                # Job failed
                await self._handle_job_failure(job, str(task.exception()))
            else:
                # Job succeeded
                await self._handle_job_success(job)
                
        except Exception as e:
            logger.error(f"Error handling job completion: {e}")
    
    async def _handle_job_success(self, job: QueuedJob):
        """Handle successful job completion."""
        # Add to completed jobs
        self.completed_jobs.append(job)
        self.queue_stats['total_jobs_completed'] += 1
        
        # Update average processing time
        if job.created_at:
            processing_time = (datetime.utcnow() - job.created_at).total_seconds()
            self._update_average_processing_time(processing_time)
        
        # Keep only last 100 completed jobs
        if len(self.completed_jobs) > 100:
            self.completed_jobs = self.completed_jobs[-100:]
        
        logger.info(f"Job completed successfully for document {job.document_id}")
    
    async def _handle_job_failure(self, job: QueuedJob, error_message: str):
        """Handle job failure and retry logic."""
        logger.error(f"Job failed for document {job.document_id}: {error_message}")
        
        # Check if we should retry
        if job.retry_count < job.max_retries:
            # Schedule retry with exponential backoff
            job.retry_count += 1
            retry_delay = min(300, 30 * (2 ** (job.retry_count - 1)))  # Max 5 minutes
            job.scheduled_at = datetime.utcnow() + timedelta(seconds=retry_delay)
            
            # Add back to queue
            heapq.heappush(self.job_queue, job)
            
            logger.info(f"Scheduled retry {job.retry_count} for document {job.document_id} in {retry_delay} seconds")
        else:
            # Max retries exceeded, mark as failed
            job.metadata['final_error'] = error_message
            self.failed_jobs.append(job)
            self.queue_stats['total_jobs_failed'] += 1
            
            # Keep only last 100 failed jobs
            if len(self.failed_jobs) > 100:
                self.failed_jobs = self.failed_jobs[-100:]
            
            logger.error(f"Job permanently failed for document {job.document_id} after {job.retry_count} retries")
    
    def _job_exists(self, document_id: UUID, job_type: str) -> bool:
        """Check if a job already exists for the document and type."""
        # Check queue
        for job in self.job_queue:
            if job.document_id == document_id and job.job_type == job_type:
                return True
        
        # Check running jobs
        job_key = f"{document_id}_{job_type}"
        return job_key in self.running_jobs
    
    def _update_average_processing_time(self, processing_time: float):
        """Update average processing time statistic."""
        completed_count = self.queue_stats['total_jobs_completed']
        if completed_count == 1:
            self.queue_stats['average_processing_time'] = processing_time
        else:
            current_avg = self.queue_stats['average_processing_time']
            self.queue_stats['average_processing_time'] = (
                (current_avg * (completed_count - 1) + processing_time) / completed_count
            )
    
    def get_queue_status(self) -> Dict[str, Any]:
        """
        Get comprehensive queue status information.
        
        Returns:
            Dictionary with queue status and statistics
        """
        return {
            'status': self.status.value,
            'queued_jobs': len(self.job_queue),
            'running_jobs': len(self.running_jobs),
            'completed_jobs': len(self.completed_jobs),
            'failed_jobs': len(self.failed_jobs),
            'max_concurrent_jobs': self.max_concurrent_jobs,
            'job_timeout': self.job_timeout,
            'statistics': self.queue_stats.copy()
        }
    
    def get_job_details(self, document_id: UUID, job_type: str = "pdf_processing") -> Optional[Dict[str, Any]]:
        """
        Get details about a specific job.
        
        Args:
            document_id: Document identifier
            job_type: Job type
            
        Returns:
            Job details or None if not found
        """
        # Check running jobs
        job_key = f"{document_id}_{job_type}"
        if job_key in self.running_jobs:
            job = self.running_jobs[job_key]
            return {
                'document_id': job.document_id,
                'job_type': job.job_type,
                'status': 'running',
                'priority': job.priority.name,
                'created_at': job.created_at,
                'retry_count': job.retry_count,
                'metadata': job.metadata
            }
        
        # Check queued jobs
        for job in self.job_queue:
            if job.document_id == document_id and job.job_type == job_type:
                return {
                    'document_id': job.document_id,
                    'job_type': job.job_type,
                    'status': 'queued',
                    'priority': job.priority.name,
                    'created_at': job.created_at,
                    'scheduled_at': job.scheduled_at,
                    'retry_count': job.retry_count,
                    'metadata': job.metadata
                }
        
        # Check completed jobs
        for job in self.completed_jobs:
            if job.document_id == document_id and job.job_type == job_type:
                return {
                    'document_id': job.document_id,
                    'job_type': job.job_type,
                    'status': 'completed',
                    'priority': job.priority.name,
                    'created_at': job.created_at,
                    'retry_count': job.retry_count,
                    'metadata': job.metadata
                }
        
        # Check failed jobs
        for job in self.failed_jobs:
            if job.document_id == document_id and job.job_type == job_type:
                return {
                    'document_id': job.document_id,
                    'job_type': job.job_type,
                    'status': 'failed',
                    'priority': job.priority.name,
                    'created_at': job.created_at,
                    'retry_count': job.retry_count,
                    'metadata': job.metadata,
                    'error': job.metadata.get('final_error')
                }
        
        return None
    
    async def cancel_job(self, document_id: UUID, job_type: str = "pdf_processing") -> bool:
        """
        Cancel a queued or running job.
        
        Args:
            document_id: Document identifier
            job_type: Job type
            
        Returns:
            True if job was cancelled
        """
        # Try to remove from queue
        for i, job in enumerate(self.job_queue):
            if job.document_id == document_id and job.job_type == job_type:
                del self.job_queue[i]
                heapq.heapify(self.job_queue)  # Restore heap property
                logger.info(f"Cancelled queued job for document {document_id}")
                return True
        
        # Try to cancel running job (note: actual cancellation depends on job implementation)
        job_key = f"{document_id}_{job_type}"
        if job_key in self.running_jobs:
            # Mark for cancellation (job handler should check this)
            job = self.running_jobs[job_key]
            job.metadata['cancelled'] = True
            logger.info(f"Marked running job for cancellation: document {document_id}")
            return True
        
        return False
    
    def clear_completed_jobs(self):
        """Clear the completed jobs history."""
        self.completed_jobs.clear()
        logger.info("Cleared completed jobs history")
    
    def clear_failed_jobs(self):
        """Clear the failed jobs history."""
        self.failed_jobs.clear()
        logger.info("Cleared failed jobs history")
    
    def health_check(self) -> Dict[str, Any]:
        """
        Perform health check on the processing queue.
        
        Returns:
            Health status information
        """
        try:
            # Calculate success rate
            total_processed = self.queue_stats['total_jobs_completed'] + self.queue_stats['total_jobs_failed']
            success_rate = 0.0
            if total_processed > 0:
                success_rate = (self.queue_stats['total_jobs_completed'] / total_processed) * 100.0
            
            # Check if queue is healthy
            is_healthy = (
                self.status in [QueueStatus.RUNNING, QueueStatus.PAUSED] and
                success_rate >= 80.0 and  # At least 80% success rate
                len(self.running_jobs) <= self.max_concurrent_jobs
            )
            
            return {
                'status': 'healthy' if is_healthy else 'degraded',
                'queue_status': self.status.value,
                'success_rate': success_rate,
                'queued_jobs': len(self.job_queue),
                'running_jobs': len(self.running_jobs),
                'max_concurrent_jobs': self.max_concurrent_jobs,
                'average_processing_time': self.queue_stats['average_processing_time']
            }
            
        except Exception as e:
            return {
                'status': 'unhealthy',
                'error': str(e)
            }