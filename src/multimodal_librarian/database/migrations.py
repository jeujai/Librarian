"""
Database migration management using Alembic.

This module provides utilities for managing database schema migrations
and version control for the Multimodal Librarian system.
"""

import os
from pathlib import Path
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine
import structlog

logger = structlog.get_logger(__name__)


class MigrationManager:
    """Manages database migrations using Alembic."""
    
    def __init__(self, database_url: str, migrations_dir: str = None):
        """Initialize migration manager."""
        self.database_url = database_url
        self.migrations_dir = migrations_dir or self._get_migrations_dir()
        self.alembic_cfg = self._create_alembic_config()
    
    def _get_migrations_dir(self) -> str:
        """Get the migrations directory path."""
        current_dir = Path(__file__).parent
        migrations_dir = current_dir / "migrations"
        migrations_dir.mkdir(exist_ok=True)
        return str(migrations_dir)
    
    def _create_alembic_config(self) -> Config:
        """Create Alembic configuration."""
        alembic_cfg = Config()
        alembic_cfg.set_main_option("script_location", self.migrations_dir)
        alembic_cfg.set_main_option("sqlalchemy.url", self.database_url)
        
        # Set up logging
        alembic_cfg.set_main_option("logger.keys", "root,sqlalchemy,alembic")
        alembic_cfg.set_main_option("logger.level", "INFO")
        
        return alembic_cfg
    
    def init_migrations(self) -> None:
        """Initialize Alembic migrations directory."""
        try:
            if not os.path.exists(os.path.join(self.migrations_dir, "alembic.ini")):
                command.init(self.alembic_cfg, self.migrations_dir)
                logger.info("Initialized Alembic migrations", directory=self.migrations_dir)
            else:
                logger.info("Alembic migrations already initialized")
        except Exception as e:
            logger.error("Failed to initialize migrations", error=str(e))
            raise
    
    def create_migration(self, message: str, autogenerate: bool = True) -> str:
        """Create a new migration script."""
        try:
            revision = command.revision(
                self.alembic_cfg,
                message=message,
                autogenerate=autogenerate
            )
            logger.info("Created migration", message=message, revision=revision.revision)
            return revision.revision
        except Exception as e:
            logger.error("Failed to create migration", error=str(e), message=message)
            raise
    
    def upgrade_database(self, revision: str = "head") -> None:
        """Upgrade database to specified revision."""
        try:
            command.upgrade(self.alembic_cfg, revision)
            logger.info("Database upgraded", revision=revision)
        except Exception as e:
            logger.error("Failed to upgrade database", error=str(e), revision=revision)
            raise
    
    def downgrade_database(self, revision: str) -> None:
        """Downgrade database to specified revision."""
        try:
            command.downgrade(self.alembic_cfg, revision)
            logger.info("Database downgraded", revision=revision)
        except Exception as e:
            logger.error("Failed to downgrade database", error=str(e), revision=revision)
            raise
    
    def get_current_revision(self) -> str:
        """Get current database revision."""
        try:
            engine = create_engine(self.database_url)
            with engine.connect() as connection:
                context = MigrationContext.configure(connection)
                current_rev = context.get_current_revision()
                return current_rev or "None"
        except Exception as e:
            logger.error("Failed to get current revision", error=str(e))
            raise
    
    def get_migration_history(self) -> list:
        """Get migration history."""
        try:
            script = ScriptDirectory.from_config(self.alembic_cfg)
            revisions = []
            
            for revision in script.walk_revisions():
                revisions.append({
                    'revision': revision.revision,
                    'down_revision': revision.down_revision,
                    'message': revision.doc,
                    'branch_labels': revision.branch_labels,
                })
            
            return revisions
        except Exception as e:
            logger.error("Failed to get migration history", error=str(e))
            raise
    
    def check_migration_status(self) -> dict:
        """Check current migration status."""
        try:
            current_rev = self.get_current_revision()
            script = ScriptDirectory.from_config(self.alembic_cfg)
            head_rev = script.get_current_head()
            
            return {
                'current_revision': current_rev,
                'head_revision': head_rev,
                'is_up_to_date': current_rev == head_rev,
                'pending_migrations': current_rev != head_rev
            }
        except Exception as e:
            logger.error("Failed to check migration status", error=str(e))
            raise


def create_initial_migration(database_url: str) -> None:
    """Create initial migration for all tables."""
    migration_manager = MigrationManager(database_url)
    
    # Initialize migrations if not already done
    migration_manager.init_migrations()
    
    # Create initial migration
    migration_manager.create_migration("Initial migration with all tables")
    
    logger.info("Initial migration created successfully")


def upgrade_to_latest(database_url: str) -> None:
    """Upgrade database to latest migration."""
    migration_manager = MigrationManager(database_url)
    migration_manager.upgrade_database()
    
    logger.info("Database upgraded to latest version")


def check_database_status(database_url: str) -> dict:
    """Check database migration status."""
    migration_manager = MigrationManager(database_url)
    return migration_manager.check_migration_status()