"""
Comprehensive error logging service for the Multimodal Librarian system.

This module provides structured error logging with:
- Error categorization and classification
- Context information capture
- Error pattern detection
- Integration with distributed tracing
- Automatic error recovery tracking
"""

import asyncio
import inspect
import sys
import traceback
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union, Callable, Type
from dataclasses import dataclass, asdict, field
from contextlib import asynccontextmanager
from enum import Enum
import threading
from collections import defaultdict, deque
import json
import hashlib

from ..config import get_settings
from ..logging_config import get_logger
from .logging_service import get_logging_service, LoggingService


class ErrorSeverity(Enum):
    """Error severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    """Error categories for classification."""
    IMPORT_ERROR = "import_error"
    SERVICE_FAILURE = "service_failure"
    PERFORMANCE_DEGRADATION = "performance_degradation"
    NETWORK_ERROR = "network_error"
    DATABASE_ERROR = "database_error"
    AUTHENTICATION_ERROR = "authentication_error"
    VALIDATION_ERROR = "validation_error"
    CONFIGURATION_ERROR = "configuration_error"
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    EXTERNAL_SERVICE_ERROR = "external_service_error"
    UNKNOWN_ERROR = "unknown_error"


class ErrorRecoveryStatus(Enum):
    """Error recovery status."""
    NOT_ATTEMPTED = "not_attempted"
    IN_PROGRESS = "in_progress"
    RECOVERED = "recovered"
    FAILED = "failed"
    MANUAL_INTERVENTION_REQUIRED = "manual_intervention_required"


@dataclass
class ErrorContext:
    """Context information for error logging."""
    service: str
    operation: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    trace_id: Optional[str] = None
    request_id: Optional[str] = None
    component: Optional[str] = None
    function_name: Optional[str] = None
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    input_parameters: Optional[Dict[str, Any]] = None
    system_state: Optional[Dict[str, Any]] = None
    environment_info: Optional[Dict[str, Any]] = None


@dataclass
class ErrorDetails:
    """Detailed error information."""
    error_id: str
    timestamp: datetime
    severity: ErrorSeverity
    category: ErrorCategory
    error_type: str
    error_message: str
    stack_trace: str
    context: ErrorContext
    recovery_status: ErrorRecoveryStatus = ErrorRecoveryStatus.NOT_ATTEMPTED
    recovery_attempts: int = 0
    recovery_log: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Optional[Dict[str, Any]] = None
    similar_errors: List[str] = field(default_factory=list)
    impact_assessment: Optional[Dict[str, Any]] = None


@dataclass
class ErrorPattern:
    """Error pattern for detection and analysis."""
    pattern_id: str
    pattern_hash: str
    error_type: str
    error_message_pattern: str
    context_pattern: Dict[str, Any]
    occurrences: int = 0
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    severity: ErrorSeverity = ErrorSeverity.MEDIUM
    category: ErrorCategory = ErrorCategory.UNKNOWN_ERROR
    recovery_success_rate: float = 0.0
    impact_score: float = 0.0


class ErrorLoggingService:
    """Comprehensive error logging service with categorization and recovery tracking."""
    
    def __init__(self):
        self.settings = get_settings()
        self.logger = get_logger("error_logging_service")
        self.logging_service = get_logging_service()
        
        # Thread-safe storage
        self._lock = threading.Lock()
        
        # Error storage
        self._error_details = deque(maxlen=10000)  # Last 10k detailed errors
        self._error_patterns = {}  # pattern_hash -> ErrorPattern
        self._error_categories = defaultdict(int)  # category -> count
        self._error_severity_counts = defaultdict(int)  # severity -> count
        
        # Recovery tracking
        self._recovery_attempts = {}  # error_id -> recovery info
        self._recovery_success_rates = defaultdict(lambda: {'attempts': 0, 'successes': 0})
        
        # Error classification rules
        self._classification_rules = self._initialize_classification_rules()
        
        # Context extractors
        self._context_extractors = self._initialize_context_extractors()
        
        self.logger.info("Error logging service initialized")
    
    def _initialize_classification_rules(self) -> Dict[str, Dict[str, Any]]:
        """Initialize error classification rules."""
        return {
            # Import errors
            'ImportError': {
                'category': ErrorCategory.IMPORT_ERROR,
                'severity': ErrorSeverity.HIGH,
                'recovery_strategy': 'retry_with_fallback'
            },
            'ModuleNotFoundError': {
                'category': ErrorCategory.IMPORT_ERROR,
                'severity': ErrorSeverity.HIGH,
                'recovery_strategy': 'install_dependency'
            },
            
            # Service failures
            'ConnectionError': {
                'category': ErrorCategory.SERVICE_FAILURE,
                'severity': ErrorSeverity.HIGH,
                'recovery_strategy': 'retry_with_backoff'
            },
            'TimeoutError': {
                'category': ErrorCategory.NETWORK_ERROR,
                'severity': ErrorSeverity.MEDIUM,
                'recovery_strategy': 'retry_with_timeout_increase'
            },
            'HTTPError': {
                'category': ErrorCategory.EXTERNAL_SERVICE_ERROR,
                'severity': ErrorSeverity.MEDIUM,
                'recovery_strategy': 'retry_with_fallback'
            },
            
            # Database errors
            'DatabaseError': {
                'category': ErrorCategory.DATABASE_ERROR,
                'severity': ErrorSeverity.HIGH,
                'recovery_strategy': 'reconnect_database'
            },
            'IntegrityError': {
                'category': ErrorCategory.DATABASE_ERROR,
                'severity': ErrorSeverity.MEDIUM,
                'recovery_strategy': 'validate_and_retry'
            },
            
            # Performance issues
            'MemoryError': {
                'category': ErrorCategory.RESOURCE_EXHAUSTION,
                'severity': ErrorSeverity.CRITICAL,
                'recovery_strategy': 'free_memory_and_retry'
            },
            'RecursionError': {
                'category': ErrorCategory.PERFORMANCE_DEGRADATION,
                'severity': ErrorSeverity.HIGH,
                'recovery_strategy': 'optimize_algorithm'
            },
            
            # Authentication errors
            'AuthenticationError': {
                'category': ErrorCategory.AUTHENTICATION_ERROR,
                'severity': ErrorSeverity.MEDIUM,
                'recovery_strategy': 'refresh_credentials'
            },
            'PermissionError': {
                'category': ErrorCategory.AUTHENTICATION_ERROR,
                'severity': ErrorSeverity.MEDIUM,
                'recovery_strategy': 'check_permissions'
            },
            
            # Validation errors
            'ValidationError': {
                'category': ErrorCategory.VALIDATION_ERROR,
                'severity': ErrorSeverity.LOW,
                'recovery_strategy': 'sanitize_input'
            },
            'ValueError': {
                'category': ErrorCategory.VALIDATION_ERROR,
                'severity': ErrorSeverity.LOW,
                'recovery_strategy': 'validate_input'
            },
            
            # Configuration errors
            'ConfigurationError': {
                'category': ErrorCategory.CONFIGURATION_ERROR,
                'severity': ErrorSeverity.HIGH,
                'recovery_strategy': 'reload_configuration'
            },
            'KeyError': {
                'category': ErrorCategory.CONFIGURATION_ERROR,
                'severity': ErrorSeverity.MEDIUM,
                'recovery_strategy': 'use_default_value'
            }
        }
    
    def _initialize_context_extractors(self) -> Dict[str, Callable]:
        """Initialize context extraction functions."""
        return {
            'system_state': self._extract_system_state,
            'environment_info': self._extract_environment_info,
            'request_context': self._extract_request_context,
            'performance_context': self._extract_performance_context
        }
    
    def _extract_system_state(self) -> Dict[str, Any]:
        """Extract current system state information."""
        try:
            import psutil
            import os
            
            return {
                'memory_usage_percent': psutil.virtual_memory().percent,
                'cpu_usage_percent': psutil.cpu_percent(interval=1),
                'disk_usage_percent': psutil.disk_usage('/').percent,
                'active_threads': threading.active_count(),
                'process_id': os.getpid(),
                'python_version': sys.version,
                'platform': sys.platform
            }
        except Exception as e:
            return {'extraction_error': str(e)}
    
    def _extract_environment_info(self) -> Dict[str, Any]:
        """Extract environment information."""
        try:
            import os
            
            return {
                'environment': os.getenv('ENVIRONMENT', 'unknown'),
                'debug_mode': self.settings.debug if hasattr(self.settings, 'debug') else False,
                'log_level': os.getenv('LOG_LEVEL', 'INFO'),
                'service_version': os.getenv('SERVICE_VERSION', 'unknown'),
                'deployment_id': os.getenv('DEPLOYMENT_ID', 'unknown')
            }
        except Exception as e:
            return {'extraction_error': str(e)}
    
    def _extract_request_context(self) -> Dict[str, Any]:
        """Extract request context information."""
        try:
            # This would be enhanced with actual request context in a web framework
            return {
                'timestamp': datetime.now().isoformat(),
                'thread_id': threading.get_ident(),
                'thread_name': threading.current_thread().name
            }
        except Exception as e:
            return {'extraction_error': str(e)}
    
    def _extract_performance_context(self) -> Dict[str, Any]:
        """Extract performance context information."""
        try:
            # Get recent performance metrics from logging service
            perf_metrics = self.logging_service.get_performance_metrics(hours=1)
            
            return {
                'recent_avg_latency': perf_metrics.get('performance', {}).get('avg_duration_ms', 0),
                'recent_error_rate': 100 - perf_metrics.get('success_rate', 100),
                'active_traces': len(self.logging_service._active_traces) if hasattr(self.logging_service, '_active_traces') else 0
            }
        except Exception as e:
            return {'extraction_error': str(e)}
    
    def _classify_error(self, error: Exception, context: ErrorContext) -> tuple[ErrorCategory, ErrorSeverity]:
        """Classify error based on type and context."""
        error_type = type(error).__name__
        
        # Check classification rules
        if error_type in self._classification_rules:
            rule = self._classification_rules[error_type]
            return rule['category'], rule['severity']
        
        # Context-based classification
        if context.service in ['database', 'postgres', 'redis']:
            return ErrorCategory.DATABASE_ERROR, ErrorSeverity.HIGH
        
        # Check for ConnectionError specifically for database service
        if error_type == 'ConnectionError' and context.service == 'database':
            return ErrorCategory.DATABASE_ERROR, ErrorSeverity.HIGH
        
        if context.service in ['vector_store', 'search']:
            return ErrorCategory.SERVICE_FAILURE, ErrorSeverity.MEDIUM
        
        if 'timeout' in str(error).lower():
            return ErrorCategory.NETWORK_ERROR, ErrorSeverity.MEDIUM
        
        if 'memory' in str(error).lower():
            return ErrorCategory.RESOURCE_EXHAUSTION, ErrorSeverity.CRITICAL
        
        if 'permission' in str(error).lower() or 'auth' in str(error).lower():
            return ErrorCategory.AUTHENTICATION_ERROR, ErrorSeverity.MEDIUM
        
        # Default classification
        return ErrorCategory.UNKNOWN_ERROR, ErrorSeverity.MEDIUM
    
    def _generate_error_pattern_hash(self, error_type: str, error_message: str, 
                                   context: ErrorContext) -> str:
        """Generate a hash for error pattern matching."""
        # Normalize error message (remove specific values)
        normalized_message = error_message
        
        # Remove common variable parts
        import re
        normalized_message = re.sub(r'\d+', 'N', normalized_message)  # Replace numbers
        normalized_message = re.sub(r'[a-f0-9-]{36}', 'UUID', normalized_message)  # Replace UUIDs
        normalized_message = re.sub(r'/[^\s]+', '/PATH', normalized_message)  # Replace paths
        
        # Create pattern key
        pattern_key = f"{error_type}:{normalized_message}:{context.service}:{context.operation}"
        
        # Generate hash
        return hashlib.md5(pattern_key.encode()).hexdigest()
    
    def _extract_error_context(self, service: str, operation: str, 
                             additional_context: Optional[Dict[str, Any]] = None) -> ErrorContext:
        """Extract comprehensive error context."""
        # Get caller information
        frame = inspect.currentframe()
        caller_frame = frame.f_back.f_back if frame and frame.f_back else None
        
        function_name = None
        file_path = None
        line_number = None
        
        if caller_frame:
            function_name = caller_frame.f_code.co_name
            file_path = caller_frame.f_code.co_filename
            line_number = caller_frame.f_lineno
        
        # Extract context information
        context = ErrorContext(
            service=service,
            operation=operation,
            function_name=function_name,
            file_path=file_path,
            line_number=line_number,
            system_state=self._extract_system_state(),
            environment_info=self._extract_environment_info()
        )
        
        # Add additional context if provided
        if additional_context:
            if 'user_id' in additional_context:
                context.user_id = additional_context['user_id']
            if 'session_id' in additional_context:
                context.session_id = additional_context['session_id']
            if 'trace_id' in additional_context:
                context.trace_id = additional_context['trace_id']
            if 'request_id' in additional_context:
                context.request_id = additional_context['request_id']
            if 'component' in additional_context:
                context.component = additional_context['component']
            if 'input_parameters' in additional_context:
                context.input_parameters = additional_context['input_parameters']
        
        return context
    
    def log_error(self, error: Exception, service: str, operation: str,
                  additional_context: Optional[Dict[str, Any]] = None,
                  custom_severity: Optional[ErrorSeverity] = None,
                  custom_category: Optional[ErrorCategory] = None) -> str:
        """Log a comprehensive error with full context and classification."""
        
        # Generate unique error ID
        error_id = str(uuid.uuid4())
        
        # Extract context
        context = self._extract_error_context(service, operation, additional_context)
        
        # Classify error
        if custom_category and custom_severity:
            category, severity = custom_category, custom_severity
        else:
            category, severity = self._classify_error(error, context)
        
        # Get stack trace
        stack_trace = traceback.format_exc()
        
        # Create error details
        error_details = ErrorDetails(
            error_id=error_id,
            timestamp=datetime.now(),
            severity=severity,
            category=category,
            error_type=type(error).__name__,
            error_message=str(error),
            stack_trace=stack_trace,
            context=context,
            metadata=additional_context
        )
        
        # Generate pattern hash and update patterns
        pattern_hash = self._generate_error_pattern_hash(
            error_details.error_type, 
            error_details.error_message, 
            context
        )
        
        with self._lock:
            # Update error patterns
            if pattern_hash not in self._error_patterns:
                self._error_patterns[pattern_hash] = ErrorPattern(
                    pattern_id=str(uuid.uuid4()),
                    pattern_hash=pattern_hash,
                    error_type=error_details.error_type,
                    error_message_pattern=error_details.error_message,
                    context_pattern={
                        'service': context.service,
                        'operation': context.operation,
                        'component': context.component
                    },
                    first_seen=datetime.now(),
                    severity=severity,
                    category=category
                )
            
            pattern = self._error_patterns[pattern_hash]
            pattern.occurrences += 1
            pattern.last_seen = datetime.now()
            
            # Find similar errors
            similar_errors = []
            for existing_pattern_hash, existing_pattern in self._error_patterns.items():
                if (existing_pattern_hash != pattern_hash and 
                    existing_pattern.error_type == error_details.error_type and
                    existing_pattern.context_pattern.get('service') == context.service):
                    similar_errors.append(existing_pattern.pattern_id)
            
            error_details.similar_errors = similar_errors[:5]  # Limit to 5 similar errors
            
            # Store error details
            self._error_details.append(error_details)
            
            # Update counters
            self._error_categories[category] += 1
            self._error_severity_counts[severity] += 1
        
        # Log to structured logging service
        self.logging_service.log_structured(
            level='ERROR',
            service=service,
            operation=operation,
            message=f"[{category.value}] {error_details.error_message}",
            trace_id=context.trace_id,
            user_id=context.user_id,
            metadata={
                'error_id': error_id,
                'error_type': error_details.error_type,
                'error_category': category.value,
                'error_severity': severity.value,
                'pattern_hash': pattern_hash,
                'similar_errors_count': len(similar_errors),
                'context': asdict(context)
            },
            error=error
        )
        
        # Log critical errors immediately
        if severity == ErrorSeverity.CRITICAL:
            self.logger.critical(
                f"CRITICAL ERROR [{error_id}]: {error_details.error_message}",
                extra={
                    'error_id': error_id,
                    'service': service,
                    'operation': operation,
                    'category': category.value
                }
            )
        
        return error_id
    
    def log_recovery_attempt(self, error_id: str, recovery_strategy: str, 
                           success: bool, details: Optional[Dict[str, Any]] = None) -> None:
        """Log an error recovery attempt."""
        
        with self._lock:
            # Find the error
            error_details = None
            for error in reversed(self._error_details):
                if error.error_id == error_id:
                    error_details = error
                    break
            
            if not error_details:
                self.logger.warning(f"Recovery attempt logged for unknown error: {error_id}")
                return
            
            # Update recovery information
            error_details.recovery_attempts += 1
            error_details.recovery_log.append({
                'timestamp': datetime.now().isoformat(),
                'strategy': recovery_strategy,
                'success': success,
                'details': details or {}
            })
            
            if success:
                error_details.recovery_status = ErrorRecoveryStatus.RECOVERED
            else:
                error_details.recovery_status = ErrorRecoveryStatus.FAILED
            
            # Update recovery success rates
            recovery_key = f"{error_details.category.value}:{recovery_strategy}"
            recovery_stats = self._recovery_success_rates[recovery_key]
            recovery_stats['attempts'] += 1
            if success:
                recovery_stats['successes'] += 1
        
        # Log recovery attempt
        self.logging_service.log_structured(
            level='INFO' if success else 'WARNING',
            service='error_recovery',
            operation='recovery_attempt',
            message=f"Recovery attempt for error {error_id}: {recovery_strategy} ({'SUCCESS' if success else 'FAILED'})",
            metadata={
                'error_id': error_id,
                'recovery_strategy': recovery_strategy,
                'success': success,
                'attempt_number': error_details.recovery_attempts if error_details else 0,
                'details': details
            }
        )
    
    @asynccontextmanager
    async def error_context(self, service: str, operation: str, 
                           additional_context: Optional[Dict[str, Any]] = None):
        """Context manager for automatic error logging."""
        try:
            yield
        except Exception as e:
            error_id = self.log_error(e, service, operation, additional_context)
            # Re-raise the exception with error ID
            e.error_id = error_id
            raise
    
    def get_error_summary(self, hours: int = 24) -> Dict[str, Any]:
        """Get comprehensive error summary."""
        
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        with self._lock:
            # Filter recent errors
            recent_errors = [
                error for error in self._error_details
                if error.timestamp >= cutoff_time
            ]
            
            if not recent_errors:
                return {
                    'total_errors': 0,
                    'time_period_hours': hours,
                    'error_categories': {},
                    'error_severities': {},
                    'errors_by_service': {},
                    'recovery_statistics': {},
                    'top_error_patterns': [],
                    'critical_errors': 0,
                    'unrecovered_errors': 0,
                    'message': 'No errors found in the specified time period'
                }
            
            # Calculate statistics
            category_counts = defaultdict(int)
            severity_counts = defaultdict(int)
            service_counts = defaultdict(int)
            recovery_stats = defaultdict(lambda: {'total': 0, 'recovered': 0})
            
            for error in recent_errors:
                category_counts[error.category.value] += 1
                severity_counts[error.severity.value] += 1
                service_counts[error.context.service] += 1
                
                recovery_key = error.category.value
                recovery_stats[recovery_key]['total'] += 1
                if error.recovery_status == ErrorRecoveryStatus.RECOVERED:
                    recovery_stats[recovery_key]['recovered'] += 1
            
            # Get top error patterns
            pattern_counts = defaultdict(int)
            for error in recent_errors:
                pattern_hash = self._generate_error_pattern_hash(
                    error.error_type, error.error_message, error.context
                )
                pattern_counts[pattern_hash] += 1
            
            top_patterns = []
            for pattern_hash, count in sorted(pattern_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
                if pattern_hash in self._error_patterns:
                    pattern = self._error_patterns[pattern_hash]
                    top_patterns.append({
                        'pattern_id': pattern.pattern_id,
                        'error_type': pattern.error_type,
                        'message_pattern': pattern.error_message_pattern[:100] + '...' if len(pattern.error_message_pattern) > 100 else pattern.error_message_pattern,
                        'occurrences': count,
                        'category': pattern.category.value,
                        'severity': pattern.severity.value
                    })
            
            return {
                'total_errors': len(recent_errors),
                'time_period_hours': hours,
                'error_categories': dict(category_counts),
                'error_severities': dict(severity_counts),
                'errors_by_service': dict(service_counts),
                'recovery_statistics': {
                    category: {
                        'recovery_rate': (stats['recovered'] / stats['total']) * 100 if stats['total'] > 0 else 0,
                        'total_errors': stats['total'],
                        'recovered_errors': stats['recovered']
                    }
                    for category, stats in recovery_stats.items()
                },
                'top_error_patterns': top_patterns,
                'critical_errors': len([e for e in recent_errors if e.severity == ErrorSeverity.CRITICAL]),
                'unrecovered_errors': len([e for e in recent_errors if e.recovery_status not in [ErrorRecoveryStatus.RECOVERED, ErrorRecoveryStatus.NOT_ATTEMPTED]])
            }
    
    def get_error_details(self, error_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a specific error."""
        
        with self._lock:
            for error in reversed(self._error_details):
                if error.error_id == error_id:
                    return {
                        'error_details': asdict(error),
                        'pattern_info': asdict(self._error_patterns.get(
                            self._generate_error_pattern_hash(
                                error.error_type, error.error_message, error.context
                            )
                        )) if self._error_patterns.get(
                            self._generate_error_pattern_hash(
                                error.error_type, error.error_message, error.context
                            )
                        ) else None
                    }
        
        return None
    
    def get_error_patterns(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get error patterns sorted by frequency and impact."""
        
        with self._lock:
            patterns = list(self._error_patterns.values())
            
            # Sort by occurrences and severity
            patterns.sort(key=lambda p: (p.occurrences, p.severity.value), reverse=True)
            
            return [asdict(pattern) for pattern in patterns[:limit]]
    
    def export_error_data(self, filepath: Optional[str] = None, hours: int = 24) -> str:
        """Export error data to JSON file."""
        
        if not filepath:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filepath = f"error_export_{timestamp}.json"
        
        export_data = {
            'export_timestamp': datetime.now().isoformat(),
            'time_period_hours': hours,
            'error_summary': self.get_error_summary(hours=hours),
            'error_patterns': self.get_error_patterns(),
            'classification_rules': {
                error_type: {
                    'category': rule['category'].value,
                    'severity': rule['severity'].value,
                    'recovery_strategy': rule['recovery_strategy']
                }
                for error_type, rule in self._classification_rules.items()
            },
            'recovery_success_rates': dict(self._recovery_success_rates)
        }
        
        try:
            import os
            if filepath and os.path.dirname(filepath):
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
            
            with open(filepath, 'w') as f:
                json.dump(export_data, f, indent=2, default=str)
            
            self.logger.info(f"Error data exported to {filepath}")
            return filepath
            
        except Exception as e:
            self.logger.error(f"Failed to export error data: {e}")
            raise


# Global error logging service instance
_error_logging_service = None


def get_error_logging_service() -> ErrorLoggingService:
    """Get the global error logging service instance."""
    global _error_logging_service
    if _error_logging_service is None:
        _error_logging_service = ErrorLoggingService()
    return _error_logging_service


# Convenience functions for error logging
def log_error(error: Exception, service: str, operation: str, **kwargs) -> str:
    """Log an error with comprehensive context."""
    return get_error_logging_service().log_error(error, service, operation, **kwargs)


def log_recovery_attempt(error_id: str, recovery_strategy: str, success: bool, **kwargs):
    """Log an error recovery attempt."""
    get_error_logging_service().log_recovery_attempt(error_id, recovery_strategy, success, **kwargs)


def error_context(service: str, operation: str, additional_context: Optional[Dict[str, Any]] = None):
    """Context manager for automatic error logging."""
    return get_error_logging_service().error_context(service, operation, additional_context)