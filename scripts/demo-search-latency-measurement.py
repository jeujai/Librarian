#!/usr/bin/env python3
"""
Demo script for search latency measurement system.

This script demonstrates the search latency measurement capabilities
by running a series of test searches and showing performance analysis.

Usage:
    python scripts/demo-search-latency-measurement.py
"""

import os
import sys
import asyncio
import json
from datetime import datetime

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tests', 'performance'))

from multimodal_librarian.logging_config import get_logger
from multimodal_librarian.monitoring.search_performance_monitor import SearchPerformanceMonitor
from multimodal_librarian.monitoring.metrics_collector import MetricsCollector


class MockVectorStore:
    """Mock vector store for demonstration."""
    
    def __init__(self):
        self.search_times = {
            "simple": 0.05,  # 50ms
            "medium": 0.15,  # 150ms
            "complex": 0.35,  # 350ms
            "slow": 0.8      # 800ms
        }
        
    def semantic_search(self, query, top_k=10, **kwargs):
        """Mock semantic search with realistic delays."""
        import time
        import random
        
        # Determine search complexity based on query
        if len(query.split()) <= 2:
            complexity = "simple"
        elif len(query.split()) <= 5:
            complexity = "medium"
        elif "complex" in query.lower() or len(query.split()) > 10:
            complexity = "slow"
        else:
            complexity = "complex"
        
        # Add some randomness
        base_time = self.search_times[complexity]
        actual_time = base_time * (0.8 + random.random() * 0.4)  # ±20% variation
        
        time.sleep(actual_time)
        
        # Return mock results
        result_count = min(top_k, random.randint(3, 8))
        return [
            {
                'chunk_id': f'chunk_{i}_{hash(query) % 1000}',
                'content': f'Mock result {i} for query: {query[:50]}...',
                'source_type': 'document',
                'source_id': f'doc_{i}',
                'content_type': 'text',
                'location_reference': f'page_{i}',
                'section': f'section_{i}',
                'similarity_score': 0.95 - (i * 0.05),
                'created_at': datetime.now().timestamp() * 1000
            }
            for i in range(result_count)
        ]
    
    def health_check(self):
        """Mock health check."""
        return True


async def simulate_search_workload(performance_monitor: SearchPerformanceMonitor):
    """Simulate a realistic search workload."""
    
    # Test queries with different characteristics
    test_queries = [
        # Simple queries (fast)
        ("AI", "simple_keyword", "simple"),
        ("ML", "abbreviation", "simple"),
        ("data", "simple_keyword", "simple"),
        
        # Medium complexity queries
        ("machine learning", "simple_keyword", "enhanced"),
        ("neural networks", "technical_term", "enhanced"),
        ("data science", "simple_keyword", "enhanced"),
        ("artificial intelligence", "simple_keyword", "enhanced"),
        
        # Complex queries (slower)
        ("How does backpropagation work in neural networks?", "question", "enhanced"),
        ("Compare supervised and unsupervised learning algorithms", "comparative", "enhanced"),
        ("Explain the mathematical foundations of deep learning", "complex_technical", "enhanced"),
        
        # Very complex queries (slowest)
        ("What are the key differences between transformer architectures and traditional RNNs in terms of computational complexity and performance on long sequences?", "complex_technical", "enhanced"),
        ("Analyze the trade-offs between model accuracy and inference speed in production machine learning systems", "analytical", "enhanced"),
    ]
    
    print("🔍 Simulating search workload...")
    print(f"   Running {len(test_queries)} different search scenarios")
    print()
    
    # Mock vector store
    vector_store = MockVectorStore()
    
    # Simulate searches
    for i, (query, query_type, service_type) in enumerate(test_queries, 1):
        print(f"[{i:2d}/{len(test_queries)}] Testing: {query[:60]}{'...' if len(query) > 60 else ''}")
        
        # Simulate search execution
        start_time = asyncio.get_event_loop().time()
        
        try:
            # Simulate vector search
            vector_start = asyncio.get_event_loop().time()
            results = vector_store.semantic_search(query, top_k=10)
            vector_end = asyncio.get_event_loop().time()
            
            # Simulate result processing
            await asyncio.sleep(0.02)  # 20ms processing time
            processing_end = asyncio.get_event_loop().time()
            
            end_time = processing_end
            
            # Calculate timing breakdown
            total_latency_ms = (end_time - start_time) * 1000
            vector_search_ms = (vector_end - vector_start) * 1000
            result_processing_ms = (processing_end - vector_end) * 1000
            
            # Simulate cache hits for repeated queries
            cache_hit = query in ["AI", "ML", "machine learning"] and i > 5
            
            # Simulate occasional fallback usage
            fallback_used = service_type == "enhanced" and total_latency_ms > 600
            
            # Record performance
            performance_monitor.record_search_performance(
                query_text=query,
                query_type=query_type,
                service_type=service_type,
                total_latency_ms=total_latency_ms,
                result_count=len(results),
                success=True,
                vector_search_ms=vector_search_ms,
                result_processing_ms=result_processing_ms,
                cache_hit=cache_hit,
                fallback_used=fallback_used
            )
            
            # Show result
            status_icon = "⚡" if total_latency_ms < 100 else "✅" if total_latency_ms < 300 else "⚠️" if total_latency_ms < 600 else "🐌"
            print(f"         {status_icon} {total_latency_ms:.1f}ms ({len(results)} results)")
            
        except Exception as e:
            # Record failure
            end_time = asyncio.get_event_loop().time()
            total_latency_ms = (end_time - start_time) * 1000
            
            performance_monitor.record_search_performance(
                query_text=query,
                query_type=query_type,
                service_type=service_type,
                total_latency_ms=total_latency_ms,
                result_count=0,
                success=False,
                error_type="search_failure"
            )
            
            print(f"         ❌ Failed: {e}")
        
        # Small delay between searches
        await asyncio.sleep(0.1)
    
    print()


async def demonstrate_concurrent_load(performance_monitor: SearchPerformanceMonitor):
    """Demonstrate concurrent search load testing."""
    
    print("⚡ Simulating concurrent search load...")
    print("   Running 5 concurrent users for 10 seconds")
    print()
    
    vector_store = MockVectorStore()
    
    # Concurrent user queries
    user_queries = [
        "artificial intelligence",
        "machine learning algorithms", 
        "neural network architectures",
        "data science techniques",
        "deep learning frameworks"
    ]
    
    async def simulate_user(user_id: int, duration_seconds: int = 10):
        """Simulate a single user's search behavior."""
        import random
        
        end_time = asyncio.get_event_loop().time() + duration_seconds
        search_count = 0
        
        while asyncio.get_event_loop().time() < end_time:
            query = random.choice(user_queries)
            
            start_time = asyncio.get_event_loop().time()
            
            try:
                results = vector_store.semantic_search(query, top_k=5)
                
                end_search_time = asyncio.get_event_loop().time()
                latency_ms = (end_search_time - start_time) * 1000
                
                performance_monitor.record_search_performance(
                    query_text=query,
                    query_type="concurrent_test",
                    service_type="enhanced",
                    total_latency_ms=latency_ms,
                    result_count=len(results),
                    success=True,
                    vector_search_ms=latency_ms * 0.8,
                    result_processing_ms=latency_ms * 0.2
                )
                
                search_count += 1
                
            except Exception as e:
                print(f"User {user_id} search failed: {e}")
            
            # Think time between searches
            await asyncio.sleep(random.uniform(0.5, 2.0))
        
        print(f"   User {user_id}: {search_count} searches completed")
    
    # Run concurrent users
    tasks = [simulate_user(i) for i in range(5)]
    await asyncio.gather(*tasks)
    
    print()


def print_performance_analysis(performance_monitor: SearchPerformanceMonitor):
    """Print comprehensive performance analysis."""
    
    print("=" * 80)
    print("📊 SEARCH PERFORMANCE ANALYSIS")
    print("=" * 80)
    
    # Get current performance
    current_performance = performance_monitor.get_current_search_performance()
    
    if "error" in current_performance:
        print(f"❌ Error getting performance data: {current_performance['error']}")
        return
    
    # Overall statistics
    print("📈 Overall Performance:")
    print(f"   Total Searches: {current_performance['total_searches']}")
    print(f"   Successful Searches: {current_performance['successful_searches']}")
    print(f"   Success Rate: {current_performance['quality_metrics']['success_rate_percent']:.1f}%")
    print()
    
    # Latency metrics
    latency = current_performance["latency_metrics"]
    print("⏱️  Latency Metrics:")
    print(f"   Average: {latency['avg_latency_ms']:.1f}ms")
    print(f"   Median: {latency['median_latency_ms']:.1f}ms")
    print(f"   P95: {latency['p95_latency_ms']:.1f}ms")
    print(f"   P99: {latency['p99_latency_ms']:.1f}ms")
    print(f"   Range: {latency['min_latency_ms']:.1f}ms - {latency['max_latency_ms']:.1f}ms")
    print()
    
    # Quality metrics
    quality = current_performance["quality_metrics"]
    print("🎯 Quality Metrics:")
    print(f"   Cache Hit Rate: {quality['cache_hit_rate_percent']:.1f}%")
    print(f"   Fallback Usage: {quality['fallback_usage_percent']:.1f}%")
    print(f"   Avg Results per Query: {quality['avg_result_count']:.1f}")
    print()
    
    # Service breakdown
    if current_performance["service_breakdown"]:
        print("🔧 Service Breakdown:")
        for service, count in current_performance["service_breakdown"].items():
            percentage = (count / current_performance['total_searches']) * 100
            print(f"   {service.title()}: {count} searches ({percentage:.1f}%)")
        print()
    
    # Query type breakdown
    if current_performance["query_type_breakdown"]:
        print("🔍 Query Type Breakdown:")
        for query_type, count in current_performance["query_type_breakdown"].items():
            percentage = (count / current_performance['total_searches']) * 100
            print(f"   {query_type.replace('_', ' ').title()}: {count} queries ({percentage:.1f}%)")
        print()
    
    # Throughput
    throughput = current_performance["throughput"]
    print("🚀 Throughput:")
    print(f"   Searches per Minute: {throughput['searches_per_minute']:.1f}")
    print(f"   Successful Searches per Minute: {throughput['successful_searches_per_minute']:.1f}")
    print()
    
    # Bottleneck analysis
    bottlenecks = performance_monitor.analyze_search_bottlenecks(hours=1)
    
    if bottlenecks:
        print("⚠️  Identified Bottlenecks:")
        for bottleneck in bottlenecks:
            impact_icon = "🔴" if bottleneck["impact_level"] == "high" else "🟡" if bottleneck["impact_level"] == "medium" else "🟢"
            print(f"   {impact_icon} {bottleneck['component'].title()}: {bottleneck['description']}")
            print(f"      Average Time: {bottleneck['avg_time_ms']:.1f}ms")
            if bottleneck["recommendations"]:
                print(f"      Recommendation: {bottleneck['recommendations'][0]}")
        print()
    else:
        print("✅ No significant bottlenecks identified")
        print()
    
    # Performance report
    report = performance_monitor.get_search_performance_report()
    
    print("🎯 Performance Status:")
    status = report["performance_status"]
    status_icons = {
        "excellent": "🎉",
        "healthy": "✅", 
        "degraded": "⚠️",
        "critical": "🔴",
        "unknown": "❓"
    }
    print(f"   {status_icons.get(status, '❓')} {status.title()}")
    print()
    
    # Recommendations
    if report["recommendations"]:
        print("💡 Performance Recommendations:")
        for i, rec in enumerate(report["recommendations"][:5], 1):
            priority_icon = "🔴" if rec["priority"] == "critical" else "🟡" if rec["priority"] == "high" else "🟢"
            print(f"   {i}. {priority_icon} {rec['recommendation']}")
            if rec.get("target"):
                print(f"      Target: {rec['target']}")
        print()
    
    print("=" * 80)


async def main():
    """Main demonstration function."""
    
    print("🚀 Search Latency Measurement Demo")
    print("=" * 80)
    print()
    
    # Initialize monitoring components
    metrics_collector = MetricsCollector()
    performance_monitor = SearchPerformanceMonitor(metrics_collector)
    
    # Set up alert callback
    def alert_callback(alert):
        severity_icons = {
            "critical": "🔴",
            "warning": "⚠️",
            "info": "ℹ️"
        }
        icon = severity_icons.get(alert.severity, "📢")
        print(f"{icon} ALERT: {alert.message}")
    
    performance_monitor.add_alert_callback(alert_callback)
    
    try:
        # Simulate different search scenarios
        await simulate_search_workload(performance_monitor)
        
        # Simulate concurrent load
        await demonstrate_concurrent_load(performance_monitor)
        
        # Wait a moment for any background processing
        await asyncio.sleep(1)
        
        # Print comprehensive analysis
        print_performance_analysis(performance_monitor)
        
        # Export results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_file = f"search_performance_demo_{timestamp}.json"
        
        performance_monitor.export_performance_data(export_file, hours=1)
        print(f"📄 Performance data exported to: {export_file}")
        
    except KeyboardInterrupt:
        print("\n⏹️  Demo interrupted by user")
    except Exception as e:
        print(f"\n❌ Demo failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Clean up
        performance_monitor.stop_monitoring()
        print("\n✅ Demo completed")


if __name__ == "__main__":
    asyncio.run(main())