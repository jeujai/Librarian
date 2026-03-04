#!/usr/bin/env python3
"""
Milvus Health Check Script

This script performs comprehensive health checks for the Milvus vector database
to ensure it's working properly in the local development environment.
"""

import sys
import time
import json
from typing import Dict, List, Any, Optional
from datetime import datetime

try:
    from pymilvus import connections, Collection, utility, DataType, FieldSchema, CollectionSchema
    from pymilvus.exceptions import MilvusException
except ImportError:
    print("ERROR: pymilvus not installed. Run: pip install pymilvus")
    sys.exit(1)


class MilvusHealthChecker:
    """Comprehensive health checker for Milvus vector database."""
    
    def __init__(self, host: str = "localhost", port: int = 19530):
        self.host = host
        self.port = port
        self.connection_alias = "health_check"
        self.test_collection_name = "health_check_test"
        self.results: List[Dict[str, Any]] = []
    
    def add_result(self, check_name: str, status: str, details: str, duration_ms: Optional[float] = None):
        """Add a health check result."""
        result = {
            "check_name": check_name,
            "status": status,
            "details": details,
            "timestamp": datetime.now().isoformat()
        }
        if duration_ms is not None:
            result["duration_ms"] = round(duration_ms, 2)
        self.results.append(result)
    
    def check_connectivity(self) -> bool:
        """Test basic connectivity to Milvus server."""
        start_time = time.time()
        try:
            connections.connect(
                alias=self.connection_alias,
                host=self.host,
                port=self.port,
                timeout=10
            )
            duration = (time.time() - start_time) * 1000
            self.add_result(
                "Milvus Connectivity",
                "OK",
                f"Connected to {self.host}:{self.port}",
                duration
            )
            return True
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            self.add_result(
                "Milvus Connectivity",
                "CRITICAL",
                f"Failed to connect: {str(e)}",
                duration
            )
            return False
    
    def check_server_version(self):
        """Check Milvus server version."""
        try:
            version = utility.get_server_version(using=self.connection_alias)
            self.add_result(
                "Milvus Version",
                "INFO",
                f"Server version: {version}"
            )
        except Exception as e:
            self.add_result(
                "Milvus Version",
                "WARNING",
                f"Could not get version: {str(e)}"
            )
    
    def check_collections(self):
        """Check existing collections and their status."""
        try:
            collections = utility.list_collections(using=self.connection_alias)
            self.add_result(
                "Collections Count",
                "INFO",
                f"Found {len(collections)} collections: {', '.join(collections) if collections else 'None'}"
            )
            
            # Check each collection's status
            for collection_name in collections:
                try:
                    collection = Collection(collection_name, using=self.connection_alias)
                    num_entities = collection.num_entities
                    self.add_result(
                        f"Collection: {collection_name}",
                        "OK",
                        f"Entities: {num_entities}, Loaded: {utility.load_state(collection_name, using=self.connection_alias)}"
                    )
                except Exception as e:
                    self.add_result(
                        f"Collection: {collection_name}",
                        "WARNING",
                        f"Error checking collection: {str(e)}"
                    )
        except Exception as e:
            self.add_result(
                "Collections Check",
                "WARNING",
                f"Could not list collections: {str(e)}"
            )
    
    def check_vector_operations(self):
        """Test basic vector operations by creating a temporary collection."""
        start_time = time.time()
        try:
            # Clean up any existing test collection
            if utility.has_collection(self.test_collection_name, using=self.connection_alias):
                utility.drop_collection(self.test_collection_name, using=self.connection_alias)
            
            # Define collection schema
            fields = [
                FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
                FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=128),
                FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=512)
            ]
            schema = CollectionSchema(fields, "Health check test collection")
            
            # Create collection
            collection = Collection(self.test_collection_name, schema, using=self.connection_alias)
            
            # Insert test data
            test_vectors = [[0.1] * 128, [0.2] * 128, [0.3] * 128]
            test_texts = ["test1", "test2", "test3"]
            entities = [test_vectors, test_texts]
            
            insert_result = collection.insert(entities)
            collection.flush()
            
            # Create index
            index_params = {
                "metric_type": "L2",
                "index_type": "IVF_FLAT",
                "params": {"nlist": 128}
            }
            collection.create_index("vector", index_params)
            
            # Load collection
            collection.load()
            
            # Perform search
            search_params = {"metric_type": "L2", "params": {"nprobe": 10}}
            search_vectors = [[0.15] * 128]
            results = collection.search(
                search_vectors,
                "vector",
                search_params,
                limit=3,
                output_fields=["text"]
            )
            
            # Clean up
            utility.drop_collection(self.test_collection_name, using=self.connection_alias)
            
            duration = (time.time() - start_time) * 1000
            self.add_result(
                "Vector Operations",
                "OK",
                f"Successfully created collection, inserted {len(test_vectors)} vectors, created index, and performed search",
                duration
            )
            
        except Exception as e:
            # Clean up on error
            try:
                if utility.has_collection(self.test_collection_name, using=self.connection_alias):
                    utility.drop_collection(self.test_collection_name, using=self.connection_alias)
            except:
                pass
            
            duration = (time.time() - start_time) * 1000
            self.add_result(
                "Vector Operations",
                "CRITICAL",
                f"Vector operations failed: {str(e)}",
                duration
            )
    
    def check_resource_usage(self):
        """Check resource usage and performance metrics."""
        try:
            # This is a placeholder for resource checks
            # In a real implementation, you might check memory usage, disk space, etc.
            self.add_result(
                "Resource Usage",
                "INFO",
                "Resource monitoring not implemented in basic health check"
            )
        except Exception as e:
            self.add_result(
                "Resource Usage",
                "WARNING",
                f"Could not check resources: {str(e)}"
            )
    
    def run_all_checks(self) -> Dict[str, Any]:
        """Run all health checks and return results."""
        print(f"Running Milvus health checks against {self.host}:{self.port}...")
        
        # Basic connectivity is required for other checks
        if not self.check_connectivity():
            return self.get_summary()
        
        # Run all other checks
        self.check_server_version()
        self.check_collections()
        self.check_vector_operations()
        self.check_resource_usage()
        
        # Disconnect
        try:
            connections.disconnect(self.connection_alias)
        except:
            pass
        
        return self.get_summary()
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary of all health check results."""
        critical_count = sum(1 for r in self.results if r["status"] == "CRITICAL")
        warning_count = sum(1 for r in self.results if r["status"] == "WARNING")
        ok_count = sum(1 for r in self.results if r["status"] == "OK")
        info_count = sum(1 for r in self.results if r["status"] == "INFO")
        
        overall_status = "OK"
        if critical_count > 0:
            overall_status = "CRITICAL"
        elif warning_count > 0:
            overall_status = "WARNING"
        
        return {
            "overall_status": overall_status,
            "summary": {
                "critical": critical_count,
                "warning": warning_count,
                "ok": ok_count,
                "info": info_count,
                "total": len(self.results)
            },
            "checks": self.results,
            "timestamp": datetime.now().isoformat()
        }


def main():
    """Main function to run health checks."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Milvus Health Check")
    parser.add_argument("--host", default="localhost", help="Milvus host")
    parser.add_argument("--port", type=int, default=19530, help="Milvus port")
    parser.add_argument("--json", action="store_true", help="Output JSON format")
    parser.add_argument("--quiet", action="store_true", help="Only show summary")
    
    args = parser.parse_args()
    
    checker = MilvusHealthChecker(args.host, args.port)
    results = checker.run_all_checks()
    
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        # Human-readable output
        print(f"\n{'='*60}")
        print(f"MILVUS HEALTH CHECK RESULTS")
        print(f"{'='*60}")
        print(f"Overall Status: {results['overall_status']}")
        print(f"Timestamp: {results['timestamp']}")
        print(f"\nSummary:")
        print(f"  Critical: {results['summary']['critical']}")
        print(f"  Warning:  {results['summary']['warning']}")
        print(f"  OK:       {results['summary']['ok']}")
        print(f"  Info:     {results['summary']['info']}")
        print(f"  Total:    {results['summary']['total']}")
        
        if not args.quiet:
            print(f"\nDetailed Results:")
            print(f"{'-'*60}")
            for check in results['checks']:
                duration_str = f" ({check['duration_ms']}ms)" if 'duration_ms' in check else ""
                print(f"[{check['status']:>8}] {check['check_name']}: {check['details']}{duration_str}")
    
    # Exit with appropriate code
    if results['overall_status'] == "CRITICAL":
        sys.exit(2)
    elif results['overall_status'] == "WARNING":
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()