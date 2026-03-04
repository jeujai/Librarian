"""
Health Dashboard Router

This module provides the web interface for the health check dashboard,
serving the HTML template and handling dashboard-specific API endpoints.
"""

from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import os
from pathlib import Path

from ...config.config_factory import get_database_config

router = APIRouter(prefix="/health", tags=["Health Dashboard"])

# Get the templates directory
templates_dir = Path(__file__).parent.parent.parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))


async def get_local_environment_check():
    """Dependency to check if we're in local development environment."""
    config = get_database_config()
    return getattr(config, 'database_type', 'unknown') == 'local'


@router.get("/dashboard", response_class=HTMLResponse)
async def health_dashboard(
    request: Request,
    is_local: bool = Depends(get_local_environment_check)
):
    """
    Serve the health check dashboard interface.
    
    This endpoint serves the main health dashboard HTML page with all the
    necessary CSS and JavaScript for monitoring local database services.
    
    Args:
        request: FastAPI request object
        is_local: Whether we're in local development environment
    
    Returns:
        HTML response with the health dashboard interface
    """
    context = {
        "request": request,
        "title": "Health Check Dashboard - Multimodal Librarian",
        "is_local_environment": is_local,
        "environment_type": "Local Development" if is_local else "Production",
        "dashboard_version": "1.0.0"
    }
    
    return templates.TemplateResponse("health_dashboard.html", context)


@router.get("/dashboard/status")
async def dashboard_status(is_local: bool = Depends(get_local_environment_check)):
    """
    Get dashboard status information.
    
    This endpoint provides basic information about the dashboard
    and the current environment configuration.
    
    Returns:
        Dashboard status and configuration information
    """
    return {
        "dashboard_available": True,
        "environment": "local" if is_local else "production",
        "features": {
            "real_time_monitoring": is_local,
            "service_health_checks": is_local,
            "connectivity_monitoring": is_local,
            "performance_metrics": is_local,
            "dependency_tracking": is_local
        },
        "endpoints": {
            "comprehensive_health": "/api/health/local/" if is_local else None,
            "service_health": "/api/health/local/{service}" if is_local else None,
            "connectivity": "/api/health/local/connectivity" if is_local else None,
            "performance": "/api/health/local/performance" if is_local else None,
            "dependencies": "/api/health/local/dependencies" if is_local else None,
            "realtime": "/api/health/local/connectivity/realtime" if is_local else None
        }
    }


@router.get("/dashboard/config")
async def dashboard_config(is_local: bool = Depends(get_local_environment_check)):
    """
    Get dashboard configuration settings.
    
    This endpoint provides configuration information that the dashboard
    JavaScript can use to customize its behavior.
    
    Returns:
        Dashboard configuration settings
    """
    if not is_local:
        return {
            "error": "Health dashboard is only available in local development environment",
            "available": False
        }
    
    return {
        "available": True,
        "refresh_interval": 30000,  # 30 seconds
        "monitoring_interval": 10000,  # 10 seconds
        "realtime_max_duration": 300,  # 5 minutes
        "chart_animation": True,
        "auto_refresh": True,
        "services": {
            "postgres": {
                "name": "PostgreSQL",
                "icon": "🐘",
                "enabled": True,
                "endpoint": "/api/health/local/postgres"
            },
            "neo4j": {
                "name": "Neo4j",
                "icon": "🕸️",
                "enabled": True,
                "endpoint": "/api/health/local/neo4j"
            },
            "milvus": {
                "name": "Milvus",
                "icon": "🔍",
                "enabled": True,
                "endpoint": "/api/health/local/milvus"
            },
            "redis": {
                "name": "Redis",
                "icon": "⚡",
                "enabled": True,
                "endpoint": "/api/health/local/redis"
            }
        },
        "thresholds": {
            "response_time_warning": 1000,  # ms
            "response_time_critical": 5000,  # ms
            "pool_utilization_warning": 80,  # %
            "pool_utilization_critical": 95,  # %
            "connectivity_warning": 95,  # %
            "connectivity_critical": 90   # %
        }
    }