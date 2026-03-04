#!/usr/bin/env python3
"""
Comprehensive Database Reset Script for Multimodal Librarian

This script provides safe and comprehensive database reset functionality for both
local development and AWS environments. It uses the database client factory to
ensure consistent behavior across different database backends.

Features:
- Environment-aware reset (local vs AWS)
- Selective database reset (choose which databases to reset)
- Safety checks and confirmations
- Backup creation before reset
- Data validation after reset
- Rollback capability

Usage:
    python scripts/reset-all-databases.py [options]

Examples:
    # Reset all databases with confirmation
    python scripts/reset-all-databases.py --all

    # Reset only PostgreSQL and Neo4j
    python scripts/reset-all-databases.py --databases postgresql,neo4j

    # Force reset without confirmation (dangerous!)
    python scripts/reset-all-databases.py --all --force

    # Reset with automatic backup
    python scripts/reset-all-databases.py --all --backup

    # Dry run to see what would be reset
    python scripts/reset-all-databases.py --all --dry-run
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
from contextlib import asynccontextmanager

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from multimodal_librarian.clients.database_client_factory import (
    DatabaseClientFactory, get_database_factory, close_global_factory
)
from multimodal_librarian.clients.protocols import (
    RelationalStoreClient, VectorStoreClient, GraphStoreClient,
    DatabaseClientError, ConnectionError, ConfigurationError
)
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
    CYAN = '\033[0;36m'
    WHITE = '\033[1;37m'
    NC = '\033[0m'  # No Color

def colored_print(message: str, color: str = Colors.NC) -> None:
    """Print colored message to terminal."""
    print(f"{color}{message}{Colors.NC}")

def log_info(message: str) -> None:
    """Log info message with color."""
    colored_print(f"[INFO] {message}", Colors.BLUE)

def log_success(message: str) -> None:
    """Log success message with color."""
    colored_print(f"[SUCCESS] {message}", Colors.GREEN)

def log_warning(message: str) -> None:
    """Log warning message with color."""
    colored_print(f"[WARNING] {message}", Colors.YELLOW)

def log_error(message: str) -> None:
    """Log error message with color."""
    colored_print(f"[ERROR] {message}", Colors.RED)

class DatabaseResetManager:
    """
    Manages database reset operations across different database types.
    
    This class provides a unified interface for resetting databases while
    maintaining safety checks, backup capabilities, and environment awareness.
    """
    
    def __init__(self, config: Any):
        """Initialize the reset manager with database configuration."""
        self.config = config
        self.factory: Optional[DatabaseClientFactory] = None
        self.reset_stats: Dict[str, Any] = {
            "start_time": None,
            "end_time": None,
            "databases_reset": [],
            "databases_failed": [],
            "backup_created": False,
            "backup_path": None,
            "total_duration": 0
        }
        
    async def initialize(self) -> None:
        """Initialize the database factory and connections."""
        try:
            self.factory = DatabaseClientFactory(self.config)
            log_info(f"Initialized database factory for {self.config.database_type} environment")
        except Exception as e:
            log_error(f"Failed to initialize database factory: {e}")
            raise
    
    async def cleanup(self) -> None:
        """Clean up database connections and resources."""
        if self.factory:
            await self.factory.close()
            self.factory = None
    
    async def check_database_health(self) -> Dict[str, Any]:
        """Check health of all database services."""
        if not self.factory:
            raise RuntimeError("Factory not initialized")
        
        log_info("Checking database health before reset...")
        health_status = await self.factory.health_check()
        
        # Display health status
        for service, status in health_status.get("services", {}).items():
            if status.get("status") == "healthy":
                log_success(f"{service}: Healthy ({status.get('response_time', 0):.3f}s)")
            else:
                log_warning(f"{service}: {status.get('status', 'Unknown')} - {status.get('error', 'No details')}")
        
        return health_status
    
    async def create_backup_before_reset(self, backup_dir: str = "./backups") -> Optional[str]:
        """Create backup before reset operation."""
        try:
            log_info("Creating backup before reset...")
            
            # Create backup directory with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = Path(backup_dir) / f"pre_reset_backup_{timestamp}"
            backup_path.mkdir(parents=True, exist_ok=True)
            
            # Run backup script
            backup_script = Path(__file__).parent / "backup-all-databases.sh"
            if backup_script.exists():
                import subprocess
                result = subprocess.run(
                    [str(backup_script), "full"],
                    env={**os.environ, "BACKUP_DIR": str(backup_path)},
                    capture_output=True,
                    text=True
                )
                
                if result.returncode == 0:
                    log_success(f"Backup created successfully: {backup_path}")
                    self.reset_stats["backup_created"] = True
                    self.reset_stats["backup_path"] = str(backup_path)
                    return str(backup_path)
                else:
                    log_warning(f"Backup creation failed: {result.stderr}")
                    return None
            else:
                log_warning("Backup script not found, skipping backup")
                return None
                
        except Exception as e:
            log_error(f"Failed to create backup: {e}")
            return None
    
    async def reset_postgresql(self, client: RelationalStoreClient) -> bool:
        """Reset PostgreSQL database."""
        try:
            log_info("Resetting PostgreSQL database...")
            
            # Get database info before reset
            db_info = await client.get_database_info()
            log_info(f"PostgreSQL info: {db_info.get('table_count', 0)} tables, "
                    f"{db_info.get('size', 0) / 1024 / 1024:.2f} MB")
            
            # Drop all tables
            await client.drop_tables()
            log_success("PostgreSQL tables dropped")
            
            # Recreate tables
            await client.create_tables()
            log_success("PostgreSQL tables recreated")
            
            # Verify reset
            new_info = await client.get_database_info()
            log_info(f"PostgreSQL after reset: {new_info.get('table_count', 0)} tables")
            
            return True
            
        except Exception as e:
            log_error(f"Failed to reset PostgreSQL: {e}")
            return False
    
    async def reset_neo4j(self, client: GraphStoreClient) -> bool:
        """Reset Neo4j database."""
        try:
            log_info("Resetting Neo4j database...")
            
            # Get node count before reset
            try:
                result = await client.execute_query("MATCH (n) RETURN count(n) as node_count")
                node_count = result[0].get("node_count", 0) if result else 0
                log_info(f"Neo4j info: {node_count} nodes")
            except Exception:
                log_warning("Could not get Neo4j node count")
            
            # Delete all nodes and relationships
            await client.execute_query("MATCH (n) DETACH DELETE n")
            log_success("Neo4j nodes and relationships deleted")
            
            # Clear any constraints and indexes
            try:
                # Drop constraints
                constraints_result = await client.execute_query("SHOW CONSTRAINTS")
                for constraint in constraints_result:
                    constraint_name = constraint.get("name")
                    if constraint_name:
                        await client.execute_query(f"DROP CONSTRAINT {constraint_name}")
                
                # Drop indexes
                indexes_result = await client.execute_query("SHOW INDEXES")
                for index in indexes_result:
                    index_name = index.get("name")
                    if index_name and not index.get("type", "").startswith("LOOKUP"):
                        await client.execute_query(f"DROP INDEX {index_name}")
                
                log_success("Neo4j constraints and indexes cleared")
            except Exception as e:
                log_warning(f"Could not clear all Neo4j constraints/indexes: {e}")
            
            # Verify reset
            try:
                result = await client.execute_query("MATCH (n) RETURN count(n) as node_count")
                new_count = result[0].get("node_count", 0) if result else 0
                log_info(f"Neo4j after reset: {new_count} nodes")
            except Exception:
                log_warning("Could not verify Neo4j reset")
            
            return True
            
        except Exception as e:
            log_error(f"Failed to reset Neo4j: {e}")
            return False
    
    async def reset_milvus(self, client: VectorStoreClient) -> bool:
        """Reset Milvus database."""
        try:
            log_info("Resetting Milvus database...")
            
            # List all collections
            collections = await client.list_collections()
            log_info(f"Milvus info: {len(collections)} collections")
            
            # Delete all collections
            for collection_name in collections:
                try:
                    await client.delete_collection(collection_name)
                    log_info(f"Deleted Milvus collection: {collection_name}")
                except Exception as e:
                    log_warning(f"Failed to delete collection {collection_name}: {e}")
            
            log_success("Milvus collections deleted")
            
            # Verify reset
            new_collections = await client.list_collections()
            log_info(f"Milvus after reset: {len(new_collections)} collections")
            
            return True
            
        except Exception as e:
            log_error(f"Failed to reset Milvus: {e}")
            return False
    
    async def reset_redis(self) -> bool:
        """Reset Redis database."""
        try:
            log_info("Resetting Redis database...")
            
            # Use redis-cli to flush all databases
            import subprocess
            
            redis_host = getattr(self.config, 'redis_host', 'localhost')
            redis_port = getattr(self.config, 'redis_port', 6379)
            
            # Get key count before reset
            try:
                result = subprocess.run(
                    ["redis-cli", "-h", redis_host, "-p", str(redis_port), "DBSIZE"],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    key_count = int(result.stdout.strip())
                    log_info(f"Redis info: {key_count} keys")
            except Exception:
                log_warning("Could not get Redis key count")
            
            # Flush all databases
            result = subprocess.run(
                ["redis-cli", "-h", redis_host, "-p", str(redis_port), "FLUSHALL"],
                capture_output=True, text=True, timeout=30
            )
            
            if result.returncode == 0:
                log_success("Redis databases flushed")
                
                # Verify reset
                try:
                    result = subprocess.run(
                        ["redis-cli", "-h", redis_host, "-p", str(redis_port), "DBSIZE"],
                        capture_output=True, text=True, timeout=10
                    )
                    if result.returncode == 0:
                        new_count = int(result.stdout.strip())
                        log_info(f"Redis after reset: {new_count} keys")
                except Exception:
                    log_warning("Could not verify Redis reset")
                
                return True
            else:
                log_error(f"Failed to flush Redis: {result.stderr}")
                return False
                
        except Exception as e:
            log_error(f"Failed to reset Redis: {e}")
            return False
    
    async def reset_databases(
        self, 
        databases: Set[str], 
        dry_run: bool = False
    ) -> Dict[str, bool]:
        """Reset specified databases."""
        if not self.factory:
            raise RuntimeError("Factory not initialized")
        
        results = {}
        self.reset_stats["start_time"] = time.time()
        
        if dry_run:
            log_info("DRY RUN MODE - No actual changes will be made")
        
        # Reset PostgreSQL
        if "postgresql" in databases:
            if dry_run:
                log_info("Would reset PostgreSQL database")
                results["postgresql"] = True
            else:
                try:
                    client = await self.factory.get_relational_client()
                    success = await self.reset_postgresql(client)
                    results["postgresql"] = success
                    if success:
                        self.reset_stats["databases_reset"].append("postgresql")
                    else:
                        self.reset_stats["databases_failed"].append("postgresql")
                except Exception as e:
                    log_error(f"PostgreSQL reset failed: {e}")
                    results["postgresql"] = False
                    self.reset_stats["databases_failed"].append("postgresql")
        
        # Reset Neo4j
        if "neo4j" in databases:
            if dry_run:
                log_info("Would reset Neo4j database")
                results["neo4j"] = True
            else:
                try:
                    client = await self.factory.get_graph_client()
                    success = await self.reset_neo4j(client)
                    results["neo4j"] = success
                    if success:
                        self.reset_stats["databases_reset"].append("neo4j")
                    else:
                        self.reset_stats["databases_failed"].append("neo4j")
                except Exception as e:
                    log_error(f"Neo4j reset failed: {e}")
                    results["neo4j"] = False
                    self.reset_stats["databases_failed"].append("neo4j")
        
        # Reset Milvus/OpenSearch
        if "milvus" in databases or "opensearch" in databases:
            db_name = "milvus" if "milvus" in databases else "opensearch"
            if dry_run:
                log_info(f"Would reset {db_name} database")
                results[db_name] = True
            else:
                try:
                    client = await self.factory.get_vector_client()
                    success = await self.reset_milvus(client)
                    results[db_name] = success
                    if success:
                        self.reset_stats["databases_reset"].append(db_name)
                    else:
                        self.reset_stats["databases_failed"].append(db_name)
                except Exception as e:
                    log_error(f"{db_name} reset failed: {e}")
                    results[db_name] = False
                    self.reset_stats["databases_failed"].append(db_name)
        
        # Reset Redis
        if "redis" in databases:
            if dry_run:
                log_info("Would reset Redis database")
                results["redis"] = True
            else:
                try:
                    success = await self.reset_redis()
                    results["redis"] = success
                    if success:
                        self.reset_stats["databases_reset"].append("redis")
                    else:
                        self.reset_stats["databases_failed"].append("redis")
                except Exception as e:
                    log_error(f"Redis reset failed: {e}")
                    results["redis"] = False
                    self.reset_stats["databases_failed"].append("redis")
        
        self.reset_stats["end_time"] = time.time()
        self.reset_stats["total_duration"] = self.reset_stats["end_time"] - self.reset_stats["start_time"]
        
        return results
    
    def print_reset_summary(self, results: Dict[str, bool]) -> None:
        """Print summary of reset operations."""
        print("\n" + "="*60)
        colored_print("DATABASE RESET SUMMARY", Colors.WHITE)
        print("="*60)
        
        # Environment info
        print(f"Environment: {self.config.database_type}")
        print(f"Duration: {self.reset_stats['total_duration']:.2f} seconds")
        
        if self.reset_stats["backup_created"]:
            print(f"Backup created: {self.reset_stats['backup_path']}")
        
        print()
        
        # Results by database
        for db_name, success in results.items():
            status = "✓ SUCCESS" if success else "✗ FAILED"
            color = Colors.GREEN if success else Colors.RED
            colored_print(f"{db_name:12} {status}", color)
        
        print()
        
        # Overall status
        successful = sum(1 for success in results.values() if success)
        total = len(results)
        
        if successful == total:
            log_success(f"All {total} databases reset successfully")
        elif successful > 0:
            log_warning(f"{successful}/{total} databases reset successfully")
        else:
            log_error("All database resets failed")
        
        print("="*60)

def confirm_reset(databases: Set[str], environment: str, force: bool = False) -> bool:
    """Confirm reset operation with user."""
    if force:
        return True
    
    print("\n" + "="*60)
    colored_print("⚠️  DATABASE RESET CONFIRMATION", Colors.YELLOW)
    print("="*60)
    
    colored_print("WARNING: This operation will permanently delete all data!", Colors.RED)
    print()
    print(f"Environment: {environment}")
    print(f"Databases to reset: {', '.join(sorted(databases))}")
    print()
    colored_print("This action cannot be undone!", Colors.RED)
    print()
    
    while True:
        response = input("Are you sure you want to continue? (yes/no): ").lower().strip()
        if response in ["yes", "y"]:
            return True
        elif response in ["no", "n"]:
            return False
        else:
            print("Please enter 'yes' or 'no'")

async def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Reset databases for Multimodal Librarian",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --all                           # Reset all databases
  %(prog)s --databases postgresql,neo4j    # Reset specific databases
  %(prog)s --all --backup                  # Reset with backup
  %(prog)s --all --dry-run                 # Show what would be reset
  %(prog)s --all --force                   # Skip confirmation
        """
    )
    
    # Database selection
    parser.add_argument(
        "--all", 
        action="store_true",
        help="Reset all databases"
    )
    parser.add_argument(
        "--databases",
        type=str,
        help="Comma-separated list of databases to reset (postgresql,neo4j,milvus,redis)"
    )
    
    # Options
    parser.add_argument(
        "--backup",
        action="store_true",
        help="Create backup before reset"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Skip confirmation prompts (dangerous!)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be reset without making changes"
    )
    parser.add_argument(
        "--environment",
        choices=["local", "aws"],
        help="Override environment detection"
    )
    parser.add_argument(
        "--backup-dir",
        default="./backups",
        help="Directory for backups (default: ./backups)"
    )
    
    # Logging
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress non-error output"
    )
    
    args = parser.parse_args()
    
    # Configure logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    elif args.quiet:
        logging.getLogger().setLevel(logging.ERROR)
    
    # Determine databases to reset
    if args.all:
        databases = {"postgresql", "neo4j", "milvus", "redis"}
    elif args.databases:
        databases = set(db.strip() for db in args.databases.split(","))
        valid_databases = {"postgresql", "neo4j", "milvus", "opensearch", "redis"}
        invalid = databases - valid_databases
        if invalid:
            log_error(f"Invalid databases: {', '.join(invalid)}")
            log_info(f"Valid databases: {', '.join(valid_databases)}")
            return 1
    else:
        log_error("Must specify --all or --databases")
        return 1
    
    try:
        # Get database configuration
        if args.environment:
            os.environ["ML_ENVIRONMENT"] = args.environment
        
        config = get_database_config()
        log_info(f"Using {config.database_type} environment")
        
        # Initialize reset manager
        reset_manager = DatabaseResetManager(config)
        await reset_manager.initialize()
        
        try:
            # Check database health
            health_status = await reset_manager.check_database_health()
            
            # Filter databases based on availability
            available_services = set()
            for service, status in health_status.get("services", {}).items():
                if status.get("status") == "healthy":
                    # Map service names to database names
                    if service == "relational":
                        available_services.add("postgresql")
                    elif service == "graph":
                        available_services.add("neo4j")
                    elif service == "vector":
                        if config.database_type == "local":
                            available_services.add("milvus")
                        else:
                            available_services.add("opensearch")
            
            # Add Redis if it's in the original list (not managed by factory)
            if "redis" in databases:
                available_services.add("redis")
            
            # Filter requested databases to only available ones
            databases_to_reset = databases & available_services
            unavailable = databases - available_services
            
            if unavailable:
                log_warning(f"Skipping unavailable databases: {', '.join(unavailable)}")
            
            if not databases_to_reset:
                log_error("No available databases to reset")
                return 1
            
            # Confirm reset operation
            if not confirm_reset(databases_to_reset, config.database_type, args.force):
                log_info("Reset cancelled by user")
                return 0
            
            # Create backup if requested
            if args.backup and not args.dry_run:
                backup_path = await reset_manager.create_backup_before_reset(args.backup_dir)
                if not backup_path:
                    log_warning("Backup creation failed, continuing with reset...")
            
            # Perform reset
            results = await reset_manager.reset_databases(databases_to_reset, args.dry_run)
            
            # Print summary
            reset_manager.print_reset_summary(results)
            
            # Return appropriate exit code
            if all(results.values()):
                return 0
            else:
                return 1
                
        finally:
            await reset_manager.cleanup()
            
    except KeyboardInterrupt:
        log_warning("Reset cancelled by user")
        return 1
    except Exception as e:
        log_error(f"Reset failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))