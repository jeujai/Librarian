#!/usr/bin/env python3
"""
Schema Migration Script

This script manages schema migrations across all database systems used by
the Multimodal Librarian application.

Usage:
    # Migrate all databases to latest version
    python scripts/migrate-schemas.py
    
    # Migrate specific databases
    python scripts/migrate-schemas.py --databases postgresql milvus
    
    # Dry run (validate without executing)
    python scripts/migrate-schemas.py --dry-run
    
    # Rollback to specific version
    python scripts/migrate-schemas.py --rollback --target-version 1.0.0
    
    # Show migration status
    python scripts/migrate-schemas.py --status
"""

import sys
import asyncio
import argparse
import logging
from pathlib import Path
from typing import Dict, List, Optional

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from database.schema_version_manager import (
        SchemaVersionManager, DatabaseType, MigrationStatus
    )
    from database.schema_validator import SchemaValidator, ValidationStatus
    MODULES_AVAILABLE = True
except ImportError as e:
    MODULES_AVAILABLE = False
    IMPORT_ERROR = str(e)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def print_migration_status(manager: SchemaVersionManager) -> None:
    """Print current migration status"""
    
    # ANSI color codes
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'
    
    print(f"\n{BOLD}{'='*80}{END}")
    print(f"{BOLD}{BLUE}SCHEMA MIGRATION STATUS{END}")
    print(f"{BOLD}{'='*80}{END}")
    
    # Get status information
    status_info = manager.get_migration_status()
    
    print(f"\n{BOLD}Available Migrations:{END}")
    for db_type, count in status_info["available_migrations"].items():
        print(f"  {db_type}: {count} migrations")
    
    print(f"\n{BOLD}Version History:{END}")
    version_history = status_info.get("version_history", {})
    
    if version_history:
        for db_type, history in version_history.items():
            current_version = history.get("current", "Unknown")
            migration_count = len(history.get("migrations", []))
            
            print(f"  {db_type}:")
            print(f"    Current Version: {current_version}")
            print(f"    Applied Migrations: {migration_count}")
            
            # Show recent migrations
            recent_migrations = history.get("migrations", [])[-3:]
            if recent_migrations:
                print(f"    Recent Migrations:")
                for migration in recent_migrations:
                    status_color = GREEN if migration["status"] == "completed" else RED
                    print(f"      {status_color}• {migration['version']} - {migration['description']}{END}")
    else:
        print(f"  {YELLOW}No migration history found{END}")
    
    print(f"\n{BOLD}Migration Settings:{END}")
    settings = status_info.get("migration_settings", {})
    for key, value in settings.items():
        print(f"  {key}: {value}")
    
    print(f"{BOLD}{'='*80}{END}\n")


async def show_migration_plan(
    manager: SchemaVersionManager,
    target_versions: Dict[DatabaseType, str],
    current_versions: Optional[Dict[DatabaseType, Optional[str]]] = None
) -> None:
    """Show migration plan without executing"""
    
    print(f"\n{'='*60}")
    print("MIGRATION PLAN")
    print(f"{'='*60}")
    
    if current_versions is None:
        current_versions = await manager.get_current_versions()
    
    migration_plans = manager.create_migration_plan(target_versions, current_versions)
    
    for db_type, plan in migration_plans.items():
        current_version = current_versions.get(db_type, "None")
        
        print(f"\n{db_type.value.upper()}:")
        print(f"  Current Version: {current_version}")
        print(f"  Target Version: {plan.target_version}")
        print(f"  Direction: {plan.direction.value}")
        print(f"  Migrations to Apply: {len(plan.migrations)}")
        
        if plan.migrations:
            print(f"  Migration Steps:")
            for i, migration in enumerate(plan.migrations, 1):
                print(f"    {i}. {migration.version} - {migration.description}")
        else:
            print(f"  No migrations needed (already at target version)")
        
        if plan.requires_backup:
            print(f"  ⚠️  Backup will be created before migration")
    
    print(f"{'='*60}\n")


async def execute_migrations(
    manager: SchemaVersionManager,
    databases: Optional[List[DatabaseType]] = None,
    dry_run: bool = False
) -> Dict[DatabaseType, bool]:
    """Execute migrations to latest versions"""
    
    logger.info(f"{'Dry run' if dry_run else 'Executing'} migrations to latest versions...")
    
    # Get current and latest versions
    current_versions = await manager.get_current_versions()
    latest_versions = manager.get_latest_versions()
    
    # Filter databases if specified
    if databases:
        target_versions = {
            db_type: version for db_type, version in latest_versions.items()
            if db_type in databases and version is not None
        }
    else:
        target_versions = {
            db_type: version for db_type, version in latest_versions.items()
            if version is not None
        }
    
    if not target_versions:
        logger.info("No migrations available or no databases specified")
        return {}
    
    # Show migration plan
    await show_migration_plan(manager, target_versions, current_versions)
    
    if dry_run:
        logger.info("Dry run completed - no changes made")
        return {db_type: True for db_type in target_versions.keys()}
    
    # Confirm execution
    try:
        response = input("Proceed with migration? (y/N): ").strip().lower()
        if response not in ['y', 'yes']:
            logger.info("Migration cancelled by user")
            return {}
    except (EOFError, KeyboardInterrupt):
        logger.info("Migration cancelled by user")
        return {}
    
    # Execute migrations
    results = await manager.migrate_to_latest(list(target_versions.keys()))
    
    # Print results
    print(f"\n{'='*60}")
    print("MIGRATION RESULTS")
    print(f"{'='*60}")
    
    for db_type, success in results.items():
        status_color = '\033[92m' if success else '\033[91m'
        status_text = "SUCCESS" if success else "FAILED"
        print(f"{db_type.value}: {status_color}{status_text}\033[0m")
    
    successful = sum(1 for success in results.values() if success)
    total = len(results)
    print(f"\nOverall: {successful}/{total} migrations successful")
    print(f"{'='*60}\n")
    
    return results


async def execute_rollback(
    manager: SchemaVersionManager,
    target_versions: Dict[DatabaseType, str],
    databases: Optional[List[DatabaseType]] = None
) -> Dict[DatabaseType, bool]:
    """Execute rollback to specific versions"""
    
    logger.info("Executing rollback to specified versions...")
    
    # Get current versions
    current_versions = await manager.get_current_versions()
    
    # Filter target versions if databases specified
    if databases:
        target_versions = {
            db_type: version for db_type, version in target_versions.items()
            if db_type in databases
        }
    
    if not target_versions:
        logger.error("No target versions specified for rollback")
        return {}
    
    # Show rollback plan
    await show_migration_plan(manager, target_versions, current_versions)
    
    # Confirm rollback
    try:
        response = input("⚠️  Proceed with rollback? This may cause data loss! (y/N): ").strip().lower()
        if response not in ['y', 'yes']:
            logger.info("Rollback cancelled by user")
            return {}
    except (EOFError, KeyboardInterrupt):
        logger.info("Rollback cancelled by user")
        return {}
    
    # Execute rollback
    results = await manager.rollback_to_version(target_versions, list(target_versions.keys()))
    
    # Print results
    print(f"\n{'='*60}")
    print("ROLLBACK RESULTS")
    print(f"{'='*60}")
    
    for db_type, success in results.items():
        status_color = '\033[92m' if success else '\033[91m'
        status_text = "SUCCESS" if success else "FAILED"
        print(f"{db_type.value}: {status_color}{status_text}\033[0m")
    
    successful = sum(1 for success in results.values() if success)
    total = len(results)
    print(f"\nOverall: {successful}/{total} rollbacks successful")
    print(f"{'='*60}\n")
    
    return results


def parse_database_list(db_list: List[str]) -> List[DatabaseType]:
    """Parse database list from command line arguments"""
    databases = []
    for db_name in db_list:
        try:
            db_type = DatabaseType(db_name.lower())
            databases.append(db_type)
        except ValueError:
            logger.error(f"Unknown database type: {db_name}")
            logger.info(f"Available types: {[dt.value for dt in DatabaseType]}")
            sys.exit(1)
    return databases


def parse_target_versions(version_specs: List[str]) -> Dict[DatabaseType, str]:
    """Parse target version specifications"""
    target_versions = {}
    
    for spec in version_specs:
        if '=' not in spec:
            logger.error(f"Invalid version specification: {spec}")
            logger.info("Use format: database=version (e.g., postgresql=1.0.1)")
            sys.exit(1)
        
        db_name, version = spec.split('=', 1)
        try:
            db_type = DatabaseType(db_name.lower())
            target_versions[db_type] = version
        except ValueError:
            logger.error(f"Unknown database type: {db_name}")
            logger.info(f"Available types: {[dt.value for dt in DatabaseType]}")
            sys.exit(1)
    
    return target_versions


async def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description="Manage database schema migrations for Multimodal Librarian",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Migrate all databases to latest
  python scripts/migrate-schemas.py
  
  # Migrate specific databases
  python scripts/migrate-schemas.py --databases postgresql milvus
  
  # Dry run (validate without executing)
  python scripts/migrate-schemas.py --dry-run
  
  # Show current status
  python scripts/migrate-schemas.py --status
  
  # Rollback to specific versions
  python scripts/migrate-schemas.py --rollback --target-versions postgresql=1.0.0 milvus=1.0.0
  
  # Rollback all to specific version
  python scripts/migrate-schemas.py --rollback --target-version 1.0.0
        """
    )
    
    # Action arguments
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show current migration status"
    )
    parser.add_argument(
        "--rollback",
        action="store_true",
        help="Rollback to specified version(s)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate migrations without executing"
    )
    
    # Target specification
    parser.add_argument(
        "--databases",
        nargs="+",
        help="Specific databases to migrate (postgresql, milvus, neo4j)"
    )
    parser.add_argument(
        "--target-version",
        help="Target version for all databases (rollback only)"
    )
    parser.add_argument(
        "--target-versions",
        nargs="+",
        help="Specific target versions (format: database=version)"
    )
    
    # Options
    parser.add_argument(
        "--force",
        action="store_true",
        help="Skip confirmation prompts"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose logging"
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Quiet mode (errors only)"
    )
    
    args = parser.parse_args()
    
    # Configure logging level
    if args.quiet:
        logging.getLogger().setLevel(logging.ERROR)
    elif args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Check module availability
    if not MODULES_AVAILABLE:
        logger.error(f"Required modules not available: {IMPORT_ERROR}")
        sys.exit(1)
    
    try:
        # Initialize manager
        manager = SchemaVersionManager()
        
        # Parse database list if provided
        databases = None
        if args.databases:
            databases = parse_database_list(args.databases)
        
        # Handle status command
        if args.status:
            print_migration_status(manager)
            sys.exit(0)
        
        # Handle rollback command
        if args.rollback:
            if args.target_versions:
                target_versions = parse_target_versions(args.target_versions)
            elif args.target_version:
                # Apply same version to all databases
                all_db_types = list(DatabaseType)
                if databases:
                    all_db_types = databases
                target_versions = {db_type: args.target_version for db_type in all_db_types}
            else:
                logger.error("Rollback requires --target-version or --target-versions")
                sys.exit(1)
            
            results = await execute_rollback(manager, target_versions, databases)
            
            # Exit with error if any rollback failed
            failed_count = sum(1 for success in results.values() if not success)
            sys.exit(failed_count)
        
        # Handle migration command (default)
        else:
            results = await execute_migrations(manager, databases, args.dry_run)
            
            if not results:
                sys.exit(0)
            
            # Exit with error if any migration failed
            failed_count = sum(1 for success in results.values() if not success)
            sys.exit(failed_count)
    
    except KeyboardInterrupt:
        logger.info("Migration interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Migration failed with error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())