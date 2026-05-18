## Purpose

This feature addresses two critical issues in the document processing pipeline:

1. **Rate Limiting**: The Wikidata client experiences HTTP 403 errors due to rate limiting, causing enrichment failures and pipeline disruptions.

2. **Synchronous Blocking**: The Wikidata enrichment currently runs synchronously within the `update_knowledge_graph_task`, blocking the main document processing pipeline and causing timeouts (SoftTimeLimitExceeded).

The solution implements proper rate limiting with exponential backoff in the Wikidata client and decouples enrichment into a separate background process, allowing documents to be marked "complete" before enrichment finishes.


### Key Terms
- **Wikidata_Client**: The HTTP client that communicates with the Wikidata API for entity search and instance-of relationship retrieval.
- **Rate_Limiter**: A component that controls the rate of outgoing API requests to prevent exceeding external service limits.
- **Request_Queue**: A queue that buffers outgoing requests to smooth out bursts and enforce rate limits.
- **Enrichment_Service**: The service that orchestrates Wikidata and ConceptNet enrichment for extracted concepts.
- **Background_Enrichment_Task**: A separate Celery task that performs concept enrichment asynchronously after document processing completes.
- **Enrichment_Status**: A tracking mechanism that records the state of enrichment separately from document processing status.
- **Exponential_Backoff**: A retry strategy where wait time increases exponentially after each failure.
- **Token_Bucket**: A rate limiting algorithm that allows bursts while maintaining an average rate limit.

## Requirements

### Requirement: Rate Limiting for Wikidata Client

The system SHALL support: As a system operator, I want the Wikidata client to respect API rate limits, so that the system avoids HTTP 403/429 errors and maintains reliable enrichment.

#### Scenario: WHEN the Wikidata_Client receives an HTTP 403 or 429 respons

- **WHEN** the Wikidata_Client receives an HTTP 403 or 429 response
- **THEN** THE Wikidata_Client SHALL implement exponential backoff with a base delay of 1 second and maximum delay of 60 seconds.

#### Scenario: WHEN the Wikidata_Client is initialized, THE Rate_Limiter SH

- **THEN** WHEN the Wikidata_Client is initialized, THE Rate_Limiter SHALL enforce a configurable maximum request rate defaulting to 10 requests per second.

#### Scenario: WHEN multiple requests are submitted simultaneously, THE Req

- **THEN** WHEN multiple requests are submitted simultaneously, THE Request_Queue SHALL buffer requests and release them at the configured rate.

#### Scenario: WHEN the Rate_Limiter is configured, THE Wikidata_Client SHA

- **THEN** WHEN the Rate_Limiter is configured, THE Wikidata_Client SHALL read rate limit settings from environment variables or configuration.

#### Scenario: IF the maximum retry attempts are exceeded after backoff, TH

- **GIVEN** the maximum retry attempts are exceeded after backoff
- **THEN** IF the maximum retry attempts are exceeded after backoff, THEN THE Wikidata_Client SHALL record the failure with the circuit breaker and return gracefully without crashing.

### Requirement: Request Queue for Burst Smoothing

The system SHALL support: As a system operator, I want API requests to be queued and smoothed, so that burst traffic does not trigger rate limiting from external services.

#### Scenario: THE Request_Queue SHALL implement a token bucket algorithm w

- **THEN** THE Request_Queue SHALL implement a token bucket algorithm with configurable bucket size and refill rate.

#### Scenario: WHEN a request is submitted to the Request_Queue, THE Reques

- **THEN** WHEN a request is submitted to the Request_Queue, THE Request_Queue SHALL block until a token is available or timeout is reached.

#### Scenario: WHEN the queue timeout is reached, THE Request_Queue SHALL r

- **THEN** WHEN the queue timeout is reached, THE Request_Queue SHALL raise a timeout exception rather than silently dropping the request.

#### Scenario: THE Request_Queue SHALL track queue depth and wait time metr

- **THEN** THE Request_Queue SHALL track queue depth and wait time metrics for monitoring.

#### Scenario: WHEN the system shuts down, THE Request_Queue SHALL drain pe

- **THEN** WHEN the system shuts down, THE Request_Queue SHALL drain pending requests gracefully within a configurable timeout.

### Requirement: Background Enrichment Task

The system SHALL support: As a system operator, I want enrichment to run as a separate background process, so that document processing completes quickly without waiting for external API calls.

#### Scenario: WHEN the knowledge graph update task completes, THE Backgrou

- **THEN** WHEN the knowledge graph update task completes, THE Background_Enrichment_Task SHALL be queued as a separate Celery task.

#### Scenario: WHEN a document is processed, THE Document_Status SHALL be m

- **THEN** WHEN a document is processed, THE Document_Status SHALL be marked as "completed" before enrichment begins.

#### Scenario: THE Background_Enrichment_Task SHALL process concepts in bat

- **THEN** THE Background_Enrichment_Task SHALL process concepts in batches with configurable batch size defaulting to 50 concepts.

#### Scenario: IF the Background_Enrichment_Task fails, THEN THE Enrichment

- **GIVEN** the Background_Enrichment_Task fails
- **THEN** IF the Background_Enrichment_Task fails, THEN THE Enrichment_Status SHALL be marked as "failed" without affecting the document's "completed" status.

#### Scenario: WHEN the Background_Enrichment_Task starts, THE Enrichment_S

- **THEN** WHEN the Background_Enrichment_Task starts, THE Enrichment_Status SHALL be updated to "enriching" with a timestamp.

### Requirement: Enrichment Status Tracking

The system SHALL support: As a user, I want to see the enrichment status separately from document processing status, so that I know when my document is ready for basic queries versus fully enriched queries.

#### Scenario: THE Enrichment_Status SHALL have states: "pending", "enrichi

- **THEN** THE Enrichment_Status SHALL have states: "pending", "enriching", "completed", "failed", and "skipped".

#### Scenario: WHEN querying document status, THE System SHALL return both

- **THEN** WHEN querying document status, THE System SHALL return both document processing status and enrichment status.

#### Scenario: THE Enrichment_Status SHALL include progress percentage, con

- **THEN** THE Enrichment_Status SHALL include progress percentage, concepts enriched count, and error count.

#### Scenario: WHEN enrichment completes, THE Enrichment_Status SHALL recor

- **THEN** WHEN enrichment completes, THE Enrichment_Status SHALL record duration, Wikidata hits, ConceptNet hits, and cache hits.

#### Scenario: IF enrichment is retried, THEN THE Enrichment_Status SHALL i

- **GIVEN** enrichment is retried
- **THEN** IF enrichment is retried, THEN THE Enrichment_Status SHALL increment a retry counter and preserve the previous error message.

### Requirement: Retry and Recovery for Background Enrichment

The system SHALL support: As a system operator, I want failed enrichment tasks to be automatically retried with backoff, so that transient failures do not permanently prevent enrichment.

#### Scenario: WHEN the Background_Enrichment_Task fails, THE Celery_Worker

- **THEN** WHEN the Background_Enrichment_Task fails, THE Celery_Worker SHALL retry with exponential backoff up to a configurable maximum of 3 retries.

#### Scenario: WHEN retrying, THE Background_Enrichment_Task SHALL resume f

- **THEN** WHEN retrying, THE Background_Enrichment_Task SHALL resume from the last successfully enriched concept rather than restarting.

#### Scenario: THE Background_Enrichment_Task SHALL checkpoint progress to

- **THEN** THE Background_Enrichment_Task SHALL checkpoint progress to the database every 10 concepts to enable resumption.

#### Scenario: IF all retries are exhausted, THEN THE Enrichment_Status SHA

- **GIVEN** all retries are exhausted
- **THEN** IF all retries are exhausted, THEN THE Enrichment_Status SHALL be marked as "failed" with the final error message.

#### Scenario: WHEN the circuit breaker is open, THE Background_Enrichment_

- **THEN** WHEN the circuit breaker is open, THE Background_Enrichment_Task SHALL defer execution and requeue with a delay.

### Requirement: Configuration Management

The system SHALL support: As a system administrator, I want to configure rate limiting and enrichment parameters, so that I can tune the system for different environments and API quotas.

#### Scenario: THE Configuration SHALL include wikidata_rate_limit_rps with

- **THEN** THE Configuration SHALL include wikidata_rate_limit_rps with a default of 10 requests per second.

#### Scenario: THE Configuration SHALL include wikidata_backoff_base_second

- **THEN** THE Configuration SHALL include wikidata_backoff_base_seconds with a default of 1 second.

#### Scenario: THE Configuration SHALL include wikidata_backoff_max_seconds

- **THEN** THE Configuration SHALL include wikidata_backoff_max_seconds with a default of 60 seconds.

#### Scenario: THE Configuration SHALL include enrichment_batch_size with a

- **THEN** THE Configuration SHALL include enrichment_batch_size with a default of 50 concepts.

#### Scenario: THE Configuration SHALL include enrichment_checkpoint_interv

- **THEN** THE Configuration SHALL include enrichment_checkpoint_interval with a default of 10 concepts.

#### Scenario: THE Configuration SHALL include enrichment_max_retries with

- **THEN** THE Configuration SHALL include enrichment_max_retries with a default of 3 retries.

#### Scenario: WHEN configuration values are changed, THE System SHALL appl

- **THEN** WHEN configuration values are changed, THE System SHALL apply them without requiring a restart for non-critical settings.

### Requirement: Monitoring and Observability

The system SHALL support: As a system operator, I want visibility into rate limiting and enrichment performance, so that I can identify bottlenecks and tune the system.

#### Scenario: THE Wikidata_Client SHALL log rate limit events including ba

- **THEN** THE Wikidata_Client SHALL log rate limit events including backoff delays and retry attempts.

#### Scenario: THE Request_Queue SHALL expose metrics for queue depth, aver

- **THEN** THE Request_Queue SHALL expose metrics for queue depth, average wait time, and tokens available.

#### Scenario: THE Background_Enrichment_Task SHALL log progress at configu

- **THEN** THE Background_Enrichment_Task SHALL log progress at configurable intervals defaulting to every 10 concepts.

#### Scenario: WHEN enrichment completes, THE System SHALL log a summary in

- **THEN** WHEN enrichment completes, THE System SHALL log a summary including duration, success rate, and error breakdown.

#### Scenario: THE System SHALL expose enrichment queue depth and processin

- **THEN** THE System SHALL expose enrichment queue depth and processing rate via the health check endpoint.
