# Implementation Plan: DeepSeek Chat Streaming

## Overview

This plan re-enables true token-level streaming for chat by replacing the shim in `DeepSeekAIService.generate_response_stream` with a real Server-Sent Events (SSE) client for DeepSeek's `POST /chat/completions` endpoint. The plan front-loads the pure, property-testable building blocks (resilience primitives and the SSE parser) so the streaming client can be assembled from already-tested pieces with no big integration jump. Each task builds on the previous, ends with wiring, and references specific requirements and correctness properties from the design document.

Throughout the plan:
- Implementation language: **Python 3.9+** (matches the existing codebase; design uses Python type hints, `httpx`, `pytest`, `hypothesis` directly).
- New module: `src/multimodal_librarian/services/provider_resilience.py`.
- Modified modules: `services/ai_service.py`, `services/deepseek_ai_service.py`, `services/rag_service.py`, `api/routers/chat.py`, `api/websocket/connection_manager.py` (or wherever `ConnectionManager.add_to_conversation_history` lives).
- New test files under `tests/services/` and `tests/integration/`.
- Test tasks are sub-tasks marked with `*` (optional) per the workflow convention.

## Tasks

- [x] 1. Extract provider-agnostic resilience primitives into `services/provider_resilience.py`
  - [x] 1.1 Create `services/provider_resilience.py` with `ErrorType`, `USER_FRIENDLY_ERROR_MESSAGES`, `ProviderError`, `CircuitState`, `CircuitBreakerConfig`, `CircuitBreaker`, `ErrorRateConfig`, `ErrorRateTracker`, `CircuitBreakerOpenError` moved (not re-implemented) from `services/ai_service.py`
    - Move class bodies verbatim; rename `GeminiCircuitBreaker` → `CircuitBreaker`, `GeminiErrorType` → `ErrorType`, `GeminiError` → `ProviderError`
    - Keep behavior bit-for-bit identical; this is a relocation, not a refactor
    - _Requirements: 5.1, 5.2, 6.6, 9.6, 11.3_
  - [x] 1.2 Add `classify_http_status(status_code: int, body_excerpt: str = "") -> ErrorType` to `services/provider_resilience.py`
    - 401/403 → `AUTHENTICATION`, 429 → `RATE_LIMIT`, 5xx → `MODEL_OVERLOADED`, other 4xx → `INVALID_RESPONSE`
    - Pure function, no I/O
    - _Requirements: 6.1, 6.2, 6.3_
  - [x] 1.3 Add backward-compatible aliases at the top of `services/ai_service.py`
    - `GeminiCircuitBreaker = CircuitBreaker`, `GeminiErrorType = ErrorType`, `GeminiError = ProviderError`, `classify_error = classify_error`
    - Re-export from `services/ai_service` so external imports continue to resolve
    - _Requirements: 11.1, 11.3_
  - [ ]* 1.4 Write unit tests for `classify_http_status` covering all status-code branches
    - Test 401, 403, 429, 500, 502, 503, 400, 404, 422 inputs
    - _Requirements: 6.1, 6.2, 6.3_
  - [ ]* 1.5 Write smoke test confirming existing Gemini `AIService` still imports and uses aliased resilience classes unchanged
    - Import `GeminiCircuitBreaker` from `services.ai_service`, assert it is `CircuitBreaker`
    - _Requirements: 11.1, 11.3_

- [x] 2. Implement the pure SSE parser (`parse_sse_line` + `SSEFrame`)
  - [x] 2.1 Add `SSEFrame` dataclass and `parse_sse_line(line: str) -> Optional[SSEFrame]` at module scope in `services/deepseek_ai_service.py`
    - `SSEFrame(kind, delta_content, finish_reason, usage, raw_line)` as a `@dataclass(frozen=True)`
    - `kind` ∈ `{"delta", "done", "usage", "malformed", "empty"}`
    - `parse_sse_line` never raises; malformed JSON → `SSEFrame(kind="malformed", raw_line=...)`
    - Blank/comment/non-`data:` lines → `None`
    - _Requirements: 1.2, 1.3, 1.4, 1.5, 1.6_
  - [ ]* 2.2 Write unit tests for `parse_sse_line` in `tests/services/test_sse_parser.py`
    - `test_parse_sse_line_delta`, `test_parse_sse_line_done`, `test_parse_sse_line_usage`, `test_parse_sse_line_malformed_returns_malformed_frame`, `test_parse_sse_line_empty_line_returns_none`, `test_parse_sse_line_non_data_line_returns_none`, `test_parse_sse_line_content_filter_finish_reason`
    - _Requirements: 1.2, 1.3, 1.4, 1.5, 1.6_
  - [x] 2.3 Write property-based test for SSE parser round-trip in `tests/services/test_sse_parser_properties.py`
    - **Property 1: SSE parser round-trip**
    - **Validates: Requirements 1.2, 12.1**
    - Use `hypothesis.strategies.lists(st.text(min_size=1))` for deltas; render as DeepSeek SSE; parse; assert concatenated `delta_content` equals concatenated input
    - `@settings(max_examples=500, deadline=None)`
    - Add explicit `@example` seeds for markdown (`"**bold**"`), emoji, CJK, zero-width chars, `"\n\n"`
  - [x] 2.4 Write property-based test for SSE parser robustness under malformed JSON
    - **Property 2: SSE parser robustness under malformed JSON**
    - **Validates: Requirements 1.6, 12.2**
    - Generate valid SSE, randomly mangle a subset of lines with non-JSON strings; assert surviving lines' deltas parse identically
    - `@settings(max_examples=200, deadline=None)`

- [x] 3. Add configuration parsing and streaming metric state to `DeepSeekAIService.__init__`
  - [x] 3.1 Read new env vars in `DeepSeekAIService.__init__` and store on instance
    - `DEEPSEEK_STREAMING_ENABLED` (default `"true"`, case-insensitive boolean) → `self.streaming_enabled_config: bool`
    - `DEEPSEEK_STREAM_TIMEOUT` (default `60.0`, float) → `self.stream_ttft_timeout: float`
    - `DEEPSEEK_STREAM_TOTAL_TIMEOUT` (default `180.0`, float) → `self.stream_total_timeout: float`
    - `DEEPSEEK_STREAM_INCLUDE_USAGE` (default `"true"`) → `self.stream_include_usage: bool`
    - On `ValueError` parsing floats, fall back to default with WARN log
    - _Requirements: 10.1, 10.3, 10.4, 10.5_
  - [x] 3.2 Instantiate shared resilience primitives on the service instance
    - `self._circuit_breaker = CircuitBreaker()`
    - `self._error_rate_tracker = ErrorRateTracker()`
    - _Requirements: 5.1, 5.2, 6.6, 11.3_
  - [x] 3.3 Initialize streaming metric counters and sample deques
    - `self._stream_total`, `self._stream_success`, `self._stream_failed` (ints)
    - `self._stream_duration_samples`, `self._stream_ttft_samples`, `self._stream_chunks_samples` (each `deque(maxlen=100)`)
    - _Requirements: 9.5_
  - [ ]* 3.4 Write unit tests for env-var parsing defaults and overrides
    - `test_env_var_parsing_defaults`, `test_streaming_enabled_false_parsed`, `test_stream_ttft_timeout_parsed`, `test_stream_include_usage_false_parsed`, `test_float_env_var_invalid_falls_back_to_default_with_warn`
    - _Requirements: 10.1, 10.3, 10.4, 10.5_

- [x] 4. Implement the context-merge helper `_merge_context`
  - [x] 4.1 Add `_merge_context(messages, context) -> List[Dict[str, str]]` to `DeepSeekAIService`
    - When `context` is non-empty and last message has `role == "user"`, return new list with last message's `content` set to `original + "\n\nAdditional context:\n" + context`
    - When `context` is None/empty, return `messages` unchanged
    - Never mutate input
    - _Requirements: 2.3_
  - [x] 4.2 Write property-based test for context-merge
    - **Property 3: Context-merge rule**
    - **Validates: Requirements 2.3**
    - Generate `messages` ending in `role="user"` and arbitrary `context`; assert role unchanged, content suffix matches exactly
    - `@settings(max_examples=200)`

- [x] 5. Implement the DeepSeek SSE streaming client in `DeepSeekAIService.generate_response_stream`
  - [x] 5.1 Replace the existing shim body with the fallback/circuit-breaker pre-flight check
    - If `not self.streaming_enabled_config` → delegate to `_streaming_disabled_fallback` (Req 5.1 / 10.2)
    - If `not self._error_rate_tracker.streaming_enabled` → delegate to `_streaming_disabled_fallback` (Req 5.1)
    - If `not await self._circuit_breaker.allow_request()` → yield one terminal chunk with `metadata["error_type"] = "circuit_breaker"` and return without issuing any HTTP request (Req 5.2)
    - _Requirements: 5.1, 5.2, 10.2_
  - [x] 5.2 Add private helper `_streaming_disabled_fallback(messages, context, temperature, max_tokens, preferred_provider)`
    - Call `self.generate_response(...)` and yield exactly one `AIResponse` with `metadata["streaming_fallback"] = True`, `metadata["is_final"] = True`, `chunk_index=0`
    - _Requirements: 5.1, 10.2_
  - [x] 5.3 Add private helper `_make_circuit_breaker_chunk()` and `_make_http_error_chunk(status_code, body)` and `_make_final_chunk(...)` and `_make_content_blocked_chunk(chunk_index)`
    - Each returns an `AIResponse` with the correct `metadata` (`is_final`, `chunk_index`, `error_type`, `recoverable`, `retry_after_seconds` where applicable, `user_message`, `finish_reason`)
    - Use `USER_FRIENDLY_ERROR_MESSAGES[ErrorType.X]` for user-facing copy
    - _Requirements: 1.7, 5.2, 6.1, 6.2, 6.3, 6.4, 6.5_
  - [x] 5.4 Implement the SSE streaming loop using `async with self._client.stream("POST", "/chat/completions", json=payload, timeout=httpx.Timeout(...)) as resp`
    - Merge context via `_merge_context`
    - Build payload with `"stream": True`; include `"stream_options": {"include_usage": True}` when `self.stream_include_usage` is true
    - If `resp.status_code != 200`: read body up to 1000 chars, log ERROR, classify via `classify_http_status`, record failure in circuit breaker and error-rate tracker, yield one terminal error chunk, return
    - On 200: iterate `resp.aiter_lines()`, pass each line to `parse_sse_line`, yield one `AIResponse` per `kind="delta"` frame with `content=delta_content`, `provider="deepseek"`, `model=self.model`, `metadata={"is_final": False, "chunk_index": N, "call_id": call_id}`
    - On `kind="done"`: break loop and yield terminal `_make_final_chunk` with aggregated `usage`, `finish_reason`, `cumulative_chars`, `duration_ms`
    - On `kind="malformed"`: WARN log (truncated to 200 chars), continue
    - On `kind="usage"`: stash `usage` and `finish_reason` for the final chunk
    - On `kind="empty"`: stash `finish_reason` only
    - On detecting `finish_reason == "content_filter"` inside a delta frame: yield `_make_content_blocked_chunk`, record success (not failure) in both trackers, return (Req 6.5)
    - On success path after `[DONE]`: `await self._circuit_breaker.record_success()` and `await self._error_rate_tracker.record_call(success=True)` and increment `_stream_success`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 2.1, 2.2, 2.4, 2.5, 2.6, 6.1, 6.2, 6.3, 6.5, 6.6, 7.4, 10.5_
  - [x] 5.5 Wrap the streaming loop in timeout and exception handlers
    - `httpx.ReadTimeout` raised during first-byte wait → yield terminal chunk with `metadata["finish_reason"] = "timeout"`, `error_type = "timeout"`, record failure (Req 1.8)
    - `httpx.ReadError` / `httpx.RemoteProtocolError` raised mid-stream → yield terminal chunk with `error_type = "network_error"`, preserve `chunk_index` of last successful delta, record failure (Req 6.4)
    - `asyncio.wait_for` around the iteration loop with `self.stream_total_timeout`; on `asyncio.TimeoutError` yield terminal timeout chunk preserving partial content (Req 1.8)
    - _Requirements: 1.8, 6.4_
  - [x] 5.6 Add `try / except GeneratorExit / finally` to emit `deepseek_stream_aborted` log on client disconnect
    - Set `aborted = True` in `except GeneratorExit`, re-raise
    - In `finally`, if `aborted`: `logger.info("deepseek_stream_aborted", extra={"event": ..., "call_id": ..., "reason": "client_disconnect", "chunks_sent": ..., "duration_ms": ...})`
    - The `async with self._client.stream(...)` context manager closes the TCP connection automatically on exit, cancelling the DeepSeek generation
    - _Requirements: 7.1, 7.2_

- [ ] 6. Checkpoint - Core streaming client implemented
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 7. Add property and example tests for `DeepSeekAIService.generate_response_stream`
  - [ ]* 7.1 Write property-based test for output contract invariants in `tests/services/test_deepseek_streaming_properties.py`
    - **Property 4: Output contract invariants**
    - **Validates: Requirements 2.4, 2.5, 2.6**
    - Generate arbitrary (status_code, delta sequence, malformed-line mask, `[DONE]` placement, usage payload, finish_reason) via Hypothesis; drive `DeepSeekAIService.generate_response_stream` via `httpx.MockTransport`; assert: at least one chunk yielded; exactly one terminal chunk and it is last; every chunk has `provider="deepseek"` and `model==service.model`; `chunk_index` increases by exactly 1
    - `@settings(max_examples=200, deadline=None)`
  - [ ]* 7.2 Write property-based test for success-path resilience recording
    - **Property 9: Success path records success in resilience trackers**
    - **Validates: Requirements 6.6**
    - For any clean `[DONE]` stream, assert `CircuitBreaker.record_success` and `ErrorRateTracker.record_call(success=True)` are each called exactly once; `record_failure` is never called
    - Use a spy/mock wrapper around the trackers
  - [ ]* 7.3 Write example-based tests for HTTP error classification in `tests/services/test_deepseek_streaming.py`
    - `test_streaming_issues_single_post_with_stream_true` (Req 1.1)
    - `test_streaming_done_marker_ends_stream` (Req 1.4)
    - `test_streaming_usage_populates_final_tokens` (Req 1.5)
    - `test_streaming_timeout_yields_terminal_timeout_chunk` (Req 1.8)
    - `test_http_401_yields_auth_error_chunk`, `test_http_403_yields_auth_error_chunk` (Req 6.1)
    - `test_http_429_honours_retry_after_header`, `test_http_429_default_retry_after_60` (Req 6.2)
    - `test_http_500_yields_model_overloaded` (Req 6.3)
    - `test_network_drop_yields_terminal_chunk_with_preserved_content` (Req 6.4)
    - `test_content_filter_records_success_in_circuit_breaker` (Req 6.5)
    - `test_streaming_disabled_config_uses_fallback` (Req 10.2)
    - `test_circuit_breaker_open_yields_terminal_chunk_no_http_request` (Req 5.2)
    - `test_error_rate_disabled_yields_fallback` (Req 5.1)
    - `test_stream_options_include_usage_when_flag_enabled`, `test_stream_options_omitted_when_flag_disabled` (Req 10.5)
    - All use `httpx.MockTransport` for canned responses

- [x] 8. Fix RAG provider-name lookup and forward streaming chunks verbatim
  - [x] 8.1 Replace hardcoded `"ai_provider": "gemini"` in `services/rag_service.py` (three occurrences near lines 1078, 1185, 1295) with dynamic lookup
    - `ai_provider = getattr(self.ai_service, "provider_name", None)`
    - Fall back to `self.ai_service.get_available_providers()[0] if providers else "unknown"`
    - _Requirements: 3.4, 11.3_
  - [x] 8.2 Add `provider_name` attribute to both `AIService` (Gemini, value `"gemini"`) and `DeepSeekAIService` (value `"deepseek"`)
    - Single-line class attribute; no behavior change
    - _Requirements: 3.4, 11.3_
  - [x] 8.3 Verify `RAGService.generate_response_stream` already forwards `AIResponse.content` unchanged (no markdown-aware chunking)
    - Read current implementation; confirm chunks are passed through as-is
    - If any buffering is present, remove it (Req 8.3)
    - _Requirements: 3.3, 3.4, 3.5, 8.3_
  - [x] 8.4 Write property-based test for RAG order preservation in `tests/services/test_rag_streaming_properties.py`
    - **Property 5: RAG order preservation**
    - **Validates: Requirements 3.3**
    - Mock `ai_service.generate_response_stream` to yield `N` deltas in order; assert `RAGService.generate_response_stream` yields content-bearing `RAGStreamingChunk` objects in the same order with identical content strings
    - `@settings(max_examples=200, deadline=None)`

- [x] 9. Update `ConnectionManager` for metadata-aware persistence and `chat.py` for partial-response-on-disconnect
  - [x] 9.1 Add optional `metadata: Optional[Dict[str, Any]] = None` kwarg to `ConnectionManager.add_to_conversation_history`
    - Attach to the appended history entry under an `_metadata` key (or equivalent) so downstream persistence sees it
    - Default behavior unchanged when `metadata` is not provided
    - _Requirements: 7.3_
  - [x] 9.2 Add optional `metadata: Optional[Dict[str, Any]] = None` kwarg to `_persist_message` in `api/routers/chat.py`
    - Merge metadata into the persisted message record's `metadata` JSON column
    - _Requirements: 7.3_
  - [x] 9.3 Edit `handle_streaming_rag_response` in `api/routers/chat.py` to hoist `citations` initialization to the top of the function
    - Ensure `citations` is defined before any branch that might `return` early
    - _Requirements: 7.2, 7.3_
  - [x] 9.4 Edit `handle_streaming_rag_response` disconnect branch to persist partial response with `metadata={"aborted": True}`
    - On detecting `not manager.is_connected(connection_id)`: log structured INFO `event="deepseek_stream_aborted"` with `connection_id`, `request_id`, `chunks_sent`, `reason="client_disconnect"`
    - If `cumulative_content` is non-empty: call `manager.add_to_conversation_history(connection_id, "assistant", cumulative_content, citations=citations, metadata={"aborted": True})` and `await _persist_message(thread_id, cumulative_content, MessageType.SYSTEM, citations=citations, metadata={"aborted": True})`
    - Do not send any further WebSocket messages for the aborted request
    - _Requirements: 7.1, 7.2, 7.3_
  - [x] 9.5 Edit `handle_streaming_rag_response` empty-stream branch to suppress empty `streaming_chunk` messages
    - If `[DONE]` arrives without any non-empty delta: do not send any `response_chunk`; send `streaming_complete` with `chunk_count=0` and `content=""` in the persisted assistant message
    - _Requirements: 7.4_
  - [x] 9.6 Verify WebSocket message type strings remain `streaming_start`, `response_chunk`, `response_complete`, `streaming_error`
    - Do not rename to match the requirements document's descriptive names; the design note under "Data Models" explicitly keeps the wire format verbatim
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 8.1, 8.2_
  - [x] 9.7 Write property-based test for WebSocket protocol invariants in `tests/integration/test_deepseek_websocket_properties.py`
    - **Property 6: WebSocket protocol invariants**
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.5, 8.3**
    - Using `TestClient.websocket_connect` with a mocked AI service yielding `N` deltas, assert message sequence matches `^streaming_start (response_chunk){N} response_complete$`; assert per-chunk `content`/`chunk_index` and `response_complete.metadata` contains all required keys
    - `@settings(max_examples=100, deadline=None)`
  - [ ]* 9.8 Write property-based test for client disconnect invariant
    - **Property 7: Client disconnect cuts off response_chunk emission**
    - **Validates: Requirements 7.1**
    - Patch `manager.is_connected` to flip to `False` at arbitrary index `k`; assert no `response_chunk` with `chunk_index >= k` and no `response_complete` is sent after disconnect
    - `@settings(max_examples=100, deadline=None)`
  - [ ]* 9.9 Write property-based test for WebSocket message schema
    - **Property 8: WebSocket message schema**
    - **Validates: Requirements 8.2**
    - Fuzz streaming invocations; assert top-level keys of each emitted WebSocket message are a subset of the allowed keys for its `type`; assert no DeepSeek-specific fields appear at the top level

- [x] 10. Add structured observability (log events + metrics aggregation)
  - [x] 10.1 Emit `deepseek_stream_start` INFO log at the start of `generate_response_stream`
    - Fields: `event="deepseek_stream_start"`, `call_id` (`uuid.uuid4().hex[:8]`), `model`, `prompt_chars`, `message_count`, `temperature`, `max_tokens`
    - _Requirements: 9.1_
  - [x] 10.2 Emit `deepseek_stream_first_token` INFO log on the first non-empty delta
    - Fields: `event`, `call_id`, `time_to_first_token_ms` (measured from request start); record into `self._stream_ttft_samples`
    - _Requirements: 9.2_
  - [x] 10.3 Emit `deepseek_stream_complete` INFO log on clean `[DONE]`
    - Fields: `event`, `call_id`, `duration_ms`, `chunks_received`, `prompt_tokens`, `completion_tokens`, `total_tokens`, `finish_reason`
    - Record `duration_ms` into `self._stream_duration_samples` and `chunks_received` into `self._stream_chunks_samples`
    - _Requirements: 9.3_
  - [x] 10.4 Emit `deepseek_stream_error` ERROR log on HTTP error, timeout, or exception
    - Fields: `event`, `call_id`, `duration_ms`, `chunks_received_before_error`, `error_type`, `error_message` (truncated to 500 chars)
    - _Requirements: 9.4_
  - [x] 10.5 Emit `deepseek_stream_malformed_chunk` WARNING log inside malformed-line branch (from task 5.4)
    - Fields: `event`, `call_id`, `raw_line` (≤200 chars)
    - _Requirements: 1.6_
  - [x] 10.6 Extend `DeepSeekAIService.get_provider_status()` to include streaming metrics
    - Add keys: `streaming_total_calls`, `streaming_successful_calls`, `streaming_failed_calls`, `streaming_avg_duration_ms`, `streaming_avg_time_to_first_token_ms`, `streaming_avg_chunks_per_response`, `circuit_breaker_state`, `streaming_enabled`
    - Compute averages from the deques; guard empty deques with `0.0`
    - _Requirements: 9.5, 9.6_
  - [x] 10.7 Add `DeepSeekAIService.get_performance_stats()` mirroring `AIService.get_performance_stats()`
    - Return `{"deepseek": {"circuit_breaker": {...}, "error_rate": {...}}}` matching the Gemini payload structure
    - _Requirements: 9.6_
  - [ ]* 10.8 Write observability tests in `tests/services/test_deepseek_streaming_observability.py`
    - `test_deepseek_stream_start_log_event` (Req 9.1)
    - `test_deepseek_stream_first_token_log_event` (Req 9.2)
    - `test_deepseek_stream_complete_log_event` (Req 9.3)
    - `test_deepseek_stream_error_log_event` (Req 9.4)
    - `test_get_provider_status_exposes_streaming_metrics` (Req 9.5)
    - `test_get_performance_stats_includes_circuit_breaker_and_error_rate` (Req 9.6)
    - Use `caplog` or a log-capture fixture

- [x] 11. Checkpoint - Observability and protocol invariants verified
  - Ensure all tests pass, ask the user if questions arise.

- [x] 12. Write end-to-end integration tests with a mocked DeepSeek server
  - [x] 12.1 Create `tests/integration/test_deepseek_websocket_streaming.py` with a reusable `httpx.MockTransport` fixture that simulates DeepSeek SSE responses
    - Helpers: `mock_deepseek_stream(deltas, include_usage=True)`, `mock_deepseek_error(status_code)`, `mock_deepseek_network_drop_after(n_chunks)`
    - Use `app.dependency_overrides` to inject the mocked `DeepSeekAIService` into the FastAPI app
    - _Requirements: 12.3, 12.4, 12.5_
  - [ ]* 12.2 `test_10_chunk_stream_produces_expected_ws_message_sequence`
    - Simulate 10 deltas, assert exactly one `streaming_start`, ten `response_chunk`, one `response_complete` in that order
    - _Requirements: 12.3, 4.1, 4.2, 4.3_
  - [ ]* 12.3 `test_http_500_triggers_streaming_error_then_fallback_response`
    - Mock returns HTTP 500; assert one `streaming_error` with `recoverable=true`, followed by a non-streaming `response` message with `metadata.streaming=false`
    - _Requirements: 12.4, 4.4, 5.3, 5.5_
  - [ ]* 12.4 `test_client_disconnect_at_chunk_5_stops_ws_and_closes_http`
    - Simulate client disconnect after chunk 5 of 10; assert no further WebSocket messages; assert `httpx.MockTransport` observes connection close within 1 second
    - _Requirements: 12.5, 7.1, 7.2_
  - [ ]* 12.5 `test_client_disconnect_persists_partial_response_with_aborted_true`
    - Simulate disconnect mid-stream; assert `ConnectionManager` history and persisted message both include `metadata={"aborted": True}` and the concatenation of deltas sent so far
    - _Requirements: 7.3_
  - [ ]* 12.6 `test_empty_stream_done_only_yields_no_response_chunk_and_complete_with_zero`
    - Simulate `[DONE]` with no prior deltas; assert zero `response_chunk` messages and one `response_complete` with `chunk_count=0`
    - _Requirements: 7.4_
  - [ ]* 12.7 `test_exception_before_any_chunk_invokes_non_streaming_fallback_directly`
    - Raise in the streaming generator before any delta; assert handler calls `handle_non_streaming_rag_response` without sending `streaming_start` or `streaming_error`
    - _Requirements: 5.4_
  - [ ]* 12.8 `test_exception_after_chunks_sent_emits_streaming_error_then_fallback`
    - Raise after 3 deltas; assert `streaming_error` with `recoverable=true` then fallback `response` message
    - _Requirements: 5.3_
  - [ ]* 12.9 `test_gemini_fallback_when_deepseek_key_absent`
    - Unset `DEEPSEEK_API_KEY`, set `GEMINI_API_KEY`; assert `get_ai_service` returns Gemini `AIService` and its existing streaming implementation runs unchanged
    - _Requirements: 11.1_
  - [ ]* 12.10 `test_deepseek_selected_when_key_present`
    - Set `DEEPSEEK_API_KEY`; assert `get_ai_service` returns `DeepSeekAIService` with `streaming_enabled_config=True`
    - _Requirements: 11.2_

- [x] 13. Create rollout documentation in `docs/operations/deepseek-streaming-rollout.md`
  - [x] 13.1 Write the deployment checklist
    - `DEEPSEEK_API_KEY` set; `DEEPSEEK_STREAMING_ENABLED` explicitly set; `DEEPSEEK_STREAM_TIMEOUT` and `DEEPSEEK_STREAM_TOTAL_TIMEOUT` reviewed; alerts configured on `deepseek_stream_error` rate and `circuit_breaker_state=open`; rollback env-var flip tested on staging
    - _Requirements: 10.1, 10.2, 10.3, 10.4_
  - [x] 13.2 Write the phased rollout plan (phases 0–4 from design §Migration and rollout plan)
    - Phase 0: code merge with flag off (default post-code-merge)
    - Phase 1: internal smoke on dev with flag on
    - Phase 2: staging canary with error-rate threshold < 5% over 24h
    - Phase 3: production canary at 10%
    - Phase 4: full production
  - [x] 13.3 Write the feature-flag runbook
    - How to flip `DEEPSEEK_STREAMING_ENABLED=false` for rollback (single env var, service restart)
    - How the automatic soft-rollback works (ErrorRateTracker disables streaming when failure rate > 50% over 5-min window, re-enables below 30%)
    - What log events and metrics to watch

- [x] 14. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional tests and can be skipped for a faster MVP, but all nine correctness properties from the design should be covered before production rollout.
- Every task references specific requirement clauses from `requirements.md` for traceability; every property test task references its property number and the validated requirement clause.
- The plan front-loads two pure, property-testable units (resilience primitives in Task 1, SSE parser in Task 2) so the streaming client in Task 5 composes already-tested pieces and the integration jump is small.
- Tasks 9 and 12 are the only places that touch WebSocket/router code; they ship additive changes only (no renames, no message-shape changes).
- No frontend changes are required at any step; the JS handlers in `static/js/chat.js` and `static/js/unified_interface.js` continue to receive byte-identical `response_chunk` / `response_complete` messages.
- Property tests use Hypothesis with `@settings(max_examples=200, deadline=None)` for protocol invariants and `max_examples=500` for the pure parser; explicit `@example` seeds cover markdown, emoji, CJK, zero-width, and boundary cases.
- No tasks cover deployment to production, user training, performance-metric gathering in a live environment, or manual end-to-end browser testing; those are out of scope for a coding agent.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "2.1", "13.1", "13.2", "13.3"] },
    { "id": 1, "tasks": ["1.2", "1.3", "2.2", "2.3", "2.4", "8.2"] },
    { "id": 2, "tasks": ["1.4", "1.5", "3.1", "3.2", "3.3", "4.1", "8.1"] },
    { "id": 3, "tasks": ["3.4", "4.2", "5.1", "5.2", "5.3", "8.3", "9.1", "9.2"] },
    { "id": 4, "tasks": ["5.4", "8.4", "9.3"] },
    { "id": 5, "tasks": ["5.5", "5.6", "9.4", "9.5", "9.6"] },
    { "id": 6, "tasks": ["7.1", "7.2", "7.3", "9.7", "9.8", "9.9", "10.1", "10.2", "10.3", "10.4", "10.5", "10.6", "10.7"] },
    { "id": 7, "tasks": ["10.8", "12.1"] },
    { "id": 8, "tasks": ["12.2", "12.3", "12.4", "12.5", "12.6", "12.7", "12.8", "12.9", "12.10"] }
  ]
}
```
