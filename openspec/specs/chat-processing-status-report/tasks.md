# Implementation Plan: Chat Processing Status Report

## Overview

Implement a natural language-invocable processing status report within the existing WebSocket chat interface. The feature extends intent classification to detect `STATUS_REPORT` requests, introduces a `StatusReportService` that aggregates data from PostgreSQL and in-memory tracking, and delivers structured reports over WebSocket. Implementation follows the existing DI pattern and builds incrementally from data models through service logic to chat integration.

## Tasks

- [x] 1. Define WebSocket message models for status reports
  - [x] 1.1 Add `ReportSummary`, `JobDetail`, and `StatusReport` Pydantic models to `src/multimodal_librarian/api/models/chat_document_models.py`
    - `ReportSummary`: `total_active`, `total_completed_recent`, `total_failed_recent`, `overall_progress` (float 0.0-100.0)
    - `JobDetail`: `document_id`, `document_title`, `status`, `current_step`, `progress_percentage`, `elapsed_seconds`, `retry_count`, `total_processing_seconds`, `chunk_count`, `error_message`, `failed_step`, `retry_available`
    - `StatusReport`: `type` literal `"processing_status_report"`, `summary`, `jobs` list, `generated_at` datetime
    - _Requirements: 2.3, 2.4, 2.5, 3.1, 3.2, 3.3, 3.4_

  - [ ]* 1.2 Write property test for report payload structure (Property 5)
    - **Property 5: Report payload structure invariant**
    - Generate random `StatusReport` instances and verify serialization produces `type == "processing_status_report"`, contains `summary`, `jobs`, and valid ISO 8601 `generated_at`
    - **Validates: Requirements 3.1, 3.4**

  - [ ]* 1.3 Write property test for job detail field completeness (Property 3)
    - **Property 3: Job detail field completeness by status**
    - Generate random `JobDetail` objects with varying statuses and verify required fields are present per status type (completed → `total_processing_seconds` + `chunk_count`; failed → `error_message` + `failed_step` + `retry_available`)
    - **Validates: Requirements 2.3, 2.4, 2.5, 3.3**

- [x] 2. Implement StatusReportService core logic
  - [x] 2.1 Create `src/multimodal_librarian/services/status_report_service.py` with `StatusReportService` class
    - Constructor accepts `RelationalStoreClient`, optional `ProcessingStatusService`, and `recent_window_minutes` (default 30)
    - Implement `_fetch_active_jobs()`: query `processing_jobs` JOIN `knowledge_sources` WHERE status IN ('pending', 'running')
    - Implement `_fetch_recent_jobs()`: query `processing_jobs` JOIN `knowledge_sources` WHERE status IN ('completed', 'failed') AND `completed_at` >= NOW() - configured interval
    - Implement `_build_summary()`: compute counts and mean progress from job list
    - Implement `_format_human_summary()`: generate natural language summary string containing numeric values from summary
    - Implement `generate_report()`: orchestrate fetch, merge, build summary, return `StatusReport`
    - Handle DB unavailability with graceful error message per Requirement 4.4
    - Handle empty state (no jobs) returning zero-count report per Requirement 2.6
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 3.2, 3.5, 4.4_

  - [ ]* 2.2 Write property test for job filtering correctness (Property 2)
    - **Property 2: Job filtering correctness**
    - Generate random lists of job dicts with varying statuses and timestamps, verify only active + recent jobs are included
    - **Validates: Requirements 2.1, 2.2**

  - [ ]* 2.3 Write property test for summary aggregation correctness (Property 4)
    - **Property 4: Summary aggregation correctness**
    - Generate random lists of `JobDetail` objects, compute summary, verify counts match and `overall_progress` equals mean of active job percentages
    - **Validates: Requirements 3.2**

  - [ ]* 2.4 Write property test for human-readable summary (Property 6)
    - **Property 6: Human-readable summary reflects report data**
    - Generate random `ReportSummary` objects, verify formatted string contains `total_active`, `total_completed_recent`, and `total_failed_recent` as substrings
    - **Validates: Requirements 3.5**

- [x] 3. Implement in-memory merge logic
  - [x] 3.1 Add `_merge_in_memory_data()` method to `StatusReportService`
    - For each active DB job, check `ProcessingStatusService._tracking` for matching `document_id`
    - Use in-memory `progress_percentage` and `current_stage` when `last_updated` is more recent
    - Include jobs tracked in-memory but not yet in DB
    - Skip merge gracefully when `ProcessingStatusService` is `None`
    - _Requirements: 5.1, 5.2, 5.3_

  - [ ]* 3.2 Write property test for in-memory merge correctness (Property 7)
    - **Property 7: In-memory merge correctness**
    - Generate random DB job records and in-memory trackers with varying timestamps, verify merge picks correct values per recency
    - **Validates: Requirements 5.1, 5.2**

- [x] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Register StatusReportService in dependency injection
  - [x] 5.1 Add `get_status_report_service` and `get_status_report_service_optional` provider functions in `src/multimodal_librarian/api/dependencies/services.py`
    - Inject `RelationalStoreClient` via `get_relational_client` and `ProcessingStatusService` via `get_processing_status_service_optional`
    - Follow existing caching pattern with module-level `_status_report_service` variable
    - Optional variant returns `None` on failure
    - _Requirements: 4.3_

- [x] 6. Extend intent classification to detect STATUS_REPORT
  - [x] 6.1 Update the LLM prompt in `QueryProcessor._classify_query_intent` in `src/multimodal_librarian/services/rag_service.py`
    - Add `STATUS_REPORT` as a new classification option in the prompt
    - Include description and examples: "show me upload stats", "what's processing?", "any uploads running?", "how are my documents doing?", "processing status"
    - Return `("status_report", None)` when detected
    - Default to `SEARCH` for ambiguous cases per Requirement 1.4
    - _Requirements: 1.1, 1.3, 1.4_

  - [ ]* 6.2 Write unit tests for intent classification
    - Test known status report phrases from Requirement 1.3 are classified as `status_report`
    - Test ambiguous queries default to `search`
    - Test greetings still classified as `no_search`
    - **Validates: Property 1, Requirements 1.1, 1.3, 1.4**

- [x] 7. Integrate status report into chat message handler
  - [x] 7.1 Update `handle_chat_message` in `src/multimodal_librarian/api/routers/chat.py` to handle `status_report` intent
    - After intent classification returns `"status_report"`, bypass RAG pipeline
    - Obtain `StatusReportService` via DI (`get_status_report_service_optional`)
    - Call `generate_report()` and send `processing_status_report` WebSocket message
    - Send human-readable `assistant` message summarizing the report
    - Add assistant summary to conversation history
    - Send `processing_complete` to dismiss typing indicator
    - Handle `StatusReportService` unavailability with error message
    - _Requirements: 1.2, 3.1, 3.5, 4.1, 4.2, 4.4_

  - [ ]* 7.2 Write unit tests for chat integration
    - Mock `_classify_query_intent` to return `"status_report"` and verify `StatusReportService.generate_report()` is called (not RAG)
    - Verify `processing_status_report` message is sent over WebSocket
    - Verify `processing_complete` message is sent after report
    - Verify assistant message is added to conversation history
    - Test DB unavailable scenario returns graceful error message
    - Test `ProcessingStatusService` unavailable returns DB-only report
    - **Validates: Property 1, Requirements 1.2, 4.1, 4.2, 4.4, 5.3**

- [ ] 8. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Property tests use Hypothesis (already in the project) with `@settings(max_examples=100)`
- Tests located at `tests/services/test_status_report_service.py` (property + unit) and `tests/integration/test_chat_status_report.py`
- The implementation language is Python, matching the existing codebase
