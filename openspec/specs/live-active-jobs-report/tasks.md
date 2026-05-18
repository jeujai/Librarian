# Implementation Plan: Live Active Jobs Report

## Overview

Extend the existing WebSocket progress event pipeline to broadcast real-time row-level updates to Active Jobs report subscribers. Implementation adds Pydantic models, a ConnectionManager subscriber set, an ActiveJobsDispatcher with per-document throttling, fan-out from the Redis progress subscriber, and WebSocket subscribe/unsubscribe message handling.

## Tasks

- [x] 1. Create Pydantic models for Active Jobs messages
  - [x] 1.1 Create `src/multimodal_librarian/api/models/active_jobs_models.py` with `SubstageInfo`, `ActiveJobPayload`, `ActiveJobsUpdateMessage`, and `ActiveJobsSnapshotMessage` models
    - `SubstageInfo`: `label` (str), `percentage` (int 0–100)
    - `ActiveJobPayload`: `document_id`, `document_title`, `status`, `current_step` (optional), `progress_percentage` (int 0–100), `elapsed_seconds` (optional float), `retry_count` (int), `substages` (optional list), `error_message` (optional)
    - `ActiveJobsUpdateMessage`: `type` literal `"active_jobs_update"`, `job` (ActiveJobPayload), `timestamp` (ISO 8601 str)
    - `ActiveJobsSnapshotMessage`: `type` literal `"active_jobs_snapshot"`, `jobs` (list), `timestamp` (str), `error` (optional)
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [ ]* 1.2 Write property test for payload schema completeness (Property 4)
    - **Property 4: Payload schema completeness**
    - Generate random valid event data (strings, ints 0–100, optional nulls) and assert all required fields present with correct types; timestamp parses as ISO 8601
    - **Validates: Requirements 2.2, 4.2, 5.2, 5.4**

  - [ ]* 1.3 Write property test for failure events (Property 5)
    - **Property 5: Failure events carry status and error message**
    - Generate random error strings and assert `status == "failed"` and `error_message` matches input
    - **Validates: Requirements 2.4**

- [x] 2. Extend ConnectionManager with subscriber set management
  - [x] 2.1 Add `_active_jobs_subscribers: Set[str]` to `ConnectionManager.__init__`
    - Implement `subscribe_active_jobs(connection_id)`, `unsubscribe_active_jobs(connection_id)`, `get_active_jobs_subscribers()` methods
    - Update `disconnect()` to also remove from `_active_jobs_subscribers`
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [ ]* 2.2 Write property test for subscribe grows set (Property 1)
    - **Property 1: Subscribe grows the subscriber set**
    - Generate random lists of distinct connection ID strings; assert set size equals list length and all IDs present
    - **Validates: Requirements 1.1, 1.4**

  - [ ]* 2.3 Write property test for unsubscribe/disconnect removes (Property 2)
    - **Property 2: Unsubscribe and disconnect remove from subscriber set**
    - Generate random subscriber sets + random ID to remove; assert removed ID absent, others unchanged
    - **Validates: Requirements 1.2, 1.3**

- [x] 3. Checkpoint
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Implement ActiveJobsDispatcher service
  - [x] 4.1 Create `src/multimodal_librarian/services/active_jobs_dispatcher.py` with `ActiveJobsDispatcher` class
    - Constructor accepts `connection_manager`, `processing_status_service`, `status_report_service` (optional), `throttle_interval_ms` (default 1000)
    - Read `ACTIVE_JOBS_UPDATE_INTERVAL_MS` env var for throttle configuration
    - Implement `_build_job_payload(event_data)` to construct `ActiveJobPayload` from progress event data, including elapsed time calculation and substage inclusion logic
    - Implement per-document throttle state: `_last_sent` dict and `_pending_state` dict
    - _Requirements: 2.1, 2.2, 6.1, 6.2, 8.1, 8.2, 8.3_

  - [x] 4.2 Implement `on_progress_event(event_data)` method
    - Accumulate latest state in `_pending_state` per document
    - Check throttle: if interval has elapsed, call `_flush_throttled`; otherwise schedule flush
    - Handle completion events (`status == "completed"`) and failure events (`status == "failed"`, populate `error_message`)
    - _Requirements: 2.1, 2.3, 2.4, 3.1, 3.2, 3.3_

  - [x] 4.3 Implement `_flush_throttled(document_id)` method
    - Build `ActiveJobsUpdateMessage` from latest pending state
    - Read Redis substage keys `docprog:{document_id}:bridges` and `docprog:{document_id}:kg` for substage fractions
    - Include `substages` array when any fraction < 1.0; set to null when both ≥ 1.0
    - Send to all subscribers via `ConnectionManager.send_personal_message`
    - Handle send failures: catch exception, log error, remove connection from subscriber set
    - _Requirements: 2.1, 3.1, 3.2, 3.3, 8.1, 8.2_

  - [x] 4.4 Implement `send_initial_snapshot(connection_id)` method
    - Call `StatusReportService._fetch_active_jobs` + `_merge_in_memory_data` to build snapshot
    - Reshape into list of `ActiveJobPayload` objects
    - Send `ActiveJobsSnapshotMessage` to the subscribing connection
    - Handle graceful degradation: PSS unavailable → DB only; DB unavailable → in-memory only; both unavailable → empty jobs + error
    - _Requirements: 4.1, 4.2, 4.3, 7.1, 7.2, 7.3_

  - [ ]* 4.5 Write property test for substage inclusion (Property 6)
    - **Property 6: Substage inclusion when fractions are incomplete**
    - Generate random float pairs (0.0–1.0) for bridges/kg; assert substages present when any < 1.0, null when both ≥ 1.0
    - **Validates: Requirements 3.1, 3.3**

  - [ ]* 4.6 Write property test for snapshot merge recency (Property 7)
    - **Property 7: Snapshot merge picks the more recent data source**
    - Generate random (db_timestamp, mem_timestamp, db_pct, mem_pct) tuples; assert winner is the source with the later timestamp
    - **Validates: Requirements 4.3**

  - [ ]* 4.7 Write property test for elapsed seconds (Property 8)
    - **Property 8: Elapsed seconds equals time since started_at**
    - Generate random `started_at` datetimes in the past (and None); assert `elapsed_seconds ≈ now - started_at` within tolerance; None when started_at is None
    - **Validates: Requirements 6.1, 6.2**

  - [ ]* 4.8 Write property test for throttle latest-only (Property 9)
    - **Property 9: Throttle sends latest state at most once per interval**
    - Generate random lists of event dicts with increasing progress; assert at most 1 send per interval and sent payload matches last event
    - **Validates: Requirements 8.1, 8.2**

- [x] 5. Checkpoint
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Wire fan-out into Redis progress subscriber and WebSocket handler
  - [x] 6.1 Add DI provider for `ActiveJobsDispatcher` in `src/multimodal_librarian/api/dependencies/services.py`
    - Create `get_active_jobs_dispatcher()` depending on `get_connection_manager`, `get_processing_status_service`, `get_status_report_service_optional`
    - Store dispatcher singleton on `app.state` for access from `_redis_progress_subscriber`
    - _Requirements: 2.1_

  - [x] 6.2 Modify `_redis_progress_subscriber` in `src/multimodal_librarian/main.py`
    - After existing `notify_processing_status_update` / `notify_processing_completion` / `notify_processing_failure` calls, add `await dispatcher.on_progress_event(data)` to fan out to active-jobs subscribers
    - Retrieve dispatcher from `app.state`
    - Wrap in try/except so dispatcher errors do not crash the subscriber loop
    - _Requirements: 2.1, 2.3, 2.4, 7.4_

  - [x] 6.3 Extend `handle_websocket_message` in `src/multimodal_librarian/api/routers/chat.py`
    - Add `subscribe_active_jobs` branch: call `manager.subscribe_active_jobs(connection_id)` then `await dispatcher.send_initial_snapshot(connection_id)`
    - Add `unsubscribe_active_jobs` branch: call `manager.unsubscribe_active_jobs(connection_id)`
    - _Requirements: 1.1, 1.2, 4.1_

  - [ ]* 6.4 Write property test for fan-out delivery (Property 3)
    - **Property 3: Fan-out delivers to all subscribers**
    - Generate random event dicts + random subscriber sets; mock `send_personal_message` and assert called once per subscriber with matching `document_id`
    - **Validates: Requirements 2.1**

  - [ ]* 6.5 Write unit tests for integration and degradation scenarios
    - Test completion event sets status to `"completed"` (Req 2.3)
    - Test snapshot on subscribe sends `active_jobs_snapshot` (Req 4.1)
    - Test message type literals are correct (Req 5.1, 5.3)
    - Test `ACTIVE_JOBS_UPDATE_INTERVAL_MS` env var configures throttle (Req 8.3)
    - Test snapshot with PSS=None uses DB only (Req 7.1)
    - Test snapshot with DB error uses in-memory only (Req 7.2)
    - Test snapshot with both unavailable returns empty + error (Req 7.3)
    - Test incremental updates continue when DB is down (Req 7.4)
    - _Requirements: 2.3, 4.1, 5.1, 5.3, 7.1, 7.2, 7.3, 7.4, 8.3_

- [x] 7. Final checkpoint
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate the 9 correctness properties from the design document using Hypothesis
- Unit tests cover example-based scenarios and degradation paths
- All code is Python targeting the existing FastAPI + Pydantic 2.x stack
