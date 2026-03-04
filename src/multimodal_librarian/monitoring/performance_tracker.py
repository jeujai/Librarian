"""
Performance Tracker Module for Multimodal Librarian Application

This module provides comprehensive performance tracking capabilities for the application,
with a focus on startup performance, model loading efficiency, and system resource utilization.

Key Features:
- Real-time performance monitoring during startup phases
- Resource utilization tracking (CPU, memory, I/O)
- Performance bottleneck identification
- Optimization recommendations based on performance data
- Integration with startup metrics for comprehensive analysis
"""

import asyncio
import time
import logging
import psutil
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
import statistics
import json

from .startup_metrics import StartupMetricsCollector, PhaseCompletionMetric
from ..startup.phase_manager import StartupPhase, StartupPhaseManager

logger = logging.getLogger(__name__)


@dataclass
class ResourceSnapshot:
    """Snapshot of system resource utilization at a point in time."""
    timestamp: datetime
    cpu_percent: float
    memory_percent: float
    memory_used_mb: float
    memory_available_mb: float
    disk_io_read_mb: float
    disk_io_write_mb: float
    network_bytes_sent: float
    network_bytes_recv: float
    process_count: int
    thread_count: int


@dataclass
class PerformanceMetric:
    """Performance metric with timing and resource information."""
    name: str
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    resource_snapshots: List[ResourceSnapshot] = field(default_factory=list)
    peak_cpu_percent: float = 0.0
    peak_memory_mb: float = 0.0
    avg_cpu_percent: float = 0.0
    avg_memory_mb: float = 0.0
    success: bool = True
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PerformanceAlert:
    """Performance alert for threshold violations."""
    alert_type: str
    severity: str  # "low", "medium", "high", "critical"
    message: str
    timestamp: datetime
    metric_name: str
    threshold_value: float
    actual_value: float
    recommendations: List[str] = field(default_factory=list)


class PerformanceThresholds:
    """Performance thresholds for alerting."""
    
    def __init__(self):
        # CPU thresholds (percentage)
        self.cpu_warning = 70.0
        self.cpu_critical = 90.0
        
        # Memory thresholds (percentage)
        self.memory_warning = 80.0
        self.memory_critical = 95.0
        
        # Phase duration thresholds (seconds)
        self.phase_duration_warning = {
            StartupPhase.MINIMAL: 45.0,    # Warning if > 45s
            StartupPhase.ESSENTIAL: 150.0,  # Warning if > 2.5 minutes
            StartupPhase.FULL: 420.0       # Warning if > 7 minutes
        }
        
        self.phase_duration_critical = {
            StartupPhase.MINIMAL: 90.0,    # Critical if > 1.5 minutes
            StartupPhase.ESSENTIAL: 300.0,  # Critical if > 5 minutes
            StartupPhase.FULL: 600.0       # Critical if > 10 minutes
        }
        
        # Model loading thresholds (seconds)
        self.model_loading_warning_multiplier = 1.5  # Warning if 1.5x estimated time
        self.model_loading_critical_multiplier = 3.0  # Critical if 3x estimated time


class PerformanceTracker:
    """
    Comprehensive performance tracker for startup and runtime performance monitoring.
    
    This class provides detailed performance tracking capabilities including resource
    utilization monitoring, bottleneck identification, and optimization recommendations.
    """
    
    def __init__(self, phase_manager: StartupPhaseManager, metrics_collector: Optional[StartupMetricsCollector] = None):
        """Initialize the performance tracker."""
        self.phase_manager = phase_manager
        self.metrics_collector = metrics_collector
        self.thresholds = PerformanceThresholds()
        
        # Tracking state
        self.tracking_start_time = datetime.now()
        self.is_tracking = False
        self._tracking_task: Optional[asyncio.Task] = None
        self._resource_monitoring_task: Optional[asyncio.Task] = None
        
        # Performance data
        self.performance_metrics: Dict[str, PerformanceMetric] = {}
        self.resource_history: List[ResourceSnapshot] = []
        self.performance_alerts: List[PerformanceAlert] = []
        
        # Resource monitoring configuration
        self.resource_sample_interval = 2.0  # seconds
        self.max_resource_history = 1000  # Keep last 1000 samples
        
        # Performance analysis
        self.bottlenecks_identified: List[Dict[str, Any]] = []
        self.optimization_recommendations: List[str] = []
        
        # User wait time tracking integration
        self._user_wait_time_thresholds = {
            "warning_seconds": 30.0,
            "critical_seconds": 60.0,
            "excessive_seconds": 120.0
        }
        
        # Callbacks for performance events
        self._alert_callbacks: List[Callable[[PerformanceAlert], None]] = []
        self._bottleneck_callbacks: List[Callable[[Dict[str, Any]], None]] = []
        
        logger.info("PerformanceTracker initialized")
    
    async def start_tracking(self) -> None:
        """Start performance tracking."""
        if self.is_tracking:
            logger.warning("Performance tracking already started")
            return
        
        self.is_tracking = True
        self.tracking_start_time = datetime.now()
        logger.info("Starting performance tracking")
        
        # Start resource monitoring
        self._resource_monitoring_task = asyncio.create_task(self._monitor_resources())
        
        # Start main tracking loop
        self._tracking_task = asyncio.create_task(self._tracking_loop())
        
        # Start tracking startup phases
        await self._start_phase_tracking()
    
    async def stop_tracking(self) -> None:
        """Stop performance tracking."""
        if not self.is_tracking:
            return
        
        self.is_tracking = False
        logger.info("Stopping performance tracking")
        
        # Cancel tracking tasks
        if self._tracking_task and not self._tracking_task.done():
            self._tracking_task.cancel()
            try:
                await self._tracking_task
            except asyncio.CancelledError:
                pass
        
        if self._resource_monitoring_task and not self._resource_monitoring_task.done():
            self._resource_monitoring_task.cancel()
            try:
                await self._resource_monitoring_task
            except asyncio.CancelledError:
                pass
        
        # Finalize any ongoing metrics
        await self._finalize_tracking()
        
        logger.info("Performance tracking stopped")
    
    async def _tracking_loop(self) -> None:
        """Main performance tracking loop."""
        try:
            while self.is_tracking:
                # Check for performance issues
                await self._check_performance_thresholds()
                
                # Analyze for bottlenecks
                await self._analyze_bottlenecks()
                
                # Update optimization recommendations
                await self._update_recommendations()
                
                # Wait before next check
                await asyncio.sleep(5.0)
                
        except asyncio.CancelledError:
            logger.info("Performance tracking loop cancelled")
            raise
        except Exception as e:
            logger.error(f"Error in performance tracking loop: {e}")
    
    async def _monitor_resources(self) -> None:
        """Monitor system resource utilization."""
        try:
            while self.is_tracking:
                snapshot = await self._capture_resource_snapshot()
                self.resource_history.append(snapshot)
                
                # Limit history size
                if len(self.resource_history) > self.max_resource_history:
                    self.resource_history = self.resource_history[-self.max_resource_history:]
                
                await asyncio.sleep(self.resource_sample_interval)
                
        except asyncio.CancelledError:
            logger.info("Resource monitoring cancelled")
            raise
        except Exception as e:
            logger.error(f"Error in resource monitoring: {e}")
    
    async def _capture_resource_snapshot(self) -> ResourceSnapshot:
        """Capture a snapshot of current resource utilization."""
        # Run resource collection in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_resource_snapshot)
    
    def _get_resource_snapshot(self) -> ResourceSnapshot:
        """Get current resource utilization (runs in thread pool)."""
        try:
            # CPU and memory
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            
            # Disk I/O
            disk_io = psutil.disk_io_counters()
            disk_read_mb = disk_io.read_bytes / (1024 * 1024) if disk_io else 0.0
            disk_write_mb = disk_io.write_bytes / (1024 * 1024) if disk_io else 0.0
            
            # Network I/O
            network_io = psutil.net_io_counters()
            network_sent = network_io.bytes_sent if network_io else 0.0
            network_recv = network_io.bytes_recv if network_io else 0.0
            
            # Process information
            process_count = len(psutil.pids())
            
            # Current process thread count
            current_process = psutil.Process()
            thread_count = current_process.num_threads()
            
            return ResourceSnapshot(
                timestamp=datetime.now(),
                cpu_percent=cpu_percent,
                memory_percent=memory.percent,
                memory_used_mb=memory.used / (1024 * 1024),
                memory_available_mb=memory.available / (1024 * 1024),
                disk_io_read_mb=disk_read_mb,
                disk_io_write_mb=disk_write_mb,
                network_bytes_sent=network_sent,
                network_bytes_recv=network_recv,
                process_count=process_count,
                thread_count=thread_count
            )
            
        except Exception as e:
            logger.error(f"Error capturing resource snapshot: {e}")
            # Return a minimal snapshot
            return ResourceSnapshot(
                timestamp=datetime.now(),
                cpu_percent=0.0,
                memory_percent=0.0,
                memory_used_mb=0.0,
                memory_available_mb=0.0,
                disk_io_read_mb=0.0,
                disk_io_write_mb=0.0,
                network_bytes_sent=0.0,
                network_bytes_recv=0.0,
                process_count=0,
                thread_count=0
            )
    
    async def _start_phase_tracking(self) -> None:
        """Start tracking startup phases."""
        # Track current phase
        current_phase = self.phase_manager.current_phase
        await self.start_metric_tracking(f"phase_{current_phase.value}")
        
        # Register callback for phase transitions
        def phase_callback():
            asyncio.create_task(self._handle_phase_transition())
        
        self.phase_manager.register_phase_callback(StartupPhase.ESSENTIAL, phase_callback)
        self.phase_manager.register_phase_callback(StartupPhase.FULL, phase_callback)
    
    async def _handle_phase_transition(self) -> None:
        """Handle phase transition for performance tracking."""
        current_phase = self.phase_manager.current_phase
        
        # End tracking for previous phase metrics
        for metric_name in list(self.performance_metrics.keys()):
            if metric_name.startswith("phase_") and not metric_name.endswith(current_phase.value):
                await self.end_metric_tracking(metric_name)
        
        # Start tracking new phase
        await self.start_metric_tracking(f"phase_{current_phase.value}")
    
    async def start_metric_tracking(self, metric_name: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Start tracking a performance metric."""
        if metric_name in self.performance_metrics:
            logger.warning(f"Metric {metric_name} is already being tracked")
            return
        
        metric = PerformanceMetric(
            name=metric_name,
            start_time=datetime.now(),
            metadata=metadata or {}
        )
        
        self.performance_metrics[metric_name] = metric
        logger.debug(f"Started tracking metric: {metric_name}")
    
    async def end_metric_tracking(self, metric_name: str, success: bool = True, error_message: Optional[str] = None) -> None:
        """End tracking a performance metric."""
        metric = self.performance_metrics.get(metric_name)
        if not metric:
            logger.warning(f"Metric {metric_name} not found for ending")
            return
        
        metric.end_time = datetime.now()
        metric.duration_seconds = (metric.end_time - metric.start_time).total_seconds()
        metric.success = success
        metric.error_message = error_message
        
        # Calculate resource statistics for this metric
        await self._calculate_metric_resource_stats(metric)
        
        logger.debug(f"Ended tracking metric: {metric_name} (duration: {metric.duration_seconds:.2f}s)")
    
    async def _calculate_metric_resource_stats(self, metric: PerformanceMetric) -> None:
        """Calculate resource statistics for a metric."""
        # Find resource snapshots within the metric timeframe
        relevant_snapshots = [
            snapshot for snapshot in self.resource_history
            if metric.start_time <= snapshot.timestamp <= (metric.end_time or datetime.now())
        ]
        
        if not relevant_snapshots:
            return
        
        metric.resource_snapshots = relevant_snapshots
        
        # Calculate statistics
        cpu_values = [s.cpu_percent for s in relevant_snapshots]
        memory_values = [s.memory_used_mb for s in relevant_snapshots]
        
        if cpu_values:
            metric.peak_cpu_percent = max(cpu_values)
            metric.avg_cpu_percent = statistics.mean(cpu_values)
        
        if memory_values:
            metric.peak_memory_mb = max(memory_values)
            metric.avg_memory_mb = statistics.mean(memory_values)
    
    async def _check_performance_thresholds(self) -> None:
        """Check for performance threshold violations."""
        if not self.resource_history:
            return
        
        latest_snapshot = self.resource_history[-1]
        
        # Check CPU thresholds
        if latest_snapshot.cpu_percent > self.thresholds.cpu_critical:
            await self._create_alert(
                "cpu_critical",
                "critical",
                f"CPU usage critically high: {latest_snapshot.cpu_percent:.1f}%",
                "cpu_usage",
                self.thresholds.cpu_critical,
                latest_snapshot.cpu_percent,
                ["Consider reducing concurrent operations", "Check for CPU-intensive processes", "Scale up CPU resources"]
            )
        elif latest_snapshot.cpu_percent > self.thresholds.cpu_warning:
            await self._create_alert(
                "cpu_warning",
                "medium",
                f"CPU usage high: {latest_snapshot.cpu_percent:.1f}%",
                "cpu_usage",
                self.thresholds.cpu_warning,
                latest_snapshot.cpu_percent,
                ["Monitor CPU usage trends", "Consider optimizing CPU-intensive operations"]
            )
        
        # Check memory thresholds
        if latest_snapshot.memory_percent > self.thresholds.memory_critical:
            await self._create_alert(
                "memory_critical",
                "critical",
                f"Memory usage critically high: {latest_snapshot.memory_percent:.1f}%",
                "memory_usage",
                self.thresholds.memory_critical,
                latest_snapshot.memory_percent,
                ["Free up memory immediately", "Check for memory leaks", "Scale up memory resources"]
            )
        elif latest_snapshot.memory_percent > self.thresholds.memory_warning:
            await self._create_alert(
                "memory_warning",
                "medium",
                f"Memory usage high: {latest_snapshot.memory_percent:.1f}%",
                "memory_usage",
                self.thresholds.memory_warning,
                latest_snapshot.memory_percent,
                ["Monitor memory usage trends", "Consider optimizing memory usage"]
            )
        
        # Check phase duration thresholds
        await self._check_phase_duration_thresholds()
        
        # Check user wait time thresholds
        await self._check_user_wait_time_thresholds()
    
    async def _check_phase_duration_thresholds(self) -> None:
        """Check for phase duration threshold violations."""
        current_phase = self.phase_manager.current_phase
        phase_start_time = self.phase_manager.phase_start_time
        current_time = datetime.now()
        phase_duration = (current_time - phase_start_time).total_seconds()
        
        warning_threshold = self.thresholds.phase_duration_warning.get(current_phase)
        critical_threshold = self.thresholds.phase_duration_critical.get(current_phase)
        
        if critical_threshold and phase_duration > critical_threshold:
            await self._create_alert(
                "phase_duration_critical",
                "critical",
                f"Phase {current_phase.value} duration critically long: {phase_duration:.1f}s",
                f"phase_{current_phase.value}_duration",
                critical_threshold,
                phase_duration,
                ["Check for stuck operations", "Review model loading progress", "Consider timeout adjustments"]
            )
        elif warning_threshold and phase_duration > warning_threshold:
            await self._create_alert(
                "phase_duration_warning",
                "medium",
                f"Phase {current_phase.value} duration longer than expected: {phase_duration:.1f}s",
                f"phase_{current_phase.value}_duration",
                warning_threshold,
                phase_duration,
                ["Monitor phase progress", "Check for performance bottlenecks"]
            )
    
    async def _check_user_wait_time_thresholds(self) -> None:
        """Check for user wait time threshold violations."""
        if not self.metrics_collector:
            return
        
        # Get active user requests
        active_requests = self.metrics_collector.get_active_user_requests()
        current_time = datetime.now()
        
        for request_id, request_info in active_requests.items():
            current_wait = request_info["current_wait_time_seconds"]
            estimated_wait = request_info.get("estimated_wait_time_seconds", 0)
            
            # Check for excessive wait times
            if current_wait > self._user_wait_time_thresholds["excessive_seconds"]:
                await self._create_alert(
                    "user_wait_excessive",
                    "critical",
                    f"User request {request_id} waiting excessively long: {current_wait:.1f}s",
                    "user_wait_time",
                    self._user_wait_time_thresholds["excessive_seconds"],
                    current_wait,
                    ["Check for stuck startup processes", "Review model loading status", "Consider request timeout"]
                )
            elif current_wait > self._user_wait_time_thresholds["critical_seconds"]:
                await self._create_alert(
                    "user_wait_critical",
                    "high",
                    f"User request {request_id} waiting critically long: {current_wait:.1f}s",
                    "user_wait_time",
                    self._user_wait_time_thresholds["critical_seconds"],
                    current_wait,
                    ["Monitor startup progress", "Check model loading bottlenecks"]
                )
            elif current_wait > self._user_wait_time_thresholds["warning_seconds"]:
                await self._create_alert(
                    "user_wait_warning",
                    "medium",
                    f"User request {request_id} waiting longer than expected: {current_wait:.1f}s",
                    "user_wait_time",
                    self._user_wait_time_thresholds["warning_seconds"],
                    current_wait,
                    ["Monitor user experience", "Review startup optimization"]
                )
            
            # Check for inaccurate estimates
            if (estimated_wait > 0 and current_wait > estimated_wait * 2.0 and 
                current_wait > self._user_wait_time_thresholds["warning_seconds"]):
                await self._create_alert(
                    "wait_estimate_inaccurate",
                    "medium",
                    f"Wait time estimate for {request_id} significantly inaccurate: estimated {estimated_wait:.1f}s, actual {current_wait:.1f}s",
                    "wait_time_estimation",
                    estimated_wait * 2.0,
                    current_wait,
                    ["Review wait time estimation algorithm", "Update model loading time estimates"]
                )
    
    async def _create_alert(self, alert_type: str, severity: str, message: str, 
                          metric_name: str, threshold_value: float, actual_value: float,
                          recommendations: List[str]) -> None:
        """Create a performance alert."""
        alert = PerformanceAlert(
            alert_type=alert_type,
            severity=severity,
            message=message,
            timestamp=datetime.now(),
            metric_name=metric_name,
            threshold_value=threshold_value,
            actual_value=actual_value,
            recommendations=recommendations
        )
        
        self.performance_alerts.append(alert)
        
        # Execute alert callbacks
        for callback in self._alert_callbacks:
            try:
                callback(alert)
            except Exception as e:
                logger.error(f"Error in alert callback: {e}")
        
        logger.warning(f"Performance alert: {alert.message}")
    
    async def _analyze_bottlenecks(self) -> None:
        """Analyze performance data for bottlenecks."""
        if len(self.resource_history) < 10:  # Need some history
            return
        
        # Analyze recent resource usage patterns
        recent_snapshots = self.resource_history[-20:]  # Last 20 samples
        
        # Check for sustained high resource usage
        cpu_values = [s.cpu_percent for s in recent_snapshots]
        memory_values = [s.memory_percent for s in recent_snapshots]
        
        avg_cpu = statistics.mean(cpu_values)
        avg_memory = statistics.mean(memory_values)
        
        # Identify bottlenecks
        bottlenecks = []
        
        if avg_cpu > 80:
            bottlenecks.append({
                "type": "cpu_bottleneck",
                "severity": "high" if avg_cpu > 90 else "medium",
                "description": f"Sustained high CPU usage: {avg_cpu:.1f}%",
                "recommendations": [
                    "Optimize CPU-intensive operations",
                    "Consider parallel processing",
                    "Review algorithm efficiency"
                ]
            })
        
        if avg_memory > 85:
            bottlenecks.append({
                "type": "memory_bottleneck",
                "severity": "high" if avg_memory > 95 else "medium",
                "description": f"Sustained high memory usage: {avg_memory:.1f}%",
                "recommendations": [
                    "Optimize memory usage",
                    "Implement memory pooling",
                    "Review data structures"
                ]
            })
        
        # Check for I/O bottlenecks
        if len(recent_snapshots) > 1:
            disk_read_rate = (recent_snapshots[-1].disk_io_read_mb - recent_snapshots[0].disk_io_read_mb) / len(recent_snapshots)
            if disk_read_rate > 100:  # > 100 MB/s average
                bottlenecks.append({
                    "type": "disk_io_bottleneck",
                    "severity": "medium",
                    "description": f"High disk I/O rate: {disk_read_rate:.1f} MB/s",
                    "recommendations": [
                        "Optimize disk access patterns",
                        "Consider SSD storage",
                        "Implement caching"
                    ]
                })
        
        # Check for user wait time bottlenecks
        if self.metrics_collector:
            user_wait_metrics = self.metrics_collector.get_user_wait_time_metrics(minutes_back=10)
            if user_wait_metrics.get("sample_count", 0) > 0:
                wait_stats = user_wait_metrics.get("wait_time_stats", {})
                avg_wait = wait_stats.get("mean_seconds", 0)
                p95_wait = wait_stats.get("p95_seconds", 0)
                
                if avg_wait > 45:
                    bottlenecks.append({
                        "type": "user_wait_time_bottleneck",
                        "severity": "high" if avg_wait > 90 else "medium",
                        "description": f"High average user wait time: {avg_wait:.1f}s",
                        "recommendations": [
                            "Optimize startup phase transitions",
                            "Implement better fallback responses",
                            "Review model loading priorities"
                        ]
                    })
                
                if p95_wait > 120:
                    bottlenecks.append({
                        "type": "user_wait_time_p95_bottleneck",
                        "severity": "high",
                        "description": f"95th percentile user wait time too high: {p95_wait:.1f}s",
                        "recommendations": [
                            "Investigate worst-case startup scenarios",
                            "Implement request queuing with better estimates",
                            "Consider parallel model loading"
                        ]
                    })
                
                fallback_rate = user_wait_metrics.get("fallback_usage_rate", 0)
                if fallback_rate > 0.7:
                    bottlenecks.append({
                        "type": "high_fallback_usage_bottleneck",
                        "severity": "medium",
                        "description": f"High fallback usage rate: {fallback_rate:.1%}",
                        "recommendations": [
                            "Optimize model loading to reduce fallback dependency",
                            "Improve fallback response quality",
                            "Consider pre-loading more models"
                        ]
                    })
        
        # Add new bottlenecks
        for bottleneck in bottlenecks:
            if bottleneck not in self.bottlenecks_identified:
                self.bottlenecks_identified.append(bottleneck)
                
                # Execute bottleneck callbacks
                for callback in self._bottleneck_callbacks:
                    try:
                        callback(bottleneck)
                    except Exception as e:
                        logger.error(f"Error in bottleneck callback: {e}")
                
                logger.info(f"Bottleneck identified: {bottleneck['description']}")
    
    async def _update_recommendations(self) -> None:
        """Update optimization recommendations based on performance data."""
        recommendations = []
        
        # Analyze phase performance
        if self.metrics_collector:
            phase_metrics = self.metrics_collector.get_phase_completion_metrics()
            if phase_metrics.get("sample_count", 0) > 0:
                efficiency = phase_metrics.get("efficiency_stats", {}).get("mean_score", 0)
                if efficiency < 70:
                    recommendations.append("Consider optimizing startup phase transitions")
                    recommendations.append("Review model loading priorities")
        
        # Analyze resource usage patterns
        if len(self.resource_history) > 10:
            recent_cpu = statistics.mean([s.cpu_percent for s in self.resource_history[-10:]])
            recent_memory = statistics.mean([s.memory_percent for s in self.resource_history[-10:]])
            
            if recent_cpu > 70:
                recommendations.append("Optimize CPU-intensive operations during startup")
            
            if recent_memory > 80:
                recommendations.append("Implement progressive model loading to reduce memory pressure")
                recommendations.append("Consider model compression techniques")
        
        # Analyze user wait time patterns
        if self.metrics_collector:
            user_experience = self.metrics_collector.get_user_experience_summary()
            if user_experience.get("total_user_requests", 0) > 0:
                avg_wait = user_experience.get("average_wait_time_seconds", 0)
                fallback_rate = user_experience.get("fallback_usage_rate", 0)
                quality = user_experience.get("user_experience_quality", "unknown")
                
                if quality in ["poor", "acceptable"]:
                    recommendations.append("Improve user experience by optimizing startup wait times")
                
                if avg_wait > 30:
                    recommendations.append("Reduce average user wait time through better startup optimization")
                
                if fallback_rate > 0.5:
                    recommendations.append("High fallback usage indicates need for faster model loading")
                
                requests_over_60s = user_experience.get("requests_over_60s", 0)
                if requests_over_60s > 0.1:  # More than 10% of requests wait over 60s
                    recommendations.append("Too many users waiting over 60s - review worst-case scenarios")
        
        # Update recommendations list (avoid duplicates)
        for rec in recommendations:
            if rec not in self.optimization_recommendations:
                self.optimization_recommendations.append(rec)
    
    async def _finalize_tracking(self) -> None:
        """Finalize performance tracking and complete any ongoing metrics."""
        for metric_name, metric in self.performance_metrics.items():
            if metric.end_time is None:
                await self.end_metric_tracking(metric_name)
    
    def register_alert_callback(self, callback: Callable[[PerformanceAlert], None]) -> None:
        """Register a callback for performance alerts."""
        self._alert_callbacks.append(callback)
    
    def register_bottleneck_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Register a callback for bottleneck detection."""
        self._bottleneck_callbacks.append(callback)
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get a comprehensive performance summary."""
        current_time = datetime.now()
        tracking_duration = (current_time - self.tracking_start_time).total_seconds()
        
        # Resource statistics
        resource_stats = {}
        if self.resource_history:
            cpu_values = [s.cpu_percent for s in self.resource_history]
            memory_values = [s.memory_percent for s in self.resource_history]
            
            resource_stats = {
                "cpu": {
                    "current": self.resource_history[-1].cpu_percent,
                    "average": statistics.mean(cpu_values),
                    "peak": max(cpu_values),
                    "min": min(cpu_values)
                },
                "memory": {
                    "current": self.resource_history[-1].memory_percent,
                    "average": statistics.mean(memory_values),
                    "peak": max(memory_values),
                    "min": min(memory_values)
                }
            }
        
        # Metric statistics
        completed_metrics = {name: metric for name, metric in self.performance_metrics.items() if metric.end_time}
        metric_stats = {}
        if completed_metrics:
            durations = [m.duration_seconds for m in completed_metrics.values() if m.duration_seconds]
            if durations:
                metric_stats = {
                    "total_metrics": len(completed_metrics),
                    "average_duration": statistics.mean(durations),
                    "total_duration": sum(durations),
                    "success_rate": sum(1 for m in completed_metrics.values() if m.success) / len(completed_metrics)
                }
        
        return {
            "tracking_duration_seconds": tracking_duration,
            "resource_statistics": resource_stats,
            "metric_statistics": metric_stats,
            "active_alerts": len([a for a in self.performance_alerts if (current_time - a.timestamp).total_seconds() < 300]),  # Last 5 minutes
            "total_alerts": len(self.performance_alerts),
            "bottlenecks_identified": len(self.bottlenecks_identified),
            "optimization_recommendations": len(self.optimization_recommendations),
            "resource_samples_collected": len(self.resource_history)
        }
    
    def get_recent_alerts(self, minutes: int = 10) -> List[PerformanceAlert]:
        """Get recent performance alerts."""
        cutoff_time = datetime.now() - timedelta(minutes=minutes)
        return [alert for alert in self.performance_alerts if alert.timestamp >= cutoff_time]
    
    def get_bottlenecks(self) -> List[Dict[str, Any]]:
        """Get identified performance bottlenecks."""
        return self.bottlenecks_identified.copy()
    
    def get_recommendations(self) -> List[str]:
        """Get optimization recommendations."""
        return self.optimization_recommendations.copy()
    
    def export_performance_data(self, format: str = "json") -> str:
        """Export performance data in the specified format."""
        data = {
            "tracking_session": {
                "start_time": self.tracking_start_time.isoformat(),
                "duration_seconds": (datetime.now() - self.tracking_start_time).total_seconds(),
                "is_active": self.is_tracking
            },
            "performance_summary": self.get_performance_summary(),
            "metrics": {
                name: {
                    "start_time": metric.start_time.isoformat(),
                    "end_time": metric.end_time.isoformat() if metric.end_time else None,
                    "duration_seconds": metric.duration_seconds,
                    "success": metric.success,
                    "peak_cpu_percent": metric.peak_cpu_percent,
                    "peak_memory_mb": metric.peak_memory_mb,
                    "avg_cpu_percent": metric.avg_cpu_percent,
                    "avg_memory_mb": metric.avg_memory_mb
                }
                for name, metric in self.performance_metrics.items()
            },
            "recent_alerts": [
                {
                    "type": alert.alert_type,
                    "severity": alert.severity,
                    "message": alert.message,
                    "timestamp": alert.timestamp.isoformat(),
                    "metric": alert.metric_name,
                    "threshold": alert.threshold_value,
                    "actual": alert.actual_value
                }
                for alert in self.get_recent_alerts(60)  # Last hour
            ],
            "bottlenecks": self.bottlenecks_identified,
            "recommendations": self.optimization_recommendations
        }
        
        if format.lower() == "json":
            return json.dumps(data, indent=2, default=str)
        else:
            raise ValueError(f"Unsupported export format: {format}")


# Convenience function for easy integration
async def track_performance(phase_manager: StartupPhaseManager, 
                          metrics_collector: Optional[StartupMetricsCollector] = None) -> PerformanceTracker:
    """
    Convenience function to start performance tracking.
    
    Args:
        phase_manager: The startup phase manager to track
        metrics_collector: Optional startup metrics collector for integration
        
    Returns:
        PerformanceTracker: The performance tracker instance
    """
    tracker = PerformanceTracker(phase_manager, metrics_collector)
    await tracker.start_tracking()
    
    # Enable bidirectional integration
    if metrics_collector:
        metrics_collector.set_performance_tracker(tracker)
    
    return tracker