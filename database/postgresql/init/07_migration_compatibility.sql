-- Migration Compatibility Layer for Local Development
-- This script ensures compatibility with existing application migrations

-- Create migration tracking table (similar to Alembic)
CREATE TABLE IF NOT EXISTS public.alembic_version (
    version_num VARCHAR(32) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Create migration history table for local tracking
CREATE TABLE IF NOT EXISTS public.migration_history (
    id SERIAL PRIMARY KEY,
    migration_name VARCHAR(255) NOT NULL,
    applied_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    checksum VARCHAR(64),
    success BOOLEAN DEFAULT true,
    error_message TEXT
);

-- Function to record migration application
CREATE OR REPLACE FUNCTION record_migration(
    migration_name VARCHAR(255),
    checksum VARCHAR(64) DEFAULT NULL,
    success BOOLEAN DEFAULT true,
    error_message TEXT DEFAULT NULL
)
RETURNS void AS $$
BEGIN
    INSERT INTO public.migration_history (migration_name, checksum, success, error_message)
    VALUES (migration_name, checksum, success, error_message);
    
    IF success THEN
        RAISE NOTICE 'Migration recorded: %', migration_name;
    ELSE
        RAISE WARNING 'Failed migration recorded: % - %', migration_name, error_message;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- Function to check if migration was already applied
CREATE OR REPLACE FUNCTION is_migration_applied(migration_name VARCHAR(255))
RETURNS BOOLEAN AS $$
BEGIN
    RETURN EXISTS (
        SELECT 1 FROM public.migration_history 
        WHERE migration_history.migration_name = is_migration_applied.migration_name 
        AND success = true
    );
END;
$$ LANGUAGE plpgsql;

-- Apply PDF upload migration compatibility
DO $$
BEGIN
    IF NOT is_migration_applied('pdf_upload_tables') THEN
        -- Create documents table if it doesn't exist (compatibility with PDF upload migration)
        CREATE TABLE IF NOT EXISTS public.documents (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            user_id VARCHAR(255) NOT NULL,
            title VARCHAR(500) NOT NULL,
            filename VARCHAR(255) NOT NULL,
            file_size BIGINT NOT NULL,
            mime_type VARCHAR(100) NOT NULL,
            s3_key VARCHAR(1000),
            upload_status VARCHAR(50) DEFAULT 'pending',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            processed_at TIMESTAMP WITH TIME ZONE
        );
        
        -- Create document_chunks table if it doesn't exist
        CREATE TABLE IF NOT EXISTS public.document_chunks (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            document_id UUID NOT NULL REFERENCES public.documents(id) ON DELETE CASCADE,
            chunk_index INTEGER NOT NULL,
            content TEXT NOT NULL,
            metadata JSONB DEFAULT '{}',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        
        -- Create indexes for PDF upload tables
        CREATE INDEX IF NOT EXISTS idx_documents_user_id_public ON public.documents(user_id);
        CREATE INDEX IF NOT EXISTS idx_documents_status_public ON public.documents(upload_status);
        CREATE INDEX IF NOT EXISTS idx_document_chunks_document_id ON public.document_chunks(document_id);
        CREATE INDEX IF NOT EXISTS idx_document_chunks_index ON public.document_chunks(chunk_index);
        
        PERFORM record_migration('pdf_upload_tables', 'local_init', true);
    END IF;
END $$;

-- Apply analytics migration compatibility
DO $$
BEGIN
    IF NOT is_migration_applied('analytics_tables') THEN
        -- Create analytics tables if they don't exist
        CREATE TABLE IF NOT EXISTS public.user_analytics (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            user_id VARCHAR(255) NOT NULL,
            event_type VARCHAR(100) NOT NULL,
            event_data JSONB DEFAULT '{}',
            timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            session_id VARCHAR(255)
        );
        
        CREATE TABLE IF NOT EXISTS public.document_analytics (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            document_id UUID REFERENCES public.documents(id) ON DELETE CASCADE,
            event_type VARCHAR(100) NOT NULL,
            event_data JSONB DEFAULT '{}',
            timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            user_id VARCHAR(255)
        );
        
        -- Create indexes for analytics tables
        CREATE INDEX IF NOT EXISTS idx_user_analytics_user_id ON public.user_analytics(user_id);
        CREATE INDEX IF NOT EXISTS idx_user_analytics_event_type ON public.user_analytics(event_type);
        CREATE INDEX IF NOT EXISTS idx_user_analytics_timestamp ON public.user_analytics(timestamp);
        CREATE INDEX IF NOT EXISTS idx_document_analytics_document_id ON public.document_analytics(document_id);
        CREATE INDEX IF NOT EXISTS idx_document_analytics_event_type ON public.document_analytics(event_type);
        
        PERFORM record_migration('analytics_tables', 'local_init', true);
    END IF;
END $$;

-- Apply chat messages migration compatibility
DO $$
BEGIN
    IF NOT is_migration_applied('chat_messages_tables') THEN
        -- Create chat_messages table if it doesn't exist (compatibility with existing migrations)
        CREATE TABLE IF NOT EXISTS public.chat_messages (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            user_id VARCHAR(255) NOT NULL,
            message TEXT NOT NULL,
            response TEXT,
            timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            metadata JSONB DEFAULT '{}'
        );
        
        -- Create indexes for chat messages
        CREATE INDEX IF NOT EXISTS idx_chat_messages_user_id ON public.chat_messages(user_id);
        CREATE INDEX IF NOT EXISTS idx_chat_messages_timestamp ON public.chat_messages(timestamp);
        
        PERFORM record_migration('chat_messages_tables', 'local_init', true);
    END IF;
END $$;

-- Create view to bridge between old and new schema
CREATE OR REPLACE VIEW public.documents_unified AS
SELECT 
    COALESCE(d1.id, d2.id) as id,
    COALESCE(d1.user_id, d2.user_id::text) as user_id,
    COALESCE(d1.title, d2.title) as title,
    COALESCE(d1.filename, d2.filename) as filename,
    COALESCE(d1.file_size, d2.file_size) as file_size,
    COALESCE(d1.mime_type, d2.mime_type) as mime_type,
    COALESCE(d1.created_at, d2.created_at) as created_at,
    COALESCE(d1.updated_at, d2.updated_at) as updated_at,
    'public' as schema_source
FROM public.documents d1
FULL OUTER JOIN multimodal_librarian.documents d2 ON d1.id = d2.id;

-- Function to migrate data between schemas
CREATE OR REPLACE FUNCTION migrate_data_to_new_schema()
RETURNS TABLE(
    migrated_table text,
    record_count integer
) AS $$
DECLARE
    rec RECORD;
    count_val INTEGER;
BEGIN
    -- Migrate documents from public to multimodal_librarian schema
    INSERT INTO multimodal_librarian.documents (
        id, user_id, title, filename, file_path, file_size, mime_type, 
        content_type, processing_status, created_at, updated_at
    )
    SELECT 
        d.id,
        u.id as user_id,
        d.title,
        d.filename,
        COALESCE(d.s3_key, d.filename) as file_path,
        d.file_size,
        d.mime_type,
        'ACADEMIC'::content_type as content_type,
        CASE 
            WHEN d.upload_status = 'completed' THEN 'COMPLETED'::processing_status
            WHEN d.upload_status = 'failed' THEN 'FAILED'::processing_status
            ELSE 'PENDING'::processing_status
        END as processing_status,
        d.created_at,
        d.updated_at
    FROM public.documents d
    LEFT JOIN multimodal_librarian.users u ON u.username = d.user_id
    WHERE NOT EXISTS (
        SELECT 1 FROM multimodal_librarian.documents md WHERE md.id = d.id
    );
    
    GET DIAGNOSTICS count_val = ROW_COUNT;
    RETURN QUERY SELECT 'documents'::text, count_val;
    
    -- Migrate document chunks
    INSERT INTO multimodal_librarian.knowledge_chunks (
        source_id, source_type, content, content_hash, chunk_index,
        content_type, created_at, updated_at
    )
    SELECT 
        dc.document_id as source_id,
        'UPLOAD'::source_type as source_type,
        dc.content,
        encode(sha256(dc.content::bytea), 'hex') as content_hash,
        dc.chunk_index,
        'ACADEMIC'::content_type as content_type,
        dc.created_at,
        dc.created_at as updated_at
    FROM public.document_chunks dc
    WHERE EXISTS (
        SELECT 1 FROM multimodal_librarian.documents md WHERE md.id = dc.document_id
    )
    AND NOT EXISTS (
        SELECT 1 FROM multimodal_librarian.knowledge_chunks kc 
        WHERE kc.source_id = dc.document_id 
        AND kc.chunk_index = dc.chunk_index
    );
    
    GET DIAGNOSTICS count_val = ROW_COUNT;
    RETURN QUERY SELECT 'knowledge_chunks'::text, count_val;
END;
$$ LANGUAGE plpgsql;

-- Grant permissions for migration functions
GRANT EXECUTE ON FUNCTION record_migration(VARCHAR, VARCHAR, BOOLEAN, TEXT) TO ml_app_user;
GRANT EXECUTE ON FUNCTION is_migration_applied(VARCHAR) TO ml_app_user;
GRANT EXECUTE ON FUNCTION migrate_data_to_new_schema() TO ml_app_user;

-- Grant permissions on migration tables
GRANT SELECT, INSERT ON public.migration_history TO ml_app_user;
GRANT SELECT ON public.alembic_version TO ml_app_user;

-- Record this migration
SELECT record_migration('migration_compatibility_layer', 'local_init_v1', true);

-- Log migration compatibility setup completion
DO $$
BEGIN
    RAISE NOTICE 'Migration compatibility layer setup completed successfully';
END $$;