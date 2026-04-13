# Implementation Plan: Cross-Encoder Reranking

## Overview

Replace the bi-encoder cosine similarity score in the SemanticReranker with a cross-encoder relevance score. The implementation adds a new `CrossEncoderModel` on the model server, a `/rerank` endpoint, a `rerank()` method on the `ModelServerClient`, and integrates the cross-encoder path into the `SemanticReranker` with bi-encoder fallback.

## Tasks

- [x] 1. Add CrossEncoderModel and server-side configuration
  - [x] 1.1 Create `src/model_server/models/cross_encoder.py` with `CrossEncoderModel` class
    - Implement `__init__`, `load`, `predict`, `get_status`, `is_loaded` following the `EmbeddingModel` pattern
    - `predict()` constructs `[(query, doc)]` pairs, calls `CrossEncoder.predict()`, applies `scipy.special.expit` (sigmoid) to raw logits
    - Add module-level `_cross_encoder_model`, `get_cross_encoder_model()`, and `initialize_cross_encoder_model()` functions
    - _Requirements: 1.1, 2.5_

  - [x] 1.2 Add cross-encoder config fields to `src/model_server/config.py`
    - Add `cross_encoder_model` (default `cross-encoder/ms-marco-MiniLM-L-6-v2`, env `CROSS_ENCODER_MODEL`)
    - Add `cross_encoder_device` (default `cpu`, env `CROSS_ENCODER_DEVICE`)
    - _Requirements: 1.2_

  - [x] 1.3 Load cross-encoder model during startup in `src/model_server/main.py`
    - Import and call `initialize_cross_encoder_model()` in the `lifespan` function after NLP model loading
    - Log success/failure; on failure log error and continue (do not block startup)
    - _Requirements: 1.1, 1.3_

  - [ ]* 1.4 Write property test for CrossEncoderModel.predict output invariants (Property 1)
    - **Property 1: Rerank endpoint output invariants**
    - Use Hypothesis to generate random query strings (min_length=1) and random document lists (0–50 items)
    - Assert `len(scores) == len(documents)` and all scores in [0.0, 1.0]
    - **Validates: Requirements 2.2, 2.3, 2.5**

- [x] 2. Create the `/rerank` API endpoint
  - [x] 2.1 Create `src/model_server/api/rerank.py` with `RerankRequest`, `RerankResponse`, and `POST /rerank` handler
    - Follow the `embeddings.py` router pattern
    - Validate `query` is non-empty via `min_length=1` (422 on empty)
    - Return 503 if cross-encoder model not loaded
    - Return empty scores list for empty documents (200 OK)
    - Include `model`, `count`, `processing_time_ms` in response
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [x] 2.2 Register the rerank router in `src/model_server/main.py`
    - Import and include the rerank router alongside embeddings and nlp routers
    - Add `/rerank` to the root endpoint's `endpoints` dict
    - _Requirements: 2.1_

  - [x] 2.3 Update health endpoints in `src/model_server/api/health.py`
    - Include cross-encoder model status in `/health` response under `models.cross_encoder`
    - Include cross-encoder loaded status in `/health/ready` response but do NOT require it for readiness
    - _Requirements: 1.5_

  - [ ]* 2.4 Write unit tests for the rerank endpoint
    - Test valid request returns correct score count and format
    - Test empty query returns 422
    - Test model not loaded returns 503
    - Test empty documents returns empty scores (200)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

- [x] 3. Checkpoint
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Add `rerank()` method to ModelServerClient
  - [x] 4.1 Add `rerank()` async method to `ModelServerClient` in `src/multimodal_librarian/clients/model_server_client.py`
    - Accept `query: str` and `documents: List[str]`, return `List[float]`
    - Use existing `_request()` method: `POST /rerank` with `{"query": query, "documents": documents}`
    - Extract and return `scores` from response
    - Raises `ModelServerError`/`ModelServerUnavailable` on failure (inherited from `_request`)
    - _Requirements: 3.1, 3.2, 3.3_

  - [ ]* 4.2 Write unit tests for ModelServerClient.rerank()
    - Test success path returns scores list
    - Test connection error raises ModelServerUnavailable
    - Test timeout raises ModelServerUnavailable
    - Test 503 response raises ModelServerUnavailable
    - _Requirements: 3.1, 3.2, 3.3_

- [x] 5. Integrate cross-encoder into SemanticReranker
  - [x] 5.1 Modify `SemanticReranker.rerank()` in `src/multimodal_librarian/components/kg_retrieval/semantic_reranker.py`
    - After pre-filtering, attempt cross-encoder scoring via `model_client.rerank(query, [c.content for c in chunks])`
    - On success: assign returned scores directly as `chunk.semantic_score`, skip bi-encoder path
    - On failure (any exception): log warning with reason, fall through to existing bi-encoder cosine similarity path
    - Validate score count matches chunk count; on mismatch log warning and fall back to bi-encoder
    - No circuit breaker — each invocation independently attempts cross-encoder
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 5.1, 5.2, 5.3, 5.4_

  - [ ]* 5.2 Write property test for cross-encoder score assignment (Property 2)
    - **Property 2: Cross-encoder score assignment**
    - Mock `model_client.rerank()` to return known scores for random chunks and query
    - Assert each chunk's `semantic_score` equals the corresponding returned score
    - **Validates: Requirements 4.1, 4.3**

  - [ ]* 5.3 Write property test for final score formula correctness (Property 3)
    - **Property 3: Final score formula correctness**
    - Use Hypothesis to generate random floats in [0, 1] for kg_score and semantic_score
    - Assert `_calculate_final_score(kg, semantic) == kg × KG_WEIGHT + semantic × SEMANTIC_WEIGHT`
    - **Validates: Requirements 4.4, 5.3**

  - [ ]* 5.4 Write property test for graceful fallback (Property 4)
    - **Property 4: Graceful fallback to bi-encoder on cross-encoder failure**
    - Mock `model_client.rerank()` to raise `ModelServerUnavailable`
    - Provide chunks with stored embeddings and a random query
    - Assert reranker returns non-empty ranked list with semantic_score values computed via bi-encoder cosine similarity
    - **Validates: Requirements 5.1, 5.3**

- [x] 6. Checkpoint
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Dockerfile and docker-compose updates
  - [x] 7.1 Update `Dockerfile.model-server` to pre-download the cross-encoder model at build time
    - Add `RUN python -c "from sentence_transformers import CrossEncoder; CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')"` after existing model downloads
    - _Requirements: 1.4, 6.1_

  - [x] 7.2 Update `docker-compose.yml` to pass `CROSS_ENCODER_MODEL` env var to model-server service
    - Add `- CROSS_ENCODER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2` to model-server environment
    - _Requirements: 6.2, 6.3_

- [x] 8. Final checkpoint
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- The cross-encoder model (~80MB) fits within the existing 4GB container memory limit alongside embedding (~420MB) and NLP (~12MB) models
