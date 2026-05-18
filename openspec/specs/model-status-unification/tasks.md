# Implementation Plan: Model Status Unification

## Overview

This implementation plan creates a unified Model Status Service that queries the actual model server container and integrates it with all existing components that need model availability information. The approach is incremental: first create the new service, then integrate it with existing components one by one, and finally deprecate the old status tracking.

## Tasks

- [x] 1. Create Model Status Service
  - [x] 1.1 Create the ModelStatusService class with core functionality
    - Create `src/multimodal_librarian/services/model_status_service.py`
    - Implement `ModelInfo`, `ModelStatusSnapshot`, `ModelServerStatus` data classes
    - Implement `ModelStatusService` with health check querying, caching, and capability mapping
    - Implement async `get_status()` and sync `get_status_sync()` methods
    - _Requirements: 1.1, 1.2, 1.4, 2.1_

  - [x] 1.2 Implement caching with configurable TTL
    - Add cache TTL configuration
    - Implement cache validation logic
    - Implement `refresh_status()` for force refresh
    - _Requirements: 1.2, 1.5_

  - [x] 1.3 Implement error handling and retry logic
    - Add exponential backoff for retries
    - Implement `_create_unavailable_status()` for error cases
    - Add proper logging for failures
    - _Requirements: 1.3, 8.1, 8.2_

  - [ ]* 1.4 Write property tests for ModelStatusService
    - **Property 1: Cache TTL Behavior**
    - **Property 2: Force Refresh Bypasses Cache**
    - **Property 3: Unavailable Status on Connection Failure**
    - **Property 4: Model-to-Capability Mapping Correctness**
    - **Validates: Requirements 1.2, 1.3, 1.5, 2.2, 2.3, 2.4**

- [x] 2. Add Dependency Injection Support
  - [x] 2.1 Create DI provider functions
    - Add `get_model_status_service()` async dependency provider
    - Add `get_model_status_service_optional()` for graceful degradation
    - Add `cleanup_model_status_service()` for shutdown
    - Update `src/multimodal_librarian/api/dependencies/services.py`
    - _Requirements: 1.4, 8.3_

  - [x] 2.2 Initialize service in application lifespan
    - Update `main.py` lifespan to initialize ModelStatusService
    - Start background refresh task
    - Add cleanup on shutdown
    - _Requirements: 8.3_

- [x] 3. Checkpoint - Verify ModelStatusService works
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Integrate with Capability Service
  - [x] 4.1 Update CapabilityService to use ModelStatusService
    - Modify `get_current_capabilities()` to query ModelStatusService
    - Remove dependency on MinimalServer.model_statuses
    - Update `_calculate_ready_time()` to use ModelStatusService data
    - _Requirements: 3.1, 3.3, 3.4_

  - [ ]* 4.2 Write property tests for CapabilityService integration
    - **Property 5: Capability Service Integration**
    - **Validates: Requirements 3.1, 3.3**

- [x] 5. Integrate with Model Availability Middleware
  - [x] 5.1 Update ModelAvailabilityMiddleware to use ModelStatusService
    - Modify `_check_capability_availability()` to use ModelStatusService
    - Remove dependency on ModelManager.get_capability_status()
    - Inject ModelStatusService via DI
    - _Requirements: 4.1, 4.3, 4.4_

  - [ ]* 5.2 Write property tests for middleware integration
    - **Property 6: Middleware Request Routing**
    - **Validates: Requirements 4.1, 4.3, 4.4**

- [x] 6. Checkpoint - Verify integrations work
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Update Loading Progress Endpoints
  - [x] 7.1 Update `/api/loading/models` endpoint
    - Modify `get_model_loading_status()` to use ModelStatusService
    - Return accurate loaded/loading/pending counts
    - _Requirements: 5.1, 5.2, 5.3_

  - [x] 7.2 Update `/api/loading/status` endpoint
    - Modify `get_loading_status()` to use ModelStatusService
    - Reflect true system readiness
    - _Requirements: 5.4_

  - [ ]* 7.3 Write property tests for loading endpoints
    - **Property 7: Loading Endpoints Consistency**
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.4**

- [x] 8. Update Health Check Endpoints
  - [x] 8.1 Update `/health/ready` endpoint
    - Modify to use ModelStatusService for essential model check
    - _Requirements: 7.1, 7.3_

  - [x] 8.2 Update `/health/full` endpoint
    - Modify to use ModelStatusService for all models check
    - _Requirements: 7.2, 7.3, 7.4_

  - [ ]* 8.3 Write property tests for health endpoints
    - **Property 8: Health Endpoints Consistency**
    - **Validates: Requirements 7.1, 7.2, 7.3, 7.4**

- [x] 9. Deprecate MinimalServer Model Status Tracking
  - [x] 9.1 Update MinimalServer to delegate to ModelStatusService
    - Modify `_check_ai_availability()` to use ModelStatusService
    - Remove direct model_statuses manipulation
    - Keep basic server status tracking (uptime, request counts)
    - _Requirements: 6.1, 6.2, 6.4_

  - [x] 9.2 Update MinimalServer status methods
    - Modify `get_model_status()` to delegate to ModelStatusService
    - Modify `is_capability_available()` to delegate to ModelStatusService
    - _Requirements: 6.2_

- [x] 10. Final Checkpoint - Full integration test
  - Ensure all tests pass, ask the user if questions arise.

- [ ]* 11. Write integration tests
  - [ ]* 11.1 Write end-to-end integration tests
    - Test document upload with model server running
    - Test capability reporting accuracy
    - Test fallback behavior when model server is down
    - _Requirements: All_

  - [ ]* 11.2 Write property tests for retry and recovery
    - **Property 9: Exponential Backoff on Retries**
    - **Property 10: Status Recovery After Server Available**
    - **Validates: Requirements 8.2, 8.4**

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties
- Unit tests validate specific examples and edge cases
- The implementation follows the existing dependency injection patterns in the codebase
