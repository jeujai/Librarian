#!/usr/bin/env python3
"""
Search Latency Measurement and Performance Testing Suite

This module provides comprehensive search performance testing capabilities including:
- Search latency measurement across different query types
- Baseline performance establishment
- Bottleneck identification and analysis
- Performance regression detection
- Load testing for search operations

Validates: Requirement 2.1 - Search Service Performance Optimization
"""

import os
import sys
import asyncio
import time
import json
import statistics
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from concurrent.futures import ThreadPoolExecutor
import threading
import uuid

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
class SearchLatencyMetric:
    """Individual search latency measurement."""
    query_text: str
    query_type: str
    search_service: str  # 'simple' or 'complex'
    latency_ms: float
    result_count: int
    timestamp: datetime
    success: bool
    error_message: Optional[str] = None
    
    # Additional performance metrics
    vector_search_time_ms: Optional[float] = None
    result_processing_time_ms: Optional[float] = None
    cache_hit: bool = False


@dataclass
class SearchPerformanceBaseline:
    """Baseline performance metrics for search operations."""
    test_timestamp: datetime
    service_type: str
    
    # Latency metrics (milliseconds)
    avg_latency_ms: float
    median_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    min_latency_ms: float
    max_latency_ms: float
    
    # Throughput metrics
    queries_per_second: float
    concurrent_queries_supported: int
    
    # Quality metrics
    success_rate_percent: float
    avg_result_count: float
    
    # Resource usage
    peak_memory_mb: Optional[float] = None
    avg_cpu_percent: Optional[float] = None


@dataclass
class SearchBottleneck:
    """Identified performance bottleneck."""
    component: str  # 'vector_search', 'result_processing', 'network', etc.
    description: str
    impact_level: str  # 'low', 'medium', 'high', 'critical'
    avg_time_ms: float
    percentage_of_total: float
    recommendations: List[str]


class SearchLatencyTester:
    """Comprehensive search latency testing and analysis."""
    
    def __init__(self, vector_store: VectorStore, config: Optional[Dict] = None):
        self.vector_store = vector_store
        self.config = config or {}
        self.logger = get_logger("search_latency_tester")
        
        # Initialize search services
        self.simple_service = SimpleSemanticSearchService(vector_store)
        self.enhanced_service = EnhancedSemanticSearchService(vector_store, config)
        
        # Test data storage
        self.measurements: List[SearchLatencyMetric] = []
        self.baselines: Dict[str, SearchPerformanceBaseline] = {}
        self.bottlenecks: List[SearchBottleneck] = []
        
        # Test configuration
        self.test_queries = self._generate_test_queries()
        
        # Thread safety
        self._lock = threading.Lock()
        
        self.logger.info("Search latency tester initialized")
    
    def _generate_test_queries(self) -> List[Dict[str, Any]]:
        """Generate diverse test queries for comprehensive testing."""
        return [
            # Simple queries
            {
                "query": "machine learning",
                "type": "simple_keyword",
                "description": "Basic keyword search",
                "expected_results": 5
            },
            {
                "query": "artificial intelligence",
                "type": "simple_keyword", 
                "description": "Common AI term",
                "expected_results": 5
            },
            
            # Complex queries
            {
                "query": "How does neural network backpropagation work?",
                "type": "question",
                "description": "Technical question",
                "expected_results": 3
            },
            {
                "query": "Compare supervised and unsupervised learning algorithms",
                "type": "comparative",
                "description": "Comparative analysis query",
                "expected_results": 4
            },
            
            # Long queries
            {
                "query": "Explain the mathematical foundations of deep learning including gradient descent optimization, activation functions, and regularization techniques used in modern neural network architectures",
                "type": "complex_technical",
                "description": "Long technical query",
                "expected_results": 6
            },
            
            # Short queries
            {
                "query": "AI",
                "type": "short_keyword",
                "description": "Very short query",
                "expected_results": 10
            },
            {
                "query": "ML",
                "type": "abbreviation",
                "description": "Abbreviation search",
                "expected_results": 8
            },
            
            # Domain-specific queries
            {
                "query": "transformer architecture attention mechanism",
                "type": "technical_specific",
                "description": "Specific technical terms",
                "expected_results": 4
            },
            {
                "query": "data preprocessing feature engineering",
                "type": "workflow",
                "description": "Process-oriented query",
                "expected_results": 5
            },
            
            # Edge cases
            {
                "query": "xyz123nonexistentterm",
                "type": "no_results",
                "description": "Query with no expected results",
                "expected_results": 0
            },
            {
                "query": "the and or but",
                "type": "stop_words",
                "description": "Common stop words",
                "expected_results": 0
            }
        ]
    
    async def measure_search_latency(
        self, 
        query: str, 
        query_type: str,
        service_type: str = "enhanced",
        iterations: int = 1
    ) -> List[SearchLatencyMetric]:
        """Measure search latency for a specific query."""
        measurements = []
        
        for i in range(iterations):
            start_time = time.perf_counter()
            
            try:
                if service_type == "simple":
                    # Test simple search service
                    request = SimpleSearchRequest(
                        query=query,
                        session_id=str(uuid.uuid4()),
                        top_k=10
                    )
                    
                    vector_search_start = time.perf_counter()
                    response = await self.simple_service.search(request)
                    vector_search_time = (time.perf_counter() - vector_search_start) * 1000
                    
                    end_time = time.perf_counter()
                    latency_ms = (end_time - start_time) * 1000
                    
                    measurement = SearchLatencyMetric(
                        query_text=query,
                        query_type=query_type,
                        search_service="simple",
                        latency_ms=latency_ms,
                        result_count=len(response.results),
                        timestamp=datetime.now(),
                        success=True,
                        vector_search_time_ms=vector_search_time,
                        result_processing_time_ms=latency_ms - vector_search_time
                    )
                
                else:
                    # Test enhanced search service
                    request = SearchRequest(
                        query=query,
                        session_id=str(uuid.uuid4()),
                        top_k=10
                    )
                    
                    vector_search_start = time.perf_counter()
                    response = await self.enhanced_service.search(request)
                    vector_search_time = (time.perf_counter() - vector_search_start) * 1000
                    
                    end_time = time.perf_counter()
                    latency_ms = (end_time - start_time) * 1000
                    
                    measurement = SearchLatencyMetric(
                        query_text=query,
                        query_type=query_type,
                        search_service="enhanced",
                        latency_ms=latency_ms,
                        result_count=len(response.results) if hasattr(response, 'results') else 0,
                        timestamp=datetime.now(),
                        success=True,
                        vector_search_time_ms=vector_search_time,
                        result_processing_time_ms=latency_ms - vector_search_time
                    )
                
                measurements.append(measurement)
                
            except Exception as e:
                end_time = time.perf_counter()
                latency_ms = (end_time - start_time) * 1000
                
                measurement = SearchLatencyMetric(
                    query_text=query,
                    query_type=query_type,
                    search_service=service_type,
                    latency_ms=latency_ms,
                    result_count=0,
                    timestamp=datetime.now(),
                    success=False,
                    error_message=str(e)
                )
                measurements.append(measurement)
                
                self.logger.error(f"Search failed for query '{query}': {e}")
        
        with self._lock:
            self.measurements.extend(measurements)
        
        return measurements
    
    async def establish_performance_baseline(
        self, 
        service_type: str = "enhanced",
        iterations_per_query: int = 10
    ) -> SearchPerformanceBaseline:
        """Establish baseline performance metrics."""
        self.logger.info(f"Establishing performance baseline for {service_type} service")
        
        all_measurements = []
        
        # Test each query type multiple times
        for query_data in self.test_queries:
            query = query_data["query"]
            query_type = query_data["type"]
            
            measurements = await self.measure_search_latency(
                query, query_type, service_type, iterations_per_query
            )
            all_measurements.extend(measurements)
        
        # Calculate baseline metrics
        successful_measurements = [m for m in all_measurements if m.success]
        
        if not successful_measurements:
            raise ValueError("No successful measurements to establish baseline")
        
        latencies = [m.latency_ms for m in successful_measurements]
        result_counts = [m.result_count for m in successful_measurements]
        
        # Calculate latency statistics
        avg_latency = statistics.mean(latencies)
        median_latency = statistics.median(latencies)
        min_latency = min(latencies)
        max_latency = max(latencies)
        
        # Calculate percentiles
        sorted_latencies = sorted(latencies)
        p95_latency = sorted_latencies[int(0.95 * len(sorted_latencies))]
        p99_latency = sorted_latencies[int(0.99 * len(sorted_latencies))]
        
        # Calculate throughput (approximate)
        total_time_seconds = sum(latencies) / 1000
        queries_per_second = len(successful_measurements) / max(total_time_seconds, 0.001)
        
        # Calculate success rate
        success_rate = (len(successful_measurements) / len(all_measurements)) * 100
        
        # Calculate average result count
        avg_result_count = statistics.mean(result_counts) if result_counts else 0
        
        baseline = SearchPerformanceBaseline(
            test_timestamp=datetime.now(),
            service_type=service_type,
            avg_latency_ms=avg_latency,
            median_latency_ms=median_latency,
            p95_latency_ms=p95_latency,
            p99_latency_ms=p99_latency,
            min_latency_ms=min_latency,
            max_latency_ms=max_latency,
            queries_per_second=queries_per_second,
            concurrent_queries_supported=1,  # Will be measured separately
            success_rate_percent=success_rate,
            avg_result_count=avg_result_count
        )
        
        self.baselines[service_type] = baseline
        
        self.logger.info(f"Baseline established: {avg_latency:.1f}ms avg, {p95_latency:.1f}ms p95")
        return baseline
    
    async def identify_bottlenecks(self, service_type: str = "enhanced") -> List[SearchBottleneck]:
        """Identify performance bottlenecks in search operations."""
        self.logger.info(f"Identifying bottlenecks for {service_type} service")
        
        # Get recent measurements for analysis
        recent_measurements = [
            m for m in self.measurements 
            if m.search_service == service_type and m.success
        ]
        
        if not recent_measurements:
            self.logger.warning("No measurements available for bottleneck analysis")
            return []
        
        bottlenecks = []
        
        # Analyze vector search time
        vector_times = [
            m.vector_search_time_ms for m in recent_measurements 
            if m.vector_search_time_ms is not None
        ]
        
        if vector_times:
            avg_vector_time = statistics.mean(vector_times)
            total_avg_time = statistics.mean([m.latency_ms for m in recent_measurements])
            vector_percentage = (avg_vector_time / total_avg_time) * 100
            
            if vector_percentage > 70:  # Vector search takes >70% of time
                bottlenecks.append(SearchBottleneck(
                    component="vector_search",
                    description="Vector search operations are consuming majority of query time",
                    impact_level="high" if vector_percentage > 85 else "medium",
                    avg_time_ms=avg_vector_time,
                    percentage_of_total=vector_percentage,
                    recommendations=[
                        "Optimize vector database indexing",
                        "Consider reducing vector dimensions",
                        "Implement vector caching for common queries",
                        "Evaluate vector database configuration"
                    ]
                ))
        
        # Analyze result processing time
        processing_times = [
            m.result_processing_time_ms for m in recent_measurements 
            if m.result_processing_time_ms is not None
        ]
        
        if processing_times:
            avg_processing_time = statistics.mean(processing_times)
            total_avg_time = statistics.mean([m.latency_ms for m in recent_measurements])
            processing_percentage = (avg_processing_time / total_avg_time) * 100
            
            if processing_percentage > 30:  # Result processing takes >30% of time
                bottlenecks.append(SearchBottleneck(
                    component="result_processing",
                    description="Result processing and formatting is taking significant time",
                    impact_level="medium" if processing_percentage > 50 else "low",
                    avg_time_ms=avg_processing_time,
                    percentage_of_total=processing_percentage,
                    recommendations=[
                        "Optimize result serialization",
                        "Reduce result metadata processing",
                        "Implement result caching",
                        "Streamline response formatting"
                    ]
                ))
        
        # Analyze query complexity impact
        query_type_performance = {}
        for measurement in recent_measurements:
            if measurement.query_type not in query_type_performance:
                query_type_performance[measurement.query_type] = []
            query_type_performance[measurement.query_type].append(measurement.latency_ms)
        
        # Find slow query types
        for query_type, latencies in query_type_performance.items():
            avg_latency = statistics.mean(latencies)
            overall_avg = statistics.mean([m.latency_ms for m in recent_measurements])
            
            if avg_latency > overall_avg * 1.5:  # 50% slower than average
                bottlenecks.append(SearchBottleneck(
                    component="query_complexity",
                    description=f"Query type '{query_type}' shows significantly higher latency",
                    impact_level="medium",
                    avg_time_ms=avg_latency,
                    percentage_of_total=(avg_latency / overall_avg) * 100,
                    recommendations=[
                        f"Optimize handling of {query_type} queries",
                        "Consider query preprocessing for complex queries",
                        "Implement query-specific caching strategies"
                    ]
                ))
        
        # Analyze error rate impact
        error_measurements = [m for m in self.measurements if not m.success]
        if error_measurements:
            error_rate = len(error_measurements) / len(self.measurements) * 100
            
            if error_rate > 5:  # >5% error rate
                bottlenecks.append(SearchBottleneck(
                    component="error_handling",
                    description=f"High error rate ({error_rate:.1f}%) impacting overall performance",
                    impact_level="high" if error_rate > 15 else "medium",
                    avg_time_ms=0,  # Errors don't contribute to successful latency
                    percentage_of_total=error_rate,
                    recommendations=[
                        "Investigate and fix search errors",
                        "Improve error handling and recovery",
                        "Add input validation and sanitization",
                        "Monitor and alert on error patterns"
                    ]
                ))
        
        self.bottlenecks = bottlenecks
        self.logger.info(f"Identified {len(bottlenecks)} potential bottlenecks")
        return bottlenecks
    
    async def run_concurrent_load_test(
        self, 
        concurrent_users: int = 10,
        duration_seconds: int = 60,
        service_type: str = "enhanced"
    ) -> Dict[str, Any]:
        """Run concurrent load test to measure performance under load."""
        self.logger.info(f"Running concurrent load test: {concurrent_users} users, {duration_seconds}s")
        
        # Prepare test data
        test_start = time.time()
        test_end = test_start + duration_seconds
        
        # Results storage
        concurrent_measurements = []
        measurement_lock = threading.Lock()
        
        async def user_simulation(user_id: int):
            """Simulate a single user's search behavior."""
            user_measurements = []
            
            while time.time() < test_end:
                # Select random query
                query_data = self.test_queries[user_id % len(self.test_queries)]
                
                try:
                    measurements = await self.measure_search_latency(
                        query_data["query"],
                        query_data["type"],
                        service_type,
                        iterations=1
                    )
                    user_measurements.extend(measurements)
                    
                    # Small delay between queries
                    await asyncio.sleep(0.1)
                    
                except Exception as e:
                    self.logger.error(f"User {user_id} simulation error: {e}")
            
            with measurement_lock:
                concurrent_measurements.extend(user_measurements)
        
        # Run concurrent users
        tasks = [user_simulation(i) for i in range(concurrent_users)]
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Analyze results
        successful_measurements = [m for m in concurrent_measurements if m.success]
        
        if not successful_measurements:
            return {"error": "No successful measurements in load test"}
        
        latencies = [m.latency_ms for m in successful_measurements]
        
        # Calculate load test metrics
        total_requests = len(concurrent_measurements)
        successful_requests = len(successful_measurements)
        failed_requests = total_requests - successful_requests
        
        actual_duration = time.time() - test_start
        requests_per_second = total_requests / actual_duration
        
        # Latency statistics under load
        avg_latency_under_load = statistics.mean(latencies)
        p95_latency_under_load = sorted(latencies)[int(0.95 * len(latencies))]
        p99_latency_under_load = sorted(latencies)[int(0.99 * len(latencies))]
        
        # Compare with baseline
        baseline = self.baselines.get(service_type)
        performance_degradation = {}
        
        if baseline:
            performance_degradation = {
                "avg_latency_increase_percent": ((avg_latency_under_load - baseline.avg_latency_ms) / baseline.avg_latency_ms) * 100,
                "p95_latency_increase_percent": ((p95_latency_under_load - baseline.p95_latency_ms) / baseline.p95_latency_ms) * 100,
                "throughput_change_percent": ((requests_per_second - baseline.queries_per_second) / baseline.queries_per_second) * 100
            }
        
        return {
            "test_config": {
                "concurrent_users": concurrent_users,
                "duration_seconds": duration_seconds,
                "service_type": service_type
            },
            "results": {
                "total_requests": total_requests,
                "successful_requests": successful_requests,
                "failed_requests": failed_requests,
                "success_rate_percent": (successful_requests / total_requests) * 100,
                "requests_per_second": requests_per_second,
                "avg_latency_ms": avg_latency_under_load,
                "p95_latency_ms": p95_latency_under_load,
                "p99_latency_ms": p99_latency_under_load,
                "min_latency_ms": min(latencies),
                "max_latency_ms": max(latencies)
            },
            "performance_degradation": performance_degradation,
            "concurrent_performance_supported": successful_requests > (total_requests * 0.95)  # >95% success rate
        }
    
    def generate_performance_report(self) -> Dict[str, Any]:
        """Generate comprehensive performance analysis report."""
        report = {
            "report_timestamp": datetime.now().isoformat(),
            "test_summary": {
                "total_measurements": len(self.measurements),
                "successful_measurements": len([m for m in self.measurements if m.success]),
                "services_tested": list(set(m.search_service for m in self.measurements)),
                "query_types_tested": list(set(m.query_type for m in self.measurements))
            },
            "baselines": {
                service: asdict(baseline) for service, baseline in self.baselines.items()
            },
            "bottlenecks": [
                {
                    "component": b.component,
                    "description": b.description,
                    "impact_level": b.impact_level,
                    "avg_time_ms": b.avg_time_ms,
                    "percentage_of_total": b.percentage_of_total,
                    "recommendations": b.recommendations
                }
                for b in self.bottlenecks
            ],
            "performance_analysis": self._analyze_performance_trends(),
            "recommendations": self._generate_performance_recommendations()
        }
        
        return report
    
    def _analyze_performance_trends(self) -> Dict[str, Any]:
        """Analyze performance trends from measurements."""
        if not self.measurements:
            return {"error": "No measurements available for trend analysis"}
        
        # Group measurements by service type
        service_analysis = {}
        
        for service_type in set(m.search_service for m in self.measurements):
            service_measurements = [m for m in self.measurements if m.search_service == service_type and m.success]
            
            if not service_measurements:
                continue
            
            latencies = [m.latency_ms for m in service_measurements]
            
            service_analysis[service_type] = {
                "measurement_count": len(service_measurements),
                "avg_latency_ms": statistics.mean(latencies),
                "median_latency_ms": statistics.median(latencies),
                "std_dev_ms": statistics.stdev(latencies) if len(latencies) > 1 else 0,
                "min_latency_ms": min(latencies),
                "max_latency_ms": max(latencies),
                "success_rate_percent": (len(service_measurements) / len([m for m in self.measurements if m.search_service == service_type])) * 100
            }
        
        # Query type analysis
        query_type_analysis = {}
        
        for query_type in set(m.query_type for m in self.measurements):
            type_measurements = [m for m in self.measurements if m.query_type == query_type and m.success]
            
            if not type_measurements:
                continue
            
            latencies = [m.latency_ms for m in type_measurements]
            
            query_type_analysis[query_type] = {
                "measurement_count": len(type_measurements),
                "avg_latency_ms": statistics.mean(latencies),
                "avg_result_count": statistics.mean([m.result_count for m in type_measurements])
            }
        
        return {
            "service_analysis": service_analysis,
            "query_type_analysis": query_type_analysis,
            "overall_statistics": {
                "total_queries_tested": len(self.measurements),
                "overall_success_rate": (len([m for m in self.measurements if m.success]) / len(self.measurements)) * 100,
                "avg_latency_all_services": statistics.mean([m.latency_ms for m in self.measurements if m.success]) if any(m.success for m in self.measurements) else 0
            }
        }
    
    def _generate_performance_recommendations(self) -> List[Dict[str, Any]]:
        """Generate performance optimization recommendations."""
        recommendations = []
        
        # Analyze baselines for recommendations
        for service_type, baseline in self.baselines.items():
            if baseline.avg_latency_ms > 500:  # >500ms average
                recommendations.append({
                    "priority": "high",
                    "category": "latency",
                    "service": service_type,
                    "issue": f"High average latency ({baseline.avg_latency_ms:.1f}ms)",
                    "recommendation": "Optimize search algorithms and consider caching strategies",
                    "target": "Reduce average latency to <300ms"
                })
            
            if baseline.p95_latency_ms > 1000:  # >1s p95
                recommendations.append({
                    "priority": "medium",
                    "category": "latency_consistency",
                    "service": service_type,
                    "issue": f"High P95 latency ({baseline.p95_latency_ms:.1f}ms)",
                    "recommendation": "Investigate and optimize worst-case performance scenarios",
                    "target": "Reduce P95 latency to <800ms"
                })
            
            if baseline.success_rate_percent < 95:
                recommendations.append({
                    "priority": "critical",
                    "category": "reliability",
                    "service": service_type,
                    "issue": f"Low success rate ({baseline.success_rate_percent:.1f}%)",
                    "recommendation": "Investigate and fix search failures, improve error handling",
                    "target": "Achieve >98% success rate"
                })
        
        # Bottleneck-based recommendations
        for bottleneck in self.bottlenecks:
            if bottleneck.impact_level in ["high", "critical"]:
                recommendations.append({
                    "priority": bottleneck.impact_level,
                    "category": "bottleneck",
                    "service": "all",
                    "issue": bottleneck.description,
                    "recommendation": bottleneck.recommendations[0] if bottleneck.recommendations else "Investigate and optimize",
                    "target": f"Reduce {bottleneck.component} impact to <20% of total time"
                })
        
        # General recommendations if no specific issues found
        if not recommendations:
            recommendations.append({
                "priority": "low",
                "category": "optimization",
                "service": "all",
                "issue": "No critical performance issues detected",
                "recommendation": "Continue monitoring and consider advanced optimizations like result caching and query preprocessing",
                "target": "Maintain current performance levels"
            })
        
        return recommendations
    
    async def save_results(self, filepath: str) -> None:
        """Save test results to file."""
        results = {
            "test_metadata": {
                "timestamp": datetime.now().isoformat(),
                "total_measurements": len(self.measurements),
                "test_queries": self.test_queries
            },
            "measurements": [
                {
                    "query_text": m.query_text,
                    "query_type": m.query_type,
                    "search_service": m.search_service,
                    "latency_ms": m.latency_ms,
                    "result_count": m.result_count,
                    "timestamp": m.timestamp.isoformat(),
                    "success": m.success,
                    "error_message": m.error_message,
                    "vector_search_time_ms": m.vector_search_time_ms,
                    "result_processing_time_ms": m.result_processing_time_ms,
                    "cache_hit": m.cache_hit
                }
                for m in self.measurements
            ],
            "performance_report": self.generate_performance_report()
        }
        
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        with open(filepath, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        self.logger.info(f"Results saved to {filepath}")


async def run_search_latency_tests(
    vector_store: VectorStore,
    output_file: Optional[str] = None,
    service_types: List[str] = None,
    include_load_test: bool = True
) -> Dict[str, Any]:
    """Run comprehensive search latency tests."""
    
    if service_types is None:
        service_types = ["simple", "enhanced"]
    
    tester = SearchLatencyTester(vector_store)
    
    print("=" * 80)
    print("🔍 SEARCH LATENCY MEASUREMENT SUITE")
    print("=" * 80)
    print(f"📅 Started: {datetime.now().isoformat()}")
    print(f"🎯 Services: {', '.join(service_types)}")
    print(f"📊 Test Queries: {len(tester.test_queries)}")
    print()
    
    results = {
        "test_start": datetime.now(),
        "baselines": {},
        "bottlenecks": {},
        "load_test_results": {},
        "performance_report": {}
    }
    
    # Establish baselines for each service
    for service_type in service_types:
        print(f"📋 Establishing baseline for {service_type} service...")
        try:
            baseline = await tester.establish_performance_baseline(service_type, iterations_per_query=5)
            results["baselines"][service_type] = asdict(baseline)
            
            print(f"✅ {service_type.title()} Service Baseline:")
            print(f"   Average Latency: {baseline.avg_latency_ms:.1f}ms")
            print(f"   P95 Latency: {baseline.p95_latency_ms:.1f}ms")
            print(f"   Success Rate: {baseline.success_rate_percent:.1f}%")
            print(f"   Throughput: {baseline.queries_per_second:.1f} QPS")
            
        except Exception as e:
            print(f"❌ Failed to establish baseline for {service_type}: {e}")
            results["baselines"][service_type] = {"error": str(e)}
        
        print()
    
    # Identify bottlenecks for each service
    for service_type in service_types:
        print(f"🔍 Identifying bottlenecks for {service_type} service...")
        try:
            bottlenecks = await tester.identify_bottlenecks(service_type)
            results["bottlenecks"][service_type] = [
                {
                    "component": b.component,
                    "description": b.description,
                    "impact_level": b.impact_level,
                    "avg_time_ms": b.avg_time_ms,
                    "percentage_of_total": b.percentage_of_total,
                    "recommendations": b.recommendations
                }
                for b in bottlenecks
            ]
            
            if bottlenecks:
                print(f"⚠️  Found {len(bottlenecks)} potential bottlenecks:")
                for bottleneck in bottlenecks[:3]:  # Show top 3
                    impact_icon = "🔴" if bottleneck.impact_level == "critical" else "🟡" if bottleneck.impact_level == "high" else "🟢"
                    print(f"   {impact_icon} {bottleneck.component}: {bottleneck.description}")
            else:
                print("✅ No significant bottlenecks identified")
                
        except Exception as e:
            print(f"❌ Failed to identify bottlenecks for {service_type}: {e}")
            results["bottlenecks"][service_type] = {"error": str(e)}
        
        print()
    
    # Run load tests if requested
    if include_load_test:
        for service_type in service_types:
            print(f"⚡ Running load test for {service_type} service...")
            try:
                load_results = await tester.run_concurrent_load_test(
                    concurrent_users=5,  # Conservative for testing
                    duration_seconds=30,
                    service_type=service_type
                )
                results["load_test_results"][service_type] = load_results
                
                test_results = load_results["results"]
                print(f"📊 Load Test Results:")
                print(f"   Requests: {test_results['total_requests']} ({test_results['successful_requests']} successful)")
                print(f"   Success Rate: {test_results['success_rate_percent']:.1f}%")
                print(f"   Throughput: {test_results['requests_per_second']:.1f} RPS")
                print(f"   Avg Latency: {test_results['avg_latency_ms']:.1f}ms")
                print(f"   P95 Latency: {test_results['p95_latency_ms']:.1f}ms")
                
                # Show performance degradation if available
                if "performance_degradation" in load_results:
                    degradation = load_results["performance_degradation"]
                    if degradation:
                        print(f"   Performance Impact:")
                        print(f"     Latency increase: {degradation.get('avg_latency_increase_percent', 0):.1f}%")
                        print(f"     Throughput change: {degradation.get('throughput_change_percent', 0):.1f}%")
                
            except Exception as e:
                print(f"❌ Load test failed for {service_type}: {e}")
                results["load_test_results"][service_type] = {"error": str(e)}
            
            print()
    
    # Generate final performance report
    results["performance_report"] = tester.generate_performance_report()
    results["test_end"] = datetime.now()
    results["total_duration"] = (results["test_end"] - results["test_start"]).total_seconds()
    
    # Save results if requested
    if output_file:
        await tester.save_results(output_file)
        print(f"📄 Detailed results saved to: {output_file}")
    
    # Print summary
    print("=" * 80)
    print("📊 SEARCH LATENCY TEST SUMMARY")
    print("=" * 80)
    
    report = results["performance_report"]
    if "performance_analysis" in report:
        analysis = report["performance_analysis"]
        
        if "service_analysis" in analysis:
            print("🔍 Service Performance:")
            for service, stats in analysis["service_analysis"].items():
                print(f"   {service.title()}: {stats['avg_latency_ms']:.1f}ms avg, {stats['success_rate_percent']:.1f}% success")
        
        if "overall_statistics" in analysis:
            overall = analysis["overall_statistics"]
            print(f"\n📈 Overall: {overall['avg_latency_all_services']:.1f}ms avg latency, {overall['overall_success_rate']:.1f}% success rate")
    
    # Show top recommendations
    if "recommendations" in report and report["recommendations"]:
        print(f"\n💡 Top Recommendations:")
        for i, rec in enumerate(report["recommendations"][:3], 1):
            priority_icon = "🔴" if rec["priority"] == "critical" else "🟡" if rec["priority"] == "high" else "🟢"
            print(f"   {i}. {priority_icon} {rec['recommendation']}")
    
    print("=" * 80)
    
    return results


def main():
    """Main function for running search latency tests."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Run Search Latency Tests')
    parser.add_argument('--output', type=str, help='Output file for detailed results')
    parser.add_argument('--services', nargs='+', default=['simple', 'enhanced'],
                       choices=['simple', 'enhanced'], help='Search services to test')
    parser.add_argument('--no-load-test', action='store_true', help='Skip load testing')
    
    args = parser.parse_args()
    
    # This would need to be connected to actual vector store in real usage
    # For now, we'll create a mock implementation
    print("⚠️  Note: This test requires a configured vector store instance")
    print("   Please integrate with your vector store setup for actual testing")
    
    return 0


if __name__ == "__main__":
    exit(main())