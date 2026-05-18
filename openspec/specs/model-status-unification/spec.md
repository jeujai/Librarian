## Purpose

This feature unifies the multiple conflicting sources of truth for ML model availability into a single authoritative source that queries the actual model server container. Currently, the application has three separate model status tracking systems that provide inconsistent information, causing document uploads and other operations to fail with fallback responses even when the model server is healthy and ready.


### Key Terms
- **Model_Server**: The dedicated container (`librarian-model-server-1`) running on port 8001 that loads and serves actual ML models (embedding and NLP)
- **Model_Status_Service**: The new unified service that queries the Model_Server for real model availability
- **Capability_Service**: The service that advertises system capabilities based on model availability
- **Model_Availability_Middleware**: Middleware that intercepts requests and provides fallback responses when models are unavailable
- **Minimal_Server**: The fast-startup server component that currently maintains fake model status tracking
- **Model_Manager**: The existing model manager that tracks model instances with status that never transitions from pending
- **Capability**: A system feature (e.g., `document_analysis`, `basic_chat`) that requires specific models to function
- **Model_To_Capability_Mapping**: The configuration that maps model server models (`embedding`, `nlp`) to application capabilities

## Requirements

### Requirement: Unified Model Status Service

The system SHALL support: As a system component, I want to query a single authoritative source for model availability, so that all parts of the application have consistent information about which models are ready.

#### Scenario: THE Model_Status_Service SHALL query the Model_Server health

- **THEN** THE Model_Status_Service SHALL query the Model_Server health endpoint to determine actual model availability

#### Scenario: THE Model_Status_Service SHALL cache model status with a con

- **THEN** THE Model_Status_Service SHALL cache model status with a configurable TTL to avoid excessive health check requests

#### Scenario: WHEN the Model_Server is unreachable, THE Model_Status_Servi

- **THEN** WHEN the Model_Server is unreachable, THE Model_Status_Service SHALL return a status indicating all models are unavailable

#### Scenario: THE Model_Status_Service SHALL expose both synchronous and a

- **THEN** THE Model_Status_Service SHALL expose both synchronous and asynchronous methods for status retrieval

#### Scenario: THE Model_Status_Service SHALL provide a method to force-ref

- **THEN** THE Model_Status_Service SHALL provide a method to force-refresh the cached status

### Requirement: Model to Capability Mapping

The system SHALL support: As a developer, I want a clear mapping between model server models and application capabilities, so that the system can determine which features are available based on loaded models.

#### Scenario: THE Model_Status_Service SHALL maintain a configurable mappi

- **THEN** THE Model_Status_Service SHALL maintain a configurable mapping from Model_Server models to application capabilities

#### Scenario: WHEN the `embedding` model is loaded, THE Model_Status_Servi

- **THEN** WHEN the `embedding` model is loaded, THE Model_Status_Service SHALL report `document_analysis`, `simple_search`, `semantic_search`, and `document_upload` capabilities as available

#### Scenario: WHEN the `nlp` model is loaded, THE Model_Status_Service SHA

- **THEN** WHEN the `nlp` model is loaded, THE Model_Status_Service SHALL report `basic_chat`, `document_upload`, and text processing capabilities as available

#### Scenario: THE Model_Status_Service SHALL provide a method to query whi

- **THEN** THE Model_Status_Service SHALL provide a method to query which capabilities are available based on current model status

#### Scenario: THE Model_Status_Service SHALL provide a method to query whi

- **THEN** THE Model_Status_Service SHALL provide a method to query which models are required for a given capability

### Requirement: Capability Service Integration

The system SHALL support: As a user, I want the capability service to reflect actual model availability, so that I receive accurate information about what features are ready.

#### Scenario: THE Capability_Service SHALL use the Model_Status_Service as

- **THEN** THE Capability_Service SHALL use the Model_Status_Service as its source of truth for model availability

#### Scenario: THE Capability_Service SHALL NOT use the Minimal_Server mode

- **THEN** THE Capability_Service SHALL NOT use the Minimal_Server model_statuses dictionary for capability determination

#### Scenario: WHEN querying current capabilities, THE Capability_Service S

- **THEN** WHEN querying current capabilities, THE Capability_Service SHALL return availability based on Model_Status_Service data

#### Scenario: THE Capability_Service SHALL continue to provide estimated r

- **THEN** THE Capability_Service SHALL continue to provide estimated ready times based on Model_Status_Service health check results

### Requirement: Model Availability Middleware Integration

The system SHALL support: As a user, I want requests to succeed when models are actually available, so that I don't receive unnecessary fallback responses.

#### Scenario: THE Model_Availability_Middleware SHALL use the Model_Status

- **THEN** THE Model_Availability_Middleware SHALL use the Model_Status_Service to check capability availability

#### Scenario: THE Model_Availability_Middleware SHALL NOT use the Model_Ma

- **THEN** THE Model_Availability_Middleware SHALL NOT use the Model_Manager for capability status checks

#### Scenario: WHEN the Model_Status_Service reports a capability as availa

- **THEN** WHEN the Model_Status_Service reports a capability as available, THE Model_Availability_Middleware SHALL allow the request to proceed normally

#### Scenario: WHEN the Model_Status_Service reports a capability as unavai

- **THEN** WHEN the Model_Status_Service reports a capability as unavailable, THE Model_Availability_Middleware SHALL provide a fallback response

### Requirement: Loading Progress Endpoint Updates

The system SHALL support: As a user, I want the loading progress endpoints to show accurate model loading status, so that I know when the system is truly ready.

#### Scenario: THE loading progress endpoints SHALL use the Model_Status_Se

- **THEN** THE loading progress endpoints SHALL use the Model_Status_Service for model status information

#### Scenario: WHEN displaying model loading status, THE endpoints SHALL sh

- **THEN** WHEN displaying model loading status, THE endpoints SHALL show the actual status from the Model_Server

#### Scenario: THE `/api/loading/models` endpoint SHALL return accurate loa

- **THEN** THE `/api/loading/models` endpoint SHALL return accurate loaded/loading/pending counts based on Model_Status_Service data

#### Scenario: THE `/api/loading/status` endpoint SHALL reflect true system

- **THEN** THE `/api/loading/status` endpoint SHALL reflect true system readiness based on Model_Status_Service data

### Requirement: Minimal Server Deprecation

The system SHALL support: As a developer, I want the fake model status tracking removed from the Minimal_Server, so that there is no confusion about the source of truth.

#### Scenario: THE Minimal_Server SHALL NOT maintain its own model_statuses

- **THEN** THE Minimal_Server SHALL NOT maintain its own model_statuses dictionary for capability determination

#### Scenario: THE Minimal_Server SHALL delegate model status queries to th

- **THEN** THE Minimal_Server SHALL delegate model status queries to the Model_Status_Service

#### Scenario: THE Minimal_Server MAY retain basic server status tracking (

- **THEN** THE Minimal_Server MAY retain basic server status tracking (uptime, request counts) that is not model-related

#### Scenario: WHEN the Minimal_Server's `_check_ai_availability` method is

- **THEN** WHEN the Minimal_Server's `_check_ai_availability` method is called, THE Minimal_Server SHALL use the Model_Status_Service instead of checking AI providers directly

### Requirement: Health Check Integration

The system SHALL support: As an operations engineer, I want health check endpoints to reflect actual model server status, so that I can accurately monitor system readiness.

#### Scenario: THE `/health/ready` endpoint SHALL use the Model_Status_Serv

- **THEN** THE `/health/ready` endpoint SHALL use the Model_Status_Service to determine if essential models are loaded

#### Scenario: THE `/health/full` endpoint SHALL use the Model_Status_Servi

- **THEN** THE `/health/full` endpoint SHALL use the Model_Status_Service to determine if all models are loaded

#### Scenario: WHEN the Model_Server reports models as loaded, THE health e

- **THEN** WHEN the Model_Server reports models as loaded, THE health endpoints SHALL report the system as ready

#### Scenario: IF the Model_Server is unreachable, THEN THE health endpoint

- **GIVEN** the Model_Server is unreachable
- **THEN** IF the Model_Server is unreachable, THEN THE health endpoints SHALL report the system as not ready

### Requirement: Error Handling and Resilience

The system SHALL support: As a system operator, I want the model status service to handle failures gracefully, so that the application remains stable even when the model server has issues.

#### Scenario: IF the Model_Server health check fails, THEN THE Model_Statu

- **GIVEN** the Model_Server health check fails
- **THEN** IF the Model_Server health check fails, THEN THE Model_Status_Service SHALL log the error and return unavailable status

#### Scenario: THE Model_Status_Service SHALL implement exponential backoff

- **THEN** THE Model_Status_Service SHALL implement exponential backoff for retries when the Model_Server is unreachable

#### Scenario: THE Model_Status_Service SHALL NOT block application startup

- **THEN** THE Model_Status_Service SHALL NOT block application startup if the Model_Server is initially unavailable

#### Scenario: WHEN the Model_Server becomes available after being unavaila

- **THEN** WHEN the Model_Server becomes available after being unavailable, THE Model_Status_Service SHALL update its cached status on the next health check
