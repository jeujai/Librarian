"""
A/B Testing Framework for Configuration Optimization.

This module implements A/B testing capabilities for domain configurations,
including test design, execution, statistical analysis, and automated deployment.
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import uuid
import numpy as np
from scipy import stats
import statistics
from collections import defaultdict

from ...models.chunking import DomainConfig, PerformanceMetrics
from ...database.connection import get_database_connection

logger = logging.getLogger(__name__)


@dataclass
class ABTestConfig:
    """Configuration for A/B testing."""
    min_sample_size: int = 50
    max_test_duration_days: int = 14
    significance_level: float = 0.05
    minimum_effect_size: float = 0.05
    power: float = 0.8
    early_stopping_enabled: bool = True
    early_stopping_check_interval_hours: int = 24


@dataclass
class ABTestResult:
    """Result of A/B testing configuration changes."""
    test_id: str
    domain_name: str
    control_config: DomainConfig
    test_config: DomainConfig
    control_performance: PerformanceMetrics
    test_performance: PerformanceMetrics
    sample_sizes: Dict[str, int]  # 'control' and 'test' sample sizes
    statistical_results: Dict[str, Any]
    improvement_score: float
    statistical_significance: float
    effect_size: float
    test_duration: timedelta
    winner: str  # 'control', 'test', or 'inconclusive'
    confidence_interval: Tuple[float, float]
    test_start: datetime
    test_end: datetime
    
    def is_significant_improvement(self, threshold: float = 0.05) -> bool:
        """Check if test shows significant improvement."""
        return (self.winner == 'test' and 
                self.statistical_significance >= (1.0 - threshold) and
                self.effect_size > 0.05)
    
    def get_recommendation(self) -> str:
        """Get deployment recommendation."""
        if self.is_significant_improvement():
            return "deploy_test_config"
        elif self.winner == 'control' and self.statistical_significance >= 0.95:
            return "keep_control_config"
        else:
            return "inconclusive_extend_test"


@dataclass
class ABTestMetrics:
    """Metrics collected during A/B testing."""
    test_id: str
    config_variant: str  # 'control' or 'test'
    metrics: PerformanceMetrics
    timestamp: datetime
    sample_id: str


class ABTestingFramework:
    """
    A/B testing framework for configuration optimization.
    
    Implements statistical A/B testing with proper sample size calculation,
    significance testing, and automated deployment decisions.
    """
    
    def __init__(self, config: ABTestConfig = None):
        """Initialize the A/B testing framework."""
        self.config = config or ABTestConfig()
        
        # Active tests tracking
        self.active_tests = {}
        self.test_metrics = defaultdict(list)
        
        # Statistical configuration
        self.metrics_weights = {
            'chunk_quality_score': 0.25,
            'bridge_success_rate': 0.20,
            'retrieval_effectiveness': 0.25,
            'user_satisfaction_score': 0.15,
            'processing_efficiency': 0.10,
            'boundary_quality': 0.05
        }
        
        logger.info("Initialized A/B Testing Framework")
    
    def design_ab_test(self, domain_name: str, control_config: DomainConfig,
                      test_config: DomainConfig, target_metrics: List[str] = None) -> str:
        """
        Design and start an A/B test for configuration comparison.
        
        Args:
            domain_name: Domain to test
            control_config: Current configuration (control)
            test_config: New configuration to test
            target_metrics: Specific metrics to focus on
            
        Returns:
            Test ID
        """
        test_id = str(uuid.uuid4())
        
        # Calculate required sample size
        required_sample_size = self._calculate_sample_size(
            effect_size=self.config.minimum_effect_size,
            power=self.config.power,
            significance_level=self.config.significance_level
        )
        
        # Create test record
        test_record = {
            'test_id': test_id,
            'domain_name': domain_name,
            'control_config': control_config,
            'test_config': test_config,
            'target_metrics': target_metrics or list(self.metrics_weights.keys()),
            'required_sample_size': required_sample_size,
            'start_time': datetime.now(),
            'status': 'active',
            'control_metrics': [],
            'test_metrics': []
        }
        
        self.active_tests[test_id] = test_record
        
        # Store in database
        self._store_ab_test(test_record)
        
        logger.info(f"Started A/B test {test_id} for domain {domain_name} "
                   f"with required sample size {required_sample_size}")
        
        return test_id
    
    def collect_test_metrics(self, test_id: str, config_variant: str,
                           performance_metrics: PerformanceMetrics) -> None:
        """
        Collect performance metrics for an active A/B test.
        
        Args:
            test_id: ID of the test
            config_variant: 'control' or 'test'
            performance_metrics: Performance metrics to record
        """
        if test_id not in self.active_tests:
            logger.warning(f"Test {test_id} not found in active tests")
            return
        
        # Create metrics record
        metrics_record = ABTestMetrics(
            test_id=test_id,
            config_variant=config_variant,
            metrics=performance_metrics,
            timestamp=datetime.now(),
            sample_id=str(uuid.uuid4())
        )
        
        # Store metrics
        self.test_metrics[test_id].append(metrics_record)
        self.active_tests[test_id][f'{config_variant}_metrics'].append(metrics_record)
        
        # Store in database
        self._store_test_metrics(metrics_record)
        
        # Check if we should analyze results
        if self._should_analyze_test(test_id):
            self._analyze_test_results(test_id)
    
    def analyze_test_results(self, test_id: str) -> Optional[ABTestResult]:
        """
        Analyze A/B test results and determine statistical significance.
        
        Args:
            test_id: ID of the test to analyze
            
        Returns:
            Test results or None if insufficient data
        """
        if test_id not in self.active_tests:
            logger.error(f"Test {test_id} not found")
            return None
        
        return self._analyze_test_results(test_id)
    
    def get_deployment_recommendation(self, test_id: str) -> Optional[str]:
        """
        Get deployment recommendation based on test results.
        
        Args:
            test_id: ID of the test
            
        Returns:
            Deployment recommendation
        """
        result = self.analyze_test_results(test_id)
        if result:
            return result.get_recommendation()
        return None
    
    def deploy_winning_configuration(self, test_id: str) -> bool:
        """
        Deploy the winning configuration from an A/B test.
        
        Args:
            test_id: ID of the test
            
        Returns:
            True if deployment was successful
        """
        result = self.analyze_test_results(test_id)
        if not result:
            return False
        
        recommendation = result.get_recommendation()
        
        if recommendation == "deploy_test_config":
            # Deploy test configuration
            success = self._deploy_configuration(result.domain_name, result.test_config)
            if success:
                self._complete_test(test_id, 'deployed_test')
                logger.info(f"Deployed test configuration for domain {result.domain_name}")
            return success
        
        elif recommendation == "keep_control_config":
            # Keep control configuration
            self._complete_test(test_id, 'kept_control')
            logger.info(f"Kept control configuration for domain {result.domain_name}")
            return True
        
        else:
            # Inconclusive - extend test or manual review
            logger.info(f"Test {test_id} inconclusive, requires manual review")
            return False
    
    def _calculate_sample_size(self, effect_size: float, power: float, 
                             significance_level: float) -> int:
        """Calculate required sample size for A/B test."""
        
        # Using Cohen's formula for sample size calculation
        # This is a simplified version - in practice would use more sophisticated methods
        
        alpha = significance_level
        beta = 1 - power
        
        # Z-scores for alpha and beta
        z_alpha = stats.norm.ppf(1 - alpha/2)
        z_beta = stats.norm.ppf(power)
        
        # Sample size calculation (per group)
        sample_size = 2 * ((z_alpha + z_beta) / effect_size) ** 2
        
        # Apply minimum sample size
        return max(int(sample_size), self.config.min_sample_size)
    
    def _should_analyze_test(self, test_id: str) -> bool:
        """Check if test should be analyzed."""
        test_record = self.active_tests[test_id]
        
        # Check if we have minimum sample size
        control_count = len(test_record['control_metrics'])
        test_count = len(test_record['test_metrics'])
        min_samples = test_record['required_sample_size']
        
        if control_count >= min_samples and test_count >= min_samples:
            return True
        
        # Check if test duration exceeded
        test_duration = datetime.now() - test_record['start_time']
        if test_duration.days >= self.config.max_test_duration_days:
            return True
        
        # Check for early stopping
        if (self.config.early_stopping_enabled and 
            control_count >= self.config.min_sample_size and 
            test_count >= self.config.min_sample_size):
            
            # Check every 24 hours
            hours_since_start = test_duration.total_seconds() / 3600
            if hours_since_start >= self.config.early_stopping_check_interval_hours:
                return True
        
        return False
    
    def _analyze_test_results(self, test_id: str) -> Optional[ABTestResult]:
        """Analyze test results with statistical significance testing."""
        test_record = self.active_tests[test_id]
        
        control_metrics = test_record['control_metrics']
        test_metrics = test_record['test_metrics']
        
        if not control_metrics or not test_metrics:
            return None
        
        # Calculate aggregate performance scores
        control_scores = [self._calculate_aggregate_score(m.metrics) for m in control_metrics]
        test_scores = [self._calculate_aggregate_score(m.metrics) for m in test_metrics]
        
        # Statistical analysis
        control_mean = np.mean(control_scores)
        test_mean = np.mean(test_scores)
        
        # Perform t-test
        t_stat, p_value = stats.ttest_ind(test_scores, control_scores)
        
        # Calculate effect size (Cohen's d)
        pooled_std = np.sqrt(((len(control_scores) - 1) * np.var(control_scores, ddof=1) +
                             (len(test_scores) - 1) * np.var(test_scores, ddof=1)) /
                            (len(control_scores) + len(test_scores) - 2))
        
        effect_size = (test_mean - control_mean) / pooled_std if pooled_std > 0 else 0
        
        # Determine winner
        if p_value < self.config.significance_level:
            if test_mean > control_mean:
                winner = 'test'
            else:
                winner = 'control'
        else:
            winner = 'inconclusive'
        
        # Calculate confidence interval
        se = pooled_std * np.sqrt(1/len(control_scores) + 1/len(test_scores))
        margin_of_error = stats.t.ppf(1 - self.config.significance_level/2, 
                                     len(control_scores) + len(test_scores) - 2) * se
        
        diff = test_mean - control_mean
        confidence_interval = (diff - margin_of_error, diff + margin_of_error)
        
        # Create result
        result = ABTestResult(
            test_id=test_id,
            domain_name=test_record['domain_name'],
            control_config=test_record['control_config'],
            test_config=test_record['test_config'],
            control_performance=self._calculate_average_performance(control_metrics),
            test_performance=self._calculate_average_performance(test_metrics),
            sample_sizes={'control': len(control_metrics), 'test': len(test_metrics)},
            statistical_results={
                't_statistic': t_stat,
                'p_value': p_value,
                'degrees_of_freedom': len(control_scores) + len(test_scores) - 2
            },
            improvement_score=diff,
            statistical_significance=1 - p_value,
            effect_size=abs(effect_size),
            test_duration=datetime.now() - test_record['start_time'],
            winner=winner,
            confidence_interval=confidence_interval,
            test_start=test_record['start_time'],
            test_end=datetime.now()
        )
        
        # Store results
        self._store_test_results(result)
        
        return result
    
    def _calculate_aggregate_score(self, metrics: PerformanceMetrics) -> float:
        """Calculate weighted aggregate performance score."""
        score = 0.0
        for metric_name, weight in self.metrics_weights.items():
            value = getattr(metrics, metric_name, 0.0)
            score += value * weight
        return score
    
    def _calculate_average_performance(self, metrics_list: List[ABTestMetrics]) -> PerformanceMetrics:
        """Calculate average performance metrics."""
        if not metrics_list:
            return PerformanceMetrics()
        
        # Calculate averages for each metric
        chunk_quality_scores = [m.metrics.chunk_quality_score for m in metrics_list]
        bridge_success_rates = [m.metrics.bridge_success_rate for m in metrics_list]
        retrieval_effectiveness = [m.metrics.retrieval_effectiveness for m in metrics_list]
        user_satisfaction_scores = [m.metrics.user_satisfaction_score for m in metrics_list]
        processing_efficiency = [m.metrics.processing_efficiency for m in metrics_list]
        boundary_quality = [m.metrics.boundary_quality for m in metrics_list]
        
        return PerformanceMetrics(
            chunk_quality_score=np.mean(chunk_quality_scores),
            bridge_success_rate=np.mean(bridge_success_rates),
            retrieval_effectiveness=np.mean(retrieval_effectiveness),
            user_satisfaction_score=np.mean(user_satisfaction_scores),
            processing_efficiency=np.mean(processing_efficiency),
            boundary_quality=np.mean(boundary_quality),
            measurement_date=datetime.now(),
            document_count=sum(m.metrics.document_count for m in metrics_list)
        )
    
    def _deploy_configuration(self, domain_name: str, config: DomainConfig) -> bool:
        """Deploy a configuration to production."""
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
                    'ab_test_winner', config.confidence_score, datetime.now()
                ))
                
                conn.commit()
                return True
        
        except Exception as e:
            logger.error(f"Failed to deploy configuration: {e}")
            return False
    
    def _complete_test(self, test_id: str, outcome: str) -> None:
        """Mark test as complete."""
        if test_id in self.active_tests:
            self.active_tests[test_id]['status'] = 'completed'
            self.active_tests[test_id]['outcome'] = outcome
            self.active_tests[test_id]['end_time'] = datetime.now()
    
    def _store_ab_test(self, test_record: Dict[str, Any]) -> None:
        """Store A/B test record in database."""
        try:
            with get_database_connection() as conn:
                cursor = conn.cursor()
                
                # Create table if it doesn't exist
                create_table_query = """
                CREATE TABLE IF NOT EXISTS ab_tests (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    test_id VARCHAR(100) UNIQUE NOT NULL,
                    domain_name VARCHAR(100) NOT NULL,
                    control_config JSONB NOT NULL,
                    test_config JSONB NOT NULL,
                    target_metrics TEXT[],
                    required_sample_size INTEGER,
                    start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    end_time TIMESTAMP,
                    status VARCHAR(20) DEFAULT 'active',
                    outcome VARCHAR(50)
                )
                """
                cursor.execute(create_table_query)
                
                insert_query = """
                INSERT INTO ab_tests 
                (test_id, domain_name, control_config, test_config, 
                 target_metrics, required_sample_size, start_time, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """
                
                cursor.execute(insert_query, (
                    test_record['test_id'], test_record['domain_name'],
                    json.dumps(test_record['control_config'].to_dict()),
                    json.dumps(test_record['test_config'].to_dict()),
                    test_record['target_metrics'], test_record['required_sample_size'],
                    test_record['start_time'], test_record['status']
                ))
                
                conn.commit()
        
        except Exception as e:
            logger.error(f"Failed to store A/B test: {e}")
    
    def _store_test_metrics(self, metrics: ABTestMetrics) -> None:
        """Store test metrics in database."""
        try:
            with get_database_connection() as conn:
                cursor = conn.cursor()
                
                # Create table if it doesn't exist
                create_table_query = """
                CREATE TABLE IF NOT EXISTS ab_test_metrics (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    test_id VARCHAR(100) NOT NULL,
                    config_variant VARCHAR(20) NOT NULL,
                    sample_id VARCHAR(100) NOT NULL,
                    chunk_quality_score FLOAT,
                    bridge_success_rate FLOAT,
                    retrieval_effectiveness FLOAT,
                    user_satisfaction_score FLOAT,
                    processing_efficiency FLOAT,
                    boundary_quality FLOAT,
                    document_count INTEGER,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
                cursor.execute(create_table_query)
                
                insert_query = """
                INSERT INTO ab_test_metrics 
                (test_id, config_variant, sample_id, chunk_quality_score,
                 bridge_success_rate, retrieval_effectiveness, user_satisfaction_score,
                 processing_efficiency, boundary_quality, document_count, timestamp)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                
                cursor.execute(insert_query, (
                    metrics.test_id, metrics.config_variant, metrics.sample_id,
                    metrics.metrics.chunk_quality_score, metrics.metrics.bridge_success_rate,
                    metrics.metrics.retrieval_effectiveness, metrics.metrics.user_satisfaction_score,
                    metrics.metrics.processing_efficiency, metrics.metrics.boundary_quality,
                    metrics.metrics.document_count, metrics.timestamp
                ))
                
                conn.commit()
        
        except Exception as e:
            logger.error(f"Failed to store test metrics: {e}")
    
    def _store_test_results(self, result: ABTestResult) -> None:
        """Store test results in database."""
        try:
            with get_database_connection() as conn:
                cursor = conn.cursor()
                
                # Create table if it doesn't exist
                create_table_query = """
                CREATE TABLE IF NOT EXISTS ab_test_results (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    test_id VARCHAR(100) UNIQUE NOT NULL,
                    domain_name VARCHAR(100) NOT NULL,
                    winner VARCHAR(20) NOT NULL,
                    improvement_score FLOAT,
                    statistical_significance FLOAT,
                    effect_size FLOAT,
                    p_value FLOAT,
                    confidence_interval_lower FLOAT,
                    confidence_interval_upper FLOAT,
                    control_sample_size INTEGER,
                    test_sample_size INTEGER,
                    test_duration_hours FLOAT,
                    test_start TIMESTAMP,
                    test_end TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
                cursor.execute(create_table_query)
                
                insert_query = """
                INSERT INTO ab_test_results 
                (test_id, domain_name, winner, improvement_score, statistical_significance,
                 effect_size, p_value, confidence_interval_lower, confidence_interval_upper,
                 control_sample_size, test_sample_size, test_duration_hours, 
                 test_start, test_end)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                
                cursor.execute(insert_query, (
                    result.test_id, result.domain_name, result.winner,
                    result.improvement_score, result.statistical_significance,
                    result.effect_size, result.statistical_results.get('p_value', 0.0),
                    result.confidence_interval[0], result.confidence_interval[1],
                    result.sample_sizes['control'], result.sample_sizes['test'],
                    result.test_duration.total_seconds() / 3600,
                    result.test_start, result.test_end
                ))
                
                conn.commit()
        
        except Exception as e:
            logger.error(f"Failed to store test results: {e}")