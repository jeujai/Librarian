# Chord Premature Finalize Bugfix Design

## Overview

The Celery chord that orchestrates parallel document processing (`generate_bridges_task` + `update_knowledge_graph_task`) fires its callback (`finalize_processing_task`) prematurely when a duplicate task invocation is detected by the `redis_task_lock` decorator. The decorator returns `{'status': 'skipped_duplicate'}`, which gets stored in the Celery result backend and counted as a valid chord completion. This causes `finalize_processing_task` to run before the real task finishes, resulting in documents being finalized with incomplete data.

The fix has two parts: (1) prevent `skipped_duplicate` from being counted by the chord by raising `celery.exceptions.Ignore()` instead of returning a result, and (2) add validation in `finalize_processing_task` as a safety net to reject incomplete parallel results.

## Glossary

- **Bug_Condition (C)**: A parallel task invocation is detected as a duplicate by `redis_task_lock` and returns `skipped_duplicate`, which the chord counts toward its completion threshold
- **Property (P)**: Duplicate invocations must not produce chord-countable results; `finalize_processing_task` must validate that all parallel results contain real completion data before proceeding
- **Preservation**: Normal chord completion, abort handling, bridge failure handling, and quality gate evaluation must remain unchanged when no duplicate redelivery occurs
- **`redis_task_lock`**: Decorator in `src/multimodal_librarian/services/redis_task_lock.py` that acquires a Redis distributed lock before task execution; returns `skipped_duplicate` if the lock is already held
- **`finalize_processing_task`**: Chord callback in `src/multimodal_librarian/services/celery_service.py` (line 969) that receives `parallel_results` from the chord and finalizes document processing
- **`generate_bridges_task`**: Parallel task (line 1518) decorated with `@redis_task_lock("bridge_lock:{document_id}")` that generates bridge chunks
- **`update_knowledge_graph_task`**: Parallel task (line 1967) decorated with `@redis_task_lock("kg_lock:{document_id}")` that extracts knowledge graph concepts
- **Chord**: Celery primitive that runs a group of tasks in parallel and fires a callback when all tasks complete; tracks completion via the result backend

## Bug Details

### Bug Condition

The bug manifests when a Celery visibility timeout causes redelivery of a parallel task (`generate_bridges_task` or `update_knowledge_graph_task`) while the original invocation is still running. The `redis_task_lock` decorator on the duplicate detects the lock is held and returns `{'status': 'skipped_duplicate'}`. This return value is stored in the Celery result backend, which the chord counts as a valid task completion. If the other parallel task has already completed, the chord fires `finalize_processing_task` immediately — before the original (real) invocation of the duplicated task finishes.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type ChordExecution
  OUTPUT: boolean

  RETURN input.parallel_results IS list
         AND ANY result IN input.parallel_results
             WHERE result.status == 'skipped_duplicate'
         AND finalize_processing_task IS invoked with these results
END FUNCTION
```

### Examples

- **Example 1**: `generate_bridges_task` is redelivered. The duplicate returns `{'status': 'skipped_duplicate', 'document_id': '...'}`. Meanwhile `update_knowledge_graph_task` completes normally. The chord sees 2/2 results and fires `finalize_processing_task` with `parallel_results = [{'status': 'skipped_duplicate', ...}, {'status': 'completed', 'kg_failures': {...}}]`. The finalize task logs a warning but proceeds, extracting no `bridge_failures` data (defaults to zeros) and marking the document COMPLETED.

- **Example 2**: `update_knowledge_graph_task` is redelivered. The duplicate returns `skipped_duplicate`. Bridges complete normally. The chord fires finalize with `parallel_results = [{'status': 'completed', 'bridge_failures': {...}}, {'status': 'skipped_duplicate', ...}]`. The finalize task extracts no `kg_failures` (defaults to `{total_chunks: 0}`). The quality gate's `kg_missing` check catches this, but only because of a recently added guard — the original bug path would have trivially passed.

- **Example 3**: Both parallel tasks are redelivered simultaneously. Both duplicates return `skipped_duplicate`. The chord fires finalize with two `skipped_duplicate` results. No real data is available for either KG or bridges.

- **Edge case**: A task completes very quickly, then is redelivered. The lock has already been released, so the duplicate acquires the lock and runs again. This is not the bug condition (the duplicate runs normally), but it shows the lock TTL/heartbeat interaction.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- When both parallel tasks complete successfully with real results and no duplicate invocations, the chord fires `finalize_processing_task` normally and the document is finalized
- When a parallel task returns `status: 'aborted'` because the document was deleted, `finalize_processing_task` handles the abort gracefully
- When bridge generation fails with an exception but KG completes, the bridge failure is handled as non-fatal per existing error handling
- When no duplicate redelivery occurs, `redis_task_lock` acquires the lock, the task executes, and the lock is released without affecting chord behavior
- When the quality gate evaluates genuine non-zero `kg_failures` and `bridge_failures`, it computes the composite rate and applies thresholds correctly

**Scope:**
All inputs where no `skipped_duplicate` result is produced should be completely unaffected by this fix. This includes:
- Normal single-invocation task execution
- Tasks that fail with exceptions (chord error handling)
- Tasks that return `aborted` status
- Quality gate evaluation with real failure data

## Hypothesized Root Cause

Based on the bug description and code analysis, the root causes are:

1. **`redis_task_lock` returns a result instead of suppressing it**: The decorator returns `{'status': 'skipped_duplicate'}` as a normal return value (line ~170 of `redis_task_lock.py`). Celery stores this in the result backend, and the chord counts it as a completed task. The fix is to raise `celery.exceptions.Ignore()` instead, which tells Celery to discard the task without storing a result or acknowledging it to the chord.

2. **`finalize_processing_task` lacks result validation**: The callback (line 969 of `celery_service.py`) logs a warning when it sees `skipped_duplicate` but continues processing. It should validate that every parallel result contains real completion data (`status` in `{'completed', 'aborted', 'failed'}` with expected keys like `kg_failures` or `bridge_failures`) before proceeding.

3. **Default `kg_failures` masks missing data**: When `finalize_processing_task` doesn't find `kg_failures` in the parallel results, it defaults to `{'ner_failures': 0, 'llm_failures': 0, 'total_chunks': 0}`. While the quality gate now has a `kg_missing` guard for `total_chunks == 0`, the finalize task should catch this earlier and fail explicitly rather than relying on the quality gate as the sole safety net.

## Correctness Properties

Property 1: Bug Condition - Duplicate Invocations Do Not Count Toward Chord

_For any_ task invocation where `redis_task_lock` detects the lock is already held, the decorator SHALL raise `celery.exceptions.Ignore()`, preventing the result backend from storing a chord-countable result. The chord waits for the original invocation to complete.

**Validates: Requirements 2.1, 1.1, 1.4**

Property 2: Bug Condition - Finalize Rejects Incomplete Results (Defense-in-Depth)

_For any_ invocation of `finalize_processing_task` where `parallel_results` contains a `skipped_duplicate` entry or is missing expected data (`kg_failures` or `bridge_failures`), the function SHALL mark the document as FAILED and SHALL NOT mark it as COMPLETED.

**Validates: Requirements 2.2, 2.3, 1.2, 1.3**

Property 3: Preservation - Normal Chord Completion Unchanged

_For any_ invocation of `finalize_processing_task` where all parallel results have `status` in `{'completed', 'aborted', 'failed'}` and contain the expected data keys, the function SHALL produce the same behavior as the original function, preserving normal finalization, quality gate evaluation, and document status updates.

**Validates: Requirements 3.1, 3.2, 3.3, 3.5**

Property 4: Preservation - Lock Acquisition Unchanged

_For any_ task invocation where `redis_task_lock` successfully acquires the lock (no duplicate), the decorator SHALL execute the wrapped function and return its result normally, preserving existing chord behavior.

**Validates: Requirements 3.4**

## Fix Implementation

### Changes Required

**Primary fix**: Raise `Ignore()` in `redis_task_lock` so the chord
never counts a duplicate as a completion.  If the original worker dies,
the lock TTL expires (10 min), Celery redelivers, the new invocation
acquires the lock and runs normally.  A temporary hang with eventual
recovery is strictly better than silent data corruption.

**Secondary guard**: Validate `parallel_results` in
`finalize_processing_task` as defense-in-depth — reject
`skipped_duplicate` entries and missing data even if `Ignore()` is
somehow bypassed.

---

**File**: `src/multimodal_librarian/services/redis_task_lock.py`

**Function**: `redis_task_lock` decorator wrapper

**Specific Changes**:
1. **Raise `Ignore()` instead of returning `skipped_duplicate`**: When
   the lock cannot be acquired, raise `celery.exceptions.Ignore()`
   instead of returning a result dict.  This tells Celery to discard
   the task without storing a result in the backend, so the chord does
   not count it as a completion.
   - Import `from celery.exceptions import Ignore` at the top
   - Replace `return {"status": "skipped_duplicate", ...}` with
     `raise Ignore()`
   - Keep the warning log before raising so duplicate detection is
     still observable in logs

---

**File**: `src/multimodal_librarian/services/celery_service.py`

**Function**: `finalize_processing_task`

**Specific Changes**:
2. **Add `_validate_parallel_results` helper** (defense-in-depth):
   Create a function that inspects `parallel_results` and returns
   `(is_valid, error_message)`.  Validation rules:
   - `parallel_results` must be a list with at least 2 entries
   - No entry may have `status == 'skipped_duplicate'`
   - At least one entry must contain `kg_failures` (from KG task)
   - At least one entry must contain `bridge_failures` (from bridge
     task)
   - Entries with `status: 'aborted'` are allowed (document deleted)

3. **Call validation early in finalize**: Before extracting
   `kg_failures` and `bridge_failures`, call
   `_validate_parallel_results`.  If invalid, mark the document as
   FAILED with a descriptive error and return early.

4. **Preserve existing abort/failure handling**: The validation allows
   `aborted` and `failed` results through — existing downstream
   handlers deal with those cases.

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Write tests that simulate the `redis_task_lock` decorator returning `skipped_duplicate` and verify that `finalize_processing_task` incorrectly proceeds with incomplete data. Run these tests on the UNFIXED code to observe the bug.

**Test Cases**:
1. **Duplicate Bridge Task Test**: Call `finalize_processing_task` with `parallel_results = [{'status': 'skipped_duplicate', 'document_id': '...'}, {'status': 'completed', 'document_id': '...', 'kg_failures': {...}}]` — observe that the document is marked COMPLETED despite missing bridge data (will demonstrate bug on unfixed code)
2. **Duplicate KG Task Test**: Call `finalize_processing_task` with `parallel_results = [{'status': 'completed', 'document_id': '...', 'bridge_failures': {...}}, {'status': 'skipped_duplicate', 'document_id': '...'}]` — observe that the document proceeds with default zero `kg_failures` (will demonstrate bug on unfixed code)
3. **Both Tasks Duplicated Test**: Call `finalize_processing_task` with two `skipped_duplicate` results — observe that finalize proceeds with all-zero defaults (will demonstrate bug on unfixed code)
4. **Lock Decorator Return Test**: Call a `redis_task_lock`-decorated function when the lock is held — observe that it returns a dict instead of raising `Ignore()` (will demonstrate bug on unfixed code)

**Expected Counterexamples**:
- `finalize_processing_task` logs a warning but marks the document as COMPLETED with missing data
- The `redis_task_lock` decorator returns a result dict that Celery stores in the result backend
- Possible root cause confirmed: the decorator's return value is chord-countable

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  result := finalize_processing_task_fixed(input.parallel_results, input.document_id)
  ASSERT result.status == 'failed'
  ASSERT document_status == FAILED
  ASSERT error_message CONTAINS 'incomplete parallel processing'
END FOR

FOR ALL input WHERE lock_already_held(input) DO
  ASSERT redis_task_lock_fixed(input) RAISES Ignore
  ASSERT no_result_stored_in_backend(input.task_id)
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT finalize_processing_task_original(input) == finalize_processing_task_fixed(input)
END FOR

FOR ALL input WHERE lock_acquired_successfully(input) DO
  ASSERT redis_task_lock_original(input) == redis_task_lock_fixed(input)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many combinations of parallel result shapes to verify the validation logic doesn't reject valid results
- It catches edge cases in result validation that manual unit tests might miss
- It provides strong guarantees that normal processing flow is unchanged

**Test Plan**: Observe behavior on UNFIXED code first for normal parallel results, then write property-based tests capturing that behavior.

**Test Cases**:
1. **Normal Completion Preservation**: Verify that `finalize_processing_task` with two valid `completed` results (containing `kg_failures` and `bridge_failures`) produces the same outcome before and after the fix
2. **Abort Handling Preservation**: Verify that `finalize_processing_task` with an `aborted` result continues to handle document deletion gracefully
3. **Bridge Failure Preservation**: Verify that `finalize_processing_task` with a `failed` bridge result and `completed` KG result continues non-fatal bridge handling
4. **Lock Acquisition Preservation**: Verify that `redis_task_lock` with no contention executes the wrapped function and returns its result normally

### Unit Tests

- Test `redis_task_lock` raises `Ignore()` when lock is already held
- Test `redis_task_lock` executes normally when lock is acquired
- Test `_validate_parallel_results` rejects `skipped_duplicate` entries
- Test `_validate_parallel_results` rejects results missing `kg_failures`
- Test `_validate_parallel_results` accepts valid `completed` results
- Test `_validate_parallel_results` accepts `aborted` results
- Test `_validate_parallel_results` accepts `failed` bridge results with `completed` KG
- Test `finalize_processing_task` marks document FAILED when validation fails

### Property-Based Tests

- Generate random `parallel_results` lists with valid statuses and data keys, verify `_validate_parallel_results` accepts them all (preservation)
- Generate random `parallel_results` lists containing at least one `skipped_duplicate`, verify `_validate_parallel_results` rejects them all (fix checking)
- Generate random task inputs with lock contention, verify `redis_task_lock` always raises `Ignore()` (fix checking)
- Generate random task inputs without lock contention, verify `redis_task_lock` returns the wrapped function's result unchanged (preservation)

### Integration Tests

- Test full chord execution with mocked duplicate redelivery — verify `finalize_processing_task` is not called prematurely
- Test full chord execution with normal completion — verify document is finalized correctly
- Test that `Ignore()` from `redis_task_lock` does not increment the chord's completion counter in the result backend
