# Implementation Plan: KG Concept Extraction Consolidation

## Overview

Consolidate the two parallel KG concept extraction pipelines by wiring the existing `QueryDecomposer` into all callers that currently use the legacy `KnowledgeGraphQueryEngine.process_graph_enhanced_query()`, then removing the dead legacy code. Python is the implementation language.

## Tasks

- [x] 1. Add DI provider for QueryDecomposer
  - [x] 1.1 Create `get_query_decomposer_optional` DI provider in `src/multimodal_librarian/api/dependencies/services.py`
    - Add module-level `_query_decomposer` cache variable
    - Implement provider that creates `QueryDecomposer` with `neo4j_client` and `model_server_client` from existing DI providers
    - Return `None` if dependencies are unavailable
    - Export from `__init__.py`
    - _Requirements: 2.4, 2.5_

- [x] 2. Rewire QueryProcessor to use QueryDecomposer
  - [x] 2.1 Modify `QueryProcessor.__init__` in `src/multimodal_librarian/services/rag_service.py`
    - Change parameter from `kg_query_engine: Optional[KnowledgeGraphQueryEngine]` to `query_decomposer: Optional[QueryDecomposer]`
    - Store `self.query_decomposer`
    - _Requirements: 1.1_
  - [x] 2.2 Rewrite `QueryProcessor.process_query` to use `QueryDecomposer.decompose()`
    - Replace `self.kg_query_engine.process_graph_enhanced_query(query)` with `await self.query_decomposer.decompose(query)`
    - Map `decomposition.concept_matches[:5]` names to `related_concepts` list
    - Construct `kg_metadata` with keys: `related_concepts` (count), `has_kg_matches`, `match_types`, `entities`
    - Preserve the `(enhanced_query, related_concepts, kg_metadata)` return contract
    - Handle `query_decomposer is None` by returning `(query, [], {})`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_
  - [ ]* 2.3 Write property tests for QueryProcessor output mapping
    - **Property 1: Concept matches map to name strings**
    - **Validates: Requirements 1.2**
    - **Property 2: QueryDecomposition maps to kg_metadata keys**
    - **Validates: Requirements 1.3**
  - [ ]* 2.4 Write unit tests for QueryProcessor
    - Test with mock QueryDecomposer returning known matches
    - Test with `query_decomposer=None` graceful degradation
    - Test with QueryDecomposer that raises an exception
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

- [x] 3. Inject QueryDecomposer into RAGService
  - [x] 3.1 Modify `RAGService.__init__` in `src/multimodal_librarian/services/rag_service.py`
    - Add `query_decomposer: Optional[QueryDecomposer] = None` parameter
    - Store `self.query_decomposer`
    - Pass `query_decomposer` to `QueryProcessor` instead of `kg_query_engine`
    - _Requirements: 2.1, 2.2, 2.3_
  - [x] 3.2 Update `get_rag_service` DI provider in `services.py`
    - Add `query_decomposer = Depends(get_query_decomposer_optional)` parameter
    - Pass `query_decomposer` to `RAGService` constructor
    - Also update the existing `_rag_service` hot-update logic for when decomposer becomes available
    - _Requirements: 2.4_
  - [x] 3.3 Update `get_cached_rag_service` and legacy `get_rag_service_legacy` DI providers similarly
    - _Requirements: 2.4_

- [x] 4. Checkpoint - Verify RAG pipeline works with QueryDecomposer
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Rewrite get_knowledge_graph_insights
  - [x] 5.1 Modify `RAGService.get_knowledge_graph_insights` in `rag_service.py`
    - Replace `self.kg_query_engine.process_graph_enhanced_query(query)` with `await self.query_decomposer.decompose(query)`
    - Make the method `async`
    - Use `self.kg_query_engine.multi_hop_reasoning_async` and `get_related_concepts_async` for reasoning
    - Preserve the response structure (reasoning_paths, related_concepts, confidence_scores, explanation)
    - Handle `query_decomposer is None` gracefully
    - _Requirements: 7.1, 7.2, 7.3, 7.4_
  - [ ]* 5.2 Write property test for response structure
    - **Property 6: get_knowledge_graph_insights response structure**
    - **Validates: Requirements 7.3**
  - [ ]* 5.3 Write unit tests for get_knowledge_graph_insights
    - Test with mock QueryDecomposer and mock KG_Query_Engine
    - Test with QueryDecomposer unavailable
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

- [x] 6. Refactor enhance_vector_search
  - [x] 6.1 Modify `enhance_vector_search` in `kg_query_engine.py`
    - Add required `concept_names: List[str]` parameter
    - Remove all internal calls to `_extract_query_concepts_from_neo4j`
    - Return original results when `concept_names` is empty
    - Use provided concepts directly for `get_related_concepts` and re-ranking
    - _Requirements: 5.1, 5.2, 5.3_
  - [ ]* 6.2 Write property test for empty concepts passthrough
    - **Property 4: Empty concept list preserves vector results**
    - **Validates: Requirements 5.3**

- [x] 7. Rewire UnifiedKnowledgeQueryProcessor
  - [x] 7.1 Modify `UnifiedKnowledgeQueryProcessor.__init__` in `query_processor.py`
    - Add `query_decomposer: Optional[QueryDecomposer] = None` parameter
    - _Requirements: 4.2_
  - [x] 7.2 Rewrite `_enhance_with_reasoning` to use QueryDecomposer
    - Replace `self.kg_query_engine.process_graph_enhanced_query()` with `QueryDecomposer.decompose()`
    - Pass extracted concept names to `enhance_vector_search` as the new required parameter
    - Skip enhancement when `query_decomposer` is None
    - _Requirements: 4.1, 4.3, 4.4_
  - [x] 7.3 Update `get_query_processor` DI provider to inject QueryDecomposer
    - _Requirements: 4.2_
  - [ ]* 7.4 Write property test for missing decomposer passthrough
    - **Property 3: Missing QueryDecomposer preserves search results**
    - **Validates: Requirements 4.3**

- [x] 8. Checkpoint - Verify all callers migrated
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Remove legacy methods from KG_Query_Engine
  - [x] 9.1 Delete legacy methods from `kg_query_engine.py`
    - Remove `_extract_query_concepts_from_neo4j`
    - Remove `process_graph_enhanced_query_async`
    - Remove `process_graph_enhanced_query`
    - Remove `_extract_query_concepts`
    - Remove `_simple_concept_extraction`
    - Remove `_generate_query_explanation` (if no longer needed)
    - Evaluate `_calculate_query_confidence_scores` — keep if used by `get_knowledge_graph_insights`, remove otherwise
    - _Requirements: 3.1, 3.2, 3.3, 3.4_
  - [x] 9.2 Update or remove tests referencing deleted methods
    - Update `tests/components/test_knowledge_graph.py` — remove `test_process_graph_enhanced_query`
    - Update `tests/components/test_query_processor.py` — remove mocks of `process_graph_enhanced_query` and `enhance_vector_search` old signature
    - Update `scripts/test-knowledge-graph-integration.py` and `scripts/test-kg-components-only.py`
    - _Requirements: 3.5_
  - [x] 9.3 Remove `kg_query_engine` import and usage from `RAGService.__init__` if no longer needed
    - Keep `kg_query_engine` if still used by `get_knowledge_graph_insights` for reasoning methods
    - Remove the `KnowledgeGraphBuilder` dependency if it was only used to construct `KG_Query_Engine`
    - _Requirements: 3.4_

- [ ] 10. Write confidence scoring property test
  - [ ]* 10.1 Write property test for confidence scoring with KG metadata
    - **Property 5: Confidence scoring incorporates KG metadata**
    - **Validates: Requirements 6.4**

- [x] 11. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties using `hypothesis`
- Unit tests validate specific examples and edge cases using `pytest`
- The `QueryDecomposer` class itself is NOT modified — only its callers are rewired
