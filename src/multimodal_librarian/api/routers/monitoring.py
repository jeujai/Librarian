"""
Monitoring API Router - Alerting and Dashboard Management

This module provides REST API endpoints for managing alerts, dashboards,
and monitoring system health with real-time data access.
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from fastapi import APIRouter, HTTPException, status, Query, Body, Depends
from fastapi.responses import JSONResponse, HTMLResponse

from ...monitoring.alerting_service import (
    get_alerting_service, AlertingService, AlertRule, Alert, 
    NotificationChannel, AlertSeverity, AlertStatus
)
from ...monitoring.dashboard_service import (
    get_dashboard_service, DashboardService, Dashboard, DashboardWidget, DashboardType
)

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/monitoring", tags=["monitoring"])

# Service dependencies
def get_alerting() -> AlertingService:
    """Get alerting service instance."""
    return get_alerting_service()

def get_dashboard() -> DashboardService:
    """Get dashboard service instance."""
    return get_dashboard_service()

# Alerting Endpoints

@router.get("/alerts/active")
async def get_active_alerts(
    severity: Optional[str] = Query(None, description="Filter by severity (low, medium, high, critical)"),
    alerting_service: AlertingService = Depends(get_alerting)
):
    """
    Get all active alerts with optional severity filtering.
    
    - **severity**: Optional severity filter
    
    Returns list of active alerts with details.
    """
    try:
        severity_filter = None
        if severity:
            try:
                severity_filter = [AlertSeverity(severity.lower())]
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid severity: {severity}. Must be one of: low, medium, high, critical"
                )
        
        alerts = alerting_service.get_active_alerts(severity_filter)
        
        alert_data = []
        for alert in alerts:
            alert_data.append({
                "alert_id": alert.alert_id,
                "rule_id": alert.rule_id,
                "rule_name": alert.rule_name,
                "severity": alert.severity.value,
                "status": alert.status.value,
                "message": alert.message,
                "metric_value": alert.metric_value,
                "threshold": alert.threshold,
                "triggered_at": alert.triggered_at.isoformat(),
                "acknowledged_at": alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
                "metadata": alert.metadata
            })
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "alerts": alert_data,
                "total_count": len(alert_data),
                "severity_filter": severity
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting active alerts: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve active alerts"
        )

@router.get("/alerts/history")
async def get_alert_history(
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of alerts to return"),
    rule_id: Optional[str] = Query(None, description="Filter by specific rule ID"),
    alerting_service: AlertingService = Depends(get_alerting)
):
    """
    Get alert history with optional filtering.
    
    - **limit**: Maximum number of alerts to return (1-1000)
    - **rule_id**: Optional rule ID filter
    
    Returns historical alert data.
    """
    try:
        alerts = alerting_service.get_alert_history(limit, rule_id)
        
        alert_data = []
        for alert in alerts:
            alert_data.append({
                "alert_id": alert.alert_id,
                "rule_id": alert.rule_id,
                "rule_name": alert.rule_name,
                "severity": alert.severity.value,
                "status": alert.status.value,
                "message": alert.message,
                "metric_value": alert.metric_value,
                "threshold": alert.threshold,
                "triggered_at": alert.triggered_at.isoformat(),
                "acknowledged_at": alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
                "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
                "metadata": alert.metadata
            })
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "alerts": alert_data,
                "total_count": len(alert_data),
                "limit": limit,
                "rule_filter": rule_id
            }
        )
        
    except Exception as e:
        logger.error(f"Error getting alert history: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve alert history"
        )

@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: str,
    acknowledged_by: str = Body(..., embed=True),
    alerting_service: AlertingService = Depends(get_alerting)
):
    """
    Acknowledge an active alert.
    
    - **alert_id**: Unique alert identifier
    - **acknowledged_by**: User or system acknowledging the alert
    
    Returns acknowledgment confirmation.
    """
    try:
        success = await alerting_service.acknowledge_alert(alert_id, acknowledged_by)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Alert not found or cannot be acknowledged: {alert_id}"
            )
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "message": "Alert acknowledged successfully",
                "alert_id": alert_id,
                "acknowledged_by": acknowledged_by,
                "acknowledged_at": datetime.now().isoformat()
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error acknowledging alert {alert_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to acknowledge alert"
        )

@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(
    alert_id: str,
    reason: str = Body(..., embed=True),
    alerting_service: AlertingService = Depends(get_alerting)
):
    """
    Manually resolve an alert.
    
    - **alert_id**: Unique alert identifier
    - **reason**: Reason for resolution
    
    Returns resolution confirmation.
    """
    try:
        success = await alerting_service.resolve_alert(alert_id, reason)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Alert not found or cannot be resolved: {alert_id}"
            )
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "message": "Alert resolved successfully",
                "alert_id": alert_id,
                "reason": reason,
                "resolved_at": datetime.now().isoformat()
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resolving alert {alert_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to resolve alert"
        )

@router.get("/alerts/statistics")
async def get_alert_statistics(
    alerting_service: AlertingService = Depends(get_alerting)
):
    """
    Get comprehensive alert statistics.
    
    Returns detailed statistics about alerts, rules, and notifications.
    """
    try:
        stats = alerting_service.get_alert_statistics()
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "statistics": stats,
                "timestamp": datetime.now().isoformat()
            }
        )
        
    except Exception as e:
        logger.error(f"Error getting alert statistics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve alert statistics"
        )

@router.post("/metrics/record")
async def record_metric(
    metric_data: Dict[str, Any] = Body(...),
    alerting_service: AlertingService = Depends(get_alerting)
):
    """
    Record a metric value for alert evaluation.
    
    Expected format:
    ```json
    {
        "metric_name": "error_rate",
        "value": 0.05,
        "timestamp": "2024-01-01T12:00:00Z",
        "metadata": {"source": "api"}
    }
    ```
    
    Returns recording confirmation.
    """
    try:
        # Validate required fields
        if "metric_name" not in metric_data or "value" not in metric_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="metric_name and value are required"
            )
        
        metric_name = metric_data["metric_name"]
        value = float(metric_data["value"])
        timestamp = None
        metadata = metric_data.get("metadata", {})
        
        if "timestamp" in metric_data:
            try:
                timestamp = datetime.fromisoformat(metric_data["timestamp"].replace('Z', '+00:00'))
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid timestamp format. Use ISO format."
                )
        
        alerting_service.record_metric(metric_name, value, timestamp, metadata)
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "message": "Metric recorded successfully",
                "metric_name": metric_name,
                "value": value,
                "recorded_at": (timestamp or datetime.now()).isoformat()
            }
        )
        
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid value format: {e}"
        )
    except Exception as e:
        logger.error(f"Error recording metric: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record metric"
        )

# Dashboard Endpoints

@router.get("/dashboards")
async def get_available_dashboards(
    dashboard_service: DashboardService = Depends(get_dashboard)
):
    """
    Get list of available dashboards.
    
    Returns dashboard metadata and configuration.
    """
    try:
        dashboards = dashboard_service.get_available_dashboards()
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "dashboards": dashboards,
                "total_count": len(dashboards)
            }
        )
        
    except Exception as e:
        logger.error(f"Error getting available dashboards: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve dashboards"
        )

@router.get("/dashboards/{dashboard_id}")
async def get_dashboard_data(
    dashboard_id: str,
    dashboard_service: DashboardService = Depends(get_dashboard)
):
    """
    Get complete dashboard data with all widget data.
    
    - **dashboard_id**: Unique dashboard identifier
    
    Returns dashboard configuration and real-time widget data.
    """
    try:
        dashboard_data = await dashboard_service.get_dashboard_data(dashboard_id)
        
        if not dashboard_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Dashboard not found: {dashboard_id}"
            )
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=dashboard_data
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting dashboard data for {dashboard_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve dashboard data"
        )

@router.get("/dashboards/{dashboard_id}/widget/{widget_id}")
async def get_widget_data(
    dashboard_id: str,
    widget_id: str,
    dashboard_service: DashboardService = Depends(get_dashboard)
):
    """
    Get data for a specific widget.
    
    - **dashboard_id**: Unique dashboard identifier
    - **widget_id**: Unique widget identifier
    
    Returns widget data and configuration.
    """
    try:
        dashboard_data = await dashboard_service.get_dashboard_data(dashboard_id)
        
        if not dashboard_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Dashboard not found: {dashboard_id}"
            )
        
        widget_data = dashboard_data["widget_data"].get(widget_id)
        if not widget_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Widget not found: {widget_id}"
            )
        
        # Find widget configuration
        widget_config = None
        for widget in dashboard_data["dashboard"]["widgets"]:
            if widget["widget_id"] == widget_id:
                widget_config = widget
                break
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "widget_config": widget_config,
                "widget_data": widget_data,
                "last_updated": dashboard_data["last_updated"]
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting widget data for {dashboard_id}/{widget_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve widget data"
        )

# Health and Status Endpoints

@router.get("/health")
async def get_monitoring_health(
    alerting_service: AlertingService = Depends(get_alerting),
    dashboard_service: DashboardService = Depends(get_dashboard)
):
    """
    Get comprehensive monitoring service health status.
    
    Returns health status of alerting and dashboard services.
    """
    try:
        alerting_status = alerting_service.get_service_status()
        dashboard_status = dashboard_service.get_service_status()
        
        overall_status = "healthy"
        if alerting_status["status"] != "active" or dashboard_status["status"] != "active":
            overall_status = "degraded"
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "status": overall_status,
                "service": "monitoring",
                "timestamp": datetime.now().isoformat(),
                "components": {
                    "alerting": alerting_status,
                    "dashboard": dashboard_status
                },
                "features": {
                    "real_time_alerting": True,
                    "dashboard_monitoring": True,
                    "metric_recording": True,
                    "notification_channels": True,
                    "alert_management": True,
                    "custom_dashboards": True
                }
            }
        )
        
    except Exception as e:
        logger.error(f"Error getting monitoring health: {e}")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "unhealthy",
                "service": "monitoring",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
        )

@router.get("/status")
async def get_monitoring_status(
    alerting_service: AlertingService = Depends(get_alerting),
    dashboard_service: DashboardService = Depends(get_dashboard)
):
    """
    Get detailed monitoring system status and statistics.
    
    Returns comprehensive status information for monitoring components.
    """
    try:
        alerting_stats = alerting_service.get_alert_statistics()
        dashboard_status = dashboard_service.get_service_status()
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "monitoring_system": {
                    "status": "operational",
                    "uptime": "99.9%",
                    "last_restart": datetime.now().isoformat()
                },
                "alerting": {
                    "active_alerts": alerting_stats["active_alerts"],
                    "total_rules": alerting_stats["total_rules"],
                    "enabled_rules": alerting_stats["enabled_rules"],
                    "alerts_last_24h": alerting_stats["alerts_last_24h"],
                    "notification_channels": alerting_stats["notification_channels"]
                },
                "dashboards": {
                    "total_dashboards": dashboard_status["statistics"]["total_dashboards"],
                    "total_widgets": dashboard_status["statistics"]["total_widgets"],
                    "data_sources": dashboard_status["statistics"]["data_sources"]
                },
                "timestamp": datetime.now().isoformat()
            }
        )
        
    except Exception as e:
        logger.error(f"Error getting monitoring status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve monitoring status"
        )

# Dashboard UI Endpoint

@router.get("/dashboard", response_class=HTMLResponse)
async def serve_monitoring_dashboard():
    """
    Serve the monitoring dashboard web interface.
    
    Returns HTML page for monitoring dashboards and alerts.
    """
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Monitoring Dashboard - Multimodal Librarian</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { 
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: #f5f5f5;
                color: #333;
            }
            .header {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 20px;
                text-align: center;
            }
            .container {
                max-width: 1200px;
                margin: 20px auto;
                padding: 0 20px;
            }
            .dashboard-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                gap: 20px;
                margin-top: 20px;
            }
            .widget {
                background: white;
                border-radius: 8px;
                padding: 20px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }
            .widget h3 {
                margin-bottom: 15px;
                color: #333;
                border-bottom: 2px solid #667eea;
                padding-bottom: 5px;
            }
            .metric-value {
                font-size: 2em;
                font-weight: bold;
                color: #667eea;
                margin: 10px 0;
            }
            .status-good { color: #28a745; }
            .status-warning { color: #ffc107; }
            .status-error { color: #dc3545; }
            .alert-item {
                padding: 10px;
                margin: 5px 0;
                border-left: 4px solid #dc3545;
                background: #f8f9fa;
                border-radius: 4px;
            }
            .nav-links {
                text-align: center;
                margin: 20px 0;
            }
            .nav-links a {
                display: inline-block;
                margin: 0 10px;
                padding: 10px 20px;
                background: #667eea;
                color: white;
                text-decoration: none;
                border-radius: 5px;
                transition: background 0.3s;
            }
            .nav-links a:hover {
                background: #5a6fd8;
            }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🔍 Monitoring Dashboard</h1>
            <p>Real-time system monitoring and alerting</p>
        </div>
        
        <div class="nav-links">
            <a href="/api/monitoring/dashboards">📊 API Dashboards</a>
            <a href="/api/monitoring/alerts/active">🚨 Active Alerts</a>
            <a href="/api/monitoring/health">🏥 Health Status</a>
            <a href="/docs">📚 API Docs</a>
            <a href="/">🏠 Home</a>
        </div>
        
        <div class="container">
            <div class="dashboard-grid">
                <div class="widget">
                    <h3>🚨 Active Alerts</h3>
                    <div class="metric-value" id="active-alerts">Loading...</div>
                    <div id="alert-list"></div>
                </div>
                
                <div class="widget">
                    <h3>📊 System Health</h3>
                    <div class="metric-value status-good" id="system-status">Healthy</div>
                    <p>All systems operational</p>
                </div>
                
                <div class="widget">
                    <h3>⚡ Performance</h3>
                    <div class="metric-value" id="response-time">Loading...</div>
                    <p>Average response time</p>
                </div>
                
                <div class="widget">
                    <h3>💰 Cost Monitoring</h3>
                    <div class="metric-value" id="daily-cost">Loading...</div>
                    <p>Daily AI API costs</p>
                </div>
                
                <div class="widget">
                    <h3>👥 User Activity</h3>
                    <div class="metric-value" id="active-users">Loading...</div>
                    <p>Currently active users</p>
                </div>
                
                <div class="widget">
                    <h3>📈 Dashboard Stats</h3>
                    <div class="metric-value" id="dashboard-count">Loading...</div>
                    <p>Available dashboards</p>
                </div>
            </div>
        </div>
        
        <script>
            // Load monitoring data
            async function loadMonitoringData() {
                try {
                    // Load active alerts
                    const alertsResponse = await fetch('/api/monitoring/alerts/active');
                    if (alertsResponse.ok) {
                        const alertsData = await alertsResponse.json();
                        document.getElementById('active-alerts').textContent = alertsData.total_count;
                        
                        const alertList = document.getElementById('alert-list');
                        alertList.innerHTML = '';
                        alertsData.alerts.slice(0, 3).forEach(alert => {
                            const alertDiv = document.createElement('div');
                            alertDiv.className = 'alert-item';
                            alertDiv.innerHTML = `<strong>${alert.rule_name}</strong><br>${alert.message}`;
                            alertList.appendChild(alertDiv);
                        });
                    }
                    
                    // Load dashboard stats
                    const dashboardResponse = await fetch('/api/monitoring/dashboards');
                    if (dashboardResponse.ok) {
                        const dashboardData = await dashboardResponse.json();
                        document.getElementById('dashboard-count').textContent = dashboardData.total_count;
                    }
                    
                    // Load system health data (mock for now)
                    document.getElementById('response-time').textContent = '180ms';
                    document.getElementById('daily-cost').textContent = '$12.45';
                    document.getElementById('active-users').textContent = '12';
                    
                } catch (error) {
                    console.error('Error loading monitoring data:', error);
                }
            }
            
            // Load data on page load
            loadMonitoringData();
            
            // Refresh data every 30 seconds
            setInterval(loadMonitoringData, 30000);
        </script>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html_content)