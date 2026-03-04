"""
Connection Pool Optimization for Local Development

This module provides advanced connection pool optimization for local development
environments. It analyzes usage patterns, monitors performance, and automatically
adjusts pool settings for optimal resource utilization.

Features:
- Dynamic pool sizing based on usage patterns
- Connection health monitoring and recovery
- Performance metrics collection and analysis
- Automatic optimization recommendations
- Resource usage monitoring and alerts
- Connection leak detection and prevention
"""

import asyncio
import logging
import time
import threading
from collections import deque, defaultdict
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple, Callable
from enum import Enum

import structlog

logger = structlog.get_logger(__name__)


class OptimizationStrategy(Enum):
    """Connection pool optimization strategies."""
    CONSERVATIVE = "conservative"  # Minimal changes, prioritize stability
    BALANCED = "balanced"         # Balance performance and resource usage
    AGGRESSIVE = "aggressive"     # Maximize performance, higher resource usage
    CUSTOM = "custom"            # User-defined optimization parameters


class PoolHealthStatus(Enum):
    """Connection pool health status levels."""
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


@dataclass
class ConnectionMetrics:
    """Metrics for individual connections."""
    connection_id: str
    created_at: datetime
    last_used: datetime
    usage_count: int = 0
    total_time_active: float = 0.0
    average_query_time: float = 0.0
    error_count: int = 0
    last_error: Optional[str] = None
    is_healthy: bool = True


@dataclass
class PoolOptimizationMetrics:
    """Comprehensive pool optimization metrics."""
    # Basic pool metrics
    pool_size: int = 0
    max_overflow: int = 0
    checked_out: int = 0
    checked_in: int = 0
    overflow_count: int = 0
    invalid_count: int = 0
    
    # Performance metrics
    average_checkout_time: float = 0.0
    average_checkin_time: float = 0.0
    peak_concurrent_connections: int = 0
    total_connection_requests: int = 0
    connection_timeouts: int = 0
    connection_errors: int = 0
    
    # Utilization metrics
    utilization_percentage: float = 0.0
    peak_utilization: float = 0.0
    idle_connection_percentage: float = 0.0
    connection_turnover_rate: float = 0.0
    
    # Health metrics
    healthy_connections: int = 0
    unhealthy_connections: int = 0
    connection_leaks_detected: int = 0
    stale_connections: int = 0
    
    # Timing metrics
    last_updated: datetime = field(default_factory=datetime.now)
    measurement_period: timedelta = field(default_factory=lambda: timedelta(minutes=5))
    
    # Optimization recommendations
    recommendations: List[Dict[str, Any]] = field(default_factory=list)
    optimization_score: float = 0.0  # 0-100 score


@dataclass
class OptimizationRecommendation:
    """Connection pool optimization recommendation."""
    type: str
    priority: str  # "low", "medium", "high", "critical"
    description: str
    current_value: Any
    recommended_value: Any
    expected_impact: str
    implementation_complexity: str  # "low", "medium", "high"
    estimated_improvement: float  # Percentage improvement expected
    risks: List[str] = field(default_factory=list)
    prerequisites: List[str] = field(default_factory=list)


class ConnectionPoolOptimizer:
    """
    Advanced connection pool optimizer for local development.
    
    This class provides comprehensive connection pool optimization including:
    - Real-time performance monitoring
    - Dynamic pool sizing recommendations
    - Connection health tracking
    - Resource usage optimization
    - Automatic leak detection
    - Performance trend analysis
    """
    
    def __init__(
        self,
        pool_name: str,
        optimization_strategy: OptimizationStrategy = OptimizationStrategy.BALANCED,
        monitoring_interval: int = 30,
        optimization_interval: int = 300,
        enable_auto_optimization: bool = False,
        max_pool_size: int = 50,
        min_pool_size: int = 2,
        target_utilization: float = 0.7,
        connection_timeout_threshold: float = 5.0,
        stale_connection_threshold: int = 3600
    ):
        """
        Initialize connection pool optimizer.
        
        Args:
            pool_name: Name of the connection pool
            optimization_strategy: Optimization strategy to use
            monitoring_interval: Interval for collecting metrics (seconds)
            optimization_interval: Interval for running optimization (seconds)
            enable_auto_optimization: Enable automatic optimization
            max_pool_size: Maximum allowed pool size
            min_pool_size: Minimum allowed pool size
            target_utilization: Target utilization percentage (0.0-1.0)
            connection_timeout_threshold: Timeout threshold for warnings (seconds)
            stale_connection_threshold: Threshold for stale connections (seconds)
        """
        self.pool_name = pool_name
        self.optimization_strategy = optimization_strategy
        self.monitoring_interval = monitoring_interval
        self.optimization_interval = optimization_interval
        self.enable_auto_optimization = enable_auto_optimization
        self.max_pool_size = max_pool_size
        self.min_pool_size = min_pool_size
        self.target_utilization = target_utilization
        self.connection_timeout_threshold = connection_timeout_threshold
        self.stale_connection_threshold = stale_connection_threshold
        
        # Metrics storage
        self.current_metrics = PoolOptimizationMetrics()
        self.historical_metrics: deque = deque(maxlen=1000)
        self.connection_metrics: Dict[str, ConnectionMetrics] = {}
        
        # Event tracking
        self.checkout_times: deque = deque(maxlen=1000)
        self.checkin_times: deque = deque(maxlen=1000)
        self.connection_events: deque = deque(maxlen=5000)
        self.error_events: deque = deque(maxlen=1000)
        
        # Optimization state
        self.last_optimization = datetime.now()
        self.optimization_history: List[Dict[str, Any]] = []
        self.active_recommendations: List[OptimizationRecommendation] = []
        
        # Threading and async support
        self._lock = threading.RLock()
        self._monitoring_task: Optional[asyncio.Task] = None
        self._optimization_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
        
        # Performance tracking
        self._performance_baseline: Optional[Dict[str, float]] = None
        self._trend_analysis: Dict[str, List[float]] = defaultdict(list)
        
        logger.info(
            "Connection pool optimizer initialized",
            pool_name=pool_name,
            strategy=optimization_strategy.value,
            auto_optimization=enable_auto_optimization
        )
    
    async def start_monitoring(self) -> None:
        """Start background monitoring and optimization tasks."""
        if self._monitoring_task is not None:
            logger.warning("Monitoring already started", pool_name=self.pool_name)
            return
        
        logger.info("Starting connection pool monitoring", pool_name=self.pool_name)
        
        # Start monitoring task
        self._monitoring_task = asyncio.create_task(self._monitoring_loop())
        
        # Start optimization task if auto-optimization is enabled
        if self.enable_auto_optimization:
            self._optimization_task = asyncio.create_task(self._optimization_loop())
        
        logger.info("Connection pool monitoring started", pool_name=self.pool_name)
    
    async def stop_monitoring(self) -> None:
        """Stop background monitoring and optimization tasks."""
        logger.info("Stopping connection pool monitoring", pool_name=self.pool_name)
        
        # Signal shutdown
        self._shutdown_event.set()
        
        # Cancel tasks
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
            self._monitoring_task = None
        
        if self._optimization_task:
            self._optimization_task.cancel()
            try:
                await self._optimization_task
            except asyncio.CancelledError:
                pass
            self._optimization_task = None
        
        logger.info("Connection pool monitoring stopped", pool_name=self.pool_name)
    
    async def _monitoring_loop(self) -> None:
        """Background monitoring loop."""
        while not self._shutdown_event.is_set():
            try:
                await self._collect_metrics()
                await self._analyze_trends()
                await self._detect_issues()
                
                # Store historical metrics
                with self._lock:
                    self.historical_metrics.append(self.current_metrics)
                
                await asyncio.sleep(self.monitoring_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(
                    "Error in monitoring loop",
                    pool_name=self.pool_name,
                    error=str(e)
                )
                await asyncio.sleep(self.monitoring_interval)
    
    async def _optimization_loop(self) -> None:
        """Background optimization loop."""
        while not self._shutdown_event.is_set():
            try:
                # Wait for optimization interval
                await asyncio.sleep(self.optimization_interval)
                
                if self._shutdown_event.is_set():
                    break
                
                # Run optimization
                optimization_result = await self.optimize_pool()
                
                # Log optimization results
                if optimization_result.get("optimizations_applied"):
                    logger.info(
                        "Automatic pool optimization completed",
                        pool_name=self.pool_name,
                        optimizations=len(optimization_result["optimizations_applied"])
                    )
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(
                    "Error in optimization loop",
                    pool_name=self.pool_name,
                    error=str(e)
                )
    
    async def _collect_metrics(self) -> None:
        """Collect current pool metrics."""
        # This method should be overridden by database-specific implementations
        # For now, we'll update the timestamp
        with self._lock:
            self.current_metrics.last_updated = datetime.now()
    
    async def _analyze_trends(self) -> None:
        """Analyze performance trends."""
        if len(self.historical_metrics) < 10:
            return  # Need more data points
        
        with self._lock:
            # Analyze utilization trend
            recent_utilizations = [m.utilization_percentage for m in list(self.historical_metrics)[-10:]]
            self._trend_analysis["utilization"] = recent_utilizations
            
            # Analyze checkout time trend
            recent_checkout_times = [m.average_checkout_time for m in list(self.historical_metrics)[-10:]]
            self._trend_analysis["checkout_time"] = recent_checkout_times
            
            # Analyze error rate trend
            recent_error_rates = [
                (m.connection_errors / max(1, m.total_connection_requests)) * 100
                for m in list(self.historical_metrics)[-10:]
            ]
            self._trend_analysis["error_rate"] = recent_error_rates
    
    async def _detect_issues(self) -> None:
        """Detect potential issues with the connection pool."""
        issues = []
        
        with self._lock:
            metrics = self.current_metrics
            
            # High utilization warning
            if metrics.utilization_percentage > 90:
                issues.append({
                    "type": "high_utilization",
                    "severity": "critical",
                    "message": f"Pool utilization is {metrics.utilization_percentage:.1f}%",
                    "recommendation": "Consider increasing pool size"
                })
            elif metrics.utilization_percentage > 80:
                issues.append({
                    "type": "high_utilization",
                    "severity": "warning",
                    "message": f"Pool utilization is {metrics.utilization_percentage:.1f}%",
                    "recommendation": "Monitor closely, may need pool size increase"
                })
            
            # Connection timeout warnings
            if metrics.connection_timeouts > 0:
                timeout_rate = (metrics.connection_timeouts / max(1, metrics.total_connection_requests)) * 100
                if timeout_rate > 5:
                    issues.append({
                        "type": "connection_timeouts",
                        "severity": "critical",
                        "message": f"Connection timeout rate is {timeout_rate:.1f}%",
                        "recommendation": "Increase pool timeout or pool size"
                    })
                elif timeout_rate > 1:
                    issues.append({
                        "type": "connection_timeouts",
                        "severity": "warning",
                        "message": f"Connection timeout rate is {timeout_rate:.1f}%",
                        "recommendation": "Monitor connection performance"
                    })
            
            # Connection leak detection
            if metrics.connection_leaks_detected > 0:
                issues.append({
                    "type": "connection_leaks",
                    "severity": "critical",
                    "message": f"Detected {metrics.connection_leaks_detected} connection leaks",
                    "recommendation": "Review application code for unclosed connections"
                })
            
            # Stale connection warnings
            if metrics.stale_connections > metrics.pool_size * 0.3:
                issues.append({
                    "type": "stale_connections",
                    "severity": "warning",
                    "message": f"Found {metrics.stale_connections} stale connections",
                    "recommendation": "Consider reducing connection recycle time"
                })
        
        # Log issues
        for issue in issues:
            if issue["severity"] == "critical":
                logger.error(
                    "Critical pool issue detected",
                    pool_name=self.pool_name,
                    issue_type=issue["type"],
                    message=issue["message"]
                )
            else:
                logger.warning(
                    "Pool issue detected",
                    pool_name=self.pool_name,
                    issue_type=issue["type"],
                    message=issue["message"]
                )
    
    def record_connection_checkout(self, connection_id: str, checkout_time: float) -> None:
        """Record a connection checkout event."""
        with self._lock:
            self.checkout_times.append(checkout_time)
            self.connection_events.append({
                "event": "checkout",
                "connection_id": connection_id,
                "timestamp": datetime.now(),
                "duration": checkout_time
            })
            
            # Update connection metrics
            if connection_id not in self.connection_metrics:
                self.connection_metrics[connection_id] = ConnectionMetrics(
                    connection_id=connection_id,
                    created_at=datetime.now(),
                    last_used=datetime.now()
                )
            
            conn_metrics = self.connection_metrics[connection_id]
            conn_metrics.last_used = datetime.now()
            conn_metrics.usage_count += 1
            
            # Update pool metrics
            self.current_metrics.checked_out += 1
            self.current_metrics.total_connection_requests += 1
            
            if checkout_time > self.connection_timeout_threshold:
                self.current_metrics.connection_timeouts += 1
    
    def record_connection_checkin(self, connection_id: str, checkin_time: float, had_error: bool = False) -> None:
        """Record a connection checkin event."""
        with self._lock:
            self.checkin_times.append(checkin_time)
            self.connection_events.append({
                "event": "checkin",
                "connection_id": connection_id,
                "timestamp": datetime.now(),
                "duration": checkin_time,
                "had_error": had_error
            })
            
            # Update connection metrics
            if connection_id in self.connection_metrics:
                conn_metrics = self.connection_metrics[connection_id]
                if had_error:
                    conn_metrics.error_count += 1
                    conn_metrics.is_healthy = False
                    self.current_metrics.connection_errors += 1
            
            # Update pool metrics
            self.current_metrics.checked_out = max(0, self.current_metrics.checked_out - 1)
            self.current_metrics.checked_in += 1
    
    def record_connection_error(self, connection_id: str, error: str) -> None:
        """Record a connection error."""
        with self._lock:
            self.error_events.append({
                "connection_id": connection_id,
                "error": error,
                "timestamp": datetime.now()
            })
            
            if connection_id in self.connection_metrics:
                conn_metrics = self.connection_metrics[connection_id]
                conn_metrics.error_count += 1
                conn_metrics.last_error = error
                conn_metrics.is_healthy = False
            
            self.current_metrics.connection_errors += 1
    
    def get_optimization_recommendations(self) -> List[OptimizationRecommendation]:
        """Get current optimization recommendations."""
        recommendations = []
        
        with self._lock:
            metrics = self.current_metrics
            
            # Pool size recommendations
            if metrics.utilization_percentage > 85:
                recommendations.append(OptimizationRecommendation(
                    type="increase_pool_size",
                    priority="high",
                    description="Pool utilization is high, consider increasing pool size",
                    current_value=metrics.pool_size,
                    recommended_value=min(metrics.pool_size + 5, self.max_pool_size),
                    expected_impact="Reduced connection wait times and timeouts",
                    implementation_complexity="low",
                    estimated_improvement=15.0,
                    risks=["Increased memory usage", "More database connections"]
                ))
            elif metrics.utilization_percentage < 30 and metrics.pool_size > self.min_pool_size:
                recommendations.append(OptimizationRecommendation(
                    type="decrease_pool_size",
                    priority="medium",
                    description="Pool utilization is low, consider decreasing pool size",
                    current_value=metrics.pool_size,
                    recommended_value=max(metrics.pool_size - 2, self.min_pool_size),
                    expected_impact="Reduced memory usage and resource consumption",
                    implementation_complexity="low",
                    estimated_improvement=10.0,
                    risks=["Potential connection waits during traffic spikes"]
                ))
            
            # Overflow recommendations
            if metrics.overflow_count > metrics.pool_size * 0.5:
                recommendations.append(OptimizationRecommendation(
                    type="increase_max_overflow",
                    priority="medium",
                    description="High overflow usage detected",
                    current_value=metrics.max_overflow,
                    recommended_value=min(metrics.max_overflow + 10, 50),
                    expected_impact="Better handling of traffic spikes",
                    implementation_complexity="low",
                    estimated_improvement=12.0,
                    risks=["Increased resource usage during spikes"]
                ))
            
            # Timeout recommendations
            if metrics.connection_timeouts > 0:
                timeout_rate = (metrics.connection_timeouts / max(1, metrics.total_connection_requests)) * 100
                if timeout_rate > 2:
                    recommendations.append(OptimizationRecommendation(
                        type="increase_pool_timeout",
                        priority="high",
                        description=f"Connection timeout rate is {timeout_rate:.1f}%",
                        current_value="current_timeout",  # Would need actual value
                        recommended_value="increased_timeout",
                        expected_impact="Reduced connection timeout errors",
                        implementation_complexity="low",
                        estimated_improvement=20.0,
                        risks=["Longer wait times for connections"]
                    ))
            
            # Connection health recommendations
            unhealthy_percentage = (metrics.unhealthy_connections / max(1, metrics.pool_size)) * 100
            if unhealthy_percentage > 20:
                recommendations.append(OptimizationRecommendation(
                    type="connection_health_check",
                    priority="high",
                    description=f"{unhealthy_percentage:.1f}% of connections are unhealthy",
                    current_value=metrics.unhealthy_connections,
                    recommended_value=0,
                    expected_impact="Improved connection reliability",
                    implementation_complexity="medium",
                    estimated_improvement=25.0,
                    risks=["Temporary connection disruption during cleanup"],
                    prerequisites=["Enable connection health checks", "Review error patterns"]
                ))
        
        return recommendations
    
    async def optimize_pool(self) -> Dict[str, Any]:
        """
        Perform pool optimization based on current metrics and strategy.
        
        Returns:
            Dictionary with optimization results and applied changes
        """
        optimization_start = datetime.now()
        
        try:
            # Get current recommendations
            recommendations = self.get_optimization_recommendations()
            
            # Filter recommendations based on strategy
            filtered_recommendations = self._filter_recommendations_by_strategy(recommendations)
            
            # Apply optimizations if auto-optimization is enabled
            applied_optimizations = []
            if self.enable_auto_optimization:
                for recommendation in filtered_recommendations:
                    if recommendation.priority in ["high", "critical"]:
                        # Apply high-priority optimizations automatically
                        result = await self._apply_optimization(recommendation)
                        if result["success"]:
                            applied_optimizations.append(result)
            
            # Update optimization history
            optimization_result = {
                "timestamp": optimization_start.isoformat(),
                "strategy": self.optimization_strategy.value,
                "recommendations_generated": len(recommendations),
                "recommendations_filtered": len(filtered_recommendations),
                "optimizations_applied": applied_optimizations,
                "metrics_snapshot": self.current_metrics,
                "duration_ms": (datetime.now() - optimization_start).total_seconds() * 1000
            }
            
            with self._lock:
                self.optimization_history.append(optimization_result)
                self.last_optimization = optimization_start
            
            logger.info(
                "Pool optimization completed",
                pool_name=self.pool_name,
                recommendations=len(recommendations),
                applied=len(applied_optimizations)
            )
            
            return optimization_result
            
        except Exception as e:
            logger.error(
                "Error during pool optimization",
                pool_name=self.pool_name,
                error=str(e)
            )
            return {
                "timestamp": optimization_start.isoformat(),
                "error": str(e),
                "success": False
            }
    
    def _filter_recommendations_by_strategy(
        self, 
        recommendations: List[OptimizationRecommendation]
    ) -> List[OptimizationRecommendation]:
        """Filter recommendations based on optimization strategy."""
        if self.optimization_strategy == OptimizationStrategy.CONSERVATIVE:
            # Only apply low-risk, high-impact optimizations
            return [
                r for r in recommendations 
                if r.implementation_complexity == "low" and r.estimated_improvement > 10
            ]
        elif self.optimization_strategy == OptimizationStrategy.BALANCED:
            # Apply medium-risk optimizations with good impact
            return [
                r for r in recommendations 
                if r.implementation_complexity in ["low", "medium"] and r.estimated_improvement > 5
            ]
        elif self.optimization_strategy == OptimizationStrategy.AGGRESSIVE:
            # Apply all optimizations with positive impact
            return [r for r in recommendations if r.estimated_improvement > 0]
        else:  # CUSTOM
            # Return all recommendations for manual review
            return recommendations
    
    async def _apply_optimization(self, recommendation: OptimizationRecommendation) -> Dict[str, Any]:
        """
        Apply a specific optimization recommendation.
        
        This method should be overridden by database-specific implementations.
        """
        logger.info(
            "Applying optimization",
            pool_name=self.pool_name,
            type=recommendation.type,
            priority=recommendation.priority
        )
        
        # Placeholder implementation
        return {
            "success": True,
            "type": recommendation.type,
            "message": f"Applied {recommendation.type} optimization",
            "old_value": recommendation.current_value,
            "new_value": recommendation.recommended_value
        }
    
    def get_performance_report(self) -> Dict[str, Any]:
        """Generate comprehensive performance report."""
        with self._lock:
            metrics = self.current_metrics
            
            # Calculate performance scores
            utilization_score = min(100, (1 - abs(metrics.utilization_percentage - (self.target_utilization * 100)) / 100) * 100)
            error_rate = (metrics.connection_errors / max(1, metrics.total_connection_requests)) * 100
            error_score = max(0, 100 - error_rate * 10)
            timeout_rate = (metrics.connection_timeouts / max(1, metrics.total_connection_requests)) * 100
            timeout_score = max(0, 100 - timeout_rate * 20)
            
            overall_score = (utilization_score + error_score + timeout_score) / 3
            
            return {
                "pool_name": self.pool_name,
                "timestamp": datetime.now().isoformat(),
                "overall_score": round(overall_score, 1),
                "scores": {
                    "utilization": round(utilization_score, 1),
                    "error_rate": round(error_score, 1),
                    "timeout_rate": round(timeout_score, 1)
                },
                "metrics": {
                    "pool_size": metrics.pool_size,
                    "utilization_percentage": round(metrics.utilization_percentage, 1),
                    "average_checkout_time": round(metrics.average_checkout_time, 3),
                    "connection_errors": metrics.connection_errors,
                    "connection_timeouts": metrics.connection_timeouts,
                    "total_requests": metrics.total_connection_requests,
                    "healthy_connections": metrics.healthy_connections,
                    "unhealthy_connections": metrics.unhealthy_connections
                },
                "trends": {
                    "utilization": self._trend_analysis.get("utilization", [])[-5:],
                    "checkout_time": self._trend_analysis.get("checkout_time", [])[-5:],
                    "error_rate": self._trend_analysis.get("error_rate", [])[-5:]
                },
                "recommendations": [
                    {
                        "type": r.type,
                        "priority": r.priority,
                        "description": r.description,
                        "estimated_improvement": r.estimated_improvement
                    }
                    for r in self.get_optimization_recommendations()
                ],
                "optimization_history": self.optimization_history[-5:] if self.optimization_history else []
            }
    
    def reset_metrics(self) -> None:
        """Reset all metrics and counters."""
        with self._lock:
            self.current_metrics = PoolOptimizationMetrics()
            self.historical_metrics.clear()
            self.connection_metrics.clear()
            self.checkout_times.clear()
            self.checkin_times.clear()
            self.connection_events.clear()
            self.error_events.clear()
            self._trend_analysis.clear()
            
        logger.info("Pool metrics reset", pool_name=self.pool_name)
    
    def export_metrics(self, format: str = "json") -> str:
        """Export metrics in specified format."""
        report = self.get_performance_report()
        
        if format.lower() == "json":
            import json
            return json.dumps(report, indent=2, default=str)
        elif format.lower() == "csv":
            # Simple CSV export of key metrics
            import csv
            import io
            
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Header
            writer.writerow([
                "timestamp", "pool_size", "utilization_percentage", 
                "average_checkout_time", "connection_errors", "connection_timeouts",
                "overall_score"
            ])
            
            # Data
            writer.writerow([
                report["timestamp"],
                report["metrics"]["pool_size"],
                report["metrics"]["utilization_percentage"],
                report["metrics"]["average_checkout_time"],
                report["metrics"]["connection_errors"],
                report["metrics"]["connection_timeouts"],
                report["overall_score"]
            ])
            
            return output.getvalue()
        else:
            raise ValueError(f"Unsupported export format: {format}")