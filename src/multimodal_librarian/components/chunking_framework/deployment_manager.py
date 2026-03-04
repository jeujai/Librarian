"""
Automated Configuration Deployment Manager.

This module implements automated deployment of optimized configurations
with rollback mechanisms and safety checks.
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import uuid
import numpy as np
from collections import defaultdict

from ...models.chunking import DomainConfig, PerformanceMetrics, StoredDomainConfig
from ...database.connection import get_database_connection

logger = logging.getLogger(__name__)


@dataclass
class DeploymentPlan:
    """Plan for configuration deployment."""
    plan_id: str
    domain_name: str
    current_config: DomainConfig
    target_config: DomainConfig
    deployment_strategy: str  # 'immediate', 'gradual', 'canary'
    rollback_criteria: Dict[str, float]
    safety_checks: List[str]
    estimated_impact: Dict[str, float]
    approval_required: bool
    created_at: datetime


@dataclass
class DeploymentRecord:
    """Record of configuration deployment."""
    deployment_id: str
    plan_id: str
    domain_name: str
    deployed_config: DomainConfig
    previous_config: DomainConfig
    deployment_type: str  # 'optimization', 'rollback', 'manual'
    deployment_status: str  # 'pending', 'active', 'completed', 'failed', 'rolled_back'
    performance_before: Optional[PerformanceMetrics]
    performance_after: Optional[PerformanceMetrics]
    deployment_time: datetime
    rollback_time: Optional[datetime]
    rollback_reason: Optional[str]


@dataclass
class RollbackTrigger:
    """Trigger for automatic rollback."""
    trigger_id: str
    deployment_id: str
    trigger_type: str  # 'performance_degradation', 'error_spike', 'user_feedback'
    severity: str  # 'low', 'medium', 'high', 'critical'
    trigger_conditions: Dict[str, Any]
    detected_at: datetime
    auto_rollback: bool


class DeploymentManager:
    """
    Automated configuration deployment manager with rollback capabilities.
    
    Implements safe deployment strategies, performance monitoring,
    and automated rollback mechanisms.
    """
    
    def __init__(self):
        """Initialize the deployment manager."""
        
        # Deployment configuration
        self.deployment_config = {
            'safety_check_duration_minutes': 30,
            'performance_monitoring_duration_hours': 24,
            'rollback_performance_threshold': 0.1,  # 10% degradation triggers rollback
            'max_concurrent_deployments': 3,
            'canary_traffic_percentage': 10.0
        }
        
        # Rollback criteria
        self.rollback_criteria = {
            'chunk_quality_score': {'min_threshold': 0.5, 'degradation_threshold': 0.15},
            'bridge_success_rate': {'min_threshold': 0.4, 'degradation_threshold': 0.20},
            'retrieval_effectiveness': {'min_threshold': 0.6, 'degradation_threshold': 0.15},
            'user_satisfaction_score': {'min_threshold': 0.5, 'degradation_threshold': 0.25},
            'processing_efficiency': {'min_threshold': 0.6, 'degradation_threshold': 0.20},
            'boundary_quality': {'min_threshold': 0.5, 'degradation_threshold': 0.15}
        }
        
        # Active deployments tracking
        self.active_deployments = {}
        self.deployment_history = defaultdict(list)
        
        logger.info("Initialized Deployment Manager")
    
    def create_deployment_plan(self, domain_name: str, target_config: DomainConfig,
                             deployment_strategy: str = 'gradual',
                             approval_required: bool = False) -> DeploymentPlan:
        """
        Create a deployment plan for a configuration change.
        
        Args:
            domain_name: Domain to deploy to
            target_config: Configuration to deploy
            deployment_strategy: Strategy for deployment
            approval_required: Whether manual approval is required
            
        Returns:
            Deployment plan
        """
        # Get current configuration
        current_config = self._get_current_config(domain_name)
        
        # Estimate impact
        estimated_impact = self._estimate_deployment_impact(current_config, target_config)
        
        # Determine safety checks
        safety_checks = self._determine_safety_checks(estimated_impact)
        
        # Create deployment plan
        plan = DeploymentPlan(
            plan_id=str(uuid.uuid4()),
            domain_name=domain_name,
            current_config=current_config,
            target_config=target_config,
            deployment_strategy=deployment_strategy,
            rollback_criteria=self.rollback_criteria.copy(),
            safety_checks=safety_checks,
            estimated_impact=estimated_impact,
            approval_required=approval_required,
            created_at=datetime.now()
        )
        
        # Store deployment plan
        self._store_deployment_plan(plan)
        
        logger.info(f"Created deployment plan {plan.plan_id} for domain {domain_name}")
        
        return plan
    
    def execute_deployment(self, plan_id: str) -> str:
        """
        Execute a deployment plan.
        
        Args:
            plan_id: ID of the deployment plan
            
        Returns:
            Deployment ID
        """
        plan = self._get_deployment_plan(plan_id)
        if not plan:
            raise ValueError(f"Deployment plan {plan_id} not found")
        
        # Check if deployment is safe
        if not self._is_deployment_safe(plan):
            raise ValueError("Deployment failed safety checks")
        
        # Create deployment record
        deployment_id = str(uuid.uuid4())
        
        # Get baseline performance
        baseline_performance = self._get_current_performance(plan.domain_name)
        
        deployment_record = DeploymentRecord(
            deployment_id=deployment_id,
            plan_id=plan_id,
            domain_name=plan.domain_name,
            deployed_config=plan.target_config,
            previous_config=plan.current_config,
            deployment_type='optimization',
            deployment_status='pending',
            performance_before=baseline_performance,
            performance_after=None,
            deployment_time=datetime.now(),
            rollback_time=None,
            rollback_reason=None
        )
        
        # Execute deployment based on strategy
        success = False
        if plan.deployment_strategy == 'immediate':
            success = self._execute_immediate_deployment(deployment_record)
        elif plan.deployment_strategy == 'gradual':
            success = self._execute_gradual_deployment(deployment_record)
        elif plan.deployment_strategy == 'canary':
            success = self._execute_canary_deployment(deployment_record)
        
        if success:
            deployment_record.deployment_status = 'active'
            self.active_deployments[deployment_id] = deployment_record
            
            # Start monitoring
            self._start_deployment_monitoring(deployment_id)
            
            logger.info(f"Successfully deployed configuration {deployment_id} "
                       f"for domain {plan.domain_name}")
        else:
            deployment_record.deployment_status = 'failed'
            logger.error(f"Failed to deploy configuration {deployment_id}")
        
        # Store deployment record
        self._store_deployment_record(deployment_record)
        
        return deployment_id
    
    def monitor_deployment(self, deployment_id: str) -> bool:
        """
        Monitor an active deployment for performance issues.
        
        Args:
            deployment_id: ID of the deployment
            
        Returns:
            True if deployment is healthy, False if rollback needed
        """
        if deployment_id not in self.active_deployments:
            logger.warning(f"Deployment {deployment_id} not found in active deployments")
            return False
        
        deployment = self.active_deployments[deployment_id]
        
        # Get current performance
        current_performance = self._get_current_performance(deployment.domain_name)
        
        # Check rollback criteria
        rollback_triggers = self._check_rollback_criteria(deployment, current_performance)
        
        if rollback_triggers:
            logger.warning(f"Rollback triggers detected for deployment {deployment_id}: "
                          f"{[t.trigger_type for t in rollback_triggers]}")
            
            # Execute automatic rollback if criteria met
            critical_triggers = [t for t in rollback_triggers if t.severity == 'critical']
            if critical_triggers:
                self.rollback_deployment(deployment_id, "Automatic rollback due to critical issues")
                return False
        
        # Update performance metrics
        deployment.performance_after = current_performance
        
        return True
    
    def rollback_deployment(self, deployment_id: str, reason: str) -> bool:
        """
        Rollback a deployment to the previous configuration.
        
        Args:
            deployment_id: ID of the deployment to rollback
            reason: Reason for rollback
            
        Returns:
            True if rollback was successful
        """
        if deployment_id not in self.active_deployments:
            logger.error(f"Deployment {deployment_id} not found for rollback")
            return False
        
        deployment = self.active_deployments[deployment_id]
        
        # Execute rollback
        success = self._execute_configuration_rollback(deployment.domain_name, 
                                                     deployment.previous_config)
        
        if success:
            # Update deployment record
            deployment.deployment_status = 'rolled_back'
            deployment.rollback_time = datetime.now()
            deployment.rollback_reason = reason
            
            # Remove from active deployments
            del self.active_deployments[deployment_id]
            
            # Store updated record
            self._store_deployment_record(deployment)
            
            logger.info(f"Successfully rolled back deployment {deployment_id}: {reason}")
        else:
            logger.error(f"Failed to rollback deployment {deployment_id}")
        
        return success
    
    def get_deployment_status(self, deployment_id: str) -> Optional[Dict[str, Any]]:
        """
        Get status of a deployment.
        
        Args:
            deployment_id: ID of the deployment
            
        Returns:
            Deployment status information
        """
        # Check active deployments first
        if deployment_id in self.active_deployments:
            deployment = self.active_deployments[deployment_id]
            return {
                'deployment_id': deployment_id,
                'status': deployment.deployment_status,
                'domain_name': deployment.domain_name,
                'deployment_time': deployment.deployment_time.isoformat(),
                'performance_before': deployment.performance_before.to_dict() if deployment.performance_before else None,
                'performance_after': deployment.performance_after.to_dict() if deployment.performance_after else None,
                'rollback_time': deployment.rollback_time.isoformat() if deployment.rollback_time else None,
                'rollback_reason': deployment.rollback_reason
            }
        
        # Check database for historical deployments
        return self._get_deployment_status_from_db(deployment_id)
    
    def _is_deployment_safe(self, plan: DeploymentPlan) -> bool:
        """Check if deployment is safe to execute."""
        
        # Check concurrent deployments limit
        if len(self.active_deployments) >= self.deployment_config['max_concurrent_deployments']:
            logger.warning("Maximum concurrent deployments reached")
            return False
        
        # Check estimated impact
        high_impact_metrics = [k for k, v in plan.estimated_impact.items() if abs(v) > 0.2]
        if len(high_impact_metrics) > 2:
            logger.warning(f"High impact deployment detected: {high_impact_metrics}")
            if plan.approval_required:
                return False  # Would require manual approval
        
        # Check safety checks
        for check in plan.safety_checks:
            if not self._execute_safety_check(check, plan):
                logger.warning(f"Safety check failed: {check}")
                return False
        
        return True
    
    def _execute_immediate_deployment(self, deployment: DeploymentRecord) -> bool:
        """Execute immediate deployment strategy."""
        return self._deploy_configuration(deployment.domain_name, deployment.deployed_config)
    
    def _execute_gradual_deployment(self, deployment: DeploymentRecord) -> bool:
        """Execute gradual deployment strategy."""
        # For gradual deployment, we would implement traffic shifting
        # For now, we'll simulate with immediate deployment
        return self._deploy_configuration(deployment.domain_name, deployment.deployed_config)
    
    def _execute_canary_deployment(self, deployment: DeploymentRecord) -> bool:
        """Execute canary deployment strategy."""
        # For canary deployment, we would deploy to a subset of traffic
        # For now, we'll simulate with immediate deployment
        return self._deploy_configuration(deployment.domain_name, deployment.deployed_config)
    
    def _deploy_configuration(self, domain_name: str, config: DomainConfig) -> bool:
        """Deploy configuration to database."""
        try:
            with get_database_connection() as conn:
                cursor = conn.cursor()
                
                # Deactivate current configuration
                update_query = """
                UPDATE domain_configurations 
                SET is_active = false 
                WHERE domain_name = %s AND is_active = true
                """
                cursor.execute(update_query, (domain_name,))
                
                # Insert new configuration
                insert_query = """
                INSERT INTO domain_configurations 
                (domain_name, version, config_data, generation_method, 
                 confidence_score, is_active, created_at)
                VALUES (%s, 
                        (SELECT COALESCE(MAX(version), 0) + 1 FROM domain_configurations WHERE domain_name = %s),
                        %s, %s, %s, true, %s)
                """
                
                cursor.execute(insert_query, (
                    domain_name, domain_name, json.dumps(config.to_dict()),
                    'automated_deployment', config.confidence_score, datetime.now()
                ))
                
                conn.commit()
                return True
        
        except Exception as e:
            logger.error(f"Failed to deploy configuration: {e}")
            return False
    
    def _execute_configuration_rollback(self, domain_name: str, previous_config: DomainConfig) -> bool:
        """Execute configuration rollback."""
        return self._deploy_configuration(domain_name, previous_config)
    
    def _start_deployment_monitoring(self, deployment_id: str) -> None:
        """Start monitoring a deployment."""
        # In a real implementation, this would start a background monitoring task
        logger.info(f"Started monitoring deployment {deployment_id}")
    
    def _check_rollback_criteria(self, deployment: DeploymentRecord, 
                               current_performance: PerformanceMetrics) -> List[RollbackTrigger]:
        """Check if rollback criteria are met."""
        triggers = []
        
        if not deployment.performance_before:
            return triggers
        
        # Check performance degradation
        for metric_name, criteria in self.rollback_criteria.items():
            before_value = getattr(deployment.performance_before, metric_name, 0.0)
            current_value = getattr(current_performance, metric_name, 0.0)
            
            # Check absolute threshold
            if current_value < criteria['min_threshold']:
                trigger = RollbackTrigger(
                    trigger_id=str(uuid.uuid4()),
                    deployment_id=deployment.deployment_id,
                    trigger_type='performance_threshold',
                    severity='critical',
                    trigger_conditions={
                        'metric': metric_name,
                        'current_value': current_value,
                        'threshold': criteria['min_threshold']
                    },
                    detected_at=datetime.now(),
                    auto_rollback=True
                )
                triggers.append(trigger)
            
            # Check degradation threshold
            elif before_value > 0:
                degradation = (before_value - current_value) / before_value
                if degradation > criteria['degradation_threshold']:
                    severity = 'critical' if degradation > 0.3 else 'high'
                    trigger = RollbackTrigger(
                        trigger_id=str(uuid.uuid4()),
                        deployment_id=deployment.deployment_id,
                        trigger_type='performance_degradation',
                        severity=severity,
                        trigger_conditions={
                            'metric': metric_name,
                            'before_value': before_value,
                            'current_value': current_value,
                            'degradation': degradation
                        },
                        detected_at=datetime.now(),
                        auto_rollback=severity == 'critical'
                    )
                    triggers.append(trigger)
        
        return triggers
    
    def _get_current_config(self, domain_name: str) -> DomainConfig:
        """Get current active configuration for domain."""
        try:
            with get_database_connection() as conn:
                cursor = conn.cursor()
                
                query = """
                SELECT config_data FROM domain_configurations 
                WHERE domain_name = %s AND is_active = true
                ORDER BY version DESC LIMIT 1
                """
                cursor.execute(query, (domain_name,))
                result = cursor.fetchone()
                
                if result:
                    config_data = json.loads(result[0])
                    return DomainConfig.from_dict(config_data)
                else:
                    # Return default configuration
                    return DomainConfig(domain_name=domain_name)
        
        except Exception as e:
            logger.error(f"Failed to get current config: {e}")
            return DomainConfig(domain_name=domain_name)
    
    def _get_current_performance(self, domain_name: str) -> Optional[PerformanceMetrics]:
        """Get current performance metrics for domain."""
        try:
            with get_database_connection() as conn:
                cursor = conn.cursor()
                
                query = """
                SELECT cpm.chunk_quality_score, cpm.bridge_success_rate,
                       cpm.retrieval_effectiveness, cpm.user_satisfaction_score,
                       cpm.processing_efficiency, cpm.boundary_quality,
                       cpm.document_count, cpm.measurement_date
                FROM config_performance_metrics cpm
                JOIN domain_configurations dc ON cpm.config_id = dc.id
                WHERE dc.domain_name = %s AND dc.is_active = true
                ORDER BY cpm.measurement_date DESC LIMIT 1
                """
                cursor.execute(query, (domain_name,))
                result = cursor.fetchone()
                
                if result:
                    return PerformanceMetrics(
                        chunk_quality_score=result[0],
                        bridge_success_rate=result[1],
                        retrieval_effectiveness=result[2],
                        user_satisfaction_score=result[3],
                        processing_efficiency=result[4],
                        boundary_quality=result[5],
                        document_count=result[6],
                        measurement_date=result[7]
                    )
        
        except Exception as e:
            logger.error(f"Failed to get current performance: {e}")
        
        return None
    
    def _estimate_deployment_impact(self, current_config: DomainConfig, 
                                  target_config: DomainConfig) -> Dict[str, float]:
        """Estimate impact of configuration change."""
        # Simplified impact estimation
        # In practice, this would use ML models or historical data
        
        impact = {}
        
        # Compare chunk size modifiers
        current_modifiers = current_config.chunk_size_modifiers
        target_modifiers = target_config.chunk_size_modifiers
        
        for key in set(current_modifiers.keys()) | set(target_modifiers.keys()):
            current_val = current_modifiers.get(key, 1.0)
            target_val = target_modifiers.get(key, 1.0)
            change = (target_val - current_val) / current_val if current_val != 0 else 0
            
            if abs(change) > 0.1:  # Significant change
                impact[f'chunk_size_{key}'] = change
        
        # Compare bridge thresholds
        current_thresholds = current_config.bridge_thresholds
        target_thresholds = target_config.bridge_thresholds
        
        for key in set(current_thresholds.keys()) | set(target_thresholds.keys()):
            current_val = current_thresholds.get(key, 0.7)
            target_val = target_thresholds.get(key, 0.7)
            change = target_val - current_val
            
            if abs(change) > 0.05:  # Significant change
                impact[f'bridge_threshold_{key}'] = change
        
        return impact
    
    def _determine_safety_checks(self, estimated_impact: Dict[str, float]) -> List[str]:
        """Determine required safety checks based on estimated impact."""
        checks = ['basic_validation']
        
        # Add checks based on impact
        if any(abs(v) > 0.2 for v in estimated_impact.values()):
            checks.append('performance_baseline_check')
        
        if any('chunk_size' in k for k in estimated_impact.keys()):
            checks.append('chunk_quality_validation')
        
        if any('bridge_threshold' in k for k in estimated_impact.keys()):
            checks.append('bridge_generation_validation')
        
        return checks
    
    def _execute_safety_check(self, check_name: str, plan: DeploymentPlan) -> bool:
        """Execute a safety check."""
        # Simplified safety checks - in practice would be more comprehensive
        
        if check_name == 'basic_validation':
            return plan.target_config.validate()
        
        elif check_name == 'performance_baseline_check':
            # Check if we have recent performance data
            current_perf = self._get_current_performance(plan.domain_name)
            return current_perf is not None
        
        elif check_name == 'chunk_quality_validation':
            # Validate chunk size parameters are reasonable
            modifiers = plan.target_config.chunk_size_modifiers
            return all(0.5 <= v <= 2.0 for v in modifiers.values())
        
        elif check_name == 'bridge_generation_validation':
            # Validate bridge thresholds are reasonable
            thresholds = plan.target_config.bridge_thresholds
            return all(0.0 <= v <= 1.0 for v in thresholds.values())
        
        return True
    
    def _store_deployment_plan(self, plan: DeploymentPlan) -> None:
        """Store deployment plan in database."""
        try:
            with get_database_connection() as conn:
                cursor = conn.cursor()
                
                # Create table if it doesn't exist
                create_table_query = """
                CREATE TABLE IF NOT EXISTS deployment_plans (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    plan_id VARCHAR(100) UNIQUE NOT NULL,
                    domain_name VARCHAR(100) NOT NULL,
                    current_config JSONB NOT NULL,
                    target_config JSONB NOT NULL,
                    deployment_strategy VARCHAR(50) NOT NULL,
                    rollback_criteria JSONB,
                    safety_checks TEXT[],
                    estimated_impact JSONB,
                    approval_required BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
                cursor.execute(create_table_query)
                
                insert_query = """
                INSERT INTO deployment_plans 
                (plan_id, domain_name, current_config, target_config, 
                 deployment_strategy, rollback_criteria, safety_checks, 
                 estimated_impact, approval_required, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                
                cursor.execute(insert_query, (
                    plan.plan_id, plan.domain_name,
                    json.dumps(plan.current_config.to_dict()),
                    json.dumps(plan.target_config.to_dict()),
                    plan.deployment_strategy, json.dumps(plan.rollback_criteria),
                    plan.safety_checks, json.dumps(plan.estimated_impact),
                    plan.approval_required, plan.created_at
                ))
                
                conn.commit()
        
        except Exception as e:
            logger.error(f"Failed to store deployment plan: {e}")
    
    def _store_deployment_record(self, record: DeploymentRecord) -> None:
        """Store deployment record in database."""
        try:
            with get_database_connection() as conn:
                cursor = conn.cursor()
                
                # Create table if it doesn't exist
                create_table_query = """
                CREATE TABLE IF NOT EXISTS deployment_records (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    deployment_id VARCHAR(100) UNIQUE NOT NULL,
                    plan_id VARCHAR(100),
                    domain_name VARCHAR(100) NOT NULL,
                    deployment_type VARCHAR(50) NOT NULL,
                    deployment_status VARCHAR(50) NOT NULL,
                    deployed_config JSONB NOT NULL,
                    previous_config JSONB NOT NULL,
                    performance_before JSONB,
                    performance_after JSONB,
                    deployment_time TIMESTAMP NOT NULL,
                    rollback_time TIMESTAMP,
                    rollback_reason TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
                cursor.execute(create_table_query)
                
                # Upsert deployment record
                upsert_query = """
                INSERT INTO deployment_records 
                (deployment_id, plan_id, domain_name, deployment_type, deployment_status,
                 deployed_config, previous_config, performance_before, performance_after,
                 deployment_time, rollback_time, rollback_reason)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (deployment_id) DO UPDATE SET
                    deployment_status = EXCLUDED.deployment_status,
                    performance_after = EXCLUDED.performance_after,
                    rollback_time = EXCLUDED.rollback_time,
                    rollback_reason = EXCLUDED.rollback_reason
                """
                
                cursor.execute(upsert_query, (
                    record.deployment_id, record.plan_id, record.domain_name,
                    record.deployment_type, record.deployment_status,
                    json.dumps(record.deployed_config.to_dict()),
                    json.dumps(record.previous_config.to_dict()),
                    json.dumps(record.performance_before.to_dict()) if record.performance_before else None,
                    json.dumps(record.performance_after.to_dict()) if record.performance_after else None,
                    record.deployment_time, record.rollback_time, record.rollback_reason
                ))
                
                conn.commit()
        
        except Exception as e:
            logger.error(f"Failed to store deployment record: {e}")
    
    def _get_deployment_plan(self, plan_id: str) -> Optional[DeploymentPlan]:
        """Get deployment plan from database."""
        try:
            with get_database_connection() as conn:
                cursor = conn.cursor()
                
                query = """
                SELECT plan_id, domain_name, current_config, target_config,
                       deployment_strategy, rollback_criteria, safety_checks,
                       estimated_impact, approval_required, created_at
                FROM deployment_plans WHERE plan_id = %s
                """
                cursor.execute(query, (plan_id,))
                result = cursor.fetchone()
                
                if result:
                    return DeploymentPlan(
                        plan_id=result[0],
                        domain_name=result[1],
                        current_config=DomainConfig.from_dict(json.loads(result[2])),
                        target_config=DomainConfig.from_dict(json.loads(result[3])),
                        deployment_strategy=result[4],
                        rollback_criteria=json.loads(result[5]) if result[5] else {},
                        safety_checks=result[6] or [],
                        estimated_impact=json.loads(result[7]) if result[7] else {},
                        approval_required=result[8],
                        created_at=result[9]
                    )
        
        except Exception as e:
            logger.error(f"Failed to get deployment plan: {e}")
        
        return None
    
    def _get_deployment_status_from_db(self, deployment_id: str) -> Optional[Dict[str, Any]]:
        """Get deployment status from database."""
        try:
            with get_database_connection() as conn:
                cursor = conn.cursor()
                
                query = """
                SELECT deployment_id, domain_name, deployment_status, deployment_time,
                       performance_before, performance_after, rollback_time, rollback_reason
                FROM deployment_records WHERE deployment_id = %s
                """
                cursor.execute(query, (deployment_id,))
                result = cursor.fetchone()
                
                if result:
                    return {
                        'deployment_id': result[0],
                        'domain_name': result[1],
                        'status': result[2],
                        'deployment_time': result[3].isoformat() if result[3] else None,
                        'performance_before': json.loads(result[4]) if result[4] else None,
                        'performance_after': json.loads(result[5]) if result[5] else None,
                        'rollback_time': result[6].isoformat() if result[6] else None,
                        'rollback_reason': result[7]
                    }
        
        except Exception as e:
            logger.error(f"Failed to get deployment status: {e}")
        
        return None