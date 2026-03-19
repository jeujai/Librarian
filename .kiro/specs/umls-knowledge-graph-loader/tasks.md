# Implementation Plan: UMLS Knowledge Graph Loader

## Overview

Extend the existing UMLS loading infrastructure with a new RRF parser module, UMLSBridger for SAME_AS edges, CLI orchestration script, and enhanced UMLSLoader methods (definitions, config check, per-category cleanup counts, SAME_AS stats). Implementation builds incrementally: parser → loader extensions → bridger → CLI → wiring.

## Tasks

- [ ] 1. Create RRF Parser module with dataclasses and streaming parsers
  - [ ] 1.1 Create `src/multimodal_librarian/components/knowledge_graph/rrf_parser.py` with dataclasses and parser functions
    - Define `MRCONSORow`, `MRRELRow`, `MRSTYRow`, `MRDEFRow` dataclasses
    - Implement `parse_mrconso(path, source_vocabs)` generator: stream line-by-line, split on `|`, filter LAT="ENG" and optional SAB filter, yield `MRCONSORow`, log warning with line number for malformed rows
    - Implement `parse_mrrel(path, source_vocabs)` generator: stream line-by-line, filter optional SAB, yield `MRRELRow`, log malformed rows
    - Implement `parse_mrsty(path)` generator: stream line-by-line, yield `MRSTYRow`, log malformed rows
    - Implement `parse_mrdef(path, source_vocabs)` generator: stream line-by-line, filter optional SAB, yield `MRDEFRow`, log malformed rows
    - Implement `validate_rrf_directory(rrf_dir)` returning `(found_files, missing_required)` — require MRCONSO.RRF and MRREL.RRF, optional MRSTY.RRF, MRDEF.RRF, SRDEF
    - Raise `FileNotFoundError` for missing required files when parsers are called with non-existent paths
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8_

  - [ ]* 1.2 Write property tests for RRF parser round-trip parsing
    - **Property 1: RRF parsing round trip**
    - Generate random valid RRF row dataclasses, serialize to pipe-delimited string at correct field positions, parse back, assert field equality
    - **Validates: Requirements 2.1, 2.4, 2.5, 2.6**

  - [ ]* 1.3 Write property tests for MRCONSO filter invariant
    - **Property 2: MRCONSO filter invariant**
    - Generate random MRCONSO lines with mixed LAT/SAB values, parse with filters, assert all output rows have LAT="ENG" and SAB in filter set
    - **Validates: Requirements 2.2, 2.3**

  - [ ]* 1.4 Write property tests for MRREL filter invariant
    - **Property 3: MRREL filter invariant**
    - Generate random MRREL lines with mixed SAB values, parse with vocab filter, assert all output rows have SAB in filter set
    - **Validates: Requirements 4.3**

  - [ ]* 1.5 Write property tests for malformed row skipping
    - **Property 4: Malformed rows are skipped**
    - Generate RRF files with mixed valid/invalid rows (fewer fields), assert output count equals valid row count
    - **Validates: Requirements 2.8**

  - [ ]* 1.6 Write unit tests for `validate_rrf_directory` and missing file errors
    - **Property 5: Missing required files raise FileNotFoundError**
    - Test `validate_rrf_directory` reports missing MRCONSO.RRF/MRREL.RRF
    - Test parsers raise `FileNotFoundError` for non-existent paths
    - Test optional files (MRDEF, MRSTY, SRDEF) reported as optional, not required
    - **Validates: Requirements 2.7**

- [ ] 2. Checkpoint - Ensure all RRF parser tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 3. Extend UMLSLoader with definitions, enhanced cleanup, config check, and SAME_AS stats
  - [ ] 3.1 Add `same_as_count` field to `UMLSStats` dataclass and update `get_umls_stats` to query SAME_AS edge count
    - Add `same_as_count: int` field to `UMLSStats` (default 0)
    - Add Cypher query `MATCH ()-[r:SAME_AS]->() RETURN count(r) AS count` in `get_umls_stats`
    - _Requirements: 1.5_

  - [ ] 3.2 Implement `load_definitions` method on `UMLSLoader`
    - Add `async def load_definitions(self, mrdef_path, source_vocabs, batch_size=5000) -> LoadResult`
    - Use `parse_mrdef` from `rrf_parser` to stream definitions
    - Aggregate first definition per CUI (after vocab filtering)
    - Batch UNWIND `MATCH (c:UMLSConcept {cui: item.cui}) SET c.definition = item.definition`
    - Track progress with `last_batch_number` on UMLSMetadata
    - _Requirements: 3.4_

  - [ ] 3.3 Implement `remove_all_umls_data_with_counts` method on `UMLSLoader`
    - Add `async def remove_all_umls_data_with_counts(self, include_same_as=True) -> Dict[str, int]`
    - Delete in order: UMLS_REL, UMLS_SEMANTIC_REL, HAS_SEMANTIC_TYPE, SAME_AS (if include_same_as), UMLSConcept, UMLSSemanticType, UMLSRelationshipDef, UMLSMetadata
    - Use count-returning Cypher for each category (e.g., `MATCH ()-[r:UMLS_REL]->() WITH r LIMIT 50000 DELETE r RETURN count(r)` in batches)
    - Return dict mapping category name to deleted count
    - _Requirements: 9.1, 9.2, 9.4_

  - [ ] 3.4 Implement `check_neo4j_config` method on `UMLSLoader`
    - Add `async def check_neo4j_config(self) -> Dict[str, Any]`
    - Query Neo4j for heap size, page cache size, and store size via `CALL dbms.listConfig()` or equivalent
    - Compare against recommended minimums: heap 5-6 GB, page cache 3 GB
    - Return dict with current values, recommended values, and whether config is sufficient
    - If insufficient, include recommended `docker-compose.yml` environment variable changes
    - _Requirements: 8.1, 8.2, 8.3_

  - [ ]* 3.5 Write property test for CUI aggregation preferred name selection
    - **Property 6: CUI aggregation selects correct preferred name**
    - Generate random MRCONSO row groups per CUI with one TS="P"/STT="PF" row, assert preferred_name matches that row's STR
    - **Validates: Requirements 3.1**

  - [ ]* 3.6 Write property test for edge type derivation
    - **Property 10: Edge type derivation**
    - Generate random MRREL rows with/without RELA, assert edge_type is `UMLS_{RELA}` when RELA non-empty, `UMLS_{REL}` otherwise
    - **Validates: Requirements 4.5, 4.1, 4.2**

  - [ ]* 3.7 Write unit tests for `load_definitions`, `remove_all_umls_data_with_counts`, `check_neo4j_config`, and `get_umls_stats` with SAME_AS count
    - Test `load_definitions` stores definition on matching CUI (mock Neo4j)
    - Test `load_definitions` skips CUIs not in loaded set
    - Test `remove_all_umls_data_with_counts` returns per-category counts
    - Test `remove_all_umls_data_with_counts` deletes relationships before nodes (verify call order)
    - Test `check_neo4j_config` returns heap/page-cache assessment
    - Test `get_umls_stats` includes `same_as_count`
    - Test default batch sizes: 5000 concepts, 10000 relationships
    - _Requirements: 3.4, 9.1, 9.2, 9.4, 8.1, 8.2, 1.5, 7.2_

- [ ] 4. Checkpoint - Ensure all UMLSLoader extension tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 5. Create UMLSBridger module for SAME_AS edge creation
  - [ ] 5.1 Create `src/multimodal_librarian/components/knowledge_graph/umls_bridger.py`
    - Define `BridgeResult` dataclass with `concepts_matched`, `same_as_edges_created`, `unmatched_concepts`, `elapsed_seconds`
    - Implement `UMLSBridger.__init__(self, neo4j_client)`
    - Implement `async def create_same_as_edges(self, batch_size=1000) -> BridgeResult`
    - Query all Concept nodes (`concept_name`) and all UMLSConcept nodes (`preferred_name`, `synonyms`)
    - Case-insensitive exact match on `preferred_name` and `synonyms` list entries
    - Batch UNWIND MERGE SAME_AS edges with `match_type` ("preferred_name" or "synonym") and `created_at` timestamp
    - Idempotent via MERGE — no duplicate edges on re-run
    - Log total matched, edges created, unmatched counts
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7_

  - [ ]* 5.2 Write property test for SAME_AS bridging completeness
    - **Property 11: SAME_AS bridging completeness**
    - Generate random Concept/UMLSConcept name sets with known overlaps, mock Neo4j, assert SAME_AS edges for all case-insensitive matches with correct `match_type`
    - **Validates: Requirements 5.2, 5.3, 5.5**

  - [ ]* 5.3 Write property test for SAME_AS bridging idempotence
    - **Property 12: SAME_AS bridging idempotence**
    - Run `create_same_as_edges` twice on same mock data, assert same edge count both times
    - **Validates: Requirements 5.7**

  - [ ]* 5.4 Write unit tests for UMLSBridger
    - Test case-insensitive matching ("Diabetes" matches "diabetes")
    - Test synonym matching (concept_name matches a synonym entry)
    - Test `BridgeResult` contains correct matched/unmatched/edge counts
    - Test no Concept nodes in graph produces zero SAME_AS edges
    - Test no UMLSConcept nodes in graph produces zero SAME_AS edges
    - _Requirements: 5.2, 5.3, 5.6, 5.7_

- [ ] 6. Checkpoint - Ensure all UMLSBridger tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 7. Create CLI script with subcommands and orchestration
  - [ ] 7.1 Create `scripts/load_umls.py` with argparse subcommands and handler functions
    - Implement `main()` with argparse: subcommands `dry-run`, `load`, `bridge`, `stats`, `clean`
    - Implement `load` subcommand arguments: `rrf_dir` (positional), `--vocabs`, `--batch-size` (default 5000), `--rel-batch-size` (default 10000), `--memory-limit`, `--resume`, `--bridge`, `--neo4j-uri`, `--neo4j-user`, `--neo4j-password`, `--check-config`
    - Implement `clean` subcommand with `--confirm` flag; prompt interactively without it
    - Default vocabulary set to Targeted_Vocabulary_Set when `--vocabs` not specified
    - Instantiate `Neo4jClient` directly (not via FastAPI DI) using args or env vars
    - _Requirements: 1.1, 1.2, 1.7, 1.8, 9.3_

  - [ ] 7.2 Implement `cmd_load` handler with correct execution order
    - Execute in order: (a) create indexes, (b) load semantic network from SRDEF if present, (c) load concepts from MRCONSO, (d) load semantic type edges from MRSTY, (e) load definitions from MRDEF, (f) load relationships from MRREL
    - If `--bridge` flag set, run `UMLSBridger.create_same_as_edges()` after relationship loading
    - If `--resume` flag set, read `last_batch_number` from UMLSMetadata and skip completed batches
    - If `--memory-limit` set, run dry-run estimate first and abort if exceeds limit
    - If `--check-config` set, run `check_neo4j_config` before loading
    - Set `import_status` to "in_progress" at start, "complete" on success
    - Print summary: total concepts, relationships, SAME_AS edges (if bridged), elapsed time, failed batches
    - Skip SRDEF gracefully if missing (log warning, continue)
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 6.2, 6.3, 7.1, 8.1_

  - [ ] 7.3 Implement `cmd_dry_run`, `cmd_bridge`, `cmd_stats`, `cmd_clean` handlers
    - `cmd_dry_run`: call `validate_rrf_directory`, scan RRF files via parsers, report estimated counts and memory usage, recommend reduced vocabs if over budget
    - `cmd_bridge`: instantiate `UMLSBridger`, call `create_same_as_edges`, print `BridgeResult`
    - `cmd_stats`: call `UMLSLoader.get_umls_stats`, display all counts including `same_as_count` and loaded tier
    - `cmd_clean`: call `UMLSLoader.remove_all_umls_data_with_counts`, print per-category deletion counts
    - Log progress at regular intervals: records processed, elapsed time, estimated time remaining, current batch number
    - _Requirements: 1.3, 1.4, 1.5, 1.6, 6.4, 7.4, 7.5_

  - [ ]* 7.4 Write unit tests for CLI argument parsing and subcommand routing
    - Test argparse accepts all 5 subcommands
    - Test `load` accepts all documented arguments with correct defaults
    - Test default vocabulary set is Targeted_Vocabulary_Set
    - Test `--neo4j-uri` overrides environment variable
    - Test `clean` without `--confirm` triggers prompt
    - Test `--check-config` output format
    - Test load execution order via mock call sequence
    - Test `--bridge` flag triggers bridging after load
    - _Requirements: 1.1, 1.2, 1.7, 1.8, 9.3, 8.1, 10.1, 10.3_

- [ ] 8. Checkpoint - Ensure all CLI tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 9. Integration wiring and remaining property tests
  - [ ] 9.1 Wire all components together and verify end-to-end flow
    - Ensure `rrf_parser` is imported correctly in `UMLSLoader` and CLI script
    - Ensure `UMLSBridger` is imported correctly in CLI script
    - Verify `__init__.py` exports for the knowledge_graph package include new modules
    - Ensure all Neo4j Cypher queries use MERGE for idempotency
    - _Requirements: 10.1, 5.7_

  - [ ]* 9.2 Write property test for batch retry and fault tolerance
    - **Property 17: Batch retry and fault tolerance**
    - Mock Neo4j to fail N times then succeed, assert retry count matches, verify exponential backoff delays (1s, 2s, 4s), assert `batches_completed + batches_failed = total_batches`
    - **Validates: Requirements 6.5, 6.6**

  - [ ]* 9.3 Write property test for progress checkpoint monotonic increase
    - **Property 19: Progress checkpoint monotonically increases**
    - Mock Neo4j, run batches, assert `last_batch_number` on UMLSMetadata increases monotonically and reaches total batch count on completion
    - **Validates: Requirements 6.1**

  - [ ]* 9.4 Write unit tests for edge cases
    - Test empty RRF files (zero rows yielded)
    - Test CUI with no TS="P"/STT="PF" row (fallback to first synonym)
    - Test all rows malformed (zero output from parser)
    - Test MRREL with all dangling CUIs (zero UMLS_REL edges created)
    - Test SRDEF missing (warning logged, import continues)
    - Test `import_status` transitions: in_progress → complete
    - Test supported RELA types list matches design spec
    - _Requirements: 2.8, 3.1, 4.4, 4.6, 6.2, 10.4_

- [ ] 10. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Property tests use `hypothesis` with `@settings(max_examples=100)` minimum
- All Neo4j interactions are mocked in unit/property tests using `unittest.mock.AsyncMock`
- The CLI script instantiates `Neo4jClient` directly (not via FastAPI DI) since it runs standalone
- Existing `test_umls_loader.py` patterns should be followed for new loader tests
- New test files: `test_rrf_parser.py`, `test_rrf_parser_props.py`, `test_umls_bridger.py`, `test_load_umls_cli.py`
