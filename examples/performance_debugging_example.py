#!/usr/bin/env python3
"""
Performance Debugging Example

This example demonstrates how to use the performance debugging tools
in the local development environment.
"""

import asyncio
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from multimodal_librarian.development.performance_debugger import get_performance_debugger
from multimodal_librarian.config.local_config import LocalDatabaseConfig


async def simulate_database_operations():
    """Simulate some database operations for testing."""
    print("🔄 Simulating database operations...")
    
    config = LocalDatabaseConfig()
    debugger = get_performance_debugger(config)
    
    try:
        # Simulate PostgreSQL operations
        postgres_client = debugger.factory.create_postgres_client()
        for i in range(5):
            await postgres_client.execute("SELECT 1")
            await asyncio.sleep(0.1)  # Simulate processing time
        
        # Simulate Neo4j operations
        neo4j_client = debugger.factory.create_graph_store_client()
        for i in range(3):
            await neo4j_client.execute_query("RETURN 1")
            await asyncio.sleep(0.2)  # Simulate processing time
        
        # Simulate Milvus operations
        milvus_client = debugger.factory.create_vector_store_client()
        for i in range(2):
            await milvus_client.list_collections()
            await asyncio.sleep(0.3)  # Simulate processing time
            
    except Exception as e:
        print(f"⚠️ Database operations failed (expected in demo): {e}")


async def demonstrate_performance_monitoring():
    """Demonstrate performance monitoring capabilities."""
    print("🚀 Performance Debugging Example")
    print("=" * 50)
    
    config = LocalDatabaseConfig()
    debugger = get_performance_debugger(config)
    
    try:
        # 1. Start monitoring
        print("\n1. Starting performance monitoring...")
        result = await debugger.start_monitoring(interval_seconds=2)
        print(f"   Status: {result['status']}")
        
        # 2. Perform operations with measurement
        print("\n2. Performing measured operations...")
        
        async with debugger.measure_operation("example_workflow", {"demo": True}):
            print("   - Running simulated CPU work...")
            # Simulate CPU-intensive work
            result = sum(i ** 2 for i in range(10000))
            
            print("   - Running simulated database operations...")
            await simulate_database_operations()
            
            print("   - Running simulated memory work...")
            # Simulate memory-intensive work
            data = [f"item_{i}" for i in range(5000)]
            processed = [item.upper() for item in data]
            del data, processed
        
        # 3. Wait for monitoring to collect data
        print("\n3. Collecting performance data...")
        await asyncio.sleep(5)
        
        # 4. Get performance summary
        print("\n4. Performance Summary:")
        print("-" * 30)
        summary = debugger.get_performance_summary(last_minutes=1)
        
        print(f"   Metrics collected: {summary['metrics_count']}")
        print(f"   Queries analyzed: {summary['queries_analyzed']}")
        print(f"   Resource snapshots: {summary['resource_snapshots']}")
        
        # Database performance
        if summary['database_performance'] and summary['database_performance'] != {"status": "no_data"}:
            print("\n   Database Performance:")
            for db, stats in summary['database_performance'].items():
                print(f"     {db.upper()}:")
                print(f"       Queries: {stats['query_count']}")
                print(f"       Avg time: {stats['avg_time_ms']:.1f}ms")
                print(f"       Max time: {stats['max_time_ms']:.1f}ms")
        
        # Resource usage
        if summary['resource_usage'] and summary['resource_usage'] != {"status": "no_data"}:
            print("\n   Resource Usage:")
            if 'cpu' in summary['resource_usage']:
                cpu = summary['resource_usage']['cpu']
                print(f"     CPU: avg {cpu['avg_percent']:.1f}%, max {cpu['max_percent']:.1f}%")
            if 'memory' in summary['resource_usage']:
                memory = summary['resource_usage']['memory']
                print(f"     Memory: avg {memory['avg_percent']:.1f}%, max {memory['max_percent']:.1f}%")
        
        # Bottlenecks
        if summary['bottlenecks']:
            print("\n   ⚠️ Performance Issues Detected:")
            for bottleneck in summary['bottlenecks']:
                severity = "🔴" if bottleneck['severity'] == 'high' else "🟡"
                print(f"     {severity} {bottleneck['description']}")
        
        # Recommendations
        if summary['recommendations']:
            print("\n   💡 Optimization Recommendations:")
            for i, rec in enumerate(summary['recommendations'], 1):
                print(f"     {i}. {rec}")
        
        # 5. Export data
        print("\n5. Exporting performance data...")
        export_path = "/tmp/performance_debug_example.json"
        export_result = debugger.export_metrics(export_path)
        if export_result["status"] == "success":
            print(f"   ✅ Data exported to: {export_path}")
            print(f"   Metrics: {export_result['metrics_exported']}")
            print(f"   Queries: {export_result['queries_exported']}")
        
        # 6. Stop monitoring
        print("\n6. Stopping monitoring...")
        result = await debugger.stop_monitoring()
        print(f"   Status: {result['status']}")
        print(f"   Final metrics collected: {result['metrics_collected']}")
        
    except Exception as e:
        print(f"\n❌ Error during demonstration: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Ensure monitoring is stopped
        if debugger.monitoring_active:
            await debugger.stop_monitoring()


async def demonstrate_context_manager():
    """Demonstrate using the performance debugger as a context manager."""
    print("\n" + "=" * 50)
    print("Context Manager Example")
    print("=" * 50)
    
    config = LocalDatabaseConfig()
    debugger = get_performance_debugger(config)
    
    # Measure a specific operation
    async with debugger.measure_operation("context_manager_demo", {"type": "demo"}):
        print("🔄 Running operation inside context manager...")
        
        # Simulate some work
        await asyncio.sleep(0.5)
        
        # Simulate database operation
        try:
            postgres_client = debugger.factory.create_postgres_client()
            await postgres_client.execute("SELECT 1")
        except Exception as e:
            print(f"   Database operation failed (expected): {e}")
    
    # Check the metrics
    recent_metrics = [m for m in debugger.metrics if "context_manager_demo" in m.name]
    if recent_metrics:
        metric = recent_metrics[-1]
        print(f"✅ Operation measured: {metric.name}")
        print(f"   Execution time: {metric.value:.1f} {metric.unit}")
        print(f"   Context: {metric.context}")


def demonstrate_cli_usage():
    """Demonstrate CLI usage examples."""
    print("\n" + "=" * 50)
    print("CLI Usage Examples")
    print("=" * 50)
    
    print("You can use the performance debugging CLI with these commands:")
    print()
    print("📊 Start monitoring:")
    print("   python scripts/performance-debug-cli.py start --interval 5")
    print()
    print("📈 Get performance summary:")
    print("   python scripts/performance-debug-cli.py summary --minutes 10")
    print()
    print("🔍 View metrics:")
    print("   python scripts/performance-debug-cli.py metrics --filter postgres")
    print()
    print("💾 Export data:")
    print("   python scripts/performance-debug-cli.py export --filepath /tmp/perf-data.json")
    print()
    print("🧪 Run benchmark:")
    print("   python scripts/performance-debug-cli.py benchmark")
    print()
    print("🛑 Stop monitoring:")
    print("   python scripts/performance-debug-cli.py stop")


def demonstrate_api_usage():
    """Demonstrate API usage examples."""
    print("\n" + "=" * 50)
    print("API Usage Examples")
    print("=" * 50)
    
    print("You can use the performance debugging API with these endpoints:")
    print()
    print("📊 Start monitoring:")
    print("   POST /debug/performance/monitoring/start?interval_seconds=5")
    print()
    print("📈 Get performance summary:")
    print("   GET /debug/performance/summary?last_minutes=10")
    print()
    print("🔍 View metrics:")
    print("   GET /debug/performance/metrics?limit=50&metric_name=postgres")
    print()
    print("💾 Export data:")
    print("   POST /debug/performance/export?filepath=/tmp/data.json")
    print()
    print("🛑 Stop monitoring:")
    print("   POST /debug/performance/monitoring/stop")
    print()
    print("Example with curl:")
    print("   curl -X POST 'http://localhost:8000/debug/performance/monitoring/start?interval_seconds=5'")


async def main():
    """Main example execution."""
    try:
        # Run the main demonstration
        await demonstrate_performance_monitoring()
        
        # Demonstrate context manager usage
        await demonstrate_context_manager()
        
        # Show CLI and API usage examples
        demonstrate_cli_usage()
        demonstrate_api_usage()
        
        print("\n" + "=" * 50)
        print("✅ Performance debugging example completed!")
        print("=" * 50)
        print()
        print("Next steps:")
        print("1. Try the CLI tool: python scripts/performance-debug-cli.py --help")
        print("2. Run the profiler: python scripts/performance-profiler.py")
        print("3. Check the API docs: http://localhost:8000/docs#/performance-debug")
        print("4. Read the guide: docs/performance-debugging-guide.md")
        
    except KeyboardInterrupt:
        print("\n\n⚠️ Example interrupted by user")
    except Exception as e:
        print(f"\n❌ Example failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())