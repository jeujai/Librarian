# Implementation Plan: UMLS Knowledge Graph Integration

## Overview

Incrementally build the four UMLS components (Loader, Client, Linker, Query Expander), integrate them into the existing knowledge graph pipeline, and wire up DI, health checks, and scoring adjustments. Each task builds on the previous, with property-based and unit tests close to implementation.

## Tasks

- [x] 1. Create data models and Neo4j index setup
  - [x] 1.1 Create UMLS dataclasses (LoadResult, DryRunResult, UMLSStats, ExpandedTerm) in `src/multimodal_librarian/components/knowledge_graph/umls_loader.py`
    - Define `LoadResult`, `DryRunResult`, `UMLSStats` as `@dataclass` classes
    - Define `ExpandedTerm` dataclass in `src/multimodal_librarian/components/knowledge_graph/umls_query_expander.py`
    - _Requirements: 1.3, 1.4, 2.3, 3.3, 7.4, 10.1_

  - [x] 1.2 Implement `create_indexes` method in `UMLSLoader.__init__` skeleton and index creation
    - Create `UMLSLoader` class skeleton with `__init__(self, neo4j_client)`
    - Implement `create_indexes()` that runs `CREATE INDEX` Cypher for `UMLSConcept.cui`, `UMLSConcept.preferred_name`, `UMLSSemanticType.type_id`
    - _Requirements: 10.3_

- [x] 2. Implement UMLS Semantic Network loading (Lite Tier)
  - [x] 2.1 Implement `load_semantic_network` in `UMLSLoader`
    - Parse SRDEF file to extract semantic type definitions (127 types) and relationship definitions (54 relationships)
    - Create `UMLSSemanticType` nodes with properties: `type_id`, `type_name`, `definition`, `tree_number`
    - Create `UMLS_SEMANTIC_REL` edges between `UMLSSemanticType` nodes with properties: `relation_name`, `relation_inverse`, `definition`
    - Create/update `UMLSMetadata` singleton node with `loaded_tier`, `load_timestamp`, `umls_version`
    - All labels use UMLS prefix for namespace isolation
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 11.3_

  - [ ]* 2.2 Write property test for Semantic Network loading round-trip
    - **Property 1: Semantic Network Loading Round-Trip**
    - Use Hypothesis to generate synthetic SRDEF entries, load into Neo4j mock, verify all nodes and edges have required properties with UMLS-prefixed labels
    - **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.6**

  - [ ]* 2.3 Write unit tests for Semantic Network loading
    - Test empty SRDEF file returns zero nodes/edges
    - Test correct property mapping for type nodes and relationship edges
    - Test `UMLSMetadata` node is created with `loaded_tier = "lite"`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

- [x] 3. Implement UMLS Metathesaurus concept loading (Full Tier)
  - [x] 3.1 Implement `load_concepts` in `UMLSLoader`
    - Parse MRCONSO.csv filtering for English-language entries (LAT = ENG)
    - Support `source_vocabs` filter for subset mode (e.g., SNOMEDCT_US, MeSH, RXNORM)
    - Create `UMLSConcept` nodes with `cui`, `preferred_name` (TS=P, STT=PF), `synonyms` list, `source_vocabulary`, `suppressed`
    - Merge multiple names for same CUI: preferred name as primary, others as synonyms
    - Use configurable batch size (default 5000) for transactions
    - Support `memory_limit_mb` parameter to stop import if exceeded
    - Parse MRSTY file to create `HAS_SEMANTIC_TYPE` edges from `UMLSConcept` to `UMLSSemanticType`
    - Log progress every 50000 records with elapsed time and ETA
    - Update `UMLSMetadata` with `loaded_tier = "full"`, `last_batch_number`, `import_status`
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 10.2, 10.4, 11.3_

  - [ ]* 3.2 Write property tests for concept loading
    - **Property 2: Concept Loading Round-Trip** — load valid MRCONSO entries, verify all required properties present
    - **Property 3: Concept Loading Filters Only English Terms from Specified Vocabularies** — verify LAT=ENG filter and vocab subset filter
    - **Property 4: Synonym Aggregation Under Same CUI** — verify preferred name selection and synonym list
    - **Property 5: Batch Size Does Not Affect Final State** — load same data with different batch sizes, verify identical results
    - **Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6**

  - [ ]* 3.3 Write unit tests for concept loading edge cases
    - Test MRCONSO with only non-English rows produces zero nodes
    - Test duplicate CUI merges synonyms correctly
    - Test memory limit stops import when exceeded
    - Test progress logging at 50000 record intervals
    - _Requirements: 2.2, 2.4, 2.5, 10.2, 10.4_

- [x] 4. Implement UMLS relationship loading
  - [x] 4.1 Implement `load_relationships` in `UMLSLoader`
    - Parse MRREL.csv and create typed edges between `UMLSConcept` nodes
    - Map REL/RELA fields to `UMLS_` prefixed edge types (e.g., `UMLS_treats`, `UMLS_causes`)
    - Store edge properties: `rel_type`, `rela_type`, `source_vocabulary`, `cui_pair`
    - Use configurable batch size (default 10000)
    - Support `source_vocabs` filter matching concept subset
    - Skip relationships where both source and target CUIs are absent from loaded concept set
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [ ]* 4.2 Write property tests for relationship loading
    - **Property 6: Relationship Loading Round-Trip with Semantic Type Mapping** — verify edges have required properties with UMLS_ prefix
    - **Property 7: Dangling Relationships Are Skipped** — verify no edges for CUI pairs absent from concept set
    - **Validates: Requirements 2.7, 3.1, 3.2, 3.3, 3.5, 3.6**

  - [ ]* 4.3 Write unit tests for relationship loading edge cases
    - Test MRREL with all dangling CUIs produces zero edges
    - Test vocabulary filter excludes relationships from non-matching SABs
    - Test malformed MRREL rows are skipped with warning log
    - _Requirements: 3.5, 3.6, 12.5_

- [x] 5. Checkpoint — Loader complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implement dry-run, data management, and error handling in UMLSLoader
  - [x] 6.1 Implement `dry_run` method
    - Scan MRCONSO/MRREL files to estimate node count, relationship count, and approximate memory usage
    - Return `DryRunResult` with `fits_in_budget` and `recommended_vocabs` when memory exceeds limit
    - _Requirements: 10.1, 10.2, 10.5_

  - [x] 6.2 Implement `remove_all_umls_data` and `get_umls_stats`
    - `remove_all_umls_data`: delete all `UMLSConcept`, `UMLSSemanticType`, `UMLSMetadata` nodes and `UMLS_*` relationships
    - `get_umls_stats`: return counts and metadata from `UMLSMetadata` node
    - _Requirements: 11.1, 11.2, 11.3_

  - [x] 6.3 Implement version replacement and resume support
    - When loading a new UMLS version, remove previous version data before importing
    - Track `last_batch_number` in `UMLSMetadata` for resume support
    - Implement `resume_import` that continues from last successful batch
    - _Requirements: 11.4, 11.5, 12.3, 12.4_

  - [x] 6.4 Implement batch retry and malformed row handling
    - Retry failed batches up to 3 times with exponential backoff (1s, 2s, 4s)
    - Log failed batch details and continue with next batch after retries exhausted
    - Skip malformed CSV rows with descriptive log warning, continue processing
    - _Requirements: 12.1, 12.2, 12.5_

  - [ ]* 6.5 Write property tests for data management
    - **Property 15: Dry-Run Estimates Are Non-Negative and Proportional** — verify non-negative estimates and fits_in_budget logic
    - **Property 16: Remove All Clears UMLS Data Completely** — verify zero UMLS nodes/edges after removal
    - **Property 17: Version Replacement Removes Previous Data** — verify only new version data remains
    - **Property 18: Resume Produces Same Final State as Uninterrupted Load** — verify resume equivalence
    - **Property 19: Malformed Rows and Failed Batches Do Not Block Valid Data** — verify valid rows loaded despite errors
    - **Validates: Requirements 10.1, 10.2, 10.5, 11.1, 11.4, 11.5, 12.2, 12.3, 12.4, 12.5**

  - [ ]* 6.6 Write unit tests for error handling
    - Test FileNotFoundError for missing SRDEF/MRCONSO/MRREL files
    - Test retry logic with simulated Neo4j failures
    - Test resume from specific batch number
    - Test transaction timeout triggers batch size reduction
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5_

- [x] 7. Checkpoint — Loader fully complete with management and error handling
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Implement UMLS_Client
  - [x] 8.1 Implement `UMLSClient` class in `src/multimodal_librarian/components/knowledge_graph/umls_client.py`
    - Implement `__init__` with `neo4j_client`, `cache_ttl`, `cache_max_size` parameters
    - Implement LRU cache with TTL using `cachetools.TTLCache` (or dict-based LRU with timestamps)
    - Implement `initialize()`, `is_available()`, `get_loaded_tier()`
    - Implement `lookup_by_cui(cui)` — Cypher query for `UMLSConcept` by CUI
    - Implement `search_by_name(name)` — case-insensitive match against `preferred_name` and `synonyms`
    - Implement `get_synonyms(cui)` — return synonyms list for CUI
    - Implement `get_semantic_types(cui)` — traverse `HAS_SEMANTIC_TYPE` edges
    - Implement `get_related_concepts(cui, relationship_type, limit)` — traverse `UMLS_*` edges
    - Implement `batch_search_by_names(names)` — single Cypher query for multiple names
    - All methods return `None` when Neo4j unavailable or UMLS not loaded
    - Log query latency via `structlog` for each method
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 9.2, 13.2, 13.3, 13.4_

  - [ ]* 8.2 Write property tests for UMLS_Client
    - **Property 8: Client Query Round-Trip** — verify all query methods return data consistent with loaded state
    - **Property 9: Batch Search Consistency** — verify batch_search_by_names matches individual search_by_name results
    - **Property 10: Graceful Degradation** (client portion) — verify all methods return None when unavailable
    - **Property 20: Cache Size Never Exceeds Maximum and Returns Consistent Results** — verify cache bounds and consistency
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 13.3, 13.4**

  - [ ]* 8.3 Write unit tests for UMLS_Client
    - Test CUI not found returns None
    - Test case-insensitive name search matches uppercase/lowercase/mixed
    - Test empty synonyms list returns empty list (not None)
    - Test unavailable Neo4j returns None for all methods
    - Test cache TTL expiration triggers re-query
    - Test LRU eviction at max cache size
    - _Requirements: 4.1, 4.2, 4.3, 4.7, 13.3, 13.4_

- [x] 9. Implement UMLS_Linker
  - [x] 9.1 Implement `UMLSLinker` class in `src/multimodal_librarian/components/knowledge_graph/umls_linker.py`
    - Implement `__init__` with optional `umls_client` parameter
    - Implement `link_concepts(concepts, document_context)`:
      - Use `batch_search_by_names` to look up all concept names in single query
      - For matched concepts, set `external_ids["umls_cui"]` to matched CUI
      - For matched concepts with `concept_type == "ENTITY"`, update `concept_type` to UMLS semantic type name
      - When multiple matches found, select match whose semantic type is most consistent with document context
      - When `umls_client` is None or unavailable, return input concepts unchanged
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 9.3_

  - [ ]* 9.2 Write property tests for UMLS_Linker
    - **Property 11: Linker Sets CUI and Updates Semantic Type for Default-Typed Concepts** — verify CUI set and concept_type updated only for ENTITY defaults
    - **Property 10: Graceful Degradation** (linker portion) — verify passthrough when client is None
    - **Validates: Requirements 5.2, 5.3, 5.6**

  - [ ]* 9.3 Write unit tests for UMLS_Linker
    - Test all concepts match — verify all get CUI and semantic type
    - Test no concepts match — verify concepts returned unchanged
    - Test mixed match/no-match
    - Test concept_type already set (non-ENTITY) is not overwritten
    - Test multiple UMLS matches disambiguation
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

- [x] 10. Implement UMLS_Query_Expander
  - [x] 10.1 Implement `UMLSQueryExpander` class in `src/multimodal_librarian/components/knowledge_graph/umls_query_expander.py`
    - Implement `__init__` with optional `umls_client` parameter
    - Implement `expand_query(query_terms, max_synonyms)`:
      - For each term, search UMLS by name
      - Retrieve up to `max_synonyms` (default 5) synonyms ranked by term frequency
      - Retrieve directly related concepts (1-hop) via UMLS relationships
      - Assign weights between 0.3 and 0.8 based on relationship distance and type
      - Return list of `ExpandedTerm` with `term`, `weight`, `source`, `cui`
      - When `umls_client` is None, return empty list
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 9.4_

  - [ ]* 10.2 Write property tests for UMLS_Query_Expander
    - **Property 13: Query Expansion Invariants** — verify max 5 synonyms, weights in [0.3, 0.8], both synonym and related sources
    - **Property 10: Graceful Degradation** (expander portion) — verify empty list when client is None
    - **Validates: Requirements 7.1, 7.2, 7.3, 7.4, 7.5**

  - [ ]* 10.3 Write unit tests for UMLS_Query_Expander
    - Test no UMLS matches returns empty list
    - Test term with no synonyms returns only related concepts
    - Test term with >5 synonyms truncates to 5
    - Test weight range enforcement
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

- [x] 11. Checkpoint — All four components implemented
  - Ensure all tests pass, ask the user if questions arise.

- [x] 12. Integrate UMLS into existing components
  - [x] 12.1 Add UMLS validation tier to `ConceptNetValidator`
    - Add optional `umls_client` constructor parameter
    - Add `kept_by_umls: int = 0` field to `ValidationResult`
    - In `validate_concepts`, after ConceptNet batch lookup, check unmatched concepts against UMLS via `batch_search_by_names`
    - Treat UMLS match as Tier 1b (between ConceptNet Tier 1 and NER Tier 2)
    - For biomedical documents, prefer UMLS semantic type over ConceptNet when both match
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [ ]* 12.2 Write property test for UMLS validation tier
    - **Property 12: UMLS Validation Tier Counts Are Consistent** — verify kept_by_umls count matches UMLS-only validated concepts
    - **Validates: Requirements 6.1, 6.2, 6.4**

  - [x] 12.3 Add UMLS semantic type boosting to `KG_Query_Engine`
    - Accept optional `umls_client` via DI
    - In reranking logic, apply 1.2x multiplier for UMLS-grounded concepts matching query domain
    - Apply 0.7x penalty for semantic type contradictions
    - When UMLS unavailable, use existing scoring unchanged
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

  - [ ]* 12.4 Write property test for UMLS scoring adjustments
    - **Property 14: UMLS Semantic Type Scoring Adjustments** — verify 1.2x boost and 0.7x penalty applied correctly
    - **Validates: Requirements 8.1, 8.2, 8.3**

  - [ ]* 12.5 Write unit tests for existing component modifications
    - Test ConceptNetValidator with concept passing UMLS but not ConceptNet
    - Test ConceptNetValidator with concept passing both
    - Test KG_Query_Engine scoring with matching semantic types
    - Test KG_Query_Engine scoring with contradicting semantic types
    - Test KG_Query_Engine scoring with non-biomedical query (no adjustment)
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 8.1, 8.2, 8.3, 8.4_

- [x] 13. Wire up Dependency Injection and Health Checks
  - [x] 13.1 Register UMLS_Client in DI system
    - Add `get_umls_client()` (required variant, raises if unavailable) to `src/multimodal_librarian/api/dependencies/services.py`
    - Add `get_umls_client_optional()` (returns None if unavailable) to `src/multimodal_librarian/api/dependencies/services.py`
    - Follow existing singleton caching pattern from other DI providers
    - Wire `umls_client` into `ConceptNetValidator`, `KG_Query_Engine`, `UMLSLinker`, `UMLSQueryExpander` via DI
    - _Requirements: 9.6_

  - [x] 13.2 Add UMLS health check
    - Register UMLS health check in `HealthCheckSystem` that reports loaded tier (none/lite/full), concept count, and relationship count
    - Log warning at startup if UMLS data is not detected in Neo4j
    - _Requirements: 9.1, 9.5, 13.1_

  - [ ]* 13.3 Write unit tests for DI and health check
    - Test `get_umls_client()` raises when Neo4j unavailable
    - Test `get_umls_client_optional()` returns None when unavailable
    - Test health check reports correct tier for none/lite/full states
    - _Requirements: 9.1, 9.5, 9.6, 13.1_

- [ ] 14. Integration testing
  - [ ]* 14.1 Write integration tests in `tests/integration/test_umls_integration.py`
    - Test full load pipeline: SRDEF → MRCONSO → MRSTY → MRREL → verify graph integrity
    - Test end-to-end query: load subset, extract concepts from medical text, verify CUI linking, run query with expansion
    - Test graceful degradation: verify all endpoints work without UMLS data
    - Test health check reports correct status for none/lite/full tiers
    - _Requirements: 1.1–1.6, 2.1–2.7, 3.1–3.6, 4.1–4.7, 5.1–5.6, 7.1–7.5, 9.1–9.6, 13.1_

- [x] 15. Final checkpoint — All components integrated and tested
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Property tests use Hypothesis and reference design document properties by number
- All UMLS data uses `UMLS` prefix labels/relationships for namespace isolation
- The system degrades gracefully at every layer when UMLS data is not loaded
- Checkpoints ensure incremental validation throughout implementation
