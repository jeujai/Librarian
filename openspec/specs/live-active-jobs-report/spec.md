## Purpose

The Active Jobs table in the status/analytics dashboard currently updates only on page refresh via a full database poll. Meanwhile, individual upload progress tiles already receive real-time WebSocket updates (progress percentage, current step, substage breakdown for Bridges/KG) via the existing `ProcessingStatusService` → `ConnectionManager` pipeline fed by Redis pub/sub from Celery workers.

This feature extends the existing WebSocket progress event flow so that the same events that drive individual upload tiles also push incremental updates to the Active Jobs report table rows in real time — eliminating the need for a page refresh to see current progress percentage, step, substage breakdown, elapsed time, and retry count.


### Key Terms
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

### Requirement: Active Jobs Update Subscription

The system SHALL support: As a dashboard user, I want to subscribe to live Active Jobs updates over my existing WebSocket connection, so that I see job progress without refreshing the page.

#### Scenario: WHEN a WebSocket client sends a message with `type` equal to

- **THEN** WHEN a WebSocket client sends a message with `type` equal to `subscribe_active_jobs`, THE ConnectionManager SHALL register that connection for Active Jobs update delivery.

#### Scenario: WHEN a WebSocket client sends a message with `type` equal to

- **THEN** WHEN a WebSocket client sends a message with `type` equal to `unsubscribe_active_jobs`, THE ConnectionManager SHALL remove that connection from Active Jobs update delivery.

#### Scenario: WHEN a subscribed connection disconnects, THE ConnectionMana

- **THEN** WHEN a subscribed connection disconnects, THE ConnectionManager SHALL remove that connection from the Active Jobs subscriber set.

#### Scenario: THE Subscription mechanism SHALL support multiple simultaneo

- **THEN** THE Subscription mechanism SHALL support multiple simultaneous subscribed connections.

### Requirement: Broadcasting Progress to Active Jobs Subscribers

The system SHALL support: As a dashboard user, I want the Active Jobs table to update in real time when any job's progress changes, so that I always see current processing status.

#### Scenario: WHEN the Redis_Progress_Subscriber receives a `status_update

- **THEN** WHEN the Redis_Progress_Subscriber receives a `status_update` Progress_Event, THE system SHALL send an Active_Jobs_Update_Message to all subscribed connections containing the updated row data for that document.

#### Scenario: THE Active_Jobs_Update_Message SHALL include the fields: `do

- **THEN** THE Active_Jobs_Update_Message SHALL include the fields: `document_id`, `document_title`, `status`, `current_step`, `progress_percentage`, `elapsed_seconds`, and `retry_count`.

#### Scenario: WHEN the Redis_Progress_Subscriber receives a `completion` P

- **THEN** WHEN the Redis_Progress_Subscriber receives a `completion` Progress_Event, THE system SHALL send an Active_Jobs_Update_Message with `status` set to `completed` to all subscribed connections.

#### Scenario: WHEN the Redis_Progress_Subscriber receives a `failure` Prog

- **THEN** WHEN the Redis_Progress_Subscriber receives a `failure` Progress_Event, THE system SHALL send an Active_Jobs_Update_Message with `status` set to `failed` and the `error_message` field populated to all subscribed connections.

### Requirement: Substage Breakdown in Live Updates

The system SHALL support: As a dashboard user, I want to see the Bridges and KG substage percentages update live in the Active Jobs table, so that I can monitor parallel task progress without refreshing.

#### Scenario: WHEN a Progress_Event includes `metadata` with a `task_name`

- **THEN** WHEN a Progress_Event includes `metadata` with a `task_name` of `bridges` or `kg`, THE Active_Jobs_Update_Message SHALL include a `substages` array with entries for each running substage containing `label` and `percentage` fields.

#### Scenario: THE system SHALL read the current substage fractions from Re

- **THEN** THE system SHALL read the current substage fractions from Redis keys `docprog:{document_id}:bridges` and `docprog:{document_id}:kg` when composing the Active_Jobs_Update_Message.

#### Scenario: WHEN both substage fractions reach 1.0, THE Active_Jobs_Upda

- **THEN** WHEN both substage fractions reach 1.0, THE Active_Jobs_Update_Message SHALL omit the `substages` field.

### Requirement: Initial Snapshot on Subscribe

The system SHALL support: As a dashboard user, I want to receive the current state of all active jobs immediately when I subscribe, so that I do not start with an empty table and wait for the next progress event.

#### Scenario: WHEN a connection subscribes to Active Jobs updates, THE sys

- **THEN** WHEN a connection subscribes to Active Jobs updates, THE system SHALL send an initial `active_jobs_snapshot` message containing the full list of currently active jobs with their latest progress data.

#### Scenario: THE `active_jobs_snapshot` message SHALL include the same fi

- **THEN** THE `active_jobs_snapshot` message SHALL include the same fields as Active_Jobs_Update_Message for each job, plus the `substages` array where applicable.

#### Scenario: THE system SHALL merge data from PostgreSQL `processing_jobs

- **THEN** THE system SHALL merge data from PostgreSQL `processing_jobs` and in-memory `ProcessingStatusService` tracking when building the initial snapshot, using the more recent data source for each field.

### Requirement: Active Jobs Update Message Format

The system SHALL support: As a frontend developer, I want a well-defined WebSocket message schema for Active Jobs updates, so that I can render table row changes incrementally.

#### Scenario: THE Active_Jobs_Update_Message SHALL have `type` set to `act

- **THEN** THE Active_Jobs_Update_Message SHALL have `type` set to `active_jobs_update`.

#### Scenario: THE Active_Jobs_Update_Message SHALL contain a `job` object

- **THEN** THE Active_Jobs_Update_Message SHALL contain a `job` object with fields: `document_id` (string), `document_title` (string), `status` (string), `current_step` (string or null), `progress_percentage` (integer 0–100), `elapsed_seconds` (float or null), `retry_count` (integer), and `substages` (array or null).

#### Scenario: THE `active_jobs_snapshot` message SHALL have `type` set to

- **THEN** THE `active_jobs_snapshot` message SHALL have `type` set to `active_jobs_snapshot` and contain a `jobs` array of objects matching the `job` schema from criterion

#### Scenario: 

- **THEN** 

#### Scenario: THE Active_Jobs_Update_Message SHALL include a `timestamp` f

- **THEN** THE Active_Jobs_Update_Message SHALL include a `timestamp` field containing an ISO 8601 formatted string.

### Requirement: Elapsed Time Calculation

The system SHALL support: As a dashboard user, I want to see accurate elapsed time for each active job in the live updates, so that I can gauge how long processing has been running.

#### Scenario: THE system SHALL calculate `elapsed_seconds` as the differen

- **THEN** THE system SHALL calculate `elapsed_seconds` as the difference between the current UTC time and the job's `started_at` timestamp from PostgreSQL or in-memory tracking.

#### Scenario: IF the `started_at` timestamp is unavailable, THEN THE syste

- **GIVEN** the `started_at` timestamp is unavailable
- **THEN** IF the `started_at` timestamp is unavailable, THEN THE system SHALL set `elapsed_seconds` to null.

### Requirement: Graceful Degradation

The system SHALL support: As a dashboard user, I want the Active Jobs table to remain functional even when parts of the system are unavailable, so that I always get the best available data.

#### Scenario: IF the ProcessingStatusService is unavailable, THEN THE syst

- **GIVEN** the ProcessingStatusService is unavailable
- **THEN** IF the ProcessingStatusService is unavailable, THEN THE system SHALL build the initial snapshot from PostgreSQL data only and log a warning.

#### Scenario: IF the PostgreSQL connection is unavailable during snapshot

- **GIVEN** the PostgreSQL connection is unavailable during snapshot generation
- **THEN** IF the PostgreSQL connection is unavailable during snapshot generation, THEN THE system SHALL build the snapshot from in-memory ProcessingStatusService tracking data only and log a warning.

#### Scenario: IF both data sources are unavailable during snapshot generat

- **GIVEN** both data sources are unavailable during snapshot generation
- **THEN** IF both data sources are unavailable during snapshot generation, THEN THE system SHALL send an `active_jobs_snapshot` with an empty `jobs` array and an `error` field describing the issue.

#### Scenario: WHILE a subscribed connection is active, THE system SHALL co

- **THEN** WHILE a subscribed connection is active, THE system SHALL continue delivering incremental Active_Jobs_Update_Messages from Redis Progress_Events regardless of PostgreSQL availability.

### Requirement: Throttling of Update Messages

The system SHALL support: As a system operator, I want to limit the rate of Active Jobs update messages per connection, so that rapid Celery progress events do not overwhelm WebSocket clients.

#### Scenario: THE system SHALL send at most one Active_Jobs_Update_Message

- **THEN** THE system SHALL send at most one Active_Jobs_Update_Message per document per subscribed connection within a configurable interval, defaulting to 1 second.

#### Scenario: WHEN multiple Progress_Events arrive for the same document w

- **THEN** WHEN multiple Progress_Events arrive for the same document within the throttle interval, THE system SHALL send only the most recent state at the end of the interval.

#### Scenario: THE throttle interval SHALL be configurable via the `ACTIVE_

- **THEN** THE throttle interval SHALL be configurable via the `ACTIVE_JOBS_UPDATE_INTERVAL_MS` environment variable.
