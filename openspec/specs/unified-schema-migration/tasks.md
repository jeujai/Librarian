# Implementation Plan: Unified Schema Migration

## Overview

This implementation plan migrates the PostgreSQL database from the dual-schema architecture (`public` schema) to the unified `multimodal_librarian` schema. The migration is executed in phases: create migration service, migrate data, update application services, and clean up deprecated tables.

## Tasks

- [x] 1. Create Migration Service and Field Mapper
  - [x] 1.1 Create migration service module with MigrationService class
    - Create `src/multimodal_librarian/services/migration_service.py`
    - Implement `migrate()`, `verify_migration()`, and `cleanup_public_schema()` methods
    - Add dry-run mode support
    - _Requirements: 1.1, 6.1, 6.2, 6.3, 6.4, 6.5_
  
  - [x] 1.2 Create FieldMapper class for schema field mapping
    - Implement `map_document_to_knowledge_source()` method
    - Implement `map_chunk_to_knowledge_chunk()` method
    - Implement `compute_content_hash()` static method
    - Implement `map_chunk_type_to_content_type()` static method
    - _Requirements: 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9_
  
  - [x] 1.3 Write property tests for FieldMapper
    - **Property 2: Content Hash Computation**
    - **Validates: Requirements 1.5, 2.3**

- [x] 2. Checkpoint - Ensure migration service tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Update Celery Service for Unified Schema
  - [x] 3.1 Update `_store_chunks_in_database` function
    - Change INSERT target from `public.document_chunks` to `multimodal_librarian.knowledge_chunks`
    - Add `source_type` field set to 'BOOK'
    - Add `content_hash` computation using SHA-256
    - Map fields according to unified schema structure
    - _Requirements: 2.1, 2.2, 2.3, 2.4_
  
  - [x] 3.2 Update `_delete_document_chunks` function
    - Change DELETE target from `public.document_chunks` to `multimodal_librarian.knowledge_chunks`
    - Update query to use `source_id` instead of `document_id`
    - _Requirements: 2.5_
  
  - [ ]* 3.3 Write property tests for chunk storage
    - **Property 3: Chunk Storage Source Type**
    - **Validates: Requirements 2.2**

- [x] 4. Update Upload Service for Unified Schema
  - [x] 4.1 Update `_store_document_in_db` method
    - Change INSERT target from `public.documents` to `multimodal_librarian.knowledge_sources`
    - Add `source_type` field set to 'UPLOAD'
    - Map fields according to unified schema structure
    - _Requirements: 3.1, 3.2_
  
  - [x] 4.2 Update `get_document` method
    - Change SELECT source from `public.documents` to `multimodal_librarian.knowledge_sources`
    - Update field mappings for response
    - _Requirements: 3.3_
  
  - [x] 4.3 Update `list_documents` method
    - Change SELECT source from `public.documents` to `multimodal_librarian.knowledge_sources`
    - Update field mappings for response
    - _Requirements: 3.5_
  
  - [x] 4.4 Update `delete_document` method
    - Change DELETE target from `public.documents` to `multimodal_librarian.knowledge_sources`
    - Verify cascade delete removes associated chunks
    - _Requirements: 3.6_
  
  - [x] 4.5 Update `update_document_status` method
    - Change UPDATE target from `public.documents` to `multimodal_librarian.knowledge_sources`
    - _Requirements: 3.4_
  
  - [ ]* 4.6 Write property tests for upload service
    - **Property 4: Upload Source Type Assignment**
    - **Property 5: Cascade Delete Behavior**
    - **Validates: Requirements 3.2, 3.6, 5.3**

- [x] 5. Checkpoint - Ensure service update tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Update Query Services
  - [x] 6.1 Update chunk retrieval queries
    - Find all queries that read from `public.document_chunks`
    - Update to read from `multimodal_librarian.knowledge_chunks`
    - Update field references (`document_id` -> `source_id`)
    - _Requirements: 4.1, 4.2, 4.3_
  
  - [x] 6.2 Update processing jobs queries
    - Update job creation to reference `multimodal_librarian.knowledge_sources`
    - Update job status queries to join with unified schema
    - _Requirements: 8.1, 8.2_

- [x] 7. Create Migration Script
  - [x] 7.1 Create CLI migration script
    - Create `scripts/migrate-to-unified-schema.py`
    - Add command-line arguments for dry-run, verify, and cleanup modes
    - Implement progress reporting and logging
    - _Requirements: 1.1, 1.10, 6.1, 6.2, 6.3_
  
  - [ ]* 7.2 Write integration tests for migration
    - **Property 1: Migration Data Preservation**
    - **Property 7: Migration Safety - Dry Run**
    - **Property 8: Migration Verification**
    - **Validates: Requirements 1.1-1.9, 6.3, 6.4**

- [x] 8. Checkpoint - Ensure migration script tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Implement Cleanup Functionality
  - [x] 9.1 Implement cleanup verification
    - Verify all data has been migrated before cleanup
    - Check for any data in public tables not in unified schema
    - _Requirements: 7.1, 7.5_
  
  - [x] 9.2 Implement table dropping
    - Drop `public.document_chunks` table
    - Drop `public.documents` table
    - Drop `public.processing_jobs` table
    - _Requirements: 7.2, 7.3, 7.4_
  
  - [ ]* 9.3 Write property tests for cleanup
    - **Property 9: Data Preservation Until Cleanup**
    - **Validates: Requirements 6.5, 7.1**

- [x] 10. Update Database Schema Files
  - [x] 10.1 Update init_db.sql
    - Ensure `multimodal_librarian.knowledge_sources` has all required fields
    - Ensure `multimodal_librarian.knowledge_chunks` has all required fields
    - Add processing_jobs table to multimodal_librarian schema if missing
    - _Requirements: 5.1, 5.2, 5.3, 5.4_
  
  - [ ]* 10.2 Write property tests for schema constraints
    - **Property 6: Schema Constraint Enforcement**
    - **Validates: Requirements 5.1, 5.2, 5.4**

- [x] 11. Final Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties
- Unit tests validate specific examples and edge cases
- The migration should be run during a maintenance window to avoid data inconsistencies
- Backup the database before running the migration
- The cleanup step should only be run after verifying the migration was successful
