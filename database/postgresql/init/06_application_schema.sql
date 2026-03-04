-- Application Schema Initialization for Multimodal Librarian
-- This script creates the main application database schema

-- Create application schemas
CREATE SCHEMA IF NOT EXISTS multimodal_librarian;
CREATE SCHEMA IF NOT EXISTS audit;

-- Set search path to include application schema
SET search_path TO multimodal_librarian, public;

-- Create enum types for the application
DO $$ 
BEGIN
    -- Content type enum
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'content_type') THEN
        CREATE TYPE content_type AS ENUM ('TECHNICAL', 'LEGAL', 'MEDICAL', 'NARRATIVE', 'ACADEMIC', 'CONVERSATION');
    END IF;
    
    -- Source type enum
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'source_type') THEN
        CREATE TYPE source_type AS ENUM ('BOOK', 'CONVERSATION', 'UPLOAD');
    END IF;
    
    -- Message type enum
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'message_type') THEN
        CREATE TYPE message_type AS ENUM ('USER', 'SYSTEM', 'UPLOAD');
    END IF;
    
    -- Processing status enum
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'processing_status') THEN
        CREATE TYPE processing_status AS ENUM ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED');
    END IF;
END $$;

-- Users table (for authentication and authorization)
CREATE TABLE IF NOT EXISTS multimodal_librarian.users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username VARCHAR(255) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    is_active BOOLEAN DEFAULT true,
    is_admin BOOLEAN DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP WITH TIME ZONE,
    failed_login_attempts INTEGER DEFAULT 0,
    locked_until TIMESTAMP WITH TIME ZONE
);

-- Sessions table (for session management)
CREATE TABLE IF NOT EXISTS multimodal_librarian.user_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES multimodal_librarian.users(id) ON DELETE CASCADE,
    session_token VARCHAR(255) UNIQUE NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_accessed TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    ip_address INET,
    user_agent TEXT
);

-- Documents table (for uploaded books and files)
CREATE TABLE IF NOT EXISTS multimodal_librarian.documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES multimodal_librarian.users(id) ON DELETE CASCADE,
    title VARCHAR(500) NOT NULL,
    filename VARCHAR(255) NOT NULL,
    file_path VARCHAR(1000) NOT NULL,
    file_size BIGINT NOT NULL,
    mime_type VARCHAR(100) NOT NULL,
    content_type content_type NOT NULL,
    processing_status processing_status DEFAULT 'PENDING',
    processing_error TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP WITH TIME ZONE
);

-- Conversation threads table
CREATE TABLE IF NOT EXISTS multimodal_librarian.conversation_threads (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES multimodal_librarian.users(id) ON DELETE CASCADE,
    title VARCHAR(500),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_message_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    is_archived BOOLEAN DEFAULT false,
    metadata JSONB DEFAULT '{}'
);

-- Messages table (for conversation history)
CREATE TABLE IF NOT EXISTS multimodal_librarian.messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    thread_id UUID NOT NULL REFERENCES multimodal_librarian.conversation_threads(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES multimodal_librarian.users(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    message_type message_type NOT NULL,
    multimedia_content JSONB DEFAULT '[]',
    knowledge_references JSONB DEFAULT '[]',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB DEFAULT '{}'
);

-- Knowledge chunks table (for vector database metadata)
CREATE TABLE IF NOT EXISTS multimodal_librarian.knowledge_chunks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_id UUID NOT NULL, -- References documents.id or conversation_threads.id
    source_type source_type NOT NULL,
    content TEXT NOT NULL,
    content_hash VARCHAR(64) NOT NULL, -- SHA-256 hash for deduplication
    chunk_index INTEGER NOT NULL,
    location_reference VARCHAR(255), -- page number, timestamp, etc.
    section VARCHAR(255),
    content_type content_type NOT NULL,
    associated_media JSONB DEFAULT '[]',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    -- Ensure unique chunks per source
    UNIQUE(source_id, source_type, content_hash)
);

-- Domain configurations table (for chunking framework)
CREATE TABLE IF NOT EXISTS multimodal_librarian.domain_configurations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    domain_name VARCHAR(255) UNIQUE NOT NULL,
    config JSONB NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    generation_method VARCHAR(100) NOT NULL,
    source_documents JSONB DEFAULT '[]',
    performance_score DECIMAL(5,4),
    optimization_history JSONB DEFAULT '[]',
    is_active BOOLEAN DEFAULT true,
    usage_count INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Performance metrics table (for configuration optimization)
CREATE TABLE IF NOT EXISTS multimodal_librarian.performance_metrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    domain_name VARCHAR(255) NOT NULL,
    chunk_quality_score DECIMAL(5,4),
    bridge_success_rate DECIMAL(5,4),
    retrieval_effectiveness DECIMAL(5,4),
    user_satisfaction_score DECIMAL(5,4),
    processing_efficiency DECIMAL(5,4),
    boundary_quality DECIMAL(5,4),
    measurement_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    document_count INTEGER,
    metadata JSONB DEFAULT '{}'
);

-- User feedback table (for system improvement)
CREATE TABLE IF NOT EXISTS multimodal_librarian.user_feedback (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES multimodal_librarian.users(id) ON DELETE CASCADE,
    chunk_id UUID REFERENCES multimodal_librarian.knowledge_chunks(id) ON DELETE CASCADE,
    interaction_type VARCHAR(50) NOT NULL, -- VIEW, CITE, EXPORT, RATE
    feedback_score DECIMAL(3,2), -- 0.00 to 5.00
    feedback_text TEXT,
    context_query TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB DEFAULT '{}'
);

-- Export history table (for tracking exports)
CREATE TABLE IF NOT EXISTS multimodal_librarian.export_history (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES multimodal_librarian.users(id) ON DELETE CASCADE,
    export_format VARCHAR(20) NOT NULL,
    content_summary TEXT,
    file_path VARCHAR(1000),
    file_size BIGINT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE,
    download_count INTEGER DEFAULT 0,
    metadata JSONB DEFAULT '{}'
);

-- Audit log table (for security and compliance)
CREATE TABLE IF NOT EXISTS audit.audit_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES multimodal_librarian.users(id) ON DELETE SET NULL,
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(100) NOT NULL,
    resource_id UUID,
    details JSONB DEFAULT '{}',
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    session_id UUID
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_documents_user_id ON multimodal_librarian.documents(user_id);
CREATE INDEX IF NOT EXISTS idx_documents_content_type ON multimodal_librarian.documents(content_type);
CREATE INDEX IF NOT EXISTS idx_documents_processing_status ON multimodal_librarian.documents(processing_status);
CREATE INDEX IF NOT EXISTS idx_documents_created_at ON multimodal_librarian.documents(created_at);

CREATE INDEX IF NOT EXISTS idx_conversation_threads_user_id ON multimodal_librarian.conversation_threads(user_id);
CREATE INDEX IF NOT EXISTS idx_conversation_threads_updated_at ON multimodal_librarian.conversation_threads(updated_at);

CREATE INDEX IF NOT EXISTS idx_messages_thread_id ON multimodal_librarian.messages(thread_id);
CREATE INDEX IF NOT EXISTS idx_messages_user_id ON multimodal_librarian.messages(user_id);
CREATE INDEX IF NOT EXISTS idx_messages_created_at ON multimodal_librarian.messages(created_at);

CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_source ON multimodal_librarian.knowledge_chunks(source_id, source_type);
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_content_type ON multimodal_librarian.knowledge_chunks(content_type);
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_hash ON multimodal_librarian.knowledge_chunks(content_hash);
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_created_at ON multimodal_librarian.knowledge_chunks(created_at);

CREATE INDEX IF NOT EXISTS idx_domain_configurations_domain_name ON multimodal_librarian.domain_configurations(domain_name);
CREATE INDEX IF NOT EXISTS idx_domain_configurations_active ON multimodal_librarian.domain_configurations(is_active);

CREATE INDEX IF NOT EXISTS idx_performance_metrics_domain ON multimodal_librarian.performance_metrics(domain_name);
CREATE INDEX IF NOT EXISTS idx_performance_metrics_date ON multimodal_librarian.performance_metrics(measurement_date);

CREATE INDEX IF NOT EXISTS idx_user_feedback_user_id ON multimodal_librarian.user_feedback(user_id);
CREATE INDEX IF NOT EXISTS idx_user_feedback_chunk_id ON multimodal_librarian.user_feedback(chunk_id);
CREATE INDEX IF NOT EXISTS idx_user_feedback_created_at ON multimodal_librarian.user_feedback(created_at);

CREATE INDEX IF NOT EXISTS idx_export_history_user_id ON multimodal_librarian.export_history(user_id);
CREATE INDEX IF NOT EXISTS idx_export_history_created_at ON multimodal_librarian.export_history(created_at);

CREATE INDEX IF NOT EXISTS idx_audit_log_user_id ON audit.audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_action ON audit.audit_log(action);
CREATE INDEX IF NOT EXISTS idx_audit_log_created_at ON audit.audit_log(created_at);

-- Create full-text search indexes
CREATE INDEX IF NOT EXISTS idx_documents_title_fts ON multimodal_librarian.documents USING gin(to_tsvector('english', title));
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_content_fts ON multimodal_librarian.knowledge_chunks USING gin(to_tsvector('english', content));
CREATE INDEX IF NOT EXISTS idx_messages_content_fts ON multimodal_librarian.messages USING gin(to_tsvector('english', content));

-- Create triggers for updated_at timestamps
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$ language 'plpgsql';

CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON multimodal_librarian.users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_documents_updated_at BEFORE UPDATE ON multimodal_librarian.documents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_conversation_threads_updated_at BEFORE UPDATE ON multimodal_librarian.conversation_threads
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_knowledge_chunks_updated_at BEFORE UPDATE ON multimodal_librarian.knowledge_chunks
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_domain_configurations_updated_at BEFORE UPDATE ON multimodal_librarian.domain_configurations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Create function to clean up expired sessions
CREATE OR REPLACE FUNCTION cleanup_expired_sessions()
RETURNS INTEGER AS $
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM multimodal_librarian.user_sessions WHERE expires_at < CURRENT_TIMESTAMP;
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$ LANGUAGE plpgsql;

-- Create function to clean up expired exports
CREATE OR REPLACE FUNCTION cleanup_expired_exports()
RETURNS INTEGER AS $
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM multimodal_librarian.export_history 
    WHERE expires_at IS NOT NULL AND expires_at < CURRENT_TIMESTAMP;
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$ LANGUAGE plpgsql;

-- Insert default admin user (password: admin123 - change in production!)
INSERT INTO multimodal_librarian.users (username, email, password_hash, is_admin) 
VALUES (
    'admin', 
    'admin@multimodal-librarian.local', 
    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj3QJflLxQjO', -- admin123
    true
) ON CONFLICT (username) DO NOTHING;

-- Grant permissions to application users
GRANT USAGE ON SCHEMA multimodal_librarian TO ml_app_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA multimodal_librarian TO ml_app_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA multimodal_librarian TO ml_app_user;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA multimodal_librarian TO ml_app_user;

GRANT USAGE ON SCHEMA audit TO ml_app_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA audit TO ml_app_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA audit TO ml_app_user;

-- Grant read-only permissions
GRANT USAGE ON SCHEMA multimodal_librarian TO ml_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA multimodal_librarian TO ml_readonly;
GRANT USAGE ON SCHEMA audit TO ml_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA audit TO ml_readonly;

-- Log application schema setup completion
DO $
BEGIN
    RAISE NOTICE 'Application schema setup completed successfully';
END $;