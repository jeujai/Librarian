"""
Cross-Domain Learning Engine.

This module implements pattern extraction from successful optimizations,
pattern applicability assessment, and automated pattern application
across domains with learning effectiveness measurement.
"""

import logging
from typing import List, Dict, Any, Optional, Tuple, Set
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import uuid
import numpy as np
from collections import defaultdict, Counter
from sklearn.cluster import KMeans
from sklearn.metrics.pairwise import cosine_similarity
import statistics

from ...models.chunking import DomainConfig, PerformanceMetrics, OptimizationStrategy
from ...database.connection import get_database_connection

logger = logging.getLogger(__name__)


@dataclass
class OptimizationPattern:
    """Pattern extracted from successful optimizations."""
    pattern_id: str
    pattern_type: str  # 'chunk_size', 'bridge_threshold', 'delimiter_adjustment'
    source_domains: List[str]
    optimization_changes: Dict[str, Any]
    success_metrics: Dict[str, float]  # Average improvements per metric
    success_rate: float  # Percentage of successful applications
    applicability_conditions: Dict[str, Any]
    confidence_score: float
    pattern_vector: List[float]  # Feature vector for similarity matching
    created_at: datetime
    last_applied: Optional[datetime] = None
    application_count: int = 0
    
    def is_applicable_to_domain(self, domain_config: DomainConfig, 
                              performance_metrics: PerformanceMetrics,
                              domain_characteristics: Dict[str, Any]) -> bool:
        """Check if pattern is applicable to a domain."""
        
        # Check minimum confidence threshold
        if self.confidence_score < 0.6:
            return False
        
        # Check performance conditions
        for condition, expected_value in self.applicability_conditions.items():
            if condition == 'min_performance_threshold':
                overall_score = self._calculate_overall_performance(performance_metrics)
                if overall_score >= expected_value:
                    continue
                else:
                    return False
            
            elif condition == 'content_complexity_range':
                complexity = domain_characteristics.get('content_complexity', 0.5)
                min_complexity, max_complexity = expected_value
                if not (min_complexity <= complexity <= max_complexity):
                    return False
            
            elif condition == 'domain_similarity_threshold':
                similarity = self._calculate_domain_similarity(
                    domain_characteristics, self.source_domains
                )
                if similarity < expected_value:
                    return False
            
            elif condition == 'config_compatibility':
                if not self._check_config_compatibility(domain_config):
                    return False
        
        return True
    
    def _calculate_overall_performance(self, metrics: PerformanceMetrics) -> float:
        """Calculate overall performance score."""
        return (
            metrics.chunk_quality_score * 0.25 +
            metrics.bridge_success_rate * 0.20 +
            metrics.retrieval_effectiveness * 0.25 +
            metrics.user_satisfaction_score * 0.15 +
            metrics.processing_efficiency * 0.10 +
            metrics.boundary_quality * 0.05
        )
    
    def _calculate_domain_similarity(self, domain_chars: Dict[str, Any], 
                                   source_domains: List[str]) -> float:
        """Calculate similarity to source domains."""
        # Simplified similarity calculation
        # In practice, would use more sophisticated domain embedding
        return 0.7  # Mock similarity score
    
    def _check_config_compatibility(self, config: DomainConfig) -> bool:
        """Check if configuration is compatible with pattern."""
        # Check if required configuration elements exist
        for change_key in self.optimization_changes.keys():
            if 'chunk_size' in change_key and not config.chunk_size_modifiers:
                return False
            elif 'bridge_threshold' in change_key and not config.bridge_thresholds:
                return False
            elif 'delimiter' in change_key and not config.delimiters:
                return False
        
        return True


@dataclass
class PatternApplication:
    """Record of pattern application to a domain."""
    application_id: str
    pattern_id: str
    domain_name: str
    applied_changes: Dict[str, Any]
    performance_before: PerformanceMetrics
    performance_after: Optional[PerformanceMetrics]
    success: Optional[bool]  # None if not yet determined
    improvement_score: float
    application_timestamp: datetime
    evaluation_timestamp: Optional[datetime] = None


@dataclass
class LearningEffectiveness:
    """Measurement of learning effectiveness."""
    pattern_id: str
    total_applications: int
    successful_applications: int
    average_improvement: float
    improvement_variance: float
    domain_coverage: int  # Number of different domains applied to
    effectiveness_score: float  # Overall effectiveness rating
    last_evaluation: datetime


class CrossDomainLearner:
    """
    Cross-domain learning engine for optimization pattern extraction and application.
    
    Implements pattern mining from successful optimizations, similarity-based
    pattern matching, and automated cross-domain knowledge transfer.
    """
    
    def __init__(self):
        """Initialize the cross-domain learner."""
        
        # Pattern storage
        self.learned_patterns = {}  # pattern_id -> OptimizationPattern
        self.pattern_applications = defaultdict(list)  # pattern_id -> List[PatternApplication]
        
        # Learning configuration
        self.learning_config = {
            'min_success_rate_for_pattern': 0.6,
            'min_applications_for_pattern': 3,
            'pattern_similarity_threshold': 0.7,
            'effectiveness_evaluation_interval_days': 7,
            'pattern_retirement_threshold': 0.3
        }
        
        # Feature extraction configuration
        self.feature_extractors = {
            'chunk_size_changes': self._extract_chunk_size_features,
            'bridge_threshold_changes': self._extract_bridge_threshold_features,
            'delimiter_changes': self._extract_delimiter_features,
            'performance_improvements': self._extract_performance_features
        }
        
        logger.info("Initialized Cross-Domain Learner")
    
    def extract_optimization_patterns(self, lookback_days: int = 30) -> List[OptimizationPattern]:
        """
        Extract optimization patterns from successful improvements.
        
        Args:
            lookback_days: Number of days to look back for optimization data
            
        Returns:
            List of extracted patterns
        """
        # Get successful optimizations from database
        successful_optimizations = self._get_successful_optimizations(lookback_days)
        
        if len(successful_optimizations) < self.learning_config['min_applications_for_pattern']:
            logger.info("Insufficient optimization data for pattern extraction")
            return []
        
        # Group optimizations by type and similarity
        optimization_groups = self._group_similar_optimizations(successful_optimizations)
        
        # Extract patterns from each group
        new_patterns = []
        for group_type, optimizations in optimization_groups.items():
            if len(optimizations) >= self.learning_config['min_applications_for_pattern']:
                pattern = self._extract_pattern_from_group(group_type, optimizations)
                if pattern and pattern.success_rate >= self.learning_config['min_success_rate_for_pattern']:
                    new_patterns.append(pattern)
                    self.learned_patterns[pattern.pattern_id] = pattern
        
        # Store patterns in database
        for pattern in new_patterns:
            self._store_optimization_pattern(pattern)
        
        logger.info(f"Extracted {len(new_patterns)} new optimization patterns")
        
        return new_patterns
    
    def assess_pattern_applicability(self, domain_name: str, 
                                   domain_config: DomainConfig,
                                   performance_metrics: PerformanceMetrics) -> List[OptimizationPattern]:
        """
        Assess which patterns are applicable to a domain.
        
        Args:
            domain_name: Name of the domain
            domain_config: Current domain configuration
            performance_metrics: Current performance metrics
            
        Returns:
            List of applicable patterns
        """
        # Get domain characteristics
        domain_characteristics = self._analyze_domain_characteristics(
            domain_name, domain_config, performance_metrics
        )
        
        # Filter applicable patterns
        applicable_patterns = []
        for pattern in self.learned_patterns.values():
            if pattern.is_applicable_to_domain(domain_config, performance_metrics, domain_characteristics):
                applicable_patterns.append(pattern)
        
        # Sort by confidence and success rate
        applicable_patterns.sort(
            key=lambda p: (p.confidence_score * p.success_rate), 
            reverse=True
        )
        
        logger.info(f"Found {len(applicable_patterns)} applicable patterns for domain {domain_name}")
        
        return applicable_patterns
    
    def apply_pattern_to_domain(self, pattern_id: str, domain_name: str,
                              current_config: DomainConfig,
                              current_performance: PerformanceMetrics) -> Optional[DomainConfig]:
        """
        Apply a learned pattern to a domain configuration.
        
        Args:
            pattern_id: ID of the pattern to apply
            domain_name: Name of the domain
            current_config: Current domain configuration
            current_performance: Current performance metrics
            
        Returns:
            Modified configuration or None if application failed
        """
        if pattern_id not in self.learned_patterns:
            logger.error(f"Pattern {pattern_id} not found")
            return None
        
        pattern = self.learned_patterns[pattern_id]
        
        # Create modified configuration
        modified_config = self._apply_pattern_changes(current_config, pattern)
        
        if not modified_config:
            logger.error(f"Failed to apply pattern {pattern_id} to domain {domain_name}")
            return None
        
        # Record pattern application
        application = PatternApplication(
            application_id=str(uuid.uuid4()),
            pattern_id=pattern_id,
            domain_name=domain_name,
            applied_changes=pattern.optimization_changes,
            performance_before=current_performance,
            performance_after=None,
            success=None,
            improvement_score=0.0,
            application_timestamp=datetime.now()
        )
        
        self.pattern_applications[pattern_id].append(application)
        self._store_pattern_application(application)
        
        # Update pattern statistics
        pattern.application_count += 1
        pattern.last_applied = datetime.now()
        
        logger.info(f"Applied pattern {pattern_id} to domain {domain_name}")
        
        return modified_config
    
    def evaluate_pattern_effectiveness(self, pattern_id: str) -> LearningEffectiveness:
        """
        Evaluate the effectiveness of a learned pattern.
        
        Args:
            pattern_id: ID of the pattern to evaluate
            
        Returns:
            Learning effectiveness metrics
        """
        if pattern_id not in self.learned_patterns:
            raise ValueError(f"Pattern {pattern_id} not found")
        
        applications = self.pattern_applications.get(pattern_id, [])
        
        if not applications:
            return LearningEffectiveness(
                pattern_id=pattern_id,
                total_applications=0,
                successful_applications=0,
                average_improvement=0.0,
                improvement_variance=0.0,
                domain_coverage=0,
                effectiveness_score=0.0,
                last_evaluation=datetime.now()
            )
        
        # Calculate success metrics
        completed_applications = [a for a in applications if a.success is not None]
        successful_applications = [a for a in completed_applications if a.success]
        
        success_rate = len(successful_applications) / len(completed_applications) if completed_applications else 0
        
        # Calculate improvement metrics
        improvements = [a.improvement_score for a in successful_applications]
        average_improvement = np.mean(improvements) if improvements else 0.0
        improvement_variance = np.var(improvements) if len(improvements) > 1 else 0.0
        
        # Calculate domain coverage
        unique_domains = set(a.domain_name for a in applications)
        domain_coverage = len(unique_domains)
        
        # Calculate overall effectiveness score
        effectiveness_score = self._calculate_effectiveness_score(
            success_rate, average_improvement, domain_coverage, len(applications)
        )
        
        effectiveness = LearningEffectiveness(
            pattern_id=pattern_id,
            total_applications=len(applications),
            successful_applications=len(successful_applications),
            average_improvement=average_improvement,
            improvement_variance=improvement_variance,
            domain_coverage=domain_coverage,
            effectiveness_score=effectiveness_score,
            last_evaluation=datetime.now()
        )
        
        # Update pattern confidence based on effectiveness
        pattern = self.learned_patterns[pattern_id]
        pattern.confidence_score = min(1.0, effectiveness_score)
        pattern.success_rate = success_rate
        
        return effectiveness
    
    def retire_ineffective_patterns(self) -> List[str]:
        """
        Retire patterns that are no longer effective.
        
        Returns:
            List of retired pattern IDs
        """
        retired_patterns = []
        
        for pattern_id, pattern in list(self.learned_patterns.items()):
            effectiveness = self.evaluate_pattern_effectiveness(pattern_id)
            
            # Retire if effectiveness is below threshold
            if effectiveness.effectiveness_score < self.learning_config['pattern_retirement_threshold']:
                logger.info(f"Retiring ineffective pattern {pattern_id} "
                           f"(effectiveness: {effectiveness.effectiveness_score:.3f})")
                
                # Mark as retired in database
                self._retire_pattern(pattern_id)
                
                # Remove from active patterns
                del self.learned_patterns[pattern_id]
                retired_patterns.append(pattern_id)
        
        return retired_patterns
    
    def generate_cross_domain_strategies(self, domain_name: str,
                                       domain_config: DomainConfig,
                                       performance_metrics: PerformanceMetrics) -> List[OptimizationStrategy]:
        """
        Generate optimization strategies based on cross-domain learning.
        
        Args:
            domain_name: Name of the domain
            domain_config: Current domain configuration
            performance_metrics: Current performance metrics
            
        Returns:
            List of cross-domain optimization strategies
        """
        applicable_patterns = self.assess_pattern_applicability(
            domain_name, domain_config, performance_metrics
        )
        
        strategies = []
        
        for pattern in applicable_patterns[:3]:  # Top 3 patterns
            strategy = OptimizationStrategy(
                type=f"cross_domain_{pattern.pattern_type}",
                target_metrics=list(pattern.success_metrics.keys()),
                adjustments=pattern.optimization_changes,
                expected_improvement=pattern.success_metrics.get('overall', 0.1),
                confidence=pattern.confidence_score
            )
            strategies.append(strategy)
        
        return strategies
    
    def _get_successful_optimizations(self, lookback_days: int) -> List[Dict[str, Any]]:
        """Get successful optimizations from database."""
        try:
            with get_database_connection() as conn:
                cursor = conn.cursor()
                
                cutoff_date = datetime.now() - timedelta(days=lookback_days)
                
                query = """
                SELECT co.domain_name, co.optimization_type, co.changes_made, 
                       co.improvement_score, co.timestamp,
                       cpm_before.chunk_quality_score as before_quality,
                       cpm_before.bridge_success_rate as before_bridge,
                       cpm_before.retrieval_effectiveness as before_retrieval,
                       cpm_after.chunk_quality_score as after_quality,
                       cpm_after.bridge_success_rate as after_bridge,
                       cpm_after.retrieval_effectiveness as after_retrieval
                FROM config_optimizations co
                JOIN domain_configurations dc ON co.config_id = dc.id
                LEFT JOIN config_performance_metrics cpm_before ON co.performance_before::text = cpm_before.id::text
                LEFT JOIN config_performance_metrics cpm_after ON co.performance_after::text = cpm_after.id::text
                WHERE co.improvement_score > 0.05 AND co.timestamp >= %s
                ORDER BY co.improvement_score DESC
                LIMIT 100
                """
                
                cursor.execute(query, (cutoff_date,))
                results = cursor.fetchall()
                
                optimizations = []
                for row in results:
                    optimization = {
                        'domain_name': row[0],
                        'optimization_type': row[1],
                        'changes_made': json.loads(row[2]) if row[2] else {},
                        'improvement_score': row[3],
                        'timestamp': row[4],
                        'performance_before': {
                            'chunk_quality_score': row[5] or 0.0,
                            'bridge_success_rate': row[6] or 0.0,
                            'retrieval_effectiveness': row[7] or 0.0
                        },
                        'performance_after': {
                            'chunk_quality_score': row[8] or 0.0,
                            'bridge_success_rate': row[9] or 0.0,
                            'retrieval_effectiveness': row[10] or 0.0
                        }
                    }
                    optimizations.append(optimization)
                
                return optimizations
        
        except Exception as e:
            logger.error(f"Failed to get successful optimizations: {e}")
            return []
    
    def _group_similar_optimizations(self, optimizations: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """Group similar optimizations for pattern extraction."""
        
        # Group by optimization type first
        type_groups = defaultdict(list)
        for opt in optimizations:
            type_groups[opt['optimization_type']].append(opt)
        
        # Further group by similarity within each type
        similar_groups = {}
        
        for opt_type, opts in type_groups.items():
            if len(opts) < 2:
                similar_groups[opt_type] = opts
                continue
            
            # Extract feature vectors for clustering
            feature_vectors = []
            for opt in opts:
                features = self._extract_optimization_features(opt)
                feature_vectors.append(features)
            
            # Cluster similar optimizations
            if len(feature_vectors) >= 3:
                try:
                    n_clusters = min(3, len(feature_vectors) // 2)
                    kmeans = KMeans(n_clusters=n_clusters, random_state=42)
                    cluster_labels = kmeans.fit_predict(feature_vectors)
                    
                    # Group by cluster
                    for i, cluster_id in enumerate(cluster_labels):
                        group_key = f"{opt_type}_cluster_{cluster_id}"
                        if group_key not in similar_groups:
                            similar_groups[group_key] = []
                        similar_groups[group_key].append(opts[i])
                
                except Exception as e:
                    logger.warning(f"Clustering failed for {opt_type}: {e}")
                    similar_groups[opt_type] = opts
            else:
                similar_groups[opt_type] = opts
        
        return similar_groups
    
    def _extract_optimization_features(self, optimization: Dict[str, Any]) -> List[float]:
        """Extract feature vector from optimization record."""
        features = []
        
        # Extract features from changes
        changes = optimization['changes_made']
        
        # Chunk size features
        features.extend(self._extract_chunk_size_features(changes))
        
        # Bridge threshold features
        features.extend(self._extract_bridge_threshold_features(changes))
        
        # Delimiter features
        features.extend(self._extract_delimiter_features(changes))
        
        # Performance improvement features
        features.extend(self._extract_performance_features(optimization))
        
        return features
    
    def _extract_chunk_size_features(self, changes: Dict[str, Any]) -> List[float]:
        """Extract chunk size related features."""
        features = [0.0, 0.0, 0.0]  # [has_size_change, size_multiplier, preserve_boundaries]
        
        if 'size_multiplier' in changes:
            features[0] = 1.0
            features[1] = float(changes['size_multiplier'])
        
        if 'preserve_boundaries' in changes:
            features[2] = 1.0 if changes['preserve_boundaries'] else 0.0
        
        return features
    
    def _extract_bridge_threshold_features(self, changes: Dict[str, Any]) -> List[float]:
        """Extract bridge threshold related features."""
        features = [0.0, 0.0, 0.0]  # [has_threshold_change, threshold_adjustment, adaptive_thresholds]
        
        if 'threshold_adjustment' in changes:
            features[0] = 1.0
            features[1] = float(changes['threshold_adjustment'])
        
        if 'adaptive_thresholds' in changes:
            features[2] = 1.0 if changes['adaptive_thresholds'] else 0.0
        
        return features
    
    def _extract_delimiter_features(self, changes: Dict[str, Any]) -> List[float]:
        """Extract delimiter related features."""
        features = [0.0, 0.0, 0.0]  # [has_delimiter_change, semantic_delimiters, content_specific]
        
        if 'add_semantic_delimiters' in changes:
            features[0] = 1.0
            features[1] = 1.0 if changes['add_semantic_delimiters'] else 0.0
        
        if 'content_specific_patterns' in changes:
            features[2] = 1.0 if changes['content_specific_patterns'] else 0.0
        
        return features
    
    def _extract_performance_features(self, optimization: Dict[str, Any]) -> List[float]:
        """Extract performance improvement features."""
        before = optimization['performance_before']
        after = optimization['performance_after']
        
        # Calculate relative improvements
        quality_improvement = (after['chunk_quality_score'] - before['chunk_quality_score']) / max(before['chunk_quality_score'], 0.01)
        bridge_improvement = (after['bridge_success_rate'] - before['bridge_success_rate']) / max(before['bridge_success_rate'], 0.01)
        retrieval_improvement = (after['retrieval_effectiveness'] - before['retrieval_effectiveness']) / max(before['retrieval_effectiveness'], 0.01)
        
        return [quality_improvement, bridge_improvement, retrieval_improvement]
    
    def _extract_pattern_from_group(self, group_type: str, 
                                   optimizations: List[Dict[str, Any]]) -> Optional[OptimizationPattern]:
        """Extract a pattern from a group of similar optimizations."""
        
        if len(optimizations) < self.learning_config['min_applications_for_pattern']:
            return None
        
        # Extract common changes
        all_changes = [opt['changes_made'] for opt in optimizations]
        common_changes = self._find_common_changes(all_changes)
        
        if not common_changes:
            return None
        
        # Calculate success metrics
        success_metrics = self._calculate_success_metrics(optimizations)
        
        # Calculate success rate
        success_rate = len([opt for opt in optimizations if opt['improvement_score'] > 0.05]) / len(optimizations)
        
        # Extract source domains
        source_domains = list(set(opt['domain_name'] for opt in optimizations))
        
        # Calculate applicability conditions
        applicability_conditions = self._determine_applicability_conditions(optimizations)
        
        # Calculate pattern vector
        pattern_vector = self._calculate_pattern_vector(optimizations)
        
        # Calculate confidence score
        confidence_score = min(1.0, success_rate * (len(optimizations) / 10.0))
        
        pattern = OptimizationPattern(
            pattern_id=str(uuid.uuid4()),
            pattern_type=group_type.split('_')[0],  # Extract base type
            source_domains=source_domains,
            optimization_changes=common_changes,
            success_metrics=success_metrics,
            success_rate=success_rate,
            applicability_conditions=applicability_conditions,
            confidence_score=confidence_score,
            pattern_vector=pattern_vector,
            created_at=datetime.now()
        )
        
        return pattern
    
    def _find_common_changes(self, all_changes: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Find common changes across optimizations."""
        common_changes = {}
        
        # Find keys that appear in most optimizations
        all_keys = set()
        for changes in all_changes:
            all_keys.update(changes.keys())
        
        for key in all_keys:
            values = []
            for changes in all_changes:
                if key in changes:
                    values.append(changes[key])
            
            # Keep if appears in at least 60% of optimizations
            if len(values) >= len(all_changes) * 0.6:
                if isinstance(values[0], (int, float)):
                    common_changes[key] = np.mean(values)
                elif isinstance(values[0], bool):
                    common_changes[key] = Counter(values).most_common(1)[0][0]
                else:
                    common_changes[key] = Counter(values).most_common(1)[0][0]
        
        return common_changes
    
    def _calculate_success_metrics(self, optimizations: List[Dict[str, Any]]) -> Dict[str, float]:
        """Calculate average success metrics."""
        improvements = defaultdict(list)
        
        for opt in optimizations:
            before = opt['performance_before']
            after = opt['performance_after']
            
            for metric in ['chunk_quality_score', 'bridge_success_rate', 'retrieval_effectiveness']:
                if before[metric] > 0:
                    improvement = (after[metric] - before[metric]) / before[metric]
                    improvements[metric].append(improvement)
        
        success_metrics = {}
        for metric, values in improvements.items():
            if values:
                success_metrics[metric] = np.mean(values)
        
        # Calculate overall improvement
        if success_metrics:
            success_metrics['overall'] = np.mean(list(success_metrics.values()))
        
        return success_metrics
    
    def _determine_applicability_conditions(self, optimizations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Determine conditions for pattern applicability."""
        conditions = {}
        
        # Analyze performance thresholds
        before_performances = []
        for opt in optimizations:
            before = opt['performance_before']
            overall_perf = (before['chunk_quality_score'] + before['bridge_success_rate'] + before['retrieval_effectiveness']) / 3.0
            before_performances.append(overall_perf)
        
        if before_performances:
            conditions['min_performance_threshold'] = np.percentile(before_performances, 25)  # 25th percentile
        
        # Add domain similarity threshold
        conditions['domain_similarity_threshold'] = 0.5
        
        # Add configuration compatibility
        conditions['config_compatibility'] = True
        
        return conditions
    
    def _calculate_pattern_vector(self, optimizations: List[Dict[str, Any]]) -> List[float]:
        """Calculate pattern feature vector."""
        feature_vectors = []
        for opt in optimizations:
            features = self._extract_optimization_features(opt)
            feature_vectors.append(features)
        
        # Return average feature vector
        return np.mean(feature_vectors, axis=0).tolist()
    
    def _analyze_domain_characteristics(self, domain_name: str, 
                                      domain_config: DomainConfig,
                                      performance_metrics: PerformanceMetrics) -> Dict[str, Any]:
        """Analyze domain characteristics for pattern matching."""
        
        characteristics = {
            'domain_name': domain_name,
            'content_complexity': 0.5,  # Would be calculated from actual content
            'config_maturity': len(domain_config.chunk_size_modifiers) + len(domain_config.bridge_thresholds),
            'performance_level': self._calculate_overall_performance(performance_metrics),
            'optimization_history_length': 0  # Would be calculated from database
        }
        
        return characteristics
    
    def _calculate_overall_performance(self, metrics: PerformanceMetrics) -> float:
        """Calculate overall performance score."""
        return (
            metrics.chunk_quality_score * 0.25 +
            metrics.bridge_success_rate * 0.20 +
            metrics.retrieval_effectiveness * 0.25 +
            metrics.user_satisfaction_score * 0.15 +
            metrics.processing_efficiency * 0.10 +
            metrics.boundary_quality * 0.05
        )
    
    def _apply_pattern_changes(self, config: DomainConfig, 
                             pattern: OptimizationPattern) -> Optional[DomainConfig]:
        """Apply pattern changes to a configuration."""
        
        try:
            # Create a copy of the configuration
            modified_config = DomainConfig(
                domain_name=config.domain_name,
                delimiters=config.delimiters.copy(),
                chunk_size_modifiers=config.chunk_size_modifiers.copy(),
                preservation_patterns=config.preservation_patterns.copy(),
                bridge_thresholds=config.bridge_thresholds.copy(),
                cross_reference_patterns=config.cross_reference_patterns.copy(),
                generation_method=config.generation_method,
                confidence_score=config.confidence_score
            )
            
            # Apply pattern changes
            for change_key, change_value in pattern.optimization_changes.items():
                if change_key == 'size_multiplier':
                    # Apply to all chunk size modifiers
                    for key in modified_config.chunk_size_modifiers:
                        modified_config.chunk_size_modifiers[key] *= change_value
                
                elif change_key == 'threshold_adjustment':
                    # Apply to all bridge thresholds
                    for key in modified_config.bridge_thresholds:
                        modified_config.bridge_thresholds[key] += change_value
                        modified_config.bridge_thresholds[key] = max(0.0, min(1.0, modified_config.bridge_thresholds[key]))
                
                elif change_key == 'add_semantic_delimiters' and change_value:
                    # Add semantic delimiters if not present
                    semantic_patterns = [r'\n\n', r'\. [A-Z]', r':\s*\n']
                    for pattern_str in semantic_patterns:
                        if not any(d.pattern == pattern_str for d in modified_config.delimiters):
                            from ...models.chunking import DelimiterPattern
                            delimiter = DelimiterPattern(pattern=pattern_str, priority=2)
                            modified_config.delimiters.append(delimiter)
            
            return modified_config
        
        except Exception as e:
            logger.error(f"Failed to apply pattern changes: {e}")
            return None
    
    def _calculate_effectiveness_score(self, success_rate: float, average_improvement: float,
                                     domain_coverage: int, total_applications: int) -> float:
        """Calculate overall effectiveness score for a pattern."""
        
        # Base score from success rate
        base_score = success_rate
        
        # Boost for high improvement
        improvement_boost = min(0.3, average_improvement * 2)
        
        # Boost for domain coverage (generalizability)
        coverage_boost = min(0.2, domain_coverage * 0.05)
        
        # Boost for sufficient applications (confidence)
        application_boost = min(0.1, total_applications * 0.01)
        
        effectiveness_score = base_score + improvement_boost + coverage_boost + application_boost
        
        return min(1.0, effectiveness_score)
    
    def _store_optimization_pattern(self, pattern: OptimizationPattern) -> None:
        """Store optimization pattern in database."""
        try:
            with get_database_connection() as conn:
                cursor = conn.cursor()
                
                # Create table if it doesn't exist
                create_table_query = """
                CREATE TABLE IF NOT EXISTS optimization_patterns (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    pattern_id VARCHAR(100) UNIQUE NOT NULL,
                    pattern_type VARCHAR(50) NOT NULL,
                    source_domains TEXT[],
                    optimization_changes JSONB NOT NULL,
                    success_metrics JSONB,
                    success_rate FLOAT,
                    applicability_conditions JSONB,
                    confidence_score FLOAT,
                    pattern_vector FLOAT[],
                    application_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_applied TIMESTAMP,
                    is_active BOOLEAN DEFAULT TRUE
                )
                """
                cursor.execute(create_table_query)
                
                insert_query = """
                INSERT INTO optimization_patterns 
                (pattern_id, pattern_type, source_domains, optimization_changes,
                 success_metrics, success_rate, applicability_conditions, 
                 confidence_score, pattern_vector, application_count, created_at, last_applied)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                
                cursor.execute(insert_query, (
                    pattern.pattern_id, pattern.pattern_type, pattern.source_domains,
                    json.dumps(pattern.optimization_changes), json.dumps(pattern.success_metrics),
                    pattern.success_rate, json.dumps(pattern.applicability_conditions),
                    pattern.confidence_score, pattern.pattern_vector, pattern.application_count,
                    pattern.created_at, pattern.last_applied
                ))
                
                conn.commit()
        
        except Exception as e:
            logger.error(f"Failed to store optimization pattern: {e}")
    
    def _store_pattern_application(self, application: PatternApplication) -> None:
        """Store pattern application record in database."""
        try:
            with get_database_connection() as conn:
                cursor = conn.cursor()
                
                # Create table if it doesn't exist
                create_table_query = """
                CREATE TABLE IF NOT EXISTS pattern_applications (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    application_id VARCHAR(100) UNIQUE NOT NULL,
                    pattern_id VARCHAR(100) NOT NULL,
                    domain_name VARCHAR(100) NOT NULL,
                    applied_changes JSONB NOT NULL,
                    performance_before JSONB,
                    performance_after JSONB,
                    success BOOLEAN,
                    improvement_score FLOAT,
                    application_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    evaluation_timestamp TIMESTAMP
                )
                """
                cursor.execute(create_table_query)
                
                insert_query = """
                INSERT INTO pattern_applications 
                (application_id, pattern_id, domain_name, applied_changes,
                 performance_before, performance_after, success, improvement_score,
                 application_timestamp, evaluation_timestamp)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                
                cursor.execute(insert_query, (
                    application.application_id, application.pattern_id, application.domain_name,
                    json.dumps(application.applied_changes),
                    json.dumps(application.performance_before.to_dict()),
                    json.dumps(application.performance_after.to_dict()) if application.performance_after else None,
                    application.success, application.improvement_score,
                    application.application_timestamp, application.evaluation_timestamp
                ))
                
                conn.commit()
        
        except Exception as e:
            logger.error(f"Failed to store pattern application: {e}")
    
    def _retire_pattern(self, pattern_id: str) -> None:
        """Mark pattern as retired in database."""
        try:
            with get_database_connection() as conn:
                cursor = conn.cursor()
                
                update_query = """
                UPDATE optimization_patterns 
                SET is_active = false 
                WHERE pattern_id = %s
                """
                cursor.execute(update_query, (pattern_id,))
                conn.commit()
        
        except Exception as e:
            logger.error(f"Failed to retire pattern: {e}")