# Implementation Plan: Code Knowledge Graph

## Overview

This implementation plan converts the Code_Knowledge_Graph feature design into a series of prompts for a code-generation LLM that will implement each step with incremental progress. Each task builds on the previous tasks, and ends with wiring things together. There is no hanging or orphaned code that isn't integrated into a previous step. Focus is ONLY on tasks that involve writing, modifying, or testing code.

The implementation follows the existing codebase patterns:
- Uses Pydantic models for all data structures
- Follows async/await patterns throughout
- Integrates with the dependency injection system
- Uses the existing Neo4j client patterns from `neo4j_client.py`
- Follows the naming conventions from the project structure

## Tasks

### Phase 1: Core Infrastructure

- [ ] 1.1 Create Pydantic models for Code Knowledge Graph
  - Create `src/multimodal_librarian/models/code_knowledge_graph.py`
  - Define `ConceptType` enum with FUNCTION, CLASS, MODULE, METHOD, LIBRARY, API_ENDPOINT, TYPE, CONSTANT
  - Define `CodeRelationshipType` enum with CODE_CALLS, CODE_DEFINES, CODE_IMPORTS, CODE_INHERITS_FROM, CODE_IMPLEMENTS, CODE_RETURNS_TYPE, CODE_PARAMETER_TYPE, CODE_DOCUMENTED_BY
  - Define `CodeConcept` model with id, display_name, normalized_name, concept_type, source_documents, first_extracted_at, last_updated_at, version, metadata
  - Define `CodeRelationship` model with id, source_concept_id, target_concept_id, relationship_type, source_document, confidence, context, parameter_name, created_at
  - Define `EnrichmentContext` model with concept, relationships, source, confidence
  - _Requirements: 1.1, 1.2, 3.1, 3.8_

- [ ] 1.2 Implement pattern normalization algorithm
  - Create `src/multimodal_librarian/components/knowledge_graph/pattern_normalizer.py`
  - Implement `normalize_identifier()` function for snake_case, camelCase, PascalCase
  - Handle edge cases: acronyms (HTTP_Request), numbers (parse2DArray), leading underscores (__private_method)
  - Write unit tests for all pattern types
  - _Requirements: 2.1, 2.2, 2.6_

- [ ] 1.3 Create Neo4j schema with namespace isolation
  - Create `src/multimodal_librarian/clients/code_knowledge_graph_client.py`
  - Implement `ensure_schema()` method to create indexes and constraints
  - Create indexes: normalized_name, concept_type, display_name
  - Create fulltext index for fuzzy matching
  - Use `CodeConcept` label prefix and `CODE_` relationship prefix
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

- [ ] 1.4 Implement CodeKnowledgeGraphClient with basic CRUD operations
  - Implement `store_concept()` with deduplication based on normalized name hash
  - Implement `store_relationship()` with referential integrity
  - Implement `query_concepts()` with exact and fuzzy matching
  - Implement `query_relationships()` with optional type filter
  - Implement `get_related_concepts()` returning List[EnrichmentContext]
  - Add circuit breaker pattern for graceful degradation
  - Add retry logic with exponential backoff for write operations
  - _Requirements: 1.3, 1.4, 1.5, 3.1, 6.1, 6.2, 6.3, 6.4, 9.1, 9.2, 9.4, 11.1, 11.2, 14.3, 14.4_

- [ ]* 1.5 Write property tests for pattern normalization
  - **Property 2: Pattern Normalization Consistency**
  - **Validates: Requirements 1.1, 2.1, 2.2, 2.6**
  - Test that normalizing twice produces the same result
  - Test idempotence across all pattern types
  - Use Hypothesis with 100 examples per test

- [ ]* 1.6 Write property tests for concept deduplication
  - **Property 1: Concept Deduplication**
  - **Validates: Requirements 1.2, 1.3**
  - Test that duplicate concepts are merged with combined source documents
  - Test version increment on update
  - Use Hypothesis to generate random concept pairs

### Phase 2: Code Extraction

- [ ] 2.1 Implement Code_Extractor component
  - Create `src/multimodal_librarian/components/knowledge_graph/code_extractor.py`
  - Implement `CodeExtractor` class with async `extract_concepts()` method
  - Implement regex patterns for: snake_case identifiers, camelCase identifiers, method calls with parentheses, dot notation, import statements
  - Handle edge cases: acronyms, numbers, leading underscores
  - Return List[CodeConcept] with normalized names
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

- [ ] 2.2 Implement relationship inference from context
  - Add `extract_relationships()` method to CodeExtractor
  - Implement heuristics for CALLS, DEFINES, IMPORTS, INHERITS_FROM, RETURNS_TYPE, PARAMETER_TYPE
  - Use surrounding context to infer relationship type and confidence
  - Return List[CodeRelationship] with source/target concept IDs
  - _Requirements: 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

- [ ]* 2.3 Write property tests for Code_Extractor
  - **Property 11: Code Pattern Extraction**
  - **Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6**
  - Test extraction of all pattern types from sample documents
  - Test edge cases with mixed patterns
  - Use Hypothesis to generate random code-like strings

- [ ]* 2.4 Write property tests for relationship inference
  - **Property 12: Relationship Type Coverage**
  - **Validates: Requirements 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8**
  - Test that correct relationship types are created for each pattern
  - Test confidence scoring logic
  - Test context preservation

### Phase 3: Integration

- [ ] 3.1 Integrate CodeKnowledgeGraphClient with dependency injection
  - Add dependency provider in `src/multimodal_librarian/api/dependencies/services.py`
  - Implement `get_code_knowledge_graph_client()` function
  - Implement optional variant `get_code_knowledge_graph_client_optional()` for graceful degradation
  - Follow existing pattern from `get_neo4j_client()`
  - _Requirements: 15.1, 15.2, 15.3_

- [ ] 3.2 Integrate with EnrichmentService
  - Modify `src/multimodal_librarian/services/enrichment_service.py` (or appropriate location)
  - Add Code_Knowledge_Graph lookup before ConceptNet lookup
  - Implement fallback logic when Code_Knowledge_Graph is unavailable
  - Implement relationship merging with Code_Knowledge_Graph prioritization
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 8.1, 8.2, 8.3, 8.4, 8.5, 14.1, 14.2_

- [ ] 3.3 Implement ConceptNet fallback
  - Use normalized term names for ConceptNet lookup
  - Namespace ConceptNet relationships to distinguish from code-specific
  - Merge results with prioritization logic
  - _Requirements: 4.2, 4.3, 4.4, 4.5_

- [ ]* 3.4 Write property tests for EnrichmentService integration
  - **Property 4: Enrichment Service Fallback and Merging**
  - **Validates: Requirements 4.1, 4.2, 4.3, 4.4**
  - Test fallback from Code_Knowledge_Graph to ConceptNet
  - Test relationship merging with prioritization
  - Test graceful degradation on unavailability

- [ ]* 3.5 Write property tests for graceful degradation
  - **Property 8: Graceful Degradation**
  - **Validates: Requirements 9.5, 14.1, 14.4**
  - Test that EnrichmentService continues when Code_Knowledge_Graph is unavailable
  - Test warning logging without exception
  - Test ConceptNet-only operation

### Phase 4: External Sources

- [ ] 4.1 Implement CodeIntelligenceSources interface
  - Create `src/multimodal_librarian/components/knowledge_graph/code_intelligence_sources.py`
  - Define `CodeIntelligenceSource` Protocol with `fetch_concepts()`, `fetch_relationships()`, `get_last_modified()`
  - Implement base class with authentication and rate limiting
  - _Requirements: 5.1, 5.2_

- [ ] 4.2 Implement PyPI metadata source
  - Create `src/multimodal_librarian/components/knowledge_graph/pypi_source.py`
  - Implement `PyPIMetadataSource` class
  - Fetch package info from PyPI API
  - Extract module structures, dependencies, type stub references
  - Return concepts with source attribution
  - _Requirements: 5.3, 5.4_

- [ ] 4.3 Implement GitHub API source
  - Create `src/multimodal_librarian/components/knowledge_graph/github_source.py`
  - Implement `GitHubAPISource` class
  - Fetch repository structure and file paths
  - Extract dependency relationships from import statements
  - Handle authentication and rate limiting
  - _Requirements: 5.3, 5.4_

- [ ] 4.4 Implement sync mechanism for external sources
  - Add `sync_source()` method to CodeIntelligenceSource
  - Support full sync and incremental sync based on modification timestamps
  - Implement refresh mechanism for on-demand updates
  - _Requirements: 5.2, 5.5_

### Phase 5: Seed Data and Validation

- [ ] 5.1 Create seed dataset for Python stdlib
  - Create `src/multimodal_librarian/data/seed_data/python_stdlib.json`
  - Include common modules: os, sys, json, re, collections, itertools, functools
  - Include common functions: print, len, str, int, list, dict
  - Include common types: str, int, float, bool, list, dict, tuple, set
  - Add relationships between concepts
  - _Requirements: 12.1, 12.3_

- [ ] 5.2 Create seed dataset for LLM libraries
  - Create `src/multimodal_librarian/data/seed_data/llm_libraries.json`
  - Include OpenAI concepts: OpenAI, ChatCompletion, create(), messages
  - Include Anthropic concepts: Anthropic, Claude, messages.create()
  - Include LangChain concepts: LLMChain, PromptTemplate, Chain, Agent
  - Add relationships between library concepts
  - _Requirements: 12.2, 12.3_

- [ ] 5.3 Implement seed data loader
  - Create `src/multimodal_librarian/components/knowledge_graph/seed_data_loader.py`
  - Implement `SeedDataLoader` class with `load_seed_data()` method
  - Implement version checking for updatable seed data
  - Validate seed data structure before loading
  - _Requirements: 12.4, 12.5_

- [ ]* 5.4 Write property tests for seed data loader
  - **Property 9: Seed Data Completeness**
  - **Validates: Requirements 12.1, 12.2, 12.3**
  - Test that all seed concepts are loaded
  - Test that all seed relationships are created
  - Test version validation

### Phase 6: Observability

- [ ] 6.1 Add health check endpoints
  - Add `health_check()` method to CodeKnowledgeGraphClient
  - Add health check endpoint in `src/multimodal_librarian/api/routers/health.py` or appropriate location
  - Check Neo4j connectivity and operational status
  - Return diagnostic information
  - _Requirements: 13.1, 13.5_

- [ ] 6.2 Add metrics collection
  - Add metrics tracking to CodeKnowledgeGraphClient
  - Track: concept count, relationship count, query latency, cache hit rate
  - Integrate with existing CloudWatch metrics system
  - _Requirements: 13.2, 13.4_

- [ ] 6.3 Add structured logging
  - Add logging for: concept additions, sync operations, errors
  - Use structlog for structured logging
  - Log significant events with appropriate levels
  - _Requirements: 13.3_

- [ ]* 6.4 Write property tests for performance requirements
  - **Property 5: Query Performance Bound**
  - **Validates: Requirements 6.5, 9.1, 9.2**
  - Test that cached queries complete within 100ms
  - Test that store operations complete within 50ms

- [ ]* 6.5 Write property tests for batch operations
  - **Property 6: Batch Operation Throughput**
  - **Validates: Requirements 9.3**
  - Test that batch of 1000 concepts completes within 500ms
  - Use Hypothesis to generate random concept batches

- [ ]* 6.6 Write property tests for write atomicity
  - **Property 10: Write Atomicity**
  - **Validates: Requirements 11.2**
  - Test that concept and relationships are stored in single transaction
  - Test rollback on failure

- [ ]* 6.7 Write property tests for namespace isolation
  - **Property 7: Namespace Isolation**
  - **Validates: Requirements 7.1, 7.2, 7.3, 7.4, 7.5**
  - Test that CodeConcept queries don't return general knowledge nodes
  - Test that CODE_ prefix is applied to all relationships

### Phase 7: Integration and Wiring

- [ ] 7.1 Wire components together in main application
  - Import and initialize CodeKnowledgeGraphClient in dependency injection
  - Import and initialize CodeExtractor in enrichment pipeline
  - Import and initialize seed data loader for initial setup
  - Ensure proper startup order and lazy initialization
  - _Requirements: 8.1, 8.2, 8.3, 8.4_

- [ ] 7.2 Add startup initialization for seed data
  - Modify application startup to load seed data if not present
  - Add version checking for seed data updates
  - Log seed data loading status
  - _Requirements: 12.5_

- [ ] 7.3 Add error handling and recovery mechanisms
  - Implement recovery mechanism to rebuild graph from source documents
  - Add error logging and alerting integration
  - Test recovery procedures
  - _Requirements: 14.5_

- [ ] 7.4 Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties
- Unit tests validate specific examples and edge cases
- The implementation uses the existing Neo4j client patterns
- All async operations follow the established patterns in the codebase
- Pydantic models ensure type safety and validation