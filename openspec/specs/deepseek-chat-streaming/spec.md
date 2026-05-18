## Purpose

When the Multimodal Librarian chat backend was migrated from Google Gemini to DeepSeek, token-level streaming of AI responses was disabled because the previous streaming implementation (which relied on `google.generativeai`'s `stream=True` interface) was incompatible with DeepSeek's OpenAI-compatible chat completions API. The current `DeepSeekAIService.generate_response_stream` is a compatibility shim that awaits the full non-streaming response and yields a single `AIResponse`, so end users see the complete answer only after the entire response is generated. This eliminates the progressive-delivery user experience that previously existed with Gemini.

This feature re-enables true token-level streaming for chat by implementing a streaming client for DeepSeek's `POST /chat/completions` endpoint using Server-Sent Events (SSE) style chunked responses (`"stream": true`), integrating the resulting async chunk stream into the existing `RAGService.generate_response_stream` pipeline, preserving the existing WebSocket transport contract (`streaming_start` / `streaming_chunk` / `streaming_complete` / `streaming_error` messages) used by the frontend, and preserving the existing resilience behaviors (circuit breaker, error-rate-based streaming disable, graceful fallback to non-streaming).

The streaming contract between the backend and the browser, the RAG retrieval flow (citations upfront, then streamed content), and frontend rendering remain unchanged. Only the AI provider implementation changes. RAG retrieval (vector search, KG retrieval) still runs to completion before any content chunks are streamed, so citations are delivered in the first frame as they are today.


### Key Terms
- **Chat_Backend**: The server-side chat subsystem comprising `ConnectionManager`, `ChatService`, the `/ws/chat` WebSocket router, `RAGService`, and `AIService` / `DeepSeekAIService`.
- **DeepSeek_Streaming_Client**: The component inside `DeepSeekAIService` that issues a `POST /chat/completions` request with `"stream": true` and incrementally parses the SSE chunked response.
- **AIService_Streaming_API**: The async generator method `generate_response_stream(messages, context, temperature, max_tokens, preferred_provider) -> AsyncGenerator[AIResponse, None]` exposed by any AI service implementation used by `RAGService`.
- **RAG_Streaming_API**: The async generator method `RAGService.generate_response_stream(query, user_id, ...) -> AsyncGenerator[RAGStreamingChunk, None]` that yields citations first, then content chunks, then a final chunk.
- **WebSocket_Streaming_Protocol**: The existing JSON message contract sent from server to browser consisting of `streaming_start` (with citations), zero or more `streaming_chunk` messages (with incremental content), exactly one `streaming_complete` message (with metadata), or a `streaming_error` message.
- **SSE_Chunk**: A single Server-Sent Events data frame returned by DeepSeek's streaming endpoint, of the form `data: {...json...}\n\n`, terminated by `data: [DONE]\n\n`.
- **Delta**: The `choices[0].delta.content` field of a DeepSeek SSE chunk, containing the incremental text fragment for the current chunk.
- **Circuit_Breaker**: The existing `GeminiCircuitBreaker` pattern (to be generalized or reused) that opens after consecutive failures and blocks further calls for a configured reset window.
- **Error_Rate_Tracker**: The existing sliding-window tracker that disables streaming when the failure rate exceeds a configured threshold and re-enables it when the rate drops.
- **Streaming_Disabled_Fallback**: The runtime behavior in which `AIService_Streaming_API` internally calls the non-streaming `generate_response` and yields a single terminal chunk, instead of opening an SSE connection.
- **Cancellation**: Client-initiated or connection-loss-initiated termination of an in-flight streaming response, causing the server to stop consuming chunks from DeepSeek and release the underlying HTTP connection.
- **AIResponse**: The existing dataclass returned by AI services (content, provider, model, tokens_used, processing_time_ms, confidence_score, metadata).

## Requirements

### Requirement: DeepSeek SSE Streaming Client

The system SHALL support: As a developer integrating DeepSeek for chat, I want `DeepSeekAIService` to issue a true streaming request to DeepSeek's chat completions endpoint, so that incremental tokens can be delivered to downstream consumers.

#### Scenario: WHEN `DeepSeekAIService.generate_response_stream` is called,

- **THEN** WHEN `DeepSeekAIService.generate_response_stream` is called, THE DeepSeek_Streaming_Client SHALL issue a single `POST /chat/completions` request to `DEEPSEEK_BASE_URL` with JSON body containing `"stream": true`, the supplied messages, `model`, `temperature`, and `max_tokens`.

#### Scenario: WHEN the DeepSeek_Streaming_Client receives an HTTP 2xx resp

- **THEN** WHEN the DeepSeek_Streaming_Client receives an HTTP 2xx response, THE DeepSeek_Streaming_Client SHALL read the response body as an asynchronous byte stream and parse each SSE_Chunk line-by-line in arrival order.

#### Scenario: WHEN a parsed SSE_Chunk contains a non-empty `choices[0].del

- **THEN** WHEN a parsed SSE_Chunk contains a non-empty `choices[0].delta.content` value, THE DeepSeek_Streaming_Client SHALL yield an `AIResponse` whose `content` field equals that delta and whose `metadata["is_final"]` equals `false`.

#### Scenario: WHEN the DeepSeek_Streaming_Client receives the terminal mar

- **THEN** WHEN the DeepSeek_Streaming_Client receives the terminal marker `data: [DONE]`, THE DeepSeek_Streaming_Client SHALL yield exactly one final `AIResponse` with `content=""`, `metadata["is_final"] = true`, and `metadata["finish_reason"]` set to the `finish_reason` of the last non-empty chunk (or `"stop"` if not provided).

#### Scenario: WHEN a parsed SSE_Chunk contains a `usage` object (DeepSeek

- **THEN** WHEN a parsed SSE_Chunk contains a `usage` object (DeepSeek emits this on the last chunk when `stream_options.include_usage=true`), THE DeepSeek_Streaming_Client SHALL populate the final `AIResponse.tokens_used` from `usage.total_tokens` and include `prompt_tokens` and `completion_tokens` in `metadata`.

#### Scenario: IF a parsed SSE_Chunk is not valid JSON or cannot be decoded

- **GIVEN** a parsed SSE_Chunk is not valid JSON or cannot be decoded
- **THEN** IF a parsed SSE_Chunk is not valid JSON or cannot be decoded, THEN THE DeepSeek_Streaming_Client SHALL log the malformed chunk at WARNING level with the raw line truncated to 200 characters and SHALL continue parsing subsequent chunks.

#### Scenario: IF the DeepSeek HTTP response status code is not 2xx, THEN T

- **GIVEN** the DeepSeek HTTP response status code is not 2xx
- **THEN** IF the DeepSeek HTTP response status code is not 2xx, THEN THE DeepSeek_Streaming_Client SHALL read the response body up to 1000 characters, log an ERROR including the status code and body excerpt, and yield exactly one terminal `AIResponse` with `metadata["is_final"] = true`, `metadata["error"]` set to the status code and body excerpt, and `content` set to a user-facing error message.

#### Scenario: WHEN the streaming request exceeds the configured `DEEPSEEK_

- **THEN** WHEN the streaming request exceeds the configured `DEEPSEEK_STREAM_TIMEOUT` (default 60 seconds for time-to-first-chunk, 180 seconds for total stream duration), THE DeepSeek_Streaming_Client SHALL abort the HTTP request and yield exactly one terminal `AIResponse` with `metadata["finish_reason"] = "timeout"`, `metadata["is_final"] = true`, and any content received so far reflected in the cumulative stream.

### Requirement: AIService Streaming Interface Compatibility

The system SHALL support: As a maintainer of `RAGService`, I want `DeepSeekAIService.generate_response_stream` to expose the same async generator contract as the previous `GeminiProvider` implementation, so that the RAG streaming pipeline does not require changes to call sites.

#### Scenario: THE AIService_Streaming_API SHALL be implemented by `DeepSee

- **THEN** THE AIService_Streaming_API SHALL be implemented by `DeepSeekAIService.generate_response_stream` as an `async def` that returns `AsyncGenerator[AIResponse, None]`.

#### Scenario: THE AIService_Streaming_API SHALL accept the keyword argumen

- **THEN** THE AIService_Streaming_API SHALL accept the keyword arguments `messages: List[Dict[str, str]]`, `context: Optional[str]`, `temperature: float`, `max_tokens: int`, and `preferred_provider: Optional[Any]`.

#### Scenario: WHEN `context` is provided and the last message has role `"u

- **THEN** WHEN `context` is provided and the last message has role `"user"`, THE AIService_Streaming_API SHALL append the context to the final user message content before sending the request to DeepSeek, using the same concatenation format (`"\n\nAdditional context:\n"`) as the non-streaming `DeepSeekAIService.generate_response`.

#### Scenario: THE AIService_Streaming_API SHALL yield at least one `AIResp

- **THEN** THE AIService_Streaming_API SHALL yield at least one `AIResponse` for every invocation that does not raise, even when the model returns no content (in which case exactly one terminal chunk with `content=""` is yielded).

#### Scenario: THE AIService_Streaming_API SHALL set `AIResponse.provider =

- **THEN** THE AIService_Streaming_API SHALL set `AIResponse.provider = "deepseek"` and `AIResponse.model` equal to the configured DeepSeek model name on every yielded chunk.

#### Scenario: THE AIService_Streaming_API SHALL include `chunk_index` (zer

- **THEN** THE AIService_Streaming_API SHALL include `chunk_index` (zero-based, monotonically increasing) and `is_final` keys in every yielded `AIResponse.metadata`.

### Requirement: RAG Streaming Pipeline Integration

The system SHALL support: As a chat user, I want RAG-powered answers to stream token-by-token after citations appear, so that I see the answer progressively rather than waiting for the full response.

#### Scenario: WHEN `RAGService.generate_response_stream` is invoked with a

- **THEN** WHEN `RAGService.generate_response_stream` is invoked with a query that triggers document retrieval, THE Chat_Backend SHALL complete vector search and knowledge-graph retrieval before yielding the first content chunk.

#### Scenario: WHEN retrieval completes and at least one citation is produc

- **THEN** WHEN retrieval completes and at least one citation is produced, THE Chat_Backend SHALL yield a `RAGStreamingChunk` with `is_final=false`, the full citation list populated, and `content=""`, before any content chunk is yielded.

#### Scenario: WHEN `RAGService` calls `self.ai_service.generate_response_s

- **THEN** WHEN `RAGService` calls `self.ai_service.generate_response_stream`, THE Chat_Backend SHALL forward every yielded `AIResponse` as a `RAGStreamingChunk` with `content` equal to the delta and `is_final=false`, preserving arrival order.

#### Scenario: WHEN the underlying AIService_Streaming_API yields its termi

- **THEN** WHEN the underlying AIService_Streaming_API yields its terminal chunk, THE Chat_Backend SHALL yield exactly one final `RAGStreamingChunk` with `is_final=true`, `cumulative_tokens` set to the cumulative token count reported by the provider (or estimated from characters if unavailable), and complete metadata including `rag_enabled`, `confidence_score`, `processing_time_ms`, `search_results_count`, and `fallback_used`.

#### Scenario: WHERE retrieval produces zero citations, THE Chat_Backend SH

- **THEN** WHERE retrieval produces zero citations, THE Chat_Backend SHALL stream a fallback response via `_generate_fallback_response_stream` and SHALL set `fallback_used=true` in the final `RAGStreamingChunk.metadata`.

### Requirement: WebSocket Streaming Protocol Preservation

The system SHALL support: As a frontend developer, I want the browser-facing WebSocket streaming message contract to remain byte-compatible with the existing implementation, so that no frontend changes are required.

#### Scenario: WHEN a user sends a `chat_message` with `streaming=true` (th

- **THEN** WHEN a user sends a `chat_message` with `streaming=true` (the default), THE Chat_Backend SHALL send exactly one `streaming_start` JSON message containing the citations array before any `streaming_chunk` message.

#### Scenario: WHEN a content delta is received from the AIService_Streamin

- **THEN** WHEN a content delta is received from the AIService_Streaming_API, THE Chat_Backend SHALL send exactly one `streaming_chunk` JSON message per non-empty delta, each containing `content` (the delta text) and `chunk_index` (zero-based monotonically increasing).

#### Scenario: WHEN the streaming response completes successfully, THE Chat

- **THEN** WHEN the streaming response completes successfully, THE Chat_Backend SHALL send exactly one `streaming_complete` JSON message containing the metadata object with `rag_enabled`, `streaming=true`, `confidence_score`, `processing_time_ms`, `search_results_count`, `fallback_used`, `tokens_used`, `request_id`, and `chunk_count`.

#### Scenario: IF the streaming response fails with a recoverable error bef

- **GIVEN** the streaming response fails with a recoverable error before completion
- **THEN** IF the streaming response fails with a recoverable error before completion, THEN THE Chat_Backend SHALL send exactly one `streaming_error` JSON message with `recoverable=true` and SHALL attempt a non-streaming fallback via `handle_non_streaming_rag_response`.

#### Scenario: THE Chat_Backend SHALL NOT send a `streaming_complete` messa

- **THEN** THE Chat_Backend SHALL NOT send a `streaming_complete` message after a `streaming_error` message for the same request.

### Requirement: Graceful Fallback to Non-Streaming

The system SHALL support: As a chat user, I want the system to fall back to a non-streaming response when streaming fails or is disabled, so that I still receive an answer rather than an error.

#### Scenario: WHILE the Error_Rate_Tracker reports `streaming_enabled=fals

- **THEN** WHILE the Error_Rate_Tracker reports `streaming_enabled=false`, THE AIService_Streaming_API SHALL call the non-streaming `generate_response` and yield exactly one `AIResponse` containing the full response with `metadata["streaming_fallback"] = true` and `metadata["is_final"] = true`.

#### Scenario: WHILE the Circuit_Breaker is in the `OPEN` state, THE AIServ

- **THEN** WHILE the Circuit_Breaker is in the `OPEN` state, THE AIService_Streaming_API SHALL yield exactly one terminal `AIResponse` with a user-facing unavailability message, `metadata["error_type"] = "circuit_breaker"`, and SHALL NOT issue any HTTP request to DeepSeek.

#### Scenario: IF an exception is raised after any `streaming_chunk` has al

- **GIVEN** an exception is raised after any `streaming_chunk` has already been sent to the client
- **THEN** IF an exception is raised after any `streaming_chunk` has already been sent to the client, THEN THE Chat_Backend SHALL send a `streaming_error` message with `recoverable=true` and SHALL call `handle_non_streaming_rag_response` to generate a complete non-streaming response as a new assistant message.

#### Scenario: IF an exception is raised before any `streaming_chunk` has b

- **GIVEN** an exception is raised before any `streaming_chunk` has been sent
- **THEN** IF an exception is raised before any `streaming_chunk` has been sent, THEN THE Chat_Backend SHALL call `handle_non_streaming_rag_response` directly without first sending `streaming_start` or `streaming_error`.

#### Scenario: WHEN a non-streaming fallback completes successfully, THE Ch

- **THEN** WHEN a non-streaming fallback completes successfully, THE Chat_Backend SHALL send the full response as a single `response` message with `metadata.streaming = false`.

### Requirement: Error Handling and Classification

The system SHALL support: As an operator, I want DeepSeek streaming errors to be classified, surfaced with user-friendly messages, and counted for circuit-breaker and error-rate tracking, so that failures cause graceful degradation instead of cascading outages.

#### Scenario: WHEN the DeepSeek_Streaming_Client receives HTTP 401 or 403,

- **THEN** WHEN the DeepSeek_Streaming_Client receives HTTP 401 or 403, THE Chat_Backend SHALL classify the error as `authentication`, record a failure in the Circuit_Breaker and Error_Rate_Tracker, and yield a terminal `AIResponse` with the user-facing authentication error message.

#### Scenario: WHEN the DeepSeek_Streaming_Client receives HTTP 429, THE Ch

- **THEN** WHEN the DeepSeek_Streaming_Client receives HTTP 429, THE Chat_Backend SHALL classify the error as `rate_limit`, record a failure, and yield a terminal `AIResponse` with `metadata["retry_after_seconds"]` set from the response `Retry-After` header when present or 60 by default.

#### Scenario: WHEN the DeepSeek_Streaming_Client receives HTTP 5xx, THE Ch

- **THEN** WHEN the DeepSeek_Streaming_Client receives HTTP 5xx, THE Chat_Backend SHALL classify the error as `model_overloaded`, record a failure, and yield a terminal `AIResponse` with `metadata["retry_after_seconds"] = 30`.

#### Scenario: IF the HTTP connection to DeepSeek drops mid-stream, THEN TH

- **GIVEN** the HTTP connection to DeepSeek drops mid-stream
- **THEN** IF the HTTP connection to DeepSeek drops mid-stream, THEN THE Chat_Backend SHALL classify the error as `network_error`, preserve any content already yielded to the client, and yield exactly one terminal `AIResponse` with `metadata["is_final"] = true` and `metadata["error"]` set to the connection error.

#### Scenario: IF an SSE_Chunk contains `"finish_reason": "content_filter"`

- **GIVEN** an SSE_Chunk contains `"finish_reason": "content_filter"`
- **THEN** IF an SSE_Chunk contains `"finish_reason": "content_filter"`, THEN THE Chat_Backend SHALL classify the error as `content_blocked`, yield a terminal `AIResponse` with the user-facing content-blocked message, and record a success (not failure) in the Circuit_Breaker because the API call itself succeeded.

#### Scenario: WHEN any streaming invocation completes without error, THE C

- **THEN** WHEN any streaming invocation completes without error, THE Chat_Backend SHALL record a success in both the Circuit_Breaker and Error_Rate_Tracker.

### Requirement: Cancellation and Partial Response Handling

The system SHALL support: As a chat user, I want an in-flight streamed response to stop server-side work when I disconnect or my browser tab closes, so that server resources and DeepSeek API quota are not wasted.

#### Scenario: WHILE a streaming response is in progress, THE Chat_Backend

- **THEN** WHILE a streaming response is in progress, THE Chat_Backend SHALL check `manager.is_connected(connection_id)` before sending each `streaming_chunk` and SHALL abort the streaming loop when the check returns `false`.

#### Scenario: WHEN the streaming loop is aborted due to client disconnect,

- **THEN** WHEN the streaming loop is aborted due to client disconnect, THE Chat_Backend SHALL cancel the underlying DeepSeek HTTP request by closing the response stream, SHALL NOT send any further WebSocket messages for the aborted request, and SHALL log a structured INFO event with `connection_id`, `request_id`, `chunks_sent`, and `reason="client_disconnect"`.

#### Scenario: WHEN a streaming response is aborted due to client disconnec

- **THEN** WHEN a streaming response is aborted due to client disconnect, THE Chat_Backend SHALL persist the partial assistant response (the concatenation of content chunks sent so far) to the conversation history with a `metadata["aborted"] = true` flag.

#### Scenario: IF the DeepSeek HTTP response yields a final `[DONE]` marker

- **GIVEN** the DeepSeek HTTP response yields a final `[DONE]` marker without ever emitting a non-empty delta
- **THEN** IF the DeepSeek HTTP response yields a final `[DONE]` marker without ever emitting a non-empty delta, THEN THE Chat_Backend SHALL send a single `streaming_chunk` with empty content suppressed (no `streaming_chunk` sent) followed by `streaming_complete` with `chunk_count=0` and `content=""` in the persisted assistant message.

### Requirement: Frontend Rendering Compatibility

The system SHALL support: As a chat user, I want streamed tokens to appear incrementally in the chat UI without layout jitter, without requiring any changes to the frontend to support DeepSeek, so that the streaming experience is visually identical to the previous Gemini implementation.

#### Scenario: THE Chat_Backend SHALL emit `streaming_start`, `streaming_ch

- **THEN** THE Chat_Backend SHALL emit `streaming_start`, `streaming_chunk`, `streaming_complete`, and `streaming_error` JSON payloads with exactly the same field names and shapes used by the existing frontend handlers registered in `static/js/chat.js` and `static/js/unified_interface.js`.

#### Scenario: THE Chat_Backend SHALL NOT include any DeepSeek-specific fie

- **THEN** THE Chat_Backend SHALL NOT include any DeepSeek-specific fields at the top level of WebSocket messages; provider-specific diagnostic data SHALL only appear nested under `metadata`.

#### Scenario: WHEN markdown-containing tokens are streamed, THE Chat_Backe

- **THEN** WHEN markdown-containing tokens are streamed, THE Chat_Backend SHALL forward byte-level deltas without buffering across markdown boundaries (no server-side markdown-aware chunking) so that the frontend's existing incremental renderer continues to work without modification.

### Requirement: Observability and Metrics

The system SHALL support: As an operator, I want streaming requests to be observable via structured logs and metrics, so that I can monitor latency, throughput, and failure rates in production.

#### Scenario: WHEN a streaming request begins, THE Chat_Backend SHALL log

- **THEN** WHEN a streaming request begins, THE Chat_Backend SHALL log a structured INFO event with fields `event="deepseek_stream_start"`, `call_id` (8-char UUID prefix), `model`, `prompt_chars`, `message_count`, `temperature`, `max_tokens`.

#### Scenario: WHEN the first non-empty delta is received, THE Chat_Backend

- **THEN** WHEN the first non-empty delta is received, THE Chat_Backend SHALL record a `time_to_first_token_ms` metric measured from request start and log it at INFO with `event="deepseek_stream_first_token"`, `call_id`, `time_to_first_token_ms`.

#### Scenario: WHEN a streaming request completes successfully, THE Chat_Ba

- **THEN** WHEN a streaming request completes successfully, THE Chat_Backend SHALL log a structured INFO event with `event="deepseek_stream_complete"`, `call_id`, `duration_ms`, `chunks_received`, `prompt_tokens`, `completion_tokens`, `total_tokens`, and `finish_reason`.

#### Scenario: WHEN a streaming request fails, THE Chat_Backend SHALL log a

- **THEN** WHEN a streaming request fails, THE Chat_Backend SHALL log a structured ERROR event with `event="deepseek_stream_error"`, `call_id`, `duration_ms`, `chunks_received_before_error`, `error_type`, and `error_message` (truncated to 500 characters).

#### Scenario: THE Chat_Backend SHALL expose aggregate streaming metrics vi

- **THEN** THE Chat_Backend SHALL expose aggregate streaming metrics via `DeepSeekAIService.get_provider_status()` including `streaming_total_calls`, `streaming_successful_calls`, `streaming_failed_calls`, `streaming_avg_duration_ms`, `streaming_avg_time_to_first_token_ms`, and `streaming_avg_chunks_per_response`.

#### Scenario: WHERE the existing `AIService.get_performance_stats()` endpo

- **THEN** WHERE the existing `AIService.get_performance_stats()` endpoint is queried, THE Chat_Backend SHALL include circuit-breaker state and error-rate tracker state in the returned payload for the DeepSeek provider, matching the structure previously returned for the Gemini provider.

### Requirement: Configuration and Feature Flag

The system SHALL support: As an operator, I want to enable, disable, and tune DeepSeek streaming via environment variables, so that I can roll out the change safely and disable it without a code deploy if issues arise.

#### Scenario: THE Chat_Backend SHALL read the environment variable `DEEPSE

- **THEN** THE Chat_Backend SHALL read the environment variable `DEEPSEEK_STREAMING_ENABLED` (default `"true"`) at service initialization and SHALL expose its parsed boolean value via `DeepSeekAIService.streaming_enabled_config`.

#### Scenario: WHILE `DEEPSEEK_STREAMING_ENABLED` is `"false"`, THE AIServi

- **THEN** WHILE `DEEPSEEK_STREAMING_ENABLED` is `"false"`, THE AIService_Streaming_API SHALL behave exactly as the Streaming_Disabled_Fallback (call `generate_response` and yield a single terminal chunk) regardless of Error_Rate_Tracker or Circuit_Breaker state.

#### Scenario: THE Chat_Backend SHALL read the environment variable `DEEPSE

- **THEN** THE Chat_Backend SHALL read the environment variable `DEEPSEEK_STREAM_TIMEOUT` (default `60.0`) as the per-request time-to-first-chunk timeout in seconds.

#### Scenario: THE Chat_Backend SHALL read the environment variable `DEEPSE

- **THEN** THE Chat_Backend SHALL read the environment variable `DEEPSEEK_STREAM_TOTAL_TIMEOUT` (default `180.0`) as the maximum total streaming duration in seconds.

#### Scenario: WHERE `DEEPSEEK_STREAM_INCLUDE_USAGE` is `"true"` (default `

- **THEN** WHERE `DEEPSEEK_STREAM_INCLUDE_USAGE` is `"true"` (default `"true"`), THE DeepSeek_Streaming_Client SHALL include `"stream_options": {"include_usage": true}` in the request body so that the final SSE_Chunk contains a `usage` object.

### Requirement: Backward Compatibility

The system SHALL support: As a maintainer, I want the chat system to still work when `DEEPSEEK_API_KEY` is unset and `GEMINI_API_KEY` is set (the legacy fallback path in `get_ai_service`), so that the streaming feature does not regress the existing Gemini code path.

#### Scenario: WHEN `DEEPSEEK_API_KEY` is empty and `GEMINI_API_KEY` is set

- **THEN** WHEN `DEEPSEEK_API_KEY` is empty and `GEMINI_API_KEY` is set, THE Chat_Backend SHALL initialize the existing Gemini `AIService` and SHALL use its existing streaming implementation unchanged.

#### Scenario: WHEN `DEEPSEEK_API_KEY` is set, THE Chat_Backend SHALL initi

- **THEN** WHEN `DEEPSEEK_API_KEY` is set, THE Chat_Backend SHALL initialize `DeepSeekAIService` with streaming enabled per Requirement 10 and SHALL NOT initialize the Gemini provider.

#### Scenario: THE `RAGService` and WebSocket handlers SHALL treat both `AI

- **THEN** THE `RAGService` and WebSocket handlers SHALL treat both `AIService` (Gemini) and `DeepSeekAIService` as interchangeable implementations of the AIService_Streaming_API contract defined in Requirement 2.

### Requirement: Unit and Integration Test Coverage

The system SHALL support: As a maintainer, I want property-based and example-based tests for the SSE parser and example-based tests for the end-to-end streaming flow, so that regressions are caught before deployment.

#### Scenario: WHEN the SSE parser test suite runs, THE test suite SHALL ve

- **THEN** WHEN the SSE parser test suite runs, THE test suite SHALL verify that parsing an arbitrary valid SSE stream (generated by splitting a concatenated sequence of DeepSeek-format data frames at arbitrary byte boundaries and then reassembling in order) yields deltas whose concatenation equals the concatenation of the original `delta.content` fields (round-trip property).

#### Scenario: WHEN the SSE parser test suite runs, THE test suite SHALL ve

- **THEN** WHEN the SSE parser test suite runs, THE test suite SHALL verify that injecting malformed JSON on any single line does not prevent subsequent valid lines from being parsed (robustness property).

#### Scenario: WHEN the integration test suite runs with a mocked DeepSeek

- **THEN** WHEN the integration test suite runs with a mocked DeepSeek HTTP server, THE test suite SHALL verify that a simulated stream of 10 chunks produces exactly one `streaming_start`, 10 `streaming_chunk`, and one `streaming_complete` WebSocket message in that order.

#### Scenario: WHEN the integration test suite runs with a mocked DeepSeek

- **THEN** WHEN the integration test suite runs with a mocked DeepSeek HTTP server that returns HTTP 500, THE test suite SHALL verify that the client receives exactly one `streaming_error` followed by a non-streaming fallback `response` message.

#### Scenario: WHEN the integration test suite runs with a simulated client

- **THEN** WHEN the integration test suite runs with a simulated client disconnect after chunk 5 of 10, THE test suite SHALL verify that no further WebSocket messages are sent and that the underlying HTTP request to the mocked DeepSeek server is closed within 1 second of the disconnect.
