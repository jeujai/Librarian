"""
Performance Tracking System.

This module implements real-time performance metrics collection, user feedback integration,
performance degradation detection, and analytics dashboard functionality.
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import uuid
import numpy as np
from collections import defaultdict, deque
import statistics

from ...models.chunking import PerformanceMetrics, DomainConfig
from ...database.connection import get_database_connection

logger = logging.getLogger(__name__)


@dataclass
class PerformanceTrend:
    """Performance trend analysis."""
    metric_name: str
    current_value: float
    trend_direction: str  # 'improving', 'declining', 'stable'
    trend_strength: float  # 0.0-1.0
    change_rate: float  # Rate of change per measurement
    confidence: float  # Confidence in trend analysis
    
    def is_significant_decline(self, threshold: float = 0.1) -> bool:
        """Check if there's a significant performance decline."""
        return (self.trend_direction == 'declining' and 
                abs(self.change_rate) > threshold and 
                self.confidence > 0.7)


@dataclass
class PerformanceAlert:
    """Performance degradation alert."""
    alert_id: str
    domain_name: str
    alert_type: str  # 'degradation', 'threshold_breach', 'anomaly'
    severity: str  # 'low', 'medium', 'high', 'critical'
    affected_metrics: List[str]
    current_values: Dict[str, float]
    threshold_values: Dict[str, float]
    trend_analysis: List[PerformanceTrend]
    suggested_actions: List[str]
    created_at: datetime
    
    def get_priority_score(self) -> float:
        """Calculate priority score for alert handling."""
        severity_scores = {'low': 0.25, 'medium': 0.5, 'high': 0.75, 'critical': 1.0}
        base_score = severity_scores.get(self.severity, 0.5)
        
        # Adjust based on number of affected metrics
        metric_factor = min(1.0, len(self.affected_metrics) / 6.0)
        
        # Adjust based on trend strength
        trend_factor = np.mean([t.trend_strength for t in self.trend_analysis]) if self.trend_analysis else 0.5
        
        return base_score * (0.5 + 0.3 * metric_factor + 0.2 * trend_factor)


@dataclass
class UserFeedbackData:
    """User feedback data for performance analysis."""
    feedback_id: str
    user_id: str
    domain_name: str
    feedback_type: str  # 'quality_rating', 'issue_report', 'suggestion'
    rating: Optional[float]  # 1.0-5.0 for ratings
    feedback_text: str
    affected_components: List[str]
    chunk_ids: List[str]
    timestamp: datetime
    processed: bool = False
    
    def get_sentiment_score(self) -> float:
        """Get sentiment score from feedback text (simplified)."""
        # In a real implementation, this would use NLP sentiment analysis
        positive_words = ['good', 'great', 'excellent', 'helpful', 'accurate', 'relevant']
        negative_words = ['bad', 'poor', 'wrong', 'irrelevant', 'confusing', 'error']
        
        text_lower = self.feedback_text.lower()
        positive_count = sum(1 for word in positive_words if word in text_lower)
        negative_count = sum(1 for word in negative_words if word in text_lower)
        
        if positive_count + negative_count == 0:
            return 0.0  # Neutral
        
        return (positive_count - negative_count) / (positive_count + negative_count)


@dataclass
class PerformanceDashboardData:
    """Data structure for performance analytics dashboard."""
    domain_name: str
    current_metrics: PerformanceMetrics
    historical_metrics: List[PerformanceMetrics]
    trends: List[PerformanceTrend]
    alerts: List[PerformanceAlert]
    user_feedback_summary: Dict[str, Any]
    optimization_history: List[Dict[str, Any]]
    recommendations: List[str]
    last_updated: datetime


class PerformanceTracker:
    """
    Real-time performance tracking system with degradation detection and analytics.
    
    Implements comprehensive performance monitoring, user feedback integration,
    trend analysis, and automated alert generation.
    """
    
    def __init__(self):
        """Initialize the performance tracker."""
        
        # Performance data storage
        self.performance_history = defaultdict(lambda: deque(maxlen=1000))  # Keep last 1000 measurements
        self.user_feedback_queue = deque(maxlen=10000)  # Keep last 10000 feedback items
        self.active_alerts = defaultdict(list)
        
        # Performance thresholds
        self.performance_thresholds = {
            'chunk_quality_score': {'warning': 0.7, 'critical': 0.5},
            'bridge_success_rate': {'warning': 0.6, 'critical': 0.4},
            'retrieval_effectiveness': {'warning': 0.75, 'critical': 0.6},
            'user_satisfaction_score': {'warning': 0.7, 'critical': 0.5},
            'processing_efficiency': {'warning': 0.8, 'critical': 0.6},
            'boundary_quality': {'warning': 0.7, 'critical': 0.5}
        }
        
        # Trend analysis configuration
        self.trend_analysis_config = {
            'min_data_points': 5,
            'trend_window': 20,  # Number of recent measurements to analyze
            'significance_threshold': 0.05,
            'stability_threshold': 0.02
        }
        
        # Alert configuration
        self.alert_config = {
            'max_alerts_per_domain': 10,
            'alert_cooldown_hours': 2,
            'auto_resolve_hours': 24
        }
        
        logger.info("Initialized Performance Tracker")
    
    def track_performance(self, domain_name: str, performance_metrics: PerformanceMetrics) -> None:
        """
        Track real-time performance metrics with trend analysis and alert generation.
        
        Args:
            domain_name: Name of the domain
            performance_metrics: Current performance metrics
        """
        # Store performance data
        self.performance_history[domain_name].append(performance_metrics)
        
        # Store in database
        self._store_performance_metrics(domain_name, performance_metrics)
        
        # Analyze trends
        trends = self._analyze_performance_trends(domain_name)
        
        # Check for performance degradation
        alerts = self._check_performance_degradation(domain_name, performance_metrics, trends)
        
        # Generate alerts if needed
        for alert in alerts:
            self._generate_performance_alert(alert)
        
        logger.debug(f"Tracked performance for domain {domain_name}: "
                    f"quality={performance_metrics.chunk_quality_score:.3f}, "
                    f"bridge_success={performance_metrics.bridge_success_rate:.3f}")
    
    def collect_user_feedback(self, feedback_data: UserFeedbackData) -> None:
        """
        Collect and process user feedback for performance analysis.
        
        Args:
            feedback_data: User feedback data
        """
        # Add to feedback queue
        self.user_feedback_queue.append(feedback_data)
        
        # Store in database
        self._store_user_feedback(feedback_data)
        
        # Process feedback for immediate insights
        self._process_user_feedback(feedback_data)
        
        logger.info(f"Collected user feedback: {feedback_data.feedback_type} "
                   f"for domain {feedback_data.domain_name}")
    
    def detect_performance_degradation(self, domain_name: str) -> List[PerformanceAlert]:
        """
        Detect performance degradation using trend analysis and threshold monitoring.
        
        Args:
            domain_name: Name of the domain to analyze
            
        Returns:
            List of performance alerts
        """
        if domain_name not in self.performance_history:
            return []
        
        recent_metrics = list(self.performance_history[domain_name])
        if len(recent_metrics) < self.trend_analysis_config['min_data_points']:
            return []
        
        current_metrics = recent_metrics[-1]
        trends = self._analyze_performance_trends(domain_name)
        
        return self._check_performance_degradation(domain_name, current_metrics, trends)
    
    def generate_dashboard_data(self, domain_name: str) -> PerformanceDashboardData:
        """
        Generate comprehensive dashboard data for performance analytics.
        
        Args:
            domain_name: Name of the domain
            
        Returns:
            Dashboard data structure
        """
        if domain_name not in self.performance_history:
            # Return empty dashboard data
            return PerformanceDashboardData(
                domain_name=domain_name,
                current_metrics=PerformanceMetrics(),
                historical_metrics=[],
                trends=[],
                alerts=[],
                user_feedback_summary={},
                optimization_history=[],
                recommendations=[],
                last_updated=datetime.now()
            )
        
        # Get performance data
        historical_metrics = list(self.performance_history[domain_name])
        current_metrics = historical_metrics[-1] if historical_metrics else PerformanceMetrics()
        
        # Analyze trends
        trends = self._analyze_performance_trends(domain_name)
        
        # Get active alerts
        alerts = self.active_alerts.get(domain_name, [])
        
        # Generate user feedback summary
        feedback_summary = self._generate_feedback_summary(domain_name)
        
        # Get optimization history
        optimization_history = self._get_optimization_history(domain_name)
        
        # Generate recommendations
        recommendations = self._generate_performance_recommendations(domain_name, trends, feedback_summary)
        
        return PerformanceDashboardData(
            domain_name=domain_name,
            current_metrics=current_metrics,
            historical_metrics=historical_metrics[-100:],  # Last 100 measurements
            trends=trends,
            alerts=alerts,
            user_feedback_summary=feedback_summary,
            optimization_history=optimization_history,
            recommendations=recommendations,
            last_updated=datetime.now()
        )
    
    def _analyze_performance_trends(self, domain_name: str) -> List[PerformanceTrend]:
        """Analyze performance trends for a domain."""
        if domain_name not in self.performance_history:
            return []
        
        recent_metrics = list(self.performance_history[domain_name])
        if len(recent_metrics) < self.trend_analysis_config['min_data_points']:
            return []
        
        # Analyze trends for each metric
        trends = []
        metric_names = [
            'chunk_quality_score', 'bridge_success_rate', 'retrieval_effectiveness',
            'user_satisfaction_score', 'processing_efficiency', 'boundary_quality'
        ]
        
        window_size = min(self.trend_analysis_config['trend_window'], len(recent_metrics))
        analysis_window = recent_metrics[-window_size:]
        
        for metric_name in metric_names:
            values = [getattr(m, metric_name) for m in analysis_window]
            trend = self._calculate_trend(metric_name, values)
            if trend:
                trends.append(trend)
        
        return trends
    
    def _calculate_trend(self, metric_name: str, values: List[float]) -> Optional[PerformanceTrend]:
        """Calculate trend for a specific metric."""
        if len(values) < 3:
            return None
        
        # Calculate linear regression slope
        x = np.arange(len(values))
        y = np.array(values)
        
        # Simple linear regression
        n = len(values)
        sum_x = np.sum(x)
        sum_y = np.sum(y)
        sum_xy = np.sum(x * y)
        sum_x2 = np.sum(x * x)
        
        slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x * sum_x)
        
        # Determine trend direction
        if abs(slope) < self.trend_analysis_config['stability_threshold']:
            trend_direction = 'stable'
            trend_strength = 0.0
        elif slope > 0:
            trend_direction = 'improving'
            trend_strength = min(1.0, abs(slope) * 10)  # Scale to 0-1
        else:
            trend_direction = 'declining'
            trend_strength = min(1.0, abs(slope) * 10)
        
        # Calculate confidence based on R-squared
        y_mean = np.mean(y)
        ss_tot = np.sum((y - y_mean) ** 2)
        y_pred = slope * x + (sum_y - slope * sum_x) / n
        ss_res = np.sum((y - y_pred) ** 2)
        
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
        confidence = max(0.0, min(1.0, r_squared))
        
        return PerformanceTrend(
            metric_name=metric_name,
            current_value=values[-1],
            trend_direction=trend_direction,
            trend_strength=trend_strength,
            change_rate=slope,
            confidence=confidence
        )
    
    def _check_performance_degradation(self, domain_name: str, 
                                     current_metrics: PerformanceMetrics,
                                     trends: List[PerformanceTrend]) -> List[PerformanceAlert]:
        """Check for performance degradation and generate alerts."""
        alerts = []
        
        # Check threshold breaches
        threshold_alerts = self._check_threshold_breaches(domain_name, current_metrics)
        alerts.extend(threshold_alerts)
        
        # Check trend-based degradation
        trend_alerts = self._check_trend_degradation(domain_name, trends)
        alerts.extend(trend_alerts)
        
        # Check for anomalies
        anomaly_alerts = self._check_performance_anomalies(domain_name, current_metrics)
        alerts.extend(anomaly_alerts)
        
        return alerts
    
    def _check_threshold_breaches(self, domain_name: str, 
                                metrics: PerformanceMetrics) -> List[PerformanceAlert]:
        """Check for threshold breaches."""
        alerts = []
        
        for metric_name, thresholds in self.performance_thresholds.items():
            current_value = getattr(metrics, metric_name)
            
            if current_value < thresholds['critical']:
                severity = 'critical'
            elif current_value < thresholds['warning']:
                severity = 'medium'
            else:
                continue
            
            alert = PerformanceAlert(
                alert_id=str(uuid.uuid4()),
                domain_name=domain_name,
                alert_type='threshold_breach',
                severity=severity,
                affected_metrics=[metric_name],
                current_values={metric_name: current_value},
                threshold_values={metric_name: thresholds[severity]},
                trend_analysis=[],
                suggested_actions=[f"Investigate {metric_name} performance issues"],
                created_at=datetime.now()
            )
            alerts.append(alert)
        
        return alerts
    
    def _check_trend_degradation(self, domain_name: str, 
                               trends: List[PerformanceTrend]) -> List[PerformanceAlert]:
        """Check for trend-based performance degradation."""
        alerts = []
        
        declining_trends = [t for t in trends if t.is_significant_decline()]
        
        if declining_trends:
            affected_metrics = [t.metric_name for t in declining_trends]
            current_values = {t.metric_name: t.current_value for t in declining_trends}
            
            # Determine severity based on number of declining metrics and trend strength
            avg_trend_strength = np.mean([t.trend_strength for t in declining_trends])
            
            if len(declining_trends) >= 3 or avg_trend_strength > 0.8:
                severity = 'high'
            elif len(declining_trends) >= 2 or avg_trend_strength > 0.6:
                severity = 'medium'
            else:
                severity = 'low'
            
            alert = PerformanceAlert(
                alert_id=str(uuid.uuid4()),
                domain_name=domain_name,
                alert_type='degradation',
                severity=severity,
                affected_metrics=affected_metrics,
                current_values=current_values,
                threshold_values={},
                trend_analysis=declining_trends,
                suggested_actions=[
                    "Review recent configuration changes",
                    "Analyze user feedback for quality issues",
                    "Consider optimization strategies"
                ],
                created_at=datetime.now()
            )
            alerts.append(alert)
        
        return alerts
    
    def _check_performance_anomalies(self, domain_name: str, 
                                   current_metrics: PerformanceMetrics) -> List[PerformanceAlert]:
        """Check for performance anomalies using statistical analysis."""
        if domain_name not in self.performance_history:
            return []
        
        historical_data = list(self.performance_history[domain_name])
        if len(historical_data) < 20:  # Need sufficient history
            return []
        
        alerts = []
        metric_names = [
            'chunk_quality_score', 'bridge_success_rate', 'retrieval_effectiveness',
            'user_satisfaction_score', 'processing_efficiency', 'boundary_quality'
        ]
        
        for metric_name in metric_names:
            historical_values = [getattr(m, metric_name) for m in historical_data[:-1]]
            current_value = getattr(current_metrics, metric_name)
            
            # Calculate z-score
            mean_value = statistics.mean(historical_values)
            std_value = statistics.stdev(historical_values) if len(historical_values) > 1 else 0
            
            if std_value > 0:
                z_score = abs(current_value - mean_value) / std_value
                
                # Check for anomaly (z-score > 2.5 is considered anomalous)
                if z_score > 2.5:
                    alert = PerformanceAlert(
                        alert_id=str(uuid.uuid4()),
                        domain_name=domain_name,
                        alert_type='anomaly',
                        severity='medium',
                        affected_metrics=[metric_name],
                        current_values={metric_name: current_value},
                        threshold_values={metric_name: mean_value},
                        trend_analysis=[],
                        suggested_actions=[
                            f"Investigate anomalous {metric_name} value",
                            "Check for data quality issues",
                            "Review recent system changes"
                        ],
                        created_at=datetime.now()
                    )
                    alerts.append(alert)
        
        return alerts
    
    def _generate_performance_alert(self, alert: PerformanceAlert) -> None:
        """Generate and store a performance alert."""
        
        # Check alert cooldown
        if self._is_alert_in_cooldown(alert):
            return
        
        # Add to active alerts
        if len(self.active_alerts[alert.domain_name]) >= self.alert_config['max_alerts_per_domain']:
            # Remove oldest alert
            self.active_alerts[alert.domain_name].pop(0)
        
        self.active_alerts[alert.domain_name].append(alert)
        
        # Store in database
        self._store_performance_alert(alert)
        
        logger.warning(f"Generated performance alert for {alert.domain_name}: "
                      f"{alert.alert_type} ({alert.severity}) - "
                      f"Metrics: {', '.join(alert.affected_metrics)}")
    
    def _is_alert_in_cooldown(self, alert: PerformanceAlert) -> bool:
        """Check if similar alert is in cooldown period."""
        cooldown_time = datetime.now() - timedelta(hours=self.alert_config['alert_cooldown_hours'])
        
        for existing_alert in self.active_alerts.get(alert.domain_name, []):
            if (existing_alert.alert_type == alert.alert_type and
                existing_alert.created_at > cooldown_time and
                set(existing_alert.affected_metrics) & set(alert.affected_metrics)):
                return True
        
        return False
    
    def _process_user_feedback(self, feedback_data: UserFeedbackData) -> None:
        """Process user feedback for immediate insights."""
        
        # Update user satisfaction scores if rating provided
        if feedback_data.rating is not None:
            self._update_user_satisfaction_score(feedback_data)
        
        # Analyze feedback sentiment
        sentiment_score = feedback_data.get_sentiment_score()
        
        # Generate feedback-based alerts if needed
        if sentiment_score < -0.5 or (feedback_data.rating and feedback_data.rating < 2.0):
            self._generate_feedback_alert(feedback_data, sentiment_score)
    
    def _update_user_satisfaction_score(self, feedback_data: UserFeedbackData) -> None:
        """Update user satisfaction score based on feedback."""
        # This would integrate with the performance tracking to update satisfaction scores
        # For now, we'll just log the feedback
        logger.info(f"User satisfaction feedback: {feedback_data.rating}/5.0 "
                   f"for domain {feedback_data.domain_name}")
    
    def _generate_feedback_alert(self, feedback_data: UserFeedbackData, sentiment_score: float) -> None:
        """Generate alert based on negative user feedback."""
        severity = 'high' if sentiment_score < -0.7 or (feedback_data.rating and feedback_data.rating < 1.5) else 'medium'
        
        alert = PerformanceAlert(
            alert_id=str(uuid.uuid4()),
            domain_name=feedback_data.domain_name,
            alert_type='user_feedback',
            severity=severity,
            affected_metrics=['user_satisfaction_score'],
            current_values={'user_satisfaction_score': feedback_data.rating or 0.0},
            threshold_values={'user_satisfaction_score': 3.0},
            trend_analysis=[],
            suggested_actions=[
                "Review user feedback details",
                "Investigate reported issues",
                "Consider configuration adjustments"
            ],
            created_at=datetime.now()
        )
        
        self._generate_performance_alert(alert)
    
    def _generate_feedback_summary(self, domain_name: str) -> Dict[str, Any]:
        """Generate summary of user feedback for a domain."""
        domain_feedback = [f for f in self.user_feedback_queue if f.domain_name == domain_name]
        
        if not domain_feedback:
            return {
                'total_feedback': 0,
                'average_rating': 0.0,
                'sentiment_distribution': {},
                'common_issues': [],
                'recent_feedback_count': 0
            }
        
        # Calculate statistics
        ratings = [f.rating for f in domain_feedback if f.rating is not None]
        avg_rating = statistics.mean(ratings) if ratings else 0.0
        
        # Sentiment analysis
        sentiments = [f.get_sentiment_score() for f in domain_feedback]
        sentiment_distribution = {
            'positive': len([s for s in sentiments if s > 0.2]),
            'neutral': len([s for s in sentiments if -0.2 <= s <= 0.2]),
            'negative': len([s for s in sentiments if s < -0.2])
        }
        
        # Recent feedback (last 7 days)
        recent_cutoff = datetime.now() - timedelta(days=7)
        recent_feedback = [f for f in domain_feedback if f.timestamp > recent_cutoff]
        
        return {
            'total_feedback': len(domain_feedback),
            'average_rating': avg_rating,
            'sentiment_distribution': sentiment_distribution,
            'common_issues': self._extract_common_issues(domain_feedback),
            'recent_feedback_count': len(recent_feedback)
        }
    
    def _extract_common_issues(self, feedback_list: List[UserFeedbackData]) -> List[str]:
        """Extract common issues from feedback text."""
        # Simplified issue extraction - in practice would use NLP
        issue_keywords = {
            'quality': ['quality', 'accuracy', 'wrong', 'incorrect'],
            'relevance': ['relevant', 'irrelevant', 'unrelated'],
            'completeness': ['incomplete', 'missing', 'partial'],
            'performance': ['slow', 'fast', 'speed', 'performance']
        }
        
        issue_counts = defaultdict(int)
        
        for feedback in feedback_list:
            text_lower = feedback.feedback_text.lower()
            for issue_type, keywords in issue_keywords.items():
                if any(keyword in text_lower for keyword in keywords):
                    issue_counts[issue_type] += 1
        
        # Return top 3 issues
        sorted_issues = sorted(issue_counts.items(), key=lambda x: x[1], reverse=True)
        return [issue for issue, count in sorted_issues[:3] if count > 0]
    
    def _get_optimization_history(self, domain_name: str) -> List[Dict[str, Any]]:
        """Get optimization history for a domain."""
        try:
            with get_database_connection() as conn:
                cursor = conn.cursor()
                
                query = """
                SELECT optimization_id, optimization_type, changes_made, 
                       improvement_score, timestamp
                FROM config_optimizations co
                JOIN domain_configurations dc ON co.config_id = dc.id
                WHERE dc.domain_name = %s
                ORDER BY timestamp DESC
                LIMIT 10
                """
                
                cursor.execute(query, (domain_name,))
                results = cursor.fetchall()
                
                history = []
                for row in results:
                    history.append({
                        'optimization_id': row[0],
                        'optimization_type': row[1],
                        'changes_made': json.loads(row[2]) if row[2] else {},
                        'improvement_score': row[3],
                        'timestamp': row[4].isoformat() if row[4] else None
                    })
                
                return history
        
        except Exception as e:
            logger.error(f"Failed to get optimization history: {e}")
            return []
    
    def _generate_performance_recommendations(self, domain_name: str, 
                                            trends: List[PerformanceTrend],
                                            feedback_summary: Dict[str, Any]) -> List[str]:
        """Generate performance improvement recommendations."""
        recommendations = []
        
        # Trend-based recommendations
        declining_trends = [t for t in trends if t.trend_direction == 'declining' and t.trend_strength > 0.3]
        
        for trend in declining_trends:
            if trend.metric_name == 'chunk_quality_score':
                recommendations.append("Consider adjusting chunk size parameters to improve quality")
            elif trend.metric_name == 'bridge_success_rate':
                recommendations.append("Review bridge generation thresholds and validation criteria")
            elif trend.metric_name == 'retrieval_effectiveness':
                recommendations.append("Optimize embedding generation and similarity search parameters")
            elif trend.metric_name == 'processing_efficiency':
                recommendations.append("Implement performance optimizations and caching strategies")
        
        # Feedback-based recommendations
        if feedback_summary.get('average_rating', 0) < 3.0:
            recommendations.append("Address user satisfaction issues identified in feedback")
        
        common_issues = feedback_summary.get('common_issues', [])
        if 'quality' in common_issues:
            recommendations.append("Focus on improving content quality and accuracy")
        if 'relevance' in common_issues:
            recommendations.append("Enhance relevance scoring and content filtering")
        
        # General recommendations if no specific issues
        if not recommendations:
            recommendations.append("Continue monitoring performance metrics")
            recommendations.append("Consider A/B testing new configuration improvements")
        
        return recommendations[:5]  # Limit to top 5 recommendations
    
    def _store_performance_metrics(self, domain_name: str, metrics: PerformanceMetrics) -> None:
        """Store performance metrics in database."""
        try:
            with get_database_connection() as conn:
                cursor = conn.cursor()
                
                # Get or create domain configuration
                config_query = """
                SELECT id FROM domain_configurations 
                WHERE domain_name = %s AND is_active = true
                ORDER BY version DESC LIMIT 1
                """
                cursor.execute(config_query, (domain_name,))
                config_result = cursor.fetchone()
                
                if config_result:
                    config_id = config_result[0]
                    
                    insert_query = """
                    INSERT INTO config_performance_metrics 
                    (config_id, chunk_quality_score, bridge_success_rate, 
                     retrieval_effectiveness, user_satisfaction_score, 
                     processing_efficiency, boundary_quality, document_count, measurement_date)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """
                    
                    cursor.execute(insert_query, (
                        config_id, metrics.chunk_quality_score, metrics.bridge_success_rate,
                        metrics.retrieval_effectiveness, metrics.user_satisfaction_score,
                        metrics.processing_efficiency, metrics.boundary_quality,
                        metrics.document_count, metrics.measurement_date
                    ))
                    
                    conn.commit()
        
        except Exception as e:
            logger.error(f"Failed to store performance metrics: {e}")
    
    def _store_user_feedback(self, feedback_data: UserFeedbackData) -> None:
        """Store user feedback in database."""
        try:
            with get_database_connection() as conn:
                cursor = conn.cursor()
                
                insert_query = """
                INSERT INTO interaction_feedback 
                (feedback_id, chunk_id, user_id, interaction_type, 
                 feedback_score, context_query, timestamp)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """
                
                # Use first chunk_id if available, otherwise use domain name
                chunk_id = feedback_data.chunk_ids[0] if feedback_data.chunk_ids else feedback_data.domain_name
                
                cursor.execute(insert_query, (
                    feedback_data.feedback_id, chunk_id, feedback_data.user_id,
                    feedback_data.feedback_type, feedback_data.rating or 0.0,
                    feedback_data.feedback_text, feedback_data.timestamp
                ))
                
                conn.commit()
        
        except Exception as e:
            logger.error(f"Failed to store user feedback: {e}")
    
    def _store_performance_alert(self, alert: PerformanceAlert) -> None:
        """Store performance alert in database."""
        try:
            with get_database_connection() as conn:
                cursor = conn.cursor()
                
                # Create alerts table if it doesn't exist
                create_table_query = """
                CREATE TABLE IF NOT EXISTS performance_alerts (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    alert_id VARCHAR(100) UNIQUE NOT NULL,
                    domain_name VARCHAR(100) NOT NULL,
                    alert_type VARCHAR(50) NOT NULL,
                    severity VARCHAR(20) NOT NULL,
                    affected_metrics TEXT[],
                    current_values JSONB,
                    threshold_values JSONB,
                    suggested_actions TEXT[],
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    resolved_at TIMESTAMP,
                    is_resolved BOOLEAN DEFAULT FALSE
                )
                """
                cursor.execute(create_table_query)
                
                insert_query = """
                INSERT INTO performance_alerts 
                (alert_id, domain_name, alert_type, severity, affected_metrics,
                 current_values, threshold_values, suggested_actions, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                
                cursor.execute(insert_query, (
                    alert.alert_id, alert.domain_name, alert.alert_type, alert.severity,
                    alert.affected_metrics, json.dumps(alert.current_values),
                    json.dumps(alert.threshold_values), alert.suggested_actions,
                    alert.created_at
                ))
                
                conn.commit()
        
        except Exception as e:
            logger.error(f"Failed to store performance alert: {e}")