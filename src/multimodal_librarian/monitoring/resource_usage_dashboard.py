"""
Resource Usage Dashboard for Local Development

This module provides comprehensive resource usage dashboards specifically designed for
local development environments with Docker containers. It integrates with existing
monitoring systems to provide real-time resource visualization and optimization insights.

Features:
- Real-time system and container resource monitoring
- Interactive dashboards with multiple chart types
- Resource optimization recommendations
- Historical trend analysis
- Docker container resource tracking
- Performance bottleneck identification
- Memory leak detection
- Resource allocation optimization

Validates: Requirements NFR-1 (Performance), NFR-2 (Reliability), TR-4 (Service Discovery)
"""

import asyncio
import json
import logging
import statistics
import time
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

import docker
import psutil

from ..config import get_settings
from ..logging_config import get_logger
from .comprehensive_metrics_collector import ComprehensiveMetricsCollector
from .local_memory_monitor import get_local_memory_monitor
from .performance_dashboard import ChartType, DashboardChart, PerformanceDashboard

logger = get_logger("resource_usage_dashboard")

class ResourceType(Enum):
    """Types of resources being monitored."""
    CPU = "cpu"
    MEMORY = "memory"
    DISK = "disk"
    NETWORK = "network"
    CONTAINER = "container"

@dataclass
class ResourceAlert:
    """Resource usage alert."""
    alert_id: str
    resource_type: ResourceType
    severity: str  # "info", "warning", "critical"
    message: str
    current_value: float
    threshold: float
    timestamp: datetime
    container_name: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "resource_type": self.resource_type.value,
            "severity": self.severity,
            "message": self.message,
            "current_value": self.current_value,
            "threshold": self.threshold,
            "timestamp": self.timestamp.isoformat(),
            "container_name": self.container_name
        }

@dataclass
class ResourceOptimization:
    """Resource optimization recommendation."""
    optimization_id: str
    resource_type: ResourceType
    priority: str  # "low", "medium", "high"
    title: str
    description: str
    impact: str
    implementation_effort: str
    estimated_savings: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "optimization_id": self.optimization_id,
            "resource_type": self.resource_type.value,
            "priority": self.priority,
            "title": self.title,
            "description": self.description,
            "impact": self.impact,
            "implementation_effort": self.implementation_effort,
            "estimated_savings": self.estimated_savings
        }

class ResourceUsageDashboardService:
    """
    Comprehensive resource usage dashboard service for local development.
    
    Provides real-time monitoring and visualization of:
    - System resources (CPU, Memory, Disk, Network)
    - Docker container resources
    - Resource trends and patterns
    - Optimization recommendations
    - Performance bottlenecks
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.logger = get_logger("resource_dashboard")
        
        # Initialize monitoring services
        self.metrics_collector = ComprehensiveMetricsCollector()
        self.memory_monitor = get_local_memory_monitor()
        
        # Docker client setup
        try:
            self.docker_client = docker.from_env()
            self.docker_available = True
            self.logger.info("Docker client initialized for resource monitoring")
        except Exception as e:
            self.logger.warning(f"Docker not available: {e}")
            self.docker_client = None
            self.docker_available = False
        
        # Resource monitoring state
        self.resource_history: deque = deque(maxlen=1440)  # 24 hours at 1-minute intervals
        self.container_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1440))
        self.active_alerts: List[ResourceAlert] = []
        self.optimization_recommendations: List[ResourceOptimization] = []
        
        # Monitoring configuration
        self.monitoring_active = False
        self.monitor_task: Optional[asyncio.Task] = None
        self.collection_interval = 60  # seconds
        
        # Resource thresholds
        self.thresholds = {
            "cpu_warning": 70.0,
            "cpu_critical": 85.0,
            "memory_warning": 75.0,
            "memory_critical": 90.0,
            "disk_warning": 80.0,
            "disk_critical": 95.0,
            "container_memory_warning": 80.0,
            "container_memory_critical": 95.0,
            "container_cpu_warning": 75.0,
            "container_cpu_critical": 90.0
        }
        
        # Initialize dashboards
        self.dashboards: Dict[str, PerformanceDashboard] = {}
        self._initialize_resource_dashboards()
        
        self.logger.info("Resource usage dashboard service initialized")
    
    def _initialize_resource_dashboards(self):
        """Initialize resource usage dashboards."""
        
        # System Resources Overview Dashboard
        system_charts = [
            DashboardChart(
                chart_id="system_cpu_usage",
                title="System CPU Usage",
                chart_type=ChartType.LINE,
                data_points=[],
                config={
                    "y_axis_label": "CPU Usage (%)",
                    "x_axis_label": "Time",
                    "color": "#3498db",
                    "warning_threshold": self.thresholds["cpu_warning"],
                    "critical_threshold": self.thresholds["cpu_critical"],
                    "show_thresholds": True
                },
                last_updated=datetime.now(),
                refresh_interval=30
            ),
            DashboardChart(
                chart_id="system_memory_usage",
                title="System Memory Usage",
                chart_type=ChartType.LINE,
                data_points=[],
                config={
                    "y_axis_label": "Memory Usage (%)",
                    "x_axis_label": "Time",
                    "color": "#2ecc71",
                    "warning_threshold": self.thresholds["memory_warning"],
                    "critical_threshold": self.thresholds["memory_critical"],
                    "show_thresholds": True
                },
                last_updated=datetime.now(),
                refresh_interval=30
            ),
            DashboardChart(
                chart_id="system_disk_usage",
                title="System Disk Usage",
                chart_type=ChartType.GAUGE,
                data_points=[],
                config={
                    "min_value": 0,
                    "max_value": 100,
                    "warning_threshold": self.thresholds["disk_warning"],
                    "critical_threshold": self.thresholds["disk_critical"],
                    "unit": "%",
                    "color_ranges": [
                        {"min": 0, "max": 70, "color": "#2ecc71"},
                        {"min": 70, "max": 80, "color": "#f39c12"},
                        {"min": 80, "max": 95, "color": "#e67e22"},
                        {"min": 95, "max": 100, "color": "#e74c3c"}
                    ]
                },
                last_updated=datetime.now(),
                refresh_interval=60
            ),
            DashboardChart(
                chart_id="resource_alerts_summary",
                title="Resource Alerts",
                chart_type=ChartType.ALERT_LIST,
                data_points=[],
                config={
                    "max_items": 8,
                    "show_severity": True,
                    "show_timestamps": True,
                    "severity_colors": {
                        "critical": "#e74c3c",
                        "warning": "#f39c12",
                        "info": "#3498db"
                    }
                },
                last_updated=datetime.now(),
                refresh_interval=15
            )
        ]
        
        system_dashboard = PerformanceDashboard(
            dashboard_id="system_resources",
            name="System Resources Overview",
            description="Real-time system resource monitoring and alerts",
            charts=system_charts,
            layout={
                "columns": 2,
                "rows": 2,
                "chart_positions": {
                    "system_cpu_usage": {"row": 0, "col": 0, "width": 1, "height": 1},
                    "system_memory_usage": {"row": 0, "col": 1, "width": 1, "height": 1},
                    "system_disk_usage": {"row": 1, "col": 0, "width": 1, "height": 1},
                    "resource_alerts_summary": {"row": 1, "col": 1, "width": 1, "height": 1}
                }
            }
        )
        
        self.dashboards["system_resources"] = system_dashboard
        
        # Container Resources Dashboard
        container_charts = [
            DashboardChart(
                chart_id="container_memory_breakdown",
                title="Container Memory Usage",
                chart_type=ChartType.BAR,
                data_points=[],
                config={
                    "y_axis_label": "Memory Usage (MB)",
                    "x_axis_label": "Container",
                    "color": "#9b59b6",
                    "show_values": True,
                    "sort_by": "value"
                },
                last_updated=datetime.now(),
                refresh_interval=30
            ),
            DashboardChart(
                chart_id="container_cpu_breakdown",
                title="Container CPU Usage",
                chart_type=ChartType.BAR,
                data_points=[],
                config={
                    "y_axis_label": "CPU Usage (%)",
                    "x_axis_label": "Container",
                    "color": "#e67e22",
                    "show_values": True,
                    "sort_by": "value"
                },
                last_updated=datetime.now(),
                refresh_interval=30
            ),
            DashboardChart(
                chart_id="container_resource_efficiency",
                title="Container Resource Efficiency",
                chart_type=ChartType.TABLE,
                data_points=[],
                config={
                    "columns": ["Container", "Memory Efficiency", "CPU Efficiency", "Status", "Recommendations"],
                    "sortable": True,
                    "highlight_inefficient": True
                },
                last_updated=datetime.now(),
                refresh_interval=60
            ),
            DashboardChart(
                chart_id="total_container_resources",
                title="Total Container Resources",
                chart_type=ChartType.PIE,
                data_points=[],
                config={
                    "show_percentages": True,
                    "colors": ["#3498db", "#2ecc71", "#f39c12", "#e74c3c", "#9b59b6"],
                    "labels": []  # Will be populated dynamically
                },
                last_updated=datetime.now(),
                refresh_interval=60
            )
        ]
        
        container_dashboard = PerformanceDashboard(
            dashboard_id="container_resources",
            name="Container Resources",
            description="Docker container resource usage and optimization",
            charts=container_charts,
            layout={
                "columns": 2,
                "rows": 2,
                "chart_positions": {
                    "container_memory_breakdown": {"row": 0, "col": 0, "width": 1, "height": 1},
                    "container_cpu_breakdown": {"row": 0, "col": 1, "width": 1, "height": 1},
                    "container_resource_efficiency": {"row": 1, "col": 0, "width": 1, "height": 1},
                    "total_container_resources": {"row": 1, "col": 1, "width": 1, "height": 1}
                }
            }
        )
        
        self.dashboards["container_resources"] = container_dashboard
        
        # Resource Trends Dashboard
        trends_charts = [
            DashboardChart(
                chart_id="resource_trends_24h",
                title="24-Hour Resource Trends",
                chart_type=ChartType.LINE,
                data_points=[],
                config={
                    "y_axis_label": "Usage (%)",
                    "x_axis_label": "Time",
                    "multiple_series": True,
                    "series": [
                        {"name": "CPU", "color": "#3498db"},
                        {"name": "Memory", "color": "#2ecc71"},
                        {"name": "Disk", "color": "#f39c12"}
                    ]
                },
                last_updated=datetime.now(),
                refresh_interval=300
            ),
            DashboardChart(
                chart_id="resource_optimization_opportunities",
                title="Optimization Opportunities",
                chart_type=ChartType.TABLE,
                data_points=[],
                config={
                    "columns": ["Resource", "Priority", "Impact", "Effort", "Savings"],
                    "sortable": True,
                    "highlight_high_priority": True
                },
                last_updated=datetime.now(),
                refresh_interval=300
            ),
            DashboardChart(
                chart_id="resource_efficiency_score",
                title="Resource Efficiency Score",
                chart_type=ChartType.GAUGE,
                data_points=[],
                config={
                    "min_value": 0,
                    "max_value": 100,
                    "unit": "score",
                    "color_ranges": [
                        {"min": 0, "max": 40, "color": "#e74c3c"},
                        {"min": 40, "max": 70, "color": "#f39c12"},
                        {"min": 70, "max": 85, "color": "#2ecc71"},
                        {"min": 85, "max": 100, "color": "#27ae60"}
                    ]
                },
                last_updated=datetime.now(),
                refresh_interval=300
            ),
            DashboardChart(
                chart_id="resource_bottlenecks",
                title="Resource Bottlenecks",
                chart_type=ChartType.HEATMAP,
                data_points=[],
                config={
                    "x_axis_label": "Hour of Day",
                    "y_axis_label": "Resource Type",
                    "color_scale": ["#2ecc71", "#f39c12", "#e74c3c"],
                    "value_label": "Usage Level"
                },
                last_updated=datetime.now(),
                refresh_interval=600
            )
        ]
        
        trends_dashboard = PerformanceDashboard(
            dashboard_id="resource_trends",
            name="Resource Trends & Optimization",
            description="Historical trends and optimization recommendations",
            charts=trends_charts,
            layout={
                "columns": 2,
                "rows": 2,
                "chart_positions": {
                    "resource_trends_24h": {"row": 0, "col": 0, "width": 2, "height": 1},
                    "resource_optimization_opportunities": {"row": 1, "col": 0, "width": 1, "height": 1},
                    "resource_efficiency_score": {"row": 1, "col": 1, "width": 1, "height": 1},
                    "resource_bottlenecks": {"row": 2, "col": 0, "width": 2, "height": 1}
                }
            }
        )
        
        self.dashboards["resource_trends"] = trends_dashboard
    
    async def start_monitoring(self) -> None:
        """Start resource usage monitoring."""
        if self.monitoring_active:
            self.logger.warning("Resource monitoring is already active")
            return
        
        self.monitoring_active = True
        self.monitor_task = asyncio.create_task(self._monitoring_loop())
        
        # Start memory monitoring if not already active
        if not self.memory_monitor.is_monitoring:
            await self.memory_monitor.start_monitoring()
        
        self.logger.info(f"Started resource usage monitoring (interval: {self.collection_interval}s)")
    
    async def stop_monitoring(self) -> None:
        """Stop resource usage monitoring."""
        if not self.monitoring_active:
            return
        
        self.monitoring_active = False
        if self.monitor_task:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass
            self.monitor_task = None
        
        self.logger.info("Stopped resource usage monitoring")
    
    async def _monitoring_loop(self) -> None:
        """Main monitoring loop."""
        try:
            while self.monitoring_active:
                try:
                    # Collect system resource metrics
                    await self._collect_system_metrics()
                    
                    # Collect container metrics
                    if self.docker_available:
                        await self._collect_container_metrics()
                    
                    # Update alerts
                    await self._update_resource_alerts()
                    
                    # Update optimization recommendations
                    await self._update_optimization_recommendations()
                    
                    # Log status
                    self.logger.debug(f"Resource monitoring cycle completed - "
                                    f"History: {len(self.resource_history)} samples, "
                                    f"Alerts: {len(self.active_alerts)}")
                    
                except Exception as e:
                    self.logger.error(f"Error in resource monitoring cycle: {e}")
                
                await asyncio.sleep(self.collection_interval)
                
        except asyncio.CancelledError:
            self.logger.info("Resource monitoring loop cancelled")
            raise
    
    async def _collect_system_metrics(self) -> None:
        """Collect system resource metrics."""
        try:
            # Get system metrics
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            network = psutil.net_io_counters()
            
            # Store metrics
            metrics = {
                "timestamp": datetime.now(),
                "cpu_percent": cpu_percent,
                "memory_percent": memory.percent,
                "memory_used_gb": memory.used / (1024**3),
                "memory_available_gb": memory.available / (1024**3),
                "disk_percent": disk.percent,
                "disk_used_gb": disk.used / (1024**3),
                "disk_free_gb": disk.free / (1024**3),
                "network_bytes_sent": network.bytes_sent,
                "network_bytes_recv": network.bytes_recv
            }
            
            self.resource_history.append(metrics)
            
        except Exception as e:
            self.logger.error(f"Error collecting system metrics: {e}")
    
    def _collect_container_metrics_sync(self) -> List[Dict[str, Any]]:
        """Collect Docker container metrics (synchronous version).
        
        This method contains blocking Docker API calls and should be run in a thread pool.
        """
        container_metrics_list = []
        
        if not self.docker_available:
            return container_metrics_list
        
        try:
            containers = self.docker_client.containers.list()
            
            for container in containers:
                try:
                    stats = container.stats(stream=False)
                    
                    # Calculate CPU percentage
                    cpu_delta = stats['cpu_stats']['cpu_usage']['total_usage'] - \
                               stats['precpu_stats']['cpu_usage']['total_usage']
                    system_delta = stats['cpu_stats']['system_cpu_usage'] - \
                                  stats['precpu_stats']['system_cpu_usage']
                    
                    cpu_percent = 0.0
                    if system_delta > 0:
                        cpu_percent = (cpu_delta / system_delta) * \
                                     len(stats['cpu_stats']['cpu_usage']['percpu_usage']) * 100.0
                    
                    # Memory metrics
                    memory_usage = stats['memory_stats']['usage']
                    memory_limit = stats['memory_stats']['limit']
                    memory_percent = (memory_usage / memory_limit) * 100.0
                    
                    # Store container metrics
                    container_metrics = {
                        "timestamp": datetime.now(),
                        "container_name": container.name,
                        "container_id": container.id[:12],
                        "cpu_percent": cpu_percent,
                        "memory_usage_mb": memory_usage / (1024**2),
                        "memory_limit_mb": memory_limit / (1024**2),
                        "memory_percent": memory_percent,
                        "status": container.status
                    }
                    
                    container_metrics_list.append(container_metrics)
                    
                except Exception as e:
                    self.logger.debug(f"Error collecting stats for container {container.name}: {e}")
                    continue
                    
        except Exception as e:
            self.logger.error(f"Error collecting container metrics: {e}")
        
        return container_metrics_list
    
    async def _collect_container_metrics(self) -> None:
        """Collect Docker container metrics (async version).
        
        Runs the blocking Docker API calls in a thread pool to avoid blocking the event loop.
        """
        if not self.docker_available:
            return
        
        try:
            # Run blocking Docker calls in thread pool with timeout
            loop = asyncio.get_event_loop()
            container_metrics_list = await asyncio.wait_for(
                loop.run_in_executor(None, self._collect_container_metrics_sync),
                timeout=15.0  # 15 second timeout
            )
            
            # Store the collected metrics
            for container_metrics in container_metrics_list:
                container_name = container_metrics["container_name"]
                self.container_history[container_name].append(container_metrics)
                
        except asyncio.TimeoutError:
            self.logger.warning("Docker container metrics collection timed out")
        except Exception as e:
            self.logger.debug(f"Error collecting container metrics: {e}")
    
    async def _update_resource_alerts(self) -> None:
        """Update resource alerts based on current metrics."""
        if not self.resource_history:
            return
        
        current_metrics = self.resource_history[-1]
        new_alerts = []
        
        # System CPU alerts
        cpu_percent = current_metrics["cpu_percent"]
        if cpu_percent > self.thresholds["cpu_critical"]:
            new_alerts.append(ResourceAlert(
                alert_id=f"cpu_critical_{int(time.time())}",
                resource_type=ResourceType.CPU,
                severity="critical",
                message=f"System CPU usage critical: {cpu_percent:.1f}%",
                current_value=cpu_percent,
                threshold=self.thresholds["cpu_critical"],
                timestamp=datetime.now()
            ))
        elif cpu_percent > self.thresholds["cpu_warning"]:
            new_alerts.append(ResourceAlert(
                alert_id=f"cpu_warning_{int(time.time())}",
                resource_type=ResourceType.CPU,
                severity="warning",
                message=f"System CPU usage high: {cpu_percent:.1f}%",
                current_value=cpu_percent,
                threshold=self.thresholds["cpu_warning"],
                timestamp=datetime.now()
            ))
        
        # System Memory alerts
        memory_percent = current_metrics["memory_percent"]
        if memory_percent > self.thresholds["memory_critical"]:
            new_alerts.append(ResourceAlert(
                alert_id=f"memory_critical_{int(time.time())}",
                resource_type=ResourceType.MEMORY,
                severity="critical",
                message=f"System memory usage critical: {memory_percent:.1f}%",
                current_value=memory_percent,
                threshold=self.thresholds["memory_critical"],
                timestamp=datetime.now()
            ))
        elif memory_percent > self.thresholds["memory_warning"]:
            new_alerts.append(ResourceAlert(
                alert_id=f"memory_warning_{int(time.time())}",
                resource_type=ResourceType.MEMORY,
                severity="warning",
                message=f"System memory usage high: {memory_percent:.1f}%",
                current_value=memory_percent,
                threshold=self.thresholds["memory_warning"],
                timestamp=datetime.now()
            ))
        
        # System Disk alerts
        disk_percent = current_metrics["disk_percent"]
        if disk_percent > self.thresholds["disk_critical"]:
            new_alerts.append(ResourceAlert(
                alert_id=f"disk_critical_{int(time.time())}",
                resource_type=ResourceType.DISK,
                severity="critical",
                message=f"System disk usage critical: {disk_percent:.1f}%",
                current_value=disk_percent,
                threshold=self.thresholds["disk_critical"],
                timestamp=datetime.now()
            ))
        elif disk_percent > self.thresholds["disk_warning"]:
            new_alerts.append(ResourceAlert(
                alert_id=f"disk_warning_{int(time.time())}",
                resource_type=ResourceType.DISK,
                severity="warning",
                message=f"System disk usage high: {disk_percent:.1f}%",
                current_value=disk_percent,
                threshold=self.thresholds["disk_warning"],
                timestamp=datetime.now()
            ))
        
        # Container alerts
        for container_name, container_metrics in self.container_history.items():
            if not container_metrics:
                continue
            
            latest_container_metrics = container_metrics[-1]
            
            # Container memory alerts
            container_memory_percent = latest_container_metrics["memory_percent"]
            if container_memory_percent > self.thresholds["container_memory_critical"]:
                new_alerts.append(ResourceAlert(
                    alert_id=f"container_memory_critical_{container_name}_{int(time.time())}",
                    resource_type=ResourceType.CONTAINER,
                    severity="critical",
                    message=f"Container {container_name} memory usage critical: {container_memory_percent:.1f}%",
                    current_value=container_memory_percent,
                    threshold=self.thresholds["container_memory_critical"],
                    timestamp=datetime.now(),
                    container_name=container_name
                ))
            elif container_memory_percent > self.thresholds["container_memory_warning"]:
                new_alerts.append(ResourceAlert(
                    alert_id=f"container_memory_warning_{container_name}_{int(time.time())}",
                    resource_type=ResourceType.CONTAINER,
                    severity="warning",
                    message=f"Container {container_name} memory usage high: {container_memory_percent:.1f}%",
                    current_value=container_memory_percent,
                    threshold=self.thresholds["container_memory_warning"],
                    timestamp=datetime.now(),
                    container_name=container_name
                ))
        
        # Update active alerts (keep only recent alerts)
        cutoff_time = datetime.now() - timedelta(hours=1)
        self.active_alerts = [alert for alert in self.active_alerts if alert.timestamp > cutoff_time]
        self.active_alerts.extend(new_alerts)
    
    async def _update_optimization_recommendations(self) -> None:
        """Update resource optimization recommendations."""
        if len(self.resource_history) < 10:  # Need some history for analysis
            return
        
        recommendations = []
        
        # Analyze recent resource usage patterns
        recent_metrics = list(self.resource_history)[-60:]  # Last hour
        
        # CPU optimization recommendations
        cpu_values = [m["cpu_percent"] for m in recent_metrics]
        avg_cpu = statistics.mean(cpu_values)
        max_cpu = max(cpu_values)
        
        if avg_cpu < 20 and max_cpu < 40:
            recommendations.append(ResourceOptimization(
                optimization_id="cpu_underutilized",
                resource_type=ResourceType.CPU,
                priority="low",
                title="CPU Underutilized",
                description=f"Average CPU usage is only {avg_cpu:.1f}%. Consider reducing container CPU limits or running additional services.",
                impact="Low - potential for better resource utilization",
                implementation_effort="Low",
                estimated_savings="5-10% resource efficiency improvement"
            ))
        elif avg_cpu > 70:
            recommendations.append(ResourceOptimization(
                optimization_id="cpu_high_usage",
                resource_type=ResourceType.CPU,
                priority="high",
                title="High CPU Usage",
                description=f"Average CPU usage is {avg_cpu:.1f}%. Consider optimizing application performance or scaling resources.",
                impact="High - performance impact likely",
                implementation_effort="Medium",
                estimated_savings="20-30% performance improvement"
            ))
        
        # Memory optimization recommendations
        memory_values = [m["memory_percent"] for m in recent_metrics]
        avg_memory = statistics.mean(memory_values)
        
        if avg_memory > 80:
            recommendations.append(ResourceOptimization(
                optimization_id="memory_high_usage",
                resource_type=ResourceType.MEMORY,
                priority="high",
                title="High Memory Usage",
                description=f"Average memory usage is {avg_memory:.1f}%. Consider increasing system RAM or optimizing memory usage.",
                impact="High - system stability risk",
                implementation_effort="Medium",
                estimated_savings="Improved system stability"
            ))
        
        # Container optimization recommendations
        for container_name, container_metrics in self.container_history.items():
            if len(container_metrics) < 10:
                continue
            
            recent_container_metrics = list(container_metrics)[-30:]
            memory_values = [m["memory_percent"] for m in recent_container_metrics]
            avg_memory = statistics.mean(memory_values)
            
            if avg_memory < 30:
                recommendations.append(ResourceOptimization(
                    optimization_id=f"container_memory_overprovisioned_{container_name}",
                    resource_type=ResourceType.CONTAINER,
                    priority="medium",
                    title=f"Container {container_name} Over-provisioned",
                    description=f"Container is using only {avg_memory:.1f}% of allocated memory. Consider reducing memory limits.",
                    impact="Medium - resource waste",
                    implementation_effort="Low",
                    estimated_savings="10-20% memory savings"
                ))
            elif avg_memory > 85:
                recommendations.append(ResourceOptimization(
                    optimization_id=f"container_memory_underprovisioned_{container_name}",
                    resource_type=ResourceType.CONTAINER,
                    priority="high",
                    title=f"Container {container_name} Under-provisioned",
                    description=f"Container is using {avg_memory:.1f}% of allocated memory. Consider increasing memory limits.",
                    impact="High - performance impact",
                    implementation_effort="Low",
                    estimated_savings="Improved container performance"
                ))
        
        # Update recommendations
        self.optimization_recommendations = recommendations
    
    async def get_dashboard_data(self, dashboard_id: str, force_refresh: bool = False) -> Optional[Dict[str, Any]]:
        """Get dashboard data with resource-specific chart data."""
        if dashboard_id not in self.dashboards:
            return None
        
        dashboard = self.dashboards[dashboard_id]
        
        # Update chart data
        updated_charts = []
        for chart in dashboard.charts:
            chart_data = await self._get_resource_chart_data(chart, force_refresh)
            updated_charts.append(chart_data)
        
        dashboard_data = dashboard.to_dict()
        dashboard_data["charts"] = updated_charts
        dashboard_data["last_updated"] = datetime.now().isoformat()
        
        return dashboard_data
    
    async def _get_resource_chart_data(self, chart: DashboardChart, force_refresh: bool = False) -> Dict[str, Any]:
        """Get data for resource-specific charts."""
        chart_data = chart.to_dict()
        
        try:
            if chart.chart_id == "system_cpu_usage":
                chart_data["data_points"] = await self._get_system_cpu_data()
            elif chart.chart_id == "system_memory_usage":
                chart_data["data_points"] = await self._get_system_memory_data()
            elif chart.chart_id == "system_disk_usage":
                chart_data["data_points"] = await self._get_system_disk_data()
            elif chart.chart_id == "resource_alerts_summary":
                chart_data["data_points"] = await self._get_resource_alerts_data()
            elif chart.chart_id == "container_memory_breakdown":
                chart_data["data_points"] = await self._get_container_memory_breakdown_data()
            elif chart.chart_id == "container_cpu_breakdown":
                chart_data["data_points"] = await self._get_container_cpu_breakdown_data()
            elif chart.chart_id == "container_resource_efficiency":
                chart_data["data_points"] = await self._get_container_efficiency_data()
            elif chart.chart_id == "total_container_resources":
                chart_data["data_points"] = await self._get_total_container_resources_data()
            elif chart.chart_id == "resource_trends_24h":
                chart_data["data_points"] = await self._get_resource_trends_data()
            elif chart.chart_id == "resource_optimization_opportunities":
                chart_data["data_points"] = await self._get_optimization_opportunities_data()
            elif chart.chart_id == "resource_efficiency_score":
                chart_data["data_points"] = await self._get_efficiency_score_data()
            elif chart.chart_id == "resource_bottlenecks":
                chart_data["data_points"] = await self._get_resource_bottlenecks_data()
            
            chart_data["last_updated"] = datetime.now().isoformat()
            
        except Exception as e:
            self.logger.error(f"Error generating chart data for {chart.chart_id}: {e}")
            chart_data["error"] = str(e)
        
        return chart_data
    
    async def _get_system_cpu_data(self) -> List[Dict[str, Any]]:
        """Get system CPU usage trend data."""
        if not self.resource_history:
            return []
        
        # Get last 30 data points
        recent_data = list(self.resource_history)[-30:]
        
        return [
            {
                "timestamp": metrics["timestamp"].isoformat(),
                "value": metrics["cpu_percent"],
                "label": metrics["timestamp"].strftime("%H:%M")
            }
            for metrics in recent_data
        ]
    
    async def _get_system_memory_data(self) -> List[Dict[str, Any]]:
        """Get system memory usage trend data."""
        if not self.resource_history:
            return []
        
        # Get last 30 data points
        recent_data = list(self.resource_history)[-30:]
        
        return [
            {
                "timestamp": metrics["timestamp"].isoformat(),
                "value": metrics["memory_percent"],
                "label": metrics["timestamp"].strftime("%H:%M")
            }
            for metrics in recent_data
        ]
    
    async def _get_system_disk_data(self) -> List[Dict[str, Any]]:
        """Get system disk usage data."""
        if not self.resource_history:
            return [{"value": 0, "status": "unknown"}]
        
        latest_metrics = self.resource_history[-1]
        disk_percent = latest_metrics["disk_percent"]
        
        if disk_percent < 70:
            status = "healthy"
        elif disk_percent < 80:
            status = "warning"
        else:
            status = "critical"
        
        return [{
            "value": disk_percent,
            "status": status,
            "label": f"{disk_percent:.1f}% used"
        }]
    
    async def _get_resource_alerts_data(self) -> List[Dict[str, Any]]:
        """Get resource alerts data."""
        return [alert.to_dict() for alert in self.active_alerts[-8:]]  # Last 8 alerts
    
    async def _get_container_memory_breakdown_data(self) -> List[Dict[str, Any]]:
        """Get container memory breakdown data."""
        if not self.docker_available:
            return []
        
        container_data = []
        for container_name, metrics_history in self.container_history.items():
            if not metrics_history:
                continue
            
            latest_metrics = metrics_history[-1]
            container_data.append({
                "label": container_name.replace("multimodal-librarian-", "").replace("-1", ""),
                "value": latest_metrics["memory_usage_mb"]
            })
        
        return sorted(container_data, key=lambda x: x["value"], reverse=True)
    
    async def _get_container_cpu_breakdown_data(self) -> List[Dict[str, Any]]:
        """Get container CPU breakdown data."""
        if not self.docker_available:
            return []
        
        container_data = []
        for container_name, metrics_history in self.container_history.items():
            if not metrics_history:
                continue
            
            latest_metrics = metrics_history[-1]
            container_data.append({
                "label": container_name.replace("multimodal-librarian-", "").replace("-1", ""),
                "value": latest_metrics["cpu_percent"]
            })
        
        return sorted(container_data, key=lambda x: x["value"], reverse=True)
    
    async def _get_container_efficiency_data(self) -> List[Dict[str, Any]]:
        """Get container resource efficiency data."""
        if not self.docker_available:
            return []
        
        efficiency_data = []
        for container_name, metrics_history in self.container_history.items():
            if len(metrics_history) < 5:
                continue
            
            recent_metrics = list(metrics_history)[-10:]
            avg_memory_percent = statistics.mean([m["memory_percent"] for m in recent_metrics])
            avg_cpu_percent = statistics.mean([m["cpu_percent"] for m in recent_metrics])
            
            # Calculate efficiency scores
            memory_efficiency = "Optimal" if 40 <= avg_memory_percent <= 80 else \
                              "Under-utilized" if avg_memory_percent < 40 else "Over-utilized"
            cpu_efficiency = "Optimal" if 20 <= avg_cpu_percent <= 70 else \
                           "Under-utilized" if avg_cpu_percent < 20 else "Over-utilized"
            
            status = "Healthy" if memory_efficiency == "Optimal" and cpu_efficiency == "Optimal" else "Needs Attention"
            
            recommendations = []
            if avg_memory_percent < 40:
                recommendations.append("Reduce memory limit")
            elif avg_memory_percent > 80:
                recommendations.append("Increase memory limit")
            if avg_cpu_percent > 70:
                recommendations.append("Optimize CPU usage")
            
            efficiency_data.append({
                "Container": container_name.replace("multimodal-librarian-", "").replace("-1", ""),
                "Memory Efficiency": f"{memory_efficiency} ({avg_memory_percent:.1f}%)",
                "CPU Efficiency": f"{cpu_efficiency} ({avg_cpu_percent:.1f}%)",
                "Status": status,
                "Recommendations": "; ".join(recommendations) if recommendations else "None"
            })
        
        return efficiency_data
    
    async def _get_total_container_resources_data(self) -> List[Dict[str, Any]]:
        """Get total container resources pie chart data."""
        if not self.docker_available:
            return []
        
        container_data = []
        for container_name, metrics_history in self.container_history.items():
            if not metrics_history:
                continue
            
            latest_metrics = metrics_history[-1]
            service_name = container_name.replace("multimodal-librarian-", "").replace("-1", "")
            container_data.append({
                "label": service_name,
                "value": latest_metrics["memory_usage_mb"]
            })
        
        return container_data
    
    async def _get_resource_trends_data(self) -> List[Dict[str, Any]]:
        """Get 24-hour resource trends data."""
        if len(self.resource_history) < 2:
            return []
        
        # Sample data points from the last 24 hours
        data_points = []
        for metrics in self.resource_history:
            data_points.append({
                "timestamp": metrics["timestamp"].isoformat(),
                "cpu": metrics["cpu_percent"],
                "memory": metrics["memory_percent"],
                "disk": metrics["disk_percent"],
                "label": metrics["timestamp"].strftime("%H:%M")
            })
        
        return data_points
    
    async def _get_optimization_opportunities_data(self) -> List[Dict[str, Any]]:
        """Get optimization opportunities table data."""
        return [
            {
                "Resource": opt.resource_type.value.title(),
                "Priority": opt.priority.title(),
                "Impact": opt.impact,
                "Effort": opt.implementation_effort,
                "Savings": opt.estimated_savings or "N/A"
            }
            for opt in self.optimization_recommendations
        ]
    
    async def _get_efficiency_score_data(self) -> List[Dict[str, Any]]:
        """Get resource efficiency score."""
        if not self.resource_history:
            return [{"value": 0, "status": "unknown"}]
        
        # Calculate efficiency score based on resource utilization
        recent_metrics = list(self.resource_history)[-10:]
        
        cpu_values = [m["cpu_percent"] for m in recent_metrics]
        memory_values = [m["memory_percent"] for m in recent_metrics]
        
        avg_cpu = statistics.mean(cpu_values)
        avg_memory = statistics.mean(memory_values)
        
        # Efficiency scoring (optimal usage ranges)
        cpu_score = 100 if 20 <= avg_cpu <= 70 else max(0, 100 - abs(avg_cpu - 45) * 2)
        memory_score = 100 if 40 <= avg_memory <= 80 else max(0, 100 - abs(avg_memory - 60) * 2)
        
        overall_score = (cpu_score + memory_score) / 2
        
        if overall_score >= 85:
            status = "excellent"
        elif overall_score >= 70:
            status = "good"
        elif overall_score >= 40:
            status = "fair"
        else:
            status = "poor"
        
        return [{
            "value": round(overall_score, 1),
            "status": status,
            "label": f"{overall_score:.0f}/100"
        }]
    
    async def _get_resource_bottlenecks_data(self) -> List[Dict[str, Any]]:
        """Get resource bottlenecks heatmap data."""
        if len(self.resource_history) < 24:  # Need at least 24 hours of data
            return []
        
        # Create heatmap data for the last 24 hours
        heatmap_data = []
        resource_types = ["CPU", "Memory", "Disk"]
        
        # Group data by hour
        hourly_data = defaultdict(lambda: defaultdict(list))
        
        for metrics in self.resource_history:
            hour = metrics["timestamp"].hour
            hourly_data[hour]["CPU"].append(metrics["cpu_percent"])
            hourly_data[hour]["Memory"].append(metrics["memory_percent"])
            hourly_data[hour]["Disk"].append(metrics["disk_percent"])
        
        # Calculate average usage for each hour and resource type
        for hour in range(24):
            for i, resource_type in enumerate(resource_types):
                if hour in hourly_data and resource_type in hourly_data[hour]:
                    avg_usage = statistics.mean(hourly_data[hour][resource_type])
                else:
                    avg_usage = 0
                
                heatmap_data.append({
                    "x": hour,
                    "y": i,
                    "value": avg_usage,
                    "hour_label": f"{hour:02d}:00",
                    "resource_label": resource_type
                })
        
        return heatmap_data
    
    def get_available_dashboards(self) -> List[Dict[str, Any]]:
        """Get list of available resource dashboards."""
        return [
            {
                "dashboard_id": dashboard.dashboard_id,
                "name": dashboard.name,
                "description": dashboard.description,
                "chart_count": len(dashboard.charts),
                "auto_refresh": dashboard.auto_refresh,
                "refresh_interval": dashboard.refresh_interval,
                "created_at": dashboard.created_at.isoformat()
            }
            for dashboard in self.dashboards.values()
        ]
    
    def get_service_status(self) -> Dict[str, Any]:
        """Get resource dashboard service status."""
        return {
            "status": "active" if self.monitoring_active else "inactive",
            "service": "resource_usage_dashboard",
            "features": {
                "system_monitoring": True,
                "container_monitoring": self.docker_available,
                "resource_alerts": True,
                "optimization_recommendations": True,
                "trend_analysis": True,
                "efficiency_scoring": True
            },
            "statistics": {
                "total_dashboards": len(self.dashboards),
                "total_charts": sum(len(d.charts) for d in self.dashboards.values()),
                "resource_history_samples": len(self.resource_history),
                "active_alerts": len(self.active_alerts),
                "optimization_recommendations": len(self.optimization_recommendations),
                "monitored_containers": len(self.container_history)
            },
            "monitoring": {
                "active": self.monitoring_active,
                "docker_available": self.docker_available,
                "collection_interval_seconds": self.collection_interval,
                "memory_monitor_active": self.memory_monitor.is_monitoring
            },
            "thresholds": self.thresholds
        }

# Global resource dashboard service instance
_resource_dashboard_service_instance = None

def get_resource_usage_dashboard_service() -> ResourceUsageDashboardService:
    """Get the global resource usage dashboard service instance."""
    global _resource_dashboard_service_instance
    if _resource_dashboard_service_instance is None:
        _resource_dashboard_service_instance = ResourceUsageDashboardService()
    return _resource_dashboard_service_instance

async def start_resource_monitoring() -> None:
    """Start resource usage monitoring."""
    service = get_resource_usage_dashboard_service()
    await service.start_monitoring()

async def stop_resource_monitoring() -> None:
    """Stop resource usage monitoring."""
    service = get_resource_usage_dashboard_service()
    await service.stop_monitoring()