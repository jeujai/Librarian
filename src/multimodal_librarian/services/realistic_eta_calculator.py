"""
Realistic ETA Calculator

This module provides realistic time estimates for model loading and capability availability.
It tracks actual loading times, adjusts estimates based on system performance, and provides
accurate progress indicators.

Key Features:
- Historical load time tracking
- Dynamic ETA adjustment based on actual progress
- Resource-aware estimates
- Confidence intervals for estimates
- Progress smoothing to avoid jumpy indicators
"""

import time
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from collections import deque
import statistics

from ..logging_config import get_logger

logger = get_logger("realistic_eta_calculator")


@dataclass
class LoadingMetrics:
    """Metrics for a loading operation."""
    start_time: float
    estimated_duration: float
    actual_progress: float = 0.0  # 0-100
    last_update: float = field(default_factory=time.time)
    progress_history: deque = field(default_factory=lambda: deque(maxlen=10))
    velocity: float = 0.0  # Progress per second
    
    def update_progress(self, progress: float):
        """Update progress and calculate velocity."""
        current_time = time.time()
        time_delta = current_time - self.last_update
        
        if time_delta > 0:
            progress_delta = progress - self.actual_progress
            self.velocity = progress_delta / time_delta
            
        self.actual_progress = progress
        self.last_update = current_time
        self.progress_history.append((current_time, progress))
    
    def get_smoothed_progress(self) -> float:
        """Get smoothed progress to avoid jumpy indicators."""
        if len(self.progress_history) < 2:
            return self.actual_progress
        
        # Use exponential moving average
        alpha = 0.3  # Smoothing factor
        smoothed = self.progress_history[0][1]
        
        for _, progress in list(self.progress_history)[1:]:
            smoothed = alpha * progress + (1 - alpha) * smoothed
        
        return smoothed
    
    def estimate_remaining_time(self) -> float:
        """Estimate remaining time based on current velocity."""
        if self.actual_progress >= 100:
            return 0
        
        if self.velocity <= 0:
            # No progress yet, use original estimate
            elapsed = time.time() - self.start_time
            return max(0, self.estimated_duration - elapsed)
        
        # Calculate based on velocity
        remaining_progress = 100 - self.actual_progress
        estimated_remaining = remaining_progress / self.velocity
        
        # Apply confidence adjustment (be conservative)
        confidence_factor = min(1.0, len(self.progress_history) / 5)
        adjusted_remaining = estimated_remaining * (1 + (1 - confidence_factor) * 0.5)
        
        return max(0, adjusted_remaining)


@dataclass
class HistoricalLoadTime:
    """Historical load time data for a model."""
    model_name: str
    load_times: deque = field(default_factory=lambda: deque(maxlen=20))
    last_load_time: Optional[float] = None
    average_load_time: Optional[float] = None
    std_deviation: Optional[float] = None
    
    def add_load_time(self, duration: float):
        """Add a new load time measurement."""
        self.load_times.append(duration)
        self.last_load_time = duration
        self._recalculate_statistics()
    
    def _recalculate_statistics(self):
        """Recalculate average and standard deviation."""
        if len(self.load_times) >= 2:
            self.average_load_time = statistics.mean(self.load_times)
            self.std_deviation = statistics.stdev(self.load_times)
        elif len(self.load_times) == 1:
            self.average_load_time = self.load_times[0]
            self.std_deviation = 0
    
    def get_estimated_time(self, confidence_level: float = 0.8) -> float:
        """Get estimated load time with confidence level."""
        if not self.average_load_time:
            return None
        
        if not self.std_deviation or self.std_deviation == 0:
            return self.average_load_time
        
        # Add confidence interval (higher confidence = more conservative estimate)
        z_score = {0.5: 0, 0.8: 1.28, 0.9: 1.645, 0.95: 1.96}.get(confidence_level, 1.28)
        return self.average_load_time + (z_score * self.std_deviation)


class RealisticETACalculator:
    """Calculator for realistic time estimates."""
    
    def __init__(self):
        self.active_loads: Dict[str, LoadingMetrics] = {}
        self.historical_data: Dict[str, HistoricalLoadTime] = {}
        self.system_load_factor = 1.0  # Multiplier based on system load
        
        # Default estimates (will be refined with historical data)
        self.default_estimates = {
            "text-embedding-small": 5,
            "chat-model-base": 15,
            "search-index": 10,
            "document-processor": 30,
            "chat-model-large": 60,
            "multimodal-model": 120,
            "specialized-analyzers": 90
        }
    
    def start_tracking(self, model_name: str, estimated_duration: Optional[float] = None):
        """Start tracking a model load operation."""
        if estimated_duration is None:
            estimated_duration = self._get_estimated_duration(model_name)
        
        self.active_loads[model_name] = LoadingMetrics(
            start_time=time.time(),
            estimated_duration=estimated_duration
        )
        
        logger.info(f"Started tracking {model_name} with estimated duration {estimated_duration}s")
    
    def update_progress(self, model_name: str, progress: float):
        """Update progress for a model load operation."""
        if model_name not in self.active_loads:
            logger.warning(f"Attempted to update progress for untracked model: {model_name}")
            return
        
        metrics = self.active_loads[model_name]
        metrics.update_progress(progress)
        
        logger.debug(f"Updated {model_name} progress to {progress}% (velocity: {metrics.velocity:.2f}%/s)")
    
    def complete_tracking(self, model_name: str, success: bool = True):
        """Complete tracking and record historical data."""
        if model_name not in self.active_loads:
            logger.warning(f"Attempted to complete tracking for untracked model: {model_name}")
            return
        
        metrics = self.active_loads[model_name]
        actual_duration = time.time() - metrics.start_time
        
        if success:
            # Record historical data
            if model_name not in self.historical_data:
                self.historical_data[model_name] = HistoricalLoadTime(model_name=model_name)
            
            self.historical_data[model_name].add_load_time(actual_duration)
            logger.info(f"Completed {model_name} in {actual_duration:.2f}s (estimated: {metrics.estimated_duration:.2f}s)")
        
        # Clean up
        del self.active_loads[model_name]
    
    def get_realistic_eta(self, model_name: str) -> Tuple[float, float]:
        """
        Get realistic ETA for a model.
        
        Returns:
            Tuple of (eta_seconds, confidence_score)
        """
        # If actively loading, use real-time calculation
        if model_name in self.active_loads:
            metrics = self.active_loads[model_name]
            eta = metrics.estimate_remaining_time()
            
            # Confidence based on how much data we have
            confidence = min(1.0, len(metrics.progress_history) / 5)
            
            return (eta, confidence)
        
        # Otherwise, use historical data or defaults
        estimated_duration = self._get_estimated_duration(model_name)
        
        # Lower confidence for estimates without active tracking
        confidence = 0.5 if model_name in self.historical_data else 0.3
        
        return (estimated_duration, confidence)
    
    def get_progress_with_eta(self, model_name: str) -> Dict[str, any]:
        """Get comprehensive progress information with realistic ETA."""
        if model_name not in self.active_loads:
            eta, confidence = self.get_realistic_eta(model_name)
            return {
                "status": "pending",
                "progress_percent": 0,
                "smoothed_progress": 0,
                "eta_seconds": eta,
                "eta_confidence": confidence,
                "velocity": 0,
                "eta_range": self._calculate_eta_range(eta, confidence)
            }
        
        metrics = self.active_loads[model_name]
        eta = metrics.estimate_remaining_time()
        
        # Calculate confidence based on data quality
        confidence = self._calculate_confidence(metrics)
        
        return {
            "status": "loading",
            "progress_percent": metrics.actual_progress,
            "smoothed_progress": metrics.get_smoothed_progress(),
            "eta_seconds": eta,
            "eta_confidence": confidence,
            "velocity": metrics.velocity,
            "eta_range": self._calculate_eta_range(eta, confidence)
        }
    
    def _get_estimated_duration(self, model_name: str) -> float:
        """Get estimated duration for a model."""
        # Use historical data if available
        if model_name in self.historical_data:
            historical = self.historical_data[model_name]
            estimated = historical.get_estimated_time(confidence_level=0.8)
            if estimated:
                return estimated * self.system_load_factor
        
        # Fall back to defaults
        default = self.default_estimates.get(model_name, 30)
        return default * self.system_load_factor
    
    def _calculate_confidence(self, metrics: LoadingMetrics) -> float:
        """Calculate confidence score for ETA."""
        # Factors affecting confidence:
        # 1. Amount of progress data
        data_confidence = min(1.0, len(metrics.progress_history) / 5)
        
        # 2. Consistency of velocity
        if len(metrics.progress_history) >= 3:
            velocities = []
            for i in range(1, len(metrics.progress_history)):
                prev_time, prev_progress = metrics.progress_history[i-1]
                curr_time, curr_progress = metrics.progress_history[i]
                time_delta = curr_time - prev_time
                if time_delta > 0:
                    velocity = (curr_progress - prev_progress) / time_delta
                    velocities.append(velocity)
            
            if velocities:
                velocity_std = statistics.stdev(velocities) if len(velocities) > 1 else 0
                velocity_mean = statistics.mean(velocities)
                # Lower std deviation relative to mean = higher confidence
                velocity_confidence = 1.0 / (1.0 + (velocity_std / max(abs(velocity_mean), 0.1)))
            else:
                velocity_confidence = 0.5
        else:
            velocity_confidence = 0.5
        
        # 3. Progress amount (more progress = more confidence)
        progress_confidence = min(1.0, metrics.actual_progress / 50)
        
        # Combine factors
        overall_confidence = (
            data_confidence * 0.4 +
            velocity_confidence * 0.3 +
            progress_confidence * 0.3
        )
        
        return overall_confidence
    
    def _calculate_eta_range(self, eta: float, confidence: float) -> Dict[str, float]:
        """Calculate ETA range based on confidence."""
        # Lower confidence = wider range
        uncertainty_factor = (1 - confidence) * 0.5
        
        min_eta = max(0, eta * (1 - uncertainty_factor))
        max_eta = eta * (1 + uncertainty_factor)
        
        return {
            "min_seconds": min_eta,
            "max_seconds": max_eta,
            "best_estimate": eta
        }
    
    def update_system_load_factor(self, cpu_usage: float, memory_usage: float):
        """Update system load factor based on resource usage."""
        # Higher resource usage = slower loading
        # This is a simplified model
        avg_usage = (cpu_usage + memory_usage) / 2
        
        if avg_usage < 0.5:
            self.system_load_factor = 1.0
        elif avg_usage < 0.7:
            self.system_load_factor = 1.2
        elif avg_usage < 0.85:
            self.system_load_factor = 1.5
        else:
            self.system_load_factor = 2.0
        
        logger.debug(f"Updated system load factor to {self.system_load_factor} (CPU: {cpu_usage}, Memory: {memory_usage})")
    
    def get_capability_eta(self, capability_name: str, dependencies: List[str]) -> Dict[str, any]:
        """Get ETA for a capability based on its dependencies."""
        if not dependencies:
            return {
                "eta_seconds": 0,
                "eta_confidence": 1.0,
                "status": "available"
            }
        
        # Find the dependency that will take longest
        max_eta = 0
        min_confidence = 1.0
        all_loaded = True
        
        for dep in dependencies:
            eta, confidence = self.get_realistic_eta(dep)
            if eta > 0:
                all_loaded = False
                max_eta = max(max_eta, eta)
                min_confidence = min(min_confidence, confidence)
        
        if all_loaded:
            return {
                "eta_seconds": 0,
                "eta_confidence": 1.0,
                "status": "available"
            }
        
        return {
            "eta_seconds": max_eta,
            "eta_confidence": min_confidence,
            "status": "loading",
            "eta_range": self._calculate_eta_range(max_eta, min_confidence)
        }
    
    def format_eta_for_display(self, eta_seconds: float, confidence: float) -> str:
        """Format ETA for user-friendly display."""
        if eta_seconds <= 0:
            return "Ready now"
        
        # Round based on confidence and magnitude
        if confidence >= 0.8:
            # High confidence - be specific
            if eta_seconds < 60:
                return f"{int(eta_seconds)} seconds"
            elif eta_seconds < 120:
                minutes = int(eta_seconds / 60)
                seconds = int(eta_seconds % 60)
                if seconds < 10:
                    return f"{minutes} minute{'s' if minutes != 1 else ''}"
                return f"{minutes}m {seconds}s"
            else:
                minutes = int(eta_seconds / 60)
                return f"{minutes} minutes"
        else:
            # Lower confidence - be more general
            if eta_seconds < 30:
                return "less than 30 seconds"
            elif eta_seconds < 60:
                return "about 1 minute"
            elif eta_seconds < 120:
                return "1-2 minutes"
            elif eta_seconds < 300:
                return f"about {int(eta_seconds / 60)} minutes"
            else:
                return "several minutes"
    
    def get_all_etas(self) -> Dict[str, Dict[str, any]]:
        """Get ETAs for all tracked models."""
        result = {}
        
        # Active loads
        for model_name in self.active_loads:
            result[model_name] = self.get_progress_with_eta(model_name)
        
        # Historical data for models not currently loading
        for model_name in self.historical_data:
            if model_name not in result:
                eta, confidence = self.get_realistic_eta(model_name)
                result[model_name] = {
                    "status": "not_loading",
                    "estimated_duration": eta,
                    "confidence": confidence,
                    "historical_average": self.historical_data[model_name].average_load_time
                }
        
        return result


# Global instance
_eta_calculator = None

def get_eta_calculator() -> RealisticETACalculator:
    """Get the global ETA calculator instance."""
    global _eta_calculator
    if _eta_calculator is None:
        _eta_calculator = RealisticETACalculator()
    return _eta_calculator
