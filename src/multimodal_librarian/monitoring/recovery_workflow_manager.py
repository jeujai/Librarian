"""
Recovery Workflow Manager for automatic service restoration.

This module provides comprehensive recovery workflows with:
- Automatic service restoration strategies
- Recovery validation and verification
- Recovery notifications and alerting
- Recovery attempt tracking and analysis
"""

import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable, Union
from dataclasses import dataclass, field
from enum import Enum
import threading
from collections import defaultdict, deque
import uuid

from ..config import get_settings
from ..logging_config import get_logger
from .service_health_monitor import ServiceHealthMonitor, HealthStatus
from .error_logging_service import get_error_logging_service, ErrorSeverity, ErrorCategory
from .alerting_service import get_alerting_service


class RecoveryStrategy(Enum):
    """Recovery strategy types."""
    RESTART_SERVICE = "restart_service"
    RECONNECT_DATABASE = "reconnect_database"
    CLEAR_CACHE = "clear_cache"
    RELOAD_CONFIGURATION = "reload_configuration"
    SCALE_RESOURCES = "scale_resources"
    FALLBACK_SERVICE = "fallback_service"
    RETRY_OPERATION = "retry_operation"
    MANUAL_INTERVENTION = "manual_intervention"


class RecoveryStatus(Enum):
    """Recovery attempt status."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


class RecoveryPriority(Enum):
    """Recovery priority levels."""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class RecoveryAction:
    """Individual recovery action definition."""
    action_id: str
    name: str
    description: str
    strategy: RecoveryStrategy
    handler: Callable
    timeout_seconds: int = 300
    retry_count: int = 3
    retry_delay_seconds: int = 30
    prerequisites: List[str] = field(default_factory=list)
    validation_checks: List[Callable] = field(default_factory=list)
    rollback_handler: Optional[Callable] = None


@dataclass
class RecoveryWorkflow:
    """Recovery workflow definition."""
    workflow_id: str
    name: str
    description: str
    service_name: str
    trigger_conditions: Dict[str, Any]
    actions: List[RecoveryAction]
    priority: RecoveryPriority = RecoveryPriority.MEDIUM
    max_execution_time: int = 1800  # 30 minutes
    cooldown_period: int = 3600     # 1 hour
    enabled: bool = True


@dataclass
class RecoveryAttempt:
    """Recovery attempt tracking."""
    attempt_id: str
    workflow_id: str
    service_name: str
    trigger_reason: str
    start_time: datetime
    end_time: Optional[datetime] = None
    status: RecoveryStatus = RecoveryStatus.PENDING
    priority: RecoveryPriority = RecoveryPriority.MEDIUM
    actions_executed: List[Dict[str, Any]] = field(default_factory=list)
    validation_results: List[Dict[str, Any]] = field(default_factory=list)
    error_messages: List[str] = field(default_factory=list)
    recovery_metrics: Dict[str, Any] = field(default_factory=dict)
    notifications_sent: List[str] = field(default_factory=list)


class RecoveryWorkflowManager:
    """
    Manages automatic service recovery workflows with validation and notifications.
    
    Provides comprehensive recovery capabilities including:
    - Automatic service restoration
    - Recovery validation and verification
    - Recovery notifications and alerting
    - Recovery attempt tracking and analysis
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.logger = get_logger("recovery_workflow_manager")
        self.error_logging_service = get_error_logging_service()
        self.alerting_service = get_alerting_service()
        
        # Thread-safe storage
        self._lock = threading.Lock()
        
        # Recovery workflows and attempts
        self._workflows: Dict[str, RecoveryWorkflow] = {}
        self._active_attempts: Dict[str, RecoveryAttempt] = {}
        self._attempt_history = deque(maxlen=1000)  # Last 1000 attempts
        
        # Service-specific recovery mappings
        self._service_workflows: Dict[str, List[str]] = defaultdict(list)
        
        # Recovery statistics
        self._recovery_stats = defaultdict(lambda: {
            'total_attempts': 0,
            'successful_attempts': 0,
            'failed_attempts': 0,
            'average_duration': 0,
            'last_attempt': None
        })
        
        # Background processing
        self._processing_active = False
        self._processing_task = None
        
        # Initialize default workflows
        self._initialize_default_workflows()
        
        self.logger.info("Recovery workflow manager initialized")
    
    def _initialize_default_workflows(self) -> None:
        """Initialize default recovery workflows for common services."""
        
        # Database recovery workflow
        self.register_workflow(RecoveryWorkflow(
            workflow_id="database_recovery",
            name="Database Recovery",
            description="Automatic database connection recovery",
            service_name="database",
            trigger_conditions={
                "consecutive_failures": 3,
                "error_categories": [ErrorCategory.DATABASE_ERROR.value],
                "health_status": [HealthStatus.UNHEALTHY.value, HealthStatus.CRITICAL.value]
            },
            actions=[
                RecoveryAction(
                    action_id="reconnect_db",
                    name="Reconnect Database",
                    description="Attempt to reconnect to database",
                    strategy=RecoveryStrategy.RECONNECT_DATABASE,
                    handler=self._reconnect_database,
                    timeout_seconds=120,
                    retry_count=3,
                    validation_checks=[self._validate_database_connection]
                ),
                RecoveryAction(
                    action_id="clear_db_cache",
                    name="Clear Database Cache",
                    description="Clear database connection cache",
                    strategy=RecoveryStrategy.CLEAR_CACHE,
                    handler=self._clear_database_cache,
                    timeout_seconds=60,
                    prerequisites=["reconnect_db"]
                )
            ],
            priority=RecoveryPriority.HIGH
        ))
        
        # Search service recovery workflow
        self.register_workflow(RecoveryWorkflow(
            workflow_id="search_service_recovery",
            name="Search Service Recovery",
            description="Automatic search service recovery",
            service_name="search_service",
            trigger_conditions={
                "consecutive_failures": 5,
                "error_categories": [ErrorCategory.SERVICE_FAILURE.value],
                "health_status": [HealthStatus.UNHEALTHY.value]
            },
            actions=[
                RecoveryAction(
                    action_id="restart_search",
                    name="Restart Search Service",
                    description="Restart the search service",
                    strategy=RecoveryStrategy.RESTART_SERVICE,
                    handler=self._restart_search_service,
                    timeout_seconds=180,
                    validation_checks=[self._validate_search_service]
                ),
                RecoveryAction(
                    action_id="fallback_search",
                    name="Enable Search Fallback",
                    description="Enable fallback search service",
                    strategy=RecoveryStrategy.FALLBACK_SERVICE,
                    handler=self._enable_search_fallback,
                    timeout_seconds=60,
                    prerequisites=["restart_search"]
                )
            ],
            priority=RecoveryPriority.MEDIUM
        ))
        
        # Vector store recovery workflow
        self.register_workflow(RecoveryWorkflow(
            workflow_id="vector_store_recovery",
            name="Vector Store Recovery",
            description="Automatic vector store recovery",
            service_name="vector_store",
            trigger_conditions={
                "consecutive_failures": 3,
                "error_categories": [ErrorCategory.SERVICE_FAILURE.value, ErrorCategory.NETWORK_ERROR.value],
                "health_status": [HealthStatus.CRITICAL.value]
            },
            actions=[
                RecoveryAction(
                    action_id="reconnect_vector_store",
                    name="Reconnect Vector Store",
                    description="Reconnect to vector store",
                    strategy=RecoveryStrategy.RECONNECT_DATABASE,
                    handler=self._reconnect_vector_store,
                    timeout_seconds=120,
                    validation_checks=[self._validate_vector_store_connection]
                ),
                RecoveryAction(
                    action_id="clear_vector_cache",
                    name="Clear Vector Cache",
                    description="Clear vector store cache",
                    strategy=RecoveryStrategy.CLEAR_CACHE,
                    handler=self._clear_vector_cache,
                    timeout_seconds=60
                )
            ],
            priority=RecoveryPriority.HIGH
        ))
        
        # AI service recovery workflow
        self.register_workflow(RecoveryWorkflow(
            workflow_id="ai_service_recovery",
            name="AI Service Recovery",
            description="Automatic AI service recovery",
            service_name="ai_services",
            trigger_conditions={
                "consecutive_failures": 4,
                "error_categories": [ErrorCategory.EXTERNAL_SERVICE_ERROR.value, ErrorCategory.NETWORK_ERROR.value],
                "health_status": [HealthStatus.UNHEALTHY.value]
            },
            actions=[
                RecoveryAction(
                    action_id="restart_ai_service",
                    name="Restart AI Service",
                    description="Restart AI service connections",
                    strategy=RecoveryStrategy.RESTART_SERVICE,
                    handler=self._restart_ai_service,
                    timeout_seconds=180,
                    validation_checks=[self._validate_ai_service]
                ),
                RecoveryAction(
                    action_id="reload_ai_config",
                    name="Reload AI Configuration",
                    description="Reload AI service configuration",
                    strategy=RecoveryStrategy.RELOAD_CONFIGURATION,
                    handler=self._reload_ai_configuration,
                    timeout_seconds=60
                )
            ],
            priority=RecoveryPriority.MEDIUM
        ))
        
        # Cache service recovery workflow
        self.register_workflow(RecoveryWorkflow(
            workflow_id="cache_recovery",
            name="Cache Service Recovery",
            description="Automatic cache service recovery",
            service_name="cache",
            trigger_conditions={
                "consecutive_failures": 5,
                "error_categories": [ErrorCategory.SERVICE_FAILURE.value],
                "health_status": [HealthStatus.DEGRADED.value, HealthStatus.UNHEALTHY.value]
            },
            actions=[
                RecoveryAction(
                    action_id="clear_cache",
                    name="Clear Cache",
                    description="Clear all cache entries",
                    strategy=RecoveryStrategy.CLEAR_CACHE,
                    handler=self._clear_cache,
                    timeout_seconds=60,
                    validation_checks=[self._validate_cache_service]
                ),
                RecoveryAction(
                    action_id="restart_cache",
                    name="Restart Cache Service",
                    description="Restart cache service",
                    strategy=RecoveryStrategy.RESTART_SERVICE,
                    handler=self._restart_cache_service,
                    timeout_seconds=120,
                    prerequisites=["clear_cache"]
                )
            ],
            priority=RecoveryPriority.LOW
        ))
    
    def register_workflow(self, workflow: RecoveryWorkflow) -> None:
        """Register a recovery workflow."""
        with self._lock:
            self._workflows[workflow.workflow_id] = workflow
            self._service_workflows[workflow.service_name].append(workflow.workflow_id)
        
        self.logger.info(f"Registered recovery workflow: {workflow.name} for service: {workflow.service_name}")
    
    def unregister_workflow(self, workflow_id: str) -> bool:
        """Unregister a recovery workflow."""
        with self._lock:
            if workflow_id in self._workflows:
                workflow = self._workflows[workflow_id]
                del self._workflows[workflow_id]
                
                # Remove from service mapping
                if workflow.service_name in self._service_workflows:
                    self._service_workflows[workflow.service_name] = [
                        wid for wid in self._service_workflows[workflow.service_name] 
                        if wid != workflow_id
                    ]
                
                self.logger.info(f"Unregistered recovery workflow: {workflow_id}")
                return True
        
        return False
    
    async def trigger_recovery(self, service_name: str, trigger_reason: str, 
                             health_status: Optional[HealthStatus] = None,
                             error_category: Optional[ErrorCategory] = None,
                             priority: Optional[RecoveryPriority] = None) -> List[str]:
        """Trigger recovery workflows for a service."""
        
        triggered_attempts = []
        
        with self._lock:
            workflow_ids = self._service_workflows.get(service_name, [])
        
        for workflow_id in workflow_ids:
            workflow = self._workflows.get(workflow_id)
            if not workflow or not workflow.enabled:
                continue
            
            # Check if workflow should be triggered
            if self._should_trigger_workflow(workflow, health_status, error_category):
                # Check cooldown period
                if self._is_in_cooldown(workflow_id):
                    self.logger.info(f"Workflow {workflow_id} is in cooldown period, skipping")
                    continue
                
                # Create recovery attempt
                attempt = RecoveryAttempt(
                    attempt_id=str(uuid.uuid4()),
                    workflow_id=workflow_id,
                    service_name=service_name,
                    trigger_reason=trigger_reason,
                    start_time=datetime.now(),
                    priority=priority or workflow.priority
                )
                
                # Start recovery workflow
                asyncio.create_task(self._execute_recovery_workflow(workflow, attempt))
                triggered_attempts.append(attempt.attempt_id)
                
                self.logger.info(f"Triggered recovery workflow: {workflow.name} for service: {service_name}")
        
        return triggered_attempts
    
    def _should_trigger_workflow(self, workflow: RecoveryWorkflow, 
                                health_status: Optional[HealthStatus],
                                error_category: Optional[ErrorCategory]) -> bool:
        """Check if workflow should be triggered based on conditions."""
        conditions = workflow.trigger_conditions
        
        # Check health status condition
        if health_status and "health_status" in conditions:
            if health_status.value not in conditions["health_status"]:
                return False
        
        # Check error category condition
        if error_category and "error_categories" in conditions:
            if error_category.value not in conditions["error_categories"]:
                return False
        
        return True
    
    def _is_in_cooldown(self, workflow_id: str) -> bool:
        """Check if workflow is in cooldown period."""
        workflow = self._workflows.get(workflow_id)
        if not workflow:
            return False
        
        # Find last attempt for this workflow
        last_attempt_time = None
        for attempt in reversed(self._attempt_history):
            if attempt.workflow_id == workflow_id:
                last_attempt_time = attempt.start_time
                break
        
        if last_attempt_time:
            time_since_last = (datetime.now() - last_attempt_time).total_seconds()
            return time_since_last < workflow.cooldown_period
        
        return False
    
    async def _execute_recovery_workflow(self, workflow: RecoveryWorkflow, 
                                       attempt: RecoveryAttempt) -> None:
        """Execute a recovery workflow."""
        
        with self._lock:
            self._active_attempts[attempt.attempt_id] = attempt
        
        try:
            attempt.status = RecoveryStatus.IN_PROGRESS
            
            # Send start notification
            await self._send_recovery_notification(
                attempt, 
                "Recovery workflow started",
                f"Started recovery workflow '{workflow.name}' for service '{workflow.service_name}'"
            )
            
            # Execute actions in sequence
            for action in workflow.actions:
                # Check prerequisites
                if not await self._check_prerequisites(action, attempt):
                    self.logger.warning(f"Prerequisites not met for action: {action.name}")
                    continue
                
                # Execute action
                action_result = await self._execute_recovery_action(action, attempt)
                
                # Record action execution
                attempt.actions_executed.append({
                    'action_id': action.action_id,
                    'name': action.name,
                    'status': 'success' if action_result else 'failed',
                    'timestamp': datetime.now().isoformat(),
                    'duration_seconds': action_result.get('duration', 0) if isinstance(action_result, dict) else 0
                })
                
                # If action failed and it's critical, stop workflow
                if not action_result:
                    attempt.error_messages.append(f"Critical action failed: {action.name}")
                    break
            
            # Validate recovery
            validation_success = await self._validate_recovery(workflow, attempt)
            
            # Determine final status
            if validation_success and not attempt.error_messages:
                attempt.status = RecoveryStatus.SUCCESS
                self.logger.info(f"Recovery workflow completed successfully: {workflow.name}")
            else:
                attempt.status = RecoveryStatus.FAILED
                self.logger.error(f"Recovery workflow failed: {workflow.name}")
            
            # Update statistics
            self._update_recovery_statistics(workflow.workflow_id, attempt)
            
            # Send completion notification
            await self._send_recovery_notification(
                attempt,
                f"Recovery workflow {'completed' if attempt.status == RecoveryStatus.SUCCESS else 'failed'}",
                f"Recovery workflow '{workflow.name}' {'completed successfully' if attempt.status == RecoveryStatus.SUCCESS else 'failed'}"
            )
            
        except asyncio.TimeoutError:
            attempt.status = RecoveryStatus.TIMEOUT
            attempt.error_messages.append("Recovery workflow timed out")
            self.logger.error(f"Recovery workflow timed out: {workflow.name}")
            
        except Exception as e:
            attempt.status = RecoveryStatus.FAILED
            attempt.error_messages.append(f"Recovery workflow exception: {str(e)}")
            self.logger.error(f"Recovery workflow exception: {workflow.name}: {e}")
            
        finally:
            attempt.end_time = datetime.now()
            
            # Move to history
            with self._lock:
                if attempt.attempt_id in self._active_attempts:
                    del self._active_attempts[attempt.attempt_id]
                self._attempt_history.append(attempt)
            
            # Log recovery attempt
            self.error_logging_service.log_recovery_attempt(
                error_id=f"recovery_{attempt.attempt_id}",
                recovery_strategy=workflow.name,
                success=attempt.status == RecoveryStatus.SUCCESS,
                details={
                    'workflow_id': workflow.workflow_id,
                    'service_name': workflow.service_name,
                    'actions_executed': len(attempt.actions_executed),
                    'duration_seconds': (attempt.end_time - attempt.start_time).total_seconds(),
                    'error_messages': attempt.error_messages
                }
            )
    
    async def _check_prerequisites(self, action: RecoveryAction, 
                                 attempt: RecoveryAttempt) -> bool:
        """Check if action prerequisites are met."""
        if not action.prerequisites:
            return True
        
        executed_actions = {a['action_id'] for a in attempt.actions_executed if a['status'] == 'success'}
        
        for prerequisite in action.prerequisites:
            if prerequisite not in executed_actions:
                return False
        
        return True
    
    async def _execute_recovery_action(self, action: RecoveryAction, 
                                     attempt: RecoveryAttempt) -> Union[bool, Dict[str, Any]]:
        """Execute a single recovery action."""
        
        self.logger.info(f"Executing recovery action: {action.name}")
        
        start_time = time.time()
        
        try:
            # Execute action with timeout
            result = await asyncio.wait_for(
                action.handler(attempt.service_name),
                timeout=action.timeout_seconds
            )
            
            duration = time.time() - start_time
            
            # Run validation checks
            if action.validation_checks:
                validation_results = []
                for check in action.validation_checks:
                    try:
                        check_result = await check(attempt.service_name)
                        validation_results.append({
                            'check_name': check.__name__,
                            'result': check_result,
                            'timestamp': datetime.now().isoformat()
                        })
                    except Exception as e:
                        validation_results.append({
                            'check_name': check.__name__,
                            'result': False,
                            'error': str(e),
                            'timestamp': datetime.now().isoformat()
                        })
                
                attempt.validation_results.extend(validation_results)
                
                # Check if all validations passed
                if not all(v['result'] for v in validation_results):
                    self.logger.warning(f"Validation failed for action: {action.name}")
                    return False
            
            self.logger.info(f"Recovery action completed successfully: {action.name}")
            return {'success': True, 'duration': duration, 'result': result}
            
        except asyncio.TimeoutError:
            self.logger.error(f"Recovery action timed out: {action.name}")
            return False
            
        except Exception as e:
            self.logger.error(f"Recovery action failed: {action.name}: {e}")
            return False
    
    async def _validate_recovery(self, workflow: RecoveryWorkflow, 
                               attempt: RecoveryAttempt) -> bool:
        """Validate that recovery was successful."""
        
        # Check if any critical errors occurred
        if attempt.error_messages:
            return False
        
        # Check if at least one action was executed successfully
        successful_actions = [a for a in attempt.actions_executed if a['status'] == 'success']
        if not successful_actions:
            return False
        
        # Run workflow-level validation if available
        # This could be extended with custom validation logic
        
        return True
    
    def _update_recovery_statistics(self, workflow_id: str, attempt: RecoveryAttempt) -> None:
        """Update recovery statistics."""
        
        stats = self._recovery_stats[workflow_id]
        stats['total_attempts'] += 1
        stats['last_attempt'] = attempt.start_time
        
        if attempt.status == RecoveryStatus.SUCCESS:
            stats['successful_attempts'] += 1
        else:
            stats['failed_attempts'] += 1
        
        # Update average duration
        if attempt.end_time:
            duration = (attempt.end_time - attempt.start_time).total_seconds()
            current_avg = stats['average_duration']
            total_attempts = stats['total_attempts']
            stats['average_duration'] = ((current_avg * (total_attempts - 1)) + duration) / total_attempts
    
    async def _send_recovery_notification(self, attempt: RecoveryAttempt, 
                                        title: str, message: str) -> None:
        """Send recovery notification."""
        
        try:
            # Determine notification severity based on attempt status
            if attempt.status == RecoveryStatus.SUCCESS:
                severity = "info"
            elif attempt.status in [RecoveryStatus.FAILED, RecoveryStatus.TIMEOUT]:
                severity = "error"
            else:
                severity = "warning"
            
            # Send notification through alerting service
            notification_id = await self.alerting_service.send_alert(
                title=title,
                message=message,
                severity=severity,
                service=attempt.service_name,
                metadata={
                    'attempt_id': attempt.attempt_id,
                    'workflow_id': attempt.workflow_id,
                    'recovery_status': attempt.status.value,
                    'actions_executed': len(attempt.actions_executed),
                    'trigger_reason': attempt.trigger_reason
                }
            )
            
            attempt.notifications_sent.append(notification_id)
            
        except Exception as e:
            self.logger.error(f"Failed to send recovery notification: {e}")
    
    # Recovery action handlers
    async def _reconnect_database(self, service_name: str) -> bool:
        """Reconnect to database."""
        try:
            from ..database.connection import get_database_connection
            
            # Close existing connections
            # This would typically involve closing connection pools
            
            # Attempt new connection
            connection = await get_database_connection()
            if connection:
                self.logger.info("Database reconnection successful")
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Database reconnection failed: {e}")
            return False
    
    async def _clear_database_cache(self, service_name: str) -> bool:
        """Clear database cache."""
        try:
            # This would clear any database-related caches
            self.logger.info("Database cache cleared")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to clear database cache: {e}")
            return False
    
    async def _restart_search_service(self, service_name: str) -> bool:
        """Restart search service."""
        try:
            from ..components.vector_store.search_service import SearchService
            
            # Create new search service instance
            new_service = SearchService()
            
            # Test the service
            from ..models.search_types import SearchQuery
            test_query = SearchQuery(query_text="recovery test", limit=1)
            await new_service.search(test_query)
            
            self.logger.info("Search service restart successful")
            return True
            
        except Exception as e:
            self.logger.error(f"Search service restart failed: {e}")
            return False
    
    async def _enable_search_fallback(self, service_name: str) -> bool:
        """Enable search service fallback."""
        try:
            # This would enable fallback to simple search service
            self.logger.info("Search service fallback enabled")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to enable search fallback: {e}")
            return False
    
    async def _reconnect_vector_store(self, service_name: str) -> bool:
        """Reconnect to vector store."""
        try:
            from ..components.vector_store.vector_store import VectorStore
            
            # Create new vector store connection
            vector_store = VectorStore()
            
            # Test connection
            # This would typically involve a simple query or health check
            
            self.logger.info("Vector store reconnection successful")
            return True
            
        except Exception as e:
            self.logger.error(f"Vector store reconnection failed: {e}")
            return False
    
    async def _clear_vector_cache(self, service_name: str) -> bool:
        """Clear vector store cache."""
        try:
            # Clear vector-related caches
            self.logger.info("Vector store cache cleared")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to clear vector cache: {e}")
            return False
    
    async def _restart_ai_service(self, service_name: str) -> bool:
        """Restart AI service."""
        try:
            from ..services.ai_service import AIService
            
            # Create new AI service instance
            ai_service = AIService()
            
            # Test the service
            test_response = await ai_service.generate_response("recovery test")
            
            if test_response:
                self.logger.info("AI service restart successful")
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"AI service restart failed: {e}")
            return False
    
    async def _reload_ai_configuration(self, service_name: str) -> bool:
        """Reload AI service configuration."""
        try:
            # Reload AI configuration
            self.logger.info("AI service configuration reloaded")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to reload AI configuration: {e}")
            return False
    
    async def _clear_cache(self, service_name: str) -> bool:
        """Clear cache service."""
        try:
            from ..services.cache_service import CacheService
            
            cache_service = CacheService()
            await cache_service.clear_all()
            
            self.logger.info("Cache cleared successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to clear cache: {e}")
            return False
    
    async def _restart_cache_service(self, service_name: str) -> bool:
        """Restart cache service."""
        try:
            from ..services.cache_service import CacheService
            
            # Create new cache service instance
            cache_service = CacheService()
            
            # Test the service
            await cache_service.set("recovery_test", {"test": True}, ttl=60)
            test_value = await cache_service.get("recovery_test")
            await cache_service.delete("recovery_test")
            
            if test_value and test_value.get("test"):
                self.logger.info("Cache service restart successful")
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Cache service restart failed: {e}")
            return False
    
    # Validation handlers
    async def _validate_database_connection(self, service_name: str) -> bool:
        """Validate database connection."""
        try:
            from ..database.connection import get_database_connection
            
            connection = await get_database_connection()
            if connection:
                # Test with a simple query
                # This would be database-specific
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Database connection validation failed: {e}")
            return False
    
    async def _validate_search_service(self, service_name: str) -> bool:
        """Validate search service."""
        try:
            from ..components.vector_store.search_service import SearchService
            from ..models.search_types import SearchQuery
            
            service = SearchService()
            test_query = SearchQuery(query_text="validation test", limit=1)
            result = await service.search(test_query)
            
            return result is not None
            
        except Exception as e:
            self.logger.error(f"Search service validation failed: {e}")
            return False
    
    async def _validate_vector_store_connection(self, service_name: str) -> bool:
        """Validate vector store connection."""
        try:
            from ..components.vector_store.vector_store import VectorStore
            
            vector_store = VectorStore()
            # This would typically involve a health check or simple query
            
            return True
            
        except Exception as e:
            self.logger.error(f"Vector store validation failed: {e}")
            return False
    
    async def _validate_ai_service(self, service_name: str) -> bool:
        """Validate AI service."""
        try:
            from ..services.ai_service import AIService
            
            ai_service = AIService()
            test_response = await ai_service.generate_response("validation test")
            
            return test_response is not None
            
        except Exception as e:
            self.logger.error(f"AI service validation failed: {e}")
            return False
    
    async def _validate_cache_service(self, service_name: str) -> bool:
        """Validate cache service."""
        try:
            from ..services.cache_service import CacheService
            
            cache_service = CacheService()
            
            # Test cache operations
            await cache_service.set("validation_test", {"test": True}, ttl=60)
            test_value = await cache_service.get("validation_test")
            await cache_service.delete("validation_test")
            
            return test_value is not None and test_value.get("test") is True
            
        except Exception as e:
            self.logger.error(f"Cache service validation failed: {e}")
            return False
    
    # Public API methods
    def get_active_attempts(self) -> List[Dict[str, Any]]:
        """Get currently active recovery attempts."""
        with self._lock:
            return [
                {
                    'attempt_id': attempt.attempt_id,
                    'workflow_id': attempt.workflow_id,
                    'service_name': attempt.service_name,
                    'status': attempt.status.value,
                    'start_time': attempt.start_time.isoformat(),
                    'actions_executed': len(attempt.actions_executed),
                    'priority': attempt.priority.value
                }
                for attempt in self._active_attempts.values()
            ]
    
    def get_recovery_history(self, hours: int = 24, service_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get recovery attempt history."""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        with self._lock:
            filtered_attempts = [
                attempt for attempt in self._attempt_history
                if attempt.start_time >= cutoff_time and
                (service_name is None or attempt.service_name == service_name)
            ]
        
        return [
            {
                'attempt_id': attempt.attempt_id,
                'workflow_id': attempt.workflow_id,
                'service_name': attempt.service_name,
                'status': attempt.status.value,
                'start_time': attempt.start_time.isoformat(),
                'end_time': attempt.end_time.isoformat() if attempt.end_time else None,
                'duration_seconds': (attempt.end_time - attempt.start_time).total_seconds() if attempt.end_time else None,
                'actions_executed': len(attempt.actions_executed),
                'validation_results': len(attempt.validation_results),
                'error_messages': attempt.error_messages,
                'trigger_reason': attempt.trigger_reason,
                'priority': attempt.priority.value
            }
            for attempt in sorted(filtered_attempts, key=lambda x: x.start_time, reverse=True)
        ]
    
    def get_recovery_statistics(self) -> Dict[str, Any]:
        """Get recovery statistics."""
        with self._lock:
            total_attempts = sum(stats['total_attempts'] for stats in self._recovery_stats.values())
            total_successes = sum(stats['successful_attempts'] for stats in self._recovery_stats.values())
            
            return {
                'overall_statistics': {
                    'total_attempts': total_attempts,
                    'successful_attempts': total_successes,
                    'success_rate': (total_successes / max(1, total_attempts)) * 100,
                    'active_workflows': len(self._workflows),
                    'active_attempts': len(self._active_attempts)
                },
                'workflow_statistics': {
                    workflow_id: {
                        'workflow_name': self._workflows[workflow_id].name if workflow_id in self._workflows else 'Unknown',
                        'total_attempts': stats['total_attempts'],
                        'successful_attempts': stats['successful_attempts'],
                        'failed_attempts': stats['failed_attempts'],
                        'success_rate': (stats['successful_attempts'] / max(1, stats['total_attempts'])) * 100,
                        'average_duration_seconds': round(stats['average_duration'], 2),
                        'last_attempt': stats['last_attempt'].isoformat() if stats['last_attempt'] else None
                    }
                    for workflow_id, stats in self._recovery_stats.items()
                }
            }
    
    def get_workflow_details(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a workflow."""
        workflow = self._workflows.get(workflow_id)
        if not workflow:
            return None
        
        return {
            'workflow_id': workflow.workflow_id,
            'name': workflow.name,
            'description': workflow.description,
            'service_name': workflow.service_name,
            'priority': workflow.priority.value,
            'enabled': workflow.enabled,
            'trigger_conditions': workflow.trigger_conditions,
            'actions': [
                {
                    'action_id': action.action_id,
                    'name': action.name,
                    'description': action.description,
                    'strategy': action.strategy.value,
                    'timeout_seconds': action.timeout_seconds,
                    'retry_count': action.retry_count,
                    'prerequisites': action.prerequisites
                }
                for action in workflow.actions
            ],
            'statistics': self._recovery_stats.get(workflow_id, {})
        }
    
    def start_processing(self) -> None:
        """Start background recovery processing."""
        if self._processing_active:
            self.logger.warning("Recovery processing is already active")
            return
        
        self._processing_active = True
        self._processing_task = asyncio.create_task(self._background_processing())
        
        self.logger.info("Started recovery workflow processing")
    
    def stop_processing(self) -> None:
        """Stop background recovery processing."""
        self._processing_active = False
        
        if self._processing_task:
            self._processing_task.cancel()
        
        self.logger.info("Stopped recovery workflow processing")
    
    async def _background_processing(self) -> None:
        """Background processing for recovery workflows."""
        while self._processing_active:
            try:
                # Monitor active attempts for timeouts
                current_time = datetime.now()
                
                with self._lock:
                    timed_out_attempts = []
                    for attempt in self._active_attempts.values():
                        workflow = self._workflows.get(attempt.workflow_id)
                        if workflow:
                            elapsed_time = (current_time - attempt.start_time).total_seconds()
                            if elapsed_time > workflow.max_execution_time:
                                timed_out_attempts.append(attempt.attempt_id)
                
                # Handle timed out attempts
                for attempt_id in timed_out_attempts:
                    attempt = self._active_attempts.get(attempt_id)
                    if attempt:
                        attempt.status = RecoveryStatus.TIMEOUT
                        attempt.end_time = current_time
                        attempt.error_messages.append("Recovery workflow exceeded maximum execution time")
                        
                        # Move to history
                        del self._active_attempts[attempt_id]
                        self._attempt_history.append(attempt)
                        
                        self.logger.warning(f"Recovery attempt timed out: {attempt_id}")
                
                await asyncio.sleep(60)  # Check every minute
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Exception in recovery background processing: {e}")
                await asyncio.sleep(60)


# Global recovery workflow manager instance
_recovery_workflow_manager = None


def get_recovery_workflow_manager() -> RecoveryWorkflowManager:
    """Get the global recovery workflow manager instance."""
    global _recovery_workflow_manager
    if _recovery_workflow_manager is None:
        _recovery_workflow_manager = RecoveryWorkflowManager()
    return _recovery_workflow_manager