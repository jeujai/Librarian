"""
Database migration to add documents and document_chunks tables for Task 3.

This migration creates the necessary tables for document upload and management
functionality as part of the chat and document integration implementation.
"""

import asyncio
import logging
from datetime import datetime
from sqlalchemy import text
from ..connection import get_database_connection

logger = logging.getLogger(__name__)

# SQL for creating documents table
CREATE_DOCUMENTS_TABLE = """
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
    doc_metadata JSONB DEFAULT '{}',
    
    CONSTRAINT check_document_status CHECK (status IN ('uploaded', 'processing', 'completed', 'failed')),
    CONSTRAINT check_positive_file_size CHECK (file_size > 0),
    CONSTRAINT check_positive_page_count CHECK (page_count IS NULL OR page_count > 0),
    CONSTRAINT check_positive_chunk_count CHECK (chunk_count IS NULL OR chunk_count >= 0)
);
"""

# SQL for creating document_chunks table
CREATE_DOCUMENT_CHUNKS_TABLE = """
CREATE TABLE IF NOT EXISTS document_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    page_number INTEGER,
    section_title VARCHAR(255),
    chunk_type VARCHAR(50) NOT NULL DEFAULT 'text',
    chunk_metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    
    CONSTRAINT uq_document_chunk_index UNIQUE(document_id, chunk_index),
    CONSTRAINT check_chunk_type CHECK (chunk_type IN ('text', 'image', 'table', 'chart')),
    CONSTRAINT check_positive_chunk_index CHECK (chunk_index >= 0),
    CONSTRAINT check_positive_page_number CHECK (page_number IS NULL OR page_number > 0)
);
"""

# SQL for creating indexes
CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_documents_user_id ON documents(user_id);",
    "CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);",
    "CREATE INDEX IF NOT EXISTS idx_documents_upload_timestamp ON documents(upload_timestamp);",
    "CREATE INDEX IF NOT EXISTS idx_documents_s3_key ON documents(s3_key);",
    "CREATE INDEX IF NOT EXISTS idx_document_chunks_document_id ON document_chunks(document_id);",
    "CREATE INDEX IF NOT EXISTS idx_document_chunks_type ON document_chunks(chunk_type);",
    "CREATE INDEX IF NOT EXISTS idx_document_chunks_page ON document_chunks(page_number);",
    "CREATE INDEX IF NOT EXISTS idx_document_chunks_created_at ON document_chunks(created_at);"
]

# SQL for creating processing_jobs table for background processing
CREATE_PROCESSING_JOBS_TABLE = """
CREATE TABLE IF NOT EXISTS processing_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
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
"""

CREATE_PROCESSING_JOBS_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_processing_jobs_document_id ON processing_jobs(document_id);",
    "CREATE INDEX IF NOT EXISTS idx_processing_jobs_status ON processing_jobs(status);",
    "CREATE INDEX IF NOT EXISTS idx_processing_jobs_task_id ON processing_jobs(task_id);"
]


async def apply_migration():
    """Apply the documents table migration."""
    try:
        logger.info("Starting documents table migration...")
        
        # Get database connection
        db_pool = await get_database_connection()
        
        async with db_pool.acquire() as conn:
            # Create documents table
            logger.info("Creating documents table...")
            await conn.execute(text(CREATE_DOCUMENTS_TABLE))
            
            # Create document_chunks table
            logger.info("Creating document_chunks table...")
            await conn.execute(text(CREATE_DOCUMENT_CHUNKS_TABLE))
            
            # Create processing_jobs table
            logger.info("Creating processing_jobs table...")
            await conn.execute(text(CREATE_PROCESSING_JOBS_TABLE))
            
            # Create indexes
            logger.info("Creating indexes...")
            for index_sql in CREATE_INDEXES + CREATE_PROCESSING_JOBS_INDEXES:
                await conn.execute(text(index_sql))
            
            # Commit transaction
            await conn.execute(text("COMMIT;"))
            
        logger.info("Documents table migration completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return False


async def rollback_migration():
    """Rollback the documents table migration."""
    try:
        logger.info("Rolling back documents table migration...")
        
        # Get database connection
        db_pool = await get_database_connection()
        
        async with db_pool.acquire() as conn:
            # Drop tables in reverse order (due to foreign key constraints)
            await conn.execute(text("DROP TABLE IF EXISTS processing_jobs CASCADE;"))
            await conn.execute(text("DROP TABLE IF EXISTS document_chunks CASCADE;"))
            await conn.execute(text("DROP TABLE IF EXISTS documents CASCADE;"))
            
            # Commit transaction
            await conn.execute(text("COMMIT;"))
            
        logger.info("Documents table migration rollback completed")
        return True
        
    except Exception as e:
        logger.error(f"Migration rollback failed: {e}")
        return False


async def check_migration_status():
    """Check if the migration has been applied."""
    try:
        db_pool = await get_database_connection()
        
        async with db_pool.acquire() as conn:
            # Check if documents table exists
            result = await conn.fetchval(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'documents'
                );
            """))
            
            return bool(result)
            
    except Exception as e:
        logger.error(f"Failed to check migration status: {e}")
        return False


if __name__ == "__main__":
    # Run migration when executed directly
    async def main():
        success = await apply_migration()
        if success:
            print("Migration applied successfully")
        else:
            print("Migration failed")
    
    asyncio.run(main())