## Purpose

This feature addresses critical performance issues with the Gemini AI API integration and implements streaming responses to improve user experience. The KG-guided retrieval pipeline is working correctly (finding concepts and retrieving chunks), but API requests are timing out due to slow Gemini API calls exceeding the 30-second limit. This spec covers profiling Gemini performance, optimizing API calls, implementing streaming responses, and completing the hybrid search fallback mechanism.


### Key Terms
- **Gemini_Provider**: The Google Gemini AI provider class that handles text generation and embeddings via the Gemini API
- **AI_Service**: The main AI service that wraps the Gemini provider and provides a unified interface for AI operations
- **RAG_Service**: The Retrieval-Augmented Generation service that combines document search with AI generation
- **Chat_Router**: The FastAPI router handling WebSocket-based chat communication
- **Streaming_Response**: A response mechanism that sends partial content incrementally as it's generated
- **Hybrid_Search_Engine**: The search engine combining vector similarity with keyword matching for document retrieval
- **KG_Retrieval_Service**: The Knowledge Graph-guided retrieval service using Neo4j for precise chunk retrieval
- **Connection_Manager**: The WebSocket connection manager handling real-time chat sessions

## Requirements

### Requirement: Gemini Performance Profiling

The system SHALL support: As a developer, I want to profile and diagnose Gemini API performance issues, so that I can identify the root cause of slow response times.

#### Scenario: WHEN a Gemini API call is made, THE Gemini_Provider SHALL lo

- **THEN** WHEN a Gemini API call is made, THE Gemini_Provider SHALL log detailed timing metrics including request preparation time, API call duration, and response processing time

#### Scenario: WHEN profiling is enabled, THE AI_Service SHALL capture and

- **THEN** WHEN profiling is enabled, THE AI_Service SHALL capture and report the time spent in each phase of the generate_response method

#### Scenario: THE Gemini_Provider SHALL log the prompt size (character cou

- **THEN** THE Gemini_Provider SHALL log the prompt size (character count and estimated tokens) for each API call

#### Scenario: WHEN an API call exceeds 10 seconds, THE Gemini_Provider SHA

- **THEN** WHEN an API call exceeds 10 seconds, THE Gemini_Provider SHALL log a warning with the call parameters and timing breakdown

#### Scenario: THE AI_Service SHALL expose a method to retrieve performance

- **THEN** THE AI_Service SHALL expose a method to retrieve performance statistics including average response time, p95 latency, and timeout count

### Requirement: Gemini API Optimization

The system SHALL support: As a user, I want Gemini API calls to complete within 10-15 seconds, so that my chat requests don't time out.

#### Scenario: THE Gemini_Provider SHALL configure optimal generation param

- **THEN** THE Gemini_Provider SHALL configure optimal generation parameters to reduce latency (temperature, top_p, top_k, max_output_tokens)

#### Scenario: WHEN generating responses, THE Gemini_Provider SHALL use the

- **THEN** WHEN generating responses, THE Gemini_Provider SHALL use the most efficient model variant (gemini-2.5-flash) for chat responses

#### Scenario: THE Gemini_Provider SHALL implement request timeout handling

- **THEN** THE Gemini_Provider SHALL implement request timeout handling with configurable timeout duration (default 25 seconds)

#### Scenario: IF a Gemini API call times out, THEN THE AI_Service SHALL re

- **GIVEN** a Gemini API call times out
- **THEN** IF a Gemini API call times out, THEN THE AI_Service SHALL return a graceful error response rather than raising an exception

#### Scenario: THE Gemini_Provider SHALL limit prompt context size to preve

- **THEN** THE Gemini_Provider SHALL limit prompt context size to prevent excessive token processing (max 6000 characters for context)

#### Scenario: WHEN building prompts, THE Gemini_Provider SHALL truncate co

- **THEN** WHEN building prompts, THE Gemini_Provider SHALL truncate conversation history to the most recent 3 messages to reduce input size

### Requirement: Streaming Response Infrastructure

The system SHALL support: As a user, I want to see partial responses as they're generated, so that I perceive faster response times.

#### Scenario: THE Gemini_Provider SHALL implement a generate_response_stre

- **THEN** THE Gemini_Provider SHALL implement a generate_response_stream method that yields content chunks as they're received

#### Scenario: WHEN streaming is enabled, THE Gemini_Provider SHALL use the

- **THEN** WHEN streaming is enabled, THE Gemini_Provider SHALL use the Gemini streaming API (generate_content_async with stream=True)

#### Scenario: THE AI_Service SHALL expose a generate_response_stream metho

- **THEN** THE AI_Service SHALL expose a generate_response_stream method that wraps the provider's streaming capability

#### Scenario: WHEN streaming, THE AI_Service SHALL yield AIResponse object

- **THEN** WHEN streaming, THE AI_Service SHALL yield AIResponse objects with partial content and cumulative token counts

#### Scenario: IF streaming fails mid-response, THEN THE AI_Service SHALL y

- **GIVEN** streaming fails mid-response
- **THEN** IF streaming fails mid-response, THEN THE AI_Service SHALL yield an error chunk and terminate the stream gracefully

### Requirement: WebSocket Streaming Integration

The system SHALL support: As a user, I want chat responses to stream in real-time through the WebSocket connection, so that I see content appearing progressively.

#### Scenario: WHEN handling a chat message, THE Chat_Router SHALL support

- **THEN** WHEN handling a chat message, THE Chat_Router SHALL support streaming responses via WebSocket

#### Scenario: THE Connection_Manager SHALL implement a send_streaming_mess

- **THEN** THE Connection_Manager SHALL implement a send_streaming_message method that sends partial response chunks

#### Scenario: WHEN streaming is active, THE Chat_Router SHALL send 'respon

- **THEN** WHEN streaming is active, THE Chat_Router SHALL send 'response_chunk' message types with incremental content

#### Scenario: WHEN streaming completes, THE Chat_Router SHALL send a 'resp

- **THEN** WHEN streaming completes, THE Chat_Router SHALL send a 'response_complete' message with final metadata

#### Scenario: IF the user disconnects during streaming, THEN THE Chat_Rout

- **GIVEN** the user disconnects during streaming
- **THEN** IF the user disconnects during streaming, THEN THE Chat_Router SHALL cancel the ongoing generation

#### Scenario: THE Chat_Router SHALL send a 'streaming_start' message befor

- **THEN** THE Chat_Router SHALL send a 'streaming_start' message before beginning to stream content

### Requirement: RAG Service Streaming Support

The system SHALL support: As a developer, I want the RAG service to support streaming responses, so that document-aware responses can be streamed to users.

#### Scenario: THE RAG_Service SHALL implement a generate_response_stream m

- **THEN** THE RAG_Service SHALL implement a generate_response_stream method that yields partial responses with citations

#### Scenario: WHEN streaming, THE RAG_Service SHALL first complete documen

- **THEN** WHEN streaming, THE RAG_Service SHALL first complete document search, then stream the AI generation

#### Scenario: THE RAG_Service SHALL yield citation information in the firs

- **THEN** THE RAG_Service SHALL yield citation information in the first chunk before streaming content

#### Scenario: WHEN streaming completes, THE RAG_Service SHALL yield a fina

- **THEN** WHEN streaming completes, THE RAG_Service SHALL yield a final chunk with complete metadata (confidence score, processing time)

#### Scenario: IF document search fails, THEN THE RAG_Service SHALL fall ba

- **GIVEN** document search fails
- **THEN** IF document search fails, THEN THE RAG_Service SHALL fall back to streaming a general AI response

### Requirement: KG-Guided Retrieval Verification

The system SHALL support: As a user, I want to verify that KG-guided retrieval correctly returns the Chelsea AI Ventures quote, so that I can confirm the retrieval pipeline is working.

#### Scenario: WHEN querying for "Chelsea AI Ventures", THE KG_Retrieval_Se

- **THEN** WHEN querying for "Chelsea AI Ventures", THE KG_Retrieval_Service SHALL return chunks containing the relevant quote

#### Scenario: THE RAG_Service SHALL correctly pass KG-retrieved chunks to

- **THEN** THE RAG_Service SHALL correctly pass KG-retrieved chunks to the AI generation step

#### Scenario: WHEN KG retrieval succeeds, THE RAG_Service SHALL include KG

- **THEN** WHEN KG retrieval succeeds, THE RAG_Service SHALL include KG metadata in the response (concepts matched, retrieval source)

#### Scenario: THE Chat_Router SHALL display KG retrieval metadata in the r

- **THEN** THE Chat_Router SHALL display KG retrieval metadata in the response when available

### Requirement: Hybrid Search Keyword Implementation

The system SHALL support: As a developer, I want the hybrid search keyword component to be implemented, so that it provides a fallback when KG retrieval fails.

#### Scenario: THE Hybrid_Search_Engine SHALL implement the _keyword_search

- **THEN** THE Hybrid_Search_Engine SHALL implement the _keyword_search method using TF-IDF vectorization

#### Scenario: WHEN performing keyword search, THE Hybrid_Search_Engine SHA

- **THEN** WHEN performing keyword search, THE Hybrid_Search_Engine SHALL index document content and return matching chunks

#### Scenario: THE Hybrid_Search_Engine SHALL combine keyword scores with v

- **THEN** THE Hybrid_Search_Engine SHALL combine keyword scores with vector scores using configurable weights

#### Scenario: IF vector search returns no results, THEN THE Hybrid_Search_

- **GIVEN** vector search returns no results
- **THEN** IF vector search returns no results, THEN THE Hybrid_Search_Engine SHALL return keyword search results as fallback

#### Scenario: THE Hybrid_Search_Engine SHALL cache TF-IDF vectors for inde

- **THEN** THE Hybrid_Search_Engine SHALL cache TF-IDF vectors for indexed documents to improve search performance

### Requirement: Error Handling and Graceful Degradation

The system SHALL support: As a user, I want the system to handle errors gracefully, so that I receive helpful responses even when components fail.

#### Scenario: IF Gemini API fails, THEN THE AI_Service SHALL return a user

- **GIVEN** Gemini API fails
- **THEN** IF Gemini API fails, THEN THE AI_Service SHALL return a user-friendly error message explaining the issue

#### Scenario: WHEN the API timeout is exceeded, THE Chat_Router SHALL send

- **THEN** WHEN the API timeout is exceeded, THE Chat_Router SHALL send a timeout notification to the user

#### Scenario: THE RAG_Service SHALL implement circuit breaker pattern for

- **THEN** THE RAG_Service SHALL implement circuit breaker pattern for Gemini API calls to prevent cascade failures

#### Scenario: IF streaming fails, THEN THE Chat_Router SHALL attempt a non

- **GIVEN** streaming fails
- **THEN** IF streaming fails, THEN THE Chat_Router SHALL attempt a non-streaming fallback response

#### Scenario: THE AI_Service SHALL track error rates and temporarily disab

- **THEN** THE AI_Service SHALL track error rates and temporarily disable streaming if error rate exceeds 50%
