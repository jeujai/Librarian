#!/usr/bin/env python3
"""
Milvus Schema Integration Utilities

This module provides integration utilities to connect the MilvusClient with
the schema management system. It allows the existing MilvusClient to use
predefined schemas while maintaining backward compatibility.

Usage:
    from database.milvus.integration import integrate_schema_manager
    
    # Integrate schema manager with existing MilvusClient
    milvus_client = MilvusClient(host="localhost", port=19530)
    await milvus_client.connect()
    
    # Add schema management capabilities
    integrate_schema_manager(milvus_client)
    
    # Now the client can use schema-aware methods
    await milvus_client.ensure_collection_with_schema("knowledge_chunks")
"""

import logging
from typing import Optional, Dict, Any, List, Tuple

try:
    from database.milvus.schema_manager import MilvusSchemaManager
    from database.milvus.schemas import (
        COLLECTION_SCHEMAS, DEFAULT_COLLECTIONS,
        get_collection_schema, get_embedding_dimension
    )
    SCHEMA_SYSTEM_AVAILABLE = True
except ImportError as e:
    SCHEMA_SYSTEM_AVAILABLE = False
    SCHEMA_IMPORT_ERROR = str(e)

logger = logging.getLogger(__name__)


def integrate_schema_manager(milvus_client) -> None:
    """
    Integrate schema management capabilities into an existing MilvusClient.
    
    This function adds schema-aware methods to the MilvusClient instance,
    allowing it to use predefined schemas while maintaining backward
    compatibility with existing code.
    
    Args:
        milvus_client: MilvusClient instance to enhance
        
    Raises:
        ImportError: If schema system is not available
    """
    if not SCHEMA_SYSTEM_AVAILABLE:
        raise ImportError(f"Schema system not available: {SCHEMA_IMPORT_ERROR}")
    
    # Create schema manager instance
    schema_manager = MilvusSchemaManager(milvus_client)
    
    # Add schema manager as an attribute
    milvus_client._schema_manager = schema_manager
    
    # Add schema-aware methods to the client
    milvus_client.ensure_collection_with_schema = _ensure_collection_with_schema.__get__(milvus_client)
    milvus_client.validate_collection_schema = _validate_collection_schema.__get__(milvus_client)
    milvus_client.ensure_default_collections = _ensure_default_collections.__get__(milvus_client)
    milvus_client.get_schema_summary = _get_schema_summary.__get__(milvus_client)
    milvus_client.list_available_schemas = _list_available_schemas.__get__(milvus_client)
    milvus_client.get_collection_schema_info = _get_collection_schema_info.__get__(milvus_client)
    
    # Override the existing _ensure_collection_exists method to use schemas
    original_ensure_collection_exists = milvus_client._ensure_collection_exists
    milvus_client._ensure_collection_exists_original = original_ensure_collection_exists
    milvus_client._ensure_collection_exists = _schema_aware_ensure_collection_exists.__get__(milvus_client)
    
    logger.info("Schema management capabilities integrated into MilvusClient")


async def _ensure_collection_with_schema(self, collection_name: str) -> bool:
    """
    Ensure a collection exists with the proper predefined schema.
    
    This method uses the schema definitions to create collections with
    the correct field types, dimensions, and index configurations.
    
    Args:
        collection_name: Name of the collection
        
    Returns:
        True if collection exists and is valid
        
    Raises:
        ValueError: If no schema is defined for the collection
    """
    if not hasattr(self, '_schema_manager'):
        raise RuntimeError("Schema manager not integrated. Call integrate_schema_manager() first.")
    
    if collection_name not in COLLECTION_SCHEMAS:
        available_schemas = list(COLLECTION_SCHEMAS.keys())
        raise ValueError(
            f"No schema defined for collection '{collection_name}'. "
            f"Available schemas: {available_schemas}"
        )
    
    logger.info(f"Ensuring collection with schema: {collection_name}")
    
    return await self._schema_manager.ensure_collection_exists(
        collection_name,
        create_if_missing=True,
        validate_schema=True
    )


async def _validate_collection_schema(self, collection_name: str) -> Tuple[bool, List[str]]:
    """
    Validate that a collection matches its expected schema.
    
    Args:
        collection_name: Name of the collection to validate
        
    Returns:
        Tuple of (is_valid, list_of_issues)
    """
    if not hasattr(self, '_schema_manager'):
        raise RuntimeError("Schema manager not integrated. Call integrate_schema_manager() first.")
    
    return await self._schema_manager.validate_collection_schema(collection_name)


async def _ensure_default_collections(self) -> Dict[str, bool]:
    """
    Ensure all default collections exist with proper schemas.
    
    Returns:
        Dictionary mapping collection names to success status
    """
    if not hasattr(self, '_schema_manager'):
        raise RuntimeError("Schema manager not integrated. Call integrate_schema_manager() first.")
    
    return await self._schema_manager.ensure_default_collections()


async def _get_schema_summary(self) -> Dict[str, Any]:
    """
    Get a comprehensive summary of all collection schemas and their status.
    
    Returns:
        Dictionary with schema summary information
    """
    if not hasattr(self, '_schema_manager'):
        raise RuntimeError("Schema manager not integrated. Call integrate_schema_manager() first.")
    
    return await self._schema_manager.get_schema_summary()


def _list_available_schemas(self) -> List[str]:
    """
    List all available collection schemas.
    
    Returns:
        List of collection names with defined schemas
    """
    return list(COLLECTION_SCHEMAS.keys())


async def _get_collection_schema_info(self, collection_name: str) -> Optional[Dict[str, Any]]:
    """
    Get detailed schema information for a collection.
    
    Args:
        collection_name: Name of the collection
        
    Returns:
        Dictionary with schema information or None if not defined
    """
    if collection_name not in COLLECTION_SCHEMAS:
        return None
    
    try:
        schema_config = get_collection_schema(collection_name)
        dimension = get_embedding_dimension(collection_name)
        
        return {
            "name": collection_name,
            "description": schema_config.description,
            "dimension": dimension,
            "index_type": schema_config.index_config.index_type.value,
            "metric_type": schema_config.index_config.metric_type.value,
            "index_params": schema_config.index_config.params,
            "shard_num": schema_config.shard_num,
            "consistency_level": schema_config.consistency_level,
            "fields": [
                {
                    "name": field.name,
                    "type": str(field.dtype),
                    "is_primary": field.is_primary,
                    "description": field.description,
                    "params": getattr(field, 'params', {})
                }
                for field in schema_config.fields
            ]
        }
    except Exception as e:
        logger.error(f"Failed to get schema info for {collection_name}: {e}")
        return None


async def _schema_aware_ensure_collection_exists(self, collection_name: str, dimension: int) -> None:
    """
    Schema-aware version of _ensure_collection_exists.
    
    This method replaces the original _ensure_collection_exists to use
    predefined schemas when available, falling back to the original
    behavior for collections without defined schemas.
    
    Args:
        collection_name: Name of the collection
        dimension: Vector dimension (used as fallback)
    """
    # Check if we have a predefined schema for this collection
    if collection_name in COLLECTION_SCHEMAS:
        logger.info(f"Using predefined schema for collection: {collection_name}")
        
        try:
            # Use schema-aware creation
            await self.ensure_collection_with_schema(collection_name)
            return
        except Exception as e:
            logger.warning(
                f"Schema-aware creation failed for {collection_name}: {e}. "
                f"Falling back to original method."
            )
    
    # Fall back to original behavior
    logger.info(f"Using original collection creation for: {collection_name}")
    await self._ensure_collection_exists_original(collection_name, dimension)


def create_schema_aware_milvus_client(*args, **kwargs):
    """
    Create a MilvusClient with integrated schema management.
    
    This is a convenience function that creates a MilvusClient and
    automatically integrates schema management capabilities.
    
    Args:
        *args, **kwargs: Arguments passed to MilvusClient constructor
        
    Returns:
        MilvusClient instance with schema management integrated
        
    Raises:
        ImportError: If MilvusClient or schema system is not available
    """
    try:
        from src.multimodal_librarian.clients.milvus_client import MilvusClient
    except ImportError as e:
        raise ImportError(f"MilvusClient not available: {e}")
    
    # Create client
    client = MilvusClient(*args, **kwargs)
    
    # Integrate schema management
    integrate_schema_manager(client)
    
    return client


# Backward compatibility functions

async def ensure_knowledge_chunks_collection(milvus_client) -> bool:
    """
    Ensure the knowledge_chunks collection exists with proper schema.
    
    This is a convenience function for the most commonly used collection.
    
    Args:
        milvus_client: MilvusClient instance
        
    Returns:
        True if collection exists and is valid
    """
    if not hasattr(milvus_client, '_schema_manager'):
        integrate_schema_manager(milvus_client)
    
    return await milvus_client.ensure_collection_with_schema("knowledge_chunks")


async def ensure_document_embeddings_collection(milvus_client) -> bool:
    """
    Ensure the document_embeddings collection exists with proper schema.
    
    Args:
        milvus_client: MilvusClient instance
        
    Returns:
        True if collection exists and is valid
    """
    if not hasattr(milvus_client, '_schema_manager'):
        integrate_schema_manager(milvus_client)
    
    return await milvus_client.ensure_collection_with_schema("document_embeddings")


async def setup_all_collections(milvus_client) -> Dict[str, bool]:
    """
    Set up all default collections with proper schemas.
    
    This function ensures all default collections exist and are properly
    configured according to their schema definitions.
    
    Args:
        milvus_client: MilvusClient instance
        
    Returns:
        Dictionary mapping collection names to success status
    """
    if not hasattr(milvus_client, '_schema_manager'):
        integrate_schema_manager(milvus_client)
    
    return await milvus_client.ensure_default_collections()


# Validation utilities

async def validate_all_collections(milvus_client) -> Dict[str, Tuple[bool, List[str]]]:
    """
    Validate all existing collections against their schemas.
    
    Args:
        milvus_client: MilvusClient instance
        
    Returns:
        Dictionary mapping collection names to (is_valid, issues) tuples
    """
    if not hasattr(milvus_client, '_schema_manager'):
        integrate_schema_manager(milvus_client)
    
    return await milvus_client._schema_manager.validate_all_schemas()


def get_schema_info(collection_name: str) -> Optional[Dict[str, Any]]:
    """
    Get schema information for a collection without requiring a client.
    
    Args:
        collection_name: Name of the collection
        
    Returns:
        Dictionary with schema information or None if not defined
    """
    if not SCHEMA_SYSTEM_AVAILABLE:
        return None
    
    if collection_name not in COLLECTION_SCHEMAS:
        return None
    
    try:
        schema_config = get_collection_schema(collection_name)
        dimension = get_embedding_dimension(collection_name)
        
        return {
            "name": collection_name,
            "description": schema_config.description,
            "dimension": dimension,
            "index_type": schema_config.index_config.index_type.value,
            "metric_type": schema_config.index_config.metric_type.value,
            "is_default": collection_name in DEFAULT_COLLECTIONS
        }
    except Exception:
        return None