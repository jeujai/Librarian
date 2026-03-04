-- PDF Upload Implementation Database Schema Migration
-- This script adds the necessary tables for PDF upload functionality

-- Documents table for PDF upload functionality
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    filename VARCHAR(255) NOT NULL,
    file_size BIGINT NOT NULL,
    mime_type VARCHAR(100) NOT NULL,
    s3_key VARCHAR(500) NOT NULL UNIQUE,
    status VARCHAR(50) NOT NULL DEFAULT 'uploaded',
    processing_error TEXT,
    upload_timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    processing_started_at TIMESTAMP WITH TIME ZONE,
    processing_completed_at TIMESTAMP WITH TIME ZONE,
    page_count INTEGER,
    chunk_count INTEGER,
    metadata JSONB DEFAULT '{}',
    
    CONSTRAINT valid_status CHECK (status IN ('uploaded', 'processing', 'completed', 'failed')),
    CONSTRAINT positive_file_size CHECK (file_size > 0),
    CONSTRAINT positive_page_count CHECK (page_count IS NULL OR page_count > 0),
    CONSTRAINT positive_chunk_count CHECK (chunk_count IS NULL OR chunk_count >= 0)
);

-- Document chunks table for processed PDF content
CREATE TABLE IF NOT EXISTS document_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    page_number INTEGER,
    section_title VARCHAR(255),
    chunk_type VARCHAR(50) NOT NULL DEFAULT 'text',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    
    CONSTRAINT valid_chunk_type CHECK (chunk_type IN ('text', 'image', 'table', 'chart')),
    CONSTRAINT positive_chunk_index CHECK (chunk_index >= 0),
    CONSTRAINT positive_page_number CHECK (page_number IS NULL OR page_number > 0),
    UNIQUE(document_id, chunk_index)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_documents_user_id ON documents(user_id);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
CREATE INDEX IF NOT EXISTS idx_documents_upload_timestamp ON documents(upload_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_documents_s3_key ON documents(s3_key);

CREATE INDEX IF NOT EXISTS idx_document_chunks_document_id ON document_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_document_chunks_type ON document_chunks(chunk_type);
CREATE INDEX IF NOT EXISTS idx_document_chunks_page ON document_chunks(page_number);
CREATE INDEX IF NOT EXISTS idx_document_chunks_created_at ON document_chunks(created_at);

-- Full-text search indexes
CREATE INDEX IF NOT EXISTS idx_documents_title_fts ON documents USING gin(to_tsvector('english', title));
CREATE INDEX IF NOT EXISTS idx_document_chunks_content_fts ON document_chunks USING gin(to_tsvector('english', content));

-- Trigger for updated_at on documents (reuse existing function)
CREATE TRIGGER update_documents_updated_at BEFORE UPDATE ON documents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

COMMIT;