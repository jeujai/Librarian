# Neo4j Write Timeout During Document Upload/Processing — Bugfix Design

## Overview

During document upload/processing, the `_update_knowledge_graph` Celery task triggers Neo4j transaction timeouts on write operations. The fix addresses five interrelated issues: (1) missing retry logic in `_run_write_session`, (2) oversized UNWIND MERGE batches, (3) silent data loss on failed batches, (4) full-graph UMLS bridging scans, and (5) no client-side timeout enforcement on writes. The strategy is to bring write-path resilience to parity with the read path, reduce batch sizes to fit within transaction timeout windows, add per-batch retry in the Celery service, introduce incremental UMLS bridging, and add a configurable client-side timeout.

## Glossary

- **Bug_Condition (C)**: A write operation (UNWIND MERGE) is executed against Neo4j via `_run_write_session` and either (a) the transaction exceeds the server-side `dbms.transaction.timeout`, (b) a `TransientError` is raised, or (c) the batch is large enough to risk timeout
- **Property (P)**: Write operations that encounter transient failures are retried with exponential backoff; batch sizes are small enough to complete within timeout; failed batches are retried before data is lost; UMLS bridging only processes new concepts
- **Preservation**: Read-path retry logic, successful first-attempt writes, incremental chunk/concept processing, document deletion detection, UMLS-unavailable graceful skip, and TCP reconnect behavior must remain unchanged
- **`_run_write_session`**: Method in `neo4j_client.py` that executes write queries via `session.execute_write()` — currently has no retry logic for `TransientError`
- **`_run_query_session`**: Method in `neo4j_client.py` that executes read queries — already retries `TransientError` up to 3 times with exponential backoff
- **`_update_knowledge_graph`**: Async function in `celery_service.py` that extracts concepts/relationships from document chunks and persists them to Neo4j in batches
- **`_CONCEPT_REL_SUB_BATCH`**: Variable in `celery_service.py` controlling UNWIND MERGE batch size — currently `max(50, 500 // _scale_factor)`
- **`UMLSBridger.create_same_as_edges`**: Method in `umls_bridger.py` that fetches ALL Concept nodes and ALL UMLSConcept nodes for matching — O(N×M) full graph scan
- **`TransientError`**: Neo4j exception indicating a temporary failure (timeout, lock contention) that may succeed on retry

## Bug Details

### Bug Condition

The bug manifests when write operations to Neo4j time out during document upload/processing. The `_run_write_session` method has no retry logic for `TransientError`, large UNWIND MERGE batches exceed the server-side transaction timeout, failed batches silently lose data, and UMLS bridging performs a full graph scan that grows with dataset size.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type WriteOperation (query, parameters, batch_size, is_umls_bridge)
  OUTPUT: boolean

  // Condition 1: TransientError on write with no retry
  transient_failure := input.raises_transient_error
                       AND input.method == '_run_write_session'

  // Condition 2: Batch too large for transaction timeout
  batch_too_large := input.batch_size > 100
                     AND input.query CONTAINS 'UNWIND'
                     AND input.query CONTAINS 'MERGE'
                     AND estimated_execution_time(input) > server_transaction_timeout

  // Condition 3: Failed batch with no retry in celery service
  silent_data_loss := input.batch_merge_fails
                      AND input.retry_count == 0

  // Condition 4: Full graph scan UMLS bridging
  full_scan_bridge := input.is_umls_bridge
                      AND input.scans_all_concepts == TRUE

  // Condition 5: No client-side timeout on write
  no_client_timeout := input.method == 'execute_write_query'
                       AND input.client_timeout == NONE

  RETURN transient_failure
         OR batch_too_large
         OR silent_data_loss
         OR full_scan_bridge
         OR no_client_timeout
END FUNCTION
```

### Examples

- **TransientError on write**: `execute_write_query("UNWIND $rows AS row MERGE (c:Concept {concept_id: row.concept_id}) ...", {"rows": [500 items]})` raises `TransientError` due to lock contention → system fails immediately instead of retrying (unlike `execute_query` which retries 3x)
- **Batch timeout**: A 500-row UNWIND MERGE with embeddings takes 45s per row-check against indexed nodes → total 120s+ exceeds `dbms.transaction.timeout=120s` → `TransientError: transaction timeout`
- **Silent data loss**: Batch MERGE of 200 concepts fails with timeout → `except Exception as e: logger.warning(...)` → 200 concepts permanently lost, no retry
- **UMLS full scan**: After uploading document #50, `create_same_as_edges()` fetches 15,000 Concept nodes and 400,000 UMLSConcept nodes → matching takes 180s → timeout
- **No client timeout**: A write query hangs indefinitely waiting for Neo4j response → no `asyncio.wait_for` or similar mechanism to abort

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Read operations (`_run_query_session`) must continue to retry `TransientError` up to 3 times with exponential backoff
- Write operations that succeed on the first attempt must return results immediately without unnecessary delays
- `_update_knowledge_graph` must continue to extract concepts, generate embeddings, and persist them incrementally in batches
- Document deletion detection mid-processing must continue to abort KG processing gracefully
- When UMLS linker is not available, the system must continue to skip UMLS linking and bridging without errors
- TCP transport closed errors must continue to trigger reconnect-and-retry via `_execute_write_with_reconnect`

**Scope:**
All inputs that do NOT involve write-path transient failures, oversized batches, failed batch retries, UMLS bridging, or client-side timeout enforcement should be completely unaffected by this fix. This includes:
- All read queries via `execute_query`
- Successful write operations (no transient error)
- Embedding generation and model server interactions
- WebSocket progress updates
- Background enrichment task queuing

## Hypothesized Root Cause

Based on the bug description and code analysis, the root causes are:

1. **Missing Write Retry Logic**: `_run_write_session` (lines ~718-745 of `neo4j_client.py`) uses `session.execute_write(write_transaction)` with no retry loop for `TransientError`. In contrast, `_run_query_session` has a `while retry_count < max_retries` loop with exponential backoff. This asymmetry means any transient failure on writes (timeout, lock contention, leader election) is fatal.

2. **Oversized UNWIND MERGE Batches**: `_CONCEPT_REL_SUB_BATCH` defaults to `max(50, 500 // _scale_factor)`. For documents under 1000 chunks (`_scale_factor=1`), this means 500-row UNWIND MERGE operations. Each MERGE must check existing nodes/indexes, and with UMLS data loaded (400K+ UMLSConcept nodes), these checks are slow enough to exceed the 120s `dbms.transaction.timeout`.

3. **No Per-Batch Retry in Celery Service**: Every `execute_query` call in `_update_knowledge_graph` is wrapped in `try/except Exception as e: logger.warning(...)` with no retry. When a batch fails, its concepts/relationships are permanently lost.

4. **Full Graph Scan UMLS Bridging**: `UMLSBridger.create_same_as_edges()` calls `_fetch_concept_names()` which runs `MATCH (c:Concept) RETURN DISTINCT c.concept_name` — fetching ALL concepts in the graph, not just the ones from the current document. This O(N) fetch + O(N×M) matching grows with every document uploaded.

5. **No Client-Side Timeout**: `execute_write_query` has no `asyncio.wait_for` wrapper or similar mechanism. If Neo4j hangs (e.g., during GC pause or network partition), the Celery worker blocks indefinitely.

## Correctness Properties

Property 1: Bug Condition — Write Operations Retry on TransientError

_For any_ write operation that encounters a `TransientError` (including transaction timeout), the fixed `_run_write_session` SHALL retry up to 3 times with exponential backoff (0.2s, 0.4s, 0.8s), matching the retry behavior of `_run_query_session`, before raising a `QueryError`.

**Validates: Requirements 2.1**

Property 2: Bug Condition — Batch Sizes Within Timeout Window

_For any_ UNWIND MERGE batch constructed in `_update_knowledge_graph`, the sub-batch size SHALL be capped at 100 rows (down from 500) to ensure individual transactions complete within the server-side `dbms.transaction.timeout`.

**Validates: Requirements 2.2**

Property 3: Bug Condition — Failed Batches Are Retried

_For any_ batch MERGE operation that fails in `_update_knowledge_graph`, the system SHALL retry the failed sub-batch up to 3 times with exponential backoff before logging a warning and continuing, preventing permanent data loss from transient failures.

**Validates: Requirements 2.3**

Property 4: Bug Condition — Incremental UMLS Bridging

_For any_ document upload that triggers UMLS bridging, the system SHALL bridge only the newly created concept names from the current document (passed as a parameter), rather than scanning all Concept nodes in the graph.

**Validates: Requirements 2.4**

Property 5: Bug Condition — Client-Side Write Timeout

_For any_ write operation executed via `execute_write_query`, the system SHALL enforce a configurable client-side timeout (default 300s) using `asyncio.wait_for`, raising `TimeoutError` if the operation exceeds the limit.

**Validates: Requirements 2.5**

Property 6: Preservation — Read Path Unchanged

_For any_ read operation via `_run_query_session` / `execute_query`, the fixed code SHALL produce exactly the same retry behavior (3 retries, exponential backoff) and results as the original code.

**Validates: Requirements 3.1**

Property 7: Preservation — Successful Writes Unchanged

_For any_ write operation that succeeds on the first attempt (no `TransientError`), the fixed code SHALL return results immediately without additional delays or overhead beyond the new timeout wrapper.

**Validates: Requirements 3.2**


## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `src/multimodal_librarian/clients/neo4j_client.py`

**Function**: `_run_write_session`

**Specific Changes**:
1. **Add TransientError retry loop**: Wrap the `session.execute_write(write_transaction)` call in a `while retry_count < max_retries` loop identical to `_run_query_session`, catching `TransientError` and retrying with exponential backoff (`0.1 * (2 ** retry_count)` seconds). After exhausting retries, raise `QueryError`.

2. **Add client-side timeout to `execute_write_query`**: Add a `write_timeout` parameter to `__init__` (default 300s). In `execute_write_query`, wrap the `_execute_write_with_reconnect` call with `asyncio.wait_for(…, timeout=self.write_timeout)` and catch `asyncio.TimeoutError` to raise the protocol's `TimeoutError`.

---

**File**: `src/multimodal_librarian/services/celery_service.py`

**Function**: `_update_knowledge_graph`

**Specific Changes**:
3. **Reduce default sub-batch size**: Change `_CONCEPT_REL_SUB_BATCH = max(50, 500 // _scale_factor)` to `_CONCEPT_REL_SUB_BATCH = max(25, 100 // _scale_factor)`. This caps the default at 100 rows instead of 500.

4. **Add per-batch retry helper**: Create an `async def _execute_with_retry(client, query, params, max_retries=3)` helper that wraps each `execute_query` / `execute_write_query` call with retry logic and exponential backoff. Replace all bare `try/except` blocks around MERGE operations with calls to this helper.

5. **Pass concept names to incremental bridging**: After the batch loop, collect the concept names from `all_concept_ids` via `concept_name_to_id` and pass them to the new `bridge_concepts` method instead of calling `create_same_as_edges()`.

---

**File**: `src/multimodal_librarian/components/knowledge_graph/umls_bridger.py`

**Function**: `UMLSBridger` (new method)

**Specific Changes**:
6. **Add `bridge_concepts(concept_names)` method**: New method that accepts a list of concept names (from the current document) and performs matching + SAME_AS edge creation only for those names, skipping the `_fetch_concept_names()` full graph scan. Reuses `_match_concepts_batch` and `_merge_same_as_batch` internally.

7. **Keep `create_same_as_edges` for backward compatibility**: The existing method remains available for full-graph bridging (e.g., manual re-bridging), but the Celery service will call the new incremental method.

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Write tests that mock Neo4j's `session.execute_write` to raise `TransientError` and verify the current `_run_write_session` fails immediately. Write tests that measure batch sizes passed to `execute_query` in `_update_knowledge_graph`. Run these tests on the UNFIXED code to observe failures.

**Test Cases**:
1. **Write TransientError Test**: Mock `session.execute_write` to raise `TransientError` once then succeed → `_run_write_session` fails immediately (will fail on unfixed code because no retry exists)
2. **Large Batch Size Test**: Process 100 chunks and assert `_CONCEPT_REL_SUB_BATCH` ≤ 100 → fails on unfixed code (default is 500)
3. **Failed Batch No Retry Test**: Mock `execute_query` to fail once on a MERGE call → verify the batch is not retried (will fail on unfixed code)
4. **Full Graph Scan Bridge Test**: Call `create_same_as_edges()` and verify it fetches ALL concepts, not just document-specific ones (will fail on unfixed code)
5. **No Client Timeout Test**: Verify `execute_write_query` has no timeout enforcement (will fail on unfixed code)

**Expected Counterexamples**:
- `_run_write_session` raises `TransientError` to caller without retry
- `_CONCEPT_REL_SUB_BATCH` evaluates to 500 for documents under 1000 chunks
- Failed MERGE batches log warning and continue with zero retry attempts
- `_fetch_concept_names` returns all concepts in graph, not document-scoped

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  result := fixed_function(input)
  ASSERT expectedBehavior(result)
END FOR
```

Specifically:
- For TransientError inputs: assert retry count == 3 before failure
- For batch size inputs: assert all sub-batches ≤ 100 rows
- For failed batch inputs: assert retry attempts == 3 before warning
- For UMLS bridge inputs: assert only document concept names are processed
- For timeout inputs: assert `asyncio.TimeoutError` raised within configured timeout

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT original_function(input) = fixed_function(input)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many test cases automatically across the input domain
- It catches edge cases that manual unit tests might miss
- It provides strong guarantees that behavior is unchanged for all non-buggy inputs

**Test Plan**: Observe behavior on UNFIXED code first for successful writes, read queries, and non-UMLS paths, then write property-based tests capturing that behavior.

**Test Cases**:
1. **Read Query Preservation**: Verify `_run_query_session` retry behavior is identical before and after fix — same retry count, same backoff timing, same error types
2. **Successful Write Preservation**: Verify writes that succeed on first attempt return the same results with no added latency beyond timeout wrapper overhead
3. **Incremental Processing Preservation**: Verify chunk extraction, embedding generation, and batch persistence flow is unchanged for non-failing batches
4. **Document Deletion Detection Preservation**: Verify `_is_document_deleted` check still aborts processing mid-batch
5. **UMLS Unavailable Preservation**: Verify that when `umls_linker is None`, no bridging is attempted (same as before)
6. **TCP Reconnect Preservation**: Verify `_execute_write_with_reconnect` still handles closed transport errors correctly

### Unit Tests

- Test `_run_write_session` retries `TransientError` up to 3 times with correct backoff
- Test `_run_write_session` does not retry non-transient errors
- Test `execute_write_query` raises `TimeoutError` when client-side timeout is exceeded
- Test `_CONCEPT_REL_SUB_BATCH` evaluates to ≤ 100 for various document sizes
- Test `_execute_with_retry` helper retries failed MERGE operations correctly
- Test `UMLSBridger.bridge_concepts` only processes provided concept names
- Test `UMLSBridger.bridge_concepts` with empty list returns zero matches

### Property-Based Tests

- Generate random `TransientError` failure patterns (fail on attempt 1, 2, or 3) and verify `_run_write_session` retries correctly and succeeds when the final attempt works
- Generate random batch sizes and verify all sub-batches in `_update_knowledge_graph` are ≤ 100 rows
- Generate random successful write inputs and verify the fixed `_run_write_session` returns identical results to a direct `session.execute_write` call (preservation)
- Generate random concept name lists and verify `bridge_concepts` produces the same SAME_AS edges as `create_same_as_edges` filtered to those names

### Integration Tests

- Test full document upload flow with a Neo4j instance configured with `dbms.transaction.timeout=5s` to verify small batches complete within timeout
- Test that a document with 500+ concepts persists all concepts (no silent data loss) when Neo4j has intermittent transient failures
- Test incremental UMLS bridging produces correct SAME_AS edges for a newly uploaded document without re-bridging existing documents
- Test that the client-side timeout fires correctly when Neo4j is artificially delayed (e.g., via `CALL dbms.sleep(10)`)
