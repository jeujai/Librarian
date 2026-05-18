# Implementation Plan: Unified Chunk ID Architecture

## Overview

This implementation plan addresses the chunk ID mismatch between Neo4j, Milvus/OpenSearch, and PostgreSQL. The approach is:
1. Verify existing UUID validation in ProcessedChunk
2. Add validation to storage functions that may be missing it
3. Create a database purge script
4. Update seeding scripts to use UUID format
5. Add property-based tests for correctness verification

## Tasks

- [ ] 1. Verify and enhance ProcessedChunk UUID validation
  - [ ] 1.1 Verify ProcessedChunk.__post_init__ validates UUID format
    - Confirm existing validation in framework.py raises ValueError for invalid IDs
    - Ensure error message includes the invalid ID value
    - _Requirements: 1.1, 1.3_
  
  - [ ]* 1.2 Write property test for invalid ID rejection
    - **Property 2: Invalid ID Rejection**
    - **Validates: Requirements 1.3, 2.2, 3.2, 8.1, 8.4**

- [ ] 2. Add UUID validation to storage functions
  - [ ] 2.1 Add validation to _store_chunks_in_database in celery_service.py
    - Verify chunk ID is valid UUID before INSERT
    - Raise ValueError with invalid ID in message if validation fails
    - _Requirements: 2.1, 2.2_
  
  - [ ] 2.2 Add validation to _store_embeddings_in_vector_db in celery_service.py
    - Verify chunk ID is valid UUID before storing
    - Raise ValueError with invalid ID in message if validation fails
    - _Requirements: 3.1, 3.2_
  
  - [ ] 2.3 Add validation to _store_bridge_embeddings_in_vector_db in celery_service.py
    - Verify bridge ID is valid UUID before storing
    - Generate UUID for backward compatibility if bridge lacks ID (with warning log)
    - _Requirements: 3.1, 3.2_

- [ ] 3. Checkpoint - Verify validation is in place
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. Create database purge script
  - [ ] 4.1 Create scripts/purge-chunk-data.py
    - Implement ChunkDataPurger class
    - Add _purge_postgresql method to delete from document_chunks
    - Add _purge_vector_db method to clear Milvus/OpenSearch collection
    - Add _purge_neo4j method to delete Chunk nodes and clear source_chunks
    - Return PurgeResult with counts from each database
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_
  
  - [ ] 4.2 Add CLI interface to purge script
    - Add --dry-run flag to preview what would be deleted
    - Add --confirm flag to require explicit confirmation
    - Add --verbose flag for detailed logging
    - _Requirements: 6.5_

- [ ] 5. Update Neo4j sample data to use UUIDs
  - [ ] 5.1 Update database/neo4j/init/03_sample_data.cypher
    - Replace chunk_001, chunk_002 with valid UUIDs
    - Use format like 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'
    - _Requirements: 7.1, 7.4_

- [ ] 6. Update seeding scripts to use UUIDs
  - [ ] 6.1 Update scripts/seed-document-concept-associations.py
    - Use str(uuid.uuid4()) when creating chunk nodes
    - Remove any hardcoded chunk_N format IDs
    - _Requirements: 7.2, 7.3_
  
  - [ ] 6.2 Update scripts/seed-sample-knowledge-graph.py
    - Use str(uuid.uuid4()) for any chunk references
    - Ensure source_chunks contain valid UUIDs
    - _Requirements: 7.2, 7.3_
  
  - [ ] 6.3 Update examples/vector_store_example.py
    - Replace chunk_1, chunk_2, chunk_3 with str(uuid.uuid4())
    - _Requirements: 7.4_

- [ ] 7. Checkpoint - Verify seeding scripts updated
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. Write property-based tests
  - [ ]* 8.1 Write property test for UUID round-trip consistency
    - **Property 1: UUID Round-Trip Consistency**
    - **Validates: Requirements 1.1, 2.1, 3.1, 4.1, 4.3**
  
  - [ ]* 8.2 Write property test for chunk resolvability
    - **Property 3: Chunk Resolvability**
    - **Validates: Requirements 5.1, 5.3, 5.4**
  
  - [ ]* 8.3 Write property test for reprocessing isolation
    - **Property 4: Reprocessing Isolation**
    - **Validates: Requirements 2.4, 3.4, 4.4**
  
  - [ ]* 8.4 Write property test for sub-chunk UUID uniqueness
    - **Property 5: Sub-Chunk UUID Uniqueness**
    - **Validates: Requirements 1.5**

- [ ] 9. Write unit tests for purge script
  - [ ]* 9.1 Write unit tests for ChunkDataPurger
    - Test _purge_postgresql deletes all chunks
    - Test _purge_vector_db clears collection
    - Test _purge_neo4j removes Chunk nodes and clears source_chunks
    - Test PurgeResult contains accurate counts
    - _Requirements: 6.1, 6.2, 6.3, 6.5_

- [x] 10. Final checkpoint - Verify chunk ID consistency across all databases
  - ✅ VERIFIED 2026-02-04: Full purge and re-upload test completed
  - PostgreSQL: 684 chunks with UUID IDs ✅
  - Milvus: 1357 chunks (684 document + 673 bridge), all UUID format ✅
  - Neo4j: 19,534 concepts, ALL with UUID format source_chunks ✅
  - 100% match rate between PostgreSQL and Milvus chunk IDs ✅
  - ZERO chunks with old chunk_N format found ✅
  - Document tested: 158523b9-9488-4758-97b4-421ee1407066 (LangChain PDF)

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- The existing ProcessedChunk already has UUID validation - task 1.1 is verification
- The celery_service.py already has some UUID validation - tasks 2.1-2.3 ensure completeness
- After implementation, run the purge script and re-upload the Langchain book to test
- Property tests validate universal correctness properties
- Unit tests validate specific examples and edge cases
