# Requirements Document

## Introduction

This feature consolidates the two separate thread pools used for Ollama-based processing (bridge generation and knowledge graph concept extraction) into a single shared 20-thread pool with dynamic concurrency scaling. Currently, bridging uses a dedicated `ThreadPoolExecutor` with 15 workers in `SmartBridgeGenerator`, while KG processing uses an `asyncio.Semaphore(15)` to limit concurrent Ollama calls. Since Ollama is configured with `OLLAMA_NUM_PARALLEL=20`, the current architecture leaves capacity unused when one task finishes faster than the other. A shared pool enables natural load balancing—whichever task has more pending work automatically gets more threads. Additionally, when Ollama becomes overwhelmed (high timeout rate), the pool dynamically halves its active concurrency (20 → 10 → 5 → 3 → 2 → 1) and ramps back up when Ollama recovers.

## Glossary

- **Shared_Ollama_Pool**: A singleton `ThreadPoolExecutor` with 20 workers that both bridge generation and KG concept extraction submit work to
- **Bridge_Generator**: The `SmartBridgeGenerator` class in `bridge_generator.py` that generates contextual bridges between document chunks using Ollama
- **KG_Builder**: The `KnowledgeGraphBuilder` and `ConceptExtractor` classes in `kg_builder.py` that extract concepts from chunks using Ollama
- **Celery_Service**: The orchestration layer in `celery_service.py` that runs bridge generation and KG processing in parallel
- **Pool_Manager**: A new module that owns the shared thread pool lifecycle and provides submission APIs
- **Ollama_Capacity**: The maximum concurrent requests Ollama can handle, configured via `OLLAMA_NUM_PARALLEL` environment variable (default 20)
- **Weighted_Fair_Share**: A scheduling policy that tracks each task type's share of completed work and prioritizes the task type that is behind its target share
- **Fair_Share_Ratio**: The target ratio of bridge tasks to KG tasks (default 1:1, configurable)
- **Dynamic_Concurrency**: An adaptive mechanism that halves active concurrency when Ollama timeout rate exceeds a threshold, and doubles it back when Ollama recovers
- **Timeout_Rate**: The ratio of timed-out Ollama requests to total requests within a sliding window

## Requirements

### Requirement 1: Shared Thread Pool Module

**User Story:** As a developer, I want a centralized module that manages the shared Ollama thread pool, so that both bridging and KG processing can submit work to the same pool without duplicating pool management code.

#### Acceptance Criteria

1. THE Pool_Manager SHALL provide a singleton `ThreadPoolExecutor` with `max_workers` equal to the Ollama_Capacity setting
2. WHEN the Ollama_Capacity environment variable is not set, THE Pool_Manager SHALL default to 20 workers
3. THE Pool_Manager SHALL provide a `submit_ollama_work(callable, *args, **kwargs)` function that submits work to the shared pool and returns a `Future`
4. THE Pool_Manager SHALL provide an async `submit_ollama_work_async(coroutine_func, *args, **kwargs)` function that wraps async Ollama calls for thread pool execution
5. THE Pool_Manager SHALL use lazy initialization to create the pool on first use, not at module import time
6. THE Pool_Manager SHALL provide a `shutdown()` function for graceful pool termination during application shutdown

### Requirement 2: Bridge Generator Integration

**User Story:** As a developer, I want the bridge generator to use the shared pool instead of its private pool, so that bridge generation can utilize idle threads when KG processing is slower.

#### Acceptance Criteria

1. THE Bridge_Generator SHALL remove its private `_ollama_pool` ThreadPoolExecutor
2. WHEN generating bridges, THE Bridge_Generator SHALL submit Ollama calls via `Pool_Manager.submit_ollama_work_async()`
3. THE Bridge_Generator SHALL preserve its existing per-thread event loop caching for httpx.AsyncClient compatibility
4. THE Bridge_Generator SHALL maintain backward compatibility with its public `batch_generate_bridges()` API
5. IF the shared pool is unavailable, THEN THE Bridge_Generator SHALL fall back to synchronous execution with a warning log

### Requirement 3: KG Builder Integration

**User Story:** As a developer, I want the KG concept extractor to use the shared pool instead of its semaphore-based concurrency, so that KG processing can utilize idle threads when bridging is faster.

#### Acceptance Criteria

1. THE KG_Builder SHALL replace its `asyncio.Semaphore(MAX_CONCURRENT)` pattern with shared pool submission
2. WHEN extracting concepts via Ollama, THE KG_Builder SHALL submit calls via `Pool_Manager.submit_ollama_work_async()`
3. THE KG_Builder SHALL preserve its existing `extract_concepts_ollama()` async interface
4. THE KG_Builder SHALL maintain the existing batch processing structure in `_update_knowledge_graph()`
5. IF the shared pool is unavailable, THEN THE KG_Builder SHALL fall back to direct async execution with a warning log

### Requirement 4: Thread-Local State Management

**User Story:** As a developer, I want thread-local state (event loops, httpx clients) to be properly managed across the shared pool, so that async Ollama calls work correctly regardless of which component submitted them.

#### Acceptance Criteria

1. THE Pool_Manager SHALL provide thread-local event loop management for workers
2. WHEN a worker thread executes an async Ollama call, THE Pool_Manager SHALL reuse the thread's existing event loop if available
3. IF no event loop exists for a worker thread, THEN THE Pool_Manager SHALL create a new event loop and cache it thread-locally
4. THE Pool_Manager SHALL NOT close thread-local event loops between tasks to preserve cached httpx.AsyncClient connections
5. WHEN the pool shuts down, THE Pool_Manager SHALL close all thread-local event loops

### Requirement 5: Configuration and Observability

**User Story:** As an operator, I want the shared pool size to be configurable and observable, so that I can tune it based on Ollama capacity and monitor utilization.

#### Acceptance Criteria

1. THE Pool_Manager SHALL read pool size from `OLLAMA_NUM_PARALLEL` environment variable
2. THE Pool_Manager SHALL expose `get_pool_stats()` returning active worker count, pending task count, and completed task count
3. WHEN a task is submitted, THE Pool_Manager SHALL log at DEBUG level with task type (bridge/kg) and queue depth
4. WHEN pool utilization exceeds 90% for more than 10 seconds, THE Pool_Manager SHALL log a WARNING about potential bottleneck
5. THE Pool_Manager SHALL expose pool statistics via a `/health/ollama-pool` endpoint for monitoring

### Requirement 6: Graceful Degradation

**User Story:** As a developer, I want the system to continue functioning if the shared pool encounters errors, so that document processing doesn't fail completely.

#### Acceptance Criteria

1. IF a pool worker thread dies unexpectedly, THEN THE Pool_Manager SHALL log an ERROR and continue with remaining workers
2. IF the pool becomes exhausted (all workers busy, queue full), THEN THE Pool_Manager SHALL reject new submissions with a `PoolExhaustedError`
3. WHEN `PoolExhaustedError` is raised, THE Bridge_Generator SHALL fall back to mechanical bridge generation
4. WHEN `PoolExhaustedError` is raised, THE KG_Builder SHALL skip Ollama extraction and continue with regex/NER only
5. THE Pool_Manager SHALL implement a bounded queue (default 1000 tasks) to prevent unbounded memory growth

### Requirement 7: Celery Worker Lifecycle

**User Story:** As a developer, I want the shared pool to integrate correctly with Celery worker lifecycle, so that pool resources are properly managed across task executions.

#### Acceptance Criteria

1. THE Pool_Manager SHALL be initialized lazily on first use within a Celery worker
2. THE Pool_Manager SHALL survive across multiple Celery task executions within the same worker process
3. WHEN a Celery worker shuts down, THE Pool_Manager SHALL gracefully shutdown the pool via worker signal handlers
4. THE Pool_Manager SHALL handle the case where multiple Celery tasks attempt concurrent pool initialization
5. THE Pool_Manager SHALL use a process-level lock to ensure single pool instance per worker process

### Requirement 8: Weighted Fair Share Scheduling

**User Story:** As a developer, I want the shared pool to prevent one task type from starving the other, so that both bridging and KG processing make progress even when one submits work faster.

#### Acceptance Criteria

1. THE Pool_Manager SHALL track the cumulative completed work count for each task type (bridge, kg)
2. THE Pool_Manager SHALL maintain a configurable Fair_Share_Ratio (default 1:1) representing the target ratio of bridge to KG task completions
3. WHEN selecting the next task to execute, THE Pool_Manager SHALL prioritize the task type that is furthest behind its fair share
4. THE Pool_Manager SHALL use separate internal queues per task type to enable fair share selection
5. IF one task type has no pending work, THEN THE Pool_Manager SHALL allow the other task type to use all available capacity
6. THE Pool_Manager SHALL expose fair share statistics (current ratio, target ratio, deficit per type) via `get_pool_stats()`
7. THE Fair_Share_Ratio SHALL be configurable via `OLLAMA_FAIR_SHARE_RATIO` environment variable (format: "bridge:kg", e.g., "1:1" or "2:1")

### Requirement 9: Dynamic Concurrency Scaling

**User Story:** As a developer, I want the pool to automatically reduce concurrency when Ollama is overwhelmed with timeouts, and ramp back up when it recovers, so that we avoid wasting threads on requests that will just time out.

#### Acceptance Criteria

1. THE Pool_Manager SHALL track the Timeout_Rate within a sliding window of the most recent N completed tasks (default N=20, configurable via `OLLAMA_TIMEOUT_WINDOW`)
2. WHEN the Timeout_Rate exceeds a configurable threshold (default 50%, configurable via `OLLAMA_TIMEOUT_THRESHOLD`), THE Pool_Manager SHALL halve the active concurrency limit (floor division, minimum 1)
3. THE Pool_Manager SHALL enforce the active concurrency limit by pausing dispatch from both queues until active workers drop below the limit
4. WHEN the Timeout_Rate drops below the threshold for a configurable recovery period (default 30 seconds, configurable via `OLLAMA_RECOVERY_PERIOD`), THE Pool_Manager SHALL double the active concurrency limit (up to the configured Ollama_Capacity)
5. THE Pool_Manager SHALL log at WARNING level when concurrency is reduced, including the current timeout rate and new concurrency limit
6. THE Pool_Manager SHALL log at INFO level when concurrency is restored, including the new concurrency limit
7. THE Pool_Manager SHALL expose the current active concurrency limit and timeout rate via `get_pool_stats()`
8. THE concurrency scaling sequence for default capacity of 20 SHALL be: 20 → 10 → 5 → 3 → 2 → 1 (halving with floor division)

### Requirement 10: Task Deduplication via Distributed Locking

**User Story:** As a developer, I want long-running Celery tasks (bridge generation, KG processing) to be protected against duplicate execution, so that unacknowledged task redelivery doesn't spawn multiple copies of the same task for the same document.

#### Acceptance Criteria

1. BEFORE starting execution, `generate_bridges_task` SHALL acquire a Redis distributed lock keyed by `bridge_lock:{document_id}` with a TTL equal to the task's `soft_time_limit`
2. BEFORE starting execution, `update_knowledge_graph_task` SHALL acquire a Redis distributed lock keyed by `kg_lock:{document_id}` with a TTL equal to the task's `soft_time_limit`
3. IF the lock is already held, THEN the task SHALL log a WARNING and return immediately with status `skipped_duplicate`
4. WHEN the task completes (success or failure), THE lock SHALL be released
5. IF the task is killed (SIGKILL, OOM, etc.) without releasing the lock, THE lock SHALL expire automatically via the TTL
6. THE lock acquisition SHALL be atomic (using Redis `SET NX EX` or equivalent)
7. THE lock holder SHALL periodically extend the TTL if the task is still running and approaching the lock expiry (heartbeat renewal every `TTL / 3` seconds)
8. THE task deduplication SHALL be implemented as a reusable decorator or mixin that can be applied to any long-running Celery task

### Requirement 11: KG Concept Extraction Gemini Failover

**User Story:** As a developer, I want KG concept extraction to fall back to Gemini when Ollama fails, consistent with the bridge generation failover pattern, so that concept quality is maintained even when Ollama is overwhelmed.

#### Acceptance Criteria

1. WHEN `extract_concepts_ollama()` fails (timeout, error, or empty result), THE ConceptExtractor SHALL attempt concept extraction via Gemini using the same prompt
2. THE Gemini concept extraction SHALL use the same domain-aware prompt template as the Ollama extraction
3. THE Gemini concept extraction SHALL parse the response using the same `_extract_json_array()` and `_filter_by_rationale()` pipeline
4. IF Gemini also fails, THEN `extract_concepts_ollama()` SHALL return `[]` (existing behavior — NER and regex still provide concepts)
5. THE failover SHALL log at INFO level: "Ollama concept extraction failed, falling back to Gemini"
6. THE failover SHALL NOT change the existing `extract_all_concepts_async()` parallel execution of NER + Ollama/Gemini + regex
7. THE Gemini model for concept extraction SHALL be initialized lazily on first failover (same pattern as bridge generator's lazy Gemini init)
8. THE ConceptExtractor SHALL track provider statistics (ollama_success, gemini_fallback, both_failed) for observability
