"""
Data models for Knowledge Graph External Enrichment.

This module defines data classes for ConceptNet relationships,
enrichment results, caching, and circuit breaker state management.

YAGO entity models live in components/yago/models.py (YagoEntityData).
"""

import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from ..components.yago.models import YagoEntityData

# =============================================================================
# ConceptNet Models
# =============================================================================

@dataclass
class ConceptNetRelation:
    """Represents a ConceptNet relationship."""
    subject: str                  # Source concept
    relation: str                 # Relationship type (e.g., "IsA")
    object: str                   # Target concept
    weight: float = 0.0           # Confidence weight
    source_uri: str = ""          # ConceptNet edge URI
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'subject': self.subject,
            'relation': self.relation,
            'object': self.object,
            'weight': self.weight,
            'source_uri': self.source_uri
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ConceptNetRelation':
        """Create from dictionary."""
        return cls(
            subject=data['subject'],
            relation=data['relation'],
            object=data['object'],
            weight=data.get('weight', 0.0),
            source_uri=data.get('source_uri', '')
        )


# =============================================================================
# Enrichment Result Models
# =============================================================================

@dataclass
class EnrichedConcept:
    """A concept with enrichment data."""
    concept_id: str
    concept_name: str
    yago_entity: Optional["YagoEntityData"] = None
    conceptnet_relations: List[ConceptNetRelation] = field(default_factory=list)
    cross_document_links: List[str] = field(default_factory=list)  # IDs of linked concepts
    enrichment_deferred: bool = False  # True if enrichment was skipped due to circuit breaker
    
    @property
    def is_enriched(self) -> bool:
        """Check if concept has any enrichment data."""
        return self.yago_entity is not None or len(self.conceptnet_relations) > 0
    
    @property
    def has_yago(self) -> bool:
        """Check if concept has YAGO enrichment."""
        return self.yago_entity is not None
    
    @property
    def has_conceptnet(self) -> bool:
        """Check if concept has ConceptNet enrichment."""
        return len(self.conceptnet_relations) > 0


@dataclass
class EnrichmentResult:
    """Result of batch enrichment."""
    concepts_processed: int = 0
    concepts_enriched: int = 0
    yago_hits: int = 0
    conceptnet_hits: int = 0
    cache_hits: int = 0
    api_calls: int = 0
    errors: List[str] = field(default_factory=list)
    duration_ms: float = 0.0
    enriched_concepts: List[EnrichedConcept] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/serialization."""
        return {
            'concepts_processed': self.concepts_processed,
            'concepts_enriched': self.concepts_enriched,
            'yago_hits': self.yago_hits,
            'conceptnet_hits': self.conceptnet_hits,
            'cache_hits': self.cache_hits,
            'api_calls': self.api_calls,
            'errors': self.errors,
            'duration_ms': self.duration_ms
        }


# =============================================================================
# Cache Models
# =============================================================================

@dataclass
class CacheEntry:
    """Cache entry with TTL."""
    data: Any
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    
    def is_expired(self, ttl: int) -> bool:
        """Check if entry has expired based on TTL."""
        return time.time() - self.created_at > ttl
    
    def touch(self) -> None:
        """Update last accessed time for LRU tracking."""
        self.last_accessed = time.time()


@dataclass
class CacheStats:
    """Cache statistics."""
    yago_size: int = 0
    conceptnet_size: int = 0
    yago_hits: int = 0
    yago_misses: int = 0
    conceptnet_hits: int = 0
    conceptnet_misses: int = 0
    evictions: int = 0
    
    @property
    def total_size(self) -> int:
        """Total cache entries."""
        return self.yago_size + self.conceptnet_size
    
    @property
    def yago_hit_rate(self) -> float:
        """YAGO cache hit rate."""
        total = self.yago_hits + self.yago_misses
        return self.yago_hits / total if total > 0 else 0.0
    
    @property
    def conceptnet_hit_rate(self) -> float:
        """ConceptNet cache hit rate."""
        total = self.conceptnet_hits + self.conceptnet_misses
        return self.conceptnet_hits / total if total > 0 else 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            'yago_size': self.yago_size,
            'conceptnet_size': self.conceptnet_size,
            'yago_hits': self.yago_hits,
            'yago_misses': self.yago_misses,
            'conceptnet_hits': self.conceptnet_hits,
            'conceptnet_misses': self.conceptnet_misses,
            'evictions': self.evictions,
            'total_size': self.total_size,
            'yago_hit_rate': self.yago_hit_rate,
            'conceptnet_hit_rate': self.conceptnet_hit_rate
        }


# =============================================================================
# Circuit Breaker Models
# =============================================================================

class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"        # Normal operation
    OPEN = "open"            # Blocking requests
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitBreakerStats:
    """Circuit breaker statistics."""
    state: CircuitState = CircuitState.CLOSED
    failures: int = 0
    successes: int = 0
    last_failure_time: Optional[float] = None
    last_state_change: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            'state': self.state.value,
            'failures': self.failures,
            'successes': self.successes,
            'last_failure_time': self.last_failure_time,
            'last_state_change': self.last_state_change
        }


# =============================================================================
# Exception Hierarchy
# =============================================================================

class EnrichmentError(Exception):
    """Base exception for enrichment errors."""
    pass


class ConceptNetAPIError(EnrichmentError):
    """ConceptNet API request failed."""
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class CircuitBreakerOpenError(EnrichmentError):
    """Circuit breaker is open, requests are blocked."""
    def __init__(self, api_name: str, recovery_time: Optional[datetime] = None):
        message = f"Circuit breaker open for {api_name}"
        if recovery_time:
            message += f", recovery at {recovery_time.isoformat()}"
        super().__init__(message)
        self.api_name = api_name
        self.recovery_time = recovery_time


class EnrichmentTimeoutError(EnrichmentError):
    """Enrichment API request timed out."""
    def __init__(self, api_name: str, timeout: float):
        super().__init__(f"{api_name} request timed out after {timeout}s")
        self.api_name = api_name
        self.timeout = timeout
