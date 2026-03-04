"""
Configuration Optimizer.

This module implements performance tracking, automated optimization strategy generation,
A/B testing for configuration improvements, and cross-domain learning capabilities.
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import uuid
import numpy as np
from collections import defaultdict, Counter

from ...models.chunking import (
    DomainConfig, PerformanceMetrics, OptimizationStrategy, OptimizationRecord
)
from ...database.connection import get_database_connection
from .performance_tracker import PerformanceTracker
from .feedback_integrator import FeedbackIntegrator
from .ab_testing import ABTestingFramework
from .deployment_manager import DeploymentManager
from .cross_domain_learner import CrossDomainLearner
from .kg_config_updater import KnowledgeGraphConfigUpdater

logger = logging.getLogger(__name__)


@dataclass
class PerformanceAnalysis:
    """Analysis of performance metrics for optimization."""
    domain_name: str
    current_performance: PerformanceMetrics
    historical_performance: List[PerformanceMetrics]
    performance_trends: Dict[str, float]  # Metric name -> trend (positive/negative)
    identified_issues: List[str]
    improvement_opportunities: List[str]
    
    def get_overall_score(self) -> float:
        """Get overall performance score."""
        metrics = [
            self.current_performance.chunk_quality_score,
            self.current_performance.bridge_success_rate,
            self.current_performance.retrieval_effectiveness,
            self.current_performance.user_satisfaction_score,
            self.current_performance.processing_efficiency,
            self.current_performance.boundary_quality
        ]
        return sum(metrics) / len(metrics)


@dataclass
class ABTestResult:
    """Result of A/B testing configuration changes."""
    test_id: str
    domain_name: str
    control_config: DomainConfig
    test_config: DomainConfig
    control_performance: PerformanceMetrics
    test_performance: PerformanceMetrics
    improvement_score: float
    statistical_significance: float
    test_duration: timedelta
    sample_size: int
    winner: str  # 'control', 'test', or 'inconclusive'
    
    def is_significant_improvement(self, threshold: float = 0.05) -> bool:
        """Check if test shows significant improvement."""
        return (self.winner == 'test' and 
                self.statistical_significance >= (1.0 - threshold) and
                self.improvement_score > 0.1)


@dataclass
class CrossDomainPattern:
    """Pattern learned from successful optimizations across domains."""
    pattern_id: str
    pattern_type: str  # 'chunk_size', 'bridge_threshold', 'delimiter_adjustment'
    source_domains: List[str]
    optimization_changes: Dict[str, Any]
    success_rate: float
    applicability_conditions: Dict[str, Any]
    confidence_score: float
    
    def is_applicable_to_domain(self, domain_config: DomainConfig, 
                              performance_metrics: PerformanceMetrics) -> bool:
        """Check if pattern is applicable to a domain."""
        # Check applicability conditions
        for condition, expected_value in self.applicability_conditions.items():
            if condition == 'min_performance_threshold':
                overall_score = (
                    performance_metrics.chunk_quality_score +
                    performance_metrics.bridge_success_rate +
                    performance_metrics.retrieval_effectiveness
                ) / 3.0
                if overall_score >= expected_value:
                    continue
                else:
                    return False
            
            elif condition == 'content_type':
                # Would need content type information
                continue
            
            elif condition == 'config_similarity':
                # Check if domain config is similar enough
                continue
        
        return self.confidence_score >= 0.7


class ConfigurationOptimizer:
    """
    Configuration optimizer with performance tracking and cross-domain learning.
    
    Implements real-time performance monitoring, automated optimization strategy generation,
    A/B testing framework, and cross-domain pattern learning.
    """
    
    def __init__(self):
        """Initialize the configuration optimizer."""
        
        # Initialize performance tracking and feedback integration
        self.performance_tracker = PerformanceTracker()
        self.feedback_integrator = FeedbackIntegrator(self.performance_tracker)
        
        # Initialize A/B testing and deployment systems
        self.ab_testing = ABTestingFramework()
        self.deployment_manager = DeploymentManager()
        
        # Initialize cross-domain learning
        self.cross_domain_learner = CrossDomainLearner()
        
        # Initialize knowledge graph integration
        self.kg_config_updater = KnowledgeGraphConfigUpdater()
        
        # Performance tracking
        self.performance_history = defaultdict(list)
        self.active_ab_tests = {}
        
        # Cross-domain learning
        self.learned_patterns = []
        self.pattern_success_tracking = defaultdict(list)
        
        # Optimization thresholds
        self.optimization_thresholds = {
            'chunk_quality_threshold': 0.7,
            'bridge_success_threshold': 0.6,
            'retrieval_effectiveness_threshold': 0.75,
            'user_satisfaction_threshold': 0.7,
            'processing_efficiency_threshold': 0.8,
            'boundary_quality_threshold': 0.7
        }
        
        # A/B testing configuration
        self.ab_test_config = {
            'min_sample_size': 50,
            'max_test_duration_days': 14,
            'significance_threshold': 0.95,
            'minimum_improvement': 0.05
        }
        
        logger.info("Initialized Configuration Optimizer with Knowledge Graph Integration")
    
    def track_performance(self, domain_name: str, chunking_result: Dict[str, Any]) -> None:
        """
        Track real-time performance metrics for configuration optimization.
        
        Args:
            domain_name: Name of the domain
            chunking_result: Results from chunking operation
        """
        # Extract performance metrics from chunking result
        performance_metrics = PerformanceMetrics(
            chunk_quality_score=chunking_result.get('chunk_quality_score', 0.0),
            bridge_success_rate=chunking_result.get('bridge_success_rate', 0.0),
            retrieval_effectiveness=chunking_result.get('retrieval_effectiveness', 0.0),
            user_satisfaction_score=chunking_result.get('user_satisfaction_score', 0.0),
            processing_efficiency=chunking_result.get('processing_efficiency', 0.0),
            boundary_quality=chunking_result.get('boundary_quality', 0.0),
            measurement_date=datetime.now(),
            document_count=chunking_result.get('document_count', 1)
        )
        
        # Store in performance history
        self.performance_history[domain_name].append(performance_metrics)
        
        # Use performance tracker for comprehensive tracking
        self.performance_tracker.track_performance(domain_name, performance_metrics)
        
        # Check if optimization is needed
        if self._should_trigger_optimization(domain_name, performance_metrics):
            logger.info(f"Performance degradation detected for domain {domain_name}, triggering optimization")
            self._trigger_optimization(domain_name)
    
    def generate_optimization_strategies(self, performance_analysis: PerformanceAnalysis) -> List[OptimizationStrategy]:
        """
        Generate targeted optimization strategies based on performance analysis.
        
        Args:
            performance_analysis: Analysis of current performance
            
        Returns:
            List of optimization strategies
        """
        strategies = []
        current_perf = performance_analysis.current_performance
        
        # Strategy 1: Chunk size adjustment
        if current_perf.chunk_quality_score < self.optimization_thresholds['chunk_quality_threshold']:
            chunk_strategy = self._generate_chunk_size_strategy(performance_analysis)
            if chunk_strategy:
                strategies.append(chunk_strategy)
        
        # Strategy 2: Bridge threshold tuning
        if current_perf.bridge_success_rate < self.optimization_thresholds['bridge_success_threshold']:
            bridge_strategy = self._generate_bridge_threshold_strategy(performance_analysis)
            if bridge_strategy:
                strategies.append(bridge_strategy)
        
        # Strategy 3: Delimiter refinement
        if current_perf.boundary_quality < self.optimization_thresholds['boundary_quality_threshold']:
            delimiter_strategy = self._generate_delimiter_strategy(performance_analysis)
            if delimiter_strategy:
                strategies.append(delimiter_strategy)
        
        # Strategy 4: Processing efficiency optimization
        if current_perf.processing_efficiency < self.optimization_thresholds['processing_efficiency_threshold']:
            efficiency_strategy = self._generate_efficiency_strategy(performance_analysis)
            if efficiency_strategy:
                strategies.append(efficiency_strategy)
        
        # Strategy 5: Cross-domain pattern application
        cross_domain_strategies = self._generate_cross_domain_strategies(performance_analysis)
        strategies.extend(cross_domain_strategies)
        
        # Sort strategies by expected improvement
        strategies.sort(key=lambda s: s.expected_improvement, reverse=True)
        
        return strategies
    
    def a_b_test_configurations(self, domain_name: str, 
                              candidate_configs: List[DomainConfig]) -> DomainConfig:
        """
        A/B test configuration candidates and select best performer.
        
        Args:
            domain_name: Name of the domain
            candidate_configs: List of configuration candidates
            
        Returns:
            Best performing configuration
        """
        if not candidate_configs:
            raise ValueError("No candidate configurations provided")
        
        if len(candidate_configs) == 1:
            return candidate_configs[0]
        
        # Get current configuration as control
        control_config = self._get_current_config(domain_name)
        if not control_config:
            logger.warning(f"No current config found for {domain_name}, using first candidate as control")
            control_config = candidate_configs[0]
            candidate_configs = candidate_configs[1:]
        
        best_config = control_config
        best_result = None
        
        # Test each candidate configuration using the A/B testing framework
        for test_config in candidate_configs:
            test_id = self.ab_testing.design_ab_test(
                domain_name=domain_name,
                control_config=control_config,
                test_config=test_config,
                target_metrics=['chunk_quality_score', 'bridge_success_rate', 'retrieval_effectiveness']
            )
            
            # In a real implementation, this would run over time
            # For now, we'll simulate the test completion
            test_result = self._simulate_ab_test_completion(test_id, control_config, test_config)
            
            if test_result and test_result.is_significant_improvement():
                logger.info(f"A/B test shows significant improvement for {domain_name}: "
                           f"{test_result.improvement_score:.3f}")
                
                if (best_result is None or 
                    test_result.improvement_score > best_result.improvement_score):
                    best_config = test_config
                    best_result = test_result
        
        # Deploy winning configuration if found
        if best_result and best_result.winner == 'test':
            deployment_plan = self.deployment_manager.create_deployment_plan(
                domain_name=domain_name,
                target_config=best_config,
                deployment_strategy='gradual'
            )
            
            deployment_id = self.deployment_manager.execute_deployment(deployment_plan.plan_id)
            logger.info(f"Deployed winning configuration {deployment_id} for domain {domain_name}")
        
        return best_config
    
    def _generate_chunk_size_strategy(self, analysis: PerformanceAnalysis) -> Optional[OptimizationStrategy]:
        """Generate chunk size adjustment strategy."""
        current_perf = analysis.current_performance
        
        # Analyze chunk quality issues
        if current_perf.chunk_quality_score < 0.5:
            # Significant quality issues - try larger chunks
            adjustment_factor = 1.2
            expected_improvement = 0.15
        elif current_perf.chunk_quality_score < 0.7:
            # Moderate quality issues - small adjustment
            adjustment_factor = 1.1
            expected_improvement = 0.08
        else:
            return None
        
        return OptimizationStrategy(
            type="chunk_size_adjustment",
            target_metrics=["chunk_quality_score", "boundary_quality"],
            adjustments={
                "size_multiplier": adjustment_factor,
                "preserve_boundaries": True
            },
            expected_improvement=expected_improvement,
            confidence=0.7
        )
    
    def _generate_bridge_threshold_strategy(self, analysis: PerformanceAnalysis) -> Optional[OptimizationStrategy]:
        """Generate bridge threshold tuning strategy."""
        current_perf = analysis.current_performance
        
        if current_perf.bridge_success_rate < 0.4:
            # Very low success rate - lower thresholds significantly
            threshold_adjustment = -0.1
            expected_improvement = 0.2
        elif current_perf.bridge_success_rate < 0.6:
            # Moderate success rate - small adjustment
            threshold_adjustment = -0.05
            expected_improvement = 0.1
        else:
            return None
        
        return OptimizationStrategy(
            type="bridge_threshold_tuning",
            target_metrics=["bridge_success_rate"],
            adjustments={
                "threshold_adjustment": threshold_adjustment,
                "adaptive_thresholds": True
            },
            expected_improvement=expected_improvement,
            confidence=0.8
        )
    
    def _generate_delimiter_strategy(self, analysis: PerformanceAnalysis) -> Optional[OptimizationStrategy]:
        """Generate delimiter refinement strategy."""
        current_perf = analysis.current_performance
        
        if current_perf.boundary_quality < 0.6:
            return OptimizationStrategy(
                type="delimiter_refinement",
                target_metrics=["boundary_quality", "chunk_quality_score"],
                adjustments={
                    "add_semantic_delimiters": True,
                    "increase_delimiter_priority": True,
                    "content_specific_patterns": True
                },
                expected_improvement=0.12,
                confidence=0.6
            )
        
        return None
    
    def _generate_efficiency_strategy(self, analysis: PerformanceAnalysis) -> Optional[OptimizationStrategy]:
        """Generate processing efficiency optimization strategy."""
        current_perf = analysis.current_performance
        
        if current_perf.processing_efficiency < 0.7:
            return OptimizationStrategy(
                type="processing_optimization",
                target_metrics=["processing_efficiency"],
                adjustments={
                    "batch_processing": True,
                    "cache_optimizations": True,
                    "parallel_processing": True
                },
                expected_improvement=0.15,
                confidence=0.7
            )
        
        return None
    
    def _generate_cross_domain_strategies(self, analysis: PerformanceAnalysis) -> List[OptimizationStrategy]:
        """Generate strategies based on cross-domain learning."""
        
        # Use the cross-domain learner to generate strategies
        current_config = self._get_current_config(analysis.domain_name)
        if current_config:
            return self.cross_domain_learner.generate_cross_domain_strategies(
                analysis.domain_name, current_config, analysis.current_performance
            )
        
        return []
    
    def _should_trigger_optimization(self, domain_name: str, 
                                   performance_metrics: PerformanceMetrics) -> bool:
        """Check if optimization should be triggered."""
        
        # Check if any metric is below threshold
        metrics_below_threshold = [
            performance_metrics.chunk_quality_score < self.optimization_thresholds['chunk_quality_threshold'],
            performance_metrics.bridge_success_rate < self.optimization_thresholds['bridge_success_threshold'],
            performance_metrics.retrieval_effectiveness < self.optimization_thresholds['retrieval_effectiveness_threshold'],
            performance_metrics.user_satisfaction_score < self.optimization_thresholds['user_satisfaction_threshold'],
            performance_metrics.processing_efficiency < self.optimization_thresholds['processing_efficiency_threshold'],
            performance_metrics.boundary_quality < self.optimization_thresholds['boundary_quality_threshold']
        ]
        
        # Trigger if 2 or more metrics are below threshold
        return sum(metrics_below_threshold) >= 2
    
    def _trigger_optimization(self, domain_name: str):
        """Trigger optimization process for a domain."""
        
        # Get performance analysis
        performance_analysis = self._analyze_domain_performance(domain_name)
        
        # Generate optimization strategies
        strategies = self.generate_optimization_strategies(performance_analysis)
        
        if strategies:
            logger.info(f"Generated {len(strategies)} optimization strategies for {domain_name}")
            
            # Apply top strategy (could be extended to test multiple)
            top_strategy = strategies[0]
            self._apply_optimization_strategy(domain_name, top_strategy)
    
    def _analyze_domain_performance(self, domain_name: str) -> PerformanceAnalysis:
        """Analyze performance for a domain."""
        
        # Get historical performance
        historical_performance = self.performance_history.get(domain_name, [])
        
        if not historical_performance:
            # Create default analysis
            return PerformanceAnalysis(
                domain_name=domain_name,
                current_performance=PerformanceMetrics(),
                historical_performance=[],
                performance_trends={},
                identified_issues=["No historical data"],
                improvement_opportunities=["Establish baseline performance"]
            )
        
        current_performance = historical_performance[-1]
        
        # Calculate trends
        performance_trends = {}
        if len(historical_performance) >= 2:
            recent_metrics = historical_performance[-5:]  # Last 5 measurements
            
            for metric_name in ['chunk_quality_score', 'bridge_success_rate', 'retrieval_effectiveness']:
                values = [getattr(m, metric_name) for m in recent_metrics]
                if len(values) >= 2:
                    trend = (values[-1] - values[0]) / len(values)
                    performance_trends[metric_name] = trend
        
        # Identify issues
        identified_issues = []
        improvement_opportunities = []
        
        if current_performance.chunk_quality_score < 0.7:
            identified_issues.append("Low chunk quality")
            improvement_opportunities.append("Optimize chunk size and boundaries")
        
        if current_performance.bridge_success_rate < 0.6:
            identified_issues.append("Low bridge success rate")
            improvement_opportunities.append("Adjust bridge generation thresholds")
        
        if current_performance.processing_efficiency < 0.8:
            identified_issues.append("Low processing efficiency")
            improvement_opportunities.append("Implement performance optimizations")
        
        return PerformanceAnalysis(
            domain_name=domain_name,
            current_performance=current_performance,
            historical_performance=historical_performance,
            performance_trends=performance_trends,
            identified_issues=identified_issues,
            improvement_opportunities=improvement_opportunities
        )
    
    def _apply_optimization_strategy(self, domain_name: str, strategy: OptimizationStrategy):
        """Apply an optimization strategy to a domain configuration."""
        
        # This would integrate with the config manager to apply changes
        logger.info(f"Applying optimization strategy '{strategy.type}' to domain {domain_name}")
        
        # Record the optimization attempt
        optimization_record = OptimizationRecord(
            optimization_id=str(uuid.uuid4()),
            optimization_type=strategy.type,
            changes_made=strategy.adjustments,
            improvement_score=0.0,  # Will be updated after measuring results
            timestamp=datetime.now()
        )
        
        # Store optimization record
        self._store_optimization_record(domain_name, optimization_record)
    
    def _simulate_ab_test_completion(self, test_id: str, control_config: DomainConfig, 
                                   test_config: DomainConfig):
        """Simulate A/B test completion for demonstration purposes."""
        # In a real implementation, this would collect actual performance data over time
        
        # Generate mock performance data
        control_performance = PerformanceMetrics(
            chunk_quality_score=0.65 + np.random.normal(0, 0.05),
            bridge_success_rate=0.55 + np.random.normal(0, 0.05),
            retrieval_effectiveness=0.70 + np.random.normal(0, 0.05),
            user_satisfaction_score=0.68 + np.random.normal(0, 0.05),
            processing_efficiency=0.75 + np.random.normal(0, 0.05),
            boundary_quality=0.62 + np.random.normal(0, 0.05)
        )
        
        # Test configuration shows improvement
        improvement_factor = 1.1  # 10% improvement
        test_performance = PerformanceMetrics(
            chunk_quality_score=min(1.0, control_performance.chunk_quality_score * improvement_factor),
            bridge_success_rate=min(1.0, control_performance.bridge_success_rate * improvement_factor),
            retrieval_effectiveness=min(1.0, control_performance.retrieval_effectiveness * improvement_factor),
            user_satisfaction_score=min(1.0, control_performance.user_satisfaction_score * improvement_factor),
            processing_efficiency=min(1.0, control_performance.processing_efficiency * improvement_factor),
            boundary_quality=min(1.0, control_performance.boundary_quality * improvement_factor)
        )
        
        # Simulate collecting metrics
        for i in range(60):  # 60 samples
            self.ab_testing.collect_test_metrics(test_id, 'control', control_performance)
            self.ab_testing.collect_test_metrics(test_id, 'test', test_performance)
        
        # Analyze results
        return self.ab_testing.analyze_test_results(test_id)
        """Run A/B test between two configurations."""
        
        test_id = str(uuid.uuid4())
        
        # Simulate A/B test (in real implementation, this would involve actual testing)
        # For now, we'll create a mock result
        
        # Mock performance metrics
        control_performance = PerformanceMetrics(
            chunk_quality_score=0.65,
            bridge_success_rate=0.55,
            retrieval_effectiveness=0.70,
            user_satisfaction_score=0.68,
            processing_efficiency=0.75,
            boundary_quality=0.62
        )
        
        test_performance = PerformanceMetrics(
            chunk_quality_score=0.72,
            bridge_success_rate=0.68,
            retrieval_effectiveness=0.75,
            user_satisfaction_score=0.74,
            processing_efficiency=0.78,
            boundary_quality=0.69
        )
        
        # Calculate improvement
        control_avg = (control_performance.chunk_quality_score + 
                      control_performance.bridge_success_rate + 
                      control_performance.retrieval_effectiveness) / 3.0
        
        test_avg = (test_performance.chunk_quality_score + 
                   test_performance.bridge_success_rate + 
                   test_performance.retrieval_effectiveness) / 3.0
        
        improvement_score = test_avg - control_avg
        
        # Mock statistical significance
        statistical_significance = 0.95 if improvement_score > 0.05 else 0.80
        
        winner = "test" if improvement_score > 0.05 and statistical_significance >= 0.95 else "control"
        
    def deploy_optimized_configuration(self, domain_name: str, 
                                     optimized_config: DomainConfig,
                                     deployment_strategy: str = 'gradual') -> str:
        """
        Deploy an optimized configuration with automated rollback capabilities.
        
        Args:
            domain_name: Domain to deploy to
            optimized_config: Optimized configuration to deploy
            deployment_strategy: Deployment strategy ('immediate', 'gradual', 'canary')
            
        Returns:
            Deployment ID
        """
        # Create deployment plan
        deployment_plan = self.deployment_manager.create_deployment_plan(
            domain_name=domain_name,
            target_config=optimized_config,
            deployment_strategy=deployment_strategy,
            approval_required=False  # Automated deployment
        )
        
        # Execute deployment
        deployment_id = self.deployment_manager.execute_deployment(deployment_plan.plan_id)
        
        logger.info(f"Deployed optimized configuration {deployment_id} for domain {domain_name}")
        
        return deployment_id
    
    def monitor_and_rollback_if_needed(self, deployment_id: str) -> bool:
        """
        Monitor deployment and rollback if performance degrades.
        
        Args:
            deployment_id: ID of the deployment to monitor
            
        Returns:
            True if deployment is healthy, False if rolled back
        """
        return self.deployment_manager.monitor_deployment(deployment_id)
    
    def _get_current_config(self, domain_name: str) -> Optional[DomainConfig]:
        """Get current configuration for a domain."""
        # This would integrate with the config manager
        return None
    
    def _store_performance_metrics(self, domain_name: str, metrics: PerformanceMetrics):
        """Store performance metrics in database."""
        try:
            with get_database_connection() as conn:
                cursor = conn.cursor()
                
                insert_query = """
                INSERT INTO performance_metrics 
                (domain_name, chunk_quality_score, bridge_success_rate, 
                 retrieval_effectiveness, user_satisfaction_score, 
                 processing_efficiency, boundary_quality, measurement_date, document_count)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                
                cursor.execute(insert_query, (
                    domain_name, metrics.chunk_quality_score, metrics.bridge_success_rate,
                    metrics.retrieval_effectiveness, metrics.user_satisfaction_score,
                    metrics.processing_efficiency, metrics.boundary_quality,
                    metrics.measurement_date, metrics.document_count
                ))
                
                conn.commit()
        
        except Exception as e:
            logger.error(f"Failed to store performance metrics: {e}")
    
    def _store_optimization_record(self, domain_name: str, record: OptimizationRecord):
        """Store optimization record in database."""
        try:
            with get_database_connection() as conn:
                cursor = conn.cursor()
                
                insert_query = """
                INSERT INTO optimization_records 
                (domain_name, optimization_id, optimization_type, changes_made, 
                 improvement_score, timestamp)
                VALUES (%s, %s, %s, %s, %s, %s)
                """
                
                cursor.execute(insert_query, (
                    domain_name, record.optimization_id, record.optimization_type,
                    json.dumps(record.changes_made), record.improvement_score,
                    record.timestamp
                ))
                
                conn.commit()
        
        except Exception as e:
            logger.error(f"Failed to store optimization record: {e}")
    
    def _store_ab_test_result(self, result: ABTestResult):
        """Store A/B test result in database."""
        try:
            with get_database_connection() as conn:
                cursor = conn.cursor()
                
                insert_query = """
                INSERT INTO ab_test_results 
                (test_id, domain_name, improvement_score, statistical_significance,
                 test_duration_days, sample_size, winner, test_date)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """
                
                cursor.execute(insert_query, (
                    result.test_id, result.domain_name, result.improvement_score,
                    result.statistical_significance, result.test_duration.days,
                    result.sample_size, result.winner, datetime.now()
                ))
                
                conn.commit()
        
        except Exception as e:
            logger.error(f"Failed to store A/B test result: {e}")
    
    def learn_cross_domain_patterns(self):
        """Extract and learn optimization patterns across domains."""
        
        # Get successful optimizations from database
        successful_optimizations = self._get_successful_optimizations()
        
        # Group by optimization type
        optimization_groups = defaultdict(list)
        for opt in successful_optimizations:
            optimization_groups[opt['optimization_type']].append(opt)
        
        # Extract patterns
        for opt_type, optimizations in optimization_groups.items():
            if len(optimizations) >= 3:  # Need at least 3 examples
                pattern = self._extract_optimization_pattern(opt_type, optimizations)
                if pattern:
                    self.learned_patterns.append(pattern)
        
        logger.info(f"Learned {len(self.learned_patterns)} cross-domain patterns")
    
    def _get_successful_optimizations(self) -> List[Dict[str, Any]]:
        """Get successful optimizations from database."""
        try:
            with get_database_connection() as conn:
                cursor = conn.cursor()
                
                query = """
                SELECT domain_name, optimization_type, changes_made, improvement_score
                FROM optimization_records 
                WHERE improvement_score > 0.1
                ORDER BY improvement_score DESC
                LIMIT 100
                """
                
                cursor.execute(query)
                results = cursor.fetchall()
                
                optimizations = []
                for row in results:
                    optimizations.append({
                        'domain_name': row[0],
                        'optimization_type': row[1],
                        'changes_made': json.loads(row[2]),
                        'improvement_score': row[3]
                    })
                
                return optimizations
        
        except Exception as e:
            logger.error(f"Failed to get successful optimizations: {e}")
            return []
    
    def _extract_optimization_pattern(self, opt_type: str, 
                                    optimizations: List[Dict[str, Any]]) -> Optional[CrossDomainPattern]:
        """Extract a cross-domain pattern from successful optimizations."""
        
        # Find common changes
        all_changes = [opt['changes_made'] for opt in optimizations]
        common_changes = {}
        
        # Find changes that appear in most optimizations
        for changes in all_changes:
            for key, value in changes.items():
                if key not in common_changes:
                    common_changes[key] = []
                common_changes[key].append(value)
        
        # Keep changes that appear in at least 60% of optimizations
        pattern_changes = {}
        for key, values in common_changes.items():
            if len(values) >= len(optimizations) * 0.6:
                # Use most common value
                if isinstance(values[0], (int, float)):
                    pattern_changes[key] = np.mean(values)
                else:
                    pattern_changes[key] = Counter(values).most_common(1)[0][0]
        
        if not pattern_changes:
            return None
        
        # Calculate success rate
        success_rate = np.mean([opt['improvement_score'] for opt in optimizations])
        
        # Extract source domains
        source_domains = list(set(opt['domain_name'] for opt in optimizations))
        
        return CrossDomainPattern(
            pattern_id=str(uuid.uuid4()),
            pattern_type=opt_type,
            source_domains=source_domains,
            optimization_changes=pattern_changes,
            success_rate=success_rate,
            applicability_conditions={
                'min_performance_threshold': 0.6,
                'min_sample_size': len(optimizations)
            },
            confidence_score=min(0.9, success_rate + 0.1)
        )
    def _simulate_ab_test_completion(self, test_id: str, control_config: DomainConfig, 
                                   test_config: DomainConfig):
        """Simulate A/B test completion for demonstration purposes."""
        # In a real implementation, this would collect actual performance data over time
        
        # Generate mock performance data
        control_performance = PerformanceMetrics(
            chunk_quality_score=0.65 + np.random.normal(0, 0.05),
            bridge_success_rate=0.55 + np.random.normal(0, 0.05),
            retrieval_effectiveness=0.70 + np.random.normal(0, 0.05),
            user_satisfaction_score=0.68 + np.random.normal(0, 0.05),
            processing_efficiency=0.75 + np.random.normal(0, 0.05),
            boundary_quality=0.62 + np.random.normal(0, 0.05)
        )
        
        # Test configuration shows improvement
        improvement_factor = 1.1  # 10% improvement
        test_performance = PerformanceMetrics(
            chunk_quality_score=min(1.0, control_performance.chunk_quality_score * improvement_factor),
            bridge_success_rate=min(1.0, control_performance.bridge_success_rate * improvement_factor),
            retrieval_effectiveness=min(1.0, control_performance.retrieval_effectiveness * improvement_factor),
            user_satisfaction_score=min(1.0, control_performance.user_satisfaction_score * improvement_factor),
            processing_efficiency=min(1.0, control_performance.processing_efficiency * improvement_factor),
            boundary_quality=min(1.0, control_performance.boundary_quality * improvement_factor)
        )
        
        # Simulate collecting metrics
        for i in range(60):  # 60 samples
            self.ab_testing.collect_test_metrics(test_id, 'control', control_performance)
            self.ab_testing.collect_test_metrics(test_id, 'test', test_performance)
        
        # Analyze results
        return self.ab_testing.analyze_test_results(test_id)
    
    def deploy_optimized_configuration(self, domain_name: str, 
                                     optimized_config: DomainConfig,
                                     deployment_strategy: str = 'gradual') -> str:
        """
        Deploy an optimized configuration with automated rollback capabilities.
        
        Args:
            domain_name: Domain to deploy to
            optimized_config: Optimized configuration to deploy
            deployment_strategy: Deployment strategy ('immediate', 'gradual', 'canary')
            
        Returns:
            Deployment ID
        """
        # Create deployment plan
        deployment_plan = self.deployment_manager.create_deployment_plan(
            domain_name=domain_name,
            target_config=optimized_config,
            deployment_strategy=deployment_strategy,
            approval_required=False  # Automated deployment
        )
        
        # Execute deployment
        deployment_id = self.deployment_manager.execute_deployment(deployment_plan.plan_id)
        
        logger.info(f"Deployed optimized configuration {deployment_id} for domain {domain_name}")
        
        return deployment_id
    
    def monitor_and_rollback_if_needed(self, deployment_id: str) -> bool:
        """
        Monitor deployment and rollback if performance degrades.
        
        Args:
            deployment_id: ID of the deployment to monitor
            
        Returns:
            True if deployment is healthy, False if rolled back
        """
        return self.deployment_manager.monitor_deployment(deployment_id)
    def extract_and_learn_patterns(self, lookback_days: int = 30) -> List[str]:
        """
        Extract optimization patterns from recent successful optimizations.
        
        Args:
            lookback_days: Number of days to look back for optimization data
            
        Returns:
            List of newly learned pattern IDs
        """
        new_patterns = self.cross_domain_learner.extract_optimization_patterns(lookback_days)
        pattern_ids = [p.pattern_id for p in new_patterns]
        
        logger.info(f"Learned {len(new_patterns)} new cross-domain patterns")
        
        return pattern_ids
    
    def apply_cross_domain_pattern(self, pattern_id: str, domain_name: str) -> Optional[str]:
        """
        Apply a cross-domain pattern to a specific domain.
        
        Args:
            pattern_id: ID of the pattern to apply
            domain_name: Name of the domain to apply to
            
        Returns:
            Deployment ID if successful, None otherwise
        """
        # Get current configuration and performance
        current_config = self._get_current_config(domain_name)
        current_performance = self._get_current_performance(domain_name)
        
        if not current_config or not current_performance:
            logger.error(f"Could not get current state for domain {domain_name}")
            return None
        
        # Apply pattern
        modified_config = self.cross_domain_learner.apply_pattern_to_domain(
            pattern_id, domain_name, current_config, current_performance
        )
        
        if not modified_config:
            logger.error(f"Failed to apply pattern {pattern_id} to domain {domain_name}")
            return None
        
        # Deploy the modified configuration
        deployment_id = self.deploy_optimized_configuration(
            domain_name, modified_config, deployment_strategy='gradual'
        )
        
        return deployment_id
    
    def evaluate_pattern_effectiveness(self) -> Dict[str, float]:
        """
        Evaluate effectiveness of all learned patterns.
        
        Returns:
            Dictionary mapping pattern IDs to effectiveness scores
        """
        effectiveness_scores = {}
        
        for pattern_id in self.cross_domain_learner.learned_patterns.keys():
            effectiveness = self.cross_domain_learner.evaluate_pattern_effectiveness(pattern_id)
            effectiveness_scores[pattern_id] = effectiveness.effectiveness_score
        
        return effectiveness_scores
    
    def retire_ineffective_patterns(self) -> List[str]:
        """
        Retire patterns that are no longer effective.
        
        Returns:
            List of retired pattern IDs
        """
        return self.cross_domain_learner.retire_ineffective_patterns()
    
    def get_applicable_patterns(self, domain_name: str) -> List[Dict[str, Any]]:
        """
        Get patterns applicable to a specific domain.
        
        Args:
            domain_name: Name of the domain
            
        Returns:
            List of applicable pattern information
        """
        current_config = self._get_current_config(domain_name)
        current_performance = self._get_current_performance(domain_name)
        
        if not current_config or not current_performance:
            return []
        
        applicable_patterns = self.cross_domain_learner.assess_pattern_applicability(
            domain_name, current_config, current_performance
        )
        
        # Convert to serializable format
        pattern_info = []
        for pattern in applicable_patterns:
            pattern_info.append({
                'pattern_id': pattern.pattern_id,
                'pattern_type': pattern.pattern_type,
                'source_domains': pattern.source_domains,
                'success_rate': pattern.success_rate,
                'confidence_score': pattern.confidence_score,
                'expected_improvements': pattern.success_metrics,
                'application_count': pattern.application_count
            })
        
        return pattern_info
    
    def _get_current_performance(self, domain_name: str) -> Optional[PerformanceMetrics]:
        """Get current performance metrics for a domain."""
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
    def monitor_knowledge_graph_updates(self) -> Dict[str, List[str]]:
        """
        Monitor knowledge graphs and update configurations as needed.
        
        Returns:
            Dictionary mapping domain names to lists of applied update IDs
        """
        return self.kg_config_updater.monitor_and_update_configurations()
    
    def refresh_domain_knowledge(self, domain_name: str) -> bool:
        """
        Refresh knowledge profile for a domain from external knowledge graphs.
        
        Args:
            domain_name: Name of the domain to refresh
            
        Returns:
            True if refresh was successful
        """
        try:
            profile = self.kg_config_updater.refresh_domain_knowledge_profile(domain_name)
            logger.info(f"Refreshed knowledge profile for domain {domain_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to refresh knowledge for domain {domain_name}: {e}")
            return False
    
    def apply_knowledge_graph_updates(self, domain_name: str) -> List[str]:
        """
        Apply pending knowledge graph-based configuration updates for a domain.
        
        Args:
            domain_name: Name of the domain
            
        Returns:
            List of applied update IDs
        """
        applied_updates = []
        
        try:
            # Get domain knowledge profile
            profile = self.kg_config_updater.domain_profiles.get(domain_name)
            if not profile:
                profile = self.kg_config_updater.refresh_domain_knowledge_profile(domain_name)
            
            # Detect recent changes
            yago_changes = self.kg_config_updater.detect_yago_changes(
                [e['id'] for e in profile.yago_entities]
            )
            conceptnet_changes = self.kg_config_updater.detect_conceptnet_changes(
                [c['concept'] for c in profile.conceptnet_concepts]
            )
            
            all_changes = yago_changes + conceptnet_changes
            
            # Filter relevant changes
            relevant_changes = []
            for change in all_changes:
                relevance = self.kg_config_updater.assess_change_relevance(change, profile)
                if relevance >= 0.4:  # Relevance threshold
                    change.relevance_score = relevance
                    relevant_changes.append(change)
            
            # Generate and apply updates
            if relevant_changes:
                updates = self.kg_config_updater.generate_configuration_updates(
                    domain_name, relevant_changes
                )
                
                for update in updates:
                    if self.kg_config_updater.validate_configuration_update(update):
                        if self.kg_config_updater.apply_configuration_update(update):
                            applied_updates.append(update.update_id)
                            logger.info(f"Applied KG-based update {update.update_id} to domain {domain_name}")
        
        except Exception as e:
            logger.error(f"Failed to apply KG updates for domain {domain_name}: {e}")
        
        return applied_updates
    
    def get_knowledge_graph_status(self, domain_name: str) -> Dict[str, Any]:
        """
        Get knowledge graph integration status for a domain.
        
        Args:
            domain_name: Name of the domain
            
        Returns:
            Status information
        """
        profile = self.kg_config_updater.domain_profiles.get(domain_name)
        
        if not profile:
            return {
                'domain_name': domain_name,
                'profile_exists': False,
                'last_updated': None,
                'entity_count': 0,
                'concept_count': 0,
                'pending_updates': 0
            }
        
        # Count pending updates
        pending_updates = len(self.kg_config_updater.pending_updates.get(domain_name, []))
        
        return {
            'domain_name': domain_name,
            'profile_exists': True,
            'last_updated': profile.last_updated.isoformat(),
            'entity_count': len(profile.yago_entities),
            'concept_count': len(profile.conceptnet_concepts),
            'pending_updates': pending_updates,
            'update_frequency_hours': profile.update_frequency_hours
        }