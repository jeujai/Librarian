#!/usr/bin/env python3
"""
Milvus Health Check Script

Dedicated health check script for Milvus service in local development.
Provides detailed Milvus-specific health monitoring and diagnostics.
"""

import os
import sys
import time
import json
import argparse
from datetime import datetime
from typing import Dict, List, Any, Optional

try:
    from pymilvus import connections, Collection, FieldSchema, CollectionSchema, DataType, utility
    from pymilvus.exceptions import MilvusException
    PYMILVUS_AVAILABLE = True
except ImportError:
    PYMILVUS_AVAILABLE = False

class MilvusHealthChecker:
    """Dedicated Milvus health checker with comprehensive diagnostics."""
    
    def __init__(self, host: str = "localhost", port: int = 19530):
        self.host = host
        self.port = port
        self.connection_alias = "health_check"
        self.test_collection_name = "health_check_collection"
        
    def connect(self, timeout: int = 10) -> bool:
        """Establish Milvus connection with timeout."""
        try:
            connections.connect(
                alias=self.connection_alias,
                host=self.host,
                port=str(self.port),
                timeout=timeout
            )
            
            # Test connection by listing collections
            utility.list_collections(using=self.connection_alias)
            return True
            
        except Exception as e:
            print(f"Connection failed: {e}", file=sys.stderr)
            return False
    
    def disconnect(self):
        """Close Milvus connection."""
        try:
            connections.disconnect(alias=self.connection_alias)
        except:
            pass
    
    def check_basic_connectivity(self) -> Dict[str, Any]:
        """Test basic Milvus connectivity."""
        start_time = time.time()
        
        try:
            if not self.connect():
                return {
                    "status": "CRITICAL",
                    "message": "Failed to connect to Milvus",
                    "duration_ms": (time.time() - start_time) * 1000
                }
            
            # Test basic operations
            collections = utility.list_collections(using=self.connection_alias)
            
            return {
                "status": "OK",
                "message": "Milvus connection successful",
                "duration_ms": (time.time() - start_time) * 1000,
                "details": {
                    "existing_collections": collections,
                    "collection_count": len(collections)
                }
            }
        except Exception as e:
            return {
                "status": "CRITICAL",
                "message": f"Connection test failed: {str(e)}",
                "duration_ms": (time.time() - start_time) * 1000
            }
    
    def check_server_info(self) -> Dict[str, Any]:
        """Check Milvus server information."""
        start_time = time.time()
        
        try:
            # Get server version
            version = utility.get_server_version(using=self.connection_alias)
            
            # Get server type
            server_type = utility.get_server_type(using=self.connection_alias)
            
            return {
                "status": "OK",
                "message": f"Milvus {version} ({server_type})",
                "duration_ms": (time.time() - start_time) * 1000,
                "details": {
                    "version": version,
                    "server_type": server_type
                }
            }
        except Exception as e:
            return {
                "status": "WARNING",
                "message": f"Server info check failed: {str(e)}",
                "duration_ms": (time.time() - start_time) * 1000
            }
    
    def check_collection_operations(self) -> Dict[str, Any]:
        """Test collection creation and management."""
        start_time = time.time()
        
        try:
            # Clean up any existing test collection
            try:
                utility.drop_collection(self.test_collection_name, using=self.connection_alias)
            except:
                pass
            
            # Define collection schema
            fields = [
                FieldSchema(name="id", dtype=DataType.VARCHAR, max_length=255, is_primary=True),
                FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=128),
                FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=1000),
            ]
            
            schema = CollectionSchema(
                fields=fields,
                description="Health check test collection"
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
                "field_count": len(collection.schema.fields)
            }
            
            return {
                "status": "OK",
                "message": "Collection operations successful",
                "duration_ms": (time.time() - start_time) * 1000,
                "details": collection_info
            }
        except Exception as e:
            return {
                "status": "CRITICAL",
                "message": f"Collection operations failed: {str(e)}",
                "duration_ms": (time.time() - start_time) * 1000
            }
    
    def check_index_operations(self) -> Dict[str, Any]:
        """Test index creation and management."""
        start_time = time.time()
        
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
                    "metric_type": index.params.get("metric_type")
                })
            
            return {
                "status": "OK",
                "message": f"Index operations successful ({len(index_info)} indexes)",
                "duration_ms": (time.time() - start_time) * 1000,
                "details": {"indexes": index_info}
            }
        except Exception as e:
            return {
                "status": "CRITICAL",
                "message": f"Index operations failed: {str(e)}",
                "duration_ms": (time.time() - start_time) * 1000
            }
    
    def check_data_operations(self) -> Dict[str, Any]:
        """Test data insertion and retrieval."""
        start_time = time.time()
        
        try:
            collection = Collection(self.test_collection_name, using=self.connection_alias)
            
            # Prepare test data
            test_data = [
                ["health_test_1", "health_test_2", "health_test_3"],  # ids
                [
                    [0.1] * 128,  # embedding 1
                    [0.2] * 128,  # embedding 2
                    [0.3] * 128,  # embedding 3
                ],
                ["Health test text 1", "Health test text 2", "Health test text 3"]  # text
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
                expr="id in ['health_test_1', 'health_test_2']",
                output_fields=["id", "text"]
            )
            
            return {
                "status": "OK",
                "message": f"Data operations successful ({num_entities} entities)",
                "duration_ms": (time.time() - start_time) * 1000,
                "details": {
                    "inserted_entities": len(insert_result.primary_keys),
                    "total_entities": num_entities,
                    "query_results": len(query_results)
                }
            }
        except Exception as e:
            return {
                "status": "CRITICAL",
                "message": f"Data operations failed: {str(e)}",
                "duration_ms": (time.time() - start_time) * 1000
            }
    
    def check_search_operations(self) -> Dict[str, Any]:
        """Test vector similarity search."""
        start_time = time.time()
        
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
            
            query_vector = [[0.15] * 128]  # Similar to test data
            
            search_start = time.time()
            search_results = collection.search(
                data=query_vector,
                anns_field="embedding",
                param=search_params,
                limit=3,
                output_fields=["id", "text"]
            )
            search_duration = (time.time() - search_start) * 1000
            
            # Process results
            results_count = sum(len(hits) for hits in search_results)
            
            # Determine status based on search performance
            if search_duration < 100:
                status = "OK"
            elif search_duration < 500:
                status = "WARNING"
            else:
                status = "CRITICAL"
            
            return {
                "status": status,
                "message": f"Search operations successful ({results_count} results in {search_duration:.1f}ms)",
                "duration_ms": (time.time() - start_time) * 1000,
                "details": {
                    "search_results_count": results_count,
                    "search_duration_ms": round(search_duration, 2),
                    "performance_acceptable": search_duration < 200
                }
            }
        except Exception as e:
            return {
                "status": "CRITICAL",
                "message": f"Search operations failed: {str(e)}",
                "duration_ms": (time.time() - start_time) * 1000
            }
    
    def check_performance_metrics(self) -> Dict[str, Any]:
        """Check performance metrics and resource usage."""
        start_time = time.time()
        
        try:
            collection = Collection(self.test_collection_name, using=self.connection_alias)
            
            # Measure multiple search operations
            search_times = []
            search_params = {"metric_type": "L2", "params": {"nprobe": 10}}
            query_vector = [[0.1] * 128]
            
            for _ in range(5):
                search_start = time.time()
                collection.search(
                    data=query_vector,
                    anns_field="embedding",
                    param=search_params,
                    limit=5
                )
                search_times.append((time.time() - search_start) * 1000)
            
            avg_search_time = sum(search_times) / len(search_times)
            min_search_time = min(search_times)
            max_search_time = max(search_times)
            
            # Get collection statistics
            try:
                stats = utility.get_query_segment_info(
                    collection_name=self.test_collection_name,
                    using=self.connection_alias
                )
                segment_count = len(stats)
            except:
                segment_count = "unknown"
            
            # Determine status based on performance
            if avg_search_time < 50:
                status = "OK"
            elif avg_search_time < 200:
                status = "WARNING"
            else:
                status = "CRITICAL"
            
            return {
                "status": status,
                "message": f"Performance metrics: {avg_search_time:.1f}ms avg search time",
                "duration_ms": (time.time() - start_time) * 1000,
                "details": {
                    "avg_search_time_ms": round(avg_search_time, 2),
                    "min_search_time_ms": round(min_search_time, 2),
                    "max_search_time_ms": round(max_search_time, 2),
                    "segment_count": segment_count,
                    "performance_acceptable": avg_search_time < 100
                }
            }
        except Exception as e:
            return {
                "status": "WARNING",
                "message": f"Performance metrics check failed: {str(e)}",
                "duration_ms": (time.time() - start_time) * 1000
            }
    
    def check_dependencies(self) -> Dict[str, Any]:
        """Check Milvus dependencies (etcd and MinIO)."""
        start_time = time.time()
        
        dependencies = {}
        overall_status = "OK"
        
        # Check etcd
        try:
            import subprocess
            result = subprocess.run(
                ["curl", "-f", "-s", "http://localhost:2379/health"],
                capture_output=True, text=True, timeout=5
            )
            
            if result.returncode == 0:
                dependencies["etcd"] = {"status": "OK", "message": "etcd healthy"}
            else:
                dependencies["etcd"] = {"status": "CRITICAL", "message": "etcd not responding"}
                overall_status = "CRITICAL"
        except Exception as e:
            dependencies["etcd"] = {"status": "CRITICAL", "message": f"etcd check failed: {str(e)}"}
            overall_status = "CRITICAL"
        
        # Check MinIO
        try:
            result = subprocess.run(
                ["curl", "-f", "-s", "http://localhost:9000/minio/health/live"],
                capture_output=True, text=True, timeout=5
            )
            
            if result.returncode == 0:
                dependencies["minio"] = {"status": "OK", "message": "MinIO healthy"}
            else:
                dependencies["minio"] = {"status": "CRITICAL", "message": "MinIO not responding"}
                overall_status = "CRITICAL"
        except Exception as e:
            dependencies["minio"] = {"status": "CRITICAL", "message": f"MinIO check failed: {str(e)}"}
            overall_status = "CRITICAL"
        
        healthy_deps = sum(1 for dep in dependencies.values() if dep["status"] == "OK")
        total_deps = len(dependencies)
        
        return {
            "status": overall_status,
            "message": f"Dependencies: {healthy_deps}/{total_deps} healthy",
            "duration_ms": (time.time() - start_time) * 1000,
            "details": dependencies
        }
    
    def cleanup_test_data(self) -> Dict[str, Any]:
        """Clean up test collection and data."""
        start_time = time.time()
        
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
            
            return {
                "status": "OK",
                "message": "Test data cleaned up successfully",
                "duration_ms": (time.time() - start_time) * 1000
            }
        except Exception as e:
            return {
                "status": "WARNING",
                "message": f"Cleanup failed: {str(e)}",
                "duration_ms": (time.time() - start_time) * 1000
            }
    
    def run_comprehensive_check(self) -> Dict[str, Any]:
        """Run all health checks and return comprehensive results."""
        if not PYMILVUS_AVAILABLE:
            return {
                "status": "CRITICAL",
                "message": "pymilvus not available - cannot perform Milvus health checks",
                "timestamp": datetime.now().isoformat(),
                "checks": {}
            }
        
        start_time = datetime.now()
        checks = {}
        
        # Run all checks
        check_methods = [
            ("connectivity", self.check_basic_connectivity),
            ("server_info", self.check_server_info),
            ("dependencies", self.check_dependencies),
            ("collection_ops", self.check_collection_operations),
            ("index_ops", self.check_index_operations),
            ("data_ops", self.check_data_operations),
            ("search_ops", self.check_search_operations),
            ("performance", self.check_performance_metrics),
            ("cleanup", self.cleanup_test_data)
        ]
        
        overall_status = "OK"
        
        for check_name, check_method in check_methods:
            try:
                result = check_method()
                checks[check_name] = result
                
                # Update overall status
                if result["status"] == "CRITICAL":
                    overall_status = "CRITICAL"
                elif result["status"] == "WARNING" and overall_status != "CRITICAL":
                    overall_status = "WARNING"
                    
            except Exception as e:
                checks[check_name] = {
                    "status": "CRITICAL",
                    "message": f"Check failed: {str(e)}",
                    "duration_ms": 0
                }
                overall_status = "CRITICAL"
            finally:
                self.disconnect()
        
        end_time = datetime.now()
        total_duration = (end_time - start_time).total_seconds()
        
        return {
            "service": "milvus",
            "status": overall_status,
            "message": f"Milvus health check completed ({overall_status})",
            "timestamp": end_time.isoformat(),
            "duration_seconds": round(total_duration, 2),
            "connection_info": {
                "host": self.host,
                "port": self.port
            },
            "checks": checks,
            "summary": {
                "total_checks": len(checks),
                "ok": sum(1 for c in checks.values() if c["status"] == "OK"),
                "warning": sum(1 for c in checks.values() if c["status"] == "WARNING"),
                "critical": sum(1 for c in checks.values() if c["status"] == "CRITICAL"),
                "info": sum(1 for c in checks.values() if c["status"] == "INFO")
            }
        }


def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Milvus Health Check")
    parser.add_argument("--host", default="localhost", help="Milvus host")
    parser.add_argument("--port", type=int, default=19530, help="Milvus port")
    parser.add_argument("--json", action="store_true", help="Output JSON format")
    parser.add_argument("--quiet", action="store_true", help="Minimal output")
    
    args = parser.parse_args()
    
    # Override with environment variables if available
    host = os.getenv("MILVUS_HOST", args.host)
    port = int(os.getenv("MILVUS_PORT", args.port))
    
    checker = MilvusHealthChecker(host, port)
    results = checker.run_comprehensive_check()
    
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        # Human-readable output
        status_emoji = {
            "OK": "✅",
            "WARNING": "⚠️",
            "CRITICAL": "❌",
            "INFO": "ℹ️"
        }
        
        print(f"\n{'='*60}")
        print(f"Milvus Health Check Results")
        print(f"{'='*60}")
        print(f"Overall Status: {status_emoji.get(results['status'], '?')} {results['status']}")
        print(f"Duration: {results['duration_seconds']}s")
        print(f"Timestamp: {results['timestamp']}")
        
        if not args.quiet:
            print(f"\nConnection: {host}:{port}")
            
            print(f"\nCheck Results:")
            for check_name, check_result in results['checks'].items():
                emoji = status_emoji.get(check_result['status'], '?')
                duration = check_result.get('duration_ms', 0)
                print(f"  {emoji} {check_name.replace('_', ' ').title()}: {check_result['message']} ({duration:.1f}ms)")
            
            summary = results['summary']
            print(f"\nSummary: {summary['ok']} OK, {summary['warning']} Warning, {summary['critical']} Critical, {summary['info']} Info")
    
    # Exit with appropriate code
    if results['status'] == "CRITICAL":
        sys.exit(2)
    elif results['status'] == "WARNING":
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()