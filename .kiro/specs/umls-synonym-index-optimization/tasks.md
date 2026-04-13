# Implementation Plan: UMLS Synonym Index Optimization

## Overview

Introduce a separate `UMLSSynonym` node model with a RANGE-indexed `name` property to replace full-scan `lower_synonyms` list queries. Implementation proceeds incrementally: indexes first, then node creation during loading, query migration across bridger and client, cleanup method updates, migration script, and tests.

## Tasks

- [x] 1. Add UMLSSynonym RANGE index to create_indexes() and ensure_indexes()
  - [x] 1.1 Add `CREATE INDEX umls_synonym_name IF NOT EXISTS FOR (s:UMLSSynonym) ON (s.name)` to the `create_indexes()` method in `umls_loader.py`
    - Append the new index statement to the `index_queries` list
    - _Requirements: 5.1, 1.3_

  - [x] 1.2 Add the same index statement to `ensure_indexes()` in `neo4j_client.py`
    - Append to the `index_statements` list
    - _Requirements: 5.2_

  - [ ]* 1.3 Write unit tests for index creation
    - Verify `create_indexes` includes the `umls_synonym_name` index statement
    - Verify `ensure_indexes` includes the `umls_synonym_name` index statement
    - Add tests in `tests/components/test_umls_loader.py` and `tests/` as appropriate
    - _Requirements: 5.1, 5.2_

- [-] 2. Add UMLSSynonym node creation in load_concepts() (Pass 2b)
  - [x] 2.1 Add Pass 2b after UMLSConcept batch creation in `load_concepts()` in `umls_loader.py`
    - After Pass 2 (UMLSConcept creation), iterate over `concept_list` in batches
    - For each batch, execute: `UNWIND $items AS item MATCH (u:UMLSConcept {cui: item.cui}) UNWIND item.lower_synonyms AS syn MERGE (s:UMLSSynonym {name: syn}) MERGE (u)-[:HAS_SYNONYM]->(s)`
    - Use `_execute_batch_with_retry` for resilience
    - Track synonym node/relationship counts in the returned `LoadResult`
    - Prepare batch items from `concept_list` using `[s.lower() for s in entry["synonyms"]]` for `lower_synonyms`
    - _Requirements: 1.1, 1.2, 1.4, 1.5_

  - [ ]* 2.2 Write property test: Synonym Node Completeness (Property 1)
    - **Property 1: Synonym Node Completeness**
    - Generate random concept data with CUIs and synonym lists using Hypothesis
    - Verify every unique lowercased synonym has a corresponding UMLSSynonym node and HAS_SYNONYM relationship
    - **Validates: Requirements 1.1, 1.2, 4.1**

  - [ ]* 2.3 Write property test: Shared Synonym Deduplication (Property 2)
    - **Property 2: Shared Synonym Deduplication**
    - Generate concepts with overlapping synonyms using Hypothesis
    - Verify exactly one UMLSSynonym node per unique name, with multiple HAS_SYNONYM relationships from sharing concepts
    - **Validates: Requirements 1.4**

  - [ ]* 2.4 Write property test: Backward Compatibility of List Properties (Property 3)
    - **Property 3: Backward Compatibility of List Properties**
    - Generate concepts, simulate load, verify `synonyms` and `lower_synonyms` list properties on UMLSConcept are unchanged
    - **Validates: Requirements 1.5**

  - [ ]* 2.5 Write unit test for empty synonym list edge case
    - Concept with no synonyms should create no UMLSSynonym nodes or HAS_SYNONYM relationships
    - _Requirements: 1.1_

- [x] 3. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Replace synonym query in umls_bridger.py _match_concepts_batch
  - [x] 4.1 Replace the synonym query in `_match_concepts_batch()` in `umls_bridger.py`
    - Change from: `UNWIND $names AS name MATCH (u:UMLSConcept) WHERE name IN u.lower_synonyms RETURN name, u.cui AS cui`
    - Change to: `UNWIND $names AS name MATCH (s:UMLSSynonym {name: name})<-[:HAS_SYNONYM]-(u:UMLSConcept) RETURN name, u.cui AS cui`
    - Preserve the preferred_name query (already indexed), result structure, and deduplication logic
    - _Requirements: 2.1, 2.2_

  - [ ]* 4.2 Write unit test for bridger query structure
    - Verify the new Cypher query uses `UMLSSynonym` pattern instead of `lower_synonyms` list scan
    - Test preferred_name + synonym overlap: name matches both on different concepts, both returned and deduplicated
    - _Requirements: 2.1, 2.2, 6.3_

- [x] 5. Replace synonym queries in umls_client.py
  - [x] 5.1 Replace the synonym query in `search_by_name()` in `umls_client.py`
    - Change from: `MATCH (c:UMLSConcept) WHERE c.lower_name = $lower_name OR $lower_name IN c.lower_synonyms RETURN c.cui AS cui, c.preferred_name AS preferred_name`
    - Change to UNION approach: `MATCH (c:UMLSConcept) WHERE c.lower_name = $lower_name RETURN c.cui AS cui, c.preferred_name AS preferred_name UNION MATCH (s:UMLSSynonym {name: $lower_name})<-[:HAS_SYNONYM]-(c:UMLSConcept) RETURN c.cui AS cui, c.preferred_name AS preferred_name`
    - _Requirements: 3.1, 3.3_

  - [x] 5.2 Replace the Phase 2 synonym query in `batch_search_by_names()` in `umls_client.py`
    - Change from: `UNWIND $names AS name MATCH (c:UMLSConcept) WHERE name IN c.lower_synonyms RETURN name, c.cui AS cui`
    - Change to: `UNWIND $names AS name MATCH (s:UMLSSynonym {name: name})<-[:HAS_SYNONYM]-(c:UMLSConcept) RETURN name, c.cui AS cui`
    - _Requirements: 3.2, 3.3_

  - [ ]* 5.3 Write property test: Query Result Equivalence (Property 4)
    - **Property 4: Query Result Equivalence**
    - Generate random concepts and query names using Hypothesis
    - Compare old list-scanning query results vs new UMLSSynonym-based query results
    - Verify identical (name, CUI) pair sets for `_match_concepts_batch`, `search_by_name`, and `batch_search_by_names`
    - **Validates: Requirements 2.2, 3.3, 6.1, 6.2**

  - [ ]* 5.4 Write unit tests for client query structure
    - Verify `search_by_name` uses UNION with UMLSSynonym pattern
    - Verify `batch_search_by_names` Phase 2 uses UMLSSynonym pattern
    - _Requirements: 3.1, 3.2_

- [x] 6. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Update cleanup methods to handle UMLSSynonym nodes
  - [x] 7.1 Add HAS_SYNONYM and UMLSSynonym deletion to `_remove_concept_data()` in `umls_loader.py`
    - Add `("MATCH ()-[r:HAS_SYNONYM]->() DELETE r", "has_synonym_relationships")` before UMLSConcept deletion
    - Add `("MATCH (n:UMLSSynonym) DETACH DELETE n", "umls_synonym_nodes")` before UMLSConcept deletion
    - _Requirements: 1.1_

  - [x] 7.2 Add HAS_SYNONYM and UMLSSynonym deletion to `remove_all_umls_data()` in `umls_loader.py`
    - Add the same two deletion entries before UMLSConcept node deletion
    - _Requirements: 1.1_

  - [x] 7.3 Add HAS_SYNONYM and UMLSSynonym deletion to `remove_all_umls_data_with_counts()` in `umls_loader.py`
    - Add batched HAS_SYNONYM relationship deletion to `delete_specs` before node deletions
    - Add batched UMLSSynonym node deletion to `delete_specs` before UMLSConcept node deletion
    - _Requirements: 1.1_

  - [ ]* 7.4 Write unit tests for cleanup methods
    - Verify `_remove_concept_data` includes HAS_SYNONYM and UMLSSynonym deletion queries
    - Verify `remove_all_umls_data` includes HAS_SYNONYM and UMLSSynonym deletion queries
    - Verify deletion order: HAS_SYNONYM relationships before UMLSSynonym nodes before UMLSConcept nodes
    - _Requirements: 1.1_

- [x] 8. Add migrate_synonyms() method and migration script
  - [x] 8.1 Add `migrate_synonyms(batch_size: int = 5000) -> LoadResult` method to `UMLSLoader` in `umls_loader.py`
    - Read existing `lower_synonyms` from UMLSConcept nodes in batches
    - For each batch, MERGE UMLSSynonym nodes and HAS_SYNONYM relationships using: `UNWIND $items AS item MATCH (u:UMLSConcept {cui: item.cui}) UNWIND item.lower_synonyms AS syn MERGE (s:UMLSSynonym {name: syn}) MERGE (u)-[:HAS_SYNONYM]->(s)`
    - Use `_execute_batch_with_retry` for resilience
    - On batch failure: log error, increment `batches_failed`, continue
    - Return `LoadResult` with accurate counts
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [x] 8.2 Create migration script at `scripts/migrate_umls_synonyms.py`
    - Standalone async script that connects to Neo4j using `Neo4jClient`
    - Calls `UMLSLoader.create_indexes()` to ensure the new index exists
    - Calls `UMLSLoader.migrate_synonyms()` to create UMLSSynonym nodes
    - Logs summary statistics
    - Runnable via `python scripts/migrate_umls_synonyms.py` or `docker compose exec app python scripts/migrate_umls_synonyms.py`
    - _Requirements: 4.1, 4.2, 4.3_

  - [ ]* 8.3 Write property test: Migration Idempotency (Property 5)
    - **Property 5: Migration Idempotency**
    - Generate random concepts, run `migrate_synonyms` twice
    - Verify node and relationship counts are identical after first and second run
    - **Validates: Requirements 4.2**

  - [ ]* 8.4 Write property test: Migration Count Accuracy (Property 6)
    - **Property 6: Migration Count Accuracy**
    - Generate random concepts, run migration
    - Verify `LoadResult.nodes_created` and `relationships_created` match actual DB counts
    - **Validates: Requirements 4.3**

  - [ ]* 8.5 Write unit test for batch failure resilience
    - Simulate a Neo4j error mid-migration
    - Verify remaining batches complete and `LoadResult.batches_failed` is accurate
    - _Requirements: 4.4_

- [x] 9. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties using Hypothesis
- Unit tests validate specific examples and edge cases
- The project uses pytest for testing and structlog for logging
- All database operations use async/await patterns
