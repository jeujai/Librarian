-- Multimodal Librarian Database Initialization Script
-- This script sets up the initial database schema and configuration

-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "btree_gin";

-- Create schemas
CREATE SCHEMA IF NOT EXISTS multimodal_librarian;
CREATE SCHEMA IF NOT EXISTS audit;

-- Set search path
SET search_path TO multimodal_librarian, public;

-- Create enum types
CREATE TYPE content_type AS ENUM ('TECHNICAL', 'LEGAL', 'MEDICAL', 'NARRATIVE', 'ACADEMIC', 'CONVERSATION', 'GENERAL');
CREATE TYPE source_type AS ENUM ('BOOK', 'CONVERSATION', 'UPLOAD');
CREATE TYPE message_type AS ENUM ('USER', 'SYSTEM', 'UPLOAD');
CREATE TYPE processing_status AS ENUM ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED');

-- Users table (for authentication and authorization)
CREATE TABLE IF NOT EXISTS users (
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
CREATE TABLE IF NOT EXISTS user_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_token VARCHAR(255) UNIQUE NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_accessed TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    ip_address INET,
    user_agent TEXT
);

-- Knowledge sources table (unified books, conversations, and uploads)
-- This is the primary table for the unified schema migration
-- Supports source_type values: 'BOOK', 'CONVERSATION', 'UPLOAD' (Requirement 5.1)
CREATE TABLE IF NOT EXISTS knowledge_sources (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source_type source_type NOT NULL,
    title VARCHAR(500) NOT NULL,
    file_path VARCHAR(1000),
    file_size BIGINT DEFAULT 0,
    mime_type VARCHAR(100),
    processing_status processing_status DEFAULT 'PENDING',
    processing_error TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP WITH TIME ZONE
);

-- Processing jobs table for background document processing
-- Tracks the status of document processing tasks
CREATE TABLE IF NOT EXISTS processing_jobs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_id UUID NOT NULL REFERENCES knowledge_sources(id) ON DELETE CASCADE,
    task_id VARCHAR(255),
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    progress_percentage INTEGER DEFAULT 0,
    current_step VARCHAR(100),
    error_message TEXT,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    retry_count INTEGER DEFAULT 0,
    job_metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT check_job_status CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    CONSTRAINT check_progress CHECK (progress_percentage >= 0 AND progress_percentage <= 100)
);

-- Conversation threads table
CREATE TABLE IF NOT EXISTS conversation_threads (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(500),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_message_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    is_archived BOOLEAN DEFAULT false,
    metadata JSONB DEFAULT '{}'
);

-- Messages table (for conversation history)
CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    thread_id UUID NOT NULL REFERENCES conversation_threads(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    message_type message_type NOT NULL,
    multimedia_content JSONB DEFAULT '[]',
    knowledge_references JSONB DEFAULT '[]',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB DEFAULT '{}'
);

-- Knowledge chunks table (for vector database metadata)
-- Maintains referential integrity with knowledge_sources (Requirement 5.2)
-- Cascade deletes associated chunks when knowledge source is deleted (Requirement 5.3)
CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_id UUID NOT NULL REFERENCES knowledge_sources(id) ON DELETE CASCADE, -- Requirement 5.2, 5.3
    source_type source_type NOT NULL,
    content TEXT NOT NULL,
    content_hash VARCHAR(64) NOT NULL, -- SHA-256 hash for deduplication
    chunk_index INTEGER NOT NULL,
    location_reference VARCHAR(255), -- page number, timestamp, etc.
    section VARCHAR(255),
    content_type content_type NOT NULL DEFAULT 'GENERAL',
    associated_media JSONB DEFAULT '[]',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    -- Ensure unique chunks per source (Requirement 5.4)
    UNIQUE(source_id, source_type, content_hash)
);

-- Domain configurations table (for chunking framework)
CREATE TABLE IF NOT EXISTS domain_configurations (
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
CREATE TABLE IF NOT EXISTS performance_metrics (
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
CREATE TABLE IF NOT EXISTS user_feedback (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    chunk_id UUID REFERENCES knowledge_chunks(id) ON DELETE CASCADE,
    interaction_type VARCHAR(50) NOT NULL, -- VIEW, CITE, EXPORT, RATE
    feedback_score DECIMAL(3,2), -- 0.00 to 5.00
    feedback_text TEXT,
    context_query TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB DEFAULT '{}'
);

-- Export history table (for tracking exports)
CREATE TABLE IF NOT EXISTS export_history (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    export_format VARCHAR(20) NOT NULL,
    content_summary TEXT,
    file_path VARCHAR(1000),
    file_size BIGINT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE,
    download_count INTEGER DEFAULT 0,
    metadata JSONB DEFAULT '{}'
);

-- Enrichment status table (for tracking background YAGO/ConceptNet enrichment)
CREATE TABLE IF NOT EXISTS enrichment_status (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES knowledge_sources(id) ON DELETE CASCADE,
    state VARCHAR(20) NOT NULL DEFAULT 'pending',
    total_concepts INTEGER NOT NULL DEFAULT 0,
    concepts_enriched INTEGER NOT NULL DEFAULT 0,
    yago_hits INTEGER NOT NULL DEFAULT 0,
    conceptnet_hits INTEGER NOT NULL DEFAULT 0,
    cache_hits INTEGER NOT NULL DEFAULT 0,
    error_count INTEGER NOT NULL DEFAULT 0,
    retry_count INTEGER NOT NULL DEFAULT 0,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    duration_ms FLOAT,
    last_error TEXT,
    checkpoint_index INTEGER,
    checkpoint_data JSONB,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_enrichment_document UNIQUE(document_id),
    CONSTRAINT check_enrichment_state CHECK (
        state IN ('pending', 'enriching', 'completed', 'failed', 'skipped')
    ),
    CONSTRAINT check_positive_total_concepts CHECK (total_concepts >= 0),
    CONSTRAINT check_positive_concepts_enriched CHECK (concepts_enriched >= 0),
    CONSTRAINT check_positive_yago_hits CHECK (yago_hits >= 0),
    CONSTRAINT check_positive_conceptnet_hits CHECK (conceptnet_hits >= 0),
    CONSTRAINT check_positive_cache_hits CHECK (cache_hits >= 0),
    CONSTRAINT check_positive_error_count CHECK (error_count >= 0),
    CONSTRAINT check_positive_retry_count CHECK (retry_count >= 0),
    CONSTRAINT check_enriched_le_total CHECK (concepts_enriched <= total_concepts)
);

-- Bridge chunks table (LLM-generated bridge chunks connecting adjacent chunks)
CREATE TABLE IF NOT EXISTS bridge_chunks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    bridge_id VARCHAR(100) UNIQUE NOT NULL,
    content TEXT NOT NULL,
    source_chunk_id UUID NOT NULL REFERENCES knowledge_chunks(id) ON DELETE CASCADE,
    target_chunk_id VARCHAR(100),
    generation_method VARCHAR(50) DEFAULT 'gemini_25_flash',
    gap_analysis JSONB,
    validation_result JSONB,
    confidence_score FLOAT DEFAULT 0.0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT check_bridge_confidence CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0)
);

-- Processing payloads table (temporary storage for inter-task data)
-- Avoids passing large serialized documents through the Celery message broker.
-- Rows are cleaned up by finalize_processing_task after processing completes.
CREATE TABLE IF NOT EXISTS processing_payloads (
    document_id UUID PRIMARY KEY REFERENCES knowledge_sources(id) ON DELETE CASCADE,
    payload JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
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

-- Indexes for knowledge_sources table
CREATE INDEX IF NOT EXISTS idx_knowledge_sources_user_id ON knowledge_sources(user_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_sources_source_type ON knowledge_sources(source_type);
CREATE INDEX IF NOT EXISTS idx_knowledge_sources_processing_status ON knowledge_sources(processing_status);
CREATE INDEX IF NOT EXISTS idx_knowledge_sources_created_at ON knowledge_sources(created_at);

-- Indexes for processing_jobs table
CREATE INDEX IF NOT EXISTS idx_processing_jobs_source_id ON processing_jobs(source_id);
CREATE INDEX IF NOT EXISTS idx_processing_jobs_status ON processing_jobs(status);
CREATE INDEX IF NOT EXISTS idx_processing_jobs_task_id ON processing_jobs(task_id);
CREATE INDEX IF NOT EXISTS idx_processing_jobs_created_at ON processing_jobs(created_at);

CREATE INDEX IF NOT EXISTS idx_conversation_threads_user_id ON conversation_threads(user_id);
CREATE INDEX IF NOT EXISTS idx_conversation_threads_updated_at ON conversation_threads(updated_at);

CREATE INDEX IF NOT EXISTS idx_messages_thread_id ON messages(thread_id);
CREATE INDEX IF NOT EXISTS idx_messages_user_id ON messages(user_id);
CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at);

CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_source ON knowledge_chunks(source_id, source_type);
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_content_type ON knowledge_chunks(content_type);
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_hash ON knowledge_chunks(content_hash);
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_created_at ON knowledge_chunks(created_at);

CREATE INDEX IF NOT EXISTS idx_domain_configurations_domain_name ON domain_configurations(domain_name);
CREATE INDEX IF NOT EXISTS idx_domain_configurations_active ON domain_configurations(is_active);

CREATE INDEX IF NOT EXISTS idx_performance_metrics_domain ON performance_metrics(domain_name);
CREATE INDEX IF NOT EXISTS idx_performance_metrics_date ON performance_metrics(measurement_date);

CREATE INDEX IF NOT EXISTS idx_user_feedback_user_id ON user_feedback(user_id);
CREATE INDEX IF NOT EXISTS idx_user_feedback_chunk_id ON user_feedback(chunk_id);
CREATE INDEX IF NOT EXISTS idx_user_feedback_created_at ON user_feedback(created_at);

CREATE INDEX IF NOT EXISTS idx_export_history_user_id ON export_history(user_id);
CREATE INDEX IF NOT EXISTS idx_export_history_created_at ON export_history(created_at);

CREATE INDEX IF NOT EXISTS idx_bridge_chunks_source ON bridge_chunks(source_chunk_id);
CREATE INDEX IF NOT EXISTS idx_bridge_chunks_method ON bridge_chunks(generation_method);
CREATE INDEX IF NOT EXISTS idx_bridge_chunks_confidence ON bridge_chunks(confidence_score);
CREATE INDEX IF NOT EXISTS idx_bridge_chunks_created ON bridge_chunks(created_at);

CREATE INDEX IF NOT EXISTS idx_enrichment_status_document_id ON enrichment_status(document_id);
CREATE INDEX IF NOT EXISTS idx_enrichment_status_state ON enrichment_status(state);
CREATE INDEX IF NOT EXISTS idx_enrichment_status_created_at ON enrichment_status(created_at);

CREATE INDEX IF NOT EXISTS idx_audit_log_user_id ON audit.audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_action ON audit.audit_log(action);
CREATE INDEX IF NOT EXISTS idx_audit_log_created_at ON audit.audit_log(created_at);

-- Create full-text search indexes
CREATE INDEX IF NOT EXISTS idx_knowledge_sources_title_fts ON knowledge_sources USING gin(to_tsvector('english', title));
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_content_fts ON knowledge_chunks USING gin(to_tsvector('english', content));
CREATE INDEX IF NOT EXISTS idx_messages_content_fts ON messages USING gin(to_tsvector('english', content));

-- Create triggers for updated_at timestamps
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_knowledge_sources_updated_at BEFORE UPDATE ON knowledge_sources
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_conversation_threads_updated_at BEFORE UPDATE ON conversation_threads
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_knowledge_chunks_updated_at BEFORE UPDATE ON knowledge_chunks
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_domain_configurations_updated_at BEFORE UPDATE ON domain_configurations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_enrichment_status_updated_at BEFORE UPDATE ON enrichment_status
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Create function to clean up expired sessions
CREATE OR REPLACE FUNCTION cleanup_expired_sessions()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM user_sessions WHERE expires_at < CURRENT_TIMESTAMP;
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- Create function to clean up expired exports
CREATE OR REPLACE FUNCTION cleanup_expired_exports()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM export_history 
    WHERE expires_at IS NOT NULL AND expires_at < CURRENT_TIMESTAMP;
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- Insert default admin user (password: admin123 - change in production!)
INSERT INTO users (username, email, password_hash, is_admin) 
VALUES (
    'admin', 
    'admin@multimodal-librarian.local', 
    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj3QJflLxQjO', -- admin123
    true
) ON CONFLICT (username) DO NOTHING;

-- Grant permissions
GRANT USAGE ON SCHEMA multimodal_librarian TO postgres;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA multimodal_librarian TO postgres;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA multimodal_librarian TO postgres;

GRANT USAGE ON SCHEMA audit TO postgres;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA audit TO postgres;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA audit TO postgres;

-- Create a read-only user for reporting (optional)
-- CREATE USER ml_readonly WITH PASSWORD 'readonly_password';
-- GRANT USAGE ON SCHEMA multimodal_librarian TO ml_readonly;
-- GRANT SELECT ON ALL TABLES IN SCHEMA multimodal_librarian TO ml_readonly;

COMMIT;