# Implementation Plan: Wikidata Rate Limiting and Background Enrichment

## Overview

This implementation plan converts the design into discrete coding tasks. The approach is:
1. Build the rate limiting infrastructure first (RateLimiter, RequestQueue)
2. Enhance the WikidataClient with rate limiting
3. Create the enrichment status tracking system
4. Implement the background enrichment task
5. Wire everything together and update the pipeline

## Tasks

- [x] 1. Implement Rate Limiter and Request Queue
  - [x] 1.1 Create RateLimiter class with token bucket algorithm
    - Create `src/multimodal_librarian/services/rate_limiter.py`
    - Implement token bucket with configurable rate and burst size
    - Add async `acquire()` method with timeout support
    - Add `get_stats()` method for monitoring
    - _Requirements: 1.2, 2.1, 2.2_
  
  - [ ]* 1.2 Write property test for token bucket behavior
    - **Property 2: Token Bucket Rate Limiting**
    - **Validates: Requirements 1.2, 1.3, 2.1, 2.2**
  
  - [x] 1.3 Create RequestQueue class
    - Add to `src/multimodal_librarian/services/rate_limiter.py`
    - Implement async `submit()` method with rate limiting
    - Implement `drain()` method for graceful shutdown
    - Add queue depth and wait time metrics
    - _Requirements: 1.3, 2.4, 2.5_
  
  - [ ]* 1.4 Write property test for timeout exception guarantee
    - **Property 3: Timeout Exception Guarantee**
    - **Validates: Requirements 2.3**
  
  - [ ]* 1.5 Write property test for graceful shutdown drain
    - **Property 4: Graceful Shutdown Drain**
    - **Validates: Requirements 2.5**

- [x] 2. Enhance WikidataClient with Rate Limiting
  - [x] 2.1 Add exponential backoff for 403/429 responses
    - Update `src/multimodal_librarian/clients/wikidata_client.py`
    - Implement `_calculate_backoff()` method
    - Handle HTTP 403 and 429 specifically with backoff
    - Respect Retry-After header when present
    - _Requirements: 1.1, 1.5_
  
  - [ ]* 2.2 Write property test for exponential backoff calculation
    - **Property 1: Exponential Backoff Calculation**
    - **Validates: Requirements 1.1**
  
  - [x] 2.3 Integrate RateLimiter into WikidataClient
    - Add rate_limiter parameter to constructor
    - Wrap API calls with rate limiter acquire
    - Add configuration loading from settings
    - _Requirements: 1.2, 1.4_
  
  - [ ]* 2.4 Write property test for circuit breaker recording
    - **Property 5: Circuit Breaker Recording on Retry Exhaustion**
    - **Validates: Requirements 1.5**

- [x] 3. Checkpoint - Ensure rate limiting tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Add Configuration Settings
  - [x] 4.1 Add rate limiting configuration to Settings
    - Update `src/multimodal_librarian/config/config.py`
    - Add wikidata_rate_limit_rps, wikidata_burst_size
    - Add wikidata_backoff_base, wikidata_backoff_max
    - Add wikidata_request_timeout
    - _Requirements: 6.1, 6.2, 6.3_
  
  - [x] 4.2 Add enrichment configuration to Settings
    - Add enrichment_batch_size, enrichment_checkpoint_interval
    - Add enrichment_max_retries, enrichment_retry_delay
    - _Requirements: 6.4, 6.5, 6.6_

- [x] 5. Implement Enrichment Status Tracking
  - [x] 5.1 Create EnrichmentStatus data models
    - Create `src/multimodal_librarian/models/enrichment_status.py`
    - Define EnrichmentState enum
    - Define EnrichmentStatus and EnrichmentCheckpoint dataclasses
    - _Requirements: 4.1_
  
  - [ ]* 5.2 Write property test for enrichment status state machine
    - **Property 9: Enrichment Status State Machine**
    - **Validates: Requirements 4.1**
  
  - [x] 5.3 Create database migration for enrichment_status table
    - Create migration file in `src/multimodal_librarian/database/migrations/`
    - Add enrichment_status table with all required columns
    - Add indexes for document_id and state
    - _Requirements: 4.1, 4.3, 4.4, 4.5_
  
  - [x] 5.4 Create EnrichmentStatusService
    - Create `src/multimodal_librarian/services/enrichment_status_service.py`
    - Implement create_status, update_progress, mark_completed, mark_failed
    - Implement get_status, get_checkpoint, save_checkpoint
    - _Requirements: 4.3, 4.4, 4.5, 5.3_
  
  - [ ]* 5.5 Write property test for enrichment status completeness
    - **Property 11: Enrichment Status Completeness**
    - **Validates: Requirements 4.3, 4.4**
  
  - [ ]* 5.6 Write property test for retry counter preservation
    - **Property 12: Retry Counter Preservation**
    - **Validates: Requirements 4.5**

- [x] 6. Checkpoint - Ensure status tracking tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Implement Background Enrichment Task
  - [x] 7.1 Create enrich_concepts_task Celery task
    - Update `src/multimodal_librarian/services/celery_service.py`
    - Add enrich_concepts_task with retry configuration
    - Implement batch processing with configurable batch size
    - Implement checkpoint saving at configured intervals
    - _Requirements: 3.1, 3.3, 5.1, 5.2, 5.3_
  
  - [ ]* 7.2 Write property test for batch processing size
    - **Property 7: Batch Processing Size**
    - **Validates: Requirements 3.3**
  
  - [ ]* 7.3 Write property test for checkpoint and resume
    - **Property 14: Checkpoint and Resume**
    - **Validates: Requirements 5.2, 5.3**
  
  - [x] 7.4 Implement circuit breaker deferral logic
    - Check circuit breaker state at task start
    - Requeue with delay if circuit breaker is open
    - _Requirements: 5.5_
  
  - [ ]* 7.5 Write property test for circuit breaker deferral
    - **Property 16: Circuit Breaker Deferral**
    - **Validates: Requirements 5.5**

- [x] 8. Update Document Processing Pipeline
  - [x] 8.1 Modify update_knowledge_graph_task to queue enrichment
    - Remove synchronous enrichment call from _update_knowledge_graph
    - Queue enrich_concepts_task after KG update completes
    - Create initial enrichment status record
    - _Requirements: 3.1, 3.5_
  
  - [x] 8.2 Modify finalize_processing_task for document completion
    - Ensure document status is COMPLETED before enrichment starts
    - _Requirements: 3.2_
  
  - [ ]* 8.3 Write property test for document completion ordering
    - **Property 6: Document Completion Before Enrichment**
    - **Validates: Requirements 3.2**
  
  - [ ]* 8.4 Write property test for enrichment failure isolation
    - **Property 8: Enrichment Failure Isolation**
    - **Validates: Requirements 3.4**

- [x] 9. Checkpoint - Ensure pipeline integration tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Update API Endpoints
  - [x] 10.1 Update document status endpoint to include enrichment status
    - Modify document status response to include enrichment_status
    - _Requirements: 4.2_
  
  - [ ]* 10.2 Write property test for combined status response
    - **Property 10: Combined Status Response**
    - **Validates: Requirements 4.2**
  
  - [x] 10.3 Add enrichment metrics to health check endpoint
    - Add enrichment_queue_depth and enrichment_processing_rate
    - _Requirements: 7.5_
  
  - [ ]* 10.4 Write property test for health check enrichment metrics
    - **Property 17: Health Check Enrichment Metrics**
    - **Validates: Requirements 7.5**

- [x] 11. Add Dependency Injection for New Services
  - [x] 11.1 Add RateLimiter dependency provider
    - Update `src/multimodal_librarian/api/dependencies/services.py`
    - Add get_rate_limiter() and get_rate_limiter_optional()
    - Follow lazy initialization pattern
    - _Requirements: 1.2_
  
  - [x] 11.2 Add EnrichmentStatusService dependency provider
    - Add get_enrichment_status_service() and optional variant
    - Follow lazy initialization pattern
    - _Requirements: 4.2_

- [x] 12. Final Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional property-based tests that can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties
- Unit tests validate specific examples and edge cases
- The implementation follows the dependency injection patterns documented in `.kiro/steering/dependency-injection.md`
