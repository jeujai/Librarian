#!/usr/bin/env python3
"""
Script to port existing database migrations to local PostgreSQL setup.

This script manages the migration porting process for local development,
ensuring all existing AWS-focused migrations work with local PostgreSQL.
"""

import sys
import asyncio
import argparse
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.multimodal_librarian.database.local_migration_manager import (
    LocalMigrationManager,
    port_migrations_to_local,
    get_local_migration_status
)
from src.multimodal_librarian.logging_config import get_logger

logger = get_logger(__name__)


async def main():
    """Main CLI function."""
    parser = argparse.ArgumentParser(
        description="Port existing database migrations to local PostgreSQL setup"
    )
    parser.add_argument(
        "action",
        choices=["port", "status", "reset", "verify"],
        help="Action to perform"
    )
    parser.add_argument(
        "--database-url",
        help="Database URL (defaults to local config)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force operation even if already completed"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    # Configure logging
    if args.verbose:
        import logging
        logging.getLogger().setLevel(logging.DEBUG)
    
    try:
        manager = LocalMigrationManager(args.database_url)
        
        if args.action == "port":
            print("🔄 Starting migration porting process...")
            
            # Check if already completed
            if not args.force:
                status = await manager.get_migration_status()
                if status.get("porting_complete"):
                    print("✅ Migration porting already completed")
                    print("   Use --force to re-run porting process")
                    return 0
            
            # Port migrations
            success = await manager.port_existing_migrations()
            
            if success:
                print("✅ Migration porting completed successfully!")
                
                # Show final status
                status = await manager.get_migration_status()
                print(f"\n📊 Final Status:")
                print(f"   • Porting complete: {status['porting_complete']}")
                print(f"   • Applied migrations: {len(status.get('migration_history', []))}")
                
                table_counts = status.get('table_counts', {})
                print(f"   • Table counts:")
                for table, count in table_counts.items():
                    print(f"     - {table}: {count}")
                
                return 0
            else:
                print("❌ Migration porting failed")
                return 1
        
        elif args.action == "status":
            print("📊 Getting migration status...")
            
            status = await manager.get_migration_status()
            
            print(f"\n🔍 Migration Status:")
            print(f"   • Porting complete: {status.get('porting_complete', False)}")
            print(f"   • Database URL: {status.get('database_url', 'Unknown')}")
            
            if 'error' in status:
                print(f"   • Error: {status['error']}")
                return 1
            
            # Show migration history
            history = status.get('migration_history', [])
            if history:
                print(f"\n📜 Migration History ({len(history)} migrations):")
                for migration in history[:10]:  # Show last 10
                    status_icon = "✅" if migration['success'] else "❌"
                    print(f"   {status_icon} {migration['name']} ({migration.get('applied_at', 'Unknown')})")
                
                if len(history) > 10:
                    print(f"   ... and {len(history) - 10} more")
            
            # Show table counts
            table_counts = status.get('table_counts', {})
            if table_counts:
                print(f"\n📋 Table Counts:")
                for table, count in table_counts.items():
                    print(f"   • {table}: {count}")
            
            return 0
        
        elif args.action == "reset":
            if not args.force:
                response = input("⚠️  This will reset all migration history. Continue? (y/N): ")
                if response.lower() != 'y':
                    print("Operation cancelled")
                    return 0
            
            print("🔄 Resetting migration state...")
            
            success = await manager.reset_migrations()
            
            if success:
                print("✅ Migration state reset successfully")
                return 0
            else:
                print("❌ Failed to reset migration state")
                return 1
        
        elif args.action == "verify":
            print("🔍 Verifying migration porting...")
            
            # Get status and verify
            status = await manager.get_migration_status()
            
            if status.get('porting_complete'):
                print("✅ Migration porting verification successful")
                
                # Additional verification
                table_counts = status.get('table_counts', {})
                required_tables = ['users', 'documents', 'knowledge_chunks', 'chat_messages']
                
                missing_tables = []
                for table in required_tables:
                    if table not in table_counts:
                        missing_tables.append(table)
                
                if missing_tables:
                    print(f"⚠️  Missing tables: {', '.join(missing_tables)}")
                    return 1
                
                print("✅ All required tables present")
                return 0
            else:
                print("❌ Migration porting not completed")
                return 1
    
    except KeyboardInterrupt:
        print("\n⚠️  Operation cancelled by user")
        return 1
    
    except Exception as e:
        print(f"❌ Error: {e}")
        logger.error("Migration porting script failed", error=str(e))
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)