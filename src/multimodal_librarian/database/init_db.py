"""
Database initialization script for the Multimodal Librarian system.

This script sets up the database, creates tables, and runs initial migrations.
"""

import os
import sys
from pathlib import Path
import structlog

# Add the src directory to the Python path
current_dir = Path(__file__).parent
src_dir = current_dir.parent.parent
sys.path.insert(0, str(src_dir))

from multimodal_librarian.database.connection import DatabaseManager, init_database, create_tables
from multimodal_librarian.database.migrations import create_initial_migration, upgrade_to_latest

logger = structlog.get_logger(__name__)


def initialize_database(database_url: str = None, create_migration: bool = True) -> None:
    """Initialize the database with tables and migrations."""
    try:
        # Initialize database connection
        if database_url:
            db_manager = DatabaseManager(database_url)
            db_manager.initialize()
        else:
            init_database()
        
        logger.info("Database connection initialized")
        
        # Create tables directly (for development)
        create_tables()
        logger.info("Database tables created")
        
        # Create initial migration if requested
        if create_migration:
            try:
                create_initial_migration(database_url or DatabaseManager()._get_database_url())
                logger.info("Initial migration created")
            except Exception as e:
                logger.warning("Migration creation failed (may already exist)", error=str(e))
        
        logger.info("Database initialization completed successfully")
        
    except Exception as e:
        logger.error("Database initialization failed", error=str(e))
        raise


def reset_database(database_url: str = None) -> None:
    """Reset the database by dropping and recreating all tables."""
    try:
        if database_url:
            db_manager = DatabaseManager(database_url)
            db_manager.initialize()
        else:
            init_database()
            db_manager = DatabaseManager()
        
        logger.warning("Dropping all database tables")
        db_manager.drop_all_tables()
        
        logger.info("Recreating database tables")
        db_manager.create_all_tables()
        
        logger.info("Database reset completed successfully")
        
    except Exception as e:
        logger.error("Database reset failed", error=str(e))
        raise


def check_database_health(database_url: str = None) -> dict:
    """Check database connection and table status."""
    try:
        if database_url:
            db_manager = DatabaseManager(database_url)
            db_manager.initialize()
        else:
            init_database()
            db_manager = DatabaseManager()
        
        # Test connection
        with db_manager.get_session() as session:
            result = session.execute("SELECT 1")
            connection_ok = result.scalar() == 1
        
        # Check if tables exist
        from multimodal_librarian.database.models import Base
        inspector = db_manager.engine.dialect.get_table_names(db_manager.engine.connect())
        expected_tables = [table.name for table in Base.metadata.tables.values()]
        existing_tables = [name for name in expected_tables if name in inspector]
        
        health_status = {
            'connection_ok': connection_ok,
            'expected_tables': len(expected_tables),
            'existing_tables': len(existing_tables),
            'tables_missing': len(expected_tables) - len(existing_tables),
            'all_tables_exist': len(existing_tables) == len(expected_tables)
        }
        
        logger.info("Database health check completed", **health_status)
        return health_status
        
    except Exception as e:
        logger.error("Database health check failed", error=str(e))
        return {
            'connection_ok': False,
            'error': str(e)
        }


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Initialize Multimodal Librarian database")
    parser.add_argument("--database-url", help="Database URL (optional)")
    parser.add_argument("--reset", action="store_true", help="Reset database (drop and recreate tables)")
    parser.add_argument("--check", action="store_true", help="Check database health")
    parser.add_argument("--no-migration", action="store_true", help="Skip migration creation")
    
    args = parser.parse_args()
    
    if args.check:
        health = check_database_health(args.database_url)
        if health.get('connection_ok'):
            print("✅ Database connection: OK")
            if health.get('all_tables_exist'):
                print("✅ All tables exist")
            else:
                print(f"⚠️  Missing {health.get('tables_missing', 0)} tables")
        else:
            print("❌ Database connection: FAILED")
            if 'error' in health:
                print(f"Error: {health['error']}")
    elif args.reset:
        reset_database(args.database_url)
        print("✅ Database reset completed")
    else:
        initialize_database(args.database_url, not args.no_migration)
        print("✅ Database initialization completed")