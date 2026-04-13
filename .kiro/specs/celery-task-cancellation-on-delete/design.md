# Celery Task Cancellation on Delete — Bugfix Design

## Overview

When a user deletes a document that is actively being processed by Celery, the background task is not reliably cancelled. Four interacting defects allow the task to escape cancellation: a race window where `task_id` is still `NULL`, a bare `try/except: pass` that swallows revocation failures, `ON DELETE CASCADE` destroying the `processing_jobs` row (and its `task_id`) before retry is possible, and no post-revoke verification that the task actually stopped.

The fix reorders the deletion flow so that cancellation is confirmed *before* the CASCADE delete runs, leverages the existing `_check_document_deleted()` / `_is_document_deleted()` mechanism as a fallback for the race-condition case, and replaces the silent `except: pass` with proper error handling.

## Glossary

- **Bug_Condition (C)**: A document deletion is requested while a Celery processing task is active (pending or running) for that document.
- **Property (P)**: The Celery task must be terminated (or guaranteed to self-terminate) before the document's data stores are cleaned up.
- **Preservation**: All existing deletion behaviour for documents without active tasks, completed tasks, conversation documents, and non-keyboard interactions must remain unchanged.
- **`cancel_job()`**: Method on `CeleryService` in `celery_service.py` that revokes a Celery task by its `task_id`.
- **`delete_document_completely()`**: Method on `DocumentManager` in `document_manager.py` that orchestrates multi-store cleanup (Milvus, Neo4j, MinIO, PostgreSQL).
- **`_check_document_deleted()`**: Synchronous helper in `celery_service.py` called by each pipeline stage; raises `DocumentDeletedError` if the `knowledge_sources` row is gone.
- **`processing_jobs`**: PostgreSQL table with `ON DELETE CASCADE` from `knowledge_sources`, storing `task_id` and job status.
- **Race window**: The interval between `_create_processing_job()` (task_id = NULL) and `_update_job_task_id()` where `cancel_job()` cannot revoke because there is no task_id to revoke.

## Bug Details

### Bug Condition

The bug manifests when a user deletes a document that has an active Celery processing pipeline. Four sub-conditions combine to let the task escape cancellation:

1. `task_id` is `NULL` in `processing_jobs` when `cancel_job()` runs (race window).
2. `cancel_processing()` raises an exception but `delete_document_completely()` swallows it.
3. The `knowledge_sources` row is deleted, CASCADE-deleting `processing_jobs` and destroying the `task_id` before a retry can use it.
4. Even when `revoke(terminate=True)` is called, no verification confirms the task stopped.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type DeleteDocumentRequest
  OUTPUT: boolean

  job := getProcessingJob(input.document_id)

  RETURN job IS NOT NULL
         AND job.status IN ['pending', 'running']
         AND (
              job.task_id IS NULL                          -- race window
              OR revokeWouldFail(job.task_id)              -- broker unreachable / swallowed error
              OR cascadeDeletesJobBeforeRetry(input)       -- task_id lost
              OR NOT taskActuallyStopped(job.task_id)      -- no verification
         )
END FUNCTION
```

### Examples

- **Race window**: User clicks delete 200 ms after upload. `processing_jobs.task_id` is still `NULL`. `cancel_job()` skips `revoke()`, returns `True`, and the task starts executing moments later on the worker.
- **Swallowed error**: Redis broker is temporarily unreachable. `celery_app.control.revoke()` raises `redis.ConnectionError`. The `except: pass` in `delete_document_completely()` swallows it. The document row is deleted, but the task keeps running and eventually fails with confusing errors when it tries to read the deleted document.
- **CASCADE destroys evidence**: `cancel_job()` succeeds in calling `revoke()`, but the task ignores SIGTERM. The `knowledge_sources` row is deleted, CASCADE-deleting `processing_jobs`. There is no `task_id` left to retry revocation.
- **No verification**: `revoke(terminate=True)` is called. The worker receives SIGTERM but the task catches it (or is between stages). The task continues processing a deleted document, writing orphaned data to Milvus/Neo4j.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Deleting a document with no active processing job must continue to clean up all stores (Milvus, Neo4j, MinIO, PostgreSQL) successfully.
- Deleting a document whose Celery task has already completed must succeed without errors; the completed task is a no-op for cancellation.
- When `revoke()` succeeds on the first attempt, the full deletion flow (Milvus → Neo4j → MinIO → PostgreSQL) must complete as it does today.
- `_check_document_deleted()` must continue to allow running tasks to proceed normally when the document still exists.
- Deleting a conversation document must continue to archive the thread and CASCADE-delete as it does today.

**Scope:**
All deletions where the bug condition does NOT hold (no active task, or task already completed/failed) should be completely unaffected by this fix. This includes:
- Documents that were never processed
- Documents whose processing completed or failed before deletion
- Conversation documents (source_type = 'CONVERSATION')
- Any non-deletion operations on documents

## Hypothesized Root Cause

Based on the code analysis, the root causes are confirmed (not merely hypothesized):

1. **Race window on `task_id`**: In `queue_document_processing()`, `_create_processing_job()` inserts a row with `task_id = NULL`, then `process_document_task.delay()` is called, and only *after* the task is dispatched does `_update_job_task_id()` write the task ID. If `cancel_job()` runs during this window, `job_status.get('task_id')` is `None` and the `if` guard skips `revoke()` entirely — but still marks the job as "failed" and returns `True`, giving the caller a false sense of success.

2. **Swallowed exception in `delete_document_completely()`**: Lines in `document_manager.py` wrap `cancel_processing()` in `try/except Exception: pass`. Any failure — broker down, timeout, DB error — is silently discarded. The deletion proceeds, and the orphaned task has no record of the failed cancellation.

3. **CASCADE deletes `processing_jobs`**: The `processing_jobs` table has `REFERENCES knowledge_sources(id) ON DELETE CASCADE`. When `upload_service.delete_document()` deletes the `knowledge_sources` row, the `processing_jobs` row (with its `task_id`) is destroyed. If a retry of `revoke()` were attempted after this point, there would be no `task_id` to revoke.

4. **No post-revoke verification**: `cancel_job()` calls `celery_app.control.revoke(task_id, terminate=True)` and immediately considers the job cancelled. It never checks `AsyncResult(task_id).status` to confirm the task reached a terminal state. Meanwhile, the existing `_check_document_deleted()` mechanism in each pipeline stage *would* catch the deletion — but only if the `knowledge_sources` row is deleted first, which currently happens *after* the (possibly failed) cancellation attempt.

## Correctness Properties

Property 1: Bug Condition — Active task is cancelled before data cleanup

_For any_ document deletion where an active Celery processing job exists (isBugCondition returns true), the fixed `delete_document_completely()` SHALL ensure the task is either revoked and confirmed stopped, or guaranteed to self-terminate via `_check_document_deleted()`, BEFORE proceeding with multi-store data cleanup.

**Validates: Requirements 2.1, 2.2, 2.3, 2.4**

Property 2: Preservation — Non-active-task deletions unchanged

_For any_ document deletion where no active Celery processing job exists (isBugCondition returns false — no job, completed job, failed job, or conversation document), the fixed code SHALL produce exactly the same deletion results as the original code, preserving all existing cleanup behaviour for Milvus, Neo4j, MinIO, and PostgreSQL.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**


## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `src/multimodal_librarian/services/celery_service.py`

**Function**: `cancel_job()`

**Specific Changes**:

1. **Handle NULL `task_id` (race window)**: When `task_id` is `None` but the job status is `pending` or `running`, poll for the `task_id` with a short timeout (e.g., 3 retries, 1 s apart). If the `task_id` never appears, rely on the `_check_document_deleted()` fallback — the task will self-terminate at its next stage checkpoint once the `knowledge_sources` row is gone.

2. **Propagate revocation errors**: Remove the bare `return False` in the `except` block. Instead, raise a new `CancellationError` (or re-raise) so the caller knows cancellation failed. Log the error with full context.

3. **Add post-revoke verification**: After calling `revoke(terminate=True)`, poll `AsyncResult(task_id).status` for up to N seconds. If the task does not reach a terminal state (`REVOKED`, `FAILURE`, `SUCCESS`), log a warning but still proceed — the `_check_document_deleted()` fallback will catch it.

---

**File**: `src/multimodal_librarian/components/document_manager/document_manager.py`

**Function**: `delete_document_completely()`

**Specific Changes**:

4. **Replace `except: pass` with proper error handling**: Catch the exception from `cancel_processing()`, log it as a warning, and append it to `results['errors']`. Do NOT silently discard it. If cancellation fails and the task has a `task_id`, record the `task_id` in the results so it can be retried or monitored.

5. **Reorder: revoke BEFORE CASCADE delete**: Move the `cancel_processing()` call (and its verification) to happen *before* `upload_service.delete_document()` (which triggers the CASCADE). This ensures the `processing_jobs` row (with `task_id`) is still available during cancellation. The existing `_check_document_deleted()` calls in each pipeline stage will serve as the safety net — once the `knowledge_sources` row is deleted, any running task will self-terminate at its next checkpoint.

---

**File**: `src/multimodal_librarian/services/celery_service.py`

**Function**: `_check_document_deleted()` (existing — no changes needed)

6. **Leverage existing mechanism**: The current `_check_document_deleted()` is already called at the start of `extract_pdf_content_task`, `generate_chunks_task`, `generate_bridges_task`, `update_knowledge_graph_task`, and `finalize_processing_task`. Once the `knowledge_sources` row is deleted (after the CASCADE), any in-flight task will raise `DocumentDeletedError` at its next checkpoint and abort cleanly. This is the safety net for the race-window case where `task_id` was `NULL` and `revoke()` could not be called.

---

**File**: `src/multimodal_librarian/database/init_db.sql`

**No schema changes required.** The `ON DELETE CASCADE` on `processing_jobs` is correct behaviour — we just need to ensure revocation happens *before* the CASCADE fires, not after.

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Write unit tests that mock the database and Celery interactions to reproduce each of the four sub-conditions. Run these tests on the UNFIXED code to observe failures.

**Test Cases**:
1. **Race window test**: Mock `get_job_status()` to return `task_id=None` with `status='pending'`. Call `cancel_job()`. Assert that `revoke()` was NOT called (will pass on unfixed code, demonstrating the bug — the task escapes cancellation).
2. **Swallowed error test**: Mock `cancel_processing()` to raise `ConnectionError`. Call `delete_document_completely()`. Assert that the error is in `results['errors']` (will fail on unfixed code — error is swallowed).
3. **CASCADE ordering test**: Instrument the call order of `cancel_processing()` and `upload_service.delete_document()`. Assert cancellation happens first (may fail on unfixed code depending on timing).
4. **No verification test**: Mock `revoke()` to succeed but `AsyncResult.status` to return `STARTED` (task still running). Call `cancel_job()`. Assert that the system detects the task is still running (will fail on unfixed code — no verification exists).

**Expected Counterexamples**:
- `cancel_job()` returns `True` even though `task_id` was `None` and no revocation occurred
- `delete_document_completely()` returns `success=True` even though `cancel_processing()` raised an exception
- Possible causes: missing `task_id` polling, bare `except: pass`, no post-revoke state check

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  result := delete_document_completely_fixed(input.document_id)
  ASSERT taskIsTerminatedOrWillSelfTerminate(input.document_id)
  ASSERT result.errors contains cancellation info IF revoke failed
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT delete_document_completely_original(input) = delete_document_completely_fixed(input)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many document states (no job, completed job, failed job, conversation doc) automatically
- It catches edge cases like partially-written job records or unusual status combinations
- It provides strong guarantees that non-buggy deletion paths are unchanged

**Test Plan**: Observe behavior on UNFIXED code first for documents without active tasks, then write property-based tests capturing that behavior.

**Test Cases**:
1. **No-job preservation**: Delete a document with no `processing_jobs` row. Verify all stores are cleaned up identically to unfixed code.
2. **Completed-job preservation**: Delete a document whose job has `status='completed'`. Verify deletion succeeds without attempting revocation.
3. **Conversation-doc preservation**: Delete a conversation document. Verify the thread archival and CASCADE behavior is unchanged.
4. **_check_document_deleted preservation**: Call `_check_document_deleted()` for a document that still exists. Verify it does NOT raise `DocumentDeletedError`.

### Unit Tests

- Test `cancel_job()` with `task_id=None` and `status='pending'` — verify polling or fallback behaviour
- Test `cancel_job()` with valid `task_id` — verify `revoke()` is called and post-revoke state is checked
- Test `cancel_job()` when `revoke()` raises — verify exception propagates (not swallowed)
- Test `delete_document_completely()` when `cancel_processing()` raises — verify error is logged and recorded
- Test ordering: `cancel_processing()` is called before `upload_service.delete_document()`

### Property-Based Tests

- Generate random document states (no job, pending job with NULL task_id, running job with task_id, completed job, failed job) and verify `cancel_job()` handles each correctly
- Generate random deletion scenarios for non-active-task documents and verify `delete_document_completely()` produces identical results to the original
- Generate random exception types from `cancel_processing()` and verify none are silently swallowed

### Integration Tests

- Test full deletion flow with a mocked Celery worker: queue a task, delete the document, verify the task is revoked and all stores are cleaned up
- Test the `_check_document_deleted()` safety net: queue a task with NULL `task_id`, delete the document, verify the task self-terminates at its next checkpoint
- Test deletion of a document mid-pipeline (e.g., during `generate_bridges_task`) and verify clean abort via `DocumentDeletedError`
