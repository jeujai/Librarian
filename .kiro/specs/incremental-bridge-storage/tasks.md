# Implementation Plan

## Overview
No the test 
This task list implements the incremental bridge storage bugfix following the exploratory bugfix workflow. The fix ensures bridges are stored incrementally as they are generated in batches, rather than waiting until all bridges are complete before attempting storage.

## Files to Modify

- `src/multimodal_librarian/services/celery_service.py` - Main task implementation
- `src/multimodal_librarian/components/chunking_framework/bridge_generator.py` - Add storage callback
- `src/multimodal_librarian/components/chunking_framework/framework.py` - Pass storage callback

---

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - Milvus Storage Failure After Full Bridge Generation
  - **IMPORTANT**: Write this property-based test BEFORE implementing the fix
  - **CRITICAL**: This test MUST FAIL on unfixed code - failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior - it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate the bug exists
  - **Scoped PBT Approach**: Scope the property to cases where:
    - `bridges_needed > 0` (document requires bridges)
    - `all_bridges_generated = true` (all bridges have been generated)
    - `milvus_storage_failed = true` (Milvus storage operation fails)
  - Test that when Milvus storage fails after generating N bridges (N > 0), the system should have stored some bridges incrementally before the failure
  - From Bug Condition in design: `isBugCondition(input)` returns true when `bridges_stored_before_failure = 0` despite bridges being generated
  - Expected behavior: `bridges_stored_before_failure > 0` for any failure after at least one batch completes
  - Run test on UNFIXED code - expect FAILURE (this confirms the bug exists)
  - Document counterexamples found (e.g., "100 bridges generated, Milvus timeout, 0 bridges stored")
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Non-Failure Behavior Unchanged
  - **IMPORTANT**: Follow observation-first methodology
  - **Observe on UNFIXED code**:
    - Documents with `bridge_needed: false` return early with `bridges_generated: 0`
    - Successful storage produces `{'status': 'completed'}` with accurate counts
    - Bridge generation failures (LLM errors) return `{'status': 'failed'}`
    - Document deletion during processing is detected and aborts gracefully
  - Write property-based tests capturing observed behavior patterns:
    - For all documents where `bridge_needed = false`: result equals `{'status': 'completed', 'bridges_generated': 0}`
    - For all successful storage operations: result status equals 'completed' AND bridges_generated equals bridges_stored
    - For all generation failures (not storage): result status equals 'failed' with error details
  - From Preservation Requirements in design: All inputs where `NOT isBugCondition(input)` should produce identical results
  - Verify tests pass on UNFIXED code
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

- [x] 3. Implement incremental bridge storage fix

  - [x] 3.1 Add storage callback parameter to `batch_generate_bridges` in `bridge_generator.py`
    - Add optional `storage_callback: Optional[Callable[[List[BridgeChunk]], Awaitable[None]]]` parameter
    - Invoke callback after each batch of bridges is generated and validated
    - Callback receives the batch of BridgeChunk objects for immediate storage
    - Maintain backward compatibility - callback is optional
    - _Bug_Condition: isBugCondition(input) where all bridges generated before any storage_
    - _Expected_Behavior: Storage callback invoked after each batch completes_
    - _Preservation: Existing callers without callback continue to work unchanged_
    - _Requirements: 2.1, 2.2_

  - [x] 3.2 Update `generate_bridges_for_document` in `framework.py` to pass storage callback
    - Accept and pass through the storage callback to `batch_generate_bridges()`
    - Add optional `storage_callback` parameter to method signature
    - _Requirements: 2.1, 2.2_

  - [x] 3.3 Implement incremental storage in `generate_bridges_task` in `celery_service.py`
    - Create async storage callback that stores each batch immediately:
      - Store batch in PostgreSQL via `_store_bridge_chunks_in_database()`
      - Store batch in Milvus via `_store_bridge_embeddings_in_vector_db()`
    - Track `bridges_stored` counter separately from `bridges_generated`
    - Pass storage callback to `generate_bridges_for_document()`
    - Update progress reporting to include both generated and stored counts
    - _Bug_Condition: isBugCondition(input) where bridges_stored_before_failure = 0_
    - _Expected_Behavior: bridges_stored_before_failure = (completed_batches * batch_size)_
    - _Preservation: Successful completions return same final result_
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [x] 3.4 Handle partial storage failures gracefully
    - When Milvus storage fails for a batch, log the error with batch details
    - Preserve count of successfully stored bridges before failure
    - Return partial success status with `bridges_stored` count
    - Allow task to continue or fail gracefully based on failure severity
    - _Bug_Condition: Storage failure loses all bridges_
    - _Expected_Behavior: Previously stored bridges preserved, only current batch lost_
    - _Requirements: 2.3, 2.4_

  - [x] 3.5 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - Incremental Storage on Failure
    - **IMPORTANT**: Re-run the SAME test from task 1 - do NOT write a new test
    - The test from task 1 encodes the expected behavior
    - When this test passes, it confirms the expected behavior is satisfied
    - Run bug condition exploration test from step 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms bug is fixed)
    - Verify that when Milvus fails after N batches, (N * batch_size) bridges are stored
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [x] 3.6 Verify preservation tests still pass
    - **Property 2: Preservation** - Non-Failure Behavior Unchanged
    - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
    - Run preservation property tests from step 2
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions)
    - Confirm all tests still pass after fix (no regressions)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

- [x] 4. Checkpoint - Ensure all tests pass
  - Run full test suite to verify no regressions
  - Verify bug condition test passes (incremental storage works)
  - Verify preservation tests pass (existing behavior unchanged)
  - Ensure all tests pass, ask the user if questions arise
