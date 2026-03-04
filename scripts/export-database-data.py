#!/usr/bin/env python3
"""
Database Data Export Utility for Multimodal Librarian

This script exports data from all database services (PostgreSQL, Neo4j, Milvus)
in a standardized format that can be imported into different environments.

Supports both local development and AWS production environments with automatic
format detection and conversion.

Usage:
    python scripts/export-database-data.py [OPTIONS]

Examples:
    # Export all data to default directory
    python scripts/export-database-data.py

    # Export specific databases
    python scripts/export-database-data.py --databases postgresql,neo4j

    # Export with compression
    python scripts/export-database-data.py --compress --format json

    # Export from AWS environment
    ML_ENVIRONMENT=aws python scripts/export-database-data.py

    # Export with custom output directory
    python scripts/export-database-data.py --output-dir ./exports/prod-backup
"""

import asyncio
import argparse
import json
import logging
import os
import sys
import gzip
import shutil
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
ExportFormat = Literal["json", "csv", "sql", "cypher"]
DatabaseType = Literal["postgresql", "neo4j", "milvus"]


@dataclass
class ExportMetadata:
    """Metadata for exported data."""
    export_timestamp: str
    source_environment: str
    database_type: str
    format: str
    record_count: int
    file_size_bytes: int
    schema_version: Optional[str] = None
    compression: Optional[str] = None
    checksum: Optional[str] = None


@dataclass
class ExportResult:
    """Result of a database export operation."""
    database_type: str
    success: bool
    file_path: Optional[str] = None
    metadata: Optional[ExportMetadata] = None
    error: Optional[str] = None
    record_count: int = 0
    duration_seconds: float = 0.0


class DatabaseExporter:
    """
    Comprehensive database data exporter.
    
    This class handles exporting data from all supported database types
    in multiple formats with metadata tracking and error handling.
    """
    
    def __init__(
        self,
        output_dir: str = "./exports",
        format: ExportFormat = "json",
        compress: bool = False,
        include_metadata: bool = True
    ):
        """
        Initialize the database exporter.
        
        Args:
            output_dir: Directory to store exported files
            format: Export format (json, csv, sql, cypher)
            compress: Whether to compress exported files
            include_metadata: Whether to include metadata files
        """
        self.output_dir = Path(output_dir)
        self.format = format
        self.compress = compress
        self.include_metadata = include_metadata
        
        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize database factory
        self.config = get_database_config()
        self.factory = DatabaseClientFactory(self.config)
        
        # Export session info
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_dir = self.output_dir / f"export_{self.session_id}"
        self.session_dir.mkdir(exist_ok=True)
        
        logger.info(f"Initialized exporter for {self.config.database_type} environment")
        logger.info(f"Export directory: {self.session_dir}")
    
    async def export_all_databases(
        self, 
        databases: Optional[List[DatabaseType]] = None
    ) -> Dict[str, ExportResult]:
        """
        Export data from all specified databases.
        
        Args:
            databases: List of databases to export (None = all available)
            
        Returns:
            Dictionary mapping database type to export result
        """
        if databases is None:
            databases = ["postgresql", "neo4j", "milvus"]
        
        results = {}
        
        logger.info(f"Starting export of databases: {', '.join(databases)}")
        
        # Export each database
        for db_type in databases:
            try:
                logger.info(f"Exporting {db_type} database...")
                result = await self._export_database(db_type)
                results[db_type] = result
                
                if result.success:
                    logger.info(
                        f"✓ {db_type}: {result.record_count} records exported "
                        f"in {result.duration_seconds:.2f}s"
                    )
                else:
                    logger.error(f"✗ {db_type}: {result.error}")
                    
            except Exception as e:
                logger.error(f"Failed to export {db_type}: {e}")
                results[db_type] = ExportResult(
                    database_type=db_type,
                    success=False,
                    error=str(e)
                )
        
        # Create export summary
        await self._create_export_summary(results)
        
        return results
    
    async def _export_database(self, db_type: DatabaseType) -> ExportResult:
        """Export data from a specific database type."""
        start_time = datetime.now()
        
        try:
            if db_type == "postgresql":
                return await self._export_postgresql()
            elif db_type == "neo4j":
                return await self._export_neo4j()
            elif db_type == "milvus":
                return await self._export_milvus()
            else:
                raise ValidationError(f"Unsupported database type: {db_type}")
                
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            return ExportResult(
                database_type=db_type,
                success=False,
                error=str(e),
                duration_seconds=duration
            )
    
    async def _export_postgresql(self) -> ExportResult:
        """Export PostgreSQL data."""
        start_time = datetime.now()
        
        try:
            # Get PostgreSQL client
            client: RelationalStoreClient = await self.factory.get_relational_client()
            
            # Get all tables
            tables_query = """
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """
            
            async with client.get_async_session() as session:
                from sqlalchemy import text
                result = await session.execute(text(tables_query))
                tables = [row[0] for row in result.fetchall()]
            
            logger.info(f"Found {len(tables)} PostgreSQL tables to export")
            
            # Export each table
            exported_data = {}
            total_records = 0
            
            for table_name in tables:
                try:
                    table_query = f"SELECT * FROM {table_name}"
                    table_data = await client.execute_query(table_query)
                    
                    exported_data[table_name] = {
                        "schema": await self._get_table_schema(client, table_name),
                        "data": table_data,
                        "record_count": len(table_data)
                    }
                    
                    total_records += len(table_data)
                    logger.debug(f"Exported {len(table_data)} records from {table_name}")
                    
                except Exception as e:
                    logger.warning(f"Failed to export table {table_name}: {e}")
                    exported_data[table_name] = {
                        "error": str(e),
                        "record_count": 0
                    }
            
            # Write export file
            file_path = await self._write_export_file(
                "postgresql", 
                exported_data, 
                total_records
            )
            
            duration = (datetime.now() - start_time).total_seconds()
            
            return ExportResult(
                database_type="postgresql",
                success=True,
                file_path=str(file_path),
                record_count=total_records,
                duration_seconds=duration,
                metadata=self._create_metadata(
                    "postgresql", 
                    file_path, 
                    total_records
                )
            )
            
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            raise DatabaseClientError(
                f"PostgreSQL export failed: {e}",
                original_exception=e
            )
    
    async def _export_neo4j(self) -> ExportResult:
        """Export Neo4j data."""
        start_time = datetime.now()
        
        try:
            # Get Neo4j client
            client: GraphStoreClient = await self.factory.get_graph_client()
            
            # Export nodes by label
            labels_query = "CALL db.labels() YIELD label RETURN label ORDER BY label"
            labels_result = await client.execute_query(labels_query)
            labels = [row["label"] for row in labels_result]
            
            logger.info(f"Found {len(labels)} Neo4j node labels to export")
            
            exported_data = {
                "nodes": {},
                "relationships": {},
                "schema": {
                    "labels": labels,
                    "relationship_types": []
                }
            }
            
            total_records = 0
            
            # Export nodes by label
            for label in labels:
                try:
                    nodes_query = f"MATCH (n:{label}) RETURN n"
                    nodes_result = await client.execute_query(nodes_query)
                    
                    # Convert Neo4j nodes to exportable format
                    nodes_data = []
                    for row in nodes_result:
                        node = row["n"]
                        nodes_data.append({
                            "id": str(node.id) if hasattr(node, 'id') else None,
                            "labels": list(node.labels) if hasattr(node, 'labels') else [label],
                            "properties": dict(node) if hasattr(node, 'items') else node
                        })
                    
                    exported_data["nodes"][label] = {
                        "data": nodes_data,
                        "record_count": len(nodes_data)
                    }
                    
                    total_records += len(nodes_data)
                    logger.debug(f"Exported {len(nodes_data)} nodes with label {label}")
                    
                except Exception as e:
                    logger.warning(f"Failed to export nodes with label {label}: {e}")
                    exported_data["nodes"][label] = {
                        "error": str(e),
                        "record_count": 0
                    }
            
            # Export relationships
            try:
                rel_types_query = "CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType ORDER BY relationshipType"
                rel_types_result = await client.execute_query(rel_types_query)
                rel_types = [row["relationshipType"] for row in rel_types_result]
                
                exported_data["schema"]["relationship_types"] = rel_types
                
                for rel_type in rel_types:
                    try:
                        rels_query = f"MATCH ()-[r:{rel_type}]->() RETURN r, startNode(r) as start, endNode(r) as end"
                        rels_result = await client.execute_query(rels_query)
                        
                        # Convert relationships to exportable format
                        rels_data = []
                        for row in rels_result:
                            rel = row["r"]
                            start_node = row["start"]
                            end_node = row["end"]
                            
                            rels_data.append({
                                "id": str(rel.id) if hasattr(rel, 'id') else None,
                                "type": rel_type,
                                "start_node_id": str(start_node.id) if hasattr(start_node, 'id') else None,
                                "end_node_id": str(end_node.id) if hasattr(end_node, 'id') else None,
                                "properties": dict(rel) if hasattr(rel, 'items') else rel
                            })
                        
                        exported_data["relationships"][rel_type] = {
                            "data": rels_data,
                            "record_count": len(rels_data)
                        }
                        
                        total_records += len(rels_data)
                        logger.debug(f"Exported {len(rels_data)} relationships of type {rel_type}")
                        
                    except Exception as e:
                        logger.warning(f"Failed to export relationships of type {rel_type}: {e}")
                        exported_data["relationships"][rel_type] = {
                            "error": str(e),
                            "record_count": 0
                        }
                        
            except Exception as e:
                logger.warning(f"Failed to export relationships: {e}")
                exported_data["relationships"] = {"error": str(e)}
            
            # Write export file
            file_path = await self._write_export_file(
                "neo4j", 
                exported_data, 
                total_records
            )
            
            duration = (datetime.now() - start_time).total_seconds()
            
            return ExportResult(
                database_type="neo4j",
                success=True,
                file_path=str(file_path),
                record_count=total_records,
                duration_seconds=duration,
                metadata=self._create_metadata(
                    "neo4j", 
                    file_path, 
                    total_records
                )
            )
            
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            raise DatabaseClientError(
                f"Neo4j export failed: {e}",
                original_exception=e
            )
    
    async def _export_milvus(self) -> ExportResult:
        """Export Milvus data."""
        start_time = datetime.now()
        
        try:
            # Get Milvus client
            client: VectorStoreClient = await self.factory.get_vector_client()
            
            # Get all collections
            collections = await client.list_collections()
            
            logger.info(f"Found {len(collections)} Milvus collections to export")
            
            exported_data = {
                "collections": {},
                "schema": {
                    "collection_names": collections
                }
            }
            
            total_records = 0
            
            # Export each collection
            for collection_name in collections:
                try:
                    # Get collection statistics
                    stats = await client.get_collection_stats(collection_name)
                    
                    # Note: Milvus doesn't have a direct "export all vectors" API
                    # We'll export metadata and collection info
                    # For actual vector data, we'd need to implement pagination
                    
                    exported_data["collections"][collection_name] = {
                        "stats": stats,
                        "record_count": stats.get("vector_count", 0),
                        "note": "Vector data export requires pagination - implement if needed"
                    }
                    
                    total_records += stats.get("vector_count", 0)
                    logger.debug(f"Exported metadata for collection {collection_name}")
                    
                except Exception as e:
                    logger.warning(f"Failed to export collection {collection_name}: {e}")
                    exported_data["collections"][collection_name] = {
                        "error": str(e),
                        "record_count": 0
                    }
            
            # Write export file
            file_path = await self._write_export_file(
                "milvus", 
                exported_data, 
                total_records
            )
            
            duration = (datetime.now() - start_time).total_seconds()
            
            return ExportResult(
                database_type="milvus",
                success=True,
                file_path=str(file_path),
                record_count=total_records,
                duration_seconds=duration,
                metadata=self._create_metadata(
                    "milvus", 
                    file_path, 
                    total_records
                )
            )
            
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            raise DatabaseClientError(
                f"Milvus export failed: {e}",
                original_exception=e
            )
    
    async def _get_table_schema(
        self, 
        client: RelationalStoreClient, 
        table_name: str
    ) -> Dict[str, Any]:
        """Get PostgreSQL table schema information."""
        try:
            schema_query = """
            SELECT 
                column_name,
                data_type,
                is_nullable,
                column_default,
                character_maximum_length
            FROM information_schema.columns 
            WHERE table_name = :table_name 
            AND table_schema = 'public'
            ORDER BY ordinal_position
            """
            
            schema_data = await client.execute_query(
                schema_query, 
                {"table_name": table_name}
            )
            
            return {
                "columns": schema_data,
                "table_name": table_name
            }
            
        except Exception as e:
            logger.warning(f"Failed to get schema for table {table_name}: {e}")
            return {"error": str(e)}
    
    async def _write_export_file(
        self, 
        db_type: str, 
        data: Dict[str, Any], 
        record_count: int
    ) -> Path:
        """Write exported data to file."""
        # Generate filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{db_type}_export_{timestamp}.{self.format}"
        
        if self.compress:
            filename += ".gz"
        
        file_path = self.session_dir / filename
        
        # Write data based on format
        if self.format == "json":
            content = json.dumps(data, indent=2, default=str)
        else:
            # For other formats, convert to JSON for now
            # TODO: Implement CSV, SQL, Cypher formats
            content = json.dumps(data, indent=2, default=str)
        
        # Write file (with optional compression)
        if self.compress:
            with gzip.open(file_path, 'wt', encoding='utf-8') as f:
                f.write(content)
        else:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
        
        logger.info(f"Exported {record_count} records to {file_path}")
        
        return file_path
    
    def _create_metadata(
        self, 
        db_type: str, 
        file_path: Path, 
        record_count: int
    ) -> ExportMetadata:
        """Create metadata for exported file."""
        file_size = file_path.stat().st_size if file_path.exists() else 0
        
        return ExportMetadata(
            export_timestamp=datetime.now().isoformat(),
            source_environment=self.config.database_type,
            database_type=db_type,
            format=self.format,
            record_count=record_count,
            file_size_bytes=file_size,
            compression="gzip" if self.compress else None
        )
    
    async def _create_export_summary(
        self, 
        results: Dict[str, ExportResult]
    ) -> None:
        """Create export summary file."""
        summary = {
            "export_session": {
                "session_id": self.session_id,
                "timestamp": datetime.now().isoformat(),
                "source_environment": self.config.database_type,
                "export_directory": str(self.session_dir)
            },
            "configuration": {
                "format": self.format,
                "compress": self.compress,
                "include_metadata": self.include_metadata
            },
            "results": {}
        }
        
        # Add results
        total_records = 0
        successful_exports = 0
        
        for db_type, result in results.items():
            summary["results"][db_type] = asdict(result)
            
            if result.success:
                successful_exports += 1
                total_records += result.record_count
        
        summary["summary"] = {
            "total_databases": len(results),
            "successful_exports": successful_exports,
            "failed_exports": len(results) - successful_exports,
            "total_records_exported": total_records
        }
        
        # Write summary file
        summary_path = self.session_dir / "export_summary.json"
        with open(summary_path, 'w') as f:
            json.dump(summary, f, indent=2, default=str)
        
        logger.info(f"Export summary written to {summary_path}")
        
        # Write metadata files if requested
        if self.include_metadata:
            for db_type, result in results.items():
                if result.success and result.metadata:
                    metadata_path = self.session_dir / f"{db_type}_metadata.json"
                    with open(metadata_path, 'w') as f:
                        json.dump(asdict(result.metadata), f, indent=2, default=str)
    
    async def close(self) -> None:
        """Clean up resources."""
        try:
            await self.factory.close()
        except Exception as e:
            logger.warning(f"Error closing database factory: {e}")


async def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Export data from Multimodal Librarian databases",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                                    # Export all databases to ./exports
  %(prog)s --databases postgresql,neo4j       # Export specific databases
  %(prog)s --output-dir ./my-exports          # Custom output directory
  %(prog)s --format json --compress           # Compressed JSON export
  %(prog)s --no-metadata                      # Skip metadata files
  
Environment Variables:
  ML_ENVIRONMENT=local|aws                    # Source environment
  ML_POSTGRES_HOST, ML_NEO4J_HOST, etc.      # Database connection settings
        """
    )
    
    parser.add_argument(
        "--databases",
        type=str,
        help="Comma-separated list of databases to export (postgresql,neo4j,milvus)"
    )
    
    parser.add_argument(
        "--output-dir",
        type=str,
        default="./exports",
        help="Output directory for exported files (default: ./exports)"
    )
    
    parser.add_argument(
        "--format",
        type=str,
        choices=["json", "csv", "sql", "cypher"],
        default="json",
        help="Export format (default: json)"
    )
    
    parser.add_argument(
        "--compress",
        action="store_true",
        help="Compress exported files with gzip"
    )
    
    parser.add_argument(
        "--no-metadata",
        action="store_true",
        help="Skip metadata file generation"
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
    
    # Initialize exporter
    exporter = DatabaseExporter(
        output_dir=args.output_dir,
        format=args.format,
        compress=args.compress,
        include_metadata=not args.no_metadata
    )
    
    try:
        # Run export
        results = await exporter.export_all_databases(databases)
        
        # Print summary
        successful = sum(1 for r in results.values() if r.success)
        total = len(results)
        total_records = sum(r.record_count for r in results.values() if r.success)
        
        print(f"\nExport Summary:")
        print(f"  Databases processed: {total}")
        print(f"  Successful exports: {successful}")
        print(f"  Failed exports: {total - successful}")
        print(f"  Total records exported: {total_records:,}")
        print(f"  Export directory: {exporter.session_dir}")
        
        # Show individual results
        for db_type, result in results.items():
            status = "✓" if result.success else "✗"
            if result.success:
                print(f"  {status} {db_type}: {result.record_count:,} records "
                      f"({result.duration_seconds:.2f}s)")
            else:
                print(f"  {status} {db_type}: {result.error}")
        
        return 0 if successful == total else 1
        
    except Exception as e:
        logger.error(f"Export failed: {e}")
        return 1
        
    finally:
        await exporter.close()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)