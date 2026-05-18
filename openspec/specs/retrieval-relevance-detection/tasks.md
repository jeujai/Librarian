# Implementation Plan: Retrieval Relevance Detection

## Overview

Implement a `RelevanceDetector` component that identifies "no relevant results" scenarios using score distribution analysis and concept specificity signals. The component integrates into the existing RAG pipeline at two points: `_post_processing_phase` (web search trigger) and `_calculate_confidence_score` (confidence adjustment). All analysis is pure in-memory computation on already-retrieved data.

## Tasks

- [x] 1. Add configuration settings and data models
  - [x] 1.1 Add relevance detection threshold fields to the `Settings` class in `src/multimodal_librarian/config/config.py`
    - Add `relevance_spread_threshold` (default 0.05), `relevance_variance_threshold` (default 0.001), and `relevance_specificity_threshold` (default 0.3) as `float` fields with `Field` descriptors
    - _Requirements: 6.1, 6.2, 6.3_

  - [x] 1.2 Create `src/multimodal_librarian/components/kg_retrieval/relevance_detector.py` with data models
    - Define `ScoreDistributionResult` dataclass with `variance`, `spread`, `is_semantic_floor`, `chunk_count`, `is_indeterminate` fields
    - Define `ConceptSpecificityResult` dataclass with `per_concept_scores`, `average_specificity`, `is_low_specificity`, `high_specificity_count`, `low_specificity_count` fields
    - Define `RelevanceVerdict` dataclass with `is_relevant`, `confidence_adjustment_factor`, `score_distribution`, `concept_specificity`, `reasoning` fields
    - _Requirements: 1.5, 2.6, 3.4_

- [x] 2. Implement score distribution analysis
  - [x] 2.1 Implement `analyze_score_distribution` function in `relevance_detector.py`
    - Accept a list of `RetrievedChunk` objects, `spread_threshold`, and `variance_threshold`
    - Return indeterminate result when fewer than 3 chunks (is_semantic_floor=False, is_indeterminate=True)
    - Compute spread (max - min) and population variance of `final_score` values
    - Set `is_semantic_floor = True` when spread < spread_threshold OR variance < variance_threshold
    - Return `ScoreDistributionResult` with computed values
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

  - [ ]* 2.2 Write property test for score distribution analysis (Property 1)
    - **Property 1: Semantic floor classification correctness**
    - Use Hypothesis to generate random score lists (≥3 items, values in [0,1]) and random thresholds
    - Verify `is_semantic_floor` matches spread/variance conditions exactly
    - Verify computed `variance`, `spread`, and `chunk_count` are correct
    - **Validates: Requirements 1.1, 1.2, 1.3, 1.5**

  - [ ]* 2.3 Write unit tests for score distribution edge cases
    - Test with 0, 1, 2 chunks returns indeterminate
    - Test with identical scores returns semantic floor
    - Test with well-separated scores returns no semantic floor
    - _Requirements: 1.4_

- [x] 3. Implement concept specificity analysis
  - [x] 3.1 Implement `analyze_concept_specificity` function in `relevance_detector.py`
    - Define `GENERIC_WORDS` frozenset with ~50-100 common English words
    - Accept a list of concept match dicts and `specificity_threshold`
    - Score each concept starting at 0.5: +0.3 for proper noun, +0.2 for multi-word/hyphenated, +0.1 for length ≥ 5, -0.3 for short generic words, -0.1 for weak word_coverage; clamp to [0.0, 1.0]
    - Return `is_low_specificity = True` when ALL per-concept scores are below threshold, or when concept list is empty
    - Use `.get()` with defaults for all dict fields to handle malformed input
    - Return `ConceptSpecificityResult` with per-concept scores, average, counts
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [ ]* 3.2 Write property test for concept specificity analysis (Property 2)
    - **Property 2: Concept specificity scoring and classification**
    - Use Hypothesis to generate random concept match dicts with varied names, proper noun flags, word coverage
    - Verify all scores are in [0.0, 1.0]
    - Verify proper nouns and multi-word names score above 0.7
    - Verify `is_low_specificity` is True iff ALL scores are below threshold
    - Verify `high_specificity_count + low_specificity_count == total concepts`
    - **Validates: Requirements 2.1, 2.3, 2.4, 2.6**

  - [ ]* 3.3 Write unit tests for concept specificity edge cases
    - Test known generic words ("world", "go", "day") score below 0.3
    - Test empty concept_matches returns is_low_specificity=True
    - Test proper nouns ("Chelsea", "LangChain") score above 0.7
    - _Requirements: 2.2, 2.5_

- [x] 4. Implement RelevanceDetector with verdict logic
  - [x] 4.1 Implement `RelevanceDetector` class in `relevance_detector.py`
    - Constructor accepts `spread_threshold`, `variance_threshold`, `specificity_threshold` with defaults from design
    - Log active threshold values at initialization
    - `evaluate` method accepts `List[RetrievedChunk]` and `QueryDecomposition`, returns `RelevanceVerdict`
    - Verdict logic: both signals fire → is_relevant=False, factor=0.3; one fires → is_relevant=True, factor=0.8; neither → is_relevant=True, factor=1.0
    - Include human-readable `reasoning` string explaining the verdict
    - Defensively clamp final_score values to [0, 1]
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 4.8_

  - [ ]* 4.2 Write property test for verdict logic (Property 3)
    - **Property 3: Verdict logic correctness**
    - Use Hypothesis to generate random `ScoreDistributionResult` and `ConceptSpecificityResult`
    - Verify three-case verdict logic: both fire → irrelevant, one fires → partial penalty in [0.7, 0.9], neither → factor=1.0
    - Verify verdict always contains non-None score_distribution, concept_specificity, and non-empty reasoning
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.4**

- [x] 5. Checkpoint
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Export and DI wiring
  - [x] 6.1 Export `RelevanceDetector` from `src/multimodal_librarian/components/kg_retrieval/__init__.py`
    - Add `RelevanceDetector` to imports and `__all__` list
    - _Requirements: 3.5_

  - [x] 6.2 Add `get_relevance_detector` dependency provider in `src/multimodal_librarian/api/dependencies/services.py`
    - Follow existing DI pattern: lazy initialization, singleton caching, read thresholds from `get_settings()`
    - Add `get_relevance_detector_optional` variant that returns `None` on failure
    - _Requirements: 6.1, 6.2, 6.3_

- [x] 7. Integrate with RAG pipeline
  - [x] 7.1 Add `relevance_detector` parameter to `RAGService.__init__` in `src/multimodal_librarian/services/rag_service.py`
    - Add `relevance_detector: Optional["RelevanceDetector"] = None` parameter
    - Store as `self.relevance_detector` and initialize `self._last_relevance_verdict = None`
    - _Requirements: 4.1_

  - [x] 7.2 Extend `_post_processing_phase` to accept optional `query_decomposition` and invoke `RelevanceDetector`
    - Add `query_decomposition: Optional["QueryDecomposition"] = None` parameter
    - Call `self.relevance_detector.evaluate()` before the web search decision, wrapped in try/except
    - Cache verdict in `self._last_relevance_verdict`; on exception, set to `None` and default `relevance_detected_irrelevant = False`
    - Add `relevance_detected_irrelevant` as a third trigger condition in the web search `if` block
    - Extend the librarian chunk drop condition: `if web_chunks and (librarian_results_irrelevant or relevance_detected_irrelevant)`
    - _Requirements: 4.1, 4.2, 4.3, 4.7_

  - [x] 7.3 Modify `_calculate_confidence_score` to apply relevance verdict adjustment
    - After existing confidence computation, check `self._last_relevance_verdict`
    - If verdict is not None and `is_relevant=False`: `confidence = min(confidence, 0.3)`
    - If verdict is not None and `is_relevant=True`: `confidence *= verdict.confidence_adjustment_factor`
    - Ensure final confidence stays in [0.1, 1.0] range
    - _Requirements: 4.4, 4.5_

  - [ ]* 7.4 Write property test for confidence cap (Property 4)
    - **Property 4: Confidence cap when irrelevant**
    - Use Hypothesis to generate random base confidence in [0.1, 1.0] and apply irrelevant verdict
    - Verify result is always ≤ 0.3
    - **Validates: Requirements 4.5**

  - [x] 7.5 Pass `query_decomposition` through the pipeline
    - In `_search_documents`, extract `query_decomposition` from `kg_metadata.get('_decomposition')` and pass to `_post_processing_phase`
    - _Requirements: 4.1_

  - [x] 7.6 Add `relevance_detection` metadata to `RAGResponse`
    - In `generate_response`, include `self._last_relevance_verdict` diagnostic data in `response_metadata` under key `"relevance_detection"`
    - Reset `self._last_relevance_verdict = None` at the start of each `generate_response` call
    - _Requirements: 4.6_

  - [x] 7.7 Wire `RelevanceDetector` into `get_rag_service` DI provider in `services.py`
    - Resolve `get_relevance_detector_optional()` and pass to `RAGService` constructor
    - _Requirements: 4.1, 6.1_

- [x] 8. Checkpoint
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. User-facing confidence display
  - [x] 9.1 Update chat router display formatting in `src/multimodal_librarian/api/routers/chat.py`
    - In `handle_non_streaming_rag_response`, check for `relevance_detection` metadata in the RAG response
    - When `is_relevant=False`, add `"confidence_label": "low confidence"` to the response metadata
    - When adjusted confidence < 0.3, add `"relevance_disclaimer": "Results may not be relevant to your query"` to the metadata
    - When `is_relevant=True` or metadata absent, use existing format unchanged
    - _Requirements: 5.1, 5.2, 5.3_

- [ ] 10. Integration tests
  - [ ]* 10.1 Write integration tests in `tests/integration/test_relevance_detection_rag.py`
    - Test RAGService calls RelevanceDetector and caches verdict
    - Test web search is triggered when verdict is irrelevant
    - Test RAGResponse metadata contains "relevance_detection" key
    - Test RelevanceDetector exception → original confidence preserved, no web search trigger from relevance detection
    - Test confidence adjustment factor is applied correctly for partial penalty case
    - Use dependency overrides and mocks following the DI testing pattern
    - _Requirements: 4.1, 4.2, 4.4, 4.6, 4.7_

- [x] 11. Final checkpoint
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 12. Implement proper-noun chunk filter on RelevanceDetector
  - [x] 12.1 Add `filter_chunks_by_proper_nouns` method to `RelevanceDetector` in `src/multimodal_librarian/components/kg_retrieval/relevance_detector.py`
    - Accept `chunks: List[RetrievedChunk]` and `query: str` parameters
    - Use `self.spacy_nlp` to extract named entities from the query
    - Return `None` when: spaCy model is unavailable, query has no proper nouns, or filtered set is empty
    - Filter chunks by case-insensitive substring match of proper nouns against `chunk.content`
    - Log before/after chunk counts, proper nouns used, and retained chunk IDs
    - _Requirements: 7.1, 7.3, 7.4, 7.6, 7.7, 7.9_

  - [ ]* 12.2 Write property test for proper-noun chunk filter correctness (Property 5)
    - **Property 5: Proper-noun chunk filter correctness**
    - Use Hypothesis to generate random chunk contents and proper noun lists, mock spaCy NER
    - Verify returned chunks are exactly those containing at least one proper noun (case-insensitive)
    - Verify returned list is a subset of input list
    - **Validates: Requirements 7.1**

  - [ ]* 12.3 Write property test for proper-noun filter no-op conditions (Property 6)
    - **Property 6: Proper-noun filter no-op conditions**
    - Use Hypothesis to generate chunks and queries with no proper nouns or no matching chunks
    - Verify filter returns `None` in all no-op cases
    - **Validates: Requirements 7.3, 7.4**

- [x] 13. Integrate proper-noun filter into KGRetrievalService
  - [x] 13.1 Add optional `relevance_detector` parameter to `KGRetrievalService.__init__` in `src/multimodal_librarian/services/kg_retrieval_service.py`
    - Add `relevance_detector: Optional["RelevanceDetector"] = None` parameter
    - Store as `self._relevance_detector`
    - _Requirements: 7.2, 7.5_

  - [x] 13.2 Call `filter_chunks_by_proper_nouns` in `KGRetrievalService.retrieve()` between `_aggregate_and_deduplicate` and `SemanticReranker.rerank`
    - If `self._relevance_detector` is not None, call `filter_chunks_by_proper_nouns(stage1_chunks, query)`
    - Use filtered result if non-None, otherwise fall back to original candidates
    - Wrap in try/except with warning log and fallback to unfiltered candidates on error
    - _Requirements: 7.2, 7.3, 7.5, 7.8_

  - [x] 13.3 Update DI wiring in `src/multimodal_librarian/api/dependencies/services.py` to pass `RelevanceDetector` to `KGRetrievalService`
    - Resolve `get_relevance_detector_optional()` in `get_kg_retrieval_service` provider
    - Pass the resolved instance to `KGRetrievalService` constructor as `relevance_detector`
    - _Requirements: 7.2, 7.5_

- [x] 14. Update selective drop logic for proper-noun retention
  - [x] 14.1 Modify the librarian chunk drop logic in `RAGService._post_processing_phase` in `src/multimodal_librarian/services/rag_service.py`
    - When `relevance_detected_irrelevant` is True and web chunks are returned, retain librarian chunks that contain proper nouns from the query
    - Use the verdict's proper noun list (from `query_term_coverage.proper_nouns`) for case-insensitive substring matching
    - If no proper nouns in verdict or no matching chunks, drop all librarian chunks (existing behavior)
    - _Requirements: 7.10_

  - [ ]* 14.2 Write property test for selective drop retains proper-noun chunks (Property 7)
    - **Property 7: Selective drop retains proper-noun chunks**
    - Use Hypothesis to generate random librarian chunk dicts and proper noun lists
    - Verify retained chunks are exactly those containing at least one proper noun (case-insensitive)
    - **Validates: Requirements 7.10**

- [x] 15. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 16. Integration tests for proper-noun filter
  - [ ]* 16.1 Write integration tests in `tests/integration/test_proper_noun_filter_kg.py`
    - Test KGRetrievalService passes filtered set to reranker when filter returns non-None
    - Test KGRetrievalService falls back to unfiltered candidates when filter returns None
    - Test filter is called after _aggregate_and_deduplicate and before rerank (mock call order)
    - Test filter exception → KGRetrievalService falls back to unfiltered candidates
    - Test RAGService selective drop retains proper-noun chunks alongside web results
    - Use dependency overrides and mocks following the DI testing pattern
    - _Requirements: 7.2, 7.3, 7.5, 7.8, 7.10_

- [x] 17. Final checkpoint
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- The RelevanceDetector is a pure in-memory analyzer with no I/O, keeping latency under 5ms (Requirement 4.8)
- The proper-noun chunk filter adds no more than 2ms latency using in-memory string matching (Requirement 7.9)
- Property tests use Hypothesis with min 200 examples per property
- The DI pattern follows the existing project conventions in `services.py`
- The same `RelevanceDetector` instance is shared between `RAGService` and `KGRetrievalService` (stateless analyzer)
