#!/usr/bin/env python3
"""
Database Data Import Utility for Multimodal Librarian

This script imports data into database services (PostgreSQL, Neo4j, Milvus)
from standardized export files created by export-database-data.py.

Supports importing between different environments (local <-> AWS) with
automatic format detection and data transformation.

Usage:
    python scripts/import-database-data.py [OPTIONS] IMPORT_PATH

Examples:
    # Import all data from export directory
    python scripts/import-database-data.py ./exports/export_20231201_120000/

    # Import specific databases
    python scripts/import-database-data.py --databases postgresql,neo4j ./exports/

    # Import with data validation
    python scripts/import-database-data.py --validate ./exports/export_20231201_120000/

    # Import to AWS environment
    ML_ENVIRONMENT=aws python scripts/import-database-data.py ./exports/

    # Dry run (validate without importing)
    python scripts/import-database-data.py --dry-run ./exports/export_20231201_120000/
"""

import asyncio
import argparse
import json
import logging
import os
import sys
import gzip
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Union, Literal
from dataclasses import dataclass, asdict

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.multimodal_librarian.config.config_factory import get_database_config
from src.multimodal_librarian.clients.database_client_factory import DatabaseClientFactory
from src.multimodal_librarian.clients.protocols import (
    RelationalStoreClient, VectorStoreClient, GraphStoreClient,
    DatabaseClientError, ConnectionError, ValidationError
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Type aliases
ImportMode = Literal["replace", "append", "update", "skip_existing"]
DatabaseType = Literal["postgresql", "neo4j", "milvus"]


@dataclass
class ImportResult:
    """Result of a database import operation."""
    database_type: str
    success: bool
    records_imported: int = 0
    records_skipped: int = 0
    records_failed: int = 0
    duration_seconds: float = 0.0
    error: Optional[str] = None
    warnings: List[str] = None
    
    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


@dataclass
class ImportFile:
    """Information about an import file."""
    path: Path
    database_type: str
    format: str
    compressed: bool
    metadata: Optional[Dict[str, Any]] = None


class DatabaseImporter:
    """
    Comprehensive database data importer.
    
    This class handles importing data into all supported database types
    with validation, error handling, and progress tracking.
    """
    
    def __init__(
        self,
        import_path: str,
        mode: ImportMode = "replace",
        validate: bool = True,
        dry_run: bool = False,
        batch_size: int = 1000
    ):
        """
        Initialize the database importer.
        
        Args:
            import_path: Path to import directory or file
            mode: Import mode (replace, append, update, skip_existing)
            validate: Whether to validate data before importing
            dry_run: Whether to perform validation without actual import
            batch_size: Number of records to process in each batch
        """
        self.import_path = Path(import_path)
        self.mode = mode
        self.validate = validate
        self.dry_run = dry_run
        self.batch_size = batch_size
        
        # Initialize database factory
        self.config = get_database_config()
        self.factory = DatabaseClientFactory(self.config)
        
        logger.info(f"Initialized importer for {self.config.database_type} environment")
        logger.info(f"Import path: {self.import_path}")
        logger.info(f"Mode: {self.mode}, Validate: {self.validate}, Dry run: {self.dry_run}")
    
    async def import_all_databases(
        self, 
        databases: Optional[List[DatabaseType]] = None
    ) -> Dict[str, ImportResult]:
        """
        Import data into all specified databases.
        
        Args:
            databases: List of databases to import (None = all available)
            
        Returns:
            Dictionary mapping database type to import result
        """
        # Discover import files
        import_files = await self._discover_import_files()
        
        if not import_files:
            logger.error("No import files found")
            return {}
        
        # Filter by requested databases
        if databases:
            import_files = {
                db: file for db, file in import_files.items() 
                if db in databases
            }
        
        logger.info(f"Found import files for: {', '.join(import_files.keys())}")
        
        results = {}
        
        # Import each database
        for db_type, import_file in import_files.items():
            try:
                logger.info(f"Importing {db_type} database from {import_file.path.name}...")
                result = await self._import_database(db_type, import_file)
                results[db_type] = result
                
                if result.success:
                    logger.info(
                        f"✓ {db_type}: {result.records_imported} records imported "
                        f"in {result.duration_seconds:.2f}s"
                    )
                    if result.records_skipped > 0:
                        logger.info(f"  Skipped: {result.records_skipped} records")
                    if result.records_failed > 0:
                        logger.warning(f"  Failed: {result.records_failed} records")
                else:
                    logger.error(f"✗ {db_type}: {result.error}")
                    
            except Exception as e:
                logger.error(f"Failed to import {db_type}: {e}")
                results[db_type] = ImportResult(
                    database_type=db_type,
                    success=False,
                    error=str(e)
                )
        
        return results
    
    async def _discover_import_files(self) -> Dict[str, ImportFile]:
        """Discover import files in the import path."""
        import_files = {}
        
        if self.import_path.is_file():
            # Single file import
            import_file = await self._analyze_import_file(self.import_path)
            if import_file:
                import_files[import_file.database_type] = import_file
        
        elif self.import_path.is_dir():
            # Directory import - look for export files
            for file_path in self.import_path.iterdir():
                if file_path.is_file():
                    import_file = await self._analyze_import_file(file_path)
                    if import_file:
                        import_files[import_file.database_type] = import_file
        
        else:
            raise ValidationError(f"Import path does not exist: {self.import_path}")
        
        return import_files
    
    async def _analyze_import_file(self, file_path: Path) -> Optional[ImportFile]:
        """Analyze a file to determine if it's a valid import file."""
        try:
            # Check file extension and naming pattern
            name = file_path.name
            
            # Detect database type from filename
            db_type = None
            if "postgresql" in name.lower():
                db_type = "postgresql"
            elif "neo4j" in name.lower():
                db_type = "neo4j"
            elif "milvus" in name.lower():
                db_type = "milvus"
            else:
                return None
            
            # Detect format and compression
            compressed = name.endswith('.gz')
            format_ext = name.replace('.gz', '').split('.')[-1]
            
            # Try to load metadata if available
            metadata = None
            metadata_path = file_path.parent / f"{db_type}_metadata.json"
            if metadata_path.exists():
                try:
                    with open(metadata_path, 'r') as f:
                        metadata = json.load(f)
                except Exception as e:
                    logger.warning(f"Failed to load metadata from {metadata_path}: {e}")
            
            return ImportFile(
                path=file_path,
                database_type=db_type,
                format=format_ext,
                compressed=compressed,
                metadata=metadata
            )
            
        except Exception as e:
            logger.debug(f"Failed to analyze file {file_path}: {e}")
            return None
    
    async def _import_database(
        self, 
        db_type: DatabaseType, 
        import_file: ImportFile
    ) -> ImportResult:
        """Import data into a specific database type."""
        start_time = datetime.now()
        
        try:
            # Load import data
            data = await self._load_import_data(import_file)
            
            # Validate data if requested
            if self.validate:
                validation_result = await self._validate_import_data(db_type, data)
                if not validation_result["valid"]:
                    return ImportResult(
                        database_type=db_type,
                        success=False,
                        error=f"Validation failed: {validation_result['error']}"
                    )
            
            # Perform import based on database type
            if self.dry_run:
                logger.info(f"Dry run: Would import {self._count_records(data)} records")
                return ImportResult(
                    database_type=db_type,
                    success=True,
                    records_imported=0,
                    duration_seconds=(datetime.now() - start_time).total_seconds()
                )
            
            if db_type == "postgresql":
                return await self._import_postgresql(data, start_time)
            elif db_type == "neo4j":
                return await self._import_neo4j(data, start_time)
            elif db_type == "milvus":
                return await self._import_milvus(data, start_time)
            else:
                raise ValidationError(f"Unsupported database type: {db_type}")
                
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            return ImportResult(
                database_type=db_type,
                success=False,
                error=str(e),
                duration_seconds=duration
            )
    
    async def _load_import_data(self, import_file: ImportFile) -> Dict[str, Any]:
        """Load data from import file."""
        try:
            if import_file.compressed:
                with gzip.open(import_file.path, 'rt', encoding='utf-8') as f:
                    content = f.read()
            else:
                with open(import_file.path, 'r', encoding='utf-8') as f:
                    content = f.read()
            
            # Parse based on format
            if import_file.format == "json":
                return json.loads(content)
            else:
                # For now, assume JSON format
                # TODO: Add support for other formats
                return json.loads(content)
                
        except Exception as e:
            raise ValidationError(f"Failed to load import file {import_file.path}: {e}")
    
    async def _validate_import_data(
        self, 
        db_type: DatabaseType, 
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate import data structure."""
        try:
            if db_type == "postgresql":
                return self._validate_postgresql_data(data)
            elif db_type == "neo4j":
                return self._validate_neo4j_data(data)
            elif db_type == "milvus":
                return self._validate_milvus_data(data)
            else:
                return {"valid": False, "error": f"Unknown database type: {db_type}"}
                
        except Exception as e:
            return {"valid": False, "error": str(e)}
    
    def _validate_postgresql_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate PostgreSQL import data."""
        if not isinstance(data, dict):
            return {"valid": False, "error": "Data must be a dictionary"}
        
        # Check for table data
        table_count = 0
        for key, value in data.items():
            if isinstance(value, dict) and "data" in value:
                table_count += 1
                
                # Validate table structure
                if not isinstance(value["data"], list):
                    return {"valid": False, "error": f"Table {key} data must be a list"}
        
        if table_count == 0:
            return {"valid": False, "error": "No valid table data found"}
        
        return {"valid": True, "tables": table_count}
    
    def _validate_neo4j_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate Neo4j import data."""
        if not isinstance(data, dict):
            return {"valid": False, "error": "Data must be a dictionary"}
        
        # Check for nodes and relationships
        if "nodes" not in data and "relationships" not in data:
            return {"valid": False, "error": "Data must contain 'nodes' or 'relationships'"}
        
        node_count = 0
        rel_count = 0
        
        if "nodes" in data:
            for label, node_data in data["nodes"].items():
                if isinstance(node_data, dict) and "data" in node_data:
                    node_count += len(node_data["data"])
        
        if "relationships" in data:
            for rel_type, rel_data in data["relationships"].items():
                if isinstance(rel_data, dict) and "data" in rel_data:
                    rel_count += len(rel_data["data"])
        
        return {"valid": True, "nodes": node_count, "relationships": rel_count}
    
    def _validate_milvus_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate Milvus import data."""
        if not isinstance(data, dict):
            return {"valid": False, "error": "Data must be a dictionary"}
        
        # Check for collections
        if "collections" not in data:
            return {"valid": False, "error": "Data must contain 'collections'"}
        
        collection_count = len(data["collections"])
        
        return {"valid": True, "collections": collection_count}
    
    def _count_records(self, data: Dict[str, Any]) -> int:
        """Count total records in import data."""
        total = 0
        
        def count_recursive(obj):
            nonlocal total
            if isinstance(obj, dict):
                if "data" in obj and isinstance(obj["data"], list):
                    total += len(obj["data"])
                else:
                    for value in obj.values():
                        count_recursive(value)
            elif isinstance(obj, list):
                total += len(obj)
        
        count_recursive(data)
        return total
    
    async def _import_postgresql(
        self, 
        data: Dict[str, Any], 
        start_time: datetime
    ) -> ImportResult:
        """Import PostgreSQL data."""
        try:
            client: RelationalStoreClient = await self.factory.get_relational_client()
            
            records_imported = 0
            records_skipped = 0
            records_failed = 0
            warnings = []
            
            # Import each table
            for table_name, table_data in data.items():
                if not isinstance(table_data, dict) or "data" not in table_data:
                    continue
                
                try:
                    table_records = table_data["data"]
                    
                    if not table_records:
                        logger.debug(f"Skipping empty table: {table_name}")
                        continue
                    
                    # Handle import mode
                    if self.mode == "replace":
                        # Clear existing data
                        try:
                            await client.execute_command(f"DELETE FROM {table_name}")
                            logger.debug(f"Cleared existing data from {table_name}")
                        except Exception as e:
                            warnings.append(f"Failed to clear table {table_name}: {e}")
                    
                    # Import records in batches
                    for i in range(0, len(table_records), self.batch_size):
                        batch = table_records[i:i + self.batch_size]
                        
                        try:
                            # Generate INSERT statements
                            for record in batch:
                                if not record:  # Skip empty records
                                    records_skipped += 1
                                    continue
                                
                                # Build INSERT query
                                columns = list(record.keys())
                                placeholders = [f":{col}" for col in columns]
                                
                                insert_query = f"""
                                INSERT INTO {table_name} ({', '.join(columns)})
                                VALUES ({', '.join(placeholders)})
                                """
                                
                                try:
                                    await client.execute_command(insert_query, record)
                                    records_imported += 1
                                except Exception as e:
                                    if self.mode == "skip_existing" and "duplicate" in str(e).lower():
                                        records_skipped += 1
                                    else:
                                        records_failed += 1
                                        logger.debug(f"Failed to insert record into {table_name}: {e}")
                        
                        except Exception as e:
                            logger.warning(f"Failed to import batch for table {table_name}: {e}")
                            records_failed += len(batch)
                    
                    logger.debug(f"Imported {len(table_records)} records into {table_name}")
                    
                except Exception as e:
                    logger.warning(f"Failed to import table {table_name}: {e}")
                    warnings.append(f"Table {table_name}: {e}")
            
            duration = (datetime.now() - start_time).total_seconds()
            
            return ImportResult(
                database_type="postgresql",
                success=True,
                records_imported=records_imported,
                records_skipped=records_skipped,
                records_failed=records_failed,
                duration_seconds=duration,
                warnings=warnings
            )
            
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            raise DatabaseClientError(
                f"PostgreSQL import failed: {e}",
                original_exception=e
            )
    
    async def _import_neo4j(
        self, 
        data: Dict[str, Any], 
        start_time: datetime
    ) -> ImportResult:
        """Import Neo4j data."""
        try:
            client: GraphStoreClient = await self.factory.get_graph_client()
            
            records_imported = 0
            records_skipped = 0
            records_failed = 0
            warnings = []
            
            # Clear existing data if replace mode
            if self.mode == "replace":
                try:
                    await client.execute_query("MATCH (n) DETACH DELETE n")
                    logger.debug("Cleared existing graph data")
                except Exception as e:
                    warnings.append(f"Failed to clear existing data: {e}")
            
            # Import nodes first
            if "nodes" in data:
                for label, node_data in data["nodes"].items():
                    if not isinstance(node_data, dict) or "data" not in node_data:
                        continue
                    
                    try:
                        nodes = node_data["data"]
                        
                        for node in nodes:
                            try:
                                # Create node
                                labels = node.get("labels", [label])
                                properties = node.get("properties", {})
                                
                                # Handle existing nodes based on mode
                                if self.mode == "skip_existing":
                                    # Check if node exists (simplified check)
                                    check_query = f"MATCH (n:{label}) WHERE n.id = $id RETURN count(n) as count"
                                    if "id" in properties:
                                        result = await client.execute_query(
                                            check_query, 
                                            {"id": properties["id"]}
                                        )
                                        if result and result[0]["count"] > 0:
                                            records_skipped += 1
                                            continue
                                
                                node_id = await client.create_node(labels, properties)
                                records_imported += 1
                                
                            except Exception as e:
                                records_failed += 1
                                logger.debug(f"Failed to create node: {e}")
                        
                        logger.debug(f"Imported {len(nodes)} nodes with label {label}")
                        
                    except Exception as e:
                        logger.warning(f"Failed to import nodes with label {label}: {e}")
                        warnings.append(f"Nodes {label}: {e}")
            
            # Import relationships
            if "relationships" in data:
                for rel_type, rel_data in data["relationships"].items():
                    if not isinstance(rel_data, dict) or "data" not in rel_data:
                        continue
                    
                    try:
                        relationships = rel_data["data"]
                        
                        for rel in relationships:
                            try:
                                # Create relationship
                                start_node_id = rel.get("start_node_id")
                                end_node_id = rel.get("end_node_id")
                                properties = rel.get("properties", {})
                                
                                if start_node_id and end_node_id:
                                    rel_id = await client.create_relationship(
                                        start_node_id, 
                                        end_node_id, 
                                        rel_type, 
                                        properties
                                    )
                                    records_imported += 1
                                else:
                                    records_skipped += 1
                                
                            except Exception as e:
                                records_failed += 1
                                logger.debug(f"Failed to create relationship: {e}")
                        
                        logger.debug(f"Imported {len(relationships)} relationships of type {rel_type}")
                        
                    except Exception as e:
                        logger.warning(f"Failed to import relationships of type {rel_type}: {e}")
                        warnings.append(f"Relationships {rel_type}: {e}")
            
            duration = (datetime.now() - start_time).total_seconds()
            
            return ImportResult(
                database_type="neo4j",
                success=True,
                records_imported=records_imported,
                records_skipped=records_skipped,
                records_failed=records_failed,
                duration_seconds=duration,
                warnings=warnings
            )
            
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            raise DatabaseClientError(
                f"Neo4j import failed: {e}",
                original_exception=e
            )
    
    async def _import_milvus(
        self, 
        data: Dict[str, Any], 
        start_time: datetime
    ) -> ImportResult:
        """Import Milvus data."""
        try:
            client: VectorStoreClient = await self.factory.get_vector_client()
            
            records_imported = 0
            records_skipped = 0
            records_failed = 0
            warnings = []
            
            # Import collections metadata
            if "collections" in data:
                for collection_name, collection_data in data["collections"].items():
                    try:
                        # For now, just recreate collections based on stats
                        if "stats" in collection_data:
                            stats = collection_data["stats"]
                            dimension = stats.get("dimension", 384)
                            
                            # Create collection if it doesn't exist
                            try:
                                success = await client.create_collection(
                                    collection_name, 
                                    dimension
                                )
                                if success:
                                    records_imported += 1
                                    logger.debug(f"Created collection {collection_name}")
                                else:
                                    records_skipped += 1
                                    logger.debug(f"Collection {collection_name} already exists")
                            except Exception as e:
                                records_failed += 1
                                logger.debug(f"Failed to create collection {collection_name}: {e}")
                        
                    except Exception as e:
                        logger.warning(f"Failed to import collection {collection_name}: {e}")
                        warnings.append(f"Collection {collection_name}: {e}")
            
            duration = (datetime.now() - start_time).total_seconds()
            
            return ImportResult(
                database_type="milvus",
                success=True,
                records_imported=records_imported,
                records_skipped=records_skipped,
                records_failed=records_failed,
                duration_seconds=duration,
                warnings=warnings
            )
            
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            raise DatabaseClientError(
                f"Milvus import failed: {e}",
                original_exception=e
            )
    
    async def close(self) -> None:
        """Clean up resources."""
        try:
            await self.factory.close()
        except Exception as e:
            logger.warning(f"Error closing database factory: {e}")


async def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Import data into Multimodal Librarian databases",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s ./exports/export_20231201_120000/     # Import from export directory
  %(prog)s --databases postgresql ./exports/     # Import specific databases
  %(prog)s --mode append ./exports/              # Append to existing data
  %(prog)s --dry-run ./exports/                  # Validate without importing
  %(prog)s --no-validate ./exports/              # Skip validation
  
Import Modes:
  replace       - Replace existing data (default)
  append        - Append to existing data
  update        - Update existing records
  skip_existing - Skip records that already exist
  
Environment Variables:
  ML_ENVIRONMENT=local|aws                       # Target environment
  ML_POSTGRES_HOST, ML_NEO4J_HOST, etc.         # Database connection settings
        """
    )
    
    parser.add_argument(
        "import_path",
        type=str,
        help="Path to import directory or file"
    )
    
    parser.add_argument(
        "--databases",
        type=str,
        help="Comma-separated list of databases to import (postgresql,neo4j,milvus)"
    )
    
    parser.add_argument(
        "--mode",
        type=str,
        choices=["replace", "append", "update", "skip_existing"],
        default="replace",
        help="Import mode (default: replace)"
    )
    
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="Skip data validation before import"
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate data without performing actual import"
    )
    
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1000,
        help="Number of records to process in each batch (default: 1000)"
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
    
    # Initialize importer
    importer = DatabaseImporter(
        import_path=args.import_path,
        mode=args.mode,
        validate=not args.no_validate,
        dry_run=args.dry_run,
        batch_size=args.batch_size
    )
    
    try:
        # Run import
        results = await importer.import_all_databases(databases)
        
        if not results:
            logger.error("No import files found or processed")
            return 1
        
        # Print summary
        successful = sum(1 for r in results.values() if r.success)
        total = len(results)
        total_imported = sum(r.records_imported for r in results.values())
        total_skipped = sum(r.records_skipped for r in results.values())
        total_failed = sum(r.records_failed for r in results.values())
        
        print(f"\nImport Summary:")
        print(f"  Databases processed: {total}")
        print(f"  Successful imports: {successful}")
        print(f"  Failed imports: {total - successful}")
        print(f"  Records imported: {total_imported:,}")
        print(f"  Records skipped: {total_skipped:,}")
        print(f"  Records failed: {total_failed:,}")
        
        if args.dry_run:
            print(f"  Mode: DRY RUN (no data was actually imported)")
        else:
            print(f"  Mode: {args.mode}")
        
        # Show individual results
        for db_type, result in results.items():
            status = "✓" if result.success else "✗"
            if result.success:
                print(f"  {status} {db_type}: {result.records_imported:,} imported, "
                      f"{result.records_skipped:,} skipped, "
                      f"{result.records_failed:,} failed "
                      f"({result.duration_seconds:.2f}s)")
                
                # Show warnings
                for warning in result.warnings:
                    print(f"    Warning: {warning}")
            else:
                print(f"  {status} {db_type}: {result.error}")
        
        return 0 if successful == total else 1
        
    except Exception as e:
        logger.error(f"Import failed: {e}")
        return 1
        
    finally:
        await importer.close()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)