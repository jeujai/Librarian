# Requirements Document

## Introduction

This document specifies the requirements for migrating the PostgreSQL database from the current dual-schema architecture (`public` schema with `documents` and `document_chunks` tables) to a unified `multimodal_librarian` schema that uses `knowledge_sources` and `knowledge_chunks` tables. The migration enables the original vision of treating books and conversations as equivalent knowledge sources while maintaining backward compatibility during the transition.

## Glossary

- **Migration_Service**: The service responsible for orchestrating the schema migration process
- **Public_Schema**: The current PostgreSQL schema containing `documents`, `document_chunks`, and `processing_jobs` tables
- **Unified_Schema**: The `multimodal_librarian` schema containing `knowledge_sources`, `knowledge_chunks`, and related tables
- **Knowledge_Chunk**: A unified chunk representation that supports both book and conversation content with source type tracking
- **Celery_Service**: The background processing service that stores chunks after PDF processing
- **Upload_Service**: The service that handles document uploads and creates document records
- **Field_Mapper**: The component that maps fields between the old `document_chunks` schema and the new `knowledge_chunks` schema

## Requirements

### Requirement 1: Data Migration

**User Story:** As a system administrator, I want to migrate existing data from the public schema to the unified schema, so that all historical data is preserved in the new architecture.

#### Acceptance Criteria

1. WHEN the migration is executed, THE Migration_Service SHALL copy all rows from `public.documents` to `multimodal_librarian.knowledge_sources` with `source_type` set to 'BOOK'
2. WHEN migrating document chunks, THE Field_Mapper SHALL map `public.document_chunks.document_id` to `multimodal_librarian.knowledge_chunks.source_id`
3. WHEN migrating document chunks, THE Field_Mapper SHALL map `public.document_chunks.chunk_index` to `multimodal_librarian.knowledge_chunks.chunk_index`
4. WHEN migrating document chunks, THE Field_Mapper SHALL map `public.document_chunks.content` to `multimodal_librarian.knowledge_chunks.content`
5. WHEN migrating document chunks, THE Field_Mapper SHALL generate a SHA-256 hash of the content and store it in `multimodal_librarian.knowledge_chunks.content_hash`
6. WHEN migrating document chunks, THE Field_Mapper SHALL map `public.document_chunks.page_number` to `multimodal_librarian.knowledge_chunks.location_reference` as a string
7. WHEN migrating document chunks, THE Field_Mapper SHALL map `public.document_chunks.section_title` to `multimodal_librarian.knowledge_chunks.section`
8. WHEN migrating document chunks, THE Field_Mapper SHALL map `public.document_chunks.chunk_type` to `multimodal_librarian.knowledge_chunks.content_type` using the appropriate enum conversion
9. WHEN migrating document chunks, THE Field_Mapper SHALL preserve `public.document_chunks.metadata` in `multimodal_librarian.knowledge_chunks.metadata`
10. WHEN the migration completes successfully, THE Migration_Service SHALL log the count of migrated documents and chunks

### Requirement 2: Celery Service Update

**User Story:** As a developer, I want the Celery service to write chunks to the unified schema, so that new document processing uses the correct tables.

#### Acceptance Criteria

1. WHEN storing chunks after PDF processing, THE Celery_Service SHALL insert into `multimodal_librarian.knowledge_chunks` instead of `public.document_chunks`
2. WHEN storing chunks, THE Celery_Service SHALL set `source_type` to 'BOOK' for all PDF-derived chunks
3. WHEN storing chunks, THE Celery_Service SHALL compute and store the `content_hash` for each chunk
4. WHEN storing chunks, THE Celery_Service SHALL map the chunk metadata fields according to the unified schema structure
5. WHEN deleting existing chunks for reprocessing, THE Celery_Service SHALL delete from `multimodal_librarian.knowledge_chunks` instead of `public.document_chunks`

### Requirement 3: Upload Service Update

**User Story:** As a developer, I want the upload service to create document records in the unified schema, so that new uploads use the correct tables.

#### Acceptance Criteria

1. WHEN creating a new document record, THE Upload_Service SHALL insert into `multimodal_librarian.knowledge_sources` instead of `public.documents`
2. WHEN creating a document record, THE Upload_Service SHALL set `source_type` to 'UPLOAD' for uploaded documents
3. WHEN querying document status, THE Upload_Service SHALL read from `multimodal_librarian.knowledge_sources`
4. WHEN updating document status, THE Upload_Service SHALL update `multimodal_librarian.knowledge_sources`
5. WHEN listing documents, THE Upload_Service SHALL query `multimodal_librarian.knowledge_sources`
6. WHEN deleting a document, THE Upload_Service SHALL delete from `multimodal_librarian.knowledge_sources` (cascading to `knowledge_chunks`)

### Requirement 4: Query Service Updates

**User Story:** As a developer, I want all services that read chunks to use the unified schema, so that the system operates consistently.

#### Acceptance Criteria

1. WHEN retrieving chunks for a document, THE system SHALL query `multimodal_librarian.knowledge_chunks` with the appropriate `source_id`
2. WHEN searching chunks by content, THE system SHALL search in `multimodal_librarian.knowledge_chunks`
3. WHEN counting chunks for a document, THE system SHALL count from `multimodal_librarian.knowledge_chunks`

### Requirement 5: Schema Compatibility

**User Story:** As a system administrator, I want the unified schema to support both book and conversation sources, so that the system can treat all knowledge sources uniformly.

#### Acceptance Criteria

1. THE Unified_Schema SHALL support `source_type` values of 'BOOK', 'CONVERSATION', and 'UPLOAD'
2. THE Unified_Schema SHALL maintain referential integrity between `knowledge_sources` and `knowledge_chunks`
3. WHEN a knowledge source is deleted, THE Unified_Schema SHALL cascade delete all associated knowledge chunks
4. THE Unified_Schema SHALL enforce unique constraints on `(source_id, source_type, content_hash)` to prevent duplicate chunks

### Requirement 6: Migration Safety

**User Story:** As a system administrator, I want the migration to be safe and reversible, so that I can recover from any issues.

#### Acceptance Criteria

1. WHEN starting the migration, THE Migration_Service SHALL verify that the target schema exists and has the correct structure
2. WHEN the migration encounters an error, THE Migration_Service SHALL rollback the current transaction and log the error
3. THE Migration_Service SHALL provide a dry-run mode that reports what would be migrated without making changes
4. WHEN the migration completes, THE Migration_Service SHALL verify the row counts match between source and target tables
5. THE Migration_Service SHALL preserve the original `public` schema tables until explicitly cleaned up

### Requirement 7: Public Schema Cleanup

**User Story:** As a system administrator, I want to clean up the deprecated public schema tables after successful migration, so that the database is not cluttered with unused tables.

#### Acceptance Criteria

1. WHEN cleanup is requested, THE Migration_Service SHALL verify that all data has been successfully migrated before dropping tables
2. WHEN cleanup is executed, THE Migration_Service SHALL drop `public.document_chunks` table
3. WHEN cleanup is executed, THE Migration_Service SHALL drop `public.documents` table
4. WHEN cleanup is executed, THE Migration_Service SHALL drop `public.processing_jobs` table
5. IF any table contains data not present in the unified schema, THEN THE Migration_Service SHALL abort cleanup and report the discrepancy

### Requirement 8: Processing Jobs Migration

**User Story:** As a developer, I want processing jobs to work with the unified schema, so that document processing status is tracked correctly.

#### Acceptance Criteria

1. WHEN creating a processing job, THE Celery_Service SHALL reference `multimodal_librarian.knowledge_sources` instead of `public.documents`
2. WHEN querying job status, THE Celery_Service SHALL join with `multimodal_librarian.knowledge_sources` for document information
3. THE Migration_Service SHALL migrate existing processing jobs to reference the new schema
