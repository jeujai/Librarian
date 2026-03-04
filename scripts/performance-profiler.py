#!/usr/bin/env python3
"""
Performance Profiler for Local Development

Advanced profiling tool that provides detailed performance analysis
including code profiling, memory profiling, and database query analysis.
"""

import asyncio
import cProfile
import pstats
import io
import sys
import time
import tracemalloc
import gc
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable
from contextlib import contextmanager, asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
import json

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from multimodal_librarian.development.performance_debugger import get_performance_debugger
from multimodal_librarian.config.local_config import LocalDatabaseConfig


@dataclass
class ProfileResult:
    """Profile execution result."""
    name: str
    execution_time: float
    cpu_stats: Optional[Dict[str, Any]] = None
    memory_stats: Optional[Dict[str, Any]] = None
    database_stats: Optional[Dict[str, Any]] = None
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


class PerformanceProfiler:
    """
    Advanced performance profiler for local development.
    
    Provides CPU profiling, memory profiling, and database query analysis
    for comprehensive performance optimization.
    """
    
    def __init__(self):
        self.config = LocalDatabaseConfig()
        self.debugger = get_performance_debugger(self.config)
        self.profile_results: List[ProfileResult] = []
        
    @contextmanager
    def cpu_profile(self, name: str = "operation"):
        """Context manager for CPU profiling."""
        profiler = cProfile.Profile()
        profiler.enable()
        start_time = time.time()
        
        try:
            yield profiler
        finally:
            profiler.disable()
            execution_time = time.time() - start_time
            
            # Analyze profile results
            stats_stream = io.StringIO()
            stats = pstats.Stats(profiler, stream=stats_stream)
            stats.sort_stats('cumulative')
            stats.print_stats(20)  # Top 20 functions
            
            cpu_stats = {
                "total_calls": stats.total_calls,
                "primitive_calls": stats.prim_calls,
                "total_time": stats.total_tt,
                "profile_output": stats_stream.getvalue()
            }
            
            result = ProfileResult(
                name=name,
                execution_time=execution_time,
                cpu_stats=cpu_stats
            )
            
            self.profile_results.append(result)
            print(f"✅ CPU profile completed for '{name}' in {execution_time:.3f}s")
    
    @contextmanager
    def memory_profile(self, name: str = "operation"):
        """Context manager for memory profiling."""
        # Start memory tracing
        tracemalloc.start()
        gc.collect()  # Clean up before measuring
        
        start_time = time.time()
        start_memory = tracemalloc.get_traced_memory()[0]
        
        try:
            yield
        finally:
            execution_time = time.time() - start_time
            current_memory, peak_memory = tracemalloc.get_traced_memory()
            
            # Get top memory allocations
            snapshot = tracemalloc.take_snapshot()
            top_stats = snapshot.statistics('lineno')
            
            memory_stats = {
                "start_memory_mb": start_memory / (1024 * 1024),
                "current_memory_mb": current_memory / (1024 * 1024),
                "peak_memory_mb": peak_memory / (1024 * 1024),
                "memory_delta_mb": (current_memory - start_memory) / (1024 * 1024),
                "top_allocations": [
                    {
                        "file": str(stat.traceback.format()[0]) if stat.traceback else "unknown",
                        "size_mb": stat.size / (1024 * 1024),
                        "count": stat.count
                    }
                    for stat in top_stats[:10]
                ]
            }
            
            tracemalloc.stop()
            
            result = ProfileResult(
                name=name,
                execution_time=execution_time,
                memory_stats=memory_stats
            )
            
            self.profile_results.append(result)
            print(f"✅ Memory profile completed for '{name}' in {execution_time:.3f}s")
            print(f"   Memory delta: {memory_stats['memory_delta_mb']:.2f}MB")
    
    @asynccontextmanager
    async def database_profile(self, name: str = "operation"):
        """Context manager for database operation profiling."""
        # Start database monitoring
        await self.debugger.start_monitoring(1)
        
        start_time = time.time()
        start_queries = len(self.debugger.query_data)
        start_metrics = len(self.debugger.metrics)
        
        try:
            yield
        finally:
            execution_time = time.time() - start_time
            
            # Wait a moment for final metrics
            await asyncio.sleep(1)
            
            # Stop monitoring
            await self.debugger.stop_monitoring()
            
            # Analyze database performance
            new_queries = self.debugger.query_data[start_queries:]
            new_metrics = self.debugger.metrics[start_metrics:]
            
            database_stats = {
                "queries_executed": len(new_queries),
                "total_query_time": sum(q.execution_time for q in new_queries),
                "avg_query_time": sum(q.execution_time for q in new_queries) / len(new_queries) if new_queries else 0,
                "queries_by_database": {},
                "slow_queries": []
            }
            
            # Group queries by database
            for query in new_queries:
                db = query.database
                if db not in database_stats["queries_by_database"]:
                    database_stats["queries_by_database"][db] = {
                        "count": 0,
                        "total_time": 0,
                        "avg_time": 0
                    }
                
                database_stats["queries_by_database"][db]["count"] += 1
                database_stats["queries_by_database"][db]["total_time"] += query.execution_time
            
            # Calculate averages
            for db_stats in database_stats["queries_by_database"].values():
                if db_stats["count"] > 0:
                    db_stats["avg_time"] = db_stats["total_time"] / db_stats["count"]
            
            # Identify slow queries (>100ms)
            database_stats["slow_queries"] = [
                {
                    "database": q.database,
                    "query_type": q.query_type,
                    "execution_time": q.execution_time,
                    "timestamp": q.timestamp.isoformat()
                }
                for q in new_queries if q.execution_time > 0.1
            ]
            
            result = ProfileResult(
                name=name,
                execution_time=execution_time,
                database_stats=database_stats
            )
            
            self.profile_results.append(result)
            print(f"✅ Database profile completed for '{name}' in {execution_time:.3f}s")
            print(f"   Queries executed: {database_stats['queries_executed']}")
            if database_stats['slow_queries']:
                print(f"   Slow queries detected: {len(database_stats['slow_queries'])}")
    
    @asynccontextmanager
    async def comprehensive_profile(self, name: str = "operation"):
        """Context manager for comprehensive profiling (CPU + Memory + Database)."""
        print(f"🔍 Starting comprehensive profile for '{name}'...")
        
        # Start all profiling
        profiler = cProfile.Profile()
        profiler.enable()
        
        tracemalloc.start()
        gc.collect()
        
        await self.debugger.start_monitoring(1)
        
        start_time = time.time()
        start_memory = tracemalloc.get_traced_memory()[0]
        start_queries = len(self.debugger.query_data)
        
        try:
            yield
        finally:
            execution_time = time.time() - start_time
            
            # Stop CPU profiling
            profiler.disable()
            
            # Get CPU stats
            stats_stream = io.StringIO()
            stats = pstats.Stats(profiler, stream=stats_stream)
            stats.sort_stats('cumulative')
            stats.print_stats(10)
            
            cpu_stats = {
                "total_calls": stats.total_calls,
                "primitive_calls": stats.prim_calls,
                "total_time": stats.total_tt,
                "top_functions": stats_stream.getvalue().split('\n')[5:15]  # Top 10 functions
            }
            
            # Get memory stats
            current_memory, peak_memory = tracemalloc.get_traced_memory()
            snapshot = tracemalloc.take_snapshot()
            top_stats = snapshot.statistics('lineno')
            
            memory_stats = {
                "start_memory_mb": start_memory / (1024 * 1024),
                "current_memory_mb": current_memory / (1024 * 1024),
                "peak_memory_mb": peak_memory / (1024 * 1024),
                "memory_delta_mb": (current_memory - start_memory) / (1024 * 1024),
                "top_allocations": [
                    {
                        "file": str(stat.traceback.format()[0]) if stat.traceback else "unknown",
                        "size_mb": stat.size / (1024 * 1024),
                        "count": stat.count
                    }
                    for stat in top_stats[:5]
                ]
            }
            
            tracemalloc.stop()
            
            # Wait for final database metrics
            await asyncio.sleep(1)
            await self.debugger.stop_monitoring()
            
            # Get database stats
            new_queries = self.debugger.query_data[start_queries:]
            database_stats = {
                "queries_executed": len(new_queries),
                "total_query_time": sum(q.execution_time for q in new_queries),
                "avg_query_time": sum(q.execution_time for q in new_queries) / len(new_queries) if new_queries else 0,
                "slow_queries_count": len([q for q in new_queries if q.execution_time > 0.1])
            }
            
            result = ProfileResult(
                name=name,
                execution_time=execution_time,
                cpu_stats=cpu_stats,
                memory_stats=memory_stats,
                database_stats=database_stats
            )
            
            self.profile_results.append(result)
            
            print(f"✅ Comprehensive profile completed for '{name}'")
            print(f"   Execution time: {execution_time:.3f}s")
            print(f"   Memory delta: {memory_stats['memory_delta_mb']:.2f}MB")
            print(f"   Peak memory: {memory_stats['peak_memory_mb']:.2f}MB")
            print(f"   Database queries: {database_stats['queries_executed']}")
            if database_stats['slow_queries_count'] > 0:
                print(f"   Slow queries: {database_stats['slow_queries_count']}")
    
    def print_profile_summary(self, name: Optional[str] = None):
        """Print summary of profile results."""
        results = self.profile_results
        if name:
            results = [r for r in results if name.lower() in r.name.lower()]
        
        if not results:
            print("No profile results found.")
            return
        
        print(f"\n{'=' * 60}")
        print(f" Profile Summary ({len(results)} results)")
        print(f"{'=' * 60}")
        
        for result in results:
            print(f"\n📊 {result.name}")
            print(f"   Execution time: {result.execution_time:.3f}s")
            print(f"   Timestamp: {result.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
            
            if result.cpu_stats:
                print(f"   CPU - Total calls: {result.cpu_stats['total_calls']}")
                print(f"   CPU - Total time: {result.cpu_stats['total_time']:.3f}s")
            
            if result.memory_stats:
                print(f"   Memory - Delta: {result.memory_stats['memory_delta_mb']:.2f}MB")
                print(f"   Memory - Peak: {result.memory_stats['peak_memory_mb']:.2f}MB")
            
            if result.database_stats:
                print(f"   Database - Queries: {result.database_stats['queries_executed']}")
                print(f"   Database - Avg time: {result.database_stats['avg_query_time']*1000:.1f}ms")
    
    def export_profiles(self, filepath: str):
        """Export profile results to JSON file."""
        data = {
            "export_timestamp": datetime.now().isoformat(),
            "profiles": []
        }
        
        for result in self.profile_results:
            profile_data = {
                "name": result.name,
                "execution_time": result.execution_time,
                "timestamp": result.timestamp.isoformat(),
                "cpu_stats": result.cpu_stats,
                "memory_stats": result.memory_stats,
                "database_stats": result.database_stats
            }
            data["profiles"].append(profile_data)
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        
        print(f"✅ Profiles exported to {filepath}")
        print(f"   Profiles exported: {len(self.profile_results)}")


async def profile_database_operations():
    """Profile database operations."""
    print("🔍 Profiling database operations...")
    
    profiler = PerformanceProfiler()
    
    async with profiler.database_profile("database_operations"):
        config = LocalDatabaseConfig()
        debugger = get_performance_debugger(config)
        
        # Test PostgreSQL
        postgres_client = debugger.factory.create_postgres_client()
        for i in range(20):
            await postgres_client.execute("SELECT 1")
        
        # Test Neo4j
        neo4j_client = debugger.factory.create_graph_store_client()
        for i in range(10):
            await neo4j_client.execute_query("RETURN 1")
        
        # Test Milvus
        milvus_client = debugger.factory.create_vector_store_client()
        for i in range(5):
            await milvus_client.list_collections()
    
    return profiler


def profile_cpu_intensive_operation():
    """Profile CPU-intensive operation."""
    print("🔍 Profiling CPU-intensive operation...")
    
    profiler = PerformanceProfiler()
    
    with profiler.cpu_profile("cpu_intensive"):
        # Simulate CPU-intensive work
        result = 0
        for i in range(1000000):
            result += i ** 2
        
        # Some string operations
        text = "performance testing " * 1000
        words = text.split()
        sorted_words = sorted(words)
    
    return profiler


def profile_memory_intensive_operation():
    """Profile memory-intensive operation."""
    print("🔍 Profiling memory-intensive operation...")
    
    profiler = PerformanceProfiler()
    
    with profiler.memory_profile("memory_intensive"):
        # Create large data structures
        large_list = list(range(100000))
        large_dict = {i: f"value_{i}" for i in range(50000)}
        
        # Some memory operations
        copied_list = large_list.copy()
        filtered_list = [x for x in large_list if x % 2 == 0]
        
        # Clean up
        del large_list, large_dict, copied_list, filtered_list
    
    return profiler


async def profile_comprehensive_operation():
    """Profile comprehensive operation (CPU + Memory + Database)."""
    print("🔍 Running comprehensive performance profile...")
    
    profiler = PerformanceProfiler()
    
    async with profiler.comprehensive_profile("comprehensive_test"):
        config = LocalDatabaseConfig()
        debugger = get_performance_debugger(config)
        
        # CPU-intensive work
        result = sum(i ** 2 for i in range(10000))
        
        # Memory-intensive work
        data = [f"item_{i}" for i in range(10000)]
        processed_data = [item.upper() for item in data]
        
        # Database operations
        postgres_client = debugger.factory.create_postgres_client()
        for i in range(5):
            await postgres_client.execute("SELECT 1")
        
        neo4j_client = debugger.factory.create_graph_store_client()
        for i in range(3):
            await neo4j_client.execute_query("RETURN 1")
        
        # Cleanup
        del data, processed_data
    
    return profiler


async def main():
    """Main profiler execution."""
    print("🚀 Performance Profiler for Local Development")
    print("=" * 60)
    
    all_profilers = []
    
    try:
        # Run different types of profiling
        print("\n1. Database Operations Profiling")
        db_profiler = await profile_database_operations()
        all_profilers.append(db_profiler)
        
        print("\n2. CPU-Intensive Operations Profiling")
        cpu_profiler = profile_cpu_intensive_operation()
        all_profilers.append(cpu_profiler)
        
        print("\n3. Memory-Intensive Operations Profiling")
        memory_profiler = profile_memory_intensive_operation()
        all_profilers.append(memory_profiler)
        
        print("\n4. Comprehensive Operations Profiling")
        comp_profiler = await profile_comprehensive_operation()
        all_profilers.append(comp_profiler)
        
        # Combine all results
        combined_profiler = PerformanceProfiler()
        for profiler in all_profilers:
            combined_profiler.profile_results.extend(profiler.profile_results)
        
        # Print summary
        print("\n" + "=" * 60)
        print(" PROFILING RESULTS SUMMARY")
        print("=" * 60)
        
        combined_profiler.print_profile_summary()
        
        # Export results
        export_path = f"/tmp/performance_profile_{int(time.time())}.json"
        combined_profiler.export_profiles(export_path)
        
        print(f"\n✅ Profiling completed successfully!")
        print(f"   Total profiles: {len(combined_profiler.profile_results)}")
        print(f"   Results exported to: {export_path}")
        
    except Exception as e:
        print(f"\n❌ Profiling failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())