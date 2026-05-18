# Implementation Plan: Semantic Concept Matching

## Overview

Add semantic similarity matching to the KG retrieval pipeline. Concepts get embedding vectors during ingestion, a Neo4j vector index enables ANN search at query time, and the QueryDecomposer merges lexical + semantic matches before feeding them to the existing KGRetrievalService.

## Tasks

- [x] 1. Add Neo4j vector index for concept embeddings
  - [x] 1.1 Add vector index creation to `Neo4jClient.ensure_indexes`
    - Add `CALL db.index.vector.createNodeIndex('concept_embedding_index', 'Concept', 'embedding', 384, 'cosine')` to the `index_statements` list in `src/multimodal_librarian/clients/neo4j_client.py`
    - Wrap in try/except like existing index statements (idempotent)
    - _Requirements: 1.4_

  - [ ]* 1.2 Write unit test for vector index creation
    - Verify `ensure_indexes` includes the vector index creation statement
    - Mock the Neo4j session and verify the statement is executed
    - _Requirements: 1.4_

- [x] 2. Store embeddings on Concept nodes during document processing
  - [x] 2.1 Add embedding generation to concept persistence in `celery_service.py`
    - Before the concept persistence loop, batch all concept names and call `model_server_client.generate_embeddings()`
    - Add the resulting embedding as an `embedding` property on each Concept node
    - Handle model server unavailability: create nodes without `embedding`, log warning
    - _Requirements: 1.1, 1.2, 1.3_

  - [x] 2.2 Add embedding generation to concept persistence in `conversations.py`
    - Same pattern as celery_service: batch concept names, generate embeddings, add to node properties
    - Handle model server unavailability gracefully
    - _Requirements: 1.1, 1.2, 1.3_

  - [ ]* 2.3 Write unit tests for embedding persistence
    - Test that concept nodes include `embedding` property when model server is available
    - Test graceful degradation when model server is unavailable (node created without embedding)
    - Test that embedding requests are batched (single call for N concepts)
    - _Requirements: 1.1, 1.2, 1.3_

- [x] 3. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Add semantic matching to QueryDecomposer
  - [x] 4.1 Extend `QueryDecomposer.__init__` with semantic matching parameters
    - Add `model_server_client`, `similarity_threshold` (default 0.7), `semantic_max_results` (default 10), `semantic_enabled` (default True) parameters
    - Add `set_model_server_client` method following existing `set_neo4j_client` pattern
    - _Requirements: 3.1, 3.2, 3.3, 5.1, 5.2_

  - [x] 4.2 Implement `_find_semantic_matches` method on `QueryDecomposer`
    - Embed the query via `model_server_client.generate_embeddings([query])`
    - Execute `CALL db.index.vector.queryNodes('concept_embedding_index', $top_k, $embedding)` Cypher query
    - Filter results by `similarity_threshold`
    - Return matches annotated with `match_type: "semantic"`
    - Return empty list if model server unavailable or semantic disabled
    - _Requirements: 2.1, 2.2, 2.4, 3.4_

  - [x] 4.3 Implement merge logic in `QueryDecomposer.decompose`
    - Run `_find_entity_matches` (lexical) and `_find_semantic_matches` concurrently with `asyncio.gather`
    - Annotate lexical matches with `match_type: "lexical"`
    - Merge by `concept_id`: deduplicate, prefer higher score, set `match_type: "both"` for overlaps
    - Populate `concept_matches` on the QueryDecomposition with merged results
    - _Requirements: 2.3, 2.5, 4.1_

  - [ ]* 4.4 Write property test: threshold filtering
    - **Property 3: Threshold filtering removes low-score matches**
    - Generate random lists of concept match dicts with random similarity_scores and random thresholds
    - Apply the threshold filter function
    - Assert all outputs have score >= threshold and no valid inputs are dropped
    - **Validates: Requirements 2.2**

  - [ ]* 4.5 Write property test: merge deduplication
    - **Property 4: Merge deduplicates by concept_id and prefers higher score**
    - Generate two random lists of concept match dicts with overlapping concept_ids and random scores
    - Apply the merge function
    - Assert unique concept_ids, correct score preference, and match_type="both" for overlaps
    - **Validates: Requirements 2.3**

  - [ ]* 4.6 Write property test: match format and annotation validity
    - **Property 5: Concept matches have valid format and match_type**
    - Generate random concept match dicts from the merge function
    - Assert required keys (concept_id, name, source_chunks, match_type) and valid match_type values
    - **Validates: Requirements 2.5, 4.1**

  - [ ]* 4.7 Write property test: semantic unavailability yields lexical-only
    - **Property 6: Semantic unavailability yields lexical-only results**
    - Generate random queries with semantic_enabled=False or model_server_client=None
    - Assert all returned matches have match_type="lexical" and model server was not invoked
    - **Validates: Requirements 3.4, 5.2**

- [x] 5. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Update QueryDecomposition model for round-trip serialization
  - [x] 6.1 Verify `to_dict` / `from_dict` preserves `match_type` in concept_matches
    - The existing implementation serializes `concept_matches` as a list of dicts, so `match_type` is preserved automatically
    - Add a test to confirm this behavior explicitly
    - _Requirements: 4.3_

  - [ ]* 6.2 Write property test: QueryDecomposition round-trip serialization
    - **Property 7: QueryDecomposition round-trip serialization**
    - Generate random QueryDecomposition objects with concept_matches containing match_type annotations
    - Assert `from_dict(to_dict(obj))` produces equivalent data with all match_type values preserved
    - **Validates: Requirements 4.3**

- [x] 7. Wire semantic matching into KGRetrievalService dependency chain
  - [x] 7.1 Update `KGRetrievalService` to inject `model_server_client` into `QueryDecomposer`
    - In `KGRetrievalService.__init__` or `set_model_client`, pass the model client through to the QueryDecomposer via `set_model_server_client`
    - Ensure the DI chain in `src/multimodal_librarian/api/dependencies/services.py` provides the model server client to the KGRetrievalService
    - _Requirements: 5.1, 5.2, 4.2_

  - [ ]* 7.2 Write integration test for end-to-end semantic matching
    - Mock Neo4j with concept nodes that have embeddings
    - Mock model server to return embeddings
    - Verify that a query with no lexical overlap still finds semantically similar concepts
    - Verify KGRetrievalService processes semantic matches identically to lexical matches
    - _Requirements: 4.1, 4.2_

- [x] 8. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties using Hypothesis
- Unit tests validate specific examples and edge cases
- The knowledge graph should be rebuilt from scratch after implementation to include embeddings on all concepts
