#!/usr/bin/env python3
"""
Neo4j Health Check Script

Dedicated health check script for Neo4j service in local development.
Provides detailed Neo4j-specific health monitoring and diagnostics.
"""

import os
import sys
import time
import json
import argparse
from datetime import datetime
from typing import Dict, List, Any, Optional

try:
    from neo4j import GraphDatabase, Driver
    from neo4j.exceptions import ServiceUnavailable, AuthError
    NEO4J_AVAILABLE = True
except ImportError:
    NEO4J_AVAILABLE = False

class Neo4jHealthChecker:
    """Dedicated Neo4j health checker with comprehensive diagnostics."""
    
    def __init__(self, uri: str = "bolt://localhost:7687", user: str = "neo4j", password: str = "ml_password"):
        self.uri = uri
        self.user = user
        self.password = password
        self.driver: Optional[Driver] = None
        
    def connect(self, timeout: int = 10) -> bool:
        """Establish Neo4j connection with timeout."""
        try:
            self.driver = GraphDatabase.driver(
                self.uri, 
                auth=(self.user, self.password),
                connection_timeout=timeout,
                max_connection_lifetime=300
            )
            
            # Test connection
            with self.driver.session() as session:
                result = session.run("RETURN 1 as test")
                test_value = result.single()["test"]
                return test_value == 1
                
        except Exception as e:
            print(f"Connection failed: {e}", file=sys.stderr)
            return False
    
    def disconnect(self):
        """Close Neo4j connection."""
        if self.driver:
            self.driver.close()
            self.driver = None
    
    def execute_query(self, query: str, parameters: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """Execute query and return results."""
        with self.driver.session() as session:
            result = session.run(query, parameters or {})
            return [record.data() for record in result]
    
    def check_basic_connectivity(self) -> Dict[str, Any]:
        """Test basic Neo4j connectivity."""
        start_time = time.time()
        
        try:
            if not self.connect():
                return {
                    "status": "CRITICAL",
                    "message": "Failed to connect to Neo4j",
                    "duration_ms": (time.time() - start_time) * 1000
                }
            
            # Test basic query
            result = self.execute_query("RETURN 'Hello Neo4j' as greeting, datetime() as server_time")
            row = result[0]
            
            return {
                "status": "OK",
                "message": "Neo4j connection successful",
                "duration_ms": (time.time() - start_time) * 1000,
                "details": {
                    "greeting": row["greeting"],
                    "server_time": str(row["server_time"])
                }
            }
        except Exception as e:
            return {
                "status": "CRITICAL",
                "message": f"Connection test failed: {str(e)}",
                "duration_ms": (time.time() - start_time) * 1000
            }
    
    def check_version_and_edition(self) -> Dict[str, Any]:
        """Check Neo4j version and edition."""
        start_time = time.time()
        
        try:
            result = self.execute_query("""
                CALL dbms.components() 
                YIELD name, versions, edition 
                WHERE name = 'Neo4j Kernel' 
                RETURN versions[0] as version, edition
            """)
            
            if not result:
                return {
                    "status": "WARNING",
                    "message": "Could not retrieve version information",
                    "duration_ms": (time.time() - start_time) * 1000
                }
            
            row = result[0]
            version = row["version"]
            edition = row["edition"]
            
            return {
                "status": "OK",
                "message": f"Neo4j {version} ({edition})",
                "duration_ms": (time.time() - start_time) * 1000,
                "details": {
                    "version": version,
                    "edition": edition
                }
            }
        except Exception as e:
            return {
                "status": "WARNING",
                "message": f"Version check failed: {str(e)}",
                "duration_ms": (time.time() - start_time) * 1000
            }
    
    def check_apoc_plugin(self) -> Dict[str, Any]:
        """Check APOC plugin availability and functionality."""
        start_time = time.time()
        
        try:
            # Check if APOC procedures are available
            result = self.execute_query("""
                SHOW PROCEDURES 
                YIELD name 
                WHERE name STARTS WITH 'apoc' 
                RETURN count(name) as apocCount
            """)
            
            apoc_count = result[0]["apocCount"]
            
            if apoc_count == 0:
                return {
                    "status": "WARNING",
                    "message": "APOC plugin not available",
                    "duration_ms": (time.time() - start_time) * 1000,
                    "details": {"apoc_procedures": 0}
                }
            
            # Test APOC functionality
            try:
                version_result = self.execute_query("CALL apoc.version() YIELD version RETURN version")
                apoc_version = version_result[0]["version"]
                
                # Test a simple APOC function
                test_result = self.execute_query("RETURN apoc.date.format(timestamp(), 'ms', 'yyyy-MM-dd') as formatted_date")
                formatted_date = test_result[0]["formatted_date"]
                
                return {
                    "status": "OK",
                    "message": f"APOC plugin functional (v{apoc_version})",
                    "duration_ms": (time.time() - start_time) * 1000,
                    "details": {
                        "apoc_version": apoc_version,
                        "apoc_procedures": apoc_count,
                        "test_result": formatted_date
                    }
                }
            except Exception as e:
                return {
                    "status": "WARNING",
                    "message": f"APOC available but not functional: {str(e)}",
                    "duration_ms": (time.time() - start_time) * 1000,
                    "details": {"apoc_procedures": apoc_count}
                }
                
        except Exception as e:
            return {
                "status": "WARNING",
                "message": f"APOC check failed: {str(e)}",
                "duration_ms": (time.time() - start_time) * 1000
            }
    
    def check_gds_plugin(self) -> Dict[str, Any]:
        """Check Graph Data Science plugin availability and functionality."""
        start_time = time.time()
        
        try:
            # Check if GDS is available
            result = self.execute_query("CALL gds.version() YIELD gdsVersion RETURN gdsVersion")
            
            if not result:
                return {
                    "status": "WARNING",
                    "message": "GDS plugin not available",
                    "duration_ms": (time.time() - start_time) * 1000
                }
            
            gds_version = result[0]["gdsVersion"]
            
            # Test GDS functionality with a simple operation
            try:
                # Create minimal test data
                self.execute_query("""
                    MERGE (a:HealthTest {id: 'test1', name: 'Node 1'})
                    MERGE (b:HealthTest {id: 'test2', name: 'Node 2'})
                    MERGE (a)-[:TEST_REL]->(b)
                """)
                
                # Create a simple graph projection
                self.execute_query("""
                    CALL gds.graph.project(
                        'health-test-graph',
                        'HealthTest',
                        'TEST_REL'
                    )
                """)
                
                # Test a simple algorithm
                result = self.execute_query("""
                    CALL gds.pageRank.stream('health-test-graph')
                    YIELD nodeId, score
                    RETURN count(*) as nodeCount, avg(score) as avgScore
                """)
                
                node_count = result[0]["nodeCount"]
                avg_score = result[0]["avgScore"]
                
                # Clean up
                self.execute_query("CALL gds.graph.drop('health-test-graph')")
                self.execute_query("MATCH (n:HealthTest) DETACH DELETE n")
                
                return {
                    "status": "OK",
                    "message": f"GDS plugin functional (v{gds_version})",
                    "duration_ms": (time.time() - start_time) * 1000,
                    "details": {
                        "gds_version": gds_version,
                        "test_nodes": node_count,
                        "avg_pagerank_score": round(float(avg_score), 4)
                    }
                }
                
            except Exception as e:
                # Clean up in case of error
                try:
                    self.execute_query("CALL gds.graph.drop('health-test-graph')")
                    self.execute_query("MATCH (n:HealthTest) DETACH DELETE n")
                except:
                    pass
                
                return {
                    "status": "WARNING",
                    "message": f"GDS available but not functional: {str(e)}",
                    "duration_ms": (time.time() - start_time) * 1000,
                    "details": {"gds_version": gds_version}
                }
                
        except Exception as e:
            return {
                "status": "WARNING",
                "message": f"GDS check failed: {str(e)}",
                "duration_ms": (time.time() - start_time) * 1000
            }
    
    def check_database_statistics(self) -> Dict[str, Any]:
        """Check database statistics and content."""
        start_time = time.time()
        
        try:
            # Get node and relationship counts
            result = self.execute_query("""
                CALL db.stats.retrieve('GRAPH COUNTS') 
                YIELD data 
                RETURN data.nodes as nodes, data.relationships as relationships
            """)
            
            if result:
                nodes = result[0]["nodes"]
                relationships = result[0]["relationships"]
            else:
                # Fallback method
                node_result = self.execute_query("MATCH (n) RETURN count(n) as nodes")
                rel_result = self.execute_query("MATCH ()-[r]->() RETURN count(r) as relationships")
                nodes = node_result[0]["nodes"]
                relationships = rel_result[0]["relationships"]
            
            # Get label information
            label_result = self.execute_query("CALL db.labels()")
            labels = [row["label"] for row in label_result]
            
            # Get relationship types
            rel_type_result = self.execute_query("CALL db.relationshipTypes()")
            rel_types = [row["relationshipType"] for row in rel_type_result]
            
            return {
                "status": "OK",
                "message": f"Database contains {nodes} nodes, {relationships} relationships",
                "duration_ms": (time.time() - start_time) * 1000,
                "details": {
                    "node_count": nodes,
                    "relationship_count": relationships,
                    "label_count": len(labels),
                    "relationship_type_count": len(rel_types),
                    "labels": labels[:10],  # Show first 10 labels
                    "relationship_types": rel_types[:10]  # Show first 10 types
                }
            }
        except Exception as e:
            return {
                "status": "WARNING",
                "message": f"Database statistics check failed: {str(e)}",
                "duration_ms": (time.time() - start_time) * 1000
            }
    
    def check_memory_usage(self) -> Dict[str, Any]:
        """Check memory usage and configuration."""
        start_time = time.time()
        
        try:
            # Get memory configuration
            result = self.execute_query("""
                CALL dbms.listConfig() 
                YIELD name, value 
                WHERE name IN [
                    'server.memory.heap.initial_size',
                    'server.memory.heap.max_size',
                    'server.memory.pagecache.size'
                ]
                RETURN name, value
            """)
            
            memory_config = {row["name"]: row["value"] for row in result}
            
            # Try to get memory usage (may not be available in all versions)
            try:
                usage_result = self.execute_query("""
                    CALL dbms.queryJmx('java.lang:type=Memory') 
                    YIELD attributes 
                    RETURN attributes.HeapMemoryUsage.used as heapUsed,
                           attributes.HeapMemoryUsage.max as heapMax
                """)
                
                if usage_result:
                    heap_used = usage_result[0]["heapUsed"]
                    heap_max = usage_result[0]["heapMax"]
                    heap_usage_pct = (heap_used / heap_max) * 100 if heap_max > 0 else 0
                    
                    status = "OK" if heap_usage_pct < 80 else "WARNING" if heap_usage_pct < 95 else "CRITICAL"
                    message = f"Heap usage: {heap_usage_pct:.1f}%"
                    
                    details = {
                        "heap_used_bytes": heap_used,
                        "heap_max_bytes": heap_max,
                        "heap_usage_percentage": round(heap_usage_pct, 2),
                        "memory_config": memory_config
                    }
                else:
                    status = "INFO"
                    message = "Memory usage information not available"
                    details = {"memory_config": memory_config}
                    
            except Exception:
                status = "INFO"
                message = "Memory usage monitoring not available"
                details = {"memory_config": memory_config}
            
            return {
                "status": status,
                "message": message,
                "duration_ms": (time.time() - start_time) * 1000,
                "details": details
            }
        except Exception as e:
            return {
                "status": "WARNING",
                "message": f"Memory check failed: {str(e)}",
                "duration_ms": (time.time() - start_time) * 1000
            }
    
    def check_query_performance(self) -> Dict[str, Any]:
        """Check query performance with a simple test."""
        start_time = time.time()
        
        try:
            # Create test data for performance check
            self.execute_query("""
                MERGE (start:PerfTest {id: 'start'})
                WITH start
                UNWIND range(1, 100) as i
                MERGE (n:PerfTest {id: 'node_' + i})
                MERGE (start)-[:CONNECTS_TO]->(n)
            """)
            
            # Measure query performance
            query_start = time.time()
            result = self.execute_query("""
                MATCH (start:PerfTest {id: 'start'})-[:CONNECTS_TO]->(n:PerfTest)
                RETURN count(n) as connected_nodes
            """)
            query_duration = (time.time() - query_start) * 1000
            
            connected_nodes = result[0]["connected_nodes"]
            
            # Clean up test data
            self.execute_query("MATCH (n:PerfTest) DETACH DELETE n")
            
            # Determine status based on query performance
            if query_duration < 50:
                status = "OK"
            elif query_duration < 200:
                status = "WARNING"
            else:
                status = "CRITICAL"
            
            return {
                "status": status,
                "message": f"Query performance: {query_duration:.1f}ms for {connected_nodes} nodes",
                "duration_ms": (time.time() - start_time) * 1000,
                "details": {
                    "test_query_duration_ms": round(query_duration, 2),
                    "test_nodes_processed": connected_nodes,
                    "performance_acceptable": query_duration < 100
                }
            }
        except Exception as e:
            # Clean up in case of error
            try:
                self.execute_query("MATCH (n:PerfTest) DETACH DELETE n")
            except:
                pass
            
            return {
                "status": "WARNING",
                "message": f"Performance check failed: {str(e)}",
                "duration_ms": (time.time() - start_time) * 1000
            }
    
    def run_comprehensive_check(self) -> Dict[str, Any]:
        """Run all health checks and return comprehensive results."""
        if not NEO4J_AVAILABLE:
            return {
                "status": "CRITICAL",
                "message": "neo4j driver not available - cannot perform Neo4j health checks",
                "timestamp": datetime.now().isoformat(),
                "checks": {}
            }
        
        start_time = datetime.now()
        checks = {}
        
        # Run all checks
        check_methods = [
            ("connectivity", self.check_basic_connectivity),
            ("version", self.check_version_and_edition),
            ("apoc_plugin", self.check_apoc_plugin),
            ("gds_plugin", self.check_gds_plugin),
            ("database_stats", self.check_database_statistics),
            ("memory_usage", self.check_memory_usage),
            ("query_performance", self.check_query_performance)
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
            "service": "neo4j",
            "status": overall_status,
            "message": f"Neo4j health check completed ({overall_status})",
            "timestamp": end_time.isoformat(),
            "duration_seconds": round(total_duration, 2),
            "connection_info": {
                "uri": self.uri,
                "user": self.user
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
    parser = argparse.ArgumentParser(description="Neo4j Health Check")
    parser.add_argument("--uri", default="bolt://localhost:7687", help="Neo4j URI")
    parser.add_argument("--user", default="neo4j", help="Neo4j user")
    parser.add_argument("--password", default="ml_password", help="Neo4j password")
    parser.add_argument("--json", action="store_true", help="Output JSON format")
    parser.add_argument("--quiet", action="store_true", help="Minimal output")
    
    args = parser.parse_args()
    
    # Override with environment variables if available
    uri = os.getenv("NEO4J_URI", args.uri)
    user = os.getenv("NEO4J_USER", args.user)
    password = os.getenv("NEO4J_PASSWORD", args.password)
    
    checker = Neo4jHealthChecker(uri, user, password)
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
        print(f"Neo4j Health Check Results")
        print(f"{'='*60}")
        print(f"Overall Status: {status_emoji.get(results['status'], '?')} {results['status']}")
        print(f"Duration: {results['duration_seconds']}s")
        print(f"Timestamp: {results['timestamp']}")
        
        if not args.quiet:
            print(f"\nConnection: {uri} (user: {user})")
            
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