# Implementation Plan: Adaptive Proper Noun Coverage

## Overview

Replace the binary all-or-nothing proper noun coverage logic with an adaptive system that scales coverage expectations based on proper noun count and domain context. All changes are confined to four existing files: `relevance_detector.py`, `config.py`, `kg_retrieval_service.py`, and `rag_service.py`. Property-based tests use Hypothesis.

## Tasks

- [x] 1. Add configuration parameters and extend the dataclass
  - [x] 1.1 Add adaptive threshold config fields to Settings
    - Add `adaptive_threshold_floor` (default 0.70), `adaptive_medical_threshold` (default 0.95), `adaptive_legal_threshold` (default 0.90), `adaptive_small_query_noun_limit` (default 2) as `Field` entries in `src/multimodal_librarian/config/config.py`
    - _Requirements: 8.1, 2.4_
  - [x] 1.2 Add new fields to `QueryTermCoverageResult` dataclass
    - Add `adaptive_threshold: float = 1.0` and `detected_domain: Optional[str] = None` to the dataclass in `src/multimodal_librarian/components/kg_retrieval/relevance_detector.py`
    - _Requirements: 1.4, 8.3_

- [-] 2. Implement pure functions and adaptive analysis logic
  - [x] 2.1 Implement `compute_adaptive_threshold()` pure function
    - Add the function to `src/multimodal_librarian/components/kg_retrieval/relevance_detector.py`
    - For `proper_noun_count <= small_query_noun_limit`: return 1.0
    - For `proper_noun_count > small_query_noun_limit`: `max(base_threshold_floor, 1.0 - (proper_noun_count - small_query_noun_limit) * 0.05)`
    - Apply domain elevation: medical → `max(threshold, medical_threshold)`, legal → `max(threshold, legal_threshold)`
    - Clamp output to `[0.0, 1.0]`
    - _Requirements: 1.1, 1.2, 1.5, 2.1, 2.2, 2.3, 2.5_

  - [ ]* 2.2 Write property test: Adaptive threshold scaling (Property 1)
    - **Property 1: Adaptive threshold scaling**
    - For any `n >= 0` with no domain: returns 1.0 when `n <= small_query_noun_limit`, monotonically non-increasing for `n > small_query_noun_limit`, never below `base_threshold_floor`
    - Test file: `tests/components/test_adaptive_proper_noun_coverage.py`
    - **Validates: Requirements 1.1, 1.2**

  - [ ]* 2.3 Write property test: Domain elevation (Property 2)
    - **Property 2: Domain elevation**
    - For any `n >= 1`: medical threshold always `>= medical_threshold`, legal always `>= legal_threshold`, non-elevated domains unchanged vs standard threshold
    - Test file: `tests/components/test_adaptive_proper_noun_coverage.py`
    - **Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5**

  - [x] 2.4 Implement `compute_chunk_noun_score()` pure function
    - Add the function to `src/multimodal_librarian/components/kg_retrieval/relevance_detector.py`
    - Compute fraction of `key_nouns` present (case-insensitive substring match) in `chunk_content`
    - Return 1.0 when `key_nouns` is empty
    - _Requirements: 3.1, 7.1_

  - [ ]* 2.5 Write property test: Chunk noun score computation (Property 5)
    - **Property 5: Chunk noun score computation**
    - For any chunk content and key nouns list: score equals count of found nouns / total nouns; 1.0 when key nouns is empty
    - Test file: `tests/components/test_adaptive_proper_noun_coverage.py`
    - **Validates: Requirements 3.1, 7.1**

  - [x] 2.6 Modify `analyze_query_term_coverage()` with adaptive logic
    - Add parameters: `domain`, `base_threshold_floor`, `medical_threshold`, `legal_threshold`, `small_query_noun_limit`
    - Call `compute_adaptive_threshold()` internally with proper noun count and domain
    - Set `has_proper_noun_gap` based on `coverage_ratio < adaptive_threshold` instead of `len(uncovered) > 0`
    - Set `has_cooccurrence_gap` based on no chunk achieving `compute_chunk_noun_score >= adaptive_threshold` instead of requiring ALL key nouns
    - Store `adaptive_threshold` and `detected_domain` on the result
    - Add INFO-level logging of threshold decisions
    - _Requirements: 1.3, 1.4, 7.2, 7.3, 8.2, 8.3_

  - [ ]* 2.7 Write property test: Gap declaration correctness (Property 3)
    - **Property 3: Gap declaration correctness**
    - For any `QueryTermCoverageResult`: `has_proper_noun_gap` is True iff `coverage_ratio < adaptive_threshold`
    - Test file: `tests/components/test_adaptive_proper_noun_coverage.py`
    - **Validates: Requirements 1.3**

  - [ ]* 2.8 Write property test: Threshold and domain exposed on result (Property 4)
    - **Property 4: Threshold and domain exposed on result**
    - For any call to `analyze_query_term_coverage`: returned `adaptive_threshold` equals `compute_adaptive_threshold(proper_noun_count, domain)` and `detected_domain` equals the domain passed in
    - Test file: `tests/components/test_adaptive_proper_noun_coverage.py`
    - **Validates: Requirements 1.4, 8.3**

  - [ ]* 2.9 Write property test: Co-occurrence gap declaration (Property 10)
    - **Property 10: Co-occurrence gap declaration**
    - For any set of chunks, key nouns (length >= 2), and adaptive threshold: `has_cooccurrence_gap` is True iff no chunk achieves `compute_chunk_noun_score >= adaptive_threshold`
    - Test file: `tests/components/test_adaptive_proper_noun_coverage.py`
    - **Validates: Requirements 7.2, 7.3**

- [x] 3. Checkpoint - Verify pure functions and analysis logic
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Implement three-tier pre-reranking filter
  - [x] 4.1 Modify `filter_chunks_by_proper_nouns()` with adaptive threshold
    - Add `adaptive_threshold: float = 1.0` parameter to the method in `src/multimodal_librarian/components/kg_retrieval/relevance_detector.py`
    - Replace two-tier filter (ALL → ANY) with three-tier filter (ALL → adaptive threshold → ANY)
    - Tier 2: chunks where `(matched_key_terms / total_key_terms) >= adaptive_threshold`
    - Update logging to include `match_mode` values: `all`, `threshold`, `any`
    - _Requirements: 5.1, 5.2, 5.3_

  - [ ]* 4.2 Write property test: Three-tier pre-reranking filter (Property 8)
    - **Property 8: Three-tier pre-reranking filter**
    - For any chunks, key terms, and adaptive threshold: if any chunks contain ALL key terms, return those; else if any meet threshold fraction, return those; else return chunks with ANY key term
    - Test file: `tests/components/test_adaptive_proper_noun_coverage.py`
    - **Validates: Requirements 5.1, 5.2, 5.3**

  - [x] 4.3 Update `kg_retrieval_service.py` to pass adaptive threshold
    - Modify the call to `filter_chunks_by_proper_nouns()` in `src/multimodal_librarian/services/kg_retrieval_service.py` to pass the adaptive threshold from the coverage result
    - _Requirements: 5.2_

- [x] 5. Implement graduated chunk scoring and web search trigger in post-processing
  - [x] 5.1 Modify `_post_processing_phase()` co-occurrence drop section
    - In `src/multimodal_librarian/services/rag_service.py`, replace the `all(kn in content)` co-occurrence drop with adaptive threshold filtering using `compute_chunk_noun_score()`
    - Retain chunks where `chunk_noun_score >= adaptive_threshold`
    - When no chunks meet threshold, fall back to retaining top chunks by `chunk_noun_score`
    - Store `chunk_noun_score` in `chunk.metadata['chunk_noun_score']`
    - _Requirements: 3.2, 3.4, 7.2, 7.3_

  - [x] 5.2 Modify `_post_processing_phase()` per-chunk key-noun filter section
    - Replace the `all(kn in content)` per-chunk filter with adaptive threshold filtering using `compute_chunk_noun_score()`
    - Retain chunks where `chunk_noun_score >= adaptive_threshold`
    - When no chunks meet threshold, fall back to retaining top chunks by `chunk_noun_score`
    - _Requirements: 3.2, 3.4_

  - [x] 5.3 Implement graduated sorting in `_post_processing_phase()`
    - Sort retained chunks by `(final_score DESC, chunk_noun_score DESC)` as primary and secondary sort keys
    - _Requirements: 3.3, 4.1, 4.2, 4.3_

  - [ ]* 5.4 Write property test: Chunk retention by adaptive threshold (Property 6)
    - **Property 6: Chunk retention by adaptive threshold**
    - For any chunks, key nouns, and adaptive threshold: retained set is exactly chunks with `compute_chunk_noun_score >= adaptive_threshold`; fallback retains top chunks when none meet threshold
    - Test file: `tests/components/test_adaptive_proper_noun_coverage.py`
    - **Validates: Requirements 3.2, 3.4**

  - [ ]* 5.5 Write property test: Relevance ranking preservation (Property 7)
    - **Property 7: Relevance ranking preservation**
    - For any retained chunks: output ordering satisfies `final_score` descending as primary key, `chunk_noun_score` descending as secondary key
    - Test file: `tests/components/test_adaptive_proper_noun_coverage.py`
    - **Validates: Requirements 3.3, 4.1, 4.2, 4.3**

  - [x] 5.6 Implement web search trigger based on surviving chunk count
    - In `_post_processing_phase()`, count chunks with `chunk_noun_score >= adaptive_threshold`; if count < `web_search_result_count_threshold`, trigger web search for the proper-noun-coverage signal
    - Preserve existing web search triggers (score-based irrelevance, thin results) as independent signals
    - Handle SearXNG unavailability gracefully (catch exception, log warning, proceed with local chunks)
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [ ]* 5.7 Write property test: Web search trigger (Property 9)
    - **Property 9: Web search trigger based on surviving chunk count**
    - For any chunks, noun scores, adaptive threshold, and `web_search_result_count_threshold`: web search fires iff count of chunks with `chunk_noun_score >= adaptive_threshold` < `web_search_result_count_threshold`
    - Test file: `tests/components/test_adaptive_proper_noun_coverage.py`
    - **Validates: Requirements 6.1, 6.2**

- [x] 6. Wire adaptive threshold through the call chain
  - [x] 6.1 Update `RelevanceDetector.evaluate()` to pass config parameters
    - Pass `domain`, `base_threshold_floor`, `medical_threshold`, `legal_threshold`, `small_query_noun_limit` from config through to `analyze_query_term_coverage()`
    - Extract domain from `query_decomposition` context keywords (look for `"domain:medical"`, `"domain:legal"`, etc.)
    - _Requirements: 2.1, 2.2, 2.3, 2.5, 8.1_

  - [x] 6.2 Update `_post_processing_phase()` logging
    - Add INFO-level logging of `proper_noun_count`, `adaptive_threshold`, `coverage_ratio`, `detected_domain`, `has_proper_noun_gap`, `has_cooccurrence_gap` to the existing relevance detection log statement
    - Log `chunk_noun_score` per chunk, surviving count, and web search trigger decision
    - _Requirements: 8.2_

  - [ ]* 6.3 Write unit tests for integration and edge cases
    - Test 0 proper nouns, 1 proper noun, boundary at `small_query_noun_limit`
    - Test `None` domain, unknown domain string, medical with 1 noun (should still be 1.0)
    - Test all-chunks-below-threshold fallback, all three filter tiers empty → `None`
    - Test end-to-end flow through `_post_processing_phase` with mocked relevance detector verifying sort order and web search trigger
    - Test file: `tests/components/test_adaptive_proper_noun_coverage.py`
    - _Requirements: 1.5, 2.5, 3.4, 5.3_

- [x] 7. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document using Hypothesis
- Unit tests validate specific examples and edge cases
- All changes are confined to 4 existing files plus 1 new test file
