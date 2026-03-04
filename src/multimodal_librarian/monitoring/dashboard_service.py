"""
Dashboard Service - Comprehensive system monitoring dashboards

This service provides real-time dashboards for system health, performance,
cost monitoring, and user activity metrics with CloudWatch integration.
"""

import asyncio
import json
import time
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger(__name__)

class DashboardType(Enum):
    """Dashboard types."""
    SYSTEM_HEALTH = "system_health"
    PERFORMANCE = "performance"
    COST_MONITORING = "cost_monitoring"
    USER_ACTIVITY = "user_activity"
    SECURITY = "security"
    CUSTOM = "custom"

@dataclass
class DashboardWidget:
    """Dashboard widget configuration."""
    widget_id: str
    title: str
    type: str  # chart, metric, table, alert_list
    data_source: str
    query: str
    refresh_interval: int = 60  # seconds
    config: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.config is None:
            self.config = {}

@dataclass
class Dashboard:
    """Dashboard configuration."""
    dashboard_id: str
    name: str
    description: str
    type: DashboardType
    widgets: List[DashboardWidget]
    layout: Dict[str, Any] = None
    auto_refresh: bool = True
    refresh_interval: int = 30  # seconds
    
    def __post_init__(self):
        if self.layout is None:
            self.layout = {"columns": 2, "rows": "auto"}

class DashboardService:
    """
    Comprehensive dashboard service for system monitoring.
    
    Provides real-time dashboards with customizable widgets and
    integration with various data sources.
    """
    
    def __init__(self):
        self.dashboards: Dict[str, Dashboard] = {}
        self.widget_data_cache: Dict[str, Dict[str, Any]] = {}
        self.data_sources: Dict[str, Any] = {}
        
        # Initialize data sources
        self._initialize_data_sources()
        
        # Initialize default dashboards
        self._initialize_default_dashboards()
        
        logger.info("Dashboard service initialized")
    
    def _initialize_data_sources(self):
        """Initialize available data sources."""
        self.data_sources = {
            "logging_service": {
                "type": "internal",
                "description": "Internal logging service metrics"
            },
            "alerting_service": {
                "type": "internal", 
                "description": "Internal alerting service data"
            },
            "cache_service": {
                "type": "internal",
                "description": "Cache service statistics"
            },
            "ai_service": {
                "type": "internal",
                "description": "AI service usage and costs"
            },
            "system_metrics": {
                "type": "internal",
                "description": "System resource metrics"
            },
            "cloudwatch": {
                "type": "external",
                "description": "AWS CloudWatch metrics",
                "enabled": False  # Would need AWS configuration
            }
        }
    
    def _initialize_default_dashboards(self):
        """Initialize default system dashboards."""
        
        # System Health Dashboard
        system_health_widgets = [
            DashboardWidget(
                widget_id="system_status",
                title="System Status",
                type="metric",
                data_source="system_metrics",
                query="system.status",
                config={"format": "status", "color_coding": True}
            ),
            DashboardWidget(
                widget_id="error_rate",
                title="Error Rate",
                type="chart",
                data_source="logging_service",
                query="errors.rate_per_minute",
                config={"chart_type": "line", "time_range": "1h"}
            ),
            DashboardWidget(
                widget_id="response_time",
                title="Average Response Time",
                type="chart",
                data_source="logging_service", 
                query="performance.avg_response_time",
                config={"chart_type": "line", "time_range": "1h", "unit": "ms"}
            ),
            DashboardWidget(
                widget_id="active_alerts",
                title="Active Alerts",
                type="alert_list",
                data_source="alerting_service",
                query="alerts.active",
                config={"max_items": 10, "severity_filter": ["high", "critical"]}
            )
        ]
        
        self.add_dashboard(Dashboard(
            dashboard_id="system_health",
            name="System Health",
            description="Overall system health and status monitoring",
            type=DashboardType.SYSTEM_HEALTH,
            widgets=system_health_widgets
        ))
        
        # Performance Dashboard
        performance_widgets = [
            DashboardWidget(
                widget_id="cpu_usage",
                title="CPU Usage",
                type="chart",
                data_source="system_metrics",
                query="system.cpu_percent",
                config={"chart_type": "area", "time_range": "2h", "unit": "%"}
            ),
            DashboardWidget(
                widget_id="memory_usage", 
                title="Memory Usage",
                type="chart",
                data_source="system_metrics",
                query="system.memory_percent",
                config={"chart_type": "area", "time_range": "2h", "unit": "%"}
            ),
            DashboardWidget(
                widget_id="cache_performance",
                title="Cache Hit Rate",
                type="metric",
                data_source="cache_service",
                query="cache.hit_rate",
                config={"format": "percentage", "threshold": 80}
            ),
            DashboardWidget(
                widget_id="request_throughput",
                title="Request Throughput",
                type="chart",
                data_source="logging_service",
                query="requests.per_minute",
                config={"chart_type": "bar", "time_range": "1h"}
            )
        ]
        
        self.add_dashboard(Dashboard(
            dashboard_id="performance",
            name="Performance Metrics",
            description="System performance and resource utilization",
            type=DashboardType.PERFORMANCE,
            widgets=performance_widgets
        ))
        
        # Cost Monitoring Dashboard
        cost_widgets = [
            DashboardWidget(
                widget_id="daily_ai_cost",
                title="Daily AI API Costs",
                type="metric",
                data_source="ai_service",
                query="costs.daily_total",
                config={"format": "currency", "currency": "USD"}
            ),
            DashboardWidget(
                widget_id="cost_trend",
                title="Cost Trend (7 days)",
                type="chart",
                data_source="ai_service",
                query="costs.daily_trend",
                config={"chart_type": "line", "time_range": "7d", "unit": "USD"}
            ),
            DashboardWidget(
                widget_id="cost_by_provider",
                title="Cost by AI Provider",
                type="chart",
                data_source="ai_service",
                query="costs.by_provider",
                config={"chart_type": "pie", "time_range": "24h"}
            ),
            DashboardWidget(
                widget_id="token_usage",
                title="Token Usage",
                type="chart",
                data_source="ai_service",
                query="usage.tokens_per_hour",
                config={"chart_type": "bar", "time_range": "24h"}
            )
        ]
        
        self.add_dashboard(Dashboard(
            dashboard_id="cost_monitoring",
            name="Cost Monitoring",
            description="AI API costs and usage tracking",
            type=DashboardType.COST_MONITORING,
            widgets=cost_widgets
        ))
        
        # User Activity Dashboard
        activity_widgets = [
            DashboardWidget(
                widget_id="active_users",
                title="Active Users",
                type="metric",
                data_source="logging_service",
                query="users.active_count",
                config={"format": "number", "time_range": "1h"}
            ),
            DashboardWidget(
                widget_id="user_sessions",
                title="User Sessions",
                type="chart",
                data_source="logging_service",
                query="sessions.per_hour",
                config={"chart_type": "line", "time_range": "24h"}
            ),
            DashboardWidget(
                widget_id="document_uploads",
                title="Document Uploads",
                type="chart",
                data_source="logging_service",
                query="documents.uploads_per_hour",
                config={"chart_type": "bar", "time_range": "24h"}
            ),
            DashboardWidget(
                widget_id="chat_messages",
                title="Chat Messages",
                type="chart",
                data_source="logging_service",
                query="chat.messages_per_hour",
                config={"chart_type": "line", "time_range": "24h"}
            )
        ]
        
        self.add_dashboard(Dashboard(
            dashboard_id="user_activity",
            name="User Activity",
            description="User engagement and activity metrics",
            type=DashboardType.USER_ACTIVITY,
            widgets=activity_widgets
        ))
    
    def add_dashboard(self, dashboard: Dashboard) -> bool:
        """Add or update a dashboard."""
        try:
            self.dashboards[dashboard.dashboard_id] = dashboard
            logger.info(f"Added dashboard: {dashboard.name} ({dashboard.dashboard_id})")
            return True
        except Exception as e:
            logger.error(f"Failed to add dashboard {dashboard.dashboard_id}: {e}")
            return False
    
    def remove_dashboard(self, dashboard_id: str) -> bool:
        """Remove a dashboard."""
        try:
            if dashboard_id in self.dashboards:
                dashboard = self.dashboards.pop(dashboard_id)
                logger.info(f"Removed dashboard: {dashboard.name} ({dashboard_id})")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to remove dashboard {dashboard_id}: {e}")
            return False
    
    async def get_dashboard_data(self, dashboard_id: str) -> Optional[Dict[str, Any]]:
        """Get complete dashboard data with all widget data."""
        if dashboard_id not in self.dashboards:
            return None
        
        dashboard = self.dashboards[dashboard_id]
        
        # Get data for all widgets
        widget_data = {}
        for widget in dashboard.widgets:
            try:
                data = await self._get_widget_data(widget)
                widget_data[widget.widget_id] = data
            except Exception as e:
                logger.error(f"Failed to get data for widget {widget.widget_id}: {e}")
                widget_data[widget.widget_id] = {"error": str(e)}
        
        return {
            "dashboard": asdict(dashboard),
            "widget_data": widget_data,
            "last_updated": datetime.now().isoformat(),
            "auto_refresh": dashboard.auto_refresh,
            "refresh_interval": dashboard.refresh_interval
        }
    
    async def _get_widget_data(self, widget: DashboardWidget) -> Dict[str, Any]:
        """Get data for a specific widget."""
        data_source = widget.data_source
        query = widget.query
        
        # Mock data generation based on data source and query
        # In a real implementation, this would query actual data sources
        
        if data_source == "system_metrics":
            return await self._get_system_metrics_data(query, widget.config)
        elif data_source == "logging_service":
            return await self._get_logging_service_data(query, widget.config)
        elif data_source == "alerting_service":
            return await self._get_alerting_service_data(query, widget.config)
        elif data_source == "cache_service":
            return await self._get_cache_service_data(query, widget.config)
        elif data_source == "ai_service":
            return await self._get_ai_service_data(query, widget.config)
        else:
            return {"error": f"Unknown data source: {data_source}"}
    
    async def _get_system_metrics_data(self, query: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Get system metrics data."""
        import psutil
        
        if query == "system.status":
            return {
                "value": "healthy",
                "status": "ok",
                "color": "green"
            }
        elif query == "system.cpu_percent":
            # Generate time series data
            now = datetime.now()
            data_points = []
            for i in range(60):  # Last 60 minutes
                timestamp = now - timedelta(minutes=i)
                value = psutil.cpu_percent() + (i * 0.1)  # Mock trending data
                data_points.append({
                    "timestamp": timestamp.isoformat(),
                    "value": min(100, max(0, value))
                })
            return {
                "data_points": list(reversed(data_points)),
                "current_value": psutil.cpu_percent(),
                "unit": "%"
            }
        elif query == "system.memory_percent":
            memory = psutil.virtual_memory()
            now = datetime.now()
            data_points = []
            for i in range(60):
                timestamp = now - timedelta(minutes=i)
                value = memory.percent + (i * 0.05)
                data_points.append({
                    "timestamp": timestamp.isoformat(),
                    "value": min(100, max(0, value))
                })
            return {
                "data_points": list(reversed(data_points)),
                "current_value": memory.percent,
                "unit": "%"
            }
        else:
            return {"error": f"Unknown system metrics query: {query}"}
    
    async def _get_logging_service_data(self, query: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Get logging service data."""
        # Mock logging service data
        now = datetime.now()
        
        if query == "errors.rate_per_minute":
            data_points = []
            for i in range(60):
                timestamp = now - timedelta(minutes=i)
                # Mock error rate with some variation
                value = max(0, 2 + (i % 10) - 5)
                data_points.append({
                    "timestamp": timestamp.isoformat(),
                    "value": value
                })
            return {
                "data_points": list(reversed(data_points)),
                "current_value": 1.2,
                "unit": "errors/min"
            }
        elif query == "performance.avg_response_time":
            data_points = []
            for i in range(60):
                timestamp = now - timedelta(minutes=i)
                value = 150 + (i % 20) * 10  # Mock response time
                data_points.append({
                    "timestamp": timestamp.isoformat(),
                    "value": value
                })
            return {
                "data_points": list(reversed(data_points)),
                "current_value": 180,
                "unit": "ms"
            }
        elif query == "requests.per_minute":
            data_points = []
            for i in range(60):
                timestamp = now - timedelta(minutes=i)
                value = 50 + (i % 15) * 5
                data_points.append({
                    "timestamp": timestamp.isoformat(),
                    "value": value
                })
            return {
                "data_points": list(reversed(data_points)),
                "current_value": 65,
                "unit": "requests/min"
            }
        elif query == "users.active_count":
            return {
                "value": 12,
                "unit": "users"
            }
        elif query == "sessions.per_hour":
            data_points = []
            for i in range(24):
                timestamp = now - timedelta(hours=i)
                value = 20 + (i % 8) * 3
                data_points.append({
                    "timestamp": timestamp.isoformat(),
                    "value": value
                })
            return {
                "data_points": list(reversed(data_points)),
                "unit": "sessions/hour"
            }
        elif query == "documents.uploads_per_hour":
            data_points = []
            for i in range(24):
                timestamp = now - timedelta(hours=i)
                value = 5 + (i % 6) * 2
                data_points.append({
                    "timestamp": timestamp.isoformat(),
                    "value": value
                })
            return {
                "data_points": list(reversed(data_points)),
                "unit": "uploads/hour"
            }
        elif query == "chat.messages_per_hour":
            data_points = []
            for i in range(24):
                timestamp = now - timedelta(hours=i)
                value = 100 + (i % 12) * 10
                data_points.append({
                    "timestamp": timestamp.isoformat(),
                    "value": value
                })
            return {
                "data_points": list(reversed(data_points)),
                "unit": "messages/hour"
            }
        else:
            return {"error": f"Unknown logging service query: {query}"}
    
    async def _get_alerting_service_data(self, query: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Get alerting service data."""
        try:
            from .alerting_service import get_alerting_service
            alerting_service = get_alerting_service()
            
            if query == "alerts.active":
                active_alerts = alerting_service.get_active_alerts()
                max_items = config.get("max_items", 10)
                severity_filter = config.get("severity_filter", [])
                
                if severity_filter:
                    from .alerting_service import AlertSeverity
                    severity_enum_filter = [AlertSeverity(s) for s in severity_filter]
                    active_alerts = [a for a in active_alerts if a.severity in severity_enum_filter]
                
                alert_data = []
                for alert in active_alerts[:max_items]:
                    alert_data.append({
                        "id": alert.alert_id,
                        "rule_name": alert.rule_name,
                        "severity": alert.severity.value,
                        "message": alert.message,
                        "triggered_at": alert.triggered_at.isoformat(),
                        "status": alert.status.value
                    })
                
                return {
                    "alerts": alert_data,
                    "total_count": len(active_alerts)
                }
            else:
                return {"error": f"Unknown alerting service query: {query}"}
        except Exception as e:
            return {"error": f"Failed to get alerting data: {e}"}
    
    async def _get_cache_service_data(self, query: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Get cache service data."""
        # Mock cache service data
        if query == "cache.hit_rate":
            return {
                "value": 85.6,
                "unit": "%",
                "status": "good" if 85.6 >= config.get("threshold", 80) else "warning"
            }
        else:
            return {"error": f"Unknown cache service query: {query}"}
    
    async def _get_ai_service_data(self, query: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Get AI service data."""
        # Mock AI service data
        now = datetime.now()
        
        if query == "costs.daily_total":
            return {
                "value": 12.45,
                "unit": "USD",
                "currency": "USD"
            }
        elif query == "costs.daily_trend":
            data_points = []
            for i in range(7):
                timestamp = now - timedelta(days=i)
                value = 10 + (i % 3) * 2 + (i * 0.5)
                data_points.append({
                    "timestamp": timestamp.isoformat(),
                    "value": value
                })
            return {
                "data_points": list(reversed(data_points)),
                "unit": "USD"
            }
        elif query == "costs.by_provider":
            return {
                "data_points": [
                    {"label": "Gemini", "value": 8.50},
                    {"label": "OpenAI", "value": 3.20},
                    {"label": "Anthropic", "value": 0.75}
                ],
                "unit": "USD"
            }
        elif query == "usage.tokens_per_hour":
            data_points = []
            for i in range(24):
                timestamp = now - timedelta(hours=i)
                value = 1000 + (i % 8) * 200
                data_points.append({
                    "timestamp": timestamp.isoformat(),
                    "value": value
                })
            return {
                "data_points": list(reversed(data_points)),
                "unit": "tokens/hour"
            }
        else:
            return {"error": f"Unknown AI service query: {query}"}
    
    def get_available_dashboards(self) -> List[Dict[str, Any]]:
        """Get list of available dashboards."""
        return [
            {
                "dashboard_id": dashboard.dashboard_id,
                "name": dashboard.name,
                "description": dashboard.description,
                "type": dashboard.type.value,
                "widget_count": len(dashboard.widgets),
                "auto_refresh": dashboard.auto_refresh,
                "refresh_interval": dashboard.refresh_interval
            }
            for dashboard in self.dashboards.values()
        ]
    
    def get_service_status(self) -> Dict[str, Any]:
        """Get dashboard service status."""
        return {
            "status": "active",
            "service": "dashboard",
            "features": {
                "real_time_dashboards": True,
                "custom_widgets": True,
                "multiple_data_sources": True,
                "auto_refresh": True,
                "responsive_design": True
            },
            "statistics": {
                "total_dashboards": len(self.dashboards),
                "total_widgets": sum(len(d.widgets) for d in self.dashboards.values()),
                "data_sources": len(self.data_sources),
                "enabled_data_sources": len([ds for ds in self.data_sources.values() if ds.get("enabled", True)])
            },
            "data_sources": self.data_sources
        }

# Global dashboard service instance
_dashboard_service_instance = None

def get_dashboard_service() -> DashboardService:
    """Get the global dashboard service instance."""
    global _dashboard_service_instance
    if _dashboard_service_instance is None:
        _dashboard_service_instance = DashboardService()
    return _dashboard_service_instance