-- Port Existing Database Migrations to Local Setup
-- This script ports all existing application migrations to work with local PostgreSQL

-- Set search path to include both schemas
SET search_path TO multimodal_librarian, public;

-- Port Authentication Tables Migration
DO $
BEGIN
    IF NOT is_migration_applied('authentication_tables_port') THEN
        -- Ensure all authentication tables exist in multimodal_librarian schema
        
        -- API Keys table (from add_authentication_tables.py)
        CREATE TABLE IF NOT EXISTS multimodal_librarian.api_keys (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            key_id VARCHAR(100) UNIQUE NOT NULL,
            user_id UUID NOT NULL REFERENCES multimodal_librarian.users(id) ON DELETE CASCADE,
            name VARCHAR(200) NOT NULL,
            key_hash VARCHAR(255) NOT NULL,
            permissions TEXT[] DEFAULT '{}',
            is_active BOOLEAN DEFAULT true,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP WITH TIME ZONE,
            last_used TIMESTAMP WITH TIME ZONE,
            usage_count INTEGER DEFAULT 0
        );
        
        -- Enhanced audit log table
        CREATE TABLE IF NOT EXISTS multimodal_librarian.audit_logs (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            event_id VARCHAR(100) UNIQUE NOT NULL,
            event_type VARCHAR(50) NOT NULL,
            level VARCHAR(20) DEFAULT 'info',
            timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            user_id UUID REFERENCES multimodal_librarian.users(id) ON DELETE SET NULL,
            session_id VARCHAR(100),
            ip_address INET,
            user_agent TEXT,
            resource_type VARCHAR(50),
            resource_id VARCHAR(100),
            action VARCHAR(100) NOT NULL,
            result VARCHAR(20) NOT NULL,
            details JSONB DEFAULT '{}',
            sensitive_data_hash VARCHAR(64)
        );
        
        -- Data deletion logs for compliance
        CREATE TABLE IF NOT EXISTS multimodal_librarian.data_deletion_logs (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            deletion_id VARCHAR(100) UNIQUE NOT NULL,
            resource_type VARCHAR(50) NOT NULL,
            resource_id VARCHAR(100) NOT NULL,
            requested_by VARCHAR(100) NOT NULL,
            deletion_reason VARCHAR(200),
            deletion_status VARCHAR(20) DEFAULT 'pending',
            deleted_components JSONB DEFAULT '[]',
            errors JSONB DEFAULT '[]',
            requested_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP WITH TIME ZONE,
            verification_hash VARCHAR(64)
        );
        
        -- Privacy requests for GDPR compliance
        CREATE TABLE IF NOT EXISTS multimodal_librarian.privacy_requests (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            request_id VARCHAR(100) UNIQUE NOT NULL,
            request_type VARCHAR(50) NOT NULL,
            user_id VARCHAR(100) NOT NULL,
            requested_by VARCHAR(100) NOT NULL,
            request_details JSONB DEFAULT '{}',
            status VARCHAR(20) DEFAULT 'pending',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            processed_at TIMESTAMP WITH TIME ZONE,
            completed_at TIMESTAMP WITH TIME ZONE,
            result_data JSONB DEFAULT '{}',
            notes TEXT
        );
        
        -- Security incidents tracking
        CREATE TABLE IF NOT EXISTS multimodal_librarian.security_incidents (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            incident_id VARCHAR(100) UNIQUE NOT NULL,
            incident_type VARCHAR(50) NOT NULL,
            severity VARCHAR(20) DEFAULT 'medium',
            status VARCHAR(20) DEFAULT 'open',
            detected_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            resolved_at TIMESTAMP WITH TIME ZONE,
            source_ip INET,
            user_id VARCHAR(100),
            description TEXT NOT NULL,
            indicators JSONB DEFAULT '{}',
            response_actions JSONB DEFAULT '[]',
            false_positive BOOLEAN DEFAULT false
        );
        
        -- Encryption key management
        CREATE TABLE IF NOT EXISTS multimodal_librarian.encryption_keys (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            key_id VARCHAR(100) UNIQUE NOT NULL,
            key_type VARCHAR(50) NOT NULL,
            key_hash VARCHAR(64) NOT NULL,
            algorithm VARCHAR(50) DEFAULT 'AES-256',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP WITH TIME ZONE,
            rotated_at TIMESTAMP WITH TIME ZONE,
            is_active BOOLEAN DEFAULT true,
            usage_count INTEGER DEFAULT 0
        );
        
        -- Create indexes for authentication tables
        CREATE INDEX IF NOT EXISTS idx_api_keys_user_id ON multimodal_librarian.api_keys(user_id);
        CREATE INDEX IF NOT EXISTS idx_api_keys_active ON multimodal_librarian.api_keys(is_active);
        CREATE INDEX IF NOT EXISTS idx_audit_logs_user_id ON multimodal_librarian.audit_logs(user_id);
        CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp ON multimodal_librarian.audit_logs(timestamp);
        CREATE INDEX IF NOT EXISTS idx_audit_logs_event_type ON multimodal_librarian.audit_logs(event_type);
        CREATE INDEX IF NOT EXISTS idx_security_incidents_type ON multimodal_librarian.security_incidents(incident_type);
        CREATE INDEX IF NOT EXISTS idx_security_incidents_status ON multimodal_librarian.security_incidents(status);
        
        PERFORM record_migration('authentication_tables_port', 'auth_port_v1', true);
        RAISE NOTICE 'Authentication tables migration ported successfully';
    END IF;
END $;

-- Port Chat Messages Migration
DO $
BEGIN
    IF NOT is_migration_applied('chat_messages_port') THEN
        -- Enhanced chat messages table (from add_chat_messages.py)
        CREATE TABLE IF NOT EXISTS multimodal_librarian.chat_messages (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            user_id VARCHAR(100) NOT NULL,
            content TEXT NOT NULL,
            message_type VARCHAR(20) NOT NULL DEFAULT 'user',
            timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            sources TEXT[] DEFAULT '{}',
            message_metadata JSONB DEFAULT '{}',
            
            CONSTRAINT check_chat_message_type CHECK (message_type IN ('user', 'assistant', 'system'))
        );
        
        -- Create indexes for chat messages
        CREATE INDEX IF NOT EXISTS idx_chat_messages_user_id ON multimodal_librarian.chat_messages(user_id);
        CREATE INDEX IF NOT EXISTS idx_chat_messages_timestamp ON multimodal_librarian.chat_messages(timestamp);
        CREATE INDEX IF NOT EXISTS idx_chat_messages_type ON multimodal_librarian.chat_messages(message_type);
        
        PERFORM record_migration('chat_messages_port', 'chat_port_v1', true);
        RAISE NOTICE 'Chat messages migration ported successfully';
    END IF;
END $;

-- Port Documents Migration
DO $
BEGIN
    IF NOT is_migration_applied('documents_tables_port') THEN
        -- Enhanced documents table (from add_documents_table.py)
        -- Note: Basic documents table already exists in schema, enhance it
        
        -- Add missing columns to existing documents table
        ALTER TABLE multimodal_librarian.documents 
        ADD COLUMN IF NOT EXISTS description TEXT,
        ADD COLUMN IF NOT EXISTS s3_key VARCHAR(500),
        ADD COLUMN IF NOT EXISTS processing_started_at TIMESTAMP WITH TIME ZONE,
        ADD COLUMN IF NOT EXISTS processing_completed_at TIMESTAMP WITH TIME ZONE,
        ADD COLUMN IF NOT EXISTS page_count INTEGER,
        ADD COLUMN IF NOT EXISTS chunk_count INTEGER,
        ADD COLUMN IF NOT EXISTS doc_metadata JSONB DEFAULT '{}';
        
        -- Create document chunks table for local development
        CREATE TABLE IF NOT EXISTS multimodal_librarian.document_chunks (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            document_id UUID NOT NULL REFERENCES multimodal_librarian.documents(id) ON DELETE CASCADE,
            chunk_index INTEGER NOT NULL,
            content TEXT NOT NULL,
            page_number INTEGER,
            section_title VARCHAR(255),
            chunk_type VARCHAR(50) NOT NULL DEFAULT 'text',
            chunk_metadata JSONB DEFAULT '{}',
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            
            CONSTRAINT uq_document_chunk_index UNIQUE(document_id, chunk_index),
            CONSTRAINT check_chunk_type CHECK (chunk_type IN ('text', 'image', 'table', 'chart')),
            CONSTRAINT check_positive_chunk_index CHECK (chunk_index >= 0),
            CONSTRAINT check_positive_page_number CHECK (page_number IS NULL OR page_number > 0)
        );
        
        -- Processing jobs table for background processing
        CREATE TABLE IF NOT EXISTS multimodal_librarian.processing_jobs (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            document_id UUID NOT NULL REFERENCES multimodal_librarian.documents(id) ON DELETE CASCADE,
            task_id VARCHAR(255),
            status VARCHAR(50) NOT NULL DEFAULT 'pending',
            progress_percentage INTEGER DEFAULT 0,
            current_step VARCHAR(100),
            error_message TEXT,
            started_at TIMESTAMP WITH TIME ZONE,
            completed_at TIMESTAMP WITH TIME ZONE,
            retry_count INTEGER DEFAULT 0,
            job_metadata JSONB DEFAULT '{}',
            
            CONSTRAINT check_job_status CHECK (status IN ('pending', 'running', 'completed', 'failed')),
            CONSTRAINT check_progress CHECK (progress_percentage >= 0 AND progress_percentage <= 100)
        );
        
        -- Create indexes for document tables
        CREATE INDEX IF NOT EXISTS idx_document_chunks_document_id ON multimodal_librarian.document_chunks(document_id);
        CREATE INDEX IF NOT EXISTS idx_document_chunks_type ON multimodal_librarian.document_chunks(chunk_type);
        CREATE INDEX IF NOT EXISTS idx_document_chunks_page ON multimodal_librarian.document_chunks(page_number);
        CREATE INDEX IF NOT EXISTS idx_processing_jobs_document_id ON multimodal_librarian.processing_jobs(document_id);
        CREATE INDEX IF NOT EXISTS idx_processing_jobs_status ON multimodal_librarian.processing_jobs(status);
        CREATE INDEX IF NOT EXISTS idx_processing_jobs_task_id ON multimodal_librarian.processing_jobs(task_id);
        
        PERFORM record_migration('documents_tables_port', 'docs_port_v1', true);
        RAISE NOTICE 'Documents tables migration ported successfully';
    END IF;
END $;

-- Port Analytics Migration
DO $
BEGIN
    IF NOT is_migration_applied('analytics_migration_port') THEN
        -- User analytics table (from analytics_migration.sql)
        CREATE TABLE IF NOT EXISTS multimodal_librarian.user_analytics (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            user_id VARCHAR(255) NOT NULL,
            event_type VARCHAR(100) NOT NULL,
            event_data JSONB DEFAULT '{}',
            timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            session_id VARCHAR(255)
        );
        
        -- Document analytics table
        CREATE TABLE IF NOT EXISTS multimodal_librarian.document_analytics (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            document_id UUID REFERENCES multimodal_librarian.documents(id) ON DELETE CASCADE,
            event_type VARCHAR(100) NOT NULL,
            event_data JSONB DEFAULT '{}',
            timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            user_id VARCHAR(255)
        );
        
        -- System performance metrics
        CREATE TABLE IF NOT EXISTS multimodal_librarian.system_metrics (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            metric_name VARCHAR(100) NOT NULL,
            metric_value DECIMAL(10,4) NOT NULL,
            metric_unit VARCHAR(20),
            timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            tags JSONB DEFAULT '{}'
        );
        
        -- Create indexes for analytics tables
        CREATE INDEX IF NOT EXISTS idx_user_analytics_user_id ON multimodal_librarian.user_analytics(user_id);
        CREATE INDEX IF NOT EXISTS idx_user_analytics_event_type ON multimodal_librarian.user_analytics(event_type);
        CREATE INDEX IF NOT EXISTS idx_user_analytics_timestamp ON multimodal_librarian.user_analytics(timestamp);
        CREATE INDEX IF NOT EXISTS idx_document_analytics_document_id ON multimodal_librarian.document_analytics(document_id);
        CREATE INDEX IF NOT EXISTS idx_document_analytics_event_type ON multimodal_librarian.document_analytics(event_type);
        CREATE INDEX IF NOT EXISTS idx_system_metrics_name ON multimodal_librarian.system_metrics(metric_name);
        CREATE INDEX IF NOT EXISTS idx_system_metrics_timestamp ON multimodal_librarian.system_metrics(timestamp);
        
        PERFORM record_migration('analytics_migration_port', 'analytics_port_v1', true);
        RAISE NOTICE 'Analytics migration ported successfully';
    END IF;
END $;

-- Port Knowledge Graph and ML Training Tables
DO $
BEGIN
    IF NOT is_migration_applied('ml_training_tables_port') THEN
        -- Knowledge sources table (unified books and conversations)
        CREATE TABLE IF NOT EXISTS multimodal_librarian.knowledge_sources (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            source_type VARCHAR(20) NOT NULL,
            title VARCHAR(500) NOT NULL,
            author VARCHAR(200),
            file_path VARCHAR(1000),
            file_size INTEGER DEFAULT 0,
            page_count INTEGER DEFAULT 0,
            language VARCHAR(10) DEFAULT 'en',
            subject VARCHAR(200),
            keywords TEXT[] DEFAULT '{}',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT true,
            
            CONSTRAINT check_source_type CHECK (source_type IN ('book', 'conversation'))
        );
        
        -- Content profiles for document analysis
        CREATE TABLE IF NOT EXISTS multimodal_librarian.content_profiles (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            source_id UUID NOT NULL REFERENCES multimodal_librarian.knowledge_sources(id) ON DELETE CASCADE,
            content_type VARCHAR(20) NOT NULL,
            domain_categories TEXT[] DEFAULT '{}',
            complexity_score DECIMAL(5,4) DEFAULT 0.0,
            structure_hierarchy JSONB DEFAULT '{}',
            domain_patterns JSONB DEFAULT '{}',
            cross_reference_density DECIMAL(5,4) DEFAULT 0.0,
            conceptual_density DECIMAL(5,4) DEFAULT 0.0,
            chunking_requirements JSONB DEFAULT '{}',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            
            CONSTRAINT check_profile_complexity CHECK (complexity_score >= 0.0 AND complexity_score <= 1.0),
            CONSTRAINT check_cross_ref_density CHECK (cross_reference_density >= 0.0),
            CONSTRAINT check_conceptual_density CHECK (conceptual_density >= 0.0)
        );
        
        -- Bridge chunks for gap filling
        CREATE TABLE IF NOT EXISTS multimodal_librarian.bridge_chunks (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            bridge_id VARCHAR(100) UNIQUE NOT NULL,
            content TEXT NOT NULL,
            source_chunk_id UUID NOT NULL REFERENCES multimodal_librarian.knowledge_chunks(id) ON DELETE CASCADE,
            target_chunk_id VARCHAR(100),
            generation_method VARCHAR(50) DEFAULT 'gemini_25_flash',
            gap_analysis JSONB DEFAULT '{}',
            validation_result JSONB DEFAULT '{}',
            confidence_score DECIMAL(5,4) DEFAULT 0.0,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            
            CONSTRAINT check_bridge_confidence CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0)
        );
        
        -- Gap analysis results
        CREATE TABLE IF NOT EXISTS multimodal_librarian.gap_analyses (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            analysis_id VARCHAR(100) UNIQUE NOT NULL,
            chunk1_id VARCHAR(100) NOT NULL,
            chunk2_id VARCHAR(100) NOT NULL,
            necessity_score DECIMAL(5,4) NOT NULL,
            gap_type VARCHAR(50) NOT NULL,
            bridge_strategy VARCHAR(50) NOT NULL,
            semantic_distance DECIMAL(5,4) DEFAULT 0.0,
            concept_overlap DECIMAL(5,4) DEFAULT 0.0,
            cross_reference_density DECIMAL(5,4) DEFAULT 0.0,
            structural_continuity DECIMAL(5,4) DEFAULT 0.0,
            domain_specific_gaps JSONB DEFAULT '{}',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            
            CONSTRAINT check_necessity_score CHECK (necessity_score >= 0.0 AND necessity_score <= 1.0),
            CONSTRAINT check_semantic_distance CHECK (semantic_distance >= 0.0),
            CONSTRAINT check_concept_overlap CHECK (concept_overlap >= 0.0 AND concept_overlap <= 1.0)
        );
        
        -- Training sessions for ML
        CREATE TABLE IF NOT EXISTS multimodal_librarian.training_sessions (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            session_id VARCHAR(100) UNIQUE NOT NULL,
            session_type VARCHAR(50) NOT NULL,
            batch_size INTEGER,
            total_chunks INTEGER DEFAULT 0,
            total_sequences INTEGER DEFAULT 0,
            content_types TEXT[] DEFAULT '{}',
            source_types TEXT[] DEFAULT '{}',
            reward_distribution JSONB DEFAULT '{}',
            performance_metrics JSONB DEFAULT '{}',
            started_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP WITH TIME ZONE,
            status VARCHAR(20) DEFAULT 'active',
            
            CONSTRAINT check_session_status CHECK (status IN ('active', 'completed', 'failed')),
            CONSTRAINT check_batch_size_positive CHECK (batch_size IS NULL OR batch_size > 0)
        );
        
        -- Create indexes for ML training tables
        CREATE INDEX IF NOT EXISTS idx_knowledge_sources_type ON multimodal_librarian.knowledge_sources(source_type);
        CREATE INDEX IF NOT EXISTS idx_content_profiles_source ON multimodal_librarian.content_profiles(source_id);
        CREATE INDEX IF NOT EXISTS idx_bridge_chunks_source ON multimodal_librarian.bridge_chunks(source_chunk_id);
        CREATE INDEX IF NOT EXISTS idx_gap_analyses_chunks ON multimodal_librarian.gap_analyses(chunk1_id, chunk2_id);
        CREATE INDEX IF NOT EXISTS idx_training_sessions_type ON multimodal_librarian.training_sessions(session_type);
        CREATE INDEX IF NOT EXISTS idx_training_sessions_status ON multimodal_librarian.training_sessions(status);
        
        PERFORM record_migration('ml_training_tables_port', 'ml_port_v1', true);
        RAISE NOTICE 'ML training tables migration ported successfully';
    END IF;
END $;

-- Create compatibility views for existing code
CREATE OR REPLACE VIEW public.documents_compat AS
SELECT 
    id,
    user_id::text as user_id,
    title,
    filename,
    file_size,
    mime_type,
    s3_key,
    CASE 
        WHEN processing_status = 'COMPLETED' THEN 'completed'
        WHEN processing_status = 'FAILED' THEN 'failed'
        WHEN processing_status = 'PROCESSING' THEN 'processing'
        ELSE 'uploaded'
    END as upload_status,
    created_at,
    updated_at,
    processed_at
FROM multimodal_librarian.documents;

CREATE OR REPLACE VIEW public.chat_messages_compat AS
SELECT 
    id,
    user_id,
    content as message,
    CASE 
        WHEN message_type = 'assistant' THEN content
        ELSE NULL
    END as response,
    timestamp,
    message_metadata as metadata
FROM multimodal_librarian.chat_messages;

-- Grant permissions on new tables
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA multimodal_librarian TO ml_app_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA multimodal_librarian TO ml_app_user;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA multimodal_librarian TO ml_app_user;

-- Grant read-only permissions
GRANT SELECT ON ALL TABLES IN SCHEMA multimodal_librarian TO ml_readonly;

-- Record the overall migration porting
SELECT record_migration('existing_migrations_port', 'complete_port_v1', true);

-- Log completion
DO $
BEGIN
    RAISE NOTICE 'All existing migrations have been successfully ported to local setup';
    RAISE NOTICE 'Migration compatibility layer is active';
    RAISE NOTICE 'Local development database is ready for use';
END $;