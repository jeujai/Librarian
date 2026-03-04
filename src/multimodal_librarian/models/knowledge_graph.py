"""
Data models for Knowledge Graph components.

This module contains data structures for concepts, relationships, reasoning paths,
and knowledge graph query results.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from .core import KnowledgeChunk, RelationshipType


@dataclass
class Triple:
    """Knowledge graph triple (subject, predicate, object)."""
    subject: str
    predicate: str
    object: str
    confidence: float = 0.0
    source_id: str = ""
    extraction_method: str = "LLM"  # LLM, NER, EMBEDDING
    created_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'subject': self.subject,
            'predicate': self.predicate,
            'object': self.object,
            'confidence': self.confidence,
            'source_id': self.source_id,
            'extraction_method': self.extraction_method,
            'created_at': self.created_at.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Triple':
        """Create from dictionary for JSON deserialization."""
        return cls(
            subject=data['subject'],
            predicate=data['predicate'],
            object=data['object'],
            confidence=data.get('confidence', 0.0),
            source_id=data.get('source_id', ''),
            extraction_method=data.get('extraction_method', 'LLM'),
            created_at=datetime.fromisoformat(data.get('created_at', datetime.now().isoformat()))
        )
    
    def validate(self) -> bool:
        """Validate triple data."""
        if not self.subject or not self.predicate or not self.object:
            return False
        if self.confidence < 0.0 or self.confidence > 1.0:
            return False
        return True
    
    def get_triple_string(self) -> str:
        """Get string representation of the triple."""
        return f"({self.subject}, {self.predicate}, {self.object})"


@dataclass
class ConceptNode:
    """Node representing a concept in the knowledge graph."""
    concept_id: str
    concept_name: str
    concept_type: str = "ENTITY"  # ENTITY, PROCESS, PROPERTY, etc.
    aliases: List[str] = field(default_factory=list)
    confidence: float = 0.0
    source_chunks: List[str] = field(default_factory=list)
    source_document: Optional[str] = None  # Document ID for cross-document linking
    external_ids: Dict[str, str] = field(default_factory=dict)  # YAGO, ConceptNet IDs
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'concept_id': self.concept_id,
            'concept_name': self.concept_name,
            'concept_type': self.concept_type,
            'aliases': self.aliases,
            'confidence': self.confidence,
            'source_chunks': self.source_chunks,
            'source_document': self.source_document,
            'external_ids': self.external_ids
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ConceptNode':
        """Create from dictionary for JSON deserialization."""
        return cls(
            concept_id=data['concept_id'],
            concept_name=data['concept_name'],
            concept_type=data.get('concept_type', 'ENTITY'),
            aliases=data.get('aliases', []),
            confidence=data.get('confidence', 0.0),
            source_chunks=data.get('source_chunks', []),
            source_document=data.get('source_document'),
            external_ids=data.get('external_ids', {})
        )
    
    def validate(self) -> bool:
        """Validate concept node data."""
        if not self.concept_id or not self.concept_name:
            return False
        if self.confidence < 0.0 or self.confidence > 1.0:
            return False
        return True
    
    def add_alias(self, alias: str) -> None:
        """Add an alias to the concept."""
        if alias not in self.aliases:
            self.aliases.append(alias)
    
    def add_source_chunk(self, chunk_id: str) -> None:
        """Add a source chunk reference."""
        if chunk_id not in self.source_chunks:
            self.source_chunks.append(chunk_id)
    
    def has_external_id(self, source: str) -> bool:
        """Check if concept has external ID from specific source."""
        return source in self.external_ids


@dataclass
class RelationshipEdge:
    """Edge representing a relationship in the knowledge graph."""
    subject_concept: str
    predicate: str
    object_concept: str
    confidence: float = 0.0
    evidence_chunks: List[str] = field(default_factory=list)
    relationship_type: RelationshipType = RelationshipType.ASSOCIATIVE
    raw_relation_type: Optional[str] = None
    bidirectional: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'subject_concept': self.subject_concept,
            'predicate': self.predicate,
            'object_concept': self.object_concept,
            'confidence': self.confidence,
            'evidence_chunks': self.evidence_chunks,
            'relationship_type': self.relationship_type.value,
            'raw_relation_type': self.raw_relation_type,
            'bidirectional': self.bidirectional
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RelationshipEdge':
        """Create from dictionary for JSON deserialization."""
        return cls(
            subject_concept=data['subject_concept'],
            predicate=data['predicate'],
            object_concept=data['object_concept'],
            confidence=data.get('confidence', 0.0),
            evidence_chunks=data.get('evidence_chunks', []),
            relationship_type=RelationshipType(data.get('relationship_type', 'associative')),
            raw_relation_type=data.get('raw_relation_type'),
            bidirectional=data.get('bidirectional', False)
        )
    
    def validate(self) -> bool:
        """Validate relationship edge data."""
        if not self.subject_concept or not self.predicate or not self.object_concept:
            return False
        if self.confidence < 0.0 or self.confidence > 1.0:
            return False
        return True
    
    def add_evidence_chunk(self, chunk_id: str) -> None:
        """Add evidence chunk to support this relationship."""
        if chunk_id not in self.evidence_chunks:
            self.evidence_chunks.append(chunk_id)
    
    def get_relationship_string(self) -> str:
        """Get string representation of the relationship."""
        return f"{self.subject_concept} --[{self.predicate}]--> {self.object_concept}"


@dataclass
class ReasoningPath:
    """Path through the knowledge graph for multi-hop reasoning."""
    start_concept: str
    end_concept: str
    path_steps: List[RelationshipEdge]
    total_confidence: float = 0.0
    path_length: int = 0
    reasoning_type: str = "CAUSAL_CHAIN"  # CAUSAL_CHAIN, HIERARCHICAL, ANALOGICAL
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'start_concept': self.start_concept,
            'end_concept': self.end_concept,
            'path_steps': [step.to_dict() for step in self.path_steps],
            'total_confidence': self.total_confidence,
            'path_length': self.path_length,
            'reasoning_type': self.reasoning_type
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ReasoningPath':
        """Create from dictionary for JSON deserialization."""
        return cls(
            start_concept=data['start_concept'],
            end_concept=data['end_concept'],
            path_steps=[RelationshipEdge.from_dict(step) for step in data['path_steps']],
            total_confidence=data.get('total_confidence', 0.0),
            path_length=data.get('path_length', 0),
            reasoning_type=data.get('reasoning_type', 'CAUSAL_CHAIN')
        )
    
    def validate(self) -> bool:
        """Validate reasoning path data."""
        if not self.start_concept or not self.end_concept:
            return False
        if not self.path_steps:
            return False
        
        # Validate all path steps
        for step in self.path_steps:
            if not step.validate():
                return False
        
        # Validate path continuity
        for i in range(len(self.path_steps) - 1):
            current_end = self.path_steps[i].object_concept
            next_start = self.path_steps[i + 1].subject_concept
            if current_end != next_start:
                return False
        
        return True
    
    def calculate_confidence(self) -> float:
        """Calculate total confidence for the reasoning path."""
        if not self.path_steps:
            return 0.0
        
        # Use geometric mean to penalize weak links
        confidences = [step.confidence for step in self.path_steps]
        product = 1.0
        for conf in confidences:
            product *= conf
        
        self.total_confidence = product ** (1.0 / len(confidences))
        return self.total_confidence
    
    def get_path_length(self) -> int:
        """Get the length of the reasoning path."""
        self.path_length = len(self.path_steps)
        return self.path_length
    
    def get_path_description(self) -> str:
        """Get human-readable description of the reasoning path."""
        if not self.path_steps:
            return f"No path from {self.start_concept} to {self.end_concept}"
        
        description = f"{self.start_concept}"
        for step in self.path_steps:
            description += f" --[{step.predicate}]--> {step.object_concept}"
        
        return description


@dataclass
class RelatedConcept:
    """Concept related to a query concept through specific relationships."""
    concept: ConceptNode
    relationship_path: List[RelationshipEdge]
    relevance_score: float = 0.0
    distance: int = 1
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'concept': self.concept.to_dict(),
            'relationship_path': [rel.to_dict() for rel in self.relationship_path],
            'relevance_score': self.relevance_score,
            'distance': self.distance
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RelatedConcept':
        """Create from dictionary for JSON deserialization."""
        return cls(
            concept=ConceptNode.from_dict(data['concept']),
            relationship_path=[RelationshipEdge.from_dict(rel) for rel in data['relationship_path']],
            relevance_score=data.get('relevance_score', 0.0),
            distance=data.get('distance', 1)
        )
    
    def validate(self) -> bool:
        """Validate related concept data."""
        if not self.concept.validate():
            return False
        if self.relevance_score < 0.0 or self.relevance_score > 1.0:
            return False
        if self.distance < 1:
            return False
        return True


@dataclass
class KnowledgeGraphQueryResult:
    """Result of a knowledge graph query with reasoning."""
    reasoning_paths: List[ReasoningPath] = field(default_factory=list)
    related_concepts: List[RelatedConcept] = field(default_factory=list)
    enhanced_chunks: List[KnowledgeChunk] = field(default_factory=list)
    confidence_scores: Dict[str, float] = field(default_factory=dict)
    explanation: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'reasoning_paths': [path.to_dict() for path in self.reasoning_paths],
            'related_concepts': [concept.to_dict() for concept in self.related_concepts],
            'enhanced_chunks': [chunk.to_dict() for chunk in self.enhanced_chunks],
            'confidence_scores': self.confidence_scores,
            'explanation': self.explanation
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'KnowledgeGraphQueryResult':
        """Create from dictionary for JSON deserialization."""
        return cls(
            reasoning_paths=[ReasoningPath.from_dict(path) for path in data.get('reasoning_paths', [])],
            related_concepts=[RelatedConcept.from_dict(concept) for concept in data.get('related_concepts', [])],
            enhanced_chunks=[KnowledgeChunk.from_dict(chunk) for chunk in data.get('enhanced_chunks', [])],
            confidence_scores=data.get('confidence_scores', {}),
            explanation=data.get('explanation', '')
        )
    
    def validate(self) -> bool:
        """Validate knowledge graph query result."""
        # Validate all reasoning paths
        for path in self.reasoning_paths:
            if not path.validate():
                return False
        
        # Validate all related concepts
        for concept in self.related_concepts:
            if not concept.validate():
                return False
        
        # Validate all enhanced chunks
        for chunk in self.enhanced_chunks:
            if not chunk.validate():
                return False
        
        return True
    
    def get_best_reasoning_path(self) -> Optional[ReasoningPath]:
        """Get the reasoning path with highest confidence."""
        if not self.reasoning_paths:
            return None
        
        return max(self.reasoning_paths, key=lambda path: path.total_confidence)
    
    def get_top_related_concepts(self, limit: int = 5) -> List[RelatedConcept]:
        """Get top related concepts by relevance score."""
        sorted_concepts = sorted(self.related_concepts, 
                               key=lambda concept: concept.relevance_score, 
                               reverse=True)
        return sorted_concepts[:limit]
    
    def has_reasoning_paths(self) -> bool:
        """Check if result contains reasoning paths."""
        return len(self.reasoning_paths) > 0
    
    def has_related_concepts(self) -> bool:
        """Check if result contains related concepts."""
        return len(self.related_concepts) > 0


@dataclass
class ConceptExtraction:
    """Record of concept extraction from a chunk."""
    extraction_id: str
    chunk_id: str
    extracted_concepts: List[ConceptNode]
    extracted_relationships: List[RelationshipEdge]
    extraction_method: str = "LLM"
    confidence_score: float = 0.0
    extraction_timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'extraction_id': self.extraction_id,
            'chunk_id': self.chunk_id,
            'extracted_concepts': [concept.to_dict() for concept in self.extracted_concepts],
            'extracted_relationships': [rel.to_dict() for rel in self.extracted_relationships],
            'extraction_method': self.extraction_method,
            'confidence_score': self.confidence_score,
            'extraction_timestamp': self.extraction_timestamp.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ConceptExtraction':
        """Create from dictionary for JSON deserialization."""
        return cls(
            extraction_id=data['extraction_id'],
            chunk_id=data['chunk_id'],
            extracted_concepts=[ConceptNode.from_dict(concept) for concept in data['extracted_concepts']],
            extracted_relationships=[RelationshipEdge.from_dict(rel) for rel in data['extracted_relationships']],
            extraction_method=data.get('extraction_method', 'LLM'),
            confidence_score=data.get('confidence_score', 0.0),
            extraction_timestamp=datetime.fromisoformat(data.get('extraction_timestamp', datetime.now().isoformat()))
        )
    
    def validate(self) -> bool:
        """Validate concept extraction data."""
        if not self.extraction_id or not self.chunk_id:
            return False
        
        # Validate extracted concepts
        for concept in self.extracted_concepts:
            if not concept.validate():
                return False
        
        # Validate extracted relationships
        for relationship in self.extracted_relationships:
            if not relationship.validate():
                return False
        
        if self.confidence_score < 0.0 or self.confidence_score > 1.0:
            return False
        
        return True
    
    def get_concept_count(self) -> int:
        """Get number of extracted concepts."""
        return len(self.extracted_concepts)
    
    def get_relationship_count(self) -> int:
        """Get number of extracted relationships."""
        return len(self.extracted_relationships)


@dataclass
class KnowledgeGraphStats:
    """Statistics about the knowledge graph."""
    total_concepts: int = 0
    total_relationships: int = 0
    concept_types: Dict[str, int] = field(default_factory=dict)
    relationship_types: Dict[str, int] = field(default_factory=dict)
    average_confidence: float = 0.0
    last_updated: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'total_concepts': self.total_concepts,
            'total_relationships': self.total_relationships,
            'concept_types': self.concept_types,
            'relationship_types': self.relationship_types,
            'average_confidence': self.average_confidence,
            'last_updated': self.last_updated.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'KnowledgeGraphStats':
        """Create from dictionary for JSON deserialization."""
        return cls(
            total_concepts=data.get('total_concepts', 0),
            total_relationships=data.get('total_relationships', 0),
            concept_types=data.get('concept_types', {}),
            relationship_types=data.get('relationship_types', {}),
            average_confidence=data.get('average_confidence', 0.0),
            last_updated=datetime.fromisoformat(data.get('last_updated', datetime.now().isoformat()))
        )
    
    def update_stats(self, concepts: List[ConceptNode], relationships: List[RelationshipEdge]) -> None:
        """Update statistics based on current graph state."""
        self.total_concepts = len(concepts)
        self.total_relationships = len(relationships)
        
        # Count concept types
        self.concept_types = {}
        for concept in concepts:
            concept_type = concept.concept_type
            self.concept_types[concept_type] = self.concept_types.get(concept_type, 0) + 1
        
        # Count relationship types
        self.relationship_types = {}
        for relationship in relationships:
            rel_type = relationship.relationship_type.value
            self.relationship_types[rel_type] = self.relationship_types.get(rel_type, 0) + 1
        
        # Calculate average confidence
        all_confidences = [concept.confidence for concept in concepts] + [rel.confidence for rel in relationships]
        if all_confidences:
            self.average_confidence = sum(all_confidences) / len(all_confidences)
        else:
            self.average_confidence = 0.0
        
        self.last_updated = datetime.now()