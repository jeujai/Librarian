# Implementation Plan

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - Skipped Duplicate Results Cause Premature Finalization
  - **CRITICAL**: This test MUST FAIL on unfixed code - failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior - it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate the bug exists
  - **Scoped PBT Approach**: Scope the property to concrete failing cases where `parallel_results` contains at least one `skipped_duplicate` entry
  - **Bug Condition from design**: `isBugCondition(input)` returns true when `parallel_results` is a list AND any result has `status == 'skipped_duplicate'` AND `finalize_processing_task` is invoked with these results
  - Test Case 1: Call `finalize_processing_task` with `parallel_results = [{'status': 'skipped_duplicate', 'document_id': '...'}, {'status': 'completed', 'document_id': '...', 'kg_failures': {...}}]` — assert document is marked FAILED (not COMPLETED)
  - Test Case 2: Call `finalize_processing_task` with `parallel_results = [{'status': 'completed', 'document_id': '...', 'bridge_failures': {...}}, {'status': 'skipped_duplicate', 'document_id': '...'}]` — assert document is marked FAILED
  - Test Case 3: Call `finalize_processing_task` with two `skipped_duplicate` results — assert document is marked FAILED
  - Test Case 4: Call a `redis_task_lock`-decorated function when the lock is already held — assert it raises `celery.exceptions.Ignore()` instead of returning `{'status': 'skipped_duplicate'}`
  - **Expected Behavior (from design)**: Duplicate invocations must not produce chord-countable results; `finalize_processing_task` must reject `skipped_duplicate` entries and mark document as FAILED with descriptive error
  - Run test on UNFIXED code
  - **EXPECTED OUTCOME**: Test FAILS (this is correct - it proves the bug exists)
  - Document counterexamples found to understand root cause (e.g., `finalize_processing_task` logs warning but marks document COMPLETED with missing data; `redis_task_lock` returns a dict instead of raising `Ignore()`)
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Normal Chord Completion and Lock Behavior Unchanged
  - **IMPORTANT**: Follow observation-first methodology
  - **Observe on UNFIXED code first**, then write property-based tests capturing observed behavior
  - Observe: `finalize_processing_task` with two valid `completed` results (one containing `kg_failures`, one containing `bridge_failures`) finalizes the document normally on unfixed code
  - Observe: `finalize_processing_task` with an `aborted` result handles document deletion gracefully on unfixed code
  - Observe: `finalize_processing_task` with a `failed` bridge result and `completed` KG result handles bridge failure as non-fatal on unfixed code
  - Observe: `redis_task_lock` with no lock contention acquires lock, executes wrapped function, returns its result, and releases lock on unfixed code
  - Write property-based test: for all `parallel_results` where every entry has `status` in `{'completed', 'aborted', 'failed'}` and contains expected data keys (`kg_failures` or `bridge_failures`), `finalize_processing_task` produces the same behavior as the original function (from Preservation Requirements in design)
  - Write property-based test: for all task invocations where `redis_task_lock` successfully acquires the lock, the decorator executes the wrapped function and returns its result normally (from Preservation Requirements in design)
  - Verify tests pass on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (this confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 3. Fix chord premature finalization bug

  - [x] 3.1 Raise `Ignore()` in `redis_task_lock` instead of returning `skipped_duplicate`
    - In `src/multimodal_librarian/services/redis_task_lock.py`, add `from celery.exceptions import Ignore` at the top of the file
    - In the `wrapper` function inside `redis_task_lock`, replace `return {"status": "skipped_duplicate", "document_id": str(document_id)}` with `raise Ignore()`
    - Keep the `logger.warning(...)` call before raising so duplicate detection remains observable in logs
    - This prevents the Celery result backend from storing a chord-countable result for duplicate invocations
    - _Bug_Condition: isBugCondition(input) where any parallel task is redelivered and lock is already held_
    - _Expected_Behavior: Duplicate invocations raise Ignore(), chord does not count them toward completion_
    - _Preservation: When lock is acquired successfully, decorator executes wrapped function and returns result normally_
    - _Requirements: 1.1, 1.4, 2.1_

  - [x] 3.2 Add `_validate_parallel_results` helper in `celery_service.py` (defense-in-depth)
    - In `src/multimodal_librarian/services/celery_service.py`, add a `_validate_parallel_results(parallel_results)` function that returns `(is_valid: bool, error_message: str)`
    - Validation rules: `parallel_results` must be a list with at least 2 entries; no entry may have `status == 'skipped_duplicate'`; at least one entry must contain `kg_failures` key (from KG task); at least one entry must contain `bridge_failures` key (from bridge task); entries with `status: 'aborted'` are allowed
    - _Bug_Condition: isBugCondition(input) where parallel_results contains skipped_duplicate or missing expected data_
    - _Expected_Behavior: Returns (False, descriptive_error) for invalid results, (True, '') for valid results_
    - _Preservation: Valid results with completed/aborted/failed status and expected data keys pass validation_
    - _Requirements: 1.2, 1.3, 2.2, 2.3_

  - [x] 3.3 Call `_validate_parallel_results` early in `finalize_processing_task`
    - In `finalize_processing_task`, call `_validate_parallel_results(parallel_results)` before extracting `kg_failures` and `bridge_failures`
    - If validation fails (`is_valid` is False), mark the document as FAILED with the error message indicating incomplete parallel processing, and return early
    - Remove or replace the existing `skipped_duplicate` warning-only logging block with the new validation call
    - Preserve existing abort/failure handling — the validation allows `aborted` and `failed` results through so downstream handlers deal with those cases
    - _Bug_Condition: isBugCondition(input) where finalize receives skipped_duplicate or incomplete results_
    - _Expected_Behavior: Document marked FAILED with descriptive error, not COMPLETED with missing data_
    - _Preservation: Normal completion, abort handling, bridge failure handling, quality gate evaluation unchanged_
    - _Requirements: 1.2, 1.3, 2.2, 2.3, 3.1, 3.2, 3.3_

  - [x] 3.4 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - Skipped Duplicate Results Cause Premature Finalization
    - **IMPORTANT**: Re-run the SAME test from task 1 - do NOT write a new test
    - The test from task 1 encodes the expected behavior: `redis_task_lock` raises `Ignore()` for duplicates; `finalize_processing_task` marks document FAILED when `parallel_results` contains `skipped_duplicate` or missing data
    - Run bug condition exploration test from step 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms bug is fixed)
    - _Requirements: 2.1, 2.2, 2.3_

  - [x] 3.5 Verify preservation tests still pass
    - **Property 2: Preservation** - Normal Chord Completion and Lock Behavior Unchanged
    - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
    - Run preservation property tests from step 2
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions)
    - Confirm all tests still pass after fix (no regressions)

- [x] 4. Checkpoint - Ensure all tests pass
  - Run the full test suite to ensure no regressions
  - Verify bug condition exploration test passes (Property 1)
  - Verify preservation property tests pass (Property 2)
  - Ensure all existing tests in the repository still pass
  - Ask the user if questions arise
