# Implementation Plan: Upload Telemetry Enhancements

## Overview

Incremental implementation of three changes to the existing Upload Throughput Report: renaming user-facing labels, adding server-side pagination with frontend controls, and auto-refreshing on upload completion events. Each task builds on the previous, ending with integration wiring and tests.

## Tasks

- [x] 1. Rename display labels and update RAG prompt
  - [x] 1.1 Update system commands list and report heading
    - In `src/multimodal_librarian/api/routers/chat.py`, change the system commands tuple from `("Upload Throughput Report", "Show me throughput for uploads")` to `("Upload Telemetry", "Show me upload telemetry")`
    - In `src/multimodal_librarian/services/status_report_service.py`, change the heading `**Upload Throughput**` to `**Upload Telemetry**` in `generate_throughput_report()`
    - Verify internal identifiers `THROUGHPUT_REPORT`, `_handle_throughput_report`, and `throughput_report` metadata key remain unchanged
    - _Requirements: 1.1, 1.2, 1.4_

  - [x] 1.2 Update RAG intent classification prompt
    - In `src/multimodal_librarian/services/rag_service.py`, replace `"show me throughput for uploads"`, `"processing throughput"`, `"processing performance"`, `"upload speed stats"` example phrases with `"upload telemetry"`, `"Show me upload telemetry"`, `"upload telemetry stats"` for the `THROUGHPUT_REPORT` intent
    - Keep the `THROUGHPUT_REPORT` keyword unchanged
    - _Requirements: 6.1, 6.2_

  - [ ]* 1.3 Write unit tests for rename changes
    - Test system commands list contains `("Upload Telemetry", "Show me upload telemetry")`
    - Test `generate_throughput_report` output starts with `**Upload Telemetry**`
    - Test internal identifiers are preserved (`THROUGHPUT_REPORT`, `_handle_throughput_report`, `throughput_report` metadata key)
    - Test RAG prompt contains "upload telemetry" and retains `THROUGHPUT_REPORT`
    - _Requirements: 1.1, 1.2, 1.4, 6.1, 6.2_

- [x] 2. Implement server-side pagination in StatusReportService
  - [x] 2.1 Add offset/limit parameters and COUNT query to generate_throughput_report
    - Update `generate_throughput_report()` signature to accept `offset: int = 0` and `limit: int = 10`
    - Change return type from `str` to `Tuple[str, int]`
    - Add a `SELECT COUNT(*)` query with the same WHERE clause (`pj.status = 'completed' AND pj.completed_at IS NOT NULL AND pj.started_at IS NOT NULL`)
    - Append `OFFSET {offset} LIMIT {limit}` to the existing data query
    - On error, return `("Throughput data is temporarily unavailable.", 0)`
    - When offset exceeds total rows, return heading + column headers with empty body and correct total_count
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [ ]* 2.2 Write property test: Paginated row count invariant (Property 1)
    - **Property 1: Paginated row count invariant**
    - Generate random lists of upload row dicts (0–200 items), random offset (0–250), random limit (1–100)
    - Assert count of data rows in markdown equals `min(limit, max(0, N - offset))`
    - **Validates: Requirements 2.2, 2.5**

  - [ ]* 2.3 Write property test: Total count independence (Property 2)
    - **Property 2: Total count is independent of pagination parameters**
    - Generate same inputs as P1
    - Assert `total_count` equals `len(rows)` regardless of offset/limit
    - **Validates: Requirements 2.3, 2.4**

- [x] 3. Update chat.py router for pagination
  - [x] 3.1 Update _handle_throughput_report to accept offset/limit and unpack tuple
    - Add `offset: int = 0` and `limit: int = 10` parameters to `_handle_throughput_report`
    - Unpack `text, total_count = await svc.generate_throughput_report(offset=offset, limit=limit)`
    - Add `total_count`, `offset`, `limit` to the response metadata dict
    - _Requirements: 2.4, 3.7_

  - [x] 3.2 Add throughput_report_page message handler in handle_websocket_message
    - Add `elif message_type == 'throughput_report_page':` branch
    - Extract `offset` and `limit` from `message_data`
    - Validate: `offset` is non-negative int, `limit` is positive int ≤ 100
    - On validation failure, send `{type: "error", message: "..."}` with descriptive message
    - On success, call `await _handle_throughput_report(connection_id, manager, offset=offset, limit=limit)`
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [ ]* 3.3 Write property test: Input validation rejects invalid offset and limit (Property 5)
    - **Property 5: Input validation rejects invalid offset and limit**
    - Generate random invalid offsets (negative ints, floats, strings) and invalid limits (0, negatives, >100, floats, strings)
    - Assert error response is returned and `generate_throughput_report` is not called
    - **Validates: Requirements 4.3, 4.4**

- [x] 4. Checkpoint - Ensure all backend tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement frontend telemetry state and pagination controls
  - [x] 5.1 Add telemetry state properties to ChatApp
    - Add `telemetryDisplayed`, `telemetryMessageElement`, `telemetryCurrentPage`, `telemetryTotalCount`, `telemetryLimit` to the ChatApp constructor
    - _Requirements: 5.3_

  - [x] 5.2 Update handleChatResponse for telemetry tracking and in-place replacement
    - When `metadata.throughput_report` is true: set `telemetryDisplayed = true`, store element ref, extract `total_count`/`offset`/`limit` from metadata, compute `telemetryCurrentPage`
    - When `telemetryMessageElement` already exists and a new telemetry response arrives, replace inner HTML in-place instead of appending a new message
    - When `metadata.throughput_report` is falsy: set `telemetryDisplayed = false`, clear element ref
    - _Requirements: 3.1, 5.3, 5.4_

  - [x] 5.3 Render pagination controls below telemetry table
    - Append pagination HTML after the telemetry table: first `«`, prev `‹`, page indicator `{current}/{total}`, next `›`, last `»`
    - Disable first/prev buttons when `currentPage == 1`
    - Disable next/last buttons when `currentPage == totalPages`
    - Click handlers compute target offset and send `{type: "throughput_report_page", offset: newOffset, limit: 10}` via WebSocket
    - Hide pagination controls when `totalPages <= 1`
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [ ]* 5.4 Write property test: Pagination button disabled states (Property 3)
    - **Property 3: Pagination button disabled states**
    - Generate random `currentPage` (1–100) and `totalPages` (1–100)
    - Assert first/prev disabled iff `currentPage == 1`; next/last disabled iff `currentPage == totalPages`
    - **Validates: Requirements 3.3, 3.4**

  - [ ]* 5.5 Write property test: Pagination offset and total pages computation (Property 4)
    - **Property 4: Pagination offset and total pages computation**
    - Generate random `totalCount` (0–500), `limit` (1–100), `currentPage`, and button action
    - Assert `totalPages == ceil(totalCount / limit)` and offset == `(targetPage - 1) * limit`
    - **Validates: Requirements 3.5, 3.6**

- [x] 6. Implement auto-refresh on upload completion
  - [x] 6.1 Add active_jobs_update handler for auto-refresh in setupWebSocketHandlers
    - Register `this.wsManager.on('active_jobs_update', ...)` handler
    - When `data.job.status === 'completed'` AND `this.telemetryDisplayed === true`, send `{type: "throughput_report_page", offset: (currentPage-1)*limit, limit: telemetryLimit}`
    - When telemetry is not displayed, take no action
    - _Requirements: 5.1, 5.2_

  - [x] 6.2 Implement page clamping on auto-refresh response
    - After receiving updated `total_count`, compute `newTotalPages = Math.ceil(total_count / limit)`
    - If `telemetryCurrentPage > newTotalPages`, clamp to `newTotalPages` (or 1 if 0)
    - _Requirements: 5.5_

  - [ ]* 6.3 Write property test: Auto-refresh trigger condition (Property 6)
    - **Property 6: Auto-refresh triggers if and only if telemetry is displayed and job completed**
    - Generate random booleans for `telemetryDisplayed` and random strings for `job.status`
    - Assert re-request sent iff both conditions met
    - **Validates: Requirements 5.1, 5.2**

  - [ ]* 6.4 Write property test: Telemetry display flag tracking (Property 7)
    - **Property 7: Telemetry display flag tracks response metadata**
    - Generate random sequences of response metadata dicts with varying `throughput_report` values
    - Assert flag matches last response's value
    - **Validates: Requirements 5.3**

  - [ ]* 6.5 Write property test: Page clamping on auto-refresh (Property 8)
    - **Property 8: Page clamping on auto-refresh**
    - Generate random `currentPage` (1–100) and `newTotalPages` (0–100)
    - Assert result == `min(currentPage, max(1, newTotalPages))`
    - **Validates: Requirements 5.5**

- [x] 7. Add CSS for pagination controls
  - Add pagination styling for telemetry report controls, matching the existing `DocumentListPanel` pagination button styles
  - _Requirements: 3.2_

- [ ] 8. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties using Hypothesis
- Unit tests validate specific examples and edge cases
- All 8 correctness properties from the design document are covered by property test sub-tasks
- Internal identifiers (`THROUGHPUT_REPORT`, `_handle_throughput_report`, `throughput_report`) are intentionally preserved per Requirement 1.4
