"""
Data models for Knowledge Graph-Guided Retrieval.

This module defines data classes for the two-stage retrieval pipeline that uses
Neo4j knowledge graph for precise chunk retrieval and semantic re-ranking for
relevance ordering.

Requirements: 1.1, 1.3, 3.5, 5.4
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

# =============================================================================
# Enums
# =============================================================================

class RetrievalSource(Enum):
    """Source of a retrieved chunk.
    
    Indicates how a chunk was retrieved in the two-stage pipeline.
    Validates: Requirement 3.5 - retrieval metadata indicating source.
    """
    DIRECT_CONCEPT = "direct_concept"        # From source_chunks of matched concept
    RELATED_CONCEPT = "related_concept"      # From source_chunks of related concept
    REASONING_PATH = "reasoning_path"        # From concepts along a reasoning path
    SEMANTIC_FALLBACK = "semantic_fallback"  # From pure semantic search fallback
    SEMANTIC_AUGMENT = "semantic_augment"    # Augmented from semantic search


# =============================================================================
# Core Data Models
# =============================================================================

@dataclass
class RetrievedChunk:
    """A chunk retrieved via knowledge graph-guided retrieval.
    
    Contains the chunk content along with metadata about how it was retrieved,
    including the source concept, relationship path, and scoring information.
    
    OPTIMIZED: Added optional embedding field to avoid regenerating embeddings
    during semantic reranking. Embeddings are fetched from Milvus during chunk
    resolution and passed through to the reranker.
    
    Validates: Requirements 1.1, 3.5
    """
    chunk_id: str
    content: str
    source: RetrievalSource
    concept_name: Optional[str] = None          # Concept that provided this chunk
    relationship_path: Optional[List[str]] = None  # Path if from related concept
    kg_relevance_score: float = 1.0             # Score based on KG distance
    semantic_score: float = 0.0                 # Score from semantic re-ranking
    final_score: float = 0.0                    # Combined score
    metadata: Dict[str, Any] = field(default_factory=dict)
    embedding: Optional[List[float]] = None     # Stored embedding from Milvus
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            'chunk_id': self.chunk_id,
            'content': self.content,
            'source': self.source.value,
            'concept_name': self.concept_name,
            'relationship_path': self.relationship_path,
            'kg_relevance_score': self.kg_relevance_score,
            'semantic_score': self.semantic_score,
            'final_score': self.final_score,
            'metadata': self.metadata
        }
        # Don't serialize embedding to reduce payload size
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RetrievedChunk':
        """Create from dictionary for JSON deserialization."""
        return cls(
            chunk_id=data['chunk_id'],
            content=data['content'],
            source=RetrievalSource(data['source']),
            concept_name=data.get('concept_name'),
            relationship_path=data.get('relationship_path'),
            kg_relevance_score=data.get('kg_relevance_score', 1.0),
            semantic_score=data.get('semantic_score', 0.0),
            final_score=data.get('final_score', 0.0),
            metadata=data.get('metadata', {}),
            embedding=data.get('embedding')
        )
    
    def validate(self) -> bool:
        """Validate retrieved chunk data integrity."""
        if not self.chunk_id or not self.content:
            return False
        if self.kg_relevance_score < 0.0 or self.kg_relevance_score > 1.0:
            return False
        if self.semantic_score < 0.0 or self.semantic_score > 1.0:
            return False
        return True
    
    def is_from_kg(self) -> bool:
        """Check if chunk was retrieved via knowledge graph."""
        return self.source in (
            RetrievalSource.DIRECT_CONCEPT,
            RetrievalSource.RELATED_CONCEPT,
            RetrievalSource.REASONING_PATH
        )
    
    def is_from_fallback(self) -> bool:
        """Check if chunk was retrieved via fallback/augmentation."""
        return self.source in (
            RetrievalSource.SEMANTIC_FALLBACK,
            RetrievalSource.SEMANTIC_AUGMENT
        )

    def has_embedding(self) -> bool:
        """Check if chunk has a stored embedding."""
        return self.embedding is not None and len(self.embedding) > 0


@dataclass
class QueryDecomposition:
    """Structured decomposition of a user query.
    
    Contains the extracted components from a user query including named entities
    found in the knowledge graph, action words, and subject references.
    
    Validates: Requirements 4.1, 4.2, 4.3, 4.4
    """
    original_query: str
    entities: List[str] = field(default_factory=list)           # Named entities found in KG
    actions: List[str] = field(default_factory=list)            # Action words (observed, found, etc.)
    subjects: List[str] = field(default_factory=list)           # Subject references (our team, etc.)
    concept_matches: List[Dict[str, Any]] = field(default_factory=list)  # Full concept match details
    has_kg_matches: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'original_query': self.original_query,
            'entities': self.entities,
            'actions': self.actions,
            'subjects': self.subjects,
            'concept_matches': self.concept_matches,
            'has_kg_matches': self.has_kg_matches
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'QueryDecomposition':
        """Create from dictionary for JSON deserialization."""
        return cls(
            original_query=data['original_query'],
            entities=data.get('entities', []),
            actions=data.get('actions', []),
            subjects=data.get('subjects', []),
            concept_matches=data.get('concept_matches', []),
            has_kg_matches=data.get('has_kg_matches', False)
        )
    
    def validate(self) -> bool:
        """Validate query decomposition data."""
        if not self.original_query:
            return False
        return True
    
    def is_empty(self) -> bool:
        """Check if decomposition found no components."""
        return (
            not self.entities and 
            not self.actions and 
            not self.subjects and
            not self.concept_matches
        )
    
    def get_entity_count(self) -> int:
        """Get number of extracted entities."""
        return len(self.entities)
    
    def get_concept_ids(self) -> List[str]:
        """Get list of concept IDs from matches."""
        return [
            match.get('concept_id', '') 
            for match in self.concept_matches 
            if match.get('concept_id')
        ]


@dataclass
class KGRetrievalResult:
    """Result of knowledge graph-guided retrieval.
    
    Contains the retrieved chunks along with metadata about the retrieval process
    including query decomposition, explanation, timing, and cache statistics.
    
    Validates: Requirements 1.1, 1.3, 3.5, 5.4, 6.5
    """
    chunks: List[RetrievedChunk] = field(default_factory=list)
    query_decomposition: Optional[QueryDecomposition] = None
    explanation: str = ""
    fallback_used: bool = False
    retrieval_time_ms: int = 0
    stage1_chunk_count: int = 0
    stage2_chunk_count: int = 0
    cache_hits: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    error_details: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'chunks': [chunk.to_dict() for chunk in self.chunks],
            'query_decomposition': self.query_decomposition.to_dict() if self.query_decomposition else None,
            'explanation': self.explanation,
            'fallback_used': self.fallback_used,
            'retrieval_time_ms': self.retrieval_time_ms,
            'stage1_chunk_count': self.stage1_chunk_count,
            'stage2_chunk_count': self.stage2_chunk_count,
            'cache_hits': self.cache_hits,
            'metadata': self.metadata,
            'error': self.error,
            'error_details': self.error_details
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'KGRetrievalResult':
        """Create from dictionary for JSON deserialization."""
        query_decomposition = None
        if data.get('query_decomposition'):
            query_decomposition = QueryDecomposition.from_dict(data['query_decomposition'])
        
        return cls(
            chunks=[RetrievedChunk.from_dict(chunk) for chunk in data.get('chunks', [])],
            query_decomposition=query_decomposition,
            explanation=data.get('explanation', ''),
            fallback_used=data.get('fallback_used', False),
            retrieval_time_ms=data.get('retrieval_time_ms', 0),
            stage1_chunk_count=data.get('stage1_chunk_count', 0),
            stage2_chunk_count=data.get('stage2_chunk_count', 0),
            cache_hits=data.get('cache_hits', 0),
            metadata=data.get('metadata', {}),
            error=data.get('error'),
            error_details=data.get('error_details')
        )
    
    def validate(self) -> bool:
        """Validate retrieval result data."""
        # Validate all chunks
        for chunk in self.chunks:
            if not chunk.validate():
                return False
        
        # Validate query decomposition if present
        if self.query_decomposition and not self.query_decomposition.validate():
            return False
        
        return True
    
    @property
    def has_error(self) -> bool:
        """Check if result contains an error."""
        return self.error is not None
    
    @property
    def chunk_count(self) -> int:
        """Get total number of chunks in result."""
        return len(self.chunks)
    
    def get_chunks_by_source(self, source: RetrievalSource) -> List[RetrievedChunk]:
        """Get chunks filtered by retrieval source."""
        return [chunk for chunk in self.chunks if chunk.source == source]
    
    def get_kg_chunks(self) -> List[RetrievedChunk]:
        """Get chunks retrieved via knowledge graph."""
        return [chunk for chunk in self.chunks if chunk.is_from_kg()]
    
    def get_fallback_chunks(self) -> List[RetrievedChunk]:
        """Get chunks retrieved via fallback/augmentation."""
        return [chunk for chunk in self.chunks if chunk.is_from_fallback()]
    
    def get_source_distribution(self) -> Dict[str, int]:
        """Get distribution of chunks by source."""
        distribution: Dict[str, int] = {}
        for chunk in self.chunks:
            source_name = chunk.source.value
            distribution[source_name] = distribution.get(source_name, 0) + 1
        return distribution


# =============================================================================
# Cache Models
# =============================================================================

@dataclass
class SourceChunksCacheEntry:
    """Cache entry for source_chunks from a concept.
    
    Caches the chunk IDs associated with a concept to avoid repeated
    Neo4j queries for the same concept.
    
    Validates: Requirement 8.2 - cache source_chunks for 5 minutes
    """
    concept_id: str
    concept_name: str
    chunk_ids: List[str] = field(default_factory=list)
    cached_at: float = field(default_factory=time.time)
    ttl_seconds: int = 300  # Default 5 minutes
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'concept_id': self.concept_id,
            'concept_name': self.concept_name,
            'chunk_ids': self.chunk_ids,
            'cached_at': self.cached_at,
            'ttl_seconds': self.ttl_seconds
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SourceChunksCacheEntry':
        """Create from dictionary for JSON deserialization."""
        return cls(
            concept_id=data['concept_id'],
            concept_name=data['concept_name'],
            chunk_ids=data.get('chunk_ids', []),
            cached_at=data.get('cached_at', time.time()),
            ttl_seconds=data.get('ttl_seconds', 300)
        )
    
    def is_expired(self) -> bool:
        """Check if cache entry has expired."""
        return (time.time() - self.cached_at) > self.ttl_seconds
    
    def time_remaining(self) -> float:
        """Get remaining time before expiration in seconds."""
        remaining = self.ttl_seconds - (time.time() - self.cached_at)
        return max(0.0, remaining)
    
    def touch(self) -> None:
        """Reset the cache timestamp (for LRU-style refresh)."""
        self.cached_at = time.time()


@dataclass
class ChunkSourceMapping:
    """Maps chunk IDs to their source concepts and retrieval paths.
    
    Used to track the provenance of each chunk during the retrieval process.
    
    Validates: Requirements 1.1, 2.1, 3.5
    """
    chunk_id: str
    source_concept_id: str
    source_concept_name: str
    retrieval_source: RetrievalSource
    relationship_path: Optional[List[str]] = None
    hop_distance: int = 0
    match_score: float = 1.0  # Concept match score from fulltext search
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'chunk_id': self.chunk_id,
            'source_concept_id': self.source_concept_id,
            'source_concept_name': self.source_concept_name,
            'retrieval_source': self.retrieval_source.value,
            'relationship_path': self.relationship_path,
            'hop_distance': self.hop_distance,
            'match_score': self.match_score,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ChunkSourceMapping':
        """Create from dictionary for JSON deserialization."""
        return cls(
            chunk_id=data['chunk_id'],
            source_concept_id=data['source_concept_id'],
            source_concept_name=data['source_concept_name'],
            retrieval_source=RetrievalSource(data['retrieval_source']),
            relationship_path=data.get('relationship_path'),
            hop_distance=data.get('hop_distance', 0),
            match_score=data.get('match_score', 1.0),
        )
    
    def validate(self) -> bool:
        """Validate chunk source mapping data."""
        if not self.chunk_id or not self.source_concept_id or not self.source_concept_name:
            return False
        if self.hop_distance < 0:
            return False
        return True
    
    def get_relevance_score(self, decay_factor: float = 0.5) -> float:
        """Calculate relevance score based on hop distance.

        Closer concepts (lower hop distance) get higher scores.
        Direct concepts (hop_distance=0) get score 1.0.

        Args:
            decay_factor: Multiplicative decay per hop. Clamped to (0.0, 1.0].
                          Default 0.5 means each hop halves the score.
        """
        # Clamp decay_factor to valid range (0.0, 1.0]
        decay_factor = max(min(decay_factor, 1.0), 0.01)
        if self.hop_distance == 0:
            return 1.0
        return decay_factor ** self.hop_distance


# =============================================================================
# Cross-Reference Data Model
# =============================================================================

@dataclass
class CrossReference:
    """Represents an explicit cross-reference extracted from chunk text.

    Cross-references link a source chunk to a referenced target (e.g.,
    "see Section 3.1", "as discussed in Chapter 4"). During reconciliation,
    resolved_chunk_ids is populated with the chunk IDs that correspond to
    the referenced target.

    Requirements: 5.1
    """
    source_chunk_id: str
    reference_type: str  # 'explicit', 'backward', or 'positional'
    target_type: str     # 'section', 'chapter', 'page', 'figure', 'table'
    target_label: str    # '3.1', '4', etc.
    raw_text: str        # the original matched text
    resolved_chunk_ids: Optional[List[str]] = None


# =============================================================================
# Exception Classes
# =============================================================================

class KGRetrievalError(Exception):
    """Base exception for KG retrieval errors."""
    pass


class Neo4jConnectionError(KGRetrievalError):
    """Raised when Neo4j connection fails."""
    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(message)
        self.original_error = original_error


class ChunkResolutionError(KGRetrievalError):
    """Raised when chunk resolution from OpenSearch fails."""
    def __init__(self, chunk_ids: List[str], message: str = "Failed to resolve chunks"):
        super().__init__(f"{message}: {chunk_ids[:5]}...")
        self.chunk_ids = chunk_ids


class QueryDecompositionError(KGRetrievalError):
    """Raised when query decomposition fails."""
    def __init__(self, query: str, message: str = "Failed to decompose query"):
        super().__init__(f"{message}: {query[:50]}...")
        self.query = query
