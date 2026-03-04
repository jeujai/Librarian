#!/usr/bin/env python3
"""
Database Performance Metrics Demo

This script demonstrates the enhanced database performance metrics functionality
implemented for the local development conversion. It shows how to collect
comprehensive performance metrics from all database services.

Usage:
    python examples/database_performance_metrics_demo.py
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def demo_database_performance_metrics():
    """Demonstrate enhanced database performance metrics collection."""
    
    print("🔍 Database Performance Metrics Demo")
    print("=" * 60)
    
    try:
        # Import the enhanced performance collection functions
        from src.multimodal_librarian.api.routers.health_local import (
            _collect_postgres_performance,
            _collect_neo4j_performance,
            _collect_milvus_performance,
            _collect_redis_performance,
            database_performance_metrics
        )
        from src.multimodal_librarian.clients.database_factory import DatabaseClientFactory
        from src.multimodal_librarian.config.local_config import LocalDatabaseConfig
        
        print("✅ Successfully imported performance metrics functions")
        
        # Create configuration for local development
        config = LocalDatabaseConfig()
        config.database_type = 'local'
        
        # Create database factory
        factory = DatabaseClientFactory(config)
        
        print(f"📊 Testing database performance metrics collection...")
        print(f"   Database type: {config.database_type}")
        print(f"   Timestamp: {datetime.now().isoformat()}")
        print()
        
        # Test individual database performance collection
        databases_to_test = [
            ("PostgreSQL", _collect_postgres_performance),
            ("Neo4j", _collect_neo4j_performance),
            ("Milvus", _collect_milvus_performance),
            ("Redis", _collect_redis_performance)
        ]
        
        individual_results = {}
        
        for db_name, collect_func in databases_to_test:
            print(f"🔍 Testing {db_name} performance metrics...")
            
            try:
                result = await collect_func(factory)
                individual_results[db_name.lower()] = result
                
                # Display key metrics
                print(f"   ✅ Status: {result.get('status', 'unknown')}")
                print(f"   ⏱️  Response Time: {result.get('response_time_ms', 'N/A')} ms")
                
                if 'performance_score' in result:
                    score = result['performance_score']
                    print(f"   📈 Performance Score: {score}/100")
                    
                    # Color code the score
                    if score >= 90:
                        print("      🟢 Excellent performance")
                    elif score >= 70:
                        print("      🟡 Good performance")
                    elif score >= 50:
                        print("      🟠 Fair performance")
                    else:
                        print("      🔴 Poor performance")
                
                # Show recommendations if any
                recommendations = result.get('recommendations', [])
                if recommendations:
                    print(f"   💡 Recommendations ({len(recommendations)}):")
                    for i, rec in enumerate(recommendations[:3], 1):  # Show first 3
                        print(f"      {i}. {rec}")
                    if len(recommendations) > 3:
                        print(f"      ... and {len(recommendations) - 3} more")
                
                # Show specific metrics based on database type
                if db_name == "PostgreSQL":
                    connections = result.get('connections', {})
                    if isinstance(connections, dict):
                        print(f"   🔗 Connections: {connections.get('total', 0)} total, {connections.get('active', 0)} active")
                    
                    cache_perf = result.get('cache_performance', {})
                    if cache_perf:
                        print(f"   💾 Cache Hit Ratio: {cache_perf.get('hit_ratio_percent', 0):.1f}%")
                
                elif db_name == "Neo4j":
                    db_stats = result.get('database_stats', {})
                    if db_stats:
                        print(f"   📊 Nodes: {db_stats.get('node_count', 0):,}, Relationships: {db_stats.get('relationship_count', 0):,}")
                    
                    memory_stats = result.get('memory_stats', {})
                    if memory_stats:
                        used_mb = memory_stats.get('heap_used_mb', 0)
                        max_mb = memory_stats.get('heap_max_mb', 0)
                        if max_mb > 0:
                            usage_percent = (used_mb / max_mb) * 100
                            print(f"   🧠 Memory Usage: {used_mb:.1f}MB / {max_mb:.1f}MB ({usage_percent:.1f}%)")
                
                elif db_name == "Milvus":
                    collection_count = result.get('collection_count', 0)
                    total_entities = result.get('total_entities', 0)
                    print(f"   📚 Collections: {collection_count}, Total Entities: {total_entities:,}")
                    
                    avg_search_time = result.get('avg_search_time_ms')
                    if avg_search_time:
                        print(f"   🔍 Avg Search Time: {avg_search_time:.2f} ms")
                
                elif db_name == "Redis":
                    memory_stats = result.get('memory_stats', {})
                    if memory_stats:
                        used_mb = memory_stats.get('used_memory_mb', 0)
                        print(f"   💾 Memory Usage: {used_mb:.1f} MB")
                    
                    cache_perf = result.get('cache_performance', {})
                    if cache_perf:
                        hit_ratio = cache_perf.get('hit_ratio_percent', 0)
                        total_requests = cache_perf.get('total_requests', 0)
                        print(f"   🎯 Cache Hit Ratio: {hit_ratio:.1f}% ({total_requests:,} requests)")
                
            except Exception as e:
                print(f"   ❌ Error: {str(e)}")
                individual_results[db_name.lower()] = {"status": "error", "error": str(e)}
            
            print()
        
        # Test comprehensive performance metrics endpoint
        print("🔍 Testing comprehensive performance metrics endpoint...")
        
        try:
            comprehensive_result = await database_performance_metrics(factory)
            
            print(f"   ✅ Collection completed in {comprehensive_result.get('collection_time_ms', 0):.2f} ms")
            
            # Display summary
            summary = comprehensive_result.get('summary', {})
            print(f"   📊 Summary:")
            print(f"      Average Response Time: {summary.get('avg_response_time_ms', 0):.2f} ms")
            print(f"      Total Connections: {summary.get('total_connections', 0)}")
            print(f"      Overall Performance Score: {summary.get('performance_score', 0):.1f}/100")
            
            # Show top recommendations
            recommendations = summary.get('recommendations', [])
            if recommendations:
                print(f"   💡 Top Recommendations:")
                for i, rec in enumerate(recommendations[:5], 1):
                    print(f"      {i}. {rec}")
            
            # Show service breakdown
            services = comprehensive_result.get('services', {})
            print(f"   🔧 Service Status:")
            for service_name, service_data in services.items():
                status = service_data.get('status', 'unknown')
                score = service_data.get('performance_score', 'N/A')
                print(f"      {service_name}: {status} (Score: {score})")
            
        except Exception as e:
            print(f"   ❌ Error in comprehensive metrics: {str(e)}")
        
        print()
        
        # Export results for analysis
        print("📄 Exporting results...")
        
        export_data = {
            "timestamp": datetime.now().isoformat(),
            "individual_results": individual_results,
            "comprehensive_result": comprehensive_result if 'comprehensive_result' in locals() else None
        }
        
        # Save to file
        output_file = f"database_performance_metrics_{int(datetime.now().timestamp())}.json"
        with open(output_file, 'w') as f:
            json.dump(export_data, f, indent=2, default=str)
        
        print(f"   ✅ Results exported to: {output_file}")
        
        # Performance analysis
        print()
        print("📈 Performance Analysis:")
        
        # Analyze response times
        response_times = []
        for db_name, result in individual_results.items():
            if result.get('status') == 'healthy' and 'response_time_ms' in result:
                response_times.append((db_name, result['response_time_ms']))
        
        if response_times:
            response_times.sort(key=lambda x: x[1])
            print(f"   ⚡ Fastest Database: {response_times[0][0]} ({response_times[0][1]:.2f} ms)")
            print(f"   🐌 Slowest Database: {response_times[-1][0]} ({response_times[-1][1]:.2f} ms)")
        
        # Analyze performance scores
        scores = []
        for db_name, result in individual_results.items():
            if result.get('status') == 'healthy' and 'performance_score' in result:
                scores.append((db_name, result['performance_score']))
        
        if scores:
            scores.sort(key=lambda x: x[1], reverse=True)
            print(f"   🏆 Best Performing: {scores[0][0]} (Score: {scores[0][1]:.1f})")
            if len(scores) > 1:
                print(f"   ⚠️  Needs Attention: {scores[-1][0]} (Score: {scores[-1][1]:.1f})")
        
        # Count total recommendations
        total_recommendations = sum(
            len(result.get('recommendations', []))
            for result in individual_results.values()
            if isinstance(result, dict)
        )
        
        if total_recommendations > 0:
            print(f"   💡 Total Optimization Opportunities: {total_recommendations}")
        else:
            print(f"   ✨ All databases performing optimally!")
        
        print()
        print("✅ Database Performance Metrics Demo completed successfully!")
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("   Make sure you're running this from the project root directory")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        logger.exception("Demo failed with exception")


async def main():
    """Main demo function."""
    print("🚀 Starting Database Performance Metrics Demo")
    print()
    
    await demo_database_performance_metrics()
    
    print()
    print("📚 Learn More:")
    print("   - Enhanced metrics implementation: src/multimodal_librarian/api/routers/health_local.py")
    print("   - Local performance collector: src/multimodal_librarian/monitoring/local_performance_metrics.py")
    print("   - Query performance monitor: src/multimodal_librarian/monitoring/query_performance_monitor.py")
    print("   - Test suite: tests/monitoring/test_enhanced_database_performance_metrics.py")


if __name__ == "__main__":
    asyncio.run(main())