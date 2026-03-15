# Implementation Plan: RAG Retrieval Quality Improvement

## Overview

Two targeted changes to improve RAG retrieval quality: (1) increase `ContextPreparer.max_context_length` from 8,000 to 32,000 characters, and (2) swap the embedding model from `all-MiniLM-L6-v2` (384-dim) to `bge-base-en-v1.5` (768-dim) across the entire stack. All code changes are in Python. After deployment, the operator re-uploads all documents manually — no migration script.

## Tasks

- [x] 1. Increase context window and add context budget tests
  - [x] 1.1 Update `ContextPreparer` default `max_context_length` from 8000 to 32000 in `src/multimodal_librarian/services/rag_service.py`
    - Change the `__init__` default parameter `max_context_length=8000` to `max_context_length=32000`
    - _Requirements: 1.1_

  - [ ]* 1.2 Write unit test `test_context_preparer_default_32000` in `tests/components/test_rag_retrieval_quality.py`
    - Instantiate `ContextPreparer()` with no arguments and assert `max_context_length == 32000`
    - _Requirements: 1.1_

  - [ ]* 1.3 Write unit test `test_empty_chunk_list_returns_empty` in `tests/components/test_rag_retrieval_quality.py`
    - Call `_select_chunks_by_length([])` and assert the result is `[]`
    - _Requirements: Edge case for 1.2, 1.3_

  - [ ]* 1.4 Write property test for context budget maximal fitting prefix in `tests/components/test_rag_retrieval_quality.py`
    - **Property 1: Context budget selects the maximal fitting prefix**
    - **Validates: Requirements 1.2, 1.3**
    - Use `hypothesis` with `@settings(max_examples=100)`
    - Generate random lists of chunks with varying content lengths
    - Verify `_select_chunks_by_length` returns the longest prefix whose cumulative formatted length (content + 100 overhead per chunk) fits within `max_context_length`
    - Verify no additional chunk from the remaining list would fit within the remaining budget
    - Tag with comment: `# Feature: rag-retrieval-quality-improvement, Property 1: Context budget selects the maximal fitting prefix`

- [x] 2. Update embedding model in Docker and model server config
  - [x] 2.1 Update `Dockerfile.model-server` to pre-download `BAAI/bge-base-en-v1.5` instead of `all-MiniLM-L6-v2`
    - Change the `RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer(...)"` line to use `'BAAI/bge-base-en-v1.5'`
    - _Requirements: 2.1_

  - [x] 2.2 Update `docker-compose.yml` `EMBEDDING_MODEL` environment variable to `bge-base-en-v1.5` for model-server, app, and celery-worker services
    - _Requirements: 2.3, 6.6_

  - [x] 2.3 Update `src/model_server/config.py` default `embedding_model` to `bge-base-en-v1.5`
    - _Requirements: 2.1, 2.2_

- [x] 3. Update application configuration defaults
  - [x] 3.1 Update `src/multimodal_librarian/config.py` (`Settings` class)
    - Change `embedding_dimension` default from 384 to 768
    - Change `embedding_model` default to reference `bge-base-en-v1.5`
    - Update `target_embedding_tokens` description to reference `bge-base-en-v1.5` instead of `all-MiniLM-L6-v2`
    - _Requirements: 3.1, 3.2, 7.1, 7.2_

  - [x] 3.2 Update `local_config.py` (`LocalSettings` class)
    - Change `embedding_dimension` default from 384 to 768
    - Change `embedding_model` default to reference `bge-base-en-v1.5`
    - Add `'BAAI/bge-base-en-v1.5': 768` and `'bge-base-en-v1.5': 768` to the `model_dimensions` mapping
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

  - [x] 3.3 Update `aws_native_config.py` (`AWSNativeSettings` class)
    - Change `embedding_dimension` default from 384 to 768
    - Change `embedding_model` default to reference `bge-base-en-v1.5`
    - _Requirements: 3.1, 3.2_

  - [ ]* 3.4 Write unit tests for config defaults in `tests/components/test_rag_retrieval_quality.py`
    - `test_config_default_dimension_768`: Assert `Settings().embedding_dimension == 768`
    - `test_config_default_model_bge`: Assert `Settings().embedding_model` contains `bge-base-en-v1.5`
    - `test_config_model_dimension_mapping`: Assert `bge-base-en-v1.5` maps to 768 in `model_dimensions`
    - `test_config_env_var_resolution`: Set `EMBEDDING_MODEL=bge-base-en-v1.5` env var and assert dimension resolves to 768
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [x] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Update database clients for 768 dimensions
  - [x] 5.1 Update Neo4j client `ensure_indexes` in `neo4j_client.py` to create `concept_embedding_index` with dimension 768 instead of 384
    - Change the `db.index.vector.createNodeIndex` call dimension parameter from 384 to 768
    - _Requirements: 5.1, 5.3_

  - [x] 5.2 Update Milvus client hardcoded dimension references from 384 to 768 in `milvus_client.py`
    - Update `_embedding_dimension` defaults in `_load_embedding_model` and `_ensure_embedding_model` from 384 to 768
    - Update any hardcoded 384 references in comments or defaults
    - _Requirements: 4.1, 4.4_

  - [ ]* 5.3 Write unit test `test_neo4j_ensure_indexes_768` in `tests/components/test_rag_retrieval_quality.py`
    - Mock the Neo4j driver and verify the Cypher statement passed to `ensure_indexes` contains `768`
    - _Requirements: 5.1_

- [x] 6. Update all remaining hardcoded 384-dimension references
  - [x] 6.1 Update `celery_service.py` — change `_embedding_dimension = 384` to `_embedding_dimension = 768` in both locations
    - _Requirements: 6.1_

  - [x] 6.2 Update `rag_service.py` — change placeholder `np.zeros(384)` to `np.zeros(768)`
    - _Requirements: 6.2_

  - [x] 6.3 Update `kg_query_engine.py` — change placeholder `np.zeros(384)` to `np.zeros(768)` in both locations
    - _Requirements: 6.3_

  - [x] 6.4 Update `opensearch_client.py` — change default `embedding_dimension` from 384 to 768
    - _Requirements: 6.4_

  - [x] 6.5 Update `health_local.py` — change dummy vector `[0.1] * 384` to `[0.1] * 768`
    - _Requirements: 6.5_

  - [x] 6.6 Update `protocols.py` — update doc comments referencing 384 dimensions to 768
    - _Requirements: 6.4 (consistency)_

  - [ ]* 6.7 Write unit tests for hardcoded dimension updates in `tests/components/test_rag_retrieval_quality.py`
    - `test_celery_embedding_dimension_768`: Verify celery worker sets `_embedding_dimension = 768`
    - `test_rag_placeholder_768`: Verify placeholder embedding in `rag_service.py` is `np.zeros(768)`
    - `test_kg_placeholder_768`: Verify placeholder embedding in `kg_query_engine.py` is `np.zeros(768)`
    - `test_opensearch_default_dimension_768`: Verify `OpenSearchClient.embedding_dimension == 768`
    - `test_health_check_dummy_vector_768`: Verify health check dummy vector has 768 elements
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

- [x] 7. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Integration tests
  - [x]* 8.1 Write integration test `test_milvus_collection_768_schema` in `tests/integration/test_rag_retrieval_quality_integration.py`
    - Create a Milvus collection with dim=768, insert 768-dim vectors, search, and verify results
    - _Requirements: 4.1, 4.2_

  - [x]* 8.2 Write integration test `test_neo4j_vector_index_768` in `tests/integration/test_rag_retrieval_quality_integration.py`
    - Create the `concept_embedding_index` at 768 dims, insert a Concept node with a 768-dim embedding, query the index, and verify results
    - _Requirements: 5.1, 5.2_

- [x] 9. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- The operator must manually drop old Milvus collections and Neo4j indexes, then re-upload all documents after deployment — no migration script is included
- Docker commands use v2 syntax: `docker compose` (not `docker-compose`)
