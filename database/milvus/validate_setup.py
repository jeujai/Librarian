#!/usr/bin/env python3
"""
Milvus Setup Validation Script

This script validates that Milvus is properly configured and accessible
for the Multimodal Librarian local development environment.
"""

import sys
import time
import json
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

try:
    from pymilvus import connections, Collection, FieldSchema, CollectionSchema, DataType, utility
    from pymilvus.exceptions import MilvusException
except ImportError:
    print("ERROR: pymilvus not installed. Run: pip install pymilvus")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class ValidationResult:
    """Result of a validation check"""
    name: str
    success: bool
    message: str
    details: Optional[Dict[str, Any]] = None

class MilvusValidator:
    """Validates Milvus setup and configuration"""
    
    def __init__(self, host: str = "localhost", port: int = 19530):
        self.host = host
        self.port = port
        self.connection_alias = "validation"
        self.test_collection_name = "validation_test_collection"
        
    def run_all_validations(self) -> List[ValidationResult]:
        """Run all validation checks"""
        results = []
        
        # Connection validation
        connection_result = self.validate_connection()
        results.append(connection_result)
        
        if not connection_result.success:
            logger.error("Cannot connect to Milvus. Skipping remaining validations.")
            return results
        
        # Server validation
        results.append(self.validate_server_info())
        
        # Collection operations
        results.append(self.validate_collection_operations())
        
        # Index operations
        results.append(self.validate_index_operations())
        
        # Data operations
        results.append(self.validate_data_operations())
        
        # Search operations
        results.append(self.validate_search_operations())
        
        # Performance validation
        results.append(self.validate_performance())
        
        # Cleanup
        results.append(self.cleanup_test_data())
        
        return results
    
    def validate_connection(self) -> ValidationResult:
        """Validate connection to Milvus server"""
        try:
            logger.info(f"Connecting to Milvus at {self.host}:{self.port}")
            connections.connect(
                alias=self.connection_alias,
                host=self.host,
                port=str(self.port),
                timeout=10
            )
            
            # Test the connection
            collections = utility.list_collections(using=self.connection_alias)
            
            return ValidationResult(
                name="Connection",
                success=True,
                message=f"Successfully connected to Milvus at {self.host}:{self.port}",
                details={"existing_collections": collections}
            )
            
        except Exception as e:
            return ValidationResult(
                name="Connection",
                success=False,
                message=f"Failed to connect to Milvus: {str(e)}"
            )
    
    def validate_server_info(self) -> ValidationResult:
        """Validate server information and capabilities"""
        try:
            # Get server version
            version = utility.get_server_version(using=self.connection_alias)
            
            # Get server type
            server_type = utility.get_server_type(using=self.connection_alias)
            
            details = {
                "version": version,
                "server_type": server_type,
            }
            
            return ValidationResult(
                name="Server Info",
                success=True,
                message=f"Milvus server info retrieved successfully",
                details=details
            )
            
        except Exception as e:
            return ValidationResult(
                name="Server Info",
                success=False,
                message=f"Failed to get server info: {str(e)}"
            )
    
    def validate_collection_operations(self) -> ValidationResult:
        """Validate collection creation and management"""
        try:
            # Define collection schema
            fields = [
                FieldSchema(name="id", dtype=DataType.VARCHAR, max_length=255, is_primary=True),
                FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=128),
                FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=1000),
            ]
            
            schema = CollectionSchema(
                fields=fields,
                description="Test collection for validation"
            )
            
            # Create collection
            collection = Collection(
                name=self.test_collection_name,
                schema=schema,
                using=self.connection_alias
            )
            
            # Verify collection exists
            collections = utility.list_collections(using=self.connection_alias)
            if self.test_collection_name not in collections:
                raise Exception("Collection not found after creation")
            
            # Get collection info
            collection_info = {
                "name": collection.name,
                "description": collection.description,
                "num_entities": collection.num_entities,
                "schema": {
                    "fields": [
                        {
                            "name": field.name,
                            "type": str(field.dtype),
                            "params": field.params
                        }
                        for field in collection.schema.fields
                    ]
                }
            }
            
            return ValidationResult(
                name="Collection Operations",
                success=True,
                message="Collection operations validated successfully",
                details=collection_info
            )
            
        except Exception as e:
            return ValidationResult(
                name="Collection Operations",
                success=False,
                message=f"Collection operations failed: {str(e)}"
            )
    
    def validate_index_operations(self) -> ValidationResult:
        """Validate index creation and management"""
        try:
            collection = Collection(self.test_collection_name, using=self.connection_alias)
            
            # Create index
            index_params = {
                "metric_type": "L2",
                "index_type": "IVF_FLAT",
                "params": {"nlist": 128}
            }
            
            collection.create_index(
                field_name="embedding",
                index_params=index_params
            )
            
            # Wait for index to be built
            time.sleep(2)
            
            # Check index info
            indexes = collection.indexes
            index_info = []
            for index in indexes:
                index_info.append({
                    "field_name": index.field_name,
                    "index_type": index.params.get("index_type"),
                    "metric_type": index.params.get("metric_type"),
                    "params": index.params.get("params", {})
                })
            
            return ValidationResult(
                name="Index Operations",
                success=True,
                message="Index operations validated successfully",
                details={"indexes": index_info}
            )
            
        except Exception as e:
            return ValidationResult(
                name="Index Operations",
                success=False,
                message=f"Index operations failed: {str(e)}"
            )
    
    def validate_data_operations(self) -> ValidationResult:
        """Validate data insertion and retrieval"""
        try:
            collection = Collection(self.test_collection_name, using=self.connection_alias)
            
            # Prepare test data
            test_data = [
                ["test_1", "test_2", "test_3"],  # ids
                [
                    [0.1] * 128,  # embedding 1
                    [0.2] * 128,  # embedding 2
                    [0.3] * 128,  # embedding 3
                ],
                ["Sample text 1", "Sample text 2", "Sample text 3"]  # text
            ]
            
            # Insert data
            insert_result = collection.insert(test_data)
            collection.flush()
            
            # Wait for data to be available
            time.sleep(2)
            
            # Check entity count
            num_entities = collection.num_entities
            
            # Query data
            query_results = collection.query(
                expr="id in ['test_1', 'test_2']",
                output_fields=["id", "text"]
            )
            
            details = {
                "inserted_entities": len(insert_result.primary_keys),
                "total_entities": num_entities,
                "query_results": len(query_results),
                "sample_data": query_results[:2] if query_results else []
            }
            
            return ValidationResult(
                name="Data Operations",
                success=True,
                message="Data operations validated successfully",
                details=details
            )
            
        except Exception as e:
            return ValidationResult(
                name="Data Operations",
                success=False,
                message=f"Data operations failed: {str(e)}"
            )
    
    def validate_search_operations(self) -> ValidationResult:
        """Validate vector similarity search"""
        try:
            collection = Collection(self.test_collection_name, using=self.connection_alias)
            
            # Load collection for search
            collection.load()
            
            # Wait for collection to be loaded
            time.sleep(3)
            
            # Perform search
            search_params = {
                "metric_type": "L2",
                "params": {"nprobe": 10}
            }
            
            query_vector = [[0.15] * 128]  # Similar to test_1
            
            search_results = collection.search(
                data=query_vector,
                anns_field="embedding",
                param=search_params,
                limit=3,
                output_fields=["id", "text"]
            )
            
            # Process results
            results_info = []
            for hits in search_results:
                for hit in hits:
                    results_info.append({
                        "id": hit.entity.get("id"),
                        "text": hit.entity.get("text"),
                        "distance": hit.distance
                    })
            
            details = {
                "search_results_count": len(results_info),
                "results": results_info
            }
            
            return ValidationResult(
                name="Search Operations",
                success=True,
                message="Search operations validated successfully",
                details=details
            )
            
        except Exception as e:
            return ValidationResult(
                name="Search Operations",
                success=False,
                message=f"Search operations failed: {str(e)}"
            )
    
    def validate_performance(self) -> ValidationResult:
        """Validate basic performance metrics"""
        try:
            collection = Collection(self.test_collection_name, using=self.connection_alias)
            
            # Measure search performance
            start_time = time.time()
            
            search_params = {"metric_type": "L2", "params": {"nprobe": 10}}
            query_vector = [[0.1] * 128]
            
            # Perform multiple searches
            for _ in range(10):
                collection.search(
                    data=query_vector,
                    anns_field="embedding",
                    param=search_params,
                    limit=5
                )
            
            end_time = time.time()
            avg_search_time = (end_time - start_time) / 10
            
            # Get collection statistics
            stats = utility.get_query_segment_info(
                collection_name=self.test_collection_name,
                using=self.connection_alias
            )
            
            details = {
                "average_search_time_ms": round(avg_search_time * 1000, 2),
                "segment_count": len(stats),
                "performance_acceptable": avg_search_time < 0.1  # Less than 100ms
            }
            
            success = avg_search_time < 1.0  # Less than 1 second is acceptable
            message = f"Performance validation {'passed' if success else 'failed'}"
            
            return ValidationResult(
                name="Performance",
                success=success,
                message=message,
                details=details
            )
            
        except Exception as e:
            return ValidationResult(
                name="Performance",
                success=False,
                message=f"Performance validation failed: {str(e)}"
            )
    
    def cleanup_test_data(self) -> ValidationResult:
        """Clean up test collection and data"""
        try:
            # Drop test collection
            utility.drop_collection(
                collection_name=self.test_collection_name,
                using=self.connection_alias
            )
            
            # Verify collection is dropped
            collections = utility.list_collections(using=self.connection_alias)
            if self.test_collection_name in collections:
                raise Exception("Test collection still exists after drop")
            
            # Disconnect
            connections.disconnect(alias=self.connection_alias)
            
            return ValidationResult(
                name="Cleanup",
                success=True,
                message="Test data cleaned up successfully"
            )
            
        except Exception as e:
            return ValidationResult(
                name="Cleanup",
                success=False,
                message=f"Cleanup failed: {str(e)}"
            )

def print_results(results: List[ValidationResult]) -> None:
    """Print validation results in a formatted way"""
    print("\n" + "="*80)
    print("MILVUS VALIDATION RESULTS")
    print("="*80)
    
    passed = 0
    failed = 0
    
    for result in results:
        status = "✅ PASS" if result.success else "❌ FAIL"
        print(f"\n{status} {result.name}")
        print(f"   {result.message}")
        
        if result.details:
            print(f"   Details: {json.dumps(result.details, indent=2)}")
        
        if result.success:
            passed += 1
        else:
            failed += 1
    
    print("\n" + "="*80)
    print(f"SUMMARY: {passed} passed, {failed} failed")
    print("="*80)
    
    if failed > 0:
        print("\n⚠️  Some validations failed. Check the logs above for details.")
        print("Common issues:")
        print("- Milvus server not running: docker-compose -f docker-compose.local.yml up -d milvus")
        print("- Network connectivity: Check if ports 19530 and 9091 are accessible")
        print("- Dependencies: Ensure etcd and minio are running")
    else:
        print("\n🎉 All validations passed! Milvus is ready for development.")

def main():
    """Main validation function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Validate Milvus setup")
    parser.add_argument("--host", default="localhost", help="Milvus host")
    parser.add_argument("--port", type=int, default=19530, help="Milvus port")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    validator = MilvusValidator(host=args.host, port=args.port)
    results = validator.run_all_validations()
    
    print_results(results)
    
    # Exit with error code if any validation failed
    failed_count = sum(1 for r in results if not r.success)
    sys.exit(failed_count)

if __name__ == "__main__":
    main()