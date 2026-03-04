# Requirements Document

## Introduction

This feature unifies the multiple conflicting sources of truth for ML model availability into a single authoritative source that queries the actual model server container. Currently, the application has three separate model status tracking systems that provide inconsistent information, causing document uploads and other operations to fail with fallback responses even when the model server is healthy and ready.

## Glossary

- **Model_Server**: The dedicated container (`librarian-model-server-1`) running on port 8001 that loads and serves actual ML models (embedding and NLP)
- **Model_Status_Service**: The new unified service that queries the Model_Server for real model availability
- **Capability_Service**: The service that advertises system capabilities based on model availability
- **Model_Availability_Middleware**: Middleware that intercepts requests and provides fallback responses when models are unavailable
- **Minimal_Server**: The fast-startup server component that currently maintains fake model status tracking
- **Model_Manager**: The existing model manager that tracks model instances with status that never transitions from pending
- **Capability**: A system feature (e.g., `document_analysis`, `basic_chat`) that requires specific models to function
- **Model_To_Capability_Mapping**: The configuration that maps model server models (`embedding`, `nlp`) to application capabilities

## Requirements

### Requirement 1: Unified Model Status Service

**User Story:** As a system component, I want to query a single authoritative source for model availability, so that all parts of the application have consistent information about which models are ready.

#### Acceptance Criteria

1. THE Model_Status_Service SHALL query the Model_Server health endpoint to determine actual model availability
2. THE Model_Status_Service SHALL cache model status with a configurable TTL to avoid excessive health check requests
3. WHEN the Model_Server is unreachable, THE Model_Status_Service SHALL return a status indicating all models are unavailable
4. THE Model_Status_Service SHALL expose both synchronous and asynchronous methods for status retrieval
5. THE Model_Status_Service SHALL provide a method to force-refresh the cached status

### Requirement 2: Model to Capability Mapping

**User Story:** As a developer, I want a clear mapping between model server models and application capabilities, so that the system can determine which features are available based on loaded models.

#### Acceptance Criteria

1. THE Model_Status_Service SHALL maintain a configurable mapping from Model_Server models to application capabilities
2. WHEN the `embedding` model is loaded, THE Model_Status_Service SHALL report `document_analysis`, `simple_search`, `semantic_search`, and `document_upload` capabilities as available
3. WHEN the `nlp` model is loaded, THE Model_Status_Service SHALL report `basic_chat`, `document_upload`, and text processing capabilities as available
4. THE Model_Status_Service SHALL provide a method to query which capabilities are available based on current model status
5. THE Model_Status_Service SHALL provide a method to query which models are required for a given capability

### Requirement 3: Capability Service Integration

**User Story:** As a user, I want the capability service to reflect actual model availability, so that I receive accurate information about what features are ready.

#### Acceptance Criteria

1. THE Capability_Service SHALL use the Model_Status_Service as its source of truth for model availability
2. THE Capability_Service SHALL NOT use the Minimal_Server model_statuses dictionary for capability determination
3. WHEN querying current capabilities, THE Capability_Service SHALL return availability based on Model_Status_Service data
4. THE Capability_Service SHALL continue to provide estimated ready times based on Model_Status_Service health check results

### Requirement 4: Model Availability Middleware Integration

**User Story:** As a user, I want requests to succeed when models are actually available, so that I don't receive unnecessary fallback responses.

#### Acceptance Criteria

1. THE Model_Availability_Middleware SHALL use the Model_Status_Service to check capability availability
2. THE Model_Availability_Middleware SHALL NOT use the Model_Manager for capability status checks
3. WHEN the Model_Status_Service reports a capability as available, THE Model_Availability_Middleware SHALL allow the request to proceed normally
4. WHEN the Model_Status_Service reports a capability as unavailable, THE Model_Availability_Middleware SHALL provide a fallback response

### Requirement 5: Loading Progress Endpoint Updates

**User Story:** As a user, I want the loading progress endpoints to show accurate model loading status, so that I know when the system is truly ready.

#### Acceptance Criteria

1. THE loading progress endpoints SHALL use the Model_Status_Service for model status information
2. WHEN displaying model loading status, THE endpoints SHALL show the actual status from the Model_Server
3. THE `/api/loading/models` endpoint SHALL return accurate loaded/loading/pending counts based on Model_Status_Service data
4. THE `/api/loading/status` endpoint SHALL reflect true system readiness based on Model_Status_Service data

### Requirement 6: Minimal Server Deprecation

**User Story:** As a developer, I want the fake model status tracking removed from the Minimal_Server, so that there is no confusion about the source of truth.

#### Acceptance Criteria

1. THE Minimal_Server SHALL NOT maintain its own model_statuses dictionary for capability determination
2. THE Minimal_Server SHALL delegate model status queries to the Model_Status_Service
3. THE Minimal_Server MAY retain basic server status tracking (uptime, request counts) that is not model-related
4. WHEN the Minimal_Server's `_check_ai_availability` method is called, THE Minimal_Server SHALL use the Model_Status_Service instead of checking AI providers directly

### Requirement 7: Health Check Integration

**User Story:** As an operations engineer, I want health check endpoints to reflect actual model server status, so that I can accurately monitor system readiness.

#### Acceptance Criteria

1. THE `/health/ready` endpoint SHALL use the Model_Status_Service to determine if essential models are loaded
2. THE `/health/full` endpoint SHALL use the Model_Status_Service to determine if all models are loaded
3. WHEN the Model_Server reports models as loaded, THE health endpoints SHALL report the system as ready
4. IF the Model_Server is unreachable, THEN THE health endpoints SHALL report the system as not ready

### Requirement 8: Error Handling and Resilience

**User Story:** As a system operator, I want the model status service to handle failures gracefully, so that the application remains stable even when the model server has issues.

#### Acceptance Criteria

1. IF the Model_Server health check fails, THEN THE Model_Status_Service SHALL log the error and return unavailable status
2. THE Model_Status_Service SHALL implement exponential backoff for retries when the Model_Server is unreachable
3. THE Model_Status_Service SHALL NOT block application startup if the Model_Server is initially unavailable
4. WHEN the Model_Server becomes available after being unavailable, THE Model_Status_Service SHALL update its cached status on the next health check
