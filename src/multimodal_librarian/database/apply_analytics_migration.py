#!/usr/bin/env python3
"""
Apply Analytics Migration

This script applies the analytics database migration to add tables for
document access tracking and analytics caching.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# Add the src directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    from multimodal_librarian.config.config import get_settings
except ImportError:
    # Fallback configuration
    class Settings:
        @property
        def postgres_url(self):
            return os.getenv(
                'DATABASE_URL', 
                'postgresql://postgres:password@localhost:5432/librarian'
            )
    
    def get_settings():
        return Settings()

logger = logging.getLogger(__name__)


async def apply_analytics_migration():
    """Apply the analytics migration to the database."""
    try:
        settings = get_settings()
        
        # Create async engine
        engine = create_async_engine(
            settings.postgres_url.replace('postgresql://', 'postgresql+asyncpg://'),
            echo=True,
            future=True
        )
        
        # Read migration SQL
        migration_file = Path(__file__).parent / "analytics_migration.sql"
        
        if not migration_file.exists():
            raise FileNotFoundError(f"Migration file not found: {migration_file}")
        
        migration_sql = migration_file.read_text()
        
        # Apply migration
        async with engine.begin() as conn:
            logger.info("Applying analytics migration...")
            
            # Split SQL into individual statements
            statements = [stmt.strip() for stmt in migration_sql.split(';') if stmt.strip()]
            
            for statement in statements:
                if statement:
                    logger.info(f"Executing: {statement[:100]}...")
                    await conn.execute(text(statement))
            
            logger.info("Analytics migration applied successfully")
        
        await engine.dispose()
        
    except Exception as e:
        logger.error(f"Failed to apply analytics migration: {e}")
        raise


async def verify_migration():
    """Verify that the migration was applied correctly."""
    try:
        settings = get_settings()
        
        engine = create_async_engine(
            settings.postgres_url.replace('postgresql://', 'postgresql+asyncpg://'),
            echo=False,
            future=True
        )
        
        async with engine.begin() as conn:
            # Check if tables exist
            tables_to_check = [
                'document_access_logs',
                'document_analytics_cache',
                'user_analytics_cache'
            ]
            
            for table_name in tables_to_check:
                result = await conn.execute(text(f"""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = '{table_name}'
                    );
                """))
                
                exists = result.fetchone()[0]
                if exists:
                    logger.info(f"✓ Table {table_name} exists")
                else:
                    logger.error(f"✗ Table {table_name} does not exist")
                    return False
            
            # Check if views exist
            views_to_check = [
                'document_stats_view',
                'user_activity_summary'
            ]
            
            for view_name in views_to_check:
                result = await conn.execute(text(f"""
                    SELECT EXISTS (
                        SELECT FROM information_schema.views 
                        WHERE table_name = '{view_name}'
                    );
                """))
                
                exists = result.fetchone()[0]
                if exists:
                    logger.info(f"✓ View {view_name} exists")
                else:
                    logger.error(f"✗ View {view_name} does not exist")
                    return False
            
            logger.info("All analytics tables and views verified successfully")
            return True
        
        await engine.dispose()
        
    except Exception as e:
        logger.error(f"Failed to verify migration: {e}")
        return False


async def main():
    """Main function to apply and verify the analytics migration."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    try:
        logger.info("Starting analytics migration...")
        
        # Apply migration
        await apply_analytics_migration()
        
        # Verify migration
        success = await verify_migration()
        
        if success:
            logger.info("Analytics migration completed successfully!")
        else:
            logger.error("Analytics migration verification failed!")
            return 1
        
        return 0
        
    except Exception as e:
        logger.error(f"Analytics migration failed: {e}")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(asyncio.run(main()))