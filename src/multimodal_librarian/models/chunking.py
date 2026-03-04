"""
Data models for the Multi-Level Chunking Framework.

This module contains data structures for content profiling, domain configuration,
gap analysis, bridge generation, and validation components.
"""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from .core import BridgeStrategy, ContentType, GapType


@dataclass
class DomainPatterns:
    """Patterns extracted from ConceptNet analysis."""
    relationship_patterns: List[str] = field(default_factory=list)
    structural_patterns: List[str] = field(default_factory=list)
    semantic_patterns: List[str] = field(default_factory=list)
    delimiter_patterns: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'relationship_patterns': self.relationship_patterns,
            'structural_patterns': self.structural_patterns,
            'semantic_patterns': self.semantic_patterns,
            'delimiter_patterns': self.delimiter_patterns
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DomainPatterns':
        """Create from dictionary for JSON deserialization."""
        return cls(
            relationship_patterns=data.get('relationship_patterns', []),
            structural_patterns=data.get('structural_patterns', []),
            semantic_patterns=data.get('semantic_patterns', []),
            delimiter_patterns=data.get('delimiter_patterns', [])
        )


@dataclass
class ChunkingRequirements:
    """Requirements for chunking based on content analysis.
    
    Note: max_chunk_size is set to 300 words (~400 tokens) to ensure
    the entire chunk content fits within embedding model context windows.
    Most embedding models (like all-MiniLM-L6-v2) truncate at 512 tokens,
    so keeping chunks smaller ensures all content is properly embedded.
    """
    preferred_chunk_size: int = 250  # ~300 tokens - optimal for embeddings
    min_chunk_size: int = 50  # Allow smaller chunks for better granularity
    max_chunk_size: int = 350  # ~450 tokens - stays within 512 token limit
    overlap_percentage: float = 0.1
    preserve_sentences: bool = True
    preserve_paragraphs: bool = True
    bridge_threshold: float = 0.7
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'preferred_chunk_size': self.preferred_chunk_size,
            'min_chunk_size': self.min_chunk_size,
            'max_chunk_size': self.max_chunk_size,
            'overlap_percentage': self.overlap_percentage,
            'preserve_sentences': self.preserve_sentences,
            'preserve_paragraphs': self.preserve_paragraphs,
            'bridge_threshold': self.bridge_threshold
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ChunkingRequirements':
        """Create from dictionary for JSON deserialization."""
        return cls(
            preferred_chunk_size=data.get('preferred_chunk_size', 250),
            min_chunk_size=data.get('min_chunk_size', 50),
            max_chunk_size=data.get('max_chunk_size', 350),
            overlap_percentage=data.get('overlap_percentage', 0.1),
            preserve_sentences=data.get('preserve_sentences', True),
            preserve_paragraphs=data.get('preserve_paragraphs', True),
            bridge_threshold=data.get('bridge_threshold', 0.7)
        )


@dataclass
class ContentProfile:
    """Automatically generated content profile for adaptive chunking."""
    content_type: ContentType
    domain_categories: List[str] = field(default_factory=list)
    complexity_score: float = 0.0  # 0.0-1.0 content complexity
    structure_hierarchy: Optional[Dict[str, Any]] = None
    domain_patterns: Optional[DomainPatterns] = None
    cross_reference_density: float = 0.0
    conceptual_density: float = 0.0
    chunking_requirements: Optional[ChunkingRequirements] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'content_type': self.content_type.value,
            'domain_categories': self.domain_categories,
            'complexity_score': self.complexity_score,
            'structure_hierarchy': self.structure_hierarchy,
            'domain_patterns': self.domain_patterns.to_dict() if self.domain_patterns else None,
            'cross_reference_density': self.cross_reference_density,
            'conceptual_density': self.conceptual_density,
            'chunking_requirements': self.chunking_requirements.to_dict() if self.chunking_requirements else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ContentProfile':
        """Create from dictionary for JSON deserialization."""
        return cls(
            content_type=ContentType(data['content_type']),
            domain_categories=data.get('domain_categories', []),
            complexity_score=data.get('complexity_score', 0.0),
            structure_hierarchy=data.get('structure_hierarchy'),
            domain_patterns=DomainPatterns.from_dict(data['domain_patterns']) if data.get('domain_patterns') else None,
            cross_reference_density=data.get('cross_reference_density', 0.0),
            conceptual_density=data.get('conceptual_density', 0.0),
            chunking_requirements=ChunkingRequirements.from_dict(data['chunking_requirements']) if data.get('chunking_requirements') else None
        )
    
    def validate(self) -> bool:
        """Validate content profile data integrity."""
        if self.complexity_score < 0.0 or self.complexity_score > 1.0:
            return False
        if self.cross_reference_density < 0.0 or self.conceptual_density < 0.0:
            return False
        return True


@dataclass
class DelimiterPattern:
    """Pattern for domain-specific delimiters."""
    pattern: str
    priority: int = 1
    context_required: bool = False
    description: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'pattern': self.pattern,
            'priority': self.priority,
            'context_required': self.context_required,
            'description': self.description
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DelimiterPattern':
        """Create from dictionary for JSON deserialization."""
        return cls(
            pattern=data['pattern'],
            priority=data.get('priority', 1),
            context_required=data.get('context_required', False),
            description=data.get('description', '')
        )


@dataclass
class PerformanceMetrics:
    """Performance metrics for domain configurations."""
    chunk_quality_score: float = 0.0
    bridge_success_rate: float = 0.0
    retrieval_effectiveness: float = 0.0
    user_satisfaction_score: float = 0.0
    processing_efficiency: float = 0.0
    boundary_quality: float = 0.0
    measurement_date: datetime = field(default_factory=datetime.now)
    document_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'chunk_quality_score': self.chunk_quality_score,
            'bridge_success_rate': self.bridge_success_rate,
            'retrieval_effectiveness': self.retrieval_effectiveness,
            'user_satisfaction_score': self.user_satisfaction_score,
            'processing_efficiency': self.processing_efficiency,
            'boundary_quality': self.boundary_quality,
            'measurement_date': self.measurement_date.isoformat(),
            'document_count': self.document_count
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PerformanceMetrics':
        """Create from dictionary for JSON deserialization."""
        return cls(
            chunk_quality_score=data.get('chunk_quality_score', 0.0),
            bridge_success_rate=data.get('bridge_success_rate', 0.0),
            retrieval_effectiveness=data.get('retrieval_effectiveness', 0.0),
            user_satisfaction_score=data.get('user_satisfaction_score', 0.0),
            processing_efficiency=data.get('processing_efficiency', 0.0),
            boundary_quality=data.get('boundary_quality', 0.0),
            measurement_date=datetime.fromisoformat(data.get('measurement_date', datetime.now().isoformat())),
            document_count=data.get('document_count', 0)
        )


@dataclass
class DomainConfig:
    """Domain-specific configuration for chunking."""
    domain_name: str
    delimiters: List[DelimiterPattern] = field(default_factory=list)
    chunk_size_modifiers: Dict[str, float] = field(default_factory=dict)
    preservation_patterns: List[str] = field(default_factory=list)
    bridge_thresholds: Dict[str, float] = field(default_factory=dict)
    cross_reference_patterns: List[str] = field(default_factory=list)
    generation_method: str = "hybrid"  # yago, conceptnet, llm, hybrid
    confidence_score: float = 0.0
    performance_baseline: Optional[PerformanceMetrics] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'domain_name': self.domain_name,
            'delimiters': [d.to_dict() for d in self.delimiters],
            'chunk_size_modifiers': self.chunk_size_modifiers,
            'preservation_patterns': self.preservation_patterns,
            'bridge_thresholds': self.bridge_thresholds,
            'cross_reference_patterns': self.cross_reference_patterns,
            'generation_method': self.generation_method,
            'confidence_score': self.confidence_score,
            'performance_baseline': self.performance_baseline.to_dict() if self.performance_baseline else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DomainConfig':
        """Create from dictionary for JSON deserialization."""
        return cls(
            domain_name=data['domain_name'],
            delimiters=[DelimiterPattern.from_dict(d) for d in data.get('delimiters', [])],
            chunk_size_modifiers=data.get('chunk_size_modifiers', {}),
            preservation_patterns=data.get('preservation_patterns', []),
            bridge_thresholds=data.get('bridge_thresholds', {}),
            cross_reference_patterns=data.get('cross_reference_patterns', []),
            generation_method=data.get('generation_method', 'hybrid'),
            confidence_score=data.get('confidence_score', 0.0),
            performance_baseline=PerformanceMetrics.from_dict(data['performance_baseline']) if data.get('performance_baseline') else None
        )
    
    def validate(self) -> bool:
        """Validate domain configuration."""
        if not self.domain_name:
            return False
        if self.confidence_score < 0.0 or self.confidence_score > 1.0:
            return False
        return True


@dataclass
class GapAnalysis:
    """Analysis of conceptual gaps between chunks."""
    necessity_score: float  # 0.0-1.0 bridge necessity
    gap_type: GapType
    bridge_strategy: BridgeStrategy
    semantic_distance: float = 0.0
    concept_overlap: float = 0.0
    cross_reference_density: float = 0.0
    structural_continuity: float = 0.0
    domain_specific_gaps: Dict[str, float] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'necessity_score': self.necessity_score,
            'gap_type': self.gap_type.value,
            'bridge_strategy': self.bridge_strategy.value,
            'semantic_distance': self.semantic_distance,
            'concept_overlap': self.concept_overlap,
            'cross_reference_density': self.cross_reference_density,
            'structural_continuity': self.structural_continuity,
            'domain_specific_gaps': self.domain_specific_gaps
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'GapAnalysis':
        """Create from dictionary for JSON deserialization."""
        return cls(
            necessity_score=data['necessity_score'],
            gap_type=GapType(data['gap_type']),
            bridge_strategy=BridgeStrategy(data['bridge_strategy']),
            semantic_distance=data.get('semantic_distance', 0.0),
            concept_overlap=data.get('concept_overlap', 0.0),
            cross_reference_density=data.get('cross_reference_density', 0.0),
            structural_continuity=data.get('structural_continuity', 0.0),
            domain_specific_gaps=data.get('domain_specific_gaps', {})
        )
    
    def validate(self) -> bool:
        """Validate gap analysis data."""
        if self.necessity_score < 0.0 or self.necessity_score > 1.0:
            return False
        return True


@dataclass
class ValidationDetails:
    """Detailed validation information."""
    semantic_relevance_score: float = 0.0
    factual_consistency_score: float = 0.0
    bidirectional_score: float = 0.0
    validation_method: str = "cross_encoding"
    validation_timestamp: datetime = field(default_factory=datetime.now)
    model_used: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'semantic_relevance_score': self.semantic_relevance_score,
            'factual_consistency_score': self.factual_consistency_score,
            'bidirectional_score': self.bidirectional_score,
            'validation_method': self.validation_method,
            'validation_timestamp': self.validation_timestamp.isoformat(),
            'model_used': self.model_used
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ValidationDetails':
        """Create from dictionary for JSON deserialization."""
        return cls(
            semantic_relevance_score=data.get('semantic_relevance_score', 0.0),
            factual_consistency_score=data.get('factual_consistency_score', 0.0),
            bidirectional_score=data.get('bidirectional_score', 0.0),
            validation_method=data.get('validation_method', 'cross_encoding'),
            validation_timestamp=datetime.fromisoformat(data.get('validation_timestamp', datetime.now().isoformat())),
            model_used=data.get('model_used', '')
        )


@dataclass
class ValidationResult:
    """Result of bridge validation process."""
    individual_scores: Dict[str, float] = field(default_factory=dict)
    composite_score: float = 0.0
    validation_details: Optional[ValidationDetails] = None
    passed_validation: bool = False
    content_type_thresholds: Dict[str, float] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'individual_scores': self.individual_scores,
            'composite_score': self.composite_score,
            'validation_details': self.validation_details.to_dict() if self.validation_details else None,
            'passed_validation': self.passed_validation,
            'content_type_thresholds': self.content_type_thresholds
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ValidationResult':
        """Create from dictionary for JSON deserialization."""
        return cls(
            individual_scores=data.get('individual_scores', {}),
            composite_score=data.get('composite_score', 0.0),
            validation_details=ValidationDetails.from_dict(data['validation_details']) if data.get('validation_details') else None,
            passed_validation=data.get('passed_validation', False),
            content_type_thresholds=data.get('content_type_thresholds', {})
        )
    
    def validate(self) -> bool:
        """Validate validation result data."""
        if self.composite_score < 0.0 or self.composite_score > 1.0:
            return False
        return True


@dataclass
class BridgeChunk:
    """LLM-generated bridge chunk connecting adjacent chunks.
    
    The bridge ID must be a valid UUID string to ensure consistency
    across PostgreSQL and Milvus storage systems.
    """
    content: str
    source_chunks: List[str]  # IDs of connected chunks
    id: str = field(default_factory=lambda: str(uuid.uuid4()))  # UUID for storage consistency
    generation_method: str = "gemini_25_flash"  # gemini_25_flash, mechanical_fallback
    gap_analysis: Optional[GapAnalysis] = None
    validation_result: Optional[ValidationResult] = None
    confidence_score: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)
    metadata: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        """Validate that id is a valid UUID for storage consistency."""
        try:
            uuid.UUID(self.id)
        except (ValueError, TypeError):
            raise ValueError(f"BridgeChunk id must be a valid UUID, got: {self.id}")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'content': self.content,
            'source_chunks': self.source_chunks,
            'generation_method': self.generation_method,
            'gap_analysis': self.gap_analysis.to_dict() if self.gap_analysis else None,
            'validation_result': self.validation_result.to_dict() if self.validation_result else None,
            'confidence_score': self.confidence_score,
            'created_at': self.created_at.isoformat(),
            'metadata': self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BridgeChunk':
        """Create from dictionary for JSON deserialization."""
        return cls(
            id=data.get('id', str(uuid.uuid4())),
            content=data['content'],
            source_chunks=data.get('source_chunks', []),
            generation_method=data.get('generation_method', 'gemini_25_flash'),
            gap_analysis=GapAnalysis.from_dict(data['gap_analysis']) if data.get('gap_analysis') else None,
            validation_result=ValidationResult.from_dict(data['validation_result']) if data.get('validation_result') else None,
            confidence_score=data.get('confidence_score', 0.0),
            created_at=datetime.fromisoformat(data.get('created_at', datetime.now().isoformat())),
            metadata=data.get('metadata'),
        )
    
    def validate(self) -> bool:
        """Validate bridge chunk data."""
        if not self.content or not self.source_chunks:
            return False
        if self.confidence_score < 0.0 or self.confidence_score > 1.0:
            return False
        return True


@dataclass
class OptimizationRecord:
    """Record of configuration optimization."""
    optimization_id: str
    optimization_type: str  # chunk_size_adjustment, bridge_threshold_tuning, etc.
    changes_made: Dict[str, Any] = field(default_factory=dict)
    performance_before: Optional[PerformanceMetrics] = None
    performance_after: Optional[PerformanceMetrics] = None
    improvement_score: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'optimization_id': self.optimization_id,
            'optimization_type': self.optimization_type,
            'changes_made': self.changes_made,
            'performance_before': self.performance_before.to_dict() if self.performance_before else None,
            'performance_after': self.performance_after.to_dict() if self.performance_after else None,
            'improvement_score': self.improvement_score,
            'timestamp': self.timestamp.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'OptimizationRecord':
        """Create from dictionary for JSON deserialization."""
        return cls(
            optimization_id=data['optimization_id'],
            optimization_type=data['optimization_type'],
            changes_made=data.get('changes_made', {}),
            performance_before=PerformanceMetrics.from_dict(data['performance_before']) if data.get('performance_before') else None,
            performance_after=PerformanceMetrics.from_dict(data['performance_after']) if data.get('performance_after') else None,
            improvement_score=data.get('improvement_score', 0.0),
            timestamp=datetime.fromisoformat(data.get('timestamp', datetime.now().isoformat()))
        )


@dataclass
class StoredDomainConfig:
    """Stored domain configuration with versioning and metadata."""
    domain_name: str
    config: DomainConfig
    version: int = 1
    created_at: datetime = field(default_factory=datetime.now)
    generation_method: str = "hybrid"
    source_documents: List[str] = field(default_factory=list)
    performance_score: Optional[float] = None
    optimization_history: List[OptimizationRecord] = field(default_factory=list)
    is_active: bool = True
    usage_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'domain_name': self.domain_name,
            'config': self.config.to_dict(),
            'version': self.version,
            'created_at': self.created_at.isoformat(),
            'generation_method': self.generation_method,
            'source_documents': self.source_documents,
            'performance_score': self.performance_score,
            'optimization_history': [opt.to_dict() for opt in self.optimization_history],
            'is_active': self.is_active,
            'usage_count': self.usage_count
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'StoredDomainConfig':
        """Create from dictionary for JSON deserialization."""
        return cls(
            domain_name=data['domain_name'],
            config=DomainConfig.from_dict(data['config']),
            version=data.get('version', 1),
            created_at=datetime.fromisoformat(data.get('created_at', datetime.now().isoformat())),
            generation_method=data.get('generation_method', 'hybrid'),
            source_documents=data.get('source_documents', []),
            performance_score=data.get('performance_score'),
            optimization_history=[OptimizationRecord.from_dict(opt) for opt in data.get('optimization_history', [])],
            is_active=data.get('is_active', True),
            usage_count=data.get('usage_count', 0)
        )
    
    def validate(self) -> bool:
        """Validate stored domain configuration."""
        if not self.domain_name or not self.config.validate():
            return False
        if self.version < 1:
            return False
        return True


@dataclass
class OptimizationStrategy:
    """Strategy for optimizing domain configurations."""
    type: str  # chunk_size_adjustment, bridge_threshold_tuning, delimiter_refinement
    target_metrics: List[str] = field(default_factory=list)
    adjustments: Dict[str, Any] = field(default_factory=dict)
    expected_improvement: float = 0.0
    confidence: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'type': self.type,
            'target_metrics': self.target_metrics,
            'adjustments': self.adjustments,
            'expected_improvement': self.expected_improvement,
            'confidence': self.confidence
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'OptimizationStrategy':
        """Create from dictionary for JSON deserialization."""
        return cls(
            type=data['type'],
            target_metrics=data.get('target_metrics', []),
            adjustments=data.get('adjustments', {}),
            expected_improvement=data.get('expected_improvement', 0.0),
            confidence=data.get('confidence', 0.0)
        )
    
    def validate(self) -> bool:
        """Validate optimization strategy."""
        if not self.type:
            return False
        if self.expected_improvement < 0.0 or self.confidence < 0.0 or self.confidence > 1.0:
            return False
        return True