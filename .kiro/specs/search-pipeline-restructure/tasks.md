# Implementation Plan: Search Pipeline Restructure

## Overview

Restructure `RAGService._search_documents` into a two-phase pipeline (Retrieval → Post-Processing), add SearXNG web search integration, and wire everything through the existing DI system. Tasks are ordered so each builds on the previous, with tests close to implementation.

## Tasks

- [x] 1. Add SearXNG configuration settings
  - [x] 1.1 Add SearXNG fields to `Settings` class in `src/multimodal_librarian/config/config.py`
    - Add `searxng_host` (default `"searxng"`), `searxng_port` (default `8080`), `searxng_timeout` (default `10.0`), `searxng_enabled` (default `False`), `searxng_max_results` (default `5`), `web_search_result_count_threshold` (default `3`)
    - _Requirements: 6.1, 6.2, 6.3_
  - [x] 1.2 Add SearXNG environment variables to `src/.env.local`
    - Add `SEARXNG_HOST`, `SEARXNG_PORT`, `SEARXNG_TIMEOUT`, `SEARXNG_ENABLED`, `SEARXNG_MAX_RESULTS`, `WEB_SEARCH_RESULT_COUNT_THRESHOLD` with defaults
    - _Requirements: 6.4_

- [-] 2. Implement SearXNG client
  - [x] 2.1 Create `src/multimodal_librarian/clients/searxng_client.py`
    - Implement `SearXNGResult` dataclass and `SearXNGClient` async class
    - Use `aiohttp` with lazy session creation (no connections at instantiation)
    - Implement `search(query, max_results)` method calling SearXNG JSON API
    - Implement `close()` for cleanup
    - _Requirements: 5.1, 5.2, 5.3, 5.6_
  - [ ]* 2.2 Write property test: Client instantiation creates no connections
    - **Property 10: Client instantiation creates no connections**
    - **Validates: Requirements 5.6**
  - [ ]* 2.3 Write property test: SearXNG results tagged as WEB_SEARCH
    - **Property 9: SearXNG results tagged as WEB_SEARCH**
    - **Validates: Requirements 3.4**

- [x] 3. Add SearXNG DI providers
  - [x] 3.1 Add `get_searxng_client` and `get_searxng_client_optional` to `src/multimodal_librarian/api/dependencies/services.py`
    - Follow existing lazy initialization and singleton caching pattern
    - Add `_searxng_client` global cache variable
    - `get_searxng_client` raises HTTPException 503 when disabled
    - `get_searxng_client_optional` returns `None` when disabled/unavailable
    - Add cleanup in `cleanup_services()` and cache clearing in `clear_all_caches()`
    - _Requirements: 5.4, 5.5_

- [x] 4. Checkpoint - Ensure SearXNG client and config work
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Restructure `_search_documents` into two-phase pipeline
  - [x] 5.1 Add `_retrieval_phase` method to `RAGService` in `src/multimodal_librarian/services/rag_service.py`
    - Extract KG-first-then-semantic-fallback logic from current `_search_documents`
    - Remove the source prioritization branch that currently short-circuits KG retrieval
    - KG Retrieval attempted first when available; falls back to semantic search on failure or empty results
    - _Requirements: 1.1, 1.2, 1.3, 1.4_
  - [x] 5.2 Add `_post_processing_phase` method to `RAGService`
    - Tag all retrieval-phase chunks as `LIBRARIAN`
    - Check result count against `web_search_result_count_threshold`; invoke SearXNG if below threshold and enabled
    - Apply `librarian_boost_factor` to LIBRARIAN chunks (cap at 1.0)
    - Merge and sort by boosted score descending, LIBRARIAN wins ties
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.2, 3.5, 3.6_
  - [x] 5.3 Add `_convert_web_results` method to `RAGService`
    - Convert `SearXNGResult` objects to `DocumentChunk` objects with `source_type` = `"web_search"`
    - _Requirements: 3.4_
  - [x] 5.4 Rewrite `_search_documents` to call `_retrieval_phase` then `_post_processing_phase`
    - Remove the old source-prioritization-as-search-strategy branch
    - Remove the old KG-retrieval branch (now in `_retrieval_phase`)
    - Remove the old semantic-search fallback branch (now in `_retrieval_phase`)
    - _Requirements: 1.5, 2.1_
  - [ ]* 5.5 Write property test: KG results bypass semantic search
    - **Property 1: KG results bypass semantic search**
    - **Validates: Requirements 1.2**
  - [ ]* 5.6 Write property test: KG failure triggers semantic fallback
    - **Property 2: KG failure triggers semantic fallback**
    - **Validates: Requirements 1.3, 1.4**
  - [ ]* 5.7 Write property test: Post-processing runs on all retrieval output
    - **Property 3: Post-processing runs on all retrieval output**
    - **Validates: Requirements 1.5, 2.1**

- [x] 6. Checkpoint - Ensure pipeline restructure works
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 7. Implement post-processing property tests
  - [ ]* 7.1 Write property test: Retrieval-phase chunks tagged as LIBRARIAN
    - **Property 4: Retrieval-phase chunks tagged as LIBRARIAN**
    - **Validates: Requirements 2.2**
  - [ ]* 7.2 Write property test: Librarian boost correctness
    - **Property 5: Librarian boost correctness**
    - **Validates: Requirements 2.3**
  - [ ]* 7.3 Write property test: Output sorted by score with LIBRARIAN tiebreaker
    - **Property 6: Output sorted by score with LIBRARIAN tiebreaker**
    - **Validates: Requirements 2.4, 2.5**
  - [ ]* 7.4 Write property test: Web search triggered below threshold
    - **Property 7: Web search triggered below threshold**
    - **Validates: Requirements 3.1**
  - [ ]* 7.5 Write property test: Web search skipped when disabled
    - **Property 8: Web search skipped when disabled**
    - **Validates: Requirements 3.2, 6.5**

- [x] 8. Update DI wiring for RAGService
  - [x] 8.1 Update `RAGService.__init__` to accept `searxng_client` parameter
    - Add `searxng_client` optional parameter
    - Read `librarian_boost_factor`, `web_search_result_count_threshold`, `searxng_max_results` from settings
    - _Requirements: 5.3, 6.1, 6.2, 6.3_
  - [x] 8.2 Update `get_rag_service` in `services.py` to inject `searxng_client`
    - Add `get_searxng_client_optional` as a dependency
    - Pass `searxng_client` to `RAGService` constructor
    - Handle dynamic injection for cached instances (same pattern as KG retrieval service)
    - _Requirements: 5.4, 5.5_

- [x] 9. Add SearXNG Docker service and configuration
  - [x] 9.1 Add `searxng` service to `docker-compose.yml`
    - Use `searxng/searxng:latest` image
    - Add to `app-network`, expose port `8888:8080`
    - Use `profiles: [web-search]` so it's optional
    - Mount `searxng-settings.yml` as config
    - _Requirements: 4.1, 4.2, 4.4, 4.5_
  - [x] 9.2 Create `searxng-settings.yml` configuration file
    - Enable JSON format responses
    - Set bind address and port
    - _Requirements: 4.3_
  - [x] 9.3 Add `SEARXNG_ENABLED` and `SEARXNG_HOST` environment variables to the `app` service in `docker-compose.yml`
    - Default `SEARXNG_ENABLED=false`
    - _Requirements: 6.5_

- [ ] 10. Graceful degradation and exception isolation tests
  - [ ]* 10.1 Write property test: Graceful degradation with semantic search
    - **Property 11: Graceful degradation with semantic search**
    - **Validates: Requirements 7.1, 7.2**
  - [ ]* 10.2 Write property test: Exception isolation across stages
    - **Property 12: Exception isolation across stages**
    - **Validates: Requirements 7.4**
  - [ ]* 10.3 Write unit tests for edge cases
    - Test: KG raises `ConnectionError` → semantic search called, no propagation
    - Test: Empty retrieval + SearXNG failure → returns empty list
    - Test: All services unavailable → returns empty list, no exception
    - _Requirements: 1.4, 3.5, 7.3_

- [x] 11. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties using Hypothesis
- Unit tests validate specific examples and edge cases
- The `source_prioritization_engine` remains in the codebase for backward compatibility but is no longer called from `_search_documents`
