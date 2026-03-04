#!/usr/bin/env python3
"""
Performance Debugging CLI Tool

Command-line interface for performance debugging and monitoring
in the local development environment.
"""

import asyncio
import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from multimodal_librarian.development.performance_debugger import get_performance_debugger
from multimodal_librarian.config.local_config import LocalDatabaseConfig


def print_header(title: str):
    """Print a formatted header."""
    print(f"\n{'=' * 60}")
    print(f" {title}")
    print(f"{'=' * 60}")


def print_section(title: str):
    """Print a formatted section header."""
    print(f"\n{'-' * 40}")
    print(f" {title}")
    print(f"{'-' * 40}")


def format_timestamp(timestamp):
    """Format timestamp for display."""
    if isinstance(timestamp, str):
        return timestamp
    return timestamp.strftime("%Y-%m-%d %H:%M:%S")


def format_duration(seconds: float) -> str:
    """Format duration in a human-readable way."""
    if seconds < 1:
        return f"{seconds * 1000:.1f}ms"
    elif seconds < 60:
        return f"{seconds:.1f}s"
    else:
        minutes = int(seconds // 60)
        remaining_seconds = seconds % 60
        return f"{minutes}m {remaining_seconds:.1f}s"


async def start_monitoring(args):
    """Start performance monitoring."""
    print_header("Starting Performance Monitoring")
    
    config = LocalDatabaseConfig()
    debugger = get_performance_debugger(config)
    
    result = await debugger.start_monitoring(args.interval)
    
    if result["status"] == "started":
        print(f"✅ Performance monitoring started successfully")
        print(f"   Monitoring interval: {args.interval} seconds")
        print(f"   Use 'python scripts/performance-debug-cli.py stop' to stop monitoring")
    else:
        print(f"⚠️  {result['message']}")


async def stop_monitoring(args):
    """Stop performance monitoring."""
    print_header("Stopping Performance Monitoring")
    
    config = LocalDatabaseConfig()
    debugger = get_performance_debugger(config)
    
    result = await debugger.stop_monitoring()
    
    if result["status"] == "stopped":
        print(f"✅ Performance monitoring stopped successfully")
        print(f"   Metrics collected: {result['metrics_collected']}")
        print(f"   Queries analyzed: {result['queries_analyzed']}")
        print(f"   Resource snapshots: {result['resource_snapshots']}")
    else:
        print(f"⚠️  {result['message']}")


async def show_summary(args):
    """Show performance summary."""
    print_header(f"Performance Summary (Last {args.minutes} minutes)")
    
    config = LocalDatabaseConfig()
    debugger = get_performance_debugger(config)
    
    summary = debugger.get_performance_summary(args.minutes)
    
    # Overall statistics
    print_section("Overall Statistics")
    print(f"Time range: {summary['time_range_minutes']} minutes")
    print(f"Metrics collected: {summary['metrics_count']}")
    print(f"Queries analyzed: {summary['queries_analyzed']}")
    print(f"Resource snapshots: {summary['resource_snapshots']}")
    
    # Database performance
    if summary['database_performance'] and summary['database_performance'] != {"status": "no_data"}:
        print_section("Database Performance")
        for db, stats in summary['database_performance'].items():
            print(f"\n{db.upper()}:")
            print(f"  Query count: {stats['query_count']}")
            print(f"  Average time: {stats['avg_time_ms']:.1f}ms")
            print(f"  Min time: {stats['min_time_ms']:.1f}ms")
            print(f"  Max time: {stats['max_time_ms']:.1f}ms")
            print(f"  Median time: {stats['median_time_ms']:.1f}ms")
            if stats.get('p95_time_ms'):
                print(f"  95th percentile: {stats['p95_time_ms']:.1f}ms")
    
    # Resource usage
    if summary['resource_usage'] and summary['resource_usage'] != {"status": "no_data"}:
        print_section("Resource Usage")
        resource_usage = summary['resource_usage']
        
        if 'cpu' in resource_usage:
            cpu = resource_usage['cpu']
            print(f"CPU Usage:")
            print(f"  Average: {cpu['avg_percent']:.1f}%")
            print(f"  Maximum: {cpu['max_percent']:.1f}%")
            print(f"  Minimum: {cpu['min_percent']:.1f}%")
        
        if 'memory' in resource_usage:
            memory = resource_usage['memory']
            print(f"\nMemory Usage:")
            print(f"  Average: {memory['avg_percent']:.1f}%")
            print(f"  Maximum: {memory['max_percent']:.1f}%")
            print(f"  Average used: {memory['avg_used_mb']:.1f}MB")
            print(f"  Maximum used: {memory['max_used_mb']:.1f}MB")
        
        # Docker containers
        if 'docker_containers' in resource_usage and resource_usage['docker_containers']:
            print(f"\nDocker Containers:")
            for container, stats in resource_usage['docker_containers'].items():
                print(f"  {container}:")
                print(f"    CPU: avg {stats['avg_cpu_percent']:.1f}%, max {stats['max_cpu_percent']:.1f}%")
                print(f"    Memory: avg {stats['avg_memory_mb']:.1f}MB, max {stats['max_memory_mb']:.1f}MB")
                print(f"    Status: {stats['status_distribution']}")
    
    # Bottlenecks
    if summary['bottlenecks']:
        print_section("Performance Bottlenecks")
        for bottleneck in summary['bottlenecks']:
            severity_icon = "🔴" if bottleneck['severity'] == 'high' else "🟡"
            print(f"{severity_icon} {bottleneck['type'].replace('_', ' ').title()}")
            print(f"   {bottleneck['description']}")
            if bottleneck.get('context'):
                print(f"   Context: {bottleneck['context']}")
    
    # Recommendations
    if summary['recommendations']:
        print_section("Optimization Recommendations")
        for i, recommendation in enumerate(summary['recommendations'], 1):
            print(f"{i}. {recommendation}")


async def show_metrics(args):
    """Show collected metrics."""
    print_header("Performance Metrics")
    
    config = LocalDatabaseConfig()
    debugger = get_performance_debugger(config)
    
    metrics = debugger.metrics
    
    if args.filter:
        metrics = [m for m in metrics if args.filter.lower() in m.name.lower()]
    
    metrics = metrics[-args.limit:]
    
    if not metrics:
        print("No metrics found.")
        return
    
    print(f"Showing {len(metrics)} metrics (total: {len(debugger.metrics)})")
    print()
    
    for metric in metrics:
        print(f"📊 {metric.name}")
        print(f"   Value: {metric.value} {metric.unit}")
        print(f"   Time: {format_timestamp(metric.timestamp)}")
        if metric.context:
            print(f"   Context: {metric.context}")
        print()


async def show_queries(args):
    """Show query performance data."""
    print_header("Database Query Performance")
    
    config = LocalDatabaseConfig()
    debugger = get_performance_debugger(config)
    
    queries = debugger.query_data
    
    if args.database:
        queries = [q for q in queries if q.database.lower() == args.database.lower()]
    
    queries = queries[-args.limit:]
    
    if not queries:
        print("No query data found.")
        return
    
    print(f"Showing {len(queries)} queries (total: {len(debugger.query_data)})")
    print()
    
    for query in queries:
        db_icon = {"postgresql": "🐘", "neo4j": "🔗", "milvus": "🔍"}.get(query.database, "💾")
        print(f"{db_icon} {query.database.upper()} - {query.query_type}")
        print(f"   Execution time: {query.execution_time * 1000:.1f}ms")
        if query.rows_affected is not None:
            print(f"   Rows affected: {query.rows_affected}")
        print(f"   Time: {format_timestamp(query.timestamp)}")
        if query.parameters:
            print(f"   Parameters: {query.parameters}")
        print()


async def show_resources(args):
    """Show resource usage snapshots."""
    print_header("System Resource Usage")
    
    config = LocalDatabaseConfig()
    debugger = get_performance_debugger(config)
    
    snapshots = debugger.resource_snapshots[-args.limit:]
    
    if not snapshots:
        print("No resource usage data found.")
        return
    
    print(f"Showing {len(snapshots)} snapshots (total: {len(debugger.resource_snapshots)})")
    print()
    
    for snapshot in snapshots:
        print(f"📈 {format_timestamp(snapshot.timestamp)}")
        print(f"   CPU: {snapshot.cpu_percent:.1f}%")
        print(f"   Memory: {snapshot.memory_percent:.1f}% ({snapshot.memory_used_mb:.1f}MB)")
        print(f"   Disk I/O: R:{snapshot.disk_io_read_mb:.1f}MB W:{snapshot.disk_io_write_mb:.1f}MB")
        print(f"   Network: S:{snapshot.network_sent_mb:.1f}MB R:{snapshot.network_recv_mb:.1f}MB")
        
        if snapshot.docker_containers:
            print(f"   Docker containers: {len(snapshot.docker_containers)} running")
            for container, stats in snapshot.docker_containers.items():
                if stats.get('status') == 'running':
                    cpu = stats.get('cpu_percent', 0)
                    mem = stats.get('memory_usage_mb', 0)
                    print(f"     {container}: CPU {cpu:.1f}%, Memory {mem:.1f}MB")
        print()


async def export_data(args):
    """Export performance data."""
    print_header("Exporting Performance Data")
    
    config = LocalDatabaseConfig()
    debugger = get_performance_debugger(config)
    
    result = debugger.export_metrics(args.filepath, args.format)
    
    if result["status"] == "success":
        print(f"✅ Data exported successfully")
        print(f"   File: {result['filepath']}")
        print(f"   Format: {result['format']}")
        print(f"   Metrics: {result['metrics_exported']}")
        print(f"   Queries: {result['queries_exported']}")
        print(f"   Snapshots: {result['snapshots_exported']}")
    else:
        print(f"❌ Export failed: {result.get('error', 'Unknown error')}")


async def clear_data(args):
    """Clear all performance data."""
    print_header("Clearing Performance Data")
    
    if not args.force:
        response = input("Are you sure you want to clear all performance data? (y/N): ")
        if response.lower() != 'y':
            print("Operation cancelled.")
            return
    
    config = LocalDatabaseConfig()
    debugger = get_performance_debugger(config)
    
    result = debugger.clear_data()
    
    print(f"✅ Data cleared successfully")
    print(f"   Metrics cleared: {result['metrics_cleared']}")
    print(f"   Queries cleared: {result['queries_cleared']}")
    print(f"   Snapshots cleared: {result['snapshots_cleared']}")


async def show_status(args):
    """Show monitoring status."""
    print_header("Performance Monitoring Status")
    
    config = LocalDatabaseConfig()
    debugger = get_performance_debugger(config)
    
    print(f"Monitoring active: {'✅ Yes' if debugger.monitoring_active else '❌ No'}")
    print(f"Metrics collected: {len(debugger.metrics)}")
    print(f"Queries analyzed: {len(debugger.query_data)}")
    print(f"Resource snapshots: {len(debugger.resource_snapshots)}")
    
    if hasattr(debugger, '_active_measurements'):
        print(f"Active measurements: {len(debugger._active_measurements)}")


async def run_benchmark(args):
    """Run performance benchmark."""
    print_header("Running Performance Benchmark")
    
    config = LocalDatabaseConfig()
    debugger = get_performance_debugger(config)
    
    print("Starting benchmark...")
    start_time = time.time()
    
    # Start monitoring for the benchmark
    await debugger.start_monitoring(1)  # 1-second intervals
    
    try:
        # Run database performance tests
        print("Testing database performance...")
        
        async with debugger.measure_operation("benchmark_postgres", {"test": "benchmark"}):
            postgres_client = debugger.factory.create_postgres_client()
            for i in range(10):
                await postgres_client.execute("SELECT 1")
        
        async with debugger.measure_operation("benchmark_neo4j", {"test": "benchmark"}):
            neo4j_client = debugger.factory.create_graph_store_client()
            for i in range(10):
                await neo4j_client.execute_query("RETURN 1")
        
        async with debugger.measure_operation("benchmark_milvus", {"test": "benchmark"}):
            milvus_client = debugger.factory.create_vector_store_client()
            for i in range(5):
                await milvus_client.list_collections()
        
        # Wait a bit to collect resource data
        await asyncio.sleep(5)
        
    finally:
        # Stop monitoring
        await debugger.stop_monitoring()
    
    end_time = time.time()
    total_time = end_time - start_time
    
    print(f"\n✅ Benchmark completed in {format_duration(total_time)}")
    
    # Show benchmark results
    benchmark_metrics = [m for m in debugger.metrics if m.context and m.context.get("test") == "benchmark"]
    
    if benchmark_metrics:
        print_section("Benchmark Results")
        for metric in benchmark_metrics:
            print(f"📊 {metric.name}: {metric.value:.1f} {metric.unit}")
    
    # Show summary
    summary = debugger.get_performance_summary(1)  # Last minute
    if summary['bottlenecks']:
        print_section("Issues Detected")
        for bottleneck in summary['bottlenecks']:
            severity_icon = "🔴" if bottleneck['severity'] == 'high' else "🟡"
            print(f"{severity_icon} {bottleneck['description']}")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Performance Debugging CLI for Local Development",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/performance-debug-cli.py start --interval 5
  python scripts/performance-debug-cli.py summary --minutes 10
  python scripts/performance-debug-cli.py metrics --filter postgres
  python scripts/performance-debug-cli.py export --filepath /tmp/perf-data.json
  python scripts/performance-debug-cli.py benchmark
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Start monitoring
    start_parser = subparsers.add_parser('start', help='Start performance monitoring')
    start_parser.add_argument('--interval', type=int, default=5, 
                             help='Monitoring interval in seconds (default: 5)')
    
    # Stop monitoring
    subparsers.add_parser('stop', help='Stop performance monitoring')
    
    # Show summary
    summary_parser = subparsers.add_parser('summary', help='Show performance summary')
    summary_parser.add_argument('--minutes', type=int, default=10,
                               help='Time range in minutes (default: 10)')
    
    # Show metrics
    metrics_parser = subparsers.add_parser('metrics', help='Show collected metrics')
    metrics_parser.add_argument('--limit', type=int, default=50,
                               help='Maximum number of metrics to show (default: 50)')
    metrics_parser.add_argument('--filter', type=str,
                               help='Filter metrics by name')
    
    # Show queries
    queries_parser = subparsers.add_parser('queries', help='Show query performance data')
    queries_parser.add_argument('--limit', type=int, default=50,
                               help='Maximum number of queries to show (default: 50)')
    queries_parser.add_argument('--database', type=str,
                               help='Filter by database type (postgresql, neo4j, milvus)')
    
    # Show resources
    resources_parser = subparsers.add_parser('resources', help='Show resource usage')
    resources_parser.add_argument('--limit', type=int, default=20,
                                 help='Maximum number of snapshots to show (default: 20)')
    
    # Export data
    export_parser = subparsers.add_parser('export', help='Export performance data')
    export_parser.add_argument('--filepath', type=str, required=True,
                              help='File path to export data')
    export_parser.add_argument('--format', type=str, default='json',
                              help='Export format (default: json)')
    
    # Clear data
    clear_parser = subparsers.add_parser('clear', help='Clear all performance data')
    clear_parser.add_argument('--force', action='store_true',
                             help='Skip confirmation prompt')
    
    # Show status
    subparsers.add_parser('status', help='Show monitoring status')
    
    # Run benchmark
    subparsers.add_parser('benchmark', help='Run performance benchmark')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # Map commands to functions
    command_map = {
        'start': start_monitoring,
        'stop': stop_monitoring,
        'summary': show_summary,
        'metrics': show_metrics,
        'queries': show_queries,
        'resources': show_resources,
        'export': export_data,
        'clear': clear_data,
        'status': show_status,
        'benchmark': run_benchmark
    }
    
    # Run the command
    try:
        asyncio.run(command_map[args.command](args))
    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user.")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()