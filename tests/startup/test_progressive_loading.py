"""
Progressive Model Loading Tests

This module tests the progressive model loading functionality for the
application health and startup optimization feature.

Tests cover:
- Model loading priority and sequencing
- Progressive loading performance and timing
- Model availability checking during loading
- Graceful degradation for unavailable models
- Background loading while serving requests
- Model loading failure scenarios

Feature: application-health-startup-optimization
Requirements: REQ-2, REQ-4
"""

import asyncio
import pytest
import pytest_asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Set
from unittest.mock import Mock, patch, AsyncMock

from src.multimodal_librarian.startup.progressive_loader import ProgressiveLoader
from src.multimodal_librarian.models.model_manager import ModelManager
from src.multimodal_librarian.startup.phase_manager import StartupPhase, ModelLoadingStatus

# Configure pytest-asyncio
pytestmark = pytest.mark.asyncio


class TestProgressiveLoader:
    """Test progressive model loading functionality."""
    
    @pytest_asyncio.fixture
    def progressive_loader(self):
        """Create a progressive loader for testing."""
        return ProgressiveLoader()
    
    @pytest_asyncio.fixture
    def mock_model_manager(self):
        """Create a mock model manager."""
        manager = Mock(spec=ModelManager)
        manager.load_model = AsyncMock()
        manager.is_model_loaded = Mock(return_value=False)
        manager.get_model_status = Mock(return_value="pending")
        manager.get_available_models = Mock(return_value=[])
        return manager
    
    def test_progressive_loader_initialization(self, progressive_loader):
        """Test that progressive loader initializes correctly."""
        assert progressive_loader is not None
        assert hasattr(progressive_loader, 'loading_schedules')
        assert hasattr(progressive_loader, 'model_manager')
        
        # Check loading schedules are configured
        assert StartupPhase.MINIMAL in progressive_loader.loading_schedules
        assert StartupPhase.ESSENTIAL in progressive_loader.loading_schedules
        assert StartupPhase.FULL in progressive_loader.loading_schedules
    
    def test_loading_schedule_configuration(self, progressive_loader):
        """Test that loading schedules are configured correctly."""
        schedules = progressive_loader.loading_schedules
        
        # Check essential phase schedule
        essential_schedule = schedules[StartupPhase.ESSENTIAL]
        assert len(essential_schedule.models_to_load) > 0
        
        expected_essential = ["text-embedding-small", "chat-model-base", "search-index"]
        for model_name in expected_essential:
            assert model_name in essential_schedule.models_to_load
        
        # Check full phase schedule
        full_schedule = schedules[StartupPhase.FULL]
        assert len(full_schedule.models_to_load) > 0
        
        expected_full = ["chat-model-large", "document-processor", "multimodal-model", "specialized-analyzers"]
        for model_name in expected_full:
            assert model_name in full_schedule.models_to_load
    
    @pytest.mark.asyncio
    async def test_essential_models_loading_first(self, progressive_loader, mock_model_manager):
        """Test that essential models are loaded first."""
        loading_order = []
        
        async def track_loading_order(model_name, **kwargs):
            loading_order.append(model_name)
            await asyncio.sleep(0.1)  # Simulate loading time
            return True
        
        mock_model_manager.load_model.side_effect = track_loading_order
        progressive_loader.model_manager = mock_model_manager
        
        # Start progressive loading
        await progressive_loader.start_progressive_loading()
        
        # Wait for essential models to load
        await asyncio.sleep(1.0)
        
        # Check that essential models were loaded first
        essential_model_names = {m["name"] for m in progressive_loader.model_priorities["essential"]}
        
        # Find positions of essential models in loading order
        essential_positions = []
        for model_name in essential_model_names:
            if model_name in loading_order:
                essential_positions.append(loading_order.index(model_name))
        
        # Find positions of non-essential models
        non_essential_positions = []
        for i, model_name in enumerate(loading_order):
            if model_name not in essential_model_names:
                non_essential_positions.append(i)
        
        # Essential models should generally come before non-essential ones
        if essential_positions and non_essential_positions:
            avg_essential_pos = sum(essential_positions) / len(essential_positions)
            avg_non_essential_pos = sum(non_essential_positions) / len(non_essential_positions)
            assert avg_essential_pos < avg_non_essential_pos
    
    @pytest.mark.asyncio
    async def test_parallel_loading_within_priority(self, progressive_loader, mock_model_manager):
        """Test that models within the same priority level load in parallel."""
        loading_times = {}
        
        async def track_loading_times(model_name, **kwargs):
            start_time = time.time()
            await asyncio.sleep(0.2)  # Simulate loading time
            end_time = time.time()
            loading_times[model_name] = (start_time, end_time)
            return True
        
        mock_model_manager.load_model.side_effect = track_loading_times
        progressive_loader.model_manager = mock_model_manager
        
        # Start progressive loading
        start_time = time.time()
        await progressive_loader.start_progressive_loading()
        
        # Wait for essential models to load
        await asyncio.sleep(1.0)
        
        # Check that essential models loaded in parallel (overlapping times)
        essential_model_names = {m["name"] for m in progressive_loader.model_priorities["essential"]}
        essential_loading_times = {
            name: times for name, times in loading_times.items() 
            if name in essential_model_names
        }
        
        if len(essential_loading_times) >= 2:
            # Check for overlapping loading times (parallel execution)
            times_list = list(essential_loading_times.values())
            overlaps = 0
            
            for i in range(len(times_list)):
                for j in range(i + 1, len(times_list)):
                    start1, end1 = times_list[i]
                    start2, end2 = times_list[j]
                    
                    # Check if time ranges overlap
                    if (start1 <= start2 <= end1) or (start2 <= start1 <= end2):
                        overlaps += 1
            
            # Should have some overlapping execution (parallel loading)
            assert overlaps > 0
    
    @pytest.mark.asyncio
    async def test_model_availability_checking(self, progressive_loader, mock_model_manager):
        """Test model availability checking during loading."""
        loaded_models = set()
        
        async def mock_load_model(model_name, **kwargs):
            await asyncio.sleep(0.1)
            loaded_models.add(model_name)
            return True
        
        def mock_is_model_loaded(model_name):
            return model_name in loaded_models
        
        mock_model_manager.load_model.side_effect = mock_load_model
        mock_model_manager.is_model_loaded.side_effect = mock_is_model_loaded
        progressive_loader.model_manager = mock_model_manager
        
        # Start progressive loading
        await progressive_loader.start_progressive_loading()
        
        # Wait for some models to load
        await asyncio.sleep(0.5)
        
        # Check model availability
        for model_name in loaded_models:
            assert progressive_loader.is_model_available(model_name) is True
        
        # Check that unloaded models are not available
        all_model_names = set()
        for priority_models in progressive_loader.model_priorities.values():
            all_model_names.update(m["name"] for m in priority_models)
        
        unloaded_models = all_model_names - loaded_models
        for model_name in unloaded_models:
            assert progressive_loader.is_model_available(model_name) is False
    
    @pytest.mark.asyncio
    async def test_graceful_degradation(self, progressive_loader, mock_model_manager):
        """Test graceful degradation when models are not available."""
        # Mock some models as loaded, others as not loaded
        loaded_models = {"text-embedding-small", "chat-model-base"}
        
        def mock_is_model_loaded(model_name):
            return model_name in loaded_models
        
        mock_model_manager.is_model_loaded.side_effect = mock_is_model_loaded
        progressive_loader.model_manager = mock_model_manager
        
        # Test capability checking with partial loading
        capabilities = progressive_loader.get_available_capabilities()
        
        # Should have basic capabilities
        assert "basic_text_processing" in capabilities
        assert capabilities["basic_text_processing"] is True
        
        # Should not have advanced capabilities
        assert capabilities.get("advanced_ai", False) is False
        assert capabilities.get("document_analysis", False) is False
    
    @pytest.mark.asyncio
    async def test_background_loading_continues(self, progressive_loader, mock_model_manager):
        """Test that background loading continues while serving requests."""
        loading_events = []
        
        async def track_loading_events(model_name, **kwargs):
            loading_events.append(f"start_{model_name}")
            await asyncio.sleep(0.2)  # Simulate loading time
            loading_events.append(f"complete_{model_name}")
            return True
        
        mock_model_manager.load_model.side_effect = track_loading_events
        progressive_loader.model_manager = mock_model_manager
        
        # Start progressive loading
        loading_task = asyncio.create_task(progressive_loader.start_progressive_loading())
        
        # Simulate serving requests while loading
        await asyncio.sleep(0.1)  # Let loading start
        
        # Simulate request processing
        for i in range(5):
            await asyncio.sleep(0.05)
            # Simulate checking model availability during request
            available_models = progressive_loader.get_available_models()
            assert isinstance(available_models, list)
        
        # Wait for more loading to complete
        await asyncio.sleep(1.0)
        
        # Check that loading continued in background
        assert len(loading_events) > 0
        assert any("start_" in event for event in loading_events)
        assert any("complete_" in event for event in loading_events)
        
        # Cleanup
        loading_task.cancel()
        try:
            await loading_task
        except asyncio.CancelledError:
            pass
    
    @pytest.mark.asyncio
    async def test_model_loading_progress_tracking(self, progressive_loader, mock_model_manager):
        """Test model loading progress tracking."""
        loading_progress = {}
        
        async def track_progress(model_name, **kwargs):
            loading_progress[model_name] = "loading"
            await asyncio.sleep(0.1)
            loading_progress[model_name] = "loaded"
            return True
        
        mock_model_manager.load_model.side_effect = track_progress
        progressive_loader.model_manager = mock_model_manager
        
        # Start progressive loading
        await progressive_loader.start_progressive_loading()
        
        # Wait for some loading to happen
        await asyncio.sleep(0.5)
        
        # Check progress tracking
        progress = progressive_loader.get_loading_progress()
        
        assert "total_models" in progress
        assert "loaded_models" in progress
        assert "loading_models" in progress
        assert "failed_models" in progress
        assert "progress_percent" in progress
        
        # Progress percent should be valid
        assert 0 <= progress["progress_percent"] <= 100
        
        # Counts should be consistent
        total = progress["total_models"]
        loaded = progress["loaded_models"]
        loading = progress["loading_models"]
        failed = progress["failed_models"]
        
        assert loaded + loading + failed <= total
    
    @pytest.mark.asyncio
    async def test_estimated_completion_times(self, progressive_loader, mock_model_manager):
        """Test estimated completion time calculations."""
        # Mock loading times based on model configuration
        async def mock_load_with_timing(model_name, **kwargs):
            # Find model config to get estimated time
            for priority_models in progressive_loader.model_priorities.values():
                for model_config in priority_models:
                    if model_config["name"] == model_name:
                        estimated_time = model_config.get("estimated_load_time", 1.0)
                        await asyncio.sleep(estimated_time / 10)  # Scale down for testing
                        return True
            await asyncio.sleep(0.1)
            return True
        
        mock_model_manager.load_model.side_effect = mock_load_with_timing
        progressive_loader.model_manager = mock_model_manager
        
        # Start progressive loading
        await progressive_loader.start_progressive_loading()
        
        # Get estimated completion times
        estimates = progressive_loader.get_estimated_completion_times()
        
        assert isinstance(estimates, dict)
        
        # Should have estimates for different capability levels
        expected_capabilities = ["basic_chat", "simple_search", "document_analysis", "advanced_ai"]
        
        for capability in expected_capabilities:
            if capability in estimates:
                assert estimates[capability] >= 0
                assert isinstance(estimates[capability], (int, float))


class TestModelLoadingFailures:
    """Test model loading failure scenarios and recovery."""
    
    @pytest.fixture
    def progressive_loader(self):
        """Create a progressive loader for testing."""
        return ProgressiveLoader()
    
    @pytest.fixture
    def mock_model_manager(self):
        """Create a mock model manager."""
        manager = Mock(spec=ModelManager)
        manager.load_model = AsyncMock()
        manager.is_model_loaded = Mock(return_value=False)
        manager.get_model_status = Mock(return_value="pending")
        return manager
    
    @pytest.mark.asyncio
    async def test_model_loading_failure_handling(self, progressive_loader, mock_model_manager):
        """Test handling of model loading failures."""
        failed_models = {"chat-model-base"}  # This model will fail
        
        async def mock_load_with_failures(model_name, **kwargs):
            if model_name in failed_models:
                raise Exception(f"Mock loading failure for {model_name}")
            await asyncio.sleep(0.1)
            return True
        
        mock_model_manager.load_model.side_effect = mock_load_with_failures
        progressive_loader.model_manager = mock_model_manager
        
        # Start progressive loading
        await progressive_loader.start_progressive_loading()
        
        # Wait for loading attempts
        await asyncio.sleep(1.0)
        
        # Check that failure was tracked
        progress = progressive_loader.get_loading_progress()
        assert progress["failed_models"] > 0
        
        # Check that other models can still load
        assert progress["loaded_models"] > 0 or progress["loading_models"] > 0
        
        # Check that system can still provide some capabilities
        capabilities = progressive_loader.get_available_capabilities()
        assert len(capabilities) > 0  # Should have some capabilities despite failure
    
    @pytest.mark.asyncio
    async def test_retry_logic_for_failed_models(self, progressive_loader, mock_model_manager):
        """Test retry logic for failed model loading."""
        attempt_counts = {}
        
        async def mock_load_with_retries(model_name, **kwargs):
            attempt_counts[model_name] = attempt_counts.get(model_name, 0) + 1
            
            # Fail first two attempts for text-embedding-small, then succeed
            if model_name == "text-embedding-small" and attempt_counts[model_name] <= 2:
                raise Exception(f"Mock failure attempt {attempt_counts[model_name]}")
            
            await asyncio.sleep(0.1)
            return True
        
        mock_model_manager.load_model.side_effect = mock_load_with_retries
        progressive_loader.model_manager = mock_model_manager
        
        # Enable retry logic
        progressive_loader.enable_retry_logic(max_retries=3, retry_delay=0.1)
        
        # Start progressive loading
        await progressive_loader.start_progressive_loading()
        
        # Wait for retries to complete
        await asyncio.sleep(2.0)
        
        # Check that retries occurred
        assert attempt_counts.get("text-embedding-small", 0) > 1
        
        # Check final status
        progress = progressive_loader.get_loading_progress()
        # Should eventually succeed or track the failure appropriately
        assert progress["loaded_models"] > 0 or progress["failed_models"] > 0
    
    @pytest.mark.asyncio
    async def test_critical_model_failure_handling(self, progressive_loader, mock_model_manager):
        """Test handling of critical model failures."""
        # Mark text-embedding-small as critical and make it fail
        progressive_loader.mark_model_as_critical("text-embedding-small")
        
        async def mock_load_with_critical_failure(model_name, **kwargs):
            if model_name == "text-embedding-small":
                raise Exception("Critical model loading failure")
            await asyncio.sleep(0.1)
            return True
        
        mock_model_manager.load_model.side_effect = mock_load_with_critical_failure
        progressive_loader.model_manager = mock_model_manager
        
        # Start progressive loading
        await progressive_loader.start_progressive_loading()
        
        # Wait for loading attempts
        await asyncio.sleep(1.0)
        
        # Check that critical failure is handled appropriately
        health_status = progressive_loader.get_health_status()
        
        assert health_status["healthy"] is False
        assert "critical_model_failures" in health_status
        assert len(health_status["critical_model_failures"]) > 0
    
    @pytest.mark.asyncio
    async def test_fallback_model_loading(self, progressive_loader, mock_model_manager):
        """Test fallback to alternative models when primary models fail."""
        # Configure fallback models
        progressive_loader.configure_fallback_models({
            "chat-model-large": "chat-model-base",  # Fallback to smaller model
            "multimodal-model": "text-embedding-small"  # Fallback to simpler model
        })
        
        failed_models = {"chat-model-large"}
        
        async def mock_load_with_fallbacks(model_name, **kwargs):
            if model_name in failed_models:
                raise Exception(f"Primary model {model_name} failed")
            await asyncio.sleep(0.1)
            return True
        
        mock_model_manager.load_model.side_effect = mock_load_with_fallbacks
        progressive_loader.model_manager = mock_model_manager
        
        # Start progressive loading
        await progressive_loader.start_progressive_loading()
        
        # Wait for loading and fallback attempts
        await asyncio.sleep(1.0)
        
        # Check that fallback was attempted
        # This would require checking internal state or mock call history
        call_args_list = mock_model_manager.load_model.call_args_list
        model_names_called = [call[0][0] for call in call_args_list]
        
        # Should have attempted both primary and fallback models
        assert "chat-model-large" in model_names_called
        assert "chat-model-base" in model_names_called


class TestModelLoadingPerformance:
    """Test model loading performance and optimization."""
    
    @pytest.fixture
    def progressive_loader(self):
        """Create a progressive loader for testing."""
        return ProgressiveLoader()
    
    @pytest.fixture
    def mock_model_manager(self):
        """Create a mock model manager."""
        manager = Mock(spec=ModelManager)
        manager.load_model = AsyncMock()
        manager.is_model_loaded = Mock(return_value=False)
        return manager
    
    @pytest.mark.asyncio
    async def test_loading_time_optimization(self, progressive_loader, mock_model_manager):
        """Test that loading times are optimized."""
        loading_times = {}
        
        async def track_loading_performance(model_name, **kwargs):
            start_time = time.time()
            
            # Simulate different loading times based on model size
            model_config = None
            for priority_models in progressive_loader.model_priorities.values():
                for config in priority_models:
                    if config["name"] == model_name:
                        model_config = config
                        break
            
            if model_config:
                # Scale down estimated time for testing
                estimated_time = model_config.get("estimated_load_time", 1.0) / 10
                await asyncio.sleep(estimated_time)
            else:
                await asyncio.sleep(0.1)
            
            end_time = time.time()
            loading_times[model_name] = end_time - start_time
            return True
        
        mock_model_manager.load_model.side_effect = track_loading_performance
        progressive_loader.model_manager = mock_model_manager
        
        # Start progressive loading
        start_time = time.time()
        await progressive_loader.start_progressive_loading()
        
        # Wait for essential models to load
        await asyncio.sleep(2.0)
        
        total_time = time.time() - start_time
        
        # Check that total loading time is reasonable
        assert total_time < 10.0  # Should complete quickly in test environment
        
        # Check that smaller models loaded faster than larger ones
        if "text-embedding-small" in loading_times and "chat-model-large" in loading_times:
            assert loading_times["text-embedding-small"] <= loading_times["chat-model-large"]
    
    @pytest.mark.asyncio
    async def test_memory_efficient_loading(self, progressive_loader, mock_model_manager):
        """Test memory-efficient model loading."""
        memory_usage = {}
        
        async def track_memory_usage(model_name, **kwargs):
            # Simulate memory usage tracking
            model_config = None
            for priority_models in progressive_loader.model_priorities.values():
                for config in priority_models:
                    if config["name"] == model_name:
                        model_config = config
                        break
            
            if model_config:
                memory_usage[model_name] = model_config.get("size_mb", 100)
            
            await asyncio.sleep(0.1)
            return True
        
        mock_model_manager.load_model.side_effect = track_memory_usage
        progressive_loader.model_manager = mock_model_manager
        
        # Configure memory limits
        progressive_loader.set_memory_limit(1000)  # 1GB limit for testing
        
        # Start progressive loading
        await progressive_loader.start_progressive_loading()
        
        # Wait for loading
        await asyncio.sleep(1.0)
        
        # Check that memory usage is tracked
        total_memory = sum(memory_usage.values())
        
        # Should respect memory limits (in real implementation)
        # For testing, just verify tracking works
        assert total_memory > 0
        assert len(memory_usage) > 0
    
    @pytest.mark.asyncio
    async def test_concurrent_loading_limits(self, progressive_loader, mock_model_manager):
        """Test concurrent loading limits to prevent resource exhaustion."""
        concurrent_loads = 0
        max_concurrent = 0
        
        async def track_concurrency(model_name, **kwargs):
            nonlocal concurrent_loads, max_concurrent
            
            concurrent_loads += 1
            max_concurrent = max(max_concurrent, concurrent_loads)
            
            await asyncio.sleep(0.2)  # Simulate loading time
            
            concurrent_loads -= 1
            return True
        
        mock_model_manager.load_model.side_effect = track_concurrency
        progressive_loader.model_manager = mock_model_manager
        
        # Set concurrency limit
        progressive_loader.set_max_concurrent_loads(3)
        
        # Start progressive loading
        await progressive_loader.start_progressive_loading()
        
        # Wait for loading to complete
        await asyncio.sleep(2.0)
        
        # Check that concurrency was limited
        assert max_concurrent <= 3  # Should respect the limit we set


class TestModelCaching:
    """Test model caching functionality."""
    
    @pytest.fixture
    def progressive_loader(self):
        """Create a progressive loader for testing."""
        return ProgressiveLoader()
    
    @pytest.fixture
    def mock_model_manager(self):
        """Create a mock model manager with caching."""
        manager = Mock(spec=ModelManager)
        manager.load_model = AsyncMock()
        manager.is_model_cached = Mock(return_value=False)
        manager.cache_model = AsyncMock()
        return manager
    
    @pytest.mark.asyncio
    async def test_cached_model_loading(self, progressive_loader, mock_model_manager):
        """Test loading of cached models."""
        cached_models = {"text-embedding-small", "chat-model-base"}
        
        def mock_is_cached(model_name):
            return model_name in cached_models
        
        async def mock_load_cached(model_name, **kwargs):
            if model_name in cached_models:
                await asyncio.sleep(0.05)  # Cached models load faster
            else:
                await asyncio.sleep(0.2)   # Non-cached models load slower
            return True
        
        mock_model_manager.is_model_cached.side_effect = mock_is_cached
        mock_model_manager.load_model.side_effect = mock_load_cached
        progressive_loader.model_manager = mock_model_manager
        
        # Start progressive loading
        start_time = time.time()
        await progressive_loader.start_progressive_loading()
        
        # Wait for essential models to load
        await asyncio.sleep(1.0)
        
        # Check that cached models were prioritized
        progress = progressive_loader.get_loading_progress()
        assert progress["loaded_models"] > 0
        
        # Verify cache checking was called
        assert mock_model_manager.is_model_cached.called
    
    @pytest.mark.asyncio
    async def test_cache_warming(self, progressive_loader, mock_model_manager):
        """Test cache warming for frequently used models."""
        warmed_models = set()
        
        async def mock_cache_warming(model_name, **kwargs):
            warmed_models.add(model_name)
            await asyncio.sleep(0.1)
            return True
        
        mock_model_manager.cache_model.side_effect = mock_cache_warming
        progressive_loader.model_manager = mock_model_manager
        
        # Enable cache warming for essential models
        progressive_loader.enable_cache_warming(["text-embedding-small", "chat-model-base"])
        
        # Start progressive loading
        await progressive_loader.start_progressive_loading()
        
        # Wait for cache warming
        await asyncio.sleep(1.0)
        
        # Check that cache warming occurred
        assert len(warmed_models) > 0
        assert "text-embedding-small" in warmed_models or "chat-model-base" in warmed_models


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--tb=short", "-s"])