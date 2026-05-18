## Purpose

This document specifies the requirements for migrating the PostgreSQL database from the current dual-schema architecture (`public` schema with `documents` and `document_chunks` tables) to a unified `multimodal_librarian` schema that uses `knowledge_sources` and `knowledge_chunks` tables. The migration enables the original vision of treating books and conversations as equivalent knowledge sources while maintaining backward compatibility during the transition.


### Key Terms
- **Migration_Service**: The service responsible for orchestrating the schema migration process
- **Public_Schema**: The current PostgreSQL schema containing `documents`, `document_chunks`, and `processing_jobs` tables
- **Unified_Schema**: The `multimodal_librarian` schema containing `knowledge_sources`, `knowledge_chunks`, and related tables
- **Knowledge_Chunk**: A unified chunk representation that supports both book and conversation content with source type tracking
- **Celery_Service**: The background processing service that stores chunks after PDF processing
- **Upload_Service**: The service that handles document uploads and creates document records
- **Field_Mapper**: The component that maps fields between the old `document_chunks` schema and the new `knowledge_chunks` schema

## Requirements

### Requirement: Data Migration

The system SHALL support: As a system administrator, I want to migrate existing data from the public schema to the unified schema, so that all historical data is preserved in the new architecture.

#### Scenario: WHEN the migration is executed, THE Migration_Service SHALL

- **THEN** WHEN the migration is executed, THE Migration_Service SHALL copy all rows from `public.documents` to `multimodal_librarian.knowledge_sources` with `source_type` set to 'BOOK'

#### Scenario: WHEN migrating document chunks, THE Field_Mapper SHALL map `

- **THEN** WHEN migrating document chunks, THE Field_Mapper SHALL map `public.document_chunks.document_id` to `multimodal_librarian.knowledge_chunks.source_id`

#### Scenario: WHEN migrating document chunks, THE Field_Mapper SHALL map `

- **THEN** WHEN migrating document chunks, THE Field_Mapper SHALL map `public.document_chunks.chunk_index` to `multimodal_librarian.knowledge_chunks.chunk_index`

#### Scenario: WHEN migrating document chunks, THE Field_Mapper SHALL map `

- **THEN** WHEN migrating document chunks, THE Field_Mapper SHALL map `public.document_chunks.content` to `multimodal_librarian.knowledge_chunks.content`

#### Scenario: WHEN migrating document chunks, THE Field_Mapper SHALL gener

- **THEN** WHEN migrating document chunks, THE Field_Mapper SHALL generate a SHA-256 hash of the content and store it in `multimodal_librarian.knowledge_chunks.content_hash`

#### Scenario: WHEN migrating document chunks, THE Field_Mapper SHALL map `

- **THEN** WHEN migrating document chunks, THE Field_Mapper SHALL map `public.document_chunks.page_number` to `multimodal_librarian.knowledge_chunks.location_reference` as a string

#### Scenario: WHEN migrating document chunks, THE Field_Mapper SHALL map `

- **THEN** WHEN migrating document chunks, THE Field_Mapper SHALL map `public.document_chunks.section_title` to `multimodal_librarian.knowledge_chunks.section`

#### Scenario: WHEN migrating document chunks, THE Field_Mapper SHALL map `

- **THEN** WHEN migrating document chunks, THE Field_Mapper SHALL map `public.document_chunks.chunk_type` to `multimodal_librarian.knowledge_chunks.content_type` using the appropriate enum conversion

#### Scenario: WHEN migrating document chunks, THE Field_Mapper SHALL prese

- **THEN** WHEN migrating document chunks, THE Field_Mapper SHALL preserve `public.document_chunks.metadata` in `multimodal_librarian.knowledge_chunks.metadata`

#### Scenario: WHEN the migration completes successfully, THE Migration_Ser

- **THEN** WHEN the migration completes successfully, THE Migration_Service SHALL log the count of migrated documents and chunks

### Requirement: Celery Service Update

The system SHALL support: As a developer, I want the Celery service to write chunks to the unified schema, so that new document processing uses the correct tables.

#### Scenario: WHEN storing chunks after PDF processing, THE Celery_Service

- **THEN** WHEN storing chunks after PDF processing, THE Celery_Service SHALL insert into `multimodal_librarian.knowledge_chunks` instead of `public.document_chunks`

#### Scenario: WHEN storing chunks, THE Celery_Service SHALL set `source_ty

- **THEN** WHEN storing chunks, THE Celery_Service SHALL set `source_type` to 'BOOK' for all PDF-derived chunks

#### Scenario: WHEN storing chunks, THE Celery_Service SHALL compute and st

- **THEN** WHEN storing chunks, THE Celery_Service SHALL compute and store the `content_hash` for each chunk

#### Scenario: WHEN storing chunks, THE Celery_Service SHALL map the chunk

- **THEN** WHEN storing chunks, THE Celery_Service SHALL map the chunk metadata fields according to the unified schema structure

#### Scenario: WHEN deleting existing chunks for reprocessing, THE Celery_S

- **THEN** WHEN deleting existing chunks for reprocessing, THE Celery_Service SHALL delete from `multimodal_librarian.knowledge_chunks` instead of `public.document_chunks`

### Requirement: Upload Service Update

The system SHALL support: As a developer, I want the upload service to create document records in the unified schema, so that new uploads use the correct tables.

#### Scenario: WHEN creating a new document record, THE Upload_Service SHAL

- **THEN** WHEN creating a new document record, THE Upload_Service SHALL insert into `multimodal_librarian.knowledge_sources` instead of `public.documents`

#### Scenario: WHEN creating a document record, THE Upload_Service SHALL se

- **THEN** WHEN creating a document record, THE Upload_Service SHALL set `source_type` to 'UPLOAD' for uploaded documents

#### Scenario: WHEN querying document status, THE Upload_Service SHALL read

- **THEN** WHEN querying document status, THE Upload_Service SHALL read from `multimodal_librarian.knowledge_sources`

#### Scenario: WHEN updating document status, THE Upload_Service SHALL upda

- **THEN** WHEN updating document status, THE Upload_Service SHALL update `multimodal_librarian.knowledge_sources`

#### Scenario: WHEN listing documents, THE Upload_Service SHALL query `mult

- **THEN** WHEN listing documents, THE Upload_Service SHALL query `multimodal_librarian.knowledge_sources`

#### Scenario: WHEN deleting a document, THE Upload_Service SHALL delete fr

- **THEN** WHEN deleting a document, THE Upload_Service SHALL delete from `multimodal_librarian.knowledge_sources` (cascading to `knowledge_chunks`)

### Requirement: Query Service Updates

The system SHALL support: As a developer, I want all services that read chunks to use the unified schema, so that the system operates consistently.

#### Scenario: WHEN retrieving chunks for a document, THE system SHALL quer

- **THEN** WHEN retrieving chunks for a document, THE system SHALL query `multimodal_librarian.knowledge_chunks` with the appropriate `source_id`

#### Scenario: WHEN searching chunks by content, THE system SHALL search in

- **THEN** WHEN searching chunks by content, THE system SHALL search in `multimodal_librarian.knowledge_chunks`

#### Scenario: WHEN counting chunks for a document, THE system SHALL count

- **THEN** WHEN counting chunks for a document, THE system SHALL count from `multimodal_librarian.knowledge_chunks`

### Requirement: Schema Compatibility

The system SHALL support: As a system administrator, I want the unified schema to support both book and conversation sources, so that the system can treat all knowledge sources uniformly.

#### Scenario: THE Unified_Schema SHALL support `source_type` values of 'BO

- **THEN** THE Unified_Schema SHALL support `source_type` values of 'BOOK', 'CONVERSATION', and 'UPLOAD'

#### Scenario: THE Unified_Schema SHALL maintain referential integrity betw

- **THEN** THE Unified_Schema SHALL maintain referential integrity between `knowledge_sources` and `knowledge_chunks`

#### Scenario: WHEN a knowledge source is deleted, THE Unified_Schema SHALL

- **THEN** WHEN a knowledge source is deleted, THE Unified_Schema SHALL cascade delete all associated knowledge chunks

#### Scenario: THE Unified_Schema SHALL enforce unique constraints on `(sou

- **THEN** THE Unified_Schema SHALL enforce unique constraints on `(source_id, source_type, content_hash)` to prevent duplicate chunks

### Requirement: Migration Safety

The system SHALL support: As a system administrator, I want the migration to be safe and reversible, so that I can recover from any issues.

#### Scenario: WHEN starting the migration, THE Migration_Service SHALL ver

- **THEN** WHEN starting the migration, THE Migration_Service SHALL verify that the target schema exists and has the correct structure

#### Scenario: WHEN the migration encounters an error, THE Migration_Servic

- **THEN** WHEN the migration encounters an error, THE Migration_Service SHALL rollback the current transaction and log the error

#### Scenario: THE Migration_Service SHALL provide a dry-run mode that repo

- **THEN** THE Migration_Service SHALL provide a dry-run mode that reports what would be migrated without making changes

#### Scenario: WHEN the migration completes, THE Migration_Service SHALL ve

- **THEN** WHEN the migration completes, THE Migration_Service SHALL verify the row counts match between source and target tables

#### Scenario: THE Migration_Service SHALL preserve the original `public` s

- **THEN** THE Migration_Service SHALL preserve the original `public` schema tables until explicitly cleaned up

### Requirement: Public Schema Cleanup

The system SHALL support: As a system administrator, I want to clean up the deprecated public schema tables after successful migration, so that the database is not cluttered with unused tables.

#### Scenario: WHEN cleanup is requested, THE Migration_Service SHALL verif

- **THEN** WHEN cleanup is requested, THE Migration_Service SHALL verify that all data has been successfully migrated before dropping tables

#### Scenario: WHEN cleanup is executed, THE Migration_Service SHALL drop `

- **THEN** WHEN cleanup is executed, THE Migration_Service SHALL drop `public.document_chunks` table

#### Scenario: WHEN cleanup is executed, THE Migration_Service SHALL drop `

- **THEN** WHEN cleanup is executed, THE Migration_Service SHALL drop `public.documents` table

#### Scenario: WHEN cleanup is executed, THE Migration_Service SHALL drop `

- **THEN** WHEN cleanup is executed, THE Migration_Service SHALL drop `public.processing_jobs` table

#### Scenario: IF any table contains data not present in the unified schema

- **GIVEN** any table contains data not present in the unified schema
- **THEN** IF any table contains data not present in the unified schema, THEN THE Migration_Service SHALL abort cleanup and report the discrepancy

### Requirement: Processing Jobs Migration

The system SHALL support: As a developer, I want processing jobs to work with the unified schema, so that document processing status is tracked correctly.

#### Scenario: WHEN creating a processing job, THE Celery_Service SHALL ref

- **THEN** WHEN creating a processing job, THE Celery_Service SHALL reference `multimodal_librarian.knowledge_sources` instead of `public.documents`

#### Scenario: WHEN querying job status, THE Celery_Service SHALL join with

- **THEN** WHEN querying job status, THE Celery_Service SHALL join with `multimodal_librarian.knowledge_sources` for document information

#### Scenario: THE Migration_Service SHALL migrate existing processing jobs

- **THEN** THE Migration_Service SHALL migrate existing processing jobs to reference the new schema
