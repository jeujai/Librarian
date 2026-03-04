"""Enrichment status data models.

This module defines the data models for tracking enrichment status
of documents in the background enrichment pipeline.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional
from uuid import UUID


class EnrichmentState(str, Enum):
    """Enrichment status states.
    
    Valid state transitions:
    - PENDING -> ENRICHING (when enrichment starts)
    - ENRICHING -> COMPLETED (when all concepts enriched successfully)
    - ENRICHING -> FAILED (when enrichment fails after retries)
    - PENDING -> SKIPPED (when document has no concepts to enrich)
    """
    PENDING = "pending"
    ENRICHING = "enriching"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class EnrichmentStatus:
    """Enrichment status for a document.
    
    Tracks the progress and results of background concept enrichment
    for a processed document.
    
    Attributes:
        document_id: UUID of the document being enriched
        state: Current enrichment state
        total_concepts: Total number of concepts to enrich
        concepts_enriched: Number of concepts successfully enriched
        yago_hits: Number of successful YAGO lookups
        conceptnet_hits: Number of successful ConceptNet lookups
        cache_hits: Number of cache hits (already enriched)
        error_count: Number of enrichment errors
        retry_count: Number of task retries
        started_at: When enrichment started
        completed_at: When enrichment completed (success or failure)
        duration_ms: Total enrichment duration in milliseconds
        last_error: Most recent error message
        checkpoint_index: Index of last checkpointed concept
    """
    document_id: UUID
    state: EnrichmentState
    total_concepts: int
    concepts_enriched: int = 0
    yago_hits: int = 0
    conceptnet_hits: int = 0
    cache_hits: int = 0
    error_count: int = 0
    retry_count: int = 0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[float] = None
    last_error: Optional[str] = None
    checkpoint_index: Optional[int] = None


    @property
    def progress_percentage(self) -> float:
        """Calculate enrichment progress as a percentage.
        
        Returns:
            Progress percentage (0.0 to 100.0)
        """
        if self.total_concepts == 0:
            return 100.0
        return (self.concepts_enriched / self.total_concepts) * 100.0
    
    @property
    def is_complete(self) -> bool:
        """Check if enrichment is complete (success or failure).
        
        Returns:
            True if enrichment has finished
        """
        return self.state in (EnrichmentState.COMPLETED, EnrichmentState.FAILED, EnrichmentState.SKIPPED)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization.
        
        Returns:
            Dictionary representation of the status
        """
        return {
            "document_id": str(self.document_id),
            "state": self.state.value,
            "total_concepts": self.total_concepts,
            "concepts_enriched": self.concepts_enriched,
            "yago_hits": self.yago_hits,
            "conceptnet_hits": self.conceptnet_hits,
            "cache_hits": self.cache_hits,
            "error_count": self.error_count,
            "retry_count": self.retry_count,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_ms": self.duration_ms,
            "last_error": self.last_error,
            "checkpoint_index": self.checkpoint_index,
            "progress_percentage": self.progress_percentage,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "EnrichmentStatus":
        """Create from dictionary.
        
        Args:
            data: Dictionary with status data
            
        Returns:
            EnrichmentStatus instance
        """
        return cls(
            document_id=UUID(data["document_id"]) if isinstance(data["document_id"], str) else data["document_id"],
            state=EnrichmentState(data["state"]),
            total_concepts=data["total_concepts"],
            concepts_enriched=data.get("concepts_enriched", 0),
            yago_hits=data.get("yago_hits", 0),
            conceptnet_hits=data.get("conceptnet_hits", 0),
            cache_hits=data.get("cache_hits", 0),
            error_count=data.get("error_count", 0),
            retry_count=data.get("retry_count", 0),
            started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None,
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            duration_ms=data.get("duration_ms"),
            last_error=data.get("last_error"),
            checkpoint_index=data.get("checkpoint_index"),
        )


@dataclass
class EnrichmentCheckpoint:
    """Checkpoint for resuming enrichment.
    
    Stores the state needed to resume enrichment after a failure
    or task restart.
    
    Attributes:
        document_id: UUID of the document being enriched
        last_concept_index: Index of the last successfully processed concept
        concepts_processed: List of concept IDs that have been processed
        partial_stats: Partial statistics from processing so far
        created_at: When the checkpoint was created
    """
    document_id: UUID
    last_concept_index: int
    concepts_processed: List[str] = field(default_factory=list)
    partial_stats: Dict[str, int] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization.
        
        Returns:
            Dictionary representation of the checkpoint
        """
        return {
            "document_id": str(self.document_id),
            "last_concept_index": self.last_concept_index,
            "concepts_processed": self.concepts_processed,
            "partial_stats": self.partial_stats,
            "created_at": self.created_at.isoformat(),
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "EnrichmentCheckpoint":
        """Create from dictionary.
        
        Args:
            data: Dictionary with checkpoint data
            
        Returns:
            EnrichmentCheckpoint instance
        """
        return cls(
            document_id=UUID(data["document_id"]) if isinstance(data["document_id"], str) else data["document_id"],
            last_concept_index=data["last_concept_index"],
            concepts_processed=data.get("concepts_processed", []),
            partial_stats=data.get("partial_stats", {}),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.utcnow(),
        )


@dataclass
class EnrichmentResult:
    """Result of an enrichment operation.
    
    Contains the final statistics from a completed enrichment task.
    
    Attributes:
        concepts_enriched: Total concepts successfully enriched
        yago_hits: Successful YAGO lookups
        conceptnet_hits: Successful ConceptNet lookups
        cache_hits: Cache hits (already enriched)
        errors: Number of errors encountered
        duration_ms: Total duration in milliseconds
    """
    concepts_enriched: int
    yago_hits: int
    conceptnet_hits: int
    cache_hits: int
    errors: int
    duration_ms: float
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization.
        
        Returns:
            Dictionary representation of the result
        """
        return {
            "concepts_enriched": self.concepts_enriched,
            "yago_hits": self.yago_hits,
            "conceptnet_hits": self.conceptnet_hits,
            "cache_hits": self.cache_hits,
            "errors": self.errors,
            "duration_ms": self.duration_ms,
        }
