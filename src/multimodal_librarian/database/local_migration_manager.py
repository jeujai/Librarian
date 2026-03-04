"""
Local Migration Manager for porting existing migrations to local PostgreSQL setup.

This module provides utilities for managing database migrations in the local development
environment, ensuring compatibility with existing AWS-focused migrations.
"""

import asyncio
import hashlib
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import structlog
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from .connection import db_manager, get_async_session
from .migrations import MigrationManager

logger = structlog.get_logger(__name__)


class LocalMigrationManager:
    """Manages migration porting for local development environment."""
    
    def __init__(self, database_url: Optional[str] = None):
        """Initialize local migration manager."""
        self.database_url = database_url or db_manager._get_database_url()
        self.migration_manager = MigrationManager(self.database_url)
        self.migrations_dir = Path(__file__).parent / "migrations"
        self.local_init_dir = Path(__file__).parent.parent.parent.parent / "database" / "postgresql" / "init"
    
    async def port_existing_migrations(self) -> bool:
        """Port all existing migrations to local setup."""
        try:
            logger.info("Starting migration porting process...")
            
            # Check if porting is needed
            if await self._is_porting_complete():
                logger.info("Migration porting already completed")
                return True
            
            # Execute the main porting script
            success = await self._execute_porting_script()
            if not success:
                logger.error("Failed to execute porting script")
                return False
            
            # Port individual migration files
            success = await self._port_individual_migrations()
            if not success:
                logger.error("Failed to port individual migrations")
                return False
            
            # Verify porting results
            success = await self._verify_porting()
            if not success:
                logger.error("Migration porting verification failed")
                return False
            
            logger.info("Migration porting completed successfully")
            return True
            
        except Exception as e:
            logger.error("Migration porting failed", error=str(e))
            return False
    
    async def _is_porting_complete(self) -> bool:
        """Check if migration porting has already been completed."""
        try:
            async with get_async_session() as session:
                result = await session.execute(text("""
                    SELECT is_migration_applied('existing_migrations_port')
                """))
                return result.scalar() or False
        except Exception as e:
            logger.debug("Could not check porting status", error=str(e))
            return False
    
    async def _execute_porting_script(self) -> bool:
        """Execute the main migration porting SQL script."""
        try:
            porting_script = self.local_init_dir / "08_existing_migrations_port.sql"
            
            if not porting_script.exists():
                logger.error("Porting script not found", path=str(porting_script))
                return False
            
            # Read and execute the porting script
            with open(porting_script, 'r') as f:
                script_content = f.read()
            
            async with get_async_session() as session:
                # Execute the script in chunks (PostgreSQL doesn't support multiple statements in one execute)
                statements = self._split_sql_statements(script_content)
                
                for statement in statements:
                    if statement.strip():
                        await session.execute(text(statement))
                
                await session.commit()
            
            logger.info("Migration porting script executed successfully")
            return True
            
        except Exception as e:
            logger.error("Failed to execute porting script", error=str(e))
            return False
    
    async def _port_individual_migrations(self) -> bool:
        """Port individual migration files to local format."""
        try:
            migration_files = [
                "add_authentication_tables.py",
                "add_chat_messages.py", 
                "add_documents_table.py"
            ]
            
            for migration_file in migration_files:
                success = await self._port_migration_file(migration_file)
                if not success:
                    logger.error("Failed to port migration file", file=migration_file)
                    return False
            
            logger.info("Individual migrations ported successfully")
            return True
            
        except Exception as e:
            logger.error("Failed to port individual migrations", error=str(e))
            return False
    
    async def _port_migration_file(self, migration_file: str) -> bool:
        """Port a specific migration file to local format."""
        try:
            source_path = self.migrations_dir / migration_file
            
            if not source_path.exists():
                logger.warning("Migration file not found", file=migration_file)
                return True  # Skip missing files
            
            # Create local version of the migration
            local_migration_name = f"local_{migration_file.replace('.py', '')}"
            
            # Check if already ported
            if await self._is_migration_applied(local_migration_name):
                logger.debug("Migration already ported", migration=local_migration_name)
                return True
            
            # Execute the migration logic adapted for local environment
            success = await self._execute_local_migration(migration_file, local_migration_name)
            
            if success:
                await self._record_migration(local_migration_name)
                logger.info("Migration ported successfully", migration=local_migration_name)
            
            return success
            
        except Exception as e:
            logger.error("Failed to port migration file", file=migration_file, error=str(e))
            return False
    
    async def _execute_local_migration(self, original_file: str, local_name: str) -> bool:
        """Execute migration logic adapted for local environment."""
        try:
            async with get_async_session() as session:
                if original_file == "add_authentication_tables.py":
                    # Authentication tables are handled by the main porting script
                    return True
                
                elif original_file == "add_chat_messages.py":
                    # Ensure chat_messages table exists with proper structure
                    await session.execute(text("""
                        CREATE TABLE IF NOT EXISTS multimodal_librarian.chat_messages_local (
                            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                            user_id VARCHAR(100) NOT NULL,
                            content TEXT NOT NULL,
                            message_type VARCHAR(20) NOT NULL DEFAULT 'user',
                            timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
                            sources TEXT[] DEFAULT '{}',
                            message_metadata JSONB DEFAULT '{}',
                            
                            CONSTRAINT check_local_chat_message_type CHECK (message_type IN ('user', 'assistant', 'system'))
                        );
                    """))
                    
                elif original_file == "add_documents_table.py":
                    # Documents tables are handled by the main porting script
                    return True
                
                await session.commit()
                return True
                
        except Exception as e:
            logger.error("Failed to execute local migration", migration=local_name, error=str(e))
            return False
    
    async def _verify_porting(self) -> bool:
        """Verify that migration porting was successful."""
        try:
            async with get_async_session() as session:
                # Check that key tables exist
                tables_to_check = [
                    'multimodal_librarian.users',
                    'multimodal_librarian.knowledge_sources', 
                    'multimodal_librarian.chat_messages',
                    'multimodal_librarian.knowledge_chunks',
                    'multimodal_librarian.api_keys',
                    'multimodal_librarian.audit_logs'
                ]
                
                for table_name in tables_to_check:
                    result = await session.execute(text(f"""
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables 
                            WHERE table_schema = 'multimodal_librarian' 
                            AND table_name = '{table_name.split('.')[1]}'
                        );
                    """))
                    
                    if not result.scalar():
                        logger.error("Required table missing after porting", table=table_name)
                        return False
                
                # Check migration tracking
                result = await session.execute(text("""
                    SELECT COUNT(*) FROM public.migration_history 
                    WHERE migration_name LIKE '%_port' AND success = true
                """))
                
                ported_count = result.scalar()
                if ported_count < 4:  # Expect at least 4 ported migrations
                    logger.error("Insufficient ported migrations", count=ported_count)
                    return False
                
                logger.info("Migration porting verification successful", ported_migrations=ported_count)
                return True
                
        except Exception as e:
            logger.error("Migration porting verification failed", error=str(e))
            return False
    
    async def _is_migration_applied(self, migration_name: str) -> bool:
        """Check if a migration has been applied."""
        try:
            async with get_async_session() as session:
                result = await session.execute(text("""
                    SELECT is_migration_applied(:migration_name)
                """), {"migration_name": migration_name})
                return result.scalar() or False
        except Exception:
            return False
    
    async def _record_migration(self, migration_name: str) -> None:
        """Record a migration as applied."""
        try:
            async with get_async_session() as session:
                await session.execute(text("""
                    SELECT record_migration(:migration_name, 'local_port', true)
                """), {"migration_name": migration_name})
                await session.commit()
        except Exception as e:
            logger.error("Failed to record migration", migration=migration_name, error=str(e))
    
    def _split_sql_statements(self, sql_content: str) -> List[str]:
        """Split SQL content into individual statements."""
        # Simple statement splitting - handles most cases
        statements = []
        current_statement = []
        in_function = False
        in_do_block = False
        
        lines = sql_content.split('\n')
        
        for line in lines:
            stripped = line.strip()
            
            # Skip comments and empty lines
            if not stripped or stripped.startswith('--'):
                continue
            
            # Track function and DO block boundaries
            if stripped.upper().startswith('CREATE OR REPLACE FUNCTION') or stripped.upper().startswith('CREATE FUNCTION'):
                in_function = True
            elif stripped.upper().startswith('DO $'):
                in_do_block = True
            elif in_function and stripped.endswith('$ LANGUAGE plpgsql;'):
                in_function = False
                current_statement.append(line)
                statements.append('\n'.join(current_statement))
                current_statement = []
                continue
            elif in_do_block and stripped.endswith('$ language \'plpgsql\';'):
                in_do_block = False
                current_statement.append(line)
                statements.append('\n'.join(current_statement))
                current_statement = []
                continue
            elif in_do_block and stripped == 'END $;':
                in_do_block = False
                current_statement.append(line)
                statements.append('\n'.join(current_statement))
                current_statement = []
                continue
            
            current_statement.append(line)
            
            # End of statement (not in function or DO block)
            if not in_function and not in_do_block and stripped.endswith(';'):
                statements.append('\n'.join(current_statement))
                current_statement = []
        
        # Add any remaining statement
        if current_statement:
            statements.append('\n'.join(current_statement))
        
        return statements
    
    async def get_migration_status(self) -> Dict[str, any]:
        """Get comprehensive migration status."""
        try:
            async with get_async_session() as session:
                # Get porting status
                result = await session.execute(text("""
                    SELECT is_migration_applied('existing_migrations_port')
                """))
                porting_complete = result.scalar() or False
                
                # Get migration history
                result = await session.execute(text("""
                    SELECT migration_name, applied_at, success 
                    FROM public.migration_history 
                    ORDER BY applied_at DESC
                """))
                migration_history = [
                    {
                        "name": row[0],
                        "applied_at": row[1].isoformat() if row[1] else None,
                        "success": row[2]
                    }
                    for row in result.fetchall()
                ]
                
                # Get table counts
                result = await session.execute(text("""
                    SELECT 
                        (SELECT COUNT(*) FROM multimodal_librarian.users) as users,
                        (SELECT COUNT(*) FROM multimodal_librarian.knowledge_sources) as knowledge_sources,
                        (SELECT COUNT(*) FROM multimodal_librarian.knowledge_chunks) as chunks,
                        (SELECT COUNT(*) FROM multimodal_librarian.chat_messages) as messages
                """))
                row = result.fetchone()
                table_counts = {
                    "users": row[0],
                    "knowledge_sources": row[1], 
                    "knowledge_chunks": row[2],
                    "chat_messages": row[3]
                }
                
                return {
                    "porting_complete": porting_complete,
                    "migration_history": migration_history,
                    "table_counts": table_counts,
                    "database_url": self.database_url.replace(self.database_url.split('@')[0].split('://')[-1], '***') if '@' in self.database_url else self.database_url
                }
                
        except Exception as e:
            logger.error("Failed to get migration status", error=str(e))
            return {
                "porting_complete": False,
                "error": str(e)
            }
    
    async def reset_migrations(self) -> bool:
        """Reset migration state (for development/testing)."""
        try:
            logger.warning("Resetting migration state - this will clear migration history")
            
            async with get_async_session() as session:
                # Clear migration history
                await session.execute(text("DELETE FROM public.migration_history"))
                await session.execute(text("DELETE FROM public.alembic_version"))
                
                await session.commit()
            
            logger.info("Migration state reset successfully")
            return True
            
        except Exception as e:
            logger.error("Failed to reset migration state", error=str(e))
            return False


async def port_migrations_to_local() -> bool:
    """Main function to port existing migrations to local setup."""
    manager = LocalMigrationManager()
    return await manager.port_existing_migrations()


async def get_local_migration_status() -> Dict[str, any]:
    """Get status of local migration porting."""
    manager = LocalMigrationManager()
    return await manager.get_migration_status()


if __name__ == "__main__":
    # Run migration porting when executed directly
    async def main():
        success = await port_migrations_to_local()
        if success:
            print("✓ Migration porting completed successfully")
            
            # Show status
            status = await get_local_migration_status()
            print(f"✓ Porting complete: {status['porting_complete']}")
            print(f"✓ Applied migrations: {len(status.get('migration_history', []))}")
            print(f"✓ Table counts: {status.get('table_counts', {})}")
        else:
            print("✗ Migration porting failed")
            return 1
        
        return 0
    
    import sys
    exit_code = asyncio.run(main())
    sys.exit(exit_code)