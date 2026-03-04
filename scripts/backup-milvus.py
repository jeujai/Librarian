#!/usr/bin/env python3

"""
Milvus Backup Script for Multimodal Librarian Local Development
This script creates backups of Milvus vector database collections
"""

import asyncio
import json
import os
import sys
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

try:
    from pymilvus import connections, Collection, utility
    from pymilvus.exceptions import MilvusException
    PYMILVUS_AVAILABLE = True
except ImportError:
    logger.warning("PyMilvus not available. Some backup features will be limited.")
    PYMILVUS_AVAILABLE = False

# Configuration
MILVUS_HOST = os.getenv("MILVUS_HOST", "localhost")
MILVUS_PORT = int(os.getenv("MILVUS_PORT", "19530"))
BACKUP_DIR = Path(os.getenv("BACKUP_DIR", "./backups/milvus"))
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

class Colors:
    """ANSI color codes for terminal output"""
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    NC = '\033[0m'  # No Color

def log(message: str, level: str = "INFO"):
    """Colored logging function"""
    color = {
        "INFO": Colors.BLUE,
        "ERROR": Colors.RED,
        "SUCCESS": Colors.GREEN,
        "WARNING": Colors.YELLOW
    }.get(level, Colors.NC)
    
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"{color}[{timestamp}]{Colors.NC} {message}")

def error(message: str):
    log(message, "ERROR")

def success(message: str):
    log(message, "SUCCESS")

def warning(message: str):
    log(message, "WARNING")

class MilvusBackupManager:
    """Manages Milvus database backups"""
    
    def __init__(self, host: str = MILVUS_HOST, port: int = MILVUS_PORT, backup_dir: Path = BACKUP_DIR):
        self.host = host
        self.port = port
        self.backup_dir = backup_dir
        self.connected = False
        
        # Create backup directory
        self.backup_dir.mkdir(parents=True, exist_ok=True)
    
    def connect(self) -> bool:
        """Connect to Milvus server"""
        if not PYMILVUS_AVAILABLE:
            error("PyMilvus not available. Cannot connect to Milvus.")
            return False
        
        try:
            connections.connect("default", host=self.host, port=self.port)
            self.connected = True
            success(f"Connected to Milvus at {self.host}:{self.port}")
            return True
        except Exception as e:
            error(f"Failed to connect to Milvus: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from Milvus server"""
        if self.connected and PYMILVUS_AVAILABLE:
            try:
                connections.disconnect("default")
                self.connected = False
                log("Disconnected from Milvus")
            except Exception as e:
                warning(f"Error during disconnect: {e}")
    
    def check_connectivity(self) -> bool:
        """Check if Milvus is accessible"""
        log("Checking Milvus connectivity...")
        
        if not PYMILVUS_AVAILABLE:
            error("PyMilvus not available")
            return False
        
        try:
            if not self.connected:
                if not self.connect():
                    return False
            
            # Test basic functionality
            collections = utility.list_collections()
            success("Milvus is accessible")
            log(f"Found {len(collections)} collections")
            return True
        except Exception as e:
            error(f"Milvus connectivity check failed: {e}")
            return False
    
    def list_collections(self) -> List[str]:
        """List all collections in Milvus"""
        if not self.connected:
            return []
        
        try:
            collections = utility.list_collections()
            return collections
        except Exception as e:
            error(f"Failed to list collections: {e}")
            return []
    
    def get_collection_info(self, collection_name: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a collection"""
        try:
            collection = Collection(collection_name)
            
            # Get basic info
            info = {
                "name": collection_name,
                "description": collection.description,
                "num_entities": collection.num_entities,
                "schema": {
                    "fields": [],
                    "description": collection.schema.description
                },
                "indexes": [],
                "partitions": []
            }
            
            # Get schema information
            for field in collection.schema.fields:
                field_info = {
                    "name": field.name,
                    "type": str(field.dtype),
                    "is_primary": field.is_primary,
                    "auto_id": field.auto_id,
                    "description": field.description
                }
                
                # Add dimension for vector fields
                if hasattr(field, 'params') and 'dim' in field.params:
                    field_info["dimension"] = field.params['dim']
                
                # Add max_length for varchar fields
                if hasattr(field, 'params') and 'max_length' in field.params:
                    field_info["max_length"] = field.params['max_length']
                
                info["schema"]["fields"].append(field_info)
            
            # Get index information
            try:
                indexes = collection.indexes
                for index in indexes:
                    index_info = {
                        "field_name": index.field_name,
                        "index_name": index.index_name,
                        "params": index.params
                    }
                    info["indexes"].append(index_info)
            except Exception as e:
                warning(f"Could not get index info for {collection_name}: {e}")
            
            # Get partition information
            try:
                partitions = collection.partitions
                for partition in partitions:
                    partition_info = {
                        "name": partition.name,
                        "description": partition.description,
                        "num_entities": partition.num_entities
                    }
                    info["partitions"].append(partition_info)
            except Exception as e:
                warning(f"Could not get partition info for {collection_name}: {e}")
            
            return info
        except Exception as e:
            error(f"Failed to get collection info for {collection_name}: {e}")
            return None
    
    def export_collection_data(self, collection_name: str, output_file: Path, 
                             batch_size: int = 1000, include_vectors: bool = True) -> bool:
        """Export collection data to JSON file"""
        try:
            collection = Collection(collection_name)
            
            # Load collection if not loaded
            if not utility.loading_progress(collection_name)["loading_progress"] == "100%":
                log(f"Loading collection {collection_name}...")
                collection.load()
            
            # Get all data
            log(f"Exporting data from collection {collection_name}...")
            
            # Determine output fields
            output_fields = ["*"]
            if not include_vectors:
                # Exclude vector fields
                vector_fields = [field.name for field in collection.schema.fields 
                               if str(field.dtype).startswith("FLOAT_VECTOR")]
                output_fields = [field.name for field in collection.schema.fields 
                               if field.name not in vector_fields]
            
            # Query all data in batches
            all_data = []
            offset = 0
            
            while True:
                try:
                    # Use query with limit and offset
                    results = collection.query(
                        expr="",
                        output_fields=output_fields,
                        limit=batch_size,
                        offset=offset
                    )
                    
                    if not results:
                        break
                    
                    all_data.extend(results)
                    offset += len(results)
                    
                    log(f"Exported {len(all_data)} entities so far...")
                    
                    # Break if we got fewer results than batch_size (end of data)
                    if len(results) < batch_size:
                        break
                        
                except Exception as e:
                    # Try without offset if not supported
                    if "offset" in str(e).lower():
                        log("Offset not supported, exporting all data at once...")
                        results = collection.query(expr="", output_fields=output_fields)
                        all_data = results
                        break
                    else:
                        raise e
            
            # Save to JSON file
            backup_data = {
                "collection_name": collection_name,
                "export_timestamp": datetime.now().isoformat(),
                "total_entities": len(all_data),
                "include_vectors": include_vectors,
                "data": all_data
            }
            
            with open(output_file, 'w') as f:
                json.dump(backup_data, f, indent=2, default=str)
            
            success(f"Exported {len(all_data)} entities to {output_file}")
            return True
            
        except Exception as e:
            error(f"Failed to export collection data: {e}")
            return False
    
    def export_collection_schema(self, collection_name: str, output_file: Path) -> bool:
        """Export collection schema to JSON file"""
        try:
            info = self.get_collection_info(collection_name)
            if not info:
                return False
            
            schema_data = {
                "collection_name": collection_name,
                "export_timestamp": datetime.now().isoformat(),
                "schema": info["schema"],
                "indexes": info["indexes"],
                "partitions": info["partitions"]
            }
            
            with open(output_file, 'w') as f:
                json.dump(schema_data, f, indent=2, default=str)
            
            success(f"Exported schema to {output_file}")
            return True
            
        except Exception as e:
            error(f"Failed to export collection schema: {e}")
            return False
    
    def create_collection_backup(self, collection_name: str, backup_type: str = "full") -> bool:
        """Create a backup of a specific collection"""
        log(f"Creating {backup_type} backup for collection: {collection_name}")
        
        # Create collection-specific backup directory
        collection_backup_dir = self.backup_dir / collection_name
        collection_backup_dir.mkdir(parents=True, exist_ok=True)
        
        success_count = 0
        
        if backup_type in ["full", "schema"]:
            # Export schema
            schema_file = collection_backup_dir / f"schema_{collection_name}_{TIMESTAMP}.json"
            if self.export_collection_schema(collection_name, schema_file):
                success_count += 1
        
        if backup_type in ["full", "data"]:
            # Export data without vectors (for size efficiency)
            data_file = collection_backup_dir / f"data_{collection_name}_{TIMESTAMP}.json"
            if self.export_collection_data(collection_name, data_file, include_vectors=False):
                success_count += 1
        
        if backup_type in ["full", "vectors"]:
            # Export data with vectors
            vectors_file = collection_backup_dir / f"vectors_{collection_name}_{TIMESTAMP}.json"
            if self.export_collection_data(collection_name, vectors_file, include_vectors=True):
                success_count += 1
        
        return success_count > 0
    
    def create_system_backup(self) -> bool:
        """Create a backup of system information"""
        log("Creating system backup...")
        
        try:
            system_info = {
                "backup_timestamp": datetime.now().isoformat(),
                "milvus_host": self.host,
                "milvus_port": self.port,
                "collections": []
            }
            
            # Get information about all collections
            collections = self.list_collections()
            for collection_name in collections:
                info = self.get_collection_info(collection_name)
                if info:
                    system_info["collections"].append(info)
            
            # Save system info
            system_file = self.backup_dir / f"system_info_{TIMESTAMP}.json"
            with open(system_file, 'w') as f:
                json.dump(system_info, f, indent=2, default=str)
            
            success(f"System backup created: {system_file}")
            return True
            
        except Exception as e:
            error(f"Failed to create system backup: {e}")
            return False
    
    def cleanup_old_backups(self, days: int = 7) -> int:
        """Clean up old backup files"""
        log(f"Cleaning up backups older than {days} days...")
        
        cutoff_date = datetime.now() - timedelta(days=days)
        deleted_count = 0
        
        try:
            for backup_file in self.backup_dir.rglob("*.json"):
                if backup_file.stat().st_mtime < cutoff_date.timestamp():
                    backup_file.unlink()
                    deleted_count += 1
            
            success(f"Cleaned up {deleted_count} old backup files")
            return deleted_count
            
        except Exception as e:
            error(f"Failed to clean up old backups: {e}")
            return 0
    
    def show_backup_stats(self):
        """Show backup statistics"""
        log("Milvus backup statistics:")
        print(f"Backup directory: {self.backup_dir}")
        
        if not self.backup_dir.exists():
            warning("Backup directory does not exist")
            return
        
        # Count backup files
        json_files = list(self.backup_dir.rglob("*.json"))
        total_size = sum(f.stat().st_size for f in json_files if f.is_file())
        
        print(f"Total backup files: {len(json_files)}")
        print(f"Total size: {total_size / (1024*1024):.2f} MB")
        print()
        
        # Show recent backups
        print("Recent backups:")
        recent_files = sorted(json_files, key=lambda f: f.stat().st_mtime, reverse=True)[:10]
        for backup_file in recent_files:
            size_mb = backup_file.stat().st_size / (1024*1024)
            mtime = datetime.fromtimestamp(backup_file.stat().st_mtime)
            print(f"  {backup_file.name} - {size_mb:.2f} MB - {mtime.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Show collections with backups
        print()
        print("Collections with backups:")
        for collection_dir in self.backup_dir.iterdir():
            if collection_dir.is_dir():
                backup_count = len(list(collection_dir.glob("*.json")))
                print(f"  {collection_dir.name}: {backup_count} backup files")

def main():
    """Main function"""
    parser = argparse.ArgumentParser(description="Milvus Backup Manager")
    parser.add_argument("action", nargs="?", default="system",
                       choices=["system", "collection", "all", "cleanup", "stats", "list"],
                       help="Backup action to perform")
    parser.add_argument("--collection", "-c", help="Collection name for collection-specific operations")
    parser.add_argument("--type", "-t", default="full", choices=["full", "schema", "data", "vectors"],
                       help="Type of backup to create")
    parser.add_argument("--host", default=MILVUS_HOST, help="Milvus host")
    parser.add_argument("--port", type=int, default=MILVUS_PORT, help="Milvus port")
    parser.add_argument("--backup-dir", type=Path, default=BACKUP_DIR, help="Backup directory")
    parser.add_argument("--days", type=int, default=7, help="Days to keep backups (for cleanup)")
    
    args = parser.parse_args()
    
    # Update backup directory
    backup_dir = args.backup_dir
    
    # Create backup manager
    manager = MilvusBackupManager(args.host, args.port)
    
    # Update manager's backup directory
    manager.backup_dir = backup_dir
    
    try:
        if args.action == "list":
            # Just list collections without connecting
            if not manager.check_connectivity():
                sys.exit(1)
            
            collections = manager.list_collections()
            if collections:
                print("Available collections:")
                for collection in collections:
                    print(f"  - {collection}")
            else:
                print("No collections found")
            return
        
        if args.action == "stats":
            manager.show_backup_stats()
            return
        
        if args.action == "cleanup":
            deleted = manager.cleanup_old_backups(args.days)
            if deleted > 0:
                success(f"Cleanup completed: {deleted} files deleted")
            else:
                log("No files to clean up")
            return
        
        # For other actions, check connectivity
        if not manager.check_connectivity():
            error("Cannot connect to Milvus. Please check if Milvus is running.")
            sys.exit(1)
        
        if args.action == "system":
            if manager.create_system_backup():
                success("System backup completed successfully")
            else:
                error("System backup failed")
                sys.exit(1)
        
        elif args.action == "collection":
            if not args.collection:
                error("Collection name is required for collection backup")
                sys.exit(1)
            
            if manager.create_collection_backup(args.collection, args.type):
                success(f"Collection backup completed for {args.collection}")
            else:
                error(f"Collection backup failed for {args.collection}")
                sys.exit(1)
        
        elif args.action == "all":
            # Backup system info
            manager.create_system_backup()
            
            # Backup all collections
            collections = manager.list_collections()
            success_count = 0
            
            for collection in collections:
                if manager.create_collection_backup(collection, args.type):
                    success_count += 1
            
            if success_count == len(collections):
                success(f"All backups completed successfully ({success_count} collections)")
            else:
                warning(f"Some backups failed. {success_count}/{len(collections)} collections backed up")
        
        # Show stats after backup operations
        if args.action in ["system", "collection", "all"]:
            print()
            manager.show_backup_stats()
    
    finally:
        manager.disconnect()

if __name__ == "__main__":
    main()