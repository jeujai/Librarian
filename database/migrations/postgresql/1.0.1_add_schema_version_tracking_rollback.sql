-- Rollback Migration: Remove schema version tracking
-- Version: 1.0.1
-- Description: Rollback schema version tracking table and functions

-- Drop functions
DROP FUNCTION IF EXISTS multimodal_librarian.validate_schema_integrity();
DROP FUNCTION IF EXISTS multimodal_librarian.get_schema_version();

-- Drop view
DROP VIEW IF EXISTS multimodal_librarian.schema_version;

-- Drop indexes
DROP INDEX IF EXISTS multimodal_librarian.idx_schema_migrations_applied_at;
DROP INDEX IF EXISTS multimodal_librarian.idx_schema_migrations_version;

-- Drop table (this will remove all migration history!)
-- WARNING: This is destructive and should only be used in development
DROP TABLE IF EXISTS multimodal_librarian.schema_migrations;