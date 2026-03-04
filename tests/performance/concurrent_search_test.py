#!/usr/bin/env python3
"""
Concurrent Search Performance Testing Suite

This module provides comprehensive concurrent search testing capabilities including:
- Multiple simultaneous search operations
- Performance degradation measurement under load
- Resource usage validation during concurrent operations
- Concurrent user simulation and load patterns
- Performance comparison between single and concurrent operations

Validates: Requirement 2.3 - Concurrent search performance maintenance
"""

import os
import sys
import asyncio
import time
import json
import statistics
import psutil
import threading
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import uuid
import resource

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from multimodal_librarian.logging_config import get_logger
from multimodal_librarian.components.vector_store.search_service import (
    EnhancedSemanticSearchService, SearchRequest
)
from multimodal_librarian.components.vector_store.search_service_simple import (
    SimpleSemanticSearchService, SimpleSearchRequest
)
from multimodal_librarian.components.vector_store.vector_store import VectorStore
from multimodal_librarian.models.search_types import SearchQuery, SearchResult
from multimodal_librarian.models.core import SourceType, ContentType


@dataclass
class ConcurrentSearchMetric:
    """Individual concurrent search measurement."""
    user_id: int
    query_text: str
    query_type: str
    search_service: str
    start_time: datetime
    end_time: datetime
    latency_ms: float
    result_count: int
    success: bool
    error_message: Optional[str] = None
    
    # Concurrent-specific metrics
    concurrent_users: int = 1
    queue_wait_time_ms: float = 0.0
    resource_contention: bool = False


@dataclass
class ResourceUsageSnapshot:
    """System resource usage at a point in time."""
    timestamp: datetime
    cpu_percent: float
    memory_mb: float
    memory_percent: float
    active_threads: int
    open_files: int
    network_connections: int
    
    # Search-specific metrics
    concurrent_searches: int = 0
    queue_depth: int = 0


@dataclass
class ConcurrentPerformanceResult:
    """Results from concurrent performance testing."""
    test_config: Dict[str, Any]
    baseline_performance: Dict[str, float]
    concurrent_performance: Dict[str, float]
    performance_degradation: Dict[str, float]
    resource_usage: Dict[str, Any]
    success_metrics: Dict[str, Any]
    recommendations: List[str]


class ConcurrentSearchTester:
    """Comprehensive concurrent search performance testing."""
    
    def __init__(self, vector_store: VectorStore, config: Optional[Dict] = None):
        self.vector_store = vector_store
        self.config = config or {}
        self.logger = get_logger("concurrent_search_tester")
        
        # Initialize search services
        self.simple_service = SimpleSemanticSearchService(vector_store)
        self.enhanced_service = EnhancedSemanticSearchService(vector_store, config)
        
        # Test data storage
        self.concurrent_measurements: List[ConcurrentSearchMetric] = []
        self.resource_snapshots: List[ResourceUsageSnapshot] = []
        
        # Test configuration
        self.test_queries = self._generate_concurrent_test_queries()
        
        # Resource monitoring
        self._monitoring_active = False
        self._resource_monitor_task = None
        
        # Thread safety
        self._lock = threading.Lock()
        
        self.logger.info("Concurrent search tester initialized")
    
    def _generate_concurrent_test_queries(self) -> List[Dict[str, Any]]:
        """Generate diverse test queries optimized for concurrent testing."""
        return [
            # Fast queries (should complete quickly even under load)
            {
                "query": "AI",
                "type": "simple_fast",
                "description": "Simple fast query",
                "expected_latency_ms": 100,
                "weight": 0.3  # 30% of concurrent load
            },
            {
                "query": "machine learning",
                "type": "keyword_fast",
                "description": "Common keyword query",
                "expected_latency_ms": 200,
                "weight": 0.25
            },
            
            # Medium complexity queries
            {
                "query": "neural network architecture",
                "type": "technical_medium",
                "description": "Technical multi-word query",
                "expected_latency_ms": 300,
                "weight": 0.2
            },
            {
                "query": "data preprocessing techniques",
                "type": "process_medium",
                "description": "Process-oriented query",
                "expected_latency_ms": 350,
                "weight": 0.15
            },
            
            # Complex queries (may be slower under load)
            {
                "query": "How do transformer models handle attention mechanisms in natural language processing?",
                "type": "complex_question",
                "description": "Complex technical question",
                "expected_latency_ms": 500,
                "weight": 0.08
            },
            {
                "query": "Compare supervised learning algorithms for classification tasks including decision trees, random forests, and support vector machines",
                "type": "complex_comparative",
                "description": "Long comparative query",
                "expected_latency_ms": 600,
                "weight": 0.02
            }
        ]
    
    async def measure_baseline_performance(
        self, 
        service_type: str = "enhanced",
        iterations: int = 10
    ) -> Dict[str, float]:
        """Measure baseline single-user performance."""
        self.logger.info(f"Measuring baseline performance for {service_type} service")
        
        baseline_measurements = []
        
        for query_data in self.test_queries:
            query = query_data["query"]
            query_type = query_data["type"]
            
            # Run multiple iterations for each query
            for _ in range(iterations):
                start_time = time.perf_counter()
                
                try:
                    if service_type == "simple":
                        request = SimpleSearchRequest(
                            query=query,
                            session_id=str(uuid.uuid4()),
                            top_k=10
                        )
                        response = await self.simple_service.search(request)
                        success = True
                        result_count = len(response.results)
                    else:
                        request = SearchRequest(
                            query=query,
                            session_id=str(uuid.uuid4()),
                            top_k=10
                        )
                        response = await self.enhanced_service.search(request)
                        success = True
                        result_count = len(response.results) if hasattr(response, 'results') else 0
                    
                    latency_ms = (time.perf_counter() - start_time) * 1000
                    baseline_measurements.append(latency_ms)
                    
                except Exception as e:
                    latency_ms = (time.perf_counter() - start_time) * 1000
                    self.logger.error(f"Baseline search failed: {e}")
                    # Don't include failed measurements in baseline
        
        if not baseline_measurements:
            raise ValueError("No successful baseline measurements")
        
        return {
            "avg_latency_ms": statistics.mean(baseline_measurements),
            "median_latency_ms": statistics.median(baseline_measurements),
            "p95_latency_ms": sorted(baseline_measurements)[int(0.95 * len(baseline_measurements))],
            "p99_latency_ms": sorted(baseline_measurements)[int(0.99 * len(baseline_measurements))],
            "min_latency_ms": min(baseline_measurements),
            "max_latency_ms": max(baseline_measurements),
            "std_dev_ms": statistics.stdev(baseline_measurements) if len(baseline_measurements) > 1 else 0
        }
    
    async def run_concurrent_search_test(
        self,
        concurrent_users: int = 10,
        duration_seconds: int = 60,
        service_type: str = "enhanced",
        query_pattern: str = "mixed"  # "mixed", "uniform", "burst"
    ) -> ConcurrentPerformanceResult:
        """Run comprehensive concurrent search performance test."""
        
        self.logger.info(f"Running concurrent search test: {concurrent_users} users, {duration_seconds}s, {query_pattern} pattern")
        
        # Start resource monitoring
        await self._start_resource_monitoring()
        
        # Measure baseline performance first
        baseline_performance = await self.measure_baseline_performance(service_type, iterations=5)
        
        # Prepare concurrent test
        test_start = time.time()
        test_end = test_start + duration_seconds
        
        # Results storage
        concurrent_measurements = []
        measurement_lock = threading.Lock()
        
        # User simulation based on pattern
        async def simulate_user(user_id: int):
            """Simulate a single user's concurrent search behavior."""
            user_measurements = []
            
            while time.time() < test_end:
                # Select query based on pattern
                if query_pattern == "uniform":
                    # All users use the same query type
                    query_data = self.test_queries[0]
                elif query_pattern == "burst":
                    # Simulate burst patterns with pauses
                    if time.time() % 10 < 3:  # 3 seconds of activity every 10 seconds
                        query_data = self.test_queries[user_id % len(self.test_queries)]
                    else:
                        await asyncio.sleep(0.5)
                        continue
                else:  # mixed pattern
                    # Weighted random selection
                    import random
                    weights = [q["weight"] for q in self.test_queries]
                    query_data = random.choices(self.test_queries, weights=weights)[0]
                
                # Record start time and resource contention
                start_time = datetime.now()
                queue_start = time.perf_counter()
                
                try:
                    if service_type == "simple":
                        request = SimpleSearchRequest(
                            query=query_data["query"],
                            session_id=f"user_{user_id}_{uuid.uuid4()}",
                            top_k=10
                        )
                        
                        search_start = time.perf_counter()
                        response = await self.simple_service.search(request)
                        search_end = time.perf_counter()
                        
                        result_count = len(response.results)
                        success = True
                        error_message = None
                    else:
                        request = SearchRequest(
                            query=query_data["query"],
                            session_id=f"user_{user_id}_{uuid.uuid4()}",
                            top_k=10
                        )
                        
                        search_start = time.perf_counter()
                        response = await self.enhanced_service.search(request)
                        search_end = time.perf_counter()
                        
                        result_count = len(response.results) if hasattr(response, 'results') else 0
                        success = True
                        error_message = None
                    
                    # Calculate metrics
                    queue_wait_time_ms = (search_start - queue_start) * 1000
                    latency_ms = (search_end - search_start) * 1000
                    
                    # Detect resource contention (if wait time is significant)
                    resource_contention = queue_wait_time_ms > 50  # >50ms wait suggests contention
                    
                    measurement = ConcurrentSearchMetric(
                        user_id=user_id,
                        query_text=query_data["query"][:50],  # Truncate for storage
                        query_type=query_data["type"],
                        search_service=service_type,
                        start_time=start_time,
                        end_time=datetime.now(),
                        latency_ms=latency_ms,
                        result_count=result_count,
                        success=success,
                        error_message=error_message,
                        concurrent_users=concurrent_users,
                        queue_wait_time_ms=queue_wait_time_ms,
                        resource_contention=resource_contention
                    )
                    
                    user_measurements.append(measurement)
                    
                except Exception as e:
                    measurement = ConcurrentSearchMetric(
                        user_id=user_id,
                        query_text=query_data["query"][:50],
                        query_type=query_data["type"],
                        search_service=service_type,
                        start_time=start_time,
                        end_time=datetime.now(),
                        latency_ms=(time.perf_counter() - search_start) * 1000,
                        result_count=0,
                        success=False,
                        error_message=str(e),
                        concurrent_users=concurrent_users,
                        queue_wait_time_ms=(time.perf_counter() - queue_start) * 1000,
                        resource_contention=True
                    )
                    
                    user_measurements.append(measurement)
                    self.logger.error(f"User {user_id} search failed: {e}")
                
                # Variable delay between searches (realistic user behavior)
                await asyncio.sleep(0.1 + (user_id % 3) * 0.05)  # 0.1-0.25s delay
            
            with measurement_lock:
                concurrent_measurements.extend(user_measurements)
        
        # Run concurrent users
        tasks = [simulate_user(i) for i in range(concurrent_users)]
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Stop resource monitoring
        await self._stop_resource_monitoring()
        
        # Store measurements
        with self._lock:
            self.concurrent_measurements.extend(concurrent_measurements)
        
        # Analyze results
        return self._analyze_concurrent_performance(
            concurrent_measurements,
            baseline_performance,
            {
                "concurrent_users": concurrent_users,
                "duration_seconds": duration_seconds,
                "service_type": service_type,
                "query_pattern": query_pattern
            }
        )
    
    def _analyze_concurrent_performance(
        self,
        measurements: List[ConcurrentSearchMetric],
        baseline: Dict[str, float],
        test_config: Dict[str, Any]
    ) -> ConcurrentPerformanceResult:
        """Analyze concurrent performance results."""
        
        successful_measurements = [m for m in measurements if m.success]
        
        if not successful_measurements:
            return ConcurrentPerformanceResult(
                test_config=test_config,
                baseline_performance=baseline,
                concurrent_performance={"error": "No successful measurements"},
                performance_degradation={},
                resource_usage={},
                success_metrics={},
                recommendations=["Investigate search failures under concurrent load"]
            )
        
        # Calculate concurrent performance metrics
        latencies = [m.latency_ms for m in successful_measurements]
        queue_waits = [m.queue_wait_time_ms for m in successful_measurements]
        
        concurrent_performance = {
            "avg_latency_ms": statistics.mean(latencies),
            "median_latency_ms": statistics.median(latencies),
            "p95_latency_ms": sorted(latencies)[int(0.95 * len(latencies))],
            "p99_latency_ms": sorted(latencies)[int(0.99 * len(latencies))],
            "min_latency_ms": min(latencies),
            "max_latency_ms": max(latencies),
            "std_dev_ms": statistics.stdev(latencies) if len(latencies) > 1 else 0,
            "avg_queue_wait_ms": statistics.mean(queue_waits),
            "max_queue_wait_ms": max(queue_waits)
        }
        
        # Calculate performance degradation
        performance_degradation = {}
        for metric in ["avg_latency_ms", "p95_latency_ms", "p99_latency_ms"]:
            if metric in baseline and baseline[metric] > 0:
                degradation_percent = ((concurrent_performance[metric] - baseline[metric]) / baseline[metric]) * 100
                performance_degradation[f"{metric}_degradation_percent"] = degradation_percent
        
        # Calculate success metrics
        total_measurements = len(measurements)
        success_rate = (len(successful_measurements) / total_measurements) * 100
        resource_contention_rate = (len([m for m in measurements if m.resource_contention]) / total_measurements) * 100
        
        success_metrics = {
            "total_requests": total_measurements,
            "successful_requests": len(successful_measurements),
            "success_rate_percent": success_rate,
            "resource_contention_rate_percent": resource_contention_rate,
            "throughput_rps": total_measurements / test_config["duration_seconds"],
            "successful_throughput_rps": len(successful_measurements) / test_config["duration_seconds"]
        }
        
        # Analyze resource usage
        resource_usage = self._analyze_resource_usage()
        
        # Generate recommendations
        recommendations = self._generate_concurrent_recommendations(
            performance_degradation, success_metrics, resource_usage
        )
        
        return ConcurrentPerformanceResult(
            test_config=test_config,
            baseline_performance=baseline,
            concurrent_performance=concurrent_performance,
            performance_degradation=performance_degradation,
            resource_usage=resource_usage,
            success_metrics=success_metrics,
            recommendations=recommendations
        )
    
    async def _start_resource_monitoring(self):
        """Start monitoring system resource usage."""
        self._monitoring_active = True
        
        async def monitor_resources():
            while self._monitoring_active:
                try:
                    # Get current process info
                    process = psutil.Process()
                    
                    # System-wide metrics
                    cpu_percent = psutil.cpu_percent(interval=0.1)
                    memory = psutil.virtual_memory()
                    
                    # Process-specific metrics
                    process_memory = process.memory_info()
                    
                    snapshot = ResourceUsageSnapshot(
                        timestamp=datetime.now(),
                        cpu_percent=cpu_percent,
                        memory_mb=memory.used / (1024 * 1024),
                        memory_percent=memory.percent,
                        active_threads=process.num_threads(),
                        open_files=len(process.open_files()),
                        network_connections=len(process.connections()),
                        concurrent_searches=len([m for m in self.concurrent_measurements 
                                               if (datetime.now() - m.start_time).total_seconds() < 1])
                    )
                    
                    with self._lock:
                        self.resource_snapshots.append(snapshot)
                    
                    await asyncio.sleep(1)  # Sample every second
                    
                except Exception as e:
                    self.logger.error(f"Resource monitoring error: {e}")
                    await asyncio.sleep(1)
        
        self._resource_monitor_task = asyncio.create_task(monitor_resources())
    
    async def _stop_resource_monitoring(self):
        """Stop resource monitoring."""
        self._monitoring_active = False
        if self._resource_monitor_task:
            self._resource_monitor_task.cancel()
            try:
                await self._resource_monitor_task
            except asyncio.CancelledError:
                pass
    
    def _analyze_resource_usage(self) -> Dict[str, Any]:
        """Analyze resource usage during concurrent testing."""
        if not self.resource_snapshots:
            return {"error": "No resource usage data available"}
        
        cpu_values = [s.cpu_percent for s in self.resource_snapshots]
        memory_values = [s.memory_mb for s in self.resource_snapshots]
        thread_values = [s.active_threads for s in self.resource_snapshots]
        
        return {
            "cpu_usage": {
                "avg_percent": statistics.mean(cpu_values),
                "max_percent": max(cpu_values),
                "min_percent": min(cpu_values)
            },
            "memory_usage": {
                "avg_mb": statistics.mean(memory_values),
                "max_mb": max(memory_values),
                "min_mb": min(memory_values)
            },
            "thread_usage": {
                "avg_threads": statistics.mean(thread_values),
                "max_threads": max(thread_values),
                "min_threads": min(thread_values)
            },
            "resource_efficiency": {
                "cpu_utilization_stable": max(cpu_values) - min(cpu_values) < 50,  # <50% variation
                "memory_growth_controlled": max(memory_values) / min(memory_values) < 2,  # <2x growth
                "thread_scaling_reasonable": max(thread_values) < 100  # <100 threads
            }
        }
    
    def _generate_concurrent_recommendations(
        self,
        performance_degradation: Dict[str, float],
        success_metrics: Dict[str, Any],
        resource_usage: Dict[str, Any]
    ) -> List[str]:
        """Generate recommendations based on concurrent test results."""
        recommendations = []
        
        # Performance degradation analysis
        avg_degradation = performance_degradation.get("avg_latency_ms_degradation_percent", 0)
        p95_degradation = performance_degradation.get("p95_latency_ms_degradation_percent", 0)
        
        if avg_degradation > 100:  # >100% degradation
            recommendations.append("Critical: Average latency more than doubled under concurrent load - investigate resource bottlenecks")
        elif avg_degradation > 50:  # >50% degradation
            recommendations.append("High: Significant performance degradation under load - optimize search algorithms or add caching")
        elif avg_degradation > 20:  # >20% degradation
            recommendations.append("Medium: Moderate performance impact - consider connection pooling and query optimization")
        
        if p95_degradation > 200:  # >200% P95 degradation
            recommendations.append("Critical: Worst-case performance severely impacted - implement circuit breakers and load shedding")
        
        # Success rate analysis
        success_rate = success_metrics.get("success_rate_percent", 100)
        if success_rate < 90:
            recommendations.append("Critical: Low success rate under concurrent load - investigate error handling and timeouts")
        elif success_rate < 95:
            recommendations.append("High: Some failures under load - improve error recovery and retry mechanisms")
        
        # Resource contention analysis
        contention_rate = success_metrics.get("resource_contention_rate_percent", 0)
        if contention_rate > 30:
            recommendations.append("High: Significant resource contention detected - implement connection pooling and async processing")
        elif contention_rate > 10:
            recommendations.append("Medium: Some resource contention - optimize database connections and query execution")
        
        # Resource usage analysis
        if "resource_efficiency" in resource_usage:
            efficiency = resource_usage["resource_efficiency"]
            
            if not efficiency.get("cpu_utilization_stable", True):
                recommendations.append("Medium: Unstable CPU usage - investigate CPU-intensive operations and optimize algorithms")
            
            if not efficiency.get("memory_growth_controlled", True):
                recommendations.append("High: Excessive memory growth - check for memory leaks and optimize data structures")
            
            if not efficiency.get("thread_scaling_reasonable", True):
                recommendations.append("High: Too many threads created - implement thread pooling and async patterns")
        
        # Throughput analysis
        throughput = success_metrics.get("successful_throughput_rps", 0)
        if throughput < 10:  # <10 successful requests per second
            recommendations.append("Medium: Low throughput under concurrent load - optimize search performance and scaling")
        
        # Default recommendation if no issues found
        if not recommendations:
            recommendations.append("Good: System handles concurrent load well - monitor for scaling and consider performance optimizations")
        
        return recommendations
    
    async def run_scaling_test(
        self,
        max_users: int = 50,
        step_size: int = 5,
        step_duration: int = 30,
        service_type: str = "enhanced"
    ) -> Dict[str, Any]:
        """Run scaling test with gradually increasing concurrent users."""
        
        self.logger.info(f"Running scaling test: 1 to {max_users} users, {step_size} user steps, {step_duration}s per step")
        
        scaling_results = []
        
        for concurrent_users in range(step_size, max_users + 1, step_size):
            self.logger.info(f"Testing with {concurrent_users} concurrent users...")
            
            try:
                result = await self.run_concurrent_search_test(
                    concurrent_users=concurrent_users,
                    duration_seconds=step_duration,
                    service_type=service_type,
                    query_pattern="mixed"
                )
                
                # Extract key metrics for scaling analysis
                scaling_point = {
                    "concurrent_users": concurrent_users,
                    "avg_latency_ms": result.concurrent_performance.get("avg_latency_ms", 0),
                    "p95_latency_ms": result.concurrent_performance.get("p95_latency_ms", 0),
                    "success_rate_percent": result.success_metrics.get("success_rate_percent", 0),
                    "throughput_rps": result.success_metrics.get("successful_throughput_rps", 0),
                    "resource_contention_percent": result.success_metrics.get("resource_contention_rate_percent", 0)
                }
                
                scaling_results.append(scaling_point)
                
                # Check if system is failing under load
                if scaling_point["success_rate_percent"] < 80:
                    self.logger.warning(f"Success rate dropped to {scaling_point['success_rate_percent']:.1f}% at {concurrent_users} users")
                    break
                
            except Exception as e:
                self.logger.error(f"Scaling test failed at {concurrent_users} users: {e}")
                break
        
        # Analyze scaling characteristics
        scaling_analysis = self._analyze_scaling_results(scaling_results)
        
        return {
            "scaling_results": scaling_results,
            "scaling_analysis": scaling_analysis,
            "max_tested_users": len(scaling_results) * step_size,
            "recommended_max_users": scaling_analysis.get("recommended_max_users", step_size)
        }
    
    def _analyze_scaling_results(self, scaling_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze scaling test results to determine system limits."""
        
        if not scaling_results:
            return {"error": "No scaling results to analyze"}
        
        # Find performance degradation points
        baseline_latency = scaling_results[0]["avg_latency_ms"]
        baseline_throughput = scaling_results[0]["throughput_rps"]
        
        degradation_points = []
        
        for result in scaling_results:
            users = result["concurrent_users"]
            latency_increase = ((result["avg_latency_ms"] - baseline_latency) / baseline_latency) * 100
            throughput_efficiency = result["throughput_rps"] / (users * (baseline_throughput / scaling_results[0]["concurrent_users"]))
            
            if latency_increase > 100:  # >100% latency increase
                degradation_points.append({"users": users, "issue": "high_latency", "severity": "critical"})
            elif result["success_rate_percent"] < 95:  # <95% success rate
                degradation_points.append({"users": users, "issue": "low_success_rate", "severity": "critical"})
            elif throughput_efficiency < 0.7:  # <70% throughput efficiency
                degradation_points.append({"users": users, "issue": "poor_scaling", "severity": "warning"})
        
        # Determine recommended maximum users
        if degradation_points:
            first_critical = next((p for p in degradation_points if p["severity"] == "critical"), None)
            recommended_max = first_critical["users"] - scaling_results[0]["concurrent_users"] if first_critical else scaling_results[-1]["concurrent_users"]
        else:
            recommended_max = scaling_results[-1]["concurrent_users"]
        
        return {
            "degradation_points": degradation_points,
            "recommended_max_users": max(recommended_max, scaling_results[0]["concurrent_users"]),
            "scaling_efficiency": self._calculate_scaling_efficiency(scaling_results),
            "performance_characteristics": self._characterize_scaling_performance(scaling_results)
        }
    
    def _calculate_scaling_efficiency(self, scaling_results: List[Dict[str, Any]]) -> Dict[str, float]:
        """Calculate how efficiently the system scales with concurrent users."""
        
        if len(scaling_results) < 2:
            return {"error": "Insufficient data for scaling efficiency calculation"}
        
        # Linear scaling would maintain constant per-user throughput
        baseline = scaling_results[0]
        final = scaling_results[-1]
        
        expected_throughput = baseline["throughput_rps"] * (final["concurrent_users"] / baseline["concurrent_users"])
        actual_throughput = final["throughput_rps"]
        
        throughput_efficiency = (actual_throughput / expected_throughput) * 100
        
        # Latency scaling (ideally should remain constant)
        latency_degradation = ((final["avg_latency_ms"] - baseline["avg_latency_ms"]) / baseline["avg_latency_ms"]) * 100
        
        return {
            "throughput_efficiency_percent": throughput_efficiency,
            "latency_degradation_percent": latency_degradation,
            "overall_scaling_score": max(0, 100 - abs(100 - throughput_efficiency) - max(0, latency_degradation))
        }
    
    def _characterize_scaling_performance(self, scaling_results: List[Dict[str, Any]]) -> str:
        """Characterize the scaling performance pattern."""
        
        if len(scaling_results) < 3:
            return "insufficient_data"
        
        # Analyze throughput trend
        throughputs = [r["throughput_rps"] for r in scaling_results]
        users = [r["concurrent_users"] for r in scaling_results]
        
        # Simple trend analysis
        throughput_growth = (throughputs[-1] - throughputs[0]) / throughputs[0]
        user_growth = (users[-1] - users[0]) / users[0]
        
        scaling_ratio = throughput_growth / user_growth
        
        if scaling_ratio > 0.8:
            return "linear_scaling"  # Good scaling
        elif scaling_ratio > 0.5:
            return "sublinear_scaling"  # Acceptable scaling
        elif scaling_ratio > 0.2:
            return "poor_scaling"  # Poor scaling
        else:
            return "degraded_scaling"  # System struggling
    
    def generate_concurrent_performance_report(self) -> Dict[str, Any]:
        """Generate comprehensive concurrent performance report."""
        
        if not self.concurrent_measurements:
            return {"error": "No concurrent performance data available"}
        
        # Group measurements by concurrent user count
        user_groups = {}
        for measurement in self.concurrent_measurements:
            users = measurement.concurrent_users
            if users not in user_groups:
                user_groups[users] = []
            user_groups[users].append(measurement)
        
        # Analyze each user group
        user_analysis = {}
        for users, measurements in user_groups.items():
            successful = [m for m in measurements if m.success]
            
            if successful:
                latencies = [m.latency_ms for m in successful]
                user_analysis[users] = {
                    "total_requests": len(measurements),
                    "successful_requests": len(successful),
                    "success_rate_percent": (len(successful) / len(measurements)) * 100,
                    "avg_latency_ms": statistics.mean(latencies),
                    "p95_latency_ms": sorted(latencies)[int(0.95 * len(latencies))],
                    "resource_contention_rate": (len([m for m in measurements if m.resource_contention]) / len(measurements)) * 100
                }
        
        return {
            "report_timestamp": datetime.now().isoformat(),
            "total_measurements": len(self.concurrent_measurements),
            "user_groups_tested": list(user_groups.keys()),
            "user_analysis": user_analysis,
            "resource_usage_summary": self._analyze_resource_usage(),
            "overall_recommendations": self._generate_overall_recommendations(user_analysis)
        }
    
    def _generate_overall_recommendations(self, user_analysis: Dict[int, Dict[str, Any]]) -> List[str]:
        """Generate overall recommendations based on all concurrent tests."""
        recommendations = []
        
        if not user_analysis:
            return ["No concurrent test data available for analysis"]
        
        # Find performance trends across user counts
        user_counts = sorted(user_analysis.keys())
        
        if len(user_counts) > 1:
            # Compare lowest and highest user counts
            low_users = user_counts[0]
            high_users = user_counts[-1]
            
            low_perf = user_analysis[low_users]
            high_perf = user_analysis[high_users]
            
            # Success rate degradation
            success_degradation = low_perf["success_rate_percent"] - high_perf["success_rate_percent"]
            if success_degradation > 10:
                recommendations.append(f"High: Success rate drops {success_degradation:.1f}% under high concurrent load - improve error handling")
            
            # Latency degradation
            latency_increase = ((high_perf["avg_latency_ms"] - low_perf["avg_latency_ms"]) / low_perf["avg_latency_ms"]) * 100
            if latency_increase > 100:
                recommendations.append(f"Critical: Latency increases {latency_increase:.1f}% under load - optimize search algorithms")
            elif latency_increase > 50:
                recommendations.append(f"High: Latency increases {latency_increase:.1f}% under load - consider caching and optimization")
            
            # Resource contention
            max_contention = max(perf["resource_contention_rate"] for perf in user_analysis.values())
            if max_contention > 25:
                recommendations.append(f"High: Resource contention reaches {max_contention:.1f}% - implement connection pooling")
        
        # General recommendations
        recommendations.append("Monitor concurrent performance regularly and set up alerting for degradation")
        recommendations.append("Consider implementing auto-scaling based on concurrent load patterns")
        
        return recommendations
    
    async def save_results(self, filepath: str) -> None:
        """Save concurrent test results to file."""
        results = {
            "test_metadata": {
                "timestamp": datetime.now().isoformat(),
                "total_measurements": len(self.concurrent_measurements),
                "resource_snapshots": len(self.resource_snapshots)
            },
            "concurrent_measurements": [
                {
                    "user_id": m.user_id,
                    "query_text": m.query_text,
                    "query_type": m.query_type,
                    "search_service": m.search_service,
                    "start_time": m.start_time.isoformat(),
                    "end_time": m.end_time.isoformat(),
                    "latency_ms": m.latency_ms,
                    "result_count": m.result_count,
                    "success": m.success,
                    "error_message": m.error_message,
                    "concurrent_users": m.concurrent_users,
                    "queue_wait_time_ms": m.queue_wait_time_ms,
                    "resource_contention": m.resource_contention
                }
                for m in self.concurrent_measurements
            ],
            "resource_snapshots": [
                {
                    "timestamp": s.timestamp.isoformat(),
                    "cpu_percent": s.cpu_percent,
                    "memory_mb": s.memory_mb,
                    "memory_percent": s.memory_percent,
                    "active_threads": s.active_threads,
                    "open_files": s.open_files,
                    "network_connections": s.network_connections,
                    "concurrent_searches": s.concurrent_searches
                }
                for s in self.resource_snapshots
            ],
            "performance_report": self.generate_concurrent_performance_report()
        }
        
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        with open(filepath, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        self.logger.info(f"Concurrent test results saved to {filepath}")


async def run_comprehensive_concurrent_tests(
    vector_store: VectorStore,
    output_file: Optional[str] = None,
    service_types: List[str] = None,
    include_scaling_test: bool = True
) -> Dict[str, Any]:
    """Run comprehensive concurrent search performance tests."""
    
    if service_types is None:
        service_types = ["simple", "enhanced"]
    
    tester = ConcurrentSearchTester(vector_store)
    
    print("=" * 80)
    print("⚡ CONCURRENT SEARCH PERFORMANCE TESTING SUITE")
    print("=" * 80)
    print(f"📅 Started: {datetime.now().isoformat()}")
    print(f"🎯 Services: {', '.join(service_types)}")
    print(f"🔄 Concurrent Patterns: mixed, uniform, burst")
    print()
    
    results = {
        "test_start": datetime.now(),
        "concurrent_tests": {},
        "scaling_tests": {},
        "performance_report": {}
    }
    
    # Run concurrent tests for each service
    for service_type in service_types:
        print(f"⚡ Testing {service_type} service concurrent performance...")
        
        service_results = {}
        
        # Test different concurrent user levels
        user_levels = [5, 10, 20]
        
        for users in user_levels:
            print(f"   Testing {users} concurrent users...")
            
            try:
                result = await tester.run_concurrent_search_test(
                    concurrent_users=users,
                    duration_seconds=30,  # Shorter duration for multiple tests
                    service_type=service_type,
                    query_pattern="mixed"
                )
                
                service_results[f"{users}_users"] = {
                    "test_config": result.test_config,
                    "baseline_performance": result.baseline_performance,
                    "concurrent_performance": result.concurrent_performance,
                    "performance_degradation": result.performance_degradation,
                    "success_metrics": result.success_metrics,
                    "recommendations": result.recommendations
                }
                
                # Print key results
                perf = result.concurrent_performance
                success = result.success_metrics
                degradation = result.performance_degradation
                
                print(f"      ✅ Results: {success['success_rate_percent']:.1f}% success, "
                      f"{perf['avg_latency_ms']:.1f}ms avg latency")
                
                if degradation.get("avg_latency_ms_degradation_percent"):
                    print(f"      📊 Performance: {degradation['avg_latency_ms_degradation_percent']:.1f}% latency increase")
                
            except Exception as e:
                print(f"      ❌ Failed: {e}")
                service_results[f"{users}_users"] = {"error": str(e)}
        
        results["concurrent_tests"][service_type] = service_results
        print()
    
    # Run scaling tests if requested
    if include_scaling_test:
        for service_type in service_types:
            print(f"📈 Running scaling test for {service_type} service...")
            
            try:
                scaling_result = await tester.run_scaling_test(
                    max_users=30,  # Conservative for testing
                    step_size=5,
                    step_duration=20,
                    service_type=service_type
                )
                
                results["scaling_tests"][service_type] = scaling_result
                
                # Print scaling results
                analysis = scaling_result["scaling_analysis"]
                print(f"   📊 Max tested: {scaling_result['max_tested_users']} users")
                print(f"   🎯 Recommended max: {scaling_result['recommended_max_users']} users")
                
                if "scaling_efficiency" in analysis:
                    efficiency = analysis["scaling_efficiency"]
                    print(f"   ⚡ Scaling efficiency: {efficiency.get('overall_scaling_score', 0):.1f}%")
                
            except Exception as e:
                print(f"   ❌ Scaling test failed: {e}")
                results["scaling_tests"][service_type] = {"error": str(e)}
            
            print()
    
    # Generate final performance report
    results["performance_report"] = tester.generate_concurrent_performance_report()
    results["test_end"] = datetime.now()
    results["total_duration"] = (results["test_end"] - results["test_start"]).total_seconds()
    
    # Save results if requested
    if output_file:
        await tester.save_results(output_file)
        print(f"📄 Detailed results saved to: {output_file}")
    
    # Print summary
    print("=" * 80)
    print("📊 CONCURRENT SEARCH PERFORMANCE SUMMARY")
    print("=" * 80)
    
    report = results["performance_report"]
    if "user_analysis" in report:
        print("🔍 Concurrent Performance by User Count:")
        for users, analysis in sorted(report["user_analysis"].items()):
            print(f"   {users} users: {analysis['success_rate_percent']:.1f}% success, "
                  f"{analysis['avg_latency_ms']:.1f}ms avg latency")
    
    if "overall_recommendations" in report:
        print(f"\n💡 Key Recommendations:")
        for i, rec in enumerate(report["overall_recommendations"][:3], 1):
            print(f"   {i}. {rec}")
    
    print("=" * 80)
    
    return results


def main():
    """Main function for running concurrent search tests."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Run Concurrent Search Performance Tests')
    parser.add_argument('--output', type=str, help='Output file for detailed results')
    parser.add_argument('--services', nargs='+', default=['simple', 'enhanced'],
                       choices=['simple', 'enhanced'], help='Search services to test')
    parser.add_argument('--no-scaling-test', action='store_true', help='Skip scaling tests')
    parser.add_argument('--max-users', type=int, default=30, help='Maximum concurrent users for scaling test')
    
    args = parser.parse_args()
    
    # This would need to be connected to actual vector store in real usage
    print("⚠️  Note: This test requires a configured vector store instance")
    print("   Please integrate with your vector store setup for actual testing")
    
    return 0


if __name__ == "__main__":
    exit(main())