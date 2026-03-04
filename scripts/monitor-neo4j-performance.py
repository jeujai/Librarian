#!/usr/bin/env python3
"""
Neo4j Performance Monitoring Script for Local Development

This script monitors Neo4j performance metrics to validate the memory and
performance optimizations implemented for local development.

Usage:
    python scripts/monitor-neo4j-performance.py
"""

import asyncio
import json
import time
from datetime import datetime
from typing import Dict, Any, List
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

try:
    from neo4j import GraphDatabase
    import psutil
    import docker
except ImportError as e:
    print(f"Missing required dependencies: {e}")
    print("Install with: pip install neo4j psutil docker")
    sys.exit(1)


class Neo4jPerformanceMonitor:
    """Monitor Neo4j performance metrics for local development."""
    
    def __init__(self, uri: str = "bolt://localhost:7687", 
                 user: str = "neo4j", password: str = "ml_password"):
        self.uri = uri
        self.user = user
        self.password = password
        self.driver = None
        self.docker_client = docker.from_env()
        
    async def connect(self):
        """Connect to Neo4j database."""
        try:
            self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
            # Test connection
            with self.driver.session() as session:
                result = session.run("RETURN 1 as test")
                result.single()
            print("✅ Connected to Neo4j successfully")
            return True
        except Exception as e:
            print(f"❌ Failed to connect to Neo4j: {e}")
            return False
    
    def get_container_stats(self) -> Dict[str, Any]:
        """Get Docker container resource usage statistics."""
        try:
            container = self.docker_client.containers.get("local-development-conversion-neo4j-1")
            stats = container.stats(stream=False)
            
            # Calculate memory usage
            memory_usage = stats['memory_stats']['usage']
            memory_limit = stats['memory_stats']['limit']
            memory_percent = (memory_usage / memory_limit) * 100
            
            # Calculate CPU usage
            cpu_delta = stats['cpu_stats']['cpu_usage']['total_usage'] - \
                       stats['precpu_stats']['cpu_usage']['total_usage']
            system_delta = stats['cpu_stats']['system_cpu_usage'] - \
                          stats['precpu_stats']['system_cpu_usage']
            cpu_percent = (cpu_delta / system_delta) * len(stats['cpu_stats']['cpu_usage']['percpu_usage']) * 100
            
            return {
                'memory_usage_mb': memory_usage / (1024 * 1024),
                'memory_limit_mb': memory_limit / (1024 * 1024),
                'memory_percent': memory_percent,
                'cpu_percent': cpu_percent,
                'container_status': container.status
            }
        except Exception as e:
            print(f"Warning: Could not get container stats: {e}")
            return {}
    
    def get_neo4j_metrics(self) -> Dict[str, Any]:
        """Get Neo4j internal performance metrics."""
        metrics = {}
        
        try:
            with self.driver.session() as session:
                # Memory usage metrics
                result = session.run("""
                    CALL dbms.queryJmx("org.neo4j:instance=kernel#0,name=Memory Pools") 
                    YIELD attributes 
                    RETURN attributes
                """)
                
                for record in result:
                    attrs = record['attributes']
                    if 'HeapMemoryUsage' in attrs:
                        heap_usage = attrs['HeapMemoryUsage']['value']
                        metrics['heap_used_mb'] = heap_usage['used'] / (1024 * 1024)
                        metrics['heap_max_mb'] = heap_usage['max'] / (1024 * 1024)
                        metrics['heap_percent'] = (heap_usage['used'] / heap_usage['max']) * 100
                
                # Page cache metrics
                result = session.run("""
                    CALL dbms.queryJmx("org.neo4j:instance=kernel#0,name=Page cache") 
                    YIELD attributes 
                    RETURN attributes
                """)
                
                for record in result:
                    attrs = record['attributes']
                    if 'BytesRead' in attrs:
                        metrics['page_cache_bytes_read'] = attrs['BytesRead']['value']
                    if 'BytesWritten' in attrs:
                        metrics['page_cache_bytes_written'] = attrs['BytesWritten']['value']
                    if 'Hits' in attrs:
                        metrics['page_cache_hits'] = attrs['Hits']['value']
                    if 'Faults' in attrs:
                        metrics['page_cache_faults'] = attrs['Faults']['value']
                
                # Calculate hit ratio
                if 'page_cache_hits' in metrics and 'page_cache_faults' in metrics:
                    total_requests = metrics['page_cache_hits'] + metrics['page_cache_faults']
                    if total_requests > 0:
                        metrics['page_cache_hit_ratio'] = (metrics['page_cache_hits'] / total_requests) * 100
                
                # Transaction metrics
                result = session.run("""
                    CALL dbms.queryJmx("org.neo4j:instance=kernel#0,name=Transactions") 
                    YIELD attributes 
                    RETURN attributes
                """)
                
                for record in result:
                    attrs = record['attributes']
                    if 'NumberOfOpenTransactions' in attrs:
                        metrics['open_transactions'] = attrs['NumberOfOpenTransactions']['value']
                    if 'NumberOfCommittedTransactions' in attrs:
                        metrics['committed_transactions'] = attrs['NumberOfCommittedTransactions']['value']
                
        except Exception as e:
            print(f"Warning: Could not get Neo4j JMX metrics: {e}")
        
        return metrics
    
    def run_performance_test(self) -> Dict[str, Any]:
        """Run a simple performance test to measure query response times."""
        test_results = {}
        
        try:
            with self.driver.session() as session:
                # Test 1: Simple node creation and retrieval
                start_time = time.time()
                session.run("""
                    CREATE (n:TestNode {id: $id, timestamp: $timestamp})
                    RETURN n
                """, id=f"test_{int(time.time())}", timestamp=datetime.now().isoformat())
                test_results['create_node_ms'] = (time.time() - start_time) * 1000
                
                # Test 2: Node count query
                start_time = time.time()
                result = session.run("MATCH (n:TestNode) RETURN count(n) as count")
                count = result.single()['count']
                test_results['count_query_ms'] = (time.time() - start_time) * 1000
                test_results['test_node_count'] = count
                
                # Test 3: Complex query with relationships
                start_time = time.time()
                session.run("""
                    MATCH (n:TestNode)
                    WHERE n.timestamp > $cutoff
                    RETURN n.id, n.timestamp
                    ORDER BY n.timestamp DESC
                    LIMIT 10
                """, cutoff=(datetime.now().isoformat()))
                test_results['complex_query_ms'] = (time.time() - start_time) * 1000
                
                # Cleanup test nodes (keep only last 100)
                session.run("""
                    MATCH (n:TestNode)
                    WITH n ORDER BY n.timestamp DESC
                    SKIP 100
                    DETACH DELETE n
                """)
                
        except Exception as e:
            print(f"Warning: Performance test failed: {e}")
            test_results['error'] = str(e)
        
        return test_results
    
    def get_database_info(self) -> Dict[str, Any]:
        """Get basic database information."""
        info = {}
        
        try:
            with self.driver.session() as session:
                # Database version
                result = session.run("CALL dbms.components() YIELD name, versions, edition")
                for record in result:
                    if record['name'] == 'Neo4j Kernel':
                        info['version'] = record['versions'][0]
                        info['edition'] = record['edition']
                
                # Node and relationship counts
                result = session.run("MATCH (n) RETURN count(n) as node_count")
                info['total_nodes'] = result.single()['node_count']
                
                result = session.run("MATCH ()-[r]->() RETURN count(r) as rel_count")
                info['total_relationships'] = result.single()['rel_count']
                
                # Available procedures
                result = session.run("CALL dbms.procedures() YIELD name WHERE name STARTS WITH 'apoc' RETURN count(name) as apoc_count")
                info['apoc_procedures'] = result.single()['apoc_count']
                
                result = session.run("CALL dbms.procedures() YIELD name WHERE name STARTS WITH 'gds' RETURN count(name) as gds_count")
                info['gds_procedures'] = result.single()['gds_count']
                
        except Exception as e:
            print(f"Warning: Could not get database info: {e}")
            info['error'] = str(e)
        
        return info
    
    async def monitor_performance(self, duration_seconds: int = 60, interval_seconds: int = 10):
        """Monitor performance for a specified duration."""
        print(f"🔍 Monitoring Neo4j performance for {duration_seconds} seconds...")
        
        measurements = []
        start_time = time.time()
        
        while time.time() - start_time < duration_seconds:
            timestamp = datetime.now().isoformat()
            
            # Collect all metrics
            container_stats = self.get_container_stats()
            neo4j_metrics = self.get_neo4j_metrics()
            performance_test = self.run_performance_test()
            
            measurement = {
                'timestamp': timestamp,
                'container_stats': container_stats,
                'neo4j_metrics': neo4j_metrics,
                'performance_test': performance_test
            }
            
            measurements.append(measurement)
            
            # Print current status
            memory_mb = container_stats.get('memory_usage_mb', 0)
            memory_percent = container_stats.get('memory_percent', 0)
            heap_mb = neo4j_metrics.get('heap_used_mb', 0)
            create_time = performance_test.get('create_node_ms', 0)
            
            print(f"📊 Memory: {memory_mb:.1f}MB ({memory_percent:.1f}%), "
                  f"Heap: {heap_mb:.1f}MB, Create: {create_time:.1f}ms")
            
            await asyncio.sleep(interval_seconds)
        
        return measurements
    
    def generate_report(self, measurements: List[Dict[str, Any]], database_info: Dict[str, Any]):
        """Generate a performance report."""
        if not measurements:
            print("❌ No measurements to report")
            return
        
        print("\n" + "="*80)
        print("📈 NEO4J PERFORMANCE REPORT")
        print("="*80)
        
        # Database info
        print(f"\n🗄️  Database Information:")
        print(f"   Version: {database_info.get('version', 'Unknown')}")
        print(f"   Edition: {database_info.get('edition', 'Unknown')}")
        print(f"   Total Nodes: {database_info.get('total_nodes', 0):,}")
        print(f"   Total Relationships: {database_info.get('total_relationships', 0):,}")
        print(f"   APOC Procedures: {database_info.get('apoc_procedures', 0)}")
        print(f"   GDS Procedures: {database_info.get('gds_procedures', 0)}")
        
        # Memory analysis
        memory_usage = [m['container_stats'].get('memory_usage_mb', 0) for m in measurements if 'container_stats' in m]
        heap_usage = [m['neo4j_metrics'].get('heap_used_mb', 0) for m in measurements if 'neo4j_metrics' in m]
        
        if memory_usage:
            print(f"\n💾 Memory Usage Analysis:")
            print(f"   Container Memory - Avg: {sum(memory_usage)/len(memory_usage):.1f}MB, "
                  f"Max: {max(memory_usage):.1f}MB, Min: {min(memory_usage):.1f}MB")
            
            # Check if within limits
            max_memory = max(memory_usage)
            if max_memory < 1536:  # 1.5GB limit
                print(f"   ✅ Memory usage within limits ({max_memory:.1f}MB < 1536MB)")
            else:
                print(f"   ⚠️  Memory usage exceeds recommended limit ({max_memory:.1f}MB > 1536MB)")
        
        if heap_usage:
            print(f"   Heap Memory - Avg: {sum(heap_usage)/len(heap_usage):.1f}MB, "
                  f"Max: {max(heap_usage):.1f}MB, Min: {min(heap_usage):.1f}MB")
        
        # Performance analysis
        create_times = [m['performance_test'].get('create_node_ms', 0) for m in measurements 
                       if 'performance_test' in m and 'create_node_ms' in m['performance_test']]
        query_times = [m['performance_test'].get('count_query_ms', 0) for m in measurements 
                      if 'performance_test' in m and 'count_query_ms' in m['performance_test']]
        
        if create_times:
            print(f"\n⚡ Query Performance Analysis:")
            print(f"   Node Creation - Avg: {sum(create_times)/len(create_times):.1f}ms, "
                  f"Max: {max(create_times):.1f}ms, Min: {min(create_times):.1f}ms")
            
            # Performance targets
            avg_create = sum(create_times)/len(create_times)
            if avg_create < 50:
                print(f"   ✅ Node creation performance excellent ({avg_create:.1f}ms < 50ms)")
            elif avg_create < 100:
                print(f"   ✅ Node creation performance good ({avg_create:.1f}ms < 100ms)")
            else:
                print(f"   ⚠️  Node creation performance needs optimization ({avg_create:.1f}ms > 100ms)")
        
        if query_times:
            print(f"   Count Queries - Avg: {sum(query_times)/len(query_times):.1f}ms, "
                  f"Max: {max(query_times):.1f}ms, Min: {min(query_times):.1f}ms")
        
        # Page cache analysis
        hit_ratios = [m['neo4j_metrics'].get('page_cache_hit_ratio', 0) for m in measurements 
                     if 'neo4j_metrics' in m and 'page_cache_hit_ratio' in m['neo4j_metrics']]
        
        if hit_ratios:
            avg_hit_ratio = sum(hit_ratios) / len(hit_ratios)
            print(f"\n🎯 Page Cache Analysis:")
            print(f"   Hit Ratio - Avg: {avg_hit_ratio:.1f}%")
            
            if avg_hit_ratio > 90:
                print(f"   ✅ Excellent page cache performance ({avg_hit_ratio:.1f}% > 90%)")
            elif avg_hit_ratio > 80:
                print(f"   ✅ Good page cache performance ({avg_hit_ratio:.1f}% > 80%)")
            else:
                print(f"   ⚠️  Page cache may need tuning ({avg_hit_ratio:.1f}% < 80%)")
        
        # Overall assessment
        print(f"\n🎯 Overall Assessment:")
        
        # Memory check
        memory_ok = max(memory_usage) < 1536 if memory_usage else False
        performance_ok = (sum(create_times)/len(create_times)) < 100 if create_times else False
        cache_ok = (sum(hit_ratios)/len(hit_ratios)) > 80 if hit_ratios else False
        
        if memory_ok and performance_ok and cache_ok:
            print("   ✅ Neo4j performance is optimized for local development")
        elif memory_ok and performance_ok:
            print("   ✅ Neo4j performance is good, cache could be improved")
        elif memory_ok:
            print("   ⚠️  Memory usage is good, but query performance needs optimization")
        else:
            print("   ❌ Neo4j configuration needs optimization")
        
        print("\n" + "="*80)
    
    def close(self):
        """Close the database connection."""
        if self.driver:
            self.driver.close()


async def main():
    """Main monitoring function."""
    print("🚀 Neo4j Performance Monitor for Local Development")
    print("="*60)
    
    monitor = Neo4jPerformanceMonitor()
    
    # Connect to Neo4j
    if not await monitor.connect():
        print("❌ Cannot connect to Neo4j. Make sure it's running with docker-compose up")
        return
    
    try:
        # Get database info
        database_info = monitor.get_database_info()
        
        # Run monitoring
        measurements = await monitor.monitor_performance(duration_seconds=60, interval_seconds=10)
        
        # Generate report
        monitor.generate_report(measurements, database_info)
        
        # Save detailed results
        report_file = f"neo4j_performance_report_{int(time.time())}.json"
        with open(report_file, 'w') as f:
            json.dump({
                'database_info': database_info,
                'measurements': measurements,
                'generated_at': datetime.now().isoformat()
            }, f, indent=2)
        
        print(f"\n📄 Detailed report saved to: {report_file}")
        
    finally:
        monitor.close()


if __name__ == "__main__":
    asyncio.run(main())