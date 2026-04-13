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
from .rrf_parser import (
    MRCONSORow,
    MRDEFRow,
    MRRELRow,
    MRSTYRow,
    parse_mrconso,
    parse_mrdef,
    parse_mrrel,
    parse_mrsty,
    validate_rrf_directory,
)
from .umls_bridger import BridgeResult, UMLSBridger
from .umls_loader import DryRunResult, LoadResult, UMLSLoader, UMLSStats

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
    # RRF Parser
    "MRCONSORow",
    "MRRELRow",
    "MRSTYRow",
    "MRDEFRow",
    "parse_mrconso",
    "parse_mrrel",
    "parse_mrsty",
    "parse_mrdef",
    "validate_rrf_directory",
    # UMLS Loader
    "UMLSLoader",
    "LoadResult",
    "DryRunResult",
    "UMLSStats",
    # UMLS Bridger
    "UMLSBridger",
    "BridgeResult",
]