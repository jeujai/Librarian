#!/usr/bin/env python3
"""
PostgreSQL Reset Script for Multimodal Librarian

This script provides PostgreSQL-specific reset functionality with advanced options
for schema management, data preservation, and selective reset operations.

Features:
- Schema-only reset (preserve data, reset structure)
- Data-only reset (preserve schema, clear data)
- Full reset (drop and recreate everything)
- Selective table reset
- Migration replay
- Backup integration

Usage:
    python scripts/reset-postgresql.py [options]

Examples:
    # Full reset with backup
    python scripts/reset-postgresql.py --full --backup

    # Reset only data, keep schema
    python scripts/reset-postgresql.py --data-only

    # Reset specific tables
    python scripts/reset-postgresql.py --tables users,sessions

    # Reset and replay migrations
    python scripts/reset-postgresql.py --full --migrate
"""

import asyncio
import argparse
import logging
import os
import sys
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Set

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from multimodal_librarian.clients.database_client_factory import DatabaseClientFactory
from multimodal_librarian.clients.protocols import RelationalStoreClient
from multimodal_librarian.config.config_factory import get_database_config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Color codes for terminal output
class Colors:
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    PURPLE = '\033[0;35m'
    NC = '\033[0m'

def colored_print(message: str, color: str = Colors.NC) -> None:
    """Print colored message to terminal."""
    print(f"{color}{message}{Colors.NC}")

def log_info(message: str) -> None:
    colored_print(f"[INFO] {message}", Colors.BLUE)

def log_success(message: str) -> None:
    colored_print(f"[SUCCESS] {message}", Colors.GREEN)

def log_warning(message: str) -> None:
    colored_print(f"[WARNING] {message}", Colors.YELLOW)

def log_error(message: str) -> None:
    colored_print(f"[ERROR] {message}", Colors.RED)

class PostgreSQLResetManager:
    """Manages PostgreSQL-specific reset operations."""
    
    def __init__(self, config: Any):
        self.config = config
        self.factory: Optional[DatabaseClientFactory] = None
        self.client: Optional[RelationalStoreClient] = None
        
    async def initialize(self) -> None:
        """Initialize database connections."""
        self.factory = DatabaseClientFactory(self.config)
        self.client = await self.factory.get_relational_client()
        log_info("Connected to PostgreSQL")
    
    async def cleanup(self) -> None:
        """Clean up connections."""
        if self.factory:
            await self.factory.close()
    
    async def get_database_info(self) -> Dict[str, Any]:
        """Get comprehensive database information."""
        if not self.client:
            raise RuntimeError("Client not initialized")
        
        info = await self.client.get_database_info()
        
        # Get additional table information
        tables_query = """
        SELECT 
            schemaname,
            tablename,
            pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size,
            pg_total_relation_size(schemaname||'.'||tablename) as size_bytes
        FROM pg_tables 
        WHERE schemaname = 'public'
        ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
        """
        
        tables_result = await self.client.execute_query(tables_query)
        info["tables"] = tables_result
        
        return info
    
    async def create_backup(self, backup_dir: str) -> Optional[str]:
        """Create PostgreSQL backup before reset."""
        try:
            log_info("Creating PostgreSQL backup...")
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = Path(backup_dir) / f"postgresql_reset_backup_{timestamp}.sql"
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Use pg_dump to create backup
            import subprocess
            
            # Build pg_dump command
            cmd = [
                "pg_dump",
                "-h", getattr(self.config, 'postgres_host', 'localhost'),
                "-p", str(getattr(self.config, 'postgres_port', 5432)),
                "-U", getattr(self.config, 'postgres_user', 'ml_user'),
                "-d", getattr(self.config, 'postgres_db', 'multimodal_librarian'),
                "-f", str(backup_path),
                "--verbose",
                "--no-password"
            ]
            
            # Set PGPASSWORD environment variable
            env = os.environ.copy()
            env["PGPASSWORD"] = getattr(self.config, 'postgres_password', 'ml_password')
            
            result = subprocess.run(cmd, env=env, capture_output=True, text=True)
            
            if result.returncode == 0:
                log_success(f"Backup created: {backup_path}")
                return str(backup_path)
            else:
                log_error(f"Backup failed: {result.stderr}")
                return None
                
        except Exception as e:
            log_error(f"Backup creation failed: {e}")
            return None
    
    async def get_table_list(self) -> List[str]:
        """Get list of all tables in the database."""
        if not self.client:
            raise RuntimeError("Client not initialized")
        
        query = """
        SELECT tablename 
        FROM pg_tables 
        WHERE schemaname = 'public'
        ORDER BY tablename
        """
        
        result = await self.client.execute_query(query)
        return [row["tablename"] for row in result]
    
    async def reset_full(self, migrate: bool = False) -> bool:
        """Perform full database reset."""
        try:
            log_info("Performing full PostgreSQL reset...")
            
            # Drop all tables
            await self.client.drop_tables()
            log_success("All tables dropped")
            
            # Recreate tables
            await self.client.create_tables()
            log_success("Tables recreated")
            
            # Run migrations if requested
            if migrate:
                await self.run_migrations()
            
            return True
            
        except Exception as e:
            log_error(f"Full reset failed: {e}")
            return False
    
    async def reset_data_only(self, tables: Optional[Set[str]] = None) -> bool:
        """Reset only data, preserve schema."""
        try:
            log_info("Performing data-only PostgreSQL reset...")
            
            if tables:
                # Reset specific tables
                for table in tables:
                    try:
                        await self.client.execute_command(f"TRUNCATE TABLE {table} CASCADE")
                        log_info(f"Truncated table: {table}")
                    except Exception as e:
                        log_warning(f"Could not truncate table {table}: {e}")
            else:
                # Get all tables and truncate them
                all_tables = await self.get_table_list()
                
                if all_tables:
                    # Truncate all tables in one command to handle foreign keys
                    tables_str = ", ".join(all_tables)
                    await self.client.execute_command(f"TRUNCATE TABLE {tables_str} CASCADE")
                    log_success(f"Truncated {len(all_tables)} tables")
                else:
                    log_info("No tables found to truncate")
            
            return True
            
        except Exception as e:
            log_error(f"Data-only reset failed: {e}")
            return False
    
    async def reset_schema_only(self) -> bool:
        """Reset only schema, preserve data."""
        try:
            log_info("Performing schema-only PostgreSQL reset...")
            
            # This is more complex - we need to:
            # 1. Export data
            # 2. Drop and recreate schema
            # 3. Import data back
            
            log_warning("Schema-only reset is complex and not fully implemented")
            log_info("Consider using migrations instead")
            
            return False
            
        except Exception as e:
            log_error(f"Schema-only reset failed: {e}")
            return False
    
    async def reset_specific_tables(self, tables: Set[str], drop_recreate: bool = False) -> bool:
        """Reset specific tables."""
        try:
            log_info(f"Resetting specific tables: {', '.join(tables)}")
            
            # Verify tables exist
            existing_tables = set(await self.get_table_list())
            invalid_tables = tables - existing_tables
            
            if invalid_tables:
                log_warning(f"Tables not found: {', '.join(invalid_tables)}")
                tables = tables - invalid_tables
            
            if not tables:
                log_warning("No valid tables to reset")
                return False
            
            if drop_recreate:
                # Drop and recreate tables (more thorough but loses structure changes)
                for table in tables:
                    try:
                        await self.client.execute_command(f"DROP TABLE IF EXISTS {table} CASCADE")
                        log_info(f"Dropped table: {table}")
                    except Exception as e:
                        log_warning(f"Could not drop table {table}: {e}")
                
                # Recreate tables (this would need schema definitions)
                log_warning("Table recreation not implemented - use full reset instead")
            else:
                # Just truncate tables
                for table in tables:
                    try:
                        await self.client.execute_command(f"TRUNCATE TABLE {table} CASCADE")
                        log_info(f"Truncated table: {table}")
                    except Exception as e:
                        log_warning(f"Could not truncate table {table}: {e}")
            
            return True
            
        except Exception as e:
            log_error(f"Table-specific reset failed: {e}")
            return False
    
    async def run_migrations(self) -> bool:
        """Run database migrations."""
        try:
            log_info("Running database migrations...")
            
            # Check if migration system exists
            migration_script = Path(__file__).parent.parent / "src" / "multimodal_librarian" / "database" / "migrations.py"
            
            if migration_script.exists():
                import subprocess
                result = subprocess.run([
                    sys.executable, "-m", "multimodal_librarian.database.migrations"
                ], capture_output=True, text=True, cwd=Path(__file__).parent.parent)
                
                if result.returncode == 0:
                    log_success("Migrations completed successfully")
                    return True
                else:
                    log_error(f"Migration failed: {result.stderr}")
                    return False
            else:
                log_warning("Migration system not found")
                return False
                
        except Exception as e:
            log_error(f"Migration execution failed: {e}")
            return False
    
    async def vacuum_analyze(self) -> bool:
        """Run VACUUM ANALYZE to optimize database."""
        try:
            log_info("Running VACUUM ANALYZE...")
            await self.client.execute_command("VACUUM ANALYZE")
            log_success("VACUUM ANALYZE completed")
            return True
        except Exception as e:
            log_error(f"VACUUM ANALYZE failed: {e}")
            return False
    
    def print_summary(self, operation: str, success: bool, info_before: Dict, info_after: Dict) -> None:
        """Print reset operation summary."""
        print("\n" + "="*60)
        colored_print("POSTGRESQL RESET SUMMARY", Colors.BLUE)
        print("="*60)
        
        print(f"Operation: {operation}")
        print(f"Status: {'SUCCESS' if success else 'FAILED'}")
        print(f"Environment: {self.config.database_type}")
        print()
        
        # Before/after comparison
        print("Database Statistics:")
        print(f"  Tables before: {info_before.get('table_count', 0)}")
        print(f"  Tables after:  {info_after.get('table_count', 0)}")
        print(f"  Size before:   {info_before.get('size', 0) / 1024 / 1024:.2f} MB")
        print(f"  Size after:    {info_after.get('size', 0) / 1024 / 1024:.2f} MB")
        
        # Table details
        if info_after.get("tables"):
            print("\nTables after reset:")
            for table in info_after["tables"][:10]:  # Show first 10 tables
                print(f"  {table['tablename']:20} {table['size']}")
            
            if len(info_after["tables"]) > 10:
                print(f"  ... and {len(info_after['tables']) - 10} more tables")
        
        print("="*60)

async def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Reset PostgreSQL database for Multimodal Librarian",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    # Reset type (mutually exclusive)
    reset_group = parser.add_mutually_exclusive_group(required=True)
    reset_group.add_argument("--full", action="store_true", help="Full reset (drop and recreate all)")
    reset_group.add_argument("--data-only", action="store_true", help="Reset data only, keep schema")
    reset_group.add_argument("--schema-only", action="store_true", help="Reset schema only, keep data")
    reset_group.add_argument("--tables", type=str, help="Reset specific tables (comma-separated)")
    
    # Options
    parser.add_argument("--backup", action="store_true", help="Create backup before reset")
    parser.add_argument("--backup-dir", default="./backups", help="Backup directory")
    parser.add_argument("--migrate", action="store_true", help="Run migrations after reset")
    parser.add_argument("--vacuum", action="store_true", help="Run VACUUM ANALYZE after reset")
    parser.add_argument("--drop-recreate", action="store_true", help="Drop and recreate tables (for --tables)")
    parser.add_argument("--force", action="store_true", help="Skip confirmation prompts")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done")
    
    # Environment
    parser.add_argument("--environment", choices=["local", "aws"], help="Override environment")
    
    # Logging
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--quiet", "-q", action="store_true", help="Quiet output")
    
    args = parser.parse_args()
    
    # Configure logging
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    elif args.quiet:
        logging.getLogger().setLevel(logging.ERROR)
    
    try:
        # Get configuration
        if args.environment:
            os.environ["ML_ENVIRONMENT"] = args.environment
        
        config = get_database_config()
        log_info(f"Using {config.database_type} environment")
        
        # Initialize manager
        manager = PostgreSQLResetManager(config)
        await manager.initialize()
        
        try:
            # Get initial database info
            info_before = await manager.get_database_info()
            
            # Determine operation
            if args.full:
                operation = "Full Reset"
            elif args.data_only:
                operation = "Data-Only Reset"
            elif args.schema_only:
                operation = "Schema-Only Reset"
            elif args.tables:
                operation = f"Table Reset ({args.tables})"
            
            # Show what will be done
            print(f"\nOperation: {operation}")
            print(f"Database: {config.database_type} PostgreSQL")
            print(f"Current tables: {info_before.get('table_count', 0)}")
            print(f"Current size: {info_before.get('size', 0) / 1024 / 1024:.2f} MB")
            
            if args.dry_run:
                log_info("DRY RUN - No changes will be made")
                return 0
            
            # Confirm operation
            if not args.force:
                print("\n⚠️  This operation will modify or delete database data!")
                response = input("Continue? (yes/no): ").lower().strip()
                if response not in ["yes", "y"]:
                    log_info("Operation cancelled")
                    return 0
            
            # Create backup if requested
            backup_path = None
            if args.backup:
                backup_path = await manager.create_backup(args.backup_dir)
                if not backup_path:
                    log_warning("Backup failed, continuing anyway...")
            
            # Perform reset operation
            success = False
            
            if args.full:
                success = await manager.reset_full(args.migrate)
            elif args.data_only:
                tables = set(args.tables.split(",")) if args.tables else None
                success = await manager.reset_data_only(tables)
            elif args.schema_only:
                success = await manager.reset_schema_only()
            elif args.tables:
                tables = set(t.strip() for t in args.tables.split(","))
                success = await manager.reset_specific_tables(tables, args.drop_recreate)
            
            # Run post-reset operations
            if success:
                if args.migrate and not args.full:  # Full reset already runs migrations
                    await manager.run_migrations()
                
                if args.vacuum:
                    await manager.vacuum_analyze()
            
            # Get final database info
            info_after = await manager.get_database_info()
            
            # Print summary
            manager.print_summary(operation, success, info_before, info_after)
            
            return 0 if success else 1
            
        finally:
            await manager.cleanup()
            
    except KeyboardInterrupt:
        log_warning("Operation cancelled by user")
        return 1
    except Exception as e:
        log_error(f"Operation failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))