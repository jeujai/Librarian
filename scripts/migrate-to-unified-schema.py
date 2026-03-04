#!/usr/bin/env python3
"""
Unified Schema Migration Script

This script migrates data from the public schema (documents, document_chunks)
to the unified multimodal_librarian schema (knowledge_sources, knowledge_chunks).

Usage:
    # Dry run - show what would be migrated without making changes
    python scripts/migrate-to-unified-schema.py --dry-run
    
    # Execute migration
    python scripts/migrate-to-unified-schema.py --migrate
    
    # Verify migration was successful
    python scripts/migrate-to-unified-schema.py --verify
    
    # Cleanup public schema tables after successful migration
    python scripts/migrate-to-unified-schema.py --cleanup
    
    # Full migration workflow (migrate + verify)
    python scripts/migrate-to-unified-schema.py --migrate --verify

Requirements:
    - PostgreSQL database must be accessible
    - multimodal_librarian schema must exist with knowledge_sources and knowledge_chunks tables
    - Backup database before running migration
"""

import argparse
import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ANSI color codes for terminal output
GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
BLUE = '\033[94m'
BOLD = '\033[1m'
END = '\033[0m'


def print_header(title: str) -> None:
    """Print a formatted header."""
    print(f"\n{BOLD}{'='*70}{END}")
    print(f"{BOLD}{BLUE}{title}{END}")
    print(f"{BOLD}{'='*70}{END}\n")


def print_section(title: str) -> None:
    """Print a section header."""
    print(f"\n{BOLD}{title}{END}")
    print(f"{'-'*50}")


def print_success(message: str) -> None:
    """Print a success message."""
    print(f"{GREEN}✓ {message}{END}")


def print_warning(message: str) -> None:
    """Print a warning message."""
    print(f"{YELLOW}⚠ {message}{END}")


def print_error(message: str) -> None:
    """Print an error message."""
    print(f"{RED}✗ {message}{END}")


def print_info(message: str) -> None:
    """Print an info message."""
    print(f"{BLUE}ℹ {message}{END}")


async def run_dry_run(verbose: bool = False) -> bool:
    """
    Execute a dry run to show what would be migrated.
    
    Args:
        verbose: If True, show detailed information
        
    Returns:
        bool: True if dry run completed successfully
    """
    from multimodal_librarian.services.migration_service import MigrationService
    
    print_header("DRY RUN - Unified Schema Migration")
    print_info("No changes will be made to the database")
    
    try:
        service = MigrationService()
        result = await service.migrate(dry_run=True)
        
        print_section("Migration Summary")
        print(f"  Documents to migrate: {result.documents_migrated}")
        print(f"  Chunks to migrate: {result.chunks_migrated}")
        print(f"  Processing jobs to migrate: {result.processing_jobs_migrated}")
        print(f"  Duration: {result.duration_seconds:.2f} seconds")
        
        if result.errors:
            print_section("Errors Detected")
            for error in result.errors:
                print_error(error)
            return False
        
        if result.documents_migrated == 0 and result.chunks_migrated == 0:
            print_warning("No data found to migrate in public schema")
        else:
            print_success("Dry run completed successfully")
            print_info("Run with --migrate to execute the migration")
        
        return True
        
    except Exception as e:
        print_error(f"Dry run failed: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        return False


async def run_migration(verbose: bool = False, force: bool = False) -> bool:
    """
    Execute the migration from public to unified schema.
    
    Args:
        verbose: If True, show detailed information
        force: If True, skip confirmation prompt
        
    Returns:
        bool: True if migration completed successfully
    """
    from multimodal_librarian.services.migration_service import MigrationService
    
    print_header("Unified Schema Migration")
    
    # First do a dry run to show what will be migrated
    print_section("Pre-Migration Analysis")
    
    try:
        service = MigrationService()
        dry_result = await service.migrate(dry_run=True)
        
        print(f"  Documents to migrate: {dry_result.documents_migrated}")
        print(f"  Chunks to migrate: {dry_result.chunks_migrated}")
        print(f"  Processing jobs to migrate: {dry_result.processing_jobs_migrated}")
        
        if dry_result.errors:
            print_section("Pre-Migration Errors")
            for error in dry_result.errors:
                print_error(error)
            print_error("Cannot proceed with migration due to errors")
            return False
        
        if dry_result.documents_migrated == 0 and dry_result.chunks_migrated == 0:
            print_warning("No data found to migrate")
            return True
        
        # Confirm migration
        if not force:
            print()
            try:
                response = input(f"{YELLOW}Proceed with migration? (y/N): {END}").strip().lower()
                if response not in ['y', 'yes']:
                    print_info("Migration cancelled by user")
                    return False
            except (EOFError, KeyboardInterrupt):
                print_info("\nMigration cancelled by user")
                return False
        
        # Execute migration
        print_section("Executing Migration")
        start_time = datetime.now()
        
        result = await service.migrate(dry_run=False)
        
        print_section("Migration Results")
        print(f"  Documents migrated: {result.documents_migrated}")
        print(f"  Chunks migrated: {result.chunks_migrated}")
        print(f"  Processing jobs migrated: {result.processing_jobs_migrated}")
        print(f"  Duration: {result.duration_seconds:.2f} seconds")
        
        if result.errors:
            print_section("Migration Errors")
            for error in result.errors:
                print_error(error)
        
        if result.success:
            print_success("Migration completed successfully")
            print_info("Run with --verify to verify the migration")
            return True
        else:
            print_error("Migration completed with errors")
            return False
            
    except Exception as e:
        print_error(f"Migration failed: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        return False


async def run_verification(verbose: bool = False) -> bool:
    """
    Verify that migration completed successfully.
    
    Args:
        verbose: If True, show detailed information
        
    Returns:
        bool: True if verification passed
    """
    from multimodal_librarian.services.migration_service import MigrationService
    
    print_header("Migration Verification")
    
    try:
        service = MigrationService()
        result = await service.verify_migration()
        
        print_section("Row Count Comparison")
        print(f"  Source documents (public.documents): {result.source_document_count}")
        print(f"  Target documents (knowledge_sources): {result.target_document_count}")
        print(f"  Source chunks (public.document_chunks): {result.source_chunk_count}")
        print(f"  Target chunks (knowledge_chunks): {result.target_chunk_count}")
        
        if result.discrepancies:
            print_section("Discrepancies Found")
            for discrepancy in result.discrepancies:
                print_warning(discrepancy)
        
        if result.success:
            print_success("Verification passed - all data migrated successfully")
            print_info("Run with --cleanup to remove public schema tables")
            return True
        else:
            print_error("Verification failed - data mismatch detected")
            print_warning("Do NOT run cleanup until discrepancies are resolved")
            return False
            
    except Exception as e:
        print_error(f"Verification failed: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        return False


async def run_cleanup(verbose: bool = False, force: bool = False) -> bool:
    """
    Clean up public schema tables after successful migration.
    
    Args:
        verbose: If True, show detailed information
        force: If True, skip confirmation prompt
        
    Returns:
        bool: True if cleanup completed successfully
    """
    from multimodal_librarian.services.migration_service import MigrationService
    
    print_header("Public Schema Cleanup")
    print_warning("This will permanently delete the following tables:")
    print("  - public.processing_jobs")
    print("  - public.document_chunks")
    print("  - public.documents")
    
    # First verify migration using thorough cleanup verification
    print_section("Pre-Cleanup Verification")
    print_info("Checking for unmigrated data...")
    
    try:
        service = MigrationService()
        verification = await service.verify_cleanup_safe()
        
        print(f"  Source documents: {verification.source_document_count}")
        print(f"  Target documents: {verification.target_document_count}")
        print(f"  Source chunks: {verification.source_chunk_count}")
        print(f"  Target chunks: {verification.target_chunk_count}")
        
        if not verification.success:
            print_error("Verification failed - cannot proceed with cleanup")
            print_section("Discrepancies Found")
            for discrepancy in verification.discrepancies:
                print_warning(discrepancy)
            print_info("Resolve discrepancies before running cleanup")
            return False
        
        print_success("All data verified - safe to proceed")
        
        # Confirm cleanup
        if not force:
            print()
            try:
                response = input(
                    f"{RED}⚠️  This action is IRREVERSIBLE. Proceed with cleanup? (y/N): {END}"
                ).strip().lower()
                if response not in ['y', 'yes']:
                    print_info("Cleanup cancelled by user")
                    return False
            except (EOFError, KeyboardInterrupt):
                print_info("\nCleanup cancelled by user")
                return False
        
        # Execute cleanup
        print_section("Executing Cleanup")
        
        result = await service.cleanup_public_schema()
        
        print_section("Cleanup Results")
        if result.tables_dropped:
            print("  Tables dropped:")
            for table in result.tables_dropped:
                print_success(f"    {table}")
        
        if result.errors:
            print_section("Cleanup Errors")
            for error in result.errors:
                print_error(error)
        
        if result.success:
            print_success("Cleanup completed successfully")
            return True
        else:
            print_error("Cleanup completed with errors")
            return False
            
    except Exception as e:
        print_error(f"Cleanup failed: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        return False


async def run_status(verbose: bool = False) -> bool:
    """
    Show current migration status.
    
    Args:
        verbose: If True, show detailed information
        
    Returns:
        bool: True if status check completed successfully
    """
    from multimodal_librarian.services.migration_service import MigrationService
    
    print_header("Migration Status")
    
    try:
        service = MigrationService()
        
        # Get source counts
        source_counts = await service._get_source_counts()
        
        print_section("Public Schema (Source)")
        print(f"  documents: {source_counts['documents']} rows")
        print(f"  document_chunks: {source_counts['chunks']} rows")
        print(f"  processing_jobs: {source_counts['processing_jobs']} rows")
        
        # Get target counts
        target_counts = await service._get_target_counts()
        
        print_section("Unified Schema (Target)")
        print(f"  knowledge_sources: {target_counts['knowledge_sources']} rows")
        print(f"  knowledge_chunks: {target_counts['knowledge_chunks']} rows")
        
        # Determine migration status
        print_section("Migration Status")
        
        source_total = source_counts['documents'] + source_counts['chunks']
        target_total = target_counts['knowledge_sources'] + target_counts['knowledge_chunks']
        
        if source_total == 0 and target_total == 0:
            print_info("No data in either schema")
        elif source_total == 0 and target_total > 0:
            print_success("Migration complete - public schema is empty")
        elif source_total > 0 and target_total == 0:
            print_warning("Migration not started - unified schema is empty")
            print_info("Run with --migrate to start migration")
        elif source_total == target_total:
            print_success("Migration appears complete - row counts match")
            print_info("Run with --verify for detailed verification")
        else:
            print_warning("Partial migration detected - row counts differ")
            print_info("Run with --verify to check for discrepancies")
        
        return True
        
    except Exception as e:
        print_error(f"Status check failed: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        return False


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Migrate data from public schema to unified multimodal_librarian schema",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Show current migration status
  python scripts/migrate-to-unified-schema.py --status
  
  # Dry run - show what would be migrated
  python scripts/migrate-to-unified-schema.py --dry-run
  
  # Execute migration
  python scripts/migrate-to-unified-schema.py --migrate
  
  # Verify migration was successful
  python scripts/migrate-to-unified-schema.py --verify
  
  # Full workflow: migrate and verify
  python scripts/migrate-to-unified-schema.py --migrate --verify
  
  # Cleanup public schema after successful migration
  python scripts/migrate-to-unified-schema.py --cleanup
  
  # Force migration without confirmation
  python scripts/migrate-to-unified-schema.py --migrate --force

Notes:
  - Always backup your database before running migration
  - Run --dry-run first to see what will be migrated
  - Run --verify after migration to confirm success
  - Only run --cleanup after successful verification
        """
    )
    
    # Action arguments (mutually exclusive for primary actions)
    action_group = parser.add_argument_group('Actions')
    action_group.add_argument(
        "--status",
        action="store_true",
        help="Show current migration status"
    )
    action_group.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be migrated without making changes"
    )
    action_group.add_argument(
        "--migrate",
        action="store_true",
        help="Execute the migration"
    )
    action_group.add_argument(
        "--verify",
        action="store_true",
        help="Verify migration was successful"
    )
    action_group.add_argument(
        "--cleanup",
        action="store_true",
        help="Remove public schema tables after successful migration"
    )
    
    # Options
    options_group = parser.add_argument_group('Options')
    options_group.add_argument(
        "--force",
        action="store_true",
        help="Skip confirmation prompts"
    )
    options_group.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed output including stack traces"
    )
    options_group.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Quiet mode - only show errors"
    )
    
    args = parser.parse_args()
    
    # Configure logging level
    if args.quiet:
        logging.getLogger().setLevel(logging.ERROR)
    elif args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Check that at least one action is specified
    if not any([args.status, args.dry_run, args.migrate, args.verify, args.cleanup]):
        parser.print_help()
        print_error("\nNo action specified. Use --status, --dry-run, --migrate, --verify, or --cleanup")
        sys.exit(1)
    
    success = True
    
    try:
        # Execute requested actions in order
        if args.status:
            success = await run_status(args.verbose) and success
        
        if args.dry_run:
            success = await run_dry_run(args.verbose) and success
        
        if args.migrate:
            success = await run_migration(args.verbose, args.force) and success
        
        if args.verify:
            success = await run_verification(args.verbose) and success
        
        if args.cleanup:
            success = await run_cleanup(args.verbose, args.force) and success
        
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        print_info("\nOperation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
