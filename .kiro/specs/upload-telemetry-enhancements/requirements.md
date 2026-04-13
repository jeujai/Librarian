# Requirements Document

## Introduction

This feature enhances the existing Upload Throughput Report with three changes: renaming the user-facing label from "Upload Throughput Report" to "Upload Telemetry", adding server-side pagination (10 rows per page) with frontend pagination controls matching the existing DocumentListPanel pattern, and auto-refreshing the telemetry report when a WebSocket upload-completion event arrives while the report is displayed.

## Glossary

- **Telemetry_Report**: The renamed report previously called "Upload Throughput Report". Displays a paginated markdown table of completed upload metrics (per-stage timings, chunk counts, quality gate data). Internally the intent keyword `THROUGHPUT_REPORT` and handler function names remain unchanged.
- **Chat_Router**: The FastAPI WebSocket message handler in `chat.py` that dispatches user intents to report generators and sends responses to the frontend.
- **StatusReportService**: The backend service class responsible for querying PostgreSQL and building the markdown table for the Telemetry_Report.
- **System_Commands_List**: The list of tuples in `chat.py` that defines available system reports, their display names, and their signature prompts.
- **DocumentListPanel**: The existing frontend component that displays paginated document listings with first/previous/page-indicator/next/last pagination controls.
- **Pagination_Controls**: A set of five UI elements — first page, previous page, page indicator (e.g. "2/5"), next page, last page — rendered below the Telemetry_Report table.
- **Frontend_Chat**: The vanilla JavaScript chat interface (`chat.js`) that renders WebSocket messages, including throughput/telemetry report tables.
- **ActiveJobsDispatcher**: The existing backend service that receives Redis pub/sub completion events and broadcasts `active_jobs_update` messages (with `status="completed"`) to subscribed WebSocket connections.
- **Completion_Event**: A WebSocket message with `type="active_jobs_update"` and `job.status="completed"` broadcast by the ActiveJobsDispatcher when an upload finishes processing.

## Requirements

### Requirement 1: Rename display label from "Upload Throughput Report" to "Upload Telemetry"

**User Story:** As a user, I want the report to be called "Upload Telemetry" so that the name better reflects the breadth of metrics displayed.

#### Acceptance Criteria

1. THE System_Commands_List SHALL contain the entry `("Upload Telemetry", "Show me upload telemetry")` in place of the former `("Upload Throughput Report", "Show me throughput for uploads")`.
2. WHEN the Chat_Router generates the Telemetry_Report, THE StatusReportService SHALL render the table heading as `**Upload Telemetry**` instead of `**Upload Throughput**`.
3. WHEN a user sends the message "Show me upload telemetry", THE Chat_Router SHALL classify the intent as `throughput_report` and invoke the existing `_handle_throughput_report` handler.
4. THE Chat_Router SHALL preserve the internal intent keyword `THROUGHPUT_REPORT`, the handler function name `_handle_throughput_report`, and the metadata key `throughput_report` without modification.

### Requirement 2: Paginated backend query for the Telemetry Report

**User Story:** As a user, I want the telemetry report to show 10 rows per page so that large upload histories remain readable and performant.

#### Acceptance Criteria

1. THE StatusReportService.generate_throughput_report method SHALL accept two optional integer parameters: `offset` (default 0) and `limit` (default 10).
2. WHEN `offset` and `limit` are provided, THE StatusReportService SHALL append `OFFSET {offset} LIMIT {limit}` to the existing completed-uploads query, returning at most `limit` rows starting from position `offset`.
3. THE StatusReportService.generate_throughput_report method SHALL execute a `SELECT COUNT(*)` query against the same completed-uploads filter and return the total count alongside the markdown table.
4. THE StatusReportService.generate_throughput_report method SHALL return a tuple of `(markdown_text: str, total_count: int)` instead of a plain string.
5. WHEN `offset` exceeds the total number of completed uploads, THE StatusReportService SHALL return an empty table body with the heading and column headers still present, and `total_count` equal to the actual total.
6. IF the database query fails, THEN THE StatusReportService SHALL return the existing error message string and a `total_count` of 0.

### Requirement 3: Frontend pagination controls for the Telemetry Report

**User Story:** As a user, I want first/previous/page-indicator/next/last pagination buttons below the telemetry table so that I can navigate through upload history pages.

#### Acceptance Criteria

1. WHEN the Frontend_Chat receives a response with `metadata.throughput_report = true`, THE Frontend_Chat SHALL render Pagination_Controls below the telemetry table.
2. THE Pagination_Controls SHALL include five elements in order: a first-page button, a previous-page button, a page indicator displaying `"{current}/{total}"`, a next-page button, and a last-page button.
3. WHILE the current page is 1, THE Frontend_Chat SHALL disable the first-page and previous-page buttons.
4. WHILE the current page equals the total number of pages, THE Frontend_Chat SHALL disable the next-page and last-page buttons.
5. WHEN the user clicks a pagination button, THE Frontend_Chat SHALL send a WebSocket message requesting the Telemetry_Report at the corresponding page offset.
6. THE Frontend_Chat SHALL derive `total_pages` as `Math.ceil(total_count / 10)` using the `total_count` value from the response metadata.
7. THE response metadata for the Telemetry_Report SHALL include `total_count` (integer), `offset` (integer), and `limit` (integer) fields so the frontend can compute pagination state.

### Requirement 4: WebSocket request message for paginated telemetry

**User Story:** As a developer, I want a well-defined WebSocket message schema for requesting a specific page of the telemetry report so that frontend and backend stay in sync.

#### Acceptance Criteria

1. THE Chat_Router SHALL accept a WebSocket message of type `throughput_report_page` with fields `offset` (integer) and `limit` (integer).
2. WHEN the Chat_Router receives a `throughput_report_page` message, THE Chat_Router SHALL call `StatusReportService.generate_throughput_report(offset=offset, limit=limit)` and return the paginated result with pagination metadata.
3. THE Chat_Router SHALL validate that `offset` is a non-negative integer and `limit` is a positive integer no greater than 100.
4. IF `offset` or `limit` fail validation, THEN THE Chat_Router SHALL return an error response with a descriptive message.

### Requirement 5: Auto-refresh telemetry report on upload completion

**User Story:** As a user, I want the telemetry report to automatically refresh when an upload completes so that I see the latest data without manually re-requesting the report.

#### Acceptance Criteria

1. WHEN the Frontend_Chat receives a Completion_Event (an `active_jobs_update` message with `job.status="completed"`) AND the Telemetry_Report is currently displayed, THE Frontend_Chat SHALL automatically re-request the current page of the Telemetry_Report.
2. WHEN the Frontend_Chat receives a Completion_Event AND the Telemetry_Report is not currently displayed, THE Frontend_Chat SHALL take no action regarding the Telemetry_Report.
3. THE Frontend_Chat SHALL track whether the Telemetry_Report is currently displayed using a boolean flag set when a `metadata.throughput_report = true` response is rendered and cleared when a non-telemetry response is rendered.
4. WHEN auto-refresh re-fetches the Telemetry_Report, THE Frontend_Chat SHALL replace the existing telemetry table and Pagination_Controls in place rather than appending a new chat message.
5. WHEN auto-refresh re-fetches the Telemetry_Report, THE Frontend_Chat SHALL preserve the current page number unless the current page would exceed the new total pages, in which case the Frontend_Chat SHALL display the last available page.

### Requirement 6: RAG intent prompt update

**User Story:** As a developer, I want the RAG intent classification prompt to reference the new report name so that the LLM correctly classifies user queries about "upload telemetry".

#### Acceptance Criteria

1. THE RagService intent classification prompt SHALL include "upload telemetry" and "Show me upload telemetry" as example phrases for the `THROUGHPUT_REPORT` intent, replacing the former "throughput for uploads" and "Show me throughput for uploads" examples.
2. THE RagService intent classification prompt SHALL retain the `THROUGHPUT_REPORT` keyword unchanged.
3. WHEN a user sends a message containing "upload telemetry", THE RagService SHALL classify the intent as `throughput_report`.
