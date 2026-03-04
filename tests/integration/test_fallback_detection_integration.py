"""
Integration tests for fallback detection system.

Tests the complete fallback detection workflow including health monitoring,
automatic fallback triggers, and service switching.
"""

import pytest
import asyncio
import logging
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch
from typing import Dict, Any, List

from src.multimodal_librarian.components.vector_store.fallback_manager import (
    FallbackManager, FallbackConfig, ServiceStatus, FallbackReason, FallbackEvent
)
from src.multimodal_librarian.components.vector_store.search_service_enhanced import (
    SearchServiceWithFallback
)
from src.multimodal_librarian.components.vector_store.search_service import SearchRequest
from src.multimodal_librarian.models.core import SourceType, ContentType

logger = logging.getLogger(__name__)


class MockService:
    """Mock service for testing fallback detection."""
    
    def __init__(self, name: str, should_fail: bool = False, response_delay: float = 0.0):
        self.name = name
        self.should_fail = should_fail
        self.response_delay = response_delay
        self.call_count = 0
        self.performance_stats = {'total_searches': 0, 'avg_response_time': 0.0}
    
    async def health_check(self) -> bool:
        """Mock health check."""
        await asyncio.sleep(self.response_delay)
        self.call_count += 1
        
        if self.should_fail:
            raise Exception(f"Mock service {self.name} health check failed")
        
        return True
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Mock performance stats."""
        return self.performance_stats.copy()
    
    async def search(self, request):
        """Mock search method."""
        await asyncio.sleep(self.response_delay)
        self.call_count += 1
        
        if self.should_fail:
            raise Exception(f"Mock service {self.name} search failed")
        
        # Return mock response
        from src.multimodal_librarian.components.vector_store.search_service_simple import SimpleSearchResponse
        return SimpleSearchResponse(
            results=[],
            search_time_ms=self.response_delay * 1000,
            session_id="test-session"
        )


@pytest.fixture
def fallback_config():
    """Create test fallback configuration."""
    return FallbackConfig(
        health_check_interval_seconds=1,  # Fast for testing
        health_check_timeout_seconds=2,
        max_response_time_ms=500.0,
        max_error_rate=0.2,
        consecutive_failures_threshold=2,
        consecutive_successes_threshold=2,
        enable_notifications=True,
        notification_cooldown_minutes=0  # No cooldown for testing
    )


@pytest.fixture
def fallback_manager(fallback_config):
    """Create fallback manager for testing."""
    return FallbackManager(fallback_config)


@pytest.fixture
def mock_vector_store():
    """Create mock vector store."""
    mock_store = Mock()
    mock_store.health_check.return_value = True
    mock_store.semantic_search.return_value = []
    return mock_store


class TestFallbackManager:
    """Test fallback manager functionality."""
    
    @pytest.mark.asyncio
    async def test_service_registration(self, fallback_manager):
        """Test service registration."""
        # Create mock services
        primary_service = MockService("primary")
        fallback_service = MockService("fallback")
        
        # Register services
        fallback_manager.register_service("primary", primary_service, is_primary=True)
        fallback_manager.register_service("fallback", fallback_service, is_primary=False)
        
        # Verify registration
        assert "primary" in fallback_manager.services
        assert "fallback" in fallback_manager.services
        assert fallback_manager.services["primary"]["is_primary"] is True
        assert fallback_manager.services["fallback"]["is_primary"] is False
        
        # Verify metrics initialization
        assert "primary" in fallback_manager.service_metrics
        assert "fallback" in fallback_manager.service_metrics
        
        primary_metrics = fallback_manager.service_metrics["primary"]
        assert primary_metrics.service_name == "primary"
        assert primary_metrics.status == ServiceStatus.UNKNOWN
    
    @pytest.mark.asyncio
    async def test_health_monitoring_healthy_service(self, fallback_manager):
        """Test health monitoring for healthy service."""
        # Create healthy service
        healthy_service = MockService("healthy")
        fallback_manager.register_service("healthy", healthy_service)
        
        # Perform health check
        await fallback_manager._check_service_health("healthy")
        
        # Verify metrics
        metrics = fallback_manager.get_service_status("healthy")
        assert metrics.status == ServiceStatus.HEALTHY
        assert metrics.total_requests == 1
        assert metrics.failed_requests == 0
        assert metrics.error_rate == 0.0
        assert metrics.success_rate == 1.0
        assert healthy_service.call_count == 1
    
    @pytest.mark.asyncio
    async def test_health_monitoring_failed_service(self, fallback_manager):
        """Test health monitoring for failed service."""
        # Create failing service
        failing_service = MockService("failing", should_fail=True)
        fallback_service = MockService("fallback")
        
        fallback_manager.register_service("failing", failing_service, is_primary=True)
        fallback_manager.register_service("fallback", fallback_service)
        
        # Set up notification callback
        notifications = []
        fallback_manager.add_notification_callback(lambda event: notifications.append(event))
        
        # Perform health check
        await fallback_manager._check_service_health("failing")
        
        # Verify metrics
        metrics = fallback_manager.get_service_status("failing")
        assert metrics.status == ServiceStatus.FAILED
        assert metrics.total_requests == 1
        assert metrics.failed_requests == 1
        assert metrics.error_rate == 1.0
        assert metrics.success_rate == 0.0
        
        # Verify fallback activation
        assert "failing" in fallback_manager.active_fallbacks
        assert len(notifications) == 1
        assert notifications[0].service_name == "failing"
        assert notifications[0].reason == FallbackReason.HEALTH_CHECK_FAILED
    
    @pytest.mark.asyncio
    async def test_response_time_threshold(self, fallback_manager):
        """Test fallback trigger based on response time threshold."""
        # Create slow service
        slow_service = MockService("slow", response_delay=1.0)  # 1 second delay
        fallback_service = MockService("fallback")
        
        fallback_manager.register_service("slow", slow_service, is_primary=True)
        fallback_manager.register_service("fallback", fallback_service)
        
        # Set up notification callback
        notifications = []
        fallback_manager.add_notification_callback(lambda event: notifications.append(event))
        
        # Perform health check
        await fallback_manager._check_service_health("slow")
        
        # Verify fallback activation due to response time
        assert "slow" in fallback_manager.active_fallbacks
        assert len(notifications) == 1
        assert notifications[0].reason == FallbackReason.RESPONSE_TIME_EXCEEDED
    
    @pytest.mark.asyncio
    async def test_consecutive_failures_threshold(self, fallback_manager):
        """Test fallback trigger based on consecutive failures."""
        # Create intermittently failing service
        failing_service = MockService("intermittent")
        fallback_service = MockService("fallback")
        
        fallback_manager.register_service("intermittent", failing_service, is_primary=True)
        fallback_manager.register_service("fallback", fallback_service)
        
        # Set up notification callback
        notifications = []
        fallback_manager.add_notification_callback(lambda event: notifications.append(event))
        
        # Simulate consecutive failures
        failing_service.should_fail = True
        
        # First failure
        await fallback_manager._check_service_health("intermittent")
        assert "intermittent" not in fallback_manager.active_fallbacks  # Not yet
        
        # Second failure - should trigger fallback
        await fallback_manager._check_service_health("intermittent")
        assert "intermittent" in fallback_manager.active_fallbacks
        assert len(notifications) == 1
    
    @pytest.mark.asyncio
    async def test_service_recovery(self, fallback_manager):
        """Test service recovery from fallback."""
        # Create service that fails then recovers
        recovering_service = MockService("recovering", should_fail=True)
        fallback_service = MockService("fallback")
        
        fallback_manager.register_service("recovering", recovering_service, is_primary=True)
        fallback_manager.register_service("fallback", fallback_service)
        
        # Set up notification callback
        notifications = []
        fallback_manager.add_notification_callback(lambda event: notifications.append(event))
        
        # Trigger initial failure
        await fallback_manager._check_service_health("recovering")
        assert "recovering" in fallback_manager.active_fallbacks
        assert len(notifications) == 1
        
        # Service recovers
        recovering_service.should_fail = False
        
        # Simulate consecutive successes
        await fallback_manager._check_service_health("recovering")
        await fallback_manager._check_service_health("recovering")
        
        # Verify recovery
        assert "recovering" not in fallback_manager.active_fallbacks
        assert len(notifications) == 2  # Initial failure + recovery
        assert notifications[1].resolved is True
    
    @pytest.mark.asyncio
    async def test_monitoring_loop(self, fallback_manager):
        """Test the monitoring loop functionality."""
        # Create services
        healthy_service = MockService("healthy")
        failing_service = MockService("failing", should_fail=True)
        fallback_service = MockService("fallback")
        
        fallback_manager.register_service("healthy", healthy_service)
        fallback_manager.register_service("failing", failing_service, is_primary=True)
        fallback_manager.register_service("fallback", fallback_service)
        
        # Set up notification callback
        notifications = []
        fallback_manager.add_notification_callback(lambda event: notifications.append(event))
        
        # Start monitoring
        await fallback_manager.start_monitoring()
        
        # Wait for a few monitoring cycles
        await asyncio.sleep(3)
        
        # Stop monitoring
        await fallback_manager.stop_monitoring()
        
        # Verify monitoring occurred
        assert healthy_service.call_count > 0
        assert failing_service.call_count > 0
        
        # Verify fallback was triggered for failing service
        assert "failing" in fallback_manager.active_fallbacks
        assert len(notifications) > 0
    
    @pytest.mark.asyncio
    async def test_manual_fallback_and_recovery(self, fallback_manager):
        """Test manual fallback and recovery operations."""
        # Create services
        primary_service = MockService("primary")
        fallback_service = MockService("fallback")
        
        fallback_manager.register_service("primary", primary_service, is_primary=True)
        fallback_manager.register_service("fallback", fallback_service)
        
        # Set up notification callback
        notifications = []
        fallback_manager.add_notification_callback(lambda event: notifications.append(event))
        
        # Manual fallback
        success = await fallback_manager.manual_fallback("primary", "Testing manual fallback")
        assert success is True
        assert "primary" in fallback_manager.active_fallbacks
        assert len(notifications) == 1
        assert notifications[0].reason == FallbackReason.MANUAL_TRIGGER
        
        # Manual recovery
        success = await fallback_manager.manual_recovery("primary")
        assert success is True
        assert "primary" not in fallback_manager.active_fallbacks
        assert len(notifications) == 2
        assert notifications[1].resolved is True
    
    def test_fallback_statistics(self, fallback_manager):
        """Test fallback statistics collection."""
        # Create services
        primary_service = MockService("primary")
        fallback_service = MockService("fallback")
        
        fallback_manager.register_service("primary", primary_service, is_primary=True)
        fallback_manager.register_service("fallback", fallback_service)
        
        # Get initial statistics
        stats = fallback_manager.get_fallback_statistics()
        assert stats['total_fallback_events'] == 0
        assert stats['active_fallbacks'] == 0
        assert stats['registered_services'] == 2
        assert stats['healthy_services'] == 0  # Status unknown initially
        
        # Create a fallback event manually
        from src.multimodal_librarian.components.vector_store.fallback_manager import FallbackEvent
        event = FallbackEvent(
            event_id="test-event",
            timestamp=datetime.now(),
            service_name="primary",
            reason=FallbackReason.HEALTH_CHECK_FAILED,
            metrics=fallback_manager.service_metrics["primary"],
            fallback_service="fallback",
            message="Test event"
        )
        
        fallback_manager.active_fallbacks["primary"] = event
        fallback_manager.fallback_history.append(event)
        
        # Get updated statistics
        stats = fallback_manager.get_fallback_statistics()
        assert stats['total_fallback_events'] == 1
        assert stats['active_fallbacks'] == 1
        assert 'health_check_failed' in stats['reason_statistics']


class TestSearchServiceWithFallback:
    """Test enhanced search service with fallback management."""
    
    @pytest.mark.asyncio
    async def test_search_service_initialization(self, mock_vector_store, fallback_config):
        """Test search service initialization with fallback management."""
        service = SearchServiceWithFallback(mock_vector_store, fallback_config=fallback_config)
        
        # Verify initialization
        assert service.fallback_manager is not None
        assert service.primary_service is not None
        assert service.fallback_service is not None
        assert service.current_service_name == "primary"
        
        # Verify service registration
        assert "primary" in service.fallback_manager.services
        assert "fallback" in service.fallback_manager.services
    
    @pytest.mark.asyncio
    async def test_search_with_healthy_service(self, mock_vector_store, fallback_config):
        """Test search operation with healthy primary service."""
        service = SearchServiceWithFallback(mock_vector_store, fallback_config=fallback_config)
        
        # Create search request
        request = SearchRequest(
            query="test query",
            session_id="test-session"
        )
        
        # Mock the search method
        with patch.object(service.primary_service, 'search', new_callable=AsyncMock) as mock_search:
            from src.multimodal_librarian.components.vector_store.search_service_simple import SimpleSearchResponse
            mock_search.return_value = SimpleSearchResponse(
                results=[],
                search_time_ms=100.0,
                session_id="test-session"
            )
            
            # Perform search
            response = await service.search(request)
            
            # Verify search was performed with primary service
            assert mock_search.called
            assert response.session_id == "test-session"
            assert service.current_service_name == "primary"
            
            # Verify performance stats
            stats = service.get_performance_stats()
            assert stats['total_searches'] == 1
            assert stats['primary_searches'] == 1
            assert stats['fallback_searches'] == 0
    
    @pytest.mark.asyncio
    async def test_search_with_fallback_activation(self, mock_vector_store, fallback_config):
        """Test search operation with automatic fallback activation."""
        service = SearchServiceWithFallback(mock_vector_store, fallback_config=fallback_config)
        
        # Create search request
        request = SearchRequest(
            query="test query",
            session_id="test-session"
        )
        
        # Mock primary service to fail
        with patch.object(service.primary_service, 'search', new_callable=AsyncMock) as mock_primary:
            mock_primary.side_effect = Exception("Primary service failed")
            
            # Mock fallback service to succeed
            with patch.object(service.fallback_service, 'search', new_callable=AsyncMock) as mock_fallback:
                from src.multimodal_librarian.components.vector_store.search_service_simple import SimpleSearchResponse
                mock_fallback.return_value = SimpleSearchResponse(
                    results=[],
                    search_time_ms=200.0,
                    session_id="test-session"
                )
                
                # Perform search
                response = await service.search(request)
                
                # Verify fallback was used
                assert mock_primary.called
                assert mock_fallback.called
                assert response.session_id == "test-session"
                
                # Verify performance stats
                stats = service.get_performance_stats()
                assert stats['total_searches'] == 1
                assert stats['fallback_searches'] == 1
    
    @pytest.mark.asyncio
    async def test_service_switching_based_on_fallback_status(self, mock_vector_store, fallback_config):
        """Test automatic service switching based on fallback manager status."""
        service = SearchServiceWithFallback(mock_vector_store, fallback_config=fallback_config)
        
        # Initially using primary service
        assert service.current_service_name == "primary"
        
        # Manually trigger fallback
        await service.fallback_manager.manual_fallback("primary", "Test fallback")
        
        # Update current service (normally done during search)
        await service._update_current_service()
        
        # Verify switch to fallback service
        assert service.current_service_name == "fallback"
        assert service.performance_stats['service_switches'] == 1
        
        # Manually trigger recovery
        await service.fallback_manager.manual_recovery("primary")
        
        # Update current service again
        await service._update_current_service()
        
        # Verify switch back to primary service
        assert service.current_service_name == "primary"
        assert service.performance_stats['service_switches'] == 2
    
    @pytest.mark.asyncio
    async def test_comprehensive_analytics(self, mock_vector_store, fallback_config):
        """Test comprehensive analytics including fallback information."""
        service = SearchServiceWithFallback(mock_vector_store, fallback_config=fallback_config)
        
        # Trigger some activity
        await service.fallback_manager.manual_fallback("primary", "Test analytics")
        
        # Get analytics
        analytics = await service.get_search_analytics(24)
        
        # Verify analytics structure
        assert 'service_analytics' in analytics
        assert 'performance_stats' in analytics
        assert 'fallback_statistics' in analytics
        assert 'service_status' in analytics
        assert 'current_service' in analytics
        assert 'active_fallbacks' in analytics
        assert 'recent_fallback_history' in analytics
        
        # Verify fallback information
        assert analytics['current_service'] == "fallback"
        assert len(analytics['active_fallbacks']) == 1
        assert analytics['active_fallbacks'][0]['service_name'] == "primary"
    
    @pytest.mark.asyncio
    async def test_health_check(self, mock_vector_store, fallback_config):
        """Test health check functionality."""
        service = SearchServiceWithFallback(mock_vector_store, fallback_config=fallback_config)
        
        # Mock health checks
        with patch.object(service.primary_service, 'health_check', return_value=True):
            # Health check should pass
            assert service.health_check() is True
        
        with patch.object(service.primary_service, 'health_check', return_value=False):
            # Health check should fail
            assert service.health_check() is False
    
    @pytest.mark.asyncio
    async def test_manual_operations(self, mock_vector_store, fallback_config):
        """Test manual fallback and recovery operations."""
        service = SearchServiceWithFallback(mock_vector_store, fallback_config=fallback_config)
        
        # Manual fallback
        success = await service.manual_fallback("Testing manual operations")
        assert success is True
        assert service.fallback_manager.is_service_in_fallback("primary")
        
        # Manual recovery
        success = await service.manual_recovery()
        assert success is True
        assert not service.fallback_manager.is_service_in_fallback("primary")


@pytest.mark.asyncio
async def test_end_to_end_fallback_scenario(mock_vector_store, fallback_config):
    """Test complete end-to-end fallback scenario."""
    # Create enhanced search service
    service = SearchServiceWithFallback(mock_vector_store, fallback_config=fallback_config)
    
    # Start monitoring
    await service.start()
    
    try:
        # Create search request
        request = SearchRequest(
            query="test query",
            session_id="e2e-test"
        )
        
        # Mock primary service to be slow (trigger fallback)
        with patch.object(service.primary_service, 'search', new_callable=AsyncMock) as mock_primary:
            # Simulate slow response
            async def slow_search(*args, **kwargs):
                await asyncio.sleep(1.0)  # Exceeds threshold
                from src.multimodal_librarian.components.vector_store.search_service_simple import SimpleSearchResponse
                return SimpleSearchResponse(results=[], search_time_ms=1000.0, session_id="e2e-test")
            
            mock_primary.side_effect = slow_search
            
            # Mock fallback service
            with patch.object(service.fallback_service, 'search', new_callable=AsyncMock) as mock_fallback:
                from src.multimodal_librarian.components.vector_store.search_service_simple import SimpleSearchResponse
                mock_fallback.return_value = SimpleSearchResponse(
                    results=[], search_time_ms=50.0, session_id="e2e-test"
                )
                
                # Wait for monitoring to detect the issue
                await asyncio.sleep(2)
                
                # Perform search - should use fallback due to monitoring
                response = await service.search(request)
                
                # Verify fallback was activated
                assert service.fallback_manager.is_service_in_fallback("primary")
                assert service.current_service_name == "fallback"
                
                # Get comprehensive status
                status = service.get_service_status()
                assert status['current_service'] == "fallback"
                assert 'primary' in status['active_fallbacks']
                
                # Get analytics
                analytics = await service.get_search_analytics()
                assert analytics['fallback_statistics']['active_fallbacks'] == 1
                assert len(analytics['recent_fallback_history']) > 0
    
    finally:
        # Stop monitoring
        await service.stop()


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])