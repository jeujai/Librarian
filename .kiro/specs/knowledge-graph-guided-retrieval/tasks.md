# Implementation Plan: Knowledge Graph-Guided Retrieval

## Overview

This implementation plan breaks down the Knowledge Graph-Guided Retrieval feature into discrete coding tasks. The feature implements a two-stage retrieval pipeline that uses Neo4j knowledge graph for precise chunk retrieval and semantic re-ranking for relevance ordering.

## Tasks

- [x] 1. Create core data models and types
  - [x] 1.1 Create data models in `src/multimodal_librarian/models/kg_retrieval.py`
    - Define RetrievalSource enum
    - Define RetrievedChunk dataclass
    - Define QueryDecomposition dataclass
    - Define KGRetrievalResult dataclass
    - Define SourceChunksCacheEntry dataclass
    - Define ChunkSourceMapping dataclass
    - _Requirements: 1.1, 1.3, 3.5, 5.4_

  - [ ]* 1.2 Write unit tests for data models
    - Test dataclass initialization
    - Test cache entry expiration logic
    - _Requirements: 1.1_

- [x] 2. Implement QueryDecomposer component
  - [x] 2.1 Create QueryDecomposer in `src/multimodal_librarian/components/kg_retrieval/query_decomposer.py`
    - Implement `__init__` with Neo4j client injection
    - Implement `decompose()` async method
    - Implement `_find_entity_matches()` for Neo4j concept lookup
    - Implement `_extract_actions()` for action word detection
    - Implement `_extract_subjects()` for subject pattern matching
    - Define ACTION_WORDS and SUBJECT_PATTERNS constants
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [ ]* 2.2 Write property test for query decomposition completeness
    - **Property 7: Query Decomposition Completeness**
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.4**

  - [ ]* 2.3 Write unit tests for QueryDecomposer
    - Test action word extraction
    - Test subject reference extraction
    - Test empty decomposition when no matches
    - _Requirements: 4.1, 4.2, 4.3, 4.5_

- [x] 3. Implement ChunkResolver component
  - [x] 3.1 Create ChunkResolver in `src/multimodal_librarian/components/kg_retrieval/chunk_resolver.py`
    - Implement `__init__` with OpenSearch client injection
    - Implement `resolve_chunks()` async method with parallel resolution
    - Implement `_resolve_single_chunk()` for individual chunk lookup
    - Handle missing chunks gracefully with logging
    - _Requirements: 1.2, 1.4_

  - [ ]* 3.2 Write unit tests for ChunkResolver
    - Test successful chunk resolution
    - Test graceful handling of missing chunks
    - Test parallel resolution behavior
    - _Requirements: 1.2, 1.4_

- [x] 4. Implement SemanticReranker component
  - [x] 4.1 Create SemanticReranker in `src/multimodal_librarian/components/kg_retrieval/semantic_reranker.py`
    - Implement `__init__` with OpenSearch client and weight configuration
    - Implement `rerank()` async method
    - Implement `_calculate_final_score()` for weighted scoring
    - Use OpenSearch for query embedding generation
    - _Requirements: 3.2_

  - [ ]* 4.2 Write property test for semantic re-ranking order
    - **Property 3: Semantic Re-ranking Preserves Relevance Order**
    - **Validates: Requirements 3.2**

  - [ ]* 4.3 Write unit tests for SemanticReranker
    - Test score calculation with different weights
    - Test re-ranking order
    - _Requirements: 3.2_

- [x] 5. Implement ExplanationGenerator component
  - [x] 5.1 Create ExplanationGenerator in `src/multimodal_librarian/components/kg_retrieval/explanation_generator.py`
    - Implement `generate()` method
    - Implement `_explain_direct_retrieval()` for concept-based explanations
    - Implement `_explain_relationship_retrieval()` for path-based explanations
    - Handle fallback explanation generation
    - _Requirements: 5.1, 5.2, 5.3, 5.5_

  - [ ]* 5.2 Write property test for explanation content correctness
    - **Property 8: Explanation Content Correctness**
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.5**

- [x] 6. Checkpoint - Ensure component tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Implement KGRetrievalService
  - [x] 7.1 Create KGRetrievalService in `src/multimodal_librarian/services/kg_retrieval_service.py`
    - Implement `__init__` with Neo4j and OpenSearch client injection
    - Implement source_chunks caching with TTL
    - Implement `retrieve()` async method orchestrating the two-stage pipeline
    - Implement `_retrieve_direct_chunks()` for Stage 1 direct retrieval
    - Implement `_retrieve_related_chunks()` for Stage 1 relationship traversal
    - Implement `_aggregate_and_deduplicate()` for chunk aggregation
    - Implement `_fallback_to_semantic()` for fallback handling
    - Implement `health_check()` method
    - Implement `get_cache_stats()` method
    - _Requirements: 1.1, 1.3, 1.5, 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.3, 3.4, 6.1, 6.2, 6.3, 6.4, 6.5, 8.1, 8.2, 8.3, 8.5_

  - [ ]* 7.2 Write property test for chunk aggregation
    - **Property 1: Chunk Aggregation from Multiple Concepts**
    - **Validates: Requirements 1.1, 1.2, 1.3, 1.5**

  - [ ]* 7.3 Write property test for relationship traversal
    - **Property 2: Relationship Traversal and Chunk Collection**
    - **Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5**

  - [ ]* 7.4 Write property test for result size invariant
    - **Property 4: Result Size Invariant**
    - **Validates: Requirements 3.4**

  - [ ]* 7.5 Write property test for augmentation threshold
    - **Property 5: Augmentation Threshold Behavior**
    - **Validates: Requirements 3.3**

  - [ ]* 7.6 Write property test for retrieval source metadata
    - **Property 6: Retrieval Source Metadata Completeness**
    - **Validates: Requirements 3.5**

  - [ ]* 7.7 Write property test for fallback triggers
    - **Property 9: Fallback Trigger Conditions**
    - **Validates: Requirements 6.1, 6.2, 6.3, 6.5**

  - [ ]* 7.8 Write property test for cache behavior
    - **Property 11: Cache Hit on Repeated Queries**
    - **Validates: Requirements 8.2**

- [x] 8. Checkpoint - Ensure KGRetrievalService tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Add dependency injection support
  - [x] 9.1 Add KGRetrievalService to DI in `src/multimodal_librarian/api/dependencies/services.py`
    - Add `_kg_retrieval_service` cached instance variable
    - Implement `get_kg_retrieval_service()` async dependency
    - Implement `get_kg_retrieval_service_optional()` for graceful degradation
    - Add cleanup logic to `cleanup_all_dependencies()`
    - _Requirements: 7.1, 7.3, 7.5_

  - [x] 9.2 Update `__init__.py` exports
    - Export new dependencies from `api/dependencies/__init__.py`
    - _Requirements: 7.1_

- [x] 10. Integrate with RAGService
  - [x] 10.1 Modify RAGService to use KGRetrievalService
    - Add optional `kg_retrieval_service` parameter to `__init__`
    - Add `use_kg_retrieval` flag
    - Modify `_search_documents()` to try KG retrieval first
    - Implement `_convert_kg_results()` to convert KGRetrievalResult to DocumentChunks
    - Add KG retrieval metadata to RAGResponse
    - _Requirements: 7.2, 7.4_

  - [ ]* 10.2 Write property test for RAGService graceful degradation
    - **Property 10: RAGService Graceful Degradation**
    - **Validates: Requirements 7.4**

  - [ ]* 10.3 Write unit tests for RAGService integration
    - Test RAGService with KG retrieval available
    - Test RAGService with KG retrieval unavailable
    - Test metadata inclusion in RAGResponse
    - _Requirements: 7.2, 7.4_

- [x] 11. Update RAGService dependency injection
  - [x] 11.1 Update `get_rag_service()` in dependencies
    - Inject KGRetrievalService into RAGService
    - Handle optional KG service gracefully
    - _Requirements: 7.1, 7.2_

- [x] 12. Checkpoint - Ensure integration tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 13. Create component package structure
  - [x] 13.1 Create package files
    - Create `src/multimodal_librarian/components/kg_retrieval/__init__.py`
    - Export QueryDecomposer, ChunkResolver, SemanticReranker, ExplanationGenerator
    - _Requirements: 7.1_

- [x] 14. Add integration test for Chelsea query
  - [x]* 14.1 Write integration test for motivating use case
    - Test query "What did our team observe at Chelsea?"
    - Verify relevant chunk is found via KG retrieval
    - Verify fallback is not used
    - _Requirements: 1.1, 2.1, 5.1_

- [x] 15. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties
- Unit tests validate specific examples and edge cases
- The implementation follows FastAPI DI patterns as specified in the steering file
