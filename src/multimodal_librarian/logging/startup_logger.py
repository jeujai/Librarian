"""
Startup Logging System for Multimodal Librarian Application

This module implements comprehensive logging for startup phase transitions,
model loading progress, and resource initialization to support debugging
and monitoring of the application startup process.

Key Features:
- Detailed startup phase transition logging
- Model loading progress and timing logs
- Structured logging for debugging
- Integration with startup phase manager
- CloudWatch-compatible log formatting
"""

import logging
import json
import time
import os
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from enum import Enum
import traceback
import threading
import uuid

from ..startup.phase_manager import StartupPhase, StartupPhaseManager, PhaseTransition, ModelLoadingStatus


class LogLevel(Enum):
    """Log levels for startup logging."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass
class StartupLogEntry:
    """Structured log entry for startup events."""
    timestamp: str
    level: str
    event_type: str
    phase: str
    message: str
    duration_ms: Optional[float] = None
    metadata: Dict[str, Any] = None
    error_details: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
    
    def to_json(self) -> str:
        """Convert to JSON string for structured logging."""
        return json.dumps(self.to_dict(), default=str)


class StartupLogger:
    """
    Comprehensive startup logging system that tracks phase transitions,
    model loading, and resource initialization with structured output.
    """
    
    def __init__(self, phase_manager: Optional[StartupPhaseManager] = None):
        """Initialize the startup logger."""
        self.logger = logging.getLogger("startup")
        self.phase_manager = phase_manager
        self.startup_time = datetime.now()
        self.log_entries: List[StartupLogEntry] = []
        
        # Configure structured logging format
        self._configure_logging()
        
        # Track phase transition timing
        self.phase_start_times: Dict[str, datetime] = {}
        self.last_logged_phase = None
        
        # Model loading tracking
        self.model_load_start_times: Dict[str, datetime] = {}
        
        # Resource initialization tracking
        self.resource_init_times: Dict[str, datetime] = {}
        
        # Debug context tracking
        self.debug_contexts: Dict[str, Dict[str, Any]] = {}
        self.correlation_ids: Dict[str, str] = {}
        self.debug_enabled = os.getenv('DEBUG', 'false').lower() == 'true'
        
        # Thread-local storage for correlation IDs
        self._local = threading.local()
        
        self.logger.info("StartupLogger initialized", extra={
            "event_type": "startup_logger_init",
            "startup_time": self.startup_time.isoformat(),
            "phase_manager_available": phase_manager is not None,
            "debug_enabled": self.debug_enabled
        })
    
    def _send_to_aggregator(self, log_entry: StartupLogEntry) -> None:
        """Send log entry to aggregator if available."""
        try:
            # Import here to avoid circular imports
            from .log_aggregator import get_log_aggregator, add_log_entry
            
            aggregator = get_log_aggregator()
            if aggregator:
                add_log_entry(log_entry)
        except ImportError:
            # Log aggregator not available, skip
            pass
        except Exception as e:
            # Don't let aggregator errors break logging
            self.logger.debug(f"Failed to send log to aggregator: {str(e)}")
    
    def _configure_logging(self) -> None:
        """Configure structured logging format for startup events."""
        # Create custom formatter for structured logging
        class StructuredFormatter(logging.Formatter):
            def format(self, record):
                # Base log data
                log_data = {
                    "timestamp": datetime.fromtimestamp(record.created).isoformat(),
                    "level": record.levelname,
                    "logger": record.name,
                    "message": record.getMessage(),
                    "module": record.module,
                    "function": record.funcName,
                    "line": record.lineno,
                    "thread_id": record.thread,
                    "process_id": record.process
                }
                
                # Add extra fields if present
                if hasattr(record, 'event_type'):
                    log_data["event_type"] = record.event_type
                if hasattr(record, 'phase'):
                    log_data["phase"] = record.phase
                if hasattr(record, 'duration_ms'):
                    log_data["duration_ms"] = record.duration_ms
                if hasattr(record, 'metadata'):
                    log_data["metadata"] = record.metadata
                if hasattr(record, 'error_details'):
                    log_data["error_details"] = record.error_details
                if hasattr(record, 'debug_context'):
                    log_data["debug_context"] = record.debug_context
                if hasattr(record, 'stack_trace'):
                    log_data["stack_trace"] = record.stack_trace
                if hasattr(record, 'correlation_id'):
                    log_data["correlation_id"] = record.correlation_id
                
                return json.dumps(log_data, default=str)
        
        # Apply formatter to startup logger
        handler = logging.StreamHandler()
        handler.setFormatter(StructuredFormatter())
        self.logger.addHandler(handler)
        
        # Set log level based on environment or debug flag
        debug_enabled = os.getenv('DEBUG', 'false').lower() == 'true'
        self.logger.setLevel(logging.DEBUG if debug_enabled else logging.INFO)
        self.logger.propagate = False  # Prevent duplicate logs
    
    def log_phase_transition_start(self, from_phase: Optional[StartupPhase], to_phase: StartupPhase) -> None:
        """Log the start of a phase transition with detailed context."""
        current_time = datetime.now()
        self.phase_start_times[to_phase.value] = current_time
        
        # Calculate time since startup
        startup_duration = (current_time - self.startup_time).total_seconds() * 1000
        
        # Calculate time since last phase (if applicable)
        last_phase_duration = None
        if from_phase and from_phase.value in self.phase_start_times:
            last_phase_start = self.phase_start_times[from_phase.value]
            last_phase_duration = (current_time - last_phase_start).total_seconds() * 1000
        
        metadata = {
            "from_phase": from_phase.value if from_phase else None,
            "to_phase": to_phase.value,
            "startup_duration_ms": startup_duration,
            "last_phase_duration_ms": last_phase_duration,
            "transition_timestamp": current_time.isoformat()
        }
        
        # Add phase manager status if available
        if self.phase_manager:
            try:
                status = self.phase_manager.get_current_status()
                metadata.update({
                    "health_check_ready": status.health_check_ready,
                    "user_requests_ready": status.user_requests_ready,
                    "capabilities_count": len(status.capabilities),
                    "loaded_models_count": sum(1 for m in status.model_statuses.values() if m.status == "loaded"),
                    "total_models_count": len(status.model_statuses)
                })
            except Exception as e:
                metadata["phase_manager_error"] = str(e)
        
        log_entry = StartupLogEntry(
            timestamp=current_time.isoformat(),
            level=LogLevel.INFO.value,
            event_type="phase_transition_start",
            phase=to_phase.value,
            message=f"Starting transition from {from_phase.value if from_phase else 'initial'} to {to_phase.value}",
            metadata=metadata
        )
        
        self.log_entries.append(log_entry)
        
        # Send to log aggregator if available
        self._send_to_aggregator(log_entry)
        
        self.logger.info(
            f"🔄 PHASE TRANSITION START: {from_phase.value if from_phase else 'initial'} → {to_phase.value}",
            extra={
                "event_type": "phase_transition_start",
                "phase": to_phase.value,
                "metadata": metadata
            }
        )
    
    def log_phase_transition_complete(self, transition: PhaseTransition) -> None:
        """Log the completion of a phase transition with timing and success details."""
        current_time = datetime.now()
        
        # Calculate transition duration
        duration_ms = None
        if transition.duration_seconds:
            duration_ms = transition.duration_seconds * 1000
        
        metadata = {
            "from_phase": transition.from_phase.value if transition.from_phase else None,
            "to_phase": transition.to_phase.value,
            "success": transition.success,
            "duration_ms": duration_ms,
            "retry_count": transition.retry_count,
            "dependencies_met": transition.dependencies_met,
            "prerequisites": transition.prerequisites,
            "started_at": transition.started_at.isoformat(),
            "completed_at": transition.completed_at.isoformat() if transition.completed_at else None
        }
        
        # Add error details if transition failed
        error_details = None
        if not transition.success and transition.error_message:
            error_details = {
                "error_message": transition.error_message,
                "retry_count": transition.retry_count,
                "timeout_seconds": transition.timeout_seconds
            }
        
        log_level = LogLevel.INFO if transition.success else LogLevel.ERROR
        status_emoji = "✅" if transition.success else "❌"
        
        log_entry = StartupLogEntry(
            timestamp=current_time.isoformat(),
            level=log_level.value,
            event_type="phase_transition_complete",
            phase=transition.to_phase.value,
            message=f"Phase transition to {transition.to_phase.value} {'completed successfully' if transition.success else 'failed'}",
            duration_ms=duration_ms,
            metadata=metadata,
            error_details=error_details
        )
        
        self.log_entries.append(log_entry)
        
        # Send to log aggregator if available
        self._send_to_aggregator(log_entry)
        
        self.logger.log(
            logging.INFO if transition.success else logging.ERROR,
            f"{status_emoji} PHASE TRANSITION COMPLETE: {transition.to_phase.value} "
            f"({'SUCCESS' if transition.success else 'FAILED'}) "
            f"in {duration_ms:.1f}ms" if duration_ms else "",
            extra={
                "event_type": "phase_transition_complete",
                "phase": transition.to_phase.value,
                "duration_ms": duration_ms,
                "metadata": metadata,
                "error_details": error_details
            }
        )
        
        # Log ready state messages for key phases
        if transition.success:
            if transition.to_phase == StartupPhase.MINIMAL:
                self.logger.info(
                    "🚀 APPLICATION MINIMAL READY: Health checks available, basic API ready",
                    extra={
                        "event_type": "application_ready",
                        "phase": "minimal",
                        "ready_type": "health_checks"
                    }
                )
            elif transition.to_phase == StartupPhase.ESSENTIAL:
                self.logger.info(
                    "⚡ APPLICATION ESSENTIAL READY: Core models loaded, basic functionality available",
                    extra={
                        "event_type": "application_ready",
                        "phase": "essential",
                        "ready_type": "basic_functionality"
                    }
                )
            elif transition.to_phase == StartupPhase.FULL:
                self.logger.info(
                    "🧠 APPLICATION FULLY READY: All models loaded, complete functionality available",
                    extra={
                        "event_type": "application_ready",
                        "phase": "full",
                        "ready_type": "complete_functionality"
                    }
                )
    
    def log_model_loading_start(self, model_name: str, model_status: ModelLoadingStatus) -> None:
        """Log the start of model loading with detailed information."""
        current_time = datetime.now()
        self.model_load_start_times[model_name] = current_time
        
        startup_duration = (current_time - self.startup_time).total_seconds() * 1000
        
        metadata = {
            "model_name": model_name,
            "priority": model_status.priority,
            "size_mb": model_status.size_mb,
            "estimated_load_time_seconds": model_status.estimated_load_time_seconds,
            "startup_duration_ms": startup_duration,
            "loading_start_time": current_time.isoformat()
        }
        
        log_entry = StartupLogEntry(
            timestamp=current_time.isoformat(),
            level=LogLevel.INFO.value,
            event_type="model_loading_start",
            phase=self.phase_manager.current_phase.value if self.phase_manager else "unknown",
            message=f"Starting to load {model_status.priority} priority model: {model_name}",
            metadata=metadata
        )
        
        self.log_entries.append(log_entry)
        
        # Send to log aggregator if available
        self._send_to_aggregator(log_entry)
        
        self.logger.info(
            f"📦 MODEL LOADING START: {model_name} ({model_status.priority} priority, "
            f"{model_status.size_mb}MB, ~{model_status.estimated_load_time_seconds}s)",
            extra={
                "event_type": "model_loading_start",
                "phase": self.phase_manager.current_phase.value if self.phase_manager else "unknown",
                "metadata": metadata
            }
        )
    
    def log_model_loading_complete(self, model_name: str, model_status: ModelLoadingStatus) -> None:
        """Log the completion of model loading with timing and success details."""
        current_time = datetime.now()
        
        # Calculate loading duration
        duration_ms = None
        if model_status.duration_seconds:
            duration_ms = model_status.duration_seconds * 1000
        
        # Calculate efficiency ratio
        efficiency_ratio = None
        if (model_status.estimated_load_time_seconds and 
            model_status.duration_seconds and 
            model_status.duration_seconds > 0):
            efficiency_ratio = model_status.estimated_load_time_seconds / model_status.duration_seconds
        
        metadata = {
            "model_name": model_name,
            "priority": model_status.priority,
            "status": model_status.status,
            "size_mb": model_status.size_mb,
            "estimated_load_time_seconds": model_status.estimated_load_time_seconds,
            "actual_load_time_seconds": model_status.duration_seconds,
            "efficiency_ratio": efficiency_ratio,
            "started_at": model_status.started_at.isoformat() if model_status.started_at else None,
            "completed_at": model_status.completed_at.isoformat() if model_status.completed_at else None
        }
        
        # Add error details if loading failed
        error_details = None
        if model_status.status == "failed" and model_status.error_message:
            error_details = {
                "error_message": model_status.error_message,
                "model_name": model_name,
                "priority": model_status.priority
            }
        
        log_level = LogLevel.INFO if model_status.status == "loaded" else LogLevel.ERROR
        status_emoji = "✅" if model_status.status == "loaded" else "❌"
        
        log_entry = StartupLogEntry(
            timestamp=current_time.isoformat(),
            level=log_level.value,
            event_type="model_loading_complete",
            phase=self.phase_manager.current_phase.value if self.phase_manager else "unknown",
            message=f"Model {model_name} loading {'completed successfully' if model_status.status == 'loaded' else 'failed'}",
            duration_ms=duration_ms,
            metadata=metadata,
            error_details=error_details
        )
        
        self.log_entries.append(log_entry)
        
        # Send to log aggregator if available
        self._send_to_aggregator(log_entry)
        
        efficiency_text = f" (efficiency: {efficiency_ratio:.2f}x)" if efficiency_ratio else ""
        
        self.logger.log(
            logging.INFO if model_status.status == "loaded" else logging.ERROR,
            f"{status_emoji} MODEL LOADING COMPLETE: {model_name} "
            f"({'SUCCESS' if model_status.status == 'loaded' else 'FAILED'}) "
            f"in {duration_ms:.1f}ms{efficiency_text}" if duration_ms else "",
            extra={
                "event_type": "model_loading_complete",
                "phase": self.phase_manager.current_phase.value if self.phase_manager else "unknown",
                "duration_ms": duration_ms,
                "metadata": metadata,
                "error_details": error_details
            }
        )
    
    def log_resource_initialization_start(self, resource_name: str, resource_type: str, 
                                        config_details: Optional[Dict[str, Any]] = None) -> None:
        """Log the start of resource initialization."""
        current_time = datetime.now()
        self.resource_init_times[resource_name] = current_time
        
        startup_duration = (current_time - self.startup_time).total_seconds() * 1000
        
        metadata = {
            "resource_name": resource_name,
            "resource_type": resource_type,
            "startup_duration_ms": startup_duration,
            "init_start_time": current_time.isoformat()
        }
        
        if config_details:
            metadata["config_details"] = config_details
        
        log_entry = StartupLogEntry(
            timestamp=current_time.isoformat(),
            level=LogLevel.INFO.value,
            event_type="resource_init_start",
            phase=self.phase_manager.current_phase.value if self.phase_manager else "unknown",
            message=f"Starting initialization of {resource_type}: {resource_name}",
            metadata=metadata
        )
        
        self.log_entries.append(log_entry)
        
        # Send to log aggregator if available
        self._send_to_aggregator(log_entry)
        
        self.logger.info(
            f"🔧 RESOURCE INIT START: {resource_name} ({resource_type})",
            extra={
                "event_type": "resource_init_start",
                "phase": self.phase_manager.current_phase.value if self.phase_manager else "unknown",
                "metadata": metadata
            }
        )
    
    def log_resource_initialization_complete(self, resource_name: str, resource_type: str,
                                           success: bool, error_message: Optional[str] = None,
                                           connection_details: Optional[Dict[str, Any]] = None) -> None:
        """Log the completion of resource initialization."""
        current_time = datetime.now()
        
        # Calculate initialization duration
        duration_ms = None
        if resource_name in self.resource_init_times:
            start_time = self.resource_init_times[resource_name]
            duration_ms = (current_time - start_time).total_seconds() * 1000
        
        metadata = {
            "resource_name": resource_name,
            "resource_type": resource_type,
            "success": success,
            "duration_ms": duration_ms,
            "completed_at": current_time.isoformat()
        }
        
        if connection_details:
            metadata["connection_details"] = connection_details
        
        # Add error details if initialization failed
        error_details = None
        if not success and error_message:
            error_details = {
                "error_message": error_message,
                "resource_name": resource_name,
                "resource_type": resource_type
            }
        
        log_level = LogLevel.INFO if success else LogLevel.ERROR
        status_emoji = "✅" if success else "❌"
        
        log_entry = StartupLogEntry(
            timestamp=current_time.isoformat(),
            level=log_level.value,
            event_type="resource_init_complete",
            phase=self.phase_manager.current_phase.value if self.phase_manager else "unknown",
            message=f"Resource {resource_name} initialization {'completed successfully' if success else 'failed'}",
            duration_ms=duration_ms,
            metadata=metadata,
            error_details=error_details
        )
        
        self.log_entries.append(log_entry)
        
        # Send to log aggregator if available
        self._send_to_aggregator(log_entry)
        
        self.logger.log(
            logging.INFO if success else logging.ERROR,
            f"{status_emoji} RESOURCE INIT COMPLETE: {resource_name} "
            f"({'SUCCESS' if success else 'FAILED'}) "
            f"in {duration_ms:.1f}ms" if duration_ms else "",
            extra={
                "event_type": "resource_init_complete",
                "phase": self.phase_manager.current_phase.value if self.phase_manager else "unknown",
                "duration_ms": duration_ms,
                "metadata": metadata,
                "error_details": error_details
            }
        )
    
    def log_application_ready(self, ready_type: str, capabilities: List[str]) -> None:
        """Log when the application reaches a ready state."""
        current_time = datetime.now()
        startup_duration = (current_time - self.startup_time).total_seconds() * 1000
        
        metadata = {
            "ready_type": ready_type,
            "capabilities": capabilities,
            "startup_duration_ms": startup_duration,
            "ready_timestamp": current_time.isoformat()
        }
        
        log_entry = StartupLogEntry(
            timestamp=current_time.isoformat(),
            level=LogLevel.INFO.value,
            event_type="application_ready",
            phase=self.phase_manager.current_phase.value if self.phase_manager else "unknown",
            message=f"Application ready to serve traffic ({ready_type})",
            duration_ms=startup_duration,
            metadata=metadata
        )
        
        self.log_entries.append(log_entry)
        
        # Send to log aggregator if available
        self._send_to_aggregator(log_entry)
        
        self.logger.info(
            f"🎉 APPLICATION READY TO SERVE TRAFFIC: {ready_type} "
            f"(startup completed in {startup_duration:.1f}ms)",
            extra={
                "event_type": "application_ready",
                "phase": self.phase_manager.current_phase.value if self.phase_manager else "unknown",
                "duration_ms": startup_duration,
                "metadata": metadata
            }
        )
    
    def log_startup_error(self, error_type: str, error_message: str, 
                         context: Optional[Dict[str, Any]] = None,
                         exception: Optional[Exception] = None) -> None:
        """Log startup errors with detailed context and stack traces."""
        current_time = datetime.now()
        startup_duration = (current_time - self.startup_time).total_seconds() * 1000
        
        metadata = {
            "error_type": error_type,
            "startup_duration_ms": startup_duration,
            "error_timestamp": current_time.isoformat()
        }
        
        if context:
            metadata["context"] = context
        
        error_details = {
            "error_message": error_message,
            "error_type": error_type
        }
        
        if exception:
            import traceback
            error_details.update({
                "exception_type": type(exception).__name__,
                "exception_message": str(exception),
                "stack_trace": traceback.format_exc()
            })
        
        log_entry = StartupLogEntry(
            timestamp=current_time.isoformat(),
            level=LogLevel.ERROR.value,
            event_type="startup_error",
            phase=self.phase_manager.current_phase.value if self.phase_manager else "unknown",
            message=f"Startup error occurred: {error_type}",
            metadata=metadata,
            error_details=error_details
        )
        
        self.log_entries.append(log_entry)
        
        # Send to log aggregator if available
        self._send_to_aggregator(log_entry)
        
        self.logger.error(
            f"💥 STARTUP ERROR: {error_type} - {error_message}",
            extra={
                "event_type": "startup_error",
                "phase": self.phase_manager.current_phase.value if self.phase_manager else "unknown",
                "metadata": metadata,
                "error_details": error_details
            }
        )
    
    def log_progress_update(self, progress_data: Dict[str, Any]) -> None:
        """Log periodic progress updates during startup."""
        current_time = datetime.now()
        startup_duration = (current_time - self.startup_time).total_seconds() * 1000
        
        metadata = {
            "startup_duration_ms": startup_duration,
            "progress_timestamp": current_time.isoformat(),
            **progress_data
        }
        
        log_entry = StartupLogEntry(
            timestamp=current_time.isoformat(),
            level=LogLevel.DEBUG.value,
            event_type="progress_update",
            phase=self.phase_manager.current_phase.value if self.phase_manager else "unknown",
            message="Startup progress update",
            metadata=metadata
        )
        
        self.log_entries.append(log_entry)
        
        # Send to log aggregator if available
        self._send_to_aggregator(log_entry)
        
        # Only log progress updates at DEBUG level to avoid spam
        self.logger.debug(
            f"📊 PROGRESS UPDATE: {progress_data.get('overall_progress_percent', 0):.1f}% complete",
            extra={
                "event_type": "progress_update",
                "phase": self.phase_manager.current_phase.value if self.phase_manager else "unknown",
                "metadata": metadata
            }
        )
    
    def set_correlation_id(self, correlation_id: Optional[str] = None) -> str:
        """Set correlation ID for tracking related log entries."""
        if correlation_id is None:
            correlation_id = str(uuid.uuid4())
        
        self._local.correlation_id = correlation_id
        self.correlation_ids[threading.current_thread().ident] = correlation_id
        
        if self.debug_enabled:
            self.logger.debug(
                f"🔗 CORRELATION ID SET: {correlation_id}",
                extra={
                    "event_type": "correlation_id_set",
                    "correlation_id": correlation_id,
                    "thread_id": threading.current_thread().ident
                }
            )
        
        return correlation_id
    
    def get_correlation_id(self) -> Optional[str]:
        """Get current correlation ID for this thread."""
        return getattr(self._local, 'correlation_id', None)
    
    def log_debug_checkpoint(self, checkpoint_name: str, context: Dict[str, Any], 
                           stack_trace: bool = False) -> None:
        """Log a debug checkpoint with detailed context information."""
        if not self.debug_enabled:
            return
        
        current_time = datetime.now()
        startup_duration = (current_time - self.startup_time).total_seconds() * 1000
        correlation_id = self.get_correlation_id()
        
        debug_context = {
            "checkpoint_name": checkpoint_name,
            "startup_duration_ms": startup_duration,
            "thread_id": threading.current_thread().ident,
            "thread_name": threading.current_thread().name,
            "correlation_id": correlation_id,
            "context": context
        }
        
        # Add stack trace if requested
        stack_info = None
        if stack_trace:
            stack_info = traceback.format_stack()
            debug_context["stack_trace"] = stack_info
        
        log_entry = StartupLogEntry(
            timestamp=current_time.isoformat(),
            level=LogLevel.DEBUG.value,
            event_type="debug_checkpoint",
            phase=self.phase_manager.current_phase.value if self.phase_manager else "unknown",
            message=f"Debug checkpoint: {checkpoint_name}",
            metadata=debug_context
        )
        
        self.log_entries.append(log_entry)
        
        # Send to log aggregator if available
        self._send_to_aggregator(log_entry)
        
        self.logger.debug(
            f"🔍 DEBUG CHECKPOINT: {checkpoint_name}",
            extra={
                "event_type": "debug_checkpoint",
                "phase": self.phase_manager.current_phase.value if self.phase_manager else "unknown",
                "debug_context": debug_context,
                "correlation_id": correlation_id,
                "stack_trace": stack_info
            }
        )
    
    def log_debug_variable_state(self, variable_name: str, variable_value: Any, 
                                context: Optional[Dict[str, Any]] = None) -> None:
        """Log the state of a variable for debugging purposes."""
        if not self.debug_enabled:
            return
        
        current_time = datetime.now()
        correlation_id = self.get_correlation_id()
        
        # Safely serialize the variable value
        try:
            if isinstance(variable_value, (dict, list, tuple, str, int, float, bool, type(None))):
                serialized_value = variable_value
            else:
                serialized_value = str(variable_value)
        except Exception:
            serialized_value = f"<unserializable {type(variable_value).__name__}>"
        
        debug_context = {
            "variable_name": variable_name,
            "variable_value": serialized_value,
            "variable_type": type(variable_value).__name__,
            "thread_id": threading.current_thread().ident,
            "correlation_id": correlation_id
        }
        
        if context:
            debug_context["additional_context"] = context
        
        log_entry = StartupLogEntry(
            timestamp=current_time.isoformat(),
            level=LogLevel.DEBUG.value,
            event_type="debug_variable_state",
            phase=self.phase_manager.current_phase.value if self.phase_manager else "unknown",
            message=f"Variable state: {variable_name} = {serialized_value}",
            metadata=debug_context
        )
        
        self.log_entries.append(log_entry)
        
        # Send to log aggregator if available
        self._send_to_aggregator(log_entry)
        
        self.logger.debug(
            f"🔬 VARIABLE STATE: {variable_name} = {serialized_value}",
            extra={
                "event_type": "debug_variable_state",
                "phase": self.phase_manager.current_phase.value if self.phase_manager else "unknown",
                "debug_context": debug_context,
                "correlation_id": correlation_id
            }
        )
    
    def log_debug_function_entry(self, function_name: str, args: Optional[Dict[str, Any]] = None,
                                kwargs: Optional[Dict[str, Any]] = None) -> str:
        """Log function entry for debugging with correlation ID."""
        if not self.debug_enabled:
            return self.get_correlation_id() or ""
        
        current_time = datetime.now()
        correlation_id = self.get_correlation_id() or self.set_correlation_id()
        
        debug_context = {
            "function_name": function_name,
            "entry_time": current_time.isoformat(),
            "thread_id": threading.current_thread().ident,
            "correlation_id": correlation_id
        }
        
        if args:
            debug_context["args"] = args
        if kwargs:
            debug_context["kwargs"] = kwargs
        
        log_entry = StartupLogEntry(
            timestamp=current_time.isoformat(),
            level=LogLevel.DEBUG.value,
            event_type="debug_function_entry",
            phase=self.phase_manager.current_phase.value if self.phase_manager else "unknown",
            message=f"Function entry: {function_name}",
            metadata=debug_context
        )
        
        self.log_entries.append(log_entry)
        
        # Send to log aggregator if available
        self._send_to_aggregator(log_entry)
        
        self.logger.debug(
            f"🚪 FUNCTION ENTRY: {function_name}",
            extra={
                "event_type": "debug_function_entry",
                "phase": self.phase_manager.current_phase.value if self.phase_manager else "unknown",
                "debug_context": debug_context,
                "correlation_id": correlation_id
            }
        )
        
        return correlation_id
    
    def log_debug_function_exit(self, function_name: str, duration_ms: Optional[float] = None,
                               return_value: Any = None, success: bool = True,
                               error: Optional[Exception] = None) -> None:
        """Log function exit for debugging."""
        if not self.debug_enabled:
            return
        
        current_time = datetime.now()
        correlation_id = self.get_correlation_id()
        
        debug_context = {
            "function_name": function_name,
            "exit_time": current_time.isoformat(),
            "success": success,
            "thread_id": threading.current_thread().ident,
            "correlation_id": correlation_id
        }
        
        if duration_ms is not None:
            debug_context["duration_ms"] = duration_ms
        
        if return_value is not None:
            try:
                if isinstance(return_value, (dict, list, tuple, str, int, float, bool, type(None))):
                    debug_context["return_value"] = return_value
                else:
                    debug_context["return_value"] = str(return_value)
            except Exception:
                debug_context["return_value"] = f"<unserializable {type(return_value).__name__}>"
        
        error_details = None
        if error:
            error_details = {
                "error_type": type(error).__name__,
                "error_message": str(error),
                "stack_trace": traceback.format_exc()
            }
            debug_context["error"] = error_details
        
        log_entry = StartupLogEntry(
            timestamp=current_time.isoformat(),
            level=LogLevel.DEBUG.value,
            event_type="debug_function_exit",
            phase=self.phase_manager.current_phase.value if self.phase_manager else "unknown",
            message=f"Function exit: {function_name} ({'SUCCESS' if success else 'ERROR'})",
            metadata=debug_context,
            error_details=error_details,
            duration_ms=duration_ms
        )
        
        self.log_entries.append(log_entry)
        
        # Send to log aggregator if available
        self._send_to_aggregator(log_entry)
        
        status_emoji = "✅" if success else "❌"
        duration_text = f" ({duration_ms:.1f}ms)" if duration_ms else ""
        
        self.logger.debug(
            f"🚪 FUNCTION EXIT: {function_name} {status_emoji}{duration_text}",
            extra={
                "event_type": "debug_function_exit",
                "phase": self.phase_manager.current_phase.value if self.phase_manager else "unknown",
                "debug_context": debug_context,
                "correlation_id": correlation_id,
                "duration_ms": duration_ms,
                "error_details": error_details
            }
        )
    
    def log_debug_performance_metric(self, metric_name: str, value: float, unit: str,
                                   context: Optional[Dict[str, Any]] = None) -> None:
        """Log performance metrics for debugging."""
        if not self.debug_enabled:
            return
        
        current_time = datetime.now()
        correlation_id = self.get_correlation_id()
        
        debug_context = {
            "metric_name": metric_name,
            "metric_value": value,
            "metric_unit": unit,
            "timestamp": current_time.isoformat(),
            "correlation_id": correlation_id
        }
        
        if context:
            debug_context["context"] = context
        
        log_entry = StartupLogEntry(
            timestamp=current_time.isoformat(),
            level=LogLevel.DEBUG.value,
            event_type="debug_performance_metric",
            phase=self.phase_manager.current_phase.value if self.phase_manager else "unknown",
            message=f"Performance metric: {metric_name} = {value} {unit}",
            metadata=debug_context
        )
        
        self.log_entries.append(log_entry)
        
        # Send to log aggregator if available
        self._send_to_aggregator(log_entry)
        
        self.logger.debug(
            f"📊 PERFORMANCE METRIC: {metric_name} = {value} {unit}",
            extra={
                "event_type": "debug_performance_metric",
                "phase": self.phase_manager.current_phase.value if self.phase_manager else "unknown",
                "debug_context": debug_context,
                "correlation_id": correlation_id
            }
        )
    
    def log_debug_memory_usage(self, context: str, additional_info: Optional[Dict[str, Any]] = None) -> None:
        """Log current memory usage for debugging."""
        if not self.debug_enabled:
            return
        
        try:
            import psutil
            process = psutil.Process()
            memory_info = process.memory_info()
            
            current_time = datetime.now()
            correlation_id = self.get_correlation_id()
            
            debug_context = {
                "context": context,
                "memory_rss_mb": memory_info.rss / 1024 / 1024,
                "memory_vms_mb": memory_info.vms / 1024 / 1024,
                "memory_percent": process.memory_percent(),
                "timestamp": current_time.isoformat(),
                "correlation_id": correlation_id
            }
            
            if additional_info:
                debug_context["additional_info"] = additional_info
            
            log_entry = StartupLogEntry(
                timestamp=current_time.isoformat(),
                level=LogLevel.DEBUG.value,
                event_type="debug_memory_usage",
                phase=self.phase_manager.current_phase.value if self.phase_manager else "unknown",
                message=f"Memory usage at {context}: {memory_info.rss / 1024 / 1024:.1f}MB RSS",
                metadata=debug_context
            )
            
            self.log_entries.append(log_entry)
            
            # Send to log aggregator if available
            self._send_to_aggregator(log_entry)
            
            self.logger.debug(
                f"🧠 MEMORY USAGE: {context} - RSS: {memory_info.rss / 1024 / 1024:.1f}MB, "
                f"VMS: {memory_info.vms / 1024 / 1024:.1f}MB ({process.memory_percent():.1f}%)",
                extra={
                    "event_type": "debug_memory_usage",
                    "phase": self.phase_manager.current_phase.value if self.phase_manager else "unknown",
                    "debug_context": debug_context,
                    "correlation_id": correlation_id
                }
            )
            
        except ImportError:
            self.logger.debug(
                f"🧠 MEMORY USAGE: {context} - psutil not available for memory monitoring",
                extra={
                    "event_type": "debug_memory_usage",
                    "phase": self.phase_manager.current_phase.value if self.phase_manager else "unknown",
                    "correlation_id": self.get_correlation_id()
                }
            )
        except Exception as e:
            self.logger.debug(
                f"🧠 MEMORY USAGE: {context} - Error getting memory info: {str(e)}",
                extra={
                    "event_type": "debug_memory_usage",
                    "phase": self.phase_manager.current_phase.value if self.phase_manager else "unknown",
                    "correlation_id": self.get_correlation_id(),
                    "error": str(e)
                }
            )
    
    def create_debug_context_manager(self, function_name: str, args: Optional[Dict[str, Any]] = None,
                                   kwargs: Optional[Dict[str, Any]] = None):
        """Create a context manager for debugging function execution."""
        return DebugContextManager(self, function_name, args, kwargs)
    
    def get_startup_summary(self) -> Dict[str, Any]:
        """Get a comprehensive summary of the startup process."""
        current_time = datetime.now()
        total_startup_time = (current_time - self.startup_time).total_seconds() * 1000
        
        # Analyze log entries
        phase_transitions = [entry for entry in self.log_entries if entry.event_type == "phase_transition_complete"]
        model_loads = [entry for entry in self.log_entries if entry.event_type == "model_loading_complete"]
        resource_inits = [entry for entry in self.log_entries if entry.event_type == "resource_init_complete"]
        errors = [entry for entry in self.log_entries if entry.level == "ERROR"]
        
        # Calculate phase timing
        phase_timing = {}
        for transition in phase_transitions:
            if transition.metadata and transition.duration_ms:
                phase_timing[transition.phase] = transition.duration_ms
        
        # Calculate model loading stats
        model_stats = {
            "total_models": len(model_loads),
            "successful_loads": len([m for m in model_loads if m.metadata and m.metadata.get("status") == "loaded"]),
            "failed_loads": len([m for m in model_loads if m.metadata and m.metadata.get("status") == "failed"]),
            "total_load_time_ms": sum(m.duration_ms for m in model_loads if m.duration_ms)
        }
        
        return {
            "startup_time": self.startup_time.isoformat(),
            "total_startup_duration_ms": total_startup_time,
            "current_phase": self.phase_manager.current_phase.value if self.phase_manager else "unknown",
            "phase_timing": phase_timing,
            "model_loading_stats": model_stats,
            "resource_initializations": len(resource_inits),
            "error_count": len(errors),
            "total_log_entries": len(self.log_entries),
            "log_entry_types": {
                entry_type: len([e for e in self.log_entries if e.event_type == entry_type])
                for entry_type in set(entry.event_type for entry in self.log_entries)
            }
        }
    
    def export_logs(self, format_type: str = "json") -> str:
        """Export all startup logs in the specified format."""
        if format_type == "json":
            return json.dumps([entry.to_dict() for entry in self.log_entries], indent=2, default=str)
        elif format_type == "text":
            lines = []
            for entry in self.log_entries:
                lines.append(f"[{entry.timestamp}] {entry.level} {entry.event_type}: {entry.message}")
                if entry.error_details:
                    lines.append(f"  ERROR: {entry.error_details}")
            return "\n".join(lines)
        else:
            raise ValueError(f"Unsupported format type: {format_type}")


# Global startup logger instance
_startup_logger: Optional[StartupLogger] = None


def get_startup_logger() -> Optional[StartupLogger]:
    """Get the global startup logger instance."""
    return _startup_logger


def initialize_startup_logger(phase_manager: Optional[StartupPhaseManager] = None) -> StartupLogger:
    """Initialize the global startup logger."""
    global _startup_logger
    _startup_logger = StartupLogger(phase_manager)
    
    # Also initialize log aggregator for automatic log aggregation
    try:
        from .log_aggregator import initialize_log_aggregator
        initialize_log_aggregator()
    except ImportError:
        # Log aggregator not available, continue without it
        pass
    except Exception as e:
        # Don't let aggregator initialization errors break startup logging
        _startup_logger.logger.debug(f"Failed to initialize log aggregator: {str(e)}")
    
    return _startup_logger


def log_phase_transition_start(from_phase: Optional[StartupPhase], to_phase: StartupPhase) -> None:
    """Convenience function to log phase transition start."""
    if _startup_logger:
        _startup_logger.log_phase_transition_start(from_phase, to_phase)


def log_phase_transition_complete(transition: PhaseTransition) -> None:
    """Convenience function to log phase transition completion."""
    if _startup_logger:
        _startup_logger.log_phase_transition_complete(transition)


def log_model_loading_start(model_name: str, model_status: ModelLoadingStatus) -> None:
    """Convenience function to log model loading start."""
    if _startup_logger:
        _startup_logger.log_model_loading_start(model_name, model_status)


def log_model_loading_complete(model_name: str, model_status: ModelLoadingStatus) -> None:
    """Convenience function to log model loading completion."""
    if _startup_logger:
        _startup_logger.log_model_loading_complete(model_name, model_status)


def log_application_ready(ready_type: str, capabilities: List[str]) -> None:
    """Convenience function to log application ready state."""
    if _startup_logger:
        _startup_logger.log_application_ready(ready_type, capabilities)


def log_startup_error(error_type: str, error_message: str, 
                     context: Optional[Dict[str, Any]] = None,
                     exception: Optional[Exception] = None) -> None:
    """Convenience function to log startup errors."""
    if _startup_logger:
        _startup_logger.log_startup_error(error_type, error_message, context, exception)


class DebugContextManager:
    """Context manager for debugging function execution with automatic timing and error handling."""
    
    def __init__(self, startup_logger: StartupLogger, function_name: str, 
                 args: Optional[Dict[str, Any]] = None, kwargs: Optional[Dict[str, Any]] = None):
        self.startup_logger = startup_logger
        self.function_name = function_name
        self.args = args
        self.kwargs = kwargs
        self.start_time = None
        self.correlation_id = None
    
    def __enter__(self):
        self.start_time = time.time()
        self.correlation_id = self.startup_logger.log_debug_function_entry(
            self.function_name, self.args, self.kwargs
        )
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time:
            duration_ms = (time.time() - self.start_time) * 1000
            success = exc_type is None
            
            self.startup_logger.log_debug_function_exit(
                self.function_name, 
                duration_ms=duration_ms,
                success=success,
                error=exc_val if exc_val else None
            )
        
        # Don't suppress exceptions
        return False
    
    def log_checkpoint(self, checkpoint_name: str, context: Dict[str, Any], stack_trace: bool = False):
        """Log a checkpoint within the function execution."""
        self.startup_logger.log_debug_checkpoint(checkpoint_name, context, stack_trace)
    
    def log_variable(self, variable_name: str, variable_value: Any, context: Optional[Dict[str, Any]] = None):
        """Log a variable state within the function execution."""
        self.startup_logger.log_debug_variable_state(variable_name, variable_value, context)
    
    def log_metric(self, metric_name: str, value: float, unit: str, context: Optional[Dict[str, Any]] = None):
        """Log a performance metric within the function execution."""
        self.startup_logger.log_debug_performance_metric(metric_name, value, unit, context)
    
    def log_memory(self, context: str, additional_info: Optional[Dict[str, Any]] = None):
        """Log memory usage within the function execution."""
        self.startup_logger.log_debug_memory_usage(context, additional_info)


# Additional convenience functions for debugging
def log_debug_checkpoint(checkpoint_name: str, context: Dict[str, Any], stack_trace: bool = False) -> None:
    """Convenience function to log debug checkpoints."""
    if _startup_logger:
        _startup_logger.log_debug_checkpoint(checkpoint_name, context, stack_trace)


def log_debug_variable_state(variable_name: str, variable_value: Any, 
                            context: Optional[Dict[str, Any]] = None) -> None:
    """Convenience function to log variable states."""
    if _startup_logger:
        _startup_logger.log_debug_variable_state(variable_name, variable_value, context)


def log_debug_function_entry(function_name: str, args: Optional[Dict[str, Any]] = None,
                            kwargs: Optional[Dict[str, Any]] = None) -> str:
    """Convenience function to log function entry."""
    if _startup_logger:
        return _startup_logger.log_debug_function_entry(function_name, args, kwargs)
    return ""


def log_debug_function_exit(function_name: str, duration_ms: Optional[float] = None,
                           return_value: Any = None, success: bool = True,
                           error: Optional[Exception] = None) -> None:
    """Convenience function to log function exit."""
    if _startup_logger:
        _startup_logger.log_debug_function_exit(function_name, duration_ms, return_value, success, error)


def log_debug_performance_metric(metric_name: str, value: float, unit: str,
                                context: Optional[Dict[str, Any]] = None) -> None:
    """Convenience function to log performance metrics."""
    if _startup_logger:
        _startup_logger.log_debug_performance_metric(metric_name, value, unit, context)


def log_debug_memory_usage(context: str, additional_info: Optional[Dict[str, Any]] = None) -> None:
    """Convenience function to log memory usage."""
    if _startup_logger:
        _startup_logger.log_debug_memory_usage(context, additional_info)


def create_debug_context_manager(function_name: str, args: Optional[Dict[str, Any]] = None,
                                kwargs: Optional[Dict[str, Any]] = None):
    """Convenience function to create debug context manager."""
    if _startup_logger:
        return _startup_logger.create_debug_context_manager(function_name, args, kwargs)
    return DebugContextManager(None, function_name, args, kwargs)


def set_correlation_id(correlation_id: Optional[str] = None) -> str:
    """Convenience function to set correlation ID."""
    if _startup_logger:
        return _startup_logger.set_correlation_id(correlation_id)
    return correlation_id or str(uuid.uuid4())


def get_correlation_id() -> Optional[str]:
    """Convenience function to get correlation ID."""
    if _startup_logger:
        return _startup_logger.get_correlation_id()
    return None