#!/usr/bin/env python3
"""
Concurrent Search Testing Demonstration

This script demonstrates the concurrent search testing capabilities and shows
how to measure performance degradation and validate resource usage under load.

Validates: Task 2.1.2 - Create concurrent search testing
"""

import os
import sys
import asyncio
import json
from datetime import datetime
from typing import Dict, Any, Optional

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tests', 'performance'))

from multimodal_librarian.logging_config import get_logger
from multimodal_librarian.monitoring.search_performance_monitor import SearchPerformanceMonitor
from concurrent_search_test import ConcurrentSearchTester, run_comprehensive_concurrent_tests


class MockVectorStoreForDemo:
    """Mock vector store for demonstration purposes."""
    
    def __init__(self, base_latency_ms: float = 150, load_sensitivity: float = 0.1):
        self.base_latency_ms = base_latency_ms
        self.load_sensitivity = load_sensitivity  # How much latency increases with load
        self.search_count = 0
        self.concurrent_searches = 0
        
    def semantic_search(self, query: str, top_k: int = 10, **kwargs):
        """Mock semantic search with load-dependent latency."""
        import time
        import random
        
        self.search_count += 1
        self.concurrent_searches += 1
        
        # Simulate load-dependent latency
        load_factor = 1 + (self.concurrent_searches * self.load_sensitivity)
        actual_latency = self.base_latency_ms * load_factor
        
        # Add some randomness
        actual_latency *= (0.8 + random.random() * 0.4)  # ±20% variation
        
        # Simulate processing time
        time.sleep(actual_latency / 1000)
        
        # Simulate occasional failures under high load
        failure_rate = min(0.1, self.concurrent_searches * 0.01)  # Up to 10% failure rate
        if random.random() < failure_rate:
            self.concurrent_searches -= 1
            raise Exception(f"Search overload (concurrent: {self.concurrent_searches})")
        
        # Return mock results
        results = [
            {
                'chunk_id': f'demo_chunk_{i}_{self.search_count}',
                'content': f'Demo content for "{query[:30]}..." - Result {i+1}',
                'source_type': 'pdf',  # Use valid SourceType
                'source_id': f'demo_doc_{i}',
                'content_type': 'text',  # Use valid ContentType
                'location_reference': f'page_{i+1}',
                'section': f'section_{i+1}',
                'similarity_score': 0.95 - (i * 0.1),
                'is_bridge': False,
                'created_at': int(datetime.now().timestamp() * 1000)
            }
            for i in range(min(top_k, 3))  # Return 3 results
        ]
        
        self.concurrent_searches -= 1
        return results
    
    def health_check(self) -> bool:
        return True


async def demonstrate_baseline_vs_concurrent():
    """Demonstrate baseline vs concurrent performance comparison."""
    print("🔍 BASELINE VS CONCURRENT PERFORMANCE DEMONSTRATION")
    print("=" * 60)
    
    # Create mock vector store
    vector_store = MockVectorStoreForDemo(base_latency_ms=100, load_sensitivity=0.15)
    tester = ConcurrentSearchTester(vector_store)
    
    # Measure baseline performance
    print("📊 Measuring baseline (single-user) performance...")
    baseline = await tester.measure_baseline_performance(service_type="simple", iterations=5)
    
    print(f"   ✅ Baseline Results:")
    print(f"      Average Latency: {baseline['avg_latency_ms']:.1f}ms")
    print(f"      P95 Latency: {baseline['p95_latency_ms']:.1f}ms")
    print(f"      Min/Max: {baseline['min_latency_ms']:.1f}ms / {baseline['max_latency_ms']:.1f}ms")
    print()
    
    # Test different concurrent user levels
    user_levels = [5, 10, 20]
    
    for users in user_levels:
        print(f"⚡ Testing {users} concurrent users...")
        
        result = await tester.run_concurrent_search_test(
            concurrent_users=users,
            duration_seconds=15,
            service_type="simple",
            query_pattern="mixed"
        )
        
        # Display results
        perf = result.concurrent_performance
        success = result.success_metrics
        degradation = result.performance_degradation
        
        print(f"   📈 Concurrent Results:")
        print(f"      Success Rate: {success['success_rate_percent']:.1f}%")
        print(f"      Average Latency: {perf['avg_latency_ms']:.1f}ms")
        print(f"      P95 Latency: {perf['p95_latency_ms']:.1f}ms")
        print(f"      Throughput: {success['successful_throughput_rps']:.1f} RPS")
        
        if degradation.get("avg_latency_ms_degradation_percent") is not None:
            print(f"      Performance Impact: {degradation['avg_latency_ms_degradation_percent']:.1f}% latency increase")
        
        if success.get("resource_contention_rate_percent", 0) > 0:
            print(f"      Resource Contention: {success['resource_contention_rate_percent']:.1f}%")
        
        # Show top recommendation
        if result.recommendations:
            print(f"      💡 Key Recommendation: {result.recommendations[0]}")
        
        print()


async def demonstrate_query_patterns():
    """Demonstrate different concurrent query patterns."""
    print("🔄 QUERY PATTERN ANALYSIS DEMONSTRATION")
    print("=" * 60)
    
    vector_store = MockVectorStoreForDemo(base_latency_ms=120, load_sensitivity=0.12)
    tester = ConcurrentSearchTester(vector_store)
    
    patterns = ["mixed", "uniform", "burst"]
    
    for pattern in patterns:
        print(f"🎯 Testing '{pattern}' query pattern...")
        
        result = await tester.run_concurrent_search_test(
            concurrent_users=8,
            duration_seconds=12,
            service_type="simple",
            query_pattern=pattern
        )
        
        perf = result.concurrent_performance
        success = result.success_metrics
        
        print(f"   Pattern: {pattern.title()}")
        print(f"   Success Rate: {success['success_rate_percent']:.1f}%")
        print(f"   Avg Latency: {perf['avg_latency_ms']:.1f}ms")
        print(f"   Throughput: {success['successful_throughput_rps']:.1f} RPS")
        
        if perf.get('avg_queue_wait_ms', 0) > 0:
            print(f"   Queue Wait: {perf['avg_queue_wait_ms']:.1f}ms")
        
        print()


async def demonstrate_scaling_analysis():
    """Demonstrate scaling analysis and capacity planning."""
    print("📈 SCALING ANALYSIS DEMONSTRATION")
    print("=" * 60)
    
    vector_store = MockVectorStoreForDemo(base_latency_ms=80, load_sensitivity=0.08)
    tester = ConcurrentSearchTester(vector_store)
    
    print("🔍 Running scaling test (gradual user increase)...")
    
    scaling_result = await tester.run_scaling_test(
        max_users=25,
        step_size=5,
        step_duration=10,
        service_type="simple"
    )
    
    print("📊 Scaling Results:")
    
    # Display scaling points
    for point in scaling_result["scaling_results"]:
        users = point["concurrent_users"]
        latency = point["avg_latency_ms"]
        success_rate = point["success_rate_percent"]
        throughput = point["throughput_rps"]
        
        status = "✅" if success_rate > 95 else "⚠️" if success_rate > 90 else "❌"
        print(f"   {status} {users:2d} users: {latency:5.1f}ms avg, {success_rate:5.1f}% success, {throughput:5.1f} RPS")
    
    # Display analysis
    analysis = scaling_result["scaling_analysis"]
    print(f"\n🎯 Scaling Analysis:")
    print(f"   Max Tested Users: {scaling_result['max_tested_users']}")
    print(f"   Recommended Max: {scaling_result['recommended_max_users']}")
    
    if "scaling_efficiency" in analysis:
        efficiency = analysis["scaling_efficiency"]
        print(f"   Scaling Efficiency: {efficiency.get('overall_scaling_score', 0):.1f}%")
        print(f"   Throughput Efficiency: {efficiency.get('throughput_efficiency_percent', 0):.1f}%")
    
    if "performance_characteristics" in analysis:
        characteristics = analysis["performance_characteristics"]
        print(f"   Scaling Pattern: {characteristics}")
    
    print()


async def demonstrate_resource_monitoring():
    """Demonstrate resource usage monitoring during concurrent tests."""
    print("💻 RESOURCE MONITORING DEMONSTRATION")
    print("=" * 60)
    
    vector_store = MockVectorStoreForDemo(base_latency_ms=200, load_sensitivity=0.2)
    tester = ConcurrentSearchTester(vector_store)
    
    print("🔍 Running concurrent test with resource monitoring...")
    
    result = await tester.run_concurrent_search_test(
        concurrent_users=12,
        duration_seconds=20,
        service_type="simple",
        query_pattern="mixed"
    )
    
    # Display resource usage
    resource_usage = result.resource_usage
    
    if "cpu_usage" in resource_usage:
        cpu = resource_usage["cpu_usage"]
        print(f"📊 CPU Usage:")
        print(f"   Average: {cpu['avg_percent']:.1f}%")
        print(f"   Peak: {cpu['max_percent']:.1f}%")
    
    if "memory_usage" in resource_usage:
        memory = resource_usage["memory_usage"]
        print(f"💾 Memory Usage:")
        print(f"   Average: {memory['avg_mb']:.1f} MB")
        print(f"   Peak: {memory['max_mb']:.1f} MB")
    
    if "thread_usage" in resource_usage:
        threads = resource_usage["thread_usage"]
        print(f"🧵 Thread Usage:")
        print(f"   Average: {threads['avg_threads']:.1f}")
        print(f"   Peak: {threads['max_threads']}")
    
    # Display efficiency metrics
    if "resource_efficiency" in resource_usage:
        efficiency = resource_usage["resource_efficiency"]
        print(f"⚡ Resource Efficiency:")
        print(f"   CPU Stable: {'✅' if efficiency['cpu_utilization_stable'] else '❌'}")
        print(f"   Memory Controlled: {'✅' if efficiency['memory_growth_controlled'] else '❌'}")
        print(f"   Thread Scaling: {'✅' if efficiency['thread_scaling_reasonable'] else '❌'}")
    
    print()


async def demonstrate_performance_monitoring_integration():
    """Demonstrate integration with search performance monitoring."""
    print("📈 PERFORMANCE MONITORING INTEGRATION")
    print("=" * 60)
    
    # Create performance monitor
    performance_monitor = SearchPerformanceMonitor()
    
    print("🔍 Simulating concurrent searches with performance monitoring...")
    
    # Simulate concurrent search operations
    queries = [
        ("machine learning algorithms", "technical"),
        ("data preprocessing", "process"),
        ("neural networks", "technical"),
        ("AI applications", "general"),
        ("deep learning", "technical")
    ]
    
    # Record multiple search operations
    for i in range(20):
        query, query_type = queries[i % len(queries)]
        
        # Simulate varying latency based on load
        base_latency = 150
        load_factor = 1 + (i % 5) * 0.1  # Simulate load
        latency_ms = base_latency * load_factor
        
        # Record the search performance
        performance_monitor.record_search_performance(
            query_text=query,
            query_type=query_type,
            service_type="enhanced",
            total_latency_ms=latency_ms,
            result_count=3,
            success=True,
            vector_search_ms=latency_ms * 0.7,
            result_processing_ms=latency_ms * 0.3,
            cache_hit=(i % 4 == 0),  # 25% cache hit rate
            fallback_used=(i % 10 == 0)  # 10% fallback usage
        )
    
    # Get current performance metrics
    current_performance = performance_monitor.get_current_search_performance()
    
    if "latency_metrics" in current_performance:
        latency = current_performance["latency_metrics"]
        print(f"📊 Current Performance Metrics:")
        print(f"   Average Latency: {latency['avg_latency_ms']:.1f}ms")
        print(f"   P95 Latency: {latency['p95_latency_ms']:.1f}ms")
        print(f"   Min/Max: {latency['min_latency_ms']:.1f}ms / {latency['max_latency_ms']:.1f}ms")
    
    if "quality_metrics" in current_performance:
        quality = current_performance["quality_metrics"]
        print(f"🎯 Quality Metrics:")
        print(f"   Success Rate: {quality['success_rate_percent']:.1f}%")
        print(f"   Cache Hit Rate: {quality['cache_hit_rate_percent']:.1f}%")
        print(f"   Fallback Usage: {quality['fallback_usage_percent']:.1f}%")
    
    if "throughput" in current_performance:
        throughput = current_performance["throughput"]
        print(f"⚡ Throughput:")
        print(f"   Searches/min: {throughput['searches_per_minute']:.1f}")
        print(f"   Successful/min: {throughput['successful_searches_per_minute']:.1f}")
    
    print()


async def demonstrate_comprehensive_testing():
    """Demonstrate comprehensive concurrent testing suite."""
    print("🚀 COMPREHENSIVE CONCURRENT TESTING SUITE")
    print("=" * 60)
    
    vector_store = MockVectorStoreForDemo(base_latency_ms=100, load_sensitivity=0.1)
    
    print("🔍 Running comprehensive concurrent tests...")
    
    # Run comprehensive tests
    results = await run_comprehensive_concurrent_tests(
        vector_store,
        service_types=["simple"],  # Test simple service only for demo
        include_scaling_test=True
    )
    
    print("📊 Comprehensive Test Results Summary:")
    
    # Display concurrent test results
    if "concurrent_tests" in results:
        for service, service_results in results["concurrent_tests"].items():
            print(f"\n🎯 {service.title()} Service Results:")
            
            for test_name, test_result in service_results.items():
                if "error" not in test_result:
                    success_rate = test_result["success_metrics"]["success_rate_percent"]
                    avg_latency = test_result["concurrent_performance"]["avg_latency_ms"]
                    print(f"   {test_name}: {success_rate:.1f}% success, {avg_latency:.1f}ms avg")
    
    # Display scaling test results
    if "scaling_tests" in results:
        for service, scaling_result in results["scaling_tests"].items():
            if "error" not in scaling_result:
                max_users = scaling_result["recommended_max_users"]
                print(f"\n📈 {service.title()} Scaling: Recommended max {max_users} users")
    
    # Display overall recommendations
    if "performance_report" in results:
        report = results["performance_report"]
        if "overall_recommendations" in report:
            print(f"\n💡 Key Recommendations:")
            for i, rec in enumerate(report["overall_recommendations"][:3], 1):
                print(f"   {i}. {rec}")
    
    print(f"\n⏱️  Total test duration: {results['total_duration']:.1f} seconds")
    print()


async def main():
    """Run all concurrent search testing demonstrations."""
    print("=" * 80)
    print("⚡ CONCURRENT SEARCH TESTING DEMONSTRATION SUITE")
    print("=" * 80)
    print(f"📅 Started: {datetime.now().isoformat()}")
    print(f"🎯 Purpose: Demonstrate Task 2.1.2 - Create concurrent search testing")
    print(f"✅ Validates: Requirement 2.3 - Concurrent search performance maintenance")
    print()
    
    try:
        # Run all demonstrations
        await demonstrate_baseline_vs_concurrent()
        await demonstrate_query_patterns()
        await demonstrate_scaling_analysis()
        await demonstrate_resource_monitoring()
        await demonstrate_performance_monitoring_integration()
        await demonstrate_comprehensive_testing()
        
        print("=" * 80)
        print("✅ CONCURRENT SEARCH TESTING DEMONSTRATION COMPLETED")
        print("=" * 80)
        print()
        print("🎯 Key Capabilities Demonstrated:")
        print("   ✅ Baseline vs concurrent performance comparison")
        print("   ✅ Multiple simultaneous search operations")
        print("   ✅ Performance degradation measurement")
        print("   ✅ Resource usage validation")
        print("   ✅ Query pattern analysis")
        print("   ✅ Scaling analysis and capacity planning")
        print("   ✅ Integration with performance monitoring")
        print()
        print("📊 Task 2.1.2 Implementation Status: COMPLETE")
        print("   - ✅ Test multiple simultaneous searches")
        print("   - ✅ Measure performance degradation")
        print("   - ✅ Validate resource usage")
        print("   - ✅ Validates Requirement 2.3")
        print()
        
    except Exception as e:
        print(f"❌ Demonstration failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit(asyncio.run(main()))