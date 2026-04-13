# Implementation Plan: Shared Ollama Thread Pool

## Overview

This plan implements a shared 20-thread pool for Ollama-based processing (bridge generation and KG concept extraction) with weighted fair share scheduling and dynamic concurrency scaling. The implementation follows the design document's architecture with a singleton `OllamaPoolManager`, separate queues per task type, a dispatcher thread for fair share scheduling, and exponential backoff on concurrency when Ollama is overwhelmed (20 → 10 → 5 → 3 → 2 → 1).

## Tasks

- [x] 1. Create Pool Manager Module
  - [x] 1.1 Create `ollama_pool_manager.py` with core data structures
    - Create `src/multimodal_librarian/services/ollama_pool_manager.py`
    - Implement `TaskType` enum (BRIDGE, KG, UNKNOWN)
    - Implement `PoolExhaustedError` exception class
    - Implement `FairShareState` dataclass with deficit calculations
    - Implement `ConcurrencyScalingState` dataclass with sliding window, scale-down/scale-up logic
    - Implement `PoolStats` dataclass for statistics
    - _Requirements: 1.1, 1.2, 8.1, 8.2, 9.1, 9.2, 9.4, 9.8_

  - [x] 1.2 Implement `OllamaPoolManager` singleton class
    - Implement `__new__` with thread-safe singleton pattern
    - Implement `__init__` with lazy initialization flag
    - Implement `_parse_fair_share_ratio()` for env var parsing
    - Implement `_ensure_pool()` for lazy pool creation
    - _Requirements: 1.1, 1.5, 7.4, 7.5, 8.7_

  - [x] 1.3 Implement thread-local event loop management
    - Implement `_get_thread_event_loop()` for per-worker event loops
    - Ensure event loops are reused across tasks on same thread
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [x] 1.4 Implement fair share dispatcher with dynamic concurrency scaling
    - Implement separate `_bridge_queue` and `_kg_queue`
    - Implement `_pick_next_task_type()` based on deficit
    - Implement `_dispatch_loop()` background thread with concurrency limit enforcement
    - Dispatcher SHALL pause dispatch when `active_count >= active_limit`
    - Dispatcher SHALL check `should_scale_down()` and `should_scale_up()` each iteration
    - Record timeout/success results in sliding window after each task completes
    - _Requirements: 8.3, 8.4, 8.5, 9.2, 9.3, 9.4, 9.5, 9.6_

  - [x] 1.5 Implement work submission APIs
    - Implement `submit_ollama_work()` for sync callables
    - Implement `submit_ollama_work_async()` for coroutines
    - Implement queue capacity enforcement with `PoolExhaustedError`
    - _Requirements: 1.3, 1.4, 6.2, 6.5_

  - [x] 1.6 Implement statistics and shutdown
    - Implement `get_pool_stats()` with fair share metrics and concurrency scaling metrics
    - Implement `shutdown()` for graceful termination
    - Implement module-level convenience functions
    - _Requirements: 1.6, 5.2, 5.3, 5.4, 8.6, 9.7_

  - [ ]* 1.7 Write property test for singleton instance
    - **Property 1: Singleton Pool Instance**
    - **Validates: Requirements 1.1, 7.4, 7.5**

  - [ ]* 1.8 Write property test for work submission returns results
    - **Property 2: Work Submission Returns Results**
    - **Validates: Requirements 1.3, 1.4**

  - [ ]* 1.9 Write property test for fair share prevents starvation
    - **Property 3: Fair Share Scheduling Prevents Starvation**
    - **Validates: Requirements 8.3, 8.5**

  - [ ]* 1.10 Write property test for fair share deficit drives selection
    - **Property 4: Fair Share Deficit Drives Selection**
    - **Validates: Requirements 8.3**

  - [ ]* 1.11 Write property test for single queue gets full capacity
    - **Property 5: Single Queue Gets Full Capacity**
    - **Validates: Requirements 8.5**

  - [ ]* 1.12 Write property test for bounded queue enforcement
    - **Property 6: Bounded Queue Enforcement**
    - **Validates: Requirements 6.2, 6.5**

  - [ ]* 1.13 Write property test for configuration from environment
    - **Property 7: Configuration from Environment**
    - **Validates: Requirements 1.2, 5.1, 8.7**

  - [ ]* 1.14 Write property test for fair share statistics accuracy
    - **Property 8: Fair Share Statistics Accuracy**
    - **Validates: Requirements 5.2, 8.6**

  - [ ]* 1.15 Write property test for thread-local event loop reuse
    - **Property 9: Thread-Local Event Loop Reuse**
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.4**

  - [ ]* 1.16 Write property test for concurrency scale-down on high timeout rate
    - **Property 10: Concurrency Scale-Down on High Timeout Rate**
    - Verify halving sequence: 20 → 10 → 5 → 3 → 2 → 1
    - **Validates: Requirements 9.2, 9.8**

  - [ ]* 1.17 Write property test for concurrency scale-up on recovery
    - **Property 11: Concurrency Scale-Up on Recovery**
    - Verify doubling back up to max capacity after recovery period
    - **Validates: Requirements 9.3, 9.4**

  - [ ]* 1.18 Write property test for concurrency limit bounds
    - **Property 12: Concurrency Limit Bounds**
    - Verify `1 <= active_limit <= max_capacity` always holds
    - **Validates: Requirements 9.2, 9.4**

- [x] 2. Checkpoint - Pool Manager Module Complete
  - Ensure all tests pass, ask the user if questions arise.


- [x] 3. Integrate with Bridge Generator
  - [x] 3.1 Remove private `_ollama_pool` from `SmartBridgeGenerator`
    - Remove `ThreadPoolExecutor` instantiation from `__init__`
    - Keep `_thread_local` for httpx.AsyncClient compatibility
    - _Requirements: 2.1, 2.3_

  - [x] 3.2 Update bridge generation to use shared pool
    - Import `submit_ollama_work_async` and `PoolExhaustedError`
    - Modify `_generate_with_ollama_sync` to use shared pool submission
    - Pass `task_type="bridge"` for fair share tracking
    - _Requirements: 2.2_

  - [x] 3.3 Add fallback handling for `PoolExhaustedError`
    - Catch `PoolExhaustedError` in bridge generation
    - Fall back to mechanical bridge generation with warning log
    - _Requirements: 2.5, 6.3_

  - [x] 3.4 Verify backward compatibility
    - Ensure `batch_generate_bridges()` API unchanged
    - Ensure `generate_bridge()` API unchanged
    - _Requirements: 2.4_

  - [ ]* 3.5 Write unit tests for bridge generator integration
    - Test shared pool submission with task_type="bridge"
    - Test fallback to mechanical bridge on PoolExhaustedError
    - _Requirements: 2.2, 2.5_

- [x] 4. Integrate with KG Builder
  - [x] 4.1 Replace semaphore pattern in celery_service.py
    - Remove `asyncio.Semaphore(MAX_CONCURRENT)` pattern
    - Import `submit_ollama_work_async` and `PoolExhaustedError`
    - _Requirements: 3.1_

  - [x] 4.2 Update KG chunk processing to use shared pool
    - Create `process_chunk_via_pool()` wrapper function
    - Pass `task_type="kg"` for fair share tracking
    - Maintain batch processing structure in `_update_knowledge_graph()`
    - _Requirements: 3.2, 3.4_

  - [x] 4.3 Add fallback handling for `PoolExhaustedError`
    - Catch `PoolExhaustedError` in chunk processing
    - Fall back to regex/NER-only extraction with warning log
    - _Requirements: 3.5, 6.4_

  - [x] 4.4 Verify async interface preserved
    - Ensure `extract_concepts_ollama()` interface unchanged
    - Ensure `extract_all_concepts_async()` interface unchanged
    - _Requirements: 3.3_

  - [ ]* 4.5 Write unit tests for KG builder integration
    - Test shared pool submission with task_type="kg"
    - Test fallback to regex/NER on PoolExhaustedError
    - _Requirements: 3.2, 3.5_

- [x] 5. Checkpoint - Integration Complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Add Celery Worker Lifecycle Integration
  - [x] 6.1 Add worker_shutdown signal handler
    - Import `worker_shutdown` from `celery.signals`
    - Import `shutdown_pool` from `ollama_pool_manager`
    - Register signal handler to call `shutdown_pool(wait=True)`
    - _Requirements: 7.3_

  - [ ]* 6.2 Write unit test for Celery lifecycle integration
    - Test that shutdown_pool is called on worker_shutdown signal
    - _Requirements: 7.3_

- [x] 7. Add Health Endpoint
  - [x] 7.1 Create `/health/ollama-pool` endpoint
    - Add endpoint to health router
    - Call `get_pool_stats()` from pool manager
    - Return JSON with pool stats, fair share metrics, and concurrency scaling metrics
    - _Requirements: 5.5, 9.7_

  - [ ]* 7.2 Write unit test for health endpoint
    - Test endpoint returns expected JSON structure
    - Test fair share metrics are included
    - Test concurrency scaling metrics are included
    - _Requirements: 5.5, 9.7_

- [x] 8. Final Checkpoint - All Tests Pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Implement Task Deduplication via Distributed Locking
  - [x] 9.1 Create `RedisTaskLock` class
    - Implement atomic lock acquisition via `SET NX EX`
    - Implement compare-and-delete release via Lua script
    - Implement heartbeat thread for TTL renewal (every TTL/3 seconds)
    - _Requirements: 10.5, 10.6, 10.7_

  - [x] 9.2 Create `@redis_task_lock` decorator
    - Extract `document_id` from task arguments
    - Acquire lock before task execution, release in `finally`
    - Return `skipped_duplicate` if lock already held
    - _Requirements: 10.3, 10.6, 10.8_

  - [x] 9.3 Apply decorator to `generate_bridges_task`
    - Add `@redis_task_lock("bridge_lock:{document_id}")` decorator
    - Lock TTL defaults to task's `soft_time_limit`
    - _Requirements: 10.1_

  - [x] 9.4 Apply decorator to `update_knowledge_graph_task`
    - Add `@redis_task_lock("kg_lock:{document_id}")` decorator
    - Lock TTL defaults to task's `soft_time_limit`
    - _Requirements: 10.2_

  - [ ]* 9.5 Write property test for task deduplication
    - **Property 13: Task Deduplication**
    - Verify at most one instance runs per document_id
    - **Validates: Requirements 10.1, 10.2, 10.3, 10.6**

  - [ ]* 9.6 Write property test for lock auto-expiry
    - **Property 14: Lock Auto-Expiry**
    - Verify lock expires after TTL if holder is killed
    - **Validates: Requirements 10.5**

- [x] 10. Final Checkpoint - All Tests Pass Including Deduplication
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. Implement KG Concept Extraction Gemini Failover
  - [x] 11.1 Add Gemini failover to `extract_concepts_ollama()`
    - Extract prompt building into shared code (used by both Ollama and Gemini)
    - Try Ollama first; on failure, fall back to Gemini with same prompt
    - Log "Ollama concept extraction failed, falling back to Gemini" at INFO level
    - _Requirements: 11.1, 11.2, 11.5_

  - [x] 11.2 Implement `_extract_concepts_gemini()` method
    - Lazy-initialize Gemini model on first failover
    - Parse response using existing `_extract_json_array()` and `_filter_by_rationale()`
    - Return `[]` if Gemini also fails
    - _Requirements: 11.3, 11.4, 11.7_

  - [x] 11.3 Add provider statistics tracking
    - Track `ollama_success`, `gemini_fallback`, `both_failed` counts
    - Expose via existing stats mechanism
    - _Requirements: 11.8_

  - [x] 11.4 Verify `extract_all_concepts_async()` unchanged
    - Confirm NER + Ollama/Gemini + regex still run in parallel
    - Confirm merge/dedup logic unchanged
    - _Requirements: 11.6_

  - [ ]* 11.5 Write property test for KG Gemini failover
    - **Property 15: KG Concept Extraction Gemini Failover**
    - **Validates: Requirements 11.1, 11.4**

- [x] 12. Final Checkpoint - All Tests Pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific integration points and edge cases
