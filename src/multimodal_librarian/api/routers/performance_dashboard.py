"""
Performance Dashboard API Router

This module provides REST API endpoints for the performance dashboard service,
enabling real-time performance monitoring, trend analysis, and alert visualization.

Validates: Requirement 6.2 - Performance monitoring and alerting
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from fastapi import APIRouter, HTTPException, status, Query, Path, Depends
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse

from ...monitoring.performance_dashboard import (
    get_performance_dashboard_service, PerformanceDashboardService
)

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/performance", tags=["performance_dashboard"])

# Service dependency
def get_dashboard_service() -> PerformanceDashboardService:
    """Get performance dashboard service instance."""
    return get_performance_dashboard_service()

# Dashboard Management Endpoints

@router.get("/dashboards")
async def get_available_dashboards(
    dashboard_service: PerformanceDashboardService = Depends(get_dashboard_service)
):
    """
    Get list of available performance dashboards.
    
    Returns dashboard metadata and configuration information.
    """
    try:
        dashboards = dashboard_service.get_available_dashboards()
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "dashboards": dashboards,
                "total_count": len(dashboards),
                "timestamp": datetime.now().isoformat()
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
    dashboard_id: str = Path(..., description="Dashboard identifier"),
    force_refresh: bool = Query(False, description="Force refresh of chart data"),
    dashboard_service: PerformanceDashboardService = Depends(get_dashboard_service)
):
    """
    Get complete dashboard data with all chart data.
    
    - **dashboard_id**: Unique dashboard identifier
    - **force_refresh**: Force refresh of cached chart data
    
    Returns dashboard configuration and real-time chart data.
    """
    try:
        dashboard_data = await dashboard_service.get_dashboard_data(dashboard_id, force_refresh)
        
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

@router.get("/dashboards/{dashboard_id}/charts/{chart_id}")
async def get_chart_data(
    dashboard_id: str = Path(..., description="Dashboard identifier"),
    chart_id: str = Path(..., description="Chart identifier"),
    force_refresh: bool = Query(False, description="Force refresh of chart data"),
    dashboard_service: PerformanceDashboardService = Depends(get_dashboard_service)
):
    """
    Get data for a specific chart within a dashboard.
    
    - **dashboard_id**: Unique dashboard identifier
    - **chart_id**: Unique chart identifier
    - **force_refresh**: Force refresh of cached chart data
    
    Returns chart configuration and data.
    """
    try:
        dashboard_data = await dashboard_service.get_dashboard_data(dashboard_id, force_refresh)
        
        if not dashboard_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Dashboard not found: {dashboard_id}"
            )
        
        # Find the specific chart
        chart_data = None
        for chart in dashboard_data["charts"]:
            if chart["chart_id"] == chart_id:
                chart_data = chart
                break
        
        if not chart_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Chart not found: {chart_id}"
            )
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=chart_data
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting chart data for {dashboard_id}/{chart_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve chart data"
        )

# Real-time Data Endpoints

@router.get("/realtime/metrics")
async def get_realtime_metrics(
    dashboard_service: PerformanceDashboardService = Depends(get_dashboard_service)
):
    """
    Get real-time performance metrics summary.
    
    Returns current performance metrics across all monitored components.
    """
    try:
        # Get real-time metrics from the underlying services
        metrics_collector = dashboard_service.metrics_collector
        search_monitor = dashboard_service.search_monitor
        performance_monitor = dashboard_service.performance_monitor
        
        realtime_metrics = metrics_collector.get_real_time_metrics()
        search_performance = search_monitor.get_current_search_performance()
        current_performance = performance_monitor.get_current_performance()
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "timestamp": datetime.now().isoformat(),
                "system_metrics": realtime_metrics,
                "search_performance": search_performance,
                "performance_monitoring": current_performance,
                "status": "healthy"
            }
        )
        
    except Exception as e:
        logger.error(f"Error getting real-time metrics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve real-time metrics"
        )

@router.get("/trends/performance")
async def get_performance_trends(
    hours: int = Query(24, ge=1, le=168, description="Number of hours to analyze (1-168)"),
    dashboard_service: PerformanceDashboardService = Depends(get_dashboard_service)
):
    """
    Get performance trends over the specified time period.
    
    - **hours**: Number of hours to analyze (1-168, default 24)
    
    Returns historical performance trends and analysis.
    """
    try:
        metrics_collector = dashboard_service.metrics_collector
        search_monitor = dashboard_service.search_monitor
        
        performance_trends = metrics_collector.get_performance_trends(hours)
        search_history = search_monitor.get_search_performance_history(hours)
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "period_hours": hours,
                "timestamp": datetime.now().isoformat(),
                "performance_trends": performance_trends,
                "search_performance_history": search_history
            }
        )
        
    except Exception as e:
        logger.error(f"Error getting performance trends: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve performance trends"
        )

@router.get("/analysis/bottlenecks")
async def get_performance_bottlenecks(
    hours: int = Query(1, ge=1, le=24, description="Number of hours to analyze"),
    dashboard_service: PerformanceDashboardService = Depends(get_dashboard_service)
):
    """
    Get performance bottleneck analysis.
    
    - **hours**: Number of hours to analyze for bottlenecks
    
    Returns detailed bottleneck analysis and recommendations.
    """
    try:
        search_monitor = dashboard_service.search_monitor
        bottlenecks = search_monitor.analyze_search_bottlenecks(hours)
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "analysis_period_hours": hours,
                "timestamp": datetime.now().isoformat(),
                "bottlenecks": bottlenecks,
                "total_bottlenecks": len(bottlenecks)
            }
        )
        
    except Exception as e:
        logger.error(f"Error getting performance bottlenecks: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve bottleneck analysis"
        )

# Export Endpoints

@router.post("/dashboards/{dashboard_id}/export")
async def export_dashboard_data(
    dashboard_id: str = Path(..., description="Dashboard identifier"),
    format: str = Query("json", regex="^(json)$", description="Export format"),
    dashboard_service: PerformanceDashboardService = Depends(get_dashboard_service)
):
    """
    Export dashboard data to file.
    
    - **dashboard_id**: Unique dashboard identifier
    - **format**: Export format (currently only 'json' supported)
    
    Returns file download link for the exported data.
    """
    try:
        filename = await dashboard_service.export_dashboard_data(dashboard_id, format)
        
        if not filename:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Dashboard not found or export failed: {dashboard_id}"
            )
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "message": "Dashboard data exported successfully",
                "filename": filename,
                "download_url": f"/api/performance/downloads/{filename}",
                "export_timestamp": datetime.now().isoformat()
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting dashboard {dashboard_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to export dashboard data"
        )

@router.get("/downloads/{filename}")
async def download_exported_file(
    filename: str = Path(..., description="Exported file name")
):
    """
    Download exported dashboard file.
    
    - **filename**: Name of the exported file
    
    Returns the exported file for download.
    """
    try:
        import os
        if not os.path.exists(filename):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found"
            )
        
        return FileResponse(
            path=filename,
            filename=filename,
            media_type="application/json"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading file {filename}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to download file"
        )

# Health and Status Endpoints

@router.get("/health")
async def get_dashboard_health(
    dashboard_service: PerformanceDashboardService = Depends(get_dashboard_service)
):
    """
    Get performance dashboard service health status.
    
    Returns health status of the dashboard service and its dependencies.
    """
    try:
        service_status = dashboard_service.get_service_status()
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "timestamp": datetime.now().isoformat(),
                **service_status
            }
        )
        
    except Exception as e:
        logger.error(f"Error getting dashboard health: {e}")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "unhealthy",
                "service": "performance_dashboard",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
        )

# Dashboard UI Endpoint

@router.get("/dashboard", response_class=HTMLResponse)
async def serve_performance_dashboard():
    """
    Serve the performance dashboard web interface.
    
    Returns HTML page for interactive performance monitoring dashboards.
    """
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Performance Dashboard - Multimodal Librarian</title>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { 
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: #f8f9fa;
                color: #333;
            }
            .header {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 20px;
                text-align: center;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }
            .nav-tabs {
                background: white;
                padding: 0 20px;
                border-bottom: 1px solid #dee2e6;
                display: flex;
                gap: 0;
            }
            .nav-tab {
                padding: 15px 25px;
                background: none;
                border: none;
                cursor: pointer;
                border-bottom: 3px solid transparent;
                font-weight: 500;
                color: #666;
                transition: all 0.3s;
            }
            .nav-tab.active {
                color: #667eea;
                border-bottom-color: #667eea;
            }
            .nav-tab:hover {
                color: #667eea;
                background: #f8f9fa;
            }
            .container {
                max-width: 1400px;
                margin: 0 auto;
                padding: 20px;
            }
            .dashboard-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
                gap: 20px;
                margin-top: 20px;
            }
            .chart-widget {
                background: white;
                border-radius: 12px;
                padding: 20px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                transition: transform 0.2s, box-shadow 0.2s;
            }
            .chart-widget:hover {
                transform: translateY(-2px);
                box-shadow: 0 4px 16px rgba(0,0,0,0.15);
            }
            .widget-header {
                display: flex;
                justify-content: between;
                align-items: center;
                margin-bottom: 15px;
                padding-bottom: 10px;
                border-bottom: 2px solid #f1f3f4;
            }
            .widget-title {
                font-size: 1.1em;
                font-weight: 600;
                color: #333;
            }
            .widget-refresh {
                background: none;
                border: none;
                color: #667eea;
                cursor: pointer;
                padding: 5px;
                border-radius: 4px;
                transition: background 0.2s;
            }
            .widget-refresh:hover {
                background: #f1f3f4;
            }
            .chart-container {
                position: relative;
                height: 300px;
            }
            .metric-value {
                font-size: 2.5em;
                font-weight: bold;
                text-align: center;
                margin: 20px 0;
            }
            .metric-excellent { color: #28a745; }
            .metric-good { color: #17a2b8; }
            .metric-warning { color: #ffc107; }
            .metric-critical { color: #dc3545; }
            .status-indicator {
                display: inline-block;
                width: 12px;
                height: 12px;
                border-radius: 50%;
                margin-right: 8px;
            }
            .status-healthy { background: #28a745; }
            .status-warning { background: #ffc107; }
            .status-critical { background: #dc3545; }
            .alert-item {
                padding: 12px;
                margin: 8px 0;
                border-radius: 8px;
                border-left: 4px solid;
                background: #f8f9fa;
            }
            .alert-critical { border-left-color: #dc3545; }
            .alert-warning { border-left-color: #ffc107; }
            .alert-info { border-left-color: #17a2b8; }
            .loading {
                text-align: center;
                padding: 40px;
                color: #666;
            }
            .error {
                text-align: center;
                padding: 40px;
                color: #dc3545;
                background: #f8d7da;
                border-radius: 8px;
                margin: 20px 0;
            }
            .refresh-indicator {
                position: fixed;
                top: 20px;
                right: 20px;
                background: #667eea;
                color: white;
                padding: 10px 15px;
                border-radius: 20px;
                font-size: 0.9em;
                opacity: 0;
                transition: opacity 0.3s;
            }
            .refresh-indicator.show {
                opacity: 1;
            }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>📊 Performance Dashboard</h1>
            <p>Real-time performance monitoring and analytics</p>
        </div>
        
        <div class="nav-tabs">
            <button class="nav-tab active" onclick="switchTab('realtime')">Real-time</button>
            <button class="nav-tab" onclick="switchTab('trends')">Trends</button>
            <button class="nav-tab" onclick="switchTab('search')">Search Performance</button>
        </div>
        
        <div class="refresh-indicator" id="refreshIndicator">Refreshing data...</div>
        
        <div class="container">
            <div id="realtime-dashboard" class="dashboard-content">
                <div class="dashboard-grid" id="realtime-grid">
                    <div class="loading">Loading real-time dashboard...</div>
                </div>
            </div>
            
            <div id="trends-dashboard" class="dashboard-content" style="display: none;">
                <div class="dashboard-grid" id="trends-grid">
                    <div class="loading">Loading trends dashboard...</div>
                </div>
            </div>
            
            <div id="search-dashboard" class="dashboard-content" style="display: none;">
                <div class="dashboard-grid" id="search-grid">
                    <div class="loading">Loading search performance dashboard...</div>
                </div>
            </div>
        </div>
        
        <script>
            let currentTab = 'realtime';
            let refreshInterval;
            let charts = {};
            
            // Tab switching
            function switchTab(tabName) {
                // Update tab buttons
                document.querySelectorAll('.nav-tab').forEach(tab => {
                    tab.classList.remove('active');
                });
                event.target.classList.add('active');
                
                // Update dashboard content
                document.querySelectorAll('.dashboard-content').forEach(content => {
                    content.style.display = 'none';
                });
                document.getElementById(tabName + '-dashboard').style.display = 'block';
                
                currentTab = tabName;
                loadDashboard(tabName);
            }
            
            // Load dashboard data
            async function loadDashboard(dashboardType) {
                const dashboardMap = {
                    'realtime': 'realtime_performance',
                    'trends': 'performance_trends',
                    'search': 'search_performance'
                };
                
                const dashboardId = dashboardMap[dashboardType];
                const gridId = dashboardType + '-grid';
                
                try {
                    showRefreshIndicator();
                    
                    const response = await fetch(`/api/performance/dashboards/${dashboardId}`);
                    if (!response.ok) throw new Error('Failed to load dashboard');
                    
                    const dashboardData = await response.json();
                    renderDashboard(dashboardData, gridId);
                    
                } catch (error) {
                    console.error('Error loading dashboard:', error);
                    document.getElementById(gridId).innerHTML = 
                        '<div class="error">Failed to load dashboard data. Please try again.</div>';
                } finally {
                    hideRefreshIndicator();
                }
            }
            
            // Render dashboard
            function renderDashboard(dashboardData, gridId) {
                const grid = document.getElementById(gridId);
                grid.innerHTML = '';
                
                dashboardData.charts.forEach(chart => {
                    const widget = createChartWidget(chart);
                    grid.appendChild(widget);
                });
            }
            
            // Create chart widget
            function createChartWidget(chartData) {
                const widget = document.createElement('div');
                widget.className = 'chart-widget';
                widget.innerHTML = `
                    <div class="widget-header">
                        <div class="widget-title">${chartData.title}</div>
                        <button class="widget-refresh" onclick="refreshChart('${chartData.chart_id}')">🔄</button>
                    </div>
                    <div class="chart-container">
                        <canvas id="chart-${chartData.chart_id}"></canvas>
                    </div>
                `;
                
                // Render chart after DOM insertion
                setTimeout(() => renderChart(chartData), 100);
                
                return widget;
            }
            
            // Render individual chart
            function renderChart(chartData) {
                const ctx = document.getElementById(`chart-${chartData.chart_id}`);
                if (!ctx) return;
                
                // Destroy existing chart
                if (charts[chartData.chart_id]) {
                    charts[chartData.chart_id].destroy();
                }
                
                const config = createChartConfig(chartData);
                charts[chartData.chart_id] = new Chart(ctx, config);
            }
            
            // Create Chart.js configuration
            function createChartConfig(chartData) {
                const type = chartData.chart_type;
                const data = chartData.data_points;
                
                if (type === 'gauge') {
                    return createGaugeChart(chartData);
                } else if (type === 'alert_list') {
                    return createAlertList(chartData);
                } else if (type === 'table') {
                    return createTable(chartData);
                }
                
                // Standard chart types
                const config = {
                    type: type === 'area' ? 'line' : type,
                    data: {
                        labels: data.map(d => d.label || d.timestamp || ''),
                        datasets: [{
                            label: chartData.title,
                            data: data.map(d => d.value),
                            backgroundColor: chartData.config.color || '#667eea',
                            borderColor: chartData.config.color || '#667eea',
                            fill: type === 'area'
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: {
                                display: type === 'pie'
                            }
                        },
                        scales: type !== 'pie' ? {
                            y: {
                                beginAtZero: true
                            }
                        } : {}
                    }
                };
                
                return config;
            }
            
            // Create gauge chart (using doughnut chart)
            function createGaugeChart(chartData) {
                const data = chartData.data_points[0];
                const value = data ? data.value : 0;
                const maxValue = chartData.config.max_value || 2000;
                
                return {
                    type: 'doughnut',
                    data: {
                        datasets: [{
                            data: [value, maxValue - value],
                            backgroundColor: ['#667eea', '#e9ecef'],
                            borderWidth: 0
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        circumference: 180,
                        rotation: 270,
                        cutout: '80%',
                        plugins: {
                            legend: { display: false },
                            tooltip: { enabled: false }
                        }
                    }
                };
            }
            
            // Create alert list (custom rendering)
            function createAlertList(chartData) {
                const container = document.getElementById(`chart-${chartData.chart_id}`).parentElement;
                const alerts = chartData.data_points;
                
                let html = '';
                if (alerts.length === 0) {
                    html = '<div style="text-align: center; padding: 40px; color: #28a745;">No active alerts</div>';
                } else {
                    alerts.forEach(alert => {
                        html += `
                            <div class="alert-item alert-${alert.severity}">
                                <div style="font-weight: 600;">${alert.title}</div>
                                <div style="font-size: 0.9em; margin-top: 4px;">${alert.message}</div>
                                <div style="font-size: 0.8em; color: #666; margin-top: 4px;">
                                    ${new Date(alert.timestamp).toLocaleString()}
                                </div>
                            </div>
                        `;
                    });
                }
                
                container.innerHTML = html;
                return null; // No Chart.js chart needed
            }
            
            // Show/hide refresh indicator
            function showRefreshIndicator() {
                document.getElementById('refreshIndicator').classList.add('show');
            }
            
            function hideRefreshIndicator() {
                setTimeout(() => {
                    document.getElementById('refreshIndicator').classList.remove('show');
                }, 500);
            }
            
            // Refresh specific chart
            async function refreshChart(chartId) {
                // Implementation would refresh individual chart
                console.log('Refreshing chart:', chartId);
            }
            
            // Auto-refresh
            function startAutoRefresh() {
                refreshInterval = setInterval(() => {
                    loadDashboard(currentTab);
                }, 30000); // Refresh every 30 seconds
            }
            
            function stopAutoRefresh() {
                if (refreshInterval) {
                    clearInterval(refreshInterval);
                }
            }
            
            // Initialize
            document.addEventListener('DOMContentLoaded', () => {
                loadDashboard('realtime');
                startAutoRefresh();
            });
            
            // Cleanup on page unload
            window.addEventListener('beforeunload', () => {
                stopAutoRefresh();
            });
        </script>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html_content)

@router.get("/dashboard/{dashboard_id}", response_class=HTMLResponse)
async def serve_specific_dashboard(
    dashboard_id: str = Path(..., description="Dashboard identifier")
):
    """
    Serve a specific performance dashboard.
    
    - **dashboard_id**: Unique dashboard identifier
    
    Returns HTML page for the specified dashboard.
    """
    # For now, redirect to main dashboard with tab selection
    # In a full implementation, this would render the specific dashboard
    return await serve_performance_dashboard()