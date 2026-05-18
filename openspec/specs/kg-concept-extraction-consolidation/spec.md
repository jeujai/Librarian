## Purpose

The codebase has two parallel knowledge graph concept extraction pipelines that run at query time:

1. **Legacy path**: `RAGService.QueryProcessor` calls `KnowledgeGraphQueryEngine.process_graph_enhanced_query()`, which internally uses `_extract_query_concepts_from_neo4j` — a lexical-only `CONTAINS` substring matching approach. This runs on every query in Stage 1 of the RAG pipeline to produce `related_concepts` and `kg_metadata` for query enhancement and confidence scoring.

2. **New path** (already implemented by the semantic-concept-matching spec): `QueryDecomposer` (in `kg_retrieval/query_decomposer.py`) already runs both lexical (full-text index) and semantic (vector ANN via `concept_embedding_index`) matching concurrently via `asyncio.gather`, merges results by `concept_id`, and produces a richer `concept_matches` list with `match_type` annotations. This is used by `KGRetrievalService`.

The legacy path is strictly inferior — it performs a subset of what the existing `QueryDecomposer` already does, with a less efficient query strategy (per-word `CONTAINS` queries instead of batched full-text index + vector search). This feature consolidates the two paths by wiring the existing `QueryDecomposer` into the places that currently use the legacy path, retiring the now-dead legacy code, and simplifying `enhance_vector_search` to accept pre-extracted concepts instead of re-extracting them internally.


### Key Terms
- **RAG_Service**: The main Retrieval-Augmented Generation service (`RAGService` in `rag_service.py`) that orchestrates query processing, document search, context preparation, and AI response generation.
- **QueryProcessor**: The inner class of RAG_Service (`QueryProcessor` in `rag_service.py`) that enhances user queries using knowledge graph concepts and AI-based query rewriting.
- **QueryDecomposer**: The existing component (`QueryDecomposer` in `kg_retrieval/query_decomposer.py`) that already decomposes queries into entities, actions, and subjects using both lexical and semantic matching against Neo4j Concept nodes. Implemented by the semantic-concept-matching spec.
- **KG_Query_Engine**: The `KnowledgeGraphQueryEngine` class (`kg_query_engine.py`) that provides multi-hop reasoning, concept disambiguation, and graph-enhanced query processing.
- **Unified_Query_Processor**: The `UnifiedKnowledgeQueryProcessor` class (`query_processor/query_processor.py`) that provides unified search across books and conversations with optional KG enhancement.
- **QueryDecomposition**: The data model returned by QueryDecomposer containing `entities`, `actions`, `subjects`, `concept_matches`, and `has_kg_matches`.
- **KG_Retrieval_Service**: The `KGRetrievalService` that uses QueryDecomposer for KG-guided chunk retrieval.
- **Output_Contract**: The tuple `(enhanced_query, related_concepts, kg_metadata)` returned by `QueryProcessor.process_query()` and consumed by the RAG pipeline.

## Requirements

### Requirement: Replace QueryProcessor's KG Dependency with Existing QueryDecomposer

The system SHALL support: As a developer, I want QueryProcessor to use the existing QueryDecomposer instead of KG_Query_Engine for concept extraction, so that the RAG pipeline benefits from the already-implemented lexical and semantic matching without maintaining redundant code.

#### Scenario: WHEN QueryProcessor processes a query, THE QueryProcessor SH

- **THEN** WHEN QueryProcessor processes a query, THE QueryProcessor SHALL call the existing `QueryDecomposer.decompose()` method to extract concept matches instead of calling `KG_Query_Engine.process_graph_enhanced_query()`.

#### Scenario: WHEN QueryDecomposer returns concept matches, THE QueryProce

- **THEN** WHEN QueryDecomposer returns concept matches, THE QueryProcessor SHALL map the `concept_matches` list to the existing `related_concepts` list format (list of concept name strings).

#### Scenario: WHEN QueryDecomposer returns concept matches, THE QueryProce

- **THEN** WHEN QueryDecomposer returns concept matches, THE QueryProcessor SHALL construct `kg_metadata` from the QueryDecomposition fields including match count, match types, and `has_kg_matches` status.

#### Scenario: THE QueryProcessor SHALL preserve the existing Output_Contra

- **THEN** THE QueryProcessor SHALL preserve the existing Output_Contract tuple `(enhanced_query, related_concepts, kg_metadata)` so that downstream consumers in the RAG pipeline require no changes.

#### Scenario: WHEN QueryDecomposer is unavailable (None), THE QueryProcess

- **THEN** WHEN QueryDecomposer is unavailable (None), THE QueryProcessor SHALL return the original query with empty `related_concepts` and empty `kg_metadata`, maintaining graceful degradation.

### Requirement: Dependency Injection for QueryDecomposer in RAG_Service

The system SHALL support: As a developer, I want QueryDecomposer to be injected into RAG_Service following the project's DI patterns, so that the system remains testable and follows established conventions.

#### Scenario: THE RAG_Service constructor SHALL accept an optional `query_

- **THEN** THE RAG_Service constructor SHALL accept an optional `query_decomposer` parameter of type QueryDecomposer.

#### Scenario: WHEN `query_decomposer` is provided, THE RAG_Service SHALL p

- **THEN** WHEN `query_decomposer` is provided, THE RAG_Service SHALL pass it to QueryProcessor instead of KG_Query_Engine.

#### Scenario: WHEN `query_decomposer` is not provided, THE QueryProcessor

- **THEN** WHEN `query_decomposer` is not provided, THE QueryProcessor SHALL operate without KG concept extraction and return empty concepts.

#### Scenario: THE DI provider `get_rag_service` in `services.py` SHALL inj

- **THEN** THE DI provider `get_rag_service` in `services.py` SHALL inject the QueryDecomposer instance into RAG_Service when available.

#### Scenario: THE DI provider SHALL obtain the QueryDecomposer's dependenc

- **THEN** THE DI provider SHALL obtain the QueryDecomposer's dependencies (neo4j_client, model_server_client) through existing DI providers without creating new connections at import time.

### Requirement: Remove Legacy Concept Extraction Methods

The system SHALL support: As a developer, I want to remove the redundant concept extraction methods from KG_Query_Engine, so that the codebase has a single concept extraction path and reduced maintenance burden.

#### Scenario: THE codebase SHALL remove `KG_Query_Engine._extract_query_co

- **THEN** THE codebase SHALL remove `KG_Query_Engine._extract_query_concepts_from_neo4j`.

#### Scenario: THE codebase SHALL remove `KG_Query_Engine.process_graph_enh

- **THEN** THE codebase SHALL remove `KG_Query_Engine.process_graph_enhanced_query` and `KG_Query_Engine.process_graph_enhanced_query_async`.

#### Scenario: THE codebase SHALL remove `KG_Query_Engine._extract_query_co

- **THEN** THE codebase SHALL remove `KG_Query_Engine._extract_query_concepts` and `KG_Query_Engine._simple_concept_extraction`.

#### Scenario: THE KG_Query_Engine SHALL retain multi-hop reasoning methods

- **THEN** THE KG_Query_Engine SHALL retain multi-hop reasoning methods (`multi_hop_reasoning`, `multi_hop_reasoning_async`), relationship traversal methods (`get_related_concepts`, `get_related_concepts_async`, `_find_related_concepts_neo4j`, `_find_paths_between_concepts`, `_find_concepts_by_name`), and re-ranking methods (`enhance_vector_search`, `_rerank_by_concept_relevance`) that serve other purposes.

#### Scenario: THE codebase SHALL update or remove tests that reference the

- **THEN** THE codebase SHALL update or remove tests that reference the removed methods.

### Requirement: Update Unified_Query_Processor's KG Enhancement

The system SHALL support: As a developer, I want Unified_Query_Processor to use QueryDecomposer for its KG enhancement step, so that it also benefits from semantic matching and the legacy `process_graph_enhanced_query` caller is eliminated.

#### Scenario: WHEN Unified_Query_Processor enhances search results with KG

- **THEN** WHEN Unified_Query_Processor enhances search results with KG reasoning, THE `_enhance_with_reasoning` method SHALL use QueryDecomposer for concept extraction instead of `KG_Query_Engine.process_graph_enhanced_query`.

#### Scenario: THE Unified_Query_Processor constructor SHALL accept an opti

- **THEN** THE Unified_Query_Processor constructor SHALL accept an optional `query_decomposer` parameter.

#### Scenario: WHEN QueryDecomposer is unavailable, THE Unified_Query_Proce

- **THEN** WHEN QueryDecomposer is unavailable, THE Unified_Query_Processor SHALL skip KG enhancement and return unmodified search results.

#### Scenario: THE `_enhance_with_reasoning` method SHALL continue to use `

- **THEN** THE `_enhance_with_reasoning` method SHALL continue to use `KG_Query_Engine.enhance_vector_search` for re-ranking vector results using the concepts obtained from QueryDecomposer.

### Requirement: Refactor enhance_vector_search to Require Pre-Extracted Concepts

The system SHALL support: As a developer, I want `KG_Query_Engine.enhance_vector_search` to accept pre-extracted concepts as a required input, so that it no longer contains any concept extraction logic (which is being removed).

#### Scenario: THE `enhance_vector_search` method SHALL accept a required l

- **THEN** THE `enhance_vector_search` method SHALL accept a required list of pre-extracted concept names as a parameter.

#### Scenario: THE `enhance_vector_search` method SHALL use the provided co

- **THEN** THE `enhance_vector_search` method SHALL use the provided concepts directly for re-ranking and SHALL NOT perform any concept extraction internally.

#### Scenario: WHEN the provided concept list is empty, THE `enhance_vector

- **THEN** WHEN the provided concept list is empty, THE `enhance_vector_search` method SHALL return the original vector results unmodified.

#### Scenario: THE callers of `enhance_vector_search` (Unified_Query_Proces

- **THEN** THE callers of `enhance_vector_search` (Unified_Query_Processor and RAG_Service `_semantic_search_documents`) SHALL pass concepts obtained from QueryDecomposer.

### Requirement: Preserve RAG Pipeline Behavior

The system SHALL support: As a user, I want the RAG pipeline to continue producing the same quality of responses after the consolidation, so that the refactoring does not degrade my experience.

#### Scenario: WHEN a query is processed through the RAG pipeline, THE syst

- **THEN** WHEN a query is processed through the RAG pipeline, THE system SHALL produce `related_concepts` that are a superset of what the legacy path produced (since QueryDecomposer finds both lexical and semantic matches).

#### Scenario: WHEN a query is processed, THE `kg_metadata` dictionary SHAL

- **THEN** WHEN a query is processed, THE `kg_metadata` dictionary SHALL contain at minimum the keys `related_concepts` (count) and `has_kg_matches` (boolean).

#### Scenario: WHEN QueryDecomposer is unavailable and KG_Retrieval_Service

- **THEN** WHEN QueryDecomposer is unavailable and KG_Retrieval_Service is also unavailable, THE RAG pipeline SHALL fall back to pure semantic search without errors.

#### Scenario: THE confidence scoring in RAG_Service SHALL continue to inco

- **THEN** THE confidence scoring in RAG_Service SHALL continue to incorporate KG metadata when available.

### Requirement: Update get_knowledge_graph_insights Endpoint

The system SHALL support: As a developer, I want the `get_knowledge_graph_insights` method on RAG_Service to use the new concept extraction path, so that it does not depend on the retired `process_graph_enhanced_query` method.

#### Scenario: THE `get_knowledge_graph_insights` method SHALL use QueryDec

- **THEN** THE `get_knowledge_graph_insights` method SHALL use QueryDecomposer for concept extraction instead of `KG_Query_Engine.process_graph_enhanced_query`.

#### Scenario: WHEN QueryDecomposer finds concepts, THE method SHALL use `K

- **THEN** WHEN QueryDecomposer finds concepts, THE method SHALL use `KG_Query_Engine.multi_hop_reasoning_async` and `KG_Query_Engine.get_related_concepts_async` to build reasoning paths and related concepts.

#### Scenario: THE method SHALL return the same response structure (reasoni

- **THEN** THE method SHALL return the same response structure (reasoning_paths, related_concepts, confidence_scores, explanation) as before.

#### Scenario: WHEN QueryDecomposer is unavailable, THE method SHALL return

- **THEN** WHEN QueryDecomposer is unavailable, THE method SHALL return a response indicating no concepts were found.
