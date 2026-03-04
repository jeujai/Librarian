"""Enrichment status tracking service.

This service manages the enrichment status for documents, tracking
progress, checkpoints, and results of background concept enrichment.

Follows the dependency injection patterns documented in
.kiro/steering/dependency-injection.md
"""

import json
import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from multimodal_librarian.models.enrichment_status import (
    EnrichmentCheckpoint,
    EnrichmentResult,
    EnrichmentState,
    EnrichmentStatus,
)

logger = logging.getLogger(__name__)


class EnrichmentStatusService:
    """Service for managing enrichment status.
    
    Provides methods to create, update, and query enrichment status
    records in the database. Supports checkpoint-based resumption
    for failed enrichment tasks.
    
    This service follows lazy initialization patterns and should be
    instantiated via dependency injection.
    """
    
    def __init__(self, db_engine: AsyncEngine):
        """Initialize the enrichment status service.
        
        Args:
            db_engine: SQLAlchemy async engine for database operations
        """
        self._engine = db_engine
    
    async def create_status(
        self,
        document_id: UUID,
        total_concepts: int,
    ) -> EnrichmentStatus:
        """Create initial enrichment status record.
        
        Args:
            document_id: UUID of the document being enriched
            total_concepts: Total number of concepts to enrich
            
        Returns:
            Created EnrichmentStatus record
        """
        # If no concepts to enrich, mark as skipped
        state = EnrichmentState.PENDING if total_concepts > 0 else EnrichmentState.SKIPPED
        
        async with self._engine.begin() as conn:
            result = await conn.execute(
                text("""
                    INSERT INTO enrichment_status (
                        document_id, state, total_concepts
                    ) VALUES (
                        :document_id, :state, :total_concepts
                    )
                    ON CONFLICT (document_id) DO UPDATE SET
                        state = :state,
                        total_concepts = :total_concepts,
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
                    RETURNING id
                """),
                {
                    "document_id": str(document_id),
                    "state": state.value,
                    "total_concepts": total_concepts,
                }
            )
            await result.fetchone()
        
        logger.info(
            f"Created enrichment status for document {document_id} "
            f"with {total_concepts} concepts, state={state.value}"
        )
        
        return EnrichmentStatus(
            document_id=document_id,
            state=state,
            total_concepts=total_concepts,
        )

    async def start_enrichment(self, document_id: UUID) -> Optional[EnrichmentStatus]:
        """Mark enrichment as started (in progress).
        
        Args:
            document_id: UUID of the document being enriched
            
        Returns:
            Updated EnrichmentStatus or None if not found
        """
        async with self._engine.begin() as conn:
            result = await conn.execute(
                text("""
                    UPDATE enrichment_status
                    SET state = :state,
                        started_at = NOW()
                    WHERE document_id = :document_id
                    RETURNING *
                """),
                {
                    "document_id": str(document_id),
                    "state": EnrichmentState.ENRICHING.value,
                }
            )
            row = result.fetchone()
        
        if row is None:
            logger.warning(f"No enrichment status found for document {document_id}")
            return None
        
        logger.info(f"Started enrichment for document {document_id}")
        return self._row_to_status(row)
    
    async def update_progress(
        self,
        document_id: UUID,
        concepts_enriched: int,
        yago_hits: int,
        conceptnet_hits: int,
        cache_hits: int,
        errors: int,
    ) -> Optional[EnrichmentStatus]:
        """Update enrichment progress.
        
        Args:
            document_id: UUID of the document being enriched
            concepts_enriched: Number of concepts successfully enriched
            yago_hits: Number of successful YAGO lookups
            conceptnet_hits: Number of successful ConceptNet lookups
            cache_hits: Number of cache hits
            errors: Number of errors encountered
            
        Returns:
            Updated EnrichmentStatus or None if not found
        """
        async with self._engine.begin() as conn:
            result = await conn.execute(
                text("""
                    UPDATE enrichment_status
                    SET concepts_enriched = :concepts_enriched,
                        yago_hits = :yago_hits,
                        conceptnet_hits = :conceptnet_hits,
                        cache_hits = :cache_hits,
                        error_count = :errors
                    WHERE document_id = :document_id
                    RETURNING *
                """),
                {
                    "document_id": str(document_id),
                    "concepts_enriched": concepts_enriched,
                    "yago_hits": yago_hits,
                    "conceptnet_hits": conceptnet_hits,
                    "cache_hits": cache_hits,
                    "errors": errors,
                }
            )
            row = result.fetchone()
        
        if row is None:
            logger.warning(f"No enrichment status found for document {document_id}")
            return None
        
        logger.debug(
            f"Updated enrichment progress for document {document_id}: "
            f"{concepts_enriched} enriched"
        )
        return self._row_to_status(row)
    
    async def mark_completed(
        self,
        document_id: UUID,
        stats: EnrichmentResult,
    ) -> Optional[EnrichmentStatus]:
        """Mark enrichment as completed with final stats.
        
        Args:
            document_id: UUID of the document that was enriched
            stats: Final enrichment statistics
            
        Returns:
            Updated EnrichmentStatus or None if not found
        """
        # Determine final state based on results
        if stats.errors == 0:
            state = EnrichmentState.COMPLETED
        elif stats.concepts_enriched > 0:
            # Partial success - some concepts enriched
            state = EnrichmentState.COMPLETED
        else:
            state = EnrichmentState.FAILED
        
        async with self._engine.begin() as conn:
            result = await conn.execute(
                text("""
                    UPDATE enrichment_status
                    SET state = :state,
                        concepts_enriched = :concepts_enriched,
                        yago_hits = :yago_hits,
                        conceptnet_hits = :conceptnet_hits,
                        cache_hits = :cache_hits,
                        error_count = :errors,
                        duration_ms = :duration_ms,
                        completed_at = NOW()
                    WHERE document_id = :document_id
                    RETURNING *
                """),
                {
                    "document_id": str(document_id),
                    "state": state.value,
                    "concepts_enriched": stats.concepts_enriched,
                    "yago_hits": stats.yago_hits,
                    "conceptnet_hits": stats.conceptnet_hits,
                    "cache_hits": stats.cache_hits,
                    "errors": stats.errors,
                    "duration_ms": stats.duration_ms,
                }
            )
            row = result.fetchone()
        
        if row is None:
            logger.warning(f"No enrichment status found for document {document_id}")
            return None
        
        logger.info(
            f"Completed enrichment for document {document_id} "
            f"with state={state.value}, {stats.concepts_enriched} enriched"
        )
        return self._row_to_status(row)

    async def mark_failed(
        self,
        document_id: UUID,
        error_message: str,
        retry_count: int,
    ) -> Optional[EnrichmentStatus]:
        """Mark enrichment as failed.
        
        Args:
            document_id: UUID of the document that failed enrichment
            error_message: Error message describing the failure
            retry_count: Current retry count
            
        Returns:
            Updated EnrichmentStatus or None if not found
        """
        async with self._engine.begin() as conn:
            result = await conn.execute(
                text("""
                    UPDATE enrichment_status
                    SET state = :state,
                        last_error = :error_message,
                        retry_count = :retry_count,
                        completed_at = NOW()
                    WHERE document_id = :document_id
                    RETURNING *
                """),
                {
                    "document_id": str(document_id),
                    "state": EnrichmentState.FAILED.value,
                    "error_message": error_message,
                    "retry_count": retry_count,
                }
            )
            row = result.fetchone()
        
        if row is None:
            logger.warning(f"No enrichment status found for document {document_id}")
            return None
        
        logger.error(
            f"Enrichment failed for document {document_id}: {error_message}"
        )
        return self._row_to_status(row)
    
    async def increment_retry(
        self,
        document_id: UUID,
    ) -> int:
        """Increment retry count and return new value.
        
        Args:
            document_id: UUID of the document to increment retry for
            
        Returns:
            New retry count, or -1 if not found
        """
        async with self._engine.begin() as conn:
            result = await conn.execute(
                text("""
                    UPDATE enrichment_status
                    SET retry_count = retry_count + 1,
                        state = :state
                    WHERE document_id = :document_id
                    RETURNING retry_count
                """),
                {
                    "document_id": str(document_id),
                    "state": EnrichmentState.PENDING.value,
                }
            )
            row = result.fetchone()
        
        if row is None:
            logger.warning(f"No enrichment status found for document {document_id}")
            return -1
        
        retry_count = row[0]
        logger.info(
            f"Incremented retry count for document {document_id} to {retry_count}"
        )
        return retry_count
    
    async def get_status(self, document_id: UUID) -> Optional[EnrichmentStatus]:
        """Get current enrichment status.
        
        Args:
            document_id: UUID of the document to check
            
        Returns:
            EnrichmentStatus or None if not found
        """
        async with self._engine.connect() as conn:
            result = await conn.execute(
                text("""
                    SELECT * FROM enrichment_status
                    WHERE document_id = :document_id
                """),
                {"document_id": str(document_id)}
            )
            row = result.fetchone()
        
        if row is None:
            return None
        
        return self._row_to_status(row)
    
    async def get_checkpoint(
        self,
        document_id: UUID,
    ) -> Optional[EnrichmentCheckpoint]:
        """Get checkpoint for resuming failed enrichment.
        
        Args:
            document_id: UUID of the document to get checkpoint for
            
        Returns:
            EnrichmentCheckpoint or None if not found
        """
        async with self._engine.connect() as conn:
            result = await conn.execute(
                text("""
                    SELECT checkpoint_index, checkpoint_data
                    FROM enrichment_status
                    WHERE document_id = :document_id
                """),
                {"document_id": str(document_id)}
            )
            row = result.fetchone()
        
        if row is None or row[0] is None:
            return None
        
        checkpoint_index = row[0]
        checkpoint_data = row[1] or {}
        
        return EnrichmentCheckpoint(
            document_id=document_id,
            last_concept_index=checkpoint_index,
            concepts_processed=checkpoint_data.get("concepts_processed", []),
            partial_stats=checkpoint_data.get("partial_stats", {}),
            created_at=datetime.fromisoformat(checkpoint_data["created_at"])
            if checkpoint_data.get("created_at") else datetime.utcnow(),
        )

    async def save_checkpoint(
        self,
        document_id: UUID,
        last_concept_index: int,
        concepts_processed: list,
        partial_stats: dict,
    ) -> None:
        """Save checkpoint for resumption.
        
        Args:
            document_id: UUID of the document being enriched
            last_concept_index: Index of the last successfully processed concept
            concepts_processed: List of concept IDs that have been processed
            partial_stats: Partial statistics from processing so far
        """
        checkpoint_data = {
            "concepts_processed": concepts_processed,
            "partial_stats": partial_stats,
            "created_at": datetime.utcnow().isoformat(),
        }
        
        async with self._engine.begin() as conn:
            await conn.execute(
                text("""
                    UPDATE enrichment_status
                    SET checkpoint_index = :checkpoint_index,
                        checkpoint_data = :checkpoint_data
                    WHERE document_id = :document_id
                """),
                {
                    "document_id": str(document_id),
                    "checkpoint_index": last_concept_index,
                    "checkpoint_data": json.dumps(checkpoint_data),
                }
            )
        
        logger.debug(
            f"Saved checkpoint for document {document_id} at index {last_concept_index}"
        )
    
    def _row_to_status(self, row) -> EnrichmentStatus:
        """Convert a database row to EnrichmentStatus.
        
        Args:
            row: Database row from enrichment_status table
            
        Returns:
            EnrichmentStatus instance
        """
        # Row columns: id, document_id, state, total_concepts, concepts_enriched,
        # yago_hits, conceptnet_hits, cache_hits, error_count, retry_count,
        # started_at, completed_at, duration_ms, last_error, checkpoint_index,
        # checkpoint_data, created_at, updated_at
        return EnrichmentStatus(
            document_id=UUID(str(row[1])),
            state=EnrichmentState(row[2]),
            total_concepts=row[3],
            concepts_enriched=row[4],
            yago_hits=row[5],
            conceptnet_hits=row[6],
            cache_hits=row[7],
            error_count=row[8],
            retry_count=row[9],
            started_at=row[10],
            completed_at=row[11],
            duration_ms=row[12],
            last_error=row[13],
            checkpoint_index=row[14],
        )


# Cached service instance for singleton pattern
_enrichment_status_service: Optional[EnrichmentStatusService] = None


async def get_enrichment_status_service(
    db_engine: AsyncEngine,
) -> EnrichmentStatusService:
    """Get or create the EnrichmentStatusService instance.
    
    This function follows the lazy initialization pattern for
    dependency injection.
    
    Args:
        db_engine: SQLAlchemy async engine
        
    Returns:
        EnrichmentStatusService instance
    """
    global _enrichment_status_service
    
    if _enrichment_status_service is None:
        _enrichment_status_service = EnrichmentStatusService(db_engine)
        logger.info("Created EnrichmentStatusService instance")
    
    return _enrichment_status_service


def clear_enrichment_status_service_cache() -> None:
    """Clear the cached EnrichmentStatusService instance.
    
    Used during testing and application shutdown.
    """
    global _enrichment_status_service
    _enrichment_status_service = None
    logger.debug("Cleared EnrichmentStatusService cache")
