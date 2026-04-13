# Requirements Document

## Introduction

The Active Jobs table in the status/analytics dashboard currently updates only on page refresh via a full database poll. Meanwhile, individual upload progress tiles already receive real-time WebSocket updates (progress percentage, current step, substage breakdown for Bridges/KG) via the existing `ProcessingStatusService` → `ConnectionManager` pipeline fed by Redis pub/sub from Celery workers.

This feature extends the existing WebSocket progress event flow so that the same events that drive individual upload tiles also push incremental updates to the Active Jobs report table rows in real time — eliminating the need for a page refresh to see current progress percentage, step, substage breakdown, elapsed time, and retry count.

## Glossary

- **Active_Jobs_Table**: The markdown table rendered by `StatusReportService.format_human_summary` showing rows for jobs with status `pending` or `running`, including columns for Document, Status, Step, Progress %, substage breakdown (Bridges/KG), Elapsed time, and Retries.
- **Progress_Event**: A JSON message published to the Redis `processing_progress` pub/sub channel by Celery workers, containing `document_id`, `status`, `progress_percentage`, `current_step`, and optional `metadata`.
- **Active_Jobs_Update_Message**: A new WebSocket message type (`active_jobs_update`) sent to subscribed connections containing incremental row-level updates for the Active Jobs table.
- **Subscription**: A registration by a WebSocket connection to receive `active_jobs_update` messages whenever any active job's progress changes.
- **ProcessingStatusService**: The existing service that tracks per-document processing progress in memory and sends WebSocket updates to the originating upload connection.
- **StatusReportService**: The existing service that generates the full status report by querying PostgreSQL `processing_jobs` and merging in-memory data from `ProcessingStatusService`.
- **ConnectionManager**: The singleton WebSocket connection manager that routes messages to specific connections via `send_personal_message`.
- **Redis_Progress_Subscriber**: The background asyncio task (`_redis_progress_subscriber`) in `main.py` that subscribes to the Redis `processing_progress` channel and forwards events to `ProcessingStatusService`.
- **Substage_Breakdown**: The per-task progress fractions stored in Redis keys `docprog:{document_id}:bridges` and `docprog:{document_id}:kg`, displayed as sub-rows under each active job.

## Requirements

### Requirement 1: Active Jobs Update Subscription

**User Story:** As a dashboard user, I want to subscribe to live Active Jobs updates over my existing WebSocket connection, so that I see job progress without refreshing the page.

#### Acceptance Criteria

1. WHEN a WebSocket client sends a message with `type` equal to `subscribe_active_jobs`, THE ConnectionManager SHALL register that connection for Active Jobs update delivery.
2. WHEN a WebSocket client sends a message with `type` equal to `unsubscribe_active_jobs`, THE ConnectionManager SHALL remove that connection from Active Jobs update delivery.
3. WHEN a subscribed connection disconnects, THE ConnectionManager SHALL remove that connection from the Active Jobs subscriber set.
4. THE Subscription mechanism SHALL support multiple simultaneous subscribed connections.

### Requirement 2: Broadcasting Progress to Active Jobs Subscribers

**User Story:** As a dashboard user, I want the Active Jobs table to update in real time when any job's progress changes, so that I always see current processing status.

#### Acceptance Criteria

1. WHEN the Redis_Progress_Subscriber receives a `status_update` Progress_Event, THE system SHALL send an Active_Jobs_Update_Message to all subscribed connections containing the updated row data for that document.
2. THE Active_Jobs_Update_Message SHALL include the fields: `document_id`, `document_title`, `status`, `current_step`, `progress_percentage`, `elapsed_seconds`, and `retry_count`.
3. WHEN the Redis_Progress_Subscriber receives a `completion` Progress_Event, THE system SHALL send an Active_Jobs_Update_Message with `status` set to `completed` to all subscribed connections.
4. WHEN the Redis_Progress_Subscriber receives a `failure` Progress_Event, THE system SHALL send an Active_Jobs_Update_Message with `status` set to `failed` and the `error_message` field populated to all subscribed connections.

### Requirement 3: Substage Breakdown in Live Updates

**User Story:** As a dashboard user, I want to see the Bridges and KG substage percentages update live in the Active Jobs table, so that I can monitor parallel task progress without refreshing.

#### Acceptance Criteria

1. WHEN a Progress_Event includes `metadata` with a `task_name` of `bridges` or `kg`, THE Active_Jobs_Update_Message SHALL include a `substages` array with entries for each running substage containing `label` and `percentage` fields.
2. THE system SHALL read the current substage fractions from Redis keys `docprog:{document_id}:bridges` and `docprog:{document_id}:kg` when composing the Active_Jobs_Update_Message.
3. WHEN both substage fractions reach 1.0, THE Active_Jobs_Update_Message SHALL omit the `substages` field.

### Requirement 4: Initial Snapshot on Subscribe

**User Story:** As a dashboard user, I want to receive the current state of all active jobs immediately when I subscribe, so that I do not start with an empty table and wait for the next progress event.

#### Acceptance Criteria

1. WHEN a connection subscribes to Active Jobs updates, THE system SHALL send an initial `active_jobs_snapshot` message containing the full list of currently active jobs with their latest progress data.
2. THE `active_jobs_snapshot` message SHALL include the same fields as Active_Jobs_Update_Message for each job, plus the `substages` array where applicable.
3. THE system SHALL merge data from PostgreSQL `processing_jobs` and in-memory `ProcessingStatusService` tracking when building the initial snapshot, using the more recent data source for each field.

### Requirement 5: Active Jobs Update Message Format

**User Story:** As a frontend developer, I want a well-defined WebSocket message schema for Active Jobs updates, so that I can render table row changes incrementally.

#### Acceptance Criteria

1. THE Active_Jobs_Update_Message SHALL have `type` set to `active_jobs_update`.
2. THE Active_Jobs_Update_Message SHALL contain a `job` object with fields: `document_id` (string), `document_title` (string), `status` (string), `current_step` (string or null), `progress_percentage` (integer 0–100), `elapsed_seconds` (float or null), `retry_count` (integer), and `substages` (array or null).
3. THE `active_jobs_snapshot` message SHALL have `type` set to `active_jobs_snapshot` and contain a `jobs` array of objects matching the `job` schema from criterion 2.
4. THE Active_Jobs_Update_Message SHALL include a `timestamp` field containing an ISO 8601 formatted string.

### Requirement 6: Elapsed Time Calculation

**User Story:** As a dashboard user, I want to see accurate elapsed time for each active job in the live updates, so that I can gauge how long processing has been running.

#### Acceptance Criteria

1. THE system SHALL calculate `elapsed_seconds` as the difference between the current UTC time and the job's `started_at` timestamp from PostgreSQL or in-memory tracking.
2. IF the `started_at` timestamp is unavailable, THEN THE system SHALL set `elapsed_seconds` to null.

### Requirement 7: Graceful Degradation

**User Story:** As a dashboard user, I want the Active Jobs table to remain functional even when parts of the system are unavailable, so that I always get the best available data.

#### Acceptance Criteria

1. IF the ProcessingStatusService is unavailable, THEN THE system SHALL build the initial snapshot from PostgreSQL data only and log a warning.
2. IF the PostgreSQL connection is unavailable during snapshot generation, THEN THE system SHALL build the snapshot from in-memory ProcessingStatusService tracking data only and log a warning.
3. IF both data sources are unavailable during snapshot generation, THEN THE system SHALL send an `active_jobs_snapshot` with an empty `jobs` array and an `error` field describing the issue.
4. WHILE a subscribed connection is active, THE system SHALL continue delivering incremental Active_Jobs_Update_Messages from Redis Progress_Events regardless of PostgreSQL availability.

### Requirement 8: Throttling of Update Messages

**User Story:** As a system operator, I want to limit the rate of Active Jobs update messages per connection, so that rapid Celery progress events do not overwhelm WebSocket clients.

#### Acceptance Criteria

1. THE system SHALL send at most one Active_Jobs_Update_Message per document per subscribed connection within a configurable interval, defaulting to 1 second.
2. WHEN multiple Progress_Events arrive for the same document within the throttle interval, THE system SHALL send only the most recent state at the end of the interval.
3. THE throttle interval SHALL be configurable via the `ACTIVE_JOBS_UPDATE_INTERVAL_MS` environment variable.
