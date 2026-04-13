# Implementation Plan

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - Page Progress Exceeds Total Pages & Completion Race
  - **CRITICAL**: This test MUST FAIL on unfixed code — failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior — it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate both bugs exist in the current code
  - **Scoped PBT Approach**: Use Hypothesis to generate chunk lists with `page_number` values drawn from ranges that exceed `total_pages` (e.g., journal-style numbering 195–236 with total_pages=89)
  - **Bug 1 — Page Overflow**: Write a property-based test targeting `_store_embeddings_in_vector_db()` and `_store_chunks_in_database()` progress metadata computation
    - Generate chunks where `chunk.metadata.page_number > total_pages` (the bug condition: `isBugCondition(input)` where `input.current_page > input.total_pages`)
    - Mock `_update_job_status_sync` to capture the `metadata` dict passed to it
    - Assert that `meta['current_page'] <= meta['total_pages']` for all progress updates (expected behavior)
    - On UNFIXED code, this assertion will FAIL because `max_page` / `max_page_seen` is not clamped — confirming the bug
  - **Bug 2 — Completion Race**: Write a test targeting `finalize_processing_task()` completion flow
    - Mock both `_update_job_status_sync` and `notify_processing_completion_sync`
    - Assert that the function does NOT send a WebSocket `status_update` with `status='completed'` AND `progress=100.0` when a completion notification follows
    - On UNFIXED code, this assertion will FAIL because both messages are sent — confirming the race condition
  - Run test on UNFIXED code — expect FAILURE (this confirms the bugs exist)
  - Document counterexamples found (e.g., `meta['current_page']=236, meta['total_pages']=89`)
  - Test file: `tests/services/test_page_progress_bug.py`
  - _Requirements: 1.1, 1.2, 1.3_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Non-Buggy Progress Metadata & Data Storage Unchanged
  - **IMPORTANT**: Follow observation-first methodology — observe behavior on UNFIXED code first
  - **Observe on unfixed code**:
    - `_store_embeddings_in_vector_db()` with chunks where all `page_number <= total_pages` (e.g., pages 1–50 with total_pages=50) — observe that `meta['current_page']` equals the max page_number from chunks
    - `_store_chunks_in_database()` with same normal-range chunks — observe identical behavior
    - `_store_embeddings_in_vector_db()` with chunks missing `page_number` metadata — observe that `current_page` is NOT added to progress metadata
    - Non-page metadata fields (`chunks_stored_so_far`, `total_chunks`, `embeddings_stored_so_far`) — observe they are computed identically
    - Intermediate progress updates (0–99%) — observe they use correct stage text and progress percentages
  - **Write property-based tests capturing observed behavior** (from Preservation Requirements in design):
    - For all chunk lists where every `page_number <= total_pages` (non-bug-condition: `¬C(X)`), assert `meta['current_page']` equals `max(page_numbers)` — same as original code
    - For all chunk lists with missing page metadata, assert `current_page` key is absent from metadata — same as original code
    - For all chunk lists, assert `chunks_stored_so_far`, `total_chunks`, `embeddings_stored_so_far` values are identical to original computation
    - For all intermediate progress updates, assert progress percentage is within expected range (15–20% for chunks, 20–25% for embeddings)
  - Verify all preservation tests PASS on UNFIXED code (confirms baseline behavior to preserve)
  - Test file: `tests/services/test_page_progress_preservation.py`
  - _Requirements: 1.4, 1.5_

- [x] 3. Fix page progress display and completion race condition

  - [x] 3.1 Clamp `max_page` against `total_pages` in `_store_embeddings_in_vector_db()`
    - In `src/multimodal_librarian/services/celery_service.py`, function `_store_embeddings_in_vector_db()` (around line 2020)
    - After computing `max_page = max(max_page, int(pn))` in the progress update loop, add clamping: `if total_pages > 0: max_page = min(max_page, total_pages)`
    - Apply clamping BEFORE assigning `meta['current_page'] = max_page`
    - This ensures `current_page <= total_pages` in all WebSocket progress metadata
    - _Bug_Condition: isBugCondition(input) where input.current_page > input.total_pages due to PDF internal page numbering exceeding physical page count_
    - _Expected_Behavior: meta['current_page'] <= meta['total_pages'] for all progress updates_
    - _Preservation: Non-page metadata fields (embeddings_stored_so_far, total_chunks) unchanged; chunks where page_number <= total_pages produce identical current_page values_
    - _Requirements: 1.1, 1.4, 1.5_

  - [x] 3.2 Clamp `max_page_seen` against `total_pages` in `_store_chunks_in_database()`
    - In `src/multimodal_librarian/services/celery_service.py`, function `_store_chunks_in_database()` (around line 3949)
    - After computing `max_page_seen = max(max_page_seen, int(page_number))` in the per-chunk loop, clamp before use in progress metadata: `clamped_page = min(max_page_seen, total_pages) if total_pages > 0 else max_page_seen`
    - Use `clamped_page` instead of `max_page_seen` when assigning `meta['current_page']`
    - Do NOT modify `max_page_seen` itself — only clamp the value used in progress metadata (preserves internal tracking)
    - _Bug_Condition: isBugCondition(input) where input.current_page > input.total_pages due to PDF internal page numbering exceeding physical page count_
    - _Expected_Behavior: meta['current_page'] <= meta['total_pages'] for all progress updates_
    - _Preservation: Chunk storage in PostgreSQL (knowledge_chunks table) produces identical rows; non-page metadata fields (chunks_stored_so_far, total_chunks) unchanged_
    - _Requirements: 1.2, 1.4, 1.5_

  - [x] 3.3 Suppress 100% progress WebSocket update in `finalize_processing_task()`
    - In `src/multimodal_librarian/services/celery_service.py`, function `finalize_processing_task()` (around line 1207)
    - The current code calls `_update_job_status_sync(UUID(document_id), 'completed', 100.0, 'Processing completed successfully')` which sends BOTH a database update AND a WebSocket notification
    - Then it calls `notify_processing_completion_sync(...)` which sends a separate completion WebSocket message with summary data
    - Fix: Keep the `_update_job_status_sync` call for the database record (status='completed', progress=100.0 must be persisted) but suppress the WebSocket notification for this specific call
    - Approach: Add a `suppress_websocket=True` parameter to `_update_job_status_sync` for the completion call, OR change the 100% call to use `'running'` status with step `'Finalizing'` at 99% and let only `notify_processing_completion_sync()` transition to the final state
    - Alternative: If modifying `_update_job_status_sync` is too invasive, split the DB update and WebSocket notification — call the DB update directly and skip the WebSocket send for the completion status
    - _Bug_Condition: status_update with status='completed' AND progress=100.0 races with processing_complete WebSocket message_
    - _Expected_Behavior: Only one terminal WebSocket message (the completion notification with summary) is sent; database record still shows completed/100.0_
    - _Preservation: Database processing_jobs table still updated to completed/100.0; intermediate progress updates (0–99%) unchanged; error/failure notifications unchanged_
    - _Requirements: 1.3, 1.4, 1.5_

  - [x] 3.4 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - Page Progress Never Exceeds Total Pages & Deterministic Completion
    - **IMPORTANT**: Re-run the SAME test from task 1 — do NOT write a new test
    - The test from task 1 encodes the expected behavior (current_page <= total_pages, no dual completion messages)
    - When this test passes, it confirms the expected behavior is satisfied
    - Run bug condition exploration test from step 1: `pytest tests/services/test_page_progress_bug.py -v`
    - **EXPECTED OUTCOME**: Test PASSES (confirms bugs are fixed)
    - _Requirements: 1.1, 1.2, 1.3_

  - [x] 3.5 Verify preservation tests still pass
    - **Property 2: Preservation** - Non-Buggy Progress Metadata & Data Storage Unchanged
    - **IMPORTANT**: Re-run the SAME tests from task 2 — do NOT write new tests
    - Run preservation property tests from step 2: `pytest tests/services/test_page_progress_preservation.py -v`
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions)
    - Confirm all preservation tests still pass after fix — non-page metadata, normal-range page numbers, missing page metadata, and intermediate progress updates all behave identically
    - _Requirements: 1.4, 1.5_

- [x] 4. Checkpoint - Ensure all tests pass
  - Run full test suite: `pytest tests/services/test_page_progress_bug.py tests/services/test_page_progress_preservation.py -v`
  - Ensure all bug condition tests pass (confirming fixes work)
  - Ensure all preservation tests pass (confirming no regressions)
  - Verify no other test regressions: `pytest tests/ -v --timeout=60`
  - Ask the user if questions arise
