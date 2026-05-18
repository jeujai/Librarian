# Implementation Plan: YAGO Bulk Load

## Overview

This implementation plan covers the YAGO bulk-load feature for importing YAGO data into Neo4j. The system consists of three main components: YagoDumpProcessor for downloading and streaming the dump, YagoNeo4jLoader for batch importing into Neo4j, and YagoLocalClient for querying local data. The implementation follows a local-first pattern with graceful degradation to external API.

## Tasks

- [-] 1. Set up project structure and data models
  - [x] 1.1 Create yago components directory structure
    - Create `src/multimodal_librarian/components/yago/` directory
    - Create `__init__.py` with component exports
    - _Requirements: N/A (infrastructure setup)_

  - [x] 1.2 Define data models for YAGO entities
    - Create `src/multimodal_librarian/components/yago/models.py`
    - Implement `FilteredEntity` dataclass with entity_id, label, description, instance_of, subclass_of, aliases, see_also
    - Implement `YagoEntityData` dataclass for query responses
    - Implement `YagoSearchResult` dataclass
    - _Requirements: 3.3, 3.4, 5.1, 5.2, 5.3, 5.4, 5.5_

  - [x] 1.3 Set up logging configuration for YAGO components
    - Configure structured logger for yago components
    - Add progress and metrics logging
    - _Requirements: 12.1, 12.2, 12.3, 12.4_

- [x] 2. Implement YagoDumpProcessor
  - [x] 2.1 Create YagoDumpProcessor class structure
    - Create `src/multimodal_librarian/components/yago/processor.py`
    - Implement `__init__` with configurable paths and memory limits
    - Add memory tracking for 512MB limit compliance
    - _Requirements: 2.2_

  - [x] 2.2 Implement dump download with resume support
    - Implement `download()` method with HTTP range requests
    - Add MD5 checksum verification
    - Implement resume capability for interrupted downloads
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [x] 2.3 Implement streaming line-by-line processing
    - Implement `process()` as async iterator yielding filtered entities
    - Use streaming JSON parser (ijson or similar)
    - Ensure memory never exceeds 512MB during processing
    - _Requirements: 2.1, 2.2, 2.3_

  - [x] 2.4 Implement English entity filtering
    - Implement `has_english_label()` check for en, en-gb, en-us
    - Implement `extract_english_data()` for filtered entity extraction
    - Extract instanceOf (P31) and subclassOf (P279) claims
    - Extract aliases and see also references
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

  - [ ]* 2.5 Write property test for memory bound
    - **Property 4: Memory Bound**
    - **Validates: Requirements 2.2**
    - Test that processing never exceeds 512MB memory

  - [ ]* 2.6 Write property test for English filtering
    - **Property 5: English Only**
    - **Validates: Requirements 3.1, 3.2**
    - Test that only entities with English labels are emitted

  - [ ]* 2.7 Write unit tests for processor
    - Test English label detection
    - Test claim extraction (P31, P279)
    - Test alias and see_also extraction
    - Test resume support logic
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [x] 3. Implement YagoNeo4jLoader
  - [x] 3.1 Create YagoNeo4jLoader class structure
    - Create `src/multimodal_librarian/components/yago/loader.py`
    - Implement `__init__` with Neo4j client and batch size (default 1000)
    - _Requirements: 4.5, 4.6_

  - [x] 3.2 Implement batch import with retry logic
    - Implement `import_entities()` with async iterator input
    - Implement `_import_batch()` with 3 retries and exponential backoff
    - Track failed batches in dead letter queue
    - _Requirements: 11.1, 11.2, 11.3, 11.4_

  - [x] 3.3 Implement YagoEntity node creation
    - Implement `create_entity_node()` with :YagoEntity label
    - Set entity_id, label, description, data properties
    - Use yago namespace isolation
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.1.1, 4.1.2, 4.1.3, 4.1.6, 4.1.7, 4.1.8_

  - [x] 3.4 Implement relationship creation
    - Implement `create_relationships()` for INSTANCE_OF, SUBCLASS_OF
    - Implement ALIAS_OF and SEE_ALSO relationships
    - Ensure relationship types are prefixed with namespace
    - _Requirements: 4.3, 4.4, 4.1.4, 4.1.5_

  - [x] 3.5 Implement progress tracking and checkpointing
    - Implement `get_progress()` returning percentage
    - Track last successfully imported entity ID
    - Support resuming from checkpoint
    - _Requirements: 11.3, 11.4, 11.5_

  - [x] 3.6 Implement storage management methods
    - Implement `get_stats()` for entity and relationship counts
    - Implement `clear_all()` to remove all YAGO data
    - Implement `estimate_storage()` for pre-import estimates
    - _Requirements: 9.1, 9.3, 9.4_

  - [ ]* 3.7 Write property test for batch atomicity
    - **Property 8: Batch Atomicity**
    - **Validates: Requirements 4.6**
    - Test that each batch is imported atomically

  - [ ]* 3.8 Write property test for no duplicate nodes
    - **Property 10: No Duplicate Nodes**
    - **Validates: Requirements 4.4**
    - Test that each entity ID creates exactly one node

  - [ ]* 3.9 Write unit tests for loader
    - Test batch import with retry logic
    - Test dead letter queue behavior
    - Test node and relationship creation
    - Test progress tracking
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5_

- [x] 4. Implement YagoLocalClient
  - [x] 4.1 Create YagoLocalClient class structure
    - Create `src/multimodal_librarian/components/yago/local_client.py`
    - Implement Neo4j query methods
    - Add graceful degradation (return None when unavailable)
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 7.1, 7.5_

  - [x] 4.2 Implement get_entity method
    - Implement `get_entity(entity_id)` returning YagoEntityData
    - Query :YagoEntity nodes by entity_id
    - Return None if not found or Neo4j unavailable
    - _Requirements: 5.1, 7.1, 7.5_

  - [x] 4.3 Implement search_entities method
    - Implement `search_entities(query, limit)` for fuzzy search
    - Use CONTAINS query for label matching
    - Return list of YagoSearchResult
    - _Requirements: 5.2, 7.1_

  - [x] 4.4 Implement get_instances_of method
    - Implement `get_instances_of(class_id, limit)` returning entity IDs
    - Query :INSTANCE_OF relationships to target class
    - _Requirements: 5.3, 7.1_

  - [x] 4.5 Implement get_subclasses_of method
    - Implement `get_subclasses_of(class_id, limit)` returning entity IDs
    - Query :SUBCLASS_OF relationships from parent class
    - _Requirements: 5.4, 7.1_

  - [x] 4.6 Implement get_related_entities method
    - Implement `get_related_entities(entity_id, relationship_type)`
    - Query by relationship type (INSTANCE_OF, SUBCLASS_OF, etc.)
    - _Requirements: 5.5, 7.1_

  - [x] 4.7 Implement is_available method
    - Implement `is_available()` to check if YAGO data is loaded
    - Query for existence of any :YagoEntity nodes
    - _Requirements: 7.1_

  - [ ]* 4.8 Write property test for query accuracy
    - **Property 12: Local Query Accuracy**
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5**
    - Test that local queries return correct data

  - [ ]* 4.9 Write property test for graceful degradation
    - **Property 13: Graceful Degradation**
    - **Validates: Requirements 7.1, 7.5**
    - Test that client returns None when data unavailable

  - [ ]* 4.10 Write unit tests for local client
    - Test all query methods
    - Test graceful degradation scenarios
    - Test is_available check
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 7.1, 7.5_

- [x] 5. Implement API fallback wrapper
  - [x] 5.1 Create YagoAPIFallback class
    - Create `src/multimodal_librarian/components/yago/fallback.py`
    - Implement local-first pattern with external API fallback
    - Log which data source was used
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [x] 5.2 Implement unified get_entity with fallback
    - Try local client first, fall back to external API
    - Return None if both unavailable
    - Log data source for each query
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [ ]* 5.3 Write unit tests for fallback behavior
    - Test local-first lookup
    - Test fallback to external API
    - Test logging of data source
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

- [x] 6. Register in dependency injection system
  - [x] 6.1 Add YagoLocalClient dependency
    - Add `get_yago_local_client()` to `api/dependencies/services.py`
    - Return None if YAGO data not loaded
    - Handle Neo4j connection errors gracefully
    - _Requirements: 10.4_

  - [x] 6.2 Add YagoClient with fallback dependency
    - Add `get_yago_client()` combining local and external
    - Use YagoAPIFallback when local available
    - Return external client otherwise
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

  - [x] 6.3 Update enrichment service to use YagoClient
    - Modify `services/enrichment_service.py` to use injected client
    - Ensure same interface as external API
    - _Requirements: 10.1, 10.2, 10.3_

- [x] 7. Implement incremental update support
  - [x] 7.1 Add incremental processing to YagoDumpProcessor
    - Support processing incremental dump files
    - Track processed timestamps
    - _Requirements: 8.1_

  - [x] 7.2 Add update and delete logic to YagoNeo4jLoader
    - Update existing entities when processing incremental
    - Remove entities not in incremental dump
    - Track last processed timestamp
    - _Requirements: 8.2, 8.3, 8.4_

  - [ ]* 7.3 Write unit tests for incremental updates
    - Test entity updates
    - Test entity deletions
    - Test timestamp tracking
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

- [-] 8. Add health check endpoint
  - [x] 8.1 Create YAGO health check
    - Add health check to `monitoring/health_check_system.py`
    - Check YAGO data availability
    - Return status and stats
    - _Requirements: 12.5_

- [x] 9. Checkpoint - Integration and testing
  - [x] 9.1 Run all unit tests
    - Ensure all tests pass
    - Fix any failing tests
    - _Requirements: All_

  - [x] 9.2 Run property-based tests
    - Verify memory bound property
    - Verify English filtering property
    - Verify batch atomicity property
    - Verify query accuracy property
    - _Requirements: 2.2, 3.1, 3.2, 4.6, 5.1, 5.2, 5.3, 5.4, 5.5_

  - [x] 9.3 Verify graceful degradation
    - Test with Neo4j unavailable
    - Test fallback to external API
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [x] 9.4 Ensure all tests pass, ask the user if questions arise.

- [x] 10. Performance optimization and tuning
  - [x] 10.1 Tune batch size for optimal throughput
    - Benchmark import rates with different batch sizes
    - Adjust based on Neo4j performance
    - _Requirements: 2.3, 4.5, 4.6_

  - [x] 10.2 Optimize query performance
    - Add Neo4j indexes for entity_id and label
    - Verify query latency under 100ms
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [x]* 10.3 Write performance tests
    - Test processing throughput (10k entities/sec)
    - Test import rate (1k entities/sec)
    - Test query latency (<100ms)
    - _Requirements: 2.3, 4.5, 4.6, 5.1, 5.2, 5.3, 5.4, 5.5_

- [-] 11. Documentation and cleanup
  - [x] 11.1 Add module docstrings and type hints
    - Ensure all public methods have docstrings
    - Verify type hints are complete
    - _Requirements: N/A (code quality)_

  - [x] 11.2 Update component exports
    - Update `components/yago/__init__.py`
    - Export all public classes and functions
    - _Requirements: N/A (infrastructure)_

  - [x] 11.3 Wire up EnrichmentService to use DI system
    - Register EnrichmentService as a DI-managed service
    - Inject YagoClient via get_yago_client dependency
    - Ensure local-first fallback is used for all YAGO queries
    - _Requirements: 10.1, 10.2, 10.3_

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties
- Unit tests validate specific examples and edge cases
- The implementation uses Python async/await patterns consistent with the codebase
- Neo4j queries use the existing GraphClient pattern from the codebase
