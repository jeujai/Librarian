#!/usr/bin/env python3
"""
Shared search types and data structures.

This module contains shared types used across search components
to avoid circular import issues.
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from .core import SourceType, ContentType


@dataclass
class SearchResult:
    """
    Represents a search result from vector or semantic search.
    
    This class encapsulates the information returned from various search
    operations including similarity scores, metadata, and content.
    """
    chunk_id: str
    content: str
    source_type: SourceType
    source_id: str
    content_type: ContentType
    location_reference: str
    section: str
    similarity_score: float
    relevance_score: float = 0.0
    is_bridge: bool = False
    created_at: Optional[datetime] = None
    
    # Legacy compatibility fields
    metadata: Dict[str, Any] = None
    document_id: Optional[str] = None
    page_number: Optional[int] = None
    section_title: Optional[str] = None
    timestamp: Optional[datetime] = None
    
    def __post_init__(self):
        """Validate and normalize the search result data."""
        # Ensure similarity score is within valid range
        if self.similarity_score < 0.0:
            self.similarity_score = 0.0
        elif self.similarity_score > 1.0:
            self.similarity_score = 1.0
        
        # Set relevance score if not provided
        if self.relevance_score == 0.0:
            self.relevance_score = self.similarity_score
        
        # Ensure metadata is not None for legacy compatibility
        if self.metadata is None:
            self.metadata = {}
        
        # Set legacy fields for compatibility
        if self.document_id is None:
            self.document_id = self.source_id
        if self.section_title is None:
            self.section_title = self.section
        if self.timestamp is None:
            self.timestamp = self.created_at
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert the search result to a dictionary."""
        return {
            'chunk_id': self.chunk_id,
            'content': self.content,
            'source_type': self.source_type.value if isinstance(self.source_type, SourceType) else self.source_type,
            'source_id': self.source_id,
            'content_type': self.content_type.value if isinstance(self.content_type, ContentType) else self.content_type,
            'location_reference': self.location_reference,
            'section': self.section,
            'similarity_score': self.similarity_score,
            'relevance_score': self.relevance_score,
            'is_bridge': self.is_bridge,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'metadata': self.metadata,
            'document_id': self.document_id,
            'page_number': self.page_number,
            'section_title': self.section_title,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SearchResult':
        """Create a SearchResult from a dictionary."""
        created_at = None
        if data.get('created_at'):
            if isinstance(data['created_at'], str):
                created_at = datetime.fromisoformat(data['created_at'].replace('Z', '+00:00'))
            elif isinstance(data['created_at'], datetime):
                created_at = data['created_at']
        
        timestamp = None
        if data.get('timestamp'):
            if isinstance(data['timestamp'], str):
                timestamp = datetime.fromisoformat(data['timestamp'].replace('Z', '+00:00'))
            elif isinstance(data['timestamp'], datetime):
                timestamp = data['timestamp']
        
        # Handle enum conversion
        source_type = data.get('source_type')
        if isinstance(source_type, str):
            source_type = SourceType(source_type)
        
        content_type = data.get('content_type')
        if isinstance(content_type, str):
            content_type = ContentType(content_type)
        
        return cls(
            chunk_id=data['chunk_id'],
            content=data['content'],
            source_type=source_type,
            source_id=data['source_id'],
            content_type=content_type,
            location_reference=data.get('location_reference', ''),
            section=data.get('section', ''),
            similarity_score=data['similarity_score'],
            relevance_score=data.get('relevance_score', data['similarity_score']),
            is_bridge=data.get('is_bridge', False),
            created_at=created_at,
            metadata=data.get('metadata', {}),
            document_id=data.get('document_id'),
            page_number=data.get('page_number'),
            section_title=data.get('section_title'),
            timestamp=timestamp
        )
    
    @classmethod
    def from_vector_result(cls, vector_result: Dict[str, Any]) -> 'SearchResult':
        """Create SearchResult from vector store result."""
        created_at = None
        if vector_result.get('created_at'):
            if isinstance(vector_result['created_at'], (int, float)):
                created_at = datetime.fromtimestamp(vector_result['created_at'] / 1000)
            elif isinstance(vector_result['created_at'], str):
                created_at = datetime.fromisoformat(vector_result['created_at'].replace('Z', '+00:00'))
            elif isinstance(vector_result['created_at'], datetime):
                created_at = vector_result['created_at']
        
        # Handle enum conversion
        source_type = vector_result.get('source_type')
        if isinstance(source_type, str):
            source_type = SourceType(source_type)
        
        content_type = vector_result.get('content_type')
        if isinstance(content_type, str):
            content_type = ContentType(content_type)
        
        return cls(
            chunk_id=vector_result['chunk_id'],
            content=vector_result['content'],
            source_type=source_type,
            source_id=vector_result['source_id'],
            content_type=content_type,
            location_reference=vector_result.get('location_reference', ''),
            section=vector_result.get('section', ''),
            similarity_score=vector_result['similarity_score'],
            relevance_score=vector_result.get('relevance_score', vector_result['similarity_score']),
            is_bridge=vector_result.get('is_bridge', False) or 'BRIDGE' in vector_result.get('section', ''),
            created_at=created_at,
            metadata=vector_result.get('metadata', {}),
            document_id=vector_result.get('document_id', vector_result['source_id']),
            page_number=vector_result.get('page_number'),
            section_title=vector_result.get('section_title', vector_result.get('section', '')),
            timestamp=created_at
        )


@dataclass
class SearchQuery:
    """
    Represents a search query with parameters and filters.
    """
    query_text: str
    limit: int = 10
    similarity_threshold: float = 0.0
    document_filters: Optional[List[str]] = None
    metadata_filters: Optional[Dict[str, Any]] = None
    include_metadata: bool = True
    
    # Additional fields for query understanding
    processed_query: str = ""
    key_terms: List[str] = field(default_factory=list)
    query_type: str = "general"
    
    def __post_init__(self):
        """Validate and normalize the search query."""
        if self.limit <= 0:
            self.limit = 10
        elif self.limit > 100:
            self.limit = 100
        
        if self.similarity_threshold < 0.0:
            self.similarity_threshold = 0.0
        elif self.similarity_threshold > 1.0:
            self.similarity_threshold = 1.0
        
        if self.document_filters is None:
            self.document_filters = []
        
        if self.metadata_filters is None:
            self.metadata_filters = {}
        
        # Set processed_query if not provided
        if not self.processed_query:
            self.processed_query = self.query_text
        
        # Extract key terms if not provided
        if not self.key_terms:
            self.key_terms = self._extract_key_terms(self.query_text)
    
    def _extract_key_terms(self, text: str) -> List[str]:
        """Extract key terms from query text."""
        import re
        # Simple key term extraction - remove common words
        words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
        common_words = {'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can', 'had', 'her', 'was', 'one', 'our', 'out', 'day', 'get', 'has', 'him', 'his', 'how', 'man', 'new', 'now', 'old', 'see', 'two', 'way', 'who', 'what', 'when', 'where', 'why'}
        return [word for word in words if word not in common_words][:10]
    
    @classmethod
    def from_text(cls, query_text: str, **kwargs) -> 'SearchQuery':
        """Create SearchQuery from text with optional parameters."""
        return cls(query_text=query_text, **kwargs)


@dataclass
class SearchResponse:
    """
    Represents the response from a search operation.
    """
    results: List[SearchResult]
    total_results: int
    query: SearchQuery
    execution_time_ms: float
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert the search response to a dictionary."""
        return {
            'results': [result.to_dict() for result in self.results],
            'total_results': self.total_results,
            'query': {
                'query_text': self.query.query_text,
                'limit': self.query.limit,
                'similarity_threshold': self.query.similarity_threshold,
                'document_filters': self.query.document_filters,
                'metadata_filters': self.query.metadata_filters
            },
            'execution_time_ms': self.execution_time_ms
        }


# Additional search types from hybrid search and query understanding
# These are defined here to avoid circular imports

class QueryIntent(Enum):
    """Types of query intents."""
    FACTUAL = "factual"  # What is X? Define Y
    PROCEDURAL = "procedural"  # How to do X? Steps for Y
    COMPARATIVE = "comparative"  # Compare X and Y, Difference between
    CAUSAL = "causal"  # Why does X happen? What causes Y?
    TEMPORAL = "temporal"  # When did X happen? Timeline of Y
    LOCATIONAL = "locational"  # Where is X? Location of Y
    QUANTITATIVE = "quantitative"  # How many X? What percentage of Y?
    CONCEPTUAL = "conceptual"  # Explain concept X, Theory of Y
    ANALYTICAL = "analytical"  # Analyze X, Evaluate Y
    SYNTHESIS = "synthesis"  # Combine X and Y, Relationship between


class QueryComplexity(Enum):
    """Query complexity levels."""
    SIMPLE = "simple"  # Single concept, direct question
    MODERATE = "moderate"  # Multiple concepts, some relationships
    COMPLEX = "complex"  # Multiple concepts, complex relationships
    MULTI_HOP = "multi_hop"  # Requires reasoning across multiple sources


@dataclass
class QueryEntity:
    """Represents an extracted entity from the query."""
    text: str
    label: str  # PERSON, ORG, CONCEPT, etc.
    start: int
    end: int
    confidence: float = 1.0
    synonyms: List[str] = field(default_factory=list)
    related_terms: List[str] = field(default_factory=list)


@dataclass
class QueryRelation:
    """Represents a relationship between entities in the query."""
    subject: str
    predicate: str
    object: str
    confidence: float = 1.0


@dataclass
class QueryContext:
    """Context information for query understanding."""
    domain: Optional[str] = None  # Technical, medical, legal, etc.
    user_expertise: str = "general"  # beginner, intermediate, expert
    conversation_history: List[str] = field(default_factory=list)
    document_context: List[str] = field(default_factory=list)
    temporal_context: Optional[datetime] = None


@dataclass
class UnderstoodQuery:
    """Comprehensive query understanding result."""
    original_query: str
    normalized_query: str
    intent: QueryIntent
    complexity: QueryComplexity
    entities: List[QueryEntity]
    relations: List[QueryRelation]
    key_concepts: List[str]
    context: QueryContext
    confidence: float
    suggested_expansions: List[str] = field(default_factory=list)
    search_strategy: str = "hybrid"  # vector, keyword, hybrid, knowledge_graph
    explanation: str = ""


@dataclass
class SearchFacets:
    """Search facets for filtering and navigation."""
    source_types: Dict[str, int] = field(default_factory=dict)
    content_types: Dict[str, int] = field(default_factory=dict)
    sources: Dict[str, int] = field(default_factory=dict)
    sections: Dict[str, int] = field(default_factory=dict)
    date_ranges: Dict[str, int] = field(default_factory=dict)


@dataclass
class HybridSearchResult:
    """Enhanced search result with hybrid scoring."""
    search_result: SearchResult
    vector_score: float
    keyword_score: float
    hybrid_score: float
    rerank_score: Optional[float] = None
    final_score: float = 0.0
    explanation: str = ""