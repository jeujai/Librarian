# Implementation Plan: Knowledge Graph External Enrichment

## Overview

This implementation plan breaks down the Knowledge Graph External Enrichment feature into discrete coding tasks. The approach follows the project's existing patterns: async operations, dependency injection, and graceful degradation. Tasks are ordered to build incrementally, with each step validating core functionality before proceeding.

## Tasks

- [x] 1. Create data models and base infrastructure
  - [x] 1.1 Create enrichment data models in `src/multimodal_librarian/models/enrichment.py`
    - Define WikidataEntity, WikidataClass, ConceptNetRelation, EnrichedConcept, EnrichmentResult dataclasses
    - Define CacheEntry, CacheStats, CircuitState classes
    - Define EnrichmentError exception hierarchy
    - _Requirements: 8.3, 8.4, 8.5_
  
  - [ ]* 1.2 Write property test for schema validation
    - **Property 19: Schema Validation for Nodes and Edges**
    - **Validates: Requirements 8.3, 8.4, 8.5**

- [x] 2. Implement EnrichmentCache with LRU and TTL
  - [x] 2.1 Create `src/multimodal_librarian/services/enrichment_cache.py`
    - Implement EnrichmentCache class with OrderedDict-based LRU
    - Implement get_wikidata, set_wikidata, get_conceptnet, set_conceptnet methods
    - Implement TTL expiration check in CacheEntry.is_expired()
    - Implement LRU eviction when max_size exceeded
    - Implement clear() and get_stats() methods
    - _Requirements: 6.1, 6.2, 6.3, 6.4_
  
  - [ ]* 2.2 Write property test for cache TTL expiration
    - **Property 14: Cache TTL Expiration**
    - **Validates: Requirements 6.1, 6.2**
  
  - [ ]* 2.3 Write property test for LRU eviction
    - **Property 15: LRU Eviction When Cache Full**
    - **Validates: Requirements 6.3**

- [-] 3. Implement CircuitBreaker for API resilience
  - [x] 3.1 Create `src/multimodal_librarian/services/circuit_breaker.py`
    - Implement CircuitBreaker class with CLOSED, OPEN, HALF_OPEN states
    - Implement record_success(), record_failure() methods
    - Implement is_open(), allow_request() methods
    - Implement automatic recovery after timeout
    - _Requirements: 7.3_
  
  - [ ]* 3.2 Write property test for circuit breaker state transitions
    - **Property 17: Circuit Breaker State Transitions**
    - **Validates: Requirements 7.3**

- [x] 4. Checkpoint - Ensure cache and circuit breaker tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [-] 5. Implement WikidataClient
  - [x] 5.1 Create `src/multimodal_librarian/clients/wikidata_client.py`
    - Implement WikidataClient class with SPARQL endpoint configuration
    - Implement async search_entity() method with 5-second timeout
    - Implement async get_instance_of() method for P31 property
    - Implement async batch_search() method for multiple concepts
    - Implement retry logic with exponential backoff (3 retries)
    - _Requirements: 1.1, 1.5, 2.1, 7.1_
  
  - [ ]* 5.2 Write property test for API retry on failure
    - **Property 16: API Retry on Failure** (Wikidata portion)
    - **Validates: Requirements 7.1**

- [-] 6. Implement ConceptNetClient
  - [x] 6.1 Create `src/multimodal_librarian/clients/conceptnet_client.py`
    - Implement ConceptNetClient class with REST API endpoint
    - Implement async get_relationships() method with 5-second timeout
    - Implement async batch_get_relationships() method
    - Implement retry logic with exponential backoff (3 retries)
    - Support all relationship types: IsA, PartOf, UsedFor, CapableOf, HasProperty, AtLocation, Causes, HasPrerequisite, MotivatedByGoal, RelatedTo
    - _Requirements: 3.1, 3.3, 3.6, 7.2_
  
  - [ ]* 6.2 Write property test for API retry on failure
    - **Property 16: API Retry on Failure** (ConceptNet portion)
    - **Validates: Requirements 7.2**

- [x] 7. Checkpoint - Ensure API client tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [-] 8. Implement EnrichmentService core functionality
  - [x] 8.1 Create `src/multimodal_librarian/services/enrichment_service.py`
    - Implement EnrichmentService class with dependency injection
    - Implement async enrich_single_concept() method
    - Implement confidence threshold check (>0.7 for Q-number storage)
    - Implement best match selection for disambiguation
    - Implement cache integration (check before API call)
    - _Requirements: 1.2, 1.3, 1.6, 3.7_
  
  - [ ]* 8.2 Write property test for Q-number storage threshold
    - **Property 1: Wikidata Q-number Storage Threshold**
    - **Validates: Requirements 1.2**
  
  - [ ]* 8.3 Write property test for best match selection
    - **Property 2: Best Match Selection for Disambiguation**
    - **Validates: Requirements 1.3**
  
  - [ ]* 8.4 Write property test for cache round-trip
    - **Property 3: Cache Round-Trip Consistency**
    - **Validates: Requirements 1.6, 3.7**

- [x] 9. Implement instance-of relationship handling
  - [x] 9.1 Add instance-of methods to EnrichmentService
    - Implement async _create_external_entity_nodes() method
    - Implement async _create_instance_of_relationships() method
    - Implement deduplication for External_Entity_Node (reuse existing)
    - _Requirements: 2.2, 2.3, 2.4, 2.5_
  
  - [ ]* 9.2 Write property test for instance-of node creation
    - **Property 4: Instance-Of Node Creation Completeness**
    - **Validates: Requirements 2.2**
  
  - [ ]* 9.3 Write property test for instance-of relationship creation
    - **Property 5: Instance-Of Relationship Creation**
    - **Validates: Requirements 2.3**
  
  - [ ]* 9.4 Write property test for external entity deduplication
    - **Property 6: External Entity Node Deduplication**
    - **Validates: Requirements 2.5**

- [x] 10. Implement ConceptNet relationship storage
  - [x] 10.1 Add ConceptNet methods to EnrichmentService
    - Implement async _store_conceptnet_relationships() method
    - Map ConceptNet relation types to Neo4j edge labels
    - Store weight and source_uri on edges
    - _Requirements: 3.2, 3.4_
  
  - [ ]* 10.2 Write property test for ConceptNet edge type preservation
    - **Property 7: ConceptNet Edge Type Preservation**
    - **Validates: Requirements 3.2**
  
  - [ ]* 10.3 Write property test for ConceptNet weight preservation
    - **Property 8: ConceptNet Weight Preservation**
    - **Validates: Requirements 3.4**

- [x] 11. Checkpoint - Ensure enrichment service tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 12. Implement batch enrichment and error handling
  - [x] 12.1 Add batch processing to EnrichmentService
    - Implement async enrich_concepts() method for batch processing
    - Implement error isolation (continue on single concept failure)
    - Implement circuit breaker integration
    - Implement deferred enrichment marking when circuit open
    - Implement enrichment statistics logging
    - _Requirements: 4.1, 4.3, 4.5, 7.5_
  
  - [ ]* 12.2 Write property test for error isolation
    - **Property 9: Error Isolation for Concept Processing**
    - **Validates: Requirements 4.3**
  
  - [ ]* 12.3 Write property test for API batching efficiency
    - **Property 10: API Batching Efficiency**
    - **Validates: Requirements 4.5**
  
  - [ ]* 12.4 Write property test for deferred enrichment marking
    - **Property 18: Deferred Enrichment Marking**
    - **Validates: Requirements 7.5**

- [x] 13. Implement cross-document linking
  - [x] 13.1 Add cross-document methods to EnrichmentService and KnowledgeGraphService
    - Implement async create_cross_document_links() in EnrichmentService
    - Implement SAME_AS relationship creation for shared Q-numbers
    - Add find_documents_by_entity() method to KnowledgeGraphService
    - Add query method that traverses SAME_AS relationships
    - _Requirements: 5.1, 5.2, 5.3_
  
  - [ ]* 13.2 Write property test for SAME_AS relationship creation
    - **Property 11: SAME_AS Relationship for Shared Q-Numbers**
    - **Validates: Requirements 5.1**
  
  - [ ]* 13.3 Write property test for cross-document query traversal
    - **Property 12: Cross-Document Query Traversal**
    - **Validates: Requirements 5.2**
  
  - [ ]* 13.4 Write property test for document lookup by entity
    - **Property 13: Document Lookup by Wikidata Entity**
    - **Validates: Requirements 5.3**

- [x] 14. Checkpoint - Ensure cross-document linking tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 15. Add dependency injection providers
  - [x] 15.1 Update `src/multimodal_librarian/api/dependencies/services.py`
    - Add get_wikidata_client() dependency provider
    - Add get_conceptnet_client() dependency provider
    - Add get_enrichment_cache() dependency provider
    - Add get_enrichment_service() and get_enrichment_service_optional() providers
    - Add cleanup functions for enrichment services
    - _Requirements: 4.2_

- [x] 16. Integrate with document processing pipeline
  - [x] 16.1 Update `src/multimodal_librarian/services/celery_service.py`
    - Import EnrichmentService in _update_knowledge_graph()
    - Call enrichment_service.enrich_concepts() after concept extraction
    - Add enrichment statistics to processing job metadata
    - Handle enrichment failures gracefully (don't fail document processing)
    - Added _enrich_concepts_with_external_knowledge() helper function
    - _Requirements: 4.1, 4.4_
  
  - [x] 16.2 Update `src/multimodal_librarian/components/knowledge_graph/kg_builder.py`
    - Concepts are already exposed via extraction.extracted_concepts
    - EnrichmentService receives concepts directly from celery_service
    - No changes needed - existing interface is sufficient
    - _Requirements: 4.1_

- [x] 17. Create Neo4j schema indexes
  - [x] 17.1 Add index creation to KnowledgeGraphService initialization
    - Create index on External_Entity_Node.q_number
    - Create index on Concept_Node.wikidata_qid
    - Add index creation to startup or migration script
    - _Requirements: 8.1, 8.2_

- [x] 18. Add API endpoints for enrichment management
  - [x] 18.1 Create `src/multimodal_librarian/api/routers/enrichment.py`
    - Add GET /enrichment/cache/stats endpoint
    - Add POST /enrichment/cache/clear endpoint
    - Add GET /enrichment/circuit-breaker/status endpoint
    - Add GET /enrichment/documents/{q_number} endpoint for document lookup
    - _Requirements: 6.4, 5.3_

- [x] 19. Final checkpoint - Run full test suite
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties
- Unit tests validate specific examples and edge cases
- The implementation follows the project's dependency injection architecture
- External API calls are async with timeouts to avoid blocking
- Circuit breaker pattern prevents cascade failures from API issues
