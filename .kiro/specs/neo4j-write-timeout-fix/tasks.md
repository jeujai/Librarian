# Implementation Plan

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - Write Operations Fail Without Retry on TransientError
  - **CRITICAL**: This test MUST FAIL on unfixed code - failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior - it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate the bug exists across all five bug conditions
  - **Scoped PBT Approach**: Use Hypothesis to generate TransientError failure patterns and verify retry behavior
  - Test 1a: Mock `session.execute_write` to raise `TransientError` once then succeed → assert `_run_write_session` retries and returns result (from Bug Condition: `transient_failure` — no retry loop exists in `_run_write_session`)
  - Test 1b: Assert `_CONCEPT_REL_SUB_BATCH` evaluates to ≤ 100 for `_scale_factor=1` (from Bug Condition: `batch_too_large` — default is `max(50, 500 // 1) = 500`)
  - Test 1c: Mock `execute_query` to fail once on a MERGE call in `_update_knowledge_graph` → assert the batch is retried before logging warning (from Bug Condition: `silent_data_loss` — no retry exists)
  - Test 1d: Verify `create_same_as_edges()` calls `_fetch_concept_names()` which fetches ALL concepts, not document-scoped (from Bug Condition: `full_scan_bridge`)
  - Test 1e: Verify `execute_write_query` has no `asyncio.wait_for` timeout enforcement (from Bug Condition: `no_client_timeout`)
  - Run tests on UNFIXED code
  - **EXPECTED OUTCOME**: Tests FAIL (this is correct - it proves the bug exists)
  - Document counterexamples found:
    - `_run_write_session` raises `TransientError` to caller without retry
    - `_CONCEPT_REL_SUB_BATCH` evaluates to 500 for documents under 1000 chunks
    - Failed MERGE batches log warning and continue with zero retry attempts
    - `_fetch_concept_names` returns all concepts in graph, not document-scoped
    - `execute_write_query` has no client-side timeout wrapper
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Read Path and Successful Write Behavior Unchanged
  - **IMPORTANT**: Follow observation-first methodology
  - Observe: `_run_query_session` retries `TransientError` up to 3 times with exponential backoff (0.2s, 0.4s, 0.8s) on unfixed code
  - Observe: `_run_write_session` returns results immediately when `session.execute_write` succeeds on first attempt on unfixed code
  - Observe: `_execute_write_with_reconnect` reconnects and retries on TCP transport closed errors on unfixed code
  - Observe: `_update_knowledge_graph` skips UMLS bridging when `umls_linker is None` on unfixed code
  - Observe: `_update_knowledge_graph` aborts when `_is_document_deleted` returns True on unfixed code
  - Write property-based tests using Hypothesis:
    - Test 2a: For all read queries that raise `TransientError` on attempt N (N ∈ {1,2}), `_run_query_session` retries and succeeds — verify retry count and backoff timing match unfixed code (from Preservation Requirements 3.1)
    - Test 2b: For all write queries that succeed on first attempt, `_run_write_session` returns identical results with no added delay (from Preservation Requirements 3.2)
    - Test 2c: For TCP transport closed errors during write, `_execute_write_with_reconnect` reconnects and retries exactly once (from Preservation Requirements 3.6)
    - Test 2d: When `umls_linker is None`, no UMLS bridging is attempted (from Preservation Requirements 3.5)
    - Test 2e: When document is deleted mid-processing, `_update_knowledge_graph` aborts gracefully (from Preservation Requirements 3.4)
  - Run tests on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (this confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

- [x] 3. Fix for Neo4j write timeout during document upload/processing

  - [x] 3.1 Add TransientError retry loop to `_run_write_session` in `neo4j_client.py`
    - Add `while retry_count < max_retries` loop (max_retries=3) around `session.execute_write(write_transaction)`
    - Catch `TransientError` and retry with exponential backoff (`0.1 * (2 ** retry_count)` seconds) — matching `_run_query_session` pattern
    - After exhausting retries, raise `QueryError` with retry count info
    - Non-transient errors must NOT be retried (re-raise immediately)
    - _Bug_Condition: isBugCondition(input) where input.raises_transient_error AND input.method == '_run_write_session'_
    - _Expected_Behavior: Retry up to 3 times with exponential backoff before raising QueryError_
    - _Preservation: Non-transient errors and successful first-attempt writes unchanged_
    - _Requirements: 2.1, 3.2_

  - [x] 3.2 Add configurable client-side write timeout to `execute_write_query` in `neo4j_client.py`
    - Add `write_timeout` parameter to `__init__` (default 300 seconds)
    - Wrap `_execute_write_with_reconnect` call in `asyncio.wait_for(..., timeout=self.write_timeout)` inside `execute_write_query`
    - Catch `asyncio.TimeoutError` and raise protocol's `TimeoutError` with timeout duration info
    - _Bug_Condition: isBugCondition(input) where input.method == 'execute_write_query' AND input.client_timeout == NONE_
    - _Expected_Behavior: Raise TimeoutError if write exceeds configured timeout (default 300s)_
    - _Preservation: Successful writes within timeout window return normally_
    - _Requirements: 2.5_

  - [x] 3.3 Reduce `_CONCEPT_REL_SUB_BATCH` default in `celery_service.py`
    - Change `_CONCEPT_REL_SUB_BATCH = max(50, 500 // _scale_factor)` to `_CONCEPT_REL_SUB_BATCH = max(25, 100 // _scale_factor)`
    - This caps the default at 100 rows (scale_factor=1) instead of 500
    - _Bug_Condition: isBugCondition(input) where input.batch_size > 100 AND estimated_execution_time > server_transaction_timeout_
    - _Expected_Behavior: All UNWIND MERGE sub-batches ≤ 100 rows_
    - _Preservation: Batch processing flow unchanged, just smaller sub-batches_
    - _Requirements: 2.2_

  - [x] 3.4 Add `_execute_with_retry` helper and wrap MERGE operations in `celery_service.py`
    - Create `async def _execute_with_retry(client, query, params, max_retries=3)` helper
    - Implements exponential backoff (1s, 2s, 4s) on any `Exception` for MERGE operations
    - After exhausting retries, log warning and continue (same as current behavior but with retry attempts)
    - Replace bare `try/except` blocks around Chunk MERGE, Concept MERGE (no emb), Concept MERGE (with emb), EXTRACTED_FROM MERGE, and relationship MERGE operations with calls to `_execute_with_retry`
    - _Bug_Condition: isBugCondition(input) where input.batch_merge_fails AND input.retry_count == 0_
    - _Expected_Behavior: Failed sub-batches retried up to 3 times before warning_
    - _Preservation: Successful MERGE operations return immediately, overall batch flow unchanged_
    - _Requirements: 2.3, 3.3_

  - [x] 3.5 Add `bridge_concepts` method to `UMLSBridger` and call from `celery_service.py`
    - Add `async def bridge_concepts(self, concept_names: List[str], batch_size: int = 500) -> BridgeResult` to `UMLSBridger`
    - Method accepts concept names from current document, skips `_fetch_concept_names()` full graph scan
    - Reuses `_match_concepts_batch` and `_merge_same_as_batch` internally
    - Keep `create_same_as_edges` for backward compatibility (full-graph bridging)
    - In `celery_service.py`, collect concept names from `concept_name_to_id` keys and pass to `bridge_concepts` instead of calling `create_same_as_edges()`
    - _Bug_Condition: isBugCondition(input) where input.is_umls_bridge AND input.scans_all_concepts == TRUE_
    - _Expected_Behavior: Only newly created concept names from current document are bridged_
    - _Preservation: `create_same_as_edges` still available for manual full-graph re-bridging_
    - _Requirements: 2.4_

  - [x] 3.6 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - Write Operations Retry on TransientError
    - **IMPORTANT**: Re-run the SAME test from task 1 - do NOT write a new test
    - The test from task 1 encodes the expected behavior
    - When this test passes, it confirms the expected behavior is satisfied
    - Run bug condition exploration test from step 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms bug is fixed)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [x] 3.7 Verify preservation tests still pass
    - **Property 2: Preservation** - Read Path and Successful Write Behavior Unchanged
    - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
    - Run preservation property tests from step 2
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions)
    - Confirm all tests still pass after fix (no regressions)

- [x] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.
