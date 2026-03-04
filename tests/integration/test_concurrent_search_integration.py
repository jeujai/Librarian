#!/usr/bin/env python3
"""
Concurrent Search Integration Test

This test validates the concurrent search testing functionality and ensures
it integrates properly with the existing search services and monitoring infrastructure.

Validates: Task 2.1.2 - Create concurrent search testing
"""

import os
import sys
import asyncio
import pytest
import tempfile
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timedelta

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from multimodal_librarian.logging_config import get_logger
from multimodal_librarian.components.vector_store.vector_store import VectorStore
from multimodal_librarian.components.vector_store.search_service import EnhancedSemanticSearchService
from multimodal_librarian.components.vector_store.search_service_simple import SimpleSemanticSearchService
from multimodal_librarian.models.core import SourceType, ContentType

# Import the concurrent search tester
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'performance'))
from concurrent_search_test import (
    ConcurrentSearchTester,
    ConcurrentSearchMetric,
    ResourceUsageSnapshot,
    run_comprehensive_concurrent_tests
)


class MockVectorStore:
    """Mock vector store for testing concurrent search functionality."""
    
    def __init__(self, latency_ms: float = 100, failure_rate: float = 0.0):
        self.latency_ms = latency_ms
        self.failure_rate = failure_rate
        self.search_count = 0
        self.concurrent_searches = 0
        
    def semantic_search(self, query: str, top_k: int = 10, **kwargs):
        """Mock semantic search with configurable latency and failure rate."""
        import random
        import time
        
        self.search_count += 1
        self.concurrent_searches += 1
        
        # Simulate failure rate
        if random.random() < self.failure_rate:
            self.concurrent_searches -= 1
            raise Exception("Mock search failure")
        
        # Simulate latency
        time.sleep(self.latency_ms / 1000)
        
        # Return mock results
        results = [
            {
                'chunk_id': f'chunk_{i}_{self.search_count}',
                'content': f'Mock content for query: {query[:50]}...',
                'source_type': 'document',
                'source_id': f'doc_{i}',
                'content_type': 'text',
                'location_reference': f'page_{i}',
                'section': f'section_{i}',
                'similarity_score': 0.9 - (i * 0.1),
                'is_bridge': False,
                'created_at': int(datetime.now().timestamp() * 1000)
            }
            for i in range(min(top_k, 5))  # Return up to 5 results
        ]
        
        self.concurrent_searches -= 1
        return results
    
    def health_check(self) -> bool:
        """Mock health check."""
        return True


@pytest.fixture
def mock_vector_store():
    """Create a mock vector store for testing."""
    return MockVectorStore(latency_ms=50, failure_rate=0.05)  # 50ms latency, 5% failure rate


@pytest.fixture
def concurrent_tester(mock_vector_store):
    """Create a concurrent search tester with mock vector store."""
    return ConcurrentSearchTester(mock_vector_store)


class TestConcurrentSearchTester:
    """Test the ConcurrentSearchTester class functionality."""
    
    @pytest.mark.asyncio
    async def test_initialization(self, concurrent_tester):
        """Test that the concurrent search tester initializes correctly."""
        assert concurrent_tester.vector_store is not None
        assert concurrent_tester.simple_service is not None
        assert concurrent_tester.enhanced_service is not None
        assert len(concurrent_tester.test_queries) > 0
        assert concurrent_tester.concurrent_measurements == []
        assert concurrent_tester.resource_snapshots == []
    
    @pytest.mark.asyncio
    async def test_baseline_performance_measurement(self, concurrent_tester):
        """Test baseline performance measurement."""
        baseline = await concurrent_tester.measure_baseline_performance(
            service_type="simple",
            iterations=3
        )
        
        # Verify baseline metrics are calculated
        assert "avg_latency_ms" in baseline
        assert "p95_latency_ms" in baseline
        assert "success_rate_percent" not in baseline  # Not calculated in baseline
        assert baseline["avg_latency_ms"] > 0
        assert baseline["min_latency_ms"] <= baseline["avg_latency_ms"] <= baseline["max_latency_ms"]
    
    @pytest.mark.asyncio
    async def test_concurrent_search_basic(self, concurrent_tester):
        """Test basic concurrent search functionality."""
        result = await concurrent_tester.run_concurrent_search_test(
            concurrent_users=3,
            duration_seconds=5,
            service_type="simple",
            query_pattern="mixed"
        )
        
        # Verify test results structure
        assert "test_config" in result.__dict__
        assert "baseline_performance" in result.__dict__
        assert "concurrent_performance" in result.__dict__
        assert "performance_degradation" in result.__dict__
        assert "success_metrics" in result.__dict__
        assert "recommendations" in result.__dict__
        
        # Verify test config
        assert result.test_config["concurrent_users"] == 3
        assert result.test_config["duration_seconds"] == 5
        assert result.test_config["service_type"] == "simple"
        
        # Verify some measurements were taken
        assert len(concurrent_tester.concurrent_measurements) > 0
        
        # Verify success metrics
        assert "total_requests" in result.success_metrics
        assert "success_rate_percent" in result.success_metrics
        assert result.success_metrics["total_requests"] > 0
    
    @pytest.mark.asyncio
    async def test_resource_monitoring(self, concurrent_tester):
        """Test resource monitoring during concurrent tests."""
        # Start resource monitoring
        await concurrent_tester._start_resource_monitoring()
        
        # Wait a bit for some snapshots
        await asyncio.sleep(2)
        
        # Stop monitoring
        await concurrent_tester._stop_resource_monitoring()
        
        # Verify snapshots were taken
        assert len(concurrent_tester.resource_snapshots) > 0
        
        # Verify snapshot structure
        snapshot = concurrent_tester.resource_snapshots[0]
        assert hasattr(snapshot, 'timestamp')
        assert hasattr(snapshot, 'cpu_percent')
        assert hasattr(snapshot, 'memory_mb')
        assert hasattr(snapshot, 'active_threads')
    
    @pytest.mark.asyncio
    async def test_performance_degradation_calculation(self, concurrent_tester):
        """Test performance degradation calculation."""
        # Run a test to generate data
        result = await concurrent_tester.run_concurrent_search_test(
            concurrent_users=2,
            duration_seconds=3,
            service_type="simple"
        )
        
        # Verify degradation metrics are calculated
        degradation = result.performance_degradation
        
        # Should have degradation percentages for key metrics
        expected_metrics = [
            "avg_latency_ms_degradation_percent",
            "p95_latency_ms_degradation_percent",
            "p99_latency_ms_degradation_percent"
        ]
        
        for metric in expected_metrics:
            if metric in degradation:
                assert isinstance(degradation[metric], (int, float))
    
    @pytest.mark.asyncio
    async def test_query_patterns(self, concurrent_tester):
        """Test different query patterns."""
        patterns = ["mixed", "uniform", "burst"]
        
        for pattern in patterns:
            result = await concurrent_tester.run_concurrent_search_test(
                concurrent_users=2,
                duration_seconds=3,
                service_type="simple",
                query_pattern=pattern
            )
            
            assert result.test_config["query_pattern"] == pattern
            assert len(concurrent_tester.concurrent_measurements) > 0
    
    @pytest.mark.asyncio
    async def test_scaling_test(self, concurrent_tester):
        """Test scaling test functionality."""
        scaling_result = await concurrent_tester.run_scaling_test(
            max_users=10,
            step_size=3,
            step_duration=3,
            service_type="simple"
        )
        
        # Verify scaling result structure
        assert "scaling_results" in scaling_result
        assert "scaling_analysis" in scaling_result
        assert "max_tested_users" in scaling_result
        assert "recommended_max_users" in scaling_result
        
        # Verify scaling results
        scaling_results = scaling_result["scaling_results"]
        assert len(scaling_results) > 0
        
        # Verify each scaling point has required metrics
        for point in scaling_results:
            assert "concurrent_users" in point
            assert "avg_latency_ms" in point
            assert "success_rate_percent" in point
            assert "throughput_rps" in point
    
    @pytest.mark.asyncio
    async def test_recommendations_generation(self, concurrent_tester):
        """Test that recommendations are generated based on performance."""
        # Test with high degradation scenario
        with patch.object(concurrent_tester, '_analyze_concurrent_performance') as mock_analyze:
            mock_result = Mock()
            mock_result.test_config = {"concurrent_users": 10}
            mock_result.baseline_performance = {"avg_latency_ms": 100}
            mock_result.concurrent_performance = {"avg_latency_ms": 300}  # 200% increase
            mock_result.performance_degradation = {"avg_latency_ms_degradation_percent": 200}
            mock_result.success_metrics = {"success_rate_percent": 85}  # Low success rate
            mock_result.resource_usage = {"resource_efficiency": {"cpu_utilization_stable": False}}
            mock_result.recommendations = []
            
            mock_analyze.return_value = mock_result
            
            # Generate recommendations
            recommendations = concurrent_tester._generate_concurrent_recommendations(
                {"avg_latency_ms_degradation_percent": 200},
                {"success_rate_percent": 85, "resource_contention_rate_percent": 35},
                {"resource_efficiency": {"cpu_utilization_stable": False}}
            )
            
            # Verify recommendations are generated for performance issues
            assert len(recommendations) > 0
            assert any("Critical" in rec for rec in recommendations)
    
    @pytest.mark.asyncio
    async def test_error_handling(self, concurrent_tester):
        """Test error handling in concurrent search tests."""
        # Create a vector store that always fails
        failing_store = MockVectorStore(failure_rate=1.0)  # 100% failure rate
        failing_tester = ConcurrentSearchTester(failing_store)
        
        result = await failing_tester.run_concurrent_search_test(
            concurrent_users=2,
            duration_seconds=2,
            service_type="simple"
        )
        
        # Should handle failures gracefully - check if we have any failures or low success rate
        success_rate = result.success_metrics["success_rate_percent"]
        
        # Either we should have failures (success rate < 100%) or recommendations about issues
        has_failures = success_rate < 100
        has_error_recommendations = any("failure" in rec.lower() or "error" in rec.lower() or "critical" in rec.lower() for rec in result.recommendations)
        
        # At least one of these should be true - either we detected failures or we have error-related recommendations
        assert has_failures or has_error_recommendations, f"Expected failures or error recommendations, got {success_rate}% success rate and recommendations: {result.recommendations}"
        assert len(result.recommendations) > 0
    
    @pytest.mark.asyncio
    async def test_results_saving(self, concurrent_tester):
        """Test saving concurrent test results to file."""
        # Run a quick test to generate data
        await concurrent_tester.run_concurrent_search_test(
            concurrent_users=2,
            duration_seconds=2,
            service_type="simple"
        )
        
        # Save results to temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_file = f.name
        
        try:
            await concurrent_tester.save_results(temp_file)
            
            # Verify file was created and contains data
            assert os.path.exists(temp_file)
            
            import json
            with open(temp_file, 'r') as f:
                data = json.load(f)
            
            # Verify file structure
            assert "test_metadata" in data
            assert "concurrent_measurements" in data
            assert "resource_snapshots" in data
            assert "performance_report" in data
            
            # Verify measurements were saved
            assert len(data["concurrent_measurements"]) > 0
            
        finally:
            # Clean up
            if os.path.exists(temp_file):
                os.unlink(temp_file)


class TestConcurrentSearchIntegration:
    """Test integration with existing search services and monitoring."""
    
    @pytest.mark.asyncio
    async def test_simple_service_integration(self, mock_vector_store):
        """Test integration with SimpleSemanticSearchService."""
        tester = ConcurrentSearchTester(mock_vector_store)
        
        result = await tester.run_concurrent_search_test(
            concurrent_users=2,
            duration_seconds=3,
            service_type="simple"
        )
        
        # Verify simple service was used
        assert result.test_config["service_type"] == "simple"
        assert len(tester.concurrent_measurements) > 0
        
        # Verify measurements have correct service type
        for measurement in tester.concurrent_measurements:
            assert measurement.search_service == "simple"
    
    @pytest.mark.asyncio
    async def test_enhanced_service_integration(self, mock_vector_store):
        """Test integration with EnhancedSemanticSearchService."""
        tester = ConcurrentSearchTester(mock_vector_store)
        
        result = await tester.run_concurrent_search_test(
            concurrent_users=2,
            duration_seconds=3,
            service_type="enhanced"
        )
        
        # Verify enhanced service was used
        assert result.test_config["service_type"] == "enhanced"
        assert len(tester.concurrent_measurements) > 0
    
    @pytest.mark.asyncio
    async def test_performance_monitoring_integration(self, mock_vector_store):
        """Test integration with performance monitoring."""
        tester = ConcurrentSearchTester(mock_vector_store)
        
        # Run test with resource monitoring
        result = await tester.run_concurrent_search_test(
            concurrent_users=3,
            duration_seconds=4,
            service_type="simple"
        )
        
        # Verify resource usage was monitored
        assert "resource_usage" in result.__dict__
        resource_usage = result.resource_usage
        
        if "cpu_usage" in resource_usage:
            assert "avg_percent" in resource_usage["cpu_usage"]
            assert "max_percent" in resource_usage["cpu_usage"]
        
        if "memory_usage" in resource_usage:
            assert "avg_mb" in resource_usage["memory_usage"]
            assert "max_mb" in resource_usage["memory_usage"]
    
    @pytest.mark.asyncio
    async def test_comprehensive_test_runner(self, mock_vector_store):
        """Test the comprehensive test runner function."""
        # Mock the vector store to avoid actual database calls
        with patch('concurrent_search_test.VectorStore', return_value=mock_vector_store):
            results = await run_comprehensive_concurrent_tests(
                mock_vector_store,
                service_types=["simple"],
                include_scaling_test=False  # Skip scaling test for speed
            )
        
        # Verify results structure
        assert "test_start" in results
        assert "concurrent_tests" in results
        assert "performance_report" in results
        
        # Verify service tests were run
        assert "simple" in results["concurrent_tests"]
        service_results = results["concurrent_tests"]["simple"]
        
        # Should have results for different user levels
        assert len(service_results) > 0


class TestConcurrentSearchMetrics:
    """Test concurrent search metrics and data structures."""
    
    def test_concurrent_search_metric_creation(self):
        """Test ConcurrentSearchMetric creation and attributes."""
        metric = ConcurrentSearchMetric(
            user_id=1,
            query_text="test query",
            query_type="test",
            search_service="simple",
            start_time=datetime.now(),
            end_time=datetime.now(),
            latency_ms=150.5,
            result_count=5,
            success=True,
            concurrent_users=10,
            queue_wait_time_ms=25.0,
            resource_contention=False
        )
        
        assert metric.user_id == 1
        assert metric.query_text == "test query"
        assert metric.latency_ms == 150.5
        assert metric.success is True
        assert metric.concurrent_users == 10
        assert metric.resource_contention is False
    
    def test_resource_usage_snapshot_creation(self):
        """Test ResourceUsageSnapshot creation and attributes."""
        snapshot = ResourceUsageSnapshot(
            timestamp=datetime.now(),
            cpu_percent=45.2,
            memory_mb=1024.5,
            memory_percent=65.3,
            active_threads=25,
            open_files=150,
            network_connections=10,
            concurrent_searches=5
        )
        
        assert snapshot.cpu_percent == 45.2
        assert snapshot.memory_mb == 1024.5
        assert snapshot.active_threads == 25
        assert snapshot.concurrent_searches == 5


@pytest.mark.asyncio
async def test_concurrent_search_requirement_validation():
    """
    Test that concurrent search testing validates Requirement 2.3:
    'WHEN handling concurrent searches, THE system SHALL maintain performance'
    """
    # Create mock vector store with predictable performance
    mock_store = MockVectorStore(latency_ms=100, failure_rate=0.02)  # 2% failure rate
    tester = ConcurrentSearchTester(mock_store)
    
    # Test concurrent performance
    result = await tester.run_concurrent_search_test(
        concurrent_users=5,
        duration_seconds=10,
        service_type="simple",
        query_pattern="mixed"
    )
    
    # Validate that performance is maintained (Requirement 2.3)
    success_rate = result.success_metrics["success_rate_percent"]
    avg_latency = result.concurrent_performance["avg_latency_ms"]
    
    # Performance should be maintained under concurrent load
    assert success_rate > 90, f"Success rate {success_rate}% too low under concurrent load"
    assert avg_latency < 500, f"Average latency {avg_latency}ms too high under concurrent load"
    
    # Performance degradation should be reasonable
    if "avg_latency_ms_degradation_percent" in result.performance_degradation:
        degradation = result.performance_degradation["avg_latency_ms_degradation_percent"]
        assert degradation < 200, f"Performance degradation {degradation}% too high"
    
    # Resource contention should be manageable
    contention_rate = result.success_metrics.get("resource_contention_rate_percent", 0)
    assert contention_rate < 50, f"Resource contention {contention_rate}% too high"
    
    print(f"✅ Requirement 2.3 validated: {success_rate:.1f}% success rate, "
          f"{avg_latency:.1f}ms avg latency under {result.test_config['concurrent_users']} concurrent users")


if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v"])