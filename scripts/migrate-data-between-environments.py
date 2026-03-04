#!/usr/bin/env python3
"""
Data Migration Utility Between Environments

This script provides high-level data migration between local development
and AWS production environments for the Multimodal Librarian application.

It combines export and import operations with environment switching,
data transformation, and validation to ensure safe migrations.

Usage:
    python scripts/migrate-data-between-environments.py [OPTIONS]

Examples:
    # Migrate from local to AWS
    python scripts/migrate-data-between-environments.py --from local --to aws

    # Migrate specific databases
    python scripts/migrate-data-between-environments.py --from aws --to local --databases postgresql,neo4j

    # Dry run migration
    python scripts/migrate-data-between-environments.py --from local --to aws --dry-run

    # Migration with data transformation
    python scripts/migrate-data-between-environments.py --from local --to aws --transform
"""

import asyncio
import argparse
import json
import logging
import os
import sys
import tempfile
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Literal
from dataclasses import dataclass, asdict

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.multimodal_librarian.config.config_factory import get_database_config
from src.multimodal_librarian.clients.database_client_factory import DatabaseClientFactory

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Type aliases
Environment = Literal["local", "aws"]
DatabaseType = Literal["postgresql", "neo4j", "milvus"]


@dataclass
class MigrationPlan:
    """Migration execution plan."""
    source_env: Environment
    target_env: Environment
    databases: List[DatabaseType]
    transform_data: bool
    dry_run: bool
    temp_dir: str
    timestamp: str


@dataclass
class MigrationResult:
    """Result of a migration operation."""
    success: bool
    source_env: Environment
    target_env: Environment
    databases_migrated: List[str]
    databases_failed: List[str]
    total_records: int
    duration_seconds: float
    temp_dir: Optional[str] = None
    error: Optional[str] = None
    warnings: List[str] = None
    
    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


class DataMigrator:
    """
    High-level data migration between environments.
    
    This class orchestrates the complete migration process including
    export, transformation, validation, and import operations.
    """
    
    def __init__(
        self,
        source_env: Environment,
        target_env: Environment,
        databases: Optional[List[DatabaseType]] = None,
        transform_data: bool = True,
        dry_run: bool = False,
        cleanup_temp: bool = True
    ):
        """
        Initialize the data migrator.
        
        Args:
            source_env: Source environment (local or aws)
            target_env: Target environment (local or aws)
            databases: List of databases to migrate (None = all)
            transform_data: Whether to transform data for target environment
            dry_run: Whether to perform validation without actual migration
            cleanup_temp: Whether to clean up temporary files after migration
        """
        self.source_env = source_env
        self.target_env = target_env
        self.databases = databases or ["postgresql", "neo4j", "milvus"]
        self.transform_data = transform_data
        self.dry_run = dry_run
        self.cleanup_temp = cleanup_temp
        
        # Create temporary directory for migration
        self.temp_dir = tempfile.mkdtemp(prefix="ml_migration_")
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        logger.info(f"Initialized migrator: {source_env} -> {target_env}")
        logger.info(f"Databases: {', '.join(self.databases)}")
        logger.info(f"Temporary directory: {self.temp_dir}")
        
        if self.dry_run:
            logger.info("DRY RUN MODE: No data will be actually migrated")
    
    async def migrate(self) -> MigrationResult:
        """
        Execute the complete migration process.
        
        Returns:
            MigrationResult with migration status and statistics
        """
        start_time = datetime.now()
        
        try:
            # Create migration plan
            plan = MigrationPlan(
                source_env=self.source_env,
                target_env=self.target_env,
                databases=self.databases,
                transform_data=self.transform_data,
                dry_run=self.dry_run,
                temp_dir=self.temp_dir,
                timestamp=self.timestamp
            )
            
            # Save migration plan
            await self._save_migration_plan(plan)
            
            # Step 1: Export data from source environment
            logger.info(f"Step 1: Exporting data from {self.source_env} environment...")
            export_result = await self._export_from_source()
            
            if not export_result["success"]:
                return MigrationResult(
                    success=False,
                    source_env=self.source_env,
                    target_env=self.target_env,
                    databases_migrated=[],
                    databases_failed=self.databases,
                    total_records=0,
                    duration_seconds=(datetime.now() - start_time).total_seconds(),
                    error=f"Export failed: {export_result['error']}"
                )
            
            # Step 2: Transform data if requested
            if self.transform_data:
                logger.info(f"Step 2: Transforming data for {self.target_env} environment...")
                transform_result = await self._transform_data()
                
                if not transform_result["success"]:
                    return MigrationResult(
                        success=False,
                        source_env=self.source_env,
                        target_env=self.target_env,
                        databases_migrated=[],
                        databases_failed=self.databases,
                        total_records=0,
                        duration_seconds=(datetime.now() - start_time).total_seconds(),
                        error=f"Transformation failed: {transform_result['error']}"
                    )
            
            # Step 3: Validate target environment
            logger.info(f"Step 3: Validating {self.target_env} environment...")
            validation_result = await self._validate_target_environment()
            
            if not validation_result["success"]:
                return MigrationResult(
                    success=False,
                    source_env=self.source_env,
                    target_env=self.target_env,
                    databases_migrated=[],
                    databases_failed=self.databases,
                    total_records=0,
                    duration_seconds=(datetime.now() - start_time).total_seconds(),
                    error=f"Target validation failed: {validation_result['error']}"
                )
            
            # Step 4: Import data to target environment
            if not self.dry_run:
                logger.info(f"Step 4: Importing data to {self.target_env} environment...")
                import_result = await self._import_to_target()
                
                if not import_result["success"]:
                    return MigrationResult(
                        success=False,
                        source_env=self.source_env,
                        target_env=self.target_env,
                        databases_migrated=import_result.get("successful", []),
                        databases_failed=import_result.get("failed", self.databases),
                        total_records=import_result.get("total_records", 0),
                        duration_seconds=(datetime.now() - start_time).total_seconds(),
                        error=f"Import failed: {import_result['error']}"
                    )
            else:
                logger.info("Step 4: Skipped (dry run mode)")
                import_result = {
                    "success": True,
                    "successful": self.databases,
                    "failed": [],
                    "total_records": export_result.get("total_records", 0)
                }
            
            # Step 5: Verify migration
            if not self.dry_run:
                logger.info(f"Step 5: Verifying migration...")
                verification_result = await self._verify_migration()
            else:
                verification_result = {"success": True, "warnings": []}
            
            duration = (datetime.now() - start_time).total_seconds()
            
            result = MigrationResult(
                success=True,
                source_env=self.source_env,
                target_env=self.target_env,
                databases_migrated=import_result.get("successful", []),
                databases_failed=import_result.get("failed", []),
                total_records=import_result.get("total_records", 0),
                duration_seconds=duration,
                temp_dir=self.temp_dir if not self.cleanup_temp else None,
                warnings=verification_result.get("warnings", [])
            )
            
            # Save migration result
            await self._save_migration_result(result)
            
            return result
            
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            logger.error(f"Migration failed: {e}")
            
            return MigrationResult(
                success=False,
                source_env=self.source_env,
                target_env=self.target_env,
                databases_migrated=[],
                databases_failed=self.databases,
                total_records=0,
                duration_seconds=duration,
                error=str(e)
            )
        
        finally:
            # Cleanup temporary files if requested
            if self.cleanup_temp and not self.dry_run:
                await self._cleanup_temp_files()
    
    async def _export_from_source(self) -> Dict[str, Any]:
        """Export data from source environment."""
        try:
            # Set environment for source
            os.environ["ML_ENVIRONMENT"] = self.source_env
            
            # Import and run export script
            from scripts.export_database_data import DatabaseExporter
            
            exporter = DatabaseExporter(
                output_dir=self.temp_dir,
                format="json",
                compress=True,
                include_metadata=True
            )
            
            try:
                results = await exporter.export_all_databases(self.databases)
                
                # Check results
                successful = [db for db, result in results.items() if result.success]
                failed = [db for db, result in results.items() if not result.success]
                total_records = sum(result.record_count for result in results.values() if result.success)
                
                if not successful:
                    return {
                        "success": False,
                        "error": "No databases exported successfully",
                        "failed": failed
                    }
                
                return {
                    "success": True,
                    "successful": successful,
                    "failed": failed,
                    "total_records": total_records,
                    "results": results
                }
                
            finally:
                await exporter.close()
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _transform_data(self) -> Dict[str, Any]:
        """Transform data for target environment."""
        try:
            # Find exported files
            export_files = list(Path(self.temp_dir).glob("*.json.gz"))
            
            if not export_files:
                return {
                    "success": False,
                    "error": "No export files found for transformation"
                }
            
            transformed_count = 0
            
            for export_file in export_files:
                try:
                    # Load and transform data
                    import gzip
                    import json
                    
                    with gzip.open(export_file, 'rt') as f:
                        data = json.load(f)
                    
                    # Apply transformations based on source/target environments
                    transformed_data = await self._apply_transformations(data, export_file.name)
                    
                    # Save transformed data
                    transformed_file = export_file.with_suffix('.transformed.json.gz')
                    with gzip.open(transformed_file, 'wt') as f:
                        json.dump(transformed_data, f, indent=2, default=str)
                    
                    transformed_count += 1
                    logger.debug(f"Transformed {export_file.name}")
                    
                except Exception as e:
                    logger.warning(f"Failed to transform {export_file}: {e}")
            
            return {
                "success": True,
                "transformed_files": transformed_count
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _apply_transformations(
        self, 
        data: Dict[str, Any], 
        filename: str
    ) -> Dict[str, Any]:
        """Apply environment-specific data transformations."""
        # Determine database type from filename
        if "postgresql" in filename:
            return await self._transform_postgresql_data(data)
        elif "neo4j" in filename:
            return await self._transform_neo4j_data(data)
        elif "milvus" in filename:
            return await self._transform_milvus_data(data)
        else:
            return data
    
    async def _transform_postgresql_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Transform PostgreSQL data for target environment."""
        # Example transformations:
        # - Update connection strings
        # - Modify user IDs or references
        # - Adjust configuration values
        
        transformed_data = data.copy()
        
        # Add transformation logic here based on requirements
        # For now, return data as-is
        
        return transformed_data
    
    async def _transform_neo4j_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Transform Neo4j data for target environment."""
        # Example transformations:
        # - Update node properties
        # - Modify relationship types
        # - Adjust graph structure
        
        transformed_data = data.copy()
        
        # Add transformation logic here based on requirements
        # For now, return data as-is
        
        return transformed_data
    
    async def _transform_milvus_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Transform Milvus data for target environment."""
        # Example transformations:
        # - Update collection configurations
        # - Modify vector dimensions
        # - Adjust index parameters
        
        transformed_data = data.copy()
        
        # Add transformation logic here based on requirements
        # For now, return data as-is
        
        return transformed_data
    
    async def _validate_target_environment(self) -> Dict[str, Any]:
        """Validate target environment is ready for import."""
        try:
            # Set environment for target
            os.environ["ML_ENVIRONMENT"] = self.target_env
            
            # Test database connections
            from src.multimodal_librarian.config.config_factory import get_database_config
            from src.multimodal_librarian.clients.database_client_factory import DatabaseClientFactory
            
            config = get_database_config()
            factory = DatabaseClientFactory(config)
            
            try:
                # Perform health checks
                health_status = await factory.health_check()
                
                if health_status["overall_status"] != "healthy":
                    return {
                        "success": False,
                        "error": f"Target environment not healthy: {health_status}"
                    }
                
                return {
                    "success": True,
                    "health_status": health_status
                }
                
            finally:
                await factory.close()
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _import_to_target(self) -> Dict[str, Any]:
        """Import data to target environment."""
        try:
            # Set environment for target
            os.environ["ML_ENVIRONMENT"] = self.target_env
            
            # Import and run import script
            from scripts.import_database_data import DatabaseImporter
            
            importer = DatabaseImporter(
                import_path=self.temp_dir,
                mode="replace",
                validate=True,
                dry_run=False,
                batch_size=1000
            )
            
            try:
                results = await importer.import_all_databases(self.databases)
                
                # Check results
                successful = [db for db, result in results.items() if result.success]
                failed = [db for db, result in results.items() if not result.success]
                total_records = sum(result.records_imported for result in results.values())
                
                return {
                    "success": len(failed) == 0,
                    "successful": successful,
                    "failed": failed,
                    "total_records": total_records,
                    "results": results,
                    "error": f"Failed databases: {failed}" if failed else None
                }
                
            finally:
                await importer.close()
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "successful": [],
                "failed": self.databases
            }
    
    async def _verify_migration(self) -> Dict[str, Any]:
        """Verify migration was successful."""
        try:
            warnings = []
            
            # Set environment for target
            os.environ["ML_ENVIRONMENT"] = self.target_env
            
            # Perform basic verification
            from src.multimodal_librarian.config.config_factory import get_database_config
            from src.multimodal_librarian.clients.database_client_factory import DatabaseClientFactory
            
            config = get_database_config()
            factory = DatabaseClientFactory(config)
            
            try:
                # Check database health
                health_status = await factory.health_check()
                
                if health_status["overall_status"] != "healthy":
                    warnings.append(f"Target environment health degraded after migration: {health_status}")
                
                # TODO: Add more specific verification checks
                # - Compare record counts
                # - Verify data integrity
                # - Check relationships and constraints
                
                return {
                    "success": True,
                    "warnings": warnings,
                    "health_status": health_status
                }
                
            finally:
                await factory.close()
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "warnings": [f"Verification failed: {e}"]
            }
    
    async def _save_migration_plan(self, plan: MigrationPlan) -> None:
        """Save migration plan to file."""
        plan_file = Path(self.temp_dir) / "migration_plan.json"
        with open(plan_file, 'w') as f:
            json.dump(asdict(plan), f, indent=2, default=str)
        
        logger.debug(f"Migration plan saved to {plan_file}")
    
    async def _save_migration_result(self, result: MigrationResult) -> None:
        """Save migration result to file."""
        result_file = Path(self.temp_dir) / "migration_result.json"
        with open(result_file, 'w') as f:
            json.dump(asdict(result), f, indent=2, default=str)
        
        logger.info(f"Migration result saved to {result_file}")
    
    async def _cleanup_temp_files(self) -> None:
        """Clean up temporary files."""
        try:
            if Path(self.temp_dir).exists():
                shutil.rmtree(self.temp_dir)
                logger.debug(f"Cleaned up temporary directory: {self.temp_dir}")
        except Exception as e:
            logger.warning(f"Failed to clean up temporary directory: {e}")


async def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Migrate data between Multimodal Librarian environments",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --from local --to aws                    # Migrate from local to AWS
  %(prog)s --from aws --to local                    # Migrate from AWS to local
  %(prog)s --from local --to aws --databases postgresql,neo4j  # Migrate specific databases
  %(prog)s --from local --to aws --dry-run          # Validate migration without executing
  %(prog)s --from local --to aws --no-transform     # Skip data transformation
  %(prog)s --from local --to aws --keep-temp        # Keep temporary files after migration
  
Environment Variables:
  ML_POSTGRES_HOST, ML_NEO4J_HOST, etc.            # Database connection settings for both environments
        """
    )
    
    parser.add_argument(
        "--from",
        dest="source_env",
        type=str,
        choices=["local", "aws"],
        required=True,
        help="Source environment"
    )
    
    parser.add_argument(
        "--to",
        dest="target_env",
        type=str,
        choices=["local", "aws"],
        required=True,
        help="Target environment"
    )
    
    parser.add_argument(
        "--databases",
        type=str,
        help="Comma-separated list of databases to migrate (postgresql,neo4j,milvus)"
    )
    
    parser.add_argument(
        "--no-transform",
        action="store_true",
        help="Skip data transformation for target environment"
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate migration without performing actual data transfer"
    )
    
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Keep temporary files after migration (for debugging)"
    )
    
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    # Configure logging
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Validate arguments
    if args.source_env == args.target_env:
        logger.error("Source and target environments cannot be the same")
        return 1
    
    # Parse databases list
    databases = None
    if args.databases:
        databases = [db.strip() for db in args.databases.split(",")]
        
        # Validate database names
        valid_databases = {"postgresql", "neo4j", "milvus"}
        invalid_databases = set(databases) - valid_databases
        if invalid_databases:
            logger.error(f"Invalid database names: {', '.join(invalid_databases)}")
            logger.error(f"Valid options: {', '.join(valid_databases)}")
            return 1
    
    # Initialize migrator
    migrator = DataMigrator(
        source_env=args.source_env,
        target_env=args.target_env,
        databases=databases,
        transform_data=not args.no_transform,
        dry_run=args.dry_run,
        cleanup_temp=not args.keep_temp
    )
    
    try:
        # Run migration
        result = await migrator.migrate()
        
        # Print summary
        print(f"\nMigration Summary:")
        print(f"  Source: {result.source_env}")
        print(f"  Target: {result.target_env}")
        print(f"  Success: {'Yes' if result.success else 'No'}")
        print(f"  Duration: {result.duration_seconds:.2f} seconds")
        
        if result.success:
            print(f"  Databases migrated: {len(result.databases_migrated)}")
            print(f"  Records migrated: {result.total_records:,}")
            
            if result.databases_migrated:
                print(f"  Successful: {', '.join(result.databases_migrated)}")
            
            if result.databases_failed:
                print(f"  Failed: {', '.join(result.databases_failed)}")
            
            if result.warnings:
                print(f"  Warnings:")
                for warning in result.warnings:
                    print(f"    - {warning}")
            
            if args.dry_run:
                print(f"  Mode: DRY RUN (no data was actually migrated)")
            
            if result.temp_dir:
                print(f"  Temporary files: {result.temp_dir}")
        else:
            print(f"  Error: {result.error}")
            if result.databases_failed:
                print(f"  Failed databases: {', '.join(result.databases_failed)}")
        
        return 0 if result.success else 1
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)