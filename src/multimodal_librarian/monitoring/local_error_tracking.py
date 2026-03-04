"""
Local Development Error Tracking System

This module provides error tracking and alerting specifically designed for local development
environments. It integrates with the existing error monitoring infrastructure while providing
local-specific features like file-based logging, desktop notifications, and development-friendly
error reporting.

Features:
- File-based error logging for local development
- Desktop notifications for critical errors
- Development-friendly error reporting with stack traces
- Integration with existing error monitoring system
- Local database error tracking
- Docker container error monitoring
- Hot reload error detection
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
import traceback

from .error_monitoring_system import (
    ErrorMonitoringSystem,
    ErrorMetrics,
    ErrorRateThreshold,
    get_error_monitoring_system
)
from .error_logging_service import (
    ErrorLoggingService,
    ErrorSeverity,
    ErrorCategory,
    get_error_logging_service
)
from .alerting_service import (
    AlertingService,
    AlertSeverity,
    get_alerting_service
)
from ..config.local_config import LocalDatabaseConfig
from ..logging_config import get_logger

logger = get_logger("local_error_tracking")


class LocalErrorCategory(Enum):
    """Local development specific error categories."""
    DATABASE_CONNECTION = "database_connection"
    DOCKER_CONTAINER = "docker_container"
    HOT_RELOAD = "hot_reload"
    FILE_SYSTEM = "file_system"
    DEVELOPMENT_SERVER = "development_server"
    DEPENDENCY_IMPORT = "dependency_import"
    CONFIGURATION = "configuration"
    RESOURCE_LIMIT = "resource_limit"


@dataclass
class LocalErrorEvent:
    """Local development error event."""
    id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=datetime.now)
    category: LocalErrorCategory = LocalErrorCategory.DEVELOPMENT_SERVER
    severity: ErrorSeverity = ErrorSeverity.MEDIUM
    service: str = "local_development"
    operation: str = "unknown"
    message: str = ""
    exception_type: str = ""
    stack_trace: str = ""
    context: Dict[str, Any] = field(default_factory=dict)
    resolved: bool = False
    resolution_time: Optional[datetime] = None
    resolution_notes: str = ""


@dataclass
class LocalErrorStats:
    """Local development error statistics."""
    total_errors: int = 0
    errors_by_category: Dict[LocalErrorCategory, int] = field(default_factory=lambda: defaultdict(int))
    errors_by_service: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    errors_by_hour: Dict[int, int] = field(default_factory=lambda: defaultdict(int))
    recent_errors: List[LocalErrorEvent] = field(default_factory=list)
    error_rate_per_minute: float = 0.0
    critical_error_count: int = 0
    unresolved_error_count: int = 0


class LocalErrorTracker:
    """
    Local development error tracking system.
    
    This class provides comprehensive error tracking specifically designed for local
    development environments, including file-based logging, desktop notifications,
    and integration with existing monitoring systems.
    """
    
    def __init__(self, config: Optional[LocalDatabaseConfig] = None):
        self.config = config or LocalDatabaseConfig()
        self.logger = get_logger("local_error_tracker")
        
        # Error storage
        self._errors: Dict[str, LocalErrorEvent] = {}
        self._error_history: deque = deque(maxlen=1000)
        self._error_counts_by_minute: deque = deque(maxlen=60)  # Last 60 minutes
        
        # Tracking state
        self._tracking_active = False
        self._tracking_task: Optional[asyncio.Task] = None
        self._lock = threading.Lock()
        
        # File-based logging
        self._log_dir = Path(self.config.log_dir) / "errors"
        try:
            self._log_dir.mkdir(parents=True, exist_ok=True)
        except (OSError, PermissionError) as e:
            # If we can't create the log directory, use a temporary one
            import tempfile
            self._log_dir = Path(tempfile.gettempdir()) / "multimodal_librarian_errors"
            self._log_dir.mkdir(parents=True, exist_ok=True)
            self.logger.warning(f"Could not create log directory {self.config.log_dir}/errors, using {self._log_dir}: {e}")
        
        self._error_log_file = self._log_dir / "local_errors.jsonl"
        self._daily_log_file = self._log_dir / f"errors_{datetime.now().strftime('%Y%m%d')}.jsonl"
        
        # Desktop notification settings
        self._enable_notifications = self._check_notification_support()
        self._notification_cooldown: Dict[str, datetime] = {}
        self._notification_cooldown_period = timedelta(minutes=5)
        
        # Integration with existing systems
        self._error_monitoring_system = get_error_monitoring_system()
        self._error_logging_service = get_error_logging_service()
        self._alerting_service = get_alerting_service()
        
        # Error pattern detection
        self._error_patterns: Dict[str, List[datetime]] = defaultdict(list)
        self._pattern_threshold = 3  # Number of similar errors to trigger pattern alert
        self._pattern_window = timedelta(minutes=10)
        
        # Service-specific error tracking
        self._service_errors: Dict[str, List[LocalErrorEvent]] = defaultdict(list)
        self._database_errors: List[LocalErrorEvent] = []
        self._docker_errors: List[LocalErrorEvent] = []
        self._hot_reload_errors: List[LocalErrorEvent] = []
        
        self.logger.info("Local error tracker initialized")
    
    def _check_notification_support(self) -> bool:
        """Check if desktop notifications are supported on this platform."""
        try:
            system = platform.system().lower()
            
            if system == "darwin":  # macOS
                # Check if osascript is available
                result = subprocess.run(["which", "osascript"], capture_output=True, text=True)
                return result.returncode == 0
            elif system == "linux":
                # Check if notify-send is available
                result = subprocess.run(["which", "notify-send"], capture_output=True, text=True)
                return result.returncode == 0
            elif system == "windows":
                # Windows has built-in notification support
                return True
            
            return False
        except Exception as e:
            self.logger.warning(f"Failed to check notification support: {e}")
            return False
    
    async def start_tracking(self) -> None:
        """Start local error tracking."""
        if self._tracking_active:
            self.logger.warning("Local error tracking is already active")
            return
        
        self._tracking_active = True
        self._tracking_task = asyncio.create_task(self._tracking_loop())
        
        # Initialize error count tracking
        self._error_counts_by_minute.clear()
        for _ in range(60):
            self._error_counts_by_minute.append(0)
        
        self.logger.info("Local error tracking started")
    
    async def stop_tracking(self) -> None:
        """Stop local error tracking."""
        self._tracking_active = False
        
        if self._tracking_task:
            self._tracking_task.cancel()
            try:
                await self._tracking_task
            except asyncio.CancelledError:
                pass
        
        # Save final error statistics
        await self._save_error_statistics()
        
        self.logger.info("Local error tracking stopped")
    
    async def _tracking_loop(self) -> None:
        """Main tracking loop for error monitoring."""
        while self._tracking_active:
            try:
                # Update error rate statistics
                await self._update_error_statistics()
                
                # Check for error patterns
                await self._check_error_patterns()
                
                # Clean up old errors
                await self._cleanup_old_errors()
                
                # Check database connectivity errors
                await self._check_database_errors()
                
                # Check Docker container errors
                await self._check_docker_errors()
                
                # Save statistics periodically
                await self._save_error_statistics()
                
                await asyncio.sleep(60)  # Check every minute
                
            except Exception as e:
                self.logger.error(f"Error in tracking loop: {e}")
                await asyncio.sleep(30)  # Continue tracking despite errors
    
    def track_error(
        self,
        category: LocalErrorCategory,
        severity: ErrorSeverity,
        service: str,
        operation: str,
        message: str,
        exception: Optional[Exception] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Track a local development error.
        
        Args:
            category: Error category
            severity: Error severity
            service: Service name where error occurred
            operation: Operation that failed
            message: Error message
            exception: Exception object (optional)
            context: Additional context (optional)
            
        Returns:
            Error ID for tracking
        """
        error_event = LocalErrorEvent(
            category=category,
            severity=severity,
            service=service,
            operation=operation,
            message=message,
            context=context or {}
        )
        
        # Add exception details if provided
        if exception:
            error_event.exception_type = type(exception).__name__
            error_event.stack_trace = traceback.format_exc()
            error_event.context.update({
                "exception_args": str(exception.args),
                "exception_str": str(exception)
            })
        
        # Store error
        with self._lock:
            self._errors[error_event.id] = error_event
            self._error_history.append(error_event)
            self._service_errors[service].append(error_event)
            
            # Category-specific storage
            if category == LocalErrorCategory.DATABASE_CONNECTION:
                self._database_errors.append(error_event)
            elif category == LocalErrorCategory.DOCKER_CONTAINER:
                self._docker_errors.append(error_event)
            elif category == LocalErrorCategory.HOT_RELOAD:
                self._hot_reload_errors.append(error_event)
        
        # Log to file
        try:
            asyncio.create_task(self._log_error_to_file(error_event))
        except RuntimeError:
            # No event loop running, skip async logging in tests
            pass
        
        # Send desktop notification for critical errors
        if severity in [ErrorSeverity.CRITICAL, ErrorSeverity.HIGH]:
            try:
                asyncio.create_task(self._send_notification(error_event))
            except RuntimeError:
                # No event loop running, skip async notification in tests
                pass
        
        # Integrate with existing error monitoring
        try:
            self._error_monitoring_system.record_operation(
                service=service,
                operation=operation,
                success=False,
                error_category=ErrorCategory.SERVICE_FAILURE,  # Map to existing category
                error_severity=severity
            )
        except Exception as e:
            # Don't fail error tracking if monitoring integration fails
            self.logger.warning(f"Failed to record operation in error monitoring system: {e}")
        
        # Log with existing error logging service
        try:
            self._error_logging_service.log_error(
                exception,
                service=service,
                operation=operation,
                additional_context=context or {}
            )
        except Exception as e:
            # Don't fail error tracking if logging integration fails
            self.logger.warning(f"Failed to log error in error logging service: {e}")
        
        self.logger.error(
            f"Local error tracked: {category.value} in {service}.{operation} - {message}",
            extra={
                "error_id": error_event.id,
                "category": category.value,
                "severity": severity.value,
                "service": service,
                "operation": operation
            }
        )
        
        return error_event.id
    
    async def _log_error_to_file(self, error_event: LocalErrorEvent) -> None:
        """Log error to file for local development."""
        try:
            error_data = {
                "id": error_event.id,
                "timestamp": error_event.timestamp.isoformat(),
                "category": error_event.category.value,
                "severity": error_event.severity.value,
                "service": error_event.service,
                "operation": error_event.operation,
                "message": error_event.message,
                "exception_type": error_event.exception_type,
                "stack_trace": error_event.stack_trace,
                "context": error_event.context,
                "resolved": error_event.resolved
            }
            
            # Write to main error log
            with open(self._error_log_file, "a") as f:
                f.write(json.dumps(error_data) + "\n")
            
            # Write to daily log
            with open(self._daily_log_file, "a") as f:
                f.write(json.dumps(error_data) + "\n")
                
        except Exception as e:
            self.logger.warning(f"Failed to log error to file: {e}")
    
    async def _send_notification(self, error_event: LocalErrorEvent) -> None:
        """Send desktop notification for error."""
        if not self._enable_notifications:
            return
        
        # Check cooldown to avoid spam
        cooldown_key = f"{error_event.service}_{error_event.category.value}"
        now = datetime.now()
        
        if cooldown_key in self._notification_cooldown:
            if now - self._notification_cooldown[cooldown_key] < self._notification_cooldown_period:
                return
        
        self._notification_cooldown[cooldown_key] = now
        
        try:
            title = f"Local Dev Error: {error_event.service}"
            message = f"{error_event.category.value}: {error_event.message[:100]}"
            
            system = platform.system().lower()
            
            if system == "darwin":  # macOS
                script = f'''
                display notification "{message}" with title "{title}"
                '''
                subprocess.run(["osascript", "-e", script], check=False)
                
            elif system == "linux":
                subprocess.run([
                    "notify-send", 
                    title, 
                    message,
                    "--urgency=normal",
                    "--expire-time=5000"
                ], check=False)
                
            elif system == "windows":
                # Use PowerShell for Windows notifications
                script = f'''
                Add-Type -AssemblyName System.Windows.Forms
                $notification = New-Object System.Windows.Forms.NotifyIcon
                $notification.Icon = [System.Drawing.SystemIcons]::Warning
                $notification.BalloonTipTitle = "{title}"
                $notification.BalloonTipText = "{message}"
                $notification.Visible = $true
                $notification.ShowBalloonTip(5000)
                '''
                subprocess.run(["powershell", "-Command", script], check=False)
                
        except Exception as e:
            self.logger.warning(f"Failed to send desktop notification: {e}")
    
    async def _update_error_statistics(self) -> None:
        """Update error rate statistics."""
        try:
            current_minute = datetime.now().minute
            
            # Count errors in the last minute
            one_minute_ago = datetime.now() - timedelta(minutes=1)
            recent_errors = [
                error for error in self._error_history
                if error.timestamp >= one_minute_ago
            ]
            
            # Update error count for current minute
            if len(self._error_counts_by_minute) >= 60:
                self._error_counts_by_minute.popleft()
            self._error_counts_by_minute.append(len(recent_errors))
            
        except Exception as e:
            self.logger.warning(f"Failed to update error statistics: {e}")
    
    async def _check_error_patterns(self) -> None:
        """Check for error patterns that might indicate systemic issues."""
        try:
            now = datetime.now()
            
            # Group errors by pattern (service + operation + exception_type)
            pattern_groups: Dict[str, List[LocalErrorEvent]] = defaultdict(list)
            
            for error in self._error_history:
                if now - error.timestamp <= self._pattern_window:
                    pattern_key = f"{error.service}_{error.operation}_{error.exception_type}"
                    pattern_groups[pattern_key].append(error)
            
            # Check for patterns that exceed threshold
            for pattern_key, errors in pattern_groups.items():
                if len(errors) >= self._pattern_threshold:
                    # Check if we've already alerted for this pattern recently
                    if pattern_key not in self._error_patterns:
                        self._error_patterns[pattern_key] = []
                    
                    # Clean old pattern alerts
                    self._error_patterns[pattern_key] = [
                        alert_time for alert_time in self._error_patterns[pattern_key]
                        if now - alert_time <= timedelta(hours=1)
                    ]
                    
                    # Send alert if we haven't alerted recently
                    if not self._error_patterns[pattern_key]:
                        await self._send_pattern_alert(pattern_key, errors)
                        self._error_patterns[pattern_key].append(now)
                        
        except Exception as e:
            self.logger.warning(f"Failed to check error patterns: {e}")
    
    async def _send_pattern_alert(self, pattern_key: str, errors: List[LocalErrorEvent]) -> None:
        """Send alert for detected error pattern."""
        try:
            service, operation, exception_type = pattern_key.split("_", 2)
            
            alert_message = (
                f"Error pattern detected in local development: "
                f"{len(errors)} similar errors in {service}.{operation} "
                f"({exception_type}) within {self._pattern_window.total_seconds()/60:.0f} minutes"
            )
            
            # Send to alerting service by recording metrics instead of direct alert
            try:
                self._alerting_service.record_metric(
                    "local_error_pattern_detected",
                    len(errors),
                    metadata={
                        "pattern": pattern_key,
                        "service": service,
                        "operation": operation,
                        "error_count": len(errors)
                    }
                )
            except Exception as e:
                self.logger.warning(f"Failed to record pattern alert metric: {e}")
            
            self.logger.warning(alert_message)
            
        except Exception as e:
            self.logger.warning(f"Failed to send pattern alert: {e}")
    
    async def _cleanup_old_errors(self) -> None:
        """Clean up old error records to prevent memory issues."""
        try:
            cutoff_time = datetime.now() - timedelta(hours=24)
            
            # Clean up main error storage
            old_error_ids = [
                error_id for error_id, error in self._errors.items()
                if error.timestamp < cutoff_time
            ]
            
            for error_id in old_error_ids:
                del self._errors[error_id]
            
            # Clean up service-specific errors
            for service, errors in self._service_errors.items():
                self._service_errors[service] = [
                    error for error in errors
                    if error.timestamp >= cutoff_time
                ]
            
            # Clean up category-specific errors
            self._database_errors = [
                error for error in self._database_errors
                if error.timestamp >= cutoff_time
            ]
            
            self._docker_errors = [
                error for error in self._docker_errors
                if error.timestamp >= cutoff_time
            ]
            
            self._hot_reload_errors = [
                error for error in self._hot_reload_errors
                if error.timestamp >= cutoff_time
            ]
            
            if old_error_ids:
                self.logger.debug(f"Cleaned up {len(old_error_ids)} old error records")
                
        except Exception as e:
            self.logger.warning(f"Failed to cleanup old errors: {e}")
    
    async def _check_database_errors(self) -> None:
        """Check for database connectivity errors."""
        try:
            # This would integrate with database health checks
            # For now, we'll check if there are recent database errors
            recent_db_errors = [
                error for error in self._database_errors
                if datetime.now() - error.timestamp <= timedelta(minutes=5)
            ]
            
            if len(recent_db_errors) >= 3:
                # Record metric for alerting service instead of direct alert
                try:
                    self._alerting_service.record_metric(
                        "local_database_connection_errors",
                        len(recent_db_errors),
                        metadata={
                            "environment": "local",
                            "category": "database",
                            "type": "connectivity",
                            "error_count": len(recent_db_errors)
                        }
                    )
                except Exception as e:
                    self.logger.warning(f"Failed to record database error metric: {e}")
                
        except Exception as e:
            self.logger.warning(f"Failed to check database errors: {e}")
    
    async def _check_docker_errors(self) -> None:
        """Check for Docker container errors."""
        try:
            # Check Docker container status if Docker is available
            if self._is_docker_available():
                # Get container status for local development services
                containers = ["postgres", "neo4j", "milvus", "redis"]
                
                for container in containers:
                    try:
                        result = subprocess.run([
                            "docker", "ps", "--filter", f"name={container}",
                            "--format", "{{.Status}}"
                        ], capture_output=True, text=True, timeout=10)
                        
                        if result.returncode == 0 and result.stdout.strip():
                            status = result.stdout.strip()
                            if "Exited" in status or "Dead" in status:
                                self.track_error(
                                    category=LocalErrorCategory.DOCKER_CONTAINER,
                                    severity=ErrorSeverity.HIGH,
                                    service="docker",
                                    operation="container_status_check",
                                    message=f"Container {container} is not running: {status}",
                                    context={"container": container, "status": status}
                                )
                        
                    except subprocess.TimeoutExpired:
                        self.logger.warning(f"Docker status check for {container} timed out")
                    except Exception as e:
                        self.logger.warning(f"Failed to check Docker container {container}: {e}")
                        
        except Exception as e:
            self.logger.warning(f"Failed to check Docker errors: {e}")
    
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
    
    async def _save_error_statistics(self) -> None:
        """Save error statistics to file."""
        try:
            stats = self.get_error_statistics()
            
            stats_file = self._log_dir / "error_statistics.json"
            stats_data = {
                "timestamp": datetime.now().isoformat(),
                "total_errors": stats.total_errors,
                "errors_by_category": {
                    category.value: count 
                    for category, count in stats.errors_by_category.items()
                },
                "errors_by_service": dict(stats.errors_by_service),
                "error_rate_per_minute": stats.error_rate_per_minute,
                "critical_error_count": stats.critical_error_count,
                "unresolved_error_count": stats.unresolved_error_count
            }
            
            with open(stats_file, "w") as f:
                json.dump(stats_data, f, indent=2)
                
        except Exception as e:
            self.logger.warning(f"Failed to save error statistics: {e}")
    
    def get_error_statistics(self) -> LocalErrorStats:
        """Get current error statistics."""
        stats = LocalErrorStats()
        
        with self._lock:
            stats.total_errors = len(self._error_history)
            
            # Count by category
            for error in self._error_history:
                stats.errors_by_category[error.category] += 1
                stats.errors_by_service[error.service] += 1
                
                if error.severity == ErrorSeverity.CRITICAL:
                    stats.critical_error_count += 1
                
                if not error.resolved:
                    stats.unresolved_error_count += 1
            
            # Count by hour
            for error in self._error_history:
                hour = error.timestamp.hour
                stats.errors_by_hour[hour] += 1
            
            # Recent errors (last 10)
            stats.recent_errors = list(self._error_history)[-10:]
            
            # Error rate per minute
            if self._error_counts_by_minute:
                stats.error_rate_per_minute = sum(self._error_counts_by_minute) / len(self._error_counts_by_minute)
        
        return stats
    
    def get_errors_by_category(self, category: LocalErrorCategory) -> List[LocalErrorEvent]:
        """Get errors by category."""
        with self._lock:
            return [error for error in self._error_history if error.category == category]
    
    def get_errors_by_service(self, service: str) -> List[LocalErrorEvent]:
        """Get errors by service."""
        with self._lock:
            return self._service_errors.get(service, [])
    
    def resolve_error(self, error_id: str, resolution_notes: str = "") -> bool:
        """Mark an error as resolved."""
        with self._lock:
            if error_id in self._errors:
                error = self._errors[error_id]
                error.resolved = True
                error.resolution_time = datetime.now()
                error.resolution_notes = resolution_notes
                
                self.logger.info(f"Error {error_id} marked as resolved: {resolution_notes}")
                return True
        
        return False
    
    def get_error_details(self, error_id: str) -> Optional[LocalErrorEvent]:
        """Get detailed information about a specific error."""
        with self._lock:
            return self._errors.get(error_id)


# Global instance
_local_error_tracker: Optional[LocalErrorTracker] = None


def get_local_error_tracker(config: Optional[LocalDatabaseConfig] = None) -> LocalErrorTracker:
    """Get the global local error tracker instance."""
    global _local_error_tracker
    if _local_error_tracker is None:
        _local_error_tracker = LocalErrorTracker(config)
    return _local_error_tracker


async def start_local_error_tracking(config: Optional[LocalDatabaseConfig] = None) -> None:
    """Start local error tracking."""
    tracker = get_local_error_tracker(config)
    await tracker.start_tracking()


async def stop_local_error_tracking() -> None:
    """Stop local error tracking."""
    if _local_error_tracker:
        await _local_error_tracker.stop_tracking()


def track_local_error(
    category: LocalErrorCategory,
    severity: ErrorSeverity,
    service: str,
    operation: str,
    message: str,
    exception: Optional[Exception] = None,
    context: Optional[Dict[str, Any]] = None
) -> str:
    """
    Convenience function to track a local development error.
    
    Args:
        category: Error category
        severity: Error severity
        service: Service name
        operation: Operation that failed
        message: Error message
        exception: Exception object (optional)
        context: Additional context (optional)
        
    Returns:
        Error ID for tracking
    """
    tracker = get_local_error_tracker()
    return tracker.track_error(
        category=category,
        severity=severity,
        service=service,
        operation=operation,
        message=message,
        exception=exception,
        context=context
    )