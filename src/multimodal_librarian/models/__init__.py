"""
Data models and schemas for the Multimodal Librarian system.

This package contains all Pydantic models, database schemas, and data structures
used throughout the application.
"""

# Chunking framework models
from .chunking import (
    BridgeChunk,
    ChunkingRequirements,
    ContentProfile,
    DelimiterPattern,
    DomainConfig,
    DomainPatterns,
    GapAnalysis,
    OptimizationRecord,
    OptimizationStrategy,
    PerformanceMetrics,
    StoredDomainConfig,
    ValidationDetails,
    ValidationResult,
)

# Core data models
from .core import (  # Enums; Core data structures; Chunk is alias for KnowledgeChunk; Conversation models; Multimedia response models
    AudioFile,
    BridgeStrategy,
    Chunk,
    ContentType,
    ConversationChunk,
    ConversationThread,
    DocumentContent,
    DocumentMetadata,
    DocumentStructure,
    ExportMetadata,
    GapType,
    InteractionType,
    KnowledgeChunk,
    KnowledgeCitation,
    KnowledgeMetadata,
    MediaElement,
    Message,
    MessageType,
    MultimediaElement,
    MultimediaResponse,
    RelationshipType,
    SequenceType,
    SourceType,
    VideoFile,
    Visualization,
)

# KG-guided retrieval models
from .kg_retrieval import (
    ChunkResolutionError,
    ChunkSourceMapping,
    KGRetrievalError,
    KGRetrievalResult,
    Neo4jConnectionError,
    QueryDecomposition,
    QueryDecompositionError,
    RetrievalSource,
    RetrievedChunk,
    SourceChunksCacheEntry,
)

# Knowledge graph models
from .knowledge_graph import (
    ConceptExtraction,
    ConceptNode,
    KnowledgeGraphQueryResult,
    KnowledgeGraphStats,
    ReasoningPath,
    RelatedConcept,
    RelationshipEdge,
    Triple,
)

# ML training models
from .ml_training import (
    BatchMetadata,
    ChunkFilters,
    ChunkSequence,
    InteractionFeedback,
    TrainingBatch,
    TrainingChunk,
    TrainingCriteria,
)

__all__ = [
    # Enums
    'SourceType', 'ContentType', 'MessageType', 'GapType', 'BridgeStrategy',
    'SequenceType', 'InteractionType', 'RelationshipType',
    
    # Core models
    'MediaElement', 'DocumentStructure', 'DocumentMetadata', 'DocumentContent',
    'KnowledgeMetadata', 'KnowledgeChunk', 'Chunk',
    'MultimediaElement', 'Message', 'ConversationThread', 'ConversationChunk',
    'Visualization', 'AudioFile', 'VideoFile', 'KnowledgeCitation',
    'ExportMetadata', 'MultimediaResponse',
    
    # Chunking models
    'DomainPatterns', 'ChunkingRequirements', 'ContentProfile',
    'DelimiterPattern', 'PerformanceMetrics', 'DomainConfig',
    'GapAnalysis', 'ValidationDetails', 'ValidationResult',
    'BridgeChunk', 'OptimizationRecord', 'StoredDomainConfig',
    'OptimizationStrategy',
    
    # ML training models
    'BatchMetadata', 'InteractionFeedback', 'TrainingChunk',
    'ChunkSequence', 'TrainingBatch', 'ChunkFilters', 'TrainingCriteria',
    
    # Knowledge graph models
    'Triple', 'ConceptNode', 'RelationshipEdge', 'ReasoningPath',
    'RelatedConcept', 'KnowledgeGraphQueryResult', 'ConceptExtraction',
    'KnowledgeGraphStats',
    
    # KG-guided retrieval models
    'RetrievalSource', 'RetrievedChunk', 'QueryDecomposition',
    'KGRetrievalResult', 'SourceChunksCacheEntry', 'ChunkSourceMapping',
    'KGRetrievalError', 'Neo4jConnectionError', 'ChunkResolutionError',
    'QueryDecompositionError'
]