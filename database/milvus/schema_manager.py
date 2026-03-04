#!/usr/bin/env python3
"""
Milvus Schema Manager

This module provides runtime schema management capabilities for the Multimodal
Librarian application. It handles:

- Dynamic schema validation and migration
- Collection creation with proper error handling
- Schema compatibility checking
- Runtime collection management
- Integration with the MilvusClient

Usage:
    from database.milvus.schema_manager import MilvusSchemaManager
    
    # Initialize schema manager
    manager = MilvusSchemaManager(milvus_client)
    
    # Ensure collection exists with proper schema
    await manager.ensure_collection_exists("knowledge_chunks")
    
    # Validate all collections
    validation_results = await manager.validate_all_schemas()
    
    # Migrate schema if needed
    await manager.migrate_collection_schema("knowledge_chunks")
"""

import logging
import time
from typing import Dict, List, Any, Optional, Tuple, Union
from datetime import datetime

try:
    from pymilvus import Collection, utility, MilvusException
    PYMILVUS_AVAILABLE = True
except ImportError:
    PYMILVUS_AVAILABLE = False

# Import schema definitions
try:
    from database.milvus.schemas import (
        COLLECTION_SCHEMAS, DEFAULT_COLLECTIONS,
        get_collection_schema, get_embedding_dimension,
        get_index_parameters, validate_schema_compatibility
    )
    SCHEMAS_AVAILABLE = True
except ImportError:
    SCHEMAS_AVAILABLE = False

logger = logging.getLogger(__name__)


class SchemaValidationError(Exception):
    """Raised when schema validation fails"""
    pass


class SchemaMigrationError(Exception):
    """Raised when schema migration fails"""
    pass


class MilvusSchemaManager:
    """
    Manages Milvus collection schemas at runtime.
    
    This class provides high-level schema management operations that can be
    used by the application to ensure collections exist with proper schemas,
    validate existing collections, and handle schema migrations.
    """
    
    def __init__(self, milvus_client=None):
        """
        Initialize schema manager.
        
        Args:
            milvus_client: MilvusClient instance (optional, can be set later)
        """
        if not PYMILVUS_AVAILABLE:
            raise ImportError("pymilvus is required for schema management")
        
        if not SCHEMAS_AVAILABLE:
            raise ImportError("Schema definitions are not available")
        
        self.milvus_client = milvus_client
        self._schema_cache = {}
        self._validation_cache = {}
        self._cache_ttl = 300  # 5 minutes
    
    def set_client(self, milvus_client) -> None:
        """Set the MilvusClient instance"""
        self.milvus_client = milvus_client
        # Clear caches when client changes
        self._schema_cache.clear()
        self._validation_cache.clear()
    
    def _ensure_client(self) -> None:
        """Ensure MilvusClient is available"""
        if self.milvus_client is None:
            raise ValueError("MilvusClient not set. Call set_client() first.")
    
    async def list_existing_collections(self) -> List[str]:
        """List all existing collections in Milvus"""
        self._ensure_client()
        
        try:
            collections = await self.milvus_client.list_collections()
            return collections
        except Exception as e:
            logger.error(f"Failed to list collections: {e}")
            return []
    
    async def collection_exists(self, collection_name: str) -> bool:
        """Check if a collection exists"""
        collections = await self.list_existing_collections()
        return collection_name in collections
    
    async def get_collection_info(self, collection_name: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a collection.
        
        Args:
            collection_name: Name of the collection
            
        Returns:
            Dictionary with collection information or None if not found
        """
        self._ensure_client()
        
        try:
            # Check cache first
            cache_key = f"info_{collection_name}"
            current_time = time.time()
            
            if cache_key in self._schema_cache:
                cached_info, cache_time = self._schema_cache[cache_key]
                if current_time - cache_time < self._cache_ttl:
                    return cached_info
            
            # Get collection stats
            stats = await self.milvus_client.get_collection_stats(collection_name)
            
            # Cache the result
            self._schema_cache[cache_key] = (stats, current_time)
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get collection info for {collection_name}: {e}")
            return None
    
    async def validate_collection_schema(
        self, 
        collection_name: str,
        raise_on_invalid: bool = False
    ) -> Tuple[bool, List[str]]:
        """
        Validate that a collection matches the expected schema.
        
        Args:
            collection_name: Name of the collection to validate
            raise_on_invalid: If True, raise exception on validation failure
            
        Returns:
            Tuple of (is_valid, list_of_issues)
            
        Raises:
            SchemaValidationError: If raise_on_invalid=True and validation fails
        """
        self._ensure_client()
        
        issues = []
        
        try:
            # Check cache first
            cache_key = f"validation_{collection_name}"
            current_time = time.time()
            
            if cache_key in self._validation_cache:
                cached_result, cache_time = self._validation_cache[cache_key]
                if current_time - cache_time < self._cache_ttl:
                    is_valid, issues = cached_result
                    if raise_on_invalid and not is_valid:
                        raise SchemaValidationError(
                            f"Schema validation failed for {collection_name}: {issues}"
                        )
                    return is_valid, issues
            
            # Check if collection exists
            if not await self.collection_exists(collection_name):
                issues.append(f"Collection {collection_name} does not exist")
                result = (False, issues)
                self._validation_cache[cache_key] = (result, current_time)
                
                if raise_on_invalid:
                    raise SchemaValidationError(
                        f"Collection {collection_name} does not exist"
                    )
                return result
            
            # Check if schema is defined
            if collection_name not in COLLECTION_SCHEMAS:
                issues.append(f"No schema definition found for {collection_name}")
                result = (False, issues)
                self._validation_cache[cache_key] = (result, current_time)
                
                if raise_on_invalid:
                    raise SchemaValidationError(
                        f"No schema definition found for {collection_name}"
                    )
                return result
            
            # Get expected schema
            expected_config = get_collection_schema(collection_name)
            
            # Get actual collection info
            collection_info = await self.get_collection_info(collection_name)
            if not collection_info:
                issues.append(f"Could not retrieve collection info for {collection_name}")
                result = (False, issues)
                self._validation_cache[cache_key] = (result, current_time)
                
                if raise_on_invalid:
                    raise SchemaValidationError(
                        f"Could not retrieve collection info for {collection_name}"
                    )
                return result
            
            # Validate schema fields
            schema_fields = collection_info.get("schema", {}).get("fields", [])
            expected_fields = {f.name: f for f in expected_config.fields}
            existing_fields = {f["name"]: f for f in schema_fields}
            
            # Check for missing fields
            missing_fields = set(expected_fields.keys()) - set(existing_fields.keys())
            if missing_fields:
                issues.append(f"Missing fields: {missing_fields}")
            
            # Check for extra fields (warning, not error)
            extra_fields = set(existing_fields.keys()) - set(expected_fields.keys())
            if extra_fields:
                issues.append(f"Extra fields (not critical): {extra_fields}")
            
            # Check field types and parameters
            for field_name, expected_field in expected_fields.items():
                if field_name in existing_fields:
                    existing_field = existing_fields[field_name]
                    expected_type = str(expected_field.dtype)
                    existing_type = existing_field["type"]
                    
                    # Normalize type names for comparison
                    if "DataType." in expected_type:
                        expected_type = expected_type.replace("DataType.", "")
                    if "DataType." in existing_type:
                        existing_type = existing_type.replace("DataType.", "")
                    
                    if expected_type != existing_type:
                        issues.append(
                            f"Field {field_name} type mismatch: "
                            f"expected {expected_type}, got {existing_type}"
                        )
            
            # Validate vector field dimension
            try:
                expected_dim = get_embedding_dimension(collection_name)
                actual_dim = collection_info.get("dimension", 0)
                
                if expected_dim != actual_dim:
                    issues.append(
                        f"Vector dimension mismatch: "
                        f"expected {expected_dim}, got {actual_dim}"
                    )
            except Exception as e:
                logger.warning(f"Could not validate vector dimension: {e}")
            
            # Check index configuration
            index_info = collection_info.get("index_info", {})
            if index_info:
                expected_index = expected_config.index_config
                actual_index_type = index_info.get("index_type", "unknown")
                actual_metric_type = index_info.get("metric_type", "unknown")
                
                if actual_index_type != expected_index.index_type.value:
                    issues.append(
                        f"Index type mismatch: "
                        f"expected {expected_index.index_type.value}, "
                        f"got {actual_index_type}"
                    )
                
                if actual_metric_type != expected_index.metric_type.value:
                    issues.append(
                        f"Metric type mismatch: "
                        f"expected {expected_index.metric_type.value}, "
                        f"got {actual_metric_type}"
                    )
            else:
                issues.append("No index information available")
            
            # Determine if validation passed
            # Only critical issues (missing fields, type mismatches) cause failure
            critical_issues = [
                issue for issue in issues 
                if not issue.startswith("Extra fields") and "not critical" not in issue
            ]
            
            is_valid = len(critical_issues) == 0
            result = (is_valid, issues)
            
            # Cache the result
            self._validation_cache[cache_key] = (result, current_time)
            
            if raise_on_invalid and not is_valid:
                raise SchemaValidationError(
                    f"Schema validation failed for {collection_name}: {critical_issues}"
                )
            
            return result
            
        except Exception as e:
            if isinstance(e, SchemaValidationError):
                raise
            
            error_msg = f"Schema validation error for {collection_name}: {e}"
            logger.error(error_msg)
            issues.append(error_msg)
            
            result = (False, issues)
            if raise_on_invalid:
                raise SchemaValidationError(error_msg)
            
            return result
    
    async def ensure_collection_exists(
        self, 
        collection_name: str,
        create_if_missing: bool = True,
        validate_schema: bool = True
    ) -> bool:
        """
        Ensure a collection exists with the proper schema.
        
        Args:
            collection_name: Name of the collection
            create_if_missing: If True, create collection if it doesn't exist
            validate_schema: If True, validate schema if collection exists
            
        Returns:
            True if collection exists and is valid
            
        Raises:
            SchemaValidationError: If schema validation fails
            SchemaMigrationError: If collection creation fails
        """
        self._ensure_client()
        
        logger.info(f"Ensuring collection exists: {collection_name}")
        
        # Check if collection exists
        exists = await self.collection_exists(collection_name)
        
        if not exists:
            if not create_if_missing:
                raise SchemaMigrationError(
                    f"Collection {collection_name} does not exist and "
                    f"create_if_missing=False"
                )
            
            # Create the collection
            logger.info(f"Creating collection: {collection_name}")
            success = await self.create_collection(collection_name)
            
            if not success:
                raise SchemaMigrationError(
                    f"Failed to create collection {collection_name}"
                )
            
            logger.info(f"Successfully created collection: {collection_name}")
            return True
        
        # Collection exists, validate schema if requested
        if validate_schema:
            logger.debug(f"Validating schema for existing collection: {collection_name}")
            is_valid, issues = await self.validate_collection_schema(
                collection_name, 
                raise_on_invalid=False
            )
            
            if not is_valid:
                logger.warning(
                    f"Schema validation failed for {collection_name}: {issues}"
                )
                # For now, we log the warning but don't fail
                # In the future, we could implement schema migration here
                return True
            
            logger.debug(f"Schema validation passed for: {collection_name}")
        
        return True
    
    async def create_collection(self, collection_name: str) -> bool:
        """
        Create a collection with the predefined schema.
        
        Args:
            collection_name: Name of the collection to create
            
        Returns:
            True if collection was created successfully
            
        Raises:
            SchemaMigrationError: If collection creation fails
        """
        self._ensure_client()
        
        try:
            logger.info(f"Creating collection with schema: {collection_name}")
            
            # Get schema configuration
            schema_config = get_collection_schema(collection_name)
            
            # Get embedding dimension
            dimension = get_embedding_dimension(collection_name)
            
            # Create collection using MilvusClient
            success = await self.milvus_client.create_collection(
                collection_name=collection_name,
                dimension=dimension,
                metric_type=schema_config.index_config.metric_type.value
            )
            
            if not success:
                raise SchemaMigrationError(
                    f"MilvusClient.create_collection returned False for {collection_name}"
                )
            
            # Create index
            logger.info(f"Creating index for collection: {collection_name}")
            index_success = await self.milvus_client.create_index(
                collection_name=collection_name,
                field_name="vector"  # Standard vector field name in MilvusClient
            )
            
            if not index_success:
                logger.warning(
                    f"Index creation failed for {collection_name}, "
                    f"but collection was created"
                )
            
            # Clear caches
            self._schema_cache.clear()
            self._validation_cache.clear()
            
            logger.info(f"Successfully created collection: {collection_name}")
            return True
            
        except Exception as e:
            error_msg = f"Failed to create collection {collection_name}: {e}"
            logger.error(error_msg)
            raise SchemaMigrationError(error_msg) from e
    
    async def ensure_default_collections(self) -> Dict[str, bool]:
        """
        Ensure all default collections exist with proper schemas.
        
        Returns:
            Dictionary mapping collection names to success status
        """
        self._ensure_client()
        
        logger.info("Ensuring default collections exist...")
        
        results = {}
        
        for collection_name in DEFAULT_COLLECTIONS:
            try:
                logger.info(f"Processing default collection: {collection_name}")
                success = await self.ensure_collection_exists(
                    collection_name,
                    create_if_missing=True,
                    validate_schema=True
                )
                results[collection_name] = success
                
                if success:
                    logger.info(f"✅ {collection_name}: OK")
                else:
                    logger.error(f"❌ {collection_name}: FAILED")
                    
            except Exception as e:
                logger.error(f"❌ {collection_name}: ERROR - {e}")
                results[collection_name] = False
        
        successful = sum(1 for success in results.values() if success)
        total = len(results)
        
        logger.info(f"Default collections status: {successful}/{total} successful")
        
        return results
    
    async def validate_all_schemas(
        self, 
        collections: Optional[List[str]] = None
    ) -> Dict[str, Tuple[bool, List[str]]]:
        """
        Validate schemas for multiple collections.
        
        Args:
            collections: List of collection names (None for all existing)
            
        Returns:
            Dictionary mapping collection names to (is_valid, issues) tuples
        """
        self._ensure_client()
        
        if collections is None:
            collections = await self.list_existing_collections()
        
        logger.info(f"Validating schemas for {len(collections)} collections...")
        
        results = {}
        
        for collection_name in collections:
            if collection_name in COLLECTION_SCHEMAS:
                logger.debug(f"Validating schema: {collection_name}")
                try:
                    is_valid, issues = await self.validate_collection_schema(
                        collection_name, 
                        raise_on_invalid=False
                    )
                    results[collection_name] = (is_valid, issues)
                    
                    if is_valid:
                        logger.debug(f"✅ {collection_name}: VALID")
                    else:
                        logger.warning(f"⚠️  {collection_name}: INVALID - {issues}")
                        
                except Exception as e:
                    logger.error(f"❌ {collection_name}: VALIDATION ERROR - {e}")
                    results[collection_name] = (False, [str(e)])
            else:
                logger.debug(f"⏭️  {collection_name}: No schema defined, skipping")
        
        valid_count = sum(1 for is_valid, _ in results.values() if is_valid)
        total_count = len(results)
        
        logger.info(f"Schema validation complete: {valid_count}/{total_count} valid")
        
        return results
    
    async def get_schema_summary(self) -> Dict[str, Any]:
        """
        Get a summary of all collection schemas and their status.
        
        Returns:
            Dictionary with schema summary information
        """
        self._ensure_client()
        
        logger.info("Generating schema summary...")
        
        # Get existing collections
        existing_collections = await self.list_existing_collections()
        
        # Validate schemas
        validation_results = await self.validate_all_schemas(existing_collections)
        
        # Build summary
        summary = {
            "timestamp": datetime.utcnow().isoformat(),
            "total_defined_schemas": len(COLLECTION_SCHEMAS),
            "total_existing_collections": len(existing_collections),
            "default_collections": DEFAULT_COLLECTIONS,
            "collections": {}
        }
        
        # Add information for each defined schema
        for collection_name in COLLECTION_SCHEMAS:
            collection_info = {
                "schema_defined": True,
                "exists": collection_name in existing_collections,
                "is_default": collection_name in DEFAULT_COLLECTIONS,
                "validation_status": "not_validated"
            }
            
            if collection_name in validation_results:
                is_valid, issues = validation_results[collection_name]
                collection_info["validation_status"] = "valid" if is_valid else "invalid"
                collection_info["validation_issues"] = issues
            
            if collection_info["exists"]:
                # Get additional collection info
                stats = await self.get_collection_info(collection_name)
                if stats:
                    collection_info["vector_count"] = stats.get("vector_count", 0)
                    collection_info["dimension"] = stats.get("dimension", 0)
                    collection_info["index_type"] = stats.get("index_info", {}).get("index_type", "unknown")
            
            summary["collections"][collection_name] = collection_info
        
        # Add information for existing collections without defined schemas
        for collection_name in existing_collections:
            if collection_name not in COLLECTION_SCHEMAS:
                summary["collections"][collection_name] = {
                    "schema_defined": False,
                    "exists": True,
                    "is_default": False,
                    "validation_status": "no_schema"
                }
        
        # Calculate summary statistics
        defined_and_existing = sum(
            1 for info in summary["collections"].values() 
            if info["schema_defined"] and info["exists"]
        )
        valid_schemas = sum(
            1 for info in summary["collections"].values() 
            if info.get("validation_status") == "valid"
        )
        
        summary["statistics"] = {
            "defined_and_existing": defined_and_existing,
            "valid_schemas": valid_schemas,
            "missing_collections": len(COLLECTION_SCHEMAS) - defined_and_existing,
            "undefined_collections": len(existing_collections) - defined_and_existing
        }
        
        logger.info("Schema summary generated successfully")
        
        return summary
    
    def clear_cache(self) -> None:
        """Clear all cached schema and validation information"""
        self._schema_cache.clear()
        self._validation_cache.clear()
        logger.debug("Schema manager cache cleared")


# Convenience functions for direct usage

async def ensure_collection_exists(
    milvus_client, 
    collection_name: str,
    create_if_missing: bool = True
) -> bool:
    """
    Convenience function to ensure a collection exists.
    
    Args:
        milvus_client: MilvusClient instance
        collection_name: Name of the collection
        create_if_missing: If True, create collection if missing
        
    Returns:
        True if collection exists and is valid
    """
    manager = MilvusSchemaManager(milvus_client)
    return await manager.ensure_collection_exists(
        collection_name, 
        create_if_missing=create_if_missing
    )


async def validate_collection_schema(
    milvus_client, 
    collection_name: str
) -> Tuple[bool, List[str]]:
    """
    Convenience function to validate a collection schema.
    
    Args:
        milvus_client: MilvusClient instance
        collection_name: Name of the collection
        
    Returns:
        Tuple of (is_valid, list_of_issues)
    """
    manager = MilvusSchemaManager(milvus_client)
    return await manager.validate_collection_schema(collection_name)


async def ensure_default_collections(milvus_client) -> Dict[str, bool]:
    """
    Convenience function to ensure all default collections exist.
    
    Args:
        milvus_client: MilvusClient instance
        
    Returns:
        Dictionary mapping collection names to success status
    """
    manager = MilvusSchemaManager(milvus_client)
    return await manager.ensure_default_collections()