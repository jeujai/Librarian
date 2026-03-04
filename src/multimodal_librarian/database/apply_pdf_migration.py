#!/usr/bin/env python3
"""
Apply PDF upload database migration.

This script applies the database schema changes needed for PDF upload functionality.
"""

import os
import sys
from pathlib import Path
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
import structlog

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from multimodal_librarian.database.connection import db_manager

logger = structlog.get_logger(__name__)


def apply_pdf_migration():
    """Apply the PDF upload database migration."""
    try:
        # Get database URL
        database_url = db_manager._get_database_url()
        
        # Parse the database URL to get connection parameters
        from urllib.parse import urlparse
        parsed = urlparse(database_url)
        
        # Connect to database
        conn = psycopg2.connect(
            host=parsed.hostname,
            port=parsed.port or 5432,
            database=parsed.path[1:],  # Remove leading slash
            user=parsed.username,
            password=parsed.password
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        
        # Read migration SQL
        migration_file = Path(__file__).parent / "pdf_upload_migration.sql"
        with open(migration_file, 'r') as f:
            migration_sql = f.read()
        
        # Execute migration
        cursor = conn.cursor()
        cursor.execute(migration_sql)
        
        logger.info("PDF upload migration applied successfully")
        
        # Verify tables were created
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN ('documents', 'document_chunks')
        """)
        
        tables = cursor.fetchall()
        logger.info("Created tables", tables=[table[0] for table in tables])
        
        cursor.close()
        conn.close()
        
        return True
        
    except Exception as e:
        logger.error("Failed to apply PDF migration", error=str(e))
        return False


def test_migration():
    """Test that the migration was applied correctly."""
    try:
        database_url = db_manager._get_database_url()
        from urllib.parse import urlparse
        parsed = urlparse(database_url)
        
        conn = psycopg2.connect(
            host=parsed.hostname,
            port=parsed.port or 5432,
            database=parsed.path[1:],
            user=parsed.username,
            password=parsed.password
        )
        
        cursor = conn.cursor()
        
        # Test documents table
        cursor.execute("""
            INSERT INTO documents (user_id, title, filename, file_size, mime_type, s3_key)
            VALUES ('test-user-id', 'Test Document', 'test.pdf', 1024, 'application/pdf', 'test-key')
            RETURNING id
        """)
        
        doc_id = cursor.fetchone()[0]
        logger.info("Test document created", document_id=doc_id)
        
        # Test document_chunks table
        cursor.execute("""
            INSERT INTO document_chunks (document_id, chunk_index, content)
            VALUES (%s, 0, 'Test chunk content')
            RETURNING id
        """, (doc_id,))
        
        chunk_id = cursor.fetchone()[0]
        logger.info("Test chunk created", chunk_id=chunk_id)
        
        # Clean up test data
        cursor.execute("DELETE FROM document_chunks WHERE id = %s", (chunk_id,))
        cursor.execute("DELETE FROM documents WHERE id = %s", (doc_id,))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        logger.info("Migration test completed successfully")
        return True
        
    except Exception as e:
        logger.error("Migration test failed", error=str(e))
        return False


if __name__ == "__main__":
    # Configure logging
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    print("Applying PDF upload database migration...")
    
    if apply_pdf_migration():
        print("Migration applied successfully!")
        
        print("Testing migration...")
        if test_migration():
            print("Migration test passed!")
        else:
            print("Migration test failed!")
            sys.exit(1)
    else:
        print("Migration failed!")
        sys.exit(1)