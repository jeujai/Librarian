# Requirements Document

## Introduction

The codebase has two parallel knowledge graph concept extraction pipelines that run at query time:

1. **Legacy path**: `RAGService.QueryProcessor` calls `KnowledgeGraphQueryEngine.process_graph_enhanced_query()`, which internally uses `_extract_query_concepts_from_neo4j` — a lexical-only `CONTAINS` substring matching approach. This runs on every query in Stage 1 of the RAG pipeline to produce `related_concepts` and `kg_metadata` for query enhancement and confidence scoring.

2. **New path** (already implemented by the semantic-concept-matching spec): `QueryDecomposer` (in `kg_retrieval/query_decomposer.py`) already runs both lexical (full-text index) and semantic (vector ANN via `concept_embedding_index`) matching concurrently via `asyncio.gather`, merges results by `concept_id`, and produces a richer `concept_matches` list with `match_type` annotations. This is used by `KGRetrievalService`.

The legacy path is strictly inferior — it performs a subset of what the existing `QueryDecomposer` already does, with a less efficient query strategy (per-word `CONTAINS` queries instead of batched full-text index + vector search). This feature consolidates the two paths by wiring the existing `QueryDecomposer` into the places that currently use the legacy path, retiring the now-dead legacy code, and simplifying `enhance_vector_search` to accept pre-extracted concepts instead of re-extracting them internally.

## Glossary

- **RAG_Service**: The main Retrieval-Augmented Generation service (`RAGService` in `rag_service.py`) that orchestrates query processing, document search, context preparation, and AI response generation.
- **QueryProcessor**: The inner class of RAG_Service (`QueryProcessor` in `rag_service.py`) that enhances user queries using knowledge graph concepts and AI-based query rewriting.
- **QueryDecomposer**: The existing component (`QueryDecomposer` in `kg_retrieval/query_decomposer.py`) that already decomposes queries into entities, actions, and subjects using both lexical and semantic matching against Neo4j Concept nodes. Implemented by the semantic-concept-matching spec.
- **KG_Query_Engine**: The `KnowledgeGraphQueryEngine` class (`kg_query_engine.py`) that provides multi-hop reasoning, concept disambiguation, and graph-enhanced query processing.
- **Unified_Query_Processor**: The `UnifiedKnowledgeQueryProcessor` class (`query_processor/query_processor.py`) that provides unified search across books and conversations with optional KG enhancement.
- **QueryDecomposition**: The data model returned by QueryDecomposer containing `entities`, `actions`, `subjects`, `concept_matches`, and `has_kg_matches`.
- **KG_Retrieval_Service**: The `KGRetrievalService` that uses QueryDecomposer for KG-guided chunk retrieval.
- **Output_Contract**: The tuple `(enhanced_query, related_concepts, kg_metadata)` returned by `QueryProcessor.process_query()` and consumed by the RAG pipeline.

## Requirements

### Requirement 1: Replace QueryProcessor's KG Dependency with Existing QueryDecomposer

**User Story:** As a developer, I want QueryProcessor to use the existing QueryDecomposer instead of KG_Query_Engine for concept extraction, so that the RAG pipeline benefits from the already-implemented lexical and semantic matching without maintaining redundant code.

#### Acceptance Criteria

1. WHEN QueryProcessor processes a query, THE QueryProcessor SHALL call the existing `QueryDecomposer.decompose()` method to extract concept matches instead of calling `KG_Query_Engine.process_graph_enhanced_query()`.
2. WHEN QueryDecomposer returns concept matches, THE QueryProcessor SHALL map the `concept_matches` list to the existing `related_concepts` list format (list of concept name strings).
3. WHEN QueryDecomposer returns concept matches, THE QueryProcessor SHALL construct `kg_metadata` from the QueryDecomposition fields including match count, match types, and `has_kg_matches` status.
4. THE QueryProcessor SHALL preserve the existing Output_Contract tuple `(enhanced_query, related_concepts, kg_metadata)` so that downstream consumers in the RAG pipeline require no changes.
5. WHEN QueryDecomposer is unavailable (None), THE QueryProcessor SHALL return the original query with empty `related_concepts` and empty `kg_metadata`, maintaining graceful degradation.

### Requirement 2: Dependency Injection for QueryDecomposer in RAG_Service

**User Story:** As a developer, I want QueryDecomposer to be injected into RAG_Service following the project's DI patterns, so that the system remains testable and follows established conventions.

#### Acceptance Criteria

1. THE RAG_Service constructor SHALL accept an optional `query_decomposer` parameter of type QueryDecomposer.
2. WHEN `query_decomposer` is provided, THE RAG_Service SHALL pass it to QueryProcessor instead of KG_Query_Engine.
3. WHEN `query_decomposer` is not provided, THE QueryProcessor SHALL operate without KG concept extraction and return empty concepts.
4. THE DI provider `get_rag_service` in `services.py` SHALL inject the QueryDecomposer instance into RAG_Service when available.
5. THE DI provider SHALL obtain the QueryDecomposer's dependencies (neo4j_client, model_server_client) through existing DI providers without creating new connections at import time.

### Requirement 3: Remove Legacy Concept Extraction Methods

**User Story:** As a developer, I want to remove the redundant concept extraction methods from KG_Query_Engine, so that the codebase has a single concept extraction path and reduced maintenance burden.

#### Acceptance Criteria

1. THE codebase SHALL remove `KG_Query_Engine._extract_query_concepts_from_neo4j`.
2. THE codebase SHALL remove `KG_Query_Engine.process_graph_enhanced_query` and `KG_Query_Engine.process_graph_enhanced_query_async`.
3. THE codebase SHALL remove `KG_Query_Engine._extract_query_concepts` and `KG_Query_Engine._simple_concept_extraction`.
4. THE KG_Query_Engine SHALL retain multi-hop reasoning methods (`multi_hop_reasoning`, `multi_hop_reasoning_async`), relationship traversal methods (`get_related_concepts`, `get_related_concepts_async`, `_find_related_concepts_neo4j`, `_find_paths_between_concepts`, `_find_concepts_by_name`), and re-ranking methods (`enhance_vector_search`, `_rerank_by_concept_relevance`) that serve other purposes.
5. THE codebase SHALL update or remove tests that reference the removed methods.

### Requirement 4: Update Unified_Query_Processor's KG Enhancement

**User Story:** As a developer, I want Unified_Query_Processor to use QueryDecomposer for its KG enhancement step, so that it also benefits from semantic matching and the legacy `process_graph_enhanced_query` caller is eliminated.

#### Acceptance Criteria

1. WHEN Unified_Query_Processor enhances search results with KG reasoning, THE `_enhance_with_reasoning` method SHALL use QueryDecomposer for concept extraction instead of `KG_Query_Engine.process_graph_enhanced_query`.
2. THE Unified_Query_Processor constructor SHALL accept an optional `query_decomposer` parameter.
3. WHEN QueryDecomposer is unavailable, THE Unified_Query_Processor SHALL skip KG enhancement and return unmodified search results.
4. THE `_enhance_with_reasoning` method SHALL continue to use `KG_Query_Engine.enhance_vector_search` for re-ranking vector results using the concepts obtained from QueryDecomposer.

### Requirement 5: Refactor enhance_vector_search to Require Pre-Extracted Concepts

**User Story:** As a developer, I want `KG_Query_Engine.enhance_vector_search` to accept pre-extracted concepts as a required input, so that it no longer contains any concept extraction logic (which is being removed).

#### Acceptance Criteria

1. THE `enhance_vector_search` method SHALL accept a required list of pre-extracted concept names as a parameter.
2. THE `enhance_vector_search` method SHALL use the provided concepts directly for re-ranking and SHALL NOT perform any concept extraction internally.
3. WHEN the provided concept list is empty, THE `enhance_vector_search` method SHALL return the original vector results unmodified.
4. THE callers of `enhance_vector_search` (Unified_Query_Processor and RAG_Service `_semantic_search_documents`) SHALL pass concepts obtained from QueryDecomposer.

### Requirement 6: Preserve RAG Pipeline Behavior

**User Story:** As a user, I want the RAG pipeline to continue producing the same quality of responses after the consolidation, so that the refactoring does not degrade my experience.

#### Acceptance Criteria

1. WHEN a query is processed through the RAG pipeline, THE system SHALL produce `related_concepts` that are a superset of what the legacy path produced (since QueryDecomposer finds both lexical and semantic matches).
2. WHEN a query is processed, THE `kg_metadata` dictionary SHALL contain at minimum the keys `related_concepts` (count) and `has_kg_matches` (boolean).
3. WHEN QueryDecomposer is unavailable and KG_Retrieval_Service is also unavailable, THE RAG pipeline SHALL fall back to pure semantic search without errors.
4. THE confidence scoring in RAG_Service SHALL continue to incorporate KG metadata when available.

### Requirement 7: Update get_knowledge_graph_insights Endpoint

**User Story:** As a developer, I want the `get_knowledge_graph_insights` method on RAG_Service to use the new concept extraction path, so that it does not depend on the retired `process_graph_enhanced_query` method.

#### Acceptance Criteria

1. THE `get_knowledge_graph_insights` method SHALL use QueryDecomposer for concept extraction instead of `KG_Query_Engine.process_graph_enhanced_query`.
2. WHEN QueryDecomposer finds concepts, THE method SHALL use `KG_Query_Engine.multi_hop_reasoning_async` and `KG_Query_Engine.get_related_concepts_async` to build reasoning paths and related concepts.
3. THE method SHALL return the same response structure (reasoning_paths, related_concepts, confidence_scores, explanation) as before.
4. WHEN QueryDecomposer is unavailable, THE method SHALL return a response indicating no concepts were found.
