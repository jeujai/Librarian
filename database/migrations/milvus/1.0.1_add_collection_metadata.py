#!/usr/bin/env python3
"""
Milvus Migration: Add collection metadata tracking
Version: 1.0.1
Description: Add metadata tracking for Milvus collections and schema versions
"""

import logging
import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional

try:
    from pymilvus import connections, Collection, utility, MilvusException
    PYMILVUS_AVAILABLE = True
except ImportError:
    PYMILVUS_AVAILABLE = False

logger = logging.getLogger(__name__)


class MilvusMetadataMigration:
    """Migration to add collection metadata tracking"""
    
    def __init__(self, host: str = "localhost", port: int = 19530):
        self.host = host
        self.port = port
        self.connection_alias = "migration_1_0_1"
    
    async def up(self) -> bool:
        """Apply the migration"""
        if not PYMILVUS_AVAILABLE:
            logger.error("pymilvus not available for migration")
            return False
        
        try:
            # Connect to Milvus
            connections.connect(
                alias=self.connection_alias,
                host=self.host,
                port=str(self.port)
            )
            
            # Create metadata collection for tracking schema versions
            metadata_collection_name = "_schema_metadata"
            
            if not utility.has_collection(metadata_collection_name, using=self.connection_alias):
                logger.info(f"Creating metadata collection: {metadata_collection_name}")
                
                # Create a simple collection to store metadata as JSON
                from pymilvus import FieldSchema, CollectionSchema, DataType
                
                fields = [
                    FieldSchema(name="id", dtype=DataType.VARCHAR, max_length=255, is_primary=True),
                    FieldSchema(name="metadata", dtype=DataType.JSON),
                    FieldSchema(name="created_at", dtype=DataType.INT64),
                    FieldSchema(name="updated_at", dtype=DataType.INT64)
                ]
                
                schema = CollectionSchema(
                    fields=fields,
                    description="Schema metadata and version tracking for Milvus collections"
                )
                
                collection = Collection(
                    name=metadata_collection_name,
                    schema=schema,
                    using=self.connection_alias
                )
                
                logger.info(f"Created metadata collection: {metadata_collection_name}")
            else:
                collection = Collection(metadata_collection_name, using=self.connection_alias)
                logger.info(f"Metadata collection already exists: {metadata_collection_name}")
            
            # Insert schema version metadata
            current_time = int(datetime.now(timezone.utc).timestamp() * 1000)
            
            schema_metadata = {
                "version": "1.0.1",
                "description": "Added collection metadata tracking",
                "migration_id": "milvus_1.0.1_add_collection_metadata",
                "applied_at": datetime.now(timezone.utc).isoformat(),
                "collections": {}
            }
            
            # Get information about existing collections
            existing_collections = utility.list_collections(using=self.connection_alias)
            for collection_name in existing_collections:
                if collection_name != metadata_collection_name:
                    try:
                        coll = Collection(collection_name, using=self.connection_alias)
                        schema_info = {
                            "num_entities": coll.num_entities,
                            "description": coll.description,
                            "fields": []
                        }
                        
                        # Get field information
                        for field in coll.schema.fields:
                            field_info = {
                                "name": field.name,
                                "type": str(field.dtype),
                                "is_primary": field.is_primary,
                                "description": field.description
                            }
                            if hasattr(field, 'params'):
                                field_info["params"] = field.params
                            schema_info["fields"].append(field_info)
                        
                        schema_metadata["collections"][collection_name] = schema_info
                        
                    except Exception as e:
                        logger.warning(f"Could not get info for collection {collection_name}: {e}")
            
            # Insert metadata record
            entities = [
                ["schema_version_1.0.1"],  # id
                [schema_metadata],         # metadata
                [current_time],            # created_at
                [current_time]             # updated_at
            ]
            
            collection.insert(entities)
            collection.flush()
            
            logger.info("Schema metadata inserted successfully")
            
            # Also insert a record for the current migration
            migration_metadata = {
                "type": "migration",
                "migration_id": "milvus_1.0.1_add_collection_metadata",
                "version": "1.0.1",
                "description": "Add collection metadata tracking",
                "status": "completed",
                "applied_at": datetime.now(timezone.utc).isoformat()
            }
            
            migration_entities = [
                ["migration_1.0.1"],      # id
                [migration_metadata],     # metadata
                [current_time],           # created_at
                [current_time]            # updated_at
            ]
            
            collection.insert(migration_entities)
            collection.flush()
            
            logger.info("Migration metadata recorded successfully")
            
            return True
            
        except Exception as e:
            logger.error(f"Migration failed: {e}")
            return False
        
        finally:
            try:
                connections.disconnect(alias=self.connection_alias)
            except:
                pass
    
    async def down(self) -> bool:
        """Rollback the migration"""
        if not PYMILVUS_AVAILABLE:
            logger.error("pymilvus not available for rollback")
            return False
        
        try:
            # Connect to Milvus
            connections.connect(
                alias=self.connection_alias,
                host=self.host,
                port=str(self.port)
            )
            
            # Drop metadata collection
            metadata_collection_name = "_schema_metadata"
            
            if utility.has_collection(metadata_collection_name, using=self.connection_alias):
                utility.drop_collection(metadata_collection_name, using=self.connection_alias)
                logger.info(f"Dropped metadata collection: {metadata_collection_name}")
            
            return True
            
        except Exception as e:
            logger.error(f"Migration rollback failed: {e}")
            return False
        
        finally:
            try:
                connections.disconnect(alias=self.connection_alias)
            except:
                pass


# Migration execution functions
async def migrate_up(host: str = "localhost", port: int = 19530) -> bool:
    """Execute the migration"""
    migration = MilvusMetadataMigration(host, port)
    return await migration.up()


async def migrate_down(host: str = "localhost", port: int = 19530) -> bool:
    """Rollback the migration"""
    migration = MilvusMetadataMigration(host, port)
    return await migration.down()


# For direct execution
if __name__ == "__main__":
    import asyncio
    import sys
    
    async def main():
        if len(sys.argv) > 1 and sys.argv[1] == "down":
            success = await migrate_down()
            action = "rollback"
        else:
            success = await migrate_up()
            action = "migration"
        
        if success:
            print(f"Milvus {action} 1.0.1 completed successfully")
            sys.exit(0)
        else:
            print(f"Milvus {action} 1.0.1 failed")
            sys.exit(1)
    
    asyncio.run(main())