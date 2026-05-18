# Page Progress Display Bug — Bugfix Design

## Overview

Two display-only bugs affect the document processing progress UI. Bug 1: during embedding/chunk storage, the progress display shows `page 236/89` because `current_page` is derived from PDF internal page numbering (`chunk.metadata.page_number`) while `total_pages` comes from the physical page count (`fitz.Document.page_count`). Bug 2: at completion, the UI inconsistently shows either "100%" or the completion summary ("✓ Document ready for querying") depending on which WebSocket message — the `status_update` with `progress: 100.0` or the `processing_complete` notification — arrives and is rendered last.

The fix strategy is minimal and backend-focused: clamp `current_page` to never exceed `total_pages` in progress metadata, and suppress the 100% progress update when a dedicated completion message follows immediately.

## Glossary

- **Bug_Condition (C)**: The condition that triggers incorrect display — either `current_page > total_pages` in progress metadata (Bug 1), or a 100% progress update racing with a completion message (Bug 2)
- **Property (P)**: The desired display behavior — page progress always shows `current_page <= total_pages`, and completion always renders the summary state
- **Preservation**: Existing chunk/embedding storage logic, database writes, non-page progress metadata, and intermediate progress updates (0–99%) must remain unchanged
- **`_store_embeddings_in_vector_db()`**: Async function in `celery_service.py` that stores chunk embeddings in the vector database and reports page-level progress via WebSocket
- **`_store_chunks_in_database()`**: Async function in `celery_service.py` that stores chunks in PostgreSQL and reports page-level progress via WebSocket
- **`_update_job_status_sync()`**: Async function that writes job status to PostgreSQL and sends WebSocket notifications via `ProcessingStatusService`
- **`notify_processing_completion_sync()`**: Synchronous wrapper that sends a dedicated completion WebSocket message with document summary
- **`max_page` / `max_page_seen`**: Local variables tracking the highest `page_number` seen across processed chunks, used as `current_page` in progress metadata
- **`total_pages`**: Physical page count from `fitz.Document.page_count`, passed as a parameter to both storage functions

## Bug Details

### Bug Condition

The bugs manifest in two distinct scenarios:

**Bug 1 — Page Overflow**: During chunk/embedding storage, `max_page` is computed from `chunk.metadata.page_number` (PDF internal/logical page numbering, e.g., journal pages 195–236) while `total_pages` comes from `fitz.Document.page_count` (physical page count, e.g., 89). For journal articles, book excerpts, or any PDF where internal page labels don't start at 1, `max_page` can far exceed `total_pages`.

**Bug 2 — Completion Race**: At processing completion, the backend sends two sequential WebSocket messages: (1) `_update_job_status_sync(..., 'completed', 100.0, 'Processing completed successfully')` which triggers a progress update with `100%`, and (2) `notify_processing_completion_sync(...)` which sends a dedicated completion message with summary data. The UI renders whichever arrives last — if the progress update renders after the completion message, the user sees "100%" instead of the summary.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type ProgressMetadata
  OUTPUT: boolean

  // Bug 1: page overflow
  IF input.current_page IS NOT NULL
     AND input.total_pages IS NOT NULL
     AND input.current_page > input.total_pages
  THEN RETURN TRUE

  // Bug 2: completion race
  IF input.message_type == 'status_update'
     AND input.status == 'completed'
     AND input.progress == 100.0
     AND completion_message_will_follow(input.document_id)
  THEN RETURN TRUE

  RETURN FALSE
END FUNCTION
```

### Examples

- **Bug 1 — Journal article**: PDF has 89 physical pages but internal page numbers run 195–236. During embedding storage, progress shows `page 236/89`. Expected: `page 89/89` (clamped).
- **Bug 1 — Book excerpt**: PDF has 42 physical pages, internal numbering starts at page 301. Progress shows `page 342/42`. Expected: `page 42/42` (clamped).
- **Bug 1 — Normal PDF**: PDF has 50 physical pages, internal numbering is 1–50. Progress shows `page 37/50`. Expected: `page 37/50` (unchanged — no clamping needed).
- **Bug 2 — Race condition**: Backend sends `{status: 'completed', progress: 100.0}` then `{type: 'completion', summary: {...}}`. If progress update renders last, UI shows "100%" instead of "✓ 89 pages • 236 chunks • 42 concepts".

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Chunk storage in PostgreSQL (`knowledge_chunks` table) must produce identical rows — content, metadata, content_hash, chunk_index, etc.
- Embedding storage in the vector database must produce identical vectors and metadata
- Non-page progress metadata fields (`chunks_stored_so_far`, `total_chunks`, `embeddings_stored_so_far`) must remain unchanged
- Intermediate progress updates (0–99%) must continue to display correctly with accurate stage text
- The progress bar's monotonic behavior (never goes backwards) must be preserved
- WebSocket connection management and error handling must remain unchanged
- Database writes in `_update_job_status_sync()` must continue to update `processing_jobs` correctly
- The completion summary content (page_count, chunk_count, concept_count) must remain accurate

**Scope:**
All inputs that do NOT involve page progress metadata or the completion status transition should be completely unaffected by this fix. This includes:
- All chunk content processing and storage logic
- All embedding generation logic
- All bridge chunk generation and storage
- Progress updates that don't include `current_page` / `total_pages` metadata
- Error handling and failure status reporting
- Document deletion detection during processing

## Hypothesized Root Cause

Based on the code analysis, the root causes are confirmed:

1. **Bug 1 — Unclamped `max_page` in `_store_embeddings_in_vector_db()`** (line ~2020): The loop computes `max_page = max(max_page, int(pn))` from `chunk.metadata.page_number` and sets `meta['current_page'] = max_page` without comparing against `total_pages`. When PDF internal page numbers exceed the physical page count, `current_page > total_pages`.

2. **Bug 1 — Unclamped `max_page_seen` in `_store_chunks_in_database()`** (line ~3949): Same pattern — `max_page_seen = max(max_page_seen, int(page_number))` is used directly as `meta['current_page']` without clamping against `total_pages`.

3. **Bug 2 — Dual completion signals in `process_document_task()`** (lines 1207–1243): The task first calls `_update_job_status_sync(document_id, 'completed', 100.0, 'Processing completed successfully')` which sends a WebSocket progress update with status `completed` and progress `100.0`. Then it calls `notify_processing_completion_sync(...)` which sends a separate completion message with summary data. Both messages update the UI, and the final display depends on arrival order.

4. **Bug 2 — Frontend renders both messages**: In `chat-upload-handler.js`, `updateProcessingStatusCard()` sets progress text to `100%` on the status update, while `showCompletionState()` replaces the body with the summary. If the status update arrives after the completion message (or re-renders), the user sees "100%" instead of the summary.

## Correctness Properties

Property 1: Bug Condition — Page Progress Never Exceeds Total Pages

_For any_ progress metadata where both `current_page` and `total_pages` are present, the fixed functions SHALL ensure that `current_page <= total_pages`. Specifically, `max_page` (or `max_page_seen`) SHALL be clamped to `min(max_page, total_pages)` before being assigned to `meta['current_page']`.

**Validates: Requirements 1.1, 1.2**

Property 2: Bug Condition — Completion Displays Deterministic Final State

_For any_ document that completes processing successfully, the fixed code SHALL ensure the UI always renders the completion summary state (not "100%"). This is achieved by either suppressing the 100% progress WebSocket update or by ensuring the completion message always takes precedence.

**Validates: Requirements 1.3**

Property 3: Preservation — Non-Page Progress Metadata Unchanged

_For any_ progress update where the bug condition does NOT hold (i.e., `current_page <= total_pages` or page metadata is absent), the fixed functions SHALL produce identical progress metadata as the original functions, preserving all non-page fields and the progress percentage calculation.

**Validates: Requirements 1.4, 1.5**

Property 4: Preservation — Data Storage Integrity

_For any_ document processing run, the fixed functions SHALL store identical chunk data in PostgreSQL and identical embeddings in the vector database as the original functions. The fix is display-only and must not alter any persisted data.

**Validates: Requirements 1.5**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `src/multimodal_librarian/services/celery_service.py`

**Function**: `_store_embeddings_in_vector_db()` (line ~2020)

**Specific Changes**:
1. **Clamp `max_page` against `total_pages`**: After computing `max_page` from chunk metadata, add: `if total_pages > 0: max_page = min(max_page, total_pages)` before assigning to `meta['current_page']`.

**Function**: `_store_chunks_in_database()` (line ~3949)

**Specific Changes**:
2. **Clamp `max_page_seen` against `total_pages`**: Before assigning to `meta['current_page']`, add: `clamped_page = min(max_page_seen, total_pages) if total_pages > 0 else max_page_seen` and use `clamped_page` in the metadata.

**Function**: `process_document_task()` (line ~1207)

**Specific Changes**:
3. **Remove the 100% progress update before completion**: Remove or skip the `_update_job_status_sync(document_id, 'completed', 100.0, 'Processing completed successfully')` call. The completion notification via `notify_processing_completion_sync()` already signals completion to the UI. Alternatively, change the 100% update to use status `'running'` with step `'Finalizing'` (keeping progress at 95%) and let only the completion message transition to the final state.

4. **Alternative for Bug 2 (frontend-side)**: If the backend change is too risky, the frontend `updateProcessingStatusCard()` could skip rendering progress updates once a completion state has been shown. Add a guard: `if (card.classList.contains('status-completed')) return;`

5. **Preferred approach for Bug 2**: Keep the `_update_job_status_sync` call with `'completed'` status (needed for database record) but suppress the WebSocket notification for it. Pass a flag or remove the WebSocket call from that specific invocation, letting only `notify_processing_completion_sync()` send the WebSocket message.

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bugs on unfixed code, then verify the fixes work correctly and preserve existing behavior. Since these are display-only bugs, testing focuses on the metadata values produced by the storage functions and the WebSocket message sequencing.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bugs BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Write unit tests that call the progress metadata computation logic with chunk data containing page numbers that exceed the physical page count. Run these tests on the UNFIXED code to observe that `current_page > total_pages` in the output metadata.

**Test Cases**:
1. **Embedding Progress — Journal Article**: Create chunks with `page_number` values 195–236 and `total_pages=89`. Verify that the unfixed code produces `meta['current_page'] = 236` (will demonstrate bug on unfixed code).
2. **Chunk Storage Progress — Book Excerpt**: Create chunks with `page_number` starting at 301 and `total_pages=42`. Verify that the unfixed code produces `meta['current_page'] = 342` (will demonstrate bug on unfixed code).
3. **Completion Race**: Verify that `process_document_task()` sends both a 100% status update AND a completion notification (will demonstrate bug on unfixed code).
4. **Normal PDF — No Bug**: Create chunks with `page_number` values 1–50 and `total_pages=50`. Verify `current_page <= total_pages` (should pass on unfixed code — confirms bug is conditional).

**Expected Counterexamples**:
- `meta['current_page']` values exceeding `meta['total_pages']` when chunk page numbers use PDF internal numbering
- Two distinct WebSocket messages sent at completion: one with `progress: 100.0` and one with `type: 'completion'`

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed functions produce the expected behavior.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  result := computeProgressMetadata_fixed(input.chunks, input.total_pages)
  ASSERT result.current_page <= result.total_pages
END FOR
```

```
FOR ALL completion_input DO
  messages := captureWebSocketMessages_fixed(completion_input)
  ASSERT messages does NOT contain both a 100% progress update AND a completion message
         OR the frontend deterministically renders the completion summary
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed functions produce the same result as the original functions.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT computeProgressMetadata_original(input) = computeProgressMetadata_fixed(input)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many random chunk configurations with varying page numbers and total_pages values
- It catches edge cases like `page_number = 0`, `total_pages = 0`, missing page metadata, single-chunk documents
- It provides strong guarantees that the clamping logic doesn't alter behavior for normal PDFs

**Test Plan**: Observe behavior on UNFIXED code first for normal PDFs (where `page_number <= total_pages`), then write property-based tests capturing that behavior.

**Test Cases**:
1. **Normal Page Progress Preservation**: Generate random chunk lists where all `page_number` values are ≤ `total_pages`. Verify the fixed code produces identical `meta['current_page']` values as the original code.
2. **Missing Page Metadata Preservation**: Generate chunks without `page_number` in metadata. Verify `current_page` is not added to progress metadata (same as original).
3. **Non-Page Metadata Preservation**: Verify that `chunks_stored_so_far`, `total_chunks`, `embeddings_stored_so_far`, and progress percentage calculations are identical between original and fixed code.
4. **Intermediate Progress Preservation**: Verify that all progress updates between 0–99% produce identical WebSocket messages.

### Unit Tests

- Test `max_page` clamping logic in `_store_embeddings_in_vector_db()` with page numbers exceeding total_pages
- Test `max_page_seen` clamping logic in `_store_chunks_in_database()` with page numbers exceeding total_pages
- Test edge cases: `total_pages = 0`, `page_number = None`, single chunk, empty chunk list
- Test that the completion flow sends only one terminal WebSocket message (not both 100% and completion)
- Test that database status is still updated to `completed` with `progress: 100.0` (DB record must be correct)

### Property-Based Tests

- Generate random chunk lists with `page_number` values drawn from `[1, 1000]` and `total_pages` drawn from `[1, 500]`. Verify `current_page <= total_pages` always holds after fix.
- Generate random chunk lists where `page_number <= total_pages` for all chunks. Verify the fixed code produces identical metadata to the original code (preservation).
- Generate random `total_pages` values including 0 and verify no division-by-zero or unexpected behavior.

### Integration Tests

- Test full document processing flow with a PDF that has internal page numbers exceeding physical page count. Verify all WebSocket progress messages show `current_page <= total_pages`.
- Test completion flow end-to-end: verify the UI receives a deterministic final state after processing completes.
- Test that the processing_jobs table has correct final status (`completed`, `100.0`) regardless of the WebSocket fix.
