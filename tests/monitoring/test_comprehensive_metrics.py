"""
Tests for comprehensive metrics collection system.

This module tests the comprehensive metrics collector, middleware, and integration utilities
to ensure accurate metrics collection for response times, resource usage, and user sessions.
"""

import pytest
import asyncio
import time
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient

from src.multimodal_librarian.monitoring.comprehensive_metrics_collector import (
    ComprehensiveMetricsCollector,
    ResponseTimeMetric,
    ResourceUsageMetric,
    UserSessionMetric,
    SearchPerformanceMetric,
    DocumentProcessingMetric
)
from src.multimodal_librarian.api.middleware.metrics_middleware import (
    ComprehensiveMetricsMiddleware,
    SearchMetricsMiddleware
)
from src.multimodal_librarian.monitoring.metrics_integration import (
    initialize_metrics_integration,
    track_response_time,
    track_search_performance,
    track_document_processing,
    MetricsContext,
    SearchMetricsHelper,
    DocumentMetricsHelper
)


class TestComprehensiveMetricsCollector:
    """Test the comprehensive metrics collector."""
    
    @pytest.fixture
    def collector(self):
        """Create a metrics collector for testing."""
        with patch('src.multimodal_librarian.monitoring.comprehensive_metrics_collector.psutil'):
            collector = ComprehensiveMetricsCollector()
            # Stop background collection for testing
            collector._collection_active = False
            return collector
    
    def test_record_response_time(self, collector):
        """Test recording response time metrics."""
        collector.record_response_time(
            endpoint="/api/test",
            method="GET",
            response_time_ms=150.5,
            status_code=200,
            user_id="user123",
            user_agent="TestAgent/1.0"
        )
        
        assert len(collector._response_times) == 1
        metric = collector._response_times[0]
        assert metric.endpoint == "/api/test"
        assert metric.method == "GET"
        assert metric.response_time_ms == 150.5
        assert metric.status_code == 200
        assert metric.user_id == "user123"
        assert metric.user_agent == "TestAgent/1.0"
    
    def test_record_user_session_activity(self, collector):
        """Test recording user session activity."""
        session_id = "session123"
        
        # Record first activity
        collector.record_user_session_activity(
            session_id=session_id,
            user_id="user123",
            endpoint="/api/search",
            response_time_ms=200.0,
            user_agent="TestAgent/1.0",
            ip_address="192.168.1.1"
        )
        
        assert session_id in collector._user_sessions
        session = collector._user_sessions[session_id]
        assert session.user_id == "user123"
        assert session.total_requests == 1
        assert session.total_response_time_ms == 200.0
        assert "/api/search" in session.endpoints_accessed
        
        # Record second activity
        collector.record_user_session_activity(
            session_id=session_id,
            endpoint="/api/documents",
            response_time_ms=100.0
        )
        
        session = collector._user_sessions[session_id]
        assert session.total_requests == 2
        assert session.total_response_time_ms == 300.0
        assert len(session.endpoints_accessed) == 2
    
    def test_record_search_performance(self, collector):
        """Test recording search performance metrics."""
        collector.record_search_performance(
            query_text="test query",
            search_type="vector",
            response_time_ms=250.0,
            results_count=15,
            cache_hit=True,
            user_id="user123"
        )
        
        assert len(collector._search_performance) == 1
        metric = collector._search_performance[0]
        assert metric.query_text == "test query"
        assert metric.search_type == "vector"
        assert metric.response_time_ms == 250.0
        assert metric.results_count == 15
        assert metric.cache_hit is True
        assert metric.user_id == "user123"
        
        # Check cache metrics updated
        assert collector._cache_metrics['hits'] == 1
        assert collector._cache_metrics['misses'] == 0
    
    def test_record_document_processing(self, collector):
        """Test recording document processing metrics."""
        collector.record_document_processing(
            document_id="doc123",
            document_size_mb=2.5,
            processing_time_ms=5000.0,
            processing_stage="extract",
            success=True
        )
        
        assert len(collector._document_processing) == 1
        metric = collector._document_processing[0]
        assert metric.document_id == "doc123"
        assert metric.document_size_mb == 2.5
        assert metric.processing_time_ms == 5000.0
        assert metric.processing_stage == "extract"
        assert metric.success is True
        assert metric.error_message is None
    
    def test_concurrent_request_tracking(self, collector):
        """Test concurrent request tracking."""
        assert collector._concurrent_requests == 0
        
        collector.record_request_start()
        assert collector._concurrent_requests == 1
        
        collector.record_request_start()
        assert collector._concurrent_requests == 2
        assert collector._peak_concurrent_requests == 2
        
        collector.record_request_end()
        assert collector._concurrent_requests == 1
        
        collector.record_request_end()
        assert collector._concurrent_requests == 0
        
        # Peak should remain
        assert collector._peak_concurrent_requests == 2
    
    @patch('src.multimodal_librarian.monitoring.comprehensive_metrics_collector.psutil')
    def test_get_real_time_metrics(self, mock_psutil, collector):
        """Test getting real-time metrics."""
        # Mock psutil for resource usage
        mock_psutil.cpu_percent.return_value = 45.2
        mock_psutil.virtual_memory.return_value = Mock(
            total=8589934592,  # 8GB
            used=4294967296,   # 4GB
            available=4294967296,  # 4GB
            percent=50.0
        )
        mock_psutil.disk_usage.return_value = Mock(
            total=1099511627776,  # 1TB
            used=549755813888,    # 512GB
            free=549755813888,    # 512GB
            percent=50.0
        )
        mock_psutil.net_io_counters.return_value = Mock(
            bytes_sent=1000000,
            bytes_recv=2000000
        )
        mock_psutil.Process.return_value = Mock(
            memory_info=Mock(rss=104857600, vms=209715200),  # 100MB RSS, 200MB VMS
            open_files=Mock(return_value=[]),
            connections=Mock(return_value=[])
        )
        
        # Add some test data
        collector.record_response_time("/api/test", "GET", 100.0, 200)
        collector.record_search_performance("test", "vector", 200.0, 10, False)
        collector.record_user_session_activity("session1", "user1")
        
        metrics = collector.get_real_time_metrics()
        
        assert 'timestamp' in metrics
        assert 'system_uptime_hours' in metrics
        assert 'response_time_metrics' in metrics
        assert 'resource_usage' in metrics
        assert 'user_session_metrics' in metrics
        assert 'search_performance' in metrics
        assert 'cache_metrics' in metrics
        
        # Check response time metrics
        response_metrics = metrics['response_time_metrics']
        assert response_metrics['total_requests_5min'] == 1
        assert response_metrics['avg_response_time_ms'] == 100.0
        
        # Check user session metrics
        session_metrics = metrics['user_session_metrics']
        assert session_metrics['active_sessions'] == 1
        assert session_metrics['total_sessions'] == 1
    
    def test_get_performance_trends(self, collector):
        """Test getting performance trends."""
        # Add test data with different timestamps
        now = datetime.now()
        
        # Simulate data from 2 hours ago
        with patch('src.multimodal_librarian.monitoring.comprehensive_metrics_collector.datetime') as mock_dt:
            mock_dt.now.return_value = now - timedelta(hours=2)
            collector.record_response_time("/api/test", "GET", 100.0, 200, "user1")
            collector.record_search_performance("old query", "vector", 150.0, 5, False, "user1")
        
        # Simulate data from 1 hour ago
        with patch('src.multimodal_librarian.monitoring.comprehensive_metrics_collector.datetime') as mock_dt:
            mock_dt.now.return_value = now - timedelta(hours=1)
            collector.record_response_time("/api/test", "GET", 200.0, 200, "user2")
            collector.record_search_performance("recent query", "hybrid", 250.0, 8, True, "user2")
        
        trends = collector.get_performance_trends(3)
        
        assert 'period_hours' in trends
        assert 'hourly_trends' in trends
        assert 'summary' in trends
        
        assert trends['period_hours'] == 3
        assert trends['summary']['total_requests'] >= 2
        assert trends['summary']['total_searches'] >= 2
    
    def test_get_user_session_analytics(self, collector):
        """Test getting user session analytics."""
        # Create test sessions
        collector.record_user_session_activity("session1", "user1", "/api/search", 100.0)
        collector.record_user_session_activity("session1", "user1", "/api/documents", 150.0)
        collector.record_user_session_activity("session2", "user2", "/api/search", 200.0)
        
        analytics = collector.get_user_session_analytics()
        
        assert 'active_sessions' in analytics
        assert 'total_sessions' in analytics
        assert 'session_analytics' in analytics
        assert 'user_engagement' in analytics
        
        assert analytics['total_sessions'] == 2
        assert analytics['session_analytics']['total_requests'] == 3
        assert analytics['user_engagement']['unique_users'] == 2
    
    def test_cache_metrics(self, collector):
        """Test cache metrics tracking."""
        # Record cache events
        collector.record_cache_event("hit")
        collector.record_cache_event("hit")
        collector.record_cache_event("miss")
        collector.record_cache_event("eviction")
        collector.record_cache_event("size_update", 1048576)  # 1MB
        
        assert collector._cache_metrics['hits'] == 2
        assert collector._cache_metrics['misses'] == 1
        assert collector._cache_metrics['evictions'] == 1
        assert collector._cache_metrics['size_bytes'] == 1048576
    
    def test_export_comprehensive_report(self, collector):
        """Test exporting comprehensive metrics report."""
        # Add some test data
        collector.record_response_time("/api/test", "GET", 100.0, 200)
        collector.record_search_performance("test", "vector", 200.0, 10, False)
        
        with patch('builtins.open', create=True) as mock_open:
            with patch('json.dump') as mock_json_dump:
                with patch('os.makedirs'):
                    filepath = collector.export_comprehensive_report("test_report.json")
                    
                    assert filepath == "test_report.json"
                    mock_open.assert_called_once()
                    mock_json_dump.assert_called_once()


class TestMetricsMiddleware:
    """Test the metrics middleware."""
    
    @pytest.fixture
    def app(self):
        """Create a test FastAPI app."""
        app = FastAPI()
        
        @app.get("/test")
        async def test_endpoint():
            return {"message": "test"}
        
        @app.get("/error")
        async def error_endpoint():
            raise Exception("Test error")
        
        return app
    
    @pytest.fixture
    def collector(self):
        """Create a metrics collector for testing."""
        with patch('src.multimodal_librarian.monitoring.comprehensive_metrics_collector.psutil'):
            collector = ComprehensiveMetricsCollector()
            collector._collection_active = False
            return collector
    
    def test_middleware_records_metrics(self, app, collector):
        """Test that middleware records metrics for requests."""
        # Add middleware
        app.add_middleware(ComprehensiveMetricsMiddleware, metrics_collector=collector)
        
        client = TestClient(app)
        response = client.get("/test")
        
        assert response.status_code == 200
        assert len(collector._response_times) == 1
        
        metric = collector._response_times[0]
        assert metric.endpoint == "/test"
        assert metric.method == "GET"
        assert metric.status_code == 200
        assert metric.response_time_ms > 0
    
    def test_middleware_records_errors(self, app, collector):
        """Test that middleware records error metrics."""
        app.add_middleware(ComprehensiveMetricsMiddleware, metrics_collector=collector)
        
        client = TestClient(app)
        
        with pytest.raises(Exception):
            client.get("/error")
        
        assert len(collector._response_times) == 1
        metric = collector._response_times[0]
        assert metric.status_code == 500
    
    def test_middleware_session_tracking(self, app, collector):
        """Test that middleware tracks user sessions."""
        app.add_middleware(ComprehensiveMetricsMiddleware, metrics_collector=collector)
        
        client = TestClient(app)
        
        # Make request with session header
        response = client.get("/test", headers={"X-Session-ID": "test-session"})
        
        assert response.status_code == 200
        assert "test-session" in collector._user_sessions
        
        session = collector._user_sessions["test-session"]
        assert session.total_requests == 1
        assert "/test" in session.endpoints_accessed


class TestMetricsIntegration:
    """Test the metrics integration utilities."""
    
    @pytest.fixture
    def collector(self):
        """Create and initialize metrics collector for integration."""
        with patch('src.multimodal_librarian.monitoring.comprehensive_metrics_collector.psutil'):
            collector = ComprehensiveMetricsCollector()
            collector._collection_active = False
            initialize_metrics_integration(collector)
            return collector
    
    def test_track_response_time_decorator(self, collector):
        """Test the response time tracking decorator."""
        @track_response_time("/api/test", "GET")
        async def test_function():
            await asyncio.sleep(0.01)  # 10ms
            return "result"
        
        # Run the decorated function
        result = asyncio.run(test_function())
        
        assert result == "result"
        assert len(collector._response_times) == 1
        
        metric = collector._response_times[0]
        assert metric.endpoint == "/api/test"
        assert metric.method == "GET"
        assert metric.status_code == 200
        assert metric.response_time_ms >= 10  # At least 10ms
    
    def test_track_search_performance_decorator(self, collector):
        """Test the search performance tracking decorator."""
        @track_search_performance("vector")
        async def search_function(query: str):
            await asyncio.sleep(0.01)
            return {"results": [1, 2, 3], "cache_hit": True}
        
        result = asyncio.run(search_function("test query"))
        
        assert result["results"] == [1, 2, 3]
        assert len(collector._search_performance) == 1
        
        metric = collector._search_performance[0]
        assert metric.query_text == "test query"
        assert metric.search_type == "vector"
        assert metric.results_count == 3
        assert metric.cache_hit is True
    
    def test_track_document_processing_decorator(self, collector):
        """Test the document processing tracking decorator."""
        @track_document_processing("extract")
        async def process_document(document_id: str, document_size_mb: float):
            await asyncio.sleep(0.01)
            return f"processed {document_id}"
        
        result = asyncio.run(process_document("doc123", 2.5))
        
        assert result == "processed doc123"
        assert len(collector._document_processing) == 1
        
        metric = collector._document_processing[0]
        assert metric.document_id == "doc123"
        assert metric.document_size_mb == 2.5
        assert metric.processing_stage == "extract"
        assert metric.success is True
    
    def test_metrics_context_manager(self, collector):
        """Test the metrics context manager."""
        async def test_context():
            async with MetricsContext("custom_operation", "TEST") as ctx:
                await asyncio.sleep(0.01)
                ctx.set_result_info(count=5)
        
        asyncio.run(test_context())
        
        assert len(collector._response_times) == 1
        metric = collector._response_times[0]
        assert metric.endpoint == "custom_operation"
        assert metric.method == "TEST"
        assert metric.status_code == 200
    
    def test_search_metrics_helper(self, collector):
        """Test the search metrics helper."""
        SearchMetricsHelper.record_search(
            query="helper test",
            search_type="hybrid",
            response_time_ms=300.0,
            results_count=7,
            cache_hit=False,
            user_id="user123"
        )
        
        assert len(collector._search_performance) == 1
        metric = collector._search_performance[0]
        assert metric.query_text == "helper test"
        assert metric.search_type == "hybrid"
        assert metric.response_time_ms == 300.0
        assert metric.results_count == 7
        assert metric.cache_hit is False
        assert metric.user_id == "user123"
    
    def test_document_metrics_helper(self, collector):
        """Test the document metrics helper."""
        DocumentMetricsHelper.record_processing(
            document_id="helper_doc",
            document_size_mb=1.5,
            processing_time_ms=2000.0,
            processing_stage="chunk",
            success=True
        )
        
        assert len(collector._document_processing) == 1
        metric = collector._document_processing[0]
        assert metric.document_id == "helper_doc"
        assert metric.document_size_mb == 1.5
        assert metric.processing_time_ms == 2000.0
        assert metric.processing_stage == "chunk"
        assert metric.success is True


class TestMetricsAPI:
    """Test the metrics API endpoints."""
    
    @pytest.fixture
    def app(self):
        """Create test app with metrics API."""
        from src.multimodal_librarian.api.routers.comprehensive_metrics import router
        
        app = FastAPI()
        app.include_router(router)
        return app
    
    def test_real_time_metrics_endpoint(self, app):
        """Test the real-time metrics endpoint."""
        client = TestClient(app)
        
        with patch('src.multimodal_librarian.api.routers.comprehensive_metrics.metrics_collector') as mock_collector:
            mock_collector.get_real_time_metrics.return_value = {
                "timestamp": "2024-01-01T00:00:00",
                "system_uptime_hours": 1.5,
                "response_time_metrics": {"avg_response_time_ms": 150.0}
            }
            
            response = client.get("/api/metrics/real-time")
            
            assert response.status_code == 200
            data = response.json()
            assert data["system_uptime_hours"] == 1.5
            assert data["response_time_metrics"]["avg_response_time_ms"] == 150.0
    
    def test_record_response_time_endpoint(self, app):
        """Test the record response time endpoint."""
        client = TestClient(app)
        
        with patch('src.multimodal_librarian.api.routers.comprehensive_metrics.metrics_collector') as mock_collector:
            response = client.post("/api/metrics/record/response-time", params={
                "endpoint": "/api/test",
                "method": "GET",
                "response_time_ms": 150.0,
                "status_code": 200,
                "user_id": "user123"
            })
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            
            mock_collector.record_response_time.assert_called_once_with(
                endpoint="/api/test",
                method="GET",
                response_time_ms=150.0,
                status_code=200,
                user_id="user123",
                user_agent=None,
                request_size_bytes=None,
                response_size_bytes=None
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])