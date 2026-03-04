#!/usr/bin/env python3
"""
Milvus Schema Initialization Script

This script initializes Milvus collections with predefined schemas for the
Multimodal Librarian application. It handles:

- Collection creation with proper schemas
- Index creation for optimal search performance
- Schema validation and migration
- Error handling and recovery
- Idempotent operations (safe to run multiple times)

Usage:
    # Initialize all default collections
    python database/milvus/init_schemas.py
    
    # Initialize specific collections
    python database/milvus/init_schemas.py --collections knowledge_chunks document_embeddings
    
    # Force recreation of existing collections
    python database/milvus/init_schemas.py --force
    
    # Validate existing schemas without changes
    python database/milvus/init_schemas.py --validate-only
"""

import sys
import time
import logging
import argparse
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

# Add the project root to the path so we can import from src
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

try:
    from pymilvus import (
        connections, Collection, CollectionSchema, FieldSchema, DataType,
        utility, MilvusException
    )
    PYMILVUS_AVAILABLE = True
except ImportError as e:
    PYMILVUS_AVAILABLE = False
    IMPORT_ERROR = str(e)

# Import our schema definitions
try:
    from database.milvus.schemas import (
        COLLECTION_SCHEMAS, DEFAULT_COLLECTIONS, OPTIONAL_COLLECTIONS,
        get_collection_schema, validate_schema_compatibility,
        get_embedding_dimension, get_index_parameters
    )
    SCHEMAS_AVAILABLE = True
except ImportError as e:
    SCHEMAS_AVAILABLE = False
    SCHEMA_IMPORT_ERROR = str(e)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MilvusSchemaInitializer:
    """Handles initialization of Milvus collection schemas"""
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 19530,
        connection_alias: str = "schema_init"
    ):
        self.host = host
        self.port = port
        self.connection_alias = connection_alias
        self.connected = False
        
        # Validate dependencies
        if not PYMILVUS_AVAILABLE:
            raise ImportError(f"pymilvus not available: {IMPORT_ERROR}")
        
        if not SCHEMAS_AVAILABLE:
            raise ImportError(f"Schema definitions not available: {SCHEMA_IMPORT_ERROR}")
    
    async def connect(self) -> None:
        """Connect to Milvus server"""
        try:
            logger.info(f"Connecting to Milvus at {self.host}:{self.port}")
            connections.connect(
                alias=self.connection_alias,
                host=self.host,
                port=str(self.port),
                timeout=30
            )
            
            # Test connection
            utility.list_collections(using=self.connection_alias)
            self.connected = True
            logger.info("Successfully connected to Milvus")
            
        except Exception as e:
            logger.error(f"Failed to connect to Milvus: {e}")
            raise
    
    def disconnect(self) -> None:
        """Disconnect from Milvus server"""
        if self.connected:
            try:
                connections.disconnect(alias=self.connection_alias)
                self.connected = False
                logger.info("Disconnected from Milvus")
            except Exception as e:
                logger.warning(f"Error during disconnect: {e}")
    
    def list_existing_collections(self) -> List[str]:
        """List existing collections in Milvus"""
        try:
            return utility.list_collections(using=self.connection_alias)
        except Exception as e:
            logger.error(f"Failed to list collections: {e}")
            return []
    
    def get_collection_info(self, collection_name: str) -> Optional[Dict[str, Any]]:
        """Get information about an existing collection"""
        try:
            if not utility.has_collection(collection_name, using=self.connection_alias):
                return None
            
            collection = Collection(collection_name, using=self.connection_alias)
            schema = collection.schema
            
            # Get field information
            fields = []
            for field in schema.fields:
                field_info = {
                    "name": field.name,
                    "type": str(field.dtype),
                    "is_primary": field.is_primary,
                    "description": field.description,
                    "params": getattr(field, 'params', {})
                }
                fields.append(field_info)
            
            # Get index information
            indexes = []
            try:
                collection_indexes = collection.indexes
                for index in collection_indexes:
                    index_info = {
                        "field_name": index.field_name,
                        "index_name": getattr(index, 'index_name', 'unknown'),
                        "index_type": index.params.get("index_type", "unknown"),
                        "metric_type": index.params.get("metric_type", "unknown"),
                        "params": index.params.get("params", {})
                    }
                    indexes.append(index_info)
            except Exception as e:
                logger.warning(f"Could not get index info for {collection_name}: {e}")
            
            return {
                "name": collection_name,
                "description": schema.description,
                "num_entities": collection.num_entities,
                "fields": fields,
                "indexes": indexes
            }
            
        except Exception as e:
            logger.error(f"Failed to get collection info for {collection_name}: {e}")
            return None
    
    def validate_collection_schema(self, collection_name: str) -> Tuple[bool, List[str]]:
        """
        Validate that an existing collection matches the expected schema.
        
        Returns:
            Tuple of (is_valid, list_of_issues)
        """
        issues = []
        
        try:
            # Get expected schema
            expected_config = get_collection_schema(collection_name)
            
            # Get existing collection info
            existing_info = self.get_collection_info(collection_name)
            if not existing_info:
                issues.append(f"Collection {collection_name} does not exist")
                return False, issues
            
            # Validate fields
            existing_fields = {f["name"]: f for f in existing_info["fields"]}
            expected_fields = {f.name: f for f in expected_config.fields}
            
            # Check for missing fields
            missing_fields = set(expected_fields.keys()) - set(existing_fields.keys())
            if missing_fields:
                issues.append(f"Missing fields: {missing_fields}")
            
            # Check for extra fields
            extra_fields = set(existing_fields.keys()) - set(expected_fields.keys())
            if extra_fields:
                issues.append(f"Extra fields: {extra_fields}")
            
            # Check field types and parameters
            for field_name, expected_field in expected_fields.items():
                if field_name in existing_fields:
                    existing_field = existing_fields[field_name]
                    expected_type = str(expected_field.dtype)
                    existing_type = existing_field["type"]
                    
                    if expected_type != existing_type:
                        issues.append(
                            f"Field {field_name} type mismatch: "
                            f"expected {expected_type}, got {existing_type}"
                        )
                    
                    # Check vector dimension for FLOAT_VECTOR fields
                    if expected_field.dtype == DataType.FLOAT_VECTOR:
                        expected_dim = expected_field.params.get('dim')
                        existing_dim = existing_field["params"].get('dim')
                        if expected_dim != existing_dim:
                            issues.append(
                                f"Vector field {field_name} dimension mismatch: "
                                f"expected {expected_dim}, got {existing_dim}"
                            )
            
            # Check indexes
            existing_indexes = {idx["field_name"]: idx for idx in existing_info["indexes"]}
            expected_index = expected_config.index_config
            
            # Check if vector field has an index
            vector_field_name = None
            for field in expected_config.fields:
                if field.dtype == DataType.FLOAT_VECTOR:
                    vector_field_name = field.name
                    break
            
            if vector_field_name and vector_field_name not in existing_indexes:
                issues.append(f"Missing index on vector field {vector_field_name}")
            elif vector_field_name and vector_field_name in existing_indexes:
                existing_index_info = existing_indexes[vector_field_name]
                if existing_index_info["index_type"] != expected_index.index_type.value:
                    issues.append(
                        f"Index type mismatch on {vector_field_name}: "
                        f"expected {expected_index.index_type.value}, "
                        f"got {existing_index_info['index_type']}"
                    )
                if existing_index_info["metric_type"] != expected_index.metric_type.value:
                    issues.append(
                        f"Metric type mismatch on {vector_field_name}: "
                        f"expected {expected_index.metric_type.value}, "
                        f"got {existing_index_info['metric_type']}"
                    )
            
            return len(issues) == 0, issues
            
        except Exception as e:
            issues.append(f"Validation error: {e}")
            return False, issues
    
    def create_collection(self, collection_name: str, force: bool = False) -> bool:
        """
        Create a collection with the predefined schema.
        
        Args:
            collection_name: Name of the collection to create
            force: If True, drop existing collection before creating
            
        Returns:
            True if collection was created successfully
        """
        try:
            logger.info(f"Creating collection: {collection_name}")
            
            # Check if collection already exists
            if utility.has_collection(collection_name, using=self.connection_alias):
                if not force:
                    logger.info(f"Collection {collection_name} already exists, skipping")
                    return True
                else:
                    logger.info(f"Dropping existing collection {collection_name}")
                    utility.drop_collection(collection_name, using=self.connection_alias)
                    time.sleep(1)  # Wait for cleanup
            
            # Get schema configuration
            schema_config = get_collection_schema(collection_name)
            
            # Create CollectionSchema object
            collection_schema = CollectionSchema(
                fields=schema_config.fields,
                description=schema_config.description
            )
            
            # Create collection
            collection = Collection(
                name=collection_name,
                schema=collection_schema,
                using=self.connection_alias,
                shards_num=schema_config.shard_num,
                consistency_level=schema_config.consistency_level
            )
            
            logger.info(f"Successfully created collection: {collection_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create collection {collection_name}: {e}")
            return False
    
    def create_index(self, collection_name: str, force: bool = False) -> bool:
        """
        Create index on the vector field of a collection.
        
        Args:
            collection_name: Name of the collection
            force: If True, drop existing index before creating
            
        Returns:
            True if index was created successfully
        """
        try:
            logger.info(f"Creating index for collection: {collection_name}")
            
            collection = Collection(collection_name, using=self.connection_alias)
            schema_config = get_collection_schema(collection_name)
            
            # Find vector field
            vector_field_name = None
            for field in schema_config.fields:
                if field.dtype == DataType.FLOAT_VECTOR:
                    vector_field_name = field.name
                    break
            
            if not vector_field_name:
                logger.warning(f"No vector field found in collection {collection_name}")
                return True
            
            # Check if index already exists
            existing_indexes = collection.indexes
            has_vector_index = any(
                idx.field_name == vector_field_name for idx in existing_indexes
            )
            
            if has_vector_index:
                if not force:
                    logger.info(f"Index already exists on {vector_field_name}, skipping")
                    return True
                else:
                    logger.info(f"Dropping existing index on {vector_field_name}")
                    collection.drop_index(vector_field_name)
                    time.sleep(2)  # Wait for cleanup
            
            # Get index parameters
            index_params = get_index_parameters(collection_name)
            
            # Create index
            logger.info(f"Creating {index_params['index_type']} index on {vector_field_name}")
            collection.create_index(
                field_name=vector_field_name,
                index_params=index_params
            )
            
            # Wait for index to be built
            logger.info("Waiting for index to be built...")
            while True:
                index_building_progress = utility.index_building_progress(
                    collection_name, using=self.connection_alias
                )
                if index_building_progress['pending_index_rows'] == 0:
                    break
                time.sleep(1)
            
            logger.info(f"Successfully created index for collection: {collection_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create index for {collection_name}: {e}")
            return False
    
    def initialize_collection(self, collection_name: str, force: bool = False) -> bool:
        """
        Initialize a collection with schema and index.
        
        Args:
            collection_name: Name of the collection to initialize
            force: If True, recreate existing collection and index
            
        Returns:
            True if initialization was successful
        """
        logger.info(f"Initializing collection: {collection_name}")
        
        # Create collection
        if not self.create_collection(collection_name, force=force):
            return False
        
        # Create index
        if not self.create_index(collection_name, force=force):
            return False
        
        logger.info(f"Successfully initialized collection: {collection_name}")
        return True
    
    def initialize_all_collections(
        self,
        collections: Optional[List[str]] = None,
        force: bool = False,
        include_optional: bool = False
    ) -> Dict[str, bool]:
        """
        Initialize multiple collections.
        
        Args:
            collections: List of collection names to initialize (None for defaults)
            force: If True, recreate existing collections
            include_optional: If True, include optional collections
            
        Returns:
            Dictionary mapping collection names to success status
        """
        if collections is None:
            collections = DEFAULT_COLLECTIONS.copy()
            if include_optional:
                collections.extend(OPTIONAL_COLLECTIONS)
        
        results = {}
        
        for collection_name in collections:
            logger.info(f"Processing collection: {collection_name}")
            try:
                success = self.initialize_collection(collection_name, force=force)
                results[collection_name] = success
                
                if success:
                    logger.info(f"✅ {collection_name}: SUCCESS")
                else:
                    logger.error(f"❌ {collection_name}: FAILED")
                    
            except Exception as e:
                logger.error(f"❌ {collection_name}: ERROR - {e}")
                results[collection_name] = False
        
        return results
    
    def validate_all_collections(
        self,
        collections: Optional[List[str]] = None
    ) -> Dict[str, Tuple[bool, List[str]]]:
        """
        Validate schemas for multiple collections.
        
        Args:
            collections: List of collection names to validate (None for all existing)
            
        Returns:
            Dictionary mapping collection names to (is_valid, issues) tuples
        """
        if collections is None:
            collections = self.list_existing_collections()
        
        results = {}
        
        for collection_name in collections:
            if collection_name in COLLECTION_SCHEMAS:
                logger.info(f"Validating collection: {collection_name}")
                is_valid, issues = self.validate_collection_schema(collection_name)
                results[collection_name] = (is_valid, issues)
                
                if is_valid:
                    logger.info(f"✅ {collection_name}: VALID")
                else:
                    logger.warning(f"⚠️  {collection_name}: INVALID")
                    for issue in issues:
                        logger.warning(f"   - {issue}")
            else:
                logger.info(f"⏭️  {collection_name}: No schema defined, skipping")
        
        return results


def print_summary(results: Dict[str, bool]) -> None:
    """Print a summary of initialization results"""
    print("\n" + "="*80)
    print("MILVUS SCHEMA INITIALIZATION SUMMARY")
    print("="*80)
    
    successful = [name for name, success in results.items() if success]
    failed = [name for name, success in results.items() if not success]
    
    if successful:
        print(f"\n✅ Successfully initialized ({len(successful)}):")
        for name in successful:
            print(f"   - {name}")
    
    if failed:
        print(f"\n❌ Failed to initialize ({len(failed)}):")
        for name in failed:
            print(f"   - {name}")
    
    print(f"\nTotal: {len(successful)} successful, {len(failed)} failed")
    print("="*80)


def print_validation_summary(results: Dict[str, Tuple[bool, List[str]]]) -> None:
    """Print a summary of validation results"""
    print("\n" + "="*80)
    print("MILVUS SCHEMA VALIDATION SUMMARY")
    print("="*80)
    
    valid = [name for name, (is_valid, _) in results.items() if is_valid]
    invalid = [(name, issues) for name, (is_valid, issues) in results.items() if not is_valid]
    
    if valid:
        print(f"\n✅ Valid schemas ({len(valid)}):")
        for name in valid:
            print(f"   - {name}")
    
    if invalid:
        print(f"\n⚠️  Invalid schemas ({len(invalid)}):")
        for name, issues in invalid:
            print(f"   - {name}:")
            for issue in issues:
                print(f"     • {issue}")
    
    print(f"\nTotal: {len(valid)} valid, {len(invalid)} invalid")
    print("="*80)


def main():
    """Main function for command-line usage"""
    parser = argparse.ArgumentParser(
        description="Initialize Milvus collection schemas",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Initialize all default collections
  python database/milvus/init_schemas.py
  
  # Initialize specific collections
  python database/milvus/init_schemas.py --collections knowledge_chunks document_embeddings
  
  # Force recreation of existing collections
  python database/milvus/init_schemas.py --force
  
  # Include optional collections
  python database/milvus/init_schemas.py --include-optional
  
  # Validate existing schemas only
  python database/milvus/init_schemas.py --validate-only
  
  # Connect to remote Milvus instance
  python database/milvus/init_schemas.py --host milvus.example.com --port 19530
        """
    )
    
    parser.add_argument(
        "--host",
        default="localhost",
        help="Milvus host (default: localhost)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=19530,
        help="Milvus port (default: 19530)"
    )
    parser.add_argument(
        "--collections",
        nargs="+",
        help="Specific collections to initialize (default: all default collections)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force recreation of existing collections"
    )
    parser.add_argument(
        "--include-optional",
        action="store_true",
        help="Include optional collections in initialization"
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Only validate existing schemas, don't create collections"
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    # Configure logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Initialize the schema initializer
    try:
        initializer = MilvusSchemaInitializer(
            host=args.host,
            port=args.port
        )
        
        # Connect to Milvus
        import asyncio
        asyncio.run(initializer.connect())
        
        if args.validate_only:
            # Validation mode
            logger.info("Running schema validation...")
            results = initializer.validate_all_collections(args.collections)
            print_validation_summary(results)
            
            # Exit with error if any validation failed
            failed_count = sum(1 for is_valid, _ in results.values() if not is_valid)
            sys.exit(failed_count)
        else:
            # Initialization mode
            logger.info("Starting schema initialization...")
            results = initializer.initialize_all_collections(
                collections=args.collections,
                force=args.force,
                include_optional=args.include_optional
            )
            print_summary(results)
            
            # Exit with error if any initialization failed
            failed_count = sum(1 for success in results.values() if not success)
            sys.exit(failed_count)
    
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Initialization failed: {e}")
        sys.exit(1)
    finally:
        try:
            initializer.disconnect()
        except:
            pass


if __name__ == "__main__":
    main()