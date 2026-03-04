#!/usr/bin/env python3

"""
Milvus Restore Script for Multimodal Librarian Local Development
This script restores Milvus vector database collections from backups
"""

import asyncio
import json
import os
import sys
import argparse
from datetime import datetime
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
    from pymilvus import connections, Collection, utility, FieldSchema, CollectionSchema, DataType
    from pymilvus.exceptions import MilvusException
    PYMILVUS_AVAILABLE = True
except ImportError:
    logger.warning("PyMilvus not available. Some restore features will be limited.")
    PYMILVUS_AVAILABLE = False

# Configuration
MILVUS_HOST = os.getenv("MILVUS_HOST", "localhost")
MILVUS_PORT = int(os.getenv("MILVUS_PORT", "19530"))
BACKUP_DIR = Path(os.getenv("BACKUP_DIR", "./backups/milvus"))

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

class MilvusRestoreManager:
    """Manages Milvus database restores"""
    
    def __init__(self, host: str = MILVUS_HOST, port: int = MILVUS_PORT, backup_dir: Path = BACKUP_DIR):
        self.host = host
        self.port = port
        self.backup_dir = backup_dir
        self.connected = False
    
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
            log(f"Current collections: {len(collections)}")
            return True
        except Exception as e:
            error(f"Milvus connectivity check failed: {e}")
            return False
    
    def list_backups(self) -> Dict[str, List[Path]]:
        """List all available backups"""
        log(f"Scanning for backups in {self.backup_dir}")
        
        if not self.backup_dir.exists():
            warning(f"Backup directory does not exist: {self.backup_dir}")
            return {}
        
        backups = {
            "system": [],
            "collections": {}
        }
        
        # Find system backups
        system_backups = list(self.backup_dir.glob("system_info_*.json"))
        backups["system"] = sorted(system_backups, key=lambda f: f.stat().st_mtime, reverse=True)
        
        # Find collection backups
        for collection_dir in self.backup_dir.iterdir():
            if collection_dir.is_dir():
                collection_name = collection_dir.name
                collection_backups = []
                
                # Find different types of collection backups
                for pattern in ["schema_*.json", "data_*.json", "vectors_*.json"]:
                    collection_backups.extend(collection_dir.glob(pattern))
                
                if collection_backups:
                    backups["collections"][collection_name] = sorted(
                        collection_backups, 
                        key=lambda f: f.stat().st_mtime, 
                        reverse=True
                    )
        
        return backups
    
    def show_backup_list(self):
        """Display available backups"""
        backups = self.list_backups()
        
        print("Available Milvus Backups:")
        print("=" * 50)
        
        # System backups
        print("\nSystem Backups:")
        if backups["system"]:
            for backup_file in backups["system"][:5]:  # Show latest 5
                size_mb = backup_file.stat().st_size / (1024*1024)
                mtime = datetime.fromtimestamp(backup_file.stat().st_mtime)
                print(f"  {backup_file.name} - {size_mb:.2f} MB - {mtime.strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            print("  No system backups found")
        
        # Collection backups
        print("\nCollection Backups:")
        if backups["collections"]:
            for collection_name, collection_backups in backups["collections"].items():
                print(f"  {collection_name}:")
                for backup_file in collection_backups[:3]:  # Show latest 3 per collection
                    size_mb = backup_file.stat().st_size / (1024*1024)
                    mtime = datetime.fromtimestamp(backup_file.stat().st_mtime)
                    backup_type = "schema" if "schema_" in backup_file.name else \
                                 "data" if "data_" in backup_file.name else "vectors"
                    print(f"    {backup_file.name} ({backup_type}) - {size_mb:.2f} MB - {mtime.strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            print("  No collection backups found")
    
    def get_latest_system_backup(self) -> Optional[Path]:
        """Get the latest system backup file"""
        backups = self.list_backups()
        if backups["system"]:
            return backups["system"][0]
        return None
    
    def load_backup_metadata(self, backup_file: Path) -> Optional[Dict[str, Any]]:
        """Load backup metadata from file"""
        try:
            with open(backup_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            error(f"Failed to load backup metadata: {e}")
            return None
    
    def create_collection_from_schema(self, schema_data: Dict[str, Any]) -> bool:
        """Create a collection from schema data"""
        try:
            collection_name = schema_data["collection_name"]
            schema_info = schema_data["schema"]
            
            log(f"Creating collection: {collection_name}")
            
            # Check if collection already exists
            if utility.has_collection(collection_name):
                warning(f"Collection {collection_name} already exists")
                response = input(f"Drop and recreate collection {collection_name}? (y/N): ")
                if response.lower() == 'y':
                    utility.drop_collection(collection_name)
                    log(f"Dropped existing collection: {collection_name}")
                else:
                    log(f"Skipping collection: {collection_name}")
                    return False
            
            # Create fields from schema
            fields = []
            for field_info in schema_info["fields"]:
                field_name = field_info["name"]
                field_type_str = field_info["type"]
                is_primary = field_info.get("is_primary", False)
                auto_id = field_info.get("auto_id", False)
                description = field_info.get("description", "")
                
                # Map string type to DataType
                type_mapping = {
                    "DataType.INT64": DataType.INT64,
                    "DataType.FLOAT_VECTOR": DataType.FLOAT_VECTOR,
                    "DataType.VARCHAR": DataType.VARCHAR,
                    "DataType.BOOL": DataType.BOOL,
                    "DataType.DOUBLE": DataType.DOUBLE,
                    "DataType.FLOAT": DataType.FLOAT,
                }
                
                field_type = type_mapping.get(field_type_str, DataType.VARCHAR)
                
                # Create field schema
                field_params = {}
                if "dimension" in field_info:
                    field_params["dim"] = field_info["dimension"]
                if "max_length" in field_info:
                    field_params["max_length"] = field_info["max_length"]
                
                field_schema = FieldSchema(
                    name=field_name,
                    dtype=field_type,
                    is_primary=is_primary,
                    auto_id=auto_id,
                    description=description,
                    **field_params
                )
                fields.append(field_schema)
            
            # Create collection schema
            collection_schema = CollectionSchema(
                fields=fields,
                description=schema_info.get("description", "")
            )
            
            # Create collection
            collection = Collection(
                name=collection_name,
                schema=collection_schema
            )
            
            success(f"Collection {collection_name} created successfully")
            
            # Create indexes if specified
            if "indexes" in schema_data:
                for index_info in schema_data["indexes"]:
                    try:
                        field_name = index_info["field_name"]
                        index_params = index_info["params"]
                        
                        collection.create_index(
                            field_name=field_name,
                            index_params=index_params
                        )
                        log(f"Created index on field: {field_name}")
                    except Exception as e:
                        warning(f"Failed to create index on {field_name}: {e}")
            
            return True
            
        except Exception as e:
            error(f"Failed to create collection from schema: {e}")
            return False
    
    def restore_collection_data(self, data_file: Path) -> bool:
        """Restore collection data from backup file"""
        try:
            log(f"Restoring collection data from: {data_file}")
            
            # Load backup data
            backup_data = self.load_backup_metadata(data_file)
            if not backup_data:
                return False
            
            collection_name = backup_data["collection_name"]
            entities_data = backup_data["data"]
            
            if not entities_data:
                warning(f"No data to restore for collection: {collection_name}")
                return True
            
            # Get collection
            if not utility.has_collection(collection_name):
                error(f"Collection {collection_name} does not exist. Create schema first.")
                return False
            
            collection = Collection(collection_name)
            
            # Prepare data for insertion
            # Group data by field names
            field_data = {}
            for entity in entities_data:
                for field_name, field_value in entity.items():
                    if field_name not in field_data:
                        field_data[field_name] = []
                    field_data[field_name].append(field_value)
            
            # Insert data in batches
            batch_size = 1000
            total_entities = len(entities_data)
            
            for i in range(0, total_entities, batch_size):
                batch_data = {}
                for field_name, values in field_data.items():
                    batch_data[field_name] = values[i:i+batch_size]
                
                # Insert batch
                collection.insert(list(batch_data.values()))
                log(f"Inserted batch {i//batch_size + 1}/{(total_entities + batch_size - 1)//batch_size}")
            
            # Flush to ensure data is persisted
            collection.flush()
            
            success(f"Restored {total_entities} entities to collection: {collection_name}")
            return True
            
        except Exception as e:
            error(f"Failed to restore collection data: {e}")
            return False
    
    def restore_system_backup(self, system_backup_file: Path) -> bool:
        """Restore system backup (recreate all collections)"""
        try:
            log(f"Restoring system backup from: {system_backup_file}")
            
            # Load system backup
            system_data = self.load_backup_metadata(system_backup_file)
            if not system_data:
                return False
            
            collections_info = system_data.get("collections", [])
            
            if not collections_info:
                warning("No collections found in system backup")
                return True
            
            success_count = 0
            
            for collection_info in collections_info:
                collection_name = collection_info["name"]
                
                log(f"Restoring collection: {collection_name}")
                
                # Create collection from schema
                schema_data = {
                    "collection_name": collection_name,
                    "schema": collection_info["schema"],
                    "indexes": collection_info.get("indexes", [])
                }
                
                if self.create_collection_from_schema(schema_data):
                    success_count += 1
                    
                    # Look for corresponding data backup
                    collection_backup_dir = self.backup_dir / collection_name
                    if collection_backup_dir.exists():
                        # Find latest data backup
                        data_backups = list(collection_backup_dir.glob("data_*.json"))
                        if data_backups:
                            latest_data_backup = max(data_backups, key=lambda f: f.stat().st_mtime)
                            self.restore_collection_data(latest_data_backup)
            
            success(f"System restore completed: {success_count}/{len(collections_info)} collections restored")
            return success_count > 0
            
        except Exception as e:
            error(f"Failed to restore system backup: {e}")
            return False
    
    def restore_collection_backup(self, collection_name: str, backup_type: str = "latest") -> bool:
        """Restore a specific collection backup"""
        try:
            log(f"Restoring collection: {collection_name}")
            
            collection_backup_dir = self.backup_dir / collection_name
            if not collection_backup_dir.exists():
                error(f"No backups found for collection: {collection_name}")
                return False
            
            # Find schema backup
            schema_backups = list(collection_backup_dir.glob("schema_*.json"))
            if not schema_backups:
                error(f"No schema backup found for collection: {collection_name}")
                return False
            
            latest_schema_backup = max(schema_backups, key=lambda f: f.stat().st_mtime)
            
            # Load and create collection from schema
            schema_data = self.load_backup_metadata(latest_schema_backup)
            if not schema_data:
                return False
            
            if not self.create_collection_from_schema(schema_data):
                return False
            
            # Restore data if available
            data_backups = list(collection_backup_dir.glob("data_*.json"))
            if data_backups:
                latest_data_backup = max(data_backups, key=lambda f: f.stat().st_mtime)
                return self.restore_collection_data(latest_data_backup)
            else:
                warning(f"No data backup found for collection: {collection_name}")
                return True
            
        except Exception as e:
            error(f"Failed to restore collection backup: {e}")
            return False
    
    def restore_from_file(self, backup_file: Path) -> bool:
        """Restore from a specific backup file"""
        try:
            log(f"Restoring from file: {backup_file}")
            
            if not backup_file.exists():
                error(f"Backup file not found: {backup_file}")
                return False
            
            # Determine backup type from filename
            if "system_info_" in backup_file.name:
                return self.restore_system_backup(backup_file)
            elif "schema_" in backup_file.name:
                # Load schema and create collection
                schema_data = self.load_backup_metadata(backup_file)
                if schema_data:
                    return self.create_collection_from_schema(schema_data)
            elif "data_" in backup_file.name or "vectors_" in backup_file.name:
                return self.restore_collection_data(backup_file)
            else:
                error(f"Unknown backup file type: {backup_file}")
                return False
            
        except Exception as e:
            error(f"Failed to restore from file: {e}")
            return False
    
    def verify_restore(self) -> bool:
        """Verify the restored data"""
        log("Verifying Milvus restore...")
        
        try:
            if not self.connected:
                if not self.connect():
                    return False
            
            collections = utility.list_collections()
            
            success(f"Restore verification completed")
            print(f"  Collections: {len(collections)}")
            
            for collection_name in collections:
                try:
                    collection = Collection(collection_name)
                    entity_count = collection.num_entities
                    print(f"    {collection_name}: {entity_count} entities")
                except Exception as e:
                    warning(f"    {collection_name}: Error getting entity count - {e}")
            
            return True
            
        except Exception as e:
            error(f"Restore verification failed: {e}")
            return False

def main():
    """Main function"""
    parser = argparse.ArgumentParser(description="Milvus Restore Manager")
    parser.add_argument("action", nargs="?", default="list",
                       choices=["list", "system", "collection", "file", "verify"],
                       help="Restore action to perform")
    parser.add_argument("--collection", "-c", help="Collection name for collection-specific operations")
    parser.add_argument("--file", "-f", type=Path, help="Specific backup file to restore from")
    parser.add_argument("--latest", action="store_true", help="Use latest backup")
    parser.add_argument("--host", default=MILVUS_HOST, help="Milvus host")
    parser.add_argument("--port", type=int, default=MILVUS_PORT, help="Milvus port")
    parser.add_argument("--backup-dir", type=Path, default=BACKUP_DIR, help="Backup directory")
    
    args = parser.parse_args()
    
    # Create restore manager
    manager = MilvusRestoreManager(args.host, args.port, args.backup_dir)
    
    try:
        if args.action == "list":
            manager.show_backup_list()
            return
        
        if args.action == "verify":
            if manager.check_connectivity():
                manager.verify_restore()
            else:
                error("Cannot connect to Milvus for verification")
                sys.exit(1)
            return
        
        # For restore actions, check connectivity
        if not manager.check_connectivity():
            error("Cannot connect to Milvus. Please check if Milvus is running.")
            sys.exit(1)
        
        if args.action == "system":
            if args.latest or args.file:
                if args.file:
                    backup_file = args.file
                else:
                    backup_file = manager.get_latest_system_backup()
                
                if backup_file and backup_file.exists():
                    if manager.restore_system_backup(backup_file):
                        success("System restore completed successfully")
                        manager.verify_restore()
                    else:
                        error("System restore failed")
                        sys.exit(1)
                else:
                    error("No system backup file found")
                    sys.exit(1)
            else:
                error("Please specify --latest or --file for system restore")
                sys.exit(1)
        
        elif args.action == "collection":
            if not args.collection:
                error("Collection name is required for collection restore")
                sys.exit(1)
            
            if manager.restore_collection_backup(args.collection):
                success(f"Collection restore completed for {args.collection}")
                manager.verify_restore()
            else:
                error(f"Collection restore failed for {args.collection}")
                sys.exit(1)
        
        elif args.action == "file":
            if not args.file:
                error("Backup file path is required for file restore")
                sys.exit(1)
            
            if manager.restore_from_file(args.file):
                success("File restore completed successfully")
                manager.verify_restore()
            else:
                error("File restore failed")
                sys.exit(1)
    
    finally:
        manager.disconnect()

if __name__ == "__main__":
    main()