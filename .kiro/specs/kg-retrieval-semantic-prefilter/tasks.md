# Implementation Plan: KG Retrieval Semantic Pre-filter

## Overview

Replace the KG-score-based pre-filter in `SemanticReranker` with a semantic-similarity-based pre-filter that uses already-fetched chunk embeddings, and adjust default reranker weights to favor semantic similarity. All changes are scoped to `semantic_reranker.py` and its test file.

## Tasks

- [x] 1. Update SemanticReranker constants and defaults
  - [x] 1.1 Update default weights and pre-filter limit in `semantic_reranker.py`
    - Change `DEFAULT_KG_WEIGHT` from 0.6 to 0.3
    - Change `DEFAULT_SEMANTIC_WEIGHT` from 0.4 to 0.7
    - Change `MAX_CHUNKS_FOR_RERANKING` from 30 to 50
    - _Requirements: 1.4, 2.1_

- [x] 2. Implement vectorized batch cosine similarity
  - [x] 2.1 Add `_batch_cosine_similarities` method to `SemanticReranker`
    - Accept query_embedding (shape D,) and chunk_embeddings matrix (shape N,D)
    - Use vectorized numpy dot product and norm operations
    - Handle zero-norm vectors by returning 0.0 for those entries
    - Return shape (N,) array of cosine similarities
    - _Requirements: 5.2_
  - [ ]* 2.2 Write property test: batch cosine similarity matches individual computation
    - **Property 5: Batch cosine similarity matches individual computation**
    - **Validates: Requirements 5.2**

- [x] 3. Replace KG-score pre-filter with semantic pre-filter
  - [x] 3.1 Rewrite `_prefilter_chunks` method
    - Change signature to accept `query_embedding: np.ndarray` parameter
    - Separate chunks into those with and without embeddings
    - Build numpy matrix from chunk embeddings and call `_batch_cosine_similarities`
    - Select top MAX_CHUNKS_FOR_RERANKING chunks by cosine similarity
    - Chunks without embeddings get default score 0.0, included only if pool of chunks with embeddings is smaller than MAX_CHUNKS_FOR_RERANKING
    - _Requirements: 1.1, 1.2, 1.3, 5.1_
  - [ ]* 3.2 Write property test: pre-filter selects top-N by semantic similarity
    - **Property 1: Semantic pre-filter selects top-N by cosine similarity**
    - **Validates: Requirements 1.1, 1.2, 1.3**

- [x] 4. Restructure `rerank` method for embedding reuse
  - [x] 4.1 Update `rerank` to generate query embedding before pre-filtering
    - Move query embedding generation (via `_get_query_embedding_cached`) to before the `_prefilter_chunks` call
    - Pass query_embedding to `_prefilter_chunks`
    - Pass the same query_embedding to `_calculate_semantic_scores` (add parameter)
    - Update `_calculate_semantic_scores` signature to accept optional `query_embedding` parameter to avoid regenerating it
    - Preserve all existing fallback behavior (no model client → KG scores only, empty chunks → empty result)
    - _Requirements: 3.1, 3.2, 4.1, 4.2, 4.4_
  - [ ]* 4.2 Write property test: query embedding generated at most once per rerank call
    - **Property 3: Query embedding is generated at most once per rerank call**
    - **Validates: Requirements 3.1, 3.2**
  - [ ]* 4.3 Write property test: fallback preserves KG score ordering
    - **Property 4: Fallback preserves KG score ordering**
    - **Validates: Requirements 4.2**

- [x] 5. Checkpoint - Verify all changes
  - Ensure all tests pass, ask the user if questions arise.
  - Run `pytest tests/components/test_semantic_reranker_prefilter.py -v`

- [x] 6. Write remaining tests
  - [x]* 6.1 Write property test: custom weights produce correct final scores
    - **Property 2: Custom weights are respected**
    - **Validates: Requirements 2.1, 2.2, 2.3**
  - [x]* 6.2 Write unit tests for edge cases and configuration
    - Test default weight values are 0.3 and 0.7
    - Test MAX_CHUNKS_FOR_RERANKING is 50
    - Test pre-filter with exactly MAX_CHUNKS_FOR_RERANKING chunks passes all through
    - Test pre-filter with all chunks missing embeddings
    - Test empty chunk list returns empty result
    - Test rerank with empty query falls back to KG scores
    - _Requirements: 1.3, 1.4, 2.1, 4.2_

- [x] 7. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.
  - Run `pytest tests/components/test_semantic_reranker_prefilter.py -v`

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- All changes are scoped to `src/multimodal_librarian/components/kg_retrieval/semantic_reranker.py`
- Tests go in `tests/components/test_semantic_reranker_prefilter.py`
- No changes needed to `KGRetrievalService`, `ChunkResolver`, or data models
- Property tests use `hypothesis` library with minimum 100 iterations
- The existing `_cosine_similarity` method is kept for use in `_calculate_semantic_scores`; the new `_batch_cosine_similarities` is used only in the pre-filter
