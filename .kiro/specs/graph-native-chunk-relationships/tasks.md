# Implementation Plan: Graph-Native Chunk Relationships

## Overview

Refactor Neo4j knowledge graph from property-based chunk storage (`source_chunks` string, `source_document` property on Concept nodes) to graph-native `Chunk` nodes linked via `EXTRACTED_FROM` relationships. Implementation proceeds schema-first, then write paths, read paths, delete paths, and cross-document queries. Each step builds on the previous and is validated incrementally.

## Tasks

- [x] 1. Schema initialization and Chunk node constraints
  - [x] 1.1 Add Chunk uniqueness constraint and source_id index to Neo4j schema initialization
    - Modify `src/multimodal_librarian/clients/neo4j_client.py` `ensure_indexes` method
    - Add `CREATE CONSTRAINT chunk_id_unique IF NOT EXISTS FOR (ch:Chunk) REQUIRE ch.chunk_id IS UNIQUE`
    - Add `CREATE INDEX chunk_source_id IF NOT EXISTS FOR (ch:Chunk) ON (ch.source_id)`
    - Keep existing Concept indexes intact (they will be used during migration transition)
    - _Requirements: 1.3, 1.4_

  - [ ]* 1.2 Write unit tests for schema initialization
    - Verify the new constraint and index Cypher statements are included in the indexes list
    - _Requirements: 1.3, 1.4_

- [x] 2. Update ConceptNode in-memory model
  - [x] 2.1 Modify ConceptNode dataclass to retain source_chunks for in-memory use only
    - Modify `src/multimodal_librarian/models/knowledge_graph.py` `ConceptNode` class
    - Keep `source_chunks: List[str]` field and `source_document: Optional[str]` field on the dataclass
    - Ensure `to_dict()` continues to include `source_chunks` and `source_document` for non-Neo4j consumers
    - Ensure `add_source_chunk()` continues to work for in-memory accumulation
    - Add a docstring clarifying these fields are for in-memory use only and are NOT persisted to Neo4j as properties
    - _Requirements: 11.1, 11.2, 11.3, 11.4_

  - [ ]* 2.2 Write property test for ConceptNode in-memory accumulation round-trip
    - **Property 11: ConceptNode in-memory round-trip**
    - Generate random chunk_id lists, create ConceptNode, call `add_source_chunk` for each, assert `to_dict()` contains deduplicated list
    - **Validates: Requirements 11.1, 11.2, 11.4**

- [x] 3. Update CeleryService write path (document processing pipeline)
  - [x] 3.1 Refactor `_update_knowledge_graph` in `src/multimodal_librarian/services/celery_service.py`
    - Collect all unique `(chunk_id, source_id)` pairs from the batch's KnowledgeChunk objects
    - Add Step 1: UNWIND MERGE for Chunk nodes with `chunk_id`, `source_id`, `created_at`
    - Modify Step 2: Remove `source_chunks` and `source_document` from Concept MERGE SET clauses
    - Add Step 3: UNWIND MERGE for EXTRACTED_FROM relationships from Concept to Chunk with `created_at`
    - Remove the `append_rows` logic that concatenates `source_chunks` strings
    - _Requirements: 3.3, 3.4, 4.1, 4.2, 4.3_

  - [ ]* 3.2 Write property test for write-path round-trip
    - **Property 1: Write-path round-trip (source_chunks ↔ EXTRACTED_FROM)**
    - Generate random ConceptNodes with random source_chunks lists, persist via write path, query EXTRACTED_FROM traversal, assert chunk_id sets match
    - **Validates: Requirements 3.1, 3.2, 4.2, 5.2, 6.1, 11.3**

  - [ ]* 3.3 Write property test for write-path MERGE idempotency
    - **Property 2: Write-path MERGE idempotency**
    - Generate random write inputs, execute write path twice, assert node/relationship counts are identical
    - **Validates: Requirements 1.2, 2.2**

  - [ ]* 3.4 Write property test for no property-based chunk storage after persistence
    - **Property 3: No property-based chunk storage**
    - Generate random concepts, persist via write path, assert no Concept node has `source_chunks` or `source_document` properties
    - **Validates: Requirements 3.3, 3.4, 3.5, 3.6, 10.3**

  - [ ]* 3.5 Write property test for Chunk nodes carry correct source_id
    - **Property 4: Chunk nodes carry correct source_id**
    - Generate random document_id and chunk list, persist, assert all Chunk nodes have correct `source_id`
    - **Validates: Requirements 1.1, 4.1, 5.1**

- [x] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Update ConversationKnowledgeService write path
  - [x] 5.1 Refactor `_persist_concepts` in `src/multimodal_librarian/services/conversation_knowledge_service.py`
    - Replace `source_document` and `source_chunks` SET clauses in the MERGE query with Chunk MERGE + EXTRACTED_FROM MERGE
    - Create Chunk nodes for each conversation chunk with `source_id` set to the thread ID
    - Create EXTRACTED_FROM relationships from Concepts to their source Chunk nodes
    - _Requirements: 3.5, 5.1, 5.2_

  - [ ]* 5.2 Write property test for existing EXTRACTED_FROM relationships preserved on re-MERGE
    - **Property 5: Existing EXTRACTED_FROM preserved on re-MERGE**
    - Create a concept with initial chunks, add more chunks via re-MERGE, assert original relationships still exist and new ones are added
    - **Validates: Requirements 4.3**

- [x] 6. Update EnrichmentService write path
  - [x] 6.1 Remove `source_chunks` and `source_document` SET clauses from EnrichmentService batch concept MERGE queries
    - Modify `src/multimodal_librarian/services/enrichment_service.py`
    - Ensure enrichment batch persistence follows the same Chunk MERGE + EXTRACTED_FROM MERGE pattern
    - _Requirements: 3.6_

- [x] 7. Update KGRetrievalService read path
  - [x] 7.1 Refactor `_retrieve_direct_chunks` and `_retrieve_related_chunks` in `src/multimodal_librarian/services/kg_retrieval_service.py`
    - Replace `concept.source_chunks` string parsing with Cypher traversal: `MATCH (c:Concept {concept_id: $id})-[:EXTRACTED_FROM]->(ch:Chunk) RETURN ch.chunk_id`
    - Update `_query_related_concepts` to collect chunk IDs via `OPTIONAL MATCH (related)-[:EXTRACTED_FROM]->(ch:Chunk)` and `collect(DISTINCT ch.chunk_id) as chunk_ids`
    - Delete the `_parse_source_chunks` method and all comma-delimited string parsing logic
    - Update cache to store chunk ID lists directly from graph traversal
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [ ]* 7.2 Write unit tests for KGRetrievalService
    - Verify `_parse_source_chunks` method no longer exists on the class
    - Test that direct chunk retrieval returns correct chunk IDs via EXTRACTED_FROM traversal
    - Test that related chunk retrieval collects chunk IDs from related concepts
    - _Requirements: 6.1, 6.2, 6.3_

- [x] 8. Update KnowledgeGraphQueryEngine read path
  - [x] 8.1 Refactor landing view, ego graph, and embedding search in `src/multimodal_librarian/components/knowledge_graph/kg_query_engine.py`
    - Replace `MATCH (c:Concept {source_document: $source_id})` with `MATCH (ch:Chunk {source_id: $source_id})<-[:EXTRACTED_FROM]-(c:Concept)` in `_get_landing_view`
    - Replace `source_document` filter in ego graph with subquery checking EXTRACTED_FROM to Chunk with matching source_id
    - Replace `c.source_document = $source_id` in `search_concepts_by_embedding` with `EXISTS { MATCH (c)-[:EXTRACTED_FROM]->(ch:Chunk {source_id: $source_id}) }`
    - _Requirements: 8.1, 8.2, 8.3_

  - [ ]* 8.2 Write property test for per-document concept counts via Chunk traversal
    - **Property 6: Per-document counts via Chunk traversal**
    - Create known graph structure with Chunks and EXTRACTED_FROM, query counts, assert counts match expected values
    - **Validates: Requirements 7.1, 7.2, 7.3, 8.1**

- [x] 9. Update ChatDocumentHandlers read path
  - [x] 9.1 Refactor concept and relationship count queries in `src/multimodal_librarian/api/routers/chat_document_handlers.py`
    - Replace concept count query: use `MATCH (ch:Chunk) WHERE ch.source_id IN $doc_ids MATCH (ch)<-[:EXTRACTED_FROM]-(c:Concept) RETURN count(DISTINCT c) AS concepts`
    - Replace relationship count query: use `MATCH (ch:Chunk) WHERE ch.source_id IN $doc_ids MATCH (ch)<-[:EXTRACTED_FROM]-(c:Concept)-[r]->() RETURN type(r) AS rel_type, count(r) AS cnt`
    - Replace cross-document query at line ~795 to use Chunk-based traversal instead of `source_document`
    - _Requirements: 7.1, 7.2_

- [x] 10. Update CompositeScoreEngine read path
  - [x] 10.1 Refactor `_discover_cross_doc_edges` and `_get_concept_counts` in `src/multimodal_librarian/services/composite_score_engine.py`
    - Replace `MATCH (c1:Concept {source_document: $doc_id})` with Chunk-based traversal in forward and reverse queries
    - Replace `MATCH (c:Concept {source_document: did})` with `MATCH (ch:Chunk {source_id: did})<-[:EXTRACTED_FROM]-(c:Concept)` in `_get_concept_counts`
    - _Requirements: 7.3_

- [x] 11. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 12. Update PrivacyService delete path
  - [x] 12.1 Refactor knowledge graph deletion in `src/multimodal_librarian/security/privacy.py`
    - Replace `MATCH (c:Concept {source_document: $source_id}) DETACH DELETE c` with three-step process:
      - Step 1: Delete EXTRACTED_FROM relationships to this source's Chunk nodes
      - Step 2: Delete Chunk nodes for this source_id
      - Step 3: Delete orphaned Concepts (no remaining EXTRACTED_FROM and no SAME_AS relationships)
    - _Requirements: 9.1, 9.2, 9.3, 9.4_

  - [ ]* 12.2 Write property test for source deletion removes all Chunks and EXTRACTED_FROM
    - **Property 7: Source deletion removes Chunks and EXTRACTED_FROM**
    - Create chunks for a source, delete, assert zero Chunks and zero EXTRACTED_FROM for that source
    - **Validates: Requirements 9.1, 9.2, 5.3**

  - [ ]* 12.3 Write property test for orphan cleanup correctness
    - **Property 8: Orphan cleanup correctness**
    - Create concepts linked to chunks from multiple sources, delete one source, assert orphans are deleted and shared concepts are retained
    - **Validates: Requirements 9.3, 9.4**

- [x] 13. Update ConversationKnowledgeService delete path
  - [x] 13.1 Refactor `_remove_kg_data` in `src/multimodal_librarian/services/conversation_knowledge_service.py`
    - Replace `MATCH (c:Concept {source_document: $source_id}) DETACH DELETE c` with the same three-step Chunk-based deletion + orphan cleanup pattern used in PrivacyService
    - _Requirements: 5.3_

- [x] 14. Update DocumentManager delete path
  - [x] 14.1 Refactor Neo4j cleanup in `src/multimodal_librarian/components/document_manager/document_manager.py`
    - Replace `MATCH (c:Concept {source_document: $doc_id}) ... DETACH DELETE c` with three-step Chunk-based deletion + orphan cleanup
    - _Requirements: 9.1, 9.2, 9.3, 9.4_

- [x] 15. Update cross-document linking
  - [x] 15.1 Refactor EnrichmentService `create_cross_document_links` in `src/multimodal_librarian/services/enrichment_service.py`
    - Replace `c.source_document as document_id` with Chunk traversal: `OPTIONAL MATCH (c)-[:EXTRACTED_FROM]->(ch:Chunk) RETURN c.concept_id as concept_id, collect(DISTINCT ch.source_id) as document_ids`
    - Compare source_ids from Chunk nodes instead of `concept.source_document`
    - _Requirements: 10.2_

  - [x] 15.2 Refactor KnowledgeGraphService `query_with_same_as_traversal` in `src/multimodal_librarian/services/knowledge_graph_service.py`
    - Replace `related.source_document <> start.source_document` with Chunk-based document derivation using EXTRACTED_FROM traversal
    - Return `collect(DISTINCT rch.source_id) as document_ids` instead of `related.source_document`
    - _Requirements: 10.1_

  - [ ]* 15.3 Write property test for cross-document SAME_AS uses Chunk-derived document IDs
    - **Property 9: Cross-document SAME_AS via Chunk-derived IDs**
    - Create concepts with Chunks from different sources sharing a Q-number, assert SAME_AS is only created when source_ids don't overlap
    - **Validates: Requirements 10.1, 10.2**

- [x] 16. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 17. Update helper scripts
  - [x] 17.1 Update `scripts/rebuild_kg.py` and `scripts/compute_all_composite_scores.py`
    - Update `rebuild_kg.py` to use the new write path (Chunk MERGE + EXTRACTED_FROM MERGE)
    - Update `compute_all_composite_scores.py` to derive document IDs from Chunk traversal instead of `c.source_document`
    - _Requirements: 7.3, 4.2_

- [x] 18. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- The design uses Python — all code examples and implementations use Python with the existing FastAPI/Neo4j stack
- The ConceptNode `source_chunks` and `source_document` fields are retained in-memory but never written to Neo4j as properties
