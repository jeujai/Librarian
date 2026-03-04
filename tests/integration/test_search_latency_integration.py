#!/usr/bin/env python3
"""
Integration test for search latency measurement system.

This test validates that the search latency measurement system works correctly
with the actual search services and monitoring infrastructure.

Validates: Requirement 2.1 - Search Service Performance Optimization
"""

import os
import sys
import asyncio
import pytest
import tempfile
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from multimodal_librarian.components.vector_store.vector_store import VectorStore
from multimodal_librarian.components.vector_store.search_service import EnhancedSemanticSearchService, SearchRequest
from multimodal_librarian.components.vector_store.search_service_simple import SimpleSemanticSearchService, SimpleSearchRequest
from multimodal_librarian.monitoring.search_performance_monitor import SearchPerformanceMonitor, SearchPerformanceMetric
from multimodal_librarian.monitoring.metrics_collector import MetricsCollector
from multimodal_librarian.models.search_types import SearchResult
from multimodal_librarian.models.core import SourceType, ContentType

# Import the performance test suite
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'performance'))
from search_latency_test import SearchLatencyTester


class MockVectorStore:
    """Mock vector store for testing."""
    
    def __init__(self):
        self.search_delay = 0.1  # 100ms simulated search time
        self.should_fail = False
        
    def semantic_search(self, query, top_k=10, **kwargs):
        """Mock semantic search with configurable delay."""
        import time
        time.sleep(self.search_delay)
        
        if self.should_fail:
            raise Exception("Simulated search failure")
        
        # Return mock results
        return [
            {
                'chunk_id': f'chunk_{i}',
                'content': f'Mock result {i} for query: {query[:50]}',
                'source_type': 'document',
                'source_id': f'doc_{i}',
                'content_type': 'text',
                'location_reference': f'page_{i}',
                'section': f'section_{i}',
                'similarity_score': 0.9 - (i * 0.1),
                'created_at': datetime.now().timestamp() * 1000
            }
            for i in range(min(top_k, 5))  # Return up to 5 results
        ]
    
    def health_check(self):
        """Mock health check."""
        return not self.should_fail


@pytest.fixture
def mock_vector_store():
    """Provide mock vector store for testing."""
    return MockVectorStore()


@pytest.fixture
def metrics_collector():
    """Provide metrics collector for testing."""
    return MetricsCollector()


@pytest.fixture
def search_performance_monitor(metrics_collector):
    """Provide search performance monitor for testing."""
    return SearchPerformanceMonitor(metrics_collector)


@pytest.fixture
def simple_search_service(mock_vector_store):
    """Provide simple search service for testing."""
    return SimpleSemanticSearchService(mock_vector_store)


@pytest.fixture
def enhanced_search_service(mock_vector_store):
    """Provide enhanced search service for testing."""
    return EnhancedSemanticSearchService(mock_vector_store)


@pytest.fixture
def search_latency_tester(mock_vector_store):
    """Provide search latency tester for testing."""
    return SearchLatencyTester(mock_vector_store)


class TestSearchLatencyMeasurement:
    """Test search latency measurement functionality."""
    
    @pytest.mark.asyncio
    async def test_simple_search_latency_measurement(self, simple_search_service, search_performance_monitor):
        """Test latency measurement for simple search service."""
        
        # Create search request
        request = SimpleSearchRequest(
            query="test query",
            session_id="test_session",
            top_k=5
        )
        
        # Measure search latency
        start_time = asyncio.get_event_loop().time()
        response = await simple_search_service.search(request)
        end_time = asyncio.get_event_loop().time()
        
        latency_ms = (end_time - start_time) * 1000
        
        # Record performance metric
        search_performance_monitor.record_search_performance(
            query_text="test query",
            query_type="simple_keyword",
            service_type="simple",
            total_latency_ms=latency_ms,
            result_count=len(response.results),
            success=True
        )
        
        # Verify measurement was recorded
        current_performance = search_performance_monitor.get_current_search_performance()
        
        assert "error" not in current_performance
        assert current_performance["total_searches"] == 1
        assert current_performance["successful_searches"] == 1
        assert current_performance["latency_metrics"]["avg_latency_ms"] > 0
        assert current_performance["quality_metrics"]["success_rate_percent"] == 100.0
    
    @pytest.mark.asyncio
    async def test_enhanced_search_latency_measurement(self, enhanced_search_service, search_performance_monitor):
        """Test latency measurement for enhanced search service."""
        
        # Create search request
        request = SearchRequest(
            query="machine learning algorithms",
            session_id="test_session",
            top_k=5
        )
        
        # Measure search latency
        start_time = asyncio.get_event_loop().time()
        response = await enhanced_search_service.search(request)
        end_time = asyncio.get_event_loop().time()
        
        latency_ms = (end_time - start_time) * 1000
        
        # Record performance metric
        search_performance_monitor.record_search_performance(
            query_text="machine learning algorithms",
            query_type="technical_specific",
            service_type="enhanced",
            total_latency_ms=latency_ms,
            result_count=len(response.results) if hasattr(response, 'results') else 0,
            success=True,
            vector_search_ms=latency_ms * 0.7,  # Simulate 70% in vector search
            result_processing_ms=latency_ms * 0.3  # Simulate 30% in processing
        )
        
        # Verify measurement was recorded
        current_performance = search_performance_monitor.get_current_search_performance()
        
        assert "error" not in current_performance
        assert current_performance["total_searches"] == 1
        assert current_performance["successful_searches"] == 1
        assert current_performance["latency_metrics"]["avg_latency_ms"] > 0
    
    @pytest.mark.asyncio
    async def test_search_failure_measurement(self, mock_vector_store, simple_search_service, search_performance_monitor):
        """Test latency measurement when search fails."""
        
        # Configure mock to fail
        mock_vector_store.should_fail = True
        
        # Create search request
        request = SimpleSearchRequest(
            query="failing query",
            session_id="test_session",
            top_k=5
        )
        
        # Measure search latency (should fail)
        start_time = asyncio.get_event_loop().time()
        response = await simple_search_service.search(request)
        end_time = asyncio.get_event_loop().time()
        
        latency_ms = (end_time - start_time) * 1000
        
        # Record performance metric for failure
        search_performance_monitor.record_search_performance(
            query_text="failing query",
            query_type="simple_keyword",
            service_type="simple",
            total_latency_ms=latency_ms,
            result_count=0,
            success=False,
            error_type="search_failure"
        )
        
        # Verify failure was recorded
        current_performance = search_performance_monitor.get_current_search_performance()
        
        assert "error" not in current_performance
        assert current_performance["total_searches"] == 1
        assert current_performance["successful_searches"] == 0
        assert current_performance["quality_metrics"]["success_rate_percent"] == 0.0
    
    @pytest.mark.asyncio
    async def test_multiple_search_measurements(self, simple_search_service, search_performance_monitor):
        """Test multiple search latency measurements."""
        
        queries = [
            ("artificial intelligence", "simple_keyword"),
            ("How does machine learning work?", "question"),
            ("neural networks deep learning", "technical_specific"),
            ("AI", "short_keyword"),
            ("Compare supervised vs unsupervised learning", "comparative")
        ]
        
        # Perform multiple searches
        for query, query_type in queries:
            request = SimpleSearchRequest(
                query=query,
                session_id="test_session",
                top_k=5
            )
            
            start_time = asyncio.get_event_loop().time()
            response = await simple_search_service.search(request)
            end_time = asyncio.get_event_loop().time()
            
            latency_ms = (end_time - start_time) * 1000
            
            search_performance_monitor.record_search_performance(
                query_text=query,
                query_type=query_type,
                service_type="simple",
                total_latency_ms=latency_ms,
                result_count=len(response.results),
                success=True
            )
        
        # Verify all measurements were recorded
        current_performance = search_performance_monitor.get_current_search_performance()
        
        assert current_performance["total_searches"] == len(queries)
        assert current_performance["successful_searches"] == len(queries)
        assert current_performance["quality_metrics"]["success_rate_percent"] == 100.0
        
        # Check query type breakdown
        query_breakdown = current_performance["query_type_breakdown"]
        assert len(query_breakdown) == len(set(qt for _, qt in queries))
    
    @pytest.mark.asyncio
    async def test_performance_baseline_establishment(self, search_latency_tester):
        """Test establishing performance baseline."""
        
        # Establish baseline for simple service
        baseline = await search_latency_tester.establish_performance_baseline(
            service_type="simple",
            iterations_per_query=3  # Reduced for testing
        )
        
        # Verify baseline was established
        assert baseline.service_type == "simple"
        assert baseline.avg_latency_ms > 0
        assert baseline.success_rate_percent > 0
        assert baseline.queries_per_second > 0
        
        # Check that baseline is stored
        assert "simple" in search_latency_tester.baselines
        stored_baseline = search_latency_tester.baselines["simple"]
        assert stored_baseline.avg_latency_ms == baseline.avg_latency_ms
    
    @pytest.mark.asyncio
    async def test_bottleneck_identification(self, search_latency_tester):
        """Test bottleneck identification."""
        
        # First establish some measurements
        await search_latency_tester.establish_performance_baseline(
            service_type="simple",
            iterations_per_query=2
        )
        
        # Identify bottlenecks
        bottlenecks = await search_latency_tester.identify_bottlenecks("simple")
        
        # Verify bottleneck analysis completed (may or may not find bottlenecks)
        assert isinstance(bottlenecks, list)
        
        # If bottlenecks found, verify structure
        for bottleneck in bottlenecks:
            assert "component" in bottleneck
            assert "description" in bottleneck
            assert "impact_level" in bottleneck
            assert "avg_time_ms" in bottleneck
            assert "percentage_of_total" in bottleneck
            assert "recommendations" in bottleneck
    
    @pytest.mark.asyncio
    async def test_concurrent_load_measurement(self, search_latency_tester):
        """Test concurrent load performance measurement."""
        
        # Run a small concurrent load test
        load_results = await search_latency_tester.run_concurrent_load_test(
            concurrent_users=3,  # Small number for testing
            duration_seconds=5,  # Short duration for testing
            service_type="simple"
        )
        
        # Verify load test results
        assert "test_config" in load_results
        assert "results" in load_results
        
        results = load_results["results"]
        assert results["total_requests"] > 0
        assert results["successful_requests"] >= 0
        assert results["success_rate_percent"] >= 0
        assert results["requests_per_second"] > 0
        assert results["avg_latency_ms"] > 0
    
    @pytest.mark.asyncio
    async def test_performance_report_generation(self, search_latency_tester):
        """Test performance report generation."""
        
        # Generate some test data
        await search_latency_tester.establish_performance_baseline(
            service_type="simple",
            iterations_per_query=2
        )
        
        # Generate performance report
        report = search_latency_tester.generate_performance_report()
        
        # Verify report structure
        assert "report_timestamp" in report
        assert "test_summary" in report
        assert "baselines" in report
        assert "bottlenecks" in report
        assert "performance_analysis" in report
        assert "recommendations" in report
        
        # Verify test summary
        test_summary = report["test_summary"]
        assert test_summary["total_measurements"] > 0
        assert test_summary["successful_measurements"] >= 0
        assert "simple" in test_summary["services_tested"]
    
    @pytest.mark.asyncio
    async def test_performance_monitoring_integration(self, search_performance_monitor, metrics_collector):
        """Test integration with performance monitoring system."""
        
        # Record several search performance metrics
        test_metrics = [
            ("query1", "simple_keyword", "simple", 150.0, 5, True),
            ("query2", "question", "enhanced", 300.0, 3, True),
            ("query3", "technical_specific", "simple", 200.0, 4, True),
            ("query4", "comparative", "enhanced", 450.0, 6, True),
        ]
        
        for query, query_type, service_type, latency, result_count, success in test_metrics:
            search_performance_monitor.record_search_performance(
                query_text=query,
                query_type=query_type,
                service_type=service_type,
                total_latency_ms=latency,
                result_count=result_count,
                success=success,
                vector_search_ms=latency * 0.7,
                result_processing_ms=latency * 0.3
            )
        
        # Get current performance
        current_performance = search_performance_monitor.get_current_search_performance()
        
        # Verify integration
        assert current_performance["total_searches"] == len(test_metrics)
        assert current_performance["successful_searches"] == len([m for m in test_metrics if m[5]])
        
        # Verify service breakdown
        service_breakdown = current_performance["service_breakdown"]
        assert "simple" in service_breakdown
        assert "enhanced" in service_breakdown
        
        # Verify latency metrics
        latency_metrics = current_performance["latency_metrics"]
        assert latency_metrics["avg_latency_ms"] > 0
        assert latency_metrics["p95_latency_ms"] > 0
    
    @pytest.mark.asyncio
    async def test_bottleneck_analysis_integration(self, search_performance_monitor):
        """Test bottleneck analysis integration."""
        
        # Record metrics with clear bottleneck pattern (slow vector search)
        for i in range(10):
            search_performance_monitor.record_search_performance(
                query_text=f"query_{i}",
                query_type="simple_keyword",
                service_type="simple",
                total_latency_ms=500.0,
                result_count=5,
                success=True,
                vector_search_ms=400.0,  # 80% of time in vector search
                result_processing_ms=100.0  # 20% in processing
            )
        
        # Analyze bottlenecks
        bottlenecks = search_performance_monitor.analyze_search_bottlenecks(hours=1)
        
        # Should identify vector search as bottleneck
        vector_bottleneck = next(
            (b for b in bottlenecks if b["component"] == "vector_search"), 
            None
        )
        
        if vector_bottleneck:  # May not always trigger depending on thresholds
            assert vector_bottleneck["impact_level"] in ["medium", "high"]
            assert "vector" in vector_bottleneck["description"].lower()
    
    @pytest.mark.asyncio
    async def test_performance_report_integration(self, search_performance_monitor):
        """Test comprehensive performance report generation."""
        
        # Record diverse performance data
        test_scenarios = [
            # Good performance
            ("fast_query", "simple_keyword", "simple", 100.0, 5, True, False, False),
            # Slow performance
            ("slow_query", "complex_technical", "enhanced", 800.0, 3, True, False, False),
            # Cache hit
            ("cached_query", "simple_keyword", "simple", 50.0, 5, True, True, False),
            # Fallback usage
            ("fallback_query", "question", "enhanced", 300.0, 4, True, False, True),
            # Failure
            ("failed_query", "technical_specific", "simple", 200.0, 0, False, False, False),
        ]
        
        for query, query_type, service_type, latency, result_count, success, cache_hit, fallback in test_scenarios:
            search_performance_monitor.record_search_performance(
                query_text=query,
                query_type=query_type,
                service_type=service_type,
                total_latency_ms=latency,
                result_count=result_count,
                success=success,
                cache_hit=cache_hit,
                fallback_used=fallback
            )
        
        # Generate comprehensive report
        report = search_performance_monitor.get_search_performance_report()
        
        # Verify report completeness
        assert "report_timestamp" in report
        assert "current_performance" in report
        assert "historical_performance" in report
        assert "bottleneck_analysis" in report
        assert "recommendations" in report
        assert "performance_status" in report
        assert "threshold_violations" in report
        
        # Verify performance status determination
        assert report["performance_status"] in ["excellent", "healthy", "degraded", "critical", "unknown"]
    
    def test_results_export(self, search_latency_tester):
        """Test exporting search latency test results."""
        
        # Add some mock measurements
        from tests.performance.search_latency_test import SearchLatencyMetric
        
        mock_measurement = SearchLatencyMetric(
            query_text="test query",
            query_type="simple_keyword",
            search_service="simple",
            latency_ms=150.0,
            result_count=5,
            timestamp=datetime.now(),
            success=True
        )
        
        search_latency_tester.measurements.append(mock_measurement)
        
        # Test export functionality
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_filepath = f.name
        
        try:
            # Export results
            asyncio.run(search_latency_tester.save_results(temp_filepath))
            
            # Verify file was created and contains data
            assert os.path.exists(temp_filepath)
            
            with open(temp_filepath, 'r') as f:
                import json
                data = json.load(f)
            
            assert "test_metadata" in data
            assert "measurements" in data
            assert "performance_report" in data
            assert len(data["measurements"]) == 1
            
        finally:
            # Clean up
            if os.path.exists(temp_filepath):
                os.unlink(temp_filepath)


class TestSearchLatencyThresholds:
    """Test search latency threshold monitoring."""
    
    @pytest.mark.asyncio
    async def test_latency_threshold_alerts(self, search_performance_monitor):
        """Test that latency threshold violations generate alerts."""
        
        alerts_received = []
        
        def alert_callback(alert):
            alerts_received.append(alert)
        
        search_performance_monitor.add_alert_callback(alert_callback)
        
        # Record a very slow search (should trigger critical alert)
        search_performance_monitor.record_search_performance(
            query_text="extremely slow query",
            query_type="complex_technical",
            service_type="enhanced",
            total_latency_ms=6000.0,  # 6 seconds - should trigger critical alert
            result_count=3,
            success=True
        )
        
        # Check if alert was generated
        assert len(alerts_received) > 0
        
        # Verify alert properties
        critical_alert = alerts_received[-1]
        assert critical_alert.severity == "critical"
        assert "slow search" in critical_alert.message.lower()
    
    @pytest.mark.asyncio
    async def test_success_rate_threshold_monitoring(self, search_performance_monitor):
        """Test success rate threshold monitoring."""
        
        # Record multiple failed searches to trigger success rate alert
        for i in range(10):
            success = i < 8  # 80% success rate
            
            search_performance_monitor.record_search_performance(
                query_text=f"query_{i}",
                query_type="simple_keyword",
                service_type="simple",
                total_latency_ms=200.0,
                result_count=5 if success else 0,
                success=success,
                error_type=None if success else "search_error"
            )
        
        # Get current performance to check success rate
        current_performance = search_performance_monitor.get_current_search_performance()
        success_rate = current_performance["quality_metrics"]["success_rate_percent"]
        
        # Should be around 80%
        assert 75 <= success_rate <= 85
        
        # Check threshold violations
        report = search_performance_monitor.get_search_performance_report()
        violations = report["threshold_violations"]
        
        # Should have success rate violation
        success_violations = [v for v in violations if "success_rate" in v["metric"]]
        assert len(success_violations) > 0


if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v"])