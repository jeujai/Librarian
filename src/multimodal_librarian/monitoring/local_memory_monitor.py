"""
Local Development Memory Monitor

This module provides memory monitoring specifically for local development environments:
- Integration with Docker containers
- Memory usage tracking and alerts
- Resource optimization recommendations
- Memory leak detection for local services
"""

import asyncio
import logging
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import docker
import psutil

from ..config import get_settings
from ..logging_config import get_logger

logger = get_logger("local_memory_monitor")

@dataclass
class LocalMemoryMetrics:
    """Memory metrics for local development environment."""
    timestamp: datetime
    system_memory_mb: float
    system_memory_percent: float
    available_memory_mb: float
    container_memory_usage: Dict[str, float]  # container_name -> memory_mb
    container_memory_limits: Dict[str, float]  # container_name -> limit_mb
    container_memory_percent: Dict[str, float]  # container_name -> percent
    total_container_memory_mb: float
    memory_alerts: List[str]
    optimization_suggestions: List[str]

class LocalMemoryMonitor:
    """Memory monitor for local development environment."""
    
    def __init__(self, alert_threshold: float = 85.0, check_interval: int = 30):
        self.alert_threshold = alert_threshold
        self.check_interval = check_interval
        self.metrics_history: deque = deque(maxlen=100)  # Keep last 100 measurements
        self.is_monitoring = False
        self.monitor_task: Optional[asyncio.Task] = None
        
        # Docker client setup
        try:
            self.docker_client = docker.from_env()
            self.docker_available = True
            logger.info("Docker client initialized for memory monitoring")
        except Exception as e:
            logger.warning(f"Docker not available for memory monitoring: {e}")
            self.docker_client = None
            self.docker_available = False
        
        # Local development container names (from docker-compose.local.yml)
        self.monitored_containers = [
            'multimodal-librarian-multimodal-librarian-1',
            'multimodal-librarian-postgres-1',
            'multimodal-librarian-neo4j-1',
            'multimodal-librarian-milvus-1',
            'multimodal-librarian-redis-1',
            'multimodal-librarian-etcd-1',
            'multimodal-librarian-minio-1'
        ]
        
        # Memory thresholds for different services
        self.service_thresholds = {
            'postgres': 80.0,
            'neo4j': 85.0,
            'milvus': 90.0,
            'redis': 75.0,
            'multimodal-librarian': 80.0
        }
    
    def _get_system_memory_info(self) -> Tuple[float, float, float]:
        """Get system memory information."""
        memory = psutil.virtual_memory()
        return (
            memory.used / (1024 * 1024),  # used_mb
            memory.percent,  # percent
            memory.available / (1024 * 1024)  # available_mb
        )
    
    def _get_container_memory_info_sync(self) -> Tuple[Dict[str, float], Dict[str, float], Dict[str, float]]:
        """Get memory information for all monitored containers (synchronous version).
        
        This method contains blocking Docker API calls and should be run in a thread pool.
        """
        container_usage = {}
        container_limits = {}
        container_percent = {}
        
        if not self.docker_available:
            return container_usage, container_limits, container_percent
        
        for container_name in self.monitored_containers:
            try:
                container = self.docker_client.containers.get(container_name)
                if container.status != 'running':
                    continue
                
                # This is a blocking call - should be run in executor
                stats = container.stats(stream=False)
                
                # Extract memory information
                memory_usage = stats['memory_stats']['usage']
                memory_limit = stats['memory_stats']['limit']
                
                usage_mb = memory_usage / (1024 * 1024)
                limit_mb = memory_limit / (1024 * 1024)
                percent = (memory_usage / memory_limit) * 100.0
                
                container_usage[container_name] = usage_mb
                container_limits[container_name] = limit_mb
                container_percent[container_name] = percent
                
            except docker.errors.NotFound:
                logger.debug(f"Container {container_name} not found")
                continue
            except Exception as e:
                logger.debug(f"Error getting stats for {container_name}: {e}")
                continue
        
        return container_usage, container_limits, container_percent
    
    async def _get_container_memory_info(self) -> Tuple[Dict[str, float], Dict[str, float], Dict[str, float]]:
        """Get memory information for all monitored containers (async version).
        
        Runs the blocking Docker API calls in a thread pool to avoid blocking the event loop.
        """
        if not self.docker_available:
            return {}, {}, {}
        
        try:
            # Run blocking Docker calls in thread pool with timeout
            loop = asyncio.get_event_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(None, self._get_container_memory_info_sync),
                timeout=10.0  # 10 second timeout
            )
            return result
        except asyncio.TimeoutError:
            logger.warning("Docker container memory info collection timed out")
            return {}, {}, {}
        except Exception as e:
            logger.debug(f"Error getting container memory info: {e}")
            return {}, {}, {}
    
    def _generate_alerts(self, system_percent: float, container_percent: Dict[str, float]) -> List[str]:
        """Generate memory alerts based on current usage."""
        alerts = []
        
        # System memory alerts
        if system_percent > self.alert_threshold:
            alerts.append(f"System memory usage high: {system_percent:.1f}%")
        
        if system_percent > 95:
            alerts.append(f"System memory critical: {system_percent:.1f}%")
        
        # Container memory alerts
        for container_name, percent in container_percent.items():
            # Extract service name from container name
            service_name = self._extract_service_name(container_name)
            threshold = self.service_thresholds.get(service_name, self.alert_threshold)
            
            if percent > threshold:
                alerts.append(f"{service_name} memory usage high: {percent:.1f}%")
            
            if percent > 95:
                alerts.append(f"{service_name} memory critical: {percent:.1f}%")
        
        return alerts
    
    def _extract_service_name(self, container_name: str) -> str:
        """Extract service name from container name."""
        # Remove prefix and suffix to get service name
        if 'multimodal-librarian-' in container_name:
            service = container_name.replace('multimodal-librarian-', '').replace('-1', '')
            return service
        return container_name
    
    def _generate_optimization_suggestions(self, metrics: LocalMemoryMetrics) -> List[str]:
        """Generate memory optimization suggestions."""
        suggestions = []
        
        # System-level suggestions
        if metrics.system_memory_percent > 80:
            suggestions.append("Consider increasing system RAM or reducing running services")
        
        if metrics.available_memory_mb < 500:
            suggestions.append("Low available memory - consider closing unnecessary applications")
        
        # Container-level suggestions
        for container_name, usage_mb in metrics.container_memory_usage.items():
            service_name = self._extract_service_name(container_name)
            limit_mb = metrics.container_memory_limits.get(container_name, 0)
            percent = metrics.container_memory_percent.get(container_name, 0)
            
            if limit_mb > 0:
                # Over-provisioned containers
                if percent < 30 and limit_mb > 500:
                    suggestions.append(f"{service_name}: Consider reducing memory limit (using {percent:.1f}% of {limit_mb:.0f}MB)")
                
                # Under-provisioned containers
                elif percent > 85:
                    new_limit = limit_mb * 1.3
                    suggestions.append(f"{service_name}: Consider increasing memory limit to {new_limit:.0f}MB")
                
                # Efficient usage
                elif 50 <= percent <= 80:
                    suggestions.append(f"{service_name}: Memory usage is optimal ({percent:.1f}%)")
        
        # Docker-specific suggestions
        if self.docker_available and metrics.total_container_memory_mb > metrics.system_memory_mb * 0.8:
            suggestions.append("Container memory limits exceed 80% of system memory - consider optimization")
        
        return suggestions
    
    async def collect_metrics(self) -> LocalMemoryMetrics:
        """Collect current memory metrics."""
        # Get system memory info (non-blocking)
        system_memory_mb, system_percent, available_mb = self._get_system_memory_info()
        
        # Get container memory info (async - runs in thread pool)
        container_usage, container_limits, container_percent = await self._get_container_memory_info()
        
        # Calculate total container memory usage
        total_container_memory = sum(container_usage.values())
        
        # Generate alerts
        alerts = self._generate_alerts(system_percent, container_percent)
        
        # Create metrics object
        metrics = LocalMemoryMetrics(
            timestamp=datetime.now(),
            system_memory_mb=system_memory_mb,
            system_memory_percent=system_percent,
            available_memory_mb=available_mb,
            container_memory_usage=container_usage,
            container_memory_limits=container_limits,
            container_memory_percent=container_percent,
            total_container_memory_mb=total_container_memory,
            memory_alerts=alerts,
            optimization_suggestions=[]  # Will be filled by optimization analysis
        )
        
        # Generate optimization suggestions
        metrics.optimization_suggestions = self._generate_optimization_suggestions(metrics)
        
        return metrics
    
    async def start_monitoring(self) -> None:
        """Start continuous memory monitoring."""
        if self.is_monitoring:
            logger.warning("Memory monitoring is already running")
            return
        
        self.is_monitoring = True
        self.monitor_task = asyncio.create_task(self._monitoring_loop())
        logger.info(f"Started local memory monitoring (interval: {self.check_interval}s)")
    
    async def stop_monitoring(self) -> None:
        """Stop memory monitoring."""
        if not self.is_monitoring:
            return
        
        self.is_monitoring = False
        if self.monitor_task:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Stopped local memory monitoring")
    
    async def _monitoring_loop(self) -> None:
        """Main monitoring loop."""
        try:
            while self.is_monitoring:
                try:
                    # Collect metrics
                    metrics = await self.collect_metrics()
                    self.metrics_history.append(metrics)
                    
                    # Log alerts
                    for alert in metrics.memory_alerts:
                        logger.warning(f"MEMORY ALERT: {alert}")
                    
                    # Log optimization suggestions (less frequently)
                    if len(self.metrics_history) % 10 == 0:  # Every 10 cycles
                        for suggestion in metrics.optimization_suggestions:
                            logger.info(f"OPTIMIZATION: {suggestion}")
                    
                    # Log current status
                    logger.debug(f"Memory status - System: {metrics.system_memory_percent:.1f}%, "
                               f"Containers: {len(metrics.container_memory_usage)}, "
                               f"Total container memory: {metrics.total_container_memory_mb:.1f}MB")
                    
                except Exception as e:
                    logger.error(f"Error in memory monitoring cycle: {e}")
                
                # Wait for next cycle
                await asyncio.sleep(self.check_interval)
                
        except asyncio.CancelledError:
            logger.info("Memory monitoring loop cancelled")
            raise
    
    def get_current_status(self) -> Dict[str, Any]:
        """Get current memory status."""
        if not self.metrics_history:
            return {"status": "no_data", "message": "No memory data available"}
        
        latest_metrics = self.metrics_history[-1]
        
        return {
            "status": "active" if self.is_monitoring else "inactive",
            "timestamp": latest_metrics.timestamp.isoformat(),
            "system_memory": {
                "used_mb": latest_metrics.system_memory_mb,
                "percent": latest_metrics.system_memory_percent,
                "available_mb": latest_metrics.available_memory_mb
            },
            "containers": {
                name: {
                    "usage_mb": usage,
                    "limit_mb": latest_metrics.container_memory_limits.get(name, 0),
                    "percent": latest_metrics.container_memory_percent.get(name, 0)
                }
                for name, usage in latest_metrics.container_memory_usage.items()
            },
            "total_container_memory_mb": latest_metrics.total_container_memory_mb,
            "alerts": latest_metrics.memory_alerts,
            "suggestions": latest_metrics.optimization_suggestions,
            "monitoring_active": self.is_monitoring,
            "docker_available": self.docker_available
        }
    
    def get_memory_history(self, minutes: int = 60) -> List[Dict[str, Any]]:
        """Get memory history for the specified number of minutes."""
        cutoff_time = datetime.now() - timedelta(minutes=minutes)
        
        history = []
        for metrics in self.metrics_history:
            if metrics.timestamp >= cutoff_time:
                history.append({
                    "timestamp": metrics.timestamp.isoformat(),
                    "system_memory_percent": metrics.system_memory_percent,
                    "system_memory_mb": metrics.system_memory_mb,
                    "available_memory_mb": metrics.available_memory_mb,
                    "total_container_memory_mb": metrics.total_container_memory_mb,
                    "container_count": len(metrics.container_memory_usage),
                    "alert_count": len(metrics.memory_alerts)
                })
        
        return history
    
    def analyze_memory_trends(self) -> Dict[str, Any]:
        """Analyze memory usage trends."""
        if len(self.metrics_history) < 2:
            return {"status": "insufficient_data"}
        
        # Get recent metrics (last 30 measurements)
        recent_metrics = list(self.metrics_history)[-30:]
        
        # System memory trend
        system_memory_values = [m.system_memory_percent for m in recent_metrics]
        system_trend = "stable"
        if len(system_memory_values) > 5:
            recent_avg = sum(system_memory_values[-5:]) / 5
            older_avg = sum(system_memory_values[:5]) / 5
            
            if recent_avg > older_avg + 5:
                system_trend = "increasing"
            elif recent_avg < older_avg - 5:
                system_trend = "decreasing"
        
        # Container memory trends
        container_trends = {}
        for container_name in self.monitored_containers:
            container_values = []
            for metrics in recent_metrics:
                if container_name in metrics.container_memory_percent:
                    container_values.append(metrics.container_memory_percent[container_name])
            
            if len(container_values) > 5:
                recent_avg = sum(container_values[-5:]) / 5
                older_avg = sum(container_values[:5]) / 5
                
                if recent_avg > older_avg + 10:
                    container_trends[container_name] = "increasing"
                elif recent_avg < older_avg - 10:
                    container_trends[container_name] = "decreasing"
                else:
                    container_trends[container_name] = "stable"
        
        return {
            "status": "analyzed",
            "analysis_period_minutes": len(recent_metrics) * (self.check_interval / 60),
            "system_memory_trend": system_trend,
            "container_memory_trends": container_trends,
            "total_measurements": len(recent_metrics),
            "current_system_usage": system_memory_values[-1] if system_memory_values else 0
        }

# Global instance for the application
_local_memory_monitor: Optional[LocalMemoryMonitor] = None

def get_local_memory_monitor() -> LocalMemoryMonitor:
    """Get the global local memory monitor instance."""
    global _local_memory_monitor
    if _local_memory_monitor is None:
        _local_memory_monitor = LocalMemoryMonitor()
    return _local_memory_monitor

async def start_local_memory_monitoring() -> None:
    """Start local memory monitoring."""
    monitor = get_local_memory_monitor()
    await monitor.start_monitoring()

async def stop_local_memory_monitoring() -> None:
    """Stop local memory monitoring."""
    monitor = get_local_memory_monitor()
    await monitor.stop_monitoring()

def get_memory_status() -> Dict[str, Any]:
    """Get current memory status."""
    monitor = get_local_memory_monitor()
    return monitor.get_current_status()