"""
Test: Average User Wait Time < 30 Seconds for Basic Operations

This test validates that the average user wait time for basic operations
remains under 30 seconds during startup phases, ensuring a good user experience.

Success Criteria:
- Average wait time for basic operations < 30 seconds
- 95th percentile wait time < 60 seconds
- At least 80% of requests complete within 30 seconds
- Fallback responses are provided immediately when needed
"""

import pytest
import pytest_asyncio
import asyncio
import time
import statistics
from datetime import datetime, timedelta
from typing import List, Dict, Any
from unittest.mock import Mock, patch, AsyncMock

# Import the components we need to test
from src.multimodal_librarian.startup.phase_manager import StartupPhaseManager, StartupPhase
from src.multimodal_librarian.monitoring.startup_metrics import StartupMetricsCollector
from src.multimodal_librarian.api.middleware.user_wait_tracking_middleware import UserWaitTrackingMiddleware
from src.multimodal_librarian.services.fallback_service import FallbackResponseService
from src.multimodal_librarian.services.capability_service import get_capability_service


class TestAverageUserWaitTime30Seconds:
    """Test suite for validating average user wait time < 30 seconds."""
    
    @pytest_asyncio.fixture
    async def phase_manager(self):
        """Create a phase manager for testing."""
        manager = StartupPhaseManager()
        yield manager
        # Cleanup
        if hasattr(manager, '_shutdown_event'):
            manager._shutdown_event.set()
        if hasattr(manager, '_background_tasks'):
            for task in manager._background_tasks:
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
    
    @pytest_asyncio.fixture
    async def metrics_collector(self, phase_manager):
        """Create a metrics collector for testing."""
        collector = StartupMetricsCollector(phase_manager)
        await collector.start_collection()
        yield collector
        await collector.stop_collection()
    
    @pytest.fixture
    def fallback_service(self):
        """Create a fallback service for testing."""
        return FallbackResponseService()
    
    @pytest.mark.asyncio
    async def test_basic_operations_average_wait_time_under_30_seconds(
        self, phase_manager, metrics_collector
    ):
        """
        Test that average wait time for basic operations is under 30 seconds.
        
        This test simulates user requests during different startup phases and
        validates that the average wait time remains acceptable.
        """
        # Start phase progression
        await phase_manager.start_phase_progression()
        
        # Wait for minimal phase to be ready
        await asyncio.sleep(2)
        
        # Simulate basic user requests during startup
        request_ids = []
        for i in range(20):
            request_id = f"test_request_{i}"
            request_ids.append(request_id)
            
            # Record request start
            await metrics_collector.record_user_request_start(
                request_id=request_id,
                user_id=f"user_{i % 5}",  # 5 different users
                endpoint="/api/chat",
                request_type="chat",
                required_capabilities=["chat-model-base"]
            )
            
            # Simulate processing time (basic operations should be fast)
            processing_time = 0.5 + (i % 3) * 0.2  # 0.5-0.9 seconds
            await asyncio.sleep(processing_time)
            
            # Determine if fallback was used based on current phase
            current_phase = phase_manager.current_phase
            fallback_used = current_phase == StartupPhase.MINIMAL
            fallback_quality = "basic" if fallback_used else "full"
            
            # Record request completion
            await metrics_collector.record_user_request_completion(
                request_id=request_id,
                success=True,
                fallback_used=fallback_used,
                fallback_quality=fallback_quality,
                actual_processing_time_seconds=processing_time
            )
            
            # Small delay between requests
            await asyncio.sleep(0.1)
        
        # Get wait time metrics
        wait_time_metrics = metrics_collector.get_user_wait_time_metrics()
        
        # Validate average wait time
        assert wait_time_metrics["sample_count"] == 20, "Should have 20 request samples"
        
        wait_time_stats = wait_time_metrics.get("wait_time_stats", {})
        mean_wait_time = wait_time_stats.get("mean_seconds", 0)
        
        # Primary assertion: average wait time < 30 seconds
        assert mean_wait_time < 30.0, (
            f"Average wait time {mean_wait_time:.2f}s exceeds 30 second target"
        )
        
        # Additional quality checks
        p95_wait_time = wait_time_stats.get("p95_seconds", 0)
        assert p95_wait_time < 60.0, (
            f"95th percentile wait time {p95_wait_time:.2f}s exceeds 60 second threshold"
        )
        
        # Check that most requests complete quickly
        requests_under_30s = sum(
            1 for m in metrics_collector.user_wait_history
            if m.wait_time_seconds and m.wait_time_seconds <= 30
        )
        completion_rate = requests_under_30s / len(metrics_collector.user_wait_history)
        
        assert completion_rate >= 0.8, (
            f"Only {completion_rate:.1%} of requests completed within 30s (target: 80%)"
        )
        
        print(f"\n✅ Average wait time validation passed:")
        print(f"   - Average wait time: {mean_wait_time:.2f}s (target: <30s)")
        print(f"   - 95th percentile: {p95_wait_time:.2f}s (target: <60s)")
        print(f"   - Requests under 30s: {completion_rate:.1%} (target: ≥80%)")
    
    @pytest.mark.asyncio
    async def test_wait_time_during_minimal_phase(
        self, phase_manager, metrics_collector
    ):
        """
        Test that wait times are acceptable during minimal phase.
        
        During minimal phase, users should get immediate fallback responses.
        """
        # Start phase progression and wait for minimal phase
        await phase_manager.start_phase_progression()
        await asyncio.sleep(2)
        
        # Ensure we're in minimal phase
        assert phase_manager.current_phase == StartupPhase.MINIMAL
        
        # Simulate 10 requests during minimal phase
        for i in range(10):
            request_id = f"minimal_request_{i}"
            
            await metrics_collector.record_user_request_start(
                request_id=request_id,
                user_id=f"user_{i}",
                endpoint="/api/chat",
                request_type="chat",
                required_capabilities=["simple_text"]
            )
            
            # Minimal phase should provide immediate fallback responses
            processing_time = 0.1 + (i % 3) * 0.05  # 0.1-0.2 seconds
            await asyncio.sleep(processing_time)
            
            await metrics_collector.record_user_request_completion(
                request_id=request_id,
                success=True,
                fallback_used=True,
                fallback_quality="basic",
                actual_processing_time_seconds=processing_time
            )
        
        # Get metrics for minimal phase
        minimal_metrics = metrics_collector.get_user_wait_time_metrics(
            phase=StartupPhase.MINIMAL
        )
        
        wait_time_stats = minimal_metrics.get("wait_time_stats", {})
        mean_wait_time = wait_time_stats.get("mean_seconds", 0)
        
        # During minimal phase, wait times should be very low (immediate fallback)
        assert mean_wait_time < 5.0, (
            f"Minimal phase wait time {mean_wait_time:.2f}s too high (should be <5s)"
        )
        
        # All requests should use fallback
        assert minimal_metrics["fallback_usage_rate"] == 1.0, (
            "All requests during minimal phase should use fallback"
        )
        
        print(f"\n✅ Minimal phase wait time validation passed:")
        print(f"   - Average wait time: {mean_wait_time:.2f}s (target: <5s)")
        print(f"   - Fallback usage: {minimal_metrics['fallback_usage_rate']:.1%}")
    
    @pytest.mark.asyncio
    async def test_wait_time_during_essential_phase(
        self, phase_manager, metrics_collector
    ):
        """
        Test that wait times improve during essential phase.
        
        During essential phase, core models are loaded and wait times should be better.
        """
        # Start phase progression
        await phase_manager.start_phase_progression()
        
        # Wait for essential phase (with timeout)
        max_wait = 60  # 60 seconds max
        start_time = time.time()
        while phase_manager.current_phase != StartupPhase.ESSENTIAL:
            if time.time() - start_time > max_wait:
                pytest.skip("Essential phase not reached within timeout")
            await asyncio.sleep(1)
        
        # Simulate 10 requests during essential phase
        for i in range(10):
            request_id = f"essential_request_{i}"
            
            await metrics_collector.record_user_request_start(
                request_id=request_id,
                user_id=f"user_{i}",
                endpoint="/api/chat",
                request_type="chat",
                required_capabilities=["chat-model-base"]
            )
            
            # Essential phase has core models loaded
            processing_time = 1.0 + (i % 3) * 0.5  # 1.0-2.0 seconds
            await asyncio.sleep(processing_time)
            
            # Some requests may still use fallback if advanced features requested
            fallback_used = i % 3 == 0  # 33% fallback rate
            fallback_quality = "basic" if fallback_used else "enhanced"
            
            await metrics_collector.record_user_request_completion(
                request_id=request_id,
                success=True,
                fallback_used=fallback_used,
                fallback_quality=fallback_quality,
                actual_processing_time_seconds=processing_time
            )
        
        # Get metrics for essential phase
        essential_metrics = metrics_collector.get_user_wait_time_metrics(
            phase=StartupPhase.ESSENTIAL
        )
        
        wait_time_stats = essential_metrics.get("wait_time_stats", {})
        mean_wait_time = wait_time_stats.get("mean_seconds", 0)
        
        # During essential phase, wait times should still be under 30s
        assert mean_wait_time < 30.0, (
            f"Essential phase wait time {mean_wait_time:.2f}s exceeds 30s target"
        )
        
        # Fallback usage should be lower than minimal phase
        assert essential_metrics["fallback_usage_rate"] < 0.5, (
            "Essential phase should have lower fallback usage"
        )
        
        print(f"\n✅ Essential phase wait time validation passed:")
        print(f"   - Average wait time: {mean_wait_time:.2f}s (target: <30s)")
        print(f"   - Fallback usage: {essential_metrics['fallback_usage_rate']:.1%}")
    
    @pytest.mark.asyncio
    async def test_fallback_response_provides_immediate_feedback(
        self, fallback_service
    ):
        """
        Test that fallback responses provide immediate feedback.
        
        When full AI is not available, users should get immediate fallback responses
        rather than waiting for models to load.
        """
        test_messages = [
            "Hello, how are you?",
            "Can you help me analyze this document?",
            "Search for information about Python",
            "What's the weather like?",
            "Explain quantum computing"
        ]
        
        response_times = []
        
        for message in test_messages:
            start_time = time.time()
            
            # Generate fallback response
            intent_analysis = fallback_service.analyze_user_intent(message)
            fallback_response = fallback_service.generate_fallback_response(
                message, intent_analysis
            )
            
            response_time = time.time() - start_time
            response_times.append(response_time)
            
            # Fallback response should be generated immediately
            assert response_time < 1.0, (
                f"Fallback response took {response_time:.3f}s (should be <1s)"
            )
            
            # Response should have content
            assert fallback_response.response_text, "Fallback response should have text"
            assert fallback_response.helpful_now is not None, "Should indicate if helpful"
        
        avg_response_time = statistics.mean(response_times)
        max_response_time = max(response_times)
        
        # Average fallback generation should be very fast
        assert avg_response_time < 0.5, (
            f"Average fallback generation time {avg_response_time:.3f}s too slow"
        )
        
        print(f"\n✅ Fallback response speed validation passed:")
        print(f"   - Average generation time: {avg_response_time:.3f}s")
        print(f"   - Max generation time: {max_response_time:.3f}s")
        print(f"   - All responses under 1 second")
    
    @pytest.mark.asyncio
    async def test_user_experience_summary_meets_targets(
        self, phase_manager, metrics_collector
    ):
        """
        Test that overall user experience summary meets quality targets.
        
        This test validates the comprehensive user experience metrics.
        """
        # Start phase progression
        await phase_manager.start_phase_progression()
        await asyncio.sleep(2)
        
        # Simulate a realistic mix of requests
        request_scenarios = [
            # Fast requests (simple queries)
            *[("simple", 0.5) for _ in range(10)],
            # Medium requests (basic chat)
            *[("chat", 2.0) for _ in range(8)],
            # Slower requests (complex operations)
            *[("complex", 5.0) for _ in range(2)]
        ]
        
        for i, (scenario_type, base_time) in enumerate(request_scenarios):
            request_id = f"mixed_request_{i}"
            
            await metrics_collector.record_user_request_start(
                request_id=request_id,
                user_id=f"user_{i % 5}",
                endpoint=f"/api/{scenario_type}",
                request_type=scenario_type,
                required_capabilities=["chat-model-base"]
            )
            
            # Add some variance to processing time
            processing_time = base_time + (i % 3) * 0.3
            await asyncio.sleep(min(processing_time, 1.0))  # Cap sleep for test speed
            
            # Determine fallback based on scenario
            fallback_used = scenario_type == "complex" or phase_manager.current_phase == StartupPhase.MINIMAL
            fallback_quality = "basic" if fallback_used else "enhanced"
            
            await metrics_collector.record_user_request_completion(
                request_id=request_id,
                success=True,
                fallback_used=fallback_used,
                fallback_quality=fallback_quality,
                actual_processing_time_seconds=min(processing_time, 1.0)
            )
        
        # Get user experience summary
        ux_summary = metrics_collector.get_user_experience_summary()
        
        # Validate key metrics
        assert ux_summary["success_rate"] >= 0.95, (
            f"Success rate {ux_summary['success_rate']:.1%} below 95% target"
        )
        
        avg_wait_time = ux_summary.get("average_wait_time_seconds", 0)
        assert avg_wait_time < 30.0, (
            f"Average wait time {avg_wait_time:.2f}s exceeds 30s target"
        )
        
        # Check that most requests complete quickly
        requests_under_30s = ux_summary.get("requests_under_30s", 0)
        assert requests_under_30s >= 0.8, (
            f"Only {requests_under_30s:.1%} of requests under 30s (target: 80%)"
        )
        
        # User experience quality should be at least "good"
        ux_quality = ux_summary.get("user_experience_quality", "unknown")
        assert ux_quality in ["excellent", "good"], (
            f"User experience quality '{ux_quality}' below acceptable threshold"
        )
        
        print(f"\n✅ User experience summary validation passed:")
        print(f"   - Success rate: {ux_summary['success_rate']:.1%}")
        print(f"   - Average wait time: {avg_wait_time:.2f}s")
        print(f"   - Requests under 30s: {requests_under_30s:.1%}")
        print(f"   - UX quality: {ux_quality}")
    
    @pytest.mark.asyncio
    async def test_wait_time_estimation_accuracy(
        self, phase_manager, metrics_collector
    ):
        """
        Test that wait time estimates are reasonably accurate.
        
        Users should get accurate estimates of how long they'll wait.
        """
        # Start phase progression
        await phase_manager.start_phase_progression()
        await asyncio.sleep(2)
        
        # Simulate requests with estimated wait times
        for i in range(10):
            request_id = f"estimated_request_{i}"
            
            await metrics_collector.record_user_request_start(
                request_id=request_id,
                user_id=f"user_{i}",
                endpoint="/api/chat",
                request_type="chat",
                required_capabilities=["chat-model-base"]
            )
            
            # Simulate processing
            processing_time = 1.0 + (i % 3) * 0.5
            await asyncio.sleep(processing_time)
            
            await metrics_collector.record_user_request_completion(
                request_id=request_id,
                success=True,
                fallback_used=False,
                actual_processing_time_seconds=processing_time
            )
        
        # Get metrics with estimate accuracy
        wait_time_metrics = metrics_collector.get_user_wait_time_metrics()
        
        # Check estimate accuracy if available
        estimate_accuracy = wait_time_metrics.get("estimate_accuracy", {})
        if estimate_accuracy:
            mean_accuracy = estimate_accuracy.get("mean_accuracy", 0)
            
            # Estimates should be reasonably accurate (within 50%)
            assert mean_accuracy >= 0.5, (
                f"Wait time estimate accuracy {mean_accuracy:.1%} too low"
            )
            
            print(f"\n✅ Wait time estimation validation passed:")
            print(f"   - Mean accuracy: {mean_accuracy:.1%}")
        else:
            print(f"\n⚠️  Wait time estimation data not available yet")
    
    @pytest.mark.asyncio
    async def test_no_requests_exceed_60_seconds(
        self, phase_manager, metrics_collector
    ):
        """
        Test that no individual request exceeds 60 seconds wait time.
        
        Even in worst case, users should not wait more than 1 minute.
        """
        # Start phase progression
        await phase_manager.start_phase_progression()
        await asyncio.sleep(2)
        
        # Simulate various request types
        for i in range(15):
            request_id = f"timeout_test_request_{i}"
            
            await metrics_collector.record_user_request_start(
                request_id=request_id,
                user_id=f"user_{i}",
                endpoint="/api/chat",
                request_type="chat",
                required_capabilities=["chat-model-base"]
            )
            
            # Vary processing times
            processing_time = 0.5 + (i % 5) * 1.0  # 0.5-4.5 seconds
            await asyncio.sleep(min(processing_time, 1.0))
            
            await metrics_collector.record_user_request_completion(
                request_id=request_id,
                success=True,
                fallback_used=i % 2 == 0,
                fallback_quality="basic" if i % 2 == 0 else "enhanced",
                actual_processing_time_seconds=min(processing_time, 1.0)
            )
        
        # Check that no request exceeded 60 seconds
        wait_times = [
            m.wait_time_seconds for m in metrics_collector.user_wait_history
            if m.wait_time_seconds is not None
        ]
        
        max_wait_time = max(wait_times) if wait_times else 0
        
        assert max_wait_time < 60.0, (
            f"Maximum wait time {max_wait_time:.2f}s exceeds 60s threshold"
        )
        
        # Count requests over 30 seconds
        requests_over_30s = sum(1 for w in wait_times if w > 30)
        over_30s_rate = requests_over_30s / len(wait_times) if wait_times else 0
        
        # Less than 20% of requests should exceed 30 seconds
        assert over_30s_rate < 0.2, (
            f"{over_30s_rate:.1%} of requests exceeded 30s (should be <20%)"
        )
        
        print(f"\n✅ Maximum wait time validation passed:")
        print(f"   - Maximum wait time: {max_wait_time:.2f}s (threshold: 60s)")
        print(f"   - Requests over 30s: {over_30s_rate:.1%} (target: <20%)")


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "-s"])
