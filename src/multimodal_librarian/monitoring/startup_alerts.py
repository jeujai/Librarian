"""
Startup Alerts System for Multimodal Librarian Application

This module provides proactive alerting for startup issues including phase timeouts,
model loading failures, health check failures, and user experience degradation.

Key Features:
- Phase timeout alerts with configurable thresholds
- Model loading failure notifications with context
- Health check failure monitoring with root cause analysis
- User experience degradation alerts with severity levels
- Integration with CloudWatch Alarms and notification systems
"""

import asyncio
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable, Set
from dataclasses import dataclass, field
from enum import Enum
import json

from ..startup.phase_manager import StartupPhase, StartupPhaseManager, PhaseTransition, ModelLoadingStatus
from .startup_metrics import StartupMetricsCollector, PhaseCompletionMetric, ModelLoadingMetric, UserWaitTimeMetric

logger = logging.getLogger(__name__)


class AlertSeverity(Enum):
    """Alert severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertType(Enum):
    """Types of startup alerts."""
    PHASE_TIMEOUT = "phase_timeout"
    MODEL_LOADING_FAILURE = "model_loading_failure"
    HEALTH_CHECK_FAILURE = "health_check_failure"
    USER_EXPERIENCE_DEGRADATION = "user_experience_degradation"
    CACHE_PERFORMANCE_DEGRADATION = "cache_performance_degradation"
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    STARTUP_FAILURE = "startup_failure"
    GIL_CONTENTION = "gil_contention"  # GIL contention during model loading


@dataclass
class AlertThreshold:
    """Configuration for alert thresholds."""
    name: str
    threshold_value: float
    comparison: str  # "greater_than", "less_than", "equals"
    duration_seconds: float = 0.0  # How long condition must persist
    severity: AlertSeverity = AlertSeverity.MEDIUM
    enabled: bool = True
    description: str = ""
    remediation_steps: List[str] = field(default_factory=list)


@dataclass
class Alert:
    """Represents a startup alert."""
    alert_id: str
    alert_type: AlertType
    severity: AlertSeverity
    title: str
    description: str
    timestamp: datetime
    source_component: str
    affected_resources: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    remediation_steps: List[str] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    resolved: bool = False
    resolved_at: Optional[datetime] = None
    resolution_notes: Optional[str] = None
    notification_sent: bool = False
    escalation_level: int = 0
    correlation_id: Optional[str] = None  # For grouping related alerts


@dataclass
class AlertRule:
    """Defines conditions for triggering alerts."""
    rule_id: str
    alert_type: AlertType
    name: str
    description: str
    condition: Callable[[Dict[str, Any]], bool]
    severity: AlertSeverity
    threshold: AlertThreshold
    cooldown_seconds: float = 300.0  # 5 minutes default cooldown
    max_alerts_per_hour: int = 10
    enabled: bool = True
    tags: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)  # Other rule IDs this depends on


class StartupAlertsService:
    """
    Proactive alerting service for startup issues.
    
    This service monitors startup metrics and triggers alerts when thresholds
    are exceeded or issues are detected.
    """
    
    def __init__(self, phase_manager: StartupPhaseManager, metrics_collector: StartupMetricsCollector):
        """Initialize the startup alerts service."""
        self.phase_manager = phase_manager
        self.metrics_collector = metrics_collector
        self.service_id = f"startup_alerts_{int(time.time())}"
        
        # Alert state
        self.active_alerts: Dict[str, Alert] = {}
        self.alert_history: List[Alert] = []
        self.alert_rules: Dict[str, AlertRule] = {}
        self.alert_counters: Dict[str, int] = {}  # Track alerts per rule per hour
        self.last_alert_times: Dict[str, datetime] = {}  # Track cooldowns
        
        # Configuration
        self.default_thresholds = self._initialize_default_thresholds()
        self.notification_handlers: List[Callable[[Alert], None]] = []
        
        # Monitoring state
        self._is_monitoring = False
        self._monitoring_task: Optional[asyncio.Task] = None
        self._alert_processing_task: Optional[asyncio.Task] = None
        self._alert_queue: asyncio.Queue = asyncio.Queue()
        
        # Performance tracking
        self._last_health_check_time: Optional[datetime] = None
        self._consecutive_health_failures = 0
        self._startup_failure_detected = False
        
        # Initialize alert rules
        self._initialize_alert_rules()
        
        logger.info(f"StartupAlertsService initialized with service ID: {self.service_id}")
    
    def _initialize_default_thresholds(self) -> Dict[str, AlertThreshold]:
        """Initialize default alert thresholds."""
        return {
            "minimal_phase_timeout": AlertThreshold(
                name="minimal_phase_timeout",
                threshold_value=60.0,  # 60 seconds
                comparison="greater_than",
                duration_seconds=10.0,
                severity=AlertSeverity.HIGH,
                description="Minimal startup phase taking too long",
                remediation_steps=[
                    "Check application logs for startup errors",
                    "Verify resource availability (CPU, memory)",
                    "Check network connectivity to dependencies",
                    "Review health check configuration"
                ]
            ),
            "essential_phase_timeout": AlertThreshold(
                name="essential_phase_timeout",
                threshold_value=180.0,  # 3 minutes
                comparison="greater_than",
                duration_seconds=15.0,
                severity=AlertSeverity.HIGH,
                description="Essential startup phase taking too long",
                remediation_steps=[
                    "Check model loading performance",
                    "Verify cache availability and performance",
                    "Review model prioritization configuration",
                    "Check for resource contention"
                ]
            ),
            "full_phase_timeout": AlertThreshold(
                name="full_phase_timeout",
                threshold_value=600.0,  # 10 minutes
                comparison="greater_than",
                duration_seconds=30.0,
                severity=AlertSeverity.MEDIUM,
                description="Full startup phase taking too long",
                remediation_steps=[
                    "Review model loading strategy",
                    "Check for network issues affecting model downloads",
                    "Verify storage performance for model cache",
                    "Consider model optimization or compression"
                ]
            ),
            "model_loading_timeout": AlertThreshold(
                name="model_loading_timeout",
                threshold_value=300.0,  # 5 minutes
                comparison="greater_than",
                duration_seconds=0.0,
                severity=AlertSeverity.HIGH,
                description="Individual model loading taking too long",
                remediation_steps=[
                    "Check model file integrity",
                    "Verify storage performance",
                    "Review model size and optimization",
                    "Check for memory constraints"
                ]
            ),
            "user_wait_time_threshold": AlertThreshold(
                name="user_wait_time_threshold",
                threshold_value=30.0,  # 30 seconds
                comparison="greater_than",
                duration_seconds=0.0,
                severity=AlertSeverity.MEDIUM,
                description="Users experiencing long wait times",
                remediation_steps=[
                    "Review startup phase progression",
                    "Check fallback response quality",
                    "Verify model loading priorities",
                    "Consider user experience optimizations"
                ]
            ),
            "user_p95_wait_time_threshold": AlertThreshold(
                name="user_p95_wait_time_threshold",
                threshold_value=60.0,  # 60 seconds for P95
                comparison="greater_than",
                duration_seconds=30.0,  # Must persist for 30 seconds
                severity=AlertSeverity.HIGH,
                description="P95 user wait times are excessive",
                remediation_steps=[
                    "Investigate outlier requests causing delays",
                    "Check for resource contention",
                    "Review model loading bottlenecks",
                    "Consider request prioritization"
                ]
            ),
            "high_fallback_usage_threshold": AlertThreshold(
                name="high_fallback_usage_threshold",
                threshold_value=0.7,  # 70% fallback usage
                comparison="greater_than",
                duration_seconds=120.0,  # Must persist for 2 minutes
                severity=AlertSeverity.MEDIUM,
                description="High fallback response usage indicates degraded service",
                remediation_steps=[
                    "Check model loading progress",
                    "Verify essential models are loaded",
                    "Review fallback response quality",
                    "Consider accelerating model loading"
                ]
            ),
            "low_success_rate_threshold": AlertThreshold(
                name="low_success_rate_threshold",
                threshold_value=0.8,  # 80% success rate
                comparison="less_than",
                duration_seconds=60.0,  # Must persist for 1 minute
                severity=AlertSeverity.HIGH,
                description="User request success rate is below acceptable levels",
                remediation_steps=[
                    "Check application error logs",
                    "Verify service dependencies",
                    "Review resource availability",
                    "Check for model loading failures"
                ]
            ),
            "high_timeout_rate_threshold": AlertThreshold(
                name="high_timeout_rate_threshold",
                threshold_value=0.1,  # 10% timeout rate
                comparison="greater_than",
                duration_seconds=60.0,  # Must persist for 1 minute
                severity=AlertSeverity.HIGH,
                description="High request timeout rate affecting user experience",
                remediation_steps=[
                    "Review request timeout configurations",
                    "Check for slow model responses",
                    "Verify resource performance",
                    "Consider request optimization"
                ]
            ),
            "high_abandonment_rate_threshold": AlertThreshold(
                name="high_abandonment_rate_threshold",
                threshold_value=0.2,  # 20% abandonment rate
                comparison="greater_than",
                duration_seconds=120.0,  # Must persist for 2 minutes
                severity=AlertSeverity.MEDIUM,
                description="High user request abandonment rate",
                remediation_steps=[
                    "Improve loading state communication",
                    "Reduce actual wait times",
                    "Enhance progress indicators",
                    "Review user experience design"
                ]
            ),
            "essential_capability_unavailable_threshold": AlertThreshold(
                name="essential_capability_unavailable_threshold",
                threshold_value=1.0,  # Any essential capability down
                comparison="greater_than",
                duration_seconds=30.0,  # Must persist for 30 seconds
                severity=AlertSeverity.CRITICAL,
                description="Essential capabilities unavailable to users",
                remediation_steps=[
                    "Immediately check essential model status",
                    "Verify model loading progress",
                    "Consider emergency model loading",
                    "Activate backup capabilities if available"
                ]
            ),
            "cache_hit_rate_minimum": AlertThreshold(
                name="cache_hit_rate_minimum",
                threshold_value=0.5,  # 50%
                comparison="less_than",
                duration_seconds=300.0,  # 5 minutes
                severity=AlertSeverity.MEDIUM,
                description="Model cache hit rate below acceptable threshold",
                remediation_steps=[
                    "Review cache warming strategies",
                    "Check cache storage availability",
                    "Verify cache retention policies",
                    "Analyze model usage patterns"
                ]
            ),
            "health_check_failure_threshold": AlertThreshold(
                name="health_check_failure_threshold",
                threshold_value=3.0,  # 3 consecutive failures
                comparison="greater_than",
                duration_seconds=0.0,
                severity=AlertSeverity.CRITICAL,
                description="Multiple consecutive health check failures",
                remediation_steps=[
                    "Check application health endpoints",
                    "Verify service dependencies",
                    "Review resource utilization",
                    "Check for application errors"
                ]
            ),
            "startup_failure_rate": AlertThreshold(
                name="startup_failure_rate",
                threshold_value=0.2,  # 20%
                comparison="greater_than",
                duration_seconds=600.0,  # 10 minutes
                severity=AlertSeverity.CRITICAL,
                description="High startup failure rate detected",
                remediation_steps=[
                    "Review startup logs for common errors",
                    "Check infrastructure health",
                    "Verify configuration correctness",
                    "Consider rollback if recent deployment"
                ]
            ),
            # GIL contention detection thresholds
            "gil_contention_slow_rate_threshold": AlertThreshold(
                name="gil_contention_slow_rate_threshold",
                threshold_value=0.1,  # 10% of health checks > 100ms
                comparison="greater_than",
                duration_seconds=30.0,  # Must persist for 30 seconds
                severity=AlertSeverity.HIGH,
                description="High rate of slow health checks indicating GIL contention",
                remediation_steps=[
                    "Use ProcessPoolExecutor for CPU-bound model loading operations",
                    "Add yield points (await asyncio.sleep(0)) in long-running async operations",
                    "Review model loading code for GIL-holding operations",
                    "Consider lazy loading for non-essential models",
                    "Check for blocking I/O operations in async code"
                ]
            ),
            "gil_contention_max_latency_threshold": AlertThreshold(
                name="gil_contention_max_latency_threshold",
                threshold_value=500.0,  # 500ms max latency
                comparison="greater_than",
                duration_seconds=0.0,  # Immediate alert on extreme latency
                severity=AlertSeverity.CRITICAL,
                description="Extreme health check latency indicating severe GIL contention",
                remediation_steps=[
                    "Immediately investigate model loading operations",
                    "Check for CPU-intensive operations blocking the event loop",
                    "Consider emergency model loading optimization",
                    "Review ProcessPoolExecutor configuration",
                    "Check for memory pressure causing GC pauses"
                ]
            ),
            "gil_contention_avg_latency_threshold": AlertThreshold(
                name="gil_contention_avg_latency_threshold",
                threshold_value=50.0,  # 50ms average latency
                comparison="greater_than",
                duration_seconds=60.0,  # Must persist for 1 minute
                severity=AlertSeverity.MEDIUM,
                description="Elevated average health check latency during model loading",
                remediation_steps=[
                    "Review model loading parallelization strategy",
                    "Consider using ProcessPoolExecutor for heavy operations",
                    "Add yield points in long-running operations",
                    "Optimize model initialization code"
                ]
            ),
            "gil_contention_loading_correlation_threshold": AlertThreshold(
                name="gil_contention_loading_correlation_threshold",
                threshold_value=0.8,  # 80% of slow checks during model loading
                comparison="greater_than",
                duration_seconds=30.0,  # Must persist for 30 seconds
                severity=AlertSeverity.HIGH,
                description="Strong correlation between model loading and slow health checks",
                remediation_steps=[
                    "Model loading is blocking the event loop",
                    "Migrate CPU-bound model loading to ProcessPoolExecutor",
                    "Review specific models causing the most contention",
                    "Consider model loading prioritization changes"
                ]
            )
        }
    
    def _initialize_alert_rules(self) -> None:
        """Initialize alert rules based on thresholds."""
        # Phase timeout rules
        for phase in StartupPhase:
            threshold_name = f"{phase.value}_phase_timeout"
            threshold = self.default_thresholds.get(threshold_name)
            if threshold:
                rule = AlertRule(
                    rule_id=f"phase_timeout_{phase.value}",
                    alert_type=AlertType.PHASE_TIMEOUT,
                    name=f"{phase.value.title()} Phase Timeout",
                    description=f"Alert when {phase.value} phase exceeds timeout threshold",
                    condition=lambda data, p=phase, t=threshold: self._check_phase_timeout(data, p, t),
                    severity=threshold.severity,
                    threshold=threshold,
                    tags=[f"phase:{phase.value}", "startup", "timeout"]
                )
                self.alert_rules[rule.rule_id] = rule
        
        # Model loading failure rule
        model_threshold = self.default_thresholds["model_loading_timeout"]
        self.alert_rules["model_loading_failure"] = AlertRule(
            rule_id="model_loading_failure",
            alert_type=AlertType.MODEL_LOADING_FAILURE,
            name="Model Loading Failure",
            description="Alert when model loading fails or times out",
            condition=lambda data: self._check_model_loading_issues(data),
            severity=model_threshold.severity,
            threshold=model_threshold,
            tags=["model", "loading", "failure"]
        )
        
        # Essential model loading failure rule (higher severity)
        self.alert_rules["essential_model_failure"] = AlertRule(
            rule_id="essential_model_failure",
            alert_type=AlertType.MODEL_LOADING_FAILURE,
            name="Essential Model Loading Failure",
            description="Critical alert when essential models fail to load",
            condition=lambda data: self._check_essential_model_failures(data),
            severity=AlertSeverity.CRITICAL,
            threshold=model_threshold,
            cooldown_seconds=60.0,  # Shorter cooldown for critical issues
            tags=["model", "essential", "critical", "failure"]
        )
        
        # Model loading timeout rule (separate from failures)
        self.alert_rules["model_loading_timeout"] = AlertRule(
            rule_id="model_loading_timeout",
            alert_type=AlertType.MODEL_LOADING_FAILURE,
            name="Model Loading Timeout",
            description="Alert when models take too long to load",
            condition=lambda data: self._check_model_loading_timeouts(data),
            severity=AlertSeverity.MEDIUM,
            threshold=model_threshold,
            tags=["model", "timeout", "performance"]
        )
        
        # Repeated model loading failures rule
        self.alert_rules["repeated_model_failures"] = AlertRule(
            rule_id="repeated_model_failures",
            alert_type=AlertType.MODEL_LOADING_FAILURE,
            name="Repeated Model Loading Failures",
            description="Alert when models fail repeatedly after retries",
            condition=lambda data: self._check_repeated_model_failures(data),
            severity=AlertSeverity.HIGH,
            threshold=model_threshold,
            cooldown_seconds=600.0,  # Longer cooldown for repeated failures
            tags=["model", "repeated", "failure", "retry"]
        )
        
        # Health check failure rule
        health_threshold = self.default_thresholds["health_check_failure_threshold"]
        self.alert_rules["health_check_failure"] = AlertRule(
            rule_id="health_check_failure",
            alert_type=AlertType.HEALTH_CHECK_FAILURE,
            name="Health Check Failure",
            description="Alert when health checks fail repeatedly",
            condition=lambda data: self._check_health_failures(data),
            severity=health_threshold.severity,
            threshold=health_threshold,
            tags=["health", "check", "failure"]
        )
        
        # User experience degradation rules
        ux_threshold = self.default_thresholds["user_wait_time_threshold"]
        self.alert_rules["user_experience_degradation"] = AlertRule(
            rule_id="user_experience_degradation",
            alert_type=AlertType.USER_EXPERIENCE_DEGRADATION,
            name="User Experience Degradation",
            description="Alert when user wait times exceed acceptable thresholds",
            condition=lambda data: self._check_user_experience_degradation(data),
            severity=ux_threshold.severity,
            threshold=ux_threshold,
            tags=["user", "experience", "performance"]
        )
        
        # P95 wait time degradation rule
        p95_threshold = self.default_thresholds["user_p95_wait_time_threshold"]
        self.alert_rules["user_p95_wait_time_degradation"] = AlertRule(
            rule_id="user_p95_wait_time_degradation",
            alert_type=AlertType.USER_EXPERIENCE_DEGRADATION,
            name="P95 User Wait Time Degradation",
            description="Alert when P95 user wait times are excessive",
            condition=lambda data: self._check_p95_wait_time_degradation(data),
            severity=p95_threshold.severity,
            threshold=p95_threshold,
            tags=["user", "experience", "p95", "performance"]
        )
        
        # High fallback usage rule
        fallback_threshold = self.default_thresholds["high_fallback_usage_threshold"]
        self.alert_rules["high_fallback_usage"] = AlertRule(
            rule_id="high_fallback_usage",
            alert_type=AlertType.USER_EXPERIENCE_DEGRADATION,
            name="High Fallback Usage",
            description="Alert when fallback response usage is high",
            condition=lambda data: self._check_high_fallback_usage(data),
            severity=fallback_threshold.severity,
            threshold=fallback_threshold,
            tags=["user", "experience", "fallback", "degradation"]
        )
        
        # Low success rate rule
        success_threshold = self.default_thresholds["low_success_rate_threshold"]
        self.alert_rules["low_user_success_rate"] = AlertRule(
            rule_id="low_user_success_rate",
            alert_type=AlertType.USER_EXPERIENCE_DEGRADATION,
            name="Low User Request Success Rate",
            description="Alert when user request success rate is low",
            condition=lambda data: self._check_low_success_rate(data),
            severity=success_threshold.severity,
            threshold=success_threshold,
            tags=["user", "experience", "success", "failure"]
        )
        
        # High timeout rate rule
        timeout_threshold = self.default_thresholds["high_timeout_rate_threshold"]
        self.alert_rules["high_timeout_rate"] = AlertRule(
            rule_id="high_timeout_rate",
            alert_type=AlertType.USER_EXPERIENCE_DEGRADATION,
            name="High Request Timeout Rate",
            description="Alert when request timeout rate is high",
            condition=lambda data: self._check_high_timeout_rate(data),
            severity=timeout_threshold.severity,
            threshold=timeout_threshold,
            tags=["user", "experience", "timeout", "performance"]
        )
        
        # High abandonment rate rule
        abandonment_threshold = self.default_thresholds["high_abandonment_rate_threshold"]
        self.alert_rules["high_abandonment_rate"] = AlertRule(
            rule_id="high_abandonment_rate",
            alert_type=AlertType.USER_EXPERIENCE_DEGRADATION,
            name="High User Request Abandonment Rate",
            description="Alert when users abandon requests frequently",
            condition=lambda data: self._check_high_abandonment_rate(data),
            severity=abandonment_threshold.severity,
            threshold=abandonment_threshold,
            tags=["user", "experience", "abandonment", "ux"]
        )
        
        # Essential capability unavailable rule
        capability_threshold = self.default_thresholds["essential_capability_unavailable_threshold"]
        self.alert_rules["essential_capability_unavailable"] = AlertRule(
            rule_id="essential_capability_unavailable",
            alert_type=AlertType.USER_EXPERIENCE_DEGRADATION,
            name="Essential Capability Unavailable",
            description="Alert when essential capabilities are unavailable to users",
            condition=lambda data: self._check_essential_capability_unavailable(data),
            severity=capability_threshold.severity,
            threshold=capability_threshold,
            cooldown_seconds=60.0,  # Shorter cooldown for critical UX issues
            tags=["user", "experience", "capability", "critical"]
        )
        
        # Cache performance degradation rule
        cache_threshold = self.default_thresholds["cache_hit_rate_minimum"]
        self.alert_rules["cache_performance_degradation"] = AlertRule(
            rule_id="cache_performance_degradation",
            alert_type=AlertType.CACHE_PERFORMANCE_DEGRADATION,
            name="Cache Performance Degradation",
            description="Alert when cache hit rate falls below acceptable levels",
            condition=lambda data: self._check_cache_performance(data),
            severity=cache_threshold.severity,
            threshold=cache_threshold,
            tags=["cache", "performance", "degradation"]
        )
        
        # Startup failure rule
        failure_threshold = self.default_thresholds["startup_failure_rate"]
        self.alert_rules["startup_failure"] = AlertRule(
            rule_id="startup_failure",
            alert_type=AlertType.STARTUP_FAILURE,
            name="Startup Failure",
            description="Alert when startup failure rate is high",
            condition=lambda data: self._check_startup_failures(data),
            severity=failure_threshold.severity,
            threshold=failure_threshold,
            cooldown_seconds=600.0,  # 10 minutes
            tags=["startup", "failure", "critical"]
        )
        
        # GIL contention detection rules
        # High slow health check rate rule
        gil_slow_rate_threshold = self.default_thresholds["gil_contention_slow_rate_threshold"]
        self.alert_rules["gil_contention_slow_rate"] = AlertRule(
            rule_id="gil_contention_slow_rate",
            alert_type=AlertType.GIL_CONTENTION,
            name="GIL Contention - High Slow Health Check Rate",
            description="Alert when health check slow rate indicates GIL contention",
            condition=lambda data: self._check_gil_contention_slow_rate(data),
            severity=gil_slow_rate_threshold.severity,
            threshold=gil_slow_rate_threshold,
            cooldown_seconds=120.0,  # 2 minutes cooldown
            tags=["gil", "contention", "health_check", "performance"]
        )
        
        # Extreme health check latency rule
        gil_max_latency_threshold = self.default_thresholds["gil_contention_max_latency_threshold"]
        self.alert_rules["gil_contention_extreme_latency"] = AlertRule(
            rule_id="gil_contention_extreme_latency",
            alert_type=AlertType.GIL_CONTENTION,
            name="GIL Contention - Extreme Health Check Latency",
            description="Alert when health check latency is extremely high",
            condition=lambda data: self._check_gil_contention_extreme_latency(data),
            severity=gil_max_latency_threshold.severity,
            threshold=gil_max_latency_threshold,
            cooldown_seconds=60.0,  # 1 minute cooldown for critical
            tags=["gil", "contention", "latency", "critical"]
        )
        
        # Elevated average latency rule
        gil_avg_latency_threshold = self.default_thresholds["gil_contention_avg_latency_threshold"]
        self.alert_rules["gil_contention_elevated_latency"] = AlertRule(
            rule_id="gil_contention_elevated_latency",
            alert_type=AlertType.GIL_CONTENTION,
            name="GIL Contention - Elevated Average Latency",
            description="Alert when average health check latency is elevated",
            condition=lambda data: self._check_gil_contention_elevated_latency(data),
            severity=gil_avg_latency_threshold.severity,
            threshold=gil_avg_latency_threshold,
            cooldown_seconds=180.0,  # 3 minutes cooldown
            tags=["gil", "contention", "latency", "performance"]
        )
        
        # Model loading correlation rule
        gil_correlation_threshold = self.default_thresholds["gil_contention_loading_correlation_threshold"]
        self.alert_rules["gil_contention_model_loading_correlation"] = AlertRule(
            rule_id="gil_contention_model_loading_correlation",
            alert_type=AlertType.GIL_CONTENTION,
            name="GIL Contention - Model Loading Correlation",
            description="Alert when slow health checks correlate strongly with model loading",
            condition=lambda data: self._check_gil_contention_loading_correlation(data),
            severity=gil_correlation_threshold.severity,
            threshold=gil_correlation_threshold,
            cooldown_seconds=120.0,  # 2 minutes cooldown
            tags=["gil", "contention", "model_loading", "correlation"]
        )
        
        logger.info(f"Initialized {len(self.alert_rules)} alert rules")
    
    async def start_monitoring(self) -> None:
        """Start the alert monitoring service."""
        if self._is_monitoring:
            logger.warning("Alert monitoring already started")
            return
        
        self._is_monitoring = True
        logger.info("Starting startup alerts monitoring")
        
        # Start monitoring task
        self._monitoring_task = asyncio.create_task(self._monitoring_loop())
        
        # Start alert processing task
        self._alert_processing_task = asyncio.create_task(self._process_alerts_loop())
        
        logger.info("Startup alerts monitoring started")
    
    async def stop_monitoring(self) -> None:
        """Stop the alert monitoring service."""
        if not self._is_monitoring:
            return
        
        self._is_monitoring = False
        logger.info("Stopping startup alerts monitoring")
        
        # Cancel monitoring tasks
        if self._monitoring_task and not self._monitoring_task.done():
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
        
        if self._alert_processing_task and not self._alert_processing_task.done():
            self._alert_processing_task.cancel()
            try:
                await self._alert_processing_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Startup alerts monitoring stopped")
    
    async def _monitoring_loop(self) -> None:
        """Main monitoring loop that checks for alert conditions."""
        try:
            while self._is_monitoring:
                try:
                    # Collect current metrics and status
                    monitoring_data = await self._collect_monitoring_data()
                    
                    # Check each alert rule
                    for rule_id, rule in self.alert_rules.items():
                        if not rule.enabled:
                            continue
                        
                        try:
                            # Check if rule condition is met
                            if rule.condition(monitoring_data):
                                await self._handle_rule_trigger(rule, monitoring_data)
                        except Exception as e:
                            logger.error(f"Error checking alert rule {rule_id}: {e}")
                    
                    # Check for alert resolutions
                    await self._check_alert_resolutions(monitoring_data)
                    
                    # Clean up old alert counters (hourly reset)
                    await self._cleanup_alert_counters()
                    
                except Exception as e:
                    logger.error(f"Error in monitoring loop: {e}")
                
                # Wait before next check
                await asyncio.sleep(10.0)  # Check every 10 seconds
                
        except asyncio.CancelledError:
            logger.info("Monitoring loop cancelled")
            raise
        except Exception as e:
            logger.error(f"Fatal error in monitoring loop: {e}")
    
    async def _process_alerts_loop(self) -> None:
        """Process alerts from the queue."""
        try:
            while self._is_monitoring:
                try:
                    # Wait for alert to process
                    alert = await asyncio.wait_for(self._alert_queue.get(), timeout=5.0)
                    
                    # Process the alert
                    await self._process_alert(alert)
                    
                    # Mark task as done
                    self._alert_queue.task_done()
                    
                except asyncio.TimeoutError:
                    # No alerts to process, continue
                    continue
                except Exception as e:
                    logger.error(f"Error processing alert: {e}")
                    
        except asyncio.CancelledError:
            logger.info("Alert processing loop cancelled")
            raise
        except Exception as e:
            logger.error(f"Fatal error in alert processing loop: {e}")
    
    async def _collect_monitoring_data(self) -> Dict[str, Any]:
        """Collect current monitoring data for alert evaluation."""
        data = {
            "timestamp": datetime.now(),
            "phase_manager_status": self.phase_manager.get_current_status(),
            "metrics_summary": {},
            "health_status": {},
            "resource_status": {}
        }
        
        # Get metrics from collector
        try:
            # Phase completion metrics
            for phase in StartupPhase:
                phase_metrics = self.metrics_collector.get_phase_completion_metrics(phase)
                data["metrics_summary"][f"{phase.value}_phase"] = phase_metrics
            
            # Model loading metrics
            model_metrics = self.metrics_collector.get_model_loading_metrics()
            data["metrics_summary"]["model_loading"] = model_metrics
            
            # User wait time metrics
            user_metrics = self.metrics_collector.get_user_wait_time_metrics()
            data["metrics_summary"]["user_experience"] = user_metrics
            
            # Cache performance metrics
            cache_metrics = self.metrics_collector.get_cache_performance_metrics()
            data["metrics_summary"]["cache_performance"] = cache_metrics
            
            # Active user requests
            active_requests = self.metrics_collector.get_active_user_requests()
            data["metrics_summary"]["active_requests"] = active_requests
            
            # Health check latency metrics for GIL contention detection
            health_check_latency_metrics = self.metrics_collector.get_health_check_latency_metrics(
                minutes_back=5  # Look at last 5 minutes of health checks
            )
            data["metrics_summary"]["health_check_latency"] = health_check_latency_metrics
            
        except Exception as e:
            logger.warning(f"Error collecting metrics data: {e}")
            data["metrics_summary"] = {"error": str(e)}
        
        # Health check status
        try:
            current_time = datetime.now()
            if self._last_health_check_time:
                time_since_last_check = (current_time - self._last_health_check_time).total_seconds()
                data["health_status"] = {
                    "last_check_seconds_ago": time_since_last_check,
                    "consecutive_failures": self._consecutive_health_failures,
                    "health_check_timeout": time_since_last_check > 60.0  # No check in 60 seconds
                }
            else:
                data["health_status"] = {
                    "last_check_seconds_ago": None,
                    "consecutive_failures": self._consecutive_health_failures,
                    "health_check_timeout": True
                }
        except Exception as e:
            logger.warning(f"Error collecting health status: {e}")
            data["health_status"] = {"error": str(e)}
        
        return data
    
    async def _handle_rule_trigger(self, rule: AlertRule, monitoring_data: Dict[str, Any]) -> None:
        """Handle when an alert rule is triggered."""
        # Check cooldown
        last_alert_time = self.last_alert_times.get(rule.rule_id)
        if last_alert_time:
            time_since_last = (datetime.now() - last_alert_time).total_seconds()
            if time_since_last < rule.cooldown_seconds:
                return  # Still in cooldown
        
        # Check rate limiting
        current_hour = datetime.now().replace(minute=0, second=0, microsecond=0)
        counter_key = f"{rule.rule_id}_{current_hour.isoformat()}"
        current_count = self.alert_counters.get(counter_key, 0)
        if current_count >= rule.max_alerts_per_hour:
            logger.warning(f"Rate limit reached for alert rule {rule.rule_id}")
            return
        
        # Create alert
        alert = await self._create_alert(rule, monitoring_data)
        
        # Update counters and timestamps
        self.alert_counters[counter_key] = current_count + 1
        self.last_alert_times[rule.rule_id] = datetime.now()
        
        # Queue alert for processing
        await self._alert_queue.put(alert)
        
        logger.warning(f"Alert triggered: {alert.title} (ID: {alert.alert_id})")
    
    async def _create_alert(self, rule: AlertRule, monitoring_data: Dict[str, Any]) -> Alert:
        """Create an alert from a triggered rule."""
        alert_id = f"{rule.rule_id}_{int(time.time())}"
        
        # Extract relevant context based on alert type
        context = await self._extract_alert_context(rule.alert_type, monitoring_data)
        
        # Determine affected resources
        affected_resources = await self._identify_affected_resources(rule.alert_type, monitoring_data)
        
        # Extract relevant metrics
        metrics = await self._extract_alert_metrics(rule.alert_type, monitoring_data)
        
        alert = Alert(
            alert_id=alert_id,
            alert_type=rule.alert_type,
            severity=rule.severity,
            title=f"{rule.name}: {rule.threshold.description}",
            description=await self._generate_alert_description(rule, monitoring_data),
            timestamp=datetime.now(),
            source_component="startup_alerts_service",
            affected_resources=affected_resources,
            metrics=metrics,
            remediation_steps=rule.threshold.remediation_steps.copy(),
            context=context
        )
        
        return alert
    
    async def _extract_alert_context(self, alert_type: AlertType, monitoring_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract relevant context for the alert type."""
        context = {
            "startup_phase": monitoring_data["phase_manager_status"].current_phase.value,
            "startup_duration": (
                datetime.now() - monitoring_data["phase_manager_status"].phase_start_time
            ).total_seconds()
        }
        
        if alert_type == AlertType.PHASE_TIMEOUT:
            context.update({
                "phase_transitions": len(monitoring_data["phase_manager_status"].phase_transitions),
                "models_loaded": sum(
                    1 for status in monitoring_data["phase_manager_status"].model_statuses.values()
                    if status.status == "loaded"
                ),
                "models_failed": sum(
                    1 for status in monitoring_data["phase_manager_status"].model_statuses.values()
                    if status.status == "failed"
                )
            })
        
        elif alert_type == AlertType.MODEL_LOADING_FAILURE:
            failed_models = [
                name for name, status in monitoring_data["phase_manager_status"].model_statuses.items()
                if status.status == "failed"
            ]
            
            timeout_models = []
            timeout_threshold = self.default_thresholds["model_loading_timeout"].threshold_value
            current_time = datetime.now()
            
            for name, status in monitoring_data["phase_manager_status"].model_statuses.items():
                if status.status == "loading" and status.started_at:
                    loading_duration = (current_time - status.started_at).total_seconds()
                    if loading_duration > timeout_threshold:
                        timeout_models.append(name)
            
            essential_failed = [
                name for name, status in monitoring_data["phase_manager_status"].model_statuses.items()
                if status.status == "failed" and status.priority == "essential"
            ]
            
            repeated_failures = [
                name for name, status in monitoring_data["phase_manager_status"].model_statuses.items()
                if status.status == "failed" and hasattr(status, 'retry_count') and status.retry_count >= 3
            ]
            
            context.update({
                "failed_models": failed_models,
                "timeout_models": timeout_models,
                "essential_failed": essential_failed,
                "repeated_failures": repeated_failures,
                "total_models": len(monitoring_data["phase_manager_status"].model_statuses),
                "loading_models": [
                    name for name, status in monitoring_data["phase_manager_status"].model_statuses.items()
                    if status.status == "loading"
                ],
                "loaded_models": [
                    name for name, status in monitoring_data["phase_manager_status"].model_statuses.items()
                    if status.status == "loaded"
                ],
                "model_failure_details": {
                    name: {
                        "priority": getattr(status, 'priority', 'unknown'),
                        "error_message": getattr(status, 'error_message', 'Unknown error'),
                        "retry_count": getattr(status, 'retry_count', 0),
                        "size_mb": getattr(status, 'size_mb', None),
                        "estimated_load_time": getattr(status, 'estimated_load_time_seconds', None)
                    }
                    for name, status in monitoring_data["phase_manager_status"].model_statuses.items()
                    if status.status == "failed"
                }
            })
        
        elif alert_type == AlertType.USER_EXPERIENCE_DEGRADATION:
            active_requests = monitoring_data["metrics_summary"].get("active_requests", {})
            user_metrics = monitoring_data["metrics_summary"].get("user_experience", {})
            
            # Calculate detailed user experience metrics
            wait_time_stats = user_metrics.get("wait_time_stats", {})
            overdue_count = sum(
                1 for req_data in active_requests.values()
                if req_data.get("is_overdue", False)
            )
            
            # Analyze request types and their performance
            request_type_performance = {}
            for req_id, req_data in active_requests.items():
                req_type = req_data.get("request_type", "unknown")
                if req_type not in request_type_performance:
                    request_type_performance[req_type] = {
                        "count": 0,
                        "overdue_count": 0,
                        "avg_wait_time": 0,
                        "fallback_count": 0
                    }
                
                request_type_performance[req_type]["count"] += 1
                if req_data.get("is_overdue", False):
                    request_type_performance[req_type]["overdue_count"] += 1
                if req_data.get("fallback_used", False):
                    request_type_performance[req_type]["fallback_count"] += 1
            
            # Get capability availability status
            capability_availability = user_metrics.get("capability_availability", {})
            unavailable_capabilities = [
                cap for cap, available in capability_availability.items()
                if not available
            ]
            
            context.update({
                "active_user_requests": len(active_requests),
                "overdue_requests": overdue_count,
                "overdue_percentage": (overdue_count / max(len(active_requests), 1)) * 100,
                "fallback_usage_rate": user_metrics.get("fallback_usage_rate", 0),
                "success_rate": user_metrics.get("success_rate", 1.0),
                "timeout_rate": user_metrics.get("timeout_rate", 0),
                "abandonment_rate": user_metrics.get("abandonment_rate", 0),
                "total_requests": user_metrics.get("total_requests", 0),
                "avg_wait_time": wait_time_stats.get("mean_seconds", 0),
                "p95_wait_time": wait_time_stats.get("p95_seconds", 0),
                "p99_wait_time": wait_time_stats.get("p99_seconds", 0),
                "min_wait_time": wait_time_stats.get("min_seconds", 0),
                "max_wait_time": wait_time_stats.get("max_seconds", 0),
                "request_type_performance": request_type_performance,
                "capability_availability": capability_availability,
                "unavailable_capabilities": unavailable_capabilities,
                "essential_capabilities_down": len([
                    cap for cap in unavailable_capabilities
                    if cap in ["chat-model-base", "search-model", "embedding-model"]
                ]),
                "user_experience_score": self._calculate_user_experience_score(user_metrics),
                "degradation_factors": self._identify_degradation_factors(user_metrics, monitoring_data)
            })
        
        elif alert_type == AlertType.CACHE_PERFORMANCE_DEGRADATION:
            cache_metrics = monitoring_data["metrics_summary"].get("cache_performance", {})
            context.update({
                "cache_hit_rate": cache_metrics.get("cache_hit_rate", 0),
                "total_cache_requests": cache_metrics.get("total_model_loads", 0),
                "cache_sources": cache_metrics.get("cache_sources", {})
            })
        
        elif alert_type == AlertType.GIL_CONTENTION:
            health_check_metrics = monitoring_data["metrics_summary"].get("health_check_latency", {})
            latency_stats = health_check_metrics.get("latency_stats", {})
            gil_analysis = health_check_metrics.get("gil_contention_analysis", {})
            model_loading_correlation = health_check_metrics.get("model_loading_correlation", {})
            
            # Get models currently loading
            models_loading = [
                name for name, status in monitoring_data["phase_manager_status"].model_statuses.items()
                if status.status == "loading"
            ]
            
            # Get models associated with slow health checks
            models_causing_contention = gil_analysis.get("models_associated_with_slow_checks", {})
            
            context.update({
                "sample_count": health_check_metrics.get("sample_count", 0),
                "slow_response_rate": health_check_metrics.get("slow_response_rate", 0),
                "elevated_response_rate": health_check_metrics.get("elevated_response_rate", 0),
                "mean_latency_ms": latency_stats.get("mean_ms", 0),
                "max_latency_ms": latency_stats.get("max_ms", 0),
                "p95_latency_ms": latency_stats.get("p95_ms", 0),
                "p99_latency_ms": latency_stats.get("p99_ms", 0),
                "contention_detected": gil_analysis.get("contention_detected", False),
                "total_slow_checks": gil_analysis.get("total_slow_checks", 0),
                "slow_during_model_loading": gil_analysis.get("slow_during_model_loading", 0),
                "loading_correlation_rate": gil_analysis.get("loading_correlation_rate", 0),
                "models_currently_loading": models_loading,
                "models_causing_contention": models_causing_contention,
                "latency_increase_during_loading": model_loading_correlation.get("latency_increase_percent", 0),
                "recommendations": gil_analysis.get("recommendations", []),
                "performance_insights": health_check_metrics.get("performance_insights", [])
            })
        
        return context
    
    async def _identify_affected_resources(self, alert_type: AlertType, monitoring_data: Dict[str, Any]) -> List[str]:
        """Identify resources affected by the alert."""
        resources = ["startup_system"]
        
        if alert_type == AlertType.PHASE_TIMEOUT:
            current_phase = monitoring_data["phase_manager_status"].current_phase.value
            resources.append(f"startup_phase_{current_phase}")
        
        elif alert_type == AlertType.MODEL_LOADING_FAILURE:
            failed_models = [
                name for name, status in monitoring_data["phase_manager_status"].model_statuses.items()
                if status.status == "failed"
            ]
            resources.extend([f"model_{model}" for model in failed_models])
            
            # Add timeout models as affected resources
            timeout_threshold = self.default_thresholds["model_loading_timeout"].threshold_value
            current_time = datetime.now()
            
            for name, status in monitoring_data["phase_manager_status"].model_statuses.items():
                if status.status == "loading" and status.started_at:
                    loading_duration = (current_time - status.started_at).total_seconds()
                    if loading_duration > timeout_threshold:
                        resources.append(f"model_{name}_timeout")
            
            # Add essential models that failed as critical resources
            essential_failed = [
                name for name, status in monitoring_data["phase_manager_status"].model_statuses.items()
                if status.status == "failed" and status.priority == "essential"
            ]
            resources.extend([f"essential_model_{model}" for model in essential_failed])
        
        elif alert_type == AlertType.HEALTH_CHECK_FAILURE:
            resources.extend(["health_endpoints", "ecs_service"])
        
        elif alert_type == AlertType.USER_EXPERIENCE_DEGRADATION:
            resources.extend(["user_requests", "api_endpoints"])
        
        elif alert_type == AlertType.CACHE_PERFORMANCE_DEGRADATION:
            resources.extend(["model_cache", "cache_storage"])
        
        elif alert_type == AlertType.GIL_CONTENTION:
            resources.extend(["event_loop", "health_endpoints", "model_loading"])
            
            # Add specific models causing contention
            health_check_metrics = monitoring_data["metrics_summary"].get("health_check_latency", {})
            gil_analysis = health_check_metrics.get("gil_contention_analysis", {})
            models_causing_contention = gil_analysis.get("models_associated_with_slow_checks", {})
            
            for model_name in models_causing_contention.keys():
                resources.append(f"model_{model_name}_gil_contention")
        
        return resources
    
    async def _extract_alert_metrics(self, alert_type: AlertType, monitoring_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract relevant metrics for the alert."""
        metrics = {
            "timestamp": monitoring_data["timestamp"].isoformat(),
            "startup_phase": monitoring_data["phase_manager_status"].current_phase.value
        }
        
        if alert_type == AlertType.PHASE_TIMEOUT:
            phase_start = monitoring_data["phase_manager_status"].phase_start_time
            current_duration = (datetime.now() - phase_start).total_seconds()
            metrics.update({
                "phase_duration_seconds": current_duration,
                "models_loading": sum(
                    1 for status in monitoring_data["phase_manager_status"].model_statuses.values()
                    if status.status == "loading"
                )
            })
        
        elif alert_type == AlertType.MODEL_LOADING_FAILURE:
            model_metrics = monitoring_data["metrics_summary"].get("model_loading", {})
            failed_models = [
                name for name, status in monitoring_data["phase_manager_status"].model_statuses.items()
                if status.status == "failed"
            ]
            
            # Calculate timeout models
            timeout_models = []
            timeout_threshold = self.default_thresholds["model_loading_timeout"].threshold_value
            current_time = datetime.now()
            
            for name, status in monitoring_data["phase_manager_status"].model_statuses.items():
                if status.status == "loading" and status.started_at:
                    loading_duration = (current_time - status.started_at).total_seconds()
                    if loading_duration > timeout_threshold:
                        timeout_models.append(name)
            
            # Calculate failure rates by priority
            priority_stats = {"essential": {"total": 0, "failed": 0}, "standard": {"total": 0, "failed": 0}, "advanced": {"total": 0, "failed": 0}}
            
            for name, status in monitoring_data["phase_manager_status"].model_statuses.items():
                priority = getattr(status, 'priority', 'standard')
                if priority in priority_stats:
                    priority_stats[priority]["total"] += 1
                    if status.status == "failed":
                        priority_stats[priority]["failed"] += 1
            
            metrics.update({
                "success_rate": model_metrics.get("success_rate", 0),
                "total_loads": model_metrics.get("sample_count", 0),
                "average_duration": model_metrics.get("loading_stats", {}).get("mean_duration_seconds", 0),
                "failed_models_count": len(failed_models),
                "timeout_models_count": len(timeout_models),
                "essential_failure_rate": (
                    priority_stats["essential"]["failed"] / max(priority_stats["essential"]["total"], 1)
                ),
                "standard_failure_rate": (
                    priority_stats["standard"]["failed"] / max(priority_stats["standard"]["total"], 1)
                ),
                "advanced_failure_rate": (
                    priority_stats["advanced"]["failed"] / max(priority_stats["advanced"]["total"], 1)
                ),
                "total_models": len(monitoring_data["phase_manager_status"].model_statuses),
                "models_loaded": sum(
                    1 for status in monitoring_data["phase_manager_status"].model_statuses.values()
                    if status.status == "loaded"
                ),
                "models_loading": sum(
                    1 for status in monitoring_data["phase_manager_status"].model_statuses.values()
                    if status.status == "loading"
                )
            })
        
        elif alert_type == AlertType.USER_EXPERIENCE_DEGRADATION:
            user_metrics = monitoring_data["metrics_summary"].get("user_experience", {})
            metrics.update({
                "average_wait_time": user_metrics.get("wait_time_stats", {}).get("mean_seconds", 0),
                "p95_wait_time": user_metrics.get("wait_time_stats", {}).get("p95_seconds", 0),
                "success_rate": user_metrics.get("success_rate", 0)
            })
        
        elif alert_type == AlertType.CACHE_PERFORMANCE_DEGRADATION:
            cache_metrics = monitoring_data["metrics_summary"].get("cache_performance", {})
            metrics.update({
                "cache_hit_rate": cache_metrics.get("cache_hit_rate", 0),
                "cache_effectiveness": cache_metrics.get("cache_effectiveness", "unknown"),
                "cache_speedup": cache_metrics.get("cache_speedup_factor", 0)
            })
        
        elif alert_type == AlertType.GIL_CONTENTION:
            health_check_metrics = monitoring_data["metrics_summary"].get("health_check_latency", {})
            latency_stats = health_check_metrics.get("latency_stats", {})
            gil_analysis = health_check_metrics.get("gil_contention_analysis", {})
            
            metrics.update({
                "sample_count": health_check_metrics.get("sample_count", 0),
                "slow_response_rate": health_check_metrics.get("slow_response_rate", 0),
                "elevated_response_rate": health_check_metrics.get("elevated_response_rate", 0),
                "mean_latency_ms": latency_stats.get("mean_ms", 0),
                "median_latency_ms": latency_stats.get("median_ms", 0),
                "max_latency_ms": latency_stats.get("max_ms", 0),
                "p95_latency_ms": latency_stats.get("p95_ms", 0),
                "p99_latency_ms": latency_stats.get("p99_ms", 0),
                "total_slow_checks": gil_analysis.get("total_slow_checks", 0),
                "slow_during_model_loading": gil_analysis.get("slow_during_model_loading", 0),
                "loading_correlation_rate": gil_analysis.get("loading_correlation_rate", 0),
                "models_loading_count": sum(
                    1 for status in monitoring_data["phase_manager_status"].model_statuses.values()
                    if status.status == "loading"
                )
            })
        
        return metrics
    
    async def _generate_alert_description(self, rule: AlertRule, monitoring_data: Dict[str, Any]) -> str:
        """Generate a detailed alert description."""
        base_description = rule.description
        
        # Add specific details based on alert type
        if rule.alert_type == AlertType.PHASE_TIMEOUT:
            current_phase = monitoring_data["phase_manager_status"].current_phase.value
            phase_start = monitoring_data["phase_manager_status"].phase_start_time
            duration = (datetime.now() - phase_start).total_seconds()
            threshold = rule.threshold.threshold_value
            
            return (f"{base_description}. Current {current_phase} phase has been running for "
                   f"{duration:.1f} seconds, exceeding the {threshold:.1f} second threshold.")
        
        elif rule.alert_type == AlertType.MODEL_LOADING_FAILURE:
            failed_models = [
                name for name, status in monitoring_data["phase_manager_status"].model_statuses.items()
                if status.status == "failed"
            ]
            
            timeout_models = []
            timeout_threshold = self.default_thresholds["model_loading_timeout"].threshold_value
            current_time = datetime.now()
            
            for name, status in monitoring_data["phase_manager_status"].model_statuses.items():
                if status.status == "loading" and status.started_at:
                    loading_duration = (current_time - status.started_at).total_seconds()
                    if loading_duration > timeout_threshold:
                        timeout_models.append(f"{name} ({loading_duration:.1f}s)")
            
            essential_failed = [
                name for name, status in monitoring_data["phase_manager_status"].model_statuses.items()
                if status.status == "failed" and status.priority == "essential"
            ]
            
            if failed_models and timeout_models:
                return f"{base_description}. Failed models: {', '.join(failed_models)}. Timeout models: {', '.join(timeout_models)}"
            elif failed_models:
                failure_details = []
                for name in failed_models:
                    status = monitoring_data["phase_manager_status"].model_statuses[name]
                    priority = getattr(status, 'priority', 'unknown')
                    error_msg = getattr(status, 'error_message', 'Unknown error')
                    failure_details.append(f"{name} ({priority}): {error_msg}")
                
                if essential_failed:
                    return f"{base_description}. CRITICAL: Essential models failed: {', '.join(essential_failed)}. All failures: {'; '.join(failure_details)}"
                else:
                    return f"{base_description}. Failed models: {'; '.join(failure_details)}"
            elif timeout_models:
                return f"{base_description}. Models taking too long to load: {', '.join(timeout_models)}"
            else:
                return f"{base_description}. Model loading issues detected."
        
        elif rule.alert_type == AlertType.USER_EXPERIENCE_DEGRADATION:
            user_metrics = monitoring_data["metrics_summary"].get("user_experience", {})
            
            # Generate specific description based on rule ID
            if rule.rule_id == "user_p95_wait_time_degradation":
                p95_wait = user_metrics.get("wait_time_stats", {}).get("p95_seconds", 0)
                threshold = rule.threshold.threshold_value
                return (f"{base_description}. P95 user wait time is {p95_wait:.1f} seconds, "
                       f"exceeding the {threshold:.1f} second threshold.")
            
            elif rule.rule_id == "high_fallback_usage":
                fallback_rate = user_metrics.get("fallback_usage_rate", 0)
                threshold = rule.threshold.threshold_value
                total_requests = user_metrics.get("total_requests", 0)
                return (f"{base_description}. Fallback usage rate is {fallback_rate:.1%} "
                       f"(threshold: {threshold:.1%}) across {total_requests} requests.")
            
            elif rule.rule_id == "low_user_success_rate":
                success_rate = user_metrics.get("success_rate", 0)
                threshold = rule.threshold.threshold_value
                total_requests = user_metrics.get("total_requests", 0)
                failed_requests = int(total_requests * (1 - success_rate))
                return (f"{base_description}. Success rate is {success_rate:.1%} "
                       f"(threshold: {threshold:.1%}) with {failed_requests} failed requests.")
            
            elif rule.rule_id == "high_timeout_rate":
                timeout_rate = user_metrics.get("timeout_rate", 0)
                threshold = rule.threshold.threshold_value
                total_requests = user_metrics.get("total_requests", 0)
                timeout_requests = int(total_requests * timeout_rate)
                return (f"{base_description}. Timeout rate is {timeout_rate:.1%} "
                       f"(threshold: {threshold:.1%}) with {timeout_requests} timeout requests.")
            
            elif rule.rule_id == "high_abandonment_rate":
                abandonment_rate = user_metrics.get("abandonment_rate", 0)
                threshold = rule.threshold.threshold_value
                total_requests = user_metrics.get("total_requests", 0)
                abandoned_requests = int(total_requests * abandonment_rate)
                return (f"{base_description}. Abandonment rate is {abandonment_rate:.1%} "
                       f"(threshold: {threshold:.1%}) with {abandoned_requests} abandoned requests.")
            
            elif rule.rule_id == "essential_capability_unavailable":
                capability_availability = user_metrics.get("capability_availability", {})
                unavailable_capabilities = [
                    cap for cap, available in capability_availability.items()
                    if not available and cap in ["chat-model-base", "search-model", "embedding-model"]
                ]
                
                # Also check model statuses
                model_statuses = monitoring_data["phase_manager_status"].model_statuses
                essential_models_down = [
                    name for name, status in model_statuses.items()
                    if status.priority == "essential" and status.status in ["failed", "not_loaded"]
                ]
                
                if unavailable_capabilities and essential_models_down:
                    return (f"{base_description}. Unavailable capabilities: {', '.join(unavailable_capabilities)}. "
                           f"Failed essential models: {', '.join(essential_models_down)}.")
                elif unavailable_capabilities:
                    return f"{base_description}. Unavailable capabilities: {', '.join(unavailable_capabilities)}."
                elif essential_models_down:
                    return f"{base_description}. Failed essential models: {', '.join(essential_models_down)}."
                else:
                    return f"{base_description}. Essential capabilities are unavailable."
            
            else:
                # Default user experience degradation description
                avg_wait = user_metrics.get("wait_time_stats", {}).get("mean_seconds", 0)
                threshold = self.default_thresholds["user_wait_time_threshold"].threshold_value
                return (f"{base_description}. Average user wait time is {avg_wait:.1f} seconds, "
                       f"exceeding the {threshold:.1f} second threshold.")
        
        elif rule.alert_type == AlertType.CACHE_PERFORMANCE_DEGRADATION:
            cache_metrics = monitoring_data["metrics_summary"].get("cache_performance", {})
            hit_rate = cache_metrics.get("cache_hit_rate", 0)
            threshold = rule.threshold.threshold_value
            
            return (f"{base_description}. Cache hit rate is {hit_rate:.1%}, "
                   f"below the {threshold:.1%} threshold.")
        
        elif rule.alert_type == AlertType.GIL_CONTENTION:
            health_check_metrics = monitoring_data["metrics_summary"].get("health_check_latency", {})
            latency_stats = health_check_metrics.get("latency_stats", {})
            gil_analysis = health_check_metrics.get("gil_contention_analysis", {})
            
            # Generate specific description based on rule ID
            if rule.rule_id == "gil_contention_slow_rate":
                slow_rate = health_check_metrics.get("slow_response_rate", 0)
                threshold = rule.threshold.threshold_value
                total_slow = gil_analysis.get("total_slow_checks", 0)
                return (f"{base_description}. {slow_rate:.1%} of health checks are slow (>100ms), "
                       f"exceeding the {threshold:.1%} threshold. Total slow checks: {total_slow}.")
            
            elif rule.rule_id == "gil_contention_extreme_latency":
                max_latency = latency_stats.get("max_ms", 0)
                threshold = rule.threshold.threshold_value
                models_loading = [
                    name for name, status in monitoring_data["phase_manager_status"].model_statuses.items()
                    if status.status == "loading"
                ]
                models_text = f" Models loading: {', '.join(models_loading)}." if models_loading else ""
                return (f"{base_description}. Maximum health check latency is {max_latency:.1f}ms, "
                       f"exceeding the {threshold:.1f}ms threshold.{models_text} "
                       f"This may cause health check timeouts and container restarts.")
            
            elif rule.rule_id == "gil_contention_elevated_latency":
                avg_latency = latency_stats.get("mean_ms", 0)
                threshold = rule.threshold.threshold_value
                return (f"{base_description}. Average health check latency is {avg_latency:.1f}ms, "
                       f"exceeding the {threshold:.1f}ms threshold. "
                       f"Consider using ProcessPoolExecutor for CPU-bound model loading.")
            
            elif rule.rule_id == "gil_contention_model_loading_correlation":
                correlation_rate = gil_analysis.get("loading_correlation_rate", 0)
                threshold = rule.threshold.threshold_value
                models_causing = gil_analysis.get("models_associated_with_slow_checks", {})
                top_models = list(models_causing.keys())[:3]
                models_text = f" Top models causing contention: {', '.join(top_models)}." if top_models else ""
                return (f"{base_description}. {correlation_rate:.1%} of slow health checks occur during model loading, "
                       f"exceeding the {threshold:.1%} threshold.{models_text}")
            
            else:
                # Default GIL contention description
                slow_rate = health_check_metrics.get("slow_response_rate", 0)
                max_latency = latency_stats.get("max_ms", 0)
                return (f"{base_description}. Slow health check rate: {slow_rate:.1%}, "
                       f"max latency: {max_latency:.1f}ms.")
        
        return base_description
    
    async def _process_alert(self, alert: Alert) -> None:
        """Process a triggered alert."""
        try:
            # Add to active alerts
            self.active_alerts[alert.alert_id] = alert
            self.alert_history.append(alert)
            
            # Send notifications
            await self._send_notifications(alert)
            
            # Log alert
            logger.warning(
                f"ALERT [{alert.severity.value.upper()}] {alert.title} - {alert.description}"
            )
            
            # Additional processing based on severity
            if alert.severity == AlertSeverity.CRITICAL:
                await self._handle_critical_alert(alert)
            
        except Exception as e:
            logger.error(f"Error processing alert {alert.alert_id}: {e}")
    
    async def _send_notifications(self, alert: Alert) -> None:
        """Send alert notifications to configured handlers."""
        try:
            for handler in self.notification_handlers:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(alert)
                    else:
                        handler(alert)
                except Exception as e:
                    logger.error(f"Error in notification handler: {e}")
            
            alert.notification_sent = True
            
        except Exception as e:
            logger.error(f"Error sending notifications for alert {alert.alert_id}: {e}")
    
    async def _handle_critical_alert(self, alert: Alert) -> None:
        """Handle critical alerts with additional actions."""
        logger.critical(f"CRITICAL ALERT: {alert.title}")
        
        # For critical startup failures, consider additional actions
        if alert.alert_type == AlertType.STARTUP_FAILURE:
            self._startup_failure_detected = True
            
            # Could trigger additional monitoring or recovery actions here
            logger.critical("Startup failure detected - enhanced monitoring enabled")
    
    async def _check_alert_resolutions(self, monitoring_data: Dict[str, Any]) -> None:
        """Check if any active alerts can be resolved."""
        resolved_alerts = []
        
        for alert_id, alert in self.active_alerts.items():
            if alert.resolved:
                continue
            
            # Find matching rule for this alert type
            matching_rules = [
                rule for rule in self.alert_rules.values()
                if rule.alert_type == alert.alert_type
            ]
            
            # Check if any matching rule's condition is no longer met
            alert_resolved = False
            for rule in matching_rules:
                try:
                    if not rule.condition(monitoring_data):
                        alert_resolved = True
                        break
                except Exception as e:
                    logger.warning(f"Error checking resolution condition for rule {rule.rule_id}: {e}")
            
            if alert_resolved:
                # Alert condition resolved
                alert.resolved = True
                alert.resolved_at = datetime.now()
                alert.resolution_notes = "Alert condition no longer met"
                resolved_alerts.append(alert)
                
                logger.info(f"Alert resolved: {alert.title} (ID: {alert.alert_id})")
        
        # Remove resolved alerts from active list
        for alert in resolved_alerts:
            if alert.alert_id in self.active_alerts:
                del self.active_alerts[alert.alert_id]
    
    async def _cleanup_alert_counters(self) -> None:
        """Clean up old alert counters (older than 1 hour)."""
        current_time = datetime.now()
        cutoff_time = current_time - timedelta(hours=1)
        
        keys_to_remove = []
        for key in self.alert_counters.keys():
            try:
                # Extract timestamp from key
                timestamp_str = key.split('_')[-1]
                timestamp = datetime.fromisoformat(timestamp_str)
                if timestamp < cutoff_time:
                    keys_to_remove.append(key)
            except (ValueError, IndexError):
                # Invalid key format, remove it
                keys_to_remove.append(key)
        
        for key in keys_to_remove:
            del self.alert_counters[key]
    
    # Alert condition checking methods
    def _check_phase_timeout(self, monitoring_data: Dict[str, Any], phase: StartupPhase, threshold: AlertThreshold) -> bool:
        """Check if a startup phase has timed out."""
        current_phase = monitoring_data["phase_manager_status"].current_phase
        if current_phase != phase:
            return False  # Not in this phase
        
        phase_start = monitoring_data["phase_manager_status"].phase_start_time
        current_duration = (datetime.now() - phase_start).total_seconds()
        
        return current_duration > threshold.threshold_value
    
    def _check_model_loading_issues(self, monitoring_data: Dict[str, Any]) -> bool:
        """Check for model loading failures or timeouts."""
        model_statuses = monitoring_data["phase_manager_status"].model_statuses
        
        # Check for failed models
        failed_models = [
            name for name, status in model_statuses.items()
            if status.status == "failed"
        ]
        
        if failed_models:
            return True
        
        # Check for models taking too long to load
        timeout_threshold = self.default_thresholds["model_loading_timeout"].threshold_value
        current_time = datetime.now()
        
        for name, status in model_statuses.items():
            if status.status == "loading" and status.started_at:
                loading_duration = (current_time - status.started_at).total_seconds()
                if loading_duration > timeout_threshold:
                    return True
        
        # Check for critical model failures (essential models that failed)
        essential_failed = [
            name for name, status in model_statuses.items()
            if status.status == "failed" and status.priority == "essential"
        ]
        
        if essential_failed:
            return True
        
        # Check for repeated loading failures (models that have failed multiple times)
        repeated_failures = [
            name for name, status in model_statuses.items()
            if status.status == "failed" and hasattr(status, 'retry_count') and status.retry_count >= 3
        ]
        
        if repeated_failures:
            return True
        
        return False
    
    def _check_essential_model_failures(self, monitoring_data: Dict[str, Any]) -> bool:
        """Check for essential model loading failures."""
        model_statuses = monitoring_data["phase_manager_status"].model_statuses
        
        # Check for failed essential models
        essential_failed = [
            name for name, status in model_statuses.items()
            if status.status == "failed" and status.priority == "essential"
        ]
        
        return len(essential_failed) > 0
    
    def _check_model_loading_timeouts(self, monitoring_data: Dict[str, Any]) -> bool:
        """Check for model loading timeouts (separate from failures)."""
        model_statuses = monitoring_data["phase_manager_status"].model_statuses
        timeout_threshold = self.default_thresholds["model_loading_timeout"].threshold_value
        current_time = datetime.now()
        
        timeout_models = []
        for name, status in model_statuses.items():
            if status.status == "loading" and status.started_at:
                loading_duration = (current_time - status.started_at).total_seconds()
                if loading_duration > timeout_threshold:
                    timeout_models.append(name)
        
        return len(timeout_models) > 0
    
    def _check_repeated_model_failures(self, monitoring_data: Dict[str, Any]) -> bool:
        """Check for models that have failed repeatedly after retries."""
        model_statuses = monitoring_data["phase_manager_status"].model_statuses
        
        repeated_failures = [
            name for name, status in model_statuses.items()
            if status.status == "failed" and hasattr(status, 'retry_count') and status.retry_count >= 3
        ]
        
        return len(repeated_failures) > 0
    
    def _check_health_failures(self, monitoring_data: Dict[str, Any]) -> bool:
        """Check for health check failures."""
        health_status = monitoring_data.get("health_status", {})
        consecutive_failures = health_status.get("consecutive_failures", 0)
        threshold = self.default_thresholds["health_check_failure_threshold"].threshold_value
        
        return consecutive_failures >= threshold
    
    def _check_user_experience_degradation(self, monitoring_data: Dict[str, Any]) -> bool:
        """Check for user experience degradation."""
        user_metrics = monitoring_data["metrics_summary"].get("user_experience", {})
        
        # Check average wait time
        wait_time_stats = user_metrics.get("wait_time_stats", {})
        avg_wait_time = wait_time_stats.get("mean_seconds", 0)
        threshold = self.default_thresholds["user_wait_time_threshold"].threshold_value
        
        if avg_wait_time > threshold:
            return True
        
        # Check P95 wait time (more sensitive to outliers)
        p95_wait_time = wait_time_stats.get("p95_seconds", 0)
        if p95_wait_time > threshold * 2:  # P95 should be within 2x threshold
            return True
        
        # Check for high number of overdue requests
        active_requests = monitoring_data["metrics_summary"].get("active_requests", {})
        overdue_count = sum(
            1 for req_data in active_requests.values()
            if req_data.get("is_overdue", False)
        )
        
        # Alert if more than 50% of active requests are overdue
        if len(active_requests) > 0 and overdue_count / len(active_requests) > 0.5:
            return True
        
        # Check for high fallback usage rate (indicates degraded service)
        fallback_usage_rate = user_metrics.get("fallback_usage_rate", 0)
        if fallback_usage_rate > 0.7:  # More than 70% fallback responses
            return True
        
        # Check for low success rate
        success_rate = user_metrics.get("success_rate", 1.0)
        if success_rate < 0.8:  # Less than 80% success rate
            return True
        
        # Check for request timeout rate
        timeout_rate = user_metrics.get("timeout_rate", 0)
        if timeout_rate > 0.1:  # More than 10% timeouts
            return True
        
        # Check for user abandonment (requests cancelled before completion)
        abandonment_rate = user_metrics.get("abandonment_rate", 0)
        if abandonment_rate > 0.2:  # More than 20% abandonment
            return True
        
        # Check for capability unavailability affecting users
        capability_availability = user_metrics.get("capability_availability", {})
        essential_capabilities_down = sum(
            1 for capability, available in capability_availability.items()
            if capability in ["chat-model-base", "search-model", "embedding-model"] and not available
        )
        if essential_capabilities_down > 0:
            return True
        
        return False
    
    def _check_p95_wait_time_degradation(self, monitoring_data: Dict[str, Any]) -> bool:
        """Check for P95 wait time degradation."""
        user_metrics = monitoring_data["metrics_summary"].get("user_experience", {})
        wait_time_stats = user_metrics.get("wait_time_stats", {})
        p95_wait_time = wait_time_stats.get("p95_seconds", 0)
        threshold = self.default_thresholds["user_p95_wait_time_threshold"].threshold_value
        
        return p95_wait_time > threshold
    
    def _check_high_fallback_usage(self, monitoring_data: Dict[str, Any]) -> bool:
        """Check for high fallback response usage."""
        user_metrics = monitoring_data["metrics_summary"].get("user_experience", {})
        fallback_usage_rate = user_metrics.get("fallback_usage_rate", 0)
        threshold = self.default_thresholds["high_fallback_usage_threshold"].threshold_value
        
        # Only alert if we have meaningful data (at least 10 requests)
        total_requests = user_metrics.get("total_requests", 0)
        if total_requests < 10:
            return False
        
        return fallback_usage_rate > threshold
    
    def _check_low_success_rate(self, monitoring_data: Dict[str, Any]) -> bool:
        """Check for low user request success rate."""
        user_metrics = monitoring_data["metrics_summary"].get("user_experience", {})
        success_rate = user_metrics.get("success_rate", 1.0)
        threshold = self.default_thresholds["low_success_rate_threshold"].threshold_value
        
        # Only alert if we have meaningful data (at least 5 requests)
        total_requests = user_metrics.get("total_requests", 0)
        if total_requests < 5:
            return False
        
        return success_rate < threshold
    
    def _check_high_timeout_rate(self, monitoring_data: Dict[str, Any]) -> bool:
        """Check for high request timeout rate."""
        user_metrics = monitoring_data["metrics_summary"].get("user_experience", {})
        timeout_rate = user_metrics.get("timeout_rate", 0)
        threshold = self.default_thresholds["high_timeout_rate_threshold"].threshold_value
        
        # Only alert if we have meaningful data (at least 10 requests)
        total_requests = user_metrics.get("total_requests", 0)
        if total_requests < 10:
            return False
        
        return timeout_rate > threshold
    
    def _check_high_abandonment_rate(self, monitoring_data: Dict[str, Any]) -> bool:
        """Check for high user request abandonment rate."""
        user_metrics = monitoring_data["metrics_summary"].get("user_experience", {})
        abandonment_rate = user_metrics.get("abandonment_rate", 0)
        threshold = self.default_thresholds["high_abandonment_rate_threshold"].threshold_value
        
        # Only alert if we have meaningful data (at least 10 requests)
        total_requests = user_metrics.get("total_requests", 0)
        if total_requests < 10:
            return False
        
        return abandonment_rate > threshold
    
    def _check_essential_capability_unavailable(self, monitoring_data: Dict[str, Any]) -> bool:
        """Check for essential capabilities being unavailable."""
        user_metrics = monitoring_data["metrics_summary"].get("user_experience", {})
        capability_availability = user_metrics.get("capability_availability", {})
        
        # Define essential capabilities that must be available
        essential_capabilities = [
            "chat-model-base",
            "search-model", 
            "embedding-model"
        ]
        
        # Check if any essential capability is unavailable
        for capability in essential_capabilities:
            if capability in capability_availability and not capability_availability[capability]:
                return True
        
        # Also check model statuses directly
        model_statuses = monitoring_data["phase_manager_status"].model_statuses
        essential_models_down = [
            name for name, status in model_statuses.items()
            if status.priority == "essential" and status.status in ["failed", "not_loaded"]
        ]
        
        return len(essential_models_down) > 0
    
    def _calculate_user_experience_score(self, user_metrics: Dict[str, Any]) -> float:
        """Calculate a user experience score from 0-100 based on various metrics."""
        score = 100.0
        
        # Deduct points for high wait times
        wait_time_stats = user_metrics.get("wait_time_stats", {})
        avg_wait_time = wait_time_stats.get("mean_seconds", 0)
        if avg_wait_time > 10:
            score -= min(30, (avg_wait_time - 10) * 2)  # Max 30 points deduction
        
        # Deduct points for low success rate
        success_rate = user_metrics.get("success_rate", 1.0)
        score -= (1.0 - success_rate) * 40  # Max 40 points deduction
        
        # Deduct points for high fallback usage
        fallback_rate = user_metrics.get("fallback_usage_rate", 0)
        score -= fallback_rate * 20  # Max 20 points deduction
        
        # Deduct points for high timeout rate
        timeout_rate = user_metrics.get("timeout_rate", 0)
        score -= timeout_rate * 30  # Max 30 points deduction
        
        # Deduct points for high abandonment rate
        abandonment_rate = user_metrics.get("abandonment_rate", 0)
        score -= abandonment_rate * 25  # Max 25 points deduction
        
        return max(0.0, score)
    
    def _identify_degradation_factors(self, user_metrics: Dict[str, Any], 
                                    monitoring_data: Dict[str, Any]) -> List[str]:
        """Identify specific factors contributing to user experience degradation."""
        factors = []
        
        # Check wait time factors
        wait_time_stats = user_metrics.get("wait_time_stats", {})
        avg_wait_time = wait_time_stats.get("mean_seconds", 0)
        p95_wait_time = wait_time_stats.get("p95_seconds", 0)
        
        if avg_wait_time > 30:
            factors.append(f"High average wait time ({avg_wait_time:.1f}s)")
        if p95_wait_time > 60:
            factors.append(f"Excessive P95 wait time ({p95_wait_time:.1f}s)")
        
        # Check success rate factors
        success_rate = user_metrics.get("success_rate", 1.0)
        if success_rate < 0.9:
            factors.append(f"Low success rate ({success_rate:.1%})")
        
        # Check fallback usage factors
        fallback_rate = user_metrics.get("fallback_usage_rate", 0)
        if fallback_rate > 0.5:
            factors.append(f"High fallback usage ({fallback_rate:.1%})")
        
        # Check timeout factors
        timeout_rate = user_metrics.get("timeout_rate", 0)
        if timeout_rate > 0.05:
            factors.append(f"High timeout rate ({timeout_rate:.1%})")
        
        # Check abandonment factors
        abandonment_rate = user_metrics.get("abandonment_rate", 0)
        if abandonment_rate > 0.1:
            factors.append(f"High abandonment rate ({abandonment_rate:.1%})")
        
        # Check model loading factors
        model_statuses = monitoring_data["phase_manager_status"].model_statuses
        failed_essential_models = [
            name for name, status in model_statuses.items()
            if status.priority == "essential" and status.status == "failed"
        ]
        if failed_essential_models:
            factors.append(f"Essential models failed: {', '.join(failed_essential_models)}")
        
        loading_essential_models = [
            name for name, status in model_statuses.items()
            if status.priority == "essential" and status.status == "loading"
        ]
        if loading_essential_models:
            factors.append(f"Essential models still loading: {', '.join(loading_essential_models)}")
        
        # Check startup phase factors
        current_phase = monitoring_data["phase_manager_status"].current_phase
        if current_phase.value == "minimal":
            factors.append("Still in minimal startup phase")
        elif current_phase.value == "essential":
            factors.append("Still in essential startup phase")
        
        # Check capability availability factors
        capability_availability = user_metrics.get("capability_availability", {})
        unavailable_essential = [
            cap for cap, available in capability_availability.items()
            if not available and cap in ["chat-model-base", "search-model", "embedding-model"]
        ]
        if unavailable_essential:
            factors.append(f"Essential capabilities unavailable: {', '.join(unavailable_essential)}")
        
        return factors
    
    def _check_cache_performance(self, monitoring_data: Dict[str, Any]) -> bool:
        """Check for cache performance degradation."""
        cache_metrics = monitoring_data["metrics_summary"].get("cache_performance", {})
        hit_rate = cache_metrics.get("cache_hit_rate", 1.0)  # Default to 100% if no data
        threshold = self.default_thresholds["cache_hit_rate_minimum"].threshold_value
        
        # Only alert if we have meaningful data (at least 5 cache requests)
        total_requests = cache_metrics.get("total_model_loads", 0)
        if total_requests < 5:
            return False
        
        return hit_rate < threshold
    
    def _check_startup_failures(self, monitoring_data: Dict[str, Any]) -> bool:
        """Check for high startup failure rate."""
        # This would typically check historical data
        # For now, check if we've detected a startup failure
        return self._startup_failure_detected
    
    # GIL contention detection methods
    def _check_gil_contention_slow_rate(self, monitoring_data: Dict[str, Any]) -> bool:
        """
        Check for high rate of slow health checks indicating GIL contention.
        
        Returns True if more than 10% of recent health checks are slow (>100ms).
        """
        health_check_metrics = monitoring_data["metrics_summary"].get("health_check_latency", {})
        
        # Need at least 5 health checks to make a determination
        sample_count = health_check_metrics.get("sample_count", 0)
        if sample_count < 5:
            return False
        
        slow_rate = health_check_metrics.get("slow_response_rate", 0)
        threshold = self.default_thresholds["gil_contention_slow_rate_threshold"].threshold_value
        
        return slow_rate > threshold
    
    def _check_gil_contention_extreme_latency(self, monitoring_data: Dict[str, Any]) -> bool:
        """
        Check for extreme health check latency indicating severe GIL contention.
        
        Returns True if any recent health check exceeded 500ms.
        """
        health_check_metrics = monitoring_data["metrics_summary"].get("health_check_latency", {})
        
        # Check if we have latency stats
        latency_stats = health_check_metrics.get("latency_stats", {})
        if not latency_stats:
            return False
        
        max_latency = latency_stats.get("max_ms", 0)
        threshold = self.default_thresholds["gil_contention_max_latency_threshold"].threshold_value
        
        return max_latency > threshold
    
    def _check_gil_contention_elevated_latency(self, monitoring_data: Dict[str, Any]) -> bool:
        """
        Check for elevated average health check latency.
        
        Returns True if average health check latency exceeds 50ms.
        """
        health_check_metrics = monitoring_data["metrics_summary"].get("health_check_latency", {})
        
        # Need at least 10 health checks for average to be meaningful
        sample_count = health_check_metrics.get("sample_count", 0)
        if sample_count < 10:
            return False
        
        latency_stats = health_check_metrics.get("latency_stats", {})
        if not latency_stats:
            return False
        
        avg_latency = latency_stats.get("mean_ms", 0)
        threshold = self.default_thresholds["gil_contention_avg_latency_threshold"].threshold_value
        
        return avg_latency > threshold
    
    def _check_gil_contention_loading_correlation(self, monitoring_data: Dict[str, Any]) -> bool:
        """
        Check for strong correlation between model loading and slow health checks.
        
        Returns True if more than 80% of slow health checks occur during model loading.
        """
        health_check_metrics = monitoring_data["metrics_summary"].get("health_check_latency", {})
        
        # Check GIL contention analysis if available
        gil_analysis = health_check_metrics.get("gil_contention_analysis", {})
        if not gil_analysis:
            return False
        
        # Check if contention was detected
        if not gil_analysis.get("contention_detected", False):
            return False
        
        # Check loading correlation rate
        loading_correlation = gil_analysis.get("loading_correlation_rate", 0)
        threshold = self.default_thresholds["gil_contention_loading_correlation_threshold"].threshold_value
        
        # Also need at least 3 slow checks to be meaningful
        total_slow_checks = gil_analysis.get("total_slow_checks", 0)
        if total_slow_checks < 3:
            return False
        
        return loading_correlation > threshold

    # Public interface methods
    def add_notification_handler(self, handler: Callable[[Alert], None]) -> None:
        """Add a notification handler for alerts."""
        self.notification_handlers.append(handler)
        logger.info(f"Added notification handler: {handler.__name__}")
    
    def remove_notification_handler(self, handler: Callable[[Alert], None]) -> None:
        """Remove a notification handler."""
        if handler in self.notification_handlers:
            self.notification_handlers.remove(handler)
            logger.info(f"Removed notification handler: {handler.__name__}")
    
    def update_threshold(self, threshold_name: str, new_value: float) -> None:
        """Update an alert threshold value."""
        if threshold_name in self.default_thresholds:
            old_value = self.default_thresholds[threshold_name].threshold_value
            self.default_thresholds[threshold_name].threshold_value = new_value
            logger.info(f"Updated threshold {threshold_name}: {old_value} -> {new_value}")
        else:
            logger.warning(f"Unknown threshold: {threshold_name}")
    
    def enable_rule(self, rule_id: str) -> None:
        """Enable an alert rule."""
        if rule_id in self.alert_rules:
            self.alert_rules[rule_id].enabled = True
            logger.info(f"Enabled alert rule: {rule_id}")
        else:
            logger.warning(f"Unknown alert rule: {rule_id}")
    
    def disable_rule(self, rule_id: str) -> None:
        """Disable an alert rule."""
        if rule_id in self.alert_rules:
            self.alert_rules[rule_id].enabled = False
            logger.info(f"Disabled alert rule: {rule_id}")
        else:
            logger.warning(f"Unknown alert rule: {rule_id}")
    
    def get_active_alerts(self) -> List[Alert]:
        """Get all currently active alerts."""
        return list(self.active_alerts.values())
    
    def get_alert_history(self, hours: int = 24) -> List[Alert]:
        """Get alert history for the specified number of hours."""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        return [
            alert for alert in self.alert_history
            if alert.timestamp >= cutoff_time
        ]
    
    def get_alert_summary(self) -> Dict[str, Any]:
        """Get a summary of alert status."""
        active_count = len(self.active_alerts)
        recent_alerts = self.get_alert_history(24)
        
        severity_counts = {}
        for severity in AlertSeverity:
            severity_counts[severity.value] = sum(
                1 for alert in recent_alerts
                if alert.severity == severity
            )
        
        type_counts = {}
        for alert_type in AlertType:
            type_counts[alert_type.value] = sum(
                1 for alert in recent_alerts
                if alert.alert_type == alert_type
            )
        
        return {
            "active_alerts": active_count,
            "alerts_last_24h": len(recent_alerts),
            "severity_breakdown": severity_counts,
            "type_breakdown": type_counts,
            "monitoring_active": self._is_monitoring,
            "rules_enabled": sum(1 for rule in self.alert_rules.values() if rule.enabled),
            "total_rules": len(self.alert_rules)
        }
    
    async def record_health_check_result(self, success: bool, response_time_ms: Optional[float] = None) -> None:
        """Record a health check result for monitoring and latency tracking."""
        self._last_health_check_time = datetime.now()
        
        if success:
            self._consecutive_health_failures = 0
        else:
            self._consecutive_health_failures += 1
            logger.warning(f"Health check failed (consecutive failures: {self._consecutive_health_failures})")
        
        # Record latency metrics if response time is provided
        if response_time_ms is not None and self.metrics_collector:
            try:
                await self.metrics_collector.record_health_check_latency(
                    response_time_ms=response_time_ms,
                    success=success,
                    endpoint="/health/minimal",  # Default endpoint
                    error_message=None if success else "Health check failed"
                )
            except Exception as e:
                logger.warning(f"Failed to record health check latency metric: {e}")
    
    async def record_startup_failure(self, error_message: str, context: Dict[str, Any] = None) -> None:
        """Record a startup failure for monitoring."""
        self._startup_failure_detected = True
        logger.error(f"Startup failure recorded: {error_message}")
        
        # Could trigger immediate alert here if needed
        if context is None:
            context = {}
        
        context.update({
            "error_message": error_message,
            "timestamp": datetime.now().isoformat()
        })
    
    async def record_model_loading_failure(self, model_name: str, error_message: str, 
                                         priority: str = "standard", retry_count: int = 0,
                                         context: Dict[str, Any] = None) -> None:
        """Record a model loading failure for immediate alerting."""
        logger.error(f"Model loading failure recorded: {model_name} - {error_message}")
        
        # Create immediate alert for critical model failures
        if priority == "essential" or retry_count >= 3:
            alert_data = {
                "timestamp": datetime.now(),
                "phase_manager_status": self.phase_manager.get_current_status(),
                "model_failure": {
                    "model_name": model_name,
                    "error_message": error_message,
                    "priority": priority,
                    "retry_count": retry_count,
                    "context": context or {}
                }
            }
            
            # Find appropriate rule for this failure type
            rule_id = "essential_model_failure" if priority == "essential" else "repeated_model_failures"
            if rule_id in self.alert_rules:
                rule = self.alert_rules[rule_id]
                alert = await self._create_model_failure_alert(rule, alert_data)
                await self._alert_queue.put(alert)
    
    async def _create_model_failure_alert(self, rule: AlertRule, alert_data: Dict[str, Any]) -> Alert:
        """Create a specific alert for model loading failures."""
        alert_id = f"{rule.rule_id}_{alert_data['model_failure']['model_name']}_{int(time.time())}"
        
        model_failure = alert_data["model_failure"]
        model_name = model_failure["model_name"]
        error_message = model_failure["error_message"]
        priority = model_failure["priority"]
        retry_count = model_failure["retry_count"]
        
        # Generate specific remediation steps based on failure type
        remediation_steps = self._generate_model_failure_remediation(
            model_name, error_message, priority, retry_count
        )
        
        # Create detailed description
        if priority == "essential":
            title = f"CRITICAL: Essential Model Loading Failure - {model_name}"
            description = (f"Essential model '{model_name}' failed to load, which will severely impact "
                         f"application functionality. Error: {error_message}")
        elif retry_count >= 3:
            title = f"Repeated Model Loading Failure - {model_name}"
            description = (f"Model '{model_name}' has failed to load {retry_count} times. "
                         f"Latest error: {error_message}")
        else:
            title = f"Model Loading Failure - {model_name}"
            description = f"Model '{model_name}' failed to load. Error: {error_message}"
        
        alert = Alert(
            alert_id=alert_id,
            alert_type=rule.alert_type,
            severity=rule.severity,
            title=title,
            description=description,
            timestamp=datetime.now(),
            source_component="startup_alerts_service",
            affected_resources=[f"model_{model_name}"],
            metrics={
                "model_name": model_name,
                "priority": priority,
                "retry_count": retry_count,
                "error_type": self._classify_model_error(error_message)
            },
            remediation_steps=remediation_steps,
            context={
                "model_failure": model_failure,
                "startup_phase": alert_data["phase_manager_status"].current_phase.value
            }
        )
        
        return alert
    
    def _generate_model_failure_remediation(self, model_name: str, error_message: str, 
                                          priority: str, retry_count: int) -> List[str]:
        """Generate specific remediation steps based on model failure details."""
        base_steps = [
            f"Check application logs for detailed error information about {model_name}",
            "Verify model file integrity and availability",
            "Check available memory and storage space",
            "Review model configuration and paths"
        ]
        
        # Add specific steps based on error type
        error_type = self._classify_model_error(error_message)
        
        if error_type == "memory":
            base_steps.extend([
                "Increase container memory allocation",
                "Consider model compression or quantization",
                "Review memory usage patterns of other models",
                "Implement model unloading for unused models"
            ])
        elif error_type == "network":
            base_steps.extend([
                "Check network connectivity to model storage",
                "Verify VPC endpoints and security groups",
                "Review download timeouts and retry policies",
                "Consider using local model cache"
            ])
        elif error_type == "storage":
            base_steps.extend([
                "Check available disk space",
                "Verify EFS/S3 connectivity and permissions",
                "Review storage performance metrics",
                "Clean up old cached models if needed"
            ])
        elif error_type == "corruption":
            base_steps.extend([
                "Re-download model files from source",
                "Verify model file checksums",
                "Clear model cache and retry",
                "Check for storage corruption issues"
            ])
        
        # Add priority-specific steps
        if priority == "essential":
            base_steps.extend([
                "URGENT: Consider rolling back to previous version",
                "Activate fallback models if available",
                "Scale down non-essential services to free resources",
                "Contact on-call engineer immediately"
            ])
        
        # Add retry-specific steps
        if retry_count >= 3:
            base_steps.extend([
                "Stop automatic retries to prevent resource waste",
                "Investigate root cause before manual retry",
                "Consider disabling this model temporarily",
                "Review model loading strategy and dependencies"
            ])
        
        return base_steps
    
    def _classify_model_error(self, error_message: str) -> str:
        """Classify the type of model loading error for targeted remediation."""
        error_lower = error_message.lower()
        
        if any(keyword in error_lower for keyword in ["memory", "oom", "out of memory", "allocation"]):
            return "memory"
        elif any(keyword in error_lower for keyword in ["network", "connection", "timeout", "download"]):
            return "network"
        elif any(keyword in error_lower for keyword in ["disk", "storage", "space", "permission"]):
            return "storage"
        elif any(keyword in error_lower for keyword in ["corrupt", "invalid", "checksum", "format"]):
            return "corruption"
        elif any(keyword in error_lower for keyword in ["config", "path", "not found", "missing"]):
            return "configuration"
        else:
            return "unknown"
    
    def get_model_failure_summary(self) -> Dict[str, Any]:
        """Get a summary of model loading failures."""
        if not hasattr(self.phase_manager, 'get_current_status'):
            return {"error": "Phase manager not available"}
        
        try:
            status = self.phase_manager.get_current_status()
            model_statuses = status.model_statuses
            
            failed_models = [
                name for name, status in model_statuses.items()
                if status.status == "failed"
            ]
            
            essential_failed = [
                name for name, status in model_statuses.items()
                if status.status == "failed" and status.priority == "essential"
            ]
            
            repeated_failures = [
                name for name, status in model_statuses.items()
                if status.status == "failed" and hasattr(status, 'retry_count') and status.retry_count >= 3
            ]
            
            failure_details = {}
            for name in failed_models:
                model_status = model_statuses[name]
                failure_details[name] = {
                    "priority": getattr(model_status, 'priority', 'unknown'),
                    "error_message": getattr(model_status, 'error_message', 'Unknown error'),
                    "retry_count": getattr(model_status, 'retry_count', 0),
                    "error_type": self._classify_model_error(getattr(model_status, 'error_message', '')),
                    "started_at": getattr(model_status, 'started_at', None),
                    "size_mb": getattr(model_status, 'size_mb', None)
                }
            
            return {
                "total_models": len(model_statuses),
                "failed_count": len(failed_models),
                "essential_failed_count": len(essential_failed),
                "repeated_failures_count": len(repeated_failures),
                "failed_models": failed_models,
                "essential_failed": essential_failed,
                "repeated_failures": repeated_failures,
                "failure_details": failure_details,
                "current_phase": status.current_phase.value,
                "models_loaded": sum(1 for s in model_statuses.values() if s.status == "loaded"),
                "models_loading": sum(1 for s in model_statuses.values() if s.status == "loading")
            }
        except Exception as e:
            logger.error(f"Error generating model failure summary: {e}")
            return {"error": str(e)}
    
    async def record_user_experience_degradation(self, degradation_type: str, severity: str = "medium",
                                               user_metrics: Dict[str, Any] = None,
                                               context: Dict[str, Any] = None) -> None:
        """Record a user experience degradation event for immediate alerting."""
        logger.warning(f"User experience degradation recorded: {degradation_type} (severity: {severity})")
        
        # Create immediate alert for critical UX degradation
        if severity in ["high", "critical"]:
            alert_data = {
                "timestamp": datetime.now(),
                "phase_manager_status": self.phase_manager.get_current_status(),
                "user_experience_degradation": {
                    "degradation_type": degradation_type,
                    "severity": severity,
                    "user_metrics": user_metrics or {},
                    "context": context or {}
                }
            }
            
            # Find appropriate rule for this degradation type
            rule_mapping = {
                "high_wait_time": "user_experience_degradation",
                "p95_wait_time": "user_p95_wait_time_degradation",
                "high_fallback_usage": "high_fallback_usage",
                "low_success_rate": "low_user_success_rate",
                "high_timeout_rate": "high_timeout_rate",
                "high_abandonment": "high_abandonment_rate",
                "capability_unavailable": "essential_capability_unavailable"
            }
            
            rule_id = rule_mapping.get(degradation_type, "user_experience_degradation")
            if rule_id in self.alert_rules:
                rule = self.alert_rules[rule_id]
                alert = await self._create_user_experience_alert(rule, alert_data)
                await self._alert_queue.put(alert)
    
    async def _create_user_experience_alert(self, rule: AlertRule, alert_data: Dict[str, Any]) -> Alert:
        """Create a specific alert for user experience degradation."""
        alert_id = f"{rule.rule_id}_{alert_data['user_experience_degradation']['degradation_type']}_{int(time.time())}"
        
        ux_degradation = alert_data["user_experience_degradation"]
        degradation_type = ux_degradation["degradation_type"]
        severity_level = ux_degradation["severity"]
        user_metrics = ux_degradation["user_metrics"]
        
        # Generate specific remediation steps based on degradation type
        remediation_steps = self._generate_ux_degradation_remediation(
            degradation_type, user_metrics, severity_level
        )
        
        # Create detailed description
        if degradation_type == "capability_unavailable":
            title = f"CRITICAL: Essential Capabilities Unavailable"
            description = (f"Essential user capabilities are unavailable, severely impacting user experience. "
                         f"Users cannot access core functionality.")
        elif degradation_type == "high_wait_time":
            avg_wait = user_metrics.get("wait_time_stats", {}).get("mean_seconds", 0)
            title = f"High User Wait Times - {avg_wait:.1f}s average"
            description = (f"Users are experiencing excessive wait times averaging {avg_wait:.1f} seconds, "
                         f"significantly impacting user experience.")
        elif degradation_type == "low_success_rate":
            success_rate = user_metrics.get("success_rate", 0)
            title = f"Low Request Success Rate - {success_rate:.1%}"
            description = (f"User request success rate has dropped to {success_rate:.1%}, "
                         f"indicating system reliability issues.")
        elif degradation_type == "high_fallback_usage":
            fallback_rate = user_metrics.get("fallback_usage_rate", 0)
            title = f"High Fallback Usage - {fallback_rate:.1%}"
            description = (f"Fallback responses are being used for {fallback_rate:.1%} of requests, "
                         f"indicating degraded service quality.")
        else:
            title = f"User Experience Degradation - {degradation_type}"
            description = f"User experience degradation detected: {degradation_type}"
        
        alert = Alert(
            alert_id=alert_id,
            alert_type=rule.alert_type,
            severity=AlertSeverity.CRITICAL if severity_level == "critical" else rule.severity,
            title=title,
            description=description,
            timestamp=datetime.now(),
            source_component="startup_alerts_service",
            affected_resources=["user_experience", "api_endpoints"],
            metrics={
                "degradation_type": degradation_type,
                "severity_level": severity_level,
                "user_experience_score": self._calculate_user_experience_score(user_metrics),
                **user_metrics
            },
            remediation_steps=remediation_steps,
            context={
                "user_experience_degradation": ux_degradation,
                "startup_phase": alert_data["phase_manager_status"].current_phase.value,
                "degradation_factors": self._identify_degradation_factors(user_metrics, alert_data)
            }
        )
        
        return alert
    
    def _generate_ux_degradation_remediation(self, degradation_type: str, user_metrics: Dict[str, Any],
                                           severity_level: str) -> List[str]:
        """Generate specific remediation steps based on UX degradation type."""
        base_steps = [
            f"Investigate {degradation_type} degradation immediately",
            "Check application and infrastructure logs",
            "Verify system resource availability",
            "Review recent deployments or changes"
        ]
        
        # Add specific steps based on degradation type
        if degradation_type == "high_wait_time":
            base_steps.extend([
                "Check model loading progress and bottlenecks",
                "Verify startup phase progression",
                "Review request queuing and processing",
                "Consider scaling resources or optimizing models",
                "Improve loading state communication to users"
            ])
        elif degradation_type == "low_success_rate":
            base_steps.extend([
                "Check error logs for common failure patterns",
                "Verify service dependencies and connectivity",
                "Review model loading failures",
                "Check resource exhaustion (memory, CPU, disk)",
                "Validate configuration and environment variables"
            ])
        elif degradation_type == "high_fallback_usage":
            base_steps.extend([
                "Accelerate essential model loading",
                "Check model loading failures and retries",
                "Verify model cache performance",
                "Review fallback response quality",
                "Consider temporary resource scaling"
            ])
        elif degradation_type == "capability_unavailable":
            base_steps.extend([
                "URGENT: Check essential model status immediately",
                "Restart failed model loading processes",
                "Verify model file integrity and availability",
                "Consider emergency fallback to backup models",
                "Scale resources if needed for model loading",
                "Contact on-call engineer if issue persists"
            ])
        elif degradation_type == "high_timeout_rate":
            base_steps.extend([
                "Review request timeout configurations",
                "Check for slow model responses",
                "Verify network connectivity and latency",
                "Review resource performance metrics",
                "Consider request optimization or caching"
            ])
        elif degradation_type == "high_abandonment":
            base_steps.extend([
                "Improve user communication about wait times",
                "Enhance progress indicators and loading states",
                "Reduce actual processing times",
                "Review user experience design",
                "Consider implementing request prioritization"
            ])
        
        # Add severity-specific steps
        if severity_level == "critical":
            base_steps.insert(0, "CRITICAL: This issue is severely impacting users")
            base_steps.extend([
                "Consider emergency rollback if recent deployment",
                "Activate incident response procedures",
                "Notify stakeholders immediately",
                "Prepare communication for affected users"
            ])
        
        return base_steps
    
    def get_user_experience_summary(self) -> Dict[str, Any]:
        """Get a comprehensive summary of user experience metrics and alerts."""
        try:
            # Get recent UX-related alerts
            recent_alerts = self.get_alert_history(24)
            ux_alerts = [
                alert for alert in recent_alerts
                if alert.alert_type == AlertType.USER_EXPERIENCE_DEGRADATION
            ]
            
            # Categorize UX alerts by type
            ux_alert_types = {}
            for alert in ux_alerts:
                degradation_type = alert.metrics.get("degradation_type", "unknown")
                if degradation_type not in ux_alert_types:
                    ux_alert_types[degradation_type] = []
                ux_alert_types[degradation_type].append(alert)
            
            # Get current active UX alerts
            active_ux_alerts = [
                alert for alert in self.active_alerts.values()
                if alert.alert_type == AlertType.USER_EXPERIENCE_DEGRADATION
            ]
            
            # Calculate UX health score based on recent alerts
            ux_health_score = 100.0
            for alert in ux_alerts:
                severity_impact = {
                    AlertSeverity.LOW: 5,
                    AlertSeverity.MEDIUM: 15,
                    AlertSeverity.HIGH: 30,
                    AlertSeverity.CRITICAL: 50
                }
                ux_health_score -= severity_impact.get(alert.severity, 10)
            
            ux_health_score = max(0.0, ux_health_score)
            
            return {
                "ux_health_score": ux_health_score,
                "active_ux_alerts": len(active_ux_alerts),
                "ux_alerts_last_24h": len(ux_alerts),
                "ux_alert_types": {
                    alert_type: len(alerts) for alert_type, alerts in ux_alert_types.items()
                },
                "critical_ux_issues": len([
                    alert for alert in active_ux_alerts
                    if alert.severity == AlertSeverity.CRITICAL
                ]),
                "most_common_ux_issue": max(ux_alert_types.keys(), key=lambda k: len(ux_alert_types[k])) if ux_alert_types else None,
                "ux_trend": self._calculate_ux_trend(ux_alerts),
                "recommendations": self._generate_ux_recommendations(ux_alerts, active_ux_alerts)
            }
        except Exception as e:
            logger.error(f"Error generating user experience summary: {e}")
            return {"error": str(e)}
    
    def _calculate_ux_trend(self, ux_alerts: List[Alert]) -> str:
        """Calculate the trend in user experience based on recent alerts."""
        if not ux_alerts:
            return "stable"
        
        # Sort alerts by timestamp
        sorted_alerts = sorted(ux_alerts, key=lambda a: a.timestamp)
        
        # Compare first half vs second half
        mid_point = len(sorted_alerts) // 2
        if mid_point == 0:
            return "stable"
        
        first_half_severity = sum(
            alert.severity.value == "critical" and 4 or
            alert.severity.value == "high" and 3 or
            alert.severity.value == "medium" and 2 or 1
            for alert in sorted_alerts[:mid_point]
        )
        
        second_half_severity = sum(
            alert.severity.value == "critical" and 4 or
            alert.severity.value == "high" and 3 or
            alert.severity.value == "medium" and 2 or 1
            for alert in sorted_alerts[mid_point:]
        )
        
        if second_half_severity > first_half_severity * 1.5:
            return "degrading"
        elif first_half_severity > second_half_severity * 1.5:
            return "improving"
        else:
            return "stable"
    
    def _generate_ux_recommendations(self, ux_alerts: List[Alert], active_ux_alerts: List[Alert]) -> List[str]:
        """Generate recommendations based on UX alert patterns."""
        recommendations = []
        
        if not ux_alerts and not active_ux_alerts:
            recommendations.append("User experience is currently stable")
            return recommendations
        
        # Analyze alert patterns
        alert_types = {}
        for alert in ux_alerts:
            degradation_type = alert.metrics.get("degradation_type", "unknown")
            alert_types[degradation_type] = alert_types.get(degradation_type, 0) + 1
        
        # Generate specific recommendations
        if alert_types.get("high_wait_time", 0) > 2:
            recommendations.append("Consider optimizing model loading or implementing better caching")
        
        if alert_types.get("high_fallback_usage", 0) > 2:
            recommendations.append("Review model loading priorities and consider pre-loading essential models")
        
        if alert_types.get("low_success_rate", 0) > 1:
            recommendations.append("Investigate system reliability issues and implement better error handling")
        
        if alert_types.get("capability_unavailable", 0) > 0:
            recommendations.append("Implement redundancy for essential capabilities and improve monitoring")
        
        if len(active_ux_alerts) > 3:
            recommendations.append("Multiple UX issues detected - consider comprehensive system review")
        
        # Check for critical issues
        critical_alerts = [a for a in active_ux_alerts if a.severity == AlertSeverity.CRITICAL]
        if critical_alerts:
            recommendations.insert(0, f"URGENT: {len(critical_alerts)} critical UX issues require immediate attention")
        
        return recommendations


# Convenience functions for easy integration
async def create_startup_alerts_service(phase_manager: StartupPhaseManager, 
                                      metrics_collector: StartupMetricsCollector) -> StartupAlertsService:
    """Create and start a startup alerts service."""
    service = StartupAlertsService(phase_manager, metrics_collector)
    await service.start_monitoring()
    return service


def create_cloudwatch_notification_handler(region: str = "us-east-1") -> Callable[[Alert], None]:
    """Create a CloudWatch notification handler for alerts."""
    def handler(alert: Alert) -> None:
        try:
            # This would integrate with AWS CloudWatch to send alerts
            # For now, just log the alert in CloudWatch format
            logger.info(f"CloudWatch Alert: {alert.alert_type.value} - {alert.title}")
            
            # In a real implementation, this would:
            # 1. Create CloudWatch custom metrics
            # 2. Trigger CloudWatch alarms
            # 3. Send SNS notifications
            # 4. Create CloudWatch Events
            
        except Exception as e:
            logger.error(f"Error in CloudWatch notification handler: {e}")
    
    return handler


def create_log_notification_handler() -> Callable[[Alert], None]:
    """Create a simple log-based notification handler."""
    def handler(alert: Alert) -> None:
        try:
            alert_data = {
                "alert_id": alert.alert_id,
                "type": alert.alert_type.value,
                "severity": alert.severity.value,
                "title": alert.title,
                "description": alert.description,
                "timestamp": alert.timestamp.isoformat(),
                "affected_resources": alert.affected_resources,
                "metrics": alert.metrics,
                "remediation_steps": alert.remediation_steps
            }
            
            logger.warning(f"STARTUP_ALERT: {json.dumps(alert_data, indent=2)}")
            
        except Exception as e:
            logger.error(f"Error in log notification handler: {e}")
    
    return handler


# Global instance for easy access
_global_alerts_service: Optional[StartupAlertsService] = None


def set_global_alerts_service(service: StartupAlertsService) -> None:
    """Set the global alerts service instance."""
    global _global_alerts_service
    _global_alerts_service = service


def get_global_alerts_service() -> Optional[StartupAlertsService]:
    """Get the global alerts service instance."""
    return _global_alerts_service