## Purpose

This feature adds a natural language-invocable processing status report to the existing Chat interface. Users can type queries like "Show me upload stats", "What's processing right now?", or "Show all jobs in progress" and receive a formatted summary of all active/recent document processing jobs. The system uses semantic intent detection to recognize status report requests regardless of phrasing, queries PostgreSQL for live job data, and renders the results as a structured report delivered over the existing WebSocket connection.


### Key Terms
- **Chat_Interface**: The existing WebSocket-based conversational interface (`/ws/chat`) that handles real-time user messages and AI responses.
- **Intent_Detector**: The component responsible for classifying user queries into intents (currently `QueryIntentClassifier` and `QueryProcessor._classify_query_intent`). Extended to recognize a new `STATUS_REPORT` intent.
- **Status_Report_Service**: A new service that queries PostgreSQL `processing_jobs` and `knowledge_sources` tables to gather live processing data and formats it into a structured report.
- **Processing_Job**: A row in the `processing_jobs` table representing a background document processing task with fields: `id`, `source_id`, `task_id`, `status`, `progress_percentage`, `current_step`, `error_message`, `started_at`, `completed_at`, `retry_count`, `job_metadata`.
- **Knowledge_Source**: A row in the `knowledge_sources` table representing an uploaded document with fields including `id`, `title`, `file_size`, `page_count`, `created_at`.
- **Report_Payload**: The structured JSON object sent over WebSocket containing the processing status report data.
- **Active_Job**: A Processing_Job with status `pending` or `running`.
- **Recent_Job**: A Processing_Job with status `completed` or `failed` that finished within a configurable time window (default: last 30 minutes).

## Requirements

### Requirement: Natural Language Intent Detection for Status Reports

The system SHALL support: As a user, I want to ask for processing status using any natural phrasing in the chat, so that I don't need to remember a specific command.

#### Scenario: WHEN a user sends a chat message, THE Intent_Detector SHALL

- **THEN** WHEN a user sends a chat message, THE Intent_Detector SHALL classify the message as `STATUS_REPORT` intent when the message semantically requests processing status information.

#### Scenario: WHEN the Intent_Detector classifies a message as `STATUS_REP

- **THEN** WHEN the Intent_Detector classifies a message as `STATUS_REPORT`, THE Chat_Interface SHALL bypass the RAG pipeline and route the message to the Status_Report_Service.

#### Scenario: THE Intent_Detector SHALL recognize status report requests e

- **THEN** THE Intent_Detector SHALL recognize status report requests expressed in varied phrasings including but not limited to: "show me upload stats", "what's processing right now", "show all jobs in progress", "any uploads running?", "processing status", and "how are my documents doing?".

#### Scenario: WHEN a message is ambiguous between a status report request

- **THEN** WHEN a message is ambiguous between a status report request and a knowledge query, THE Intent_Detector SHALL default to the `SEARCH` intent to avoid false positives.

### Requirement: Processing Status Data Retrieval

The system SHALL support: As a user, I want to see accurate, real-time data about my processing jobs, so that I can monitor progress at a glance.

#### Scenario: WHEN the Status_Report_Service receives a report request, TH

- **THEN** WHEN the Status_Report_Service receives a report request, THE Status_Report_Service SHALL query the `processing_jobs` table joined with `knowledge_sources` to retrieve all Active_Jobs.

#### Scenario: THE Status_Report_Service SHALL also retrieve Recent_Jobs (c

- **THEN** THE Status_Report_Service SHALL also retrieve Recent_Jobs (completed or failed within the last 30 minutes) to provide context on recently finished work.

#### Scenario: FOR EACH job in the report, THE Status_Report_Service SHALL

- **GIVEN** EACH job in the report
- **THEN** FOR EACH job in the report, THE Status_Report_Service SHALL include: document title, current processing step, progress percentage, elapsed time since `started_at`, job status, and retry count.

#### Scenario: FOR EACH completed job in the report, THE Status_Report_Serv

- **GIVEN** EACH completed job in the report
- **THEN** FOR EACH completed job in the report, THE Status_Report_Service SHALL include: document title, total processing time, and chunk count from `job_metadata`.

#### Scenario: FOR EACH failed job in the report, THE Status_Report_Service

- **GIVEN** EACH failed job in the report
- **THEN** FOR EACH failed job in the report, THE Status_Report_Service SHALL include: document title, error message, failed step, and whether retry is available.

#### Scenario: IF no Active_Jobs or Recent_Jobs exist, THEN THE Status_Repo

- **GIVEN** no Active_Jobs or Recent_Jobs exist
- **THEN** IF no Active_Jobs or Recent_Jobs exist, THEN THE Status_Report_Service SHALL return a report indicating zero active processing jobs.

### Requirement: Report Formatting and Delivery

The system SHALL support: As a user, I want the processing report to appear as a clear, readable message in the chat, so that I can quickly understand the state of all my uploads.

#### Scenario: WHEN the Status_Report_Service produces a report, THE Chat_I

- **THEN** WHEN the Status_Report_Service produces a report, THE Chat_Interface SHALL deliver the Report_Payload as a WebSocket message with type `processing_status_report`.

#### Scenario: THE Report_Payload SHALL contain a `summary` object with: to

- **THEN** THE Report_Payload SHALL contain a `summary` object with: total active job count, total completed count (recent), total failed count (recent), and overall progress across all active jobs.

#### Scenario: THE Report_Payload SHALL contain a `jobs` array where each e

- **THEN** THE Report_Payload SHALL contain a `jobs` array where each entry includes the fields specified in Requirement 2 acceptance criteria 3, 4, and

#### Scenario: 

- **THEN** 

#### Scenario: THE Report_Payload SHALL include a `generated_at` ISO 8601 t

- **THEN** THE Report_Payload SHALL include a `generated_at` ISO 8601 timestamp indicating when the report was generated.

#### Scenario: THE Chat_Interface SHALL also send a human-readable `assista

- **THEN** THE Chat_Interface SHALL also send a human-readable `assistant` message summarizing the report in natural language (e.g., "You have 3 uploads in progress and 2 completed recently.").

### Requirement: Integration with Existing Chat Flow

The system SHALL support: As a user, I want the status report to feel like a natural part of the chat conversation, so that the experience is seamless.

#### Scenario: THE Chat_Interface SHALL add the status report response to t

- **THEN** THE Chat_Interface SHALL add the status report response to the conversation history so it appears in the chat thread.

#### Scenario: WHEN the status report is delivered, THE Chat_Interface SHAL

- **THEN** WHEN the status report is delivered, THE Chat_Interface SHALL send a `processing_complete` message to dismiss the typing indicator, consistent with existing chat message handling.

#### Scenario: THE Status_Report_Service SHALL follow the dependency inject

- **THEN** THE Status_Report_Service SHALL follow the dependency injection pattern used by existing services, with a provider function in `api/dependencies/services.py`.

#### Scenario: IF the database connection is unavailable, THEN THE Status_R

- **GIVEN** the database connection is unavailable
- **THEN** IF the database connection is unavailable, THEN THE Status_Report_Service SHALL return an error message indicating that status information is temporarily unavailable.

### Requirement: In-Memory Status Augmentation

The system SHALL support: As a user, I want the report to include the most up-to-date status from in-memory tracking, so that I see real-time progress even between database writes.

#### Scenario: WHEN the ProcessingStatusService has in-memory tracking data

- **THEN** WHEN the ProcessingStatusService has in-memory tracking data for an Active_Job, THE Status_Report_Service SHALL merge the in-memory progress percentage and current stage with the database record, preferring the in-memory value when it is more recent.

#### Scenario: WHEN the ProcessingStatusService has in-memory tracking data

- **THEN** WHEN the ProcessingStatusService has in-memory tracking data for a job not yet in the database, THE Status_Report_Service SHALL include that job in the report with the in-memory data.

#### Scenario: IF the ProcessingStatusService is unavailable, THEN THE Stat

- **GIVEN** the ProcessingStatusService is unavailable
- **THEN** IF the ProcessingStatusService is unavailable, THEN THE Status_Report_Service SHALL fall back to database-only data without error.
