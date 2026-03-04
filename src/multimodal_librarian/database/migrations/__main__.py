#!/usr/bin/env python3
"""
Database Migrations CLI

This module provides a command-line interface for running database migrations
in the local development environment.
"""

import asyncio
import os
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from multimodal_librarian.config.config_factory import get_database_config
from multimodal_librarian.database.migrations import (
    MigrationManager,
    upgrade_to_latest,
    check_database_status,
    create_initial_migration
)
import structlog

logger = structlog.get_logger(__name__)


def main():
    """Main CLI function for database migrations."""
    print("🔄 Running database migrations for local environment...")
    
    # Ensure we're in local environment
    os.environ["ML_ENVIRONMENT"] = "local"
    
    try:
        # Get configuration
        config = get_database_config()
        
        if not hasattr(config, 'postgres_connection_string'):
            print("❌ PostgreSQL configuration not found")
            sys.exit(1)
        
        database_url = config.postgres_connection_string
        print(f"📋 Using database: {database_url.split('@')[1] if '@' in database_url else 'local'}")
        
        # Check current migration status
        print("📊 Checking migration status...")
        status = check_database_status(database_url)
        
        print(f"   Current revision: {status['current_revision']}")
        print(f"   Head revision: {status['head_revision']}")
        print(f"   Up to date: {status['is_up_to_date']}")
        
        if status['pending_migrations']:
            print("⏳ Applying pending migrations...")
            upgrade_to_latest(database_url)
            print("✅ Database migrations completed successfully!")
        else:
            print("✅ Database is already up to date!")
        
        # Final status check
        final_status = check_database_status(database_url)
        print(f"📋 Final status: {final_status['current_revision']}")
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        logger.error("Migration failed", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()