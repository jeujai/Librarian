"""
Knowledge Graph Component.

This component builds and manages knowledge graphs from all content sources,
providing concept extraction, relationship discovery, and multi-hop reasoning capabilities.
"""

from .conceptnet_validator import ConceptNetValidator, ValidationResult
from .kg_builder import ConceptExtractor, KnowledgeGraphBuilder, RelationshipExtractor
from .kg_manager import (
    ConflictResolver,
    ExternalKnowledgeBootstrapper,
    KnowledgeGraphManager,
    UserFeedbackIntegrator,
)
from .kg_query_engine import KnowledgeGraphQueryEngine

__all__ = [
    "KnowledgeGraphBuilder", 
    "KnowledgeGraphQueryEngine",
    "KnowledgeGraphManager",
    "ConceptExtractor",
    "RelationshipExtractor",
    "ExternalKnowledgeBootstrapper",
    "ConflictResolver",
    "UserFeedbackIntegrator",
    "ConceptNetValidator",
    "ValidationResult",
]