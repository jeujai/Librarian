"""
Data models for Machine Learning training integration.

This module contains data structures for ML training APIs, reward signals,
chunk sequences, and training batch management.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional, Any
import numpy as np
from .core import KnowledgeChunk, SequenceType, InteractionType


@dataclass
class BatchMetadata:
    """Metadata for training batches."""
    batch_id: str
    created_at: datetime = field(default_factory=datetime.now)
    total_chunks: int = 0
    total_sequences: int = 0
    content_types: List[str] = field(default_factory=list)
    source_types: List[str] = field(default_factory=list)
    complexity_range: Dict[str, float] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'batch_id': self.batch_id,
            'created_at': self.created_at.isoformat(),
            'total_chunks': self.total_chunks,
            'total_sequences': self.total_sequences,
            'content_types': self.content_types,
            'source_types': self.source_types,
            'complexity_range': self.complexity_range
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BatchMetadata':
        """Create from dictionary for JSON deserialization."""
        return cls(
            batch_id=data['batch_id'],
            created_at=datetime.fromisoformat(data.get('created_at', datetime.now().isoformat())),
            total_chunks=data.get('total_chunks', 0),
            total_sequences=data.get('total_sequences', 0),
            content_types=data.get('content_types', []),
            source_types=data.get('source_types', []),
            complexity_range=data.get('complexity_range', {})
        )


@dataclass
class InteractionFeedback:
    """User interaction feedback for reward signal generation."""
    chunk_id: str
    user_id: str
    interaction_type: InteractionType
    feedback_score: float  # -1.0 to 1.0
    timestamp: datetime = field(default_factory=datetime.now)
    context_query: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'chunk_id': self.chunk_id,
            'user_id': self.user_id,
            'interaction_type': self.interaction_type.value,
            'feedback_score': self.feedback_score,
            'timestamp': self.timestamp.isoformat(),
            'context_query': self.context_query
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'InteractionFeedback':
        """Create from dictionary for JSON deserialization."""
        return cls(
            chunk_id=data['chunk_id'],
            user_id=data['user_id'],
            interaction_type=InteractionType(data['interaction_type']),
            feedback_score=data['feedback_score'],
            timestamp=datetime.fromisoformat(data.get('timestamp', datetime.now().isoformat())),
            context_query=data.get('context_query', '')
        )
    
    def validate(self) -> bool:
        """Validate interaction feedback data."""
        if not self.chunk_id or not self.user_id:
            return False
        if self.feedback_score < -1.0 or self.feedback_score > 1.0:
            return False
        return True


@dataclass
class TrainingChunk:
    """Knowledge chunk enhanced for ML training."""
    knowledge_chunk: KnowledgeChunk
    embedding_vector: np.ndarray
    reward_signal: float = 0.0
    interaction_count: int = 0
    complexity_score: float = 0.0
    temporal_weight: float = 1.0
    related_chunk_ids: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'knowledge_chunk': self.knowledge_chunk.to_dict(),
            'embedding_vector': self.embedding_vector.tolist(),
            'reward_signal': self.reward_signal,
            'interaction_count': self.interaction_count,
            'complexity_score': self.complexity_score,
            'temporal_weight': self.temporal_weight,
            'related_chunk_ids': self.related_chunk_ids
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TrainingChunk':
        """Create from dictionary for JSON deserialization."""
        return cls(
            knowledge_chunk=KnowledgeChunk.from_dict(data['knowledge_chunk']),
            embedding_vector=np.array(data['embedding_vector']),
            reward_signal=data.get('reward_signal', 0.0),
            interaction_count=data.get('interaction_count', 0),
            complexity_score=data.get('complexity_score', 0.0),
            temporal_weight=data.get('temporal_weight', 1.0),
            related_chunk_ids=data.get('related_chunk_ids', [])
        )
    
    def validate(self) -> bool:
        """Validate training chunk data."""
        if not self.knowledge_chunk.validate():
            return False
        if self.embedding_vector is None or len(self.embedding_vector) == 0:
            return False
        if self.interaction_count < 0:
            return False
        return True
    
    def get_chunk_id(self) -> str:
        """Get the chunk ID from the knowledge chunk."""
        return self.knowledge_chunk.id
    
    def update_reward_signal(self, feedback: InteractionFeedback) -> None:
        """Update reward signal based on new feedback."""
        # Simple weighted average with decay for older interactions
        weight = 1.0 / (self.interaction_count + 1)
        self.reward_signal = (self.reward_signal * (1 - weight)) + (feedback.feedback_score * weight)
        self.interaction_count += 1


@dataclass
class ChunkSequence:
    """Ordered sequence of related knowledge chunks for sequential ML training."""
    sequence_id: str
    chunks: List[TrainingChunk]
    sequence_type: SequenceType
    coherence_score: float = 0.0
    total_reward: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'sequence_id': self.sequence_id,
            'chunks': [chunk.to_dict() for chunk in self.chunks],
            'sequence_type': self.sequence_type.value,
            'coherence_score': self.coherence_score,
            'total_reward': self.total_reward
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ChunkSequence':
        """Create from dictionary for JSON deserialization."""
        return cls(
            sequence_id=data['sequence_id'],
            chunks=[TrainingChunk.from_dict(chunk) for chunk in data['chunks']],
            sequence_type=SequenceType(data['sequence_type']),
            coherence_score=data.get('coherence_score', 0.0),
            total_reward=data.get('total_reward', 0.0)
        )
    
    def validate(self) -> bool:
        """Validate chunk sequence data."""
        if not self.sequence_id or not self.chunks:
            return False
        
        # Validate all chunks in sequence
        for chunk in self.chunks:
            if not chunk.validate():
                return False
        
        return True
    
    def get_sequence_length(self) -> int:
        """Get the number of chunks in the sequence."""
        return len(self.chunks)
    
    def calculate_total_reward(self) -> float:
        """Calculate total reward for the sequence."""
        if not self.chunks:
            return 0.0
        
        total = sum(chunk.reward_signal for chunk in self.chunks)
        self.total_reward = total / len(self.chunks)  # Average reward
        return self.total_reward
    
    def get_chunk_ids(self) -> List[str]:
        """Get list of chunk IDs in the sequence."""
        return [chunk.get_chunk_id() for chunk in self.chunks]


@dataclass
class TrainingBatch:
    """Batch of training data for ML models."""
    batch_id: str
    chunks: List[TrainingChunk]
    sequences: List[ChunkSequence]
    batch_metadata: BatchMetadata
    reward_distribution: Dict[str, float] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'batch_id': self.batch_id,
            'chunks': [chunk.to_dict() for chunk in self.chunks],
            'sequences': [seq.to_dict() for seq in self.sequences],
            'batch_metadata': self.batch_metadata.to_dict(),
            'reward_distribution': self.reward_distribution
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TrainingBatch':
        """Create from dictionary for JSON deserialization."""
        return cls(
            batch_id=data['batch_id'],
            chunks=[TrainingChunk.from_dict(chunk) for chunk in data['chunks']],
            sequences=[ChunkSequence.from_dict(seq) for seq in data['sequences']],
            batch_metadata=BatchMetadata.from_dict(data['batch_metadata']),
            reward_distribution=data.get('reward_distribution', {})
        )
    
    def validate(self) -> bool:
        """Validate training batch data."""
        if not self.batch_id:
            return False
        
        # Validate all chunks
        for chunk in self.chunks:
            if not chunk.validate():
                return False
        
        # Validate all sequences
        for sequence in self.sequences:
            if not sequence.validate():
                return False
        
        return True
    
    def get_total_chunks(self) -> int:
        """Get total number of chunks in the batch."""
        return len(self.chunks)
    
    def get_total_sequences(self) -> int:
        """Get total number of sequences in the batch."""
        return len(self.sequences)
    
    def calculate_reward_distribution(self) -> Dict[str, float]:
        """Calculate reward distribution statistics."""
        if not self.chunks:
            return {}
        
        rewards = [chunk.reward_signal for chunk in self.chunks]
        
        self.reward_distribution = {
            'mean': np.mean(rewards),
            'std': np.std(rewards),
            'min': np.min(rewards),
            'max': np.max(rewards),
            'median': np.median(rewards)
        }
        
        return self.reward_distribution
    
    def filter_by_reward_threshold(self, threshold: float) -> 'TrainingBatch':
        """Create new batch with chunks above reward threshold."""
        filtered_chunks = [chunk for chunk in self.chunks if chunk.reward_signal >= threshold]
        
        # Update metadata
        new_metadata = BatchMetadata(
            batch_id=f"{self.batch_id}_filtered_{threshold}",
            total_chunks=len(filtered_chunks),
            total_sequences=len(self.sequences),  # Keep sequences unchanged
            content_types=self.batch_metadata.content_types,
            source_types=self.batch_metadata.source_types,
            complexity_range=self.batch_metadata.complexity_range
        )
        
        return TrainingBatch(
            batch_id=new_metadata.batch_id,
            chunks=filtered_chunks,
            sequences=self.sequences,
            batch_metadata=new_metadata,
            reward_distribution={}
        )


@dataclass
class ChunkFilters:
    """Filters for knowledge chunk streaming."""
    content_types: Optional[List[str]] = None
    source_types: Optional[List[str]] = None
    complexity_range: Optional[Dict[str, float]] = None
    temporal_range: Optional[Dict[str, datetime]] = None
    reward_threshold: Optional[float] = None
    interaction_threshold: Optional[int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        temporal_dict = None
        if self.temporal_range:
            temporal_dict = {
                key: value.isoformat() if isinstance(value, datetime) else value
                for key, value in self.temporal_range.items()
            }
        
        return {
            'content_types': self.content_types,
            'source_types': self.source_types,
            'complexity_range': self.complexity_range,
            'temporal_range': temporal_dict,
            'reward_threshold': self.reward_threshold,
            'interaction_threshold': self.interaction_threshold
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ChunkFilters':
        """Create from dictionary for JSON deserialization."""
        temporal_range = None
        if data.get('temporal_range'):
            temporal_range = {
                key: datetime.fromisoformat(value) if isinstance(value, str) else value
                for key, value in data['temporal_range'].items()
            }
        
        return cls(
            content_types=data.get('content_types'),
            source_types=data.get('source_types'),
            complexity_range=data.get('complexity_range'),
            temporal_range=temporal_range,
            reward_threshold=data.get('reward_threshold'),
            interaction_threshold=data.get('interaction_threshold')
        )
    
    def matches_chunk(self, chunk: TrainingChunk) -> bool:
        """Check if a chunk matches the filter criteria."""
        # Check content type
        if self.content_types and chunk.knowledge_chunk.content_type.value not in self.content_types:
            return False
        
        # Check source type
        if self.source_types and chunk.knowledge_chunk.source_type.value not in self.source_types:
            return False
        
        # Check complexity range
        if self.complexity_range:
            min_complexity = self.complexity_range.get('min', 0.0)
            max_complexity = self.complexity_range.get('max', 1.0)
            if not (min_complexity <= chunk.complexity_score <= max_complexity):
                return False
        
        # Check reward threshold
        if self.reward_threshold is not None and chunk.reward_signal < self.reward_threshold:
            return False
        
        # Check interaction threshold
        if self.interaction_threshold is not None and chunk.interaction_count < self.interaction_threshold:
            return False
        
        return True


@dataclass
class TrainingCriteria:
    """Criteria for training batch generation."""
    batch_size: int = 100
    include_sequences: bool = True
    sequence_length: int = 5
    balance_content_types: bool = True
    balance_source_types: bool = True
    reward_weighting: bool = True
    temporal_weighting: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'batch_size': self.batch_size,
            'include_sequences': self.include_sequences,
            'sequence_length': self.sequence_length,
            'balance_content_types': self.balance_content_types,
            'balance_source_types': self.balance_source_types,
            'reward_weighting': self.reward_weighting,
            'temporal_weighting': self.temporal_weighting
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TrainingCriteria':
        """Create from dictionary for JSON deserialization."""
        return cls(
            batch_size=data.get('batch_size', 100),
            include_sequences=data.get('include_sequences', True),
            sequence_length=data.get('sequence_length', 5),
            balance_content_types=data.get('balance_content_types', True),
            balance_source_types=data.get('balance_source_types', True),
            reward_weighting=data.get('reward_weighting', True),
            temporal_weighting=data.get('temporal_weighting', True)
        )
    
    def validate(self) -> bool:
        """Validate training criteria."""
        if self.batch_size <= 0 or self.sequence_length <= 0:
            return False
        return True