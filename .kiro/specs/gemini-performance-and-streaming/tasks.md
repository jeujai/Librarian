# Implementation Plan: Gemini Performance and Streaming

## Overview

This implementation plan addresses Gemini API performance issues and adds streaming response support. Tasks are ordered to deliver value incrementally: first profiling to understand the problem, then optimization, then streaming infrastructure, and finally hybrid search fallback.

## Tasks

- [x] 1. Implement Gemini Performance Profiling
  - [x] 1.1 Add performance metrics dataclasses to ai_service.py
    - Create `APICallMetrics` and `PerformanceStats` dataclasses
    - Add timing fields for request prep, API call, and response processing
    - _Requirements: 1.1, 1.2_
  
  - [x] 1.2 Implement metrics capture in GeminiProvider
    - Add timing instrumentation around API calls
    - Log prompt size (chars and estimated tokens) for each call
    - Log warnings for calls exceeding 10 seconds
    - _Requirements: 1.1, 1.3, 1.4_
  
  - [x] 1.3 Add performance statistics aggregation to AIService
    - Implement `get_performance_stats()` method
    - Calculate avg, p50, p95, p99 latencies
    - Track timeout and error counts
    - _Requirements: 1.5_
  
  - [ ]* 1.4 Write property tests for metrics capture
    - **Property 1: API Call Metrics Capture**
    - **Property 2: Prompt Size Logging Accuracy**
    - **Validates: Requirements 1.1, 1.2, 1.3, 1.5**

- [x] 2. Implement Gemini API Optimization
  - [x] 2.1 Add configurable timeout to GeminiProvider
    - Add `timeout_seconds` parameter (default 25s)
    - Implement asyncio timeout wrapper for API calls
    - Return graceful error response on timeout
    - _Requirements: 2.3, 2.4_
  
  - [x] 2.2 Implement context size limiting
    - Add `max_context_chars` parameter (default 6000)
    - Implement `_truncate_context()` method
    - Truncate conversation history to last 3 messages
    - _Requirements: 2.5, 2.6_
  
  - [x] 2.3 Optimize generation parameters
    - Configure optimal temperature, top_p, top_k values
    - Reduce max_output_tokens for chat responses (1024)
    - Verify gemini-2.5-flash model is used
    - _Requirements: 2.1, 2.2_
  
  - [ ]* 2.4 Write property tests for optimization
    - **Property 3: Timeout Handling Graceful Response**
    - **Property 4: Context Size Truncation**
    - **Property 5: Conversation History Limiting**
    - **Validates: Requirements 2.3, 2.4, 2.5, 2.6**

- [x] 3. Checkpoint - Verify Gemini Performance Improvements
  - Ensure all tests pass, ask the user if questions arise.
  - Test Gemini API calls complete within 15 seconds
  - Verify timeout handling works correctly

- [x] 4. Implement Streaming Response Infrastructure
  - [x] 4.1 Add StreamingChunk dataclass to ai_service.py
    - Create `StreamingChunk` with content, is_final, cumulative_tokens, error fields
    - _Requirements: 3.4_
  
  - [x] 4.2 Implement generate_response_stream in GeminiProvider
    - Use Gemini streaming API (generate_content_async with stream=True)
    - Yield StreamingChunk objects as content arrives
    - Handle mid-stream errors gracefully
    - _Requirements: 3.1, 3.2, 3.5_
  
  - [x] 4.3 Implement generate_response_stream in AIService
    - Wrap provider streaming method
    - Yield AIResponse objects with partial content
    - Track cumulative token counts
    - _Requirements: 3.3, 3.4_
  
  - [ ]* 4.4 Write property tests for streaming infrastructure
    - **Property 6: Streaming Yields Multiple Chunks**
    - **Property 7: Streaming Error Graceful Termination**
    - **Validates: Requirements 3.1, 3.3, 3.4, 3.5**

- [x] 5. Implement WebSocket Streaming Integration
  - [x] 5.1 Add streaming methods to ConnectionManager
    - Implement `send_streaming_message()` for partial chunks
    - Implement `send_streaming_start()` with citations
    - Implement `send_streaming_complete()` with metadata
    - _Requirements: 4.2_
  
  - [x] 5.2 Update Chat Router for streaming responses
    - Add streaming message handling in `handle_chat_message()`
    - Send streaming_start, response_chunk, response_complete messages
    - Implement cancellation on WebSocket disconnect
    - _Requirements: 4.1, 4.3, 4.4, 4.5, 4.6_
  
  - [ ]* 5.3 Write property tests for WebSocket streaming
    - **Property 8: WebSocket Streaming Message Sequence**
    - **Property 9: Streaming Cancellation on Disconnect**
    - **Validates: Requirements 4.3, 4.4, 4.5, 4.6**

- [x] 6. Implement RAG Service Streaming Support
  - [x] 6.1 Add RAGStreamingChunk dataclass to rag_service.py
    - Create dataclass with content, is_final, citations, metadata fields
    - _Requirements: 5.1_
  
  - [x] 6.2 Implement generate_response_stream in RAGService
    - Complete document search before streaming
    - Yield first chunk with citations
    - Stream AI generation chunks
    - Yield final chunk with metadata
    - _Requirements: 5.1, 5.2, 5.3, 5.4_
  
  - [x] 6.3 Implement streaming fallback on search failure
    - Fall back to general AI streaming if search fails
    - Log fallback reason
    - _Requirements: 5.5_
  
  - [ ]* 6.4 Write property tests for RAG streaming
    - **Property 10: RAG Streaming Search-First Order**
    - **Property 11: RAG Streaming Final Metadata**
    - **Property 12: RAG Streaming Fallback on Search Failure**
    - **Validates: Requirements 5.2, 5.3, 5.4, 5.5**

- [x] 7. Checkpoint - Verify Streaming End-to-End
  - Ensure all tests pass, ask the user if questions arise.
  - Test streaming responses through WebSocket
  - Verify citations appear before content

- [ ] 8. Verify KG-Guided Retrieval
  - [x] 8.1 Add KG metadata to RAG response
    - Include concepts_matched, retrieval_source in response metadata
    - Pass KG metadata through to Chat Router response
    - _Requirements: 6.2, 6.3, 6.4_
  
  - [x] 8.2 Write integration test for Chelsea AI Ventures query
    - Test KG retrieval returns relevant chunks
    - Verify KG metadata is present in response
    - _Requirements: 6.1_
  
  - [ ]* 8.3 Write property test for KG metadata flow
    - **Property 13: KG Metadata Flow Through**
    - **Validates: Requirements 6.2, 6.3, 6.4**

- [x] 9. Implement Hybrid Search Keyword Component
  - [x] 9.1 Implement TF-IDF indexing in HybridSearchEngine
    - Add `TfidfIndex` dataclass
    - Implement `build_keyword_index()` method
    - Cache TF-IDF vectors for performance
    - _Requirements: 7.5_
  
  - [x] 9.2 Implement _keyword_search method
    - Use TfidfVectorizer for query vectorization
    - Return matching chunks with scores
    - _Requirements: 7.1, 7.2_
  
  - [x] 9.3 Implement hybrid score combination
    - Combine vector and keyword scores with configurable weights
    - Implement fallback to keyword results when vector returns empty
    - _Requirements: 7.3, 7.4_
  
  - [ ]* 9.4 Write property tests for hybrid search
    - **Property 14: Keyword Search Returns Matching Results**
    - **Property 15: Hybrid Score Weighted Combination**
    - **Property 16: Keyword Fallback on Empty Vector Results**
    - **Validates: Requirements 7.1, 7.2, 7.3, 7.4**

- [x] 10. Implement Error Handling and Circuit Breaker
  - [x] 10.1 Add user-friendly error messages to AIService
    - Map error types to user-friendly messages
    - Return graceful responses instead of exceptions
    - _Requirements: 8.1_
  
  - [x] 10.2 Implement circuit breaker for Gemini API
    - Add CircuitBreaker class with CLOSED/OPEN/HALF_OPEN states
    - Configure failure threshold and reset timeout
    - Wrap Gemini API calls with circuit breaker
    - _Requirements: 8.3_
  
  - [x] 10.3 Add timeout notification to Chat Router
    - Send timeout notification to user on API timeout
    - Implement streaming fallback to non-streaming
    - _Requirements: 8.2, 8.4_
  
  - [x] 10.4 Implement error rate tracking and streaming disable
    - Track error rate over sliding window
    - Disable streaming when error rate exceeds 50%
    - Re-enable when error rate drops
    - _Requirements: 8.5_
  
  - [ ]* 10.5 Write property tests for error handling
    - **Property 17: API Failure User-Friendly Response**
    - **Property 18: Circuit Breaker State Transitions**
    - **Property 19: Streaming Fallback to Non-Streaming**
    - **Property 20: Error Rate Streaming Disable**
    - **Validates: Requirements 8.1, 8.3, 8.4, 8.5**

- [x] 11. Final Checkpoint - Full Integration Testing
  - Ensure all tests pass, ask the user if questions arise.
  - Test complete flow: chat message → KG retrieval → streaming response
  - Verify Chelsea AI Ventures query returns correct quote
  - Test error handling and fallback scenarios

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties
- Unit tests validate specific examples and edge cases
- All new code should follow FastAPI DI patterns per dependency-injection.md
