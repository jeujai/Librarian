"""
Search Performance Monitor

This module provides real-time monitoring and analysis of search performance,
integrating with the existing monitoring infrastructure to track search latency,
throughput, and quality metrics.

Validates: Requirement 2.1 - Search Service Performance Optimization
"""

import asyncio
import time
import statistics
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, asdict
from collections import deque, defaultdict
import threading
import json

from ..config import get_settings
from ..logging_config import get_logger
from .metrics_collector import MetricsCollector
from .performance_monitor import PerformanceMonitor, PerformanceAlert


@dataclass
class SearchPerformanceMetric:
    """Individual search performance measurement."""
    timestamp: datetime
    query_text: str
    query_type: str
    service_type: str  # 'simple', 'enhanced', 'fallback'
    
    # Timing metrics (milliseconds)
    total_latency_ms: float
    vector_search_ms: Optional[float] = None
    result_processing_ms: Optional[float] = None
    cache_lookup_ms: Optional[float] = None
    
    # Quality metrics
    result_count: int = 0
    relevance_score: Optional[float] = None
    
    # Status
    success: bool = True
    error_type: Optional[str] = None
    cache_hit: bool = False
    fallback_used: bool = False


@dataclass
class SearchPerformanceThreshold:
    """Search-specific performance thresholds."""
    metric_name: str
    warning_threshold: float
    critical_threshold: float
    query_type: Optional[str] = None  # Apply to specific query types
    service_type: Optional[str] = None  # Apply to specific services


class SearchPerformanceMonitor:
    """Monitors search performance in real-time."""
    
    def __init__(self, metrics_collector: Optional[MetricsCollector] = None):
        self.settings = get_settings()
        self.logger = get_logger("search_performance_monitor")
        self.metrics_collector = metrics_collector
        
        # Performance data storage
        self._search_metrics = deque(maxlen=50000)  # Last 50k searches
        self._performance_summaries = deque(maxlen=1440)  # 24 hours of minute summaries
        
        # Real-time tracking
        self._current_minute_metrics = []
        self._last_summary_time = datetime.now().replace(second=0, microsecond=0)
        
        # Performance thresholds
        self._search_thresholds = self._initialize_search_thresholds()
        
        # Alert callbacks
        self._alert_callbacks: List[Callable[[PerformanceAlert], None]] = []
        
        # Thread safety
        self._lock = threading.Lock()
        
        # Background monitoring
        self._monitoring_active = False
        self._start_background_monitoring()
        
        self.logger.info("Search performance monitor initialized")
    
    def _initialize_search_thresholds(self) -> List[SearchPerformanceThreshold]:
        """Initialize search-specific performance thresholds."""
        return [
            # General search latency thresholds
            SearchPerformanceThreshold(
                metric_name="avg_search_latency_ms",
                warning_threshold=500.0,  # 500ms
                critical_threshold=1000.0  # 1 second
            ),
            SearchPerformanceThreshold(
                metric_name="p95_search_latency_ms",
                warning_threshold=1000.0,  # 1 second
                critical_threshold=2000.0  # 2 seconds
            ),
            SearchPerformanceThreshold(
                metric_name="p99_search_latency_ms",
                warning_threshold=2000.0,  # 2 seconds
                critical_threshold=5000.0  # 5 seconds
            ),
            
            # Search success rate
            SearchPerformanceThreshold(
                metric_name="search_success_rate_percent",
                warning_threshold=95.0,  # Below 95%
                critical_threshold=90.0  # Below 90%
            ),
            
            # Fallback usage rate
            SearchPerformanceThreshold(
                metric_name="fallback_usage_percent",
                warning_threshold=10.0,  # Above 10%
                critical_threshold=25.0  # Above 25%
            ),
            
            # Cache performance
            SearchPerformanceThreshold(
                metric_name="cache_hit_rate_percent",
                warning_threshold=70.0,  # Below 70%
                critical_threshold=50.0  # Below 50%
            ),
            
            # Query-specific thresholds
            SearchPerformanceThreshold(
                metric_name="avg_search_latency_ms",
                warning_threshold=300.0,
                critical_threshold=600.0,
                query_type="simple_keyword"
            ),
            SearchPerformanceThreshold(
                metric_name="avg_search_latency_ms",
                warning_threshold=800.0,
                critical_threshold=1500.0,
                query_type="complex_technical"
            ),
            
            # Service-specific thresholds
            SearchPerformanceThreshold(
                metric_name="avg_search_latency_ms",
                warning_threshold=200.0,
                critical_threshold=400.0,
                service_type="simple"
            ),
            SearchPerformanceThreshold(
                metric_name="avg_search_latency_ms",
                warning_threshold=600.0,
                critical_threshold=1200.0,
                service_type="enhanced"
            )
        ]
    
    def record_search_performance(
        self,
        query_text: str,
        query_type: str,
        service_type: str,
        total_latency_ms: float,
        result_count: int = 0,
        success: bool = True,
        vector_search_ms: Optional[float] = None,
        result_processing_ms: Optional[float] = None,
        cache_lookup_ms: Optional[float] = None,
        relevance_score: Optional[float] = None,
        error_type: Optional[str] = None,
        cache_hit: bool = False,
        fallback_used: bool = False
    ) -> None:
        """Record a search performance measurement."""
        
        metric = SearchPerformanceMetric(
            timestamp=datetime.now(),
            query_text=query_text[:100],  # Truncate for storage
            query_type=query_type,
            service_type=service_type,
            total_latency_ms=total_latency_ms,
            vector_search_ms=vector_search_ms,
            result_processing_ms=result_processing_ms,
            cache_lookup_ms=cache_lookup_ms,
            result_count=result_count,
            relevance_score=relevance_score,
            success=success,
            error_type=error_type,
            cache_hit=cache_hit,
            fallback_used=fallback_used
        )
        
        with self._lock:
            self._search_metrics.append(metric)
            self._current_minute_metrics.append(metric)
        
        # Record in general metrics collector if available
        if self.metrics_collector:
            self.metrics_collector.record_request(
                endpoint="/search",
                method="POST",
                response_time=total_latency_ms / 1000,  # Convert to seconds
                status_code=200 if success else 500,
                user_id=None
            )
        
        # Check thresholds in real-time for critical alerts
        self._check_real_time_thresholds(metric)
    
    def _check_real_time_thresholds(self, metric: SearchPerformanceMetric) -> None:
        """Check if individual search exceeds critical thresholds."""
        
        # Check for extremely slow searches
        if metric.total_latency_ms > 5000:  # 5 seconds
            self._generate_search_alert(
                "critical_search_latency",
                f"Extremely slow search: {metric.total_latency_ms:.0f}ms for query type '{metric.query_type}'",
                "critical",
                {
                    "query_type": metric.query_type,
                    "service_type": metric.service_type,
                    "latency_ms": metric.total_latency_ms,
                    "query_preview": metric.query_text[:50]
                }
            )
        
        # Check for search failures
        if not metric.success:
            self._generate_search_alert(
                "search_failure",
                f"Search failed: {metric.error_type or 'Unknown error'} for query type '{metric.query_type}'",
                "warning",
                {
                    "query_type": metric.query_type,
                    "service_type": metric.service_type,
                    "error_type": metric.error_type,
                    "query_preview": metric.query_text[:50]
                }
            )
    
    def _generate_search_alert(
        self, 
        alert_type: str, 
        message: str, 
        severity: str, 
        context: Dict[str, Any]
    ) -> None:
        """Generate a search-specific performance alert."""
        
        alert = PerformanceAlert(
            alert_type=alert_type,
            severity=severity,
            message=message,
            metric_name="search_performance",
            current_value=context.get("latency_ms", 0),
            threshold=0,  # Context-dependent
            timestamp=datetime.now()
        )
        
        # Notify callbacks
        for callback in self._alert_callbacks:
            try:
                callback(alert)
            except Exception as e:
                self.logger.error(f"Error in search alert callback: {e}")
        
        self.logger.warning(f"Search performance alert: {message}")
    
    def get_current_search_performance(self) -> Dict[str, Any]:
        """Get current search performance metrics."""
        
        with self._lock:
            if not self._search_metrics:
                return {"error": "No search performance data available"}
            
            # Get recent metrics (last 5 minutes)
            now = datetime.now()
            recent_cutoff = now - timedelta(minutes=5)
            recent_metrics = [
                m for m in self._search_metrics 
                if m.timestamp >= recent_cutoff
            ]
            
            if not recent_metrics:
                return {"error": "No recent search performance data"}
            
            # Calculate current performance statistics
            successful_searches = [m for m in recent_metrics if m.success]
            
            # Latency statistics
            if successful_searches:
                latencies = [m.total_latency_ms for m in successful_searches]
                avg_latency = statistics.mean(latencies)
                median_latency = statistics.median(latencies)
                p95_latency = sorted(latencies)[int(0.95 * len(latencies))] if len(latencies) > 1 else latencies[0]
                p99_latency = sorted(latencies)[int(0.99 * len(latencies))] if len(latencies) > 1 else latencies[0]
            else:
                avg_latency = median_latency = p95_latency = p99_latency = 0
            
            # Success rate
            success_rate = (len(successful_searches) / len(recent_metrics)) * 100
            
            # Cache performance
            cache_hits = len([m for m in recent_metrics if m.cache_hit])
            cache_hit_rate = (cache_hits / len(recent_metrics)) * 100 if recent_metrics else 0
            
            # Fallback usage
            fallback_uses = len([m for m in recent_metrics if m.fallback_used])
            fallback_rate = (fallback_uses / len(recent_metrics)) * 100 if recent_metrics else 0
            
            # Service breakdown
            service_breakdown = defaultdict(int)
            for metric in recent_metrics:
                service_breakdown[metric.service_type] += 1
            
            # Query type breakdown
            query_type_breakdown = defaultdict(int)
            for metric in recent_metrics:
                query_type_breakdown[metric.query_type] += 1
            
            return {
                "timestamp": now.isoformat(),
                "period_minutes": 5,
                "total_searches": len(recent_metrics),
                "successful_searches": len(successful_searches),
                "latency_metrics": {
                    "avg_latency_ms": round(avg_latency, 2),
                    "median_latency_ms": round(median_latency, 2),
                    "p95_latency_ms": round(p95_latency, 2),
                    "p99_latency_ms": round(p99_latency, 2),
                    "min_latency_ms": round(min([m.total_latency_ms for m in successful_searches]), 2) if successful_searches else 0,
                    "max_latency_ms": round(max([m.total_latency_ms for m in successful_searches]), 2) if successful_searches else 0
                },
                "quality_metrics": {
                    "success_rate_percent": round(success_rate, 2),
                    "cache_hit_rate_percent": round(cache_hit_rate, 2),
                    "fallback_usage_percent": round(fallback_rate, 2),
                    "avg_result_count": round(statistics.mean([m.result_count for m in successful_searches]), 2) if successful_searches else 0
                },
                "service_breakdown": dict(service_breakdown),
                "query_type_breakdown": dict(query_type_breakdown),
                "throughput": {
                    "searches_per_minute": len(recent_metrics) / 5,
                    "successful_searches_per_minute": len(successful_searches) / 5
                }
            }
    
    def get_search_performance_history(self, hours: int = 24) -> Dict[str, Any]:
        """Get historical search performance data."""
        
        with self._lock:
            cutoff_time = datetime.now() - timedelta(hours=hours)
            
            historical_metrics = [
                m for m in self._search_metrics
                if m.timestamp >= cutoff_time
            ]
            
            if not historical_metrics:
                return {"error": "No historical search performance data available"}
            
            # Group by hour for trend analysis
            hourly_data = defaultdict(list)
            for metric in historical_metrics:
                hour_key = metric.timestamp.strftime('%Y-%m-%d %H:00')
                hourly_data[hour_key].append(metric)
            
            # Calculate hourly statistics
            hourly_stats = []
            for hour, metrics in sorted(hourly_data.items()):
                successful_metrics = [m for m in metrics if m.success]
                
                if successful_metrics:
                    latencies = [m.total_latency_ms for m in successful_metrics]
                    avg_latency = statistics.mean(latencies)
                    p95_latency = sorted(latencies)[int(0.95 * len(latencies))]
                else:
                    avg_latency = p95_latency = 0
                
                success_rate = (len(successful_metrics) / len(metrics)) * 100
                cache_hit_rate = (len([m for m in metrics if m.cache_hit]) / len(metrics)) * 100
                fallback_rate = (len([m for m in metrics if m.fallback_used]) / len(metrics)) * 100
                
                hourly_stats.append({
                    "hour": hour,
                    "total_searches": len(metrics),
                    "successful_searches": len(successful_metrics),
                    "avg_latency_ms": round(avg_latency, 2),
                    "p95_latency_ms": round(p95_latency, 2),
                    "success_rate_percent": round(success_rate, 2),
                    "cache_hit_rate_percent": round(cache_hit_rate, 2),
                    "fallback_usage_percent": round(fallback_rate, 2)
                })
            
            # Calculate overall period statistics
            successful_metrics = [m for m in historical_metrics if m.success]
            
            if successful_metrics:
                all_latencies = [m.total_latency_ms for m in successful_metrics]
                period_stats = {
                    "avg_latency_ms": round(statistics.mean(all_latencies), 2),
                    "median_latency_ms": round(statistics.median(all_latencies), 2),
                    "p95_latency_ms": round(sorted(all_latencies)[int(0.95 * len(all_latencies))], 2),
                    "p99_latency_ms": round(sorted(all_latencies)[int(0.99 * len(all_latencies))], 2),
                    "min_latency_ms": round(min(all_latencies), 2),
                    "max_latency_ms": round(max(all_latencies), 2)
                }
            else:
                period_stats = {
                    "avg_latency_ms": 0,
                    "median_latency_ms": 0,
                    "p95_latency_ms": 0,
                    "p99_latency_ms": 0,
                    "min_latency_ms": 0,
                    "max_latency_ms": 0
                }
            
            return {
                "period_hours": hours,
                "total_searches": len(historical_metrics),
                "successful_searches": len(successful_metrics),
                "overall_success_rate_percent": round((len(successful_metrics) / len(historical_metrics)) * 100, 2),
                "period_statistics": period_stats,
                "hourly_breakdown": hourly_stats,
                "performance_summaries": list(self._performance_summaries)[-hours*60:]  # Last N hours of minute summaries
            }
    
    def analyze_search_bottlenecks(self, hours: int = 1) -> List[Dict[str, Any]]:
        """Analyze search performance bottlenecks."""
        
        with self._lock:
            cutoff_time = datetime.now() - timedelta(hours=hours)
            
            recent_metrics = [
                m for m in self._search_metrics
                if m.timestamp >= cutoff_time and m.success
            ]
            
            if not recent_metrics:
                return []
            
            bottlenecks = []
            
            # Analyze component timing breakdown
            metrics_with_breakdown = [
                m for m in recent_metrics 
                if m.vector_search_ms is not None and m.result_processing_ms is not None
            ]
            
            if metrics_with_breakdown:
                # Vector search bottleneck analysis
                vector_times = [m.vector_search_ms for m in metrics_with_breakdown]
                total_times = [m.total_latency_ms for m in metrics_with_breakdown]
                
                avg_vector_time = statistics.mean(vector_times)
                avg_total_time = statistics.mean(total_times)
                vector_percentage = (avg_vector_time / avg_total_time) * 100
                
                if vector_percentage > 70:  # Vector search dominates
                    bottlenecks.append({
                        "component": "vector_search",
                        "description": f"Vector search consuming {vector_percentage:.1f}% of search time",
                        "avg_time_ms": round(avg_vector_time, 2),
                        "impact_level": "high" if vector_percentage > 85 else "medium",
                        "recommendations": [
                            "Optimize vector database indexing",
                            "Consider vector dimension reduction",
                            "Implement vector result caching"
                        ]
                    })
                
                # Result processing bottleneck analysis
                processing_times = [m.result_processing_ms for m in metrics_with_breakdown]
                avg_processing_time = statistics.mean(processing_times)
                processing_percentage = (avg_processing_time / avg_total_time) * 100
                
                if processing_percentage > 30:  # Result processing is significant
                    bottlenecks.append({
                        "component": "result_processing",
                        "description": f"Result processing consuming {processing_percentage:.1f}% of search time",
                        "avg_time_ms": round(avg_processing_time, 2),
                        "impact_level": "medium" if processing_percentage > 50 else "low",
                        "recommendations": [
                            "Optimize result serialization",
                            "Reduce metadata processing overhead",
                            "Implement result format caching"
                        ]
                    })
            
            # Analyze query type performance variations
            query_type_performance = defaultdict(list)
            for metric in recent_metrics:
                query_type_performance[metric.query_type].append(metric.total_latency_ms)
            
            if len(query_type_performance) > 1:
                overall_avg = statistics.mean([m.total_latency_ms for m in recent_metrics])
                
                for query_type, latencies in query_type_performance.items():
                    avg_latency = statistics.mean(latencies)
                    
                    if avg_latency > overall_avg * 1.5:  # 50% slower than average
                        bottlenecks.append({
                            "component": f"query_type_{query_type}",
                            "description": f"Query type '{query_type}' shows {((avg_latency / overall_avg) - 1) * 100:.1f}% higher latency",
                            "avg_time_ms": round(avg_latency, 2),
                            "impact_level": "medium",
                            "recommendations": [
                                f"Optimize handling of {query_type} queries",
                                "Consider query-specific preprocessing",
                                "Implement specialized caching for this query type"
                            ]
                        })
            
            # Analyze service performance variations
            service_performance = defaultdict(list)
            for metric in recent_metrics:
                service_performance[metric.service_type].append(metric.total_latency_ms)
            
            if len(service_performance) > 1:
                for service_type, latencies in service_performance.items():
                    avg_latency = statistics.mean(latencies)
                    
                    # Check if this service is significantly slower
                    other_services = [
                        statistics.mean(other_latencies) 
                        for other_service, other_latencies in service_performance.items()
                        if other_service != service_type
                    ]
                    
                    if other_services:
                        min_other_avg = min(other_services)
                        
                        if avg_latency > min_other_avg * 2:  # 2x slower than best service
                            bottlenecks.append({
                                "component": f"service_{service_type}",
                                "description": f"Service '{service_type}' shows significantly higher latency than alternatives",
                                "avg_time_ms": round(avg_latency, 2),
                                "impact_level": "high",
                                "recommendations": [
                                    f"Investigate {service_type} service performance",
                                    "Consider load balancing between services",
                                    "Optimize service-specific algorithms"
                                ]
                            })
            
            return bottlenecks
    
    def get_search_performance_report(self) -> Dict[str, Any]:
        """Generate comprehensive search performance report."""
        
        current_performance = self.get_current_search_performance()
        historical_performance = self.get_search_performance_history(24)
        bottlenecks = self.analyze_search_bottlenecks(1)
        
        # Generate recommendations
        recommendations = []
        
        if "latency_metrics" in current_performance:
            latency = current_performance["latency_metrics"]
            
            if latency["avg_latency_ms"] > 500:
                recommendations.append({
                    "priority": "high",
                    "category": "latency",
                    "issue": f"High average search latency ({latency['avg_latency_ms']:.1f}ms)",
                    "recommendation": "Optimize search algorithms and implement caching",
                    "target": "Reduce average latency to <300ms"
                })
            
            if latency["p95_latency_ms"] > 1000:
                recommendations.append({
                    "priority": "medium",
                    "category": "consistency",
                    "issue": f"High P95 latency ({latency['p95_latency_ms']:.1f}ms)",
                    "recommendation": "Investigate and optimize worst-case scenarios",
                    "target": "Reduce P95 latency to <800ms"
                })
        
        if "quality_metrics" in current_performance:
            quality = current_performance["quality_metrics"]
            
            if quality["success_rate_percent"] < 95:
                recommendations.append({
                    "priority": "critical",
                    "category": "reliability",
                    "issue": f"Low search success rate ({quality['success_rate_percent']:.1f}%)",
                    "recommendation": "Investigate and fix search failures",
                    "target": "Achieve >98% success rate"
                })
            
            if quality["cache_hit_rate_percent"] < 70:
                recommendations.append({
                    "priority": "medium",
                    "category": "efficiency",
                    "issue": f"Low cache hit rate ({quality['cache_hit_rate_percent']:.1f}%)",
                    "recommendation": "Optimize caching strategy and cache warming",
                    "target": "Achieve >80% cache hit rate"
                })
            
            if quality["fallback_usage_percent"] > 10:
                recommendations.append({
                    "priority": "medium",
                    "category": "service_health",
                    "issue": f"High fallback usage ({quality['fallback_usage_percent']:.1f}%)",
                    "recommendation": "Investigate primary service issues",
                    "target": "Reduce fallback usage to <5%"
                })
        
        return {
            "report_timestamp": datetime.now().isoformat(),
            "current_performance": current_performance,
            "historical_performance": historical_performance,
            "bottleneck_analysis": bottlenecks,
            "recommendations": recommendations,
            "performance_status": self._determine_performance_status(current_performance),
            "threshold_violations": self._check_threshold_violations(current_performance)
        }
    
    def _determine_performance_status(self, current_performance: Dict[str, Any]) -> str:
        """Determine overall search performance status."""
        
        if "error" in current_performance:
            return "unknown"
        
        latency = current_performance.get("latency_metrics", {})
        quality = current_performance.get("quality_metrics", {})
        
        # Check critical thresholds
        if (quality.get("success_rate_percent", 100) < 90 or 
            latency.get("avg_latency_ms", 0) > 1000):
            return "critical"
        
        # Check warning thresholds
        if (quality.get("success_rate_percent", 100) < 95 or 
            latency.get("avg_latency_ms", 0) > 500 or
            quality.get("fallback_usage_percent", 0) > 15):
            return "degraded"
        
        # Check for good performance
        if (quality.get("success_rate_percent", 0) > 98 and 
            latency.get("avg_latency_ms", 1000) < 300 and
            quality.get("cache_hit_rate_percent", 0) > 80):
            return "excellent"
        
        return "healthy"
    
    def _check_threshold_violations(self, current_performance: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Check for threshold violations in current performance."""
        
        violations = []
        
        if "error" in current_performance:
            return violations
        
        latency = current_performance.get("latency_metrics", {})
        quality = current_performance.get("quality_metrics", {})
        
        # Check each threshold
        for threshold in self._search_thresholds:
            current_value = None
            
            # Map threshold metric names to current performance data
            if threshold.metric_name == "avg_search_latency_ms":
                current_value = latency.get("avg_latency_ms")
            elif threshold.metric_name == "p95_search_latency_ms":
                current_value = latency.get("p95_latency_ms")
            elif threshold.metric_name == "p99_search_latency_ms":
                current_value = latency.get("p99_latency_ms")
            elif threshold.metric_name == "search_success_rate_percent":
                current_value = quality.get("success_rate_percent")
            elif threshold.metric_name == "fallback_usage_percent":
                current_value = quality.get("fallback_usage_percent")
            elif threshold.metric_name == "cache_hit_rate_percent":
                current_value = quality.get("cache_hit_rate_percent")
            
            if current_value is None:
                continue
            
            # Check for violations
            if current_value > threshold.critical_threshold:
                violations.append({
                    "metric": threshold.metric_name,
                    "severity": "critical",
                    "current_value": current_value,
                    "threshold": threshold.critical_threshold,
                    "query_type": threshold.query_type,
                    "service_type": threshold.service_type
                })
            elif current_value > threshold.warning_threshold:
                violations.append({
                    "metric": threshold.metric_name,
                    "severity": "warning",
                    "current_value": current_value,
                    "threshold": threshold.warning_threshold,
                    "query_type": threshold.query_type,
                    "service_type": threshold.service_type
                })
        
        return violations
    
    def add_alert_callback(self, callback: Callable[[PerformanceAlert], None]) -> None:
        """Add callback for search performance alerts."""
        self._alert_callbacks.append(callback)
    
    def _start_background_monitoring(self) -> None:
        """Start background monitoring and summarization."""
        
        async def monitoring_loop():
            self._monitoring_active = True
            self.logger.info("Search performance background monitoring started")
            
            while self._monitoring_active:
                try:
                    await self._generate_minute_summary()
                    await asyncio.sleep(60)  # Run every minute
                    
                except Exception as e:
                    self.logger.error(f"Error in search performance monitoring loop: {e}")
                    await asyncio.sleep(60)
        
        # Start monitoring task only if event loop is running
        try:
            asyncio.create_task(monitoring_loop())
        except RuntimeError:
            # No event loop running, skip background monitoring for now
            self.logger.info("No event loop available, background monitoring disabled")
    
    async def _generate_minute_summary(self) -> None:
        """Generate and store minute-level performance summary."""
        
        current_time = datetime.now().replace(second=0, microsecond=0)
        
        with self._lock:
            if not self._current_minute_metrics:
                return
            
            # Calculate minute summary
            successful_metrics = [m for m in self._current_minute_metrics if m.success]
            
            if successful_metrics:
                latencies = [m.total_latency_ms for m in successful_metrics]
                avg_latency = statistics.mean(latencies)
                p95_latency = sorted(latencies)[int(0.95 * len(latencies))] if len(latencies) > 1 else latencies[0]
            else:
                avg_latency = p95_latency = 0
            
            success_rate = (len(successful_metrics) / len(self._current_minute_metrics)) * 100
            cache_hit_rate = (len([m for m in self._current_minute_metrics if m.cache_hit]) / len(self._current_minute_metrics)) * 100
            fallback_rate = (len([m for m in self._current_minute_metrics if m.fallback_used]) / len(self._current_minute_metrics)) * 100
            
            minute_summary = {
                "timestamp": current_time.isoformat(),
                "total_searches": len(self._current_minute_metrics),
                "successful_searches": len(successful_metrics),
                "avg_latency_ms": round(avg_latency, 2),
                "p95_latency_ms": round(p95_latency, 2),
                "success_rate_percent": round(success_rate, 2),
                "cache_hit_rate_percent": round(cache_hit_rate, 2),
                "fallback_usage_percent": round(fallback_rate, 2)
            }
            
            self._performance_summaries.append(minute_summary)
            
            # Check thresholds on minute summary
            self._check_minute_thresholds(minute_summary)
            
            # Reset current minute metrics
            self._current_minute_metrics = []
            self._last_summary_time = current_time
    
    def _check_minute_thresholds(self, minute_summary: Dict[str, Any]) -> None:
        """Check thresholds against minute summary data."""
        
        # Check for sustained threshold violations
        for threshold in self._search_thresholds:
            if threshold.query_type or threshold.service_type:
                continue  # Skip specific type thresholds for minute summaries
            
            current_value = minute_summary.get(threshold.metric_name.replace("search_", ""))
            
            if current_value is None:
                continue
            
            # Generate alerts for sustained violations
            if current_value > threshold.critical_threshold:
                self._generate_search_alert(
                    f"sustained_{threshold.metric_name}",
                    f"Sustained {threshold.metric_name} violation: {current_value:.1f} > {threshold.critical_threshold:.1f}",
                    "critical",
                    {"metric": threshold.metric_name, "value": current_value, "threshold": threshold.critical_threshold}
                )
            elif current_value > threshold.warning_threshold:
                self._generate_search_alert(
                    f"sustained_{threshold.metric_name}",
                    f"Sustained {threshold.metric_name} warning: {current_value:.1f} > {threshold.warning_threshold:.1f}",
                    "warning",
                    {"metric": threshold.metric_name, "value": current_value, "threshold": threshold.warning_threshold}
                )
    
    def stop_monitoring(self) -> None:
        """Stop background monitoring."""
        self._monitoring_active = False
        self.logger.info("Search performance monitoring stopped")
    
    def export_performance_data(self, filepath: str, hours: int = 24) -> None:
        """Export search performance data to file."""
        
        data = {
            "export_timestamp": datetime.now().isoformat(),
            "export_period_hours": hours,
            "current_performance": self.get_current_search_performance(),
            "historical_performance": self.get_search_performance_history(hours),
            "performance_report": self.get_search_performance_report()
        }
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        
        self.logger.info(f"Search performance data exported to {filepath}")