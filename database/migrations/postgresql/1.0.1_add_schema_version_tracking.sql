-- Migration: Add schema version tracking
-- Version: 1.0.1
-- Description: Add schema version tracking table and initial version record

-- Create schema_migrations table if it doesn't exist
CREATE TABLE IF NOT EXISTS multimodal_librarian.schema_migrations (
    id SERIAL PRIMARY KEY,
    migration_id VARCHAR(255) UNIQUE NOT NULL,
    version VARCHAR(50) NOT NULL,
    description TEXT,
    checksum VARCHAR(64),
    applied_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    applied_by VARCHAR(100) DEFAULT CURRENT_USER,
    execution_time_ms INTEGER,
    status VARCHAR(20) DEFAULT 'completed'
);

-- Create index on version for quick lookups
CREATE INDEX IF NOT EXISTS idx_schema_migrations_version 
ON multimodal_librarian.schema_migrations(version);

-- Create index on applied_at for chronological queries
CREATE INDEX IF NOT EXISTS idx_schema_migrations_applied_at 
ON multimodal_librarian.schema_migrations(applied_at);

-- Create schema_version view for easy version checking
CREATE OR REPLACE VIEW multimodal_librarian.schema_version AS
SELECT 
    version,
    description,
    applied_at,
    applied_by
FROM multimodal_librarian.schema_migrations 
WHERE status = 'completed'
ORDER BY applied_at DESC 
LIMIT 1;

-- Insert initial version record
INSERT INTO multimodal_librarian.schema_migrations (
    migration_id, 
    version, 
    description, 
    checksum,
    applied_at,
    status
) VALUES (
    'postgresql_1.0.0_initial_schema',
    '1.0.0',
    'Initial schema setup from initialization scripts',
    'initial',
    CURRENT_TIMESTAMP,
    'completed'
) ON CONFLICT (migration_id) DO NOTHING;

-- Insert this migration record
INSERT INTO multimodal_librarian.schema_migrations (
    migration_id, 
    version, 
    description,
    applied_at,
    status
) VALUES (
    'postgresql_1.0.1_add_schema_version_tracking',
    '1.0.1',
    'Add schema version tracking table and initial version record',
    CURRENT_TIMESTAMP,
    'completed'
) ON CONFLICT (migration_id) DO NOTHING;

-- Create function to get current schema version
CREATE OR REPLACE FUNCTION multimodal_librarian.get_schema_version()
RETURNS TABLE(version VARCHAR(50), applied_at TIMESTAMP WITH TIME ZONE) 
LANGUAGE SQL STABLE
AS $$
    SELECT sm.version, sm.applied_at
    FROM multimodal_librarian.schema_migrations sm
    WHERE sm.status = 'completed'
    ORDER BY sm.applied_at DESC
    LIMIT 1;
$$;

-- Create function to validate schema integrity
CREATE OR REPLACE FUNCTION multimodal_librarian.validate_schema_integrity()
RETURNS TABLE(
    check_name VARCHAR(100),
    status VARCHAR(20),
    details TEXT
) 
LANGUAGE SQL STABLE
AS $$
    -- Check required extensions
    SELECT 
        'required_extensions' as check_name,
        CASE 
            WHEN COUNT(*) >= 3 THEN 'PASS'
            ELSE 'FAIL'
        END as status,
        'Found ' || COUNT(*) || ' of 3 required extensions' as details
    FROM pg_extension 
    WHERE extname IN ('uuid-ossp', 'pg_trgm', 'btree_gin')
    
    UNION ALL
    
    -- Check required schemas
    SELECT 
        'required_schemas' as check_name,
        CASE 
            WHEN COUNT(*) >= 3 THEN 'PASS'
            ELSE 'FAIL'
        END as status,
        'Found ' || COUNT(*) || ' of 3 required schemas' as details
    FROM information_schema.schemata 
    WHERE schema_name IN ('multimodal_librarian', 'audit', 'monitoring')
    
    UNION ALL
    
    -- Check core tables
    SELECT 
        'core_tables' as check_name,
        CASE 
            WHEN COUNT(*) >= 5 THEN 'PASS'
            ELSE 'FAIL'
        END as status,
        'Found ' || COUNT(*) || ' of 5 core tables' as details
    FROM information_schema.tables 
    WHERE table_schema = 'multimodal_librarian'
    AND table_name IN ('users', 'documents', 'conversation_threads', 'messages', 'knowledge_chunks');
$$;

-- Grant permissions to application user
GRANT SELECT ON multimodal_librarian.schema_migrations TO ml_app_user;
GRANT SELECT ON multimodal_librarian.schema_version TO ml_app_user;
GRANT EXECUTE ON FUNCTION multimodal_librarian.get_schema_version() TO ml_app_user;
GRANT EXECUTE ON FUNCTION multimodal_librarian.validate_schema_integrity() TO ml_app_user;

-- Add comment for documentation
COMMENT ON TABLE multimodal_librarian.schema_migrations IS 
'Tracks database schema migrations and versions for the Multimodal Librarian application';

COMMENT ON VIEW multimodal_librarian.schema_version IS 
'Provides easy access to the current schema version';

COMMENT ON FUNCTION multimodal_librarian.get_schema_version() IS 
'Returns the current schema version and when it was applied';

COMMENT ON FUNCTION multimodal_librarian.validate_schema_integrity() IS 
'Validates that required database components are present and properly configured';