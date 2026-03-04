"""
Startup Metrics Module for Multimodal Librarian Application

This module provides comprehensive tracking and analysis of startup phase completion times,
model loading performance, and overall startup efficiency metrics.

Key Features:
- Phase completion time tracking with detailed timing analysis
- Model loading performance metrics and optimization insights
- Startup efficiency scoring and trend analysis
- Historical data collection for performance optimization
- Real-time metrics for monitoring and alerting
"""

import asyncio
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import statistics
import json

from ..startup.phase_manager import StartupPhase, StartupPhaseManager, PhaseTransition, ModelLoadingStatus

logger = logging.getLogger(__name__)


@dataclass
class PhaseCompletionMetric:
    """Detailed metrics for a single phase completion."""
    phase: StartupPhase
    start_time: datetime
    end_time: datetime
    duration_seconds: float
    success: bool
    retry_count: int
    timeout_seconds: float
    efficiency_score: float  # 0-100, based on expected vs actual time
    dependencies_ready_time: Optional[float] = None  # Time to get dependencies ready
    models_loaded_count: int = 0
    models_failed_count: int = 0
    error_message: Optional[str] = None
    resource_usage: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelLoadingMetric:
    """Detailed metrics for model loading performance."""
    model_name: str
    priority: str
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    estimated_duration_seconds: float = 0.0
    actual_size_mb: Optional[float] = None
    estimated_size_mb: float = 0.0
    success: bool = False
    error_message: Optional[str] = None
    loading_efficiency: Optional[float] = None  # actual vs estimated time ratio
    memory_usage_mb: Optional[float] = None
    cache_hit: bool = False
    # Enhanced performance metrics
    memory_peak_mb: Optional[float] = None  # Peak memory during loading
    memory_baseline_mb: Optional[float] = None  # Memory before loading
    cpu_usage_percent: Optional[float] = None  # Average CPU during loading
    cpu_peak_percent: Optional[float] = None  # Peak CPU during loading
    disk_io_read_mb: Optional[float] = None  # Disk I/O during loading
    network_io_mb: Optional[float] = None  # Network I/O for downloads
    switching_strategy: Optional[str] = None  # Model switching strategy used
    cache_source: Optional[str] = None  # Cache source (local, efs, s3, etc.)
    retry_count: int = 0  # Number of retries needed
    timeout_occurred: bool = False  # Whether loading timed out
    concurrent_loads: int = 0  # Number of concurrent model loads
    queue_wait_time_seconds: Optional[float] = None  # Time spent waiting in queue
    initialization_time_seconds: Optional[float] = None  # Time for model initialization
    download_time_seconds: Optional[float] = None  # Time for model download
    load_from_cache_time_seconds: Optional[float] = None  # Time to load from cache


@dataclass
class UserWaitTimeMetric:
    """Metrics for user wait times during startup."""
    request_id: str
    user_id: Optional[str]
    endpoint: str
    request_start_time: datetime
    response_time: Optional[datetime] = None
    wait_time_seconds: Optional[float] = None
    startup_phase_at_request: StartupPhase = StartupPhase.MINIMAL
    required_capabilities: List[str] = field(default_factory=list)
    available_capabilities: List[str] = field(default_factory=list)
    fallback_used: bool = False
    fallback_quality: Optional[str] = None  # "basic", "enhanced", "full"
    request_type: str = "unknown"  # "chat", "search", "document", etc.
    success: bool = True
    error_message: Optional[str] = None
    queue_position: Optional[int] = None
    estimated_wait_time_seconds: Optional[float] = None
    actual_processing_time_seconds: Optional[float] = None


@dataclass
class HealthCheckLatencyMetric:
    """Metrics for health check latency during model loading.
    
    Tracks health check response times to detect GIL contention and event loop
    blocking during CPU-bound model loading operations.
    """
    timestamp: datetime
    response_time_ms: float
    success: bool
    startup_phase: StartupPhase = StartupPhase.MINIMAL
    models_loading: List[str] = field(default_factory=list)  # Models being loaded at time of check
    models_loaded_count: int = 0
    models_total_count: int = 0
    is_slow: bool = False  # True if response_time_ms > 100ms (GIL contention threshold)
    is_elevated: bool = False  # True if response_time_ms > 50ms
    endpoint: str = "/health/simple"  # Which health endpoint was called
    error_message: Optional[str] = None


@dataclass
class StartupSessionMetrics:
    """Complete metrics for a single startup session."""
    session_id: str
    startup_time: datetime
    completion_time: Optional[datetime] = None
    total_duration_seconds: Optional[float] = None
    final_phase_reached: StartupPhase = StartupPhase.MINIMAL
    phase_metrics: List[PhaseCompletionMetric] = field(default_factory=list)
    model_metrics: List[ModelLoadingMetric] = field(default_factory=list)
    user_wait_metrics: List[UserWaitTimeMetric] = field(default_factory=list)
    health_check_latency_metrics: List[HealthCheckLatencyMetric] = field(default_factory=list)
    overall_efficiency_score: float = 0.0
    success: bool = False
    error_count: int = 0
    retry_count: int = 0


class StartupMetricsCollector:
    """
    Collects and analyzes startup metrics for performance optimization and monitoring.
    
    This class tracks phase completion times, model loading performance, and provides
    insights for startup optimization.
    """
    
    def __init__(self, phase_manager: StartupPhaseManager):
        """Initialize the startup metrics collector."""
        self.phase_manager = phase_manager
        self.session_id = f"startup_{int(time.time())}"
        self.collection_start_time = datetime.now()
        
        # Current session metrics
        self.current_session = StartupSessionMetrics(
            session_id=self.session_id,
            startup_time=self.collection_start_time
        )
        
        # Historical data (in-memory for now, could be persisted)
        self.historical_sessions: List[StartupSessionMetrics] = []
        self.phase_completion_history: Dict[StartupPhase, List[PhaseCompletionMetric]] = {
            phase: [] for phase in StartupPhase
        }
        self.model_loading_history: Dict[str, List[ModelLoadingMetric]] = {}
        self.user_wait_history: List[UserWaitTimeMetric] = []
        self.health_check_latency_history: List[HealthCheckLatencyMetric] = []  # Health check latency tracking
        
        # Tracking state
        self._phase_start_times: Dict[StartupPhase, datetime] = {}
        self._model_start_times: Dict[str, datetime] = {}
        self._active_user_requests: Dict[str, UserWaitTimeMetric] = {}  # Track ongoing requests
        self._is_collecting = False
        self._collection_task: Optional[asyncio.Task] = None
        
        # Resource snapshots for enhanced metrics (shared with performance tracker)
        self._resource_snapshots: List = []
        self._performance_tracker = None  # Will be set by performance tracker
        
        # Performance baselines (can be updated based on historical data)
        self.phase_baselines = {
            StartupPhase.MINIMAL: 30.0,    # Expected 30 seconds
            StartupPhase.ESSENTIAL: 120.0,  # Expected 2 minutes
            StartupPhase.FULL: 300.0       # Expected 5 minutes
        }
        
        logger.info(f"StartupMetricsCollector initialized for session {self.session_id}")
    
    def set_performance_tracker(self, performance_tracker) -> None:
        """Set the performance tracker for resource snapshot integration."""
        self._performance_tracker = performance_tracker
        if hasattr(performance_tracker, 'resource_history'):
            self._resource_snapshots = performance_tracker.resource_history
        logger.debug("Performance tracker integration enabled for enhanced model loading metrics")
    
    async def start_collection(self) -> None:
        """Start collecting startup metrics."""
        if self._is_collecting:
            logger.warning("Metrics collection already started")
            return
        
        self._is_collecting = True
        logger.info("Starting startup metrics collection")
        
        # Start the collection task
        self._collection_task = asyncio.create_task(self._collect_metrics_loop())
        
        # Record initial phase
        await self._record_phase_start(self.phase_manager.current_phase)
    
    async def stop_collection(self) -> None:
        """Stop collecting startup metrics and finalize the session."""
        if not self._is_collecting:
            return
        
        self._is_collecting = False
        logger.info("Stopping startup metrics collection")
        
        # Cancel collection task
        if self._collection_task and not self._collection_task.done():
            self._collection_task.cancel()
            try:
                await self._collection_task
            except asyncio.CancelledError:
                pass
        
        # Finalize current session
        await self._finalize_session()
        
        # Add to historical data
        self.historical_sessions.append(self.current_session)
        
        logger.info(f"Metrics collection stopped. Session {self.session_id} finalized.")
    
    async def _collect_metrics_loop(self) -> None:
        """Main metrics collection loop."""
        last_phase = self.phase_manager.current_phase
        last_model_statuses = {}
        
        try:
            while self._is_collecting:
                current_status = self.phase_manager.get_current_status()
                
                # Check for phase transitions
                if current_status.current_phase != last_phase:
                    await self._record_phase_completion(last_phase)
                    await self._record_phase_start(current_status.current_phase)
                    last_phase = current_status.current_phase
                
                # Check for model loading updates
                for model_name, model_status in current_status.model_statuses.items():
                    last_status = last_model_statuses.get(model_name)
                    
                    # Model started loading
                    if (not last_status or last_status.status != "loading") and model_status.status == "loading":
                        await self._record_model_loading_start(model_name, model_status)
                    
                    # Model completed (success or failure)
                    elif (last_status and last_status.status == "loading") and model_status.status in ["loaded", "failed"]:
                        await self._record_model_loading_completion(model_name, model_status)
                
                last_model_statuses = current_status.model_statuses.copy()
                
                # Wait before next check
                await asyncio.sleep(1.0)
                
        except asyncio.CancelledError:
            logger.info("Metrics collection loop cancelled")
            raise
        except Exception as e:
            logger.error(f"Error in metrics collection loop: {e}")
    
    async def _record_phase_start(self, phase: StartupPhase) -> None:
        """Record the start of a phase."""
        start_time = datetime.now()
        self._phase_start_times[phase] = start_time
        logger.debug(f"Recorded phase start: {phase.value} at {start_time}")
    
    async def _record_phase_completion(self, phase: StartupPhase) -> None:
        """Record the completion of a phase."""
        end_time = datetime.now()
        start_time = self._phase_start_times.get(phase)
        
        if not start_time:
            logger.warning(f"No start time recorded for phase {phase.value}")
            return
        
        duration = (end_time - start_time).total_seconds()
        
        # Get phase transition details from phase manager
        phase_transitions = self.phase_manager.status.phase_transitions
        latest_transition = None
        for transition in reversed(phase_transitions):
            if transition.to_phase == phase:
                latest_transition = transition
                break
        
        # Calculate efficiency score
        baseline = self.phase_baselines.get(phase, duration)
        efficiency_score = min(100.0, (baseline / duration) * 100) if duration > 0 else 0.0
        
        # Count models loaded/failed during this phase
        models_loaded = 0
        models_failed = 0
        for model_status in self.phase_manager.status.model_statuses.values():
            if model_status.completed_at and start_time <= model_status.completed_at <= end_time:
                if model_status.status == "loaded":
                    models_loaded += 1
                elif model_status.status == "failed":
                    models_failed += 1
        
        # Create phase completion metric
        phase_metric = PhaseCompletionMetric(
            phase=phase,
            start_time=start_time,
            end_time=end_time,
            duration_seconds=duration,
            success=latest_transition.success if latest_transition else True,
            retry_count=latest_transition.retry_count if latest_transition else 0,
            timeout_seconds=self.phase_manager.phase_configs[phase].timeout_seconds,
            efficiency_score=efficiency_score,
            models_loaded_count=models_loaded,
            models_failed_count=models_failed,
            error_message=latest_transition.error_message if latest_transition else None
        )
        
        # Add to current session and history
        self.current_session.phase_metrics.append(phase_metric)
        self.phase_completion_history[phase].append(phase_metric)
        
        logger.info(f"Recorded phase completion: {phase.value} in {duration:.2f}s (efficiency: {efficiency_score:.1f}%)")
    
    async def _record_model_loading_start(self, model_name: str, model_status: ModelLoadingStatus) -> None:
        """Record the start of model loading."""
        if model_status.started_at:
            self._model_start_times[model_name] = model_status.started_at
            logger.debug(f"Recorded model loading start: {model_name}")
    
    async def _record_model_loading_completion(self, model_name: str, model_status: ModelLoadingStatus) -> None:
        """Record the completion of model loading."""
        if not model_status.completed_at or not model_status.started_at:
            logger.warning(f"Incomplete timing data for model {model_name}")
            return
        
        duration = model_status.duration_seconds or 0.0
        estimated_duration = model_status.estimated_load_time_seconds or 0.0
        
        # Calculate loading efficiency
        loading_efficiency = None
        if estimated_duration > 0:
            loading_efficiency = estimated_duration / duration if duration > 0 else 0.0
        
        # Get enhanced performance metrics from resource monitoring
        memory_metrics = await self._get_model_loading_memory_metrics(model_name, model_status)
        cpu_metrics = await self._get_model_loading_cpu_metrics(model_name, model_status)
        io_metrics = await self._get_model_loading_io_metrics(model_name, model_status)
        
        # Create model loading metric with enhanced data
        model_metric = ModelLoadingMetric(
            model_name=model_name,
            priority=model_status.priority,
            start_time=model_status.started_at,
            end_time=model_status.completed_at,
            duration_seconds=duration,
            estimated_duration_seconds=estimated_duration,
            estimated_size_mb=model_status.size_mb or 0.0,
            success=model_status.status == "loaded",
            error_message=model_status.error_message,
            loading_efficiency=loading_efficiency,
            cache_hit=getattr(model_status, 'cache_hit', False),
            # Enhanced performance metrics
            memory_usage_mb=memory_metrics.get('average_mb'),
            memory_peak_mb=memory_metrics.get('peak_mb'),
            memory_baseline_mb=memory_metrics.get('baseline_mb'),
            cpu_usage_percent=cpu_metrics.get('average_percent'),
            cpu_peak_percent=cpu_metrics.get('peak_percent'),
            disk_io_read_mb=io_metrics.get('disk_read_mb'),
            network_io_mb=io_metrics.get('network_mb'),
            switching_strategy=getattr(model_status, 'switching_strategy', None),
            cache_source=getattr(model_status, 'cache_source', None),
            retry_count=getattr(model_status, 'retry_count', 0),
            timeout_occurred=getattr(model_status, 'timeout_occurred', False),
            concurrent_loads=getattr(model_status, 'concurrent_loads', 0),
            queue_wait_time_seconds=getattr(model_status, 'queue_wait_time_seconds', None),
            initialization_time_seconds=getattr(model_status, 'initialization_time_seconds', None),
            download_time_seconds=getattr(model_status, 'download_time_seconds', None),
            load_from_cache_time_seconds=getattr(model_status, 'load_from_cache_time_seconds', None)
        )
        
        # Add to current session and history
        self.current_session.model_metrics.append(model_metric)
        if model_name not in self.model_loading_history:
            self.model_loading_history[model_name] = []
        self.model_loading_history[model_name].append(model_metric)
        
        status_text = "success" if model_metric.success else "failure"
        efficiency_text = f" (efficiency: {loading_efficiency:.2f}x)" if loading_efficiency else ""
        cache_text = " [CACHE HIT]" if model_metric.cache_hit else ""
        memory_text = f" (mem: {model_metric.memory_peak_mb:.1f}MB peak)" if model_metric.memory_peak_mb else ""
        
        logger.info(f"Recorded model loading {status_text}: {model_name} in {duration:.2f}s{efficiency_text}{cache_text}{memory_text}")
    
    async def _get_model_loading_memory_metrics(self, model_name: str, model_status: ModelLoadingStatus) -> Dict[str, Optional[float]]:
        """Get memory metrics for model loading period."""
        try:
            # Get resource snapshots during model loading period
            start_time = model_status.started_at
            end_time = model_status.completed_at or datetime.now()
            
            # Find baseline memory before loading started
            baseline_snapshots = [
                s for s in getattr(self, '_resource_snapshots', [])
                if s.timestamp < start_time and (start_time - s.timestamp).total_seconds() < 30
            ]
            baseline_memory = baseline_snapshots[-1].memory_used_mb if baseline_snapshots else None
            
            # Find memory snapshots during loading
            loading_snapshots = [
                s for s in getattr(self, '_resource_snapshots', [])
                if start_time <= s.timestamp <= end_time
            ]
            
            if not loading_snapshots:
                return {'baseline_mb': baseline_memory, 'average_mb': None, 'peak_mb': None}
            
            memory_values = [s.memory_used_mb for s in loading_snapshots]
            return {
                'baseline_mb': baseline_memory,
                'average_mb': statistics.mean(memory_values),
                'peak_mb': max(memory_values)
            }
            
        except Exception as e:
            logger.warning(f"Failed to get memory metrics for {model_name}: {e}")
            return {'baseline_mb': None, 'average_mb': None, 'peak_mb': None}
    
    async def _get_model_loading_cpu_metrics(self, model_name: str, model_status: ModelLoadingStatus) -> Dict[str, Optional[float]]:
        """Get CPU metrics for model loading period."""
        try:
            # Get resource snapshots during model loading period
            start_time = model_status.started_at
            end_time = model_status.completed_at or datetime.now()
            
            # Find CPU snapshots during loading
            loading_snapshots = [
                s for s in getattr(self, '_resource_snapshots', [])
                if start_time <= s.timestamp <= end_time
            ]
            
            if not loading_snapshots:
                return {'average_percent': None, 'peak_percent': None}
            
            cpu_values = [s.cpu_percent for s in loading_snapshots]
            return {
                'average_percent': statistics.mean(cpu_values),
                'peak_percent': max(cpu_values)
            }
            
        except Exception as e:
            logger.warning(f"Failed to get CPU metrics for {model_name}: {e}")
            return {'average_percent': None, 'peak_percent': None}
    
    async def _get_model_loading_io_metrics(self, model_name: str, model_status: ModelLoadingStatus) -> Dict[str, Optional[float]]:
        """Get I/O metrics for model loading period."""
        try:
            # Get resource snapshots during model loading period
            start_time = model_status.started_at
            end_time = model_status.completed_at or datetime.now()
            
            # Find I/O snapshots during loading
            loading_snapshots = [
                s for s in getattr(self, '_resource_snapshots', [])
                if start_time <= s.timestamp <= end_time
            ]
            
            if len(loading_snapshots) < 2:
                return {'disk_read_mb': None, 'network_mb': None}
            
            # Calculate I/O deltas
            first_snapshot = loading_snapshots[0]
            last_snapshot = loading_snapshots[-1]
            
            disk_read_delta = last_snapshot.disk_io_read_mb - first_snapshot.disk_io_read_mb
            network_delta = (last_snapshot.network_bytes_recv - first_snapshot.network_bytes_recv) / (1024 * 1024)
            
            return {
                'disk_read_mb': max(0, disk_read_delta),
                'network_mb': max(0, network_delta)
            }
            
        except Exception as e:
            logger.warning(f"Failed to get I/O metrics for {model_name}: {e}")
            return {'disk_read_mb': None, 'network_mb': None}
    
    async def _finalize_session(self) -> None:
        """Finalize the current metrics session."""
        self.current_session.completion_time = datetime.now()
        self.current_session.total_duration_seconds = (
            self.current_session.completion_time - self.current_session.startup_time
        ).total_seconds()
        
        # Determine final phase reached
        if self.current_session.phase_metrics:
            self.current_session.final_phase_reached = max(
                (metric.phase for metric in self.current_session.phase_metrics),
                key=lambda p: list(StartupPhase).index(p)
            )
        
        # Calculate overall efficiency score
        if self.current_session.phase_metrics:
            phase_scores = [metric.efficiency_score for metric in self.current_session.phase_metrics]
            self.current_session.overall_efficiency_score = statistics.mean(phase_scores)
        
        # Count errors and retries
        self.current_session.error_count = sum(
            1 for metric in self.current_session.phase_metrics if not metric.success
        ) + sum(
            1 for metric in self.current_session.model_metrics if not metric.success
        )
        
        self.current_session.retry_count = sum(
            metric.retry_count for metric in self.current_session.phase_metrics
        )
        
        # Mark session as successful if we reached at least essential phase
        self.current_session.success = (
            self.current_session.final_phase_reached in [StartupPhase.ESSENTIAL, StartupPhase.FULL] and
            self.current_session.error_count == 0
        )
        
        logger.info(f"Session finalized: {self.current_session.success}, "
                   f"final phase: {self.current_session.final_phase_reached.value}, "
                   f"efficiency: {self.current_session.overall_efficiency_score:.1f}%")
    
    async def record_user_request_start(self, request_id: str, user_id: Optional[str] = None, 
                                      endpoint: str = "unknown", request_type: str = "unknown",
                                      required_capabilities: Optional[List[str]] = None) -> None:
        """Record the start of a user request during startup."""
        if not self._is_collecting:
            return
        
        current_status = self.phase_manager.get_current_status()
        
        # Get currently available capabilities
        available_capabilities = []
        for model_name, model_status in current_status.model_statuses.items():
            if model_status.status == "loaded":
                available_capabilities.append(model_name)
        
        # Estimate wait time based on current phase and required capabilities
        estimated_wait_time = await self._estimate_user_wait_time(
            required_capabilities or [], available_capabilities
        )
        
        user_wait_metric = UserWaitTimeMetric(
            request_id=request_id,
            user_id=user_id,
            endpoint=endpoint,
            request_start_time=datetime.now(),
            startup_phase_at_request=current_status.current_phase,
            required_capabilities=required_capabilities or [],
            available_capabilities=available_capabilities,
            request_type=request_type,
            estimated_wait_time_seconds=estimated_wait_time
        )
        
        self._active_user_requests[request_id] = user_wait_metric
        logger.debug(f"Started tracking user request: {request_id} (estimated wait: {estimated_wait_time:.1f}s)")
    
    async def record_user_request_completion(self, request_id: str, success: bool = True, 
                                           error_message: Optional[str] = None,
                                           fallback_used: bool = False, 
                                           fallback_quality: Optional[str] = None,
                                           actual_processing_time_seconds: Optional[float] = None) -> None:
        """Record the completion of a user request."""
        user_wait_metric = self._active_user_requests.get(request_id)
        if not user_wait_metric:
            logger.warning(f"No active request found for ID: {request_id}")
            return
        
        completion_time = datetime.now()
        wait_time = (completion_time - user_wait_metric.request_start_time).total_seconds()
        
        # Update the metric
        user_wait_metric.response_time = completion_time
        user_wait_metric.wait_time_seconds = wait_time
        user_wait_metric.success = success
        user_wait_metric.error_message = error_message
        user_wait_metric.fallback_used = fallback_used
        user_wait_metric.fallback_quality = fallback_quality
        user_wait_metric.actual_processing_time_seconds = actual_processing_time_seconds
        
        # Add to session and history
        self.current_session.user_wait_metrics.append(user_wait_metric)
        self.user_wait_history.append(user_wait_metric)
        
        # Remove from active requests
        del self._active_user_requests[request_id]
        
        status_text = "success" if success else "failure"
        fallback_text = f" [FALLBACK: {fallback_quality}]" if fallback_used else ""
        phase_text = f" (phase: {user_wait_metric.startup_phase_at_request.value})"
        
        logger.info(f"User request {status_text}: {request_id} waited {wait_time:.2f}s{fallback_text}{phase_text}")
    
    async def _estimate_user_wait_time(self, required_capabilities: List[str], 
                                     available_capabilities: List[str]) -> float:
        """Estimate how long a user will wait based on required vs available capabilities."""
        if not required_capabilities:
            return 0.0  # No specific requirements, can respond immediately
        
        # Check if all required capabilities are available
        missing_capabilities = set(required_capabilities) - set(available_capabilities)
        if not missing_capabilities:
            return 0.0  # All capabilities available, no wait time
        
        # Estimate wait time based on current phase and missing capabilities
        current_phase = self.phase_manager.current_phase
        current_status = self.phase_manager.get_current_status()
        
        estimated_wait = 0.0
        
        # Base wait time estimates by phase
        phase_wait_estimates = {
            StartupPhase.MINIMAL: 30.0,    # Up to 30s to reach essential
            StartupPhase.ESSENTIAL: 180.0,  # Up to 3 minutes to reach full
            StartupPhase.FULL: 0.0         # Already at full capability
        }
        
        base_wait = phase_wait_estimates.get(current_phase, 0.0)
        
        # Adjust based on specific missing capabilities
        for capability in missing_capabilities:
            # Check if this capability is currently loading
            model_status = current_status.model_statuses.get(capability)
            if model_status and model_status.status == "loading":
                # Use estimated remaining time for this model
                if model_status.estimated_load_time_seconds and model_status.started_at:
                    elapsed = (datetime.now() - model_status.started_at).total_seconds()
                    remaining = max(0, model_status.estimated_load_time_seconds - elapsed)
                    estimated_wait = max(estimated_wait, remaining)
                else:
                    # Use default estimate
                    estimated_wait = max(estimated_wait, base_wait * 0.5)
            else:
                # Capability not yet loading, use phase-based estimate
                estimated_wait = max(estimated_wait, base_wait)
        
        return min(estimated_wait, 300.0)  # Cap at 5 minutes
    
    def get_user_wait_time_metrics(self, phase: Optional[StartupPhase] = None,
                                 request_type: Optional[str] = None,
                                 minutes_back: Optional[int] = None) -> Dict[str, Any]:
        """Get user wait time metrics with optional filtering."""
        # Filter metrics based on criteria
        filtered_metrics = self.user_wait_history.copy()
        
        if phase:
            filtered_metrics = [m for m in filtered_metrics if m.startup_phase_at_request == phase]
        
        if request_type:
            filtered_metrics = [m for m in filtered_metrics if m.request_type == request_type]
        
        if minutes_back:
            cutoff_time = datetime.now() - timedelta(minutes=minutes_back)
            filtered_metrics = [m for m in filtered_metrics if m.request_start_time >= cutoff_time]
        
        if not filtered_metrics:
            return {
                "sample_count": 0,
                "message": "No user wait time metrics available",
                "filters": {
                    "phase": phase.value if phase else None,
                    "request_type": request_type,
                    "minutes_back": minutes_back
                }
            }
        
        # Calculate statistics
        wait_times = [m.wait_time_seconds for m in filtered_metrics if m.wait_time_seconds is not None]
        success_count = sum(1 for m in filtered_metrics if m.success)
        fallback_count = sum(1 for m in filtered_metrics if m.fallback_used)
        
        # Processing time statistics (actual work vs wait time)
        processing_times = [m.actual_processing_time_seconds for m in filtered_metrics 
                          if m.actual_processing_time_seconds is not None]
        
        # Estimate accuracy (estimated vs actual wait times)
        estimate_accuracies = []
        for metric in filtered_metrics:
            if (metric.estimated_wait_time_seconds is not None and 
                metric.wait_time_seconds is not None and 
                metric.estimated_wait_time_seconds > 0):
                accuracy = min(1.0, metric.estimated_wait_time_seconds / metric.wait_time_seconds)
                estimate_accuracies.append(accuracy)
        
        result = {
            "sample_count": len(filtered_metrics),
            "success_rate": success_count / len(filtered_metrics),
            "fallback_usage_rate": fallback_count / len(filtered_metrics),
            "filters": {
                "phase": phase.value if phase else None,
                "request_type": request_type,
                "minutes_back": minutes_back
            }
        }
        
        if wait_times:
            result["wait_time_stats"] = {
                "mean_seconds": statistics.mean(wait_times),
                "median_seconds": statistics.median(wait_times),
                "min_seconds": min(wait_times),
                "max_seconds": max(wait_times),
                "p95_seconds": self._calculate_percentile(wait_times, 95),
                "p99_seconds": self._calculate_percentile(wait_times, 99),
                "std_dev_seconds": statistics.stdev(wait_times) if len(wait_times) > 1 else 0.0
            }
        
        if processing_times:
            result["processing_time_stats"] = {
                "mean_seconds": statistics.mean(processing_times),
                "median_seconds": statistics.median(processing_times),
                "max_seconds": max(processing_times)
            }
        
        if estimate_accuracies:
            result["estimate_accuracy"] = {
                "mean_accuracy": statistics.mean(estimate_accuracies),
                "median_accuracy": statistics.median(estimate_accuracies),
                "estimates_within_50_percent": sum(1 for a in estimate_accuracies if a >= 0.5) / len(estimate_accuracies)
            }
        
        # Phase distribution
        phase_distribution = {}
        for phase_enum in StartupPhase:
            count = sum(1 for m in filtered_metrics if m.startup_phase_at_request == phase_enum)
            if count > 0:
                phase_distribution[phase_enum.value] = count
        
        if phase_distribution:
            result["phase_distribution"] = phase_distribution
        
        # Request type distribution
        if not request_type:  # Only show if not filtering by request type
            type_distribution = {}
            for metric in filtered_metrics:
                type_distribution[metric.request_type] = type_distribution.get(metric.request_type, 0) + 1
            result["request_type_distribution"] = type_distribution
        
        # Fallback quality distribution
        fallback_quality_distribution = {}
        for metric in filtered_metrics:
            if metric.fallback_used and metric.fallback_quality:
                quality = metric.fallback_quality
                fallback_quality_distribution[quality] = fallback_quality_distribution.get(quality, 0) + 1
        
        if fallback_quality_distribution:
            result["fallback_quality_distribution"] = fallback_quality_distribution
        
        # Performance insights
        insights = []
        
        if wait_times:
            avg_wait = statistics.mean(wait_times)
            if avg_wait > 30:
                insights.append(f"High average wait time: {avg_wait:.1f}s - consider startup optimization")
            
            if max(wait_times) > 120:
                insights.append(f"Some users waited over 2 minutes - review worst-case scenarios")
            
            p95_wait = self._calculate_percentile(wait_times, 95)
            if p95_wait > 60:
                insights.append(f"95th percentile wait time is {p95_wait:.1f}s - affects user experience")
        
        if fallback_count / len(filtered_metrics) > 0.5:
            insights.append("High fallback usage - many requests during startup phases")
        
        if estimate_accuracies and statistics.mean(estimate_accuracies) < 0.7:
            insights.append("Wait time estimates are inaccurate - review estimation algorithm")
        
        if insights:
            result["performance_insights"] = insights
        
        return result
    
    def get_active_user_requests(self) -> Dict[str, Dict[str, Any]]:
        """Get information about currently active user requests."""
        active_requests = {}
        current_time = datetime.now()
        
        for request_id, metric in self._active_user_requests.items():
            current_wait_time = (current_time - metric.request_start_time).total_seconds()
            
            active_requests[request_id] = {
                "user_id": metric.user_id,
                "endpoint": metric.endpoint,
                "request_type": metric.request_type,
                "current_wait_time_seconds": current_wait_time,
                "estimated_wait_time_seconds": metric.estimated_wait_time_seconds,
                "startup_phase": metric.startup_phase_at_request.value,
                "required_capabilities": metric.required_capabilities,
                "available_capabilities": metric.available_capabilities,
                "is_overdue": (
                    metric.estimated_wait_time_seconds is not None and 
                    current_wait_time > metric.estimated_wait_time_seconds * 1.5
                )
            }
        
        return active_requests
    
    def get_user_experience_summary(self) -> Dict[str, Any]:
        """Get a comprehensive user experience summary during startup."""
        if not self.user_wait_history:
            return {
                "status": "no_data",
                "message": "No user wait time data available"
            }
        
        # Overall statistics
        total_requests = len(self.user_wait_history)
        successful_requests = sum(1 for m in self.user_wait_history if m.success)
        fallback_requests = sum(1 for m in self.user_wait_history if m.fallback_used)
        
        wait_times = [m.wait_time_seconds for m in self.user_wait_history if m.wait_time_seconds is not None]
        
        summary = {
            "total_user_requests": total_requests,
            "successful_requests": successful_requests,
            "success_rate": successful_requests / total_requests,
            "fallback_usage_rate": fallback_requests / total_requests,
            "active_requests": len(self._active_user_requests)
        }
        
        if wait_times:
            avg_wait = statistics.mean(wait_times)
            summary.update({
                "average_wait_time_seconds": avg_wait,
                "median_wait_time_seconds": statistics.median(wait_times),
                "max_wait_time_seconds": max(wait_times),
                "p95_wait_time_seconds": self._calculate_percentile(wait_times, 95),
                "requests_under_10s": sum(1 for w in wait_times if w <= 10) / len(wait_times),
                "requests_under_30s": sum(1 for w in wait_times if w <= 30) / len(wait_times),
                "requests_over_60s": sum(1 for w in wait_times if w > 60) / len(wait_times)
            })
            
            # User experience quality assessment
            if avg_wait < 10:
                summary["user_experience_quality"] = "excellent"
            elif avg_wait < 30:
                summary["user_experience_quality"] = "good"
            elif avg_wait < 60:
                summary["user_experience_quality"] = "acceptable"
            else:
                summary["user_experience_quality"] = "poor"
        
        # Phase-based analysis
        phase_analysis = {}
        for phase in StartupPhase:
            phase_metrics = [m for m in self.user_wait_history if m.startup_phase_at_request == phase]
            if phase_metrics:
                phase_wait_times = [m.wait_time_seconds for m in phase_metrics if m.wait_time_seconds is not None]
                if phase_wait_times:
                    phase_analysis[phase.value] = {
                        "request_count": len(phase_metrics),
                        "average_wait_seconds": statistics.mean(phase_wait_times),
                        "fallback_rate": sum(1 for m in phase_metrics if m.fallback_used) / len(phase_metrics)
                    }
        
        if phase_analysis:
            summary["phase_analysis"] = phase_analysis
        
        # Request type analysis
        type_analysis = {}
        request_types = set(m.request_type for m in self.user_wait_history)
        for req_type in request_types:
            type_metrics = [m for m in self.user_wait_history if m.request_type == req_type]
            type_wait_times = [m.wait_time_seconds for m in type_metrics if m.wait_time_seconds is not None]
            if type_wait_times:
                type_analysis[req_type] = {
                    "request_count": len(type_metrics),
                    "average_wait_seconds": statistics.mean(type_wait_times),
                    "success_rate": sum(1 for m in type_metrics if m.success) / len(type_metrics)
                }
        
        if type_analysis:
            summary["request_type_analysis"] = type_analysis
        
        return summary
    
    def get_phase_completion_metrics(self, phase: Optional[StartupPhase] = None) -> Dict[str, Any]:
        """Get phase completion time metrics."""
        if phase:
            metrics = self.phase_completion_history.get(phase, [])
            phase_name = phase.value
        else:
            # Aggregate all phases
            metrics = []
            for phase_metrics in self.phase_completion_history.values():
                metrics.extend(phase_metrics)
            phase_name = "all_phases"
        
        if not metrics:
            return {
                "phase": phase_name,
                "sample_count": 0,
                "message": "No metrics available"
            }
        
        durations = [m.duration_seconds for m in metrics]
        efficiency_scores = [m.efficiency_score for m in metrics]
        success_count = sum(1 for m in metrics if m.success)
        
        return {
            "phase": phase_name,
            "sample_count": len(metrics),
            "duration_stats": {
                "mean_seconds": statistics.mean(durations),
                "median_seconds": statistics.median(durations),
                "min_seconds": min(durations),
                "max_seconds": max(durations),
                "std_dev_seconds": statistics.stdev(durations) if len(durations) > 1 else 0.0
            },
            "efficiency_stats": {
                "mean_score": statistics.mean(efficiency_scores),
                "median_score": statistics.median(efficiency_scores),
                "min_score": min(efficiency_scores),
                "max_score": max(efficiency_scores)
            },
            "success_rate": success_count / len(metrics),
            "total_retries": sum(m.retry_count for m in metrics),
            "recent_trend": self._calculate_trend(durations[-10:]) if len(durations) >= 5 else "insufficient_data"
        }
    
    def get_model_loading_metrics(self, model_name: Optional[str] = None) -> Dict[str, Any]:
        """Get model loading performance metrics."""
        if model_name:
            metrics = self.model_loading_history.get(model_name, [])
            metric_name = model_name
        else:
            # Aggregate all models
            metrics = []
            for model_metrics in self.model_loading_history.values():
                metrics.extend(model_metrics)
            metric_name = "all_models"
        
        if not metrics:
            return {
                "model": metric_name,
                "sample_count": 0,
                "message": "No metrics available"
            }
        
        durations = [m.duration_seconds for m in metrics if m.duration_seconds is not None]
        efficiencies = [m.loading_efficiency for m in metrics if m.loading_efficiency is not None]
        success_count = sum(1 for m in metrics if m.success)
        cache_hits = sum(1 for m in metrics if m.cache_hit)
        
        # Enhanced performance metrics
        memory_peaks = [m.memory_peak_mb for m in metrics if m.memory_peak_mb is not None]
        cpu_peaks = [m.cpu_peak_percent for m in metrics if m.cpu_peak_percent is not None]
        disk_io_totals = [m.disk_io_read_mb for m in metrics if m.disk_io_read_mb is not None]
        network_io_totals = [m.network_io_mb for m in metrics if m.network_io_mb is not None]
        retry_counts = [m.retry_count for m in metrics]
        timeout_count = sum(1 for m in metrics if m.timeout_occurred)
        
        # Queue and timing breakdown
        queue_wait_times = [m.queue_wait_time_seconds for m in metrics if m.queue_wait_time_seconds is not None]
        init_times = [m.initialization_time_seconds for m in metrics if m.initialization_time_seconds is not None]
        download_times = [m.download_time_seconds for m in metrics if m.download_time_seconds is not None]
        cache_load_times = [m.load_from_cache_time_seconds for m in metrics if m.load_from_cache_time_seconds is not None]
        
        result = {
            "model": metric_name,
            "sample_count": len(metrics),
            "success_rate": success_count / len(metrics),
            "cache_hit_rate": cache_hits / len(metrics),
            "timeout_rate": timeout_count / len(metrics),
            "average_retry_count": statistics.mean(retry_counts) if retry_counts else 0.0,
            "loading_stats": {}
        }
        
        if durations:
            result["loading_stats"] = {
                "mean_duration_seconds": statistics.mean(durations),
                "median_duration_seconds": statistics.median(durations),
                "min_duration_seconds": min(durations),
                "max_duration_seconds": max(durations),
                "std_dev_seconds": statistics.stdev(durations) if len(durations) > 1 else 0.0,
                "p95_duration_seconds": self._calculate_percentile(durations, 95),
                "p99_duration_seconds": self._calculate_percentile(durations, 99)
            }
        
        if efficiencies:
            result["efficiency_stats"] = {
                "mean_efficiency": statistics.mean(efficiencies),
                "median_efficiency": statistics.median(efficiencies),
                "min_efficiency": min(efficiencies),
                "max_efficiency": max(efficiencies),
                "efficiency_trend": self._calculate_trend(efficiencies[-10:]) if len(efficiencies) >= 5 else "insufficient_data"
            }
        
        # Resource utilization stats
        if memory_peaks:
            result["memory_stats"] = {
                "mean_peak_memory_mb": statistics.mean(memory_peaks),
                "max_peak_memory_mb": max(memory_peaks),
                "min_peak_memory_mb": min(memory_peaks)
            }
        
        if cpu_peaks:
            result["cpu_stats"] = {
                "mean_peak_cpu_percent": statistics.mean(cpu_peaks),
                "max_peak_cpu_percent": max(cpu_peaks),
                "min_peak_cpu_percent": min(cpu_peaks)
            }
        
        # I/O stats
        if disk_io_totals:
            result["disk_io_stats"] = {
                "mean_disk_read_mb": statistics.mean(disk_io_totals),
                "total_disk_read_mb": sum(disk_io_totals),
                "max_disk_read_mb": max(disk_io_totals)
            }
        
        if network_io_totals:
            result["network_io_stats"] = {
                "mean_network_mb": statistics.mean(network_io_totals),
                "total_network_mb": sum(network_io_totals),
                "max_network_mb": max(network_io_totals)
            }
        
        # Timing breakdown stats
        timing_breakdown = {}
        if queue_wait_times:
            timing_breakdown["queue_wait"] = {
                "mean_seconds": statistics.mean(queue_wait_times),
                "max_seconds": max(queue_wait_times)
            }
        
        if init_times:
            timing_breakdown["initialization"] = {
                "mean_seconds": statistics.mean(init_times),
                "max_seconds": max(init_times)
            }
        
        if download_times:
            timing_breakdown["download"] = {
                "mean_seconds": statistics.mean(download_times),
                "max_seconds": max(download_times)
            }
        
        if cache_load_times:
            timing_breakdown["cache_load"] = {
                "mean_seconds": statistics.mean(cache_load_times),
                "max_seconds": max(cache_load_times)
            }
        
        if timing_breakdown:
            result["timing_breakdown"] = timing_breakdown
        
        # Performance insights
        insights = []
        if cache_hits / len(metrics) < 0.5:
            insights.append("Low cache hit rate - consider cache warming strategies")
        
        if timeout_count > 0:
            insights.append(f"{timeout_count} model loading timeouts detected - review timeout thresholds")
        
        if retry_counts and statistics.mean(retry_counts) > 1.0:
            insights.append("High retry rate - investigate model loading reliability")
        
        if memory_peaks and max(memory_peaks) > 8000:  # > 8GB
            insights.append("High memory usage detected - consider model optimization")
        
        if durations and statistics.mean(durations) > 180:  # > 3 minutes
            insights.append("Slow model loading detected - investigate performance bottlenecks")
        
        if insights:
            result["performance_insights"] = insights
        
        return result
    
    def _calculate_percentile(self, values: List[float], percentile: int) -> float:
        """Calculate the specified percentile of a list of values."""
        if not values:
            return 0.0
        
        sorted_values = sorted(values)
        index = (percentile / 100.0) * (len(sorted_values) - 1)
        
        if index.is_integer():
            return sorted_values[int(index)]
        else:
            lower_index = int(index)
            upper_index = lower_index + 1
            weight = index - lower_index
            return sorted_values[lower_index] * (1 - weight) + sorted_values[upper_index] * weight
    
    def get_startup_session_summary(self) -> Dict[str, Any]:
        """Get a summary of the current startup session."""
        # Calculate current duration if session is still active
        current_duration = None
        if self.current_session.completion_time:
            current_duration = self.current_session.total_duration_seconds
        else:
            current_duration = (datetime.now() - self.current_session.startup_time).total_seconds()
        
        return {
            "session_id": self.current_session.session_id,
            "startup_time": self.current_session.startup_time.isoformat(),
            "completion_time": self.current_session.completion_time.isoformat() if self.current_session.completion_time else None,
            "total_duration_seconds": current_duration,
            "final_phase_reached": self.current_session.final_phase_reached.value,
            "overall_efficiency_score": self.current_session.overall_efficiency_score,
            "success": self.current_session.success,
            "error_count": self.current_session.error_count,
            "retry_count": self.current_session.retry_count,
            "phases_completed": len(self.current_session.phase_metrics),
            "models_processed": len(self.current_session.model_metrics),
            "models_loaded_successfully": sum(1 for m in self.current_session.model_metrics if m.success)
        }
    
    def get_historical_trends(self, days: int = 7) -> Dict[str, Any]:
        """Get historical startup performance trends."""
        cutoff_date = datetime.now() - timedelta(days=days)
        recent_sessions = [
            session for session in self.historical_sessions
            if session.startup_time >= cutoff_date
        ]
        
        if not recent_sessions:
            return {
                "period_days": days,
                "sample_count": 0,
                "message": "No historical data available"
            }
        
        # Calculate trends
        durations = [s.total_duration_seconds for s in recent_sessions if s.total_duration_seconds]
        efficiency_scores = [s.overall_efficiency_score for s in recent_sessions]
        success_rate = sum(1 for s in recent_sessions if s.success) / len(recent_sessions)
        
        return {
            "period_days": days,
            "sample_count": len(recent_sessions),
            "performance_trends": {
                "mean_startup_time_seconds": statistics.mean(durations) if durations else 0,
                "startup_time_trend": self._calculate_trend(durations) if len(durations) >= 3 else "insufficient_data",
                "mean_efficiency_score": statistics.mean(efficiency_scores) if efficiency_scores else 0,
                "efficiency_trend": self._calculate_trend(efficiency_scores) if len(efficiency_scores) >= 3 else "insufficient_data",
                "success_rate": success_rate,
                "total_errors": sum(s.error_count for s in recent_sessions),
                "total_retries": sum(s.retry_count for s in recent_sessions)
            },
            "phase_distribution": {
                phase.value: sum(1 for s in recent_sessions if s.final_phase_reached == phase)
                for phase in StartupPhase
            }
        }
    
    def _calculate_trend(self, values: List[float]) -> str:
        """Calculate trend direction from a list of values."""
        if len(values) < 3:
            return "insufficient_data"
        
        # Simple linear trend calculation
        n = len(values)
        x_mean = (n - 1) / 2
        y_mean = statistics.mean(values)
        
        numerator = sum((i - x_mean) * (values[i] - y_mean) for i in range(n))
        denominator = sum((i - x_mean) ** 2 for i in range(n))
        
        if denominator == 0:
            return "stable"
        
        slope = numerator / denominator
        
        if slope > 0.1:
            return "increasing"
        elif slope < -0.1:
            return "decreasing"
        else:
            return "stable"
    
    def export_metrics(self, format: str = "json") -> str:
        """Export metrics data in the specified format."""
        data = {
            "current_session": {
                "session_id": self.current_session.session_id,
                "startup_time": self.current_session.startup_time.isoformat(),
                "completion_time": self.current_session.completion_time.isoformat() if self.current_session.completion_time else None,
                "total_duration_seconds": self.current_session.total_duration_seconds,
                "final_phase_reached": self.current_session.final_phase_reached.value,
                "overall_efficiency_score": self.current_session.overall_efficiency_score,
                "success": self.current_session.success,
                "phase_metrics": [
                    {
                        "phase": m.phase.value,
                        "duration_seconds": m.duration_seconds,
                        "efficiency_score": m.efficiency_score,
                        "success": m.success,
                        "retry_count": m.retry_count
                    }
                    for m in self.current_session.phase_metrics
                ],
                "model_metrics": [
                    {
                        "model_name": m.model_name,
                        "priority": m.priority,
                        "duration_seconds": m.duration_seconds,
                        "success": m.success,
                        "loading_efficiency": m.loading_efficiency
                    }
                    for m in self.current_session.model_metrics
                ],
                "user_wait_metrics": [
                    {
                        "request_id": m.request_id,
                        "user_id": m.user_id,
                        "endpoint": m.endpoint,
                        "request_type": m.request_type,
                        "wait_time_seconds": m.wait_time_seconds,
                        "startup_phase": m.startup_phase_at_request.value,
                        "fallback_used": m.fallback_used,
                        "fallback_quality": m.fallback_quality,
                        "success": m.success,
                        "estimated_wait_time_seconds": m.estimated_wait_time_seconds
                    }
                    for m in self.current_session.user_wait_metrics
                ]
            },
            "historical_summary": {
                "total_sessions": len(self.historical_sessions),
                "phase_completion_stats": {
                    phase.value: self.get_phase_completion_metrics(phase)
                    for phase in StartupPhase
                },
                "user_wait_time_stats": self.get_user_wait_time_metrics(),
                "user_experience_summary": self.get_user_experience_summary(),
                "recent_trends": self.get_historical_trends()
            }
        }
        
        if format.lower() == "json":
            return json.dumps(data, indent=2, default=str)
        else:
            raise ValueError(f"Unsupported export format: {format}")
    
    def get_cache_hit_rate_monitoring(self) -> Dict[str, Any]:
        """
        Get comprehensive cache hit rate monitoring data.
        
        This method provides real-time cache hit rate monitoring with detailed
        breakdowns by model, time period, and cache source.
        """
        all_metrics = []
        for model_metrics in self.model_loading_history.values():
            all_metrics.extend(model_metrics)
        
        if not all_metrics:
            return {
                "status": "no_data",
                "message": "No model loading metrics available for cache monitoring",
                "timestamp": datetime.now().isoformat()
            }
        
        # Overall cache statistics
        total_loads = len(all_metrics)
        cache_hits = sum(1 for m in all_metrics if m.cache_hit)
        cache_misses = total_loads - cache_hits
        overall_hit_rate = cache_hits / total_loads if total_loads > 0 else 0.0
        
        # Time-based analysis (last 24 hours in hourly buckets)
        now = datetime.now()
        hourly_buckets = {}
        
        for i in range(24):
            hour_start = now - timedelta(hours=i+1)
            hour_end = now - timedelta(hours=i)
            hour_key = f"hour_{i}"
            
            hour_metrics = [
                m for m in all_metrics
                if hour_start <= m.start_time < hour_end
            ]
            
            if hour_metrics:
                hour_hits = sum(1 for m in hour_metrics if m.cache_hit)
                hourly_buckets[hour_key] = {
                    "hour_offset": i,
                    "start_time": hour_start.isoformat(),
                    "end_time": hour_end.isoformat(),
                    "total_loads": len(hour_metrics),
                    "cache_hits": hour_hits,
                    "cache_misses": len(hour_metrics) - hour_hits,
                    "hit_rate": hour_hits / len(hour_metrics)
                }
        
        # Model-specific cache performance
        model_performance = {}
        for model_name, model_metrics in self.model_loading_history.items():
            if model_metrics:
                model_hits = sum(1 for m in model_metrics if m.cache_hit)
                model_total = len(model_metrics)
                model_hit_rate = model_hits / model_total
                
                # Recent performance (last 6 hours)
                recent_cutoff = now - timedelta(hours=6)
                recent_metrics = [m for m in model_metrics if m.start_time >= recent_cutoff]
                recent_hits = sum(1 for m in recent_metrics if m.cache_hit)
                recent_hit_rate = recent_hits / len(recent_metrics) if recent_metrics else 0.0
                
                # Average load times for cache hits vs misses
                hit_times = [m.duration_seconds for m in model_metrics if m.cache_hit and m.duration_seconds]
                miss_times = [m.duration_seconds for m in model_metrics if not m.cache_hit and m.duration_seconds]
                
                model_performance[model_name] = {
                    "total_loads": model_total,
                    "cache_hits": model_hits,
                    "cache_misses": model_total - model_hits,
                    "overall_hit_rate": model_hit_rate,
                    "recent_hit_rate": recent_hit_rate,
                    "recent_loads": len(recent_metrics),
                    "avg_hit_time_seconds": statistics.mean(hit_times) if hit_times else None,
                    "avg_miss_time_seconds": statistics.mean(miss_times) if miss_times else None,
                    "cache_efficiency": (
                        statistics.mean(miss_times) / statistics.mean(hit_times)
                        if hit_times and miss_times else None
                    )
                }
        
        # Cache source analysis
        cache_source_stats = {}
        for metric in all_metrics:
            if metric.cache_hit and metric.cache_source:
                source = metric.cache_source
                if source not in cache_source_stats:
                    cache_source_stats[source] = {
                        "hits": 0,
                        "total_hit_time": 0.0,
                        "hit_times": []
                    }
                
                cache_source_stats[source]["hits"] += 1
                if metric.duration_seconds:
                    cache_source_stats[source]["total_hit_time"] += metric.duration_seconds
                    cache_source_stats[source]["hit_times"].append(metric.duration_seconds)
        
        # Calculate averages for cache sources
        for source, stats in cache_source_stats.items():
            if stats["hits"] > 0:
                stats["avg_hit_time_seconds"] = stats["total_hit_time"] / stats["hits"]
                stats["hit_rate_contribution"] = stats["hits"] / cache_hits if cache_hits > 0 else 0.0
                # Remove raw data to keep response clean
                del stats["total_hit_time"]
                del stats["hit_times"]
        
        # Performance trends (compare recent vs historical)
        recent_cutoff = now - timedelta(hours=6)
        recent_metrics = [m for m in all_metrics if m.start_time >= recent_cutoff]
        historical_metrics = [m for m in all_metrics if m.start_time < recent_cutoff]
        
        trend_analysis = {}
        if recent_metrics and historical_metrics:
            recent_hit_rate = sum(1 for m in recent_metrics if m.cache_hit) / len(recent_metrics)
            historical_hit_rate = sum(1 for m in historical_metrics if m.cache_hit) / len(historical_metrics)
            
            trend_analysis = {
                "recent_hit_rate": recent_hit_rate,
                "historical_hit_rate": historical_hit_rate,
                "trend_direction": (
                    "improving" if recent_hit_rate > historical_hit_rate * 1.1 else
                    "declining" if recent_hit_rate < historical_hit_rate * 0.9 else
                    "stable"
                ),
                "trend_magnitude": abs(recent_hit_rate - historical_hit_rate),
                "recent_sample_size": len(recent_metrics),
                "historical_sample_size": len(historical_metrics)
            }
        
        # Cache effectiveness scoring
        effectiveness_score = 0.0
        effectiveness_factors = []
        
        # Factor 1: Overall hit rate (40% weight)
        hit_rate_score = min(1.0, overall_hit_rate / 0.8) * 40  # Target 80% hit rate
        effectiveness_score += hit_rate_score
        effectiveness_factors.append(f"Hit rate: {hit_rate_score:.1f}/40 (rate: {overall_hit_rate:.1%})")
        
        # Factor 2: Cache efficiency (30% weight) - how much faster cache hits are
        if model_performance:
            efficiencies = [
                data["cache_efficiency"] for data in model_performance.values()
                if data["cache_efficiency"] is not None
            ]
            if efficiencies:
                avg_efficiency = statistics.mean(efficiencies)
                efficiency_score = min(1.0, avg_efficiency / 5.0) * 30  # Target 5x speedup
                effectiveness_score += efficiency_score
                effectiveness_factors.append(f"Efficiency: {efficiency_score:.1f}/30 (speedup: {avg_efficiency:.1f}x)")
        
        # Factor 3: Consistency across models (20% weight)
        if model_performance:
            model_hit_rates = [data["overall_hit_rate"] for data in model_performance.values()]
            hit_rate_std = statistics.stdev(model_hit_rates) if len(model_hit_rates) > 1 else 0.0
            consistency_score = max(0.0, (0.2 - hit_rate_std) / 0.2) * 20  # Lower std dev is better
            effectiveness_score += consistency_score
            effectiveness_factors.append(f"Consistency: {consistency_score:.1f}/20 (std dev: {hit_rate_std:.3f})")
        
        # Factor 4: Recent performance (10% weight)
        if trend_analysis:
            recent_performance_score = min(1.0, trend_analysis["recent_hit_rate"] / 0.8) * 10
            effectiveness_score += recent_performance_score
            effectiveness_factors.append(f"Recent performance: {recent_performance_score:.1f}/10")
        
        # Generate recommendations
        recommendations = []
        
        if overall_hit_rate < 0.5:
            recommendations.append("Critical: Implement cache warming strategies for frequently used models")
            recommendations.append("Review cache retention policies and storage capacity")
        elif overall_hit_rate < 0.7:
            recommendations.append("Consider pre-loading popular models during startup")
            recommendations.append("Analyze model usage patterns to optimize cache warming")
        
        if model_performance:
            low_performing_models = [
                name for name, data in model_performance.items()
                if data["overall_hit_rate"] < 0.3 and data["total_loads"] >= 5
            ]
            if low_performing_models:
                recommendations.append(f"Focus cache warming on low-performing models: {', '.join(low_performing_models)}")
        
        if trend_analysis and trend_analysis["trend_direction"] == "declining":
            recommendations.append("Investigate recent cache performance decline")
            recommendations.append("Check for cache eviction issues or storage problems")
        
        if not cache_source_stats:
            recommendations.append("Enable cache source tracking for better diagnostics")
        
        # Compile final result
        result = {
            "timestamp": now.isoformat(),
            "monitoring_period_hours": 24,
            "overall_statistics": {
                "total_model_loads": total_loads,
                "cache_hits": cache_hits,
                "cache_misses": cache_misses,
                "overall_hit_rate": overall_hit_rate,
                "unique_models_tracked": len(self.model_loading_history)
            },
            "hourly_breakdown": hourly_buckets,
            "model_performance": model_performance,
            "cache_source_analysis": cache_source_stats,
            "trend_analysis": trend_analysis,
            "effectiveness_assessment": {
                "overall_score": effectiveness_score,
                "max_score": 100.0,
                "grade": (
                    "A" if effectiveness_score >= 90 else
                    "B" if effectiveness_score >= 80 else
                    "C" if effectiveness_score >= 70 else
                    "D" if effectiveness_score >= 60 else
                    "F"
                ),
                "factors": effectiveness_factors
            },
            "recommendations": recommendations,
            "alerts": self._generate_cache_alerts(overall_hit_rate, model_performance, trend_analysis)
        }
        
        return result
    
    def _generate_cache_alerts(self, overall_hit_rate: float, model_performance: Dict, trend_analysis: Dict) -> List[Dict[str, Any]]:
        """Generate cache performance alerts."""
        alerts = []
        
        # Critical hit rate alert
        if overall_hit_rate < 0.3:
            alerts.append({
                "level": "critical",
                "type": "low_hit_rate",
                "message": f"Cache hit rate is critically low at {overall_hit_rate:.1%}",
                "threshold": 0.3,
                "current_value": overall_hit_rate,
                "action_required": True
            })
        elif overall_hit_rate < 0.5:
            alerts.append({
                "level": "warning",
                "type": "low_hit_rate", 
                "message": f"Cache hit rate is below optimal at {overall_hit_rate:.1%}",
                "threshold": 0.5,
                "current_value": overall_hit_rate,
                "action_required": False
            })
        
        # Model-specific alerts
        if model_performance:
            problematic_models = [
                (name, data) for name, data in model_performance.items()
                if data["overall_hit_rate"] < 0.2 and data["total_loads"] >= 5
            ]
            
            for model_name, data in problematic_models:
                alerts.append({
                    "level": "warning",
                    "type": "model_low_hit_rate",
                    "message": f"Model '{model_name}' has very low cache hit rate: {data['overall_hit_rate']:.1%}",
                    "model": model_name,
                    "hit_rate": data["overall_hit_rate"],
                    "total_loads": data["total_loads"],
                    "action_required": True
                })
        
        # Trend alerts
        if trend_analysis and trend_analysis["trend_direction"] == "declining":
            if trend_analysis["trend_magnitude"] > 0.2:
                alerts.append({
                    "level": "warning",
                    "type": "declining_performance",
                    "message": f"Cache hit rate has declined significantly from {trend_analysis['historical_hit_rate']:.1%} to {trend_analysis['recent_hit_rate']:.1%}",
                    "historical_rate": trend_analysis["historical_hit_rate"],
                    "recent_rate": trend_analysis["recent_hit_rate"],
                    "magnitude": trend_analysis["trend_magnitude"],
                    "action_required": True
                })
        
        return alerts

    def get_cache_performance_metrics(self) -> Dict[str, Any]:
        """Get cache performance metrics for model loading."""
        all_metrics = []
        for model_metrics in self.model_loading_history.values():
            all_metrics.extend(model_metrics)
        
        if not all_metrics:
            return {
                "cache_performance": "no_data",
                "message": "No model loading metrics available"
            }
        
        cache_hits = sum(1 for m in all_metrics if m.cache_hit)
        total_loads = len(all_metrics)
        cache_hit_rate = cache_hits / total_loads if total_loads > 0 else 0.0
        
        # Analyze cache vs non-cache performance
        cache_hit_metrics = [m for m in all_metrics if m.cache_hit and m.duration_seconds is not None]
        cache_miss_metrics = [m for m in all_metrics if not m.cache_hit and m.duration_seconds is not None]
        
        cache_hit_times = [m.duration_seconds for m in cache_hit_metrics]
        cache_miss_times = [m.duration_seconds for m in cache_miss_metrics]
        
        result = {
            "cache_hit_rate": cache_hit_rate,
            "total_model_loads": total_loads,
            "cache_hits": cache_hits,
            "cache_misses": total_loads - cache_hits
        }
        
        if cache_hit_times:
            result["cache_hit_performance"] = {
                "mean_duration_seconds": statistics.mean(cache_hit_times),
                "median_duration_seconds": statistics.median(cache_hit_times),
                "max_duration_seconds": max(cache_hit_times)
            }
        
        if cache_miss_times:
            result["cache_miss_performance"] = {
                "mean_duration_seconds": statistics.mean(cache_miss_times),
                "median_duration_seconds": statistics.median(cache_miss_times),
                "max_duration_seconds": max(cache_miss_times)
            }
        
        # Calculate cache efficiency
        if cache_hit_times and cache_miss_times:
            cache_speedup = statistics.mean(cache_miss_times) / statistics.mean(cache_hit_times)
            result["cache_speedup_factor"] = cache_speedup
            
            if cache_speedup > 5.0:
                result["cache_effectiveness"] = "excellent"
            elif cache_speedup > 2.0:
                result["cache_effectiveness"] = "good"
            elif cache_speedup > 1.2:
                result["cache_effectiveness"] = "moderate"
            else:
                result["cache_effectiveness"] = "poor"
        
        # Cache source analysis
        cache_sources = {}
        for metric in all_metrics:
            if metric.cache_hit and metric.cache_source:
                cache_sources[metric.cache_source] = cache_sources.get(metric.cache_source, 0) + 1
        
        if cache_sources:
            result["cache_sources"] = cache_sources
        
        # Time-based cache hit rate analysis
        if all_metrics:
            # Group metrics by time periods for trend analysis
            now = datetime.now()
            time_periods = {
                "last_hour": now - timedelta(hours=1),
                "last_6_hours": now - timedelta(hours=6),
                "last_24_hours": now - timedelta(hours=24),
                "last_week": now - timedelta(days=7)
            }
            
            time_based_rates = {}
            for period_name, cutoff_time in time_periods.items():
                period_metrics = [
                    m for m in all_metrics 
                    if m.start_time >= cutoff_time
                ]
                
                if period_metrics:
                    period_hits = sum(1 for m in period_metrics if m.cache_hit)
                    period_rate = period_hits / len(period_metrics)
                    time_based_rates[period_name] = {
                        "hit_rate": period_rate,
                        "total_loads": len(period_metrics),
                        "cache_hits": period_hits
                    }
            
            if time_based_rates:
                result["time_based_hit_rates"] = time_based_rates
        
        # Model-specific cache hit rates
        model_cache_rates = {}
        for model_name, model_metrics in self.model_loading_history.items():
            if model_metrics:
                model_hits = sum(1 for m in model_metrics if m.cache_hit)
                model_total = len(model_metrics)
                model_cache_rates[model_name] = {
                    "hit_rate": model_hits / model_total,
                    "total_loads": model_total,
                    "cache_hits": model_hits,
                    "cache_misses": model_total - model_hits
                }
        
        if model_cache_rates:
            result["model_specific_hit_rates"] = model_cache_rates
        
        # Cache performance insights
        insights = []
        
        if cache_hit_rate < 0.3:
            insights.append("Very low cache hit rate - investigate cache configuration and warming strategies")
        elif cache_hit_rate < 0.5:
            insights.append("Low cache hit rate - consider improving cache warming or retention policies")
        elif cache_hit_rate > 0.8:
            insights.append("Excellent cache hit rate - cache is performing well")
        
        # Check for models with consistently low cache rates
        if model_cache_rates:
            low_cache_models = [
                name for name, data in model_cache_rates.items()
                if data["hit_rate"] < 0.3 and data["total_loads"] >= 3
            ]
            if low_cache_models:
                insights.append(f"Models with low cache hit rates: {', '.join(low_cache_models)}")
        
        # Check cache effectiveness trends
        if "time_based_hit_rates" in result:
            recent_rate = result["time_based_hit_rates"].get("last_hour", {}).get("hit_rate", 0)
            older_rate = result["time_based_hit_rates"].get("last_24_hours", {}).get("hit_rate", 0)
            
            if recent_rate > 0 and older_rate > 0:
                if recent_rate < older_rate * 0.8:
                    insights.append("Cache hit rate has decreased recently - investigate cache eviction or warming issues")
                elif recent_rate > older_rate * 1.2:
                    insights.append("Cache hit rate has improved recently - cache warming strategies are working")
        
        if insights:
            result["cache_insights"] = insights
        
        return result
    
    def get_model_loading_bottlenecks(self) -> List[Dict[str, Any]]:
        """Identify model loading performance bottlenecks."""
        bottlenecks = []
        
        # Analyze all model metrics
        all_metrics = []
        for model_metrics in self.model_loading_history.values():
            all_metrics.extend(model_metrics)
        
        if not all_metrics:
            return bottlenecks
        
        # Check for slow loading models
        slow_models = {}
        for metric in all_metrics:
            if metric.duration_seconds and metric.duration_seconds > 120:  # > 2 minutes
                model_name = metric.model_name
                if model_name not in slow_models:
                    slow_models[model_name] = []
                slow_models[model_name].append(metric.duration_seconds)
        
        for model_name, durations in slow_models.items():
            avg_duration = statistics.mean(durations)
            bottlenecks.append({
                "type": "slow_model_loading",
                "model": model_name,
                "severity": "high" if avg_duration > 300 else "medium",
                "description": f"Model {model_name} has slow loading times (avg: {avg_duration:.1f}s)",
                "average_duration_seconds": avg_duration,
                "occurrences": len(durations),
                "recommendations": [
                    "Consider model compression or optimization",
                    "Implement model caching if not already enabled",
                    "Review model size and loading strategy"
                ]
            })
        
        # Check for high memory usage
        high_memory_models = {}
        for metric in all_metrics:
            if metric.memory_peak_mb and metric.memory_peak_mb > 4000:  # > 4GB
                model_name = metric.model_name
                if model_name not in high_memory_models:
                    high_memory_models[model_name] = []
                high_memory_models[model_name].append(metric.memory_peak_mb)
        
        for model_name, memory_peaks in high_memory_models.items():
            avg_memory = statistics.mean(memory_peaks)
            bottlenecks.append({
                "type": "high_memory_usage",
                "model": model_name,
                "severity": "high" if avg_memory > 8000 else "medium",
                "description": f"Model {model_name} uses high memory during loading (avg: {avg_memory:.1f}MB)",
                "average_memory_mb": avg_memory,
                "peak_memory_mb": max(memory_peaks),
                "occurrences": len(memory_peaks),
                "recommendations": [
                    "Consider model quantization or compression",
                    "Implement progressive model loading",
                    "Review memory allocation strategies"
                ]
            })
        
        # Check for frequent failures
        failed_models = {}
        for metric in all_metrics:
            if not metric.success:
                model_name = metric.model_name
                failed_models[model_name] = failed_models.get(model_name, 0) + 1
        
        total_loads_per_model = {}
        for metric in all_metrics:
            model_name = metric.model_name
            total_loads_per_model[model_name] = total_loads_per_model.get(model_name, 0) + 1
        
        for model_name, failure_count in failed_models.items():
            total_loads = total_loads_per_model[model_name]
            failure_rate = failure_count / total_loads
            
            if failure_rate > 0.1:  # > 10% failure rate
                bottlenecks.append({
                    "type": "high_failure_rate",
                    "model": model_name,
                    "severity": "high" if failure_rate > 0.3 else "medium",
                    "description": f"Model {model_name} has high failure rate ({failure_rate:.1%})",
                    "failure_rate": failure_rate,
                    "failure_count": failure_count,
                    "total_attempts": total_loads,
                    "recommendations": [
                        "Investigate model loading errors",
                        "Review model file integrity",
                        "Check resource availability during loading"
                    ]
                })
        
        # Check for low cache hit rates
        model_cache_rates = {}
        for metric in all_metrics:
            model_name = metric.model_name
            if model_name not in model_cache_rates:
                model_cache_rates[model_name] = {"hits": 0, "total": 0}
            
            model_cache_rates[model_name]["total"] += 1
            if metric.cache_hit:
                model_cache_rates[model_name]["hits"] += 1
        
        for model_name, cache_data in model_cache_rates.items():
            if cache_data["total"] >= 3:  # Only consider models with multiple loads
                cache_rate = cache_data["hits"] / cache_data["total"]
                if cache_rate < 0.5:  # < 50% cache hit rate
                    bottlenecks.append({
                        "type": "low_cache_hit_rate",
                        "model": model_name,
                        "severity": "medium",
                        "description": f"Model {model_name} has low cache hit rate ({cache_rate:.1%})",
                        "cache_hit_rate": cache_rate,
                        "cache_hits": cache_data["hits"],
                        "total_loads": cache_data["total"],
                        "recommendations": [
                            "Implement or improve model caching",
                            "Review cache eviction policies",
                            "Consider cache warming strategies"
                        ]
                    })
        
        return bottlenecks
    
    def get_model_loading_performance_summary(self) -> Dict[str, Any]:
        """Get a comprehensive model loading performance summary."""
        all_metrics = []
        for model_metrics in self.model_loading_history.values():
            all_metrics.extend(model_metrics)
        
        if not all_metrics:
            return {
                "status": "no_data",
                "message": "No model loading metrics available"
            }
        
        # Basic statistics
        total_loads = len(all_metrics)
        successful_loads = sum(1 for m in all_metrics if m.success)
        success_rate = successful_loads / total_loads
        
        durations = [m.duration_seconds for m in all_metrics if m.duration_seconds is not None]
        
        summary = {
            "total_model_loads": total_loads,
            "successful_loads": successful_loads,
            "success_rate": success_rate,
            "unique_models": len(self.model_loading_history),
            "cache_performance": self.get_cache_performance_metrics(),
            "bottlenecks": self.get_model_loading_bottlenecks()
        }
        
        if durations:
            summary["performance_overview"] = {
                "mean_loading_time_seconds": statistics.mean(durations),
                "median_loading_time_seconds": statistics.median(durations),
                "fastest_load_seconds": min(durations),
                "slowest_load_seconds": max(durations),
                "p95_loading_time_seconds": self._calculate_percentile(durations, 95)
            }
        
        # Performance trends
        if len(durations) >= 10:
            recent_durations = durations[-10:]
            older_durations = durations[:-10]
            
            if older_durations:
                recent_avg = statistics.mean(recent_durations)
                older_avg = statistics.mean(older_durations)
                
                if recent_avg < older_avg * 0.9:
                    summary["performance_trend"] = "improving"
                elif recent_avg > older_avg * 1.1:
                    summary["performance_trend"] = "degrading"
                else:
                    summary["performance_trend"] = "stable"
        
        # Top performing and problematic models
        model_performance = {}
        for model_name, metrics in self.model_loading_history.items():
            if len(metrics) >= 2:  # Only consider models with multiple loads
                model_durations = [m.duration_seconds for m in metrics if m.duration_seconds is not None]
                if model_durations:
                    model_performance[model_name] = {
                        "avg_duration": statistics.mean(model_durations),
                        "load_count": len(metrics),
                        "success_rate": sum(1 for m in metrics if m.success) / len(metrics)
                    }
        
        if model_performance:
            # Best performing models (fastest average load time)
            best_models = sorted(model_performance.items(), key=lambda x: x[1]["avg_duration"])[:3]
            summary["best_performing_models"] = [
                {
                    "model": name,
                    "avg_duration_seconds": data["avg_duration"],
                    "success_rate": data["success_rate"]
                }
                for name, data in best_models
            ]
            
            # Worst performing models (slowest average load time)
            worst_models = sorted(model_performance.items(), key=lambda x: x[1]["avg_duration"], reverse=True)[:3]
            summary["worst_performing_models"] = [
                {
                    "model": name,
                    "avg_duration_seconds": data["avg_duration"],
                    "success_rate": data["success_rate"]
                }
                for name, data in worst_models
            ]
        
        return summary

    async def record_health_check_latency(
        self, 
        response_time_ms: float, 
        success: bool = True,
        endpoint: str = "/health/simple",
        error_message: Optional[str] = None
    ) -> None:
        """
        Record a health check latency measurement during model loading.
        
        This method tracks health check response times to detect GIL contention
        and event loop blocking during CPU-bound model loading operations.
        
        Args:
            response_time_ms: Health check response time in milliseconds
            success: Whether the health check succeeded
            endpoint: Which health endpoint was called
            error_message: Error message if health check failed
        """
        # Get current startup phase and model loading status
        current_status = self.phase_manager.get_current_status()
        
        # Identify models currently being loaded
        models_loading = [
            model_name for model_name, model_status in current_status.model_statuses.items()
            if model_status.status == "loading"
        ]
        
        models_loaded_count = sum(
            1 for model_status in current_status.model_statuses.values()
            if model_status.status == "loaded"
        )
        
        models_total_count = len(current_status.model_statuses)
        
        # Determine if response time indicates GIL contention
        is_slow = response_time_ms > 100  # > 100ms indicates possible GIL contention
        is_elevated = response_time_ms > 50  # > 50ms is elevated but not critical
        
        # Create the metric
        metric = HealthCheckLatencyMetric(
            timestamp=datetime.now(),
            response_time_ms=response_time_ms,
            success=success,
            startup_phase=current_status.current_phase,
            models_loading=models_loading,
            models_loaded_count=models_loaded_count,
            models_total_count=models_total_count,
            is_slow=is_slow,
            is_elevated=is_elevated,
            endpoint=endpoint,
            error_message=error_message
        )
        
        # Add to current session and history
        self.current_session.health_check_latency_metrics.append(metric)
        self.health_check_latency_history.append(metric)
        
        # Log if slow (GIL contention detected)
        if is_slow:
            logger.warning(
                f"Health check latency {response_time_ms:.1f}ms during model loading "
                f"(phase: {current_status.current_phase.value}, "
                f"models loading: {models_loading}). "
                f"Possible GIL contention detected."
            )
        elif is_elevated:
            logger.debug(
                f"Health check latency elevated: {response_time_ms:.1f}ms "
                f"(phase: {current_status.current_phase.value})"
            )
    
    def get_health_check_latency_metrics(
        self,
        phase: Optional[StartupPhase] = None,
        minutes_back: Optional[int] = None,
        during_model_loading: bool = False
    ) -> Dict[str, Any]:
        """
        Get health check latency metrics with optional filtering.
        
        Args:
            phase: Filter by startup phase
            minutes_back: Only include metrics from the last N minutes
            during_model_loading: Only include metrics when models were being loaded
            
        Returns:
            Dictionary containing health check latency statistics and analysis
        """
        # Filter metrics based on criteria
        filtered_metrics = self.health_check_latency_history.copy()
        
        if phase:
            filtered_metrics = [m for m in filtered_metrics if m.startup_phase == phase]
        
        if minutes_back:
            cutoff_time = datetime.now() - timedelta(minutes=minutes_back)
            filtered_metrics = [m for m in filtered_metrics if m.timestamp >= cutoff_time]
        
        if during_model_loading:
            filtered_metrics = [m for m in filtered_metrics if len(m.models_loading) > 0]
        
        if not filtered_metrics:
            return {
                "sample_count": 0,
                "message": "No health check latency metrics available",
                "filters": {
                    "phase": phase.value if phase else None,
                    "minutes_back": minutes_back,
                    "during_model_loading": during_model_loading
                }
            }
        
        # Calculate statistics
        response_times = [m.response_time_ms for m in filtered_metrics]
        success_count = sum(1 for m in filtered_metrics if m.success)
        slow_count = sum(1 for m in filtered_metrics if m.is_slow)
        elevated_count = sum(1 for m in filtered_metrics if m.is_elevated)
        
        result = {
            "sample_count": len(filtered_metrics),
            "success_rate": success_count / len(filtered_metrics),
            "slow_response_rate": slow_count / len(filtered_metrics),
            "elevated_response_rate": elevated_count / len(filtered_metrics),
            "filters": {
                "phase": phase.value if phase else None,
                "minutes_back": minutes_back,
                "during_model_loading": during_model_loading
            }
        }
        
        if response_times:
            result["latency_stats"] = {
                "mean_ms": statistics.mean(response_times),
                "median_ms": statistics.median(response_times),
                "min_ms": min(response_times),
                "max_ms": max(response_times),
                "p95_ms": self._calculate_percentile(response_times, 95),
                "p99_ms": self._calculate_percentile(response_times, 99),
                "std_dev_ms": statistics.stdev(response_times) if len(response_times) > 1 else 0.0
            }
        
        # Phase distribution
        phase_distribution = {}
        for phase_enum in StartupPhase:
            count = sum(1 for m in filtered_metrics if m.startup_phase == phase_enum)
            if count > 0:
                phase_metrics = [m.response_time_ms for m in filtered_metrics if m.startup_phase == phase_enum]
                phase_distribution[phase_enum.value] = {
                    "count": count,
                    "mean_ms": statistics.mean(phase_metrics),
                    "max_ms": max(phase_metrics),
                    "slow_count": sum(1 for m in filtered_metrics if m.startup_phase == phase_enum and m.is_slow)
                }
        
        if phase_distribution:
            result["phase_distribution"] = phase_distribution
        
        # Model loading correlation analysis
        loading_correlation = self._analyze_model_loading_correlation(filtered_metrics)
        if loading_correlation:
            result["model_loading_correlation"] = loading_correlation
        
        # GIL contention analysis
        gil_analysis = self._analyze_gil_contention(filtered_metrics)
        if gil_analysis:
            result["gil_contention_analysis"] = gil_analysis
        
        # Performance insights
        insights = self._generate_health_check_insights(filtered_metrics, result)
        if insights:
            result["performance_insights"] = insights
        
        return result
    
    def _analyze_model_loading_correlation(self, metrics: List[HealthCheckLatencyMetric]) -> Dict[str, Any]:
        """Analyze correlation between model loading and health check latency."""
        # Separate metrics by whether models were loading
        loading_metrics = [m for m in metrics if len(m.models_loading) > 0]
        idle_metrics = [m for m in metrics if len(m.models_loading) == 0]
        
        if not loading_metrics or not idle_metrics:
            return {}
        
        loading_times = [m.response_time_ms for m in loading_metrics]
        idle_times = [m.response_time_ms for m in idle_metrics]
        
        # Calculate impact of model loading on health check latency
        loading_avg = statistics.mean(loading_times)
        idle_avg = statistics.mean(idle_times)
        latency_increase = ((loading_avg - idle_avg) / idle_avg * 100) if idle_avg > 0 else 0
        
        # Identify which models cause the most latency
        model_impact = {}
        for metric in loading_metrics:
            for model in metric.models_loading:
                if model not in model_impact:
                    model_impact[model] = {"latencies": [], "count": 0}
                model_impact[model]["latencies"].append(metric.response_time_ms)
                model_impact[model]["count"] += 1
        
        # Calculate average latency per model
        for model, data in model_impact.items():
            data["avg_latency_ms"] = statistics.mean(data["latencies"])
            data["max_latency_ms"] = max(data["latencies"])
            del data["latencies"]  # Remove raw data
        
        # Sort by average latency (highest impact first)
        sorted_models = sorted(model_impact.items(), key=lambda x: x[1]["avg_latency_ms"], reverse=True)
        
        return {
            "during_loading": {
                "sample_count": len(loading_metrics),
                "mean_latency_ms": loading_avg,
                "max_latency_ms": max(loading_times),
                "slow_rate": sum(1 for m in loading_metrics if m.is_slow) / len(loading_metrics)
            },
            "during_idle": {
                "sample_count": len(idle_metrics),
                "mean_latency_ms": idle_avg,
                "max_latency_ms": max(idle_times),
                "slow_rate": sum(1 for m in idle_metrics if m.is_slow) / len(idle_metrics)
            },
            "latency_increase_percent": latency_increase,
            "model_impact": dict(sorted_models[:5])  # Top 5 models by impact
        }
    
    def _analyze_gil_contention(self, metrics: List[HealthCheckLatencyMetric]) -> Dict[str, Any]:
        """Analyze GIL contention patterns from health check latency data."""
        slow_metrics = [m for m in metrics if m.is_slow]
        
        if not slow_metrics:
            return {
                "contention_detected": False,
                "message": "No GIL contention detected (all health checks < 100ms)"
            }
        
        # Analyze patterns in slow health checks
        slow_during_loading = [m for m in slow_metrics if len(m.models_loading) > 0]
        slow_during_idle = [m for m in slow_metrics if len(m.models_loading) == 0]
        
        # Identify models most associated with slow health checks
        model_slow_association = {}
        for metric in slow_during_loading:
            for model in metric.models_loading:
                model_slow_association[model] = model_slow_association.get(model, 0) + 1
        
        return {
            "contention_detected": True,
            "total_slow_checks": len(slow_metrics),
            "slow_during_model_loading": len(slow_during_loading),
            "slow_during_idle": len(slow_during_idle),
            "loading_correlation_rate": len(slow_during_loading) / len(slow_metrics) if slow_metrics else 0,
            "models_associated_with_slow_checks": dict(
                sorted(model_slow_association.items(), key=lambda x: x[1], reverse=True)[:5]
            ),
            "max_latency_ms": max(m.response_time_ms for m in slow_metrics),
            "avg_slow_latency_ms": statistics.mean([m.response_time_ms for m in slow_metrics]),
            "recommendations": [
                "Consider using ProcessPoolExecutor for CPU-bound model loading",
                "Add yield points (await asyncio.sleep(0)) in long-running operations",
                "Review model loading code for GIL-holding operations"
            ] if len(slow_during_loading) > len(slow_during_idle) else [
                "Investigate non-model-loading causes of slow health checks",
                "Check for other CPU-bound operations blocking the event loop"
            ]
        }
    
    def _generate_health_check_insights(
        self, 
        metrics: List[HealthCheckLatencyMetric], 
        stats: Dict[str, Any]
    ) -> List[str]:
        """Generate actionable insights from health check latency data."""
        insights = []
        
        if not metrics:
            return insights
        
        # Check for high slow response rate
        slow_rate = stats.get("slow_response_rate", 0)
        if slow_rate > 0.1:  # > 10% slow responses
            insights.append(
                f"High slow response rate ({slow_rate*100:.1f}%) - "
                f"GIL contention likely affecting health checks"
            )
        
        # Check for latency spikes
        latency_stats = stats.get("latency_stats", {})
        if latency_stats:
            max_latency = latency_stats.get("max_ms", 0)
            mean_latency = latency_stats.get("mean_ms", 0)
            
            if max_latency > 500:  # > 500ms max latency
                insights.append(
                    f"Extreme latency spike detected ({max_latency:.1f}ms) - "
                    f"may cause health check timeouts"
                )
            
            if mean_latency > 50:  # > 50ms average
                insights.append(
                    f"Elevated average latency ({mean_latency:.1f}ms) - "
                    f"consider optimizing model loading"
                )
        
        # Check model loading correlation
        correlation = stats.get("model_loading_correlation", {})
        if correlation:
            increase = correlation.get("latency_increase_percent", 0)
            if increase > 100:  # > 100% increase during loading
                insights.append(
                    f"Health check latency increases {increase:.0f}% during model loading - "
                    f"ProcessPoolExecutor recommended"
                )
        
        # Check phase-specific issues
        phase_dist = stats.get("phase_distribution", {})
        for phase_name, phase_data in phase_dist.items():
            if phase_data.get("slow_count", 0) > 5:
                insights.append(
                    f"Multiple slow health checks during {phase_name} phase - "
                    f"review {phase_name} phase model loading"
                )
        
        return insights
    
    def get_health_check_latency_summary(self) -> Dict[str, Any]:
        """
        Get a comprehensive summary of health check latency during startup.
        
        Returns:
            Dictionary containing overall health check latency summary
        """
        if not self.health_check_latency_history:
            return {
                "status": "no_data",
                "message": "No health check latency data available"
            }
        
        all_metrics = self.health_check_latency_history
        
        # Overall statistics
        total_checks = len(all_metrics)
        successful_checks = sum(1 for m in all_metrics if m.success)
        slow_checks = sum(1 for m in all_metrics if m.is_slow)
        elevated_checks = sum(1 for m in all_metrics if m.is_elevated)
        
        response_times = [m.response_time_ms for m in all_metrics]
        
        summary = {
            "total_health_checks": total_checks,
            "successful_checks": successful_checks,
            "success_rate": successful_checks / total_checks,
            "slow_checks": slow_checks,
            "slow_rate": slow_checks / total_checks,
            "elevated_checks": elevated_checks,
            "elevated_rate": elevated_checks / total_checks
        }
        
        if response_times:
            avg_latency = statistics.mean(response_times)
            summary.update({
                "average_latency_ms": avg_latency,
                "median_latency_ms": statistics.median(response_times),
                "max_latency_ms": max(response_times),
                "p95_latency_ms": self._calculate_percentile(response_times, 95),
                "p99_latency_ms": self._calculate_percentile(response_times, 99)
            })
            
            # Health check quality assessment
            if avg_latency < 10:
                summary["health_check_quality"] = "excellent"
            elif avg_latency < 50:
                summary["health_check_quality"] = "good"
            elif avg_latency < 100:
                summary["health_check_quality"] = "acceptable"
            else:
                summary["health_check_quality"] = "poor"
        
        # Model loading impact analysis
        loading_metrics = [m for m in all_metrics if len(m.models_loading) > 0]
        idle_metrics = [m for m in all_metrics if len(m.models_loading) == 0]
        
        if loading_metrics and idle_metrics:
            loading_avg = statistics.mean([m.response_time_ms for m in loading_metrics])
            idle_avg = statistics.mean([m.response_time_ms for m in idle_metrics])
            
            summary["model_loading_impact"] = {
                "during_loading_avg_ms": loading_avg,
                "during_idle_avg_ms": idle_avg,
                "latency_increase_factor": loading_avg / idle_avg if idle_avg > 0 else 0,
                "checks_during_loading": len(loading_metrics),
                "checks_during_idle": len(idle_metrics)
            }
        
        # GIL contention summary
        if slow_checks > 0:
            slow_during_loading = sum(1 for m in all_metrics if m.is_slow and len(m.models_loading) > 0)
            summary["gil_contention_summary"] = {
                "total_slow_checks": slow_checks,
                "slow_during_model_loading": slow_during_loading,
                "loading_correlation_rate": slow_during_loading / slow_checks if slow_checks > 0 else 0,
                "likely_gil_contention": slow_during_loading > slow_checks * 0.5
            }
        
        return summary


# Convenience function for easy integration
async def track_startup_metrics(phase_manager: StartupPhaseManager, performance_tracker=None) -> StartupMetricsCollector:
    """
    Convenience function to start tracking startup metrics.
    
    Args:
        phase_manager: The startup phase manager to track
        performance_tracker: Optional performance tracker for enhanced metrics
        
    Returns:
        StartupMetricsCollector: The metrics collector instance
    """
    collector = StartupMetricsCollector(phase_manager)
    if performance_tracker:
        collector.set_performance_tracker(performance_tracker)
    await collector.start_collection()
    return collector


# Global instance for easy access (will be set during startup)
_global_metrics_collector: Optional[StartupMetricsCollector] = None


def set_global_metrics_collector(collector: StartupMetricsCollector) -> None:
    """Set the global metrics collector instance."""
    global _global_metrics_collector
    _global_metrics_collector = collector


def get_global_metrics_collector() -> Optional[StartupMetricsCollector]:
    """Get the global metrics collector instance."""
    return _global_metrics_collector


async def track_user_request(request_id: str, user_id: Optional[str] = None, 
                           endpoint: str = "unknown", request_type: str = "unknown",
                           required_capabilities: Optional[List[str]] = None) -> None:
    """
    Convenience function to track a user request start.
    
    Args:
        request_id: Unique identifier for the request
        user_id: Optional user identifier
        endpoint: API endpoint being called
        request_type: Type of request (chat, search, document, etc.)
        required_capabilities: List of capabilities required for this request
    """
    collector = get_global_metrics_collector()
    if collector:
        await collector.record_user_request_start(
            request_id=request_id,
            user_id=user_id,
            endpoint=endpoint,
            request_type=request_type,
            required_capabilities=required_capabilities
        )


async def complete_user_request(request_id: str, success: bool = True, 
                              error_message: Optional[str] = None,
                              fallback_used: bool = False, 
                              fallback_quality: Optional[str] = None,
                              actual_processing_time_seconds: Optional[float] = None) -> None:
    """
    Convenience function to track a user request completion.
    
    Args:
        request_id: Unique identifier for the request
        success: Whether the request was successful
        error_message: Optional error message if request failed
        fallback_used: Whether a fallback response was used
        fallback_quality: Quality level of fallback response
        actual_processing_time_seconds: Actual time spent processing (vs waiting)
    """
    collector = get_global_metrics_collector()
    if collector:
        await collector.record_user_request_completion(
            request_id=request_id,
            success=success,
            error_message=error_message,
            fallback_used=fallback_used,
            fallback_quality=fallback_quality,
            actual_processing_time_seconds=actual_processing_time_seconds
        )