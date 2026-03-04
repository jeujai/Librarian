"""
Search Analytics and Monitoring for Multimodal Librarian.

This module provides comprehensive analytics, performance monitoring,
and optimization insights for the search system.
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict, Counter
import json
import asyncio
from enum import Enum

import numpy as np
import pandas as pd
from sklearn.metrics import ndcg_score

logger = logging.getLogger(__name__)


class SearchEventType(Enum):
    """Types of search events to track."""
    QUERY_SUBMITTED = "query_submitted"
    RESULTS_RETURNED = "results_returned"
    RESULT_CLICKED = "result_clicked"
    RESULT_RATED = "result_rated"
    QUERY_REFINED = "query_refined"
    SEARCH_ABANDONED = "search_abandoned"
    EXPORT_REQUESTED = "export_requested"


@dataclass
class SearchEvent:
    """Represents a search-related event."""
    event_id: str
    event_type: SearchEventType
    timestamp: datetime
    user_id: Optional[str]
    session_id: str
    query: str
    query_intent: Optional[str] = None
    query_complexity: Optional[str] = None
    search_strategy: Optional[str] = None
    results_count: int = 0
    response_time_ms: float = 0.0
    result_clicked: Optional[str] = None  # chunk_id if clicked
    click_position: Optional[int] = None
    rating: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchMetrics:
    """Aggregated search metrics."""
    total_queries: int = 0
    unique_users: int = 0
    avg_response_time_ms: float = 0.0
    avg_results_per_query: float = 0.0
    click_through_rate: float = 0.0
    query_success_rate: float = 0.0
    query_refinement_rate: float = 0.0
    search_abandonment_rate: float = 0.0
    avg_rating: float = 0.0
    ndcg_score: float = 0.0
    
    # Intent-based metrics
    intent_distribution: Dict[str, int] = field(default_factory=dict)
    complexity_distribution: Dict[str, int] = field(default_factory=dict)
    strategy_performance: Dict[str, float] = field(default_factory=dict)
    
    # Temporal metrics
    queries_per_hour: Dict[int, int] = field(default_factory=dict)
    peak_hours: List[int] = field(default_factory=list)
    
    # Quality metrics
    top_performing_queries: List[Tuple[str, float]] = field(default_factory=list)
    poor_performing_queries: List[Tuple[str, float]] = field(default_factory=list)


@dataclass
class PerformanceAlert:
    """Performance alert for monitoring."""
    alert_id: str
    alert_type: str  # latency, accuracy, volume
    severity: str  # low, medium, high, critical
    message: str
    timestamp: datetime
    metrics: Dict[str, Any]
    threshold_breached: str
    suggested_actions: List[str] = field(default_factory=list)


class SearchAnalyticsCollector:
    """Collects and stores search analytics events."""
    
    def __init__(self, storage_backend: str = "memory"):
        """
        Initialize analytics collector.
        
        Args:
            storage_backend: Storage backend (memory, database, file)
        """
        self.storage_backend = storage_backend
        self.events = []  # In-memory storage
        self.session_data = defaultdict(list)
        self.user_data = defaultdict(list)
        
        # Performance thresholds
        self.thresholds = {
            'response_time_ms': 5000,  # 5 seconds
            'click_through_rate': 0.1,  # 10%
            'success_rate': 0.7,  # 70%
            'abandonment_rate': 0.3  # 30%
        }
        
        logger.info(f"Search analytics collector initialized with {storage_backend} backend")
    
    async def record_event(self, event: SearchEvent) -> None:
        """
        Record a search event.
        
        Args:
            event: Search event to record
        """
        try:
            # Store event
            if self.storage_backend == "memory":
                self.events.append(event)
            elif self.storage_backend == "database":
                await self._store_event_in_database(event)
            elif self.storage_backend == "file":
                await self._store_event_in_file(event)
            
            # Update session and user data
            self.session_data[event.session_id].append(event)
            if event.user_id:
                self.user_data[event.user_id].append(event)
            
            logger.debug(f"Recorded search event: {event.event_type.value}")
            
        except Exception as e:
            logger.error(f"Failed to record search event: {e}")
    
    async def record_query_submitted(
        self,
        query: str,
        user_id: Optional[str],
        session_id: str,
        query_intent: Optional[str] = None,
        query_complexity: Optional[str] = None,
        search_strategy: Optional[str] = None
    ) -> str:
        """Record a query submission event."""
        event_id = f"query_{datetime.now().timestamp()}"
        event = SearchEvent(
            event_id=event_id,
            event_type=SearchEventType.QUERY_SUBMITTED,
            timestamp=datetime.now(),
            user_id=user_id,
            session_id=session_id,
            query=query,
            query_intent=query_intent,
            query_complexity=query_complexity,
            search_strategy=search_strategy
        )
        await self.record_event(event)
        return event_id
    
    async def record_results_returned(
        self,
        event_id: str,
        results_count: int,
        response_time_ms: float
    ) -> None:
        """Record search results returned."""
        # Find the original query event
        original_event = None
        for event in reversed(self.events):
            if event.event_id == event_id:
                original_event = event
                break
        
        if original_event:
            # Update the original event
            original_event.results_count = results_count
            original_event.response_time_ms = response_time_ms
            
            # Create results event
            results_event = SearchEvent(
                event_id=f"results_{event_id}",
                event_type=SearchEventType.RESULTS_RETURNED,
                timestamp=datetime.now(),
                user_id=original_event.user_id,
                session_id=original_event.session_id,
                query=original_event.query,
                query_intent=original_event.query_intent,
                query_complexity=original_event.query_complexity,
                search_strategy=original_event.search_strategy,
                results_count=results_count,
                response_time_ms=response_time_ms
            )
            await self.record_event(results_event)
    
    async def record_result_clicked(
        self,
        session_id: str,
        query: str,
        chunk_id: str,
        position: int
    ) -> None:
        """Record a result click."""
        event = SearchEvent(
            event_id=f"click_{datetime.now().timestamp()}",
            event_type=SearchEventType.RESULT_CLICKED,
            timestamp=datetime.now(),
            user_id=None,
            session_id=session_id,
            query=query,
            result_clicked=chunk_id,
            click_position=position
        )
        await self.record_event(event)
    
    async def record_result_rating(
        self,
        session_id: str,
        query: str,
        chunk_id: str,
        rating: float
    ) -> None:
        """Record a result rating."""
        event = SearchEvent(
            event_id=f"rating_{datetime.now().timestamp()}",
            event_type=SearchEventType.RESULT_RATED,
            timestamp=datetime.now(),
            user_id=None,
            session_id=session_id,
            query=query,
            result_clicked=chunk_id,
            rating=rating
        )
        await self.record_event(event)
    
    async def _store_event_in_database(self, event: SearchEvent) -> None:
        """Store event in database (placeholder)."""
        # This would implement actual database storage
        pass
    
    async def _store_event_in_file(self, event: SearchEvent) -> None:
        """Store event in file (placeholder)."""
        # This would implement file-based storage
        pass


class SearchMetricsCalculator:
    """Calculates search performance metrics from events."""
    
    def __init__(self, collector: SearchAnalyticsCollector):
        """
        Initialize metrics calculator.
        
        Args:
            collector: Analytics collector instance
        """
        self.collector = collector
    
    def calculate_metrics(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> SearchMetrics:
        """
        Calculate comprehensive search metrics.
        
        Args:
            start_time: Start of time range (default: 24 hours ago)
            end_time: End of time range (default: now)
            
        Returns:
            Calculated search metrics
        """
        if start_time is None:
            start_time = datetime.now() - timedelta(hours=24)
        if end_time is None:
            end_time = datetime.now()
        
        # Filter events by time range
        events = [
            event for event in self.collector.events
            if start_time <= event.timestamp <= end_time
        ]
        
        if not events:
            return SearchMetrics()
        
        metrics = SearchMetrics()
        
        # Basic metrics
        query_events = [e for e in events if e.event_type == SearchEventType.QUERY_SUBMITTED]
        result_events = [e for e in events if e.event_type == SearchEventType.RESULTS_RETURNED]
        click_events = [e for e in events if e.event_type == SearchEventType.RESULT_CLICKED]
        rating_events = [e for e in events if e.event_type == SearchEventType.RESULT_RATED]
        
        metrics.total_queries = len(query_events)
        metrics.unique_users = len(set(e.user_id for e in query_events if e.user_id))
        
        # Response time metrics
        if result_events:
            response_times = [e.response_time_ms for e in result_events if e.response_time_ms > 0]
            metrics.avg_response_time_ms = np.mean(response_times) if response_times else 0.0
        
        # Results per query
        if result_events:
            results_counts = [e.results_count for e in result_events]
            metrics.avg_results_per_query = np.mean(results_counts) if results_counts else 0.0
        
        # Click-through rate
        if query_events:
            metrics.click_through_rate = len(click_events) / len(query_events)
        
        # Query success rate (queries that got clicks or ratings)
        successful_sessions = set()
        for event in click_events + rating_events:
            successful_sessions.add(event.session_id)
        
        total_sessions = len(set(e.session_id for e in query_events))
        if total_sessions > 0:
            metrics.query_success_rate = len(successful_sessions) / total_sessions
        
        # Average rating
        if rating_events:
            ratings = [e.rating for e in rating_events if e.rating is not None]
            metrics.avg_rating = np.mean(ratings) if ratings else 0.0
        
        # Intent and complexity distribution
        for event in query_events:
            if event.query_intent:
                metrics.intent_distribution[event.query_intent] = \
                    metrics.intent_distribution.get(event.query_intent, 0) + 1
            if event.query_complexity:
                metrics.complexity_distribution[event.query_complexity] = \
                    metrics.complexity_distribution.get(event.query_complexity, 0) + 1
        
        # Strategy performance
        strategy_clicks = defaultdict(int)
        strategy_queries = defaultdict(int)
        
        for event in query_events:
            if event.search_strategy:
                strategy_queries[event.search_strategy] += 1
        
        for event in click_events:
            # Find corresponding query event
            query_event = self._find_query_event_for_click(event, query_events)
            if query_event and query_event.search_strategy:
                strategy_clicks[query_event.search_strategy] += 1
        
        for strategy in strategy_queries:
            if strategy_queries[strategy] > 0:
                metrics.strategy_performance[strategy] = \
                    strategy_clicks[strategy] / strategy_queries[strategy]
        
        # Temporal metrics
        for event in query_events:
            hour = event.timestamp.hour
            metrics.queries_per_hour[hour] = metrics.queries_per_hour.get(hour, 0) + 1
        
        # Find peak hours (top 3)
        if metrics.queries_per_hour:
            sorted_hours = sorted(metrics.queries_per_hour.items(), key=lambda x: x[1], reverse=True)
            metrics.peak_hours = [hour for hour, count in sorted_hours[:3]]
        
        # Query performance analysis
        metrics.top_performing_queries = self._analyze_query_performance(events, top=True)
        metrics.poor_performing_queries = self._analyze_query_performance(events, top=False)
        
        # NDCG calculation (simplified)
        metrics.ndcg_score = self._calculate_ndcg(events)
        
        return metrics
    
    def _find_query_event_for_click(self, click_event: SearchEvent, query_events: List[SearchEvent]) -> Optional[SearchEvent]:
        """Find the query event that corresponds to a click event."""
        # Find the most recent query in the same session
        session_queries = [
            e for e in query_events
            if e.session_id == click_event.session_id and e.timestamp <= click_event.timestamp
        ]
        
        if session_queries:
            return max(session_queries, key=lambda x: x.timestamp)
        
        return None
    
    def _analyze_query_performance(self, events: List[SearchEvent], top: bool = True) -> List[Tuple[str, float]]:
        """Analyze query performance to find top/poor performing queries."""
        query_performance = defaultdict(list)
        
        # Group events by query
        for event in events:
            if event.event_type in [SearchEventType.RESULT_CLICKED, SearchEventType.RESULT_RATED]:
                score = 1.0 if event.event_type == SearchEventType.RESULT_CLICKED else (event.rating or 0.0)
                query_performance[event.query].append(score)
        
        # Calculate average performance per query
        query_scores = {}
        for query, scores in query_performance.items():
            if len(scores) >= 2:  # Only consider queries with multiple interactions
                query_scores[query] = np.mean(scores)
        
        # Sort and return top/bottom queries
        sorted_queries = sorted(query_scores.items(), key=lambda x: x[1], reverse=top)
        return sorted_queries[:10]  # Top/bottom 10
    
    def _calculate_ndcg(self, events: List[SearchEvent]) -> float:
        """Calculate NDCG score (simplified implementation)."""
        try:
            # This is a simplified NDCG calculation
            # In practice, you'd need more sophisticated relevance scoring
            
            session_scores = defaultdict(list)
            
            # Group clicks by session and calculate position-based scores
            for event in events:
                if event.event_type == SearchEventType.RESULT_CLICKED and event.click_position:
                    # Higher score for higher positions (lower position numbers)
                    score = 1.0 / event.click_position
                    session_scores[event.session_id].append(score)
            
            if not session_scores:
                return 0.0
            
            # Calculate average NDCG across sessions
            ndcg_scores = []
            for session_id, scores in session_scores.items():
                if len(scores) > 1:
                    # Simple NDCG approximation
                    dcg = sum(score / np.log2(i + 2) for i, score in enumerate(scores))
                    ideal_scores = sorted(scores, reverse=True)
                    idcg = sum(score / np.log2(i + 2) for i, score in enumerate(ideal_scores))
                    
                    if idcg > 0:
                        ndcg_scores.append(dcg / idcg)
            
            return np.mean(ndcg_scores) if ndcg_scores else 0.0
            
        except Exception as e:
            logger.error(f"Failed to calculate NDCG: {e}")
            return 0.0


class SearchPerformanceMonitor:
    """Monitors search performance and generates alerts."""
    
    def __init__(self, collector: SearchAnalyticsCollector, calculator: SearchMetricsCalculator):
        """
        Initialize performance monitor.
        
        Args:
            collector: Analytics collector
            calculator: Metrics calculator
        """
        self.collector = collector
        self.calculator = calculator
        self.alerts = []
        
        # Alert thresholds
        self.thresholds = {
            'response_time_ms': 5000,
            'click_through_rate': 0.1,
            'success_rate': 0.7,
            'abandonment_rate': 0.3,
            'avg_rating': 3.0
        }
    
    async def check_performance(self) -> List[PerformanceAlert]:
        """
        Check current performance and generate alerts.
        
        Returns:
            List of performance alerts
        """
        current_metrics = self.calculator.calculate_metrics()
        alerts = []
        
        # Response time alert
        if current_metrics.avg_response_time_ms > self.thresholds['response_time_ms']:
            alert = PerformanceAlert(
                alert_id=f"latency_{datetime.now().timestamp()}",
                alert_type="latency",
                severity="high" if current_metrics.avg_response_time_ms > 10000 else "medium",
                message=f"Average response time is {current_metrics.avg_response_time_ms:.0f}ms",
                timestamp=datetime.now(),
                metrics={"avg_response_time_ms": current_metrics.avg_response_time_ms},
                threshold_breached="response_time_ms",
                suggested_actions=[
                    "Check vector database performance",
                    "Review query complexity",
                    "Consider caching optimization"
                ]
            )
            alerts.append(alert)
        
        # Click-through rate alert
        if current_metrics.click_through_rate < self.thresholds['click_through_rate']:
            alert = PerformanceAlert(
                alert_id=f"ctr_{datetime.now().timestamp()}",
                alert_type="accuracy",
                severity="medium",
                message=f"Click-through rate is {current_metrics.click_through_rate:.2%}",
                timestamp=datetime.now(),
                metrics={"click_through_rate": current_metrics.click_through_rate},
                threshold_breached="click_through_rate",
                suggested_actions=[
                    "Review search result relevance",
                    "Improve result ranking",
                    "Analyze query understanding accuracy"
                ]
            )
            alerts.append(alert)
        
        # Success rate alert
        if current_metrics.query_success_rate < self.thresholds['success_rate']:
            alert = PerformanceAlert(
                alert_id=f"success_{datetime.now().timestamp()}",
                alert_type="accuracy",
                severity="high",
                message=f"Query success rate is {current_metrics.query_success_rate:.2%}",
                timestamp=datetime.now(),
                metrics={"query_success_rate": current_metrics.query_success_rate},
                threshold_breached="success_rate",
                suggested_actions=[
                    "Analyze failed queries",
                    "Improve search algorithms",
                    "Enhance query expansion"
                ]
            )
            alerts.append(alert)
        
        # Rating alert
        if current_metrics.avg_rating > 0 and current_metrics.avg_rating < self.thresholds['avg_rating']:
            alert = PerformanceAlert(
                alert_id=f"rating_{datetime.now().timestamp()}",
                alert_type="accuracy",
                severity="medium",
                message=f"Average rating is {current_metrics.avg_rating:.1f}",
                timestamp=datetime.now(),
                metrics={"avg_rating": current_metrics.avg_rating},
                threshold_breached="avg_rating",
                suggested_actions=[
                    "Review low-rated results",
                    "Improve result quality",
                    "Gather more user feedback"
                ]
            )
            alerts.append(alert)
        
        # Store alerts
        self.alerts.extend(alerts)
        
        # Log alerts
        for alert in alerts:
            logger.warning(f"Performance alert: {alert.message} (Severity: {alert.severity})")
        
        return alerts
    
    def get_recent_alerts(self, hours: int = 24) -> List[PerformanceAlert]:
        """Get alerts from the last N hours."""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        return [
            alert for alert in self.alerts
            if alert.timestamp >= cutoff_time
        ]


class SearchAnalyticsDashboard:
    """Provides dashboard data for search analytics visualization."""
    
    def __init__(self, calculator: SearchMetricsCalculator, monitor: SearchPerformanceMonitor):
        """
        Initialize analytics dashboard.
        
        Args:
            calculator: Metrics calculator
            monitor: Performance monitor
        """
        self.calculator = calculator
        self.monitor = monitor
    
    def get_dashboard_data(self, time_range_hours: int = 24) -> Dict[str, Any]:
        """
        Get comprehensive dashboard data.
        
        Args:
            time_range_hours: Time range for metrics calculation
            
        Returns:
            Dashboard data dictionary
        """
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=time_range_hours)
        
        # Calculate current metrics
        current_metrics = self.calculator.calculate_metrics(start_time, end_time)
        
        # Get recent alerts
        recent_alerts = self.monitor.get_recent_alerts(time_range_hours)
        
        # Prepare dashboard data
        dashboard_data = {
            'overview': {
                'total_queries': current_metrics.total_queries,
                'unique_users': current_metrics.unique_users,
                'avg_response_time_ms': current_metrics.avg_response_time_ms,
                'click_through_rate': current_metrics.click_through_rate,
                'success_rate': current_metrics.query_success_rate,
                'avg_rating': current_metrics.avg_rating
            },
            'performance': {
                'response_time_trend': self._get_response_time_trend(time_range_hours),
                'query_volume_trend': self._get_query_volume_trend(time_range_hours),
                'success_rate_trend': self._get_success_rate_trend(time_range_hours)
            },
            'distribution': {
                'intent_distribution': current_metrics.intent_distribution,
                'complexity_distribution': current_metrics.complexity_distribution,
                'strategy_performance': current_metrics.strategy_performance,
                'hourly_distribution': current_metrics.queries_per_hour
            },
            'quality': {
                'top_performing_queries': current_metrics.top_performing_queries,
                'poor_performing_queries': current_metrics.poor_performing_queries,
                'ndcg_score': current_metrics.ndcg_score
            },
            'alerts': {
                'recent_alerts': [
                    {
                        'type': alert.alert_type,
                        'severity': alert.severity,
                        'message': alert.message,
                        'timestamp': alert.timestamp.isoformat(),
                        'suggested_actions': alert.suggested_actions
                    }
                    for alert in recent_alerts
                ],
                'alert_count_by_severity': self._count_alerts_by_severity(recent_alerts)
            },
            'metadata': {
                'time_range_hours': time_range_hours,
                'generated_at': datetime.now().isoformat(),
                'data_points': len(self.calculator.collector.events)
            }
        }
        
        return dashboard_data
    
    def _get_response_time_trend(self, hours: int) -> List[Dict[str, Any]]:
        """Get response time trend data."""
        # This would implement time-series data for response times
        # Placeholder implementation
        return []
    
    def _get_query_volume_trend(self, hours: int) -> List[Dict[str, Any]]:
        """Get query volume trend data."""
        # This would implement time-series data for query volumes
        # Placeholder implementation
        return []
    
    def _get_success_rate_trend(self, hours: int) -> List[Dict[str, Any]]:
        """Get success rate trend data."""
        # This would implement time-series data for success rates
        # Placeholder implementation
        return []
    
    def _count_alerts_by_severity(self, alerts: List[PerformanceAlert]) -> Dict[str, int]:
        """Count alerts by severity level."""
        severity_counts = defaultdict(int)
        for alert in alerts:
            severity_counts[alert.severity] += 1
        return dict(severity_counts)