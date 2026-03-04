# Requirements Document

## Introduction

This feature addresses critical performance issues with the Gemini AI API integration and implements streaming responses to improve user experience. The KG-guided retrieval pipeline is working correctly (finding concepts and retrieving chunks), but API requests are timing out due to slow Gemini API calls exceeding the 30-second limit. This spec covers profiling Gemini performance, optimizing API calls, implementing streaming responses, and completing the hybrid search fallback mechanism.

## Glossary

- **Gemini_Provider**: The Google Gemini AI provider class that handles text generation and embeddings via the Gemini API
- **AI_Service**: The main AI service that wraps the Gemini provider and provides a unified interface for AI operations
- **RAG_Service**: The Retrieval-Augmented Generation service that combines document search with AI generation
- **Chat_Router**: The FastAPI router handling WebSocket-based chat communication
- **Streaming_Response**: A response mechanism that sends partial content incrementally as it's generated
- **Hybrid_Search_Engine**: The search engine combining vector similarity with keyword matching for document retrieval
- **KG_Retrieval_Service**: The Knowledge Graph-guided retrieval service using Neo4j for precise chunk retrieval
- **Connection_Manager**: The WebSocket connection manager handling real-time chat sessions

## Requirements

### Requirement 1: Gemini Performance Profiling

**User Story:** As a developer, I want to profile and diagnose Gemini API performance issues, so that I can identify the root cause of slow response times.

#### Acceptance Criteria

1. WHEN a Gemini API call is made, THE Gemini_Provider SHALL log detailed timing metrics including request preparation time, API call duration, and response processing time
2. WHEN profiling is enabled, THE AI_Service SHALL capture and report the time spent in each phase of the generate_response method
3. THE Gemini_Provider SHALL log the prompt size (character count and estimated tokens) for each API call
4. WHEN an API call exceeds 10 seconds, THE Gemini_Provider SHALL log a warning with the call parameters and timing breakdown
5. THE AI_Service SHALL expose a method to retrieve performance statistics including average response time, p95 latency, and timeout count

### Requirement 2: Gemini API Optimization

**User Story:** As a user, I want Gemini API calls to complete within 10-15 seconds, so that my chat requests don't time out.

#### Acceptance Criteria

1. THE Gemini_Provider SHALL configure optimal generation parameters to reduce latency (temperature, top_p, top_k, max_output_tokens)
2. WHEN generating responses, THE Gemini_Provider SHALL use the most efficient model variant (gemini-2.5-flash) for chat responses
3. THE Gemini_Provider SHALL implement request timeout handling with configurable timeout duration (default 25 seconds)
4. IF a Gemini API call times out, THEN THE AI_Service SHALL return a graceful error response rather than raising an exception
5. THE Gemini_Provider SHALL limit prompt context size to prevent excessive token processing (max 6000 characters for context)
6. WHEN building prompts, THE Gemini_Provider SHALL truncate conversation history to the most recent 3 messages to reduce input size

### Requirement 3: Streaming Response Infrastructure

**User Story:** As a user, I want to see partial responses as they're generated, so that I perceive faster response times.

#### Acceptance Criteria

1. THE Gemini_Provider SHALL implement a generate_response_stream method that yields content chunks as they're received
2. WHEN streaming is enabled, THE Gemini_Provider SHALL use the Gemini streaming API (generate_content_async with stream=True)
3. THE AI_Service SHALL expose a generate_response_stream method that wraps the provider's streaming capability
4. WHEN streaming, THE AI_Service SHALL yield AIResponse objects with partial content and cumulative token counts
5. IF streaming fails mid-response, THEN THE AI_Service SHALL yield an error chunk and terminate the stream gracefully

### Requirement 4: WebSocket Streaming Integration

**User Story:** As a user, I want chat responses to stream in real-time through the WebSocket connection, so that I see content appearing progressively.

#### Acceptance Criteria

1. WHEN handling a chat message, THE Chat_Router SHALL support streaming responses via WebSocket
2. THE Connection_Manager SHALL implement a send_streaming_message method that sends partial response chunks
3. WHEN streaming is active, THE Chat_Router SHALL send 'response_chunk' message types with incremental content
4. WHEN streaming completes, THE Chat_Router SHALL send a 'response_complete' message with final metadata
5. IF the user disconnects during streaming, THEN THE Chat_Router SHALL cancel the ongoing generation
6. THE Chat_Router SHALL send a 'streaming_start' message before beginning to stream content

### Requirement 5: RAG Service Streaming Support

**User Story:** As a developer, I want the RAG service to support streaming responses, so that document-aware responses can be streamed to users.

#### Acceptance Criteria

1. THE RAG_Service SHALL implement a generate_response_stream method that yields partial responses with citations
2. WHEN streaming, THE RAG_Service SHALL first complete document search, then stream the AI generation
3. THE RAG_Service SHALL yield citation information in the first chunk before streaming content
4. WHEN streaming completes, THE RAG_Service SHALL yield a final chunk with complete metadata (confidence score, processing time)
5. IF document search fails, THEN THE RAG_Service SHALL fall back to streaming a general AI response

### Requirement 6: KG-Guided Retrieval Verification

**User Story:** As a user, I want to verify that KG-guided retrieval correctly returns the Chelsea AI Ventures quote, so that I can confirm the retrieval pipeline is working.

#### Acceptance Criteria

1. WHEN querying for "Chelsea AI Ventures", THE KG_Retrieval_Service SHALL return chunks containing the relevant quote
2. THE RAG_Service SHALL correctly pass KG-retrieved chunks to the AI generation step
3. WHEN KG retrieval succeeds, THE RAG_Service SHALL include KG metadata in the response (concepts matched, retrieval source)
4. THE Chat_Router SHALL display KG retrieval metadata in the response when available

### Requirement 7: Hybrid Search Keyword Implementation

**User Story:** As a developer, I want the hybrid search keyword component to be implemented, so that it provides a fallback when KG retrieval fails.

#### Acceptance Criteria

1. THE Hybrid_Search_Engine SHALL implement the _keyword_search method using TF-IDF vectorization
2. WHEN performing keyword search, THE Hybrid_Search_Engine SHALL index document content and return matching chunks
3. THE Hybrid_Search_Engine SHALL combine keyword scores with vector scores using configurable weights
4. IF vector search returns no results, THEN THE Hybrid_Search_Engine SHALL return keyword search results as fallback
5. THE Hybrid_Search_Engine SHALL cache TF-IDF vectors for indexed documents to improve search performance

### Requirement 8: Error Handling and Graceful Degradation

**User Story:** As a user, I want the system to handle errors gracefully, so that I receive helpful responses even when components fail.

#### Acceptance Criteria

1. IF Gemini API fails, THEN THE AI_Service SHALL return a user-friendly error message explaining the issue
2. WHEN the API timeout is exceeded, THE Chat_Router SHALL send a timeout notification to the user
3. THE RAG_Service SHALL implement circuit breaker pattern for Gemini API calls to prevent cascade failures
4. IF streaming fails, THEN THE Chat_Router SHALL attempt a non-streaming fallback response
5. THE AI_Service SHALL track error rates and temporarily disable streaming if error rate exceeds 50%
