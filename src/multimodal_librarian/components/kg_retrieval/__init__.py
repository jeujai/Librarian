"""
Knowledge Graph-Guided Retrieval Components.

This package provides components for the two-stage retrieval pipeline that uses
Neo4j knowledge graph for precise chunk retrieval and semantic re-ranking for
relevance ordering.

Components:
- QueryDecomposer: Extracts entities, actions, and subjects from user queries
- ChunkResolver: Resolves chunk IDs to actual content from OpenSearch
- SemanticReranker: Re-ranks candidate chunks using semantic similarity
- RelevanceDetector: Identifies "no relevant results" scenarios via score distribution and concept specificity
- ExplanationGenerator: Generates human-readable explanations for retrieval results
"""

from .chunk_resolver import ChunkResolver
from .explanation_generator import ExplanationGenerator
from .query_decomposer import QueryDecomposer
from .relevance_detector import RelevanceDetector
from .semantic_reranker import SemanticReranker

__all__ = [
    "ChunkResolver",
    "ExplanationGenerator",
    "QueryDecomposer",
    "RelevanceDetector",
    "SemanticReranker",
]
