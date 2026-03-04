"""
Local Development Alerting System

This module provides alerting capabilities specifically designed for local development
environments. It extends the existing alerting infrastructure with local-specific
features like file-based alerts, desktop notifications, and development-friendly
alert management.

Features:
- File-based alert logging for local development
- Desktop notifications for critical alerts
- Development-friendly alert formatting
- Integration with existing alerting system
- Local service health alerting
- Resource usage alerts for local development
- Hot reload and development server alerts
"""

import asyncio
import json
import os
import platform
import subprocess
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable, Set
from uuid import uuid4
import threading

from .alerting_service import (
    AlertingService,
    AlertSeverity,
    AlertRule,
    get_alerting_service
)
from .local_error_tracking import (
    LocalErrorTracker,
    LocalErrorCategory,
    get_local_error_tracker
)
from ..config.local_config import LocalDatabaseConfig
from ..logging_config import get_logger

logger = get_logger("local_alerting_system")


class LocalAlertType(Enum):
    """Local development specific alert types."""
    DATABASE_DOWN = "database_down"
    DOCKER_CONTAINER_FAILED = "docker_container_failed"
    HIGH_MEMORY_USAGE = "high_memory_usage"
    HIGH_CPU_USAGE = "high_cpu_usage"
    DISK_SPACE_LOW = "disk_space_low"
    HOT_RELOAD_FAILED = "hot_reload_failed"
    DEVELOPMENT_SERVER_DOWN = "development_server_down"
    DEPENDENCY_MISSING = "dependency_missing"
    CONFIGURATION_ERROR = "configuration_error"
    RESOURCE_LIMIT_EXCEEDED = "resource_limit_exceeded"


@dataclass
class LocalAlert:
    """Local development alert."""
    id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=datetime.now)
    alert_type: LocalAlertType = LocalAlertType.DEVELOPMENT_SERVER_DOWN
    severity: AlertSeverity = AlertSeverity.MEDIUM
    title: str = ""
    message: str = ""
    service: str = "local_development"
    context: Dict[str, Any] = field(default_factory=dict)
    acknowledged: bool = False
    acknowledged_by: str = ""
    acknowledged_at: Optional[datetime] = None
    resolved: bool = False
    resolved_at: Optional[datetime] = None
    resolution_notes: str = ""
    notification_sent: bool = False


@dataclass
class LocalAlertStats:
    """Local development alert statistics."""
    total_alerts: int = 0
    alerts_by_type: Dict[LocalAlertType, int] = field(default_factory=lambda: defaultdict(int))
    alerts_by_severity: Dict[AlertSeverity, int] = field(default_factory=lambda: defaultdict(int))
    alerts_by_service: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    active_alerts: int = 0
    acknowledged_alerts: int = 0
    resolved_alerts: int = 0
    recent_alerts: List[LocalAlert] = field(default_factory=list)


class LocalAlertingSystem:
    """
    Local development alerting system.
    
    This class provides comprehensive alerting specifically designed for local
    development environments, including file-based logging, desktop notifications,
    and integration with existing alerting systems.
    """
    
    def __init__(self, config: Optional[LocalDatabaseConfig] = None):
        self.config = config or LocalDatabaseConfig()
        self.logger = get_logger("local_alerting_system")
        
        # Alert storage
        self._alerts: Dict[str, LocalAlert] = {}
        self._alert_history: deque = deque(maxlen=1000)
        self._active_alerts: Dict[str, LocalAlert] = {}
        
        # Alerting state
        self._alerting_active = False
        self._alerting_task: Optional[asyncio.Task] = None
        self._lock = threading.Lock()
        
        # File-based logging
        self._log_dir = Path(self.config.log_dir) / "alerts"
        try:
            self._log_dir.mkdir(parents=True, exist_ok=True)
        except (OSError, PermissionError) as e:
            # If we can't create the log directory, use a temporary one
            import tempfile
            self._log_dir = Path(tempfile.gettempdir()) / "multimodal_librarian_alerts"
            self._log_dir.mkdir(parents=True, exist_ok=True)
            self.logger.warning(f"Could not create log directory {self.config.log_dir}/alerts, using {self._log_dir}: {e}")
        
        self._alert_log_file = self._log_dir / "local_alerts.jsonl"
        self._daily_alert_file = self._log_dir / f"alerts_{datetime.now().strftime('%Y%m%d')}.jsonl"
        
        # Desktop notification settings
        self._enable_notifications = self._check_notification_support()
        self._notification_cooldown: Dict[str, datetime] = {}
        self._notification_cooldown_period = timedelta(minutes=2)
        
        # Integration with existing systems
        self._alerting_service = get_alerting_service()
        self._error_tracker = get_local_error_tracker()
        
        # Alert rules for local development
        self._alert_rules: Dict[LocalAlertType, Dict[str, Any]] = {
            LocalAlertType.DATABASE_DOWN: {
                "threshold": 3,  # 3 failed connection attempts
                "window": timedelta(minutes=5),
                "severity": AlertSeverity.CRITICAL,
                "auto_resolve": True,
                "cooldown": timedelta(minutes=10)
            },
            LocalAlertType.DOCKER_CONTAINER_FAILED: {
                "threshold": 1,  # Immediate alert
                "window": timedelta(minutes=1),
                "severity": AlertSeverity.HIGH,
                "auto_resolve": True,
                "cooldown": timedelta(minutes=5)
            },
            LocalAlertType.HIGH_MEMORY_USAGE: {
                "threshold": 85,  # 85% memory usage
                "window": timedelta(minutes=5),
                "severity": AlertSeverity.MEDIUM,
                "auto_resolve": True,
                "cooldown": timedelta(minutes=15)
            },
            LocalAlertType.HIGH_CPU_USAGE: {
                "threshold": 90,  # 90% CPU usage
                "window": timedelta(minutes=3),
                "severity": AlertSeverity.MEDIUM,
                "auto_resolve": True,
                "cooldown": timedelta(minutes=10)
            },
            LocalAlertType.DISK_SPACE_LOW: {
                "threshold": 90,  # 90% disk usage
                "window": timedelta(minutes=10),
                "severity": AlertSeverity.MEDIUM,
                "auto_resolve": True,
                "cooldown": timedelta(hours=1)
            },
            LocalAlertType.HOT_RELOAD_FAILED: {
                "threshold": 3,  # 3 failed reloads
                "window": timedelta(minutes=5),
                "severity": AlertSeverity.MEDIUM,
                "auto_resolve": False,
                "cooldown": timedelta(minutes=5)
            }
        }
        
        # Resource monitoring
        self._resource_monitoring_enabled = True
        self._last_resource_check = datetime.now()
        self._resource_check_interval = timedelta(minutes=1)
        
        self.logger.info("Local alerting system initialized")
    
    def _check_notification_support(self) -> bool:
        """Check if desktop notifications are supported on this platform."""
        try:
            system = platform.system().lower()
            
            if system == "darwin":  # macOS
                result = subprocess.run(["which", "osascript"], capture_output=True, text=True)
                return result.returncode == 0
            elif system == "linux":
                result = subprocess.run(["which", "notify-send"], capture_output=True, text=True)
                return result.returncode == 0
            elif system == "windows":
                return True
            
            return False
        except Exception as e:
            self.logger.warning(f"Failed to check notification support: {e}")
            return False
    
    async def start_alerting(self) -> None:
        """Start local alerting system."""
        if self._alerting_active:
            self.logger.warning("Local alerting system is already active")
            return
        
        self._alerting_active = True
        self._alerting_task = asyncio.create_task(self._alerting_loop())
        
        self.logger.info("Local alerting system started")
    
    async def stop_alerting(self) -> None:
        """Stop local alerting system."""
        self._alerting_active = False
        
        if self._alerting_task:
            self._alerting_task.cancel()
            try:
                await self._alerting_task
            except asyncio.CancelledError:
                pass
        
        # Save final alert statistics
        await self._save_alert_statistics()
        
        self.logger.info("Local alerting system stopped")
    
    async def _alerting_loop(self) -> None:
        """Main alerting loop for monitoring and alert management."""
        while self._alerting_active:
            try:
                # Check resource usage
                if self._resource_monitoring_enabled:
                    await self._check_resource_usage()
                
                # Check database connectivity
                await self._check_database_connectivity()
                
                # Check Docker containers
                await self._check_docker_containers()
                
                # Check development server health
                await self._check_development_server()
                
                # Auto-resolve alerts
                await self._auto_resolve_alerts()
                
                # Clean up old alerts
                await self._cleanup_old_alerts()
                
                # Save statistics
                await self._save_alert_statistics()
                
                await asyncio.sleep(60)  # Check every minute
                
            except Exception as e:
                self.logger.error(f"Error in alerting loop: {e}")
                await asyncio.sleep(30)  # Continue alerting despite errors
    
    async def send_alert(
        self,
        alert_type: LocalAlertType,
        title: str,
        message: str,
        severity: AlertSeverity = AlertSeverity.MEDIUM,
        service: str = "local_development",
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Send a local development alert.
        
        Args:
            alert_type: Type of alert
            title: Alert title
            message: Alert message
            severity: Alert severity
            service: Service name
            context: Additional context
            
        Returns:
            Alert ID for tracking
        """
        # Check if we should suppress this alert due to cooldown
        if self._should_suppress_alert(alert_type, service):
            return ""
        
        alert = LocalAlert(
            alert_type=alert_type,
            severity=severity,
            title=title,
            message=message,
            service=service,
            context=context or {}
        )
        
        # Store alert
        with self._lock:
            self._alerts[alert.id] = alert
            self._alert_history.append(alert)
            
            # Add to active alerts if not resolved
            if not alert.resolved:
                self._active_alerts[alert.id] = alert
        
        # Log to file
        await self._log_alert_to_file(alert)
        
        # Send desktop notification
        if severity in [AlertSeverity.CRITICAL, AlertSeverity.HIGH]:
            await self._send_notification(alert)
            alert.notification_sent = True
        
        # Integrate with existing alerting service by recording metrics
        try:
            self._alerting_service.record_metric(
                f"local_alert_{alert_type.value}",
                1.0,  # Count of 1 for this alert
                metadata={
                    "environment": "local",
                    "alert_type": alert_type.value,
                    "service": service,
                    "severity": severity.value,
                    "title": title
                }
            )
        except Exception as e:
            self.logger.warning(f"Failed to record alert metric: {e}")
        
        self.logger.warning(
            f"Local alert sent: {alert_type.value} - {title}",
            extra={
                "alert_id": alert.id,
                "alert_type": alert_type.value,
                "severity": severity.value,
                "service": service
            }
        )
        
        return alert.id
    
    def _should_suppress_alert(self, alert_type: LocalAlertType, service: str) -> bool:
        """Check if alert should be suppressed due to cooldown."""
        if alert_type not in self._alert_rules:
            return False
        
        cooldown = self._alert_rules[alert_type].get("cooldown", timedelta(minutes=5))
        cooldown_key = f"{alert_type.value}_{service}"
        
        # Check if we have a recent alert of the same type
        cutoff_time = datetime.now() - cooldown
        
        with self._lock:
            for alert in reversed(self._alert_history):
                if alert.timestamp < cutoff_time:
                    break
                
                if (alert.alert_type == alert_type and 
                    alert.service == service and 
                    not alert.resolved):
                    return True
        
        return False
    
    async def _log_alert_to_file(self, alert: LocalAlert) -> None:
        """Log alert to file for local development."""
        try:
            alert_data = {
                "id": alert.id,
                "timestamp": alert.timestamp.isoformat(),
                "alert_type": alert.alert_type.value,
                "severity": alert.severity.value,
                "title": alert.title,
                "message": alert.message,
                "service": alert.service,
                "context": alert.context,
                "acknowledged": alert.acknowledged,
                "resolved": alert.resolved,
                "notification_sent": alert.notification_sent
            }
            
            # Write to main alert log
            with open(self._alert_log_file, "a") as f:
                f.write(json.dumps(alert_data) + "\n")
            
            # Write to daily log
            with open(self._daily_alert_file, "a") as f:
                f.write(json.dumps(alert_data) + "\n")
                
        except Exception as e:
            self.logger.warning(f"Failed to log alert to file: {e}")
    
    async def _send_notification(self, alert: LocalAlert) -> None:
        """Send desktop notification for alert."""
        if not self._enable_notifications:
            return
        
        # Check cooldown to avoid spam
        cooldown_key = f"{alert.service}_{alert.alert_type.value}"
        now = datetime.now()
        
        if cooldown_key in self._notification_cooldown:
            if now - self._notification_cooldown[cooldown_key] < self._notification_cooldown_period:
                return
        
        self._notification_cooldown[cooldown_key] = now
        
        try:
            title = f"Local Dev Alert: {alert.title}"
            message = alert.message[:100]
            
            system = platform.system().lower()
            
            if system == "darwin":  # macOS
                script = f'''
                display notification "{message}" with title "{title}" sound name "Glass"
                '''
                subprocess.run(["osascript", "-e", script], check=False)
                
            elif system == "linux":
                urgency = "critical" if alert.severity == AlertSeverity.CRITICAL else "normal"
                subprocess.run([
                    "notify-send", 
                    title, 
                    message,
                    f"--urgency={urgency}",
                    "--expire-time=10000"
                ], check=False)
                
            elif system == "windows":
                script = f'''
                Add-Type -AssemblyName System.Windows.Forms
                $notification = New-Object System.Windows.Forms.NotifyIcon
                $notification.Icon = [System.Drawing.SystemIcons]::Error
                $notification.BalloonTipTitle = "{title}"
                $notification.BalloonTipText = "{message}"
                $notification.Visible = $true
                $notification.ShowBalloonTip(10000)
                '''
                subprocess.run(["powershell", "-Command", script], check=False)
                
        except Exception as e:
            self.logger.warning(f"Failed to send desktop notification: {e}")
    
    async def _check_resource_usage(self) -> None:
        """Check system resource usage and send alerts if thresholds are exceeded."""
        try:
            import psutil
            
            # Check memory usage
            memory = psutil.virtual_memory()
            if memory.percent >= self._alert_rules[LocalAlertType.HIGH_MEMORY_USAGE]["threshold"]:
                await self.send_alert(
                    alert_type=LocalAlertType.HIGH_MEMORY_USAGE,
                    title="High Memory Usage",
                    message=f"Memory usage is at {memory.percent:.1f}% ({memory.used / (1024**3):.1f}GB used)",
                    severity=AlertSeverity.MEDIUM,
                    service="system",
                    context={
                        "memory_percent": memory.percent,
                        "memory_used_gb": memory.used / (1024**3),
                        "memory_total_gb": memory.total / (1024**3)
                    }
                )
            
            # Check CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            if cpu_percent >= self._alert_rules[LocalAlertType.HIGH_CPU_USAGE]["threshold"]:
                await self.send_alert(
                    alert_type=LocalAlertType.HIGH_CPU_USAGE,
                    title="High CPU Usage",
                    message=f"CPU usage is at {cpu_percent:.1f}%",
                    severity=AlertSeverity.MEDIUM,
                    service="system",
                    context={
                        "cpu_percent": cpu_percent,
                        "cpu_count": psutil.cpu_count()
                    }
                )
            
            # Check disk usage
            disk = psutil.disk_usage('/')
            if disk.percent >= self._alert_rules[LocalAlertType.DISK_SPACE_LOW]["threshold"]:
                await self.send_alert(
                    alert_type=LocalAlertType.DISK_SPACE_LOW,
                    title="Low Disk Space",
                    message=f"Disk usage is at {disk.percent:.1f}% ({disk.free / (1024**3):.1f}GB free)",
                    severity=AlertSeverity.MEDIUM,
                    service="system",
                    context={
                        "disk_percent": disk.percent,
                        "disk_free_gb": disk.free / (1024**3),
                        "disk_total_gb": disk.total / (1024**3)
                    }
                )
                
        except ImportError:
            # psutil not available, skip resource monitoring
            if self._resource_monitoring_enabled:
                self.logger.warning("psutil not available, disabling resource monitoring")
                self._resource_monitoring_enabled = False
        except Exception as e:
            self.logger.warning(f"Failed to check resource usage: {e}")
    
    async def _check_database_connectivity(self) -> None:
        """Check database connectivity and send alerts for failures."""
        try:
            # Check recent database errors from error tracker
            db_errors = self._error_tracker.get_errors_by_category(LocalErrorCategory.DATABASE_CONNECTION)
            
            # Count recent errors (last 5 minutes)
            recent_errors = [
                error for error in db_errors
                if datetime.now() - error.timestamp <= timedelta(minutes=5)
            ]
            
            if len(recent_errors) >= self._alert_rules[LocalAlertType.DATABASE_DOWN]["threshold"]:
                # Group by service to send specific alerts
                errors_by_service = defaultdict(list)
                for error in recent_errors:
                    errors_by_service[error.service].append(error)
                
                for service, errors in errors_by_service.items():
                    await self.send_alert(
                        alert_type=LocalAlertType.DATABASE_DOWN,
                        title=f"Database Connection Issues - {service}",
                        message=f"Multiple database connection failures detected: {len(errors)} errors in last 5 minutes",
                        severity=AlertSeverity.CRITICAL,
                        service=service,
                        context={
                            "error_count": len(errors),
                            "recent_errors": [error.message for error in errors[-3:]]
                        }
                    )
                    
        except Exception as e:
            self.logger.warning(f"Failed to check database connectivity: {e}")
    
    async def _check_docker_containers(self) -> None:
        """Check Docker container status and send alerts for failures."""
        try:
            if not self._is_docker_available():
                return
            
            # Check status of local development containers
            containers = ["postgres", "neo4j", "milvus", "redis"]
            
            for container in containers:
                try:
                    result = subprocess.run([
                        "docker", "ps", "--filter", f"name={container}",
                        "--format", "{{.Status}}"
                    ], capture_output=True, text=True, timeout=10)
                    
                    if result.returncode == 0:
                        status = result.stdout.strip()
                        
                        if not status:
                            # Container not found
                            await self.send_alert(
                                alert_type=LocalAlertType.DOCKER_CONTAINER_FAILED,
                                title=f"Docker Container Missing - {container}",
                                message=f"Container {container} is not running or does not exist",
                                severity=AlertSeverity.HIGH,
                                service="docker",
                                context={"container": container, "status": "not_found"}
                            )
                        elif "Exited" in status or "Dead" in status:
                            # Container failed
                            await self.send_alert(
                                alert_type=LocalAlertType.DOCKER_CONTAINER_FAILED,
                                title=f"Docker Container Failed - {container}",
                                message=f"Container {container} has failed: {status}",
                                severity=AlertSeverity.HIGH,
                                service="docker",
                                context={"container": container, "status": status}
                            )
                    
                except subprocess.TimeoutExpired:
                    self.logger.warning(f"Docker status check for {container} timed out")
                except Exception as e:
                    self.logger.warning(f"Failed to check Docker container {container}: {e}")
                    
        except Exception as e:
            self.logger.warning(f"Failed to check Docker containers: {e}")
    
    async def _check_development_server(self) -> None:
        """Check development server health."""
        try:
            # Check if the development server is responding
            import aiohttp
            
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                    async with session.get(f"http://{self.config.api_host}:{self.config.api_port}/health/simple") as response:
                        if response.status != 200:
                            await self.send_alert(
                                alert_type=LocalAlertType.DEVELOPMENT_SERVER_DOWN,
                                title="Development Server Health Check Failed",
                                message=f"Health check returned status {response.status}",
                                severity=AlertSeverity.HIGH,
                                service="development_server",
                                context={"status_code": response.status}
                            )
            except asyncio.TimeoutError:
                await self.send_alert(
                    alert_type=LocalAlertType.DEVELOPMENT_SERVER_DOWN,
                    title="Development Server Timeout",
                    message="Health check request timed out",
                    severity=AlertSeverity.HIGH,
                    service="development_server",
                    context={"error": "timeout"}
                )
            except Exception as e:
                await self.send_alert(
                    alert_type=LocalAlertType.DEVELOPMENT_SERVER_DOWN,
                    title="Development Server Connection Failed",
                    message=f"Failed to connect to development server: {str(e)}",
                    severity=AlertSeverity.HIGH,
                    service="development_server",
                    context={"error": str(e)}
                )
                
        except ImportError:
            # aiohttp not available, skip server health check
            pass
        except Exception as e:
            self.logger.warning(f"Failed to check development server: {e}")
    
    def _is_docker_available(self) -> bool:
        """Check if Docker is available."""
        try:
            result = subprocess.run(
                ["docker", "--version"], 
                capture_output=True, 
                text=True, 
                timeout=5
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
    
    async def _auto_resolve_alerts(self) -> None:
        """Auto-resolve alerts that have auto-resolve enabled."""
        try:
            current_time = datetime.now()
            alerts_to_resolve = []
            
            with self._lock:
                for alert_id, alert in self._active_alerts.items():
                    alert_rule = self._alert_rules.get(alert.alert_type)
                    if alert_rule and alert_rule.get("auto_resolve", False):
                        # Check if conditions for auto-resolve are met
                        if await self._check_auto_resolve_conditions(alert):
                            alerts_to_resolve.append(alert_id)
            
            # Resolve alerts outside of lock
            for alert_id in alerts_to_resolve:
                await self.resolve_alert(alert_id, "Auto-resolved: conditions no longer met")
                
        except Exception as e:
            self.logger.warning(f"Failed to auto-resolve alerts: {e}")
    
    async def _check_auto_resolve_conditions(self, alert: LocalAlert) -> bool:
        """Check if conditions for auto-resolving an alert are met."""
        try:
            if alert.alert_type == LocalAlertType.DATABASE_DOWN:
                # Check if database is now accessible
                # This would integrate with actual database health checks
                return False  # Placeholder
            
            elif alert.alert_type == LocalAlertType.DOCKER_CONTAINER_FAILED:
                # Check if container is now running
                if "container" in alert.context:
                    container = alert.context["container"]
                    result = subprocess.run([
                        "docker", "ps", "--filter", f"name={container}",
                        "--format", "{{.Status}}"
                    ], capture_output=True, text=True, timeout=5)
                    
                    if result.returncode == 0 and result.stdout.strip():
                        status = result.stdout.strip()
                        return "Up" in status
            
            elif alert.alert_type in [LocalAlertType.HIGH_MEMORY_USAGE, LocalAlertType.HIGH_CPU_USAGE]:
                # Check if resource usage is back to normal
                try:
                    import psutil
                    
                    if alert.alert_type == LocalAlertType.HIGH_MEMORY_USAGE:
                        memory = psutil.virtual_memory()
                        threshold = self._alert_rules[LocalAlertType.HIGH_MEMORY_USAGE]["threshold"]
                        return memory.percent < threshold - 10  # 10% buffer
                    
                    elif alert.alert_type == LocalAlertType.HIGH_CPU_USAGE:
                        cpu_percent = psutil.cpu_percent(interval=1)
                        threshold = self._alert_rules[LocalAlertType.HIGH_CPU_USAGE]["threshold"]
                        return cpu_percent < threshold - 10  # 10% buffer
                        
                except ImportError:
                    pass
            
            return False
            
        except Exception as e:
            self.logger.warning(f"Failed to check auto-resolve conditions for alert {alert.id}: {e}")
            return False
    
    async def _cleanup_old_alerts(self) -> None:
        """Clean up old alert records to prevent memory issues."""
        try:
            cutoff_time = datetime.now() - timedelta(hours=24)
            
            # Clean up main alert storage
            old_alert_ids = [
                alert_id for alert_id, alert in self._alerts.items()
                if alert.timestamp < cutoff_time and alert.resolved
            ]
            
            for alert_id in old_alert_ids:
                del self._alerts[alert_id]
                if alert_id in self._active_alerts:
                    del self._active_alerts[alert_id]
            
            if old_alert_ids:
                self.logger.debug(f"Cleaned up {len(old_alert_ids)} old alert records")
                
        except Exception as e:
            self.logger.warning(f"Failed to cleanup old alerts: {e}")
    
    async def _save_alert_statistics(self) -> None:
        """Save alert statistics to file."""
        try:
            stats = self.get_alert_statistics()
            
            stats_file = self._log_dir / "alert_statistics.json"
            stats_data = {
                "timestamp": datetime.now().isoformat(),
                "total_alerts": stats.total_alerts,
                "alerts_by_type": {
                    alert_type.value: count 
                    for alert_type, count in stats.alerts_by_type.items()
                },
                "alerts_by_severity": {
                    severity.value: count 
                    for severity, count in stats.alerts_by_severity.items()
                },
                "alerts_by_service": dict(stats.alerts_by_service),
                "active_alerts": stats.active_alerts,
                "acknowledged_alerts": stats.acknowledged_alerts,
                "resolved_alerts": stats.resolved_alerts
            }
            
            with open(stats_file, "w") as f:
                json.dump(stats_data, f, indent=2)
                
        except Exception as e:
            self.logger.warning(f"Failed to save alert statistics: {e}")
    
    def get_alert_statistics(self) -> LocalAlertStats:
        """Get current alert statistics."""
        stats = LocalAlertStats()
        
        with self._lock:
            stats.total_alerts = len(self._alert_history)
            stats.active_alerts = len(self._active_alerts)
            
            # Count by type, severity, and service
            for alert in self._alert_history:
                stats.alerts_by_type[alert.alert_type] += 1
                stats.alerts_by_severity[alert.severity] += 1
                stats.alerts_by_service[alert.service] += 1
                
                if alert.acknowledged:
                    stats.acknowledged_alerts += 1
                
                if alert.resolved:
                    stats.resolved_alerts += 1
            
            # Recent alerts (last 10)
            stats.recent_alerts = list(self._alert_history)[-10:]
        
        return stats
    
    def get_active_alerts(self) -> List[LocalAlert]:
        """Get all active (unresolved) alerts."""
        with self._lock:
            return list(self._active_alerts.values())
    
    def get_alerts_by_type(self, alert_type: LocalAlertType) -> List[LocalAlert]:
        """Get alerts by type."""
        with self._lock:
            return [alert for alert in self._alert_history if alert.alert_type == alert_type]
    
    def get_alerts_by_service(self, service: str) -> List[LocalAlert]:
        """Get alerts by service."""
        with self._lock:
            return [alert for alert in self._alert_history if alert.service == service]
    
    async def acknowledge_alert(self, alert_id: str, acknowledged_by: str = "developer") -> bool:
        """Acknowledge an alert."""
        with self._lock:
            if alert_id in self._alerts:
                alert = self._alerts[alert_id]
                alert.acknowledged = True
                alert.acknowledged_by = acknowledged_by
                alert.acknowledged_at = datetime.now()
                
                self.logger.info(f"Alert {alert_id} acknowledged by {acknowledged_by}")
                return True
        
        return False
    
    async def resolve_alert(self, alert_id: str, resolution_notes: str = "") -> bool:
        """Resolve an alert."""
        with self._lock:
            if alert_id in self._alerts:
                alert = self._alerts[alert_id]
                alert.resolved = True
                alert.resolved_at = datetime.now()
                alert.resolution_notes = resolution_notes
                
                # Remove from active alerts
                if alert_id in self._active_alerts:
                    del self._active_alerts[alert_id]
                
                self.logger.info(f"Alert {alert_id} resolved: {resolution_notes}")
                return True
        
        return False
    
    def get_alert_details(self, alert_id: str) -> Optional[LocalAlert]:
        """Get detailed information about a specific alert."""
        with self._lock:
            return self._alerts.get(alert_id)


# Global instance
_local_alerting_system: Optional[LocalAlertingSystem] = None


def get_local_alerting_system(config: Optional[LocalDatabaseConfig] = None) -> LocalAlertingSystem:
    """Get the global local alerting system instance."""
    global _local_alerting_system
    if _local_alerting_system is None:
        _local_alerting_system = LocalAlertingSystem(config)
    return _local_alerting_system


async def start_local_alerting(config: Optional[LocalDatabaseConfig] = None) -> None:
    """Start local alerting system."""
    alerting_system = get_local_alerting_system(config)
    await alerting_system.start_alerting()


async def stop_local_alerting() -> None:
    """Stop local alerting system."""
    if _local_alerting_system:
        await _local_alerting_system.stop_alerting()


async def send_local_alert(
    alert_type: LocalAlertType,
    title: str,
    message: str,
    severity: AlertSeverity = AlertSeverity.MEDIUM,
    service: str = "local_development",
    context: Optional[Dict[str, Any]] = None
) -> str:
    """
    Convenience function to send a local development alert.
    
    Args:
        alert_type: Type of alert
        title: Alert title
        message: Alert message
        severity: Alert severity
        service: Service name
        context: Additional context
        
    Returns:
        Alert ID for tracking
    """
    alerting_system = get_local_alerting_system()
    return await alerting_system.send_alert(
        alert_type=alert_type,
        title=title,
        message=message,
        severity=severity,
        service=service,
        context=context
    )