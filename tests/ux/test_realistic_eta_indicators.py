"""
Test Realistic ETA Indicators

This test validates that progress indicators show realistic time estimates
with confidence intervals and proper tracking.
"""

import pytest
import time
from src.multimodal_librarian.services.realistic_eta_calculator import (
    get_eta_calculator,
    RealisticETACalculator,
    LoadingMetrics,
    HistoricalLoadTime
)


class TestRealisticETACalculator:
    """Test the realistic ETA calculator."""
    
    def test_start_tracking(self):
        """Test starting to track a model load."""
        calculator = RealisticETACalculator()
        
        calculator.start_tracking("test-model", estimated_duration=30)
        
        assert "test-model" in calculator.active_loads
        assert calculator.active_loads["test-model"].estimated_duration == 30
    
    def test_update_progress(self):
        """Test updating progress for a model."""
        calculator = RealisticETACalculator()
        calculator.start_tracking("test-model", estimated_duration=30)
        
        calculator.update_progress("test-model", 25.0)
        
        metrics = calculator.active_loads["test-model"]
        assert metrics.actual_progress == 25.0
        assert len(metrics.progress_history) == 1
    
    def test_progress_velocity_calculation(self):
        """Test that velocity is calculated correctly."""
        calculator = RealisticETACalculator()
        calculator.start_tracking("test-model", estimated_duration=30)
        
        # Update progress twice to calculate velocity
        calculator.update_progress("test-model", 0.0)
        time.sleep(0.1)  # Small delay
        calculator.update_progress("test-model", 10.0)
        
        metrics = calculator.active_loads["test-model"]
        assert metrics.velocity > 0  # Should have positive velocity
    
    def test_smoothed_progress(self):
        """Test that progress smoothing works."""
        metrics = LoadingMetrics(start_time=time.time(), estimated_duration=30)
        
        # Add some progress data
        metrics.update_progress(10.0)
        time.sleep(0.01)
        metrics.update_progress(20.0)
        time.sleep(0.01)
        metrics.update_progress(30.0)
        
        smoothed = metrics.get_smoothed_progress()
        assert 10.0 <= smoothed <= 30.0  # Should be within range
    
    def test_estimate_remaining_time(self):
        """Test remaining time estimation."""
        metrics = LoadingMetrics(start_time=time.time(), estimated_duration=30)
        
        # Simulate progress
        metrics.update_progress(0.0)
        time.sleep(0.1)
        metrics.update_progress(50.0)  # 50% complete
        
        remaining = metrics.estimate_remaining_time()
        assert remaining >= 0  # Should be non-negative
        assert remaining < 30  # Should be less than original estimate
    
    def test_complete_tracking_records_history(self):
        """Test that completing tracking records historical data."""
        calculator = RealisticETACalculator()
        calculator.start_tracking("test-model", estimated_duration=30)
        
        # Simulate some progress
        calculator.update_progress("test-model", 100.0)
        
        # Complete tracking
        calculator.complete_tracking("test-model", success=True)
        
        assert "test-model" not in calculator.active_loads
        assert "test-model" in calculator.historical_data
        assert len(calculator.historical_data["test-model"].load_times) > 0
    
    def test_historical_load_time_statistics(self):
        """Test historical load time statistics calculation."""
        historical = HistoricalLoadTime(model_name="test-model")
        
        # Add some load times
        historical.add_load_time(10.0)
        historical.add_load_time(12.0)
        historical.add_load_time(11.0)
        
        assert historical.average_load_time is not None
        assert 10.0 <= historical.average_load_time <= 12.0
        assert historical.std_deviation is not None
    
    def test_get_realistic_eta_with_active_load(self):
        """Test getting realistic ETA for an actively loading model."""
        calculator = RealisticETACalculator()
        calculator.start_tracking("test-model", estimated_duration=30)
        calculator.update_progress("test-model", 50.0)
        
        eta, confidence = calculator.get_realistic_eta("test-model")
        
        assert eta >= 0
        assert 0.0 <= confidence <= 1.0
    
    def test_get_realistic_eta_with_historical_data(self):
        """Test getting realistic ETA using historical data."""
        calculator = RealisticETACalculator()
        
        # Add historical data
        calculator.historical_data["test-model"] = HistoricalLoadTime(model_name="test-model")
        calculator.historical_data["test-model"].add_load_time(25.0)
        calculator.historical_data["test-model"].add_load_time(30.0)
        
        eta, confidence = calculator.get_realistic_eta("test-model")
        
        assert eta > 0
        assert 0.0 <= confidence <= 1.0
        assert confidence < 1.0  # Should have lower confidence without active tracking
    
    def test_get_progress_with_eta(self):
        """Test getting comprehensive progress information."""
        calculator = RealisticETACalculator()
        calculator.start_tracking("test-model", estimated_duration=30)
        calculator.update_progress("test-model", 40.0)
        
        progress_info = calculator.get_progress_with_eta("test-model")
        
        assert progress_info["status"] == "loading"
        assert progress_info["progress_percent"] == 40.0
        assert "smoothed_progress" in progress_info
        assert "eta_seconds" in progress_info
        assert "eta_confidence" in progress_info
        assert "eta_range" in progress_info
        assert "velocity" in progress_info
    
    def test_eta_range_calculation(self):
        """Test ETA range calculation based on confidence."""
        calculator = RealisticETACalculator()
        
        # High confidence should have narrow range
        eta_range_high = calculator._calculate_eta_range(60.0, 0.9)
        range_width_high = eta_range_high["max_seconds"] - eta_range_high["min_seconds"]
        
        # Low confidence should have wider range
        eta_range_low = calculator._calculate_eta_range(60.0, 0.3)
        range_width_low = eta_range_low["max_seconds"] - eta_range_low["min_seconds"]
        
        assert range_width_low > range_width_high
    
    def test_system_load_factor_adjustment(self):
        """Test system load factor adjustment."""
        calculator = RealisticETACalculator()
        
        # Low resource usage
        calculator.update_system_load_factor(cpu_usage=0.3, memory_usage=0.4)
        assert calculator.system_load_factor == 1.0
        
        # High resource usage
        calculator.update_system_load_factor(cpu_usage=0.9, memory_usage=0.9)
        assert calculator.system_load_factor > 1.0
    
    def test_capability_eta_calculation(self):
        """Test ETA calculation for capabilities with dependencies."""
        calculator = RealisticETACalculator()
        
        # Set up some models with different ETAs
        calculator.start_tracking("model-a", estimated_duration=20)
        calculator.start_tracking("model-b", estimated_duration=40)
        
        # Get capability ETA (should be max of dependencies)
        cap_eta = calculator.get_capability_eta(
            "test-capability",
            dependencies=["model-a", "model-b"]
        )
        
        assert cap_eta["eta_seconds"] >= 20  # Should be at least the max
        assert "eta_confidence" in cap_eta
        assert "status" in cap_eta
    
    def test_format_eta_for_display(self):
        """Test ETA formatting for user display."""
        calculator = RealisticETACalculator()
        
        # Test various ETAs with different confidence levels
        assert "Ready now" in calculator.format_eta_for_display(0, 1.0)
        assert "seconds" in calculator.format_eta_for_display(30, 0.9)
        
        # 90 seconds with high confidence should show specific time (could be "1m 30s" or "1 minute")
        result_90_high = calculator.format_eta_for_display(90, 0.8)
        assert any(x in result_90_high for x in ["minute", "1m", "90"])
        
        # Lower confidence should show range or less specific time
        result_90_low = calculator.format_eta_for_display(90, 0.5)
        assert any(x in result_90_low for x in ["about", "1-2", "minutes"])
    
    def test_confidence_calculation(self):
        """Test confidence score calculation."""
        calculator = RealisticETACalculator()
        
        metrics = LoadingMetrics(start_time=time.time(), estimated_duration=30)
        
        # Add consistent progress data
        for i in range(5):
            metrics.update_progress(i * 10.0)
            time.sleep(0.01)
        
        confidence = calculator._calculate_confidence(metrics)
        
        assert 0.0 <= confidence <= 1.0
        # More data points should increase confidence
        assert confidence > 0.3


class TestETACalculatorIntegration:
    """Integration tests for ETA calculator with capability service."""
    
    def test_global_instance(self):
        """Test that global instance works correctly."""
        calc1 = get_eta_calculator()
        calc2 = get_eta_calculator()
        
        assert calc1 is calc2  # Should be same instance
    
    def test_multiple_models_tracking(self):
        """Test tracking multiple models simultaneously."""
        calculator = RealisticETACalculator()
        
        calculator.start_tracking("model-1", estimated_duration=20)
        calculator.start_tracking("model-2", estimated_duration=30)
        calculator.start_tracking("model-3", estimated_duration=40)
        
        assert len(calculator.active_loads) == 3
        
        # Update progress for each
        calculator.update_progress("model-1", 50.0)
        calculator.update_progress("model-2", 30.0)
        calculator.update_progress("model-3", 70.0)
        
        # Get all ETAs
        all_etas = calculator.get_all_etas()
        
        assert len(all_etas) == 3
        assert all(info["status"] == "loading" for info in all_etas.values())


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
