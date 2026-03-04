-- Analytics Migration: Document Access Tracking
-- This migration adds tables for document analytics and usage tracking

-- Document access logs table
CREATE TABLE IF NOT EXISTS document_access_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    user_id UUID NOT NULL,
    access_type VARCHAR(50) NOT NULL DEFAULT 'view',
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    metadata JSONB DEFAULT '{}',
    
    CONSTRAINT valid_access_type CHECK (access_type IN ('view', 'search', 'chat', 'download', 'share'))
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_document_access_logs_document_id ON document_access_logs(document_id);
CREATE INDEX IF NOT EXISTS idx_document_access_logs_user_id ON document_access_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_document_access_logs_timestamp ON document_access_logs(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_document_access_logs_access_type ON document_access_logs(access_type);
CREATE INDEX IF NOT EXISTS idx_document_access_logs_composite ON document_access_logs(document_id, user_id, timestamp);

-- Document analytics summary table (for caching computed analytics)
CREATE TABLE IF NOT EXISTS document_analytics_cache (
    document_id UUID PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
    analytics_data JSONB NOT NULL,
    last_updated TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    cache_version INTEGER NOT NULL DEFAULT 1
);

-- Index for cache table
CREATE INDEX IF NOT EXISTS idx_document_analytics_cache_updated ON document_analytics_cache(last_updated DESC);

-- User analytics summary table (for caching user-level analytics)
CREATE TABLE IF NOT EXISTS user_analytics_cache (
    user_id UUID PRIMARY KEY,
    analytics_data JSONB NOT NULL,
    last_updated TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    cache_version INTEGER NOT NULL DEFAULT 1
);

-- Index for user analytics cache
CREATE INDEX IF NOT EXISTS idx_user_analytics_cache_updated ON user_analytics_cache(last_updated DESC);

-- Function to automatically update cache timestamps
CREATE OR REPLACE FUNCTION update_analytics_cache_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.last_updated = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Triggers to update cache timestamps
DROP TRIGGER IF EXISTS trigger_update_document_analytics_cache ON document_analytics_cache;
CREATE TRIGGER trigger_update_document_analytics_cache
    BEFORE UPDATE ON document_analytics_cache
    FOR EACH ROW
    EXECUTE FUNCTION update_analytics_cache_timestamp();

DROP TRIGGER IF EXISTS trigger_update_user_analytics_cache ON user_analytics_cache;
CREATE TRIGGER trigger_update_user_analytics_cache
    BEFORE UPDATE ON user_analytics_cache
    FOR EACH ROW
    EXECUTE FUNCTION update_analytics_cache_timestamp();

-- View for quick access to document statistics
CREATE OR REPLACE VIEW document_stats_view AS
SELECT 
    d.id,
    d.title,
    d.user_id,
    d.status,
    d.page_count,
    d.chunk_count,
    d.file_size,
    d.upload_timestamp,
    COALESCE(access_stats.total_accesses, 0) as total_accesses,
    COALESCE(access_stats.unique_users, 0) as unique_users,
    access_stats.last_access,
    CASE 
        WHEN d.processing_completed_at IS NOT NULL 
        THEN EXTRACT(EPOCH FROM (d.processing_completed_at - d.upload_timestamp)) / 60
        ELSE NULL 
    END as processing_time_minutes
FROM documents d
LEFT JOIN (
    SELECT 
        document_id,
        COUNT(*) as total_accesses,
        COUNT(DISTINCT user_id) as unique_users,
        MAX(timestamp) as last_access
    FROM document_access_logs
    GROUP BY document_id
) access_stats ON d.id = access_stats.document_id;

-- View for user activity summary
CREATE OR REPLACE VIEW user_activity_summary AS
SELECT 
    user_id,
    COUNT(DISTINCT document_id) as documents_accessed,
    COUNT(*) as total_accesses,
    COUNT(CASE WHEN access_type = 'view' THEN 1 END) as views,
    COUNT(CASE WHEN access_type = 'search' THEN 1 END) as searches,
    COUNT(CASE WHEN access_type = 'chat' THEN 1 END) as chat_interactions,
    COUNT(CASE WHEN access_type = 'download' THEN 1 END) as downloads,
    MIN(timestamp) as first_access,
    MAX(timestamp) as last_access
FROM document_access_logs
GROUP BY user_id;

-- Insert some sample data for testing (optional)
-- This would be removed in production
/*
INSERT INTO document_access_logs (document_id, user_id, access_type, timestamp, metadata)
SELECT 
    d.id,
    d.user_id,
    'view',
    d.upload_timestamp + INTERVAL '1 hour',
    '{"source": "test_data"}'
FROM documents d
WHERE d.status = 'completed'
LIMIT 10;
*/