#!/usr/bin/env python3
"""
Test script for Milvus schema definitions.

This script validates that all schema definitions are correct and can be
loaded without errors. It's useful for testing schema changes before
deployment.

Usage:
    python database/milvus/test_schemas.py
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

def test_schema_imports():
    """Test that all schema modules can be imported"""
    print("Testing schema imports...")
    
    try:
        from database.milvus.schemas import (
            COLLECTION_SCHEMAS, DEFAULT_COLLECTIONS, OPTIONAL_COLLECTIONS,
            get_collection_schema, get_embedding_dimension, get_index_parameters
        )
        print("✅ Schema definitions imported successfully")
        
        from database.milvus.schema_manager import MilvusSchemaManager
        print("✅ Schema manager imported successfully")
        
        from database.milvus.integration import (
            integrate_schema_manager, get_schema_info
        )
        print("✅ Integration utilities imported successfully")
        
        return True
    except Exception as e:
        print(f"❌ Import error: {e}")
        return False

def test_schema_definitions():
    """Test that all schema definitions are valid"""
    print("\nTesting schema definitions...")
    
    try:
        from database.milvus.schemas import COLLECTION_SCHEMAS, get_collection_schema
        
        for collection_name in COLLECTION_SCHEMAS:
            schema_config = get_collection_schema(collection_name)
            
            # Validate basic properties
            assert schema_config.name == collection_name
            assert len(schema_config.fields) > 0
            assert schema_config.description
            
            # Check for primary key field
            has_primary = any(field.is_primary for field in schema_config.fields)
            assert has_primary, f"Collection {collection_name} has no primary key field"
            
            # Check for vector field
            from database.milvus.schemas import DataType
            has_vector = any(
                hasattr(field, 'dtype') and 
                field.dtype == DataType.FLOAT_VECTOR
                for field in schema_config.fields
            )
            assert has_vector, f"Collection {collection_name} has no vector field"
            
            print(f"✅ {collection_name}: Valid schema with {len(schema_config.fields)} fields")
        
        return True
    except Exception as e:
        print(f"❌ Schema validation error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_embedding_dimensions():
    """Test that embedding dimensions can be retrieved"""
    print("\nTesting embedding dimensions...")
    
    try:
        from database.milvus.schemas import COLLECTION_SCHEMAS, get_embedding_dimension
        
        for collection_name in COLLECTION_SCHEMAS:
            dimension = get_embedding_dimension(collection_name)
            assert dimension > 0, f"Invalid dimension for {collection_name}: {dimension}"
            print(f"✅ {collection_name}: {dimension}D embeddings")
        
        return True
    except Exception as e:
        print(f"❌ Dimension test error: {e}")
        return False

def test_index_parameters():
    """Test that index parameters can be retrieved"""
    print("\nTesting index parameters...")
    
    try:
        from database.milvus.schemas import COLLECTION_SCHEMAS, get_index_parameters
        
        for collection_name in COLLECTION_SCHEMAS:
            params = get_index_parameters(collection_name)
            
            # Validate required parameters
            assert "index_type" in params
            assert "metric_type" in params
            assert "params" in params
            
            print(f"✅ {collection_name}: {params['index_type']} index with {params['metric_type']} metric")
        
        return True
    except Exception as e:
        print(f"❌ Index parameters test error: {e}")
        return False

def test_collection_lists():
    """Test that collection lists are properly defined"""
    print("\nTesting collection lists...")
    
    try:
        from database.milvus.schemas import (
            COLLECTION_SCHEMAS, DEFAULT_COLLECTIONS, OPTIONAL_COLLECTIONS
        )
        
        # Check that default collections are defined
        for collection_name in DEFAULT_COLLECTIONS:
            assert collection_name in COLLECTION_SCHEMAS, f"Default collection {collection_name} not defined"
        
        # Check that optional collections are defined
        for collection_name in OPTIONAL_COLLECTIONS:
            assert collection_name in COLLECTION_SCHEMAS, f"Optional collection {collection_name} not defined"
        
        # Check for no overlap
        default_set = set(DEFAULT_COLLECTIONS)
        optional_set = set(OPTIONAL_COLLECTIONS)
        overlap = default_set & optional_set
        assert not overlap, f"Collections in both default and optional lists: {overlap}"
        
        print(f"✅ Default collections: {DEFAULT_COLLECTIONS}")
        print(f"✅ Optional collections: {OPTIONAL_COLLECTIONS}")
        
        return True
    except Exception as e:
        print(f"❌ Collection lists test error: {e}")
        return False

def test_integration_utilities():
    """Test integration utility functions"""
    print("\nTesting integration utilities...")
    
    try:
        from database.milvus.integration import get_schema_info
        from database.milvus.schemas import COLLECTION_SCHEMAS
        
        for collection_name in COLLECTION_SCHEMAS:
            info = get_schema_info(collection_name)
            
            assert info is not None, f"No schema info for {collection_name}"
            assert info["name"] == collection_name
            assert info["dimension"] > 0
            assert "index_type" in info
            assert "metric_type" in info
            
            print(f"✅ {collection_name}: Schema info retrieved successfully")
        
        # Test non-existent collection
        info = get_schema_info("non_existent_collection")
        assert info is None, "Should return None for non-existent collection"
        
        return True
    except Exception as e:
        print(f"❌ Integration utilities test error: {e}")
        return False

def main():
    """Run all tests"""
    print("Milvus Schema Test Suite")
    print("=" * 50)
    
    tests = [
        test_schema_imports,
        test_schema_definitions,
        test_embedding_dimensions,
        test_index_parameters,
        test_collection_lists,
        test_integration_utilities
    ]
    
    passed = 0
    failed = 0
    
    for test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"❌ Test {test_func.__name__} failed with exception: {e}")
            failed += 1
    
    print("\n" + "=" * 50)
    print(f"Test Results: {passed} passed, {failed} failed")
    
    if failed == 0:
        print("🎉 All tests passed! Schema system is ready.")
        return 0
    else:
        print("⚠️  Some tests failed. Check the output above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())