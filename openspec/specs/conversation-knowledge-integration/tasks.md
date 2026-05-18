# Implementation Plan: Conversation Knowledge Integration

## Overview

Wire conversation-derived `KnowledgeChunk` objects through the existing embedding → vector store → knowledge graph → unified search pipeline. The core addition is a `ConversationKnowledgeService` that orchestrates the full fail-fast pipeline, exposed via a new API endpoint. Existing RAG pipeline, vector search, and KG query engine require no modifications.

## Tasks

- [x] 1. Enhance ConversationManager location_reference format
  - [x] 1.1 Update `convert_to_knowledge_chunks()` in `src/multimodal_librarian/components/conversation/conversation_manager.py`
    - Change `location_reference` from `group[0].timestamp.isoformat()` to `"{thread_title} | {start_timestamp} – {end_timestamp}"` format
    - Derive thread title from the conversation's `knowledge_summary` field or first user message content (truncated to 80 chars)
    - Set `section` field to the thread title instead of message ID range
    - Accept an optional `thread_title` parameter to allow the caller to pass the title
    - _Requirements: 6.2_

  - [ ]* 1.2 Write unit tests for updated location_reference format
    - Test file: `tests/components/test_conversation_manager_location_ref.py`
    - Test single-message group produces correct format with title and single timestamp
    - Test multi-message group produces correct format with title and timestamp range
    - Test fallback when no title is available (uses first message content truncated)
    - _Requirements: 6.2_

- [x] 2. Implement ConversationKnowledgeService core
  - [x] 2.1 Create `src/multimodal_librarian/services/conversation_knowledge_service.py` with dataclasses and service skeleton
    - Define `ConversionResult` and `CleanupResult` dataclasses
    - Implement `ConversationKnowledgeService.__init__()` accepting `ConversationManager`, `VectorStore`, `ModelServerClient`, and Neo4j client
    - Implement `_cleanup_existing(thread_id)` — delete vectors via `VectorStore.delete_chunks_by_source()` and KG concepts via Cypher `MATCH (c:Concept {source_document: $thread_id}) DETACH DELETE c`
    - Implement `_remove_kg_data(thread_id)` as the Neo4j cleanup helper
    - _Requirements: 8.1, 8.2_

  - [x] 2.2 Implement embedding generation in `ConversationKnowledgeService`
    - Implement `_generate_embeddings(chunks)` — call `ModelServerClient.generate_embeddings()` with `[chunk.content for chunk in chunks]` (text only, no multimedia metadata)
    - Assign returned embedding vectors to each chunk's `embedding` field
    - Raise on failure (fail-fast)
    - _Requirements: 1.2, 2.1, 2.2, 2.3_

  - [x] 2.3 Implement vector storage in `ConversationKnowledgeService`
    - Implement `_store_vectors(chunks)` — call `VectorStore.store_embeddings(chunks)`
    - Chunks already have `source_type=SourceType.CONVERSATION` and `source_id=thread_id` set by `ConversationManager`
    - Raise on failure (fail-fast)
    - _Requirements: 1.3, 3.1, 3.2, 3.3, 3.4_

  - [x] 2.4 Implement KG concept extraction in `ConversationKnowledgeService`
    - Implement `_extract_and_store_concepts(chunks, thread_id)` — use `ConceptExtractor.extract_all_concepts_async()` for each chunk
    - Set `source_document=thread_id` on all Concept nodes
    - Persist concepts and relationships to Neo4j
    - Raise on failure (fail-fast, KG failure is FATAL)
    - _Requirements: 1.4, 4.1, 4.2, 4.3_

  - [x] 2.5 Implement the main `convert_conversation(thread_id)` orchestrator method
    - Retrieve conversation via `ConversationManager.get_conversation(thread_id)`
    - Raise if thread not found or has no messages
    - Execute pipeline: cleanup → chunk → embed → store → KG extract
    - Return `ConversionResult` with all counts
    - _Requirements: 1.1, 1.5, 1.6, 1.7, 8.3_

  - [ ]* 2.6 Write property test: Pipeline produces embedded, stored chunks (Property 1)
    - Test file: `tests/services/test_conversation_knowledge_pbt.py`
    - **Property 1: Pipeline produces embedded, stored chunks**
    - Use Hypothesis to generate random `ConversationThread` objects with at least one message
    - Mock dependencies, run `convert_conversation()`, verify all chunks have non-null embeddings and `store_embeddings` was called
    - **Validates: Requirements 1.1, 1.2, 1.3**

  - [ ]* 2.7 Write property test: KG extraction produces concepts for all chunks (Property 2)
    - Test file: `tests/services/test_conversation_knowledge_pbt.py`
    - **Property 2: KG extraction produces concepts for all chunks**
    - Verify concept extraction is called for each chunk and all Concept nodes have `source_document=thread_id`
    - **Validates: Requirements 1.4, 4.1, 4.2**

  - [ ]* 2.8 Write property test: Only text content is embedded (Property 4)
    - Test file: `tests/services/test_conversation_knowledge_pbt.py`
    - **Property 4: Only text content is embedded**
    - Generate chunks with random multimedia metadata, verify embedding input is exactly `chunk.content`
    - **Validates: Requirements 2.3**

  - [ ]* 2.9 Write property test: Re-ingestion idempotence (Property 11)
    - Test file: `tests/services/test_conversation_knowledge_pbt.py`
    - **Property 11: Re-ingestion idempotence**
    - Run pipeline twice on same thread, verify cleanup was called before second ingestion and final state has no duplicates
    - **Validates: Requirements 3.4, 8.1, 8.2**

- [x] 3. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Create API endpoint and DI wiring
  - [x] 4.1 Add `get_conversation_knowledge_service` DI provider in `src/multimodal_librarian/api/dependencies/services.py`
    - Follow existing pattern: lazy init, singleton caching
    - Depend on `get_conversation_manager`, `get_vector_store`, `get_model_server_client`, `get_graph_client`
    - _Requirements: 7.5_

  - [x] 4.2 Create API router at `src/multimodal_librarian/api/routers/conversation_knowledge.py`
    - Define `ConvertToKnowledgeResponse` Pydantic model with `thread_id`, `chunks_created`, `concepts_extracted`, `status`
    - Implement `POST /api/conversations/{thread_id}/convert-to-knowledge` endpoint
    - Use `Depends(get_conversation_knowledge_service)` for DI
    - Return 404 for nonexistent thread, 400 for empty conversation, 500 for pipeline failures with stage info
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [x] 4.3 Register router in `src/multimodal_librarian/main.py`
    - Add try/except import block for `conversation_knowledge` router following existing pattern
    - Set `FEATURES["conversation_knowledge"] = True` on success
    - _Requirements: 7.1_

  - [ ]* 4.4 Write property test: API response contains required fields (Property 10)
    - Test file: `tests/api/test_conversation_knowledge_api_pbt.py`
    - **Property 10: API response contains required fields**
    - Use Hypothesis + FastAPI TestClient with mocked service, verify response always contains `thread_id`, `chunks_created` (int ≥ 0), `concepts_extracted` (int ≥ 0), `status="success"`
    - **Validates: Requirements 7.2**

  - [ ]* 4.5 Write unit tests for API error handling
    - Test file: `tests/api/test_conversation_knowledge_api.py`
    - Test 404 for nonexistent thread_id
    - Test 400 for empty conversation
    - Test 500 for pipeline failure with stage info in response
    - _Requirements: 7.3, 7.4_

- [x] 5. Verify unified search and citation behavior
  - [x] 5.1 Verify existing RAG pipeline handles conversation chunks without modification
    - Confirm `RAGService._retrieval_phase` does not filter by `source_type` in Milvus queries
    - Confirm `KnowledgeGraphQueryEngine._find_related_concepts_neo4j` returns concepts regardless of `source_document` value
    - Add inline code comments documenting this behavior if not already present
    - _Requirements: 5.1, 5.2, 5.3_

  - [ ]* 5.2 Write property test: Unified search returns both source types (Property 6)
    - Test file: `tests/services/test_unified_search_pbt.py`
    - **Property 6: Unified search returns both source types**
    - Insert mixed-source chunks into mocked vector store, verify search returns both types without filtering
    - **Validates: Requirements 5.1**

  - [ ]* 5.3 Write property test: Conversation citation location_reference format (Property 8)
    - Test file: `tests/components/test_citation_pbt.py`
    - **Property 8: Conversation citation location_reference format**
    - Generate `KnowledgeCitation` objects with `source_type=SourceType.CONVERSATION`, verify `location_reference` contains thread title and timestamp range
    - **Validates: Requirements 6.2**

  - [ ]* 5.4 Write property test: Citation filtering by source type (Property 9)
    - Test file: `tests/components/test_citation_pbt.py`
    - **Property 9: Citation filtering by source type**
    - Generate mixed `BOOK` and `CONVERSATION` citations, verify `get_citations_by_source()` partitions correctly
    - **Validates: Requirements 6.1, 6.3**

- [x] 6. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- The design uses Python — all code examples target Python 3.9+ with FastAPI and Pydantic 2.5+
- KG failure is FATAL — no graceful degradation in the pipeline
- No Celery — conversation conversion is synchronous (small data volume per conversation)
- Existing RAG pipeline, vector search, and KG query engine require no code changes
- Property tests use Hypothesis with minimum 100 examples per property
